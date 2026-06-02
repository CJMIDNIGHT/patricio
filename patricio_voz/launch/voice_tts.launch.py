import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('patricio_voz')
    default_params = os.path.join(pkg_share, 'config', 'voice_tts_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='YAML de parámetros del nodo TTS',
        ),
        Node(
            package='patricio_voz',
            executable='voice_tts_node',
            name='voice_tts_node',
            output='screen',
            parameters=[LaunchConfiguration('params_file')],
        ),
    ])
