import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class VisionNode(Node):
    """
    Nodo de visión unificado para el robot Patricio.

    Prioridad de fuente:
      1. /camera/real      → webcam del portátil (robot real simulado)
      2. /camera/image_raw → cámara de Gazebo (fallback automático)

    Si /camera/real deja de publicar durante TIMEOUT segundos,
    el nodo cambia automáticamente a /camera/image_raw.
    Cuando /camera/real vuelve, recupera la prioridad.
    """

    TIMEOUT = 3.0

    def __init__(self):
        super().__init__('vision_node')

        self.bridge = CvBridge()

        # ── ESTADO INTERNO ───────────────────────────────────────────────
        self.using_real   = False
        self.last_real_ts = 0.0

        # ── PUBLISHER ────────────────────────────────────────────────────
        self.publisher = self.create_publisher(
            Image,
            '/patricio/camera_processed',
            10
        )

        # ── SUBSCRIBER PRIORITARIO: webcam real ──────────────────────────
        # Publica el webcam_publisher cuando la cámara del portátil está activa.
        # Si llega un frame aquí, siempre tiene preferencia sobre Gazebo.
        self.sub_real = self.create_subscription(
            Image,
            '/camera/real',
            self.callback_real,
            10
        )

        # ── SUBSCRIBER FALLBACK: Gazebo / robot real ─────────────────────
        # Se usa cuando /camera/real no ha publicado en los últimos TIMEOUT segundos.
        self.sub_gazebo = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.callback_gazebo,
            10
        )

        # ── TIMER DE WATCHDOG ────────────────────────────────────────────
        # Comprueba cada segundo si /camera/real sigue activo.
        self.watchdog = self.create_timer(1.0, self.check_source)

        self.get_logger().info(
            'VisionNode arrancado.\n'
            f'  Fuente prioritaria : /camera/real\n'
            f'  Fuente fallback     : /camera/image_raw\n'
            f'  Timeout fallback    : {self.TIMEOUT}s'
        )

    # ── CALLBACK WEBCAM REAL ─────────────────────────────────────────────
    def callback_real(self, msg: Image):
        """
        Se ejecuta cuando llega un frame de /camera/real (webcam portátil).
        Siempre procesa y publica — tiene prioridad absoluta.
        """
        self.last_real_ts = self.get_clock().now().nanoseconds / 1e9

        if not self.using_real:
            self.using_real = True
            self.get_logger().info('📷 Fuente activa: webcam real (/camera/real)')

        self._process_and_publish(msg)

    # ── CALLBACK GAZEBO / FALLBACK ───────────────────────────────────────
    def callback_gazebo(self, msg: Image):
        """
        Se ejecuta cuando llega un frame de /camera/image_raw (Gazebo o robot real).
        Solo procesa si /camera/real no está activo (using_real = False).
        """
        if self.using_real:
            return

        self._process_and_publish(msg)

    # ── WATCHDOG ─────────────────────────────────────────────────────────
    def check_source(self):
        """
        Se ejecuta cada segundo. Si han pasado más de TIMEOUT segundos
        sin frames reales, desactiva la prioridad y deja pasar Gazebo.
        """
        if not self.using_real:
            return

        now = self.get_clock().now().nanoseconds / 1e9
        elapsed = now - self.last_real_ts

        if elapsed > self.TIMEOUT:
            self.using_real = False
            self.get_logger().warn(
                f'⚠️  /camera/real sin frames durante {elapsed:.1f}s. '
                'Cambiando a fallback: /camera/image_raw'
            )

    # ── PROCESADO COMÚN ──────────────────────────────────────────────────
    def _process_and_publish(self, msg: Image):
        """
        Convierte, filtra y publica un frame independientemente de su origen.
        """
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'CvBridge error al recibir imagen: {e}')
            return

        processed = cv2.GaussianBlur(frame, (3, 3), 0)

        try:
            out_msg = self.bridge.cv2_to_imgmsg(processed, encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'CvBridge error al publicar imagen: {e}')
            return

        out_msg.header = msg.header
        self.publisher.publish(out_msg)


# ── PUNTO DE ENTRADA ─────────────────────────────────────────────────────
def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()