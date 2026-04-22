"""Tests for the JSON/dict DSL spec loader.

Every spec in these tests is a plain Python dict so the test is truly
unit-level — no JSON parsing, no file I/O.  Real task_repository flow
will JSON-decode the spec and pass the dict here; that layer is out of
scope for this module's tests.
"""

from __future__ import annotations

import pytest

from mw_hfsm_engine import (
    BehaviorSM,
    HfsmError,
    Parallel,
    State,
    StateMachine,
    StateRegistry,
    Userdata,
    build_from_spec,
    register_state,
)


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    yield
    StateRegistry.clear()


# ---------------------------------------------------------------------------
# Fixture States
# ---------------------------------------------------------------------------


class _Tag(State):
    outcomes = ['done']

    def __init__(self, tag: str = 'X'):
        super().__init__()
        self.tag = tag

    def execute(self, userdata: Userdata) -> str:
        trace = userdata.get('trace', [])
        trace.append(self.tag)
        userdata['trace'] = trace
        return 'done'


class _Switcher(State):
    outcomes = ['left', 'right']

    def execute(self, userdata: Userdata) -> str:
        return userdata.get('pick', 'left')


# ---------------------------------------------------------------------------
# Leaf State
# ---------------------------------------------------------------------------


def test_loader_builds_registered_leaf_state():
    StateRegistry.register('Tag', _Tag)
    spec = {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'A'}}
    inst = build_from_spec(spec)
    assert isinstance(inst, _Tag)
    assert inst.tag == 'A'


def test_loader_rejects_state_spec_without_ref():
    with pytest.raises(HfsmError):
        build_from_spec({'kind': 'State'})


def test_loader_ref_resolution_error_propagates_as_hfsmerror():
    # StateRegistry.resolve raises RegistryError (HfsmError subclass).
    with pytest.raises(HfsmError):
        build_from_spec({'kind': 'State', 'ref': 'NeverRegistered'})


# ---------------------------------------------------------------------------
# StateMachine
# ---------------------------------------------------------------------------


def test_loader_builds_statemachine_with_transitions():
    StateRegistry.register('Tag', _Tag)
    spec = {
        'kind': 'StateMachine',
        'outcomes': ['done', 'failed'],
        'children': {
            'A': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'A'}},
            'B': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'B'}},
        },
        'transitions': {
            'A': {'done': 'B'},
            'B': {'done': 'done'},
        },
        'initial_state': 'A',
    }
    sm = build_from_spec(spec)
    assert isinstance(sm, StateMachine) and not isinstance(sm, BehaviorSM)

    ud = Userdata()
    outcome = sm.execute(ud)
    assert outcome == 'done'
    assert ud['trace'] == ['A', 'B']


def test_loader_statemachine_branch_on_userdata():
    StateRegistry.register('Tag', _Tag)
    StateRegistry.register('Switcher', _Switcher)
    spec = {
        'kind': 'StateMachine',
        'outcomes': ['done'],
        'children': {
            'pick': {'kind': 'State', 'ref': 'Switcher'},
            'L': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'L'}},
            'R': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'R'}},
        },
        'transitions': {
            'pick': {'left': 'L', 'right': 'R'},
            'L': {'done': 'done'},
            'R': {'done': 'done'},
        },
        'initial_state': 'pick',
    }
    sm = build_from_spec(spec)
    ud = Userdata({'pick': 'right'})
    assert sm.execute(ud) == 'done'
    assert ud['trace'] == ['R']


# ---------------------------------------------------------------------------
# BehaviorSM
# ---------------------------------------------------------------------------


def test_loader_builds_behavior_sm_with_parameters():
    StateRegistry.register('Tag', _Tag)
    spec = {
        'kind': 'BehaviorSM',
        'outcomes': ['done', 'failed'],
        'behavior_parameters': ['target'],
        'children': {
            'A': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'A'}},
        },
        'transitions': {'A': {'done': 'done'}},
    }
    sm = build_from_spec(spec)
    assert isinstance(sm, BehaviorSM)
    assert sm.behavior_parameters == ['target']

    # Missing required param raises HfsmError; supplying it succeeds.
    with pytest.raises(HfsmError):
        sm.run(behavior_parameter={})

    outcome, ud_out = sm.run(behavior_parameter={'target': 'cup'})
    assert outcome == 'done'
    assert ud_out['target'] == 'cup'


def test_loader_nested_behavior_sm_and_state_machine():
    StateRegistry.register('Tag', _Tag)
    spec = {
        'kind': 'BehaviorSM',
        'outcomes': ['done'],
        'children': {
            'step1': {
                'kind': 'StateMachine',
                'outcomes': ['done'],
                'children': {
                    'a': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'a'}},
                },
                'transitions': {'a': {'done': 'done'}},
            },
            'step2': {
                'kind': 'StateMachine',
                'outcomes': ['done'],
                'children': {
                    'b': {'kind': 'State', 'ref': 'Tag', 'args': {'tag': 'b'}},
                },
                'transitions': {'b': {'done': 'done'}},
            },
        },
        'transitions': {
            'step1': {'done': 'step2'},
            'step2': {'done': 'done'},
        },
    }
    sm = build_from_spec(spec)
    outcome, ud_out = sm.run()
    assert outcome == 'done'
    assert ud_out['trace'] == ['a', 'b']


# ---------------------------------------------------------------------------
# Parallel
# ---------------------------------------------------------------------------


def test_loader_builds_parallel_first_wins():
    StateRegistry.register('Tag', _Tag)

    class _FastLeft(State):
        outcomes = ['left']

        def execute(self, userdata):
            return 'left'

    class _SlowRight(State):
        outcomes = ['right']

        def execute(self, userdata):
            import time
            time.sleep(0.2)
            return 'right'

    StateRegistry.register('FastLeft', _FastLeft)
    StateRegistry.register('SlowRight', _SlowRight)

    spec = {
        'kind': 'Parallel',
        'policy': 'first_wins',
        'regions': {
            'L': {
                'state': {'kind': 'State', 'ref': 'FastLeft'},
                'outcomes': {'left': 'picked_left'},
            },
            'R': {
                'state': {'kind': 'State', 'ref': 'SlowRight'},
                'outcomes': {'right': 'picked_right'},
            },
        },
    }
    p = build_from_spec(spec)
    assert isinstance(p, Parallel)
    assert set(p.outcomes) == {'picked_left', 'picked_right'}
    assert p.execute(Userdata()) == 'picked_left'


def test_loader_parallel_requires_regions():
    with pytest.raises(HfsmError):
        build_from_spec({'kind': 'Parallel', 'regions': {}})


def test_loader_parallel_region_missing_state_raises():
    with pytest.raises(HfsmError):
        build_from_spec({
            'kind': 'Parallel',
            'regions': {'r': {'outcomes': {'x': 'y'}}},
        })


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


def test_loader_unknown_kind_raises():
    with pytest.raises(HfsmError):
        build_from_spec({'kind': 'Mystery'})


def test_loader_rejects_non_dict_spec():
    with pytest.raises(HfsmError):
        build_from_spec('not a dict')  # type: ignore[arg-type]
