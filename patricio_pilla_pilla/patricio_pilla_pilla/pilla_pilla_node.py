
#!/usr/bin/env python3

import math
import random
import yaml
import cv2
import threading

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from patricio_interfaces.srv import StartGame


class PillaPillaNode(Node):

    def __init__(self):
        super().__init__('pilla_pilla_node')

        # ---------------- PARÁMETROS ----------------
        self.declare_parameter('route_mode', 'random')
        self.declare_parameter('map_yaml', '')
        self.declare_parameter('random_num_points', 5)
        self.declare_parameter('circle_center_x', 0.0)
        self.declare_parameter('circle_center_y', 0.0)
        self.declare_parameter('circle_radius', 1.5)

        self.route_mode = self.get_parameter('route_mode').get_parameter_value().string_value
        self.map_yaml = self.get_parameter('map_yaml').get_parameter_value().string_value
        self.random_num_points = self.get_parameter('random_num_points').get_parameter_value().integer_value
        self.circle_center_x = self.get_parameter('circle_center_x').get_parameter_value().double_value
        self.circle_center_y = self.get_parameter('circle_center_y').get_parameter_value().double_value
        self.circle_radius = self.get_parameter('circle_radius').get_parameter_value().double_value

        # ---------------- ESTADO ----------------
        self.running = False
        self.stop_requested = False
        self.current_waypoint_index = 0
        self.waypoints = []
        self.current_pos = (0.0, 0.0)
        self._game_thread = None

        # ---------------- ROS ----------------
        self.status_pub = self.create_publisher(String, '/patricio/pilla_pilla/status', 10)

        self.goal_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)

        self.cmd_sub = self.create_subscription(
            String, '/patricio/pilla_pilla/cmd', self.cmd_callback, 10)

        self.odom_sub = self.create_subscription(
            Odometry, '/odom', self.odom_callback, 10)

        self.srv = self.create_service(StartGame, '/start_game', self.handle_start_game)

        # ---------------- MAPA ----------------
        self.free_cells = []
        self.load_map()

        self.publish_status('Descansando')
        self.get_logger().info('Nodo pilla_pilla_node listo.')
        self.get_logger().info('Servicio disponible en /start_game')

    # ------------------------------------------------
    # ODOMETRY — track current position
    # ------------------------------------------------
    def odom_callback(self, msg):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        self.current_pos = (x, y)

    # ------------------------------------------------
    # MAPA
    # ------------------------------------------------
    def load_map(self):
        if self.map_yaml == '':
            self.get_logger().warn('No se indicó map_yaml.')
            return
        try:
            with open(self.map_yaml, 'r') as f:
                data = yaml.safe_load(f)
            pgm_path = data['image']
            resolution = data['resolution']
            origin = data['origin']
            pgm_full_path = self.map_yaml.replace(self.map_yaml.split('/')[-1], pgm_path)
            img = cv2.imread(pgm_full_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise RuntimeError(f'No se pudo leer el mapa: {pgm_full_path}')
            h, w = img.shape
            for y in range(h):
                for x in range(w):
                    if img[y, x] > 250:
                        wx = origin[0] + x * resolution
                        wy = origin[1] + (h - y) * resolution
                        self.free_cells.append((wx, wy))
            self.get_logger().info(f'Mapa cargado: {w}x{h}, celdas libres: {len(self.free_cells)}')
        except Exception as e:
            self.get_logger().error(f'Error cargando mapa: {e}')

    # ------------------------------------------------
    # SERVICIO
    # ------------------------------------------------
    def handle_start_game(self, request, response):
        self.get_logger().info(f'Recibida petición de inicio de {request.game_name}.')
        if request.game_name != 'pilla_pilla':
            response.started = False
            return response
        if self.running:
            self.get_logger().info('El juego ya está en marcha.')
            response.started = True
            return response

        # Start game in background thread — no executor conflict
        self._game_thread = threading.Thread(target=self.game_loop, daemon=True)
        self._game_thread.start()

        response.started = True
        return response

    # ------------------------------------------------
    # GAME LOOP — runs in its own thread
    # ------------------------------------------------
    def game_loop(self):
        self.running = True
        self.stop_requested = False
        self.publish_status('Corriendo')

        # Generate waypoints
        self.waypoints = self.generate_waypoints()
        if len(self.waypoints) == 0:
            self.get_logger().error('No se generaron waypoints.')
            self.running = False
            self.publish_status('Descansando')
            return

        self.get_logger().info(f'Iniciando juego con {len(self.waypoints)} waypoints.')

        for i, waypoint in enumerate(self.waypoints):
            if self.stop_requested:
                self.get_logger().info('Juego detenido por petición.')
                break

            self.current_waypoint_index = i
            self.get_logger().info(f'Navegando a waypoint {i+1}/{len(self.waypoints)}: '
                                   f'({waypoint.pose.position.x:.2f}, {waypoint.pose.position.y:.2f})')

            # Publish goal
            self.goal_pub.publish(waypoint)
            self.publish_status(f'Corriendo - punto {i+1}/{len(self.waypoints)}')

            # Wait until robot reaches waypoint or stop is requested
            reached = self.wait_for_waypoint(
                waypoint.pose.position.x,
                waypoint.pose.position.y,
                tolerance=0.8,
                timeout=30.0
            )

            if self.stop_requested:
                self.get_logger().info('Juego detenido por petición.')
                break

            if reached:
                self.get_logger().info(f'Waypoint {i+1} alcanzado.')
            else:
                self.get_logger().warn(f'Waypoint {i+1} no alcanzado (timeout), continuando...')

        self.running = False

        if self.stop_requested:
            self.publish_status('Descansando')
            self.get_logger().info('Juego cancelado.')
        else:
            self.publish_status('Descansando')
            self.get_logger().info('Juego completado.')

    # ------------------------------------------------
    # WAIT FOR WAYPOINT
    # ------------------------------------------------
    def wait_for_waypoint(self, target_x, target_y, tolerance=0.8, timeout=30.0):
        import time
        start = time.time()
        while not self.stop_requested:
            cx, cy = self.current_pos
            dist = math.sqrt((target_x - cx)**2 + (target_y - cy)**2)
            if dist < tolerance:
                return True
            if time.time() - start > timeout:
                return False
            time.sleep(0.2)
        return False

    # ------------------------------------------------
    # STOP
    # ------------------------------------------------
    def cmd_callback(self, msg):
        cmd = msg.data.upper()
        if cmd in ('STOP', 'DETENER'):
            self.get_logger().info('Petición de parada recibida.')
            self.stop_requested = True
            self.running = False
            self.publish_status('Descansando')

    # ------------------------------------------------
    # WAYPOINTS
    # ------------------------------------------------
    def generate_waypoints(self):
        if self.route_mode == 'circle':
            return self.generate_circle_waypoints()
        return self.generate_random_waypoints()

    def generate_random_waypoints(self):
        points = []
        if len(self.free_cells) == 0:
            return points
        chosen = random.sample(self.free_cells, min(self.random_num_points, len(self.free_cells)))
        for p in chosen:
            points.append(self.create_pose(p[0], p[1]))
        return points

    def generate_circle_waypoints(self):
        points = []
        for i in range(8):
            ang = i * 2.0 * math.pi / 8.0
            x = self.circle_center_x + self.circle_radius * math.cos(ang)
            y = self.circle_center_y + self.circle_radius * math.sin(ang)
            points.append(self.create_pose(x, y))
        return points

    def create_pose(self, x, y):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = 0.0
        pose.pose.orientation.w = 1.0
        return pose

    # ------------------------------------------------
    # STATUS
    # ------------------------------------------------
    def publish_status(self, text):
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PillaPillaNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
