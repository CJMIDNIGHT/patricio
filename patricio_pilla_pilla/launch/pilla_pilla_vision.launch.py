import os
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():

    return LaunchDescription([

        # ── Nodo de seguimiento visual (nuevo) ──────────────────────────
        Node(
            package='patricio_pilla_pilla',
            executable='vision_follower',
            name='pilla_pilla_vision_node',
            output='screen',
            parameters=[
                {'kp_angular':         1.2},
                {'kp_linear':          0.6},
                {'max_angular_vel':    0.5},
                {'max_linear_vel':     0.2},
                {'search_angular_vel': 0.3},
                {'center_threshold':   0.08},
                {'catch_bbox_height':  0.60},
                {'search_timeout_sec': 30.0},
                {'control_hz':         20.0},
                {'catch_confirm_sec':  0.5},
            ]
        ),
    ])