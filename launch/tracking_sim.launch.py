"""Standalone source template; installable copy lives in the bringup package."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("uav_tracking_bringup")
    default_params = os.path.join(package_share, "config", "tracking.yaml")
    params_file = LaunchConfiguration("params_file")
    start_pipeline = LaunchConfiguration("start_pipeline")
    start_simulator = LaunchConfiguration("start_simulator")
    start_bridge = LaunchConfiguration("start_bridge")
    start_static_tf = LaunchConfiguration("start_static_tf")
    start_fake_vehicle = LaunchConfiguration("start_fake_vehicle")
    start_px4_adapter = LaunchConfiguration("start_px4_adapter")
    world = LaunchConfiguration("world")
    bridge_config = LaunchConfiguration("bridge_config")
    return LaunchDescription([
        AppendEnvironmentVariable(
            name="GZ_SIM_RESOURCE_PATH",
            value=os.path.join(package_share, "models"),
        ),
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("start_pipeline", default_value="false"),
        DeclareLaunchArgument("start_simulator", default_value="false"),
        DeclareLaunchArgument("start_bridge", default_value="false"),
        DeclareLaunchArgument("start_static_tf", default_value="false"),
        DeclareLaunchArgument("start_fake_vehicle", default_value="false"),
        DeclareLaunchArgument(
            "start_px4_adapter",
            default_value="true",
            description="Start the PX4 adapter; disable for ROS/Gazebo-only smoke tests.",
        ),
        DeclareLaunchArgument(
            "world",
            default_value=os.path.join(package_share, "worlds", "stage1_single_target.sdf"),
        ),
        DeclareLaunchArgument(
            "bridge_config",
            default_value=os.path.join(package_share, "config", "stage1_bridge.yaml"),
        ),
        Node(
            package="ros_gz_sim", executable="gzserver", name="gazebo",
            arguments=["--ros-args", "-p", ["world_sdf_file:=", world]], output="screen",
            condition=IfCondition(start_simulator),
        ),
        Node(
            package="ros_gz_bridge", executable="parameter_bridge",
            name="uav_tracking_gz_bridge",
            arguments=["--ros-args", "-p", ["config_file:=", bridge_config]],
            output="screen", condition=IfCondition(start_bridge),
        ),
        Node(
            package="tf2_ros", executable="static_transform_publisher",
            name="uav_tracking_camera_static_tf",
            # REP-103 optical camera frame (x right, y down, z forward) to
            # ENU map, including the rig's 0.18 rad downward pitch.
            arguments=[
                "0", "0", "3.0",
                "-0.54291564", "0.54291564", "-0.45303709", "0.45303709",
                "map", "camera_link",
            ],
            output="screen", condition=IfCondition(start_static_tf),
        ),
        Node(
            package="uav_tracking_bringup", executable="fake_vehicle_state",
            name="uav_tracking_fake_vehicle_state", output="screen",
            parameters=[{"use_sim_time": True}],
            condition=IfCondition(start_fake_vehicle),
        ),
        Node(
            package="uav_tracking_nodes", executable="detector",
            name="uav_tracking_detection", parameters=[params_file], output="screen",
            condition=IfCondition(start_pipeline),
        ),
        Node(
            package="uav_tracking_nodes", executable="state_estimator",
            name="uav_tracking_state_estimator", parameters=[params_file], output="screen",
            condition=IfCondition(start_pipeline),
        ),
        Node(
            package="uav_tracking_nodes", executable="controller",
            name="uav_tracking_controller", parameters=[params_file], output="screen",
            condition=IfCondition(start_pipeline),
        ),
        GroupAction(
            condition=IfCondition(start_pipeline),
            actions=[
                Node(
                    package="uav_tracking_px4_adapter", executable="px4_adapter",
                    name="uav_tracking_px4_adapter", parameters=[params_file], output="screen",
                    condition=IfCondition(start_px4_adapter),
                )
            ],
        ),
    ])
