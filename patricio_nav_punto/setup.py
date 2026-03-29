import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'patricio_nav_punto'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'param'), glob('param/*.yaml')),
        (os.path.join('share', package_name, 'rviz'), glob('rviz/*.rviz')),
        (os.path.join('share', package_name, 'map'), glob('map/*.pgm')),
        (os.path.join('share', package_name, 'map'), glob('map/*.yaml'))
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='saac',
    maintainer_email='saac@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'initial_pose_pub = patricio_nav_punto.initial_pose_pub:main', #añadir
            'nav_to_pose = patricio_nav_punto.nav_to_pose:main' #añadir
        ],
    },
)
