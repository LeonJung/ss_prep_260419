"""Execution observer hook.

A thin context-local sink that containers call as they enter / exit their
children.  Built on `contextvars` so the hook threads through nested
StateMachines without every execute() signature having to change.

Typical consumer is the ROS 2 executor: it creates an observer, publishes
the current active_state path to /mw_hfsm_status, and the engine threads
the path updates in automatically.  Pure-Python tests that don't care
simply don't install an observer; the no-op path has O(1) overhead per
child invocation.
"""

from __future__ import annotations

import contextvars
import threading
from typing import Callable, Optional


ObserverFn = Callable[[str, str, Optional[str]], None]
# args: event ("enter"|"exit"), active_path, child_outcome (only on "exit")


_OBSERVER: contextvars.ContextVar[Optional[ObserverFn]] = (
    contextvars.ContextVar('hfsm_observer', default=None)
)
_ACTIVE_PATH: contextvars.ContextVar[str] = (
    contextvars.ContextVar('hfsm_active_path', default='')
)

# Cross-thread snapshot of the *currently executing* state path.  The
# contextvar above is per-task so reads from another thread (like the
# ROS 2 status publisher timer) would return ''.  A module-level
# variable under a lock gives that thread a readable snapshot — one
# SubJob runs at a time, so a single slot is sufficient.
_GLOBAL_PATH: str = ''
_GLOBAL_LOCK = threading.Lock()


def install_observer(obs: Optional[ObserverFn]) -> None:
    """Install an observer for the current context (and its children).

    Passing None clears it.
    """
    _OBSERVER.set(obs)


def active_path() -> str:
    """Return the dot-joined path of the currently-executing state.

    Thread-safe snapshot — readable from any thread including the status
    publisher timer.  Empty string when no SubJob is running.
    """
    with _GLOBAL_LOCK:
        return _GLOBAL_PATH


def _set_global_path(path: str) -> None:
    global _GLOBAL_PATH
    with _GLOBAL_LOCK:
        _GLOBAL_PATH = path


def enter(segment: str) -> str:
    """Containers call this as they hand control to a child.

    Returns the parent path so the caller can restore it in `exit()`.
    """
    parent = _ACTIVE_PATH.get()
    new_path = f'{parent}.{segment}' if parent else segment
    _ACTIVE_PATH.set(new_path)
    _set_global_path(new_path)
    obs = _OBSERVER.get()
    if obs is not None:
        try:
            obs('enter', new_path, None)
        except Exception:  # noqa: BLE001
            # Never let observer bugs break execution.
            pass
    return parent


def exit(parent_path: str, outcome: str | None) -> None:
    """Containers call this as the child returns; `parent_path` is the value
    enter() returned.
    """
    current = _ACTIVE_PATH.get()
    obs = _OBSERVER.get()
    if obs is not None:
        try:
            obs('exit', current, outcome)
        except Exception:  # noqa: BLE001
            pass
    _ACTIVE_PATH.set(parent_path)
    _set_global_path(parent_path)


def reset_global_path() -> None:
    """Clear the thread-local global path.  Useful between SubJob runs."""
    _set_global_path('')
