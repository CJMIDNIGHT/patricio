#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
actividad_client.py
===================

Cliente ROS 2 para registrar ACTIVIDADES (partidas de juego y también
interacciones conversacionales como chistes o cuentos) en la base de datos
SQL del robot Patricio.

Consume el servicio que expone el servidor `patricio_db_interface`:

    /patricio/db/guardar_partida   (patricio_interfaces/srv/GuardarPartida)

que a su vez traduce la petición en un POST /api/guardar_juego contra la API
Flask, la cual escribe en la tabla SQL `partidas` (con su fecha y datos
estructurados).

Se puede usar de dos formas:

  1) Como CLASE reutilizable desde otro nodo (p. ej. el nodo de IA):

        from patricio_db_interface.actividad_client import ActividadDbClient
        cli = ActividadDbClient(self)            # self = un rclpy Node
        ok, msg, id_partida = cli.registrar_actividad('chiste', puntos=0, duracion=8)

  2) Como SCRIPT de terminal (para verificar la persistencia a mano):

        ros2 run patricio_db_interface registrar_actividad \\
             --tipo chiste --puntos 0 --duracion 8
"""

from __future__ import annotations

import argparse
import json
import math
import threading
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.utilities import remove_ros_args

from patricio_interfaces.srv import GuardarPartida

SERVICIO_GUARDAR_PARTIDA = '/patricio/db/guardar_partida'


class ActividadDbClient:
    """Cliente reutilizable del servicio de BBDD para registrar actividades."""

    def __init__(self, node, service_name: str = SERVICIO_GUARDAR_PARTIDA,
                 callback_group=None) -> None:
        self._node = node
        self._service_name = service_name
        self._cli = node.create_client(
            GuardarPartida, service_name, callback_group=callback_group
        )

    # ------------------------------------------------------------------
    def disponible(self, timeout: float = 3.0) -> bool:
        """True si el servidor de BBDD está accesible."""
        return self._cli.wait_for_service(timeout_sec=timeout)

    # ------------------------------------------------------------------
    def registrar_actividad(
        self,
        tipo: str,
        puntos: float = float('nan'),
        duracion: int = 0,
        usuario_id: int = 0,
        resultado: str = '',
        estado: str = 'finalizado_ok',
        detalles: Any = None,
        timeout: float = 10.0,
    ) -> tuple[bool, str, int]:
        """Empaqueta (tipo, puntos, duracion) y lo envía al servidor de BBDD.

        Parámetros
        ----------
        tipo : str
            Nombre/tipo de la actividad: "chiste", "cuento", "conversacion",
            "pilla_pilla", "escondite", "calamar"...  (impacta `partidas` y, si
            no existe, la API crea la actividad correspondiente).
        puntos : float
            Puntuación obtenida. NaN = no aplica (no se envía a la API).
        duracion : int
            Duración en segundos (0 si no aplica).
        usuario_id : int
            ID de usuario. 0 o negativo = anónimo / sistema.
        resultado, estado : str
            Metadatos opcionales (p. ej. "victoria", "finalizado_ok").
        detalles : dict | str | None
            Metadatos extra. Se serializan a JSON si es un dict.

        Devuelve
        --------
        (success, message, id_partida)
        """
        tipo = (tipo or '').strip()
        if not tipo:
            return False, 'El tipo (nombre de la actividad) es obligatorio.', 0

        if not self.disponible(timeout=3.0):
            return False, f'Servicio {self._service_name} no disponible.', 0

        request = self._construir_request(
            tipo, puntos, duracion, usuario_id, resultado, estado, detalles
        )

        response = self._llamar_sincrono(request, timeout)
        if response is None:
            return False, 'El servicio de BBDD no respondió a tiempo.', 0

        return (
            bool(getattr(response, 'success', False)),
            str(getattr(response, 'message', '') or ''),
            int(getattr(response, 'id_partida', 0) or 0),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _construir_request(
        tipo: str,
        puntos: float,
        duracion: int,
        usuario_id: int,
        resultado: str,
        estado: str,
        detalles: Any,
    ) -> GuardarPartida.Request:
        """Construye el GuardarPartida.Request a partir de los datos sueltos."""
        request = GuardarPartida.Request()
        # En el esquema actual del servicio, el nombre de la actividad viaja en
        # 'nombre_juego' (la API lo resuelve o crea como actividad).
        request.nombre_juego = tipo
        request.usuario_id = int(usuario_id or 0)

        # puntos -> puntuacion (NaN = no aplica).
        try:
            punt = float(puntos)
        except (TypeError, ValueError):
            punt = float('nan')
        request.puntuacion = punt if not math.isnan(punt) else float('nan')

        request.duracion = int(duracion or 0)
        request.resultado = str(resultado or '')
        request.estado = str(estado or 'finalizado_ok')

        if detalles is None:
            request.detalles_json = ''
        elif isinstance(detalles, str):
            request.detalles_json = detalles
        else:
            try:
                request.detalles_json = json.dumps(detalles, ensure_ascii=False)
            except (TypeError, ValueError):
                request.detalles_json = ''
        return request

    # ------------------------------------------------------------------
    def _llamar_sincrono(self, request: GuardarPartida.Request, timeout: float):
        """Llama al servicio sin re-entrar en el spin (válido dentro de callbacks).

        Requiere que el nodo esté siendo girado por un executor (idealmente
        MultiThreadedExecutor) en otro hilo.
        """
        future = self._cli.call_async(request)
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout):
            return None
        return future.result()


# ----------------------------------------------------------------------
#  CLI — uso desde terminal para verificar la persistencia a mano
# ----------------------------------------------------------------------
def main(argv=None) -> int:
    # Quita los --ros-args para que argparse no se confunda.
    ros_clean = remove_ros_args(args=argv)
    parser = argparse.ArgumentParser(
        prog='registrar_actividad',
        description='Registra una actividad (juego o conversación) en la BBDD '
                    'vía el servicio /patricio/db/guardar_partida.',
    )
    parser.add_argument('--tipo', required=True,
                        help='Nombre/tipo: chiste, cuento, conversacion, pilla_pilla, ...')
    parser.add_argument('--puntos', type=float, default=float('nan'),
                        help='Puntuación (por defecto NaN = no aplica).')
    parser.add_argument('--duracion', type=int, default=0,
                        help='Duración en segundos (por defecto 0).')
    parser.add_argument('--usuario-id', type=int, default=0,
                        help='ID de usuario (0 = anónimo).')
    parser.add_argument('--detalles', default='',
                        help='JSON opcional con metadatos extra.')
    # ros_clean[0] es el nombre del programa; el resto son los argumentos.
    args = parser.parse_args(ros_clean[1:])

    rclpy.init(args=argv)
    node = rclpy.create_node('registrar_actividad_cli')
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    detalles = args.detalles.strip() or None
    cliente = ActividadDbClient(node)
    node.get_logger().info(
        f'Registrando actividad: tipo="{args.tipo}" puntos={args.puntos} '
        f'duracion={args.duracion}s usuario_id={args.usuario_id}'
    )
    ok, msg, id_partida = cliente.registrar_actividad(
        tipo=args.tipo,
        puntos=args.puntos,
        duracion=args.duracion,
        usuario_id=args.usuario_id,
        detalles=detalles,
    )

    estado = 'OK' if ok else 'FALLO'
    print(f'[{estado}] {msg} (id_partida={id_partida})')

    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
