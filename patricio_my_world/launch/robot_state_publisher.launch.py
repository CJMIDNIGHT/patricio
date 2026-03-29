import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    TURTLEBOT3_MODEL = os.environ.get('TURTLEBOT3_MODEL', 'burger')

    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    frame_prefix = LaunchConfiguration('frame_prefix', default='')

    urdf_file_name = 'turtlebot3_' + TURTLEBOT3_MODEL + '.urdf'

    urdf_path = os.path.join(
        get_package_share_directory('patricio_my_world'),  # 🔥 CAMBIADO
        'urdf',
        urdf_file_name
    )

    with open(urdf_path, 'r') as infp:
        robot_desc = infp.read()

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use simulation clock'
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'robot_description': robot_desc,
                'frame_prefix': PythonExpression(["'", frame_prefix, "/'"])
            }],
        ),
    ])