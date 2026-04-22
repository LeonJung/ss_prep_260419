"""Tests for the execution observer hook (active_path tracking)."""

from __future__ import annotations

import threading
import time

import pytest

from mw_hfsm_engine import (
    BehaviorSM,
    State,
    StateMachine,
    StateRegistry,
    Userdata,
    active_path,
    install_observer,
    register_state,
)


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    install_observer(None)
    yield
    StateRegistry.clear()
    install_observer(None)


class _Recorder(State):
    """On execute, stashes the active_path seen from inside the state."""

    outcomes = ['done']

    def execute(self, userdata: Userdata) -> str:
        seen = userdata.get('paths', [])
        seen.append(active_path())
        userdata['paths'] = seen
        return 'done'


class _Slow(State):
    outcomes = ['done']

    def execute(self, userdata: Userdata) -> str:
        time.sleep(0.2)
        return 'done'


# ---------------------------------------------------------------------------


def test_inside_state_sees_full_dotted_path():
    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            step = StateMachine(outcomes=['done'])
            step.add('rec', _Recorder(), transitions={'done': 'done'})
            self.add('STEP1', step, transitions={'done': 'done'})

    outcome, ud = Demo().run()
    assert outcome == 'done'
    # Path seen at _Recorder.execute = Demo.STEP1.rec
    assert ud['paths'] == ['Demo.STEP1.rec']


def test_active_path_resets_between_runs():
    class One(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('r', _Recorder(), transitions={'done': 'done'})

    one = One()
    _, ud1 = one.run()
    assert ud1['paths'] == ['One.r']
    # After run() completes, the global path should have been cleared.
    assert active_path() == ''


def test_observer_callback_fires_on_enter_and_exit():
    events: list[tuple[str, str, str | None]] = []

    def obs(kind, path, outcome):
        events.append((kind, path, outcome))

    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('a', _Recorder(), transitions={'done': 'b'})
            self.add('b', _Recorder(), transitions={'done': 'done'})

    install_observer(obs)
    Demo().run()

    # Expect paired enter/exit at both Demo root and each child.
    kinds = [e[0] for e in events]
    paths = [e[1] for e in events]
    assert 'Demo' in paths
    assert 'Demo.a' in paths
    assert 'Demo.b' in paths
    assert kinds.count('enter') == kinds.count('exit')
    # Last event must be the Demo root exiting with the final outcome.
    assert events[-1] == ('exit', 'Demo', 'done')


def test_active_path_visible_from_another_thread_during_slow_state():
    """Simulates the ROS 2 status publisher reading active_path() from its
    timer thread while a SubJob is running on a worker thread."""
    observed: list[str] = []

    class Demo(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('slow', _Slow(), transitions={'done': 'done'})

    done = threading.Event()

    def worker():
        Demo().run()
        done.set()

    threading.Thread(target=worker, daemon=True).start()
    # Poll active_path from this (the "publisher") thread while the worker
    # sits in _Slow.execute.
    for _ in range(5):
        observed.append(active_path())
        time.sleep(0.05)
    done.wait(timeout=2.0)

    # At least one observation while the slow state was running must
    # have seen the full path.
    assert 'Demo.slow' in observed
