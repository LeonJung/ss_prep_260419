from setuptools import find_packages, setup

package_name = 'mw_hfsm_ros'

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
    description='ROS 2 integration layer for mw_hfsm_engine',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={},
)
