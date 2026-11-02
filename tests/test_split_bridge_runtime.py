"""Owned split-bridge proc/config fixtures; no ROS, WSL or real ELF probes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts import run_stage1_trial as trial
from tests import test_dds_runtime as dds_fixtures
from tests import test_ros_gz_runtime as ros_gz_fixtures
from uav_tracking import ros_gz_runtime


class SplitBridgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        # This existing fixture creates only tiny local ELF/config/proc files.
        self.fixture = dds_fixtures.DdsRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.owned_graph()
        self.root, self.backend = self.fixture.root, self.fixture.backend
        self.evidence = self.fixture.directory / "split_evidence"
        self.evidence.mkdir()
        self.executable = self.fixture.directory / "overlay/lib/ros_gz_bridge/parameter_bridge"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b"\x7fELFsplit-bridge-fixture\0")
        self._write_configs(1)
        self.specs = trial.split_bridge_specs(self.root, 1)
        self._set_bridges(data_pid=102, clock_pid=103)

    def _write_configs(self, stage):
        data_name = "stage1_flight_data_bridge.yaml" if stage == 1 else f"stage{stage}_data_bridge.yaml"
        for name, topic in ((data_name, "/camera/color/image_raw"), ("clock_bridge.yaml", "/clock")):
            raw = ("- ros_topic_name: " + topic + "\n").encode("utf-8")
            for relative in ("ros2_ws/src/uav_tracking_bringup/config",
                             "ros2_ws/install/share/uav_tracking_bringup/config"):
                path = self.root / relative / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)

    def _command(self, role):
        spec = self.specs[role]
        return [str(self.executable), *([spec["service_argument"]] if role == "data" else []),
                "--ros-args", "-p", "use_sim_time:=true", "-p", "config_file:=" + spec["config_file"],
                "--ros-args", "-r", "__node:=" + spec["node_name"]]

    def _set_bridges(self, *, data_pid, clock_pid):
        self.data_pid, self.clock_pid = data_pid, clock_pid
        self.backend.add(100, executable="bash", children=[101, data_pid, clock_pid])
        libraries = [self.fixture.files[key] for key in dds_fixtures.runtime.ROLE_KEYS["bridge"].values()]
        for role, pid in (("data", data_pid), ("clock", clock_pid)):
            self.backend.add(pid, parent=100, executable=self.executable, command=self._command(role),
                             mappings=[self.executable, *libraries])

    def _find(self, **kwargs):
        return trial.find_owned_parameter_bridges(100, self.specs, backend=self.backend, **kwargs)

    def _elf_context(self):
        def record(path):
            return {"path": str(path), "real_path": str(path.resolve()),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}

        return {"registration": {"executable": record(self.executable),
                    "dependencies": [record(path) for path in self.backend.mappings[self.data_pid]
                                     if path != self.executable], "plugins": []},
                "sha256": "a" * 64, "patch": None}

    def _numeric_elf_report(self, registration, pid, **kwargs):
        # Only the expensive numerical ELF verifier is replaced. Ownership,
        # argv, on-disk configurations and pending maps remain production code.
        self.assertEqual(kwargs["backend"], self.backend)
        identity = ros_gz_runtime.parse_process_stat(self.backend.proc_text(pid, "stat"), pid)
        self.assertEqual(kwargs["expected_start_ticks"], identity["start_ticks"])
        return {"status": "PASS", "scope": "FIXTURE_NUMERIC_ELF_RESULT_ONLY", "process": identity}

    def _independent_registration_files(self):
        """Small actual registration files with a reviewed local Git diff.

        The existing fixture substitutes ldd output and uses tiny fake ELFs;
        all source/patch/registration validation remains production code.
        """
        fixture = ros_gz_fixtures.RosGzRuntimeTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.source.write_text("int main() { return 1; }\n", encoding="utf-8")
        fixture.patch.write_bytes(fixture.git("diff", "--binary", "HEAD", "--"))
        installed_patch = self.root / trial.ROS_GZ_PATCH
        installed_patch.parent.mkdir(parents=True, exist_ok=True)
        installed_patch.write_bytes(fixture.patch.read_bytes())
        plugin = fixture.directory / "interface_plugin/libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so"
        plugin.parent.mkdir()
        plugin.write_bytes(b"\x7fELF\x02\x01interface-fixture\0")
        fixture.backend.plugin_dependencies[str(plugin)] = [fixture.system]
        data_value = ros_gz_runtime.create_registration(fixture.overlay, fixture.repo,
            patch_path=fixture.patch, plugin_elf_paths=[plugin], backend=fixture.backend)
        data_path = self.root / trial.ROS_GZ_CONFIG
        data_path.write_text(json.dumps(data_value), encoding="utf-8")
        data = trial.prepare_ros_gz_runtime(self.root, backend=fixture.backend)
        clock_patch = fixture.directory / "independent_clock_receipt.patch"
        clock_patch.write_bytes(fixture.patch.read_bytes())
        clock_value = ros_gz_runtime.create_registration(fixture.overlay, fixture.repo,
            patch_path=clock_patch, backend=fixture.backend)
        clock_path = self.root / trial.ROS_GZ_CLOCK_CONFIG
        clock_path.write_text(json.dumps(clock_value), encoding="utf-8")
        return fixture, data, clock_value, clock_path

    def test_specs_bind_all_stages_to_identical_installed_source_bytes(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                self._write_configs(stage)
                specs = trial.split_bridge_specs(self.root, stage)
                self.assertEqual(set(specs), {"data", "clock"})
                for role, spec in specs.items():
                    source, installed = Path(spec["source_config"]), Path(spec["config_file"])
                    self.assertEqual(source.read_bytes(), installed.read_bytes())
                    self.assertTrue(installed.is_absolute())
                    self.assertEqual(spec["config_real_path"], str(installed.resolve()))
                    self.assertEqual(spec["config_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertIsNone(specs["clock"]["service_argument"])
                self.assertEqual(specs["data"]["service_argument"],
                    f"/world/stage{stage}_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose")

    def test_specs_reject_source_install_mismatch_for_either_role(self):
        for role in ("data", "clock"):
            with self.subTest(role=role):
                installed = Path(self.specs[role]["config_file"])
                original = installed.read_bytes()
                try:
                    installed.write_bytes(original + b"# changed only in install\n")
                    with self.assertRaisesRegex(ValueError, "differs from source"):
                        trial.split_bridge_specs(self.root, 1)
                finally:
                    installed.write_bytes(original)

    def test_discovery_proves_two_distinct_pids_roles_and_actual_argv(self):
        # Deliberately put the clock before data in PID order: role must come
        # from its registered argv, not discovery order or the first match.
        self._set_bridges(data_pid=103, clock_pid=102)
        found = self._find()
        self.assertEqual(set(found), {"data", "clock"})
        self.assertEqual(found["data"]["process"]["pid"], 103)
        self.assertEqual(found["clock"]["process"]["pid"], 102)
        for role, owned in found.items():
            self.assertEqual(owned["bridge_role"], role)
            self.assertEqual(owned["command"], self._command(role))
            self.assertEqual(owned["config_sha256"], self.specs[role]["config_sha256"])
            self.assertEqual([row["pid"] for row in owned["ancestor_chain"]],
                             [100, owned["process"]["pid"]])

    def test_third_owned_bridge_is_rejected_even_if_its_argv_is_registered(self):
        self.backend.add(104, parent=100, executable=self.executable, command=self._command("clock"))
        self.backend.add(100, executable="bash", children=[101, 102, 103, 104])
        with self.assertRaisesRegex(RuntimeError, "extra parameter_bridge"):
            self._find()

    def test_two_pids_with_the_same_role_cannot_replace_the_other_role(self):
        original = deepcopy(self.backend.commands)
        for role in ("data", "clock"):
            with self.subTest(role=role):
                try:
                    self.backend.commands[102] = self._command(role)
                    self.backend.commands[103] = self._command(role)
                    with self.assertRaisesRegex(RuntimeError, "Duplicate owned split bridge role"):
                        self._find()
                finally:
                    self.backend.commands = deepcopy(original)

    def test_argv_config_and_service_tampering_do_not_relabel_a_foreign_bridge(self):
        original = self._command("data")
        foreign = self.fixture.directory / "same bytes foreign data.yaml"
        foreign.write_bytes(Path(self.specs["data"]["config_file"]).read_bytes())
        for before, after in (
            ("config_file:=" + self.specs["data"]["config_file"], "config_file:=" + str(foreign)),
            (self.specs["data"]["service_argument"],
             "/world/foreign/set_pose@ros_gz_interfaces/srv/SetEntityPose"),
        ):
            with self.subTest(after=after):
                argv = list(original)
                argv[argv.index(before)] = after
                self.backend.commands[self.data_pid] = argv
                with self.assertRaisesRegex(RuntimeError, "unregistered role/argv/config"):
                    self._find()
        self.backend.commands[self.data_pid] = original

    def test_installed_config_changed_after_spec_creation_is_rejected(self):
        for role in ("data", "clock"):
            with self.subTest(role=role):
                config = Path(self.specs[role]["config_file"])
                original = config.read_bytes()
                try:
                    config.write_bytes(original + b"# changed after registered digest\n")
                    with self.assertRaisesRegex(RuntimeError, "configuration changed: " + role):
                        self._find()
                finally:
                    config.write_bytes(original)

    def test_config_realpath_is_bound_independently_of_matching_bytes(self):
        original = self.specs["clock"]["config_real_path"]
        other = self.fixture.directory / "different clock path.yaml"
        other.write_bytes(Path(self.specs["clock"]["config_file"]).read_bytes())
        self.specs["clock"]["config_real_path"] = str(other.resolve())
        try:
            with self.assertRaisesRegex(RuntimeError, "configuration changed: clock"):
                self._find()
        finally:
            self.specs["clock"]["config_real_path"] = original

    def test_intermediate_ancestor_creation_change_is_rejected(self):
        self.backend.add(150, parent=100, executable="python", children=[102, 103])
        self.backend.add(100, executable="bash", children=[101, 150])
        self.backend.records[102]["parent_pid"] = 150
        self.backend.records[103]["parent_pid"] = 150
        self.backend.reuse_pid = 150
        with self.assertRaisesRegex(RuntimeError, "ancestor creation identity changed"):
            self._find()

    def test_parent_mismatch_and_stale_leader_creation_receipt_are_rejected(self):
        self.backend.records[self.clock_pid]["parent_pid"] = 999
        with self.assertRaisesRegex(RuntimeError, "parent identity changed"):
            self._find()
        self.backend.records[self.clock_pid]["parent_pid"] = 100
        leader = ros_gz_runtime.parse_process_stat(self.backend.proc_text(100, "stat"), 100)
        self.backend.records[100]["start_ticks"] += 1
        with self.assertRaisesRegex(RuntimeError, "launch creation identity changed"):
            self._find(expected_leader=leader)

    def test_legacy_single_bridge_finder_still_rejects_the_split_graph(self):
        with self.assertRaisesRegex(RuntimeError, "multiple parameter_bridge"):
            trial.find_owned_parameter_bridge(100, backend=self.backend)

    def test_data_and_clock_numeric_captures_use_distinct_pids_and_artifacts(self):
        context = self._elf_context()
        with mock.patch.object(ros_gz_runtime, "verify_live_process", side_effect=self._numeric_elf_report) as verify:
            for role, prefix in (("data", "ros_gz_runtime"), ("clock", "ros_gz_clock_runtime")):
                report = trial.capture_owned_ros_gz_runtime(context, self.evidence, 100,
                    backend=self.backend, timeout_s=2., bridge_specs=self.specs,
                    bridge_role=role, artifact_prefix=prefix)
                recorded = json.loads((self.evidence / (prefix + "_actual.json")).read_text(encoding="utf-8"))
                self.assertEqual(recorded, report)
                self.assertEqual(recorded["owned_launch"]["bridge_role"], role)
                self.assertEqual(recorded["process"]["pid"], self.data_pid if role == "data" else self.clock_pid)
            self.assertEqual([call.args[1] for call in verify.call_args_list], [self.data_pid, self.clock_pid])

    def test_config_changed_during_elf_capture_cannot_publish_success(self):
        def change_after_probe(*args, **kwargs):
            report = self._numeric_elf_report(*args, **kwargs)
            Path(self.specs["clock"]["config_file"]).write_bytes(b"# changed during ELF capture\n")
            return report

        with mock.patch.object(ros_gz_runtime, "verify_live_process", side_effect=change_after_probe):
            with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                trial.capture_owned_ros_gz_runtime(self._elf_context(), self.evidence, 100,
                    backend=self.backend, timeout_s=2., bridge_specs=self.specs,
                    bridge_role="clock", artifact_prefix="ros_gz_clock_runtime")
        self.assertFalse((self.evidence / "ros_gz_clock_runtime_actual.json").exists())
        error = json.loads((self.evidence / "ros_gz_clock_runtime_actual_error.json").read_text(encoding="utf-8"))
        self.assertIn("configuration changed: clock", error["error"])

    def test_missing_clock_registration_is_not_inferred_from_data_registration(self):
        data = {"registration": {"overlay_root": str(self.executable.parent),
                                 "executable": self._elf_context()["registration"]["executable"]}}
        before = deepcopy(data)
        self.assertFalse((self.root / trial.ROS_GZ_CLOCK_CONFIG).exists())
        with self.assertRaises(FileNotFoundError):
            trial.prepare_split_clock_runtime(self.root, data, backend=self.backend)
        self.assertEqual(data, before)
        with self.assertRaisesRegex(ValueError, "require the reviewed data"):
            trial.prepare_split_clock_runtime(self.root, None, backend=self.backend)

    def test_clock_registration_accepts_same_source_and_patch_bytes_with_distinct_plugin_scope(self):
        fixture, data, clock_value, clock_path = self._independent_registration_files()
        clock = trial.prepare_split_clock_runtime(self.root, data, backend=fixture.backend)
        self.assertEqual(clock["path"], clock_path.resolve())
        self.assertEqual(clock["registration"]["plugins"], [])
        self.assertEqual(len(data["registration"]["plugins"]), 1)
        self.assertEqual(clock_value["source"], data["registration"]["source"])
        self.assertNotEqual(clock_value["patch"]["real_path"], data["registration"]["patch"]["real_path"])
        for field in ("sha256", "bytes"):
            self.assertEqual(clock_value["patch"][field], data["registration"]["patch"][field])

    def test_clock_registration_cannot_pair_with_a_different_reviewed_source(self):
        fixture, data, _value, _path = self._independent_registration_files()
        different_data = deepcopy(data)
        different_data["registration"]["source"]["commit"] = "0" * 40
        with self.assertRaises(ValueError):
            trial.prepare_split_clock_runtime(self.root, different_data, backend=fixture.backend)

    def test_clock_registration_requires_matching_present_patch_hash_and_byte_count(self):
        fixture, data, _value, _path = self._independent_registration_files()
        for change in ("absent", "hash", "bytes"):
            with self.subTest(change=change):
                different_data = deepcopy(data)
                if change == "absent":
                    different_data["registration"]["patch"] = None
                elif change == "hash":
                    different_data["registration"]["patch"]["sha256"] = "0" * 64
                else:
                    different_data["registration"]["patch"]["bytes"] += 1
                with self.assertRaises(ValueError):
                    trial.prepare_split_clock_runtime(self.root, different_data, backend=fixture.backend)

    def test_clock_registration_requires_an_explicit_empty_plugin_list(self):
        fixture, data, clock_value, clock_path = self._independent_registration_files()
        for invalid_value in (deepcopy(data["registration"]), deepcopy(clock_value)):
            if not invalid_value["plugins"]:
                del invalid_value["plugins"]
                invalid_value["registration_digest"] = ros_gz_runtime.registration_digest(invalid_value)
            with self.subTest(plugins=invalid_value.get("plugins", "MISSING")):
                clock_path.write_text(json.dumps(invalid_value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    trial.prepare_split_clock_runtime(self.root, data, backend=fixture.backend)

    def test_unloaded_clock_plugin_cannot_borrow_data_mapping_evidence(self):
        context = self._elf_context()
        plugin = self.fixture.directory / "libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so"
        plugin.write_bytes(b"\x7fELFservice-plugin-not-mapped-in-clock\0")
        context["registration"]["plugins"] = [{"path": str(plugin), "real_path": str(plugin.resolve())}]
        with mock.patch.object(ros_gz_runtime, "verify_live_process") as verify:
            with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                trial.capture_owned_ros_gz_runtime(context, self.evidence, 100,
                    backend=self.backend, timeout_s=.03, bridge_specs=self.specs,
                    bridge_role="clock", artifact_prefix="ros_gz_clock_runtime")
        verify.assert_not_called()
        self.assertNotIn(self.specs["data"]["service_argument"], self.backend.commands[self.clock_pid])
        self.assertFalse((self.evidence / "ros_gz_clock_runtime_actual.json").exists())

    def test_dds_capture_independently_binds_both_bridge_pids_and_original_roles(self):
        context = trial.prepare_dds_runtime(self.root, environ=self.fixture.env, backend=self.backend)
        trial.snapshot_dds_runtime(context, self.evidence)
        report = trial.capture_owned_dds_runtime(context, self.evidence, 100, 200,
            backend=self.backend, bridge_specs=self.specs)
        self.assertEqual(set(report["processes"]), {"flight_tf", "bridge_data", "bridge_clock", "agent"})
        self.assertEqual(report["processes"]["bridge_data"]["process"]["pid"], self.data_pid)
        self.assertEqual(report["processes"]["bridge_clock"]["process"]["pid"], self.clock_pid)
        for role in ("data", "clock"):
            evidence = report["processes"]["bridge_" + role]
            self.assertEqual(evidence["role"], "bridge")
            self.assertEqual(evidence["owned_launch"]["bridge_role"], role)
            self.assertEqual(set(evidence["mapped_elfs"]), {"dds", "cdr", "rmw_cpp", "rmw_shared"})

    def test_a_live_but_unowned_clock_bridge_does_not_complete_dds_capture(self):
        # The clock PID still exists and has valid mappings, but is absent from
        # the launch's kernel child tree. It must not be discovered globally.
        self.backend.add(100, executable="bash", children=[101, self.data_pid])
        self.assertEqual(set(self._find()), {"data"})
        context = trial.prepare_dds_runtime(self.root, environ=self.fixture.env, backend=self.backend)
        trial.snapshot_dds_runtime(context, self.evidence)
        with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
            trial.capture_owned_dds_runtime(context, self.evidence, 100, 200,
                backend=self.backend, bridge_specs=self.specs, timeout_s=.05)
        self.assertFalse((self.evidence / "dds_runtime_actual.json").exists())
        self.assertEqual(context["summary"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
