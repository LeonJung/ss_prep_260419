"""Parallel composite — run multiple regions concurrently, collapse to a
single outcome per a selected policy.

Semantics in Phase 1:
- Each Region holds one child State plus an explicit `outcomes` dict that
  maps child-level outcome strings to Parallel-level outcome strings.  This
  is the colocated-mapping style we chose over BT's threshold-count form;
  it preserves *which* region produced *which* kind of outcome, so the
  enclosing StateMachine can branch accordingly.
- Policy `first_wins`: the first region to produce a mapped outcome wins,
  its mapped outcome becomes the Parallel's outcome, other regions are
  abandoned (background threads keep running to completion; cooperative
  cancellation is a later addition tied to ROS action-cancel support).
- The Parallel's own `outcomes` is auto-derived as the union of all region
  mappings' target values.  The enclosing StateMachine's transitions
  should cover every such target.

Known limitations (Phase 1):
- No cooperative cancellation: a losing region finishes on its own time.
  Userdata writes from losing regions after the winner was declared may
  still land, which can cause logical races.  Design real-world regions
  to write into disjoint userdata keys until we add cancel.
- No `wait_all` policy yet.  Added when the need appears (none in current
  scope).  The API accepts only 'first_wins' today.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .exceptions import HfsmError, TransitionError
from .state import State
from .userdata import Userdata


@dataclass
class Region:
    """One region of a Parallel composite: a child state + outcome mapping.

    The mapping is always explicit — each child outcome we care about maps
    to a Parallel-level outcome name.  Child outcomes not present in the
    mapping are treated as mapping errors (surfaced as TransitionError).
    """

    state: State
    outcomes: dict[str, str]


class Parallel(State):
    """Concurrent composite state.  See module docstring for semantics."""

    _SUPPORTED_POLICIES = ('first_wins',)

    def __init__(
        self,
        regions: dict[str, Region],
        policy: str = 'first_wins',
        poll_interval_sec: float = 0.005,
    ):
        if not regions:
            raise HfsmError('Parallel requires at least one region')
        if policy not in self._SUPPORTED_POLICIES:
            raise HfsmError(
                f'unsupported Parallel policy {policy!r}; '
                f'supported: {self._SUPPORTED_POLICIES}'
            )

        super().__init__()
        self.regions: dict[str, Region] = dict(regions)
        self.policy = policy
        self.poll_interval_sec = poll_interval_sec
        # Derive parallel-level outcomes from region mappings (union, sorted).
        self.outcomes = sorted({
            target
            for region in self.regions.values()
            for target in region.outcomes.values()
        })

    def to_spec(self) -> dict:
        return {
            'kind': 'Parallel',
            'policy': self.policy,
            'outcomes': list(self.outcomes),
            'regions': {
                name: {
                    'state': region.state.to_spec(),
                    'outcomes': dict(region.outcomes),
                }
                for name, region in self.regions.items()
            },
        }

    def execute(self, userdata: Userdata) -> str:
        if self.policy == 'first_wins':
            return self._execute_first_wins(userdata)
        # Defensive — __init__ would have rejected an unknown policy.
        raise HfsmError(f'Parallel policy not implemented: {self.policy}')

    # ------------------------------------------------------------------
    def _execute_first_wins(self, userdata: Userdata) -> str:
        lock = threading.Lock()
        winner: dict[str, str] = {}
        errors: list[tuple[str, Exception]] = []

        def runner(name: str, region: Region) -> None:
            try:
                raw = region.state.execute(userdata)
            except Exception as exc:  # noqa: BLE001 — we capture anything
                with lock:
                    errors.append((name, exc))
                return
            with lock:
                if winner:
                    # Someone already won; our work is now irrelevant.
                    return
                if raw not in region.outcomes:
                    errors.append((
                        name,
                        TransitionError(
                            f'Parallel region "{name}" produced outcome '
                            f'"{raw}" not in its mapping '
                            f'{sorted(region.outcomes)}'
                        ),
                    ))
                    return
                winner['value'] = region.outcomes[raw]

        threads = [
            threading.Thread(target=runner, args=(n, r), daemon=True)
            for n, r in self.regions.items()
        ]
        for t in threads:
            t.start()

        while True:
            with lock:
                if winner:
                    return winner['value']
            if all(not t.is_alive() for t in threads):
                break
            time.sleep(self.poll_interval_sec)

        # All regions finished, nobody produced a mapped outcome.
        with lock:
            if winner:
                return winner['value']
            if errors:
                raise errors[0][1]
        raise TransitionError(
            'Parallel: no region produced a mapped outcome'
        )
