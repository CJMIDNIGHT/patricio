#!/usr/bin/env python3
"""
webcam_publisher_linux.py

Publishes the laptop webcam feed to /camera/real using cv2.VideoCapture.
Native Linux version — no WSL or Windows HTTP server needed.
vision_node will automatically prefer this over /camera/image_raw (Gazebo).
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class WebcamPublisherLinux(Node):
    def __init__(self):
        super().__init__('webcam_publisher_linux')

        self.declare_parameter('camera_index', 0)  # 0 = default webcam
        self.declare_parameter('fps', 30)

        camera_index = (
            self.get_parameter('camera_index')
            .get_parameter_value()
            .integer_value
        )
        fps = (
            self.get_parameter('fps')
            .get_parameter_value()
            .integer_value
        )

        self.bridge = CvBridge()

        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            self.get_logger().error(
                f'No se pudo abrir la cámara con índice {camera_index}. '
                'Comprueba que la webcam está conectada.'
            )
            raise RuntimeError('Webcam no disponible')

        self.get_logger().info(
            f'Webcam abierta (índice {camera_index}). '
            f'Publicando en /camera/real a {fps} fps.'
        )

        self.publisher = self.create_publisher(Image, '/camera/real', 10)
        self.timer = self.create_timer(1.0 / fps, self.callback)

    def callback(self):
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().warn('No se pudo leer frame de la webcam.')
            return

        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera'
        self.publisher.publish(msg)

    def destroy_node(self):
        if self.cap.isOpened():
            self.cap.release()
            self.get_logger().info('Webcam liberada.')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    try:
        node = WebcamPublisherLinux()
        rclpy.spin(node)
    except RuntimeError:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()