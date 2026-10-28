from setuptools import setup

package_name = "uav_tracking_px4_adapter"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    entry_points={"console_scripts": [
        "px4_adapter = uav_tracking_px4_adapter.adapter_node:main",
        "flight_supervisor = uav_tracking_px4_adapter.flight_supervisor:main",
    ]},
)
