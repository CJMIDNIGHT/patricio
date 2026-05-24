import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import urllib.request

class WebcamPublisher(Node):
    def __init__(self):
        super().__init__('webcam_publisher')
        self.declare_parameter('windows_ip', '172.18.64.1')  # IP de Windows
        self.windows_ip = self.get_parameter('windows_ip').get_parameter_value().string_value
        self.url = f'http://{self.windows_ip}:8888/frame'

        self.publisher = self.create_publisher(Image, '/camera/real', 10)
        self.bridge = CvBridge()
        self.timer = self.create_timer(1/30, self.callback)
        self.get_logger().info(f'Conectando a cámara Windows en {self.url}')

    def callback(self):
        try:
            resp = urllib.request.urlopen(self.url, timeout=1)
            img_array = np.asarray(bytearray(resp.read()), dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if frame is not None:
                msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
                msg.header.stamp = self.get_clock().now().to_msg()
                self.publisher.publish(msg)
        except Exception as e:
            self.get_logger().warn(f'Error capturando frame: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = WebcamPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()