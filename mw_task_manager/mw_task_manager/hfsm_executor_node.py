"""HFSM executor node — runs a SubJob (a BehaviorSM class) on demand.

Phase 1 scope:
- Resolve subjob_id against mw_hfsm_engine's StateRegistry (no JSON spec loader yet).
- Accept one ExecuteSubJob goal at a time; reject concurrent goals.
- Run the SubJob on a worker thread so the rclpy executor stays responsive
  to lifecycle / action callbacks the SubJob's substates will hit.
- Publish /mw_hfsm_status at a steady rate so the web GUI can render state.

Not yet in Phase 1:
- JSON/YAML spec loading (via mw_task_repository).  For now, the user
  authors SubJobs as Python classes decorated with @register_state, and
  lists the importable module paths via the `subjob_modules` parameter.
- Cancel support inside the engine (goal cancel currently becomes a
  no-op; the SubJob runs to completion and the action reports 'canceled'
  only if we can stop it at the outer boundary).  Full cooperative
  cancellation is a later pass tied to Parallel region cancel + action
  goal cancel.
"""

from __future__ import annotations

import importlib
import json
import threading
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from mw_hfsm_engine import (
    BehaviorSM,
    CancelledError,
    CancelToken,
    HfsmError,
    StateRegistry,
    active_path,
)
from mw_task_msgs.action import ExecuteSubJob
from mw_task_msgs.msg import HfsmExecutionStatus


class HfsmExecutorNode(Node):
    """ROS 2 node that runs SubJobs from the HFSM engine."""

    def __init__(self) -> None:
        super().__init__('mw_hfsm_executor')

        self.declare_parameter('status_publish_hz', 10.0)
        self.declare_parameter('subjob_modules', [''])
        self.declare_parameter('default_action_name',
                               '/mw_task_manager/execute_sub_job')

        self._import_subjob_modules()

        self._status_lock = threading.Lock()
        self._current_subjob_id: str = ''
        self._current_active_state: str = ''
        self._current_status: int = HfsmExecutionStatus.STATUS_IDLE
        self._current_spec_json: str = ''
        self._current_userdata_snapshot_json: str = '{}'
        self._start_time = self.get_clock().now()
        self._busy = False
        self._current_cancel_token: CancelToken | None = None

        self._cb_group = ReentrantCallbackGroup()

        self._status_pub = self.create_publisher(
            HfsmExecutionStatus, '/mw_hfsm_status', 10,
        )
        period = 1.0 / max(
            0.1, float(self.get_parameter('status_publish_hz').value),
        )
        self._status_timer = self.create_timer(
            period, self._publish_status, callback_group=self._cb_group,
        )

        self._action_server = ActionServer(
            self,
            ExecuteSubJob,
            self.get_parameter('default_action_name').value,
            execute_callback=self._execute_goal,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._cb_group,
        )

        self.get_logger().info(
            'mw_hfsm_executor ready. registered subjobs: %s'
            % sorted(StateRegistry.ids()),
        )

    # ------------------------------------------------------------------
    # Parameter-driven imports so users can point the node at their own
    # SubJob modules without changing this code.
    # ------------------------------------------------------------------
    def _import_subjob_modules(self) -> None:
        mods = self.get_parameter('subjob_modules').value or []
        for m in mods:
            if not m:
                continue
            try:
                importlib.import_module(m)
                self.get_logger().info(f'imported subjob module: {m}')
            except Exception as exc:  # noqa: BLE001
                self.get_logger().error(
                    f'failed to import subjob module {m!r}: {exc}'
                )

    # ------------------------------------------------------------------
    # Action callbacks
    # ------------------------------------------------------------------
    def _goal_callback(self, goal_request: ExecuteSubJob.Goal) -> GoalResponse:
        with self._status_lock:
            if self._busy:
                self.get_logger().warn(
                    f'rejecting ExecuteSubJob goal: already running '
                    f'{self._current_subjob_id!r}'
                )
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(
        self, goal_handle: ServerGoalHandle,
    ) -> CancelResponse:
        # Flip the cooperative cancel token.  StateMachine.execute checks
        # it between children and LifecycleAwareActionState polls it
        # inside its future-wait loop, so the SubJob worker raises
        # CancelledError at the next checkpoint.
        with self._status_lock:
            token = self._current_cancel_token
        if token is not None:
            token.request()
        return CancelResponse.ACCEPT

    def _execute_goal(
        self, goal_handle: ServerGoalHandle,
    ) -> ExecuteSubJob.Result:
        goal = goal_handle.request
        result = ExecuteSubJob.Result()

        subjob_id = goal.subjob_id
        behavior_parameter = _safe_json_loads(goal.behavior_parameter_json)
        userdata_in = _safe_json_loads(goal.userdata_in_json)

        cancel_token = CancelToken()
        with self._status_lock:
            self._busy = True
            self._current_subjob_id = subjob_id
            self._current_status = HfsmExecutionStatus.STATUS_RUNNING
            self._current_active_state = ''
            self._current_userdata_snapshot_json = json.dumps(userdata_in)
            self._current_spec_json = ''  # populated once SubJob is built
            self._start_time = self.get_clock().now()
            self._current_cancel_token = cancel_token

        self.get_logger().info(
            f'ExecuteSubJob: id={subjob_id!r} '
            f'params={behavior_parameter!r} userdata_in={userdata_in!r}'
        )

        try:
            sm = self._build_subjob(subjob_id)
        except Exception as exc:  # noqa: BLE001
            return self._finish_failure(
                goal_handle, result, subjob_id,
                outcome='build_error', message=str(exc),
                userdata_out={},
            )

        # Serialize the SubJob spec once at dispatch time so the GUI gets
        # the full chart on its next /mw_hfsm_status tick.
        try:
            spec = sm.to_spec()
            spec_json = json.dumps(spec)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(
                f'spec serialization failed (GUI chart will be empty): {exc}'
            )
            spec_json = ''
        with self._status_lock:
            self._current_spec_json = spec_json

        try:
            outcome, userdata_out = sm.run(
                behavior_parameter=behavior_parameter,
                userdata_in=userdata_in,
                cancel_token=cancel_token,
            )
        except CancelledError:
            result.succeeded = False
            result.outcome = 'canceled'
            result.message = 'SubJob canceled by client'
            result.userdata_out_json = json.dumps({})
            with self._status_lock:
                self._busy = False
                self._current_status = HfsmExecutionStatus.STATUS_FAILURE
                self._current_userdata_snapshot_json = json.dumps({})
                self._current_active_state = (
                    f'{type(sm).__name__} → canceled'
                )
                self._current_cancel_token = None
            self.get_logger().info(
                f'ExecuteSubJob canceled: subjob_id={subjob_id!r}'
            )
            goal_handle.canceled()
            return result
        except Exception as exc:  # noqa: BLE001
            return self._finish_failure(
                goal_handle, result, subjob_id,
                outcome='exception', message=repr(exc),
                userdata_out={},
            )

        succeeded = outcome in _SUCCESS_OUTCOMES
        with self._status_lock:
            self._busy = False
            self._current_status = (
                HfsmExecutionStatus.STATUS_SUCCESS
                if succeeded else HfsmExecutionStatus.STATUS_FAILURE
            )
            self._current_userdata_snapshot_json = json.dumps(userdata_out)
            # Freeze a descriptive terminal state so the GUI keeps showing
            # where the SubJob ended instead of flashing to empty.
            self._current_active_state = f'{type(sm).__name__} → {outcome}'
            self._current_cancel_token = None

        result.succeeded = succeeded
        result.outcome = outcome
        result.message = 'ok' if succeeded else f'outcome={outcome}'
        result.userdata_out_json = json.dumps(userdata_out)

        if succeeded:
            goal_handle.succeed()
        else:
            goal_handle.abort()
        return result

    # ------------------------------------------------------------------
    # Construction / helpers
    # ------------------------------------------------------------------
    def _build_subjob(self, subjob_id: str) -> BehaviorSM:
        klass = StateRegistry.resolve(subjob_id)
        if not issubclass(klass, BehaviorSM):
            raise HfsmError(
                f'subjob_id {subjob_id!r} resolves to '
                f'{klass.__name__}, which is not a BehaviorSM'
            )
        # Subclasses may or may not accept `node` — fall back gracefully.
        try:
            return klass(node=self)
        except TypeError:
            return klass()

    def _finish_failure(
        self,
        goal_handle: ServerGoalHandle,
        result: ExecuteSubJob.Result,
        subjob_id: str,
        *,
        outcome: str,
        message: str,
        userdata_out: dict[str, Any],
    ) -> ExecuteSubJob.Result:
        with self._status_lock:
            self._busy = False
            self._current_status = HfsmExecutionStatus.STATUS_FAILURE
            self._current_userdata_snapshot_json = json.dumps(userdata_out)

        self.get_logger().error(
            f'ExecuteSubJob failed: subjob_id={subjob_id!r} '
            f'outcome={outcome!r} message={message!r}'
        )
        result.succeeded = False
        result.outcome = outcome
        result.message = message
        result.userdata_out_json = json.dumps(userdata_out)
        goal_handle.abort()
        return result

    # ------------------------------------------------------------------
    # Status publishing
    # ------------------------------------------------------------------
    def _publish_status(self) -> None:
        # active_path() is read from the engine's thread-safe global slot
        # outside the lock — it reflects whichever state's execute() is
        # on the worker thread right now.
        live_path = active_path()
        with self._status_lock:
            msg = HfsmExecutionStatus()
            msg.subjob_id = self._current_subjob_id
            msg.spec_json = self._current_spec_json
            msg.active_state = live_path if self._busy else self._current_active_state
            msg.userdata_snapshot_json = self._current_userdata_snapshot_json
            msg.status = self._current_status
            msg.start_time = self._start_time.to_msg()
            if self._current_status == HfsmExecutionStatus.STATUS_RUNNING:
                elapsed = (self.get_clock().now() - self._start_time)
                msg.elapsed_sec = elapsed.nanoseconds * 1e-9
            else:
                msg.elapsed_sec = 0.0
        self._status_pub.publish(msg)


_SUCCESS_OUTCOMES = frozenset({'done', 'succeeded'})


def _safe_json_loads(s: str) -> dict[str, Any]:
    s = (s or '').strip()
    if not s:
        return {}
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def main() -> None:
    rclpy.init()
    node = HfsmExecutorNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
