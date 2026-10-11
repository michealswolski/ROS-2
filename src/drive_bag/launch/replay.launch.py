"""
Replay a drive bag with `ros2 bag play` while kpi_monitor computes live KPIs.

Examples:
ros2 launch drive_bag replay.launch.py bag:=bags/sample_drive rate:=5.0
ros2 launch drive_bag replay.launch.py foxglove:=true loop:=true   # live view in Foxglove
"""

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            IncludeLaunchDescription, RegisterEventHandler)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bag = LaunchConfiguration('bag')
    rate = LaunchConfiguration('rate')
    output = LaunchConfiguration('output')
    loop = LaunchConfiguration('loop')
    foxglove = LaunchConfiguration('foxglove')

    monitor = Node(
        package='drive_bag', executable='kpi_monitor', name='kpi_monitor', output='screen',
        parameters=[{'bag': bag, 'output': output, 'idle_timeout_s': 3.0}])

    play = ['ros2', 'bag', 'play', bag, '--rate', rate, '--delay', '2',
            '--disable-keyboard-controls']
    player = ExecuteProcess(cmd=play, output='screen', condition=UnlessCondition(loop))
    player_loop = ExecuteProcess(cmd=play + ['--loop'], output='screen',
                                 condition=IfCondition(loop))

    # Foxglove: connect to ws://localhost:8765 (needs ros-jazzy-foxglove-bridge).
    bridge = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(PathJoinSubstitution(
            [FindPackageShare('foxglove_bridge'), 'launch', 'foxglove_bridge_launch.xml'])),
        launch_arguments={'port': LaunchConfiguration('foxglove_port')}.items(),
        condition=IfCondition(foxglove))

    return LaunchDescription([
        DeclareLaunchArgument('bag', default_value='bags/sample_drive'),
        DeclareLaunchArgument('rate', default_value='1.0',
                              description='playback speed multiplier'),
        DeclareLaunchArgument('output', default_value='results/replay_kpis.json'),
        DeclareLaunchArgument('loop', default_value='false',
                              description='replay forever (the KPI monitor keeps running)'),
        DeclareLaunchArgument('foxglove', default_value='false',
                              description='also start foxglove_bridge for a live Foxglove view'),
        DeclareLaunchArgument('foxglove_port', default_value='8765'),
        monitor,
        player,
        player_loop,
        bridge,
        # The monitor exits by itself once the replay has gone quiet.
        RegisterEventHandler(OnProcessExit(target_action=monitor,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ])
