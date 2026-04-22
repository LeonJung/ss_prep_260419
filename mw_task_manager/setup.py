from setuptools import find_packages, setup

package_name = 'mw_task_manager'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Ryuwoon Jung',
    maintainer_email='jung.ryuwoon@gmail.com',
    description='HFSM executor node for mw Task Manager',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'hfsm_executor = mw_task_manager.hfsm_executor_node:main',
        ],
    },
)
