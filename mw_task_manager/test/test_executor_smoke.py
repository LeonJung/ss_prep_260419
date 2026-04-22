"""Smoke test for the HFSM executor node.

Brings up a real rclpy context in-process, registers a tiny BehaviorSM
with mw_hfsm_engine's registry, starts HfsmExecutorNode, and dispatches
one ExecuteSubJob goal via ActionClient.  Asserts the response shape and
that the SubJob's recorded userdata made it back out.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from mw_hfsm_engine import (
    BehaviorSM,
    State,
    StateMachine,
    StateRegistry,
    Userdata,
    register_state,
)
from mw_task_manager import HfsmExecutorNode
from mw_task_msgs.action import ExecuteSubJob


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rclpy_ctx():
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture(autouse=True)
def clear_registry():
    StateRegistry.clear()
    yield
    StateRegistry.clear()


# ---------------------------------------------------------------------------
# Fixture SubJob: two steps, records a trace into userdata.
# ---------------------------------------------------------------------------


class _TagState(State):
    outcomes = ['done']

    def __init__(self, tag: str):
        super().__init__()
        self.tag = tag

    def execute(self, userdata: Userdata) -> str:
        trace = userdata.get('trace', [])
        trace.append(self.tag)
        userdata['trace'] = trace
        return 'done'


@register_state
class TwoStepDummy(BehaviorSM):
    behavior_parameters = []
    outcomes = ['done', 'failed']

    def __init__(self, node=None):
        super().__init__()
        step1 = StateMachine(outcomes=['done'])
        step1.add('s1', _TagState('A'), transitions={'done': 'done'})
        step2 = StateMachine(outcomes=['done'])
        step2.add('s1', _TagState('B'), transitions={'done': 'done'})
        self.add('STEP1', step1, transitions={'done': 'STEP2'})
        self.add('STEP2', step2, transitions={'done': 'done'})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_goal(executor_node: Node, subjob_id: str,
              behavior_parameter: dict | None = None,
              userdata_in: dict | None = None,
              timeout_sec: float = 5.0):
    client = ActionClient(executor_node, ExecuteSubJob,
                          '/mw_task_manager/execute_sub_job')
    assert client.wait_for_server(timeout_sec=2.0), 'action server not up'

    goal = ExecuteSubJob.Goal()
    goal.subjob_id = subjob_id
    goal.behavior_parameter_json = json.dumps(behavior_parameter or {})
    goal.userdata_in_json = json.dumps(userdata_in or {})

    send_future = client.send_goal_async(goal)
    deadline = time.monotonic() + timeout_sec
    while not send_future.done() and time.monotonic() < deadline:
        time.sleep(0.02)
    handle = send_future.result()
    assert handle is not None and handle.accepted, 'goal not accepted'

    result_future = handle.get_result_async()
    while not result_future.done() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert result_future.done(), 'goal did not complete in time'
    return result_future.result()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_executor_runs_registered_subjob_and_returns_userdata(rclpy_ctx):
    # Re-register inside test since fixture cleared the registry.
    StateRegistry.register('TwoStepDummy', TwoStepDummy, override=True)

    node = HfsmExecutorNode()
    exec_ = MultiThreadedExecutor()
    exec_.add_node(node)

    spin_thread = threading.Thread(target=exec_.spin, daemon=True)
    spin_thread.start()

    try:
        response = _run_goal(node, subjob_id='TwoStepDummy')

        assert response.result.succeeded is True
        assert response.result.outcome == 'done'
        userdata_out = json.loads(response.result.userdata_out_json)
        assert userdata_out['trace'] == ['A', 'B']
    finally:
        exec_.shutdown()
        node.destroy_node()


def test_executor_rejects_unknown_subjob_id(rclpy_ctx):
    node = HfsmExecutorNode()
    exec_ = MultiThreadedExecutor()
    exec_.add_node(node)
    spin_thread = threading.Thread(target=exec_.spin, daemon=True)
    spin_thread.start()

    try:
        response = _run_goal(node, subjob_id='DoesNotExist')
        assert response.result.succeeded is False
        # 'build_error' is what _finish_failure tags the registry miss with.
        assert response.result.outcome == 'build_error'
    finally:
        exec_.shutdown()
        node.destroy_node()
