#!/usr/bin/env python3
"""
vision.launch.py  —  patricio_vision

Lanza la cadena completa de visión del robot Patricio:

  webcam_publisher
      └─► /camera/real
            └─► vision_node  (/patricio/camera_processed)
                  └─► mediapipe_node  (/patricio/vision/pose_landmarks)
                            └─► fall_detection_node
                                      ├─► /patricio/vision/fall_detected
                                      └─► /patricio/web/notification

Uso básico:
  ros2 launch patricio_vision vision.launch.py

Con IP de Windows para la webcam:
  ros2 launch patricio_vision vision.launch.py windows_ip:=192.168.1.50

Sin cámara real (solo Gazebo):
  ros2 launch patricio_vision vision.launch.py use_real_camera:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():

    # ── Argumentos del launch ────────────────────────────────────────────
    args = [
        DeclareLaunchArgument(
            'windows_ip',
            default_value='localhost',
            description='IP del servidor de webcam en Windows (webcam_publisher)',
        ),
        DeclareLaunchArgument(
            'use_real_camera',
            default_value='true',
            description='Lanzar webcam_publisher (true) o solo usar Gazebo (false)',
        ),
        DeclareLaunchArgument(
            'publish_annotated',
            default_value='true',
            description='Publicar frame anotado con esqueleto en /patricio/vision/camera_annotated',
        ),
        DeclareLaunchArgument(
            'target_fps',
            default_value='15.0',
            description='FPS objetivo para el procesado de MediaPipe',
        ),
        DeclareLaunchArgument(
            'fall_min_criteria',
            default_value='2',
            description='Nº mínimo de criterios (0-4) para considerar posible caída',
        ),
        DeclareLaunchArgument(
            'fall_confirm_frames',
            default_value='3',
            description='Frames consecutivos necesarios para confirmar la caída',
        ),
        DeclareLaunchArgument(
            'alert_cooldown',
            default_value='10.0',
            description='Segundos mínimos entre alertas de caída (anti-flood)',
        ),
    ]

    # ── Nodo 3: mediapipe_node ───────────────────────────────────────────
    mediapipe_node = Node(
        package='patricio_vision',
        executable='mediapipe_node',
        name='mediapipe_node',
        output='screen',
        parameters=[{
            'publish_annotated':        LaunchConfiguration('publish_annotated'),
            'target_fps':               LaunchConfiguration('target_fps'),
            'movement_threshold':       0.015,
            'min_detection_confidence': 0.6,
            'min_tracking_confidence':  0.5,
            'model_complexity':         1,
        }],
    )

    # ── Nodo 4: fall_detection_node ──────────────────────────────────────
    fall_detection_node = Node(
        package='patricio_vision',
        executable='fall_detection_node',
        name='fall_detection_node',
        output='screen',
        parameters=[{
            'fall_hip_height_threshold':  0.55,
            'fall_torso_angle_threshold': 45.0,
            'fall_velocity_threshold':    0.08,
            'fall_bbox_ratio_threshold':  1.5,
            'fall_min_criteria':          LaunchConfiguration('fall_min_criteria'),
            'fall_confirm_frames':        LaunchConfiguration('fall_confirm_frames'),
            'alert_cooldown':             LaunchConfiguration('alert_cooldown'),
            'history_size':               30,
        }],
    )

    # ── Log informativo al arrancar ──────────────────────────────────────
    log_start = LogInfo(
        msg=[
            '\n',
            '╔══════════════════════════════════════════════╗\n',
            '║       patricio_vision — cadena completa      ║\n',
            '╚══════════════════════════════════════════════╝\n',
            '  webcam IP  : ', LaunchConfiguration('windows_ip'), '\n',
            '  real cam   : ', LaunchConfiguration('use_real_camera'), '\n',
            '  target fps : ', LaunchConfiguration('target_fps'), '\n',
            '  fall conf. : ', LaunchConfiguration('fall_confirm_frames'),
            ' frames / min_criteria=', LaunchConfiguration('fall_min_criteria'), '\n',
        ]
    )

    return LaunchDescription([
        *args,
        log_start,
        mediapipe_node,
        fall_detection_node,
    ])