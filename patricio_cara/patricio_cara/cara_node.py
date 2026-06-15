import json 
#!/usr/bin/env python3
"""
cara_node.py — patricio_cara

Escucha el estado de los tres juegos y publica las emociones
correspondientes para la pantalla de caras (face_screen.html).

Tópicos suscritos:
  /patricio/pilla_pilla/status  (std_msgs/String)
  /patricio/escondite/status    (std_msgs/String)
  /patricio/calamar/status      (std_msgs/String)
  /patricio/alerta_juego        (std_msgs/String)

Tópicos publicados:
  /patricio/face_status   (std_msgs/String)  → happy | focus | alert | sad
  /patricio/game_status   (std_msgs/String)  → none | pilla_pilla | escondite | calamar
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ── Constantes de emoción ────────────────────────────────────────────────────
HAPPY = 'happy'
FOCUS = 'focus'
ALERT = 'alert'
SAD   = 'sad'

# ── Constantes de juego ──────────────────────────────────────────────────────
GAME_NONE      = 'none'
GAME_PILLA     = 'pilla_pilla'
GAME_ESCONDITE = 'escondite'
GAME_CALAMAR   = 'calamar'


class CaraNode(Node):

    def __init__(self):
        super().__init__('cara_node')

        # ── Estado interno ────────────────────────────────────────────────
        self._current_game    = GAME_NONE
        self._current_emotion = HAPPY

        # ── Publishers ────────────────────────────────────────────────────
        self._face_pub = self.create_publisher(
            String, '/patricio/face_status', 10)
        self._game_pub = self.create_publisher(
            String, '/patricio/game_status', 10)

        # ── Subscribers ───────────────────────────────────────────────────
        self.create_subscription(
            String,
            '/patricio/pilla_pilla/status',
            self._cb_pilla,
            10,
        )
        self.create_subscription(
            String,
            '/patricio/escondite/status',
            self._cb_escondite,
            10,
        )
        self.create_subscription(
            String,
            '/patricio/calamar/status',
            self._cb_calamar,
            10,
        )
        self.create_subscription(
            String,
            '/patricio/alerta_juego',
            self._cb_alerta,
            10,
        )

        # ── Heartbeat: republica el estado actual cada 2 s ────────────────
        # Así face_screen.html siempre tiene datos frescos aunque no haya
        # cambio de estado.
        self.create_timer(2.0, self._heartbeat)

        # Publicar estado inicial
        self._publish_all()

        self.get_logger().info(
            'cara_node listo.\n'
            '  Publica → /patricio/face_status, /patricio/game_status'
        )

        #---Subsripción a topico de /patricio/resultado_juego NO ESTA FUNCIONAL---
        self.create_subscription(
            String,
            '/patricio/resultado_juego',
            self._cb_resultado,
            10,
        )

    # ── Callbacks de juegos ───────────────────────────────────────────────────

    def _cb_pilla(self, msg: String) -> None:
        estado = msg.data.strip()
        if estado in ('BUSCANDO', 'SIGUIENDO'):
            self._set_state(GAME_PILLA, FOCUS)
        elif estado == 'PILLADO' or estado == '¡PILLADO!':
            self._set_state(GAME_NONE, HAPPY)
        elif estado == 'TIEMPO_AGOTADO':
            self._set_state(GAME_NONE, SAD)
        elif estado == 'ESPERA':
            if self._current_game == GAME_PILLA:
                self._set_state(GAME_NONE, HAPPY)

    def _cb_escondite(self, msg: String) -> None:
        estado = msg.data.strip()
        if '¡Te encontré!' in estado:
            self._set_state(GAME_NONE, HAPPY)
        elif 'TIEMPO_AGOTADO' in estado or 'Nadie aquí' in estado:
            self._set_state(GAME_NONE, SAD)
        elif 'detenida' in estado or 'No puedo llegar' in estado:
            if self._current_game == GAME_ESCONDITE:
                self._set_state(GAME_NONE, HAPPY)
        elif estado:
            self._set_state(GAME_ESCONDITE, FOCUS)

    def _cb_calamar(self, msg: String) -> None:
        estado = msg.data.strip()
        self.get_logger().debug(f'calamar/status: {estado}')

        if estado == 'LUZ_VERDE':
            self._set_state(GAME_CALAMAR, FOCUS)
        elif estado == 'LUZ_ROJA':
            self._set_state(GAME_CALAMAR, ALERT)
        elif estado == 'ESPERA':
            if self._current_game == GAME_CALAMAR:
                self._set_state(GAME_NONE, HAPPY)
        else:
            if self._current_game == GAME_CALAMAR:
                self._set_state(GAME_CALAMAR, FOCUS)

    def _cb_alerta(self, msg: String) -> None:
        if msg.data.strip() == 'INFRACCION':
            self.get_logger().debug('alerta_juego: INFRACCION')
            # Solo mostrar alerta si el calamar está activo
            if self._current_game == GAME_CALAMAR:
                self._publish_face(ALERT)

    #---Callback a topico de /patricio/resultado_juego NO ESTA FUNCIONAL---
    def _cb_resultado(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            resultado = data.get('resultado', '')
            if resultado == 'WIN':
                self._set_state(GAME_NONE, HAPPY)
            elif resultado == 'LOSE':
                self._set_state(GAME_NONE, SAD)
        except Exception:
            pass
    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_state(self, game: str, emotion: str) -> None:
        changed = (game != self._current_game or emotion != self._current_emotion)
        self._current_game    = game
        self._current_emotion = emotion
        if changed:
            self._publish_all()
            self.get_logger().info(
                f'Estado → juego={game}  emoción={emotion}')

    def _publish_all(self) -> None:
        self._publish_face(self._current_emotion)
        self._publish_game(self._current_game)

    def _publish_face(self, emotion: str) -> None:
        msg      = String()
        msg.data = emotion
        self._face_pub.publish(msg)

    def _publish_game(self, game: str) -> None:
        msg      = String()
        msg.data = game
        self._game_pub.publish(msg)

    def _heartbeat(self) -> None:
        self._publish_all()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = CaraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()