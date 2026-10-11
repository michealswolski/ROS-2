from glob import glob

from setuptools import find_packages, setup

package_name = 'drive_bag'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='michealswolski',
    maintainer_email='michealswolski@users.noreply.github.com',
    description='Drive log -> rosbag2 (MCAP) -> replay -> KPIs',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'generate_sample = drive_bag.generate_sample:main',
            'csv_to_bag = drive_bag.csv_to_bag:main',
            'mcap_to_bag = drive_bag.mcap_to_bag:main',
            'bag_to_csv = drive_bag.bag_to_csv:main',
            'drive_publisher = drive_bag.drive_publisher:main',
            'kpi_monitor = drive_bag.kpi_monitor:main',
            'bag_kpis = drive_bag.bag_kpis:main',
            'plot_bag = drive_bag.plot_bag:main',
        ],
    },
)
