from setuptools import find_packages, setup

package_name = 'patricio_deteccion_caidas'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='saac',
    maintainer_email='santiagoaaguirrec@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'deteccion_caidas_node = patricio_deteccion_caidas.deteccion_caidas_node:main',
        ],
    },
)
