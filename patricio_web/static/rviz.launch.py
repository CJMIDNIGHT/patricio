import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():

    # Ruta al mapa y configuración de RViz
    map_file = '/home/asun/turtlebot3_ws/src/pamabot/pamabot_web/static/farmaciaMapa.yaml'
    rviz_config = '/home/asun/turtlebot3_ws/src/pamabot/pamabot_web/static/farmacia_config.rviz'

    return LaunchDescription([

        # 🗺️ map_server → publica el /map
        Node(
            package='nav2_map_server',
            executable='map_server',
            name='map_server',
            output='screen',
            parameters=[
                {'use_sim_time': False},
                {'yaml_filename': map_file}
            ]
        ),

        # 🖥️ RViz2 → abre la vista personalizada
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', rviz_config],
            parameters=[{'use_sim_time': False}]
        ),
    ])

