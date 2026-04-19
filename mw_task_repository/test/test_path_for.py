"""Unit tests for TaskRepoNode path sanitization (no ROS context needed)."""

import os
import pytest

import rclpy

from mw_task_repository.repo_node import TaskRepoNode


@pytest.fixture(scope='module')
def node(tmp_path_factory):
    os.environ['MW_TASK_REPO_DIR'] = str(tmp_path_factory.mktemp('repo'))
    rclpy.init()
    n = TaskRepoNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def test_valid_id(node):
    p = node._path_for('foo_bar')
    assert p.name == 'foo_bar.xml'


def test_reject_traversal(node):
    with pytest.raises(ValueError):
        node._path_for('../etc/passwd')


def test_reject_slash(node):
    with pytest.raises(ValueError):
        node._path_for('sub/dir')


def test_reject_empty(node):
    with pytest.raises(ValueError):
        node._path_for('')
