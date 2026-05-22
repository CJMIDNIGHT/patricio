#!/usr/bin/env python3
"""
Flask API for Patricio web — bridges HTTP to ROS 2 via rosbridge WebSocket.
No rclpy or patricio_interfaces needed.

Endpoints:
  POST /api/juego/iniciar   → calls /start_game service via rosbridge
  POST /api/juego/detener   → publishes STOP to /patricio/pilla_pilla/cmd
  GET  /api/juego/estado    → returns last known status
  GET  /api/db/health       → comprobación SELECT 1 contra MySQL
  POST /api/db/selftest     → INSERT+SELECT en users/actividades/partidas/incidencias (solo si ENABLE_DB_SELFTEST)
  GET  /api/incidencias     → listado con filtros (fecha, rango, resuelto/estado, búsqueda)
  POST /api/incidencias     → registra anomalía (robot / monitor) y notifica admin por WebSocket
  GET  /api/incidencias/pendientes → incidencias con resuelto=0
  POST /api/incidencias/<id>/revisar → marca resuelta (silencia alerta)
  POST /api/guardar_juego     → nueva fila en partidas (actividad finalizada)
  GET  /api/historico_dia     → partidas del día (filtros: fecha, actividad, duración, orden)
  POST /api/auth/login        → comprobar email/dni + contraseña (bcrypt)
  POST /api/auth/register      → alta en users, contraseña con política fuerte
  POST /api/juego/iniciar        → calls /start_game service via rosbridge
  POST /api/juego/detener        → publishes STOP to /patricio/pilla_pilla/cmd
  GET  /api/juego/estado         → returns last known status

  POST /api/calamar/comando      → publishes command to /patricio/calamar/cmd
                                   body: { "comando": "START_AUTO" | "CAMBIAR_A_VERDE"
                                                     | "CAMBIAR_A_ROJO" | "STOP" }
  GET  /api/calamar/estado       → returns last known calamar status + alert
"""

import json
import os
import re
import threading
import time
import uuid
import atexit
from datetime import date, datetime

import bcrypt

import websocket  # pip install websocket-client
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from sqlalchemy import text

from database import get_engine

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

ROSBRIDGE_URL = 'ws://localhost:9090'
last_status = 'Descansando'
status_lock = threading.Lock()

# ── Calamar state ─────────────────────────────────────────
last_calamar_status = 'ESPERA'
last_calamar_alerta = ''
last_calamar_alerta_ts = 0.0
last_calamar_pose = False
calamar_lock = threading.Lock()


# ── Rosbridge helper ──────────────────────────────────────

def rosbridge_call_service(service, service_type, args: dict, timeout=5.0):
    """
    Calls a ROS service through rosbridge and returns the response dict.
    Blocks until response arrives or timeout.
    """
    result = {'done': False, 'response': None, 'error': None}
    call_id = str(uuid.uuid4())

    def on_message(ws, message):
        msg = json.loads(message)
        if msg.get('op') == 'service_response' and msg.get('id') == call_id:
            result['response'] = msg.get('values', {})
            result['done'] = True
            ws.close()

    def on_error(ws, error):
        result['error'] = str(error)
        result['done'] = True

    def on_open(ws):
        payload = {
            'op': 'call_service',
            'id': call_id,
            'service': service,
            'type': service_type,
            'args': args
        }
        ws.send(json.dumps(payload))

    ws = websocket.WebSocketApp(
        ROSBRIDGE_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )

    thread = threading.Thread(target=ws.run_forever)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)

    if not result['done']:
        result['error'] = 'Timeout waiting for service response'

    return result


def rosbridge_publish(topic, msg_type, data: dict):
    """
    Publishes a single message to a ROS topic via rosbridge.
    Fire and forget.
    """
    def run():
        try:
            ws = websocket.create_connection(ROSBRIDGE_URL, timeout=3)
            payload = {
                'op': 'publish',
                'topic': topic,
                'type': msg_type,
                'msg': data
            }
            ws.send(json.dumps(payload))
            ws.close()
        except Exception as e:
            print(f'rosbridge_publish error: {e}')

    threading.Thread(target=run, daemon=True).start()


def rosbridge_subscribe_status():
    """
    Runs in background thread — keeps last_status up to date
    by subscribing to /patricio/pilla_pilla/status.
    """
    global last_status

    def on_message(ws, message):
        global last_status
        msg = json.loads(message)
        if msg.get('op') == 'publish':
            with status_lock:
                last_status = msg.get('msg', {}).get('data', last_status)

    def on_open(ws):
        payload = {
            'op': 'subscribe',
            'topic': '/patricio/pilla_pilla/status',
            'type': 'std_msgs/msg/String'
        }
        ws.send(json.dumps(payload))
        print('Subscribed to /patricio/pilla_pilla/status')

    def on_error(ws, error):
        print(f'Status subscriber error: {error}')
        time.sleep(3)

    def on_close(ws, *args):
        print('Status subscriber closed, reconnecting...')
        time.sleep(3)
        rosbridge_subscribe_status()

    ws = websocket.WebSocketApp(
        ROSBRIDGE_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


def rosbridge_subscribe_status_escondite():
    global last_status

    def on_message(ws, message):
        global last_status
        msg = json.loads(message)
        if msg.get('op') == 'publish':
            with status_lock:
                last_status = msg.get('msg', {}).get('data', last_status)

    def on_open(ws):
        payload = {
            'op': 'subscribe',
            'topic': '/patricio/escondite/status',
            'type': 'std_msgs/msg/String'
        }
        ws.send(json.dumps(payload))

    def on_close(ws, *args):
        time.sleep(3)
        rosbridge_subscribe_status_escondite()

    ws = websocket.WebSocketApp(
        ROSBRIDGE_URL,
        on_open=on_open,
        on_message=on_message,
        on_close=on_close
    )
    ws.run_forever()


# ── Esquema ER: mapeos y helpers ───────────────────────────

JUEGO_SLUG_A_ACTIVIDAD = {
    'pilla_pilla': 'Pilla-Pilla',
    'escondite': 'Escondite',
    'calamar': 'Juego del Calamar',
    'juego_del_calamar': 'Juego del Calamar',
}


def _rol_desde_email(email: str) -> str:
    e = (email or '').strip().lower()
    if e == 'admin@patricio.local':
        return 'admin'
    if e == 'educador@patricio.local':
        return 'educador'
    return 'familia'


def _resolve_actividad_id(conn, body: dict) -> int:
    """Obtiene id_actividad por id, nombre de actividad o slug de juego (nombre_juego)."""
    aid = body.get('id_actividad')
    if aid is not None:
        aid = int(aid)
        row = conn.execute(
            text('SELECT id_actividad FROM actividades WHERE id_actividad = :id'),
            {'id': aid},
        ).first()
        if row:
            return int(row[0])
        raise ValueError('id_actividad no encontrado')

    nombre = (
        (body.get('nombre_actividad') or body.get('nombre_juego') or '')
        .strip()
    )
    if not nombre:
        raise ValueError('nombre_juego o id_actividad requerido')

    slug = nombre.lower().replace(' ', '_').replace('-', '_')
    nombre_canon = JUEGO_SLUG_A_ACTIVIDAD.get(slug, nombre)

    row = conn.execute(
        text('SELECT id_actividad FROM actividades WHERE nombre = :n LIMIT 1'),
        {'n': nombre_canon[:100]},
    ).first()
    if row:
        return int(row[0])

    row = conn.execute(
        text(
            """INSERT INTO actividades (nombre, tipo)
               VALUES (:n, :t)"""
        ),
        {'n': nombre_canon[:100], 't': (body.get('tipo_actividad') or 'juego')[:50]},
    )
    return int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())


# ── Incidencias (SQL + Socket.IO) ─────────────────────────

def _incidencia_row_to_dict(row) -> dict:
    d = dict(row)
    iid = d.get('id_incidencia', d.get('id'))
    d['id'] = int(iid) if iid is not None else None
    d['id_incidencia'] = d['id']
    for key in ('fecha',):
        v = d.get(key)
        if v is not None and hasattr(v, 'isoformat'):
            d[key] = v.isoformat()
    resuelto = bool(d.get('resuelto'))
    d['resuelto'] = resuelto
    d['resuelta'] = resuelto
    desc = d.get('descripcion') or ''
    d['titulo'] = d.get('tipo') or ''
    d['mensaje'] = desc
    d['estado'] = 'revisada' if resuelto else 'abierta'
    d['severidad'] = d.get('severidad') or 'aviso'
    return d


def _emit_nueva_incidencia(payload: dict) -> None:
    try:
        socketio.emit('nueva_incidencia', payload)
    except Exception as e:
        print(f'Socket emit nueva_incidencia: {e}')


def _emit_incidencia_revisada(inc_id: int) -> None:
    try:
        socketio.emit('incidencia_revisada', {'id': inc_id})
    except Exception as e:
        print(f'Socket emit incidencia_revisada: {e}')


# ── Flask routes ──────────────────────────────────────────
def rosbridge_subscribe_calamar():
    """
    Background thread — subscribes to both calamar status and alert topics.
    Keeps last_calamar_status and last_calamar_alerta up to date.
    """
    global last_calamar_status, last_calamar_alerta, last_calamar_alerta_ts, last_calamar_pose

    def on_message(ws, message):
        global last_calamar_status, last_calamar_alerta, last_calamar_alerta_ts, last_calamar_pose
        msg = json.loads(message)
        if msg.get('op') == 'publish':
            topic = msg.get('topic', '')
            data = msg.get('msg', {}).get('data', '')
            with calamar_lock:
                if topic == '/patricio/calamar/status':
                    last_calamar_status = data
                elif topic == '/patricio/alerta_juego':
                    last_calamar_alerta    = data
                    last_calamar_alerta_ts = time.time()

    def on_open(ws):
        for topic in ['/patricio/calamar/status', '/patricio/alerta_juego']:
            ws.send(json.dumps({
                'op': 'subscribe',
                'topic': topic,
                'type': 'std_msgs/msg/String'
            }))
        print('Subscribed to calamar topics')

    def on_error(ws, error):
        print(f'Calamar subscriber error: {error}')
        time.sleep(3)

    def on_close(ws, *args):
        print('Calamar subscriber closed, reconnecting...')
        time.sleep(3)
        rosbridge_subscribe_calamar()

    ws = websocket.WebSocketApp(
        ROSBRIDGE_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


# ── Flask routes — juegos existentes ─────────────────────

@app.route('/api/juego/iniciar', methods=['POST'])
def iniciar_juego():
    body = request.get_json(force=True)
    game_name = body.get('game_name', 'pilla_pilla')

    if game_name != 'pilla_pilla':
        return jsonify({'started': False, 'error': 'Juego no reconocido'}), 400

    result = None
    for attempt in range(2):
        result = rosbridge_call_service(
            service='/start_game',
            service_type='patricio_interfaces/srv/StartGame',
            args={'game_name': game_name},
            timeout=10.0
        )
        if not result['error']:
            break
        print(f'Attempt {attempt + 1} failed: {result["error"]}, retrying...')
        time.sleep(1)

    if result['error']:
        return jsonify({'started': False, 'error': result['error']}), 500

    started = result['response'].get('started', False)
    return jsonify({'started': started})


@app.route('/api/juego/detener', methods=['POST'])
def detener_juego():
    rosbridge_publish(
        topic='/patricio/pilla_pilla/cmd',
        msg_type='std_msgs/msg/String',
        data={'data': 'STOP'}
    )
    return jsonify({'stopped': True})


@app.route('/api/juego/estado', methods=['GET'])
def estado_juego():
    with status_lock:
        return jsonify({'status': last_status})


# ── Histórico de juegos ───────────────────────────────────


def _partida_row_to_dict(row) -> dict:
    d = dict(row)
    pid = d.get('id_partida', d.get('id'))
    d['id'] = int(pid) if pid is not None else None
    d['id_partida'] = d['id']
    for key in ('fecha',):
        v = d.get(key)
        if v is not None and hasattr(v, 'isoformat'):
            d[key] = v.isoformat()
    d['nombre_juego'] = d.get('nombre_actividad') or d.get('nombre_juego')
    d['iniciado_en'] = d.get('fecha')
    d['finalizado_en'] = d.get('fecha')
    det = d.get('detalles_json')
    if isinstance(det, str):
        try:
            det = json.loads(det)
        except json.JSONDecodeError:
            det = {}
    if isinstance(det, dict):
        d['resultado'] = det.get('resultado')
        d['estado'] = det.get('estado')
    return d


@app.route('/api/guardar_juego', methods=['POST'])
def guardar_juego():
    """
    Registra una partida finalizada.
    JSON: nombre_juego o id_actividad (obligatorio uno de los dos),
          id_usuario (opcional), puntuacion, duracion (segundos),
          resultado, estado, detalles (objeto opcional, se fusiona en detalles_json).
    """
    body = request.get_json(force=True, silent=True) or {}
    nombre_juego = (body.get('nombre_juego') or body.get('nombre_actividad') or '').strip()
    if not nombre_juego and body.get('id_actividad') is None:
        return jsonify({'ok': False, 'error': 'nombre_juego o id_actividad requerido'}), 400

    resultado_raw = body.get('resultado')
    resultado = (str(resultado_raw).strip()[:64]) if resultado_raw is not None else None
    estado = (body.get('estado') or 'finalizado_ok').strip()[:64]

    id_usuario = body.get('id_usuario', body.get('usuario_id'))
    if id_usuario is not None:
        try:
            id_usuario = int(id_usuario)
        except (TypeError, ValueError):
            id_usuario = None

    puntuacion = body.get('puntuacion')
    if puntuacion is not None:
        try:
            puntuacion = float(puntuacion)
        except (TypeError, ValueError):
            puntuacion = None

    duracion = body.get('duracion', 0)
    try:
        duracion = int(duracion)
    except (TypeError, ValueError):
        duracion = 0

    detalles = body.get('detalles')
    if detalles is not None and not isinstance(detalles, dict):
        detalles = {'valor': str(detalles)}
    else:
        detalles = dict(detalles or {})
    if resultado is not None:
        detalles['resultado'] = resultado
    if estado:
        detalles['estado'] = estado
    det_json = json.dumps(detalles, ensure_ascii=False) if detalles else None

    try:
        with get_engine().begin() as conn:
            id_actividad = _resolve_actividad_id(conn, body)
            if det_json is None:
                conn.execute(
                    text(
                        """INSERT INTO partidas
                           (id_usuario, id_actividad, puntuacion, duracion, detalles_json)
                           VALUES (:uid, :aid, :punt, :dur, NULL)"""
                    ),
                    {
                        'uid': id_usuario,
                        'aid': id_actividad,
                        'punt': puntuacion,
                        'dur': duracion,
                    },
                )
            else:
                conn.execute(
                    text(
                        """INSERT INTO partidas
                           (id_usuario, id_actividad, puntuacion, duracion, detalles_json)
                           VALUES (:uid, :aid, :punt, :dur, CAST(:det AS JSON))"""
                    ),
                    {
                        'uid': id_usuario,
                        'aid': id_actividad,
                        'punt': puntuacion,
                        'dur': duracion,
                        'det': det_json,
                    },
                )
            pid = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())
            row = conn.execute(
                text(
                    """SELECT p.id_partida, p.id_usuario, p.id_actividad, p.puntuacion,
                              p.duracion, p.detalles_json, p.fecha,
                              a.nombre AS nombre_actividad
                       FROM partidas p
                       JOIN actividades a ON a.id_actividad = p.id_actividad
                       WHERE p.id_partida = :id"""
                ),
                {'id': pid},
            ).mappings().one()

        return jsonify({'ok': True, 'registro': _partida_row_to_dict(row)}), 201
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


_HISTORICO_ORDEN = {
    'fecha_desc': 'p.fecha DESC, p.id_partida DESC',
    'fecha_asc': 'p.fecha ASC, p.id_partida ASC',
    'puntuacion_desc': 'p.puntuacion DESC, p.fecha DESC, p.id_partida DESC',
    'puntuacion_asc': 'p.puntuacion ASC, p.fecha DESC, p.id_partida DESC',
    'duracion_desc': 'p.duracion DESC, p.fecha DESC, p.id_partida DESC',
    'duracion_asc': 'p.duracion ASC, p.fecha DESC, p.id_partida DESC',
}


@app.route('/api/historico_dia', methods=['GET'])
def historico_dia():
    """
    Histórico de partidas para la fecha indicada (o hoy).
    Query: fecha=YYYY-MM-DD, id_usuario|usuario_id,
           actividad (nombre exacto en actividades),
           duracion_min, duracion_max (segundos),
           orden (fecha_desc|puntuacion_desc|puntuacion_asc|duracion_desc|duracion_asc).
    """
    fecha_str = request.args.get('fecha')
    if fecha_str:
        try:
            datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'ok': False, 'error': 'fecha debe ser YYYY-MM-DD'}), 400
    else:
        fecha_str = date.today().isoformat()

    id_usuario = request.args.get('id_usuario', type=int)
    if id_usuario is None:
        id_usuario = request.args.get('usuario_id', type=int)

    actividad = (request.args.get('actividad') or request.args.get('nombre_actividad') or '').strip()
    duracion_min = request.args.get('duracion_min', type=int)
    duracion_max = request.args.get('duracion_max', type=int)
    orden = (request.args.get('orden') or 'fecha_desc').strip().lower()
    if orden not in _HISTORICO_ORDEN:
        return jsonify({
            'ok': False,
            'error': 'orden no válido (fecha_desc, puntuacion_desc, puntuacion_asc, duracion_desc, duracion_asc)',
        }), 400

    clauses = ['DATE(p.fecha) = :fecha']
    params = {'fecha': fecha_str}

    if id_usuario is not None:
        # Partidas del robot/admin suelen guardarse sin id_usuario (NULL)
        clauses.append('(p.id_usuario = :uid OR p.id_usuario IS NULL)')
        params['uid'] = id_usuario
    if actividad:
        clauses.append('a.nombre = :act')
        params['act'] = actividad[:100]
    if duracion_min is not None:
        clauses.append('p.duracion >= :dmin')
        params['dmin'] = max(0, duracion_min)
    if duracion_max is not None:
        clauses.append('p.duracion <= :dmax')
        params['dmax'] = max(0, duracion_max)

    where_sql = ' AND '.join(clauses)
    order_sql = _HISTORICO_ORDEN[orden]

    try:
        with get_engine().connect() as conn:
            detalle = conn.execute(
                text(
                    f"""SELECT p.id_partida, p.id_usuario, p.id_actividad, p.puntuacion,
                               p.duracion, p.detalles_json, p.fecha,
                               a.nombre AS nombre_actividad, a.tipo AS tipo_actividad
                        FROM partidas p
                        JOIN actividades a ON a.id_actividad = p.id_actividad
                        WHERE {where_sql}
                        ORDER BY {order_sql}"""
                ),
                params,
            ).mappings().all()

            agrupado = conn.execute(
                text(
                    f"""SELECT a.nombre AS nombre_actividad, COUNT(*) AS veces,
                               COALESCE(SUM(p.puntuacion), 0) AS puntos_totales,
                               COALESCE(SUM(p.duracion), 0) AS duracion_total
                        FROM partidas p
                        JOIN actividades a ON a.id_actividad = p.id_actividad
                        WHERE {where_sql}
                        GROUP BY a.nombre
                        ORDER BY veces DESC, a.nombre ASC"""
                ),
                params,
            ).mappings().all()

        lista_detalle = [_partida_row_to_dict(r) for r in detalle]
        lista_agrupado = [
            {
                'nombre_juego': r['nombre_actividad'],
                'nombre_actividad': r['nombre_actividad'],
                'veces': int(r['veces']),
                'puntos_totales': float(r['puntos_totales']) if r['puntos_totales'] is not None else 0.0,
                'duracion_total': int(r['duracion_total'] or 0),
            }
            for r in agrupado
        ]
        veces_list = [int(x['veces']) for x in lista_agrupado]
        total = sum(veces_list)
        favorito = lista_agrupado[0]['nombre_actividad'] if lista_agrupado else None
        favorito_veces = int(lista_agrupado[0]['veces']) if lista_agrupado else 0

        return jsonify({
            'ok': True,
            'fecha': fecha_str,
            'total_partidas': total,
            'favorito': favorito,
            'favorito_veces': favorito_veces,
            'agrupado': lista_agrupado,
            'detalle': lista_detalle,
            'filtros_aplicados': {
                'actividad': actividad or None,
                'duracion_min': duracion_min,
                'duracion_max': duracion_max,
                'orden': orden,
            },
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Autenticación ─────────────────────────────────────────

_RE_PASS_STRONG = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$')


def _hash_password_bcrypt(plain: str) -> str:
    return bcrypt.hashpw(
        plain.encode('utf-8'), bcrypt.gensalt(rounds=12)
    ).decode('ascii')


def _verify_password_bcrypt(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode('utf-8'), hashed.encode('ascii')
        )
    except Exception:
        return False


def _slug_part(s: str) -> str:
    s = (s or '').strip().lower()
    s = re.sub(r'[^a-z0-9._-]+', '_', s)
    return re.sub(r'_+', '_', s).strip('_')[:72]


def _usuario_session_dict(row) -> dict:
    email = row['email']
    return {
        'id': int(row['id_usuario']),
        'id_usuario': int(row['id_usuario']),
        'nombre': row['nombre'],
        'apellidos': row['apellidos'],
        'email': email,
        'correo': email,
        'rol': _rol_desde_email(email),
        'nombre_usuario': email,
    }


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    body = request.get_json(force=True, silent=True) or {}
    ident = (
        body.get('email')
        or body.get('correo')
        or body.get('nombre_usuario')
        or body.get('login')
        or ''
    ).strip()
    password = body.get('contrasena') or body.get('password') or ''

    if not ident or not password:
        return jsonify({'ok': False, 'error': 'Email y contraseña requeridos'}), 400

    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    """SELECT id_usuario, nombre, apellidos, email, contrasenya
                       FROM users
                       WHERE email = :i OR dni = :i
                       LIMIT 1"""
                ),
                {'i': ident[:255]},
            ).mappings().first()

        if row is None or not _verify_password_bcrypt(password, row['contrasenya']):
            return jsonify({'ok': False, 'error': 'Email o contraseña incorrectos'}), 401

        return jsonify({'ok': True, 'usuario': _usuario_session_dict(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Registro en users. Contraseña: min 8, mayúscula, minúscula, número."""
    body = request.get_json(force=True, silent=True) or {}
    nombre = (body.get('nombre') or '').strip()[:20]
    apellidos = (body.get('apellido') or body.get('apellidos') or '').strip()[:40]
    email = (body.get('correo') or body.get('email') or '').strip()[:255]
    dni = (body.get('dni') or '').strip()[:9] or None
    direccion = (body.get('direccion') or '').strip()[:255] or None
    telefono = (body.get('telefono') or '').strip()[:20] or None
    contrasena = body.get('contrasena') or body.get('password') or ''

    if not nombre or not apellidos:
        return jsonify({'ok': False, 'error': 'Nombre y apellidos obligatorios'}), 400
    if not email or '@' not in email:
        return jsonify({'ok': False, 'error': 'Correo electrónico inválido'}), 400
    if not _RE_PASS_STRONG.match(contrasena):
        return jsonify({
            'ok': False,
            'error': 'La contraseña debe tener mínimo 8 caracteres, mayúscula, minúscula y un número',
        }), 400

    hpw = _hash_password_bcrypt(contrasena)

    try:
        with get_engine().begin() as conn:
            if conn.execute(
                text('SELECT id_usuario FROM users WHERE email = :c LIMIT 1'),
                {'c': email},
            ).first():
                return jsonify({'ok': False, 'error': 'Ese correo ya está registrado'}), 409

            conn.execute(
                text(
                    """INSERT INTO users
                       (nombre, apellidos, email, dni, direccion, telefono, contrasenya)
                       VALUES (:n, :a, :e, :dni, :dir, :tel, :h)"""
                ),
                {
                    'n': nombre,
                    'a': apellidos,
                    'e': email,
                    'dni': dni,
                    'dir': direccion,
                    'tel': telefono,
                    'h': hpw,
                },
            )
            uid = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())
            row = conn.execute(
                text(
                    """SELECT id_usuario, nombre, apellidos, email
                       FROM users WHERE id_usuario = :id"""
                ),
                {'id': uid},
            ).mappings().one()
            return jsonify({'ok': True, 'usuario': _usuario_session_dict(row)}), 201
    except Exception as e:
        if 'Duplicate' in str(e) or '1062' in str(e):
            return jsonify({'ok': False, 'error': 'Ese correo o DNI ya está registrado'}), 409
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Persistencia MySQL (SQLAlchemy) ───────────────────────


@app.route('/api/db/health', methods=['GET'])
def db_health():
    """SELECT 1 — verifica credenciales y red sin escribir datos."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text('SELECT 1'))
        return jsonify({'ok': True, 'database': 'reachable'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 503


@app.route('/api/db/selftest', methods=['POST'])
def db_selftest():
    """
    Inserta filas de prueba en users, actividades, partidas e incidencias,
    las lee con SELECT y las elimina en la misma transacción.
    Requiere ENABLE_DB_SELFTEST=true en .env (no usar en producción expuesta).
    """
    if os.getenv('ENABLE_DB_SELFTEST', 'false').lower() not in ('1', 'true', 'yes'):
        return jsonify({'ok': False, 'error': 'ENABLE_DB_SELFTEST desactivado'}), 403

    suffix = uuid.uuid4().hex[:12]
    email_prueba = f'selftest_{suffix}@patricio.local'
    hpw = _hash_password_bcrypt('Selftest1')

    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO users (nombre, apellidos, email, contrasenya)
                       VALUES ('Test', 'Selftest', :email, :hash)"""
                ),
                {'email': email_prueba, 'hash': hpw},
            )
            uid = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())

            aid = _resolve_actividad_id(conn, {'nombre_juego': 'pilla_pilla'})

            conn.execute(
                text(
                    """INSERT INTO partidas
                       (id_usuario, id_actividad, puntuacion, duracion, detalles_json)
                       VALUES (:uid, :aid, 1.0, 60, NULL)"""
                ),
                {'uid': uid, 'aid': aid},
            )
            pid = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())

            fila_partida = conn.execute(
                text(
                    """SELECT id_partida, id_usuario, id_actividad, puntuacion, duracion
                       FROM partidas WHERE id_partida = :pid"""
                ),
                {'pid': pid},
            ).mappings().one()

            conn.execute(
                text(
                    """INSERT INTO incidencias
                       (id_usuario, tipo, descripcion, resuelto)
                       VALUES (:uid, 'sistema', :desc, 0)"""
                ),
                {
                    'uid': uid,
                    'desc': 'Inserción de prueba desde patricio_api',
                },
            )
            iid = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())

            fila_incidencia = conn.execute(
                text(
                    """SELECT id_incidencia, tipo, descripcion, resuelto
                       FROM incidencias WHERE id_incidencia = :iid"""
                ),
                {'iid': iid},
            ).mappings().one()

            conn.execute(
                text('DELETE FROM incidencias WHERE id_incidencia = :iid'), {'iid': iid}
            )
            conn.execute(text('DELETE FROM partidas WHERE id_partida = :pid'), {'pid': pid})
            conn.execute(text('DELETE FROM users WHERE id_usuario = :uid'), {'uid': uid})

        return jsonify({
            'ok': True,
            'mensaje': 'INSERT y SELECT correctos; filas de prueba eliminadas.',
            'usuario_prueba': email_prueba,
            'partida_insertada_y_leida': dict(fila_partida),
            'incidencia_insertada_y_leida': dict(fila_incidencia),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


def _parse_fecha_query(arg_name: str):
    """Valida YYYY-MM-DD desde query string; devuelve (str, None) o (None, error_msg)."""
    raw = request.args.get(arg_name)
    if not raw:
        return None, None
    try:
        datetime.strptime(raw.strip(), '%Y-%m-%d').date()
        return raw.strip(), None
    except ValueError:
        return None, f'{arg_name} debe ser YYYY-MM-DD'


@app.route('/api/incidencias', methods=['GET'])
def api_listar_incidencias():
    """
    Listado de incidencias para la tabla web.
    Query: fecha (día concreto), fecha_desde, fecha_hasta,
           resuelto (0|1), estado (pendiente|resuelta),
           q (búsqueda en tipo/descripcion).
    """
    fecha, err = _parse_fecha_query('fecha')
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    fecha_desde, err = _parse_fecha_query('fecha_desde')
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    fecha_hasta, err = _parse_fecha_query('fecha_hasta')
    if err:
        return jsonify({'ok': False, 'error': err}), 400

    clauses = []
    params = {}

    if fecha:
        clauses.append('DATE(fecha) = :fecha')
        params['fecha'] = fecha
    else:
        if fecha_desde:
            clauses.append('DATE(fecha) >= :fdesde')
            params['fdesde'] = fecha_desde
        if fecha_hasta:
            clauses.append('DATE(fecha) <= :fhasta')
            params['fhasta'] = fecha_hasta

    resuelto_raw = request.args.get('resuelto')
    if resuelto_raw is not None and str(resuelto_raw).strip() != '':
        try:
            params['resuelto'] = int(resuelto_raw)
            if params['resuelto'] not in (0, 1):
                raise ValueError()
            clauses.append('resuelto = :resuelto')
        except ValueError:
            return jsonify({'ok': False, 'error': 'resuelto debe ser 0 o 1'}), 400
    else:
        estado = (request.args.get('estado') or '').strip().lower()
        if estado in ('pendiente', 'abierta', 'no_resuelta', 'no_resuelto'):
            clauses.append('resuelto = 0')
        elif estado in ('resuelta', 'revisada', 'resuelto'):
            clauses.append('resuelto = 1')

    q = (request.args.get('q') or '').strip()
    if q:
        clauses.append('(tipo LIKE :q OR descripcion LIKE :q)')
        params['q'] = f'%{q[:80]}%'

    where_sql = ' AND '.join(clauses) if clauses else '1=1'

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"""SELECT id_incidencia, id_usuario, tipo, descripcion,
                               resuelto, fecha
                        FROM incidencias
                        WHERE {where_sql}
                        ORDER BY fecha DESC, id_incidencia DESC
                        LIMIT 500"""
                ),
                params,
            ).mappings().all()

        lista = [_incidencia_row_to_dict(r) for r in rows]
        return jsonify({'ok': True, 'incidencias': lista, 'total': len(lista)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/incidencias', methods=['POST'])
def api_crear_incidencia():
    """
    Cuerpo JSON: tipo (obligatorio), descripcion (o titulo + mensaje),
    id_usuario (opcional), severidad (solo para UI, no se persiste).
    """
    body = request.get_json(force=True, silent=True) or {}
    tipo = (body.get('tipo') or '').strip()
    if not tipo:
        return jsonify({'ok': False, 'error': 'tipo requerido (ej. Caída, Batería baja)'}), 400

    descripcion = (body.get('descripcion') or '').strip()
    if not descripcion:
        titulo = (body.get('titulo') or tipo).strip()
        mensaje = (body.get('mensaje') or 'Sin detalle adicional').strip()
        descripcion = f'{titulo}: {mensaje}' if titulo != mensaje else mensaje
    descripcion = descripcion[:255]

    severidad = body.get('severidad', 'aviso')
    if severidad not in ('info', 'aviso', 'critico'):
        severidad = 'aviso'

    id_usuario = body.get('id_usuario', body.get('usuario_id'))
    if id_usuario is not None:
        try:
            id_usuario = int(id_usuario)
        except (TypeError, ValueError):
            id_usuario = None

    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO incidencias
                       (id_usuario, tipo, descripcion, resuelto)
                       VALUES (:uid, :tipo, :desc, 0)"""
                ),
                {
                    'uid': id_usuario,
                    'tipo': tipo[:50],
                    'desc': descripcion,
                },
            )
            new_id = int(conn.execute(text('SELECT LAST_INSERT_ID() AS id')).scalar_one())
            row = conn.execute(
                text(
                    """SELECT id_incidencia, id_usuario, tipo, descripcion,
                              resuelto, fecha
                       FROM incidencias WHERE id_incidencia = :id"""
                ),
                {'id': new_id},
            ).mappings().one()

        payload = _incidencia_row_to_dict(row)
        payload['severidad'] = severidad
        _emit_nueva_incidencia(payload)
        return jsonify({'ok': True, 'incidencia': payload}), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/incidencias/pendientes', methods=['GET'])
def api_incidencias_pendientes():
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT id_incidencia, id_usuario, tipo, descripcion,
                              resuelto, fecha
                       FROM incidencias
                       WHERE resuelto = 0
                       ORDER BY id_incidencia DESC"""
                ),
            ).mappings().all()

        lista = [_incidencia_row_to_dict(r) for r in rows]
        return jsonify({'ok': True, 'incidencias': lista})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/incidencias/<int:iid>/revisar', methods=['POST'])
def api_revisar_incidencia(iid):
    try:
        with get_engine().begin() as conn:
            r = conn.execute(
                text(
                    """UPDATE incidencias
                       SET resuelto = 1
                       WHERE id_incidencia = :id AND resuelto = 0"""
                ),
                {'id': iid},
            )
            if getattr(r, 'rowcount', 0) == 0:
                return jsonify({'ok': False, 'error': 'Incidencia no encontrada o ya revisada'}), 404

        _emit_incidencia_revisada(iid)
        return jsonify({'ok': True, 'id': iid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/escondite/iniciar', methods=['POST'])
def iniciar_escondite():
    body = request.get_json(force=True)
    poses = body.get('poses', [])

    if not poses:
        return jsonify({'success': False, 'error': 'No se enviaron poses'}), 400

    pose_list = [
        {
            'position': {'x': p['x'], 'y': p['y'], 'z': 0.0},
            'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}
        }
        for p in poses
    ]

    result = rosbridge_call_service(
        service='/patricio/escondite/iniciar',
        service_type='patricio_interfaces/srv/IniciarEscondite',
        args={
            'command': 'START',
            'poses': {
                'header': {'frame_id': 'map', 'stamp': {'sec': 0, 'nanosec': 0}},
                'poses': pose_list
            }
        },
        timeout=10.0
    )

    if result['error']:
        return jsonify({'success': False, 'error': result['error']}), 500

    return jsonify({
        'success': result['response'].get('success', False),
        'message': result['response'].get('message', ''),
        'target_pose': result['response'].get('target_pose', {})
    })


@app.route('/api/escondite/detener', methods=['POST'])
def detener_escondite():
    rosbridge_call_service(
        service='/patricio/escondite/iniciar',
        service_type='patricio_interfaces/srv/IniciarEscondite',
        args={
            'command': 'STOP',
            'poses': {
                'header': {'frame_id': 'map', 'stamp': {'sec': 0, 'nanosec': 0}},
                'poses': []
            }
        },
        timeout=5.0
    )
    return jsonify({'stopped': True})


# ── Flask routes — Juego del Calamar ─────────────────────

@app.route('/api/calamar/comando', methods=['POST'])
def calamar_comando():
    """
    Envía un comando al nodo juego_calamar_node.

    Body JSON: { "comando": "START_AUTO" | "CAMBIAR_A_VERDE"
                            | "CAMBIAR_A_ROJO" | "STOP" }
    """
    body = request.get_json(force=True)
    comando = body.get('comando', '').strip().upper()

    comandos_validos = {'START_AUTO', 'CAMBIAR_A_VERDE', 'CAMBIAR_A_ROJO', 'STOP'}
    if comando not in comandos_validos:
        return jsonify({'ok': False, 'error': f'Comando no válido: {comando}'}), 400

    rosbridge_publish(
        topic='/patricio/calamar/cmd',
        msg_type='std_msgs/msg/String',
        data={'data': comando}
    )
    return jsonify({'ok': True, 'comando': comando})


@app.route('/api/calamar/estado', methods=['GET'])
def calamar_estado():
    """Devuelve el último estado y alerta del juego del calamar."""
    with calamar_lock:
        return jsonify({
            'status':        last_calamar_status,
            'alerta':        last_calamar_alerta,
            'alerta_ts':     last_calamar_alerta_ts,
            'pose_detected': last_calamar_pose
        })


# ── Entry point ───────────────────────────────────────────

def on_shutdown():
    print('API shutting down, sending STOP...')
    rosbridge_publish(
        topic='/patricio/pilla_pilla/cmd',
        msg_type='std_msgs/msg/String',
        data={'data': 'STOP'}
    )
    rosbridge_publish(
        topic='/patricio/calamar/cmd',
        msg_type='std_msgs/msg/String',
        data={'data': 'STOP'}
    )
    rosbridge_call_service(
        service='/patricio/escondite/iniciar',
        service_type='patricio_interfaces/srv/IniciarEscondite',
        args={
            'command': 'STOP',
            'poses': {
                'header': {'frame_id': 'map', 'stamp': {'sec': 0, 'nanosec': 0}},
                'poses': []
            }
        }
    )
    time.sleep(1)


if __name__ == '__main__':
    # Status subscribers in background
    threading.Thread(target=rosbridge_subscribe_status, daemon=True).start()
    threading.Thread(target=rosbridge_subscribe_status_escondite, daemon=True).start()
    threading.Thread(target=rosbridge_subscribe_calamar, daemon=True).start()

    print('Starting Patricio API + Socket.IO on http://0.0.0.0:5000')

    atexit.register(on_shutdown)
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)