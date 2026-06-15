from setuptools import find_packages, setup

package_name = 'patricio_cara'

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
    maintainer='adenor',
    maintainer_email='adenor@todo.todo',
    description='Nodo de cara/emociones para Patricio',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'cara_node = patricio_cara.cara_node:main',
        ],
    },
)