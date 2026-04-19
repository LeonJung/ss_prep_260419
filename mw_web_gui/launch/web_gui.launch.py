"""Full web-GUI stack: emulator + long-lived task_manager + foxglove_bridge.

The vite dev server and cloudflared tunnel are started separately from
scripts/start_web_gui.sh so the cloudflared URL can be captured and
printed at run time.
"""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
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

    return LaunchDescription([
        fg_port,
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(emulator_launch)),
        Node(
            package='mw_task_manager',
            executable='mw_task_manager_node',
            name='mw_bt_executor',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'tick_rate_hz': 10.0,
                'groot_port': 1667,
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
