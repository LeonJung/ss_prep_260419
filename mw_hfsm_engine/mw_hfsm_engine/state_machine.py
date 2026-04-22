"""StateMachine — the Step layer: a container of States with transitions.

Responsibilities:
- Hold children (State instances, or nested StateMachines).
- Map each child's outcome to either another child's name or a terminal
  outcome of this StateMachine.
- Execute children one at a time, following transitions until a terminal.
- Enforce the core rule: iteration of children is THIS layer's job, a child
  cannot loop over itself.  Adding self as a child raises SelfIterationError.

Late binding: `add(name, ref, ...)` accepts ref as an instance, a class, or
a string ID resolved through StateRegistry.
"""

from __future__ import annotations

from typing import Union

from . import observer as _observer
from .exceptions import HfsmError, SelfIterationError, TransitionError
from .state import State, StateRegistry
from .userdata import Userdata


StateRef = Union[State, type, str]


class StateMachine(State):
    """A Step-layer container.  Executes children per transition map.

    Outcomes declared in `outcomes` are the terminal results bubbled up to
    this machine's parent (which treats a StateMachine just like any State).
    That recursion is what makes hierarchy work.
    """

    # Default terminal outcomes at the Step level.  Subclasses can override
    # by passing outcomes= to __init__ or setting the class attribute.
    outcomes: list[str] = ['done', 'failed']

    def __init__(
        self,
        outcomes: list[str] | None = None,
        initial_state: str | None = None,
    ):
        super().__init__()
        if outcomes is not None:
            # Instance-level override (don't mutate the class attribute).
            self.outcomes = list(outcomes)
        self._children: dict[str, State] = {}
        self._transitions: dict[str, dict[str, str]] = {}
        self._initial_state: str | None = initial_state

    # ------------------------------------------------------------------ add
    def add(
        self,
        name: str,
        state_ref: StateRef,
        transitions: dict[str, str] | None = None,
    ) -> None:
        """Register a child state by name.

        state_ref: a State instance, a State subclass, or a registered ID.
        transitions: mapping of child_outcome -> (another child name OR
            one of self.outcomes).
        """
        if name in self._children:
            raise HfsmError(f'child "{name}" already added')

        state = self._materialize(state_ref)

        if state is self:
            raise SelfIterationError(
                f'state machine cannot add itself as child "{name}"'
            )

        self._children[name] = state
        self._transitions[name] = dict(transitions or {})

        # First added child is the default initial state.
        if self._initial_state is None:
            self._initial_state = name

    @staticmethod
    def _materialize(ref: StateRef) -> State:
        if isinstance(ref, State):
            return ref
        if isinstance(ref, type):
            if not issubclass(ref, State):
                raise HfsmError(
                    f'class {ref.__name__} is not a State subclass'
                )
            return ref()
        if isinstance(ref, str):
            klass = StateRegistry.resolve(ref)
            return klass()
        raise HfsmError(
            f'state_ref must be State | class | id str, got {type(ref).__name__}'
        )

    # -------------------------------------------------------------- execute
    def execute(self, userdata: Userdata) -> str:
        """Run children until a transition produces a terminal outcome."""
        if self._initial_state is None:
            raise HfsmError(
                f'{type(self).__name__} has no child states; '
                f'call add() at least once before execute()'
            )

        current = self._initial_state
        # Safety: a misconfigured transition graph could loop forever at the
        # same name.  We allow revisits (iteration IS this layer's job) but
        # cap per-run visits at a generous ceiling to surface bugs early.
        visit_cap = 10_000
        visits = 0

        while True:
            visits += 1
            if visits > visit_cap:
                raise HfsmError(
                    f'{type(self).__name__}: exceeded {visit_cap} child '
                    f'invocations — possible infinite transition loop'
                )

            child = self._children[current]
            parent_path = _observer.enter(current)
            outcome: str | None = None
            try:
                outcome = child.execute(userdata)
            finally:
                _observer.exit(parent_path, outcome)
            if outcome not in child.outcomes:
                raise TransitionError(
                    f'child "{current}" returned outcome "{outcome}" '
                    f'not in its declared outcomes {child.outcomes}'
                )

            trans = self._transitions[current]
            if outcome not in trans:
                raise TransitionError(
                    f'no transition for child "{current}" outcome "{outcome}"; '
                    f'defined: {list(trans)}'
                )

            target = trans[outcome]
            if target in self.outcomes:
                return target
            if target in self._children:
                current = target
                continue
            raise TransitionError(
                f'transition target "{target}" is neither a terminal outcome '
                f'of {type(self).__name__} ({self.outcomes}) nor a child '
                f'name ({list(self._children)})'
            )

    # --------------------------------------------------------------- introspect
    def children(self) -> dict[str, State]:
        """Return child name → state instance (for observability / serialization)."""
        return dict(self._children)

    def transitions(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in self._transitions.items()}

    def initial(self) -> str | None:
        return self._initial_state

    # ------------------------------------------------------------------ spec
    def to_spec(self) -> dict:
        return {
            'kind': 'StateMachine',
            'id': type(self).__name__,
            'outcomes': list(self.outcomes),
            'initial_state': self._initial_state,
            'children': {
                name: child.to_spec()
                for name, child in self._children.items()
            },
            'transitions': self.transitions(),
        }
