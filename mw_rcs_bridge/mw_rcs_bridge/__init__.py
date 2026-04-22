"""mw_rcs_bridge — Phase 5 stub translating between a remote RCS and the
local HFSM executor.

At this stage we ship:
- A schema module defining the request/response shapes the eventual
  VDA5050-aligned protocol will carry.  Having these as Python
  dataclasses makes the contract reviewable and unit-testable before
  any wire code lands.
- A minimal HTTP bridge node that:
    * accepts POST /order  → forwards to /mw_task_manager/execute_sub_job
    * accepts POST /cancel → forwards the goal-cancel request
    * exposes GET /state   → snapshot of the latest HfsmExecutionStatus
  No WebSocket push yet; the frontend/RCS can poll /state until the
  streaming pipe is ready.

Everything here is explicitly a stub: enough surface to demo an
RCS-like external client + enough tests to lock the schema before we
iterate.  The real VDA5050 conversion and the WebSocket stream come
when we wire against a concrete RCS.
"""

from .schema import (
    OrderRequest,
    OrderResponse,
    StateSnapshot,
    CancelRequest,
    CancelResponse,
)

__all__ = [
    'OrderRequest',
    'OrderResponse',
    'StateSnapshot',
    'CancelRequest',
    'CancelResponse',
]
