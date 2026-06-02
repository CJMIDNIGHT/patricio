# Guía paso a paso — Salida de audio (TTS) y pantalla (Patricio T18)

Esta guía explica cómo instalar y probar el **motor de texto a voz (TTS)** de Patricio: el robot **habla** las respuestas de la IA por el altavoz y, **a la vez**, muestra subtítulos en la pantalla facial mediante el tópico `/patricio/screen_text`.

**Historia:** H12 / H15 — **T18** Salida de Audio (Text-to-Speech) y Visualización.

---

## 1. Qué vas a tener al terminar

| Elemento | Descripción |
|----------|-------------|
| Nodo `voice_tts_node` | Escucha `/patricio/voice_output` y reproduce audio |
| Motor TTS | **pyttsx3** (local, baja latencia) o **gTTS** (más natural, requiere red) |
| Pantalla física | **Raspberry Pi + LCD** muestra globo vía `face_screen.html` en modo kiosk |
| Tópico pantalla | `/patricio/screen_text` (subtítulos sincronizados con el audio) |
| Pipeline voz | STT → Gemini → TTS + pantalla |

**Arquitectura (setup real del robot):**

```
┌──────────────────── PC del robot (TurtleBot / Ubuntu) ────────────────────┐
│  Micrófono → voice_stt_node → /patricio/voice_input → gemini_node       │
│                              → /patricio/voice_output → voice_tts_node   │
│                                    │                    │               │
│                                    │                    └──→ altavoz    │
│                                    └──→ /patricio/screen_text             │
│  rosbridge_server :9090  ←──────── publica tópicos ROS por WebSocket    │
└────────────────────────────────────────────│──────────────────────────────┘
                                             │ WiFi / Ethernet
┌──────────────────── Raspberry Pi + LCD físico ────────────────────────────┐
│  Chromium kiosk → face_screen.html (globo de diálogo)                   │
│  Se conecta a ws://IP_DEL_ROBOT:9090                                      │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Requisitos previos

- Ubuntu con **ROS 2** (Jazzy o Humble) y workspace Patricio clonado.
- Paquetes **patricio_voz** (STT) y **patricio_gemini** (IA) ya compilados.
- **Altavoz** conectado al PC del robot (Jack, USB o HDMI audio).
- **Pantalla física:** Raspberry Pi con LCD real (7", 800×480 típico) montada en el robot.
- **Red:** Pi y PC del robot en la misma WiFi/Ethernet (`ROS_DOMAIN_ID` igual en ambos).
- Clave de API de IA (`NIM_API_KEY` o `GOOGLE_API_KEY`) para Gemini.

> **Nota:** El audio (TTS) sale del **PC del robot**. La Raspberry solo **muestra** el texto en su LCD; no necesita ROS 2 instalado, solo Chromium y el repo `patricio_web`.

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

## 8. Pantalla física — Raspberry Pi + LCD

La pantalla del robot **no es un monitor de desarrollo**: es una **Raspberry Pi** con **LCD integrado** (SPI/HDMI) que muestra la cara de Patricio y el globo de texto cuando habla.

### 8.1 Qué va en cada dispositivo

| Dispositivo | Rol |
|-------------|-----|
| **PC del robot** (Ubuntu + ROS 2) | STT, Gemini, TTS, altavoz, **rosbridge** |
| **Raspberry Pi + LCD** | Solo visualización: `face_screen.html` a pantalla completa |

### 8.2 Preparar la Raspberry Pi (una sola vez)

En la Raspberry Pi (Raspberry Pi OS):

```bash
sudo apt update
sudo apt install -y git python3 chromium-browser unclutter
```

Clona o copia la carpeta web (puede ser todo el repo):

```bash
mkdir -p ~/patricio
cd ~/patricio
git clone https://github.com/CJMIDNIGHT/patricio.git
# o: git pull si ya lo tienes
```

Averigua la **IP del PC del robot** (donde corre ROS 2):

```bash
# En el PC del robot:
hostname -I
# Ejemplo: 192.168.1.50
```

Prueba que la Pi alcanza el rosbridge del robot:

```bash
# En la Raspberry (sustituye la IP):
ping -c 2 192.168.1.50
curl -I http://192.168.1.50:9090 2>/dev/null || echo "rosbridge usa WebSocket ws://IP:9090"
```

### 8.3 Arrancar la LCD en modo kiosk

En la **Raspberry Pi**:

```bash
export PATRICIO_ROS_HOST=192.168.1.50   # ← IP del PC del robot
cd ~/patricio/patricio_web
chmod +x static/arrancar_face_screen_raspberry.sh
./static/arrancar_face_screen_raspberry.sh
```

El script:
1. Levanta un servidor HTTP local (`python3 -m http.server 8000`).
2. Abre **Chromium en pantalla completa** con `face_screen.html?ros_host=IP_DEL_ROBOT`.
3. La Pi se suscribe a `/patricio/screen_text` vía rosbridge del robot.

### 8.4 Arranque automático al encender la Pi (opcional)

Edita autostart de Raspberry Pi OS:

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/patricio-face.desktop
```

Contenido (ajusta rutas e IP):

```ini
[Desktop Entry]
Type=Application
Name=Patricio Face Screen
Exec=env PATRICIO_ROS_HOST=192.168.1.50 /home/pi/patricio/patricio_web/static/arrancar_face_screen_raspberry.sh
X-GNOME-Autostart-enabled=true
```

### 8.5 Rotación / resolución LCD

Si la imagen sale girada o cortada (`/boot/firmware/config.txt` en Pi 4/5):

```bash
sudo nano /boot/firmware/config.txt
# Añade según tu pantalla, por ejemplo:
# display_rotate=2
# hdmi_group=2
# hdmi_mode=87
sudo reboot
```

La interfaz ya incluye estilos para LCD pequeños (800×480).

### 8.6 Cambiar IP del robot sin editar código

Opciones (de mayor a menor prioridad):

1. URL: `face_screen.html?ros_host=192.168.1.50`
2. Variable al arrancar: `export PATRICIO_ROS_HOST=192.168.1.50`
3. Consola del navegador en la Pi: `localStorage.setItem('patricio_ros_host','192.168.1.50')`

---

## 9. Arrancar el pipeline en el PC del robot

Abre **varias terminales en el PC del robot** (`source ~/turtlebot3_ws/install/setup.bash`).

### Terminal 1 — rosbridge (la Pi se conecta aquí)

```bash
export ROS_DOMAIN_ID=7
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

### Terminal 2 — IA (Gemini / NIM)

```bash
export NIM_API_KEY="tu_clave_aqui"
ros2 launch patricio_gemini gemini.launch.py
```

### Terminal 3 — STT + TTS (micrófono + altavoz)

```bash
ros2 launch patricio_voz voice_assistant.launch.py
```

### Terminal 4 — Pantalla en la Raspberry Pi

En la **Pi** (no en el PC del robot):

```bash
export PATRICIO_ROS_HOST=IP_DEL_PC_ROBOT
./static/arrancar_face_screen_raspberry.sh
```

Solo TTS (prueba manual sin micrófono):

```bash
ros2 launch patricio_voz voice_tts.launch.py
```

> **Desarrollo / prueba en PC:** puedes usar `./static/arrancar_face_screen.sh` con Firefox si no tienes la Pi a mano.

---

## 10. Probar TTS sin micrófono (publicación manual)

Con `voice_tts_node` en marcha:

```bash
ros2 topic pub --once /patricio/voice_output std_msgs/msg/String \
  "{data: 'Hola, soy Patricio. ¿Jugamos al pilla-pilla?'}"
```

Deberías oír el audio en el **altavoz del robot** y ver el globo en la **LCD de la Raspberry**.

Monitoriza tópicos:

```bash
ros2 topic echo /patricio/screen_text
ros2 topic echo /patricio/tts_status
```

Estados de `/patricio/tts_status`: `idle`, `speaking`, `error`.

---

## 11. Probar flujo completo con voz

1. Di **«Hola Patricio»** al micrófono (STT).
2. Haz una pregunta corta: *«¿Cuánto es dos más dos?»*
3. Gemini publica en `/patricio/voice_output`.
4. TTS habla por el altavoz y la **LCD de la Pi** muestra el mismo texto.

## 12. Solución de problemas

| Problema | Solución |
|----------|----------|
| No se oye nada | `pactl set-sink-volume @DEFAULT_SINK@ 100%`; prueba `speaker-test` |
| pyttsx3 falla al iniciar | `sudo apt install espeak-ng`; reinstala `pip install pyttsx3` |
| Voz en inglés | Ajusta `voice_name_contains: "spanish"` en el YAML |
| gTTS sin sonido | Instala `mpg123`; comprueba Internet |
| Pantalla LCD sin texto | `PATRICIO_ROS_HOST` = IP del PC robot; rosbridge activo; mismo `ROS_DOMAIN_ID` |
| Pi no conecta a rosbridge | Misma red WiFi; firewall: `sudo ufw allow 9090` en el PC robot |
| Globo muy grande en LCD | Resolución en `config.txt`; CSS ya adapta 800×480 |
| Retardo alto | Usa `tts_engine: pyttsx3` (no gTTS) |
| Se corta al hablar de nuevo | Normal con `interrupt_on_new: true` (prioriza última respuesta) |

Comprueba la cadena en el **PC del robot**:

```bash
ros2 topic echo /patricio/voice_input
ros2 topic echo /patricio/voice_output
ros2 topic echo /patricio/screen_text
```

---

## 13. Checklist final

- [ ] `voice_tts_node` arranca sin errores
- [ ] Publicación manual en `/patricio/voice_output` reproduce audio
- [ ] `/patricio/screen_text` muestra globo en la **LCD de la Raspberry Pi**
- [ ] `PATRICIO_ROS_HOST` apunta al PC del robot
- [ ] STT + Gemini + TTS funcionan en cadena
- [ ] Voz suena clara y a ritmo adecuado para niños
- [ ] Latencia aceptable (respuesta hablada en pocos segundos tras la IA)

---

## 14. Comandos de referencia rápida

```bash
# Compilar (PC del robot)
colcon build --packages-select patricio_voz --symlink-install && source install/setup.bash

# Rosbridge (PC del robot)
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

# TTS + STT (PC del robot)
ros2 launch patricio_voz voice_assistant.launch.py

# Pantalla LCD (Raspberry Pi)
export PATRICIO_ROS_HOST=192.168.1.50
./patricio_web/static/arrancar_face_screen_raspberry.sh

# Prueba rápida audio + pantalla
ros2 topic pub --once /patricio/voice_output std_msgs/msg/String "{data: 'Hola niños'}"

# PDF de esta guía
python3 ~/turtlebot3_ws/src/patricio/patricio_voz/scripts/generar_guia_tts_pdf.py
```

---

*Documento asociado al paquete patricio_voz — T18 Salida de Audio y Visualización — Patricio 2026.*
