#!/usr/bin/env python3
"""
Nodo ROS 2 para integrar Google Gemini con Patricio como personalidad infantil.

- Suscribe a /patricio/voice_input para recibir prompts de entrada.
- Consulta Google Gemini usando la clave de API del entorno.
- Publica la respuesta en /patricio/voice_output y /patricio/face_text.
- Verifica la comunicación básica al arrancar si verify_connection está activo.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

import requests
import rclpy
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
    'Si el usuario pide noticias o temas interesantes, da una respuesta actual, bien conectada y con sentido.'
)

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

    def generate_reply(self, user_prompt: str, temperature: float, max_tokens: int) -> str:
        prompt = _clean_text(user_prompt)
        if not prompt:
            return ''

        if self.service == 'nim':
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
            payload = {
                'model': self.model_name,
                'messages': [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
                'temperature': float(temperature),
                'max_tokens': int(max_tokens),
            }
            response = requests.post(self._nim_url, headers=headers, json=payload, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f'NIM API error: {response.status_code} {response.text}')
            return self._extract_text(response.json())

        if self.sdk == 'google.generativeai':
            payload = [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ]
            if hasattr(genai, 'chat'):
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

        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: Any) -> str:
        if response is None:
            return ''

        if isinstance(response, dict):
            choices = response.get('choices')
            if choices and isinstance(choices, list) and len(choices) > 0:
                message = choices[0].get('message')
                if message and isinstance(message, dict):
                    content = message.get('content')
                    if isinstance(content, str):
                        return _clean_text(content)
            text = response.get('text')
            if isinstance(text, str):
                return _clean_text(text)
            return ''

        if hasattr(response, 'last'):
            last = getattr(response, 'last')
            if last is None:
                return ''
            return _clean_text(getattr(last, 'content', str(last)))

        if hasattr(response, 'output'):
            output = getattr(response, 'output')
            if output is None:
                return ''
            return _clean_text(getattr(output, 'content', str(output)))

        if hasattr(response, 'candidates'):
            candidates = getattr(response, 'candidates')
            if candidates:
                return _clean_text(getattr(candidates[0], 'content', str(candidates[0])))

        text = getattr(response, 'text', None)
        if isinstance(text, str):
            return _clean_text(text)

        try:
            return _clean_text(str(response))
        except Exception:
            return ''


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
            if response:
                self.get_logger().info(f'Respuesta de verificación: "{response}"')
                self._publish_status('verificado')
                self._publish_faces_and_voice(response)
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
            answer = self._client.generate_reply(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            self.get_logger().error(f'Error al consultar Gemini: {exc}')
            self._publish_status('error_api')
            return

        if not answer:
            self.get_logger().warn('Gemini devolvió respuesta vacía.')
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
