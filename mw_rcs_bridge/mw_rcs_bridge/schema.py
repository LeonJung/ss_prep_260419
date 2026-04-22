"""RCS bridge request/response dataclasses.

Names and field semantics borrow from VDA5050 (order / state / action)
while keeping the SubJob hierarchy the robot-side Task Manager already
understands.  Full VDA5050 alignment — topic namespacing, time-
synced state publication, factsheet — lands once a concrete RCS is
available to test against.

Shape at a glance:

    POST /order       → OrderRequest        ↦ OrderResponse
    POST /cancel      → CancelRequest       ↦ CancelResponse
    GET  /state                              ↦ StateSnapshot

These are intentionally flat JSON-friendly dicts under the hood (via
dataclasses.asdict) so the REST layer can (de)serialize with the
stdlib `json` module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OrderRequest:
    """An RCS dispatch request targeting one SubJob."""

    subjob_id: str
    behavior_parameter: dict[str, Any] = field(default_factory=dict)
    userdata_in: dict[str, Any] = field(default_factory=dict)
    # VDA5050-esque identifiers — echoed back in state updates.
    order_id: str = ''
    order_update_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'OrderRequest':
        if not isinstance(data, dict):
            raise TypeError('OrderRequest body must be a JSON object')
        if not data.get('subjob_id'):
            raise ValueError('OrderRequest requires "subjob_id"')
        return cls(
            subjob_id=str(data['subjob_id']),
            behavior_parameter=dict(data.get('behavior_parameter') or {}),
            userdata_in=dict(data.get('userdata_in') or {}),
            order_id=str(data.get('order_id') or ''),
            order_update_id=int(data.get('order_update_id') or 0),
        )


@dataclass
class OrderResponse:
    ok: bool
    order_id: str
    message: str = 'dispatched'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CancelRequest:
    order_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'CancelRequest':
        if not isinstance(data, dict) or not data.get('order_id'):
            raise ValueError('CancelRequest requires "order_id"')
        return cls(order_id=str(data['order_id']))


@dataclass
class CancelResponse:
    ok: bool
    message: str = 'cancel requested'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StateSnapshot:
    """Whatever the HFSM executor last published on /mw_hfsm_status,
    repackaged in an RCS-friendly shape."""

    order_id: str
    subjob_id: str
    status: str              # 'idle' | 'running' | 'success' | 'failure'
    active_state: str
    userdata_snapshot: dict[str, Any]
    elapsed_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
