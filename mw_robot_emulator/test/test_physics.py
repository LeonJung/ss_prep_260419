"""Pure-logic tests for the RobotState dataclasses + motor physics step.

Does not spin ROS — exercises the numerical update by manipulating the
VirtualRobot._update_physics loop indirectly. For higher-level integration
tests see mw_bringup/scripts/self_test.py.
"""

from __future__ import annotations

import math
import time

import pytest
import rclpy

from mw_task_msgs.msg import MotorStatus
from mw_robot_emulator.virtual_robot_node import VirtualRobot


@pytest.fixture(scope='module')
def node():
    rclpy.init()
    n = VirtualRobot()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _advance(node: VirtualRobot, seconds: float, step: float = 0.02) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=step)


def test_motor_reaches_target(node):
    m = node.state.ensure_motor('test_a')
    m.position = 0.0
    m.target_position = 1.0
    m.max_velocity = 2.0
    _advance(node, 1.0)
    assert math.isclose(m.position, 1.0, abs_tol=0.02)
    assert m.velocity == pytest.approx(0.0, abs=1e-3)


def test_stuck_motor_does_not_move(node):
    m = node.state.ensure_motor('test_b')
    m.position = 0.0
    m.target_position = 2.0
    m.max_velocity = 1.0
    m.status = MotorStatus.STATUS_STUCK
    _advance(node, 0.5)
    assert m.position == 0.0


def test_dead_motor_rejects_target(node):
    req = type('R', (), {'motor_id': 'test_c',
                         'target_position': 5.0,
                         'max_velocity': 1.0})()
    resp = type('P', (), {'accepted': None, 'message': ''})()
    m = node.state.ensure_motor('test_c')
    m.status = MotorStatus.STATUS_DEAD
    out = node._set_target_cb(req, resp)
    assert out.accepted is False
