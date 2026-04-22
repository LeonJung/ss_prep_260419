"""LifecycleAwareActionState — a generic State that calls a ROS 2 action
on a LifecycleNode-managed skill server.

The execute() flow:
  1. Check the server's lifecycle state.  If not 'active', issue
     `configure` and `activate` transitions (per Layer 3 in our
     lifecycle-management plan).
  2. Wait for the action server to be reachable.
  3. Build the goal from userdata (subclass contract).
  4. Send goal, block until result (by polling Future.done()).
  5. Optionally write result fields back to userdata.
  6. Translate action status and return an outcome string.

Threading contract:
  The caller (typically the SubJob executor) is expected to spin the node
  with a MultiThreadedExecutor on a separate thread, so that action-client
  callbacks keep firing while this state's execute() polls its futures.
  We deliberately do NOT call `rclpy.spin_*` here — double-spinning a node
  is a common source of hangs.

Subclass contract (minimum):
  - class attrs: `action_type`, `action_name`.
  - override `build_goal(userdata) -> action_type.Goal`.
Subclass contract (optional):
  - class attrs: `server_node_name` (enables lifecycle check),
    `goal_timeout_sec`, `server_wait_timeout_sec`, `lifecycle_wait_timeout_sec`.
  - override `on_result(userdata, result)` to propagate fields to userdata.
  - extend the `outcomes` class attribute if you want additional outcomes
    (route to them from `map_status`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from mw_hfsm_engine import State, Userdata
from mw_hfsm_engine import cancel as _cancel


class ActionOutcome:
    """String constants for the default outcome set.

    Subclasses can add their own outcome names, but these are the ones
    emitted by the default machinery.
    """

    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    LIFECYCLE_ERROR = 'lifecycle_error'
    TIMEOUT = 'timeout'
    REJECTED = 'rejected'


@dataclass
class _GoalOutcome:
    """Intermediate result of the goal send + await sequence."""

    outcome: str
    result: Any = None


class LifecycleAwareActionState(State):
    """Base State wrapping a ROS 2 action call on a LifecycleNode server."""

    # --- Subclass overrides ---------------------------------------------
    action_type: Any = None            # e.g. mw_task_msgs.action.DriveToPose
    action_name: str = ''              # e.g. '/drive_to_pose'
    server_node_name: str | None = None  # e.g. 'drive_to_pose_server' (enables /get_state)

    # --- Timeouts (override as needed) ----------------------------------
    server_wait_timeout_sec: float = 5.0
    lifecycle_wait_timeout_sec: float = 5.0
    goal_accept_timeout_sec: float = 5.0
    goal_complete_timeout_sec: float = 60.0
    poll_interval_sec: float = 0.01

    # --- Default outcome set --------------------------------------------
    outcomes = [
        ActionOutcome.SUCCEEDED,
        ActionOutcome.FAILED,
        ActionOutcome.LIFECYCLE_ERROR,
        ActionOutcome.TIMEOUT,
        ActionOutcome.REJECTED,
    ]

    def __init__(self, node: Any, **kwargs: Any):
        """node: a rclpy.node.Node-like object used to create clients."""
        super().__init__(**kwargs)
        self._node = node
        self._action_client: Any = None
        self._get_state_client: Any = None
        self._change_state_client: Any = None
        self._clients_ready = False

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    def build_goal(self, userdata: Userdata) -> Any:
        """Construct the action goal from userdata.  Subclass MUST override."""
        raise NotImplementedError(
            f'{type(self).__name__}.build_goal not implemented'
        )

    def on_result(self, userdata: Userdata, result: Any) -> None:
        """Optional: write result fields back to userdata."""
        pass

    def map_status(self, status: int) -> str:
        """Optional: override to support custom outcome mapping.

        Default maps GoalStatus.STATUS_SUCCEEDED → 'succeeded', else 'failed'.
        Subclasses that add outcomes should override accordingly.
        """
        # Import lazily so pure-Python unit tests don't require action_msgs.
        from action_msgs.msg import GoalStatus
        if status == GoalStatus.STATUS_SUCCEEDED:
            return ActionOutcome.SUCCEEDED
        return ActionOutcome.FAILED

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self, userdata: Userdata) -> str:
        if not self._clients_ready:
            self._lazy_init_clients()

        if self.server_node_name is not None:
            if not self._ensure_lifecycle_active():
                return ActionOutcome.LIFECYCLE_ERROR

        if not self._action_client.wait_for_server(
                timeout_sec=self.server_wait_timeout_sec):
            return ActionOutcome.TIMEOUT

        goal = self.build_goal(userdata)
        res = self._send_and_wait(goal)
        if res.outcome == ActionOutcome.SUCCEEDED and res.result is not None:
            self.on_result(userdata, res.result)
        return res.outcome

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _lazy_init_clients(self) -> None:
        """Create action + lifecycle clients on first execute()."""
        # Lazy imports keep the module importable in pure-Python unit tests
        # that stub out ROS pieces before creating the State.
        from rclpy.action import ActionClient

        if self.action_type is None or not self.action_name:
            raise RuntimeError(
                f'{type(self).__name__}: action_type and action_name must be '
                f'set as class attributes'
            )
        self._action_client = ActionClient(
            self._node, self.action_type, self.action_name
        )

        if self.server_node_name is not None:
            from lifecycle_msgs.srv import ChangeState, GetState
            self._get_state_client = self._node.create_client(
                GetState, f'/{self.server_node_name}/get_state'
            )
            self._change_state_client = self._node.create_client(
                ChangeState, f'/{self.server_node_name}/change_state'
            )

        self._clients_ready = True

    def _ensure_lifecycle_active(self) -> bool:
        """Query lifecycle state; transition configure+activate if needed."""
        from lifecycle_msgs.msg import State as LifecycleState, Transition
        from lifecycle_msgs.srv import ChangeState, GetState

        if not self._get_state_client.wait_for_service(
                timeout_sec=self.lifecycle_wait_timeout_sec):
            return False

        state_id = self._get_lifecycle_state_id()
        if state_id is None:
            return False
        if state_id == LifecycleState.PRIMARY_STATE_ACTIVE:
            return True

        # unconfigured → configure → inactive
        if state_id == LifecycleState.PRIMARY_STATE_UNCONFIGURED:
            if not self._request_transition(Transition.TRANSITION_CONFIGURE):
                return False
            state_id = self._get_lifecycle_state_id()
            if state_id != LifecycleState.PRIMARY_STATE_INACTIVE:
                return False

        # inactive → activate → active
        if state_id == LifecycleState.PRIMARY_STATE_INACTIVE:
            if not self._request_transition(Transition.TRANSITION_ACTIVATE):
                return False
            state_id = self._get_lifecycle_state_id()
            return state_id == LifecycleState.PRIMARY_STATE_ACTIVE

        # Any other state (finalized, errorprocessing, ...) = not recoverable here.
        return False

    def _get_lifecycle_state_id(self) -> int | None:
        from lifecycle_msgs.srv import GetState
        future = self._get_state_client.call_async(GetState.Request())
        result = self._wait_future(future, self.lifecycle_wait_timeout_sec)
        if result is None:
            return None
        return result.current_state.id

    def _request_transition(self, transition_id: int) -> bool:
        from lifecycle_msgs.msg import Transition
        from lifecycle_msgs.srv import ChangeState
        req = ChangeState.Request()
        req.transition = Transition(id=transition_id)
        future = self._change_state_client.call_async(req)
        result = self._wait_future(future, self.lifecycle_wait_timeout_sec)
        return bool(result and result.success)

    def _send_and_wait(self, goal: Any) -> _GoalOutcome:
        send_future = self._action_client.send_goal_async(goal)
        handle = self._wait_future(send_future, self.goal_accept_timeout_sec)
        if handle is None:
            return _GoalOutcome(ActionOutcome.TIMEOUT)
        if not handle.accepted:
            return _GoalOutcome(ActionOutcome.REJECTED)

        result_future = handle.get_result_async()
        wrapped = self._wait_future(
            result_future, self.goal_complete_timeout_sec
        )
        if wrapped is None:
            return _GoalOutcome(ActionOutcome.TIMEOUT)

        outcome = self.map_status(wrapped.status)
        return _GoalOutcome(outcome=outcome, result=wrapped.result)

    def _wait_future(self, future: Any, timeout_sec: float) -> Any:
        """Block until future.done(), returning its result (or None on timeout).

        Relies on an outer executor spinning the node to make callbacks fire.
        Polls the cancel token between sleeps so the SubJob can abandon
        a long action (and the executor can cancel the ROS 2 goal handle
        via the handle it already holds from send_goal_async).
        """
        deadline = time.monotonic() + timeout_sec
        while not future.done():
            if time.monotonic() >= deadline:
                return None
            _cancel.raise_if_cancelled()
            time.sleep(self.poll_interval_sec)
        try:
            return future.result()
        except Exception:
            return None
