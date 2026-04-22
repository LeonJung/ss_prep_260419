"""Tests for RetryDecorator."""

import pytest

from mw_hfsm_engine import (
    RetryDecorator,
    State,
    StateRegistry,
    Userdata,
)


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    yield
    StateRegistry.clear()


class _Countdown(State):
    """State that fails `fail_count` times then succeeds."""

    outcomes = ['succeeded', 'failed']

    def __init__(self, fail_count: int):
        super().__init__()
        self.fail_count = fail_count
        self.invocations = 0

    def execute(self, userdata: Userdata) -> str:
        self.invocations += 1
        if self.invocations <= self.fail_count:
            return 'failed'
        return 'succeeded'


class _AlwaysFails(State):
    outcomes = ['succeeded', 'failed']

    def __init__(self):
        super().__init__()
        self.invocations = 0

    def execute(self, userdata):
        self.invocations += 1
        return 'failed'


class _AlwaysCanceled(State):
    outcomes = ['succeeded', 'failed', 'canceled']

    def execute(self, userdata):
        return 'canceled'


def test_retry_succeeds_first_try_returns_without_retry():
    inner = _Countdown(fail_count=0)
    deco = RetryDecorator(inner, max_retries=3)
    assert deco.execute(Userdata()) == 'succeeded'
    assert inner.invocations == 1


def test_retry_recovers_within_budget():
    inner = _Countdown(fail_count=2)  # fails twice, succeeds on 3rd
    deco = RetryDecorator(inner, max_retries=3)
    assert deco.execute(Userdata()) == 'succeeded'
    assert inner.invocations == 3


def test_retry_exhausts_budget_and_returns_failed():
    inner = _AlwaysFails()
    deco = RetryDecorator(inner, max_retries=2)
    assert deco.execute(Userdata()) == 'failed'
    # Budget of 2 retries = 1 initial + 2 extras = 3 invocations.
    assert inner.invocations == 3


def test_retry_does_not_retry_non_retry_outcome():
    # retry_outcome defaults to 'failed'; a 'canceled' outcome must pass
    # through unchanged without triggering retry.
    inner = _AlwaysCanceled()
    deco = RetryDecorator(inner, max_retries=5, retry_outcome='failed')
    assert deco.execute(Userdata()) == 'canceled'


def test_retry_custom_retry_outcome():
    # If retry_outcome='aborted', only 'aborted' triggers retries.
    class Flaky(State):
        outcomes = ['done', 'aborted']

        def __init__(self):
            super().__init__()
            self.n = 0

        def execute(self, userdata):
            self.n += 1
            return 'aborted' if self.n <= 1 else 'done'

    inner = Flaky()
    deco = RetryDecorator(inner, max_retries=3, retry_outcome='aborted')
    assert deco.execute(Userdata()) == 'done'
    assert inner.n == 2


def test_retry_outcome_must_be_in_inner_outcomes():
    class X(State):
        outcomes = ['a', 'b']

        def execute(self, userdata):
            return 'a'

    with pytest.raises(ValueError):
        RetryDecorator(X(), max_retries=1, retry_outcome='nope')


def test_retry_inner_must_be_state():
    with pytest.raises(TypeError):
        RetryDecorator(inner='not a state', max_retries=1)


def test_retry_negative_max_rejected():
    with pytest.raises(ValueError):
        RetryDecorator(_Countdown(0), max_retries=-1)


def test_retry_zero_max_runs_once():
    inner = _AlwaysFails()
    deco = RetryDecorator(inner, max_retries=0)
    assert deco.execute(Userdata()) == 'failed'
    assert inner.invocations == 1
