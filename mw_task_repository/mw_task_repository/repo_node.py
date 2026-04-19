"""Git-backed Task XML repository.

Exposes three services under the node namespace:
  ~/list_tasks   (ListTasks) -> list of stored Task ids (XML filename stem)
  ~/load_task    (LoadTask)  -> XML content for a Task id
  ~/save_task    (SaveTask)  -> validate XML, write file, git commit

Default storage: $MW_TASK_REPO_DIR or ~/mw_tasks. One XML file per Task.
The directory is initialized as a git repo on first start so every save
produces an auditable commit (useful when RCS pushes policy updates later).
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import rclpy
from rclpy.node import Node

from mw_task_msgs.srv import ListTasks, LoadTask, SaveTask


class TaskRepoNode(Node):

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

    def _path_for(self, task_id: str) -> Path:
        # Block path traversal by requiring a single filename component.
        safe = Path(task_id).name
        if not safe or safe != task_id or '/' in task_id:
            raise ValueError(f'invalid task_id: {task_id!r}')
        return self.repo_dir / f'{safe}.xml'

    def _list_cb(self, _req, resp):
        resp.task_ids = [p.stem for p in sorted(self.repo_dir.glob('*.xml'))]
        return resp

    def _load_cb(self, req, resp):
        try:
            path = self._path_for(req.task_id)
            if not path.exists():
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
            path = self._path_for(req.task_id)
            # Minimal structural validation; full BT schema check lives in
            # mw_task_domain (future package).
            ET.fromstring(req.xml_content)
            path.write_text(req.xml_content, encoding='utf-8')
            subprocess.run(
                ['git', 'add', path.name], cwd=self.repo_dir, check=True)
            msg = req.commit_message or f'save {req.task_id}'
            subprocess.run(
                ['git', 'commit', '-q', '-m', msg, '--allow-empty'],
                cwd=self.repo_dir, check=True)
            resp.success = True
            resp.message = 'saved'
        except ET.ParseError as e:
            resp.success = False
            resp.message = f'invalid XML: {e}'
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
