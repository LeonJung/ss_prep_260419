"""Tests for Parallel composite (first_wins policy, region-outcome colocated).

Design intent verified here:
- Region mapping is colocated with the region: no separate cross-ref table
- Different regions can produce different parallel-level outcomes
- First mapped outcome wins under first_wins policy
- Region producing an outcome not in its mapping surfaces as an error
- Parallel outcomes attribute is the union of all regions' target outcomes
"""

import threading
import time

import pytest

from mw_hfsm_engine import (
    HfsmError,
    Parallel,
    Region,
    State,
    StateMachine,
    StateRegistry,
    TransitionError,
    Userdata,
)


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    yield
    StateRegistry.clear()


class _Sleepy(State):
    """State that sleeps `delay` seconds then returns `outcome_name`."""

    def __init__(self, outcome_name: str, delay: float = 0.0,
                 all_outcomes: list[str] | None = None):
        super().__init__()
        self._outcome = outcome_name
        self._delay = delay
        self.outcomes = list(all_outcomes or [outcome_name])

    def execute(self, userdata: Userdata) -> str:
        if self._delay:
            time.sleep(self._delay)
        return self._outcome


class _Raiser(State):
    outcomes = ['never']

    def execute(self, userdata):
        raise RuntimeError('region exploded')


def test_parallel_outcomes_auto_derived_from_region_mappings():
    p = Parallel(
        regions={
            'nav': Region(
                state=_Sleepy('succeeded', all_outcomes=['succeeded', 'failed']),
                outcomes={'succeeded': 'arrived', 'failed': 'nav_error'},
            ),
            'bat': Region(
                state=_Sleepy('low', all_outcomes=['ok', 'low', 'error']),
                outcomes={'low': 'battery_low', 'error': 'bat_error'},
            ),
        }
    )
    assert set(p.outcomes) == {'arrived', 'nav_error', 'battery_low', 'bat_error'}


def test_parallel_first_wins_fast_region_determines_outcome():
    # nav is fast (0 delay), bat is slow — nav must win.
    p = Parallel(
        regions={
            'nav': Region(
                state=_Sleepy('succeeded', delay=0.0,
                              all_outcomes=['succeeded', 'failed']),
                outcomes={'succeeded': 'arrived', 'failed': 'nav_error'},
            ),
            'bat': Region(
                state=_Sleepy('low', delay=0.5,
                              all_outcomes=['low']),
                outcomes={'low': 'battery_low'},
            ),
        },
        poll_interval_sec=0.001,
    )

    ud = Userdata()
    outcome = p.execute(ud)
    assert outcome == 'arrived'


def test_parallel_region_producing_unmapped_outcome_surfaces_transition_error():
    # Region says its outcomes include 'surprise' but the mapping doesn't
    # include it — must surface.
    p = Parallel(
        regions={
            'rogue': Region(
                state=_Sleepy('surprise', all_outcomes=['surprise']),
                outcomes={'done': 'ok'},
            ),
        },
    )
    with pytest.raises(TransitionError):
        p.execute(Userdata())


def test_parallel_all_regions_raise_surfaces_first_error():
    p = Parallel(
        regions={
            'a': Region(state=_Raiser(), outcomes={'never': 'nope'}),
            'b': Region(state=_Raiser(), outcomes={'never': 'nope'}),
        },
    )
    with pytest.raises(RuntimeError, match='region exploded'):
        p.execute(Userdata())


def test_parallel_requires_at_least_one_region():
    with pytest.raises(HfsmError):
        Parallel(regions={})


def test_parallel_rejects_unsupported_policy():
    r = Region(
        state=_Sleepy('done'),
        outcomes={'done': 'ok'},
    )
    with pytest.raises(HfsmError):
        Parallel(regions={'x': r}, policy='wait_all')


def test_parallel_nested_inside_state_machine():
    # Demonstrate the composition: a Step-level StateMachine embeds a
    # Parallel composite like any other State, and its outcomes become
    # transition keys.
    nav = Region(
        state=_Sleepy('succeeded', all_outcomes=['succeeded']),
        outcomes={'succeeded': 'arrived'},
    )
    bat = Region(
        state=_Sleepy('ok', delay=1.0, all_outcomes=['ok']),
        outcomes={'ok': 'battery_fine'},
    )
    parallel = Parallel(
        regions={'nav': nav, 'bat': bat},
        poll_interval_sec=0.001,
    )

    step = StateMachine(outcomes=['done', 'failed'])
    step.add('watch', parallel, transitions={
        'arrived': 'done',
        'battery_fine': 'done',
    })

    assert step.execute(Userdata()) == 'done'
