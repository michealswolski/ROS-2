"""Replay a drive bag with `ros2 bag play` while kpi_monitor computes live KPIs.

  ros2 launch drive_bag replay.launch.py bag:=bags/sample_drive rate:=5.0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bag = LaunchConfiguration('bag')
    rate = LaunchConfiguration('rate')
    output = LaunchConfiguration('output')

    monitor = Node(
        package='drive_bag', executable='kpi_monitor', name='kpi_monitor', output='screen',
        parameters=[{'bag': bag, 'output': output, 'idle_timeout_s': 3.0}])

    player = ExecuteProcess(
        cmd=['ros2', 'bag', 'play', bag, '--rate', rate, '--delay', '2',
             '--disable-keyboard-controls'],
        output='screen')

    return LaunchDescription([
        DeclareLaunchArgument('bag', default_value='bags/sample_drive'),
        DeclareLaunchArgument('rate', default_value='1.0', description='playback speed multiplier'),
        DeclareLaunchArgument('output', default_value='results/replay_kpis.json'),
        monitor,
        player,
        # The monitor exits by itself once the replay has gone quiet.
        RegisterEventHandler(OnProcessExit(target_action=monitor,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ])
