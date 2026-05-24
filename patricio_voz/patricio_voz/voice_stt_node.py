#!/usr/bin/env python3
"""
Nodo ROS 2 — reconocimiento de voz (Speech-to-Text) para Patricio.

- Captura audio del micrófono (PyAudio / SpeechRecognition).
- Activación por palabra clave (p. ej. «Hola Patricio») o señal en /patricio/voice_activate.
- Transcripción en español (Google SR por defecto; Whisper opcional).
- Publica texto limpio en /patricio/voice_input (std_msgs/String).
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

try:
    import speech_recognition as sr
except ImportError as sr_import_error:
    sr = None
    _SR_IMPORT_ERROR = sr_import_error
else:
    _SR_IMPORT_ERROR = None

TOPIC_VOICE_INPUT = '/patricio/voice_input'
TOPIC_VOICE_STATUS = '/patricio/voice_status'
TOPIC_VOICE_ACTIVATE = '/patricio/voice_activate'


def _normalize_text(text: str) -> str:
    text = (text or '').lower().strip()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return re.sub(r'\s+', ' ', text)


def _clean_transcript(text: str) -> str:
    text = (text or '').strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def _resolve_microphone_index(name_contains: str, explicit_index: int) -> int | None:
    if explicit_index >= 0:
        return explicit_index
    needle = (name_contains or '').strip().lower()
    if not needle:
        return None
    names = sr.Microphone.list_microphone_names()
    for i, name in enumerate(names):
        if needle in (name or '').lower():
            return i
    return None


class VoiceSttNode(Node):
    """Escucha el micrófono y publica transcripciones en /patricio/voice_input."""

    def __init__(self) -> None:
        super().__init__('voice_stt_node')

        if sr is None:
            self.get_logger().error(
                f'SpeechRecognition no instalado: {_SR_IMPORT_ERROR}. '
                'Ejecuta: pip install -r patricio_voz/requirements.txt'
            )
            raise RuntimeError('SpeechRecognition no disponible') from _SR_IMPORT_ERROR

        self.declare_parameter('microphone_device_index', -1)
        self.declare_parameter('microphone_name_contains', 'konobo')
        self.declare_parameter('language', 'es-ES')
        self.declare_parameter('recognition_engine', 'google')
        self.declare_parameter('wake_phrases', ['hola patricio', 'patricio'])
        self.declare_parameter('require_wake_word', True)
        self.declare_parameter('wake_listen_seconds', 2.5)
        self.declare_parameter('command_listen_seconds', 10.0)
        self.declare_parameter('listen_timeout_sec', 1.0)
        self.declare_parameter('ambient_calibration_sec', 1.0)
        self.declare_parameter('energy_threshold', 300)
        self.declare_parameter('dynamic_energy_threshold', True)
        self.declare_parameter('publish_partial_status', True)

        self._language = self.get_parameter('language').value
        self._engine = str(self.get_parameter('recognition_engine').value).lower()
        self._wake_phrases = [
            _normalize_text(p)
            for p in self.get_parameter('wake_phrases').value
            if str(p).strip()
        ]
        self._require_wake = self.get_parameter('require_wake_word').value
        self._wake_sec = float(self.get_parameter('wake_listen_seconds').value)
        self._cmd_sec = float(self.get_parameter('command_listen_seconds').value)
        self._timeout = float(self.get_parameter('listen_timeout_sec').value)
        self._calib_sec = float(self.get_parameter('ambient_calibration_sec').value)
        self._energy = int(self.get_parameter('energy_threshold').value)
        self._dynamic_energy = self.get_parameter('dynamic_energy_threshold').value

        dev_index = int(self.get_parameter('microphone_device_index').value)
        name_sub = str(self.get_parameter('microphone_name_contains').value)
        resolved = _resolve_microphone_index(name_sub, dev_index)

        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = self._energy
        self._recognizer.dynamic_energy_threshold = self._dynamic_energy

        mic_kwargs = {}
        if resolved is not None:
            mic_kwargs['device_index'] = resolved
            self.get_logger().info(f'Micrófono índice {resolved}: {sr.Microphone.list_microphone_names()[resolved]}')
        else:
            self.get_logger().info('Micrófono: dispositivo por defecto del sistema')

        self._microphone = sr.Microphone(**mic_kwargs)

        self._pub_input = self.create_publisher(String, TOPIC_VOICE_INPUT, 10)
        self._pub_status = self.create_publisher(String, TOPIC_VOICE_STATUS, 10)
        self.create_subscription(Bool, TOPIC_VOICE_ACTIVATE, self._on_activate, 10)

        self._lock = threading.Lock()
        self._force_listen = False
        self._shutdown = False

        self.get_logger().info(
            f'Nodo STT listo. Motor={self._engine}, idioma={self._language}, '
            f'wake={self._wake_phrases}, publica en {TOPIC_VOICE_INPUT}'
        )

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def _on_activate(self, msg: Bool) -> None:
        if msg.data:
            with self._lock:
                self._force_listen = True
            self._publish_status('activado_por_sistema')
            self.get_logger().info('Activación por /patricio/voice_activate')

    def _publish_status(self, status: str) -> None:
        if not self.get_parameter('publish_partial_status').value:
            return
        m = String()
        m.data = status
        self._pub_status.publish(m)

    def _publish_transcript(self, text: str) -> None:
        cleaned = _clean_transcript(text)
        if not cleaned:
            self._publish_status('vacio')
            return
        msg = String()
        msg.data = cleaned
        self._pub_input.publish(msg)
        self._publish_status('transcrito')
        self.get_logger().info(f'Publicado en {TOPIC_VOICE_INPUT}: "{cleaned}"')

    def _transcribe(self, audio: sr.AudioData) -> str | None:
        try:
            if self._engine == 'whisper':
                return self._recognizer.recognize_whisper(
                    audio, language='spanish'
                )
            return self._recognizer.recognize_google(
                audio, language=self._language
            )
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            self.get_logger().warn(f'Error del motor {self._engine}: {e}')
            return None

    def _listen_once(self, phrase_limit: float) -> sr.AudioData | None:
        try:
            with self._microphone as source:
                return self._recognizer.listen(
                    source,
                    timeout=self._timeout,
                    phrase_time_limit=phrase_limit,
                )
        except sr.WaitTimeoutError:
            return None

    def _contains_wake(self, text: str) -> bool:
        norm = _normalize_text(text)
        return any(p in norm for p in self._wake_phrases)

    def _strip_wake_prefix(self, text: str) -> str:
        norm = _normalize_text(text)
        original = _clean_transcript(text)
        for phrase in sorted(self._wake_phrases, key=len, reverse=True):
            if norm.startswith(phrase):
                idx = len(phrase)
                rest = original[idx:].lstrip(' ,.;:')
                return rest
            pos = norm.find(phrase)
            if pos >= 0:
                rest_norm = norm[pos + len(phrase):].strip(' ,.;:')
                if rest_norm:
                    return rest_norm
        return original

    def _handle_command_audio(self, audio: sr.AudioData) -> None:
        self._publish_status('transcribiendo')
        text = self._transcribe(audio)
        if not text:
            self._publish_status('no_entendido')
            return
        command = self._strip_wake_prefix(text)
        if command:
            self._publish_transcript(command)
        else:
            self._publish_status('solo_palabra_clave')

    def _listen_loop(self) -> None:
        time.sleep(0.5)
        try:
            with self._microphone as source:
                self.get_logger().info(
                    f'Calibrando ruido ambiente ({self._calib_sec}s)...'
                )
                self._recognizer.adjust_for_ambient_noise(source, duration=self._calib_sec)
        except Exception as e:
            self.get_logger().error(f'No se pudo abrir el micrófono: {e}')
            return

        self._publish_status('idle')

        while rclpy.ok() and not self._shutdown:
            force = False
            with self._lock:
                if self._force_listen:
                    force = True
                    self._force_listen = False

            try:
                if force or not self._require_wake:
                    self._publish_status('escuchando_comando')
                    audio = self._listen_once(self._cmd_sec)
                    if audio:
                        self._handle_command_audio(audio)
                    else:
                        self._publish_status('timeout')
                    continue

                self._publish_status('esperando_palabra_clave')
                audio = self._listen_once(self._wake_sec)
                if not audio:
                    continue

                self._publish_status('transcribiendo_wake')
                snippet = self._transcribe(audio)
                if not snippet:
                    continue

                if not self._contains_wake(snippet):
                    self._publish_status('idle')
                    continue

                self.get_logger().info(f'Palabra clave detectada: "{snippet}"')
                remainder = self._strip_wake_prefix(snippet)
                if len(remainder) >= 3:
                    self._publish_transcript(remainder)
                    continue

                self._publish_status('escuchando_comando')
                cmd_audio = self._listen_once(self._cmd_sec)
                if cmd_audio:
                    self._handle_command_audio(cmd_audio)
                else:
                    self._publish_status('timeout')

            except Exception as e:
                self.get_logger().error(f'Error en bucle de escucha: {e}')
                time.sleep(1.0)

        self._publish_status('detenido')

    def destroy_node(self) -> None:
        self._shutdown = True
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = VoiceSttNode()
        rclpy.spin(node)
    except RuntimeError:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
