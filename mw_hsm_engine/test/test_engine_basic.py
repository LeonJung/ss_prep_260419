"""Basic engine tests — a dummy SubJob with Steps and SubSteps executing once.

Covers:
- State subclass + override of `execute`
- `@register_state` auto-registration + string ID late binding
- StateMachine transitions (named targets + terminal outcomes)
- Nested StateMachine (Step inside Step)
- BehaviorSM.run() with behavior_parameter + userdata_in/out
- SelfIterationError and TransitionError surface at the right moments
- Missing behavior_parameter surfaces as HsmError
"""

import pytest

from mw_hsm_engine import (
    BehaviorSM,
    HsmError,
    SelfIterationError,
    State,
    StateMachine,
    StateRegistry,
    TransitionError,
    Userdata,
    register_state,
)


@pytest.fixture(autouse=True)
def clear_registry():
    """Each test gets a fresh StateRegistry so IDs don't leak."""
    StateRegistry.clear()
    yield
    StateRegistry.clear()


# ---------------------------------------------------------------------------
# Helper states used across tests
# ---------------------------------------------------------------------------


@register_state
class Succeeder(State):
    """Always returns 'done', writes a trace entry to userdata['trace']."""

    outcomes = ['done']

    def __init__(self, tag: str = 'S'):
        super().__init__(tag=tag)
        self.tag = tag

    def execute(self, userdata: Userdata) -> str:
        trace = userdata.get('trace', [])
        trace.append(self.tag)
        userdata['trace'] = trace
        return 'done'


@register_state
class Failer(State):
    outcomes = ['failed']

    def execute(self, userdata: Userdata) -> str:
        return 'failed'


@register_state
class Chooser(State):
    """Returns 'left' or 'right' based on userdata['pick']."""

    outcomes = ['left', 'right']

    def execute(self, userdata: Userdata) -> str:
        pick = userdata.get('pick', 'left')
        assert pick in self.outcomes, f'bad pick: {pick}'
        return pick


# ---------------------------------------------------------------------------
# State & registry
# ---------------------------------------------------------------------------


def test_state_registry_auto_registration():
    # Fixture cleared registry; redecorate a class here to assert registration.
    @register_state
    class Local(State):
        outcomes = ['done']

        def execute(self, userdata):
            return 'done'

    assert 'Local' in StateRegistry.ids()
    assert StateRegistry.resolve('Local') is Local


def test_state_registry_custom_id_and_override():
    @register_state('FancyName')
    class Something(State):
        outcomes = ['done']

        def execute(self, userdata):
            return 'done'

    assert 'FancyName' in StateRegistry.ids()
    assert 'Something' not in StateRegistry.ids()

    # Re-registering same id without override fails.
    with pytest.raises(Exception):
        @register_state('FancyName')
        class Collider(State):
            outcomes = ['done']

            def execute(self, userdata):
                return 'done'

    # override=True replaces.
    @register_state('FancyName', override=True)
    class Replacement(State):
        outcomes = ['done']

        def execute(self, userdata):
            return 'done'

    assert StateRegistry.resolve('FancyName') is Replacement


def test_state_base_execute_raises_not_implemented():
    s = State()
    with pytest.raises(NotImplementedError):
        s.execute(Userdata())


# ---------------------------------------------------------------------------
# StateMachine (Step) basics
# ---------------------------------------------------------------------------


def test_step_sequence_two_substeps():
    step = StateMachine(outcomes=['done', 'failed'])
    step.add('A', Succeeder(tag='A'), transitions={'done': 'B'})
    step.add('B', Succeeder(tag='B'), transitions={'done': 'done'})

    ud = Userdata()
    outcome = step.execute(ud)
    assert outcome == 'done'
    assert ud['trace'] == ['A', 'B']


def test_step_branches_on_outcome():
    step = StateMachine(outcomes=['done', 'failed'])
    step.add('pick', Chooser(), transitions={'left': 'L', 'right': 'R'})
    step.add('L', Succeeder(tag='L'), transitions={'done': 'done'})
    step.add('R', Succeeder(tag='R'), transitions={'done': 'done'})

    ud_left = Userdata({'pick': 'left'})
    assert step.execute(ud_left) == 'done'
    assert ud_left['trace'] == ['L']

    ud_right = Userdata({'pick': 'right'})
    assert step.execute(ud_right) == 'done'
    assert ud_right['trace'] == ['R']


def test_step_terminal_on_failure():
    step = StateMachine(outcomes=['done', 'failed'])
    step.add('A', Failer(), transitions={'failed': 'failed'})
    assert step.execute(Userdata()) == 'failed'


def test_step_rejects_self_as_child():
    step = StateMachine(outcomes=['done'])
    with pytest.raises(SelfIterationError):
        step.add('self', step, transitions={'done': 'done'})


def test_step_transition_to_unknown_target_raises():
    step = StateMachine(outcomes=['done'])
    step.add('A', Succeeder(tag='A'), transitions={'done': 'nowhere'})
    with pytest.raises(TransitionError):
        step.execute(Userdata())


def test_step_child_outcome_not_declared_raises():
    step = StateMachine(outcomes=['done'])

    class Rogue(State):
        outcomes = ['a']

        def execute(self, userdata):
            return 'b'  # not in its own outcomes

    step.add('A', Rogue(), transitions={'a': 'done'})
    with pytest.raises(TransitionError):
        step.execute(Userdata())


def test_step_missing_transition_for_outcome_raises():
    step = StateMachine(outcomes=['done', 'failed'])
    step.add('A', Chooser(), transitions={'left': 'done'})  # no 'right' mapping
    with pytest.raises(TransitionError):
        step.execute(Userdata({'pick': 'right'}))


# ---------------------------------------------------------------------------
# Late binding by string ID
# ---------------------------------------------------------------------------


def test_step_adds_child_by_string_id():
    # Succeeder is already registered by @register_state at import time; but
    # clear_registry fixture wiped it.  Re-register inline.
    StateRegistry.register('Succeeder', Succeeder)
    step = StateMachine(outcomes=['done'])
    step.add('A', 'Succeeder', transitions={'done': 'done'})
    assert step.execute(Userdata()) == 'done'


# ---------------------------------------------------------------------------
# Nested StateMachine (Step inside Step)
# ---------------------------------------------------------------------------


def test_nested_stepmachines_bubble_outcome():
    inner = StateMachine(outcomes=['done', 'failed'])
    inner.add('x', Succeeder(tag='x'), transitions={'done': 'done'})

    outer = StateMachine(outcomes=['done', 'failed'])
    outer.add('IN', inner, transitions={'done': 'AFTER'})
    outer.add('AFTER', Succeeder(tag='after'), transitions={'done': 'done'})

    ud = Userdata()
    assert outer.execute(ud) == 'done'
    assert ud['trace'] == ['x', 'after']


# ---------------------------------------------------------------------------
# BehaviorSM (SubJob)
# ---------------------------------------------------------------------------


def test_behavior_sm_run_with_behavior_parameter_and_userdata_chain():
    class VisitOne(BehaviorSM):
        behavior_parameters = ['target']
        outcomes = ['done', 'failed']

    # Step 1: one SubStep that just succeeds.
    step1 = StateMachine(outcomes=['done'])
    step1.add('substep_call', Succeeder(tag='call'), transitions={'done': 'done'})

    # Step 2: use behavior_parameter 'target' from userdata.
    @register_state
    class VerifyTarget(State):
        outcomes = ['ok']

        def execute(self, userdata: Userdata) -> str:
            trace = userdata.get('trace', [])
            trace.append(f'target={userdata["target"]}')
            userdata['trace'] = trace
            return 'ok'

    step2 = StateMachine(outcomes=['done'])
    step2.add('verify', VerifyTarget(), transitions={'ok': 'done'})

    sj = VisitOne()
    sj.add('STEP1', step1, transitions={'done': 'STEP2'})
    sj.add('STEP2', step2, transitions={'done': 'done'})

    outcome, userdata_out = sj.run(
        behavior_parameter={'target': 'cup'},
        userdata_in={'trace': []},
    )
    assert outcome == 'done'
    assert userdata_out['trace'] == ['call', 'target=cup']
    assert userdata_out['target'] == 'cup'


def test_behavior_sm_missing_behavior_parameter_raises():
    class Needs(BehaviorSM):
        behavior_parameters = ['required_thing']
        outcomes = ['done']

    sj = Needs()
    sj.add('A', Succeeder(tag='A'), transitions={'done': 'done'})

    with pytest.raises(HsmError):
        sj.run(behavior_parameter={}, userdata_in={})


def test_behavior_sm_empty_raises():
    class Empty(BehaviorSM):
        outcomes = ['done']

    with pytest.raises(HsmError):
        Empty().run()
