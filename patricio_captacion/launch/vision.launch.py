from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():

    vision_node = Node(
        package='patricio_captacion',
        executable='vision_node',
        name='vision_node',
        parameters=[{
            'image_topic': '/camera/image_raw',
        }],
        output='screen',
    )

    return LaunchDescription([
        vision_node,
    ])