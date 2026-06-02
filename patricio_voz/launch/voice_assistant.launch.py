"""
Pipeline voz completo: STT (micrófono) + TTS (altavoz y pantalla).
Ejecuta también patricio_gemini por separado (otro paquete) para la IA.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('patricio_voz')
    stt_params = os.path.join(pkg_share, 'config', 'voice_stt_params.yaml')
    tts_params = os.path.join(pkg_share, 'config', 'voice_tts_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('stt_params_file', default_value=stt_params),
        DeclareLaunchArgument('tts_params_file', default_value=tts_params),
        Node(
            package='patricio_voz',
            executable='voice_stt_node',
            name='voice_stt_node',
            output='screen',
            parameters=[LaunchConfiguration('stt_params_file')],
        ),
        Node(
            package='patricio_voz',
            executable='voice_tts_node',
            name='voice_tts_node',
            output='screen',
            parameters=[LaunchConfiguration('tts_params_file')],
        ),
    ])
