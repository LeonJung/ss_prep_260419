"""TurtleBot3 Gazebo + long-lived task_manager + Web GUI bridge.

Unlike web_gui.launch.py (which uses the virtual_robot emulator), this
launch brings up the real TurtleBot3 empty_world simulation and wires
the ExecuteTask action + /mw_bt_status publishers into foxglove_bridge
so the Vue frontend can dispatch Jobs (e.g. visit_three_points) and
watch the tree tick live while the robot actually drives in Gazebo.

No nav2 — the navigation control loop lives in
mw_skill_library/drive_to_pose_server (our own P-controller).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    tb3_gazebo_dir = get_package_share_directory('turtlebot3_gazebo')
    tb3_empty_launch = os.path.join(
        tb3_gazebo_dir, 'launch', 'empty_world.launch.py')

    fg_port = DeclareLaunchArgument(
        'foxglove_port', default_value='8765',
        description='foxglove_bridge WebSocket port')

    tb3_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(tb3_empty_launch),
    )

    drive_server = Node(
        package='mw_skill_library',
        executable='drive_to_pose_server',
        name='drive_to_pose_server',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'cmd_vel_topic': '/cmd_vel',
            'odom_topic': '/odom',
        }],
    )

    task_manager = Node(
        package='mw_task_manager',
        executable='mw_task_manager_node',
        name='mw_bt_executor',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'tick_rate_hz': 10.0,
            'groot_port': 1667,
        }],
    )

    repo = Node(
        package='mw_task_repository',
        executable='repo_node',
        name='mw_task_repository',
        output='screen',
        emulate_tty=True,
    )

    foxglove = Node(
        package='foxglove_bridge',
        executable='foxglove_bridge',
        name='foxglove_bridge',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'port': 8765,
            'address': '0.0.0.0',
            'send_buffer_limit': 10_000_000,
        }],
    )

    return LaunchDescription([
        fg_port,
        tb3_sim,
        drive_server,
        task_manager,
        repo,
        foxglove,
    ])
