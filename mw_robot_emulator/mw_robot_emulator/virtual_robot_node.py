"""Virtual robot emulator.

Central state-holder used by mock skill action servers so that:
  - motor motion is physically modeled (velocity-limited integration)
  - faults can be injected from a test driver (stuck motor, dead camera, low
    battery) to exercise abnormal-case subtrees in the BT
  - /joint_states is published at a steady rate so rviz/Foxglove can
    visualize robot state without any extra plumbing

Topics published:
  /joint_states                (sensor_msgs/JointState, 30 Hz)
  /virtual_robot/motor_status  (mw_task_msgs/MotorStatusArray, 30 Hz)
  /battery_state               (sensor_msgs/BatteryState, 1 Hz)

Services exposed:
  /virtual_robot/set_motor_target (mw_task_msgs/srv/SetMotorTarget)
  /virtual_robot/capture_image    (mw_task_msgs/srv/RequestCapture)
  /virtual_robot/inject_fault     (mw_task_msgs/srv/InjectFault)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, JointState

from mw_task_msgs.msg import MotorStatus, MotorStatusArray
from mw_task_msgs.srv import (
    InjectFault, RequestCapture, ResetRobot, SetMotorTarget,
)


@dataclass
class Motor:
    motor_id: str
    position: float = 0.0
    velocity: float = 0.0
    target_position: float = 0.0
    max_velocity: float = 1.0
    status: int = MotorStatus.STATUS_OK


@dataclass
class Camera:
    camera_id: str
    available: bool = True


@dataclass
class Battery:
    level: float = 1.0        # 0.0 .. 1.0
    drain_rate: float = 0.0   # per second (set >0 to simulate use)


@dataclass
class RobotState:
    motors: Dict[str, Motor] = field(default_factory=dict)
    cameras: Dict[str, Camera] = field(default_factory=dict)
    battery: Battery = field(default_factory=Battery)

    def ensure_motor(self, motor_id: str) -> Motor:
        m = self.motors.get(motor_id)
        if m is None:
            m = Motor(motor_id=motor_id)
            self.motors[motor_id] = m
        return m

    def ensure_camera(self, camera_id: str) -> Camera:
        c = self.cameras.get(camera_id)
        if c is None:
            c = Camera(camera_id=camera_id)
            self.cameras[camera_id] = c
        return c


class VirtualRobot(Node):

    UPDATE_HZ = 50.0
    STATUS_HZ = 30.0
    BATTERY_HZ = 1.0
    TOLERANCE = 1e-3

    def __init__(self) -> None:
        super().__init__('virtual_robot')

        self.state = RobotState()
        # Seed the motors referenced by demo_fetch_cup so /joint_states has
        # content from startup and tests can inspect them before the first
        # set_motor_target call.
        for mid in ('base_x', 'base_yaw', 'arm_shoulder', 'arm_gripper'):
            self.state.ensure_motor(mid)
        self.state.ensure_camera('head_rgb')

        self.joint_pub = self.create_publisher(JointState, '/joint_states', 10)
        self.status_pub = self.create_publisher(
            MotorStatusArray, '/virtual_robot/motor_status', 10)
        self.battery_pub = self.create_publisher(
            BatteryState, '/battery_state', 10)

        self.create_service(
            SetMotorTarget, '/virtual_robot/set_motor_target',
            self._set_target_cb)
        self.create_service(
            RequestCapture, '/virtual_robot/capture_image',
            self._capture_cb)
        self.create_service(
            InjectFault, '/virtual_robot/inject_fault',
            self._inject_fault_cb)
        self.create_service(
            ResetRobot, '/virtual_robot/reset',
            self._reset_cb)

        self._last_update = self.get_clock().now()
        self.create_timer(1.0 / self.UPDATE_HZ, self._update_physics)
        self.create_timer(1.0 / self.STATUS_HZ, self._publish_status)
        self.create_timer(1.0 / self.BATTERY_HZ, self._publish_battery)

        self.get_logger().info('virtual robot ready')

    # ---- service callbacks ----

    def _set_target_cb(self, req, resp):
        if req.motor_id == '':
            resp.accepted = False
            resp.message = 'motor_id is empty'
            return resp
        m = self.state.ensure_motor(req.motor_id)
        if m.status == MotorStatus.STATUS_DEAD:
            resp.accepted = False
            resp.message = f'motor {req.motor_id} is dead'
            return resp
        m.target_position = req.target_position
        m.max_velocity = max(1e-3, req.max_velocity)
        resp.accepted = True
        resp.message = 'ok'
        return resp

    def _capture_cb(self, req, resp):
        cam = self.state.ensure_camera(req.camera_id)
        if not cam.available:
            resp.success = False
            resp.image_path = ''
            resp.message = f'camera {req.camera_id} unavailable'
            return resp
        resp.success = True
        resp.image_path = req.save_path or f'/tmp/mw_capture_{req.camera_id}.jpg'
        resp.message = 'ok'
        return resp

    def _inject_fault_cb(self, req, resp):
        target = req.target
        kind = req.kind
        try:
            if target.startswith('motor:'):
                mid = target.split(':', 1)[1]
                m = self.state.ensure_motor(mid)
                m.status = self._motor_kind_to_status(kind)
                resp.applied = True
                resp.message = f'motor {mid} -> {kind}'
            elif target.startswith('camera:'):
                cid = target.split(':', 1)[1]
                c = self.state.ensure_camera(cid)
                c.available = (kind == 'clear')
                resp.applied = True
                resp.message = f'camera {cid} -> {kind}'
            elif target == 'battery':
                self.state.battery.level = max(0.0, min(1.0, req.parameter))
                resp.applied = True
                resp.message = f'battery -> {self.state.battery.level:.2f}'
            else:
                resp.applied = False
                resp.message = f'unknown target: {target!r}'
        except Exception as e:  # noqa: BLE001
            resp.applied = False
            resp.message = str(e)
        return resp

    def _reset_cb(self, _req, resp):
        for m in self.state.motors.values():
            m.position = 0.0
            m.velocity = 0.0
            m.target_position = 0.0
            m.status = MotorStatus.STATUS_OK
        for c in self.state.cameras.values():
            c.available = True
        self.state.battery.level = 1.0
        self.state.battery.drain_rate = 0.0
        resp.success = True
        resp.message = 'reset ok'
        self.get_logger().info('virtual robot reset')
        return resp

    @staticmethod
    def _motor_kind_to_status(kind: str) -> int:
        mapping = {
            'clear': MotorStatus.STATUS_OK,
            'stuck': MotorStatus.STATUS_STUCK,
            'dead': MotorStatus.STATUS_DEAD,
            'unreachable': MotorStatus.STATUS_UNREACHABLE,
        }
        if kind not in mapping:
            raise ValueError(f'unknown motor fault kind: {kind!r}')
        return mapping[kind]

    # ---- physics loop ----

    def _update_physics(self) -> None:
        now = self.get_clock().now()
        dt = (now - self._last_update).nanoseconds * 1e-9
        self._last_update = now
        if dt <= 0:
            return

        for m in self.state.motors.values():
            if m.status != MotorStatus.STATUS_OK:
                # Stuck/dead motors do not move regardless of target.
                m.velocity = 0.0
                continue
            delta = m.target_position - m.position
            step = m.max_velocity * dt
            if abs(delta) <= step:
                m.position = m.target_position
                m.velocity = 0.0
            else:
                direction = math.copysign(1.0, delta)
                m.position += direction * step
                m.velocity = direction * m.max_velocity

        if self.state.battery.drain_rate > 0:
            self.state.battery.level = max(
                0.0, self.state.battery.level
                - self.state.battery.drain_rate * dt)

    # ---- publishers ----

    def _publish_status(self) -> None:
        stamp = self.get_clock().now().to_msg()

        js = JointState()
        js.header.stamp = stamp
        js.name = list(self.state.motors.keys())
        js.position = [m.position for m in self.state.motors.values()]
        js.velocity = [m.velocity for m in self.state.motors.values()]
        self.joint_pub.publish(js)

        arr = MotorStatusArray()
        arr.stamp = stamp
        for m in self.state.motors.values():
            s = MotorStatus()
            s.motor_id = m.motor_id
            s.position = m.position
            s.velocity = m.velocity
            s.target_position = m.target_position
            s.status = m.status
            arr.motors.append(s)
        self.status_pub.publish(arr)

    def _publish_battery(self) -> None:
        msg = BatteryState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.percentage = float(self.state.battery.level)
        msg.present = True
        self.battery_pub.publish(msg)


def main() -> None:
    rclpy.init()
    node = VirtualRobot()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
