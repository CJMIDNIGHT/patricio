#!/usr/bin/env python3
"""
escondite.py
Lógica pura del juego del escondite. Sin dependencias de ROS2.

Esta clase no sabe nada de tópicos, servicios ni mensajes.
Solo sabe navegar a una lista de poses usando BasicNavigator
y notificar el progreso a través de un callback.

Responsabilidades:
  - Elegir el punto objetivo secreto de entre las poses candidatas
  - Visitar todos los puntos falsos en orden aleatorio
  - Navegar al objetivo final
  - Notificar cada cambio de estado via on_status_cb
  - Permitir cancelación en cualquier momento
"""

import random
import threading
from typing import Callable

from geometry_msgs.msg import Pose, PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from builtin_interfaces.msg import Time


class EsconditoLogic:
    """
    Lógica del juego del escondite desacoplada de ROS2.

    Uso:
        def mi_callback(texto: str):
            # publicar en /status, loggear, etc.
            print(texto)

        logic = EsconditoLogic(navigator, clock_fn, mi_callback)
        target = logic.iniciar(lista_de_poses)
        # → navega por los falsos y luego al objetivo
        # → mi_callback se llama en cada paso

        logic.detener()  # cancela si está navegando
    """

    def __init__(
        self,
        navigator: BasicNavigator,
        get_stamp_fn: Callable[[], Time],
        on_status_cb: Callable[[str], None],
    ):
        """
        Args:
            navigator:     Instancia de BasicNavigator ya inicializada.
            get_stamp_fn:  Función que devuelve el timestamp actual (node.get_clock().now().to_msg()).
            on_status_cb:  Callback llamado con un string cada vez que hay un evento de estado.
        """
        self._navigator    = navigator
        self._get_stamp    = get_stamp_fn
        self._on_status    = on_status_cb

        self._navigating   = False
        self._target: Pose = None
        self._lock         = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────────

    def iniciar(self, poses: list[Pose]) -> Pose | None:
        """
        Arranca el juego:
          1. Elige el objetivo secreto aleatoriamente.
          2. Lanza un hilo que visita los falsos y luego el objetivo.

        Returns:
            La Pose elegida como objetivo, o None si hubo error.
        """
        with self._lock:
            if self._navigating:
                self._on_status("Ya estoy buscando. Detén primero.")
                return None

            if not poses:
                self._on_status("Error: la lista de poses está vacía.")
                return None

            if len(poses) == 1:
                # Con un solo punto no hay falsos, va directo
                self._target = poses[0]
                falsas = []
            else:
                self._target = random.choice(poses)
                falsas = [p for p in poses if p != self._target]
                random.shuffle(falsas)

            self._navigating = True

        # Lanzar en hilo para no bloquear al caller (el servidor de servicio)
        threading.Thread(
            target=self._run,
            args=(falsas, self._target),
            daemon=True,
        ).start()

        return self._target

    def detener(self) -> bool:
        """
        Cancela la navegación activa.

        Returns:
            True si había algo que cancelar, False si ya estaba idle.
        """
        with self._lock:
            if not self._navigating:
                return False

        self._navigator.cancelTask()
        return True

    @property
    def esta_navegando(self) -> bool:
        return self._navigating

    # ──────────────────────────────────────────────────────────────────────────
    # Lógica interna (corre en hilo separado)
    # ──────────────────────────────────────────────────────────────────────────

    def _run(self, falsas: list[Pose], objetivo: Pose) -> None:
        """Visita los puntos falsos y luego navega al objetivo."""

        # ── Fase 1: puntos falsos ─────────────────────────────────────────
        for i, pose in enumerate(falsas, start=1):
            #self._on_status(
            #    f"Buscando en punto {i} de {len(falsas)}... "
            #    f"(x={pose.position.x:.1f}, y={pose.position.y:.1f})"
            #)

            ok = self._navegar_a(pose)
            if not ok:
                # Cancelado o fallo: salir limpiamente
                with self._lock:
                    self._navigating = False
                return

            #self._on_status(f"Punto {i} revisado. Aquí no hay nadie.")

        # ── Fase 2: objetivo real ─────────────────────────────────────────
        #self._on_status(
        #    f"Yendo al último punto... "
        #    f"(x={objetivo.position.x:.1f}, y={objetivo.position.y:.1f})"
        #)

        ok = self._navegar_a(objetivo)

        if ok:
            self._on_status("¡Te encontré!")
        else:
            # Distinguir cancelación de fallo de navegación
            result = self._navigator.getResult()
            if result == TaskResult.CANCELED:
                self._on_status("Búsqueda detenida.")
            else:
                self._on_status("No puedo llegar ahí.")

        with self._lock:
            self._navigating = False

    def _navegar_a(self, pose: Pose) -> bool:
        """
        Envía una pose a Nav2 y espera el resultado.

        Returns:
            True si SUCCEEDED, False en cualquier otro caso (CANCELED, FAILED).
        """
        goal = PoseStamped()
        goal.header.frame_id = "map"
        goal.header.stamp    = self._get_stamp()
        goal.pose            = pose

        self._navigator.goToPose(goal)

        while not self._navigator.isTaskComplete():
            pass

        return self._navigator.getResult() == TaskResult.SUCCEEDED