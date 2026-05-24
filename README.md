# 🤖 Patricio — Robot Educativo para Niños

**Proyecto de Robótica 2026**  
Repositorio: `patricio`

---

## 📖 Descripción

**Patricio** es un robot educativo diseñado para niños de entre 4 y 6 años, cuyo objetivo es fomentar el aprendizaje mediante la interacción lúdica.

El sistema combina:
- 🤖 Navegación autónoma  
- 🌐 Control remoto desde interfaz web  
- 🧠 Juegos interactivos  

---

## 🎯 Funcionalidades principales

- 🧮 Matemáticas básicas y alfabeto  
- 📚 Cuentos y chistes  
- 🎮 Juegos:
  - Pilla-Pilla  
  - Escondite  
  - Juego del Calamar (Luz Roja / Luz Verde)
- 🌐 Control desde web  
- 🤖 Navegación autónoma  

---

## 📦 Estructura del repositorio

```
patricio/
├── patricio/
├── patricio_calamar/         ← Juego del Calamar (MediaPipe + OpenCV)
├── patricio_captacion/       ← Visión: vision_node, webcam_publisher_linux
├── patricio_my_world/
├── patricio_nav_punto/
├── patricio_pilla_pilla/
├── patricio_escondite/
├── patricio_interfaces/
└── patricio_web/             ← API Flask + interfaz web + calamar_game.html
```

---

## 🧠 Requisitos

- ROS 2 Jazzy instalado
- Ubuntu 22.04 o superior
- Python 3.10+
- Webcam conectada (para Juego del Calamar en modo simulación)

---

## 🔧 Dependencias

### ROS 2 + navegación
```bash
sudo apt install ros-jazzy-desktop
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup
```

### Comunicación web
```bash
sudo apt install ros-jazzy-rosbridge-server
```

### Simulación
```bash
sudo apt install ros-jazzy-turtlebot3*
sudo apt install ros-jazzy-ros-gz*
```

### Visión y cámara
```bash
sudo apt install ros-jazzy-cv-bridge
sudo apt install ros-jazzy-web-video-server
```

### Python — paquetes del sistema
```bash
sudo apt install gnome-terminal
sudo apt install python3-websocket
sudo apt install python3-flask
sudo apt install python3-flask-cors
```

### Python — paquetes pip
```bash
pip install mediapipe --break-system-packages
pip install opencv-python --break-system-packages
pip install sqlalchemy --user --break-system-packages
pip install dotenv --user --break-system-packages
```

⚠️ `sqlalchemy` y `dotenv` son necesarios para el funcionamiento de la base de datos de la API Flask.

### Gestión de dependencias (rosdep)
```bash
sudo apt install python3-rosdep
```

⚠️ Inicializar rosdep (solo la primera vez):
```bash
sudo rosdep init
rosdep update
```

---

## ⚙️ Instalación

```bash
git clone https://github.com/CJMIDNIGHT/patricio.git
cd patricio

rosdep update
rosdep install --from-paths src --ignore-src -r -y

colcon build
source install/setup.bash
```

---

## ⚡ Ejecución rápida de todo el sistema

```bash
bash ~/turtlebot3_ws/src/patricio/patricio_web/static/arrancar_web.sh
```

Este script lanza automáticamente todos los nodos necesarios incluyendo Gazebo, navegación, rosbridge, web_video_server, API Flask, webcam, visión y todos los juegos.

---

## 🚀 Ejecución manual

### 🌍 Simulación
```bash
ros2 launch patricio_my_world house.launch.py
```

### 🧭 Navegación
```bash
ros2 launch patricio_nav_punto my_navigation.launch.py
```

⚠️ En RViz usar **2D Pose Estimate**

---

## 🎮 Juegos

### 🕹️ Pilla-Pilla

```bash
# Terminal 1
ros2 launch patricio_my_world house.launch.py

# Terminal 2
ros2 launch patricio_nav_punto my_navigation.launch.py

# Terminal 3
ros2 launch patricio_pilla_pilla pilla_pilla.launch.py

# Terminal 4
ros2 service call /start_game patricio_interfaces/srv/StartGame "{game_name: 'pilla_pilla'}"
```

---

### 🕹️ Escondite

```bash
# Terminal 1
ros2 launch patricio_my_world house.launch.py

# Terminal 2
ros2 launch patricio_nav_punto my_tb3_navigator.launch.py

# Terminal 3
ros2 run patricio_escondite escondite_service

# Terminal 4
ros2 topic echo /patricio/escondite/status

# Terminal 5
ros2 service call /patricio/escondite/iniciar patricio_interfaces/srv/IniciarEscondite "{command: 'START', poses: {...}}"
```

---

### 🦑 Juego del Calamar — Luz Roja / Luz Verde

Detección de movimiento en tiempo real mediante **MediaPipe Pose** con visualización del esqueleto corporal sobre el feed de cámara.

**Modo simulación (webcam del ordenador):**

```bash
# Terminal 1 — Rosbridge
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

# Terminal 2 — Webcam publisher (Linux nativo)
ros2 run patricio_captacion webcam_publisher_linux

# Terminal 3 — Vision node (procesa y reenvía el feed)
ros2 run patricio_captacion vision_node

# Terminal 4 — web_video_server (stream al navegador)
ros2 run web_video_server web_video_server

# Terminal 5 — Nodo del juego (MediaPipe + lógica)
ros2 launch patricio_calamar calamar.launch.py

# Terminal 6 — API Flask
cd ~/turtlebot3_ws/src/patricio/patricio_web
python3 patricio_api.py

# Terminal 7 — Servidor web
cd ~/turtlebot3_ws/src/patricio/patricio_web
python3 -m http.server 8000
```

Acceso: `http://<IP>:8000/admin.html` → pulsar botón 🦑  
La página del juego se abre automáticamente en una nueva pestaña.

**Tópicos ROS del juego del calamar:**

| Tópico | Tipo | Descripción |
|--------|------|-------------|
| `/patricio/calamar/cmd` | String | Comandos: START_AUTO, CAMBIAR_A_VERDE, CAMBIAR_A_ROJO, STOP |
| `/patricio/calamar/status` | String | Estado: ESPERA, LUZ_VERDE, LUZ_ROJA |
| `/patricio/alerta_juego` | String | Publica INFRACCION al detectar movimiento |
| `/patricio/calamar/camera_annotated` | Image | Feed con esqueleto MediaPipe dibujado |
| `/patricio/camera_processed` | Image | Feed procesado por vision_node |

**Parámetros configurables (`calamar.launch.py`):**

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `pose_movement_threshold` | 0.015 | Sensibilidad de detección (menor = más sensible) |
| `verde_min_sec` | 3.0 | Duración mínima de luz verde (s) |
| `verde_max_sec` | 6.0 | Duración máxima de luz verde (s) |
| `rojo_min_sec` | 3.0 | Duración mínima de luz roja (s) |
| `rojo_max_sec` | 5.0 | Duración máxima de luz roja (s) |
| `pose_fallback_pixel` | True | Usar diferencia de píxeles si no hay persona detectada |

---

## 🌐 Interfaz web

```bash
# Terminal 1
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

# Terminal 2
ros2 launch patricio_nav_punto my_tb3_navigator.launch.py

# Terminal 3
ros2 launch patricio_my_world house.launch.py

# Terminal 4
cd ~/turtlebot3_ws/src/patricio/patricio_web
python3 -m http.server 8000
```

Acceso: `http://<IP_DEL_ROBOT>:8000/admin.html`

---

## 🎛️ Funcionalidades web

- Control del robot  
- Inicio / parada de juegos  
- Monitorización  
- Login  
- Feed de cámara en tiempo real  
- Juego del Calamar con detección de movimiento  

---

## 🧪 Verificación

- ✔ Control desde la web  
- ✔ Comunicación Web ↔ ROS  
- ✔ Navegación autónoma  
- ✔ Juegos funcionando  
- ✔ Juego del Calamar funcionando  
- ✔ Detección de movimiento con MediaPipe Pose  
- ✔ Feed de cámara en tiempo real (web_video_server)  
- ✔ Esqueleto corporal visible sobre el feed  
- ✔ Modo automático y manual del Calamar  
- ✔ Texto a voz en español (Luz Verde / Luz Roja)  

---

## 🔍 Troubleshooting

### 🌐 Problema 1: La web muestra "Disconnected"
- Verificar que rosbridge está en ejecución:
  ```bash
  ros2 launch rosbridge_server rosbridge_websocket_launch.xml
  ```
- Comprobar que el puerto 9090 está activo
- Revisar la IP introducida en la web (`ws://<IP>:9090`)
- Comprobar firewall o red

---

### 🔗 Problema 2: No conecta la web con el robot
- Asegurarse de haber lanzado rosbridge
- Verificar que el robot/simulación está en ejecución
- Revisar conexión de red entre cliente y robot

---

### 🤖 Problema 3: El robot no se mueve
- Verificar que la navegación está lanzada:
  ```bash
  ros2 launch patricio_nav_punto my_navigation.launch.py
  ```
- Comprobar que se ha hecho **2D Pose Estimate** en RViz
- Verificar que el mapa está cargado correctamente
- Revisar que `/cmd_vel` recibe mensajes

---

### 🎮 Problema 4: El juego Pilla-Pilla no inicia
- Verificar que el nodo está activo:
  ```bash
  ros2 run patricio_pilla_pilla pilla_pilla_node
  ```
- Comprobar que el servicio `/start_game` está disponible
- Revisar logs en consola

---

### 📍 Problema 5: El robot no llega a los waypoints
- Comprobar tolerancia de llegada
- Verificar que los puntos están en zona navegable del mapa
- Revisar si hay obstáculos en el entorno

---

### 🗺️ Problema 6: No se ve el mapa en la web
- Verificar que `/map` está siendo publicado
- Comprobar conexión con rosbridge
- Revisar errores en consola del navegador

---

### 🔐 Problema 7: El login no funciona
- Verificar credenciales introducidas
- Revisar conexión con la API Flask
- Comprobar que el backend está activo

---

### 📷 Problema 8: Feed de cámara negro en el Juego del Calamar
- Verificar que `web_video_server` está corriendo en el puerto 8080:
  ```bash
  curl -I "http://localhost:8080/stream?topic=/patricio/camera_processed"
  ```
- Si falla, lanzar manualmente:
  ```bash
  ros2 run web_video_server web_video_server
  ```
- Verificar que `webcam_publisher_linux` y `vision_node` están activos:
  ```bash
  ros2 topic hz /patricio/camera_processed
  ```

---

### 🦴 Problema 9: No se ve el esqueleto en el juego
- Verificar que el nodo calamar está corriendo y recibe frames:
  ```bash
  ros2 topic hz /patricio/calamar/camera_annotated
  ```
- Comprobar que hay buena iluminación y la persona es visible entera en cámara
- Verificar la versión de MediaPipe:
  ```bash
  python3 -c "import mediapipe; print(mediapipe.__version__)"
  ```
  Versión recomendada: 0.10.x

---

### 🦑 Problema 10: "❌ No se pudo conectar con la API" en el Calamar
- Verificar que `patricio_api.py` está corriendo:
  ```bash
  curl http://localhost:5000/api/calamar/estado
  ```
  La respuesta debe incluir `alerta_ts` y `pose_detected`. Si no aparecen, el API está desactualizado — reemplazar con la versión correcta del repositorio.

---

### 💥 Problema 11: El nodo Calamar se cierra solo (exit code -11)
- Este error es un segfault causado por procesar MediaPipe en dos hilos simultáneamente.
- Verificar que se está usando la versión más reciente de `juego_calamar_node.py` del repositorio, que comparte los resultados de pose entre callbacks en lugar de procesarlos dos veces.

---

## 👥 Autores

- Adenor Buret — https://github.com/CJMIDNIGHT  
- Santiago Aguirre Crespo — https://github.com/Saac04  
- Pablo Meana — https://github.com/Meana13  
- Mari Dapcheva — https://github.com/ohmarimari  
- César Herrero — https://github.com/ElCesarEse  
- Juan Bautista — https://github.com/jbperfon