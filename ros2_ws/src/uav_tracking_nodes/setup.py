from setuptools import find_packages, setup

package_name = "uav_tracking_nodes"

_local_packages = find_packages()

setup(
    name=package_name,
    version="0.1.0",
    # The portable algorithm package is installed from the repository root
    # with ``python3 -m pip install -e ..`` before colcon. Keeping it out of
    # this ROS distribution avoids ament's symlink-install collision with the
    # source-tree ``uav_tracking`` directory.
    packages=_local_packages,
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    entry_points={
        "console_scripts": [
            "detector = uav_tracking_nodes.detector_node:main",
            "state_estimator = uav_tracking_nodes.state_estimator_node:main",
            "controller = uav_tracking_nodes.controller_node:main",
        ]
    },
)
