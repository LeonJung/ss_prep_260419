"""Lifecycle supervisor for mw Task Manager skill servers.

Layer 3 of the 3-layer resilience design:
  Layer 1  OS respawn (ros2 launch respawn=True + systemd)
  Layer 2  rclcpp_lifecycle::LifecycleNode per skill
  Layer 3  (this file) — auto-transition skills to ACTIVE after launch or
           after Layer 1 respawn, attempt recovery on error

Implementation notes:
  - All service calls use async + done_callback (never rclpy.spin_once from
    a timer — that triggers "Executor is already spinning").
  - A single atomic 'in_flight' flag per skill prevents racing transitions.
  - If /<skill>/get_state service is unreachable, the skill process is
    assumed dead; Layer 1 respawn will give us a fresh unconfigured node
    that the next poll transitions forward automatically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List

import rclpy
from rclpy.node import Node

from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState


IN_FLIGHT_TIMEOUT_SEC = 3.0


@dataclass
class ManagedSkill:
    name: str
    get_state_cli: object = None
    change_state_cli: object = None
    last_state: int = State.PRIMARY_STATE_UNKNOWN
    in_flight: bool = False
    in_flight_deadline: float = 0.0


class SkillSupervisor(Node):

    STATE_LABELS = {
        State.PRIMARY_STATE_UNKNOWN: 'unknown',
        State.PRIMARY_STATE_UNCONFIGURED: 'unconfigured',
        State.PRIMARY_STATE_INACTIVE: 'inactive',
        State.PRIMARY_STATE_ACTIVE: 'active',
        State.PRIMARY_STATE_FINALIZED: 'finalized',
    }

    def __init__(self) -> None:
        super().__init__('mw_skill_supervisor')
        self.declare_parameter(
            'managed_nodes',
            ['move_motor_server', 'capture_image_server'])
        self.declare_parameter('poll_hz', 2.0)

        managed: List[str] = list(self.get_parameter(
            'managed_nodes').get_parameter_value().string_array_value)
        poll_hz = self.get_parameter('poll_hz').value

        self.skills: Dict[str, ManagedSkill] = {}
        for name in managed:
            skill = ManagedSkill(name=name)
            skill.get_state_cli = self.create_client(
                GetState, f'/{name}/get_state')
            skill.change_state_cli = self.create_client(
                ChangeState, f'/{name}/change_state')
            self.skills[name] = skill

        self.create_timer(1.0 / max(poll_hz, 0.1), self._poll_all)
        self.get_logger().info(
            f'supervisor managing {list(self.skills.keys())}')

    # ------------------------------------------------------------------
    def _poll_all(self) -> None:
        for skill in self.skills.values():
            self._kick(skill)

    def _kick(self, skill: ManagedSkill) -> None:
        if skill.in_flight:
            # If the peer died mid-call the done_callback never fires;
            # fall back to a wallclock deadline so we can recover.
            if time.monotonic() > skill.in_flight_deadline:
                self.get_logger().warn(
                    f'{skill.name}: in-flight call timed out, resetting')
                skill.in_flight = False
            else:
                return
        if not skill.get_state_cli.service_is_ready():
            # Skill process likely dead (or hasn't come up yet). When it
            # returns via Layer 1 respawn the service will reappear and
            # we'll pick it up next poll. Mark unknown so we re-log the
            # first observed state when it reappears.
            if skill.last_state != State.PRIMARY_STATE_UNKNOWN:
                self.get_logger().warn(
                    f'{skill.name}: service offline — waiting for respawn')
            skill.last_state = State.PRIMARY_STATE_UNKNOWN
            return

        req = GetState.Request()
        fut = skill.get_state_cli.call_async(req)
        skill.in_flight = True
        skill.in_flight_deadline = time.monotonic() + IN_FLIGHT_TIMEOUT_SEC
        fut.add_done_callback(
            lambda f, s=skill: self._on_state(s, f))

    def _on_state(self, skill: ManagedSkill, fut) -> None:
        try:
            resp = fut.result()
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(
                f'{skill.name}: get_state exception {e}')
            skill.in_flight = False
            return
        if resp is None:
            skill.in_flight = False
            return
        state_id = resp.current_state.id
        if state_id != skill.last_state:
            self.get_logger().info(
                f'{skill.name}: state -> {self._label(state_id)}')
            skill.last_state = state_id

        # Decide next transition toward ACTIVE.
        transition = None
        if state_id == State.PRIMARY_STATE_UNCONFIGURED:
            transition = Transition.TRANSITION_CONFIGURE
        elif state_id == State.PRIMARY_STATE_INACTIVE:
            transition = Transition.TRANSITION_ACTIVATE
        elif state_id == State.PRIMARY_STATE_FINALIZED:
            # Finalized skills only recover via process restart (Layer 1).
            self.get_logger().warn(
                f'{skill.name}: finalized, awaiting respawn')

        if transition is None:
            skill.in_flight = False
            return
        self._fire_transition(skill, transition)

    def _fire_transition(self, skill: ManagedSkill, transition_id: int) -> None:
        if not skill.change_state_cli.service_is_ready():
            skill.in_flight = False
            return
        req = ChangeState.Request()
        req.transition.id = transition_id
        fut = skill.change_state_cli.call_async(req)
        skill.in_flight_deadline = time.monotonic() + IN_FLIGHT_TIMEOUT_SEC
        fut.add_done_callback(
            lambda f, s=skill, t=transition_id:
                self._on_transition_done(s, t, f))

    def _on_transition_done(
        self, skill: ManagedSkill, transition_id: int, fut,
    ) -> None:
        skill.in_flight = False
        try:
            r = fut.result()
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(
                f'{skill.name}: transition {transition_id} exception {e}')
            return
        ok = bool(r and r.success)
        self.get_logger().info(
            f'{skill.name}: transition {transition_id} '
            f'-> {"ok" if ok else "FAILED"}')

    def _label(self, state_id: int) -> str:
        return self.STATE_LABELS.get(state_id, f'state_{state_id}')


def main() -> None:
    rclpy.init()
    node = SkillSupervisor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
