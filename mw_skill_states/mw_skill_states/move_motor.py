"""MoveMotorState — HFSM SubStep wrapper for the /move_motor action.

The action server (`move_motor_server` in mw_skill_library) drives a named
motor to a target position with a simple velocity-limited closed loop.

Parameter resolution mirrors DriveToPoseState:

    1. Constants at construction:
         MoveMotorState(node, motor_id='gripper_pitch', target_position=0.5)

    2. Lookup from userdata:
         MoveMotorState(node)   # userdata['motor_id'], userdata['target_position']

    3. Mix — e.g. fixed motor, variable target:
         MoveMotorState(node, motor_id='gripper_pitch')
         # userdata['target_position'] = 0.8

Required userdata keys when constructor values are omitted:
  motor_id (string), target_position (float)

Written back to userdata after SUCCEEDED:
  final_position (float)
"""

from __future__ import annotations

from typing import Any

from mw_hfsm_engine import Userdata, register_state
from mw_hfsm_ros import LifecycleAwareActionState
from mw_task_msgs.action import MoveMotor


@register_state
class MoveMotorState(LifecycleAwareActionState):
    """Invoke the move_motor action, lifecycle-aware."""

    action_type = MoveMotor
    action_name = '/move_motor'
    server_node_name = 'move_motor_server'

    def __init__(
        self,
        node: Any,
        *,
        motor_id: str | None = None,
        target_position: float | None = None,
        max_velocity: float | None = None,
    ) -> None:
        super().__init__(node=node)
        self._motor_id = motor_id
        self._target_position = target_position
        self._max_velocity = max_velocity

    # ------------------------------------------------------------------
    def build_goal(self, userdata: Userdata) -> MoveMotor.Goal:
        goal = MoveMotor.Goal()
        goal.motor_id = _require_str(self, 'motor_id', self._motor_id, userdata)
        goal.target_position = _require_float(
            self, 'target_position', self._target_position, userdata,
        )
        mv = _optional_float('max_velocity', self._max_velocity, userdata)
        if mv is not None:
            goal.max_velocity = mv
        return goal

    def on_result(self, userdata: Userdata, result: MoveMotor.Result) -> None:
        userdata['final_position'] = result.final_position


# ---------------------------------------------------------------------------
# Tiny private resolution helpers.  Shared across skill states lives in
# this module for now; promote to a util module once a third state appears.
# ---------------------------------------------------------------------------

def _require_str(
    state: LifecycleAwareActionState, key: str,
    fixed: str | None, userdata: Userdata,
) -> str:
    if fixed is not None:
        return str(fixed)
    if key in userdata:
        return str(userdata[key])
    raise KeyError(
        f'{type(state).__name__}: required "{key}" neither passed to '
        f'constructor nor present in userdata'
    )


def _require_float(
    state: LifecycleAwareActionState, key: str,
    fixed: float | None, userdata: Userdata,
) -> float:
    if fixed is not None:
        return float(fixed)
    if key in userdata:
        return float(userdata[key])
    raise KeyError(
        f'{type(state).__name__}: required "{key}" neither passed to '
        f'constructor nor present in userdata'
    )


def _optional_float(
    key: str, fixed: float | None, userdata: Userdata,
) -> float | None:
    if fixed is not None:
        return float(fixed)
    if key in userdata:
        return float(userdata[key])
    return None
