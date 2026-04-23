"""BehaviorSM — the SubJob layer: robot-side top orchestration unit.

A BehaviorSM is the dispatch entry point.  An external dispatcher (the ROS 2
action bridge, in practice) constructs one, supplies a behavior_parameter
dict plus userdata_in, calls `run()`, and receives (outcome, userdata_out).

Structurally it IS a StateMachine — the only differences are:
- declared `behavior_parameters` list (design-time contract with the dispatcher)
- `run()` convenience that seeds userdata and returns userdata out

Work / Job layers (MCS / RCS concepts) are intentionally NOT materialized
here; they live on other PCs and only talk to us via the dispatch interface.
"""

from __future__ import annotations

from typing import Any

from . import cancel as _cancel
from . import observer as _observer
from .exceptions import HfsmError
from .state_machine import StateMachine
from .userdata import Userdata


class BehaviorSM(StateMachine):
    """SubJob-level container.  Declared with a behavior_parameter contract."""

    # Subclasses typically override behavior_parameters at the class level.
    behavior_parameters: list[str] = []

    def __init__(
        self,
        outcomes: list[str] | None = None,
        initial_state: str | None = None,
        behavior_parameters: list[str] | None = None,
    ):
        super().__init__(outcomes=outcomes, initial_state=initial_state)
        if behavior_parameters is not None:
            self.behavior_parameters = list(behavior_parameters)

    def run(
        self,
        behavior_parameter: dict[str, Any] | None = None,
        userdata_in: dict[str, Any] | None = None,
        cancel_token: _cancel.CancelToken | None = None,
        root_name: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Dispatch entry point.

        Returns (outcome, userdata_out).  `outcome` is one of self.outcomes.
        """
        behavior_parameter = behavior_parameter or {}
        userdata_in = userdata_in or {}

        missing = [p for p in self.behavior_parameters if p not in behavior_parameter]
        if missing:
            raise HfsmError(
                f'{type(self).__name__}: missing behavior_parameter(s): {missing}'
            )

        # Seed userdata: behavior_parameter merged with userdata_in.
        # behavior_parameter takes precedence (design-time fixed) — in practice
        # the two key spaces shouldn't collide; if they do, that's a bug worth
        # surfacing via this ordering.
        seed: dict[str, Any] = {}
        seed.update(userdata_in)
        seed.update(behavior_parameter)
        userdata = Userdata(seed)

        # Install the cancel token in the current context so every
        # descendant State can poll it without parameter plumbing.
        _cancel.install_token(cancel_token)
        # Root of the observer path is the caller-supplied name (so the
        # executor can use the dispatched subjob_id), falling back to
        # the BehaviorSM's class name for test and CLI callers.
        _observer.reset_global_path()
        parent_path = _observer.enter(root_name or type(self).__name__)
        outcome: str | None = None
        try:
            outcome = self.execute(userdata)
        finally:
            _observer.exit(parent_path, outcome)
            _observer.reset_global_path()
            _cancel.install_token(None)
        return outcome, userdata.to_dict()

    def to_spec(self) -> dict:
        spec = super().to_spec()
        spec['kind'] = 'BehaviorSM'
        spec['behavior_parameters'] = list(self.behavior_parameters)
        return spec
