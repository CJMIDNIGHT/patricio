#!/usr/bin/env python3
"""
escondite_service.py
Nodo ROS2 que expone el servicio del escondite hacia rosbridge.

Responsabilidades de este archivo:
  - Crear el nodo ROS2 y el executor
  - Registrar el servidor de servicio /patricio/escondite/iniciar
  - Registrar la subscripción /patricio/escondite/control (STOP en caliente)
  - Publicar en /patricio/escondite/status
  - Delegar TODA la lógica del juego en EsconditoLogic

No contiene lógica de navegación ni de selección de poses.
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from nav2_simple_commander.robot_navigator import BasicNavigator
from std_msgs.msg import String

from patricio_interfaces.srv import IniciarEscondite
from .escondite import EsconditoLogic


class EsconditoServiceNode(Node):

    def __init__(self):
        super().__init__("escondite_service_node")

        # ── Callback group reentrant ─────────────────────────────────────────
        # Necesario para que el handler del servicio y la sub. de STOP
        # puedan ejecutarse en paralelo sin bloquearse.
        self._cb_group = ReentrantCallbackGroup()

        # ── Nav2 ─────────────────────────────────────────────────────────────
        self._navigator = BasicNavigator()
        self._navigator.waitUntilNav2Active()  # ← añade esta línea


        # ── Publicador de estado ─────────────────────────────────────────────
        self._pub_status = self.create_publisher(
            String,
            "/patricio/escondite/status",
            10,
        )

        # ── Lógica del juego ─────────────────────────────────────────────────
        # EsconditoLogic recibe el navigator, una función para obtener
        # el timestamp actual y el callback de publicación de estado.
        self._logic = EsconditoLogic(
            navigator    = self._navigator,
            get_stamp_fn = lambda: self.get_clock().now().to_msg(),
            on_status_cb = self._publicar_status,
        )

        # ── Servidor de servicio ─────────────────────────────────────────────
        self.create_service(
            IniciarEscondite,
            "/patricio/escondite/iniciar",
            self._handle_service,
            callback_group=self._cb_group,
        )

        # ── Subscripción STOP en caliente ────────────────────────────────────
        # Permite cancelar desde la web sin llamar al servicio completo.
        self.create_subscription(
            String,
            "/patricio/escondite/control",
            self._cb_control,
            10,
            callback_group=self._cb_group,
        )

        self.get_logger().info(
            "EsconditoServiceNode listo.\n"
            "  Servicio : /patricio/escondite/iniciar\n"
            "  Control  : /patricio/escondite/control  (STOP)\n"
            "  Status   : /patricio/escondite/status"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Handler del servicio
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_service(
        self,
        request: IniciarEscondite.Request,
        response: IniciarEscondite.Response,
    ) -> IniciarEscondite.Response:

        command = request.command.strip().upper()

        if command == "START":
            target = self._logic.iniciar(request.poses.poses)

            if target is None:
                # EsconditoLogic ya publicó el motivo en /status
                response.success = False
                response.message = "No se pudo iniciar. Revisa /status para más detalles."
            else:
                response.success     = True
                response.message     = "Búsqueda iniciada."
                response.target_pose = target

        elif command == "STOP":
            hubo_cancelacion = self._logic.detener()
            response.success = hubo_cancelacion
            response.message = (
                "Cancelación enviada." if hubo_cancelacion
                else "No había navegación activa."
            )

        else:
            response.success = False
            response.message = f"Comando desconocido: '{request.command}'. Usa START o STOP."
            self.get_logger().warn(response.message)

        return response

    # ──────────────────────────────────────────────────────────────────────────
    # STOP en caliente desde tópico /control
    # ──────────────────────────────────────────────────────────────────────────

    def _cb_control(self, msg: String) -> None:
        command = msg.data.strip().upper()

        if command == "STOP":
            cancelado = self._logic.detener()
            if not cancelado:
                self.get_logger().info("STOP recibido pero no había navegación activa.")
        else:
            self.get_logger().warn(f"Comando desconocido en /control: '{msg.data}'")

    # ──────────────────────────────────────────────────────────────────────────
    # Publicación de estado (callback que recibe EsconditoLogic)
    # ──────────────────────────────────────────────────────────────────────────

    def _publicar_status(self, texto: str) -> None:
        msg      = String()
        msg.data = texto
        self._pub_status.publish(msg)
        self.get_logger().info(f"Status → '{texto}'")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = EsconditoServiceNode()

    # MultiThreadedExecutor es obligatorio:
    # el servicio responde inmediatamente mientras el hilo de lógica
    # navega en segundo plano.
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()