#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_interface_node.py
====================

Nodo servidor ROS 2 del paquete `patricio_db_interface`.

Centraliza el envío de información del robot hacia la base de datos SQL.
Expone dos servicios ROS 2 personalizados (definidos en `patricio_interfaces`):

  * /patricio/db/guardar_partida       (patricio_interfaces/srv/GuardarPartida)
  * /patricio/db/registrar_incidencia  (patricio_interfaces/srv/RegistrarIncidencia)

Cada petición ROS se traduce en una llamada HTTP POST contra `patricio_api.py`
(servidor Flask local). El nodo sólo responde `success=True` cuando:
  1. La API responde con código HTTP 2xx.
  2. El JSON de respuesta contiene `ok: true`.
  3. La BBDD ha confirmado el guardado (la API sólo devuelve `ok: true`
     después de un COMMIT exitoso, ver patricio_web/patricio_api.py).

Parámetros ROS:
  - api_url (string, default "http://localhost:5000"):
        URL base de patricio_api.py. Cambiar sólo si se mueve la API
        o cambia el puerto. Todo el proyecto corre en local.
  - request_timeout (double, default 5.0):
        Timeout en segundos para las peticiones HTTP.

Mapeo BBDD (esquema actual, ver patricio_web/schema.sql):
  - guardar_partida → tabla `partidas` (id_partida, id_usuario, id_actividad,
    puntuacion, duracion, detalles_json, fecha)
  - registrar_incidencia → tabla `incidencias` (id_incidencia, id_usuario,
    tipo, descripcion, fecha, resuelto)
"""

import json
import math

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

import requests

from patricio_interfaces.srv import GuardarPartida, RegistrarIncidencia


class DbInterfaceNode(Node):
    """Nodo que traduce servicios ROS 2 en llamadas REST a patricio_api.py."""

    def __init__(self) -> None:
        super().__init__('db_interface_node')

        # ── Parámetros ──────────────────────────────────────────────────────
        self.declare_parameter('api_url', 'http://localhost:5000')
        self.declare_parameter('request_timeout', 5.0)

        self._api_url: str = (
            self.get_parameter('api_url').get_parameter_value().string_value
        ).rstrip('/')
        self._timeout: float = float(
            self.get_parameter('request_timeout').get_parameter_value().double_value
        )

        # Callback group reentrant: permite atender varios servicios en
        # paralelo sin que se bloqueen entre sí mientras esperan la respuesta
        # HTTP (las llamadas requests.post son síncronas y bloqueantes).
        self._cb_group = ReentrantCallbackGroup()

        # ── Servicios ROS 2 ─────────────────────────────────────────────────
        self._srv_guardar = self.create_service(
            GuardarPartida,
            '/patricio/db/guardar_partida',
            self._cb_guardar_partida,
            callback_group=self._cb_group,
        )
        self._srv_incidencia = self.create_service(
            RegistrarIncidencia,
            '/patricio/db/registrar_incidencia',
            self._cb_registrar_incidencia,
            callback_group=self._cb_group,
        )

        self.get_logger().info(
            f'patricio_db_interface listo — API={self._api_url} '
            f'(timeout={self._timeout:.1f}s)'
        )
        self.get_logger().info(
            'Servicios: /patricio/db/guardar_partida , '
            '/patricio/db/registrar_incidencia'
        )

    # ────────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_field(raw: str):
        """Convierte una cadena JSON en dict/list.

        - Devuelve None si está vacía.
        - Devuelve el dict/list parseado si es JSON válido.
        - Devuelve {"valor": raw} como fallback si no es JSON válido,
          para no perder el dato.
        """
        if raw is None:
            return None
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return {'valor': s}

    def _post_json(self, path: str, payload: dict):
        """Hace POST contra la API y devuelve (status_code, dict_json, error_msg).

        - error_msg es None si la petición llegó (aunque devuelva 4xx/5xx).
        - status_code es None si hubo error de transporte (conexión/timeout).
        """
        url = f'{self._api_url}{path}'
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
        except requests.exceptions.ConnectionError:
            return None, None, f'No se pudo conectar a la API en {url}'
        except requests.exceptions.Timeout:
            return None, None, f'Timeout ({self._timeout:.1f}s) llamando a {url}'
        except requests.exceptions.RequestException as exc:
            return None, None, f'Error HTTP en {url}: {exc}'

        try:
            data = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data, None

    # ────────────────────────────────────────────────────────────────────────
    #  CALLBACKS
    # ────────────────────────────────────────────────────────────────────────

    def _cb_guardar_partida(self, request, response):
        """Maneja /patricio/db/guardar_partida → POST /api/guardar_juego."""
        self.get_logger().info(
            f'guardar_partida recibido: juego="{request.nombre_juego}" '
            f'resultado="{request.resultado}" estado="{request.estado}" '
            f'usuario_id={request.usuario_id} duracion={request.duracion}'
        )

        # ── Validación de entrada ────────────────────────────────────────────
        nombre = (request.nombre_juego or '').strip()
        if not nombre:
            response.success = False
            response.message = 'nombre_juego es obligatorio'
            response.id_partida = 0
            return response

        # ── Construcción del payload para la API ─────────────────────────────
        payload = {'nombre_juego': nombre}

        if request.usuario_id and request.usuario_id > 0:
            payload['id_usuario'] = int(request.usuario_id)

        # puntuacion: NaN significa "no aplica" (no se puede transmitir None
        # en un float32 de ROS, usamos NaN como centinela).
        if not math.isnan(request.puntuacion):
            payload['puntuacion'] = float(request.puntuacion)

        # duracion: 0 es válido (la API tiene default 0), siempre lo enviamos.
        payload['duracion'] = int(max(0, request.duracion))

        if request.resultado:
            payload['resultado'] = request.resultado
        if request.estado:
            payload['estado'] = request.estado

        # detalles_json: parseamos para enviarlo como objeto JSON real
        # a la API (no como string).
        detalles = self._parse_json_field(request.detalles_json)
        if detalles is not None:
            payload['detalles'] = detalles

        # ── Llamada HTTP ─────────────────────────────────────────────────────
        status, data, err = self._post_json('/api/guardar_juego', payload)

        # ── Verificación de Respuesta (criterio del checklist) ───────────────
        if err is not None:
            response.success = False
            response.message = err
            response.id_partida = 0
            self.get_logger().error(err)
            return response

        ok = bool(data and data.get('ok') is True)
        if not (status and 200 <= status < 300 and ok):
            err_msg = (data or {}).get('error') if isinstance(data, dict) else None
            response.success = False
            response.message = (
                f'API devolvió status={status} ok={ok} error={err_msg!r}'
            )
            response.id_partida = 0
            self.get_logger().warn(response.message)
            return response

        # ── Éxito: extraer id_partida del registro creado ────────────────────
        # La API devuelve `registro` con tanto `id_partida` (canónico)
        # como `id` (alias). Usamos el canónico.
        registro = data.get('registro') or {}
        try:
            response.id_partida = int(registro.get('id_partida') or registro.get('id') or 0)
        except (TypeError, ValueError):
            response.id_partida = 0

        response.success = True
        response.message = f'Partida guardada correctamente (id_partida={response.id_partida})'
        self.get_logger().info(
            f'guardar_partida OK → id_partida={response.id_partida}'
        )
        return response

    def _cb_registrar_incidencia(self, request, response):
        """Maneja /patricio/db/registrar_incidencia → POST /api/incidencias."""
        self.get_logger().info(
            f'registrar_incidencia recibido: tipo="{request.tipo}" '
            f'severidad="{request.severidad}" usuario_id={request.usuario_id}'
        )

        # ── Validación de entrada ────────────────────────────────────────────
        tipo = (request.tipo or '').strip()
        if not tipo:
            response.success = False
            response.message = 'tipo es obligatorio'
            response.id_incidencia = 0
            return response

        # severidad válida según la API: info|aviso|critico (default aviso)
        sev = (request.severidad or '').strip().lower() or 'aviso'
        if sev not in ('info', 'aviso', 'critico'):
            sev = 'aviso'

        # ── Construcción del payload para la API ─────────────────────────────
        payload = {
            'tipo': tipo,
            'severidad': sev,
        }
        if request.descripcion:
            payload['descripcion'] = request.descripcion
        if request.usuario_id and request.usuario_id > 0:
            payload['id_usuario'] = int(request.usuario_id)

        # ── Llamada HTTP ─────────────────────────────────────────────────────
        status, data, err = self._post_json('/api/incidencias', payload)

        # ── Verificación de Respuesta (criterio del checklist) ───────────────
        if err is not None:
            response.success = False
            response.message = err
            response.id_incidencia = 0
            self.get_logger().error(err)
            return response

        ok = bool(data and data.get('ok') is True)
        if not (status and 200 <= status < 300 and ok):
            err_msg = (data or {}).get('error') if isinstance(data, dict) else None
            response.success = False
            response.message = (
                f'API devolvió status={status} ok={ok} error={err_msg!r}'
            )
            response.id_incidencia = 0
            self.get_logger().warn(response.message)
            return response

        # ── Éxito: extraer id_incidencia ─────────────────────────────────────
        incidencia = data.get('incidencia') or {}
        try:
            response.id_incidencia = int(
                incidencia.get('id_incidencia') or incidencia.get('id') or 0
            )
        except (TypeError, ValueError):
            response.id_incidencia = 0

        response.success = True
        response.message = f'Incidencia registrada correctamente (id_incidencia={response.id_incidencia})'
        self.get_logger().info(
            f'registrar_incidencia OK → id_incidencia={response.id_incidencia}'
        )
        return response


def main(args=None):
    rclpy.init(args=args)
    node = DbInterfaceNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
