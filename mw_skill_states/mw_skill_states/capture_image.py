"""CaptureImageState — HFSM SubStep wrapper for the /capture_image action.

The action server (`capture_image_server` in mw_skill_library) captures
one frame from a named camera and writes it to `save_path`.

Parameter resolution mirrors the other skill states:

    1. Constants at construction:
         CaptureImageState(node, camera_id='head', save_path='/tmp/cup.jpg')

    2. Lookup from userdata:
         CaptureImageState(node)
         # userdata['camera_id'], userdata['save_path']

    3. Mix:
         CaptureImageState(node, camera_id='head')
         # userdata['save_path'] = '/var/captures/frame-42.jpg'

Required userdata keys when constructor values are omitted:
  camera_id (string), save_path (string)

Written back to userdata after SUCCEEDED:
  image_path (string — the path the server actually wrote to, which may
  differ from save_path if the server normalized it)
"""

from __future__ import annotations

from typing import Any

from mw_hfsm_engine import Userdata
from mw_hfsm_ros import LifecycleAwareActionState
from mw_task_msgs.action import CaptureImage

from .move_motor import _require_str


class CaptureImageState(LifecycleAwareActionState):
    """Invoke the capture_image action, lifecycle-aware."""

    action_type = CaptureImage
    action_name = '/capture_image'
    server_node_name = 'capture_image_server'

    def __init__(
        self,
        node: Any,
        *,
        camera_id: str | None = None,
        save_path: str | None = None,
    ) -> None:
        super().__init__(node=node)
        self._camera_id = camera_id
        self._save_path = save_path

    # ------------------------------------------------------------------
    def build_goal(self, userdata: Userdata) -> CaptureImage.Goal:
        goal = CaptureImage.Goal()
        goal.camera_id = _require_str(self, 'camera_id', self._camera_id, userdata)
        goal.save_path = _require_str(self, 'save_path', self._save_path, userdata)
        return goal

    def on_result(
        self, userdata: Userdata, result: CaptureImage.Result,
    ) -> None:
        userdata['image_path'] = result.image_path
