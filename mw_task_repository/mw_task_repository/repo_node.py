"""Git-backed SubJob spec repository.

Exposes three services under the node namespace:
  ~/list_tasks   (ListTasks) -> list of stored SubJob ids
  ~/load_task    (LoadTask)  -> spec content (JSON) for a SubJob id
  ~/save_task    (SaveTask)  -> minimally validate + write file + git commit

Default storage: $MW_TASK_REPO_DIR or ~/mw_tasks.  One JSON file per SubJob
(`<id>.json`).  The legacy `.xml` suffix is still recognized on read so
existing installs with BT XML can be inspected before migration; new
saves always land as `.json`.

Validation deliberately stays minimal at this layer (non-empty + JSON
parseable into an object with a "kind" field).  Deep schema checking
(outcomes / transitions coverage) lives in mw_hfsm_engine.build_from_spec
at dispatch time so authoring feedback is one clear place, not two.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import rclpy
from rclpy.node import Node

from mw_task_msgs.srv import ListTasks, LoadTask, SaveTask


class TaskRepoNode(Node):

    SUPPORTED_SUFFIXES = ('.json', '.xml')

    def __init__(self) -> None:
        super().__init__('mw_task_repository')
        default_dir = os.environ.get(
            'MW_TASK_REPO_DIR', str(Path.home() / 'mw_tasks'))
        self.declare_parameter('repo_dir', default_dir)
        self.repo_dir = Path(self.get_parameter('repo_dir').value).expanduser()
        self._ensure_repo()

        self.create_service(ListTasks, '~/list_tasks', self._list_cb)
        self.create_service(LoadTask, '~/load_task', self._load_cb)
        self.create_service(SaveTask, '~/save_task', self._save_cb)
        self.get_logger().info(f'task repository ready at {self.repo_dir}')

    def _ensure_repo(self) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        if (self.repo_dir / '.git').exists():
            return
        subprocess.run(
            ['git', 'init', '-q', '-b', 'main'],
            cwd=self.repo_dir, check=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'task-repo@mw.local'],
            cwd=self.repo_dir, check=True)
        subprocess.run(
            ['git', 'config', 'user.name', 'mw-task-repo'],
            cwd=self.repo_dir, check=True)
        self.get_logger().info(f'initialized git repo at {self.repo_dir}')

    # ------------------------------------------------------------------
    def _safe_id(self, task_id: str) -> str:
        safe = Path(task_id).name
        if not safe or safe != task_id or '/' in task_id:
            raise ValueError(f'invalid task_id: {task_id!r}')
        return safe

    def _save_path(self, task_id: str) -> Path:
        """Where a newly-saved spec is written ( .json )."""
        return self.repo_dir / f'{self._safe_id(task_id)}.json'

    def _load_path(self, task_id: str) -> Path | None:
        """Find an existing spec, preferring .json, falling back to .xml."""
        safe = self._safe_id(task_id)
        for suffix in self.SUPPORTED_SUFFIXES:
            p = self.repo_dir / f'{safe}{suffix}'
            if p.exists():
                return p
        return None

    # ------------------------------------------------------------------
    def _list_cb(self, _req, resp):
        seen: set[str] = set()
        for suffix in self.SUPPORTED_SUFFIXES:
            for p in self.repo_dir.glob(f'*{suffix}'):
                seen.add(p.stem)
        resp.task_ids = sorted(seen)
        return resp

    def _load_cb(self, req, resp):
        try:
            path = self._load_path(req.task_id)
            if path is None:
                resp.success = False
                resp.message = f'not found: {req.task_id}'
                return resp
            resp.xml_content = path.read_text(encoding='utf-8')
            resp.success = True
            resp.message = 'ok'
        except Exception as e:  # noqa: BLE001
            resp.success = False
            resp.message = str(e)
        return resp

    def _save_cb(self, req, resp):
        try:
            content = (req.xml_content or '').strip()
            if not content:
                resp.success = False
                resp.message = 'empty spec'
                return resp
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                resp.success = False
                resp.message = f'invalid JSON: {e}'
                return resp
            if not isinstance(parsed, dict) or 'kind' not in parsed:
                resp.success = False
                resp.message = 'spec must be a JSON object with a "kind" field'
                return resp

            path = self._save_path(req.task_id)
            path.write_text(req.xml_content, encoding='utf-8')
            subprocess.run(
                ['git', 'add', path.name], cwd=self.repo_dir, check=True)
            msg = req.commit_message or f'save {req.task_id}'
            subprocess.run(
                ['git', 'commit', '-q', '-m', msg, '--allow-empty'],
                cwd=self.repo_dir, check=True)
            resp.success = True
            resp.message = 'saved'
        except Exception as e:  # noqa: BLE001
            resp.success = False
            resp.message = str(e)
        return resp


def main() -> None:
    rclpy.init()
    node = TaskRepoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
