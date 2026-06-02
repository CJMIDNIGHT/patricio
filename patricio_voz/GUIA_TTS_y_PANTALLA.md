# Guía paso a paso — Salida de audio (TTS) y pantalla (Patricio T18)

Esta guía explica cómo instalar y probar el **motor de texto a voz (TTS)** de Patricio: el robot **habla** las respuestas de la IA por el altavoz y, **a la vez**, muestra subtítulos en la pantalla facial mediante el tópico `/patricio/screen_text`.

**Historia:** H12 / H15 — **T18** Salida de Audio (Text-to-Speech) y Visualización.

---

## 1. Qué vas a tener al terminar

| Elemento | Descripción |
|----------|-------------|
| Nodo `voice_tts_node` | Escucha `/patricio/voice_output` y reproduce audio |
| Motor TTS | **pyttsx3** (local, baja latencia) o **gTTS** (más natural, requiere red) |
| Pantalla | Publica en `/patricio/screen_text` al mismo tiempo que habla |
| Face screen | Globo de diálogo en `face_screen.html` vía rosbridge |
| Pipeline voz | STT → Gemini → TTS + pantalla |

**Arquitectura:**

```
Micrófono → voice_stt_node → /patricio/voice_input
                                      ↓
                              patricio_gemini_node
                                      ↓
                              /patricio/voice_output
                                      ↓
                              voice_tts_node ──→ altavoz (pyttsx3 / gTTS)
                                      │
                                      └──→ /patricio/screen_text → face_screen
```

---

## 2. Requisitos previos

- Ubuntu con **ROS 2** (Jazzy o Humble) y workspace Patricio clonado.
- Paquetes **patricio_voz** (STT) y **patricio_gemini** (IA) ya compilados.
- **Altavoz** conectado (Jack, USB o HDMI audio) y volumen audible.
- Para pruebas de pantalla: **rosbridge** + navegador con `face_screen.html`.
- Clave de API de IA (`NIM_API_KEY` o `GOOGLE_API_KEY`) para Gemini.

Comprueba audio de salida:

```bash
speaker-test -t wav -c 2 -l 1
# Ctrl+C para parar
```

Usuario en grupo `audio`:

```bash
sudo usermod -aG audio $USER
# Cierra sesión y vuelve a entrar
```

---

## 3. Obtener la rama del repositorio

En el ordenador donde vayas a trabajar:

```bash
cd ~/turtlebot3_ws/src/patricio
git fetch origin
git checkout H12-H15-T18-tts-screen
git pull origin H12-H15-T18-tts-screen
```

Si aún no existe en remoto, usa `master` tras hacer merge; la rama contiene el nodo TTS.

---

## 4. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y \
  espeak-ng \
  espeak-ng-data \
  libespeak-ng1 \
  mpg123 \
  portaudio19-dev \
  python3-pip \
  python3-pyaudio
```

| Paquete | Para qué sirve |
|---------|----------------|
| `espeak-ng` | Motor de voz local usado por pyttsx3 |
| `mpg123` | Reproducir MP3 si usas motor **gTTS** |
| `portaudio19-dev` | Micrófono (STT) |

---

## 5. Instalar dependencias Python

```bash
cd ~/turtlebot3_ws/src/patricio/patricio_voz
pip install -r requirements.txt
```

Motor **gTTS** (opcional):

```bash
pip install gTTS
```

Comprueba pyttsx3:

```bash
python3 -c "import pyttsx3; e=pyttsx3.init(); print('OK', e.getProperty('voice'))"
```

Lista voces disponibles:

```bash
python3 - <<'PY'
import pyttsx3
e = pyttsx3.init()
for v in e.getProperty('voices'):
    print(v.id, '-', v.name)
PY
```

---

## 6. Compilar paquetes ROS 2

```bash
cd ~/turtlebot3_ws
source /opt/ros/jazzy/setup.bash
# Humble: source /opt/ros/humble/setup.bash

colcon build --packages-select patricio_voz patricio_gemini --symlink-install
source install/setup.bash
```

Verifica ejecutables:

```bash
ros2 pkg executables patricio_voz
```

Salida esperada:

```
patricio_voz voice_stt_node
patricio_voz voice_tts_node
patricio_voz list_audio_devices
```

---

## 7. Configurar voz infantil / simpática

Edita `patricio_voz/config/voice_tts_params.yaml`:

```yaml
tts_engine: "pyttsx3"
speech_rate: 178        # más alto = más ágil (niños). Prueba 165–195
speech_volume: 1.0
voice_name_contains: "spanish"
max_screen_chars: 160
```

**Calibración:**

1. Sube `speech_rate` si suena lento; bájalo si suena acelerado.
2. Cambia `voice_name_contains` según la salida del listado de voces (`spanish`, `es`, `mb`).
3. Para voz más suave con **gTTS** (más latencia):

```yaml
tts_engine: "gtts"
gtts_lang: "es"
gtts_tld: "com.mx"
gtts_player_cmd: "mpg123 -q"
```

---

## 8. Arrancar el pipeline completo

Abre **varias terminales** (todas con `source ~/turtlebot3_ws/install/setup.bash`).

### Terminal 1 — rosbridge (pantalla web)

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

### Terminal 2 — Pantalla facial (navegador)

```bash
cd ~/turtlebot3_ws/src/patricio/patricio_web
./static/arrancar_face_screen.sh
```

Abre la URL que indique el script (p. ej. `http://localhost:8081/face_screen.html`).  
Ajusta `ROSBRIDGE_URL` en `js/face_logic.js` si el robot usa otra IP.

### Terminal 3 — IA (Gemini / NIM)

```bash
export NIM_API_KEY="tu_clave_aqui"
# o: export GOOGLE_API_KEY="..."
ros2 launch patricio_gemini gemini.launch.py
```

### Terminal 4 — STT + TTS (voz entrada y salida)

```bash
ros2 launch patricio_voz voice_assistant.launch.py
```

Solo TTS (prueba manual sin micrófono):

```bash
ros2 launch patricio_voz voice_tts.launch.py
```

---

## 9. Probar TTS sin micrófono (publicación manual)

Con `voice_tts_node` en marcha:

```bash
ros2 topic pub --once /patricio/voice_output std_msgs/msg/String \
  "{data: 'Hola, soy Patricio. ¿Jugamos al pilla-pilla?'}"
```

Deberías oír el audio **de inmediato** y ver el globo de texto en la face screen.

Monitoriza tópicos:

```bash
ros2 topic echo /patricio/screen_text
ros2 topic echo /patricio/tts_status
```

Estados de `/patricio/tts_status`: `idle`, `speaking`, `error`.

---

## 10. Probar flujo completo con voz

1. Di **«Hola Patricio»** al micrófono (STT).
2. Haz una pregunta corta: *«¿Cuánto es dos más dos?»*
3. Gemini publica en `/patricio/voice_output`.
4. TTS habla y la pantalla muestra el mismo texto.

Comprueba la cadena:

```bash
ros2 topic echo /patricio/voice_input
ros2 topic echo /patricio/voice_output
ros2 topic echo /patricio/screen_text
```

---

## 11. Solución de problemas

| Problema | Solución |
|----------|----------|
| No se oye nada | `pactl set-sink-volume @DEFAULT_SINK@ 100%`; prueba `speaker-test` |
| pyttsx3 falla al iniciar | `sudo apt install espeak-ng`; reinstala `pip install pyttsx3` |
| Voz en inglés | Ajusta `voice_name_contains: "spanish"` en el YAML |
| gTTS sin sonido | Instala `mpg123`; comprueba Internet |
| Pantalla sin texto | rosbridge activo; IP correcta en `face_logic.js` |
| Retardo alto | Usa `tts_engine: pyttsx3` (no gTTS) |
| Se corta al hablar de nuevo | Normal con `interrupt_on_new: true` (prioriza última respuesta) |

---

## 12. Checklist final

- [ ] `voice_tts_node` arranca sin errores
- [ ] Publicación manual en `/patricio/voice_output` reproduce audio
- [ ] `/patricio/screen_text` muestra globo en face screen
- [ ] STT + Gemini + TTS funcionan en cadena
- [ ] Voz suena clara y a ritmo adecuado para niños
- [ ] Latencia aceptable (respuesta hablada en pocos segundos tras la IA)

---

## 13. Comandos de referencia rápida

```bash
# Compilar
colcon build --packages-select patricio_voz --symlink-install && source install/setup.bash

# TTS solo
ros2 launch patricio_voz voice_tts.launch.py

# STT + TTS
ros2 launch patricio_voz voice_assistant.launch.py

# Prueba rápida
ros2 topic pub --once /patricio/voice_output std_msgs/msg/String "{data: 'Hola niños'}"

# PDF de esta guía
python3 ~/turtlebot3_ws/src/patricio/patricio_voz/scripts/generar_guia_tts_pdf.py
```

---

*Documento asociado al paquete patricio_voz — T18 Salida de Audio y Visualización — Patricio 2026.*
