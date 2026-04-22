"""RCS bridge node.

Listens over HTTP (Phase 5 stub), forwards order dispatch + cancellation
to the local HFSM executor's ExecuteSubJob action, mirrors the latest
/mw_hfsm_status back out as a /state snapshot.

The handlers run on an HTTPServer worker thread; rclpy spin lives on
the main thread.  ROS-side futures are polled (not spin_until_future)
so both threads can coexist cleanly.

Endpoints (stub):
    POST /order    OrderRequest JSON  → OrderResponse JSON
    POST /cancel   CancelRequest JSON → CancelResponse JSON
    GET  /state                       → StateSnapshot JSON
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from mw_task_msgs.action import ExecuteSubJob
from mw_task_msgs.msg import HfsmExecutionStatus

from .schema import (
    CancelRequest,
    CancelResponse,
    OrderRequest,
    OrderResponse,
    StateSnapshot,
)


_STATUS_LABELS = {
    HfsmExecutionStatus.STATUS_IDLE: 'idle',
    HfsmExecutionStatus.STATUS_RUNNING: 'running',
    HfsmExecutionStatus.STATUS_SUCCESS: 'success',
    HfsmExecutionStatus.STATUS_FAILURE: 'failure',
}


class RcsBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('mw_rcs_bridge')

        self.declare_parameter(
            'action_name', '/mw_task_manager/execute_sub_job'
        )
        self.declare_parameter(
            'status_topic', '/mw_hfsm_status'
        )

        self._action = ActionClient(
            self,
            ExecuteSubJob,
            self.get_parameter('action_name').value,
        )

        # Outstanding goals so we can honor /cancel by order_id.
        self._pending_lock = threading.Lock()
        self._pending: dict[str, object] = {}  # order_id → goal handle

        # Latest state snapshot, captured off the status topic.
        self._state_lock = threading.Lock()
        self._last_state: HfsmExecutionStatus | None = None
        self._last_order_id: str = ''

        self.create_subscription(
            HfsmExecutionStatus,
            self.get_parameter('status_topic').value,
            self._on_status,
            10,
        )

    # ------------------------------------------------------------------
    # ROS-side callbacks
    # ------------------------------------------------------------------
    def _on_status(self, msg: HfsmExecutionStatus) -> None:
        with self._state_lock:
            self._last_state = msg

    # ------------------------------------------------------------------
    # HTTP handlers — called from the server worker thread
    # ------------------------------------------------------------------
    def submit_order(self, req: OrderRequest) -> OrderResponse:
        if not self._action.wait_for_server(timeout_sec=3.0):
            return OrderResponse(
                ok=False, order_id=req.order_id, message='executor unavailable',
            )
        goal = ExecuteSubJob.Goal()
        goal.subjob_id = req.subjob_id
        goal.behavior_parameter_json = json.dumps(req.behavior_parameter)
        goal.userdata_in_json = json.dumps(req.userdata_in)

        order_id = req.order_id or uuid.uuid4().hex
        future = self._action.send_goal_async(goal)

        # We complete the HTTP response without waiting for accept to
        # avoid the rclcpp_action fast-loopback race — progress flows
        # through /state polling like in the web dispatcher.
        with self._pending_lock:
            self._pending[order_id] = future
            self._last_order_id = order_id
        return OrderResponse(ok=True, order_id=order_id, message='dispatched')

    def cancel_order(self, req: CancelRequest) -> CancelResponse:
        with self._pending_lock:
            future = self._pending.get(req.order_id)
        if future is None:
            return CancelResponse(ok=False, message='unknown order_id')
        handle = getattr(future, 'result', lambda: None)()
        if handle is None or not getattr(handle, 'accepted', False):
            return CancelResponse(
                ok=False, message='goal handle not yet accepted',
            )
        handle.cancel_goal_async()
        return CancelResponse(ok=True, message='cancel requested')

    def snapshot(self) -> StateSnapshot:
        with self._state_lock:
            last = self._last_state
            order_id = self._last_order_id
        if last is None:
            return StateSnapshot(
                order_id=order_id, subjob_id='', status='idle',
                active_state='', userdata_snapshot={}, elapsed_sec=0.0,
            )
        try:
            userdata = json.loads(last.userdata_snapshot_json or '{}')
        except json.JSONDecodeError:
            userdata = {}
        return StateSnapshot(
            order_id=order_id,
            subjob_id=last.subjob_id,
            status=_STATUS_LABELS.get(last.status, f'unknown_{last.status}'),
            active_state=last.active_state,
            userdata_snapshot=userdata,
            elapsed_sec=last.elapsed_sec,
        )


# ---------------------------------------------------------------------------
# HTTP server plumbing
# ---------------------------------------------------------------------------


def _build_handler(node: RcsBridgeNode):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/state':
                self._send_json(200, node.snapshot().to_dict())
                return
            self.send_error(404)

        def do_POST(self):
            n = int(self.headers.get('Content-Length', '0'))
            try:
                body = json.loads(self.rfile.read(n) or b'{}')
            except json.JSONDecodeError:
                self._send_json(400, {'ok': False, 'message': 'invalid JSON'})
                return

            if self.path == '/order':
                try:
                    req = OrderRequest.from_dict(body)
                except (TypeError, ValueError) as e:
                    self._send_json(400, {'ok': False, 'message': str(e)})
                    return
                resp = node.submit_order(req)
                self._send_json(200 if resp.ok else 500, resp.to_dict())
                return

            if self.path == '/cancel':
                try:
                    req = CancelRequest.from_dict(body)
                except (TypeError, ValueError) as e:
                    self._send_json(400, {'ok': False, 'message': str(e)})
                    return
                resp = node.cancel_order(req)
                self._send_json(200 if resp.ok else 404, resp.to_dict())
                return

            self.send_error(404)

        # ------------------------------------------------------------
        def _send_json(self, code: int, obj) -> None:
            b = json.dumps(obj).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, fmt, *args):  # silence noisy default
            pass

    return Handler


def main() -> None:
    rclpy.init()
    node = RcsBridgeNode()

    port = int(os.environ.get('RCS_BRIDGE_PORT', '5180'))
    server = HTTPServer(('0.0.0.0', port), _build_handler(node))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    node.get_logger().info(
        f'mw_rcs_bridge REST on 0.0.0.0:{port} '
        f'(POST /order, /cancel ; GET /state)'
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
