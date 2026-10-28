from glob import glob
import os

from setuptools import setup


package_name = "uav_tracking_bringup"
_model_path = os.path.join("models", "yolo11n.pt")
_model_data = []
for directory, _, filenames in os.walk("models"):
    resources = [os.path.join(directory, name) for name in filenames if not name.endswith(".zip")]
    if resources:
        _model_data.append((os.path.join("share", package_name, directory), resources))

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "launch"),
            glob(os.path.join("launch", "*.launch.py")),
        ),
        (
            os.path.join("share", package_name, "config"),
            glob(os.path.join("config", "*.yaml")),
        ),
        (
            os.path.join("share", package_name, "worlds"),
            glob(os.path.join("worlds", "*.sdf")),
        ),
    ] + _model_data,
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    description="Launch and parameter templates for UAV target tracking.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "fake_vehicle_state = uav_tracking_bringup.fake_vehicle_state:main",
            "stage1_smoke_test = uav_tracking_bringup.stage1_smoke_test:main",
            "flight_tf = uav_tracking_bringup.flight_tf_node:main",
            "gimbal_adapter = uav_tracking_bringup.gimbal_adapter_node:main",
            "stage2_motion = uav_tracking_bringup.stage2_motion:main",
            "scenario_motion = uav_tracking_bringup.scenario_motion:main",
        ],
    },
)
