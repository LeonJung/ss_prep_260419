"""VisitThreePoints — canonical SubJob that drives a robot through three
2D poses using DriveToPoseState.

Structure mirrors the doc hierarchy:

    SubJob  VisitThreePoints
      ├─ Step  GO_P1
      │    └─ SubStep  drive  (DriveToPoseState @ waypoint 1)
      ├─ Step  GO_P2
      │    └─ SubStep  drive  (DriveToPoseState @ waypoint 2)
      └─ Step  GO_P3
           └─ SubStep  drive  (DriveToPoseState @ waypoint 3)

Each Step is a single-SubStep StateMachine.  Successful DriveToPose
returns 'succeeded' which the Step maps to its own 'done'; failure
modes of DriveToPoseState (failed / lifecycle_error / timeout /
rejected) all bubble up to the SubJob's 'failed' outcome.

Waypoints match the original BT config (job_visit_three_points.xml) so
that existing Gazebo TurtleBot3 demos keep landing in the same spots.

Run end-to-end:

    ros2 launch mw_bringup navigate_test.launch.py \\
        subjob_modules:="['mw_hfsm_examples']"
    # in another terminal:
    ros2 action send_goal /mw_task_manager/execute_sub_job \\
        mw_task_msgs/action/ExecuteSubJob '{subjob_id: "VisitThreePoints"}'
"""

from __future__ import annotations

from typing import Any

from mw_hfsm_engine import (
    BehaviorSM,
    StateMachine,
    register_state,
)
from mw_hfsm_ros import ActionOutcome
from mw_skill_states import DriveToPoseState


# Waypoints inherited verbatim from the pre-HFSM
# mw_task_manager/config/job_visit_three_points.xml.
_WAYPOINTS = [
    ('P1', 1.0, 0.0, 0.0),
    ('P2', 1.0, 1.0, 1.5707963),   # ~90°
    ('P3', -1.0, 0.5, 3.14159),    # ~180°
]


def _build_go_step(node: Any, x: float, y: float, yaw: float) -> StateMachine:
    """A single-SubStep Step that drives to (x, y, yaw).

    Any of DriveToPoseState's failure outcomes collapses to 'failed' at
    the Step boundary so the SubJob's transition table stays shallow.
    """
    step = StateMachine(outcomes=['done', 'failed'])
    step.add(
        'drive',
        DriveToPoseState(node=node, target_x=x, target_y=y, target_yaw=yaw),
        transitions={
            ActionOutcome.SUCCEEDED: 'done',
            ActionOutcome.FAILED: 'failed',
            ActionOutcome.LIFECYCLE_ERROR: 'failed',
            ActionOutcome.TIMEOUT: 'failed',
            ActionOutcome.REJECTED: 'failed',
        },
    )
    return step


@register_state
class VisitThreePoints(BehaviorSM):
    """Visit three fixed waypoints in order.  Any leg's failure aborts."""

    outcomes = ['done', 'failed']
    behavior_parameters: list[str] = []

    def __init__(self, node: Any = None):
        super().__init__()
        for i, (name, x, y, yaw) in enumerate(_WAYPOINTS):
            is_last = i == len(_WAYPOINTS) - 1
            on_done = 'done' if is_last else f'GO_{_WAYPOINTS[i + 1][0]}'
            self.add(
                f'GO_{name}',
                _build_go_step(node, x, y, yaw),
                transitions={'done': on_done, 'failed': 'failed'},
            )
