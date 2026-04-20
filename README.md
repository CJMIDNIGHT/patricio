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
- 🌐 Control desde web  
- 🤖 Navegación autónoma  

---

## 📦 Estructura del repositorio

patricio/
├── patricio/
├── patricio_captacion/
├── patricio_my_world/
├── patricio_nav_punto/
├── patricio_pilla_pilla/
├── patricio_escondite/
├── patricio_interfaces/
└── patricio_web/

---
## 🧠 Requisitos

- ROS 2 Jazzy instalado
- Ubuntu 22.04 o superior
- Python 3.10+

## 🔧 Dependencias

# ROS2 + navegación
sudo apt install ros-jazzy-desktop
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup

# Comunicación web
sudo apt install ros-jazzy-rosbridge-server

# Simulación
sudo apt install ros-jazzy-turtlebot3*
sudo apt install ros-jazzy-ros-gz*

# Python
sudo apt install gnome-terminal  
sudo apt install python3-websocket  
sudo apt install python3-flask  
sudo apt install python3-flask-cors  

#Gestión de dependencias (rosdep)

sudo apt install python3-rosdep

⚠️ Inicializar rosdep (solo la primera vez):

sudo rosdep init
rosdep update

---

## ⚙️ Instalación

git clone https://github.com/CJMIDNIGHT/patricio.git  
cd patricio  

rosdep update  
rosdep install --from-paths src --ignore-src -r -y  

colcon build  
source install/setup.bash  

---

## ⚡ Ejecución rápida de todo el sistema

bash ~/turtlebot3_ws/src/patricio/patricio_web/static/arrancar_web.sh

---

## 🚀 Ejecución manual

### 🌍 Simulación
ros2 launch patricio_my_world house.launch.py

### 🧭 Navegación
ros2 launch patricio_nav_punto my_navigation.launch.py

⚠️ En RViz usar 2D Pose Estimate

---

## 🎮 Juegos

### 🕹️ Pilla-Pilla

Terminal 1:
ros2 launch patricio_my_world house.launch.py

Terminal 2:
ros2 launch patricio_nav_punto my_navigation.launch.py

Terminal 3:
ros2 launch patricio_pilla_pilla pilla_pilla.launch.py

Terminal 4:
ros2 service call /start_game patricio_interfaces/srv/StartGame "{game_name: 'pilla_pilla'}"

---

### 🕹️ Escondite

Terminal 1:
ros2 launch patricio_my_world house.launch.py

Terminal 2:
ros2 launch patricio_nav_punto my_tb3_navigator.launch.py

Terminal 3:
ros2 run patricio_escondite escondite_service

Terminal 4:
ros2 topic echo /patricio/escondite/status

Terminal 5:
ros2 service call /patricio/escondite/iniciar patricio_interfaces/srv/IniciarEscondite "{command: 'START', poses: {...}}"

---

## 🌐 Interfaz web

Terminal 1:
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

Terminal 2:
ros2 launch patricio_nav_punto my_tb3_navigator.launch.py

Terminal 3:
ros2 launch patricio_my_world house.launch.py

Terminal 4:
cd ~/turtlebot3_ws/src/patricio/patricio_web  
python3 -m http.server 8000  

Acceso:
http://<IP_DEL_ROBOT>:8000/admin.html

---

## 🎛️ Funcionalidades web

- Control del robot  
- Inicio / parada de juegos  
- Monitorización  
- Login  

---

## 🧪 Verificación

✔ Control desde la web  
✔ Comunicación Web ↔ ROS  
✔ Navegación autónoma  
✔ Juegos funcionando  

---

##Troubleshooting

A continuación se describen los problemas más comunes detectados durante el uso del sistema y sus posibles soluciones.

### 🌐 Problema 1: La web muestra "Disconnected"
- 🔌 Verificar que rosbridge está en ejecución:
  ros2 launch rosbridge_server rosbridge_websocket_launch.xml
- 📡 Comprobar que el puerto 9090 está activo
- 🌍 Revisar la IP introducida en la web (ws://<IP>:9090)
- 🔥 Comprobar firewall o red

---

### 🔗 Problema 2: No conecta la web con el robot
- ▶️ Asegurarse de haber lanzado rosbridge
- 🤖 Verificar que el robot/simulación está en ejecución
- 🌐 Revisar conexión de red entre cliente y robot

---

### 🤖 Problema 3: El robot no se mueve
- 🚀 Verificar que la navegación está lanzada:
  ros2 launch patricio_nav_punto my_navigation.launch.py
- 📍 Comprobar que se ha hecho "2D Pose Estimate" en RViz
- 🗺️ Verificar que el mapa está cargado correctamente
- 📤 Revisar que /cmd_vel recibe mensajes

---

### 🎮 Problema 4: El juego Pilla-Pilla no inicia
- ▶️ Verificar que el nodo está activo:
  ros2 run patricio_pilla_pilla pilla_pilla_node
- 🔌 Comprobar que el servicio /start_game está disponible
- 🧾 Revisar logs en consola

---

### 📍 Problema 5: El robot no llega a los waypoints
- 🎯 Comprobar tolerancia de llegada
- 🗺️ Verificar que los puntos están en zona navegable del mapa
- 🚧 Revisar si hay obstáculos en el entorno

---

### 🗺️ Problema 6: No se ve el mapa en la web
- 📡 Verificar que /map está siendo publicado
- 🔗 Comprobar conexión con rosbridge
- 🖥️ Revisar errores en consola del navegador

---

### 🔐 Problema 7: El login no funciona
- 👤 Verificar credenciales introducidas
- 🔌 Revisar conexión con la API Flask
- 🖥️ Comprobar que el backend está activo

## 👥 Autores

Adenor Buret — https://github.com/CJMIDNIGHT  
Santiago Aguirre Crespo — https://github.com/Saac04  
Pablo Meana — https://github.com/Meana13  
Mari Dapcheva — https://github.com/ohmarimari  
César Herrero — https://github.com/ElCesarEse  
Juan Bautista — https://github.com/jbperfon  

