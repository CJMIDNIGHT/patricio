#!/bin/bash

# ========================
# CONFIGURACIÓN GLOBAL
# ========================
export ROS_DOMAIN_ID=1
export ROS_LOCALHOST_ONLY=0
export TURTLEBOT3_MODEL=burger
source ~/turtlebot3_ws/install/setup.bash

# ========================
# TERMINAL 1: rosbridge_websocket
# ========================
gnome-terminal -- bash -c "
echo '📡 Lanzando rosbridge...';
ros2 launch rosbridge_server rosbridge_websocket_launch.xml;
exec bash"

# ========================
# TERMINAL 2: web_video_server
# ========================
gnome-terminal -- bash -c "
echo '📷 Lanzando web_video_server...';
ros2 run web_video_server web_video_server;
exec bash"

# ========================
# TERMINAL 3: HTTP server
# ========================
gnome-terminal -- bash -c "
echo '🌐 Servidor web en puerto 8000...';
cd ~/turtlebot3_ws/src/pamabot/pamabot_web;
python3 -m http.server 8000;
exec bash"

# ========================
# TERMINAL 4: Nav2 + Mapa + RViz
# ========================
gnome-terminal -- bash -c "
echo '🗺️ Lanzando sistema de navegación con mapa y RViz...';
ros2 launch my_nav2_system rviz_nav2.launch.py;
exec bash"




# ========================
# ESPERAR Y ABRIR NAVEGADOR
# ========================
sleep 3
xdg-open http://192.168.0.115:8000/admin.html
