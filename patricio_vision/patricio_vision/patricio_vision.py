#!/usr/bin/env python3
"""
mediapipe_node.py  —  patricio_vision

Nodo centralizado de MediaPipe para el robot Patricio.

Responsabilidades:
  - Suscribirse a /patricio/camera_processed (ya procesado por VisionNode)
  - Ejecutar MediaPipe Pose UNA SOLA VEZ por frame
  - Publicar resultados continuos en dos topics:
      /patricio/vision/person_detection  →  PersonDetection.msg
      /patricio/vision/pose_landmarks    →  PoseResult.msg

Los juegos (pilla_pilla, escondite, calamar) suscriben a estos topics
y usan los datos sin ejecutar MediaPipe ellos mismos.

Diseño de threading:
  - El callback de imagen es ligero: solo guarda el frame.
  - Un hilo dedicado ejecuta MediaPipe y publica resultados.
  - Así el executor de ROS2 nunca se bloquea.

Compatibilidad: MediaPipe 0.10.x (solutions API clásica).
"""

import threading
import time

import cv2
import numpy as np
from cv_bridge import CvBridge

import mediapipe as mp

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Header

from patricio_interfaces.msg import PersonDetection, PoseResult


# ── MediaPipe setup ──────────────────────────────────────────────────────────
mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Landmarks clave para calcular movimiento (cubre todo el cuerpo)
# nariz(0), hombros(11,12), codos(13,14), muñecas(15,16),
# caderas(23,24), rodillas(25,26), tobillos(27,28)
TRACKED_LANDMARKS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]

# Umbral por defecto de movimiento (score medio de desplazamiento normalizado)
MOVEMENT_THRESHOLD_DEFAULT = 0.015


class MediaPipeNode(Node):
    """
    Nodo ROS2 que centraliza la ejecución de MediaPipe Pose.

    Topics de entrada:
      /patricio/camera_processed  (sensor_msgs/Image, bgr8)

    Topics de salida:
      /patricio/vision/person_detection  (patricio_interfaces/PersonDetection)
      /patricio/vision/pose_landmarks    (patricio_interfaces/PoseResult)
      /patricio/vision/camera_annotated  (sensor_msgs/Image)  ← debug visual
    """

    def __init__(self):
        super().__init__('mediapipe_node')

        # ── Parámetros ────────────────────────────────────────────────────
        self.declare_parameter('movement_threshold',       MOVEMENT_THRESHOLD_DEFAULT)
        self.declare_parameter('min_detection_confidence', 0.6)
        self.declare_parameter('min_tracking_confidence',  0.5)
        self.declare_parameter('model_complexity',         1)
        self.declare_parameter('publish_annotated',        True)
        self.declare_parameter('target_fps',               15.0)

        self._threshold   = self.get_parameter('movement_threshold').value
        det_conf          = self.get_parameter('min_detection_confidence').value
        trk_conf          = self.get_parameter('min_tracking_confidence').value
        model_complexity  = self.get_parameter('model_complexity').value
        self._pub_annot   = self.get_parameter('publish_annotated').value
        target_fps        = self.get_parameter('target_fps').value

        self._min_frame_interval = 1.0 / target_fps  # segundos entre procesados

        # ── MediaPipe Pose ────────────────────────────────────────────────
        self._pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=det_conf,
            min_tracking_confidence=trk_conf,
        )
        self.get_logger().info(
            f'MediaPipe Pose cargado '
            f'(det={det_conf}, trk={trk_conf}, '
            f'complexity={model_complexity}, '
            f'umbral_movimiento={self._threshold}, '
            f'target_fps={target_fps})'
        )

        # ── Estado interno ────────────────────────────────────────────────
        self._bridge        = CvBridge()
        self._latest_frame  = None
        self._latest_header = None
        self._frame_lock    = threading.Lock()
        self._frame_event   = threading.Event()
        self._prev_landmarks: np.ndarray | None = None  # para delta de movimiento
        self._last_process_time = 0.0

        # ── Publishers ────────────────────────────────────────────────────
        self._pub_detection = self.create_publisher(
            PersonDetection,
            '/patricio/vision/person_detection',
            10,
        )
        self._pub_pose = self.create_publisher(
            PoseResult,
            '/patricio/vision/pose_landmarks',
            10,
        )
        if self._pub_annot:
            self._pub_annotated = self.create_publisher(
                Image,
                '/patricio/vision/camera_annotated',
                10,
            )

        # ── Subscriber ────────────────────────────────────────────────────
        self.create_subscription(
            Image,
            '/patricio/camera_processed',
            self._image_callback,
            10,
        )

        # ── Hilo de procesado ─────────────────────────────────────────────
        # MediaPipe corre en su propio hilo para no bloquear el executor.
        self._running = True
        self._process_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
            name='mediapipe_process',
        )
        self._process_thread.start()

        self.get_logger().info(
            'MediaPipeNode listo.\n'
            '  Entrada  : /patricio/camera_processed\n'
            '  Salida 1 : /patricio/vision/person_detection\n'
            '  Salida 2 : /patricio/vision/pose_landmarks\n'
            '  Debug    : /patricio/vision/camera_annotated'
        )

    # ── Callback de imagen (ligero, no bloquea) ──────────────────────────────

    def _image_callback(self, msg: Image) -> None:
        """
        Solo guarda el frame más reciente. No hace ningún procesado aquí.
        El hilo _process_loop consume los frames a la tasa objetivo.
        """
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'CvBridge error: {e}')
            return

        with self._frame_lock:
            self._latest_frame  = frame
            self._latest_header = msg.header

        self._frame_event.set()

    # ── Hilo de procesado ────────────────────────────────────────────────────

    def _process_loop(self) -> None:
        """
        Hilo dedicado a ejecutar MediaPipe y publicar resultados.
        Respeta target_fps para no sobrecargar la CPU.
        """
        self.get_logger().info('Hilo de procesado MediaPipe iniciado.')

        while self._running:
            # Esperar nuevo frame (timeout para poder salir limpiamente)
            signaled = self._frame_event.wait(timeout=1.0)
            if not signaled:
                continue
            self._frame_event.clear()

            # Respetar la tasa objetivo
            now = time.monotonic()
            elapsed = now - self._last_process_time
            if elapsed < self._min_frame_interval:
                time.sleep(self._min_frame_interval - elapsed)

            # Leer frame de forma thread-safe
            with self._frame_lock:
                if self._latest_frame is None:
                    continue
                frame  = self._latest_frame.copy()
                header = self._latest_header

            self._last_process_time = time.monotonic()

            # ── Ejecutar MediaPipe ────────────────────────────────────
            try:
                rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._pose.process(rgb)
            except Exception as e:
                self.get_logger().error(f'MediaPipe error: {e}')
                continue

            # ── Publicar resultados ───────────────────────────────────
            self._publish_detection(header, frame, results)
            self._publish_pose(header, results)

            if self._pub_annot:
                self._publish_annotated(header, frame, results)

        self.get_logger().info('Hilo de procesado MediaPipe terminado.')

    # ── Publicar PersonDetection ─────────────────────────────────────────────

    def _publish_detection(self, header, frame: np.ndarray, results) -> None:
        """
        Calcula la posición del centro de la persona y el error respecto
        al centro del frame. Usado por pilla_pilla para centrar al niño.
        """
        msg = PersonDetection()
        msg.header = header

        if not results.pose_landmarks:
            # Sin persona detectada — publicar con detected=False
            msg.detected     = False
            msg.center_x     = 0.5
            msg.center_y     = 0.5
            msg.error_x      = 0.0
            msg.error_y      = 0.0
            msg.bbox_width   = 0.0
            msg.bbox_height  = 0.0
            msg.confidence   = 0.0
            msg.movement_score = 0.0
            self._pub_detection.publish(msg)
            self._prev_landmarks = None
            return

        lm = results.pose_landmarks.landmark

        # ── Bounding box a partir de todos los landmarks visibles ─────
        xs = [l.x for l in lm if l.visibility > 0.3]
        ys = [l.y for l in lm if l.visibility > 0.3]

        if not xs:
            msg.detected = False
            self._pub_detection.publish(msg)
            return

        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        center_x = (x_min + x_max) / 2.0
        center_y = (y_min + y_max) / 2.0

        # ── Score de movimiento ───────────────────────────────────────
        curr_lm = self._get_tracked_landmarks(lm)
        movement_score = self._compute_movement(self._prev_landmarks, curr_lm)
        self._prev_landmarks = curr_lm

        # ── Construir mensaje ─────────────────────────────────────────
        msg.detected       = True
        msg.center_x       = float(center_x)
        msg.center_y       = float(center_y)
        # Error: cuánto se aleja del centro del frame (0.5, 0.5)
        # Positivo = persona a la derecha / abajo
        msg.error_x        = float(center_x - 0.5)
        msg.error_y        = float(center_y - 0.5)
        msg.bbox_width     = float(x_max - x_min)
        msg.bbox_height    = float(y_max - y_min)
        # Usamos la visibilidad media de hombros como proxy de confianza
        shoulder_vis = (lm[11].visibility + lm[12].visibility) / 2.0
        msg.confidence     = float(min(shoulder_vis, 1.0))
        msg.movement_score = float(movement_score)

        self._pub_detection.publish(msg)

    # ── Publicar PoseResult ──────────────────────────────────────────────────

    def _publish_pose(self, header, results) -> None:
        """
        Publica los 33 landmarks de MediaPipe Pose normalizados.
        Usado por juego_calamar para la detección de movimiento.
        """
        msg = PoseResult()
        msg.header = header

        if not results.pose_landmarks:
            msg.detected              = False
            msg.landmarks_x           = []
            msg.landmarks_y           = []
            msg.landmarks_z           = []
            msg.landmarks_visibility  = []
            msg.movement_score        = 0.0
            msg.movement_threshold_used = float(self._threshold)
            self._pub_pose.publish(msg)
            return

        lm = results.pose_landmarks.landmark

        msg.detected             = True
        msg.landmarks_x          = [float(l.x)          for l in lm]
        msg.landmarks_y          = [float(l.y)          for l in lm]
        msg.landmarks_z          = [float(l.z)          for l in lm]
        msg.landmarks_visibility = [float(l.visibility) for l in lm]

        curr_lm = self._get_tracked_landmarks(lm)
        msg.movement_score           = float(
            self._compute_movement(self._prev_landmarks, curr_lm)
        )
        msg.movement_threshold_used  = float(self._threshold)

        self._pub_pose.publish(msg)

    # ── Publicar frame anotado (debug) ───────────────────────────────────────

    def _publish_annotated(self, header, frame: np.ndarray, results) -> None:
        """
        Publica el frame con el esqueleto dibujado encima.
        Solo activo si publish_annotated=True (parámetro).
        """
        annotated = frame.copy()

        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                annotated,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing.DrawingSpec(
                    color=(0, 255, 120), thickness=3, circle_radius=4),
                connection_drawing_spec=mp_drawing.DrawingSpec(
                    color=(255, 255, 0), thickness=2),
            )

        try:
            out_msg = self._bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            out_msg.header = header
            self._pub_annotated.publish(out_msg)
        except Exception as e:
            self.get_logger().error(f'Error publicando frame anotado: {e}')

    # ── Helpers de movimiento ────────────────────────────────────────────────

    def _get_tracked_landmarks(self, lm) -> np.ndarray:
        """Extrae los landmarks clave como array numpy (N, 2)."""
        return np.array(
            [[lm[i].x, lm[i].y] for i in TRACKED_LANDMARKS],
            dtype=np.float32,
        )

    @staticmethod
    def _compute_movement(
        prev: np.ndarray | None,
        curr: np.ndarray | None,
    ) -> float:
        """
        Score de movimiento = distancia Euclidea media entre landmarks
        consecutivos. Devuelve 0.0 si alguno es None.
        """
        if prev is None or curr is None:
            return 0.0
        dists = np.linalg.norm(curr - prev, axis=1)
        return float(np.mean(dists))

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def destroy_node(self) -> None:
        self._running = False
        self._frame_event.set()          # desbloquear el hilo si está esperando
        self._process_thread.join(timeout=3.0)
        self._pose.close()
        super().destroy_node()
        self.get_logger().info('MediaPipeNode destruido limpiamente.')


# ── Entry point ──────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = MediaPipeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()