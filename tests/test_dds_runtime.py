"""Small file/proc fixtures only: no ROS, WSL, native build or large hashes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from uav_tracking import dds_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dds_trial_fixture", ROOT / "scripts/run_stage1_trial.py")
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


class FixtureBackend(runtime.RuntimeBackend):
    fixture_only = True

    def __init__(self, directory):
        super().__init__(directory / "proc")
        self.records, self.executables, self.commands, self.mappings = {}, {}, {}, {}
        self.stat_reads, self.maps_reads = {}, {}
        self.reuse_pid = None

    def add(self, pid, *, parent=1, executable="python", command=None, children=(), mappings=()):
        self.records[pid] = {"pid": pid, "parent_pid": parent, "process_group": pid,
                             "session": pid, "start_ticks": 1000 + pid}
        self.executables[pid] = str(executable)
        self.commands[pid] = command or [str(executable)]
        self.mappings[pid] = [Path(path) for path in mappings]
        task = self.proc_root / str(pid) / "task" / str(pid)
        task.mkdir(parents=True, exist_ok=True)
        (task / "children").write_text(" ".join(map(str, children)), encoding="utf-8")

    def proc_text(self, pid, filename):
        if pid not in self.records:
            raise FileNotFoundError(pid)
        if filename == "stat":
            self.stat_reads[pid] = self.stat_reads.get(pid, 0) + 1
            record = self.records[pid]
            fields = ["0"] * 20
            fields[:4] = ["S", str(record["parent_pid"]), str(record["process_group"]), str(record["session"])]
            fields[19] = str(record["start_ticks"] + int(self.reuse_pid == pid and self.stat_reads[pid] > 1))
            return str(pid) + " (fixture child) " + " ".join(fields)
        if filename == "cmdline":
            return "\0".join(self.commands[pid]) + "\0"
        if filename == "maps":
            self.maps_reads[pid] = self.maps_reads.get(pid, 0) + 1
            rows = []
            for index, path in enumerate(self.mappings[pid]):
                deleted = str(path).endswith(" (deleted)")
                actual = runtime._file_record(str(path).removesuffix(" (deleted)"), elf=True)
                escaped = str(path).replace("\\", "\\134").replace(" ", "\\040")
                rows.append(f'{index+1:08x}-{index+2:08x} r-xp 00000000 '
                            f'{actual["device_major"]:x}:{actual["device_minor"]:x} {actual["inode"]} {escaped}')
            return "\n".join(rows) + "\n"
        return super().proc_text(pid, filename)

    def exe_path(self, pid):
        return self.executables[pid]

    def namespace_file(self, pid, path):
        return Path(path)


class DdsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dds_contract_fixture_")
        self.directory = Path(self.temp.name).resolve()
        self.prefix = self.directory / "dependency/install"
        self.agent = self.directory / "agent/lib"
        self.system = self.directory / "system/lib"
        self.root = self.directory / "project"
        self.config = self.root / trial.DDS_CONFIG
        self.config.parent.mkdir(parents=True)
        files = {
            "flight_tf_fastdds": self.prefix / "lib/libfastrtps.so.2.6.12",
            "flight_tf_fastcdr": self.system / "libfastcdr.so.1.0.29",
            "rmw_fastrtps_cpp": self.system / "librmw_fastrtps_cpp.so",
            "rmw_fastrtps_shared_cpp": self.system / "librmw_fastrtps_shared_cpp.so",
            "agent_fastdds": self.agent / "libfastrtps.so.2.14.7",
            "agent_fastcdr": self.agent / "libfastcdr.so.2.2.8",
        }
        for name, path in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x7fELF\x02\x01" + name.encode() + b"\0" * 32)
        self.files = files
        receipt = self.prefix.parent / "build_inputs.json"
        receipt.write_text(json.dumps({"scope": "ISOLATED_DEPENDENCY_BUILD_NOT_RUNTIME_ACCEPTANCE",
            "files": {"patch": {"sha256": runtime.PATCH_SHA256},
                      "source_archive": {"sha256": runtime.ARCHIVE_SHA256}}}), encoding="utf-8")
        self.registration = {"schema_version": 1, "scope": runtime.SCOPE, "prefix": str(self.prefix),
            "agent_library_directory": str(self.agent), "rmw_implementation": "rmw_fastrtps_cpp",
            "build_inputs": self.descriptor(receipt),
            "elf_files": {name: self.descriptor(path) for name, path in files.items()}}
        self.write_config()
        self.env = {"ROS_DISTRO": "humble", "STAGE1_ROS_DISTRO": "humble", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
                    "LD_LIBRARY_PATH": os.pathsep.join(map(str, (self.agent, self.prefix / "lib", self.system)))}
        self.backend = FixtureBackend(self.directory)
        self.backend.add(42, mappings=[files[key] for key in runtime.ROLE_KEYS["flight_tf"].values()])

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def descriptor(path):
        raw = path.read_bytes()
        return {"path": str(path), "realpath": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def write_config(self):
        self.config.write_text(json.dumps(self.registration, indent=2), encoding="utf-8")

    def preflight(self, **kwargs):
        return runtime.preflight(self.config, backend=self.backend, environ=kwargs.pop("environ", self.env), **kwargs)

    def live(self, **kwargs):
        return runtime.verify_loaded_process(self.config, 42, role=kwargs.pop("role", "flight_tf"),
            expected_process=kwargs.pop("expected_process", self.backend.records[42]), backend=self.backend, **kwargs)

    def test_complete_contract_and_full_environment_are_bound(self):
        report = self.preflight()
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["fixture_only"])
        self.assertEqual(report["registration_sha256"], hashlib.sha256(self.config.read_bytes()).hexdigest())
        current = os.pathsep.join(map(str, (self.system, self.agent, self.system)))
        observed = runtime.environment(self.config, current_library_path=current, backend=self.backend)
        self.assertEqual(observed, self.env["LD_LIBRARY_PATH"])

    def test_cli_help_imports_current_root_from_an_unrelated_cwd_without_pythonpath(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/dds_runtime.py"), "--help"],
            cwd=self.directory, env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--registration", result.stdout)

    def test_wrong_environment_and_path_order_cannot_activate_contract(self):
        cases = [{"ROS_DISTRO": "jazzy"}, {"RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp"},
                 {"LD_LIBRARY_PATH": os.pathsep.join(map(str, (self.prefix / "lib", self.agent)))},
                 {"LD_LIBRARY_PATH": self.env["LD_LIBRARY_PATH"] + os.pathsep + str(self.agent)}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(runtime.DdsRuntimeError):
                self.preflight(environ={**self.env, **changes})

    def test_empty_relative_or_multiline_loader_components_are_rejected(self):
        for value in ("relative", str(self.system) + os.pathsep, str(self.system) + "\n/injected"):
            with self.subTest(value=value), self.assertRaises(runtime.DdsRuntimeError):
                runtime.environment(self.config, current_library_path=value, backend=self.backend)

    def test_changed_file_or_declared_realpath_is_rejected(self):
        self.files["flight_tf_fastdds"].write_bytes(b"\x7fELFchanged")
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "Pinned DDS file differs"):
            self.preflight()
        self.registration["elf_files"]["flight_tf_fastdds"] = self.descriptor(self.files["flight_tf_fastdds"])
        self.registration["elf_files"]["flight_tf_fastdds"]["realpath"] = str(self.prefix / "lib/other.so")
        self.write_config()
        with self.assertRaises(runtime.DdsRuntimeError):
            self.preflight()

    def test_schema_requires_six_exact_roles_and_inside_prefix(self):
        original = deepcopy(self.registration)
        mutations = [lambda v: v.update(schema_version=True),
                     lambda v: v["elf_files"].pop("agent_fastcdr"),
                     lambda v: v["elf_files"].update(extra=v["elf_files"]["agent_fastcdr"]),
                     lambda v: v["elf_files"]["flight_tf_fastdds"].update(realpath=str(self.system / "libfastrtps.so.2.6.12"))]
        for change in mutations:
            self.registration = deepcopy(original)
            change(self.registration)
            self.write_config()
            with self.assertRaises(runtime.DdsRuntimeError):
                self.preflight()

    def test_receipt_hash_and_semantic_source_binding_are_both_required(self):
        receipt = Path(self.registration["build_inputs"]["path"])
        value = json.loads(receipt.read_text(encoding="utf-8"))
        value["files"]["patch"]["sha256"] = "0" * 64
        receipt.write_text(json.dumps(value), encoding="utf-8")
        self.registration["build_inputs"] = self.descriptor(receipt)
        self.write_config()
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "reviewed A01"):
            self.preflight()

    def test_real_process_maps_must_independently_match_all_four_ros_libraries(self):
        report = self.live()
        self.assertEqual(set(report["mapped_elfs"]), {"dds", "cdr", "rmw_cpp", "rmw_shared"})
        self.assertEqual(report["process"], self.backend.records[42])
        self.assertTrue(report["fixture_only"])

    def test_bridge_independently_requires_the_same_four_ros_libraries(self):
        report = self.live(role="bridge")
        self.assertEqual(set(report["mapped_elfs"]), {"dds", "cdr", "rmw_cpp", "rmw_shared"})
        self.assertEqual(report["process"], self.backend.records[42])
        self.assertEqual(len(runtime.ELF_KEYS), 6)
        self.backend.mappings[42].pop()
        with self.assertRaises(runtime.MappingsNotReadyError):
            self.live(role="bridge")

    def test_agent_two_fourteen_is_valid_only_for_agent_process(self):
        self.backend.mappings[42] = [self.files["agent_fastdds"], self.files["agent_fastcdr"]]
        self.assertEqual(set(self.live(role="agent")["mapped_elfs"]), {"dds", "cdr"})
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "Old, mixed-version"):
            self.live()

    def test_extra_old_dds_is_rejected_even_when_expected_new_dds_is_present(self):
        old = self.system / "libfastrtps.so.2.6.12"
        old.write_bytes(b"\x7fELFold DDS")
        self.backend.mappings[42].append(old)
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "Old, mixed-version"):
            self.live()

    def test_typesupport_names_do_not_count_as_dds_or_rmw_libraries(self):
        fake = self.system / "libpx4_msgs__rosidl_typesupport_fastrtps_cpp.so"
        fake.write_bytes(b"\x7fELFtypesupport")
        self.backend.mappings[42].append(fake)
        self.assertEqual(len(self.live()["mapped_elfs"]), 4)
        self.assertIsNone(runtime.library_family(fake))
        self.backend.mappings[42] = [fake]
        with self.assertRaises(runtime.MappingsNotReadyError):
            self.live()

    def test_foreign_rmw_is_rejected_while_common_support_library_is_ignored(self):
        common = self.system / "librmw_dds_common.so"
        common.write_bytes(b"\x7fELFcommon support")
        self.backend.mappings[42].append(common)
        self.assertEqual(len(self.live()["mapped_elfs"]), 4)
        foreign = self.system / "librmw_cyclonedds_cpp.so"
        foreign.write_bytes(b"\x7fELFother RMW")
        self.backend.mappings[42].append(foreign)
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "Unexpected"):
            self.live()

    def test_deleted_mapping_and_pid_reuse_are_hard_failures(self):
        original = list(self.backend.mappings[42])
        self.backend.mappings[42][0] = Path(str(original[0]) + " (deleted)")
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "deleted"):
            self.live()
        self.backend.mappings[42] = original
        self.backend.stat_reads.clear()
        self.backend.reuse_pid = 42
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "changed during live capture"):
            self.live()

    def test_mapped_inode_mismatch_is_not_accepted_from_path_and_hash_alone(self):
        original = self.backend.proc_text
        def changed(pid, filename):
            text = original(pid, filename)
            if filename == "maps":
                first, *rest = text.splitlines()
                fields = first.split(maxsplit=5)
                fields[4] = str(int(fields[4]) + 1)
                return " ".join(fields) + "\n" + "\n".join(rest) + "\n"
            return text
        with mock.patch.object(self.backend, "proc_text", side_effect=changed):
            with self.assertRaisesRegex(runtime.DdsRuntimeError, "device/inode"):
                self.live()

    def test_final_revalidation_rejects_changed_registration_or_library(self):
        expected = self.preflight()["registration_sha256"]
        self.config.write_text(self.config.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "registration changed"):
            runtime.revalidate_files(self.config, expected_config_sha256=expected, backend=self.backend)
        self.write_config()
        self.files["agent_fastcdr"].write_bytes(b"\x7fELFchanged Agent CDR")
        with self.assertRaisesRegex(runtime.DdsRuntimeError, "Pinned DDS file differs"):
            runtime.revalidate_files(self.config, expected_config_sha256=expected, backend=self.backend)

    def test_production_backend_rejects_windows_and_fixture_prefixes(self):
        with mock.patch.object(runtime.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(runtime.DdsRuntimeError, "requires Linux"):
                runtime.preflight(self.config, environ=self.env)
        with mock.patch.object(runtime.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(runtime.DdsRuntimeError, "reviewed isolated prefixes"):
                runtime.preflight(self.config, environ=self.env)

    def context(self):
        return trial.prepare_dds_runtime(self.root, environ=self.env, backend=self.backend)

    def owned_graph(self):
        target = self.root / "ros2_ws/install/lib/uav_tracking_bringup/flight_tf"
        target.parent.mkdir(parents=True)
        target.write_text("# fixture entrypoint\n", encoding="utf-8")
        agent = self.agent.parent / "bin/MicroXRCEAgent"
        agent.parent.mkdir(parents=True)
        agent.write_bytes(b"\x7fELFfixture Agent")
        self.backend.add(100, executable="bash", children=[101, 102])
        self.backend.add(101, parent=100, executable="python", command=["python", str(target), "--ros-args"],
                         mappings=[self.files[key] for key in runtime.ROLE_KEYS["flight_tf"].values()])
        self.backend.add(102, parent=100, executable="parameter_bridge",
                         mappings=[self.files[key] for key in runtime.ROLE_KEYS["bridge"].values()])
        self.backend.add(200, executable=agent, mappings=[self.files["agent_fastdds"], self.files["agent_fastcdr"]])

    def test_jazzy_default_skips_new_humble_config_but_explicit_config_fails(self):
        env = {"ROS_DISTRO": "jazzy"}
        self.assertIsNone(trial.prepare_dds_runtime(self.root, environ=env, backend=self.backend))
        with self.assertRaisesRegex(ValueError, "requires Humble"):
            trial.prepare_dds_runtime(self.root, str(self.config), environ=env, backend=self.backend)

    def test_environment_cannot_redirect_an_implicit_root_registration(self):
        with self.assertRaisesRegex(ValueError, "this root's default"):
            trial.prepare_dds_runtime(self.root,
                environ={**self.env, "UAV_TRACKING_DDS_RUNTIME_CONFIG": str(self.directory / "foreign.json")},
                backend=self.backend)

    def test_owned_tree_capture_and_summary_bind_three_processes_and_file_revalidation(self):
        self.owned_graph()
        context = self.context()
        destination = self.directory / "evidence"
        destination.mkdir()
        trial.snapshot_dds_runtime(context, destination)
        report = trial.capture_owned_dds_runtime(context, destination, 100, 200, backend=self.backend)
        self.assertEqual(set(report["processes"]), {"flight_tf", "bridge", "agent"})
        self.assertEqual(report["processes"]["flight_tf"]["owned_launch"]["process"]["pid"], 101)
        self.assertEqual(report["processes"]["bridge"]["owned_launch"]["process"]["pid"], 102)
        self.assertEqual(report["processes"]["agent"]["owned_launch"]["process"]["pid"], 200)
        self.assertIsNone(trial.verify_dds_runtime_after(context, destination,
            ros_exit_code=0, agent_exit_code=-2, ros_log="", backend=self.backend))
        summary = json.loads((destination / "dds_runtime_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "PASS")
        for key in ("preflight", "actual", "after", "registration_snapshot"):
            self.assertTrue((destination / summary[key]).is_file())

    def test_owned_process_parent_mismatch_and_duplicate_targets_are_rejected(self):
        self.owned_graph()
        context = self.context()
        self.backend.records[101]["parent_pid"] = 999
        with self.assertRaisesRegex(RuntimeError, "parent identity"):
            trial.find_owned_dds_process(context, 100, "flight_tf", backend=self.backend)
        self.backend.records[101]["parent_pid"] = 100
        self.backend.add(103, parent=100, command=self.backend.commands[101])
        (self.backend.proc_root / "100/task/100/children").write_text("101 102 103", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Multiple owned"):
            trial.find_owned_dds_process(context, 100, "flight_tf", backend=self.backend)

    def test_unowned_same_name_is_never_selected(self):
        self.owned_graph()
        context = self.context()
        (self.backend.proc_root / "100/task/100/children").write_text("", encoding="utf-8")
        self.assertIsNone(trial.find_owned_dds_process(context, 100, "flight_tf", backend=self.backend))

    def test_child_shutdown_fault_is_retained_as_failed_dds_evidence(self):
        self.owned_graph()
        context = self.context()
        destination = self.directory / "evidence"
        destination.mkdir()
        trial.snapshot_dds_runtime(context, destination)
        trial.capture_owned_dds_runtime(context, destination, 100, 200, backend=self.backend)
        error = trial.verify_dds_runtime_after(context, destination, ros_exit_code=0, agent_exit_code=-2,
            ros_log="[ERROR] [flight_tf]: process has died exit code -11", backend=self.backend)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(context["summary"]["status"], "FAIL")

    def test_mixed_startup_dds_fails_without_publishing_a_successful_capture(self):
        self.owned_graph()
        context = self.context()
        destination = self.directory / "evidence"
        destination.mkdir()
        trial.snapshot_dds_runtime(context, destination)
        self.backend.mappings[101][0] = self.files["agent_fastdds"]
        with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
            trial.capture_owned_dds_runtime(context, destination, 100, 200, backend=self.backend)
        self.assertFalse((destination / "dds_runtime_actual.json").exists())
        self.assertTrue((destination / "dds_runtime_actual_error.json").is_file())
        self.assertEqual(context["summary"]["status"], "FAIL")

    def test_bridge_mixed_dds_is_rejected_independently_of_valid_tf_and_agent(self):
        self.owned_graph()
        context = self.context()
        destination = self.directory / "evidence"
        destination.mkdir()
        trial.snapshot_dds_runtime(context, destination)
        self.backend.mappings[102][0] = self.files["agent_fastdds"]
        with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
            trial.capture_owned_dds_runtime(context, destination, 100, 200, backend=self.backend)
        self.assertFalse((destination / "dds_runtime_actual.json").exists())
        failure = json.loads((destination / "dds_runtime_actual_error.json").read_text(encoding="utf-8"))
        self.assertIn("Old, mixed-version", failure["error"])
        self.assertEqual(context["summary"]["status"], "FAIL")

    def test_missing_or_unowned_bridge_cannot_publish_successful_three_process_capture(self):
        self.owned_graph()
        context = self.context()
        destination = self.directory / "evidence"
        destination.mkdir()
        (self.backend.proc_root / "100/task/100/children").write_text("101", encoding="utf-8")
        for presence in ("unowned", "absent"):
            with self.subTest(presence=presence):
                if presence == "absent":
                    del self.backend.records[102]
                trial.snapshot_dds_runtime(context, destination)
                with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                    trial.capture_owned_dds_runtime(context, destination, 100, 200,
                                                    timeout_s=.01, backend=self.backend)
                self.assertFalse((destination / "dds_runtime_actual.json").exists())
                failure = json.loads((destination / "dds_runtime_actual_error.json").read_text(encoding="utf-8"))
                self.assertIn("flight_tf/bridge/Agent mappings were not ready", failure["error"])
                self.assertEqual(context["summary"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
