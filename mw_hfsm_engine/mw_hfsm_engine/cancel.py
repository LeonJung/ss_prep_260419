"""Cooperative cancellation primitives.

CancelToken is a thread-safe flag plus the exception engine users throw
when they honor it.  The contextvar lets nested StateMachines and their
leaf States pick up the current token without every execute() signature
needing a keyword.

StateMachine.execute checks the token at its loop boundary; long-running
States (LifecycleAwareActionState) poll the token via
`engine.is_cancellation_requested()` inside their wait loops and raise
CancelledError on the next check.  Parent StateMachines catch
CancelledError at the loop boundary and re-raise so the BehaviorSM.run
caller sees a single exception for a canceled run (alternatively they
could return a 'canceled' outcome, but canceling is an interruption of
a plan, not a planned outcome — making it an exception keeps the
transition table clean and avoids polluting every SubJob's outcome list).
"""

from __future__ import annotations

import contextvars
import threading
from typing import Optional


class CancelledError(Exception):
    """Raised by states that honored a CancelToken.

    BehaviorSM.run surfaces this to the caller (typically the ROS 2
    executor) instead of returning an outcome.  Mid-hierarchy parents
    propagate, they do not swallow — cancellation is end-to-end.
    """


class CancelToken:
    """Flag-style cancel signal shared across threads.

    Usage: construct one in the dispatcher, pass it via install_token()
    into the context that runs the SubJob, call `request()` from any
    thread (e.g. the ROS 2 action cancel callback) to request a halt.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def reset(self) -> None:
        self._event.clear()


# Context-scoped token so nested execution paths can read it without
# plumbing a parameter through every method call.
_TOKEN: contextvars.ContextVar[Optional[CancelToken]] = (
    contextvars.ContextVar('hfsm_cancel_token', default=None)
)


def install_token(token: Optional[CancelToken]) -> None:
    """Install `token` as the cancellation signal for the current context.

    Pass None to clear.  Installed in BehaviorSM.run so the whole SubJob
    tree sees the same token without any explicit wiring.
    """
    _TOKEN.set(token)


def current_token() -> Optional[CancelToken]:
    return _TOKEN.get()


def is_cancellation_requested() -> bool:
    tok = _TOKEN.get()
    return tok is not None and tok.is_set()


def raise_if_cancelled() -> None:
    """Convenience — call from a State's wait loop to interrupt promptly."""
    if is_cancellation_requested():
        raise CancelledError('cancellation requested')
