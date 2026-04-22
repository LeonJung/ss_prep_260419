"""Unit tests for CaptureImageState."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from action_msgs.msg import GoalStatus

from mw_hfsm_engine import Userdata
from mw_hfsm_ros import ActionOutcome
from mw_skill_states import CaptureImageState


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


def _make_state(result_value=None, **ctor_kwargs) -> CaptureImageState:
    state = CaptureImageState(node=SimpleNamespace(), **ctor_kwargs)
    state.server_node_name = None
    state._action_client = _FakeActionClient(
        result_value=result_value or SimpleNamespace(
            image_path='', succeeded=True, message='ok',
        ),
    )
    state._clients_ready = True
    state.server_wait_timeout_sec = 0.05
    state.goal_accept_timeout_sec = 0.05
    state.goal_complete_timeout_sec = 0.05
    state.poll_interval_sec = 0.001
    return state


def test_build_goal_uses_constants():
    st = _make_state(camera_id='head_rgb', save_path='/tmp/cup.jpg')
    goal = st.build_goal(Userdata())
    assert goal.camera_id == 'head_rgb'
    assert goal.save_path == '/tmp/cup.jpg'


def test_build_goal_from_userdata():
    st = _make_state()
    goal = st.build_goal(Userdata({
        'camera_id': 'wrist_rgb',
        'save_path': '/var/captures/a.jpg',
    }))
    assert goal.camera_id == 'wrist_rgb'
    assert goal.save_path == '/var/captures/a.jpg'


def test_build_goal_mixed_ctor_and_userdata():
    st = _make_state(camera_id='head_rgb')
    goal = st.build_goal(Userdata({'save_path': '/var/tmp/x.png'}))
    assert goal.camera_id == 'head_rgb'
    assert goal.save_path == '/var/tmp/x.png'


def test_build_goal_missing_required_raises():
    st = _make_state(camera_id='head_rgb')  # save_path missing
    with pytest.raises(KeyError):
        st.build_goal(Userdata())


def test_on_result_writes_image_path():
    st = _make_state(
        camera_id='head_rgb', save_path='/tmp/a.jpg',
        result_value=SimpleNamespace(
            image_path='/tmp/a_normalized.jpg',
            succeeded=True, message='ok',
        ),
    )
    ud = Userdata()
    outcome = st.execute(ud)
    assert outcome == ActionOutcome.SUCCEEDED
    assert ud['image_path'] == '/tmp/a_normalized.jpg'
