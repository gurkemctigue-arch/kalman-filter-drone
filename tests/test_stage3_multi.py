"""The optional combined graph must keep one motion driver and real gimbal."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
BRINGUP = ROOT / "ros2_ws/src/uav_tracking_bringup"


class Config:
    def __init__(self, name):
        self.name = name

    def value(self, values):
        return values[self.name]


class If:
    def __init__(self, expression):
        self.expression = expression

    def enabled(self, values):
        return self.expression.value(values) == "true"


class Unless(If):
    def enabled(self, values):
        return not super().enabled(values)


def launch_graph(environment):
    """Evaluate launch condition wiring with lightweight ROS-free actions."""
    modules = {
        "ament_index_python": NS(),
        "ament_index_python.packages": NS(get_package_share_directory=lambda _: str(BRINGUP)),
        "launch": NS(LaunchDescription=lambda actions: actions),
        "launch.actions": NS(DeclareLaunchArgument=lambda name, **kwargs: NS(kind="argument", name=name, **kwargs)),
        "launch.conditions": NS(IfCondition=If, UnlessCondition=Unless),
        "launch.substitutions": NS(LaunchConfiguration=Config),
        "launch_ros": NS(),
        "launch_ros.actions": NS(Node=lambda **kwargs: NS(kind="node", **kwargs)),
        "launch_ros.parameter_descriptions": NS(ParameterValue=lambda value, **_: value),
    }
    with patch.dict(sys.modules, modules), patch.dict(os.environ, environment):
        spec = importlib.util.spec_from_file_location("stage3_multi_test_launch", BRINGUP / "launch/stage3_flight.launch.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actions = module.generate_launch_description()
    defaults = {action.name: action.default_value for action in actions if action.kind == "argument"}
    nodes = [action for action in actions if action.kind == "node"
             and (not hasattr(action, "condition") or action.condition.enabled(defaults))]
    return defaults, nodes


class Stage3MultiTests(unittest.TestCase):
    def test_joint_pipeline_keeps_stage2_identity_safety_and_stage3_physical_gimbal(self):
        spec = importlib.util.spec_from_file_location("joint_trial_runner", ROOT / "scripts/run_stage1_trial.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for category in ("person", "car"):
            params = yaml.safe_load((BRINGUP / f"config/stage3_tracking_{category}.yaml").read_text(encoding="utf-8"))
            gimbal = dict(params["uav_tracking_gimbal"]["ros__parameters"])
            controller = dict(params["uav_tracking_controller"]["ros__parameters"])
            module.apply_multi_target_identity(params, BRINGUP, category)
            identity = params["uav_tracking_state_estimator"]["ros__parameters"]
            self.assertEqual(identity["target_mode"], "locked_target")
            self.assertEqual(identity["association_mode"], "hybrid_3d")
            self.assertTrue(identity["reject_ambiguous_associations"])
            self.assertEqual(identity["association_max_distance_m"], 1.5)
            self.assertEqual(identity["max_prediction_duration_s"], .75)
            self.assertEqual(identity["max_observation_age_s"], .60)
            self.assertEqual(identity["target_class"], category)
            self.assertEqual(params["uav_tracking_gimbal"]["ros__parameters"], gimbal)
            self.assertEqual(params["uav_tracking_controller"]["ros__parameters"], controller)

    def test_both_combined_worlds_keep_the_identical_three_actor_experiment(self):
        for category in ("person", "car"):
            source = ET.parse(BRINGUP / f"worlds/stage2_flight_{category}.sdf").getroot().find("world")
            combined = ET.parse(BRINGUP / f"worlds/stage3_multi_{category}.sdf").getroot().find("world")
            self.assertEqual(combined.attrib["name"], "stage3_flight")
            vehicle = combined.find("include[name='stage1_uav']")
            self.assertIsNotNone(vehicle)
            self.assertEqual(vehicle.findtext("uri"), "model://x500_stage3")
            for index in range(3):
                name = f"stage2_{category}_{index}"
                self.assertEqual(ET.tostring(source.find(f"model[@name='{name}']")),
                                 ET.tostring(combined.find(f"model[@name='{name}']")))
            self.assertEqual(ET.tostring(source.find("model[@name='vision_shutter']")),
                             ET.tostring(combined.find("model[@name='vision_shutter']")))

    def test_extra_command_bridges_are_distinct_and_gimbal_feedback_is_retained(self):
        rows = yaml.safe_load((BRINGUP / "config/stage3_bridge.yaml").read_text(encoding="utf-8"))
        topics = {row["ros_topic_name"]: row for row in rows}
        self.assertEqual(len(topics), len(rows))
        for index in range(3):
            topic = f"/scenario/target_{index}/cmd_vel"
            self.assertEqual(topics[topic]["gz_topic_name"], topic)
            self.assertEqual(topics[topic]["direction"], "ROS_TO_GZ")
        self.assertEqual(topics["/gimbal/joint_states"]["direction"], "GZ_TO_ROS")
        self.assertEqual(topics["/camera/color/image_raw"]["gz_topic_name"], "/camera/rgbd/image")

    def test_default_single_graph_starts_exactly_one_single_actor_motion_driver(self):
        defaults, nodes = launch_graph({"STAGE_MULTI_TARGET": "false"})
        self.assertEqual(defaults["multi_target"], "false")
        drivers = [node.executable for node in nodes if node.executable in {"scenario_motion", "stage2_motion"}]
        self.assertEqual(drivers, ["scenario_motion"])
        self.assertEqual(sum(node.executable == "gimbal_adapter" for node in nodes), 1)

    def test_env_optin_starts_exactly_one_three_actor_driver_with_class_and_profile(self):
        defaults, nodes = launch_graph({"STAGE_MULTI_TARGET": "true", "STAGE_TARGET_CLASS": "car", "STAGE_SCENARIO_KIND": "parallel"})
        drivers = [node for node in nodes if node.executable in {"scenario_motion", "stage2_motion"}]
        self.assertEqual([node.executable for node in drivers], ["stage2_motion"])
        parameters = drivers[0].parameters[-1]
        self.assertEqual(parameters["target_class"].value(defaults), "car")
        self.assertEqual(parameters["scenario_kind"].value(defaults), "parallel")
        self.assertEqual(sum(node.executable == "gimbal_adapter" for node in nodes), 1)


if __name__ == "__main__":
    unittest.main()
