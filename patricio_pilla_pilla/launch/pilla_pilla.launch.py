from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='patricio_pilla_pilla',
            executable='pilla_pilla_node',
            name='pilla_pilla_node',
            output='screen',
            parameters=[
                {'route_mode': 'random'},
                {'map_frame': 'map'},
                {'map_yaml': '/home/juan/turtlebot3_ws/src/patricio/patricio_nav_punto/map/my_map.yaml'},
                {'random_num_points': 5},
                {'safety_radius_cells': 3},
                {'circle_center_x': 0.0},
                {'circle_center_y': 0.0},
                {'circle_radius': 1.5},
            ]
        )
    ])
