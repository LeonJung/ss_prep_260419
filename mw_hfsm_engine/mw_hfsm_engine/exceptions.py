"""Engine exceptions. All inherit from HfsmError for catch-all."""


class HfsmError(Exception):
    """Base exception for all HFSM engine errors."""


class TransitionError(HfsmError):
    """Raised when a state emits an outcome with no matching transition."""


class RegistryError(HfsmError):
    """Raised for late-binding resolution failures (unknown ID, etc)."""


class SelfIterationError(HfsmError):
    """Raised when a layer tries to add itself or iterate over itself.

    Enforces the core rule: every layer is one invocation, iteration of
    children is the parent's responsibility.
    """
