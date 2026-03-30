import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    """
    Genera la descripción de lanzamiento para el nodo robot_state_publisher.

    Lee el archivo URDF del modelo TurtleBot3 especificado por la variable de
    entorno TURTLEBOT3_MODEL y lanza el nodo robot_state_publisher, que publica
    las transformaciones TF del robot a partir de su descripción cinemática.

    El URDF se carga desde el paquete patricio_my_world, permitiendo usar modelos
    personalizados como turtlebot3_burger o turtlebot3_burger_cam.

    Launch Arguments:
        use_sim_time (bool): Usar el reloj de simulación de Gazebo. Por defecto: 'true'.
        frame_prefix (str): Prefijo opcional para los frames TF del robot. Por defecto: ''.

    Environment Variables:
        TURTLEBOT3_MODEL (str): Modelo del robot a cargar. Por defecto: 'burger'.

    Returns:
        LaunchDescription: Conjunto de acciones a ejecutar en el lanzamiento.
    """

    # -----------------------------------------------------------------------
    # Modelo del robot
    # Lee la variable de entorno TURTLEBOT3_MODEL para determinar qué URDF
    # cargar. Si no está definida, usa 'burger' como valor por defecto
    # -----------------------------------------------------------------------
    TURTLEBOT3_MODEL = os.environ.get('TURTLEBOT3_MODEL', 'burger')

    # -----------------------------------------------------------------------
    # Parámetros configurables
    # use_sim_time sincroniza el nodo con el reloj de Gazebo
    # frame_prefix permite añadir un prefijo a los frames TF del robot,
    # útil en entornos multi-robot
    # -----------------------------------------------------------------------
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    frame_prefix = LaunchConfiguration('frame_prefix', default='')

    # -----------------------------------------------------------------------
    # Ruta al archivo URDF
    # Construye el nombre del archivo URDF a partir del modelo seleccionado
    # y obtiene su ruta absoluta dentro del paquete patricio_my_world
    # -----------------------------------------------------------------------
    urdf_file_name = 'turtlebot3_' + TURTLEBOT3_MODEL + '.urdf'

    urdf_path = os.path.join(
        get_package_share_directory('patricio_my_world'),
        'urdf',
        urdf_file_name
    )

    # -----------------------------------------------------------------------
    # Lectura del URDF
    # Lee el contenido del archivo URDF como string para pasarlo como
    # parámetro al nodo robot_state_publisher
    # -----------------------------------------------------------------------
    with open(urdf_path, 'r') as infp:
        robot_desc = infp.read()

    # -----------------------------------------------------------------------
    # LaunchDescription
    # Declara el argumento use_sim_time y lanza el nodo robot_state_publisher
    # con la descripción del robot, el tiempo de simulación y el prefijo de
    # frames TF configurados
    # -----------------------------------------------------------------------
    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use simulation clock'
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'robot_description': robot_desc,
                'frame_prefix': PythonExpression(["'", frame_prefix, "/'"])
            }],
        ),
    ])