"""TurtleBot3 Gazebo (empty world) + DriveToPose skill + HFSM executor.

Intentionally does NOT include nav2 — the Step-level control loop lives
inside mw_skill_library/drive_to_pose_server (see docstring there).
Coordinates are in /odom frame; the robot starts at the origin.

Usage:
  ros2 launch mw_bringup navigate_test.launch.py
  ros2 action send_goal /mw_task_manager/execute_sub_job \\
    mw_task_msgs/action/ExecuteSubJob \\
    '{subjob_id: "VisitThreePoints"}'

Env:
  TURTLEBOT3_MODEL   defaults to 'waffle' (set in this launch)
"""

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

from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    tb3_gazebo_dir = get_package_share_directory('turtlebot3_gazebo')
    tb3_empty_launch = os.path.join(
        tb3_gazebo_dir, 'launch', 'empty_world.launch.py',
    )

    rmw_env = SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp')
    tb3_model_env = SetEnvironmentVariable('TURTLEBOT3_MODEL', 'waffle')

    subjob_modules_arg = DeclareLaunchArgument(
        'subjob_modules', default_value='[]',
        description='List of Python modules registering SubJobs',
    )
    executor_delay_arg = DeclareLaunchArgument(
        'executor_start_delay', default_value='12.0',
        description='seconds to wait for Gazebo + drive_to_pose_server '
                    'before starting the HFSM executor',
    )

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

    hfsm_executor = Node(
        package='mw_task_manager',
        executable='hfsm_executor',
        name='mw_hfsm_executor',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'subjob_modules': LaunchConfiguration('subjob_modules'),
            'status_publish_hz': 5.0,
        }],
    )

    return LaunchDescription([
        rmw_env,
        tb3_model_env,
        subjob_modules_arg,
        executor_delay_arg,
        tb3_sim,
        drive_server,
        TimerAction(
            period=LaunchConfiguration('executor_start_delay'),
            actions=[hfsm_executor],
        ),
    ])
