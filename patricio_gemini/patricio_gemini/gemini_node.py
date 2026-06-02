#!/usr/bin/env python3
"""
Nodo ROS 2 para integrar Google Gemini con Patricio como personalidad infantil.

- Suscribe a /patricio/voice_input para recibir prompts de entrada.
- Consulta Google Gemini usando la clave de API del entorno.
- Publica la respuesta en /patricio/voice_output y /patricio/face_text.
- Verifica la comunicación básica al arrancar si verify_connection está activo.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import requests
import rclpy
from geometry_msgs.msg import PoseArray
from patricio_interfaces.srv import GuardarPartida, IniciarEscondite, StartGame
from rclpy.node import Node
from std_msgs.msg import String

try:
    import google.generativeai as genai
    _GEMINI_SDK = 'google.generativeai'
    _GEMINI_IMPORT_ERROR = None
except ImportError as exc1:
    genai = None
    _GEMINI_SDK = None
    try:
        from google.ai import generativelanguage as genai
        _GEMINI_SDK = 'google.ai.generativelanguage'
        _GEMINI_IMPORT_ERROR = None
    except ImportError as exc2:
        genai = None
        _GEMINI_IMPORT_ERROR = exc2

SYSTEM_PROMPT = (
    'Eres Patricio, un asistente robótico amable, claro y coherente. '
    'Responde directamente a la pregunta del usuario con información relevante y ejemplos concretos. '
    'No termines las respuestas con puntos suspensivos ni frases incompletas; entrega la respuesta completa. '
    'Mantén un tono amistoso y entusiasta, pero evita respuestas vagas. '
    'Si no conoces algo con certeza, dilo con honestidad y ofrece una alternativa útil. '
    'Si el usuario pide noticias o temas interesantes, da una respuesta actual, bien conectada y con sentido. '
    'Si quieres iniciar un juego o registrar una actividad, responde con un JSON exacto del tipo '
    '{"function":"<nombre>","arguments":{...}} y no agregues texto adicional. '
    'Si no es una llamada de función, responde normalmente en texto.'
)

FUNCTIONS_SCHEMA = [
    {
        'name': 'iniciar_juego',
        'description': 'Inicia un juego local en el robot: pilla_pilla, escondite o calamar.',
        'parameters': {
            'type': 'object',
            'properties': {
                'game_name': {
                    'type': 'string',
                    'enum': ['pilla_pilla', 'escondite', 'calamar'],
                    'description': 'Nombre del juego a iniciar.',
                },
                'usuario_id': {
                    'type': 'integer',
                    'description': 'ID de usuario opcional para registro en BBDD.',
                },
                'motivo': {
                    'type': 'string',
                    'description': 'Razón o contexto para el inicio del juego.',
                },
            },
            'required': ['game_name'],
        },
    },
    {
        'name': 'registrar_actividad',
        'description': 'Registra la actividad o partida en la BBDD local a través de /patricio/db/guardar_partida.',
        'parameters': {
            'type': 'object',
            'properties': {
                'nombre_juego': {
                    'type': 'string',
                    'enum': ['pilla_pilla', 'escondite', 'calamar'],
                    'description': 'Nombre del juego registrado.',
                },
                'usuario_id': {
                    'type': 'integer',
                    'description': 'ID de usuario; 0 o negativo para anónimo.',
                },
                'puntuacion': {
                    'type': 'number',
                    'description': 'Puntuación final, o NaN si no aplica.',
                },
                'duracion': {
                    'type': 'integer',
                    'description': 'Duración en segundos.',
                },
                'resultado': {
                    'type': 'string',
                    'description': 'Resultado de la partida: victoria, derrota, abortado.',
                },
                'estado': {
                    'type': 'string',
                    'description': 'Estado del registro: en_curso, finalizado_ok, abortado.',
                },
                'detalles_json': {
                    'type': 'string',
                    'description': 'JSON con metadatos extra (poses, eventos, etc.).',
                },
            },
            'required': ['nombre_juego'],
        },
    },
]

DEFAULT_PROMPT = 'Hola Patricio, cuéntame algo corto y feliz.'


def _clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip())


def _normalize_response_text(text: str) -> str:
    if not text:
        return ''
    text = text.strip()
    # Replace ellipsis or spaced dot sequences with a single period.
    text = re.sub(r'(?:\s*(?:\.{2,}|…)+\s*)+', '. ', text)
    # Also collapse any remaining long dot sequences into a single period.
    text = re.sub(r'\.{2,}', '.', text)
    # Normalize repeated punctuation like '??', '!!' or '?!'.
    text = re.sub(r'([.?!]){2,}', r'\1', text)
    text = re.sub(r'([.?!])\s+', r'\1 ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if text and not re.search(r'[.?!]$', text):
        text += '.'
    return text


class GeminiClient:
    def __init__(self, api_key: str, model_name: str, api_key_env_var: str) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.api_key_env_var = api_key_env_var
        self.service = (
            'nim' if api_key_env_var == 'NIM_API_KEY' or api_key.startswith('nvapi-') else 'gemini'
        )

        if self.service == 'nim':
            self._client = None
            self._nim_url = 'https://integrate.api.nvidia.com/v1/chat/completions'
            return

        if genai is None:
            raise RuntimeError(
                'No se encontró el SDK de Gemini. Instala google-generativeai o google-ai, o usa NIM_API_KEY para Nvidia NIM.'
            )

        self.sdk = _GEMINI_SDK
        if self.sdk == 'google.generativeai':
            genai.configure(api_key=self.api_key)
        elif self.sdk == 'google.ai.generativelanguage':
            os.environ.setdefault('GOOGLE_API_KEY', self.api_key)
            self._client = genai.TextServiceClient()
        else:
            raise RuntimeError('SDK Gemini inválido o no compatible.')

    def generate_reply(self, user_prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        prompt = _clean_text(user_prompt)
        if not prompt:
            return {'text': '', 'function_call': None}

        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ]

        if self.service == 'nim':
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
            payload = {
                'model': self.model_name,
                'messages': messages,
                'temperature': float(temperature),
                'max_tokens': int(max_tokens),
                'functions': FUNCTIONS_SCHEMA,
                'function_call': 'auto',
            }
            response = requests.post(self._nim_url, headers=headers, json=payload, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f'NIM API error: {response.status_code} {response.text}')
            return self._parse_response(response.json())

        if self.sdk == 'google.generativeai':
            payload = messages
            if hasattr(genai, 'chat'):
                try:
                    response = genai.chat.create(
                        model=self.model_name,
                        messages=payload,
                        temperature=float(temperature),
                        max_output_tokens=int(max_tokens),
                        functions=FUNCTIONS_SCHEMA,
                        function_call='auto',
                    )
                except TypeError:
                    response = genai.chat.create(
                        model=self.model_name,
                        messages=payload,
                        temperature=float(temperature),
                        max_output_tokens=int(max_tokens),
                    )
            else:
                response = genai.generate_text(
                    model=self.model_name,
                    prompt=SYSTEM_PROMPT + '\n' + prompt,
                    temperature=float(temperature),
                    max_output_tokens=int(max_tokens),
                )
        else:
            text_prompt = genai.TextPrompt(
                text=SYSTEM_PROMPT + '\n' + prompt,
            )
            response = self._client.generate_text(
                model=self.model_name,
                prompt=text_prompt,
                temperature=float(temperature),
                max_output_tokens=int(max_tokens),
            )

        return self._parse_response(response)

    @staticmethod
    def _parse_json_from_text(text: str) -> Any | None:
        if not isinstance(text, str) or not text.strip():
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for match in re.finditer(r'\{', text):
                try:
                    obj, _ = decoder.raw_decode(text[match.start():])
                    return obj
                except json.JSONDecodeError:
                    continue
        return None

    @staticmethod
    def _extract_raw_function_call(message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return None
        function_call = message.get('function_call') or message.get('tool') or message.get('tool_call')
        if isinstance(function_call, dict):
            arguments = function_call.get('arguments')
            if isinstance(arguments, str):
                parsed = GeminiClient._parse_json_from_text(arguments)
                if isinstance(parsed, dict):
                    function_call['arguments'] = parsed
            return function_call if function_call.get('name') else None
        if isinstance(function_call, str):
            parsed = GeminiClient._parse_json_from_text(function_call)
            if isinstance(parsed, dict) and parsed.get('function'):
                return parsed
        return None

    @staticmethod
    def _parse_response(response: Any) -> dict[str, Any]:
        if response is None:
            return {'text': '', 'function_call': None}

        if hasattr(response, 'to_dict'):
            try:
                response = response.to_dict()
            except Exception:
                pass

        text = ''
        function_call = None

        if isinstance(response, dict):
            choices = response.get('choices')
            if choices and isinstance(choices, list) and choices:
                message = choices[0].get('message') or choices[0]
                if isinstance(message, dict):
                    function_call = GeminiClient._extract_raw_function_call(message)
                    content = message.get('content')
                    if isinstance(content, str):
                        text = content
            if not text:
                text = response.get('text') or response.get('output')
                if isinstance(text, dict):
                    text = text.get('content')
            if isinstance(text, list) and text:
                text = text[0]
            if not isinstance(text, str):
                text = str(text) if text is not None else ''

        elif hasattr(response, 'last'):
            last = getattr(response, 'last')
            text = getattr(last, 'content', str(last)) if last is not None else ''
        elif hasattr(response, 'output'):
            output = getattr(response, 'output')
            if isinstance(output, dict):
                text = output.get('content', '')
            elif isinstance(output, list) and output:
                text = getattr(output[0], 'content', str(output[0]))
            else:
                text = str(output)
        elif hasattr(response, 'candidates'):
            candidates = getattr(response, 'candidates')
            if candidates:
                text = getattr(candidates[0], 'content', str(candidates[0]))
        else:
            text = getattr(response, 'text', None)
            if not isinstance(text, str):
                text = str(response)

        text = _clean_text(text)
        if function_call is None:
            parsed_json = GeminiClient._parse_json_from_text(text)
            if isinstance(parsed_json, dict) and parsed_json.get('function'):
                function_call = parsed_json
                text = ''

        return {'text': text, 'function_call': function_call}


class GeminiNode(Node):
    def __init__(self) -> None:
        super().__init__('patricio_gemini_node')

        self.declare_parameter('voice_input_topic', '/patricio/voice_input')
        self.declare_parameter('voice_output_topic', '/patricio/voice_output')
        self.declare_parameter('face_text_topic', '/patricio/face_text')
        self.declare_parameter('status_topic', '/patricio/gemini_status')
        self.declare_parameter('model_name', 'meta/llama-3.1-8b-instruct')
        self.declare_parameter('api_key_env_var', 'NIM_API_KEY')
        self.declare_parameter('verify_connection', True)
        self.declare_parameter('verify_prompt', DEFAULT_PROMPT)
        self.declare_parameter('response_max_tokens', 512)
        self.declare_parameter('response_temperature', 0.8)

        self.voice_input_topic = self.get_parameter('voice_input_topic').value
        self.voice_output_topic = self.get_parameter('voice_output_topic').value
        self.face_text_topic = self.get_parameter('face_text_topic').value
        self.status_topic = self.get_parameter('status_topic').value
        self.model_name = self.get_parameter('model_name').value
        self.api_key_env_var = self.get_parameter('api_key_env_var').value
        self.verify_connection = self.get_parameter('verify_connection').value
        self.verify_prompt = self.get_parameter('verify_prompt').value
        self.max_tokens = self.get_parameter('response_max_tokens').value
        self.temperature = self.get_parameter('response_temperature').value

        self._pub_voice = self.create_publisher(String, self.voice_output_topic, 10)
        self._pub_face = self.create_publisher(String, self.face_text_topic, 10)
        self._pub_status = self.create_publisher(String, self.status_topic, 10)
        self._start_game_client = self.create_client(StartGame, '/start_game')
        self._escondite_client = self.create_client(IniciarEscondite, '/patricio/escondite/iniciar')
        self._db_client = self.create_client(GuardarPartida, '/patricio/db/guardar_partida')
        self._calamar_pub = self.create_publisher(String, '/patricio/calamar/cmd', 10)
        self.create_subscription(String, self.voice_input_topic, self._on_input, 10)

        self.get_logger().info('Inicializando nodo de Patricio con IA...')
        api_key = self._load_api_key()
        if api_key is None:
            self.get_logger().error(
                'No se pudo iniciar la IA porque falta la clave de API. '
                f'Configura {self.api_key_env_var} o GOOGLE_API_KEY.'
            )
            return

        try:
            self._client = GeminiClient(api_key, self.model_name, self.api_key_env_var)
        except Exception as exc:
            self.get_logger().error(f'Error inicializando la IA: {exc}')
            return

        self.get_logger().info(
            f'Gemini listo con modelo={self.model_name}. ' 
            f'Entrada={self.voice_input_topic}, voz={self.voice_output_topic}, pantalla={self.face_text_topic}'
        )

        if self.verify_connection:
            self._verify_connection_to_service()

    def _load_api_key(self) -> str | None:
        api_key = (
            os.environ.get(self.api_key_env_var)
            or os.environ.get('NIM_API_KEY')
            or os.environ.get('GEMINI_API_KEY')
            or os.environ.get('GOOGLE_API_KEY')
        )
        return _clean_text(api_key) or None

    def _verify_connection_to_service(self) -> None:
        self._publish_status('verificando')
        try:
            self.get_logger().info('Verificando comunicación con la IA...')
            response = self._client.generate_reply(
                self.verify_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            text = response.get('text') if isinstance(response, dict) else ''
            if text:
                self.get_logger().info(f'Respuesta de verificación: "{text}"')
                self._publish_status('verificado')
                self._publish_faces_and_voice(text)
            else:
                self.get_logger().warn('Gemini devolvió respuesta vacía en la verificación.')
                self._publish_status('verificacion_fallida')
        except Exception as exc:
            self.get_logger().error(f'Error en verificación Gemini: {exc}')
            self._publish_status('verificacion_error')

    def _on_input(self, msg: String) -> None:
        prompt = _clean_text(msg.data)
        if not prompt:
            self.get_logger().warn('Se recibió un prompt vacío en /patricio/voice_input.')
            self._publish_status('input_vacio')
            return

        self._publish_status('procesando')
        self.get_logger().info(f'Recibido prompt de voz: "{prompt}"')

        try:
            result = self._client.generate_reply(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            self.get_logger().error(f'Error al consultar Gemini: {exc}')
            self._publish_status('error_api')
            return

        if not result or not isinstance(result, dict):
            self.get_logger().warn('Gemini devolvió respuesta vacía o inesperada.')
            self._publish_status('respuesta_vacia')
            return

        function_call = result.get('function_call')
        if function_call:
            self.get_logger().info(f'Función solicitada por IA: {function_call.get("name")}.')
            response_text = self._handle_function_call(function_call)
            self._publish_faces_and_voice(response_text)
            self._publish_status('funcion_ejecutada')
            return

        answer = result.get('text', '')
        if not answer:
            self.get_logger().warn('Gemini devolvió una respuesta sin texto.')
            self._publish_status('respuesta_vacia')
            return

        self._publish_faces_and_voice(answer)
        self._publish_status('respuesta_publicada')

    def _publish_faces_and_voice(self, text: str) -> None:
        raw_text = text
        text = _normalize_response_text(text)
        if raw_text != text:
            self.get_logger().info(
                f'Respuesta normalizada: {repr(raw_text[:180])} -> {repr(text[:180])}'
            )
        voice_msg = String()
        voice_msg.data = text
        face_msg = String()
        face_msg.data = text
        self._pub_voice.publish(voice_msg)
        self._pub_face.publish(face_msg)
        self.get_logger().info(
            f'Publicado a voz (len={len(text)}) y pantalla (len={len(text)})'
        )

    def _publish_status(self, status: str) -> None:
        msg = String()
        msg.data = status
        self._pub_status.publish(msg)

    def _handle_function_call(self, function_call: dict[str, Any]) -> str:
        name = (function_call.get('name') or '').strip()
        arguments = function_call.get('arguments') or {}
        if isinstance(arguments, str):
            parsed_args = GeminiClient._parse_json_from_text(arguments)
            if isinstance(parsed_args, dict):
                arguments = parsed_args
        if not isinstance(arguments, dict):
            arguments = {}

        if name == 'iniciar_juego':
            return self._execute_iniciar_juego(arguments)

        if name == 'registrar_actividad':
            return self._execute_registrar_actividad(arguments)

        return f'No conozco la función {name}. Usa iniciar_juego o registrar_actividad.'

    def _execute_iniciar_juego(self, arguments: dict[str, Any]) -> str:
        game_name = (arguments.get('game_name') or '').strip().lower()
        if game_name not in ('pilla_pilla', 'escondite', 'calamar'):
            return (
                'Nombre de juego inválido. Debe ser uno de: pilla_pilla, escondite, calamar.'
            )

        if game_name == 'pilla_pilla':
            return self._call_start_game_service('pilla_pilla')

        if game_name == 'escondite':
            return self._call_escondite_service()

        return self._publish_calamar_cmd('START_AUTO')

    def _execute_registrar_actividad(self, arguments: dict[str, Any]) -> str:
        nombre_juego = (arguments.get('nombre_juego') or '').strip().lower()
        if nombre_juego not in ('pilla_pilla', 'escondite', 'calamar'):
            return (
                'Nombre de juego inválido para registro. Usa pilla_pilla, escondite o calamar.'
            )

        request = GuardarPartida.Request()
        request.nombre_juego = nombre_juego
        request.usuario_id = int(arguments.get('usuario_id') or 0)

        puntuacion = arguments.get('puntuacion')
        if isinstance(puntuacion, str):
            puntuacion = puntuacion.strip()
            if puntuacion.lower() in ('nan', 'none', 'null', ''):
                request.puntuacion = float('nan')
            else:
                try:
                    request.puntuacion = float(puntuacion)
                except ValueError:
                    request.puntuacion = float('nan')
        elif isinstance(puntuacion, (int, float)):
            request.puntuacion = float(puntuacion)
        else:
            request.puntuacion = float('nan')

        request.duracion = int(arguments.get('duracion') or 0)
        request.resultado = str(arguments.get('resultado') or '').strip()
        request.estado = str(arguments.get('estado') or 'finalizado_ok').strip()
        request.detalles_json = str(arguments.get('detalles_json') or '').strip()

        if not self._wait_for_service(self._db_client, '/patricio/db/guardar_partida'):
            return 'No se pudo conectar al servicio de base de datos para registrar la actividad.'

        future = self._db_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done():
            return 'El servicio de registro no respondió a tiempo.'

        response = future.result()
        if not response or not getattr(response, 'success', False):
            return (
                'Fallo al registrar la actividad: '
                + (getattr(response, 'message', 'respuesta inválida') or '')
            )

        return f'Actividad registrada correctamente (id={getattr(response, "id_partida", 0)}).'

    def _call_start_game_service(self, game_name: str) -> str:
        if not self._wait_for_service(self._start_game_client, '/start_game'):
            return 'El servicio de inicio de juego no está disponible en este momento.'

        request = StartGame.Request()
        request.game_name = game_name
        future = self._start_game_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done():
            return 'No se recibió respuesta del juego pilla_pilla a tiempo.'

        response = future.result()
        if not response or not getattr(response, 'started', False):
            return f'No se pudo iniciar {game_name} en el robot.'

        return f'Juego {game_name} iniciado correctamente.'

    def _call_escondite_service(self) -> str:
        if not self._wait_for_service(self._escondite_client, '/patricio/escondite/iniciar'):
            return 'El servicio de escondite no está disponible en este momento.'

        request = IniciarEscondite.Request()
        request.command = 'START'
        request.poses = PoseArray()
        future = self._escondite_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done():
            return 'No se recibió respuesta del servicio de escondite a tiempo.'

        response = future.result()
        if not response or not getattr(response, 'success', False):
            return 'No se pudo iniciar escondite en el robot.'

        return 'Juego de escondite iniciado correctamente.'

    def _publish_calamar_cmd(self, command: str) -> str:
        msg = String()
        msg.data = command
        self._calamar_pub.publish(msg)
        return 'Juego del calamar iniciado.'

    def _wait_for_service(self, client, service_name: str, timeout: float = 3.0) -> bool:
        if client.wait_for_service(timeout_sec=timeout):
            return True
        self.get_logger().warn(f'Servicio {service_name} no disponible.')
        return False


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GeminiNode()
    try:
        if getattr(node, '_client', None) is not None:
            rclpy.spin(node)
        else:
            node.get_logger().error(
                'El nodo Gemini no se inicializó correctamente. Comprueba la clave de API y las dependencias.'
            )
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
