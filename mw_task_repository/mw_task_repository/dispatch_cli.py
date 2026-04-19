"""Dispatch a stored Task by id.

Usage:
  ros2 run mw_task_repository dispatch <task_id>

Pipeline:
  1. LoadTask service call to mw_task_repository
  2. Write XML to temp file
  3. ros2 run mw_task_manager mw_task_manager_node ... (only the BT executor,
     relying on emulator + skill servers already running)

Assumes the emulator stack (mw_bringup emulator.launch.py) is up. If not,
start it first or pass --standalone to also launch it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import rclpy
from rclpy.node import Node

from mw_task_msgs.srv import LoadTask


class DispatchClient(Node):

    def __init__(self) -> None:
        super().__init__('mw_dispatch_cli')
        self.cli = self.create_client(
            LoadTask, '/mw_task_repository/load_task')

    def fetch(self, task_id: str, timeout_sec: float = 5.0) -> str:
        if not self.cli.wait_for_service(timeout_sec=timeout_sec):
            raise RuntimeError('task repository service not available')
        req = LoadTask.Request()
        req.task_id = task_id
        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(
            self, future, timeout_sec=timeout_sec)
        resp = future.result()
        if resp is None:
            raise RuntimeError('load_task timed out')
        if not resp.success:
            raise RuntimeError(f'load_task failed: {resp.message}')
        return resp.xml_content


def main() -> int:
    parser = argparse.ArgumentParser(description='Dispatch a stored Task')
    parser.add_argument('task_id', help='Task identifier (XML filename stem)')
    args = parser.parse_args()

    rclpy.init()
    client = DispatchClient()
    try:
        xml = client.fetch(args.task_id)
    except Exception as e:  # noqa: BLE001
        print(f'[dispatch] {e}', file=sys.stderr)
        client.destroy_node()
        rclpy.shutdown()
        return 2
    client.destroy_node()
    rclpy.shutdown()

    with tempfile.NamedTemporaryFile(
            mode='w', suffix='.xml', delete=False) as f:
        f.write(xml)
        tmp_path = f.name

    cmd = [
        'ros2', 'run', 'mw_task_manager', 'mw_task_manager_node',
        '--ros-args',
        '-p', f'tree_xml_path:={tmp_path}',
        '-p', 'tick_rate_hz:=10.0',
        '-p', 'groot_port:=1667',
    ]
    print(f'[dispatch] running {args.task_id} via: {" ".join(cmd)}',
          file=sys.stderr)
    try:
        return subprocess.call(cmd)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == '__main__':
    sys.exit(main())
