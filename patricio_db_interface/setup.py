from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'patricio_db_interface'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='juan',
    maintainer_email='juan@todo.todo',
    description='Paquete de conexión a BBDD vía servicios ROS 2 que llaman a patricio_api.py',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'db_interface_node = patricio_db_interface.db_interface_node:main',
        ],
    },
)
