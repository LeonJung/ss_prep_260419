"""DriveToPoseState — HFSM SubStep wrapper for the /drive_to_pose action.

The action server (`drive_to_pose_server` in mw_skill_library) implements
a 3-phase P-controller (rotate-to-heading → drive → rotate-to-yaw) against
`/cmd_vel` and `/odom`.  This state gives a BehaviorSM a way to invoke it.

Parameter resolution is deliberately flexible to match both authoring
styles we care about:

    1. Constants at construction ("waypoint spelled inline"):
         DriveToPoseState(node, target_x=1.0, target_y=0.0, target_yaw=0.0)

    2. Lookup from userdata ("parameter pipeline"):
         DriveToPoseState(node)
         # and upstream writes userdata['target_x'] etc before execute()

    3. Mixed (e.g. fixed pose, variable tolerance):
         DriveToPoseState(node, target_x=1.0, target_y=0.0, target_yaw=0.0)
         # userdata['xy_tolerance'] = 0.01 etc

Required userdata keys when constructor values are omitted:
  target_x, target_y, target_yaw

Written back to userdata after SUCCEEDED:
  final_x, final_y, final_yaw
"""

from __future__ import annotations

from typing import Any

from mw_hfsm_engine import Userdata, register_state
from mw_hfsm_ros import LifecycleAwareActionState
from mw_task_msgs.action import DriveToPose


_REQUIRED_KEYS = ('target_x', 'target_y', 'target_yaw')
_OPTIONAL_KEYS = (
    'xy_tolerance',
    'yaw_tolerance',
    'max_linear_velocity',
    'max_angular_velocity',
)


@register_state
class DriveToPoseState(LifecycleAwareActionState):
    """Invoke the drive_to_pose action, lifecycle-aware."""

    action_type = DriveToPose
    action_name = '/drive_to_pose'
    # drive_to_pose_server is currently a plain rclcpp::Node (not a
    # LifecycleNode) because it owns raw /cmd_vel + /odom and has no
    # managed state beyond "alive".  Skip the /get_state probe; if a
    # future server becomes lifecycle-managed, override this attribute
    # in a subclass or construct with server_node_name='drive_to_pose_server'.
    server_node_name = None

    def __init__(
        self,
        node: Any,
        *,
        target_x: float | None = None,
        target_y: float | None = None,
        target_yaw: float | None = None,
        xy_tolerance: float | None = None,
        yaw_tolerance: float | None = None,
        max_linear_velocity: float | None = None,
        max_angular_velocity: float | None = None,
    ) -> None:
        super().__init__(node=node)
        # Store "override" values; None means "read from userdata at exec time".
        self._fixed: dict[str, float | None] = {
            'target_x': target_x,
            'target_y': target_y,
            'target_yaw': target_yaw,
            'xy_tolerance': xy_tolerance,
            'yaw_tolerance': yaw_tolerance,
            'max_linear_velocity': max_linear_velocity,
            'max_angular_velocity': max_angular_velocity,
        }

    # ------------------------------------------------------------------
    def build_goal(self, userdata: Userdata) -> DriveToPose.Goal:
        goal = DriveToPose.Goal()
        for key in _REQUIRED_KEYS:
            setattr(goal, key, self._resolve_required(key, userdata))
        for key in _OPTIONAL_KEYS:
            value = self._resolve_optional(key, userdata)
            if value is not None:
                setattr(goal, key, value)
        return goal

    def on_result(self, userdata: Userdata, result: DriveToPose.Result) -> None:
        userdata['final_x'] = result.final_x
        userdata['final_y'] = result.final_y
        userdata['final_yaw'] = result.final_yaw

    # ------------------------------------------------------------------
    # Parameter resolution
    # ------------------------------------------------------------------
    def _resolve_required(self, key: str, userdata: Userdata) -> float:
        fixed = self._fixed.get(key)
        if fixed is not None:
            return float(fixed)
        if key in userdata:
            return float(userdata[key])
        raise KeyError(
            f'{type(self).__name__}: required "{key}" neither passed to '
            f'constructor nor present in userdata'
        )

    def _resolve_optional(self, key: str, userdata: Userdata) -> float | None:
        fixed = self._fixed.get(key)
        if fixed is not None:
            return float(fixed)
        if key in userdata:
            return float(userdata[key])
        return None  # let the action's default kick in
