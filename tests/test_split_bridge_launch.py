"""Split/legacy launch routing contracts without ROS or native execution."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import yaml

from scripts import run_stage1_trial as trial
from tests.test_graph_startup_readiness import ready_graph
from tests.test_stage3_multi import Config, If, Unless
from uav_tracking.bridge_process_contract import validate_split_bridge_argv
from uav_tracking.startup_readiness import assess_graph


ROOT = Path(__file__).resolve().parents[1]
BRINGUP = ROOT / "ros2_ws/src/uav_tracking_bringup"


def launch_nodes(stage, overrides=None):
    modules = {
        "ament_index_python": NS(),
        "ament_index_python.packages": NS(get_package_share_directory=lambda _: str(BRINGUP)),
        "launch": NS(LaunchDescription=lambda actions: actions),
        "launch.actions": NS(DeclareLaunchArgument=lambda name, **kw: NS(kind="argument", name=name, **kw)),
        "launch.conditions": NS(IfCondition=If, UnlessCondition=Unless),
        "launch.substitutions": NS(LaunchConfiguration=Config),
        "launch_ros": NS(),
        "launch_ros.actions": NS(Node=lambda **kw: NS(kind="node", **kw)),
        "launch_ros.parameter_descriptions": NS(ParameterValue=lambda value, **_: value),
    }
    with patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=True):
        spec = importlib.util.spec_from_file_location(
            f"split_stage{stage}_launch_fixture", BRINGUP / f"launch/stage{stage}_flight.launch.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actions = module.generate_launch_description()
    values = {item.name: item.default_value for item in actions if item.kind == "argument"}
    values.update(overrides or {})
    return values, [item for item in actions if item.kind == "node"
                    and (not hasattr(item, "condition") or item.condition.enabled(values))]


class SplitBridgeLaunchTests(unittest.TestCase):
    def test_each_stage_defaults_to_two_explicit_roles_with_service_only_on_data(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                values, nodes = launch_nodes(stage)
                self.assertEqual(values["split_clock_bridge"], "true")
                bridges = [node for node in nodes if node.executable == "parameter_bridge"]
                self.assertEqual(len(bridges), 2)
                by_name = {node.name: node for node in bridges}
                self.assertEqual(set(by_name), {"uav_tracking_gz_bridge", "uav_tracking_clock_bridge"})
                data_name = "stage1_flight_data_bridge.yaml" if stage == 1 else f"stage{stage}_data_bridge.yaml"
                for role, node_name, name in (("data", "uav_tracking_gz_bridge", data_name),
                                              ("clock", "uav_tracking_clock_bridge", "clock_bridge.yaml")):
                    node = by_name[node_name]
                    # launch appends this remap to the direct production argv.
                    argv = ["/fixture/bin/parameter_bridge", *node.arguments,
                            "--ros-args", "-r", "__node:=" + node_name]
                    result = validate_split_bridge_argv(argv, {
                        "node_name": node_name, "config_file": str(BRINGUP / "config" / name),
                        "service_argument": (f"/world/stage{stage}_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose"
                                             if role == "data" else None)}, role=role)
                    self.assertEqual(result["bridge_role"], role)
                    self.assertFalse(hasattr(node, "parameters"), "No temporary params-file indirection")

    def test_explicit_legacy_has_one_original_bridge_and_one_pose_service(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                _, nodes = launch_nodes(stage, {"split_clock_bridge": "false"})
                bridges = [node for node in nodes if node.executable == "parameter_bridge"]
                self.assertEqual(len(bridges), 1)
                bridge = bridges[0]
                self.assertEqual(bridge.name, "uav_tracking_gz_bridge")
                self.assertEqual(bridge.arguments,
                    [f"/world/stage{stage}_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose"])
                original = "stage1_flight_bridge.yaml" if stage == 1 else f"stage{stage}_bridge.yaml"
                self.assertEqual(bridge.parameters[-1]["config_file"], str(BRINGUP / "config" / original))

    def test_split_configs_move_only_clock_and_preserve_every_data_setting(self):
        clock = yaml.safe_load((BRINGUP / "config/clock_bridge.yaml").read_text(encoding="utf-8"))
        self.assertEqual(len(clock), 1)
        self.assertEqual(clock[0]["ros_topic_name"], "/clock")
        self.assertEqual(clock[0]["direction"], "GZ_TO_ROS")
        for stage in (1, 2, 3):
            original = "stage1_flight_bridge.yaml" if stage == 1 else f"stage{stage}_bridge.yaml"
            split = "stage1_flight_data_bridge.yaml" if stage == 1 else f"stage{stage}_data_bridge.yaml"
            rows = yaml.safe_load((BRINGUP / "config" / original).read_text(encoding="utf-8"))
            data = yaml.safe_load((BRINGUP / "config" / split).read_text(encoding="utf-8"))
            with self.subTest(stage=stage):
                self.assertEqual(clock, [row for row in rows if row["ros_topic_name"] == "/clock"])
                self.assertEqual(data, [row for row in rows if row["ros_topic_name"] != "/clock"])
                effective = [*data, *clock]
                self.assertEqual(sum(row["ros_topic_name"] == "/clock" for row in effective), 1)
                self.assertEqual(len({row["ros_topic_name"] for row in effective}), len(effective))

    def test_real_parser_default_and_optout_choose_the_correct_preflight_branch(self):
        # Stop before output creation, environment sourcing or process launch.
        for option, split_expected in (([], True), (["--no-split-clock-bridge"], False)):
            with self.subTest(option=option), patch.object(sys, "argv", ["run_stage1_trial.py", "--name", "fixture", *option]), \
                    patch.object(trial, "prepare_ros_gz_runtime", return_value=None), \
                    patch.object(trial, "prepare_split_clock_runtime", side_effect=RuntimeError("split fixture stop")) as split, \
                    patch.object(trial, "prepare_dds_runtime", side_effect=RuntimeError("legacy fixture stop")):
                with self.assertRaisesRegex(RuntimeError, "split fixture stop" if split_expected else "legacy fixture stop"):
                    trial.main()
                self.assertEqual(split.call_count, int(split_expected))

    def test_split_startup_requires_the_one_clock_publisher_to_have_its_registered_name(self):
        expected = "/uav_tracking_clock_bridge"
        graph = ready_graph()
        self.assertTrue(assess_graph(graph, require_recorder=True)["ready"])
        self.assertFalse(assess_graph(graph, require_recorder=True, expected_clock_node=expected)["ready"])
        graph["topics"]["/clock"]["publishers"][0]["node"] = expected
        self.assertTrue(assess_graph(graph, require_recorder=True, expected_clock_node=expected)["ready"])
        duplicate = copy.deepcopy(graph["topics"]["/clock"]["publishers"][0])
        duplicate.update(node="/old_mixed_bridge", gid="ff" * 24)
        graph["topics"]["/clock"]["publishers"].append(duplicate)
        self.assertFalse(assess_graph(graph, require_recorder=True, expected_clock_node=expected)["ready"])


if __name__ == "__main__":
    unittest.main()
