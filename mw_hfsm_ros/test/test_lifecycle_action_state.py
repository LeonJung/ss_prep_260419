"""Unit tests for LifecycleAwareActionState — uses mocks so no real ROS graph."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from action_msgs.msg import GoalStatus
from lifecycle_msgs.msg import State as LifecycleState, Transition

from mw_hfsm_engine import Userdata
from mw_hfsm_ros import ActionOutcome, LifecycleAwareActionState


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


class _FakeFuture:
    """Minimal asyncio-free Future stand-in: always done, carries a value."""

    def __init__(self, value: Any, raises: Exception | None = None):
        self._value = value
        self._raises = raises

    def done(self) -> bool:
        return True

    def result(self) -> Any:
        if self._raises is not None:
            raise self._raises
        return self._value


class _FakeActionClient:
    def __init__(
        self,
        *,
        server_ready: bool = True,
        goal_accepted: bool = True,
        final_status: int = GoalStatus.STATUS_SUCCEEDED,
        result_value: Any = None,
    ):
        self._server_ready = server_ready
        self._goal_accepted = goal_accepted
        self._final_status = final_status
        self._result_value = result_value
        self.sent_goals: list[Any] = []

    def wait_for_server(self, timeout_sec: float) -> bool:
        return self._server_ready

    def send_goal_async(self, goal: Any) -> _FakeFuture:
        self.sent_goals.append(goal)
        handle = SimpleNamespace(
            accepted=self._goal_accepted,
            get_result_async=lambda: _FakeFuture(
                SimpleNamespace(
                    status=self._final_status,
                    result=self._result_value,
                )
            ),
        )
        return _FakeFuture(handle)


class _FakeServiceClient:
    def __init__(self, responses: list[Any], *, service_ready: bool = True):
        self._responses = list(responses)
        self._service_ready = service_ready
        self.calls: list[Any] = []

    def wait_for_service(self, timeout_sec: float) -> bool:
        return self._service_ready

    def call_async(self, request: Any) -> _FakeFuture:
        self.calls.append(request)
        if not self._responses:
            return _FakeFuture(None)
        return _FakeFuture(self._responses.pop(0))


# ---------------------------------------------------------------------------
# Test subclass
# ---------------------------------------------------------------------------


@dataclass
class _DummyGoal:
    x: float


@dataclass
class _DummyResult:
    final_x: float
    succeeded: bool


class _DummyActionType:
    Goal = _DummyGoal
    Result = _DummyResult


class ProbeState(LifecycleAwareActionState):
    """Concrete subclass used by every test — small and mockable."""

    action_type = _DummyActionType
    action_name = '/probe'
    # server_node_name intentionally unset so lifecycle path is skipped by default.
    goal_accept_timeout_sec = 0.05
    goal_complete_timeout_sec = 0.05
    server_wait_timeout_sec = 0.05
    lifecycle_wait_timeout_sec = 0.05
    poll_interval_sec = 0.001

    def build_goal(self, userdata: Userdata):
        return _DummyGoal(x=userdata['x'])

    def on_result(self, userdata: Userdata, result: _DummyResult) -> None:
        userdata['final_x'] = result.final_x
        userdata['ok'] = result.succeeded


def _make_state(
    *,
    server_node_name: str | None = None,
    action_client: _FakeActionClient | None = None,
    get_state_client: _FakeServiceClient | None = None,
    change_state_client: _FakeServiceClient | None = None,
) -> ProbeState:
    """Create a ProbeState, skipping _lazy_init_clients by injecting mocks."""
    ProbeState.server_node_name = server_node_name
    node = SimpleNamespace()  # unused when clients are injected
    state = ProbeState(node=node)
    state._action_client = action_client or _FakeActionClient()
    state._get_state_client = get_state_client
    state._change_state_client = change_state_client
    state._clients_ready = True
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_outcome_constants_are_declared_in_class_outcomes():
    for expected in (
        ActionOutcome.SUCCEEDED,
        ActionOutcome.FAILED,
        ActionOutcome.LIFECYCLE_ERROR,
        ActionOutcome.TIMEOUT,
        ActionOutcome.REJECTED,
    ):
        assert expected in LifecycleAwareActionState.outcomes


def test_build_goal_unimplemented_raises():
    class Incomplete(LifecycleAwareActionState):
        action_type = _DummyActionType
        action_name = '/probe'

    st = Incomplete(node=SimpleNamespace())
    st._action_client = _FakeActionClient()
    st._clients_ready = True
    with pytest.raises(NotImplementedError):
        st.build_goal(Userdata())


def test_successful_action_populates_userdata_and_returns_succeeded():
    ac = _FakeActionClient(
        final_status=GoalStatus.STATUS_SUCCEEDED,
        result_value=_DummyResult(final_x=3.5, succeeded=True),
    )
    st = _make_state(action_client=ac)

    ud = Userdata({'x': 3.5})
    outcome = st.execute(ud)

    assert outcome == ActionOutcome.SUCCEEDED
    assert ud['final_x'] == 3.5
    assert ud['ok'] is True
    # and the goal we built was passed through.
    assert ac.sent_goals == [_DummyGoal(x=3.5)]


def test_aborted_action_maps_to_failed():
    ac = _FakeActionClient(
        final_status=GoalStatus.STATUS_ABORTED,
        result_value=_DummyResult(final_x=0.0, succeeded=False),
    )
    st = _make_state(action_client=ac)
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.FAILED


def test_rejected_goal_returns_rejected():
    ac = _FakeActionClient(goal_accepted=False)
    st = _make_state(action_client=ac)
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.REJECTED


def test_server_not_ready_returns_timeout():
    ac = _FakeActionClient(server_ready=False)
    st = _make_state(action_client=ac)
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.TIMEOUT


def test_lifecycle_active_server_proceeds_to_action():
    get_state = _FakeServiceClient([
        SimpleNamespace(current_state=SimpleNamespace(
            id=LifecycleState.PRIMARY_STATE_ACTIVE
        )),
    ])
    ac = _FakeActionClient(
        final_status=GoalStatus.STATUS_SUCCEEDED,
        result_value=_DummyResult(final_x=1.0, succeeded=True),
    )
    st = _make_state(
        server_node_name='probe_server',
        action_client=ac,
        get_state_client=get_state,
        change_state_client=_FakeServiceClient([]),
    )
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.SUCCEEDED
    # No transitions were requested since server was already active.
    assert st._change_state_client.calls == []


def test_lifecycle_unconfigured_transitions_configure_and_activate():
    # Sequence:
    #   get_state #1 → UNCONFIGURED
    #   change_state(CONFIGURE) → success=True
    #   get_state #2 → INACTIVE
    #   change_state(ACTIVATE) → success=True
    #   get_state #3 → ACTIVE
    get_state = _FakeServiceClient([
        SimpleNamespace(current_state=SimpleNamespace(
            id=LifecycleState.PRIMARY_STATE_UNCONFIGURED)),
        SimpleNamespace(current_state=SimpleNamespace(
            id=LifecycleState.PRIMARY_STATE_INACTIVE)),
        SimpleNamespace(current_state=SimpleNamespace(
            id=LifecycleState.PRIMARY_STATE_ACTIVE)),
    ])
    change_state = _FakeServiceClient([
        SimpleNamespace(success=True),
        SimpleNamespace(success=True),
    ])
    ac = _FakeActionClient(
        final_status=GoalStatus.STATUS_SUCCEEDED,
        result_value=_DummyResult(final_x=0.0, succeeded=True),
    )
    st = _make_state(
        server_node_name='probe_server',
        action_client=ac,
        get_state_client=get_state,
        change_state_client=change_state,
    )

    outcome = st.execute(Userdata({'x': 0.0}))
    assert outcome == ActionOutcome.SUCCEEDED

    # Exactly two transitions requested, in the right order.
    ids = [r.transition.id for r in change_state.calls]
    assert ids == [Transition.TRANSITION_CONFIGURE, Transition.TRANSITION_ACTIVATE]


def test_lifecycle_finalized_server_returns_lifecycle_error():
    get_state = _FakeServiceClient([
        SimpleNamespace(current_state=SimpleNamespace(
            id=LifecycleState.PRIMARY_STATE_FINALIZED)),
    ])
    st = _make_state(
        server_node_name='probe_server',
        get_state_client=get_state,
        change_state_client=_FakeServiceClient([]),
    )
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.LIFECYCLE_ERROR


def test_lifecycle_get_state_unavailable_returns_lifecycle_error():
    # Service never ready → _ensure_lifecycle_active returns False.
    get_state = _FakeServiceClient([], service_ready=False)
    st = _make_state(
        server_node_name='probe_server',
        get_state_client=get_state,
        change_state_client=_FakeServiceClient([]),
    )
    outcome = st.execute(Userdata({'x': 1.0}))
    assert outcome == ActionOutcome.LIFECYCLE_ERROR
