"""TurtleBot3 Gazebo + long-lived HFSM executor + Web GUI bridge.

Unlike web_gui.launch.py (which uses the virtual_robot emulator), this
launch brings up the real TurtleBot3 empty_world simulation and wires
the ExecuteSubJob action + /mw_hfsm_status publishers into foxglove_bridge
so the Vue frontend can dispatch SubJobs and watch the state chart tick
live while the robot actually drives in Gazebo.

No nav2 — the navigation control loop lives in
mw_skill_library/drive_to_pose_server (our own P-controller).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    tb3_gazebo_dir = get_package_share_directory('turtlebot3_gazebo')
    tb3_empty_launch = os.path.join(
        tb3_gazebo_dir, 'launch', 'empty_world.launch.py')

    fg_port = DeclareLaunchArgument(
        'foxglove_port', default_value='8765',
        description='foxglove_bridge WebSocket port')
    subjob_modules_arg = DeclareLaunchArgument(
        'subjob_modules',
        default_value="['mw_skill_states', 'mw_hfsm_examples']",
        description='List of Python modules registering SubJobs',
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
            'status_publish_hz': 10.0,
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
        subjob_modules_arg,
        tb3_sim,
        drive_server,
        hfsm_executor,
        repo,
        foxglove,
    ])
