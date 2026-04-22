"""State decorators — wrappers that change how a child state is executed.

Phase 1 ships RetryDecorator.  Planned additions (as need arises):
- InverterDecorator: flip 'succeeded' ↔ 'failed'.
- TimeoutDecorator: give up after N seconds, return 'timeout'.
- RateLimitDecorator: ensure minimum period between invocations.
"""

from __future__ import annotations

from .state import State
from .userdata import Userdata


class RetryDecorator(State):
    """Retry an inner state up to `max_retries` additional times on a given outcome.

    The inner state runs once; if its outcome equals `retry_outcome`, it runs
    again, up to `max_retries` additional attempts (so the total invocations
    are at most `max_retries + 1`).  Any other outcome returns immediately.
    After exhausting retries, whatever outcome the inner emits is returned —
    including `retry_outcome` itself if it's still failing.

    This implements "iteration is the parent's job" correctly: RetryDecorator
    is a parent that repeats one child.  The child itself is oblivious.

    outcomes == inner.outcomes (same terminal set).
    """

    def __init__(
        self,
        inner: State,
        max_retries: int = 3,
        retry_outcome: str = 'failed',
    ):
        if not isinstance(inner, State):
            raise TypeError(
                f'RetryDecorator inner must be a State, '
                f'got {type(inner).__name__}'
            )
        if max_retries < 0:
            raise ValueError('max_retries must be >= 0')
        if retry_outcome not in inner.outcomes:
            raise ValueError(
                f'retry_outcome "{retry_outcome}" not in inner.outcomes '
                f'({inner.outcomes})'
            )
        super().__init__()
        self.inner = inner
        self.max_retries = max_retries
        self.retry_outcome = retry_outcome
        # Mirror inner's outcomes — this decorator does not introduce new ones.
        self.outcomes = list(inner.outcomes)

    def execute(self, userdata: Userdata) -> str:
        last = self.inner.execute(userdata)
        attempts = 1
        while last == self.retry_outcome and attempts <= self.max_retries:
            last = self.inner.execute(userdata)
            attempts += 1
        return last
