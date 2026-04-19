"""TurtleBot3 Gazebo (empty world) + DriveToPose skill + BT executor.

Intentionally does NOT include nav2 — the Step-level control loop lives
inside mw_skill_library/drive_to_pose_server (see docstring there).
Coordinates are in /odom frame; the robot starts at the origin.

Usage:
  ros2 launch mw_bringup navigate_test.launch.py

Env:
  TURTLEBOT3_MODEL   defaults to 'waffle' (set in this launch)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    task_xml = os.path.join(
        get_package_share_directory('mw_task_manager'),
        'config',
        'job_visit_three_points.xml',
    )
    tb3_gazebo_dir = get_package_share_directory('turtlebot3_gazebo')
    tb3_empty_launch = os.path.join(
        tb3_gazebo_dir, 'launch', 'empty_world.launch.py')

    rmw_env = SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp')
    tb3_model_env = SetEnvironmentVariable('TURTLEBOT3_MODEL', 'waffle')

    bt_delay_arg = DeclareLaunchArgument(
        'bt_start_delay', default_value='12.0',
        description='seconds to wait for Gazebo + drive server before BT start')

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

    bt_executor = Node(
        package='mw_task_manager',
        executable='mw_task_manager_node',
        name='mw_bt_executor',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'tree_xml_path': task_xml,
            'tick_rate_hz': 5.0,
            'groot_port': 1667,
        }],
    )

    return LaunchDescription([
        rmw_env,
        tb3_model_env,
        bt_delay_arg,
        tb3_sim,
        drive_server,
        TimerAction(
            period=LaunchConfiguration('bt_start_delay'),
            actions=[bt_executor],
        ),
    ])
