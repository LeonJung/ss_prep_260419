"""Engine exceptions. All inherit from HsmError for catch-all."""


class HsmError(Exception):
    """Base exception for all HFSM engine errors."""


class TransitionError(HsmError):
    """Raised when a state emits an outcome with no matching transition."""


class RegistryError(HsmError):
    """Raised for late-binding resolution failures (unknown ID, etc)."""


class SelfIterationError(HsmError):
    """Raised when a layer tries to add itself or iterate over itself.

    Enforces the core rule: every layer is one invocation, iteration of
    children is the parent's responsibility.
    """
