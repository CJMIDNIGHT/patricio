import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'patricio_gemini'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'requests'],
    zip_safe=True,
    maintainer='adenor',
    maintainer_email='amburet@epsg.upv.es',
    description='Nodo ROS 2 para Google Gemini con personalidad Patricio',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gemini_node = patricio_gemini.gemini_node:main',
        ],
    },
)
