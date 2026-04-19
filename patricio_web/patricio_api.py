#!/usr/bin/env python3
"""
Flask API for Patricio web — bridges HTTP to ROS 2 via rosbridge WebSocket.
No rclpy or patricio_interfaces needed.

Endpoints:
  POST /api/juego/iniciar   → calls /start_game service via rosbridge
  POST /api/juego/detener   → publishes STOP to /patricio/pilla_pilla/cmd
  GET  /api/juego/estado    → returns last known status
"""

import json
import threading
import time
import uuid
import atexit

import websocket  # pip install websocket-client
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ROSBRIDGE_URL = 'ws://localhost:9090'
last_status = 'Descansando'
status_lock = threading.Lock()


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
        time.sleep(3)  # wait before reconnecting

    def on_close(ws, *args):
        print('Status subscriber closed, reconnecting...')
        time.sleep(3)
        rosbridge_subscribe_status()  # reconnect

    ws = websocket.WebSocketApp(
        ROSBRIDGE_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()
    
def rosbridge_subscribe_status_escondite():
    global last_status  # puedes reutilizar la misma variable o crear last_status_escondite

    def on_message(ws, message):
        global last_status
        msg = json.loads(message)
        if msg.get('op') == 'publish':
            with status_lock:
                last_status = msg.get('msg', {}).get('data', last_status)

    def on_open(ws):
        payload = {
            'op': 'subscribe',
            'topic': '/patricio/escondite/status',   # ← tópico del escondite
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


# ── Flask routes ──────────────────────────────────────────

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
    

@app.route('/api/escondite/iniciar', methods=['POST'])
def iniciar_escondite():
    body = request.get_json(force=True)
    poses = body.get('poses', [])

    if not poses:
        return jsonify({'success': False, 'error': 'No se enviaron poses'}), 400

    # Construir el PoseArray para el servicio
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
            'poses': {'header': {'frame_id': 'map', 'stamp': {'sec': 0, 'nanosec': 0}}, 'poses': []}
        },
        timeout=5.0
    )
    return jsonify({'stopped': True})


# ── Entry point ───────────────────────────────────────────

def on_shutdown():
    print('API shutting down, sending STOP...')
    rosbridge_publish(
        topic='/patricio/pilla_pilla/cmd',
        msg_type='std_msgs/msg/String',
        data={'data': 'STOP'}
    )
    rosbridge_call_service(
        service='/patricio/escondite/iniciar',
        service_type='patricio_interfaces/srv/IniciarEscondite',
        args={'command': 'STOP', 'poses': {'header': {'frame_id': 'map', 'stamp': {'sec': 0, 'nanosec': 0}}, 'poses': []}}
    )
    time.sleep(1)

if __name__ == '__main__':
    # Start status subscriber in background
    sub_thread = threading.Thread(target=rosbridge_subscribe_status, daemon=True)
    sub_thread.start()
    sub_thread_escondite = threading.Thread(target=rosbridge_subscribe_status_escondite, daemon=True)
    sub_thread_escondite.start()

    print('Starting Patricio API on http://0.0.0.0:5000')

    atexit.register(on_shutdown)
    app.run(host='0.0.0.0', port=5000)