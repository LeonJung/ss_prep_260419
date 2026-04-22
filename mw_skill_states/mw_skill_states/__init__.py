"""mw_skill_states — HFSM State wrappers around mw_skill_library actions.

One file per skill action.  Each concrete State inherits
LifecycleAwareActionState, fills in build_goal + on_result, and exposes a
constructor that accepts either constants (waypoint-in-XML style) or
defers to userdata keys (parametric pipeline style).
"""

from .drive_to_pose import DriveToPoseState

__all__ = ['DriveToPoseState']
