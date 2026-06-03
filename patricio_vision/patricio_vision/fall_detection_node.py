#!/usr/bin/env python3
"""
deteccion_caidas_node.py  —  patricio_vision

Nodo de detección de caídas del niño mediante análisis geométrico
y cinemático de los landmarks de MediaPipe Pose.

Arquitectura:
  - Consume /patricio/vision/pose_landmarks  (PoseResult)
  - Publica  /patricio/vision/fall_detected  (FallEvent)
  - Llama al servicio de BBDD para registrar la alerta (Tarea 1)
  - Publica notificación en tiempo real a la web via topic

Algoritmo de detección (multi-criterio, umbral configurable):
  1. ALTURA DEL CENTRO DE MASA
       Si el CoM (promedio ponderado de hombros + caderas) cae
       por debajo de `fall_hip_height_threshold` (normalizado 0–1,
       siendo 1 la parte inferior del frame), se suma 1 al score.

  2. INCLINACIÓN DEL TORSO
       El ángulo entre la línea hombros y la horizontal.
       Si |ángulo| > `fall_torso_angle_threshold` grados, +1 al score.

  3. VELOCIDAD DE DESCENSO DEL CoM
       Si la velocidad vertical del CoM (pixeles/s normalizados)
       supera `fall_velocity_threshold`, +1 al score.

  4. RELACIÓN ANCHURA/ALTURA DEL BOUNDING BOX
       Una persona tumbada tiene bbox más ancho que alto.
       Si ratio > `fall_bbox_ratio_threshold`, +1 al score.

  Se confirma caída cuando score >= `fall_min_criteria` (por defecto 2/4).
  Para evitar falsos positivos, la caída se confirma solo si el estado
  persiste durante `fall_confirm_frames` frames consecutivos.

Integración con BBDD (Tarea 1):
  - Servicio: /patricio/db/register_alert  (RegisterAlert.srv)
  - Topic web: /patricio/web/notification  (WebNotification.msg)

Compatibilidad: ROS 2 Jazzy · MediaPipe 0.10.13 · Python 3.10+
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import Header, String
from builtin_interfaces.msg import Time

from patricio_interfaces.msg import PoseResult, FallEvent
# from patricio_interfaces.srv import RegisterAlert   # ← descomentar cuando exista
# from patricio_interfaces.msg import WebNotification  # ← descomentar cuando exista


# ── Índices de landmarks MediaPipe Pose ─────────────────────────────────────
# Referencia: https://developers.google.com/mediapipe/solutions/vision/pose_landmarker
LM_NOSE          = 0
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER= 12
LM_LEFT_HIP      = 23
LM_RIGHT_HIP     = 24
LM_LEFT_KNEE     = 25
LM_RIGHT_KNEE    = 26
LM_LEFT_ANKLE    = 27
LM_RIGHT_ANKLE   = 28

# Landmarks mínimos necesarios para el análisis (deben estar visibles)
REQUIRED_LANDMARKS = [
    LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER,
    LM_LEFT_HIP,      LM_RIGHT_HIP,
]

# Umbral de visibilidad mínima por landmark
MIN_VISIBILITY = 0.4


@dataclass
class PoseSnapshot:
    """Captura instantánea del estado de pose en un frame."""
    timestamp: float              # time.monotonic()
    com_y: float                  # Centro de masa Y normalizado (0=arriba, 1=abajo)
    com_x: float                  # Centro de masa X normalizado
    torso_angle: float            # Ángulo del torso en grados (0=vertical)
    bbox_ratio: float             # anchura_bbox / altura_bbox
    hip_y: float                  # Altura media de caderas normalizada
    shoulder_y: float             # Altura media de hombros normalizada
    criteria_hit: int = 0         # Score de criterios satisfechos en este frame
    fall_confirmed: bool = False  # True si se confirmó caída en este frame


@dataclass
class FallState:
    """Estado del detector de caídas."""
    consecutive_fall_frames: int = 0
    fall_active: bool = False        # True mientras dura el evento de caída
    fall_start_time: float = 0.0     # Cuándo comenzó la caída confirmada
    last_alert_time: float = 0.0     # Para anti-flood de alertas
    alert_cooldown: float = 10.0     # Segundos mínimos entre alertas


class FallDetectionNode(Node):
    """
    Nodo ROS2 de detección de caídas basado en análisis de pose MediaPipe.

    Suscripciones:
      /patricio/vision/pose_landmarks  (patricio_interfaces/PoseResult)

    Publicaciones:
      /patricio/vision/fall_detected   (patricio_interfaces/FallEvent)
      /patricio/web/notification       (std_msgs/String — JSON)

    Servicios llamados:
      /patricio/db/register_alert      (patricio_interfaces/RegisterAlert)
    """

    def __init__(self):
        super().__init__('fall_detection_node')

        # ── Parámetros configurables ──────────────────────────────────────
        self.declare_parameter('fall_hip_height_threshold',  0.55)
        # Y normalizado (0=arriba). Si cadera > este valor → persona baja.

        self.declare_parameter('fall_torso_angle_threshold', 45.0)
        # Grados. Si |ángulo torso-horizontal| > este valor → persona inclinada.

        self.declare_parameter('fall_velocity_threshold',    0.08)
        # Velocidad de descenso del CoM (unidades normalizadas/s).

        self.declare_parameter('fall_bbox_ratio_threshold',  1.5)
        # anchura/altura. > 1.5 → persona tumbada horizontalmente.

        self.declare_parameter('fall_min_criteria',          2)
        # Mínimo de criterios para activar contador de frames.

        self.declare_parameter('fall_confirm_frames',        3)
        # Frames consecutivos antes de confirmar la caída.

        self.declare_parameter('alert_cooldown',             10.0)
        # Segundos entre alertas para evitar spam.

        self.declare_parameter('history_size',               30)
        # Frames de historial para análisis de velocidad.

        # Leer parámetros
        self._hip_thr      = self.get_parameter('fall_hip_height_threshold').value
        self._angle_thr    = self.get_parameter('fall_torso_angle_threshold').value
        self._vel_thr      = self.get_parameter('fall_velocity_threshold').value
        self._bbox_thr     = self.get_parameter('fall_bbox_ratio_threshold').value
        self._min_criteria = self.get_parameter('fall_min_criteria').value
        self._confirm_frm  = self.get_parameter('fall_confirm_frames').value
        self._cooldown     = self.get_parameter('alert_cooldown').value
        history_size       = self.get_parameter('history_size').value

        self.get_logger().info(
            f'FallDetectionNode iniciado con parámetros:\n'
            f'  hip_height_thr   = {self._hip_thr}\n'
            f'  torso_angle_thr  = {self._angle_thr}°\n'
            f'  velocity_thr     = {self._vel_thr}\n'
            f'  bbox_ratio_thr   = {self._bbox_thr}\n'
            f'  min_criteria     = {self._min_criteria}/4\n'
            f'  confirm_frames   = {self._confirm_frm}\n'
            f'  alert_cooldown   = {self._cooldown}s'
        )

        # ── Estado interno ────────────────────────────────────────────────
        self._history: deque[PoseSnapshot] = deque(maxlen=history_size)
        self._fall_state = FallState(alert_cooldown=self._cooldown)
        self._cb_group = ReentrantCallbackGroup()

        # ── Publishers ────────────────────────────────────────────────────
        self._pub_fall = self.create_publisher(
            FallEvent,
            '/patricio/vision/fall_detected',
            10,
        )
        # Topic de notificación web (JSON serializado en String)
        self._pub_web = self.create_publisher(
            String,
            '/patricio/web/notification',
            10,
        )

        # ── Subscriber de landmarks ───────────────────────────────────────
        self.create_subscription(
            PoseResult,
            '/patricio/vision/pose_landmarks',
            self._pose_callback,
            10,
            callback_group=self._cb_group,
        )

        # ── Cliente del servicio BBDD (Tarea 1) ───────────────────────────
        # Se inicializa de forma diferida para no bloquear el arranque.
        self._db_client = None
        self._db_timer = self.create_timer(
            2.0, self._try_connect_db, callback_group=self._cb_group
        )

        self.get_logger().info(
            'FallDetectionNode listo.\n'
            '  Entrada : /patricio/vision/pose_landmarks\n'
            '  Salida  : /patricio/vision/fall_detected\n'
            '  Web     : /patricio/web/notification\n'
            '  BBDD    : /patricio/db/register_alert (pendiente conexión)'
        )

    # ── Conexión diferida al servicio BBDD ──────────────────────────────────

    def _try_connect_db(self):
        """
        Intenta conectar al servicio de BBDD. Cuando lo logra, cancela el timer.
        Así el nodo arranca aunque la BBDD no esté disponible inmediatamente.
        """
        # TODO: Descomentar cuando patricio_interfaces/RegisterAlert esté definido
        # from patricio_interfaces.srv import RegisterAlert
        # if not self._db_client:
        #     self._db_client = self.create_client(
        #         RegisterAlert, '/patricio/db/register_alert',
        #         callback_group=self._cb_group,
        #     )
        # if self._db_client.service_is_ready():
        #     self._db_timer.cancel()
        #     self.get_logger().info('✅ Conectado al servicio BBDD /patricio/db/register_alert')
        # else:
        #     self.get_logger().warn('⏳ Esperando servicio BBDD /patricio/db/register_alert...')
        pass  # Eliminar cuando se descomente el bloque anterior

    # ── Callback principal ───────────────────────────────────────────────────

    def _pose_callback(self, msg: PoseResult) -> None:
        """
        Procesa cada mensaje de pose y actualiza el estado del detector.
        """
        # Sin persona → resetear contador de caída progresivamente
        if not msg.detected:
            self._handle_no_detection()
            return

        # Verificar que los landmarks necesarios estén visibles
        if not self._landmarks_visible(msg):
            self._handle_no_detection()
            return

        # ── Extraer métricas de pose ──────────────────────────────────
        snapshot = self._extract_pose_metrics(msg)

        # ── Evaluar criterios de caída ────────────────────────────────
        snapshot.criteria_hit = self._evaluate_criteria(snapshot)

        # ── Actualizar máquina de estados ─────────────────────────────
        self._update_fall_state(snapshot, msg.header)

        # Guardar en historial
        self._history.append(snapshot)

    # ── Sin detección ────────────────────────────────────────────────────────

    def _handle_no_detection(self):
        """
        Si no hay persona visible, decrementamos el contador de frames
        de caída para evitar que una oclusión momentánea dispare la alerta.
        """
        if self._fall_state.consecutive_fall_frames > 0:
            self._fall_state.consecutive_fall_frames -= 1

        # Si ya no hay persona y la caída estaba activa, finalizarla
        if self._fall_state.fall_active:
            duration = time.monotonic() - self._fall_state.fall_start_time
            if duration > 5.0:  # Si lleva >5s sin detectarse, asumir que se levantó
                self._fall_state.fall_active = False
                self.get_logger().info('✅ Caída finalizada (persona no detectada).')

    # ── Validación de visibilidad ────────────────────────────────────────────

    def _landmarks_visible(self, msg: PoseResult) -> bool:
        """
        Comprueba que los landmarks mínimos necesarios estén suficientemente visibles.
        """
        if len(msg.landmarks_visibility) < max(REQUIRED_LANDMARKS) + 1:
            return False
        return all(
            msg.landmarks_visibility[i] >= MIN_VISIBILITY
            for i in REQUIRED_LANDMARKS
        )

    # ── Extracción de métricas ───────────────────────────────────────────────

    def _extract_pose_metrics(self, msg: PoseResult) -> PoseSnapshot:
        """
        Calcula todas las métricas geométricas necesarias para el análisis.
        """
        x  = msg.landmarks_x
        y  = msg.landmarks_y
        # vis = msg.landmarks_visibility  # disponible si se necesita ponderación

        # Puntos clave
        ls_x, ls_y = x[LM_LEFT_SHOULDER],  y[LM_LEFT_SHOULDER]
        rs_x, rs_y = x[LM_RIGHT_SHOULDER], y[LM_RIGHT_SHOULDER]
        lh_x, lh_y = x[LM_LEFT_HIP],       y[LM_LEFT_HIP]
        rh_x, rh_y = x[LM_RIGHT_HIP],      y[LM_RIGHT_HIP]

        # Centro de hombros y caderas
        shoulder_mid_x = (ls_x + rs_x) / 2.0
        shoulder_mid_y = (ls_y + rs_y) / 2.0
        hip_mid_x      = (lh_x + rh_x) / 2.0
        hip_mid_y      = (lh_y + rh_y) / 2.0

        # Centro de masa (promedio hombros + caderas, ponderado igualmente)
        com_x = (shoulder_mid_x + hip_mid_x) / 2.0
        com_y = (shoulder_mid_y + hip_mid_y) / 2.0

        # Ángulo del torso respecto a la vertical
        # Vector de caderas a hombros
        vec_x = shoulder_mid_x - hip_mid_x
        vec_y = shoulder_mid_y - hip_mid_y
        # Ángulo con la vertical (0 = completamente erguido)
        torso_angle_rad = math.atan2(abs(vec_x), abs(vec_y) + 1e-9)
        torso_angle_deg = math.degrees(torso_angle_rad)

        # Bounding box de todos los landmarks con visibilidad suficiente
        visible_x = [x[i] for i in range(len(x))
                     if i < len(msg.landmarks_visibility)
                     and msg.landmarks_visibility[i] >= MIN_VISIBILITY]
        visible_y = [y[i] for i in range(len(y))
                     if i < len(msg.landmarks_visibility)
                     and msg.landmarks_visibility[i] >= MIN_VISIBILITY]

        if visible_x and visible_y:
            bbox_w = max(visible_x) - min(visible_x)
            bbox_h = max(visible_y) - min(visible_y)
            bbox_ratio = bbox_w / (bbox_h + 1e-9)
        else:
            bbox_ratio = 1.0

        return PoseSnapshot(
            timestamp    = time.monotonic(),
            com_y        = com_y,
            com_x        = com_x,
            torso_angle  = torso_angle_deg,
            bbox_ratio   = bbox_ratio,
            hip_y        = hip_mid_y,
            shoulder_y   = shoulder_mid_y,
        )

    # ── Evaluación de criterios ──────────────────────────────────────────────

    def _evaluate_criteria(self, snap: PoseSnapshot) -> int:
        """
        Evalúa los 4 criterios de caída y devuelve el score (0–4).
        """
        score = 0

        # ── Criterio 1: Altura de la cadera ──────────────────────────
        # Si la cadera está en la mitad inferior del frame (y alto = > thr)
        if snap.hip_y > self._hip_thr:
            score += 1
            self.get_logger().debug(
                f'  [C1] Cadera baja: hip_y={snap.hip_y:.3f} > {self._hip_thr}'
            )

        # ── Criterio 2: Ángulo del torso ─────────────────────────────
        # Si el torso está muy inclinado respecto a la vertical
        if snap.torso_angle > self._angle_thr:
            score += 1
            self.get_logger().debug(
                f'  [C2] Torso inclinado: {snap.torso_angle:.1f}° > {self._angle_thr}°'
            )

        # ── Criterio 3: Velocidad de descenso del CoM ─────────────────
        velocity = self._compute_com_velocity()
        if velocity > self._vel_thr:
            score += 1
            self.get_logger().debug(
                f'  [C3] Descenso rápido: vel={velocity:.4f} > {self._vel_thr}'
            )

        # ── Criterio 4: Ratio bounding box ────────────────────────────
        if snap.bbox_ratio > self._bbox_thr:
            score += 1
            self.get_logger().debug(
                f'  [C4] BBox horizontal: ratio={snap.bbox_ratio:.2f} > {self._bbox_thr}'
            )

        return score

    def _compute_com_velocity(self) -> float:
        """
        Calcula la velocidad media de descenso del CoM en los últimos frames.
        Devuelve 0.0 si no hay suficiente historial.
        """
        if len(self._history) < 2:
            return 0.0

        # Tomar los últimos 5 frames para la ventana de velocidad
        window = list(self._history)[-5:]

        total_velocity = 0.0
        count = 0
        for i in range(1, len(window)):
            dt = window[i].timestamp - window[i-1].timestamp
            if dt <= 0:
                continue
            # dy positivo = descenso (en coordenadas imagen, Y crece hacia abajo)
            dy = window[i].com_y - window[i-1].com_y
            velocity = dy / dt  # unidades_normalizadas / segundo
            if velocity > 0:  # Solo descenso, no subida
                total_velocity += velocity
                count += 1

        return total_velocity / count if count > 0 else 0.0

    # ── Máquina de estados ───────────────────────────────────────────────────

    def _update_fall_state(self, snap: PoseSnapshot, header: Header) -> None:
        """
        Actualiza el estado del detector basado en el score del frame actual.
        Implementa confirmación por frames consecutivos para evitar falsos positivos.
        """
        is_fall_candidate = snap.criteria_hit >= self._min_criteria

        if is_fall_candidate:
            self._fall_state.consecutive_fall_frames += 1
        else:
            # Decrementar suavemente para tolerar frames ruidosos ocasionales
            self._fall_state.consecutive_fall_frames = max(
                0, self._fall_state.consecutive_fall_frames - 1
            )

        self.get_logger().debug(
            f'Score={snap.criteria_hit}/4  '
            f'consecutive={self._fall_state.consecutive_fall_frames}/'
            f'{self._confirm_frm}  '
            f'fall_active={self._fall_state.fall_active}'
        )

        # ── Confirmación de caída ──────────────────────────────────────
        if (self._fall_state.consecutive_fall_frames >= self._confirm_frm
                and not self._fall_state.fall_active):

            # Nueva caída confirmada
            self._fall_state.fall_active    = True
            self._fall_state.fall_start_time = time.monotonic()
            snap.fall_confirmed = True

            self.get_logger().warn(
                f'🚨 CAÍDA CONFIRMADA '
                f'(score={snap.criteria_hit}/4, '
                f'hip_y={snap.hip_y:.2f}, '
                f'torso={snap.torso_angle:.1f}°, '
                f'bbox={snap.bbox_ratio:.2f})'
            )

            self._publish_fall_event(snap, header)
            self._trigger_alert(snap)

        # ── Fin de caída ───────────────────────────────────────────────
        elif (self._fall_state.fall_active
              and self._fall_state.consecutive_fall_frames == 0):

            duration = time.monotonic() - self._fall_state.fall_start_time
            self._fall_state.fall_active = False
            self.get_logger().info(
                f'✅ Persona recuperada tras {duration:.1f}s de caída.'
            )

    # ── Publicar FallEvent ───────────────────────────────────────────────────

    def _publish_fall_event(self, snap: PoseSnapshot, header: Header) -> None:
        """
        Publica el evento de caída en /patricio/vision/fall_detected.
        """
        msg = FallEvent()
        msg.header          = header
        msg.detected        = True
        msg.criteria_score  = snap.criteria_hit
        msg.com_y           = snap.com_y
        msg.torso_angle_deg = snap.torso_angle
        msg.bbox_ratio      = snap.bbox_ratio
        msg.hip_y           = snap.hip_y
        self._pub_fall.publish(msg)

    # ── Disparador de alerta (BBDD + Web) ───────────────────────────────────

    def _trigger_alert(self, snap: PoseSnapshot) -> None:
        """
        Invoca el servicio de BBDD y publica notificación web.
        Respeta el cooldown para evitar spam de alertas.
        """
        now = time.monotonic()
        if now - self._fall_state.last_alert_time < self._cooldown:
            self.get_logger().debug('Alert skipped (cooldown activo)')
            return

        self._fall_state.last_alert_time = now

        # ── 1. Registrar en BBDD (Tarea 1) ────────────────────────────
        self._call_db_service(snap)

        # ── 2. Notificar a la web (JSON via String) ────────────────────
        import json
        notification = {
            'type':      'FALL_DETECTED',
            'severity':  'CRITICAL',
            'timestamp': time.time(),
            'data': {
                'criteria_score': snap.criteria_hit,
                'hip_y':          round(snap.hip_y, 4),
                'torso_angle':    round(snap.torso_angle, 2),
                'bbox_ratio':     round(snap.bbox_ratio, 3),
                'com_y':          round(snap.com_y, 4),
            },
            'message': (
                f'⚠️ Caída detectada: score={snap.criteria_hit}/4, '
                f'cadera_y={snap.hip_y:.2f}, '
                f'ángulo_torso={snap.torso_angle:.1f}°'
            )
        }

        web_msg = String()
        web_msg.data = json.dumps(notification, ensure_ascii=False)
        self._pub_web.publish(web_msg)

        self.get_logger().warn(
            f'📡 Notificación enviada a /patricio/web/notification'
        )

    def _call_db_service(self, snap: PoseSnapshot) -> None:
        """
        Llama al servicio de BBDD para registrar la alerta.
        El bloque está preparado para activarse cuando Tarea 1 esté disponible.
        """
        # TODO: Descomentar cuando patricio_interfaces/RegisterAlert esté definido
        # if self._db_client is None or not self._db_client.service_is_ready():
        #     self.get_logger().warn('⚠️ Servicio BBDD no disponible. Alerta no registrada.')
        #     return
        #
        # request = RegisterAlert.Request()
        # request.alert_type    = 'FALL_DETECTED'
        # request.severity      = 'CRITICAL'
        # request.description   = (
        #     f'Caída detectada: score={snap.criteria_hit}/4, '
        #     f'cadera_y={snap.hip_y:.3f}, '
        #     f'ángulo_torso={snap.torso_angle:.1f}°, '
        #     f'bbox_ratio={snap.bbox_ratio:.3f}'
        # )
        # request.timestamp     = self.get_clock().now().to_msg()
        # request.extra_data    = json.dumps({
        #     'hip_y':          snap.hip_y,
        #     'torso_angle':    snap.torso_angle,
        #     'bbox_ratio':     snap.bbox_ratio,
        #     'criteria_score': snap.criteria_hit,
        # })
        #
        # future = self._db_client.call_async(request)
        # future.add_done_callback(self._db_response_callback)

        self.get_logger().warn(
            '⚠️ [STUB] Servicio BBDD no conectado todavía. '
            'Descomentar _call_db_service cuando Tarea 1 esté disponible.'
        )

    def _db_response_callback(self, future) -> None:
        """
        Callback asíncrono de la respuesta del servicio BBDD.
        """
        try:
            response = future.result()
            if response.success:
                self.get_logger().info(
                    f'✅ Alerta registrada en BBDD. ID: {response.alert_id}'
                )
            else:
                self.get_logger().error(
                    f'❌ Error al registrar alerta: {response.message}'
                )
        except Exception as e:
            self.get_logger().error(f'❌ Excepción al llamar BBDD: {e}')

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def destroy_node(self) -> None:
        super().destroy_node()
        self.get_logger().info('FallDetectionNode destruido.')


# ── Entry point ──────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = FallDetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()