"""Real visual/PX4 designated-target graph; simulator owned by the runner."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = get_package_share_directory("uav_tracking_bringup")
    params = LaunchConfiguration("params_file")
    sim_time = {"use_sim_time": True}
    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=os.path.join(share, "config", "stage2_tracking_person.yaml")),
        DeclareLaunchArgument("target_class", default_value=os.environ.get("STAGE_TARGET_CLASS", "person"), choices=["person", "car"]),
        DeclareLaunchArgument("scenario_kind", default_value=os.environ.get("STAGE_SCENARIO_KIND", "crossing"), choices=["parallel", "crossing", "ambiguity"]),
        DeclareLaunchArgument("speed_mps", default_value="0.5"),
        DeclareLaunchArgument("motion_profile_kind", default_value="standard", choices=["standard"]),
        DeclareLaunchArgument("auto_start", default_value="false"),
        DeclareLaunchArgument("takeoff_height_m", default_value="3.0"),
        DeclareLaunchArgument("command_mode", default_value="velocity", choices=["velocity", "position"]),
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="uav_tracking_gz_bridge",
             arguments=["/world/stage2_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose"],
             parameters=[sim_time, {"config_file": os.path.join(share, "config", "stage2_bridge.yaml")}], output="screen"),
        Node(package="uav_tracking_px4_adapter", executable="px4_adapter", name="uav_tracking_px4_adapter",
             parameters=[params, sim_time, {"command_topic": "/tracking/flight_command", "require_vehicle_status": True,
                                           "vehicle_status_topic": "/fmu/out/vehicle_status_v1"}], output="screen"),
        Node(package="uav_tracking_bringup", executable="flight_tf", name="uav_tracking_flight_tf",
             parameters=[sim_time], output="screen"),
        Node(package="uav_tracking_bringup", executable="stage2_motion", name="stage2_scenario_motion",
             parameters=[sim_time, {"target_class": LaunchConfiguration("target_class"),
                                     "scenario_kind": LaunchConfiguration("scenario_kind"),
                                     "speed_mps": ParameterValue(LaunchConfiguration("speed_mps"), value_type=float)}], output="screen"),
        Node(package="uav_tracking_nodes", executable="detector", name="uav_tracking_detection",
             parameters=[params, sim_time, {"activation_phase_topic": "/tracking/flight_phase",
                                           "image_reliability": "reliable"}], output="screen"),
        Node(package="uav_tracking_nodes", executable="state_estimator", name="uav_tracking_state_estimator",
             parameters=[params, sim_time], output="screen"),
        Node(package="uav_tracking_nodes", executable="controller", name="uav_tracking_controller",
             parameters=[params, sim_time, {"command_mode": LaunchConfiguration("command_mode")}], output="screen"),
        Node(package="uav_tracking_px4_adapter", executable="flight_supervisor", name="uav_tracking_flight_supervisor",
             parameters=[params, sim_time, {"auto_start": ParameterValue(LaunchConfiguration("auto_start"), value_type=bool),
                                    "simulation_only": True,
                                    "takeoff_height_m": ParameterValue(LaunchConfiguration("takeoff_height_m"), value_type=float)}],
             output="screen"),
    ])
