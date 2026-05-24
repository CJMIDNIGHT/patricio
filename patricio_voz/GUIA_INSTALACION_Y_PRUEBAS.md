# Guía paso a paso — Reconocimiento de voz (Patricio STT)

Esta guía explica cómo instalar el paquete **`patricio_voz`**, configurar el micrófono **Konobo USB 2.0 Mini** y comprobar que el robot publica texto en el tópico `/patricio/voice_input` para la IA.

---

## 1. Qué vas a tener al terminar

| Elemento | Descripción |
|----------|-------------|
| Nodo `voice_stt_node` | Escucha el micrófono y transcribe voz en español |
| Activación | Palabra clave **«Hola Patricio»** o señal en `/patricio/voice_activate` |
| Salida | Texto en `/patricio/voice_input` (`std_msgs/String`) |
| Estado | Mensajes en `/patricio/voice_status` (opcional, para depurar) |

**Requisito importante (motor Google):** el PC del robot necesita **conexión a Internet** para enviar el audio a Google Speech Recognition. Si no hay red, puedes cambiar a Whisper (sección 8).

---

## 2. Requisitos previos

- Ubuntu con **ROS 2** (Jazzy o Humble) ya instalado y funcionando.
- Workspace clonado, por ejemplo: `~/turtlebot3_ws/src/patricio`
- Micrófono **Konobo USB** conectado por USB (o el que uses).
- Usuario con permisos para usar audio (grupo `audio`):

```bash
sudo usermod -aG audio $USER
# Cierra sesión y vuelve a entrar para que aplique el grupo
```

Comprueba que el sistema ve el micrófono:

```bash
# Si tienes pipewire/pulseaudio
pactl list sources short

# O con arecord (ALSA)
arecord -l
```

Deberías ver una entrada USB relacionada con Konobo, ICE o similar.

---

## 3. Instalar dependencias del sistema

Abre una terminal y ejecuta:

```bash
sudo apt update
sudo apt install -y \
  portaudio19-dev \
  python3-pyaudio \
  python3-pip \
  ffmpeg
```

| Paquete | Para qué sirve |
|---------|----------------|
| `portaudio19-dev` | Compilar/usar PyAudio |
| `python3-pyaudio` | Acceso al micrófono desde Python |
| `python3-pip` | Instalar SpeechRecognition |
| `ffmpeg` | Solo necesario si usas motor **Whisper** |

---

## 4. Instalar dependencias Python

```bash
cd ~/turtlebot3_ws/src/patricio/patricio_voz
pip install -r requirements.txt
```

O, si usas el entorno del sistema con `--break-system-packages` (Ubuntu 24.04+):

```bash
pip install --user -r requirements.txt
```

Comprueba que se importan bien:

```bash
python3 -c "import speech_recognition as sr; import pyaudio; print('OK')"
```

Si falla `pyaudio`, repite el paso 3 y vuelve a instalar `requirements.txt`.

---

## 5. Compilar el paquete ROS 2

```bash
cd ~/turtlebot3_ws
source /opt/ros/jazzy/setup.bash
# En Humble: source /opt/ros/humble/setup.bash

colcon build --packages-select patricio_voz --symlink-install
source install/setup.bash
```

Verifica que el ejecutable existe:

```bash
ros2 pkg executables patricio_voz
```

Salida esperada (aproximada):

```
patricio_voz voice_stt_node
patricio_voz list_audio_devices
```

---

## 6. Configurar el micrófono Konobo

### 6.1 Listar dispositivos de audio

Con el workspace cargado:

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 run patricio_voz list_audio_devices
```

Verás una tabla con **índice** y **nombre**. Busca una línea que contenga `konobo`, `ice`, `usb` o el nombre de tu micrófono.

Ejemplo:

```
     4 | USB Audio Device: - (hw:2,0)  <-- posible Konobo USB
```

### 6.2 Editar parámetros

Abre el archivo:

`~/turtlebot3_ws/src/patricio/patricio_voz/config/voice_stt_params.yaml`

Ajusta según tu listado:

```yaml
microphone_device_index: 4          # índice que viste (o -1 para auto)
microphone_name_contains: "konobo"  # texto que aparece en el nombre
```

- Si pones **`microphone_device_index: -1`**, el nodo intentará elegir el micrófono cuyo nombre contenga `microphone_name_contains`.
- Si conoces el índice exacto, ponlo en `microphone_device_index` (más fiable).

### 6.3 Prueba rápida de grabación (opcional)

```bash
arecord -D plughw:2,0 -f cd -d 3 /tmp/prueba.wav
aplay /tmp/prueba.wav
```

(Sustituye `2,0` por la tarjeta que corresponda a tu `arecord -l`.)

---

## 7. Arrancar el nodo de voz

**Terminal 1** — nodo STT:

```bash
cd ~/turtlebot3_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch patricio_voz voice_stt.launch.py
```

Mensajes esperados al inicio:

- `Calibrando ruido ambiente (1.0s)...`
- `Nodo STT listo. Motor=google, idioma=es-ES...`
- `esperando_palabra_clave` (en logs o en `/patricio/voice_status`)

---

## 8. Comprobar que funciona (pruebas paso a paso)

### 8.1 Ver tópicos

**Terminal 2:**

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 topic list | grep patricio/voice
```

Debes ver:

```
/patricio/voice_activate
/patricio/voice_input
/patricio/voice_status
```

### 8.2 Ver el estado del nodo

```bash
ros2 topic echo /patricio/voice_status
```

Estados habituales:

| Estado | Significado |
|--------|-------------|
| `idle` | Esperando |
| `esperando_palabra_clave` | Escuchando «Hola Patricio» |
| `escuchando_comando` | Grabando la frase del niño |
| `transcribiendo` | Enviando audio al motor STT |
| `transcrito` | Texto publicado correctamente |
| `no_entendido` | No se entendió el audio |

### 8.3 Prueba con palabra clave (modo normal)

1. Deja `require_wake_word: true` en el YAML.
2. En la **Terminal 2**:

```bash
ros2 topic echo /patricio/voice_input
```

3. Habla al micrófono, con claridad:
   - Primero: **«Hola Patricio»**
   - Luego (si no dijiste el comando en la misma frase): **«¿Qué hora es?»** o **«Cuéntame un chiste»**

4. En `voice_input` debería aparecer algo como:

```
data: ¿Qué hora es?
---
```

### 8.4 Prueba con activación por sistema (sin palabra clave)

Útil para depurar el micrófono y Google sin depender del wake word.

**Terminal 2:**

```bash
ros2 topic pub --once /patricio/voice_activate std_msgs/msg/Bool "{data: true}"
```

Inmediatamente di una frase corta al micrófono. Mira `voice_input` y `voice_status`.

### 8.5 Prueba en una sola frase

Di de seguido: **«Hola Patricio, cuéntame un cuento»**.

Si el motor entiende todo, publicará: `cuéntame un cuento` (sin la palabra clave).

---

## 9. Ajustes si no te escucha bien

Edita `config/voice_stt_params.yaml`:

| Parámetro | Qué hacer |
|-----------|-----------|
| `energy_threshold` | Sube (400–800) si captura ruido; baja (200) si no reacciona |
| `ambient_calibration_sec` | Sube a `2.0` en entornos ruidosos |
| `command_listen_seconds` | Sube a `15.0` para frases largas |
| `wake_listen_seconds` | Sube a `3.5` si no detecta «Hola Patricio» |

Tras cambiar el YAML, **reinicia** el launch (Ctrl+C y vuelve a lanzar).

Para probar **sin palabra clave** (escucha continua):

```yaml
require_wake_word: false
```

---

## 10. Motor Whisper (local, sin Google)

Solo si necesitas funcionar **sin Internet**:

1. Instala Whisper y dependencias:

```bash
pip install openai-whisper
# ffmpeg ya instalado en paso 3
```

2. En `voice_stt_params.yaml`:

```yaml
recognition_engine: "whisper"
```

3. La primera ejecución puede **descargar el modelo** (tarda y ocupa espacio).

4. Reinicia el nodo.

---

## 11. Integración con la IA

El nodo de IA (cuando lo tengas) debe **suscribirse** a:

```
/patricio/voice_input   (std_msgs/msg/String)
```

Ejemplo de prueba manual simulando lo que recibiría la IA:

```bash
ros2 topic pub --once /patricio/voice_input std_msgs/msg/String "{data: 'hola patricio qué tiempo hace'}"
```

---

## 12. Resolución de problemas

### «SpeechRecognition no instalado»

```bash
pip install SpeechRecognition PyAudio
```

### «No se pudo abrir el micrófono»

- Comprueba USB y `arecord -l`.
- Prueba otro `microphone_device_index`.
- Cierra otras apps que usen el micrófono (Zoom, navegador).

### No aparece nada en `voice_input`

- Comprueba Internet (motor `google`).
- Mira `/patricio/voice_status`: si sale `no_entendido`, habla más alto o más cerca.
- Prueba activación por `/patricio/voice_activate`.
- Sube `energy_threshold` o `ambient_calibration_sec`.

### Error «Request Error» de Google

- Sin conexión o firewall bloqueando Google.
- Cambia a `whisper` o revisa proxy/VPN.

### El nodo no arranca tras `colcon build`

```bash
source ~/turtlebot3_ws/install/setup.bash
ros2 pkg list | grep patricio_voz
```

Si no aparece, repite la compilación (paso 5).

---

## 13. Checklist final

Marca cuando lo tengas:

- [ ] `portaudio19-dev` y `python3-pyaudio` instalados
- [ ] `pip install -r requirements.txt` sin errores
- [ ] `colcon build --packages-select patricio_voz` correcto
- [ ] `list_audio_devices` muestra el Konobo
- [ ] `voice_stt_params.yaml` con índice o nombre correcto
- [ ] `ros2 launch patricio_voz voice_stt.launch.py` sin errores de micrófono
- [ ] `ros2 topic echo /patricio/voice_input` muestra texto al hablar
- [ ] Prueba con «Hola Patricio» + frase OK
- [ ] Prueba con `/patricio/voice_activate` OK

---

## 14. Comandos de referencia rápida

```bash
# Entorno
source /opt/ros/jazzy/setup.bash
source ~/turtlebot3_ws/install/setup.bash

# Listar micrófonos
ros2 run patricio_voz list_audio_devices

# Arrancar STT
ros2 launch patricio_voz voice_stt.launch.py

# Ver texto reconocido
ros2 topic echo /patricio/voice_input

# Ver estado
ros2 topic echo /patricio/voice_status

# Activar escucha sin palabra clave
ros2 topic pub --once /patricio/voice_activate std_msgs/msg/Bool "{data: true}"
```

---

*Documento asociado al paquete `patricio_voz` — Patricio 2026.*
