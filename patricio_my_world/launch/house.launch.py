import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():

    pkg = get_package_share_directory('patricio_my_world')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    launch_dir = os.path.join(pkg, 'launch')
    world = os.path.join(pkg, 'worlds', 'house.sdf')

    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    x_pose = LaunchConfiguration('x_pose', default='2.0')
    y_pose = LaunchConfiguration('y_pose', default='2.0')

    # 🔥 PATH MODELOS (IMPORTANTE)
    set_env = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(pkg, 'models')
    )

    # 🔥 Gazebo (SOLO UNA VEZ)
    gzserver_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': f'-r {world}'
        }.items()
    )

    # 🔥 robot_state_publisher
    robot_state_publisher_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'robot_state_publisher.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items()
    )

    # 🔥 spawn robot
    spawn_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'spawn_turtlebot3.launch.py')
        ),
        launch_arguments={
            'x_pose': x_pose,
            'y_pose': y_pose
        }.items()
    )

    ld = LaunchDescription()

    # 🔥 ORDEN CORRECTO
    ld.add_action(set_env)
    ld.add_action(gzserver_cmd)
    ld.add_action(robot_state_publisher_cmd)
    ld.add_action(spawn_cmd)

    return ld