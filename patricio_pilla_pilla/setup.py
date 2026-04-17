import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'patricio_pilla_pilla'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='juan',
    maintainer_email='juan@todo.todo',
    description='Juego pilla-pilla usando Nav2 y servicio StartGame',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pilla_pilla_node = patricio_pilla_pilla.pilla_pilla_node:main',
        ],
    },
)
