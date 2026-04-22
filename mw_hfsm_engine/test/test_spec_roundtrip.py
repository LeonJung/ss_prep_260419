"""Round-trip tests: programmatically built SM → to_spec() → build_from_spec()
should produce an equivalent SM (same structure + behavior).
"""

import pytest

from mw_hfsm_engine import (
    BehaviorSM,
    Parallel,
    Region,
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


@register_state
class _Tag(State):
    outcomes = ['done']

    def __init__(self, tag: str = 'X'):
        super().__init__()
        self.tag = tag

    def execute(self, userdata):
        trace = userdata.get('trace', [])
        trace.append(self.tag)
        userdata['trace'] = trace
        return 'done'

    def to_spec(self):
        spec = super().to_spec()
        spec['args'] = {'tag': self.tag}
        return spec


# ---------------------------------------------------------------------------


def test_state_to_spec_minimal_shape():
    StateRegistry.register('_Tag', _Tag, override=True)
    s = _Tag(tag='Z')
    spec = s.to_spec()
    assert spec['kind'] == 'State'
    assert spec['ref'] == '_Tag'
    assert spec['args'] == {'tag': 'Z'}


def test_statemachine_to_spec_preserves_structure():
    StateRegistry.register('_Tag', _Tag, override=True)
    sm = StateMachine(outcomes=['done', 'failed'])
    sm.add('A', _Tag(tag='A'), transitions={'done': 'B'})
    sm.add('B', _Tag(tag='B'), transitions={'done': 'done'})

    spec = sm.to_spec()
    assert spec['kind'] == 'StateMachine'
    assert spec['outcomes'] == ['done', 'failed']
    assert spec['initial_state'] == 'A'
    assert set(spec['children']) == {'A', 'B'}
    assert spec['transitions'] == {
        'A': {'done': 'B'},
        'B': {'done': 'done'},
    }


def test_statemachine_roundtrip_executes_identically():
    StateRegistry.register('_Tag', _Tag, override=True)
    sm = StateMachine(outcomes=['done', 'failed'])
    sm.add('A', _Tag(tag='A'), transitions={'done': 'B'})
    sm.add('B', _Tag(tag='B'), transitions={'done': 'done'})

    rebuilt = build_from_spec(sm.to_spec())
    ud = Userdata()
    assert rebuilt.execute(ud) == 'done'
    assert ud['trace'] == ['A', 'B']


def test_behavior_sm_roundtrip_preserves_params_and_execution():
    StateRegistry.register('_Tag', _Tag, override=True)

    class Outer(BehaviorSM):
        outcomes = ['done']
        behavior_parameters = ['mode']

        def __init__(self):
            super().__init__()
            self.add('A', _Tag(tag='A'), transitions={'done': 'done'})

    sj = Outer()
    spec = sj.to_spec()
    assert spec['kind'] == 'BehaviorSM'
    assert spec['behavior_parameters'] == ['mode']

    rebuilt = build_from_spec(spec)
    assert isinstance(rebuilt, BehaviorSM)
    assert rebuilt.behavior_parameters == ['mode']
    outcome, ud_out = rebuilt.run(behavior_parameter={'mode': 'fast'})
    assert outcome == 'done'
    assert ud_out['mode'] == 'fast'
    assert ud_out['trace'] == ['A']


def test_parallel_to_spec_and_roundtrip():
    @register_state
    class _Left(State):
        outcomes = ['l']

        def execute(self, userdata):
            return 'l'

    @register_state
    class _Right(State):
        outcomes = ['r']

        def execute(self, userdata):
            import time
            time.sleep(0.05)
            return 'r'

    p = Parallel(regions={
        'L': Region(state=_Left(), outcomes={'l': 'picked_left'}),
        'R': Region(state=_Right(), outcomes={'r': 'picked_right'}),
    })
    spec = p.to_spec()
    assert spec['kind'] == 'Parallel'
    assert spec['policy'] == 'first_wins'
    assert set(spec['regions']) == {'L', 'R'}

    rebuilt = build_from_spec(spec)
    assert isinstance(rebuilt, Parallel)
    # Fast region wins deterministically.
    assert rebuilt.execute(Userdata()) == 'picked_left'


def test_nested_behavior_sm_spec_round_trip():
    StateRegistry.register('_Tag', _Tag, override=True)

    inner = StateMachine(outcomes=['done'])
    inner.add('x', _Tag(tag='x'), transitions={'done': 'done'})

    class Outer(BehaviorSM):
        outcomes = ['done']

        def __init__(self):
            super().__init__()
            self.add('IN', inner, transitions={'done': 'FIN'})
            self.add('FIN', _Tag(tag='FIN'), transitions={'done': 'done'})

    sj = Outer()
    spec = sj.to_spec()
    rebuilt = build_from_spec(spec)
    outcome, ud_out = rebuilt.run()
    assert outcome == 'done'
    assert ud_out['trace'] == ['x', 'FIN']
