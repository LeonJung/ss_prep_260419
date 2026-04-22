"""Unit tests for DriveToPoseState — mocks the action client so no ROS graph.

Focuses on the wrapper's responsibilities: parameter resolution (constants
at construction, fallback to userdata, optional keys, missing-required
error) and the round-trip through LifecycleAwareActionState internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from action_msgs.msg import GoalStatus

from mw_hfsm_engine import Userdata
from mw_hfsm_ros import ActionOutcome
from mw_skill_states import DriveToPoseState


# ---------------------------------------------------------------------------
# Fake rclpy pieces — same pattern as mw_hfsm_ros tests
# ---------------------------------------------------------------------------


class _FakeFuture:
    def __init__(self, value):
        self._value = value

    def done(self) -> bool:
        return True

    def result(self):
        return self._value


@dataclass
class _GoalHandle:
    accepted: bool
    result_future_value: object

    def get_result_async(self):
        return _FakeFuture(self.result_future_value)


class _FakeActionClient:
    def __init__(self, result_value):
        self._result_value = result_value
        self.sent_goals: list[object] = []

    def wait_for_server(self, timeout_sec):
        return True

    def send_goal_async(self, goal):
        self.sent_goals.append(goal)
        return _FakeFuture(
            _GoalHandle(
                accepted=True,
                result_future_value=SimpleNamespace(
                    status=GoalStatus.STATUS_SUCCEEDED,
                    result=self._result_value,
                ),
            )
        )


def _make_state(result_value=None, **ctor_kwargs) -> DriveToPoseState:
    state = DriveToPoseState(node=SimpleNamespace(), **ctor_kwargs)
    # Skip real lifecycle check for these tests.
    state.server_node_name = None
    state._action_client = _FakeActionClient(
        result_value=result_value
        or SimpleNamespace(final_x=0.0, final_y=0.0, final_yaw=0.0,
                           succeeded=True, message='ok'),
    )
    state._clients_ready = True
    state.server_wait_timeout_sec = 0.05
    state.goal_accept_timeout_sec = 0.05
    state.goal_complete_timeout_sec = 0.05
    state.poll_interval_sec = 0.001
    return state


# ---------------------------------------------------------------------------
# build_goal parameter resolution
# ---------------------------------------------------------------------------


def test_build_goal_uses_constructor_constants_over_userdata():
    st = _make_state(
        target_x=1.0, target_y=2.0, target_yaw=3.0,
        xy_tolerance=0.05,
    )
    # userdata has conflicting values; constructor must win.
    ud = Userdata({
        'target_x': 99.0, 'target_y': 99.0, 'target_yaw': 99.0,
        'xy_tolerance': 0.5,
    })
    goal = st.build_goal(ud)
    assert goal.target_x == 1.0
    assert goal.target_y == 2.0
    assert goal.target_yaw == 3.0
    assert goal.xy_tolerance == 0.05


def test_build_goal_reads_userdata_when_constructor_unset():
    st = _make_state()
    ud = Userdata({'target_x': 5.0, 'target_y': 6.0, 'target_yaw': 1.57})
    goal = st.build_goal(ud)
    assert goal.target_x == 5.0
    assert goal.target_y == 6.0
    assert goal.target_yaw == pytest.approx(1.57)


def test_build_goal_missing_required_raises_keyerror():
    st = _make_state()
    ud = Userdata({'target_x': 1.0})  # target_y / target_yaw missing
    with pytest.raises(KeyError):
        st.build_goal(ud)


def test_build_goal_optional_keys_fall_through_to_action_defaults():
    # Neither constructor nor userdata provides xy_tolerance — goal keeps
    # the value defined by the .action file default.
    st = _make_state(target_x=0.0, target_y=0.0, target_yaw=0.0)
    goal = st.build_goal(Userdata())
    # .action default is 0.15 — see mw_task_msgs/action/DriveToPose.action
    assert goal.xy_tolerance == pytest.approx(0.15)


def test_build_goal_userdata_optional_overrides_action_default():
    st = _make_state(target_x=0.0, target_y=0.0, target_yaw=0.0)
    ud = Userdata({
        'xy_tolerance': 0.01,
        'yaw_tolerance': 0.02,
        'max_linear_velocity': 0.5,
        'max_angular_velocity': 1.2,
    })
    goal = st.build_goal(ud)
    assert goal.xy_tolerance == pytest.approx(0.01)
    assert goal.yaw_tolerance == pytest.approx(0.02)
    assert goal.max_linear_velocity == pytest.approx(0.5)
    assert goal.max_angular_velocity == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# on_result userdata chaining
# ---------------------------------------------------------------------------


def test_on_result_writes_final_pose_to_userdata():
    st = _make_state(
        result_value=SimpleNamespace(
            final_x=3.14, final_y=-0.5, final_yaw=1.0,
            succeeded=True, message='ok',
        ),
        target_x=3.14, target_y=-0.5, target_yaw=1.0,
    )
    ud = Userdata()
    outcome = st.execute(ud)
    assert outcome == ActionOutcome.SUCCEEDED
    assert ud['final_x'] == pytest.approx(3.14)
    assert ud['final_y'] == pytest.approx(-0.5)
    assert ud['final_yaw'] == pytest.approx(1.0)


def test_declared_outcomes_match_parent():
    # Subclass shouldn't silently alter the outcome set.
    assert ActionOutcome.SUCCEEDED in DriveToPoseState.outcomes
    assert ActionOutcome.FAILED in DriveToPoseState.outcomes
    assert ActionOutcome.LIFECYCLE_ERROR in DriveToPoseState.outcomes
