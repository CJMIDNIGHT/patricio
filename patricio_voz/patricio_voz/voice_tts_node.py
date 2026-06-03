#!/usr/bin/env python3
"""
Nodo ROS 2 — Text-to-Speech (TTS) para Patricio.

- Suscribe respuestas de la IA en /patricio/voice_output.
- Publica el mismo texto en /patricio/screen_text (subtítulos / globo en pantalla).
- Reproduce audio por el altavoz del robot (pyttsx3 local = baja latencia; gTTS opcional).
- Voz calibrada: ritmo algo más rápido y voz en español para tono amigable infantil.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import pyttsx3
except ImportError as pyttsx3_import_error:
    pyttsx3 = None
    _PYTTSX3_IMPORT_ERROR = pyttsx3_import_error
else:
    _PYTTSX3_IMPORT_ERROR = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

TOPIC_VOICE_OUTPUT = '/patricio/voice_output'
TOPIC_SCREEN_TEXT = '/patricio/screen_text'
TOPIC_TTS_STATUS = '/patricio/tts_status'


def _clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip())


def _screen_snippet(text: str, max_chars: int) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(' ', 1)[0]
    return (cut or text[: max_chars - 1]) + '…'


class Pyttsx3Backend:
    """Motor local — baja latencia, sin red."""

    def __init__(self, rate: int, volume: float, voice_contains: str, logger) -> None:
        if pyttsx3 is None:
            raise RuntimeError(
                f'pyttsx3 no instalado: {_PYTTSX3_IMPORT_ERROR}. '
                'pip install pyttsx3'
            ) from _PYTTSX3_IMPORT_ERROR
        self._logger = logger
        self._lock = threading.Lock()
        try:
            self._engine = pyttsx3.init()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                'pyttsx3 no pudo iniciar el motor de voz. En Linux necesita eSpeak-NG: '
                'instala con "sudo apt install espeak-ng" o cambia tts_engine a "gtts". '
                f'(detalle: {exc})'
            ) from exc
        self._engine.setProperty('rate', int(rate))
        self._engine.setProperty('volume', float(volume))
        self._pick_voice(voice_contains)

    def _pick_voice(self, voice_contains: str) -> None:
        voices = self._engine.getProperty('voices') or []
        needle = (voice_contains or 'spanish').lower()
        chosen = None
        for voice in voices:
            blob = f'{voice.id} {getattr(voice, "name", "")}'.lower()
            if needle in blob or 'es' in blob.split('-')[0:1]:
                chosen = voice.id
                break
        if chosen is None and voices:
            chosen = voices[0].id
        if chosen:
            self._engine.setProperty('voice', chosen)
            self._logger.info(f'TTS pyttsx3 voz seleccionada: {chosen}')

    def stop(self) -> None:
        with self._lock:
            try:
                self._engine.stop()
            except Exception:
                pass

    def speak(self, text: str) -> None:
        with self._lock:
            self._engine.stop()
            self._engine.say(text)
            self._engine.runAndWait()


class GttsBackend:
    """Motor en la nube — más natural, mayor latencia (requiere Internet)."""

    def __init__(self, lang: str, tld: str, player_cmd: str, logger, timeout: float = 8.0) -> None:
        if gTTS is None:
            raise RuntimeError('gTTS no instalado. pip install gTTS')
        self._lang = lang
        self._tld = tld
        self._player_cmd = player_cmd.strip() or 'mpg123 -q'
        self._logger = logger
        self._timeout = float(timeout)
        self._proc: subprocess.Popen | None = None
        # RLock (reentrante): speak() llama a stop() mientras ya tiene el lock,
        # por lo que un Lock normal provocaría un interbloqueo.
        self._lock = threading.RLock()

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def speak(self, text: str) -> None:
        with self._lock:
            self.stop()
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                path = Path(tmp.name)
            try:
                # gTTS no expone timeout y puede colgarse si la red falla, así que
                # generamos el audio en un hilo y lo abandonamos si tarda demasiado.
                gen_error: dict[str, Exception] = {}

                def _generate() -> None:
                    try:
                        gTTS(text=text, lang=self._lang, tld=self._tld).save(str(path))
                    except Exception as exc:  # noqa: BLE001
                        gen_error['exc'] = exc

                gen_thread = threading.Thread(target=_generate, daemon=True)
                gen_thread.start()
                gen_thread.join(self._timeout)
                if gen_thread.is_alive():
                    raise TimeoutError(
                        f'gTTS no respondió en {self._timeout:.0f}s (¿sin Internet?). '
                        'Usa el motor pyttsx3 para voz offline.'
                    )
                if 'exc' in gen_error:
                    raise gen_error['exc']

                parts = self._player_cmd.split()
                self._proc = subprocess.Popen([*parts, str(path)])
                self._proc.wait()
            finally:
                path.unlink(missing_ok=True)


class VoiceTtsNode(Node):
    """Convierte respuestas de texto en audio + subtítulo en pantalla."""

    def __init__(self) -> None:
        super().__init__('voice_tts_node')

        self.declare_parameter('voice_output_topic', TOPIC_VOICE_OUTPUT)
        self.declare_parameter('screen_text_topic', TOPIC_SCREEN_TEXT)
        self.declare_parameter('status_topic', TOPIC_TTS_STATUS)
        self.declare_parameter('tts_engine', 'pyttsx3')
        self.declare_parameter('speech_rate', 178)
        self.declare_parameter('speech_volume', 1.0)
        self.declare_parameter('voice_name_contains', 'spanish')
        self.declare_parameter('gtts_lang', 'es')
        self.declare_parameter('gtts_tld', 'com.mx')
        self.declare_parameter('gtts_player_cmd', 'mpg123 -q')
        self.declare_parameter('gtts_timeout', 8.0)
        self.declare_parameter('max_screen_chars', 160)
        self.declare_parameter('interrupt_on_new', True)

        self._voice_output_topic = self.get_parameter('voice_output_topic').value
        self._screen_text_topic = self.get_parameter('screen_text_topic').value
        self._status_topic = self.get_parameter('status_topic').value
        self._max_screen_chars = int(self.get_parameter('max_screen_chars').value)
        self._interrupt = bool(self.get_parameter('interrupt_on_new').value)

        engine_name = str(self.get_parameter('tts_engine').value).lower().strip()
        if engine_name == 'gtts':
            self._backend = GttsBackend(
                lang=self.get_parameter('gtts_lang').value,
                tld=self.get_parameter('gtts_tld').value,
                player_cmd=self.get_parameter('gtts_player_cmd').value,
                logger=self.get_logger(),
                timeout=self.get_parameter('gtts_timeout').value,
            )
        else:
            self._backend = Pyttsx3Backend(
                rate=self.get_parameter('speech_rate').value,
                volume=self.get_parameter('speech_volume').value,
                voice_contains=self.get_parameter('voice_name_contains').value,
                logger=self.get_logger(),
            )

        self._pub_screen = self.create_publisher(String, self._screen_text_topic, 10)
        self._pub_status = self.create_publisher(String, self._status_topic, 10)
        self.create_subscription(
            String, self._voice_output_topic, self._on_voice_output, 10
        )

        self._speak_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop_flag = threading.Event()

        self._publish_status('idle')
        self.get_logger().info(
            f'TTS listo (motor={engine_name}). '
            f'Entrada={self._voice_output_topic}, pantalla={self._screen_text_topic}'
        )

    def _publish_status(self, status: str) -> None:
        msg = String()
        msg.data = status
        self._pub_status.publish(msg)

    def _publish_screen(self, text: str) -> None:
        snippet = _screen_snippet(text, self._max_screen_chars)
        msg = String()
        msg.data = snippet
        self._pub_screen.publish(msg)
        self.get_logger().info(f'Pantalla ({len(snippet)} chars): "{snippet[:80]}…"')

    def _on_voice_output(self, msg: String) -> None:
        text = _clean_text(msg.data)
        if not text:
            self.get_logger().warn('Mensaje vacío en voice_output, ignorado.')
            return

        if self._interrupt:
            self._stop_flag.set()
            self._backend.stop()

        self._publish_screen(text)
        self._publish_status('speaking')

        if self._worker and self._worker.is_alive():
            if not self._interrupt:
                self.get_logger().info('Ocupado hablando; encolando no implementado — se interrumpe.')
            self._worker.join(timeout=0.5)

        self._stop_flag.clear()

        def _run() -> None:
            try:
                t0 = time.monotonic()
                self._backend.speak(text)
                if not self._stop_flag.is_set():
                    elapsed = time.monotonic() - t0
                    self.get_logger().info(f'Audio terminado ({elapsed:.2f}s, {len(text)} chars)')
                    self._publish_status('idle')
            except Exception as exc:
                self.get_logger().error(f'Error TTS: {exc}')
                self._publish_status('error')

        self._worker = threading.Thread(target=_run, daemon=True, name='patricio-tts')
        self._worker.start()

    def destroy_node(self) -> None:
        self._stop_flag.set()
        self._backend.stop()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceTtsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
