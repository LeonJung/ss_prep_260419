"""Spec loader — build a BehaviorSM / StateMachine / State tree from a dict.

The dict shape is our self-built DSL.  Authored either directly as JSON/
YAML in the task repository or produced by future editors.  The executor
can keep using @register_state-authored SubJobs *or* load a spec through
this loader; both paths produce the same State/StateMachine/BehaviorSM
instances the engine already knows how to run.

Schema (by "kind"):

  State:
    {
      "kind": "State",
      "ref":  "<StateRegistry id>",
      "args": {... constructor kwargs ...}
    }

  StateMachine:
    {
      "kind": "StateMachine",
      "outcomes": ["done", "failed"],
      "initial_state": "<child name (optional — defaults to first)>",
      "children": {
          "<child name>": <nested spec>,
          ...
      },
      "transitions": {
          "<child name>": {"<child outcome>": "<next child name or outcome>", ...},
          ...
      }
    }

  BehaviorSM:
    like StateMachine plus:
      "behavior_parameters": ["param1", ...]

  Parallel:
    {
      "kind": "Parallel",
      "policy": "first_wins",
      "regions": {
          "<region name>": {
              "state": <nested spec>,
              "outcomes": {"<inner outcome>": "<parallel outcome>", ...}
          },
          ...
      }
    }

Node injection: if a `node` argument is passed to `build_from_spec`, it
is forwarded to the constructed State classes via keyword (`node=...`).
Classes whose __init__ doesn't accept `node` are instantiated without it.
"""

from __future__ import annotations

from typing import Any

from .behavior_sm import BehaviorSM
from .exceptions import HfsmError
from .parallel import Parallel, Region
from .state import State, StateRegistry
from .state_machine import StateMachine


def build_from_spec(spec: dict[str, Any], node: Any = None) -> State:
    """Entry point.  `spec` is the parsed dict; `node` is an optional rclpy
    Node that gets forwarded into leaf State constructors that accept it."""
    if not isinstance(spec, dict):
        raise HfsmError(f'spec must be a dict, got {type(spec).__name__}')

    kind = spec.get('kind', 'State')
    if kind == 'State':
        return _build_state(spec, node)
    if kind == 'StateMachine':
        return _build_state_machine(spec, node)
    if kind == 'BehaviorSM':
        return _build_behavior_sm(spec, node)
    if kind == 'Parallel':
        return _build_parallel(spec, node)
    raise HfsmError(f'unknown spec kind: {kind!r}')


# ---------------------------------------------------------------------------
# Builders per kind
# ---------------------------------------------------------------------------

def _build_state(spec: dict[str, Any], node: Any) -> State:
    ref = spec.get('ref')
    if not ref:
        raise HfsmError(f'State spec missing "ref": {spec!r}')
    klass = StateRegistry.resolve(ref)
    if not issubclass(klass, State):
        raise HfsmError(
            f'ref {ref!r} resolves to {klass.__name__}, not a State subclass'
        )
    kwargs = dict(spec.get('args') or {})
    # Try passing node first; fall back gracefully for pure-Python states.
    try:
        return klass(node=node, **kwargs) if node is not None else klass(**kwargs)
    except TypeError:
        return klass(**kwargs)


def _build_state_machine(spec: dict[str, Any], node: Any) -> StateMachine:
    outcomes = list(spec.get('outcomes') or ['done', 'failed'])
    initial_state = spec.get('initial_state')
    sm = StateMachine(outcomes=outcomes, initial_state=initial_state)
    _attach_children(sm, spec, node)
    return sm


def _build_behavior_sm(spec: dict[str, Any], node: Any) -> BehaviorSM:
    outcomes = list(spec.get('outcomes') or ['done', 'failed'])
    initial_state = spec.get('initial_state')
    bps = list(spec.get('behavior_parameters') or [])
    sm = BehaviorSM(
        outcomes=outcomes,
        initial_state=initial_state,
        behavior_parameters=bps,
    )
    _attach_children(sm, spec, node)
    return sm


def _build_parallel(spec: dict[str, Any], node: Any) -> Parallel:
    policy = spec.get('policy', 'first_wins')
    regions_spec = spec.get('regions') or {}
    if not regions_spec:
        raise HfsmError('Parallel spec must define at least one region')
    regions: dict[str, Region] = {}
    for name, r_spec in regions_spec.items():
        if 'state' not in r_spec:
            raise HfsmError(
                f'Parallel region {name!r} missing "state": {r_spec!r}'
            )
        inner = build_from_spec(r_spec['state'], node)
        regions[name] = Region(
            state=inner,
            outcomes=dict(r_spec.get('outcomes') or {}),
        )
    return Parallel(regions=regions, policy=policy)


# ---------------------------------------------------------------------------
# Shared helper — children/transitions plumbing for SM + BehaviorSM
# ---------------------------------------------------------------------------

def _attach_children(
    sm: StateMachine, spec: dict[str, Any], node: Any,
) -> None:
    children = spec.get('children') or {}
    transitions = spec.get('transitions') or {}
    for name, child_spec in children.items():
        child = build_from_spec(child_spec, node)
        sm.add(name, child, transitions.get(name, {}))
