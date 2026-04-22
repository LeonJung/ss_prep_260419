"""Full web-GUI stack: emulator + long-lived HFSM executor + foxglove_bridge.

The vite dev server and cloudflared tunnel are started separately from
scripts/start_web_gui.sh so the cloudflared URL can be captured and
printed at run time.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    emulator_launch = os.path.join(
        get_package_share_directory('mw_bringup'),
        'launch', 'emulator.launch.py')
    # RMW_IMPLEMENTATION is inherited from the shell so the caller can
    # pick rmw_fastrtps_cpp / rmw_zenoh_cpp / rmw_cyclonedds_cpp without
    # editing this file. For zenoh the caller must also have `rmw_zenohd`
    # running (start_web_gui.sh handles that automatically).

    fg_port = DeclareLaunchArgument(
        'foxglove_port', default_value='8765',
        description='foxglove_bridge WebSocket port')
    subjob_modules_arg = DeclareLaunchArgument(
        'subjob_modules', default_value='[]',
        description='List of Python modules registering SubJobs',
    )

    return LaunchDescription([
        fg_port,
        subjob_modules_arg,
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(emulator_launch)),
        Node(
            package='mw_task_manager',
            executable='hfsm_executor',
            name='mw_hfsm_executor',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'subjob_modules': LaunchConfiguration('subjob_modules'),
                'status_publish_hz': 10.0,
            }],
        ),
        Node(
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
        ),
    ])
