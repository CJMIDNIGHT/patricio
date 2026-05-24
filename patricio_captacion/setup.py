from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'patricio_captacion'

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
    maintainer='adenor',
    maintainer_email='amburet@epsg.upv.es',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'vision_node = patricio_captacion.vision_node:main',
            'webcam_publisher = patricio_captacion.webcam_publisher:main',
            'webcam_publisher_linux = patricio_captacion.webcam_publisher_linux:main',
        ],
    },
)