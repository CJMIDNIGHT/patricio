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


STATE_IDLE    = 'ESPERA'
STATE_SEARCH  = 'BUSCANDO'
STATE_FOLLOW  = 'SIGUIENDO'
STATE_CAUGHT  = 'PILLADO'
STATE_TIMEOUT = 'TIEMPO_AGOTADO'

# Resultados de partida
RESULT_WIN     = 'WIN'
RESULT_LOSE    = 'LOSE'


class VisionFollowerNode(Node):

    def __init__(self):
        super().__init__('pilla_pilla_vision_node')

        # ── Parámetros ────────────────────────────────────────────────────
        self.declare_parameter('kp_angular',           1.2)
        self.declare_parameter('kp_linear',            0.6)
        self.declare_parameter('max_angular_vel',      0.5)
        self.declare_parameter('max_linear_vel',       0.2)
        self.declare_parameter('search_angular_vel',   0.3)
        self.declare_parameter('center_threshold',     0.08)
        self.declare_parameter('catch_bbox_height',    0.60)
        self.declare_parameter('catch_confirm_sec',    0.5)
        self.declare_parameter('control_hz',           20.0)
        # Timeout global: si no pilla en este tiempo → derrota
        self.declare_parameter('game_timeout_sec',     120.0)
        # Timeout de búsqueda sin persona: vuelve a buscar (no es derrota)
        self.declare_parameter('search_timeout_sec',   30.0)

        self._kp_ang        = self.get_parameter('kp_angular').value
        self._kp_lin        = self.get_parameter('kp_linear').value
        self._max_ang       = self.get_parameter('max_angular_vel').value
        self._max_lin       = self.get_parameter('max_linear_vel').value
        self._search_ang    = self.get_parameter('search_angular_vel').value
        self._center_thr    = self.get_parameter('center_threshold').value
        self._catch_height  = self.get_parameter('catch_bbox_height').value
        self._catch_confirm = self.get_parameter('catch_confirm_sec').value
        self._control_hz    = self.get_parameter('control_hz').value
        self._game_timeout  = self.get_parameter('game_timeout_sec').value
        self._search_to     = self.get_parameter('search_timeout_sec').value

        # ── Estado ────────────────────────────────────────────────────────
        self._state       = STATE_IDLE
        self._state_lock  = threading.Lock()
        self._running     = False
        self._game_thread = None
        self._game_start_time: float | None = None

        self._detection: PersonDetection | None = None
        self._detection_lock  = threading.Lock()
        self._catch_start_time: float | None = None

        # ── Publishers ────────────────────────────────────────────────────
        self._cmd_vel_pub = self.create_publisher(Twist,  '/cmd_vel', 10)
        self._status_pub  = self.create_publisher(String, '/patricio/pilla_pilla/status', 10)

        # ── Subscribers ───────────────────────────────────────────────────
        self.create_subscription(
            PersonDetection,
            '/patricio/vision/person_detection',
            self._detection_callback, 10)

        self.create_subscription(
            String,
            '/patricio/pilla_pilla/cmd',
            self._cmd_callback, 10)

        # ── Servicio ──────────────────────────────────────────────────────
        self.create_service(StartGame, '/start_game', self._handle_start_game)

        self._publish_status(STATE_IDLE)
        self.get_logger().info('VisionFollowerNode listo.')

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _detection_callback(self, msg: PersonDetection) -> None:
        with self._detection_lock:
            self._detection = msg

    def _handle_start_game(self, request, response):
        if request.game_name != 'pilla_pilla':
            response.started = False
            return response
        with self._state_lock:
            if self._running:
                response.started = True
                return response
            self._running = True
        self._game_thread = threading.Thread(target=self._game_loop, daemon=True)
        self._game_thread.start()
        response.started = True
        return response

    def _cmd_callback(self, msg: String) -> None:
        if msg.data.strip().upper() in ('STOP', 'DETENER'):
            self._stop_game()

    # ── Bucle principal ───────────────────────────────────────────────────────

    def _game_loop(self) -> None:
        self.get_logger().info('Juego Pilla-Pilla iniciado.')
        self._set_state(STATE_SEARCH)

        self._game_start_time = time.monotonic()
        interval     = 1.0 / self._control_hz
        search_start = time.monotonic()

        while True:
            with self._state_lock:
                if not self._running:
                    break

            # ── Timeout global de partida ─────────────────────────────
            game_elapsed = time.monotonic() - self._game_start_time
            if game_elapsed >= self._game_timeout:
                self.get_logger().warn(
                    f'⏰ Timeout global ({self._game_timeout}s). '
                    'El niño ha escapado.')
                self._stop_motors()
                self._set_state(STATE_TIMEOUT)
                self._finish_game(
                    result=RESULT_LOSE,
                    reason='timeout',
                    duration=game_elapsed,
                )
                with self._state_lock:
                    self._running = False
                break

            with self._detection_lock:
                det = self._detection

            state = self._get_state()

            if state == STATE_SEARCH:
                twist = self._control_search()

                # Timeout de búsqueda sin persona → sigue girando, no es derrota
                if time.monotonic() - search_start > self._search_to:
                    self.get_logger().info(
                        f'Sin persona tras {self._search_to}s, reiniciando búsqueda.')
                    search_start = time.monotonic()

                if det is not None and det.detected:
                    self.get_logger().info('¡Persona detectada!')
                    self._set_state(STATE_FOLLOW)
                    self._catch_start_time = None

            elif state == STATE_FOLLOW:
                if det is None or not det.detected:
                    self.get_logger().info('Persona perdida. Volviendo a buscar...')
                    self._set_state(STATE_SEARCH)
                    search_start = time.monotonic()
                    twist = self._control_search()
                else:
                    twist = self._control_follow(det)

                    centered = abs(det.error_x) < self._center_thr
                    close    = det.bbox_height  > self._catch_height

                    if centered and close:
                        if self._catch_start_time is None:
                            self._catch_start_time = time.monotonic()
                        elif (time.monotonic() - self._catch_start_time
                              >= self._catch_confirm):
                            # ── VICTORIA ──────────────────────────────
                            duration = time.monotonic() - self._game_start_time
                            self._stop_motors()
                            self._set_state(STATE_CAUGHT)
                            self._finish_game(
                                result=RESULT_WIN,
                                reason='pillado',
                                duration=duration,
                            )
                            with self._state_lock:
                                self._running = False
                            break
                    else:
                        self._catch_start_time = None
            else:
                twist = Twist()

            self._cmd_vel_pub.publish(twist)
            time.sleep(interval)

        self._stop_motors()
        self.get_logger().info('Bucle de juego terminado.')

    # ── Controladores ────────────────────────────────────────────────────────

    def _control_search(self) -> Twist:
        twist = Twist()
        twist.angular.z = self._search_ang
        return twist

    def _control_follow(self, det: PersonDetection) -> Twist:
        vel_ang = -self._kp_ang * det.error_x
        vel_ang = max(-self._max_ang, min(self._max_ang, vel_ang))

        height_error = self._catch_height - det.bbox_height
        vel_lin = self._kp_lin * height_error
        vel_lin = max(-self._max_lin * 0.5, min(self._max_lin, vel_lin))

        if abs(det.error_x) > 0.20:
            vel_lin *= 0.3

        twist = Twist()
        twist.linear.x  = float(vel_lin)
        twist.angular.z = float(vel_ang)
        return twist

    # ── Resultado de partida ─────────────────────────────────────────────────

    def _finish_game(self, result: str, reason: str, duration: float) -> None:
        """
        Llamado al terminar la partida (victoria o derrota).
        Publica el resultado en el topic de status y llama a la BBDD.
        """
        resultado_texto = '¡PILLADO!' if result == RESULT_WIN else 'TIEMPO_AGOTADO'
        self._publish_status(resultado_texto)

        self.get_logger().info(
            f'Partida finalizada — resultado={result}, '
            f'motivo={reason}, duración={duration:.1f}s'
        )

        self._guardar_resultado_bbdd(
            juego='pilla_pilla',
            resultado=result,
            duracion_seg=duration,
            motivo=reason,
        )

    def _guardar_resultado_bbdd(
        self,
        juego: str,
        resultado: str,
        duracion_seg: float,
        motivo: str,
    ) -> None:
        """
        TODO: Conectar con el servicio de BBDD.
        Sustituir el contenido de esta función con la llamada real.

        Parámetros disponibles:
          juego        : 'pilla_pilla'
          resultado    : 'WIN' | 'LOSE'
          duracion_seg : duración de la partida en segundos
          motivo       : 'pillado' | 'timeout'
        """
        self.get_logger().info(
            f'[BBDD] TODO: guardar resultado '
            f'juego={juego}, resultado={resultado}, '
            f'duracion={duracion_seg:.1f}s, motivo={motivo}'
        )
        # ── INSERTAR AQUÍ LA LLAMADA A LA BBDD ──────────────────────────────
        # Ejemplo si es API REST:
        #   import requests
        #   requests.post('http://localhost:XXXX/api/resultado', json={
        #       'juego': juego,
        #       'resultado': resultado,
        #       'duracion': duracion_seg,
        #       'motivo': motivo,
        #   })
        #
        # Ejemplo si es servicio ROS2:
        #   client = self.create_client(TuServicio, '/tu_servicio_bbdd')
        #   req = TuServicio.Request()
        #   req.juego = juego
        #   ...
        #   client.call_async(req)
        # ────────────────────────────────────────────────────────────────────

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _stop_game(self) -> None:
        with self._state_lock:
            self._running = False
        self._stop_motors()
        self._set_state(STATE_IDLE)

    def _stop_motors(self) -> None:
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

    def destroy_node(self) -> None:
        self._stop_motors()
        super().destroy_node()


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