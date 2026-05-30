#!/usr/bin/env python3
"""
juego_calamar_node.py  —  patricio_calamar

Nodo ROS2 para el juego del Calamar — "Luz Roja, Luz Verde".

Fuente de datos de pose (prioridad):
  1. /patricio/vision/pose_landmarks  → patricio_vision corriendo (preferido)
  2. MediaPipe interno                → fallback si patricio_vision no responde

El watchdog comprueba cada segundo si llegan datos de patricio_vision.
Si no llegan en VISION_TIMEOUT segundos, activa el modo fallback.
Cuando vuelven, recupera el modo centralizado automáticamente.
"""

import random
import threading
import time

import cv2
import numpy as np
from cv_bridge import CvBridge

import mediapipe as mp

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from patricio_interfaces.msg import PoseResult


# ── Constantes de estado ─────────────────────────────────────────────────────
ESTADO_ESPERA = 'ESPERA'
ESTADO_VERDE  = 'LUZ_VERDE'
ESTADO_ROJO   = 'LUZ_ROJA'

# Timeout para considerar que patricio_vision no está disponible
VISION_TIMEOUT = 3.0

# ── MediaPipe setup (fallback) ───────────────────────────────────────────────
mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

TRACKED_LANDMARKS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
POSE_MOVEMENT_THRESHOLD_DEFAULT = 0.015


class JuegoCalamarNode(Node):

    def __init__(self):
        super().__init__('juego_calamar_real_node')

        # ── Parámetros ────────────────────────────────────────────────────
        self.declare_parameter('pose_movement_threshold',        POSE_MOVEMENT_THRESHOLD_DEFAULT)
        self.declare_parameter('pose_min_detection_confidence',  0.6)
        self.declare_parameter('pose_min_tracking_confidence',   0.5)
        self.declare_parameter('pose_fallback_pixel',            True)
        self.declare_parameter('verde_min_sec',                  3.0)
        self.declare_parameter('verde_max_sec',                  6.0)
        self.declare_parameter('rojo_min_sec',                   3.0)
        self.declare_parameter('rojo_max_sec',                   5.0)
        self.declare_parameter('vision_timeout',                 VISION_TIMEOUT)

        self.pose_threshold  = self.get_parameter('pose_movement_threshold').value
        det_conf             = self.get_parameter('pose_min_detection_confidence').value
        trk_conf             = self.get_parameter('pose_min_tracking_confidence').value
        self.fallback_pixel  = self.get_parameter('pose_fallback_pixel').value
        self.verde_min       = self.get_parameter('verde_min_sec').value
        self.verde_max       = self.get_parameter('verde_max_sec').value
        self.rojo_min        = self.get_parameter('rojo_min_sec').value
        self.rojo_max        = self.get_parameter('rojo_max_sec').value
        self._vision_timeout = self.get_parameter('vision_timeout').value

        # ── MediaPipe Pose (fallback interno) ─────────────────────────────
        self._pose_fallback = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=det_conf,
            min_tracking_confidence=trk_conf,
        )

        # ── Modo de fuente de datos ───────────────────────────────────────
        # True  → usando /patricio/vision/pose_landmarks (patricio_vision)
        # False → usando MediaPipe interno (fallback)
        self._using_central   = False
        self._last_central_ts = 0.0

        # ── Último PoseResult recibido de patricio_vision ─────────────────
        self._latest_pose_result: PoseResult | None = None
        self._pose_result_lock = threading.Lock()

        # ── Estado del juego ──────────────────────────────────────────────
        self.estado          = ESTADO_ESPERA
        self.stop_requested  = False
        self._detecting      = False
        self._game_thread    = None
        self._state_lock     = threading.Lock()

        # ── Pipeline de frames (para fallback y anotación) ────────────────
        self._bridge              = CvBridge()
        self._latest_frame        = None
        self._frame_lock          = threading.Lock()
        self._frame_event         = threading.Event()
        self._latest_pose_results = None   # resultados MediaPipe interno

        # ── Publishers ────────────────────────────────────────────────────
        self.status_pub    = self.create_publisher(String, '/patricio/calamar/status',           10)
        self.annotated_pub = self.create_publisher(Image,  '/patricio/calamar/camera_annotated', 10)
        self.alerta_pub    = self.create_publisher(String, '/patricio/alerta_juego',             10)

        # ── Subscribers ───────────────────────────────────────────────────
        self.cmd_sub = self.create_subscription(
            String, '/patricio/calamar/cmd', self.cmd_callback, 10)

        self.image_sub = self.create_subscription(
            Image, '/patricio/camera_processed', self._image_callback, 10)

        # Subscriber a patricio_vision (fuente prioritaria)
        self.create_subscription(
            PoseResult,
            '/patricio/vision/pose_landmarks',
            self._pose_result_callback,
            10,
        )

        # ── Watchdog: comprueba cada segundo si patricio_vision sigue vivo ─
        self.create_timer(1.0, self._watchdog)

        self.publish_status(ESTADO_ESPERA)
        self.get_logger().info(
            'juego_calamar_node listo.\n'
            '  Fuente prioritaria : /patricio/vision/pose_landmarks\n'
            f'  Timeout fallback   : {self._vision_timeout}s\n'
            '  Fallback           : MediaPipe interno'
        )

    # ── Watchdog ─────────────────────────────────────────────────────────────

    def _watchdog(self) -> None:
        """
        Comprueba cada segundo si patricio_vision sigue publicando.
        Mismo patrón que VisionNode con /camera/real.
        """
        now = self.get_clock().now().nanoseconds / 1e9

        if self._using_central:
            elapsed = now - self._last_central_ts
            if elapsed > self._vision_timeout:
                self._using_central = False
                self.get_logger().warn(
                    f'⚠️  /patricio/vision/pose_landmarks sin datos '
                    f'durante {elapsed:.1f}s. '
                    'Activando MediaPipe interno (fallback).'
                )
        # Si no estamos en central, el callback _pose_result_callback
        # lo reactivará automáticamente cuando vuelvan datos.

    # ── Callback de PoseResult (patricio_vision) ──────────────────────────────

    def _pose_result_callback(self, msg: PoseResult) -> None:
        """Recibe resultados de patricio_vision. Tiene prioridad absoluta."""
        self._last_central_ts = self.get_clock().now().nanoseconds / 1e9

        if not self._using_central:
            self._using_central = True
            self.get_logger().info(
                '✅ Usando /patricio/vision/pose_landmarks (patricio_vision activo).')

        with self._pose_result_lock:
            self._latest_pose_result = msg

    # ── Pipeline de imagen (para fallback y anotación) ───────────────────────

    def _image_callback(self, msg: Image) -> None:
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Solo ejecutar MediaPipe interno si estamos en modo fallback
            if not self._using_central:
                rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._pose_fallback.process(rgb)

                annotated = frame.copy()
                if results.pose_landmarks:
                    mp_drawing.draw_landmarks(
                        annotated,
                        results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS,
                        landmark_drawing_spec=mp_drawing.DrawingSpec(
                            color=(0, 120, 255), thickness=3, circle_radius=4),
                        connection_drawing_spec=mp_drawing.DrawingSpec(
                            color=(255, 120, 0), thickness=2),
                    )
                out_msg = self._bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
                out_msg.header = msg.header
                self.annotated_pub.publish(out_msg)

                with self._frame_lock:
                    self._latest_frame        = frame
                    self._latest_pose_results = results
                self._frame_event.set()

            else:
                # En modo central solo guardamos el frame (para pixel fallback)
                with self._frame_lock:
                    self._latest_frame = frame
                self._frame_event.set()

        except Exception as e:
            self.get_logger().warn(f'Error en _image_callback: {e}')

    def _get_frame(self, timeout=0.5):
        self._frame_event.wait(timeout=timeout)
        self._frame_event.clear()
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def _flush_frames(self, n_warmup=4):
        self._frame_event.clear()
        with self._frame_lock:
            self._latest_frame = None

        last_frame     = None
        last_landmarks = None
        collected      = 0

        while collected < n_warmup:
            if not self._detecting:
                return None, None
            frame = self._get_frame(timeout=1.0)
            if frame is None:
                self.get_logger().warn('Esperando frame para baseline...')
                continue
            last_frame     = frame
            last_landmarks = self._extract_landmarks_from_current_source()
            collected += 1

        return last_frame, last_landmarks

    # ── Extracción de landmarks (fuente unificada) ────────────────────────────

    def _extract_landmarks_from_current_source(self) -> np.ndarray | None:
        """
        Devuelve los landmarks como array numpy (N, 2) sea cual sea la fuente.
        Prioridad: patricio_vision → MediaPipe interno.
        """
        if self._using_central:
            return self._extract_landmarks_from_pose_result()
        else:
            return self._extract_landmarks_from_internal()

    def _extract_landmarks_from_pose_result(self) -> np.ndarray | None:
        """Extrae landmarks del último PoseResult de patricio_vision."""
        with self._pose_result_lock:
            result = self._latest_pose_result

        if result is None or not result.detected:
            return None

        if len(result.landmarks_x) < max(TRACKED_LANDMARKS) + 1:
            return None

        pts = np.array(
            [[result.landmarks_x[i], result.landmarks_y[i]]
             for i in TRACKED_LANDMARKS],
            dtype=np.float32,
        )
        return pts

    def _extract_landmarks_from_internal(self) -> np.ndarray | None:
        """Extrae landmarks del MediaPipe interno (fallback)."""
        with self._frame_lock:
            results = self._latest_pose_results

        if results is None or not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark
        return np.array(
            [[lm[i].x, lm[i].y] for i in TRACKED_LANDMARKS],
            dtype=np.float32,
        )

    # ── Detección de movimiento (sin cambios respecto a versión anterior) ─────

    def _detectar_movimiento(self, duracion_seg):
        t_inicio = time.time()

        fuente = 'patricio_vision' if self._using_central else 'MediaPipe interno'
        self.get_logger().info(
            f'Detección iniciada — fuente: {fuente} — construyendo baseline...')

        baseline_frame, baseline_lm = self._flush_frames(n_warmup=4)
        if baseline_frame is None:
            self.get_logger().warn('Baseline cancelado, saliendo.')
            return

        baseline_gray = self._to_gray(baseline_frame)

        if baseline_lm is not None:
            self.get_logger().info(
                f'Baseline listo CON pose ({len(TRACKED_LANDMARKS)} landmarks). '
                f'Umbral: {self.pose_threshold:.3f}')
        else:
            self.get_logger().warn(
                f'Baseline listo SIN pose. Fallback pixel: {self.fallback_pixel}')

        consecutive_no_person = 0

        while self._detecting and not self.stop_requested:
            with self._state_lock:
                if self.estado != ESTADO_ROJO:
                    break

            if duracion_seg is not None and (time.time() - t_inicio) >= duracion_seg:
                break

            frame = self._get_frame(timeout=0.5)
            if frame is None:
                continue

            # ── Obtener landmarks de la fuente activa ─────────────────
            curr_lm = self._extract_landmarks_from_current_source()

            infraccion = False
            score      = 0.0
            method     = 'none'

            if curr_lm is not None and baseline_lm is not None:
                score  = self._landmark_movement(baseline_lm, curr_lm)
                method = 'pose'
                consecutive_no_person = 0
                if score > self.pose_threshold:
                    infraccion = True

            elif self.fallback_pixel:
                curr_gray = self._to_gray(frame)
                diff      = cv2.absdiff(baseline_gray, curr_gray)
                _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                total     = thresh.shape[0] * thresh.shape[1]
                active    = int(np.sum(thresh) / 255)
                score     = (active / total) * 100.0
                method    = 'pixel_fallback'
                if score > 5.0:
                    infraccion = True

                consecutive_no_person += 1
                if consecutive_no_person % 20 == 1:
                    self.get_logger().warn(
                        'No se detecta persona — usando pixel fallback.')
            else:
                consecutive_no_person += 1
                if consecutive_no_person % 20 == 1:
                    self.get_logger().warn(
                        'No se detecta persona y fallback desactivado — esperando...')
                continue

            self.get_logger().debug(
                f'[{method}] score={score:.4f}  '
                f'fuente={"central" if self._using_central else "fallback_interno"}')

            if infraccion:
                self.get_logger().info(
                    f'¡INFRACCIÓN! método={method} score={score:.4f}')
                self._publicar_infraccion()

                for _ in range(20):
                    if not self._detecting:
                        break
                    with self._state_lock:
                        if self.estado != ESTADO_ROJO:
                            break
                    time.sleep(0.1)

                if not self._detecting:
                    break
                with self._state_lock:
                    still_red = (self.estado == ESTADO_ROJO)
                if not still_red:
                    break

                self.get_logger().info('Reconstruyendo baseline tras infracción...')
                baseline_frame, baseline_lm = self._flush_frames(n_warmup=4)
                if baseline_frame is None:
                    break
                baseline_gray = self._to_gray(baseline_frame)
                self.get_logger().info('Baseline reconstruido. Reanudando detección.')
                continue

            if curr_lm is not None:
                baseline_lm = curr_lm
            curr_gray_for_update = self._to_gray(frame)
            baseline_gray = cv2.addWeighted(
                baseline_gray, 0.95, curr_gray_for_update, 0.05, 0)

        self.get_logger().info('Detección finalizada.')

    # ── Comandos ──────────────────────────────────────────────────────────────

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()
        self.get_logger().info(f'Comando recibido: {cmd}')
        if   cmd == 'START_AUTO':       self._iniciar_auto()
        elif cmd == 'CAMBIAR_A_VERDE':  self._set_manual(ESTADO_VERDE)
        elif cmd == 'CAMBIAR_A_ROJO':   self._set_manual(ESTADO_ROJO)
        elif cmd == 'STOP':             self._detener()
        elif cmd.startswith('SET_THRESHOLD:'):
            try:
                val = float(cmd.split(':')[1])
                self.pose_threshold = val
                self.get_logger().info(f'Umbral actualizado → {val}')
            except (IndexError, ValueError):
                self.get_logger().warn('SET_THRESHOLD mal formado, ignorado.')

    # ── Modo automático ───────────────────────────────────────────────────────

    def _iniciar_auto(self):
        with self._state_lock:
            if self.estado != ESTADO_ESPERA:
                self.get_logger().warn('Juego ya en marcha, ignorando START_AUTO.')
                return
            self.stop_requested = False

        self.get_logger().info('Esperando frames de cámara...')
        if self._get_frame(timeout=5.0) is None:
            self.get_logger().error('No llegan frames. Comprueba la cámara.')
            return

        self._game_thread = threading.Thread(target=self._bucle_auto, daemon=True)
        self._game_thread.start()

    def _bucle_auto(self):
        self.get_logger().info('Modo automático iniciado.')
        while not self.stop_requested:
            dur_verde = random.uniform(self.verde_min, self.verde_max)
            self._detecting = False
            self._cambiar_estado(ESTADO_VERDE)
            self.get_logger().info(f'LUZ VERDE {dur_verde:.1f}s')
            self._esperar(dur_verde)
            if self.stop_requested:
                break

            dur_roja = random.uniform(self.rojo_min, self.rojo_max)
            self._detecting = True
            self._cambiar_estado(ESTADO_ROJO)
            self.get_logger().info(f'LUZ ROJA {dur_roja:.1f}s')
            self._detectar_movimiento(dur_roja)

        self._detecting = False
        self._cambiar_estado(ESTADO_ESPERA)
        self.get_logger().info('Modo automático detenido.')

    # ── Modo manual ───────────────────────────────────────────────────────────

    def _set_manual(self, nuevo_estado):
        self._detecting = False
        time.sleep(0.15)

        with self._state_lock:
            self.stop_requested = False

        self._cambiar_estado(nuevo_estado)

        if nuevo_estado == ESTADO_ROJO:
            self._detecting = True
            self._game_thread = threading.Thread(
                target=self._detectar_movimiento, args=(None,), daemon=True)
            self._game_thread.start()

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_gray(bgr_frame):
        gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (21, 21), 0)

    @staticmethod
    def _landmark_movement(prev_lm, curr_lm):
        if prev_lm is None or curr_lm is None:
            return 0.0
        dists = np.linalg.norm(curr_lm - prev_lm, axis=1)
        return float(np.mean(dists))

    def _publicar_infraccion(self):
        msg = String()
        msg.data = 'INFRACCION'
        self.alerta_pub.publish(msg)

    def _cambiar_estado(self, nuevo):
        with self._state_lock:
            self.estado = nuevo
        self.publish_status(nuevo)
        self.get_logger().info(f'Estado → {nuevo}')

    def _detener(self):
        self._detecting     = False
        self.stop_requested = True
        with self._state_lock:
            self.estado = ESTADO_ESPERA
        self.publish_status(ESTADO_ESPERA)
        self.get_logger().info('Juego detenido.')

    def _esperar(self, segundos):
        t_fin = time.time() + segundos
        while not self.stop_requested and time.time() < t_fin:
            time.sleep(0.1)

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)

    def destroy_node(self):
        self._pose_fallback.close()
        super().destroy_node()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = JuegoCalamarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._detener()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()