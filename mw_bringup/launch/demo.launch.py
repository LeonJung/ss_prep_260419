"""Phase 1 demo launch: 2 mock skill servers + BT executor running demo_fetch_cup.

Respawn is enabled now (Layer 1 of the 3-layer lifecycle plan) so even the
Phase 1 basic action servers survive a crash. Layer 2/3 (LifecycleNode +
supervisor) land in Phase 3.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_tree = os.path.join(
        get_package_share_directory('mw_task_manager'),
        'config',
        'demo_fetch_cup.xml',
    )

    tree_arg = DeclareLaunchArgument(
        'tree_xml_path',
        default_value=default_tree,
        description='Absolute path to the BT XML Job definition',
    )

    # Force FastDDS: Zenoh is the Jazzy default but requires a separate
    # rmw_zenohd router. FastDDS works out of the box for local demos.
    rmw_env = SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp')

    return LaunchDescription([
        rmw_env,
        tree_arg,
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
            package='mw_task_manager',
            executable='mw_task_manager_node',
            name='mw_bt_executor',
            output='screen',
            parameters=[{
                'tree_xml_path': LaunchConfiguration('tree_xml_path'),
                'tick_rate_hz': 10.0,
                'groot_port': 1667,
            }],
        ),
    ])
