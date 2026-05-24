from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='patricio_calamar',
            executable='juego_calamar_node',
            name='juego_calamar_node',
            output='screen',
            parameters=[
                {'motion_threshold': 2500},   # píxeles — ajustar al calibrar
                {'verde_min_sec': 2.0},
                {'verde_max_sec': 5.0},
                {'rojo_min_sec': 2.0},
                {'rojo_max_sec': 4.0},
            ]
        )
    ])