#!/usr/bin/env python3

import math
import random
import yaml
import cv2

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

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

        self.route_mode = self.get_parameter(
            'route_mode').get_parameter_value().string_value

        self.map_yaml = self.get_parameter(
            'map_yaml').get_parameter_value().string_value

        self.random_num_points = self.get_parameter(
            'random_num_points').get_parameter_value().integer_value

        self.circle_center_x = self.get_parameter(
            'circle_center_x').get_parameter_value().double_value

        self.circle_center_y = self.get_parameter(
            'circle_center_y').get_parameter_value().double_value

        self.circle_radius = self.get_parameter(
            'circle_radius').get_parameter_value().double_value

        # ---------------- ESTADO ----------------
        self.running = False
        self.start_requested = False
        self.stop_requested = False

        # ---------------- ROS ----------------
        self.status_pub = self.create_publisher(
            String,
            '/patricio/pilla_pilla/status',
            10
        )

        self.cmd_sub = self.create_subscription(
            String,
            '/patricio/pilla_pilla/cmd',
            self.cmd_callback,
            10
        )

        self.srv = self.create_service(
            StartGame,
            '/start_game',
            self.handle_start_game
        )

        self.navigator = BasicNavigator()

        # timer principal para gestionar arranque/parada fuera del callback del servicio
        self.control_timer = self.create_timer(0.5, self.control_loop)

        # cargar mapa
        self.free_cells = []
        self.load_map()

        self.publish_status('Descansando')

        self.get_logger().info('Nodo pilla_pilla_node listo.')
        self.get_logger().info('Servicio disponible en /start_game')

    # ----------------------------------------------------
    # CARGA MAPA
    # ----------------------------------------------------
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

            self.get_logger().info(
                f'Mapa cargado: {w}x{h}, celdas libres: {len(self.free_cells)}'
            )

        except Exception as e:
            self.get_logger().error(f'Error cargando mapa: {e}')

    # ----------------------------------------------------
    # SERVICIO
    # ----------------------------------------------------
    def handle_start_game(self, request, response):
        self.get_logger().info(
            f'Recibida petición de inicio de {request.game_name}.'
        )

        if request.game_name != 'pilla_pilla':
            response.started = False
            return response

        if self.running or self.start_requested:
            self.get_logger().info('El juego ya está en marcha o pendiente de arrancar.')
            response.started = True
            return response

        self.start_requested = True
        response.started = True
        return response

    # ----------------------------------------------------
    # LOOP DE CONTROL
    # ----------------------------------------------------
    def control_loop(self):
        # arrancar juego fuera del callback del servicio
        if self.start_requested and not self.running:
            self.start_requested = False
            self.start_game_internal()

        # parar juego fuera del callback del subscriber
        if self.stop_requested:
            self.stop_requested = False
            self.stop_game_internal()

        # comprobar si terminó la navegación
        if self.running and self.navigator.isTaskComplete():
            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:
                self.get_logger().info('Juego completado.')
            elif result == TaskResult.CANCELED:
                self.get_logger().info('Juego cancelado.')
            elif result == TaskResult.FAILED:
                self.get_logger().warn('La navegación falló.')
            else:
                self.get_logger().warn('Resultado desconocido.')

            self.running = False
            self.publish_status('Descansando')

    # ----------------------------------------------------
    # INICIAR / PARAR JUEGO
    # ----------------------------------------------------
    def start_game_internal(self):
        try:
            self.get_logger().info('Iniciando juego pilla pilla...')

            waypoints = self.generate_waypoints()

            if len(waypoints) == 0:
                self.get_logger().error('No se generaron waypoints.')
                self.publish_status('Descansando')
                return

            self.navigator.followWaypoints(waypoints)

            self.running = True
            self.publish_status('Corriendo')
            self.get_logger().info(f'Following {len(waypoints)} goals....')

        except Exception as e:
            self.get_logger().error(f'Error al iniciar el juego: {e}')
            self.running = False
            self.publish_status('Descansando')

    def stop_game_internal(self):
        try:
            self.get_logger().info('Deteniendo juego...')
            self.navigator.cancelTask()
        except Exception as e:
            self.get_logger().warn(f'Error al cancelar navegación: {e}')

        self.running = False
        self.publish_status('Descansando')

    # ----------------------------------------------------
    # COMANDOS STOP
    # ----------------------------------------------------
    def cmd_callback(self, msg):
        cmd = msg.data.upper()

        if cmd in ('STOP', 'DETENER'):
            self.get_logger().info('Petición de parada recibida.')
            self.stop_requested = True

    # ----------------------------------------------------
    # GENERAR WAYPOINTS
    # ----------------------------------------------------
    def generate_waypoints(self):
        if self.route_mode == 'circle':
            return self.generate_circle_waypoints()

        return self.generate_random_waypoints()

    def generate_random_waypoints(self):
        points = []
        if len(self.free_cells) == 0:
            return points

        chosen = random.sample(
            self.free_cells,
            min(self.random_num_points, len(self.free_cells))
        )

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

    # ----------------------------------------------------
    # CREAR POSE
    # ----------------------------------------------------
    def create_pose(self, x, y):
        pose = PoseStamped()

        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()

        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = 0.0

        pose.pose.orientation.x = 0.0
        pose.pose.orientation.y = 0.0
        pose.pose.orientation.z = 0.0
        pose.pose.orientation.w = 1.0

        return pose

    # ----------------------------------------------------
    # STATUS
    # ----------------------------------------------------
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
