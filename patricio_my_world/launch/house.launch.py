import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    """
    Genera la descripción de lanzamiento para el entorno de simulación.

    Configura:
    - Rutas de recursos de Gazebo (modelos propios y de TurtleBot3)
    - Lanzamiento del simulador con el mundo definido
    - Publicación del estado del robot
    - Inserción del robot en el mundo

    Returns:
        LaunchDescription: conjunto de acciones a ejecutar en el lanzamiento.
    """

    # Obtener rutas de paquetes necesarios
    pkg = get_package_share_directory('patricio_my_world')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    launch_dir = os.path.join(pkg, 'launch')
    world = os.path.join(pkg, 'worlds', 'house.sdf')

    # Parámetros configurables
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    x_pose = LaunchConfiguration('x_pose', default='-2.0')
    y_pose = LaunchConfiguration('y_pose', default='-2.0')

    # Añade la carpeta de modelos propios al buscador de recursos de Gazebo
    set_env_models = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(pkg, 'models')
    )

    # Añade los modelos oficiales de TurtleBot3
    set_env_tb3 = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(
            get_package_share_directory('turtlebot3_gazebo'),
            'models'
        )
    )

    # Lanza el simulador Gazebo con el mundo especificado
    gz_sim_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': f'-r {world}'
        }.items()
    )

    # Publica las transformaciones del robot (TF)
    robot_state_publisher_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'robot_state_publisher.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items()
    )

    # Inserta el robot en el mundo con la posición inicial indicada
    spawn_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'spawn_turtlebot3.launch.py')
        ),
        launch_arguments={
            'x_pose': x_pose,
            'y_pose': y_pose
        }.items()
    )

    # Construcción de la descripción de lanzamiento
    ld = LaunchDescription()

    # Orden importante: primero recursos, luego simulación y robot
    ld.add_action(set_env_models)
    ld.add_action(set_env_tb3)
    ld.add_action(gz_sim_cmd)
    ld.add_action(robot_state_publisher_cmd)
    ld.add_action(spawn_cmd)

    return ld