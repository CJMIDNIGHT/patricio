#!/bin/bash
export ROS_DOMAIN_ID=7
export ROS_LOCALHOST_ONLY=0
source ~/turtlebot3_ws/install/setup.bash

# TERMINAL: cara_node
gnome-terminal -- bash -c "
echo '😊 Lanzando cara_node...';
sleep 3;
source ~/turtlebot3_ws/install/setup.bash;
export ROS_DOMAIN_ID=7;
ros2 run patricio_cara cara_node;
exec bash"

# ESPERAR
sleep 5

# ABRIR FACE SCREEN
MYIP=$(ip route get 1.1.1.1 | awk '{print $7; exit}')
echo '🤖 Abriendo Face Screen...'
xdg-open http://${MYIP}:8000/face_screen.html &