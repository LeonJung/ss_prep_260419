"""Basic demo: emulator + skill servers + HFSM executor.

No SubJob is auto-dispatched — bring up the stack, then dispatch a SubJob
from the CLI or web GUI:

    ros2 launch mw_bringup demo.launch.py
    # then, in another terminal:
    ros2 action send_goal /mw_task_manager/execute_sub_job \\
      mw_task_msgs/action/ExecuteSubJob '{subjob_id: "MySubJob", ...}'

The `subjob_modules` parameter accepts a list of importable Python module
paths that register SubJobs via @register_state on BehaviorSM subclasses.
Pass your own via -p subjob_modules:="['my_pkg.my_subjobs']".
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    subjob_modules_arg = DeclareLaunchArgument(
        'subjob_modules',
        default_value='[]',
        description='List of Python modules (as a YAML list) that register '
                    'SubJobs via @register_state',
    )
    rmw_env = SetEnvironmentVariable('RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp')

    return LaunchDescription([
        rmw_env,
        subjob_modules_arg,
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
            executable='hfsm_executor',
            name='mw_hfsm_executor',
            output='screen',
            parameters=[{
                'subjob_modules': LaunchConfiguration('subjob_modules'),
                'status_publish_hz': 10.0,
            }],
        ),
    ])
