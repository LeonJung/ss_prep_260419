"""State — the SubStep layer: one driver API call (or a small composite).

Every State declares its possible outcomes up front.  Concrete states
override `execute(userdata) -> outcome_name`.

Late binding: `@register_state` records the class in StateRegistry, so
containers can reference states by string ID instead of import.
"""

from __future__ import annotations

from typing import Any, TypeVar

from .exceptions import RegistryError
from .userdata import Userdata


class State:
    """Base class for SubStep-level engine units.

    Subclass it and override `execute(userdata) -> outcome_str`.
    Declare `outcomes` as a class attribute (list of valid outcome names).
    """

    outcomes: list[str] = ['done']

    def __init__(self, **kwargs: Any):
        # kwargs stashed for introspection / serialization / editor use.
        # Subclasses can override __init__ and capture specific params.
        self._init_kwargs = kwargs

    def execute(self, userdata: Userdata) -> str:
        """Run one invocation. Must return one of self.outcomes."""
        raise NotImplementedError(
            f'{type(self).__name__}.execute not implemented'
        )

    def __repr__(self) -> str:
        return f'{type(self).__name__}(outcomes={self.outcomes})'


# ---------------------------------------------------------------------------
# StateRegistry + @register_state
# ---------------------------------------------------------------------------

T = TypeVar('T', bound=type)


class StateRegistry:
    """Global registry for late-binding state references.

    `@register_state` writes to this registry.  StateMachine.add(name, ref)
    resolves ref against this registry when ref is a string.
    """

    _classes: dict[str, type] = {}

    @classmethod
    def register(cls, id: str, klass: type, *, override: bool = False) -> None:
        if id in cls._classes and not override:
            raise RegistryError(
                f'state id "{id}" already registered as '
                f'{cls._classes[id].__name__}; pass override=True to replace'
            )
        cls._classes[id] = klass

    @classmethod
    def resolve(cls, id: str) -> type:
        try:
            return cls._classes[id]
        except KeyError as err:
            raise RegistryError(
                f'state id "{id}" not registered; '
                f'available: {sorted(cls._classes)}'
            ) from err

    @classmethod
    def clear(cls) -> None:
        """Reset registry — intended for tests only."""
        cls._classes.clear()

    @classmethod
    def ids(cls) -> list[str]:
        return sorted(cls._classes)


def register_state(arg: Any = None, *, override: bool = False) -> Any:
    """Decorator: register a class under its name (or a custom id).

    Usage:
        @register_state
        class GraspItem(State):
            ...

        @register_state("CustomId")
        class Grasp(State):
            ...

        @register_state(override=True)
        class GraspItem(State):   # silently replaces previous
            ...
    """

    def apply(klass: type, id: str) -> type:
        StateRegistry.register(id, klass, override=override)
        return klass

    # Form 1: @register_state (bare) — arg is the class.
    if isinstance(arg, type):
        return apply(arg, arg.__name__)

    # Form 2: @register_state("CustomId") or @register_state(override=True).
    def decorator(klass: type) -> type:
        id = arg if isinstance(arg, str) else klass.__name__
        return apply(klass, id)

    return decorator
