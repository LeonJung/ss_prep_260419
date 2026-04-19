"""Emulator + skill servers + task repository only.

Intended for self-tests: the BT executor is NOT started here; the test
driver launches it via `ros2 run mw_task_repository dispatch` so that
fault injection can occur before the Job begins.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # RMW_IMPLEMENTATION inherited from the shell environment.
    return LaunchDescription([
        Node(
            package='mw_robot_emulator',
            executable='virtual_robot',
            name='virtual_robot',
            output='screen',
            emulate_tty=True,
        ),
        Node(
            package='mw_skill_library',
            executable='move_motor_server',
            name='move_motor_server',
            output='screen',
            emulate_tty=True,
            respawn=True,
            respawn_delay=2.0,
        ),
        Node(
            package='mw_skill_library',
            executable='capture_image_server',
            name='capture_image_server',
            output='screen',
            emulate_tty=True,
            respawn=True,
            respawn_delay=2.0,
        ),
        Node(
            package='mw_skill_supervisor',
            executable='supervisor',
            name='mw_skill_supervisor',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'managed_nodes':
                    ['move_motor_server', 'capture_image_server'],
                'poll_hz': 2.0,
            }],
        ),
        Node(
            package='mw_task_repository',
            executable='repo_node',
            name='mw_task_repository',
            output='screen',
            emulate_tty=True,
        ),
    ])
