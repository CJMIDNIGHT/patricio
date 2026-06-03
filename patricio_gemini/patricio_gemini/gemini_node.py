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
import threading
import time
from typing import Any

import requests
import rclpy
from geometry_msgs.msg import Point, Pose, PoseArray, Quaternion
from patricio_interfaces.srv import GuardarPartida, IniciarEscondite, StartGame
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
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
    'Eres Patricio, un asistente robótico amable, claro y coherente que habla con niños de 4 a 6 años. '
    'Responde directamente a la pregunta del usuario con información relevante y ejemplos concretos. '
    'No termines las respuestas con puntos suspensivos ni frases incompletas; entrega la respuesta completa. '
    'Mantén un tono amistoso y entusiasta, pero evita respuestas vagas. '
    'Si no conoces algo con certeza, dilo con honestidad y ofrece una alternativa útil. '
    'Si el usuario pide noticias o temas interesantes, da una respuesta actual, bien conectada y con sentido. '
    'Solo existen DOS herramientas (tools) y no hay ninguna más: iniciar_juego (para empezar '
    'pilla_pilla, escondite o calamar) y registrar_actividad (para guardar en la base de datos el '
    'RESULTADO de una partida ya terminada). '
    'Usa iniciar_juego SOLO cuando el niño quiera jugar a uno de esos tres juegos. '
    'Para CUALQUIER otra cosa (chistes, cuentos, adivinanzas, preguntas, saludos, matemáticas, etc.) '
    'CUENTA o RESPONDE el contenido SIEMPRE con texto normal (por ejemplo, si te piden un chiste, '
    'cuéntalo de verdad). NO llames a registrar_actividad para chistes/cuentos/conversaciones: el '
    'sistema registra esas interacciones automáticamente. Y NUNCA inventes funciones que no existen '
    '(no uses nombres como contar_chiste, contar_cuento, etc.). '
    'Si tu motor de IA no soporta herramientas nativas, y solo si se trata de uno de los tres juegos, '
    'responde con un JSON exacto del tipo {"function":"<iniciar_juego|registrar_actividad>","arguments":{...}} '
    'y nada más. En el resto de casos, responde normalmente en texto.'
)

# Prompt para respuestas de texto puro (sin herramientas), usado como respaldo
# cuando la petición no tiene relación con los juegos.
SYSTEM_PROMPT_TEXT_ONLY = (
    'Eres Patricio, un asistente robótico amable y entusiasta que habla con niños de 4 a 6 años. '
    'Responde de forma clara, breve y completa a lo que te pidan (chistes, cuentos, preguntas, etc.). '
    'No invoques funciones ni devuelvas JSON: responde siempre en texto natural y cercano para un niño.'
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
        'description': (
            'Registra en la base de datos una actividad realizada con el niño a través de '
            '/patricio/db/guardar_partida. Sirve tanto para partidas de juego como para '
            'interacciones conversacionales (un chiste contado, un cuento, una conversación, '
            'una adivinanza, etc.).'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'tipo': {
                    'type': 'string',
                    'description': (
                        'Tipo o nombre de la actividad. Ej.: "chiste", "cuento", "adivinanza", '
                        '"conversacion", "pilla_pilla", "escondite", "calamar".'
                    ),
                },
                'puntos': {
                    'type': 'number',
                    'description': 'Puntuación obtenida. 0 si no aplica (p. ej. en conversaciones).',
                },
                'duracion': {
                    'type': 'integer',
                    'description': 'Duración en segundos (0 si no aplica).',
                },
                'resultado': {
                    'type': 'string',
                    'description': 'Resultado opcional: victoria, derrota, abortado.',
                },
                'detalles_json': {
                    'type': 'string',
                    'description': 'JSON opcional con metadatos extra.',
                },
            },
            'required': ['tipo'],
        },
    },
]

# Esquema en formato moderno de "tools" (OpenAI / NVIDIA NIM). Se deriva del
# mismo FUNCTIONS_SCHEMA para no duplicar las declaraciones: cada función queda
# envuelta como {"type": "function", "function": {...}}.
TOOLS_SCHEMA = [{'type': 'function', 'function': fn} for fn in FUNCTIONS_SCHEMA]

# Nombres de las únicas funciones reales que el router sabe ejecutar. Cualquier
# otra "función" que devuelva la IA se trata como alucinación y se responde como
# texto generativo normal.
KNOWN_FUNCTIONS = {'iniciar_juego', 'registrar_actividad'}

# Posiciones candidatas (en metros, marco "map") donde el robot buscará al
# iniciar el escondite desde la IA. El servicio elige una de ellas al azar.
# Edita esta lista para cambiar los escondites; cada entrada es (x, y).
ESCONDITE_SEARCH_POSES = [
    (1.0, 0.5),
    (-1.0, 1.0),
    (0.5, -1.5),
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

    def generate_reply(
        self,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        use_tools: bool = True,
    ) -> dict[str, Any]:
        prompt = _clean_text(user_prompt)
        if not prompt:
            return {'text': '', 'function_call': None}

        # Con use_tools=False forzamos una respuesta de texto plano (sin
        # herramientas). Se usa para responder como IA generativa normal
        # cuando la petición no tiene que ver con los juegos.
        system_prompt = SYSTEM_PROMPT if use_tools else SYSTEM_PROMPT_TEXT_ONLY
        messages = [
            {'role': 'system', 'content': system_prompt},
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
            }
            if use_tools:
                # Formato moderno de herramientas: la IA decide cuándo invocarlas
                # (tool_choice="auto"). NIM devuelve las llamadas en
                # message.tool_calls cuando finish_reason == "tool_calls".
                payload['tools'] = TOOLS_SCHEMA
                payload['tool_choice'] = 'auto'
            response = requests.post(self._nim_url, headers=headers, json=payload, timeout=30)
            # Si el modelo no soporta herramientas nativas, NIM responde 400.
            # En ese caso reintentamos sin "tools" y dejamos que el modelo use el
            # mecanismo de respaldo (JSON-en-texto definido en SYSTEM_PROMPT).
            if response.status_code == 400 and 'tool' in response.text.lower():
                payload.pop('tools', None)
                payload.pop('tool_choice', None)
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

        # Formato moderno de NIM/OpenAI: message.tool_calls es una lista de
        # {"id":..., "type":"function", "function":{"name":..., "arguments": "<json string>"}}.
        tool_calls = message.get('tool_calls')
        if isinstance(tool_calls, list) and tool_calls:
            first = tool_calls[0]
            fn = first.get('function') if isinstance(first, dict) else None
            if isinstance(fn, dict) and fn.get('name'):
                arguments = fn.get('arguments')
                if isinstance(arguments, str):
                    parsed = GeminiClient._parse_json_from_text(arguments)
                    arguments = parsed if isinstance(parsed, dict) else {}
                elif not isinstance(arguments, dict):
                    arguments = {}
                return {'name': fn['name'], 'arguments': arguments}

        # Formato antiguo (function_call) y otras variantes.
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
        self.declare_parameter('api_key', '')
        self.declare_parameter('verify_connection', True)
        self.declare_parameter('verify_prompt', DEFAULT_PROMPT)
        self.declare_parameter('response_max_tokens', 512)
        self.declare_parameter('response_temperature', 0.8)
        # Registrar automáticamente en la BBDD las interacciones conversacionales
        # (chistes, cuentos, conversaciones) que hace la IA.
        self.declare_parameter('registrar_conversaciones', True)

        self.voice_input_topic = self.get_parameter('voice_input_topic').value
        self.voice_output_topic = self.get_parameter('voice_output_topic').value
        self.face_text_topic = self.get_parameter('face_text_topic').value
        self.status_topic = self.get_parameter('status_topic').value
        self.model_name = self.get_parameter('model_name').value
        self.api_key_env_var = self.get_parameter('api_key_env_var').value
        self.api_key_param = self.get_parameter('api_key').value
        self.verify_connection = self.get_parameter('verify_connection').value
        self.verify_prompt = self.get_parameter('verify_prompt').value
        self.max_tokens = self.get_parameter('response_max_tokens').value
        self.temperature = self.get_parameter('response_temperature').value
        self.registrar_conversaciones = self.get_parameter('registrar_conversaciones').value

        # Grupo de callbacks reentrante: permite que las respuestas de los
        # servicios se procesen mientras el callback de voz sigue esperando,
        # evitando el error "Executor is already spinning" (requiere ejecutor
        # multihilo, configurado en main()).
        self._cb_group = ReentrantCallbackGroup()

        self._pub_voice = self.create_publisher(String, self.voice_output_topic, 10)
        self._pub_face = self.create_publisher(String, self.face_text_topic, 10)
        self._pub_status = self.create_publisher(String, self.status_topic, 10)
        self._start_game_client = self.create_client(
            StartGame, '/start_game', callback_group=self._cb_group)
        self._escondite_client = self.create_client(
            IniciarEscondite, '/patricio/escondite/iniciar', callback_group=self._cb_group)
        self._db_client = self.create_client(
            GuardarPartida, '/patricio/db/guardar_partida', callback_group=self._cb_group)
        self._calamar_pub = self.create_publisher(String, '/patricio/calamar/cmd', 10)
        self.create_subscription(
            String, self.voice_input_topic, self._on_input, 10,
            callback_group=self._cb_group)

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
        # Prioridad: parámetro ROS explícito > variables de entorno.
        api_key = (
            self.api_key_param
            or os.environ.get(self.api_key_env_var)
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
        t0 = time.monotonic()

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
            fn_name = (function_call.get('name') or function_call.get('function') or '').strip()
            if fn_name in KNOWN_FUNCTIONS:
                self.get_logger().info(f'Función solicitada por IA: {fn_name}.')
                response_text = self._handle_function_call(function_call)
                self._publish_faces_and_voice(response_text)
                self._publish_status('funcion_ejecutada')
                return
            # La IA "alucinó" una función inexistente (p.ej. contar_chiste).
            # No es un juego: respondemos como IA generativa normal.
            self.get_logger().warn(
                f'La IA pidió una función desconocida ("{fn_name}"); respondo en texto normal.'
            )
            answer = self._generate_plain_text(prompt)
            if answer:
                self._publish_faces_and_voice(answer)
                self._publish_status('respuesta_publicada')
                self._auto_registrar_conversacion(prompt, answer, time.monotonic() - t0)
            else:
                self.get_logger().warn('No se pudo generar respuesta de texto alternativa.')
                self._publish_status('respuesta_vacia')
            return

        answer = result.get('text', '')
        if not answer:
            self.get_logger().warn('Gemini devolvió una respuesta sin texto.')
            self._publish_status('respuesta_vacia')
            return

        self._publish_faces_and_voice(answer)
        self._publish_status('respuesta_publicada')
        self._auto_registrar_conversacion(prompt, answer, time.monotonic() - t0)

    def _generate_plain_text(self, prompt: str) -> str:
        """Pide a la IA una respuesta de texto puro (sin herramientas).

        Se usa cuando la petición no tiene que ver con los juegos para que
        Patricio responda como una IA generativa normal (chistes, cuentos,
        preguntas, etc.).
        """
        try:
            result = self._client.generate_reply(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                use_tools=False,
            )
        except Exception as exc:
            self.get_logger().error(f'Error al generar respuesta de texto: {exc}')
            return ''
        if isinstance(result, dict):
            return result.get('text', '') or ''
        return ''

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
        # "name" lo usa el tool calling nativo; "function" lo usa el respaldo
        # JSON-en-texto ({"function": "...", "arguments": {...}}).
        name = (function_call.get('name') or function_call.get('function') or '').strip()
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
            mensaje = self._call_start_game_service('pilla_pilla')
        elif game_name == 'escondite':
            mensaje = self._call_escondite_service()
        else:
            mensaje = self._publish_calamar_cmd('START_AUTO')

        # Si el juego arrancó bien, registramos el inicio en la BBDD.
        low = mensaje.lower()
        if 'correctamente' in low or 'iniciado' in low:
            self._registrar_inicio_juego(game_name, arguments)
        return mensaje

    def _registrar_inicio_juego(self, game_name: str, arguments: dict[str, Any]) -> None:
        """Registra en la BBDD que se ha iniciado un juego."""
        detalles = {'evento': 'inicio_juego', 'motivo': str(arguments.get('motivo') or '')}
        # usuario_id=0 (anónimo): la IA no debe asociar usuarios, y un ID
        # inventado rompería la clave foránea de la tabla partidas.
        success, message, id_partida = self._registrar_en_bbdd(
            tipo=game_name,
            estado='iniciado',
            usuario_id=0,
            detalles=detalles,
        )
        if success:
            self.get_logger().info(
                f'Inicio del juego "{game_name}" registrado en BBDD (id_partida={id_partida}).'
            )
        else:
            self.get_logger().warn(f'No se registró el inicio del juego: {message}')

    def _execute_registrar_actividad(self, arguments: dict[str, Any]) -> str:
        # Acepta 'tipo' (nuevo, admite juegos y conversaciones) y, por
        # compatibilidad, 'nombre_juego'. 'puntos' o 'puntuacion'.
        tipo = (arguments.get('tipo') or arguments.get('nombre_juego') or '').strip().lower()
        if not tipo:
            return 'Falta el tipo de actividad a registrar (p. ej. "chiste" o "pilla_pilla").'

        puntos = arguments.get('puntos', arguments.get('puntuacion'))
        success, message, id_partida = self._registrar_en_bbdd(
            tipo=tipo,
            puntos=puntos,
            duracion=arguments.get('duracion') or 0,
            # Anónimo: evitamos IDs de usuario inventados por la IA (FK partidas).
            usuario_id=0,
            resultado=str(arguments.get('resultado') or '').strip(),
            estado=str(arguments.get('estado') or 'finalizado_ok').strip(),
            detalles=arguments.get('detalles_json') or arguments.get('detalles'),
        )
        if not success:
            return f'Fallo al registrar la actividad: {message}'
        return f'Actividad "{tipo}" registrada correctamente (id={id_partida}).'

    @staticmethod
    def _clasificar_tipo_conversacion(prompt: str) -> str:
        """Deduce el 'tipo' de actividad conversacional a partir de la petición."""
        p = (prompt or '').lower()
        if 'chiste' in p:
            return 'chiste'
        if 'cuento' in p or 'historia' in p:
            return 'cuento'
        if 'adivina' in p or 'adivinanza' in p:
            return 'adivinanza'
        if 'cancion' in p or 'canción' in p or 'cántame' in p or 'cantame' in p:
            return 'cancion'
        return 'conversacion'

    def _auto_registrar_conversacion(self, prompt: str, answer: str, duracion: float) -> None:
        """Registra automáticamente en la BBDD la interacción conversacional.

        Mapeo conversacional: cuando la IA responde con texto (un chiste, un
        cuento, una conversación...), se registra la actividad con el tipo
        correspondiente, sin intervención del usuario.
        """
        if not self.registrar_conversaciones:
            return
        # Si el servidor de BBDD no está, no penalizamos la conversación.
        if not self._db_client.service_is_ready():
            self.get_logger().debug('BBDD no disponible; no se registra la conversación.')
            return

        tipo = self._clasificar_tipo_conversacion(prompt)
        detalles = {
            'categoria': 'conversacion',
            'pregunta': (prompt or '')[:200],
            'respuesta_chars': len(answer or ''),
        }
        success, message, id_partida = self._registrar_en_bbdd(
            tipo=tipo,
            puntos=float('nan'),
            duracion=int(round(duracion)),
            detalles=detalles,
        )
        if success:
            self.get_logger().info(
                f'Actividad conversacional "{tipo}" registrada en BBDD (id_partida={id_partida}).'
            )
            self._publish_status('actividad_registrada')
        else:
            self.get_logger().warn(f'No se registró la conversación: {message}')

    def _registrar_en_bbdd(
        self,
        tipo: str,
        puntos: Any = None,
        duracion: Any = 0,
        usuario_id: Any = 0,
        resultado: str = '',
        estado: str = 'finalizado_ok',
        detalles: Any = None,
    ) -> tuple[bool, str, int]:
        """Empaqueta los datos de una actividad y llama al servicio de BBDD.

        Reutilizado tanto por la herramienta registrar_actividad como por el
        registro automático de las interacciones conversacionales.
        Devuelve (success, message, id_partida).
        """
        request = GuardarPartida.Request()
        request.nombre_juego = (tipo or '').strip()
        request.usuario_id = int(usuario_id or 0)

        # puntos -> puntuacion (NaN = no aplica).
        if isinstance(puntos, str):
            p = puntos.strip().lower()
            if p in ('', 'nan', 'none', 'null'):
                request.puntuacion = float('nan')
            else:
                try:
                    request.puntuacion = float(puntos)
                except ValueError:
                    request.puntuacion = float('nan')
        elif isinstance(puntos, (int, float)):
            request.puntuacion = float(puntos)
        else:
            request.puntuacion = float('nan')

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

        if not self._wait_for_service(self._db_client, '/patricio/db/guardar_partida'):
            return False, 'servicio de base de datos no disponible', 0

        response = self._call_service_sync(self._db_client, request, timeout=10.0)
        if response is None:
            return False, 'el servicio de registro no respondió a tiempo', 0

        return (
            bool(getattr(response, 'success', False)),
            str(getattr(response, 'message', '') or 'respuesta inválida'),
            int(getattr(response, 'id_partida', 0) or 0),
        )

    def _call_start_game_service(self, game_name: str) -> str:
        if not self._wait_for_service(self._start_game_client, '/start_game'):
            return 'El servicio de inicio de juego no está disponible en este momento.'

        request = StartGame.Request()
        request.game_name = game_name
        response = self._call_service_sync(self._start_game_client, request, timeout=10.0)
        if response is None:
            return 'No se recibió respuesta del juego pilla_pilla a tiempo.'

        if not getattr(response, 'started', False):
            return f'No se pudo iniciar {game_name} en el robot.'

        return f'Juego {game_name} iniciado correctamente.'

    def _build_escondite_poses(self) -> PoseArray:
        """Construye el PoseArray con las posiciones candidatas del escondite.

        Las coordenadas se toman de ESCONDITE_SEARCH_POSES (marco "map") y se
        envían con orientación neutra; el servicio del escondite elegirá una de
        ellas al azar como objetivo de búsqueda.
        """
        pose_array = PoseArray()
        pose_array.header.frame_id = 'map'
        for x, y in ESCONDITE_SEARCH_POSES:
            pose = Pose()
            pose.position = Point(x=float(x), y=float(y), z=0.0)
            pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
            pose_array.poses.append(pose)
        return pose_array

    def _call_escondite_service(self) -> str:
        if not self._wait_for_service(self._escondite_client, '/patricio/escondite/iniciar'):
            return 'El servicio de escondite no está disponible en este momento.'

        request = IniciarEscondite.Request()
        request.command = 'START'
        request.poses = self._build_escondite_poses()
        self.get_logger().info(
            f'Enviando escondite con {len(request.poses.poses)} posiciones candidatas.'
        )
        response = self._call_service_sync(self._escondite_client, request, timeout=10.0)
        if response is None:
            return 'No se recibió respuesta del servicio de escondite a tiempo.'

        if not getattr(response, 'success', False):
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

    def _call_service_sync(self, client, request, timeout: float = 10.0):
        """Llama a un servicio desde dentro de un callback sin re-entrar en el spin.

        No se puede usar rclpy.spin_until_future_complete dentro de un callback
        (el ejecutor ya está girando). En su lugar enviamos la petición y
        esperamos a que un hilo del MultiThreadedExecutor complete el future,
        avisándonos con un threading.Event. Devuelve la respuesta o None si
        se agota el tiempo.
        """
        future = client.call_async(request)
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout):
            return None
        return future.result()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GeminiNode()
    # Ejecutor multihilo: necesario para poder llamar a servicios desde dentro
    # del callback de voz sin bloquear el procesamiento de sus respuestas.
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        if getattr(node, '_client', None) is not None:
            executor.spin()
        else:
            node.get_logger().error(
                'El nodo Gemini no se inicializó correctamente. Comprueba la clave de API y las dependencias.'
            )
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
