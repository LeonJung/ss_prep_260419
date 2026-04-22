"""Unit tests for MoveMotorState — same mock pattern as drive_to_pose tests."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from action_msgs.msg import GoalStatus

from mw_hfsm_engine import Userdata
from mw_hfsm_ros import ActionOutcome
from mw_skill_states import MoveMotorState


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


def _make_state(result_value=None, **ctor_kwargs) -> MoveMotorState:
    state = MoveMotorState(node=SimpleNamespace(), **ctor_kwargs)
    state.server_node_name = None  # skip lifecycle probe
    state._action_client = _FakeActionClient(
        result_value=result_value or SimpleNamespace(
            final_position=0.0, succeeded=True, message='ok',
        ),
    )
    state._clients_ready = True
    state.server_wait_timeout_sec = 0.05
    state.goal_accept_timeout_sec = 0.05
    state.goal_complete_timeout_sec = 0.05
    state.poll_interval_sec = 0.001
    return state


def test_build_goal_uses_constants_over_userdata():
    st = _make_state(motor_id='arm_j0', target_position=1.57, max_velocity=0.5)
    ud = Userdata({
        'motor_id': 'IGNORED',
        'target_position': -9.9,
        'max_velocity': 99.0,
    })
    goal = st.build_goal(ud)
    assert goal.motor_id == 'arm_j0'
    assert goal.target_position == pytest.approx(1.57)
    assert goal.max_velocity == pytest.approx(0.5)


def test_build_goal_reads_userdata_when_constructor_unset():
    st = _make_state()
    ud = Userdata({'motor_id': 'gripper_pitch', 'target_position': 0.9})
    goal = st.build_goal(ud)
    assert goal.motor_id == 'gripper_pitch'
    assert goal.target_position == pytest.approx(0.9)


def test_build_goal_missing_required_raises():
    st = _make_state()
    with pytest.raises(KeyError):
        st.build_goal(Userdata({'motor_id': 'arm_j0'}))  # target_position missing


def test_build_goal_max_velocity_defaults_to_action_default():
    st = _make_state(motor_id='arm_j0', target_position=0.0)
    goal = st.build_goal(Userdata())
    # .action default is 1.0 — MoveMotor.action line 4.
    assert goal.max_velocity == pytest.approx(1.0)


def test_on_result_writes_final_position():
    st = _make_state(
        motor_id='arm_j0', target_position=1.0,
        result_value=SimpleNamespace(
            final_position=0.97, succeeded=True, message='ok',
        ),
    )
    ud = Userdata()
    outcome = st.execute(ud)
    assert outcome == ActionOutcome.SUCCEEDED
    assert ud['final_position'] == pytest.approx(0.97)
