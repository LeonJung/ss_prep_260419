"""Cooperative cancellation tests."""

from __future__ import annotations

import threading
import time

import pytest

from mw_hfsm_engine import (
    BehaviorSM,
    CancelledError,
    CancelToken,
    Parallel,
    Region,
    State,
    StateMachine,
    StateRegistry,
    Userdata,
    install_observer,
    is_cancellation_requested,
    raise_if_cancelled,
    register_state,
)


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    install_observer(None)
    yield
    StateRegistry.clear()
    install_observer(None)


class _Fast(State):
    outcomes = ['done']

    def execute(self, userdata):
        trace = userdata.get('trace', [])
        trace.append(type(self).__name__)
        userdata['trace'] = trace
        return 'done'


class _Polling(State):
    """Simulates a long-running leaf that honors the cancel token."""

    outcomes = ['done']

    def execute(self, userdata):
        for _ in range(200):
            raise_if_cancelled()
            time.sleep(0.01)
        return 'done'


# ---------------------------------------------------------------------------


def test_cancel_between_children_stops_the_sub_job():
    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('a', _Fast(), transitions={'done': 'b'})
            self.add('b', _Fast(), transitions={'done': 'c'})
            self.add('c', _Fast(), transitions={'done': 'done'})

    token = CancelToken()

    # Flip the token inside the observer so the cancel happens after
    # child 'a' finishes, right before 'b' is about to start.
    def obs(event, path, outcome):
        if event == 'exit' and path == 'Demo.a':
            token.request()

    install_observer(obs)
    with pytest.raises(CancelledError):
        Demo().run(cancel_token=token)


def test_cancel_interrupts_long_running_leaf_state():
    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('slow', _Polling(), transitions={'done': 'done'})

    token = CancelToken()
    errors: list[BaseException] = []

    def worker():
        try:
            Demo().run(cancel_token=token)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    time.sleep(0.05)
    token.request()
    t.join(timeout=2.0)

    assert not t.is_alive(), 'worker did not exit after cancel'
    assert errors and isinstance(errors[0], CancelledError)


def test_is_cancellation_requested_reflects_token_state():
    token = CancelToken()

    class Probe(State):
        outcomes = ['pre', 'post']

        def execute(self, userdata):
            first = is_cancellation_requested()
            token.request()
            second = is_cancellation_requested()
            userdata['first'] = first
            userdata['second'] = second
            return 'post'

    class Demo(BehaviorSM):
        outcomes = ['post']

        def __init__(self):
            super().__init__()
            self.add('p', Probe(), transitions={'post': 'post'})

    # Let the Probe finish naturally (the between-children check fires
    # on the NEXT child, but there isn't one — loop terminates via
    # terminal outcome before the check runs).
    outcome, ud = Demo().run(cancel_token=token)
    assert outcome == 'post'
    assert ud['first'] is False
    assert ud['second'] is True


def test_cancel_token_not_installed_means_no_interference():
    # Sanity: running without a token behaves like before.
    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('a', _Fast(), transitions={'done': 'done'})

    outcome, ud = Demo().run()
    assert outcome == 'done'
    assert ud['trace'] == ['_Fast']


def test_parallel_bails_out_on_cancel():
    class _Blocker(State):
        outcomes = ['done']

        def execute(self, userdata):
            # Busy-wait honoring cancel — a stand-in for a blocking
            # ROS action client.
            for _ in range(500):
                raise_if_cancelled()
                time.sleep(0.01)
            return 'done'

    p = Parallel(
        regions={
            'a': Region(state=_Blocker(), outcomes={'done': 'A'}),
            'b': Region(state=_Blocker(), outcomes={'done': 'B'}),
        },
        poll_interval_sec=0.005,
    )

    class Demo(BehaviorSM):
        outcomes = ['A', 'B']

        def __init__(self):
            super().__init__()
            self.add('p', p, transitions={'A': 'A', 'B': 'B'})

    token = CancelToken()

    def worker():
        try:
            Demo().run(cancel_token=token)
        except CancelledError:
            pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    time.sleep(0.05)
    token.request()
    t.join(timeout=2.0)
    assert not t.is_alive()
