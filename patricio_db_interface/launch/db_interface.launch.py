"""Launch del nodo db_interface_node del paquete patricio_db_interface.

Uso:
    ros2 launch patricio_db_interface db_interface.launch.py
    ros2 launch patricio_db_interface db_interface.launch.py api_url:=http://localhost:5000
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    api_url_arg = DeclareLaunchArgument(
        'api_url',
        default_value='http://localhost:5000',
        description='URL base de patricio_api.py (Flask). Todo corre en local.',
    )
    timeout_arg = DeclareLaunchArgument(
        'request_timeout',
        default_value='5.0',
        description='Timeout en segundos para las peticiones HTTP a la API.',
    )

    db_node = Node(
        package='patricio_db_interface',
        executable='db_interface_node',
        name='db_interface_node',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'api_url': LaunchConfiguration('api_url'),
            'request_timeout': LaunchConfiguration('request_timeout'),
        }],
    )

    return LaunchDescription([
        api_url_arg,
        timeout_arg,
        db_node,
    ])
