"""mw_hfsm_ros — ROS 2 integration for mw_hfsm_engine.

Currently provides:
- LifecycleAwareActionState: generic State that calls a ROS 2 action on a
  lifecycle-managed skill server, auto-activating it if needed.
"""

from .lifecycle_action_state import (
    ActionOutcome,
    LifecycleAwareActionState,
)

__all__ = [
    'ActionOutcome',
    'LifecycleAwareActionState',
]
