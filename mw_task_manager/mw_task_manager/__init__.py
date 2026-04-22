"""mw_task_manager — ROS 2 node that runs SubJob specs through mw_hfsm_engine.

Console entry point: `hfsm_executor` (see setup.py).

Design:
- Accepts `ExecuteSubJob` action goals.
- Loads the JSON HFSM spec for the given subjob_id via mw_task_repository's
  LoadTask service (xml_content field now carries JSON).
- Builds a BehaviorSM via the spec loader, runs it on a worker thread,
  returns the outcome + userdata_out as action result.
- Publishes HfsmExecutionStatus on /mw_hfsm_status at a fixed rate so the
  web GUI can render a live state chart.
"""

from .hfsm_executor_node import HfsmExecutorNode, main

__all__ = ['HfsmExecutorNode', 'main']
