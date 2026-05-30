#!/usr/bin/env python3
"""
escondite.py
Lógica pura del juego del escondite.

Cambio respecto a la versión anterior:
  - Al llegar a cada punto (SUCCEEDED), se ejecuta una validación visual
    mediante /patricio/vision/person_detection antes de dar el goal por válido.
  - Si no se detecta persona en el tiempo máximo, el punto se considera
    "vacío" y se continúa con el siguiente.
  - Solo cuando la navegación al objetivo real termina con persona detectada
    se publica "¡Te encontré!".

La validación visual es configurable:
  - vision_confirm_sec   : segundos que la persona debe ser visible
                           de forma continua para confirmar detección.
  - vision_timeout_sec   : tiempo máximo esperando confirmación visual
                           antes de dar el punto por vacío.
  - vision_confidence_min: confianza mínima del landmark de hombros
                           para aceptar la detección.
"""

import random
import threading
import time
from typing import Callable

from geometry_msgs.msg import Pose, PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from builtin_interfaces.msg import Time

from patricio_interfaces.msg import PersonDetection


class EsconditoLogic:
    """
    Lógica del juego del escondite con validación visual al llegar a cada punto.

    Uso:
        logic = EsconditoLogic(
            navigator    = navigator,
            get_stamp_fn = lambda: node.get_clock().now().to_msg(),
            on_status_cb = mi_callback,
            node         = node,           # ← necesario para el subscriber
        )
        target = logic.iniciar(lista_de_poses)
        logic.detener()
    """

    def __init__(
        self,
        navigator:    BasicNavigator,
        get_stamp_fn: Callable[[], Time],
        on_status_cb: Callable[[str], None],
        node,                               # rclpy.Node — para crear subscriber
        vision_confirm_sec:    float = 1.5,
        vision_timeout_sec:    float = 5.0,
        vision_confidence_min: float = 0.5,
    ):
        self._navigator   = navigator
        self._get_stamp   = get_stamp_fn
        self._on_status   = on_status_cb
        self._node        = node

        self._vision_confirm  = vision_confirm_sec
        self._vision_timeout  = vision_timeout_sec
        self._vision_conf_min = vision_confidence_min

        self._navigating  = False
        self._target: Pose = None
        self._lock        = threading.Lock()

        # ── Último dato de PersonDetection ────────────────────────────
        self._latest_detection: PersonDetection | None = None
        self._detection_lock  = threading.Lock()

        # ── Subscriber a /patricio/vision/person_detection ───────────
        self._node.create_subscription(
            PersonDetection,
            '/patricio/vision/person_detection',
            self._detection_callback,
            10,
        )

    # ── Callback de visión ───────────────────────────────────────────────────

    def _detection_callback(self, msg: PersonDetection) -> None:
        """Guarda el último resultado de MediaPipe. Siempre ligero."""
        with self._detection_lock:
            self._latest_detection = msg

    # ── API pública ──────────────────────────────────────────────────────────

    def iniciar(self, poses: list[Pose]) -> Pose | None:
        with self._lock:
            if self._navigating:
                self._on_status("Ya estoy buscando. Detén primero.")
                return None
            if not poses:
                self._on_status("Error: la lista de poses está vacía.")
                return None

            if len(poses) == 1:
                self._target = poses[0]
                falsas = []
            else:
                self._target = random.choice(poses)
                falsas = [p for p in poses if p != self._target]
                random.shuffle(falsas)

            self._navigating = True

        threading.Thread(
            target=self._run,
            args=(falsas, self._target),
            daemon=True,
        ).start()

        return self._target

    def detener(self) -> bool:
        with self._lock:
            if not self._navigating:
                return False
        self._navigator.cancelTask()
        return True

    @property
    def esta_navegando(self) -> bool:
        return self._navigating

    # ── Lógica interna ───────────────────────────────────────────────────────

    def _run(self, falsas: list[Pose], objetivo: Pose) -> None:

        # ── Fase 1: puntos falsos ─────────────────────────────────────
        for i, pose in enumerate(falsas, start=1):
            ok = self._navegar_a(pose)
            if not ok:
                with self._lock:
                    self._navigating = False
                return

            # Validación visual en punto falso
            # Si hay persona aquí → coincidencia anticipada, terminar
            self._on_status(f"Revisando punto {i}...")
            persona_aqui = self._confirmar_persona()

            if persona_aqui:
                self._on_status("¡Te encontré! (punto intermedio)")
                with self._lock:
                    self._navigating = False
                return

            self._on_status(f"Punto {i} vacío. Continuando...")

        # ── Fase 2: objetivo real ─────────────────────────────────────
        ok = self._navegar_a(objetivo)

        if not ok:
            result = self._navigator.getResult()
            if result == TaskResult.CANCELED:
                self._on_status("Búsqueda detenida.")
            else:
                self._on_status("No puedo llegar ahí.")
            with self._lock:
                self._navigating = False
            return

        # Validación visual en el objetivo real
        self._on_status("Llegué al punto objetivo. Buscando al niño...")
        persona_aqui = self._confirmar_persona()

        if persona_aqui:
            self._on_status("¡Te encontré!")
        else:
            self._on_status("Nadie aquí. Búsqueda completada sin éxito.")

        with self._lock:
            self._navigating = False

    # ── Validación visual ────────────────────────────────────────────────────

    def _confirmar_persona(self) -> bool:
        """
        Espera hasta que MediaPipe detecte una persona de forma continua
        durante vision_confirm_sec segundos.

        Lógica:
          - Si hay detección válida (detected=True, confidence >= mínimo)
            inicia un contador.
          - Si la detección se interrumpe, el contador se resetea.
          - Si el contador llega a vision_confirm_sec → True.
          - Si pasa vision_timeout_sec sin confirmación → False.

        Returns:
            True  → persona confirmada
            False → timeout, nadie detectado
        """
        self._node.get_logger().info(
            f'Validación visual iniciada '
            f'(confirmar={self._vision_confirm}s, '
            f'timeout={self._vision_timeout}s, '
            f'confianza_min={self._vision_conf_min})'
        )

        t_inicio        = time.monotonic()
        t_deteccion_ini = None   # cuándo empezó la detección continua actual

        while True:
            elapsed = time.monotonic() - t_inicio

            # Timeout global
            if elapsed > self._vision_timeout:
                self._node.get_logger().info(
                    f'Validación visual: timeout tras {elapsed:.1f}s.')
                return False

            # Cancelación desde detener()
            with self._lock:
                if not self._navigating:
                    return False

            # Leer última detección
            with self._detection_lock:
                det = self._latest_detection

            # Evaluar si la detección es válida
            valida = (
                det is not None
                and det.detected
                and det.confidence >= self._vision_conf_min
            )

            if valida:
                if t_deteccion_ini is None:
                    t_deteccion_ini = time.monotonic()
                    self._node.get_logger().info('Persona detectada, confirmando...')

                tiempo_continuo = time.monotonic() - t_deteccion_ini

                self._node.get_logger().debug(
                    f'Detección continua: {tiempo_continuo:.2f}s '
                    f'/ {self._vision_confirm}s requeridos'
                )

                if tiempo_continuo >= self._vision_confirm:
                    self._node.get_logger().info(
                        f'¡Persona confirmada tras {tiempo_continuo:.2f}s!')
                    return True
            else:
                # Detección perdida → resetear contador
                if t_deteccion_ini is not None:
                    self._node.get_logger().info(
                        'Detección perdida, reiniciando contador...')
                t_deteccion_ini = None

            time.sleep(0.1)   # 10 Hz es suficiente para este bucle

    # ── Navegación ───────────────────────────────────────────────────────────

    def _navegar_a(self, pose: Pose) -> bool:
        """
        Envía una pose a Nav2 y espera el resultado.

        Returns:
            True si SUCCEEDED, False en cualquier otro caso.
        """
        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp    = self._get_stamp()
        goal.pose            = pose

        self._navigator.goToPose(goal)

        while not self._navigator.isTaskComplete():
            pass

        return self._navigator.getResult() == TaskResult.SUCCEEDED