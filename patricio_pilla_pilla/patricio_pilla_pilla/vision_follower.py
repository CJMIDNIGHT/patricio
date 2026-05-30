#!/usr/bin/env python3
"""
vision_follower.py  —  patricio_pilla_pilla

Nodo de seguimiento visual para el juego Pilla-Pilla.

Sustituye la lógica de waypoints fijos por seguimiento reactivo
basado en los datos de MediaPipe publicados por patricio_vision.

Arquitectura:
  - Suscribe a /patricio/vision/person_detection  (PersonDetection)
  - Publica velocidades en /cmd_vel               (Twist)
  - Publica estado en /patricio/pilla_pilla/status (String)
  - Expone servicio /start_game                   (StartGame)
  - Acepta comandos en /patricio/pilla_pilla/cmd  (String)

Fases del juego:
  BUSCAR   → No hay persona. El robot gira despacio hasta detectarla.
  SEGUIR   → Persona detectada. Control proporcional: error_x → angular,
             bbox_height → lineal (para cuando está suficientemente cerca).
  PILLADO  → Persona centrada y cerca. Publica éxito y termina.
  ESPERA   → Juego parado.

Control proporcional (P):
  vel_angular = -Kp_angular * error_x
    error_x ∈ [-0.5, 0.5]: negativo = persona a la izquierda → girar izquierda
  vel_lineal  =  Kp_lineal * (bbox_height_target - bbox_height_actual)
    Si bbox_height_actual > bbox_height_target → persona cerca → parar/retroceder
    Si bbox_height_actual < bbox_height_target → persona lejos → avanzar

Todos los umbrales son parámetros ROS2 ajustables en caliente vía
  ros2 param set /pilla_pilla_vision_node <param> <valor>
"""

import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String

from patricio_interfaces.msg import PersonDetection
from patricio_interfaces.srv import StartGame


# ── Estados internos ─────────────────────────────────────────────────────────
STATE_IDLE    = 'ESPERA'
STATE_SEARCH  = 'BUSCANDO'
STATE_FOLLOW  = 'SIGUIENDO'
STATE_CAUGHT  = 'PILLADO'


class VisionFollowerNode(Node):
    """
    Nodo de seguimiento visual para Pilla-Pilla.

    Consume /patricio/vision/person_detection y genera comandos
    de velocidad directos en /cmd_vel mediante control proporcional.
    """

    def __init__(self):
        super().__init__('pilla_pilla_vision_node')

        # ── Parámetros ────────────────────────────────────────────────────
        # Control proporcional
        self.declare_parameter('kp_angular',          1.2)
        self.declare_parameter('kp_linear',           0.6)

        # Velocidades máximas (seguridad)
        self.declare_parameter('max_angular_vel',     0.5)   # rad/s
        self.declare_parameter('max_linear_vel',      0.2)   # m/s

        # Velocidad de búsqueda (giro cuando no hay persona)
        self.declare_parameter('search_angular_vel',  0.3)   # rad/s

        # Umbral de centrado: error_x < este valor → persona "centrada"
        self.declare_parameter('center_threshold',    0.08)  # fracción del frame

        # bbox_height objetivo: cuando la persona ocupa este % del frame
        # en altura → está suficientemente cerca → pillado
        # 0.6 = persona ocupa el 60% de la altura del frame
        self.declare_parameter('catch_bbox_height',   0.60)

        # Timeout de búsqueda: si no encuentra persona en N segundos → para
        self.declare_parameter('search_timeout_sec',  30.0)

        # Frecuencia del bucle de control (Hz)
        self.declare_parameter('control_hz',          20.0)

        # Tiempo que la persona debe estar "pillada" continuamente (segundos)
        # Evita falsos positivos por un frame puntual
        self.declare_parameter('catch_confirm_sec',   0.5)

        self._kp_ang        = self.get_parameter('kp_angular').value
        self._kp_lin        = self.get_parameter('kp_linear').value
        self._max_ang       = self.get_parameter('max_angular_vel').value
        self._max_lin       = self.get_parameter('max_linear_vel').value
        self._search_ang    = self.get_parameter('search_angular_vel').value
        self._center_thr    = self.get_parameter('center_threshold').value
        self._catch_height  = self.get_parameter('catch_bbox_height').value
        self._search_to     = self.get_parameter('search_timeout_sec').value
        self._control_hz    = self.get_parameter('control_hz').value
        self._catch_confirm = self.get_parameter('catch_confirm_sec').value

        # ── Estado interno ────────────────────────────────────────────────
        self._state       = STATE_IDLE
        self._state_lock  = threading.Lock()
        self._running     = False
        self._game_thread = None

        # Último dato de detección recibido
        self._detection: PersonDetection | None = None
        self._detection_lock = threading.Lock()
        self._detection_event = threading.Event()

        # Contador de confirmación de pillado
        self._catch_start_time: float | None = None

        # ── Publishers ────────────────────────────────────────────────────
        self._cmd_vel_pub = self.create_publisher(
            Twist, '/cmd_vel', 10)

        self._status_pub = self.create_publisher(
            String, '/patricio/pilla_pilla/status', 10)

        # ── Subscribers ───────────────────────────────────────────────────
        self.create_subscription(
            PersonDetection,
            '/patricio/vision/person_detection',
            self._detection_callback,
            10,
        )

        self.create_subscription(
            String,
            '/patricio/pilla_pilla/cmd',
            self._cmd_callback,
            10,
        )

        # ── Servicio ──────────────────────────────────────────────────────
        self.create_service(
            StartGame,
            '/start_game',
            self._handle_start_game,
        )

        self._publish_status(STATE_IDLE)
        self.get_logger().info(
            'VisionFollowerNode listo.\n'
            '  Detección : /patricio/vision/person_detection\n'
            '  Velocidad : /cmd_vel\n'
            '  Servicio  : /start_game\n'
            '  Comandos  : /patricio/pilla_pilla/cmd'
        )

    # ── Callback de detección ────────────────────────────────────────────────

    def _detection_callback(self, msg: PersonDetection) -> None:
        """Guarda el último resultado de MediaPipe. Ligero, no bloquea."""
        with self._detection_lock:
            self._detection = msg
        self._detection_event.set()

    # ── Servicio StartGame ───────────────────────────────────────────────────

    def _handle_start_game(
        self,
        request: StartGame.Request,
        response: StartGame.Response,
    ) -> StartGame.Response:

        if request.game_name != 'pilla_pilla':
            response.started = False
            return response

        with self._state_lock:
            if self._running:
                self.get_logger().info('Juego ya en marcha.')
                response.started = True
                return response

            self._running = True

        self._game_thread = threading.Thread(
            target=self._game_loop, daemon=True)
        self._game_thread.start()

        response.started = True
        return response

    # ── Callback de comandos ─────────────────────────────────────────────────

    def _cmd_callback(self, msg: String) -> None:
        cmd = msg.data.strip().upper()
        if cmd in ('STOP', 'DETENER'):
            self.get_logger().info('STOP recibido.')
            self._stop_game()

    # ── Bucle principal del juego ────────────────────────────────────────────

    def _game_loop(self) -> None:
        """
        Bucle de control reactivo. Corre en su propio hilo.

        Ciclo:
          1. Leer último PersonDetection.
          2. Según el estado actual, calcular Twist.
          3. Publicar Twist.
          4. Dormir para mantener control_hz.
        """
        self.get_logger().info('Juego Pilla-Pilla iniciado.')
        self._set_state(STATE_SEARCH)

        interval      = 1.0 / self._control_hz
        search_start  = time.monotonic()

        while True:
            with self._state_lock:
                if not self._running:
                    break

            # ── Leer detección más reciente ───────────────────────────
            with self._detection_lock:
                det = self._detection

            state = self._get_state()

            # ── Máquina de estados ────────────────────────────────────
            if state == STATE_SEARCH:
                twist = self._control_search()

                # Timeout de búsqueda
                if time.monotonic() - search_start > self._search_to:
                    self.get_logger().warn(
                        f'Búsqueda sin éxito tras {self._search_to}s. Parando.')
                    self._stop_game()
                    break

                # Transición SEARCH → FOLLOW si hay persona
                if det is not None and det.detected:
                    self.get_logger().info('¡Persona detectada! Iniciando seguimiento.')
                    self._set_state(STATE_FOLLOW)
                    self._catch_start_time = None

            elif state == STATE_FOLLOW:
                if det is None or not det.detected:
                    # Persona perdida → volver a buscar
                    self.get_logger().info('Persona perdida. Volviendo a buscar...')
                    self._set_state(STATE_SEARCH)
                    search_start = time.monotonic()
                    twist = self._control_search()
                else:
                    twist = self._control_follow(det)

                    # ── Condición de pillado ──────────────────────────
                    # La persona está centrada Y ocupa suficiente altura
                    centered = abs(det.error_x) < self._center_thr
                    close    = det.bbox_height  > self._catch_height

                    if centered and close:
                        if self._catch_start_time is None:
                            self._catch_start_time = time.monotonic()
                        elif (time.monotonic() - self._catch_start_time
                              >= self._catch_confirm):
                            # ¡Pillado confirmado!
                            self._stop_motors()
                            self._set_state(STATE_CAUGHT)
                            self._publish_status(STATE_CAUGHT)
                            self.get_logger().info('¡¡PILLADO!!')
                            with self._state_lock:
                                self._running = False
                            break
                    else:
                        # Resetear contador si deja de cumplirse
                        self._catch_start_time = None

            else:
                # Estado inesperado — parar
                twist = Twist()

            # ── Publicar velocidad ────────────────────────────────────
            self._cmd_vel_pub.publish(twist)
            time.sleep(interval)

        # Fin del bucle — asegurar parada total
        self._stop_motors()
        self.get_logger().info('Bucle de juego terminado.')

    # ── Controladores ────────────────────────────────────────────────────────

    def _control_search(self) -> Twist:
        """
        Fase BUSCAR: gira en su sitio hasta encontrar a alguien.
        Sin traslación para no salirse del mapa.
        """
        twist = Twist()
        twist.angular.z = self._search_ang   # gira hacia la izquierda
        return twist

    def _control_follow(self, det: PersonDetection) -> Twist:
        """
        Fase SEGUIR: control proporcional sobre error_x y bbox_height.

        Angular: corrige el centrado horizontal.
          vel_ang = -Kp_ang * error_x
          error_x > 0 → persona a la derecha → girar derecha (negativo en ROS)

        Lineal: se acerca si la persona es pequeña, para si es grande.
          vel_lin = Kp_lin * (catch_height - bbox_height)
          Si bbox_height < catch_height → avanzar
          Si bbox_height > catch_height → retroceder levemente (anti-colisión)
        """
        # ── Angular ──────────────────────────────────────────────────
        vel_ang = -self._kp_ang * det.error_x
        vel_ang = max(-self._max_ang, min(self._max_ang, vel_ang))

        # ── Lineal ───────────────────────────────────────────────────
        height_error = self._catch_height - det.bbox_height
        vel_lin = self._kp_lin * height_error
        vel_lin = max(-self._max_lin * 0.5,   # retroceso máximo = 50% del máximo
                      min(self._max_lin, vel_lin))

        # Si el error angular es muy grande, priorizar giro sobre avance
        # (no avanzar en diagonal hacia la persona)
        if abs(det.error_x) > 0.20:
            vel_lin *= 0.3   # reducir avance un 70% mientras centra

        twist = Twist()
        twist.linear.x  = float(vel_lin)
        twist.angular.z = float(vel_ang)

        self.get_logger().debug(
            f'FOLLOW → error_x={det.error_x:.3f} '
            f'bbox_h={det.bbox_height:.3f} '
            f'lin={vel_lin:.3f} ang={vel_ang:.3f}'
        )

        return twist

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _stop_game(self) -> None:
        """Detiene el juego limpiamente desde cualquier estado."""
        with self._state_lock:
            self._running = False
        self._stop_motors()
        self._set_state(STATE_IDLE)
        self._publish_status(STATE_IDLE)
        self.get_logger().info('Juego detenido.')

    def _stop_motors(self) -> None:
        """Publica Twist cero para detener el robot inmediatamente."""
        self._cmd_vel_pub.publish(Twist())

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state
        self._publish_status(state)
        self.get_logger().info(f'Estado → {state}')

    def _get_state(self) -> str:
        with self._state_lock:
            return self._state

    def _publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self._status_pub.publish(msg)

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def destroy_node(self) -> None:
        self._stop_motors()
        super().destroy_node()


# ── Entry point ──────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = VisionFollowerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()