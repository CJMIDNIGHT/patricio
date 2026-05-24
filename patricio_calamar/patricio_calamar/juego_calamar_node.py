#!/usr/bin/env python3

"""
Nodo ROS2 para el juego del Calamar — "Luz Roja, Luz Verde".
Detección de movimiento basada en MediaPipe Pose (landmarks corporales)
en lugar de diferencia de píxeles.
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

ESTADO_ESPERA = 'ESPERA'
ESTADO_VERDE  = 'LUZ_VERDE'
ESTADO_ROJO   = 'LUZ_ROJA'

# ── MediaPipe Pose setup ─────────────────────────────────────────────────────
# We use the standard Pose solution (not the newer Tasks API) because it ships
# with MediaPipe 0.10.x and doesn't require a model file download at runtime.
mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Landmark indices we care about — full body coverage:
#   nose(0), shoulders(11,12), elbows(13,14), wrists(15,16),
#   hips(23,24), knees(25,26), ankles(27,28)
# Using all 33 is also fine; these 14 are the most reliable for occlusion.
TRACKED_LANDMARKS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]

# Default movement threshold: sum of normalised-coordinate displacements
# across all tracked landmarks between two consecutive frames.
# 0.02  → very sensitive  (detects small hand/head shifts)
# 0.05  → medium          (good starting point)
# 0.10  → requires obvious body movement
POSE_MOVEMENT_THRESHOLD_DEFAULT = 0.015


class JuegoCalamarNode(Node):

    def __init__(self):
        super().__init__('juego_calamar_node')

        # ── ROS parameters ────────────────────────────────
        self.declare_parameter('pose_movement_threshold', POSE_MOVEMENT_THRESHOLD_DEFAULT)
        self.declare_parameter('pose_min_detection_confidence', 0.6)
        self.declare_parameter('pose_min_tracking_confidence',  0.5)
        self.declare_parameter('pose_fallback_pixel', True)   # pixel-diff if no person found
        self.declare_parameter('verde_min_sec', 3.0)
        self.declare_parameter('verde_max_sec', 6.0)
        self.declare_parameter('rojo_min_sec',  3.0)
        self.declare_parameter('rojo_max_sec',  5.0)

        self.pose_threshold = self.get_parameter(
            'pose_movement_threshold').get_parameter_value().double_value
        det_conf = self.get_parameter(
            'pose_min_detection_confidence').get_parameter_value().double_value
        trk_conf = self.get_parameter(
            'pose_min_tracking_confidence').get_parameter_value().double_value
        self.fallback_pixel = self.get_parameter(
            'pose_fallback_pixel').get_parameter_value().bool_value

        self.verde_min = self.get_parameter('verde_min_sec').get_parameter_value().double_value
        self.verde_max = self.get_parameter('verde_max_sec').get_parameter_value().double_value
        self.rojo_min  = self.get_parameter('rojo_min_sec').get_parameter_value().double_value
        self.rojo_max  = self.get_parameter('rojo_max_sec').get_parameter_value().double_value

        # ── MediaPipe Pose ────────────────────────────────
        # static_image_mode=False → treats input as a video stream (faster tracking)
        self._pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,             # 0=fast/lite, 1=balanced, 2=heavy
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=det_conf,
            min_tracking_confidence=trk_conf,
        )
        self.get_logger().info(
            f'MediaPipe Pose cargado (det={det_conf}, trk={trk_conf}, '
            f'umbral_movimiento={self.pose_threshold})'
        )

        # ── Game state ────────────────────────────────────
        self.estado         = ESTADO_ESPERA
        self.stop_requested = False
        self._detecting     = False
        self._game_thread   = None
        self._state_lock    = threading.Lock()

        # ── Frame pipeline ────────────────────────────────
        self._bridge       = CvBridge()
        self._latest_frame = None
        self._frame_lock   = threading.Lock()
        self._frame_event  = threading.Event()
        self._latest_pose_results = None

        # ── ROS topics ────────────────────────────────────
        self.status_pub = self.create_publisher(String, '/patricio/calamar/status', 10)
        self.annotated_pub = self.create_publisher(Image, '/patricio/calamar/camera_annotated', 10)
        self.alerta_pub = self.create_publisher(String, '/patricio/alerta_juego',   10)
        self.cmd_sub    = self.create_subscription(
            String, '/patricio/calamar/cmd',  self.cmd_callback,    10)
        self.image_sub  = self.create_subscription(
            Image,  '/patricio/camera_processed',            self._image_callback, 10)

        self.publish_status(ESTADO_ESPERA)
        self.get_logger().info('juego_calamar_node listo (modo: MediaPipe Pose).')

    # ────────────────────────────────────────────────────
    # Image pipeline
    # ────────────────────────────────────────────────────

    def _image_callback(self, msg):
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Run MediaPipe ONCE here for both annotation and detection
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._pose.process(rgb)

            # Draw skeleton on annotated frame
            annotated = frame.copy()
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    annotated,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing.DrawingSpec(
                        color=(0, 255, 120), thickness=3, circle_radius=4),
                    connection_drawing_spec=mp_drawing.DrawingSpec(
                        color=(255, 255, 0), thickness=2)
                )

            # Publish annotated frame
            out_msg = self._bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
            out_msg.header = msg.header
            self.annotated_pub.publish(out_msg)

            # Share raw frame AND pose results with detection loop
            with self._frame_lock:
                self._latest_frame = frame
                self._latest_pose_results = results
            self._frame_event.set()

        except Exception as e:
            self.get_logger().warn(f'Error en _image_callback: {e}')

    def _get_frame(self, timeout=0.5):
        """Wait for a new frame. Returns None on timeout."""
        self._frame_event.wait(timeout=timeout)
        self._frame_event.clear()
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def _flush_frames(self, n_warmup=4):
        """
        Flush stale frames and wait for n_warmup fresh ones.
        Returns the last frame (used as stable baseline for pixel fallback),
        AND the landmark array from that frame (pose baseline).
        Returns (None, None) if cancelled.
        """
        self._frame_event.clear()
        with self._frame_lock:
            self._latest_frame = None

        last_frame     = None
        last_landmarks = None
        collected = 0

        while collected < n_warmup:
            if not self._detecting:
                return None, None
            frame = self._get_frame(timeout=1.0)
            if frame is None:
                self.get_logger().warn('Esperando frame para baseline...')
                continue
            last_frame = frame
            last_landmarks = self._extract_landmarks(frame)
            collected += 1

        return last_frame, last_landmarks

    # ────────────────────────────────────────────────────
    # MediaPipe helpers
    # ────────────────────────────────────────────────────

    def _extract_landmarks(self, bgr_frame):
        with self._frame_lock:
            results = self._latest_pose_results
        if results is None or not results.pose_landmarks:
            return None
        lm = results.pose_landmarks.landmark
        pts = np.array(
            [[lm[i].x, lm[i].y] for i in TRACKED_LANDMARKS],
            dtype=np.float32
        )
        return pts

    @staticmethod
    def _landmark_movement(prev_lm, curr_lm):
        """
        Compute total movement score between two landmark arrays.
        Score = mean Euclidean distance across all tracked landmarks.
        Both arrays must have the same shape; returns 0.0 if either is None.
        """
        if prev_lm is None or curr_lm is None:
            return 0.0
        # Per-landmark Euclidean distance, then mean across all landmarks
        dists = np.linalg.norm(curr_lm - prev_lm, axis=1)
        return float(np.mean(dists))

    # ────────────────────────────────────────────────────
    # Commands
    # ────────────────────────────────────────────────────

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()
        self.get_logger().info(f'Comando recibido: {cmd}')
        if   cmd == 'START_AUTO':      self._iniciar_auto()
        elif cmd == 'CAMBIAR_A_VERDE': self._set_manual(ESTADO_VERDE)
        elif cmd == 'CAMBIAR_A_ROJO':  self._set_manual(ESTADO_ROJO)
        elif cmd == 'STOP':            self._detener()
        elif cmd.startswith('SET_THRESHOLD:'):
            # Dynamic threshold update from frontend
            # e.g.  SET_THRESHOLD:0.04
            try:
                val = float(cmd.split(':')[1])
                self.pose_threshold = val
                self.get_logger().info(f'Umbral actualizado → {val}')
            except (IndexError, ValueError):
                self.get_logger().warn('SET_THRESHOLD mal formado, ignorado.')

    # ────────────────────────────────────────────────────
    # Auto mode
    # ────────────────────────────────────────────────────

    def _iniciar_auto(self):
        with self._state_lock:
            if self.estado != ESTADO_ESPERA:
                self.get_logger().warn('Juego ya en marcha, ignorando START_AUTO.')
                return
            self.stop_requested = False

        self.get_logger().info('Esperando frames de /camera/real...')
        if self._get_frame(timeout=5.0) is None:
            self.get_logger().error('No llegan frames. Comprueba webcam_publisher_linux.')
            return

        self._game_thread = threading.Thread(target=self._bucle_auto, daemon=True)
        self._game_thread.start()

    def _bucle_auto(self):
        self.get_logger().info('Modo automático iniciado.')
        while not self.stop_requested:
            # ── Verde — detección OFF ─────────────────────
            dur_verde = random.uniform(self.verde_min, self.verde_max)
            self._detecting = False
            self._cambiar_estado(ESTADO_VERDE)
            self.get_logger().info(f'LUZ VERDE {dur_verde:.1f}s')
            self._esperar(dur_verde)
            if self.stop_requested:
                break

            # ── Rojo — detección ON ───────────────────────
            dur_roja = random.uniform(self.rojo_min, self.rojo_max)
            self._detecting = True
            self._cambiar_estado(ESTADO_ROJO)
            self.get_logger().info(f'LUZ ROJA {dur_roja:.1f}s')
            self._detectar_movimiento(dur_roja)

        self._detecting = False
        self._cambiar_estado(ESTADO_ESPERA)
        self.get_logger().info('Modo automático detenido.')

    # ────────────────────────────────────────────────────
    # Manual mode
    # ────────────────────────────────────────────────────

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

    # ────────────────────────────────────────────────────
    # Movement detection  ← CORE CHANGE
    # ────────────────────────────────────────────────────

    def _detectar_movimiento(self, duracion_seg):
        """
        Pose-based movement detection loop.

        Strategy:
          1. Flush stale frames and build a stable baseline (pose landmarks).
          2. Each iteration:
               a. Extract landmarks from the current frame.
               b. If a person IS detected → compare landmark positions to baseline.
                  Movement score = mean displacement across 14 key joints.
               c. If NO person detected AND fallback_pixel=True → use pixel diff
                  as a safety net (same logic as before, higher threshold).
          3. On infraction: anti-spam sleep, then rebuild baseline from scratch.
          4. If no infraction: update baseline landmark array gradually.

        Why landmarks beat pixels:
          - Immune to lighting changes, camera noise, background motion.
          - Measures actual skeletal movement, not raw frame differences.
          - Gracefully degrades: if partial body visible, only visible joints count.
        """
        t_inicio = time.time()
        self.get_logger().info('Detección iniciada — construyendo baseline...')

        # ── Build initial baseline ────────────────────────
        baseline_frame, baseline_lm = self._flush_frames(n_warmup=4)
        if baseline_frame is None:
            self.get_logger().warn('Baseline cancelado, saliendo.')
            return

        # Pre-compute pixel baseline for fallback (greyscale + blur)
        baseline_gray = self._to_gray(baseline_frame)

        if baseline_lm is not None:
            self.get_logger().info(
                f'Baseline listo CON pose ({len(TRACKED_LANDMARKS)} landmarks). '
                f'Umbral: {self.pose_threshold:.3f}')
        else:
            self.get_logger().warn(
                'Baseline listo SIN pose (nadie detectado). '
                f'Fallback pixel: {self.fallback_pixel}')

        consecutive_no_person = 0  # log noise limiter

        while self._detecting and not self.stop_requested:
            with self._state_lock:
                if self.estado != ESTADO_ROJO:
                    break

            if duracion_seg is not None and (time.time() - t_inicio) >= duracion_seg:
                break

            frame = self._get_frame(timeout=0.5)
            if frame is None:
                continue

            # ── Extract current pose ──────────────────────
            curr_lm = self._extract_landmarks(frame)

            infraccion = False
            score      = 0.0
            method     = 'none'

            if curr_lm is not None and baseline_lm is not None:
                # ── PRIMARY: pose landmark comparison ─────
                score  = self._landmark_movement(baseline_lm, curr_lm)
                method = 'pose'
                consecutive_no_person = 0

                if score > self.pose_threshold:
                    infraccion = True

            elif self.fallback_pixel:
                # ── FALLBACK: pixel diff (higher threshold) ─
                # Only fires if NO human skeleton is visible at all.
                # We use 5 % of pixels — much stricter than before — to
                # avoid false positives from background motion.
                curr_gray = self._to_gray(frame)
                diff      = cv2.absdiff(baseline_gray, curr_gray)
                _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                total     = thresh.shape[0] * thresh.shape[1]
                active    = int(np.sum(thresh) / 255)
                score     = (active / total) * 100.0
                method    = 'pixel_fallback'

                if score > 5.0:   # hard-coded 5 % for fallback
                    infraccion = True

                consecutive_no_person += 1
                if consecutive_no_person % 20 == 1:
                    self.get_logger().warn(
                        'No se detecta persona — usando pixel fallback.')
            else:
                # No person, fallback disabled → skip frame
                consecutive_no_person += 1
                if consecutive_no_person % 20 == 1:
                    self.get_logger().warn(
                        'No se detecta persona y fallback desactivado — esperando...')
                continue

            self.get_logger().debug(
                f'[{method}] score={score:.4f}  umbral='
                f'{self.pose_threshold if method == "pose" else "5.0%"}')

            if infraccion:
                self.get_logger().info(
                    f'¡INFRACCIÓN! método={method} score={score:.4f}')
                self._publicar_infraccion()

                # Anti-spam: interruptible 2 s wait.
                # Checks _detecting and estado every 100 ms so that if the game
                # switches to LUZ_VERDE or STOP mid-wait we exit immediately
                # instead of waking up 2 s later and running baseline rebuild
                # + detection in the wrong state.
                for _ in range(20):
                    if not self._detecting:
                        break
                    with self._state_lock:
                        if self.estado != ESTADO_ROJO:
                            break
                    time.sleep(0.1)

                # Re-check after sleep — game may have moved on.
                if not self._detecting:
                    break
                with self._state_lock:
                    still_red = (self.estado == ESTADO_ROJO)
                if not still_red:
                    break

                # Rebuild baseline AFTER movement stops
                self.get_logger().info('Reconstruyendo baseline tras infracción...')
                baseline_frame, baseline_lm = self._flush_frames(n_warmup=4)
                if baseline_frame is None:
                    break
                baseline_gray = self._to_gray(baseline_frame)
                self.get_logger().info('Baseline reconstruido. Reanudando detección.')
                continue

            # ── No infraction: rolling baseline update ────
            # Pose: replace landmarks directly (they're already stable from MediaPipe smoothing)
            if curr_lm is not None:
                baseline_lm = curr_lm
            # Pixel: weighted rolling average (handles slow lighting drift)
            curr_gray_for_update = self._to_gray(frame)
            baseline_gray = cv2.addWeighted(
                baseline_gray, 0.95, curr_gray_for_update, 0.05, 0)

        self.get_logger().info('Detección finalizada.')

    # ────────────────────────────────────────────────────
    # Utilities
    # ────────────────────────────────────────────────────

    @staticmethod
    def _to_gray(bgr_frame):
        """Convert BGR frame to blurred greyscale (for pixel fallback)."""
        gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (21, 21), 0)

    def _publicar_infraccion(self):
        # Publish ONLY to alerta_pub.
        # status_pub is owned exclusively by _cambiar_estado / publish_status.
        # Publishing INFRACCION to status_pub used to permanently overwrite the
        # game state (LUZ_ROJA/LUZ_VERDE/ESPERA) and the frontend would keep
        # showing "INFRACCION" forever until the next state transition.
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
        """Clean up MediaPipe resources on shutdown."""
        self._pose.close()
        super().destroy_node()


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