"""Strict argv identity fixtures; no ROS, subprocesses or filesystem access."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from uav_tracking.bridge_process_contract import validate_split_bridge_argv


EXECUTABLE = "/root/overlay/install/lib/ros_gz_bridge/parameter_bridge"
SERVICE = "/world/stage1_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose"


def expected(role):
    return {
        "node_name": "uav_tracking_gz_" + role + "_bridge",
        "config_file": "/root/项目/config/" + role + " bridge.yaml",
        "service_argument": SERVICE if role == "data" else None,
    }


def command(role):
    contract = expected(role)
    return [
        EXECUTABLE,
        *([SERVICE] if role == "data" else []),
        "--ros-args", "-p", "use_sim_time:=true",
        "-p", "config_file:=" + contract["config_file"],
        "--ros-args", "-r", "__node:=" + contract["node_name"],
    ]


class SplitBridgeContractTests(unittest.TestCase):
    def reject(self, argv, contract=None, *, role="clock"):
        with self.assertRaises(ValueError):
            validate_split_bridge_argv(argv, expected(role) if contract is None else contract, role=role)

    def test_clock_and_data_return_serializable_independent_command_receipts(self):
        for role in ("clock", "data"):
            with self.subTest(role=role):
                argv, contract = command(role), expected(role)
                before = deepcopy((argv, contract))
                receipt = validate_split_bridge_argv(argv, contract, role=role)
                self.assertEqual(receipt, {
                    "bridge_role": role, "node_name": contract["node_name"],
                    "config_file": contract["config_file"], "command": argv,
                })
                self.assertEqual(json.loads(json.dumps(receipt)), receipt)
                self.assertEqual((argv, contract), before)
                self.assertIsNot(receipt["command"], argv)

    def test_long_options_parameter_order_and_multiple_ros_blocks(self):
        contract = expected("clock")
        argv = [EXECUTABLE, "--ros-args", "--remap", "__node:=" + contract["node_name"],
                "--ros-args", "--param", "config_file:=" + contract["config_file"],
                "--param", "use_sim_time:=true"]
        self.assertEqual(validate_split_bridge_argv(tuple(argv), contract, role="clock")["command"], argv)

    def test_absolute_windows_fixture_path_is_compared_without_normalizing(self):
        contract = expected("clock")
        contract["config_file"] = "D:\\临时夹具\\clock bridge.yaml"
        argv = command("clock")
        argv[argv.index("-p") + 3] = "config_file:=" + contract["config_file"]
        self.assertEqual(validate_split_bridge_argv(argv, contract, role="clock")["config_file"],
                         contract["config_file"])

    def test_role_exchange_and_clock_service_are_rejected(self):
        self.reject(command("data"), role="clock")
        self.reject(command("clock"), role="data")
        argv = command("clock")
        argv.insert(1, SERVICE)
        self.reject(argv)

    def test_wrong_or_missing_or_duplicate_data_service_is_rejected(self):
        argv = command("data")
        self.reject([argv[0], *argv[2:]], role="data")
        self.reject([argv[0], SERVICE, *argv[1:]], role="data")
        argv[1] = SERVICE.replace("stage1_flight", "foreign_world")
        self.reject(argv, role="data")

    def test_duplicate_clock_node_remap_is_not_treated_as_a_second_valid_role(self):
        argv = command("clock") + ["--ros-args", "--remap", "__node:=" + expected("clock")["node_name"]]
        self.reject(argv)

    def test_each_required_setting_is_unique_even_across_ros_blocks(self):
        for token in ("__node:=" + expected("clock")["node_name"],
                      "config_file:=" + expected("clock")["config_file"], "use_sim_time:=true"):
            with self.subTest(token=token):
                option = "--remap" if token.startswith("__node") else "--param"
                self.reject(command("clock") + ["--ros-args", option, token])

    def test_parameter_files_cannot_bypass_direct_config_binding(self):
        for extra in (["--params-file", "/tmp/launch_params_secret"],
                      ["--params-file=/tmp/launch_params_secret"],
                      ["-p", "params_file:=/tmp/launch_params_secret"]):
            with self.subTest(extra=extra):
                self.reject(command("clock") + extra)

    def test_foreign_remaps_parameters_flags_and_topic_bridges_are_rejected(self):
        for extra in (["-r", "/clock:=/foreign_clock"], ["--remap", "__ns:=/other"],
                      ["-p", "lazy:=true"], ["--param", "use_sim_time:=false"],
                      ["--log-level", "debug"], ["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"]):
            with self.subTest(extra=extra):
                self.reject(command("clock") + extra)

    def test_changed_config_node_and_sim_time_cannot_override_expected(self):
        for original, replacement in (
            ("config_file:=" + expected("clock")["config_file"], "config_file:=/tmp/other.yaml"),
            ("__node:=" + expected("clock")["node_name"], "__node:=uav_tracking_gz_data_bridge"),
            ("use_sim_time:=true", "use_sim_time:=True"),
        ):
            with self.subTest(original=original):
                argv = command("clock")
                argv[argv.index(original)] = replacement
                self.reject(argv)

    def test_missing_settings_dangling_options_and_flags_outside_ros_arguments(self):
        for option, value in (("-r", "__node:=" + expected("clock")["node_name"]),
                              ("-p", "config_file:=" + expected("clock")["config_file"]),
                              ("-p", "use_sim_time:=true")):
            with self.subTest(missing=value):
                argv = command("clock")
                index = argv.index(value)
                del argv[index - 1:index + 1]
                self.reject(argv)
        self.reject(command("clock") + ["-p"])
        self.reject([EXECUTABLE, "-p", "use_sim_time:=true", *command("clock")[1:]])
        argv = command("data")
        argv.remove(SERVICE)
        self.reject([*argv, SERVICE], role="data")

    def test_wrong_executable_empty_or_nonstring_tokens_and_invalid_roles(self):
        for argv in ([], "parameter_bridge", [EXECUTABLE, ""], [EXECUTABLE, None],
                     [EXECUTABLE + ".old", *command("clock")[1:]],
                     [EXECUTABLE + " (deleted)", *command("clock")[1:]],
                     [EXECUTABLE, "--ros-args\0foreign"]):
            with self.subTest(argv=argv):
                self.reject(argv)
        for role in ("bridge", "", None, []):
            with self.subTest(role=role):
                self.reject(command("clock"), expected("clock"), role=role)

    def test_expected_contract_cannot_register_relative_paths_or_foreign_services(self):
        cases = []
        for field, value in (("node_name", ""), ("config_file", "relative/clock.yaml"),
                             ("config_file", "C:relative\\clock.yaml"),
                             ("service_argument", SERVICE)):
            contract = expected("clock")
            contract[field] = value
            cases.append(("clock", contract))
        for service in (None, "", "/world/x/set_pose@other/srv/Type",
                        "relative/set_pose@ros_gz_interfaces/srv/SetEntityPose"):
            contract = expected("data")
            contract["service_argument"] = service
            cases.append(("data", contract))
        extra = expected("clock")
        extra["extra"] = True
        cases.append(("clock", extra))
        cases.append(("clock", {}))
        missing = expected("clock")
        del missing["service_argument"]
        cases.append(("clock", missing))
        for role, contract in cases:
            with self.subTest(role=role, contract=contract):
                self.reject(command(role), contract, role=role)


if __name__ == "__main__":
    unittest.main()
