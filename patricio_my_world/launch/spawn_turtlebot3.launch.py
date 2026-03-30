import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """
    Genera la descripción de lanzamiento para insertar el TurtleBot3 en Gazebo.

    Se encarga de dos tareas principales:
    - Insertar el modelo SDF del robot en el mundo de Gazebo en la posición
      inicial especificada mediante el nodo 'create' de ros_gz_sim.
    - Lanzar el bridge ROS-Gazebo (ros_gz_bridge) con la configuración YAML
      correspondiente al modelo, conectando los topics de sensores y actuadores
      entre Gazebo y ROS 2.

    El modelo y el archivo de configuración del bridge se seleccionan
    automáticamente en función de la variable de entorno TURTLEBOT3_MODEL.

    Launch Arguments:
        x_pose (float): Posición inicial del robot en el eje X. Por defecto: '0.0'.
        y_pose (float): Posición inicial del robot en el eje Y. Por defecto: '0.0'.

    Environment Variables:
        TURTLEBOT3_MODEL (str): Modelo del robot a insertar. Por defecto: 'burger'.

    Returns:
        LaunchDescription: Conjunto de acciones a ejecutar en el lanzamiento.
    """

    # -----------------------------------------------------------------------
    # Modelo del robot
    # Lee la variable de entorno TURTLEBOT3_MODEL para determinar qué modelo
    # SDF insertar en Gazebo. Si no está definida, usa 'burger' por defecto
    # -----------------------------------------------------------------------
    TURTLEBOT3_MODEL = os.environ.get('TURTLEBOT3_MODEL', 'burger')
    model_folder = 'turtlebot3_' + TURTLEBOT3_MODEL

    # -----------------------------------------------------------------------
    # Ruta al modelo SDF
    # Construye la ruta absoluta al archivo model.sdf del robot dentro del
    # paquete patricio_my_world
    # -----------------------------------------------------------------------
    model_path = os.path.join(
        get_package_share_directory('patricio_my_world'),
        'models',
        model_folder,
        'model.sdf'
    )

    # -----------------------------------------------------------------------
    # Parámetros configurables
    # Posición inicial del robot en el plano XY del mundo de Gazebo
    # -----------------------------------------------------------------------
    x_pose = LaunchConfiguration('x_pose', default='0.0')
    y_pose = LaunchConfiguration('y_pose', default='0.0')

    # -----------------------------------------------------------------------
    # Declaración de argumentos de lanzamiento
    # Permite sobreescribir la posición inicial desde la línea de comandos
    # -----------------------------------------------------------------------
    declare_x = DeclareLaunchArgument('x_pose', default_value='0.0')
    declare_y = DeclareLaunchArgument('y_pose', default_value='0.0')

    # -----------------------------------------------------------------------
    # Spawn del robot
    # Inserta el modelo SDF del TurtleBot3 en el mundo activo de Gazebo
    # en la posición especificada, con una altura de 0.1m sobre el suelo
    # -----------------------------------------------------------------------
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', TURTLEBOT3_MODEL,
            '-file', model_path,
            '-x', x_pose,
            '-y', y_pose,
            '-z', '0.1'
        ],
        output='screen'
    )

    # -----------------------------------------------------------------------
    # Configuración del bridge ROS-Gazebo
    # Construye la ruta al archivo YAML de configuración del bridge,
    # que define los topics a conectar entre Gazebo y ROS 2
    # (clock, joint_states, odom, tf, cmd_vel, imu, scan)
    # -----------------------------------------------------------------------
    bridge_params = os.path.join(
        get_package_share_directory('patricio_my_world'),
        'params',
        model_folder + '_bridge.yaml'
    )

    # -----------------------------------------------------------------------
    # Bridge ROS-Gazebo
    # Lanza el nodo parameter_bridge con la configuración YAML del modelo,
    # habilitando la comunicación bidireccional entre ROS 2 y Gazebo
    # para todos los sensores y actuadores del robot
    # -----------------------------------------------------------------------
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '--ros-args',
            '-p',
            f'config_file:={bridge_params}',
        ],
        output='screen'
    )

    # -----------------------------------------------------------------------
    # Construcción del LaunchDescription
    # Orden: primero se declaran los argumentos, luego se inserta el robot
    # y finalmente se lanza el bridge de comunicación
    # -----------------------------------------------------------------------
    return LaunchDescription([
        declare_x,
        declare_y,
        spawn,
        bridge
    ])