#!/bin/bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
export TURTLEBOT3_MODEL=burger_cam
source ~/turtlebot3_ws/install/setup.bash

# TERMINAL 1: Gazebo
gnome-terminal -- bash -c "
echo '🏠 Lanzando Gazebo...';
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 launch patricio_my_world house.launch.py;
exec bash"

# TERMINAL 2: Navegación (Nav2)
gnome-terminal -- bash -c "
echo '🗺️ Lanzando Navegación...';
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 launch patricio_nav_punto my_tb3_navigator.launch.py;
exec bash"

# TERMINAL 3: rosbridge_websocket
gnome-terminal -- bash -c "
echo '📡 Lanzando rosbridge...';
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 launch rosbridge_server rosbridge_websocket_launch.xml;
exec bash"

# TERMINAL 4: web_video_server
gnome-terminal -- bash -c "
echo '📷 Lanzando web_video_server...';
sleep 12;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run web_video_server web_video_server;
exec bash"

# TERMINAL 5: HTTP server
gnome-terminal -- bash -c "
echo '🌐 Servidor web en puerto 8000...';
cd ~/turtlebot3_ws/src/patricio/patricio_web;
python3 -m http.server 8000;
exec bash"

# TERMINAL 6: Flask API
gnome-terminal -- bash -c "
echo '🎮 Lanzando Patricio API...';
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
cd ~/turtlebot3_ws/src/patricio/patricio_web;
python3 patricio_api.py;
exec bash"

# TERMINAL 7: Pilla-Pilla node (nuevo — seguimiento visual)
gnome-terminal -- bash -c "
echo '🏃 Lanzando nodo Pilla-Pilla (vision follower)...';
sleep 5;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 launch patricio_pilla_pilla pilla_pilla_vision.launch.py;
exec bash"

# TERMINAL 8: Escondite node
gnome-terminal -- bash -c "
echo '🔍 Lanzando nodo Escondite...';
sleep 10;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run patricio_escondite escondite_service;
exec bash"

# TERMINAL 9: Juego del Calamar (nuevo — con fallback MediaPipe)
gnome-terminal -- bash -c "
echo '🦑 Lanzando nodo Calamar...';
sleep 8;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run patricio_calamar juego_calamar_node;
exec bash"

# TERMINAL 10: Vision node (procesado de cámara)
gnome-terminal -- bash -c "
echo '👁️ Lanzando Vision Node...';
sleep 5;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
export TURTLEBOT3_MODEL=burger_cam;
ros2 launch patricio_captacion vision.launch.py;
exec bash"

# TERMINAL 11: Webcam publisher (WSL — conecta con servidor Python en Windows)
# Asegúrate de que el servidor camera_server.py está corriendo en Windows antes de lanzar
gnome-terminal -- bash -c "
echo '📷 Lanzando webcam publisher (WSL)...';
sleep 6;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run patricio_captacion webcam_publisher;
exec bash"

# TERMINAL 12: MediaPipe node (nuevo — centraliza detección de personas)
gnome-terminal -- bash -c "
echo '🤖 Lanzando MediaPipe node...';
sleep 8;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run patricio_vision mediapipe_node;
exec bash"

sleep 10
MYIP=$(ip route get 1.1.1.1 | awk '{print $7; exit}')
xdg-open http://${MYIP}:8000/admin.html