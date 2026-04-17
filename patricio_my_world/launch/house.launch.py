import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """
    Genera la descripción de lanzamiento para el entorno de simulación doméstica.

    Configura el entorno completo de simulación incluyendo:
    - Rutas de recursos de Gazebo (modelos propios del paquete y modelos de TurtleBot3)
    - Lanzamiento del simulador Gazebo con el mundo house.sdf
    - Publicación del estado del robot mediante robot_state_publisher
    - Inserción del robot TurtleBot3 en el mundo en la posición inicial especificada

    El mundo cargado (house.sdf) contiene una vivienda con mobiliario y un modelo
    de niño (kumaeye) que actúa como obstáculo detectable por el sensor LiDAR del robot.

    Launch Arguments:
        use_sim_time (bool): Usar el reloj de simulación de Gazebo. Por defecto: 'true'.
        x_pose (float): Posición inicial del robot en el eje X. Por defecto: '1.0'.
        y_pose (float): Posición inicial del robot en el eje Y. Por defecto: '1.0'.

    Returns:
        LaunchDescription: Conjunto ordenado de acciones a ejecutar en el lanzamiento.
    """

    # -----------------------------------------------------------------------
    # Rutas de paquetes
    # Obtiene las rutas absolutas de los paquetes necesarios para el lanzamiento
    # -----------------------------------------------------------------------
    pkg = get_package_share_directory('patricio_my_world')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    launch_dir = os.path.join(pkg, 'launch')
    world = os.path.join(pkg, 'worlds', 'house.sdf')

    # -----------------------------------------------------------------------
    # Parámetros configurables
    # Permiten sobreescribir valores desde la línea de comandos al lanzar
    # -----------------------------------------------------------------------
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    x_pose = LaunchConfiguration('x_pose', default='-2.0')
    y_pose = LaunchConfiguration('y_pose', default='-2.0')

    # -----------------------------------------------------------------------
    # Variables de entorno — modelos propios
    # Añade la carpeta models/ del paquete a GZ_SIM_RESOURCE_PATH para que
    # Gazebo pueda encontrar los modelos locales (turtlebot3_burger, kumaeye, etc.)
    # -----------------------------------------------------------------------
    set_env_models = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(pkg, 'models')
    )

    # -----------------------------------------------------------------------
    # Variables de entorno — modelos de TurtleBot3
    # Añade los modelos oficiales de turtlebot3_gazebo a GZ_SIM_RESOURCE_PATH
    # para que Gazebo pueda encontrar el URDF y meshes del robot
    # -----------------------------------------------------------------------
    set_env_tb3 = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(
            get_package_share_directory('turtlebot3_gazebo'),
            'models'
        )
    )

    # -----------------------------------------------------------------------
    # Lanzamiento de Gazebo
    # Inicia el simulador Gazebo con el mundo house.sdf en modo ejecución (-r)
    # y verbosidad nivel 2 (-v2). on_exit_shutdown cierra todo el sistema
    # cuando se cierra Gazebo
    # -----------------------------------------------------------------------
    gz_sim_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': ['-r -v2 ', world],
            'on_exit_shutdown': 'true'
        }.items()
    )

    # -----------------------------------------------------------------------
    # Robot State Publisher
    # Publica las transformaciones TF del robot a partir de su URDF,
    # necesario para que el resto del sistema conozca la geometría del robot
    # -----------------------------------------------------------------------
    robot_state_publisher_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'robot_state_publisher.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items()
    )

    # -----------------------------------------------------------------------
    # Spawn del robot
    # Inserta el modelo del TurtleBot3 en el mundo de Gazebo en la posición
    # inicial definida por x_pose e y_pose, e inicia el bridge ROS-Gazebo
    # para los topics de sensores y actuadores
    # -----------------------------------------------------------------------
    spawn_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'spawn_turtlebot3.launch.py')
        ),
        launch_arguments={
            'x_pose': x_pose,
            'y_pose': y_pose
        }.items()
    )
    
    

    # -----------------------------------------------------------------------
    # Construcción del LaunchDescription
    # El orden es importante: primero se configuran las rutas de recursos,
    # luego se lanza el simulador, y finalmente el robot
    # -----------------------------------------------------------------------
    ld = LaunchDescription()
    ld.add_action(set_env_models)
    ld.add_action(set_env_tb3)
    ld.add_action(gz_sim_cmd)
    ld.add_action(robot_state_publisher_cmd)
    ld.add_action(spawn_cmd)
    
    bridge_cmd = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        parameters=[{
            'config_file': os.path.join(pkg, 'config', 'turtlebot3_burger_bridge.yaml'),
            'qos_overrides./tf_static.publisher.durability': 'transient_local',
        }],
        output='screen'
    )
    
    ld.add_action(bridge_cmd)

    return ld
