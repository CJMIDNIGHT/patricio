from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('patricio_gemini')
    config_file = os.path.join(pkg_share, 'config', 'gemini_params.yaml')

    venv_path = os.environ.get('VIRTUAL_ENV')
    python_executable = (
        os.path.join(venv_path, 'bin', 'python3')
        if venv_path
        else '/usr/bin/python3'
    )

    site_packages = os.path.normpath(
        os.path.join(pkg_share, '..', 'lib', 'python3.12', 'site-packages')
    )
    ros_site_packages = '/opt/ros/jazzy/lib/python3.12/site-packages'
    current_pythonpath = os.environ.get('PYTHONPATH', '')
    pythonpath_parts = [p for p in [current_pythonpath, ros_site_packages, site_packages] if p]
    pythonpath = os.pathsep.join(pythonpath_parts)

    return LaunchDescription([
        Node(
            executable=python_executable,
            name='patricio_gemini_node',
            output='screen',
            parameters=[config_file],
            arguments=['-m', 'patricio_gemini.gemini_node'],
            additional_env={'PYTHONPATH': pythonpath},
        ),
    ])
