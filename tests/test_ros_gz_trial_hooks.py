"""Exercise the trial's bridge provenance/cleanup with explicit proc fixtures."""
from __future__ import annotations

import ast
from copy import deepcopy
import errno
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

from scripts import run_stage1_trial as trial
from tests import test_ros_gz_runtime as fixtures
from uav_tracking import ros_gz_runtime as runtime


class OwnedBackend(fixtures.FixtureBackend):
    def __init__(self, fixture):
        super().__init__(fixture.executable, fixture.backend.dependencies)
        self.proc_root = fixture.directory / "proc_fixture"
        self.leader = 100
        self.middle = 200
        self.identities = {self.leader: (1, 111), self.middle: (self.leader, 222), self.pid: (self.middle, self.start_ticks)}
        self.states = {}
        self.links = {self.leader: [self.middle], self.middle: [self.pid], self.pid: []}
        self.refresh_children()

    def refresh_children(self):
        for pid, children in self.links.items():
            path = self.proc_root / str(pid) / "task" / str(pid) / "children"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(" ".join(map(str, children)), encoding="ascii")

    def proc_text(self, pid, filename):
        if filename.startswith("task/"):
            return (self.proc_root / str(pid) / filename).read_text(encoding="ascii")
        if filename == "stat":
            parent, start = self.identities[pid]
            fields = ["0"] * 20
            fields[:4] = [self.states.get(pid, "S"), str(parent), str(self.leader), str(self.leader)]
            fields[19] = str(start)
            return str(pid) + " (fixture process) " + " ".join(fields)
        return super().proc_text(pid, filename)

    def exe_path(self, pid):
        return str(self.executable) if pid == self.pid else "/usr/bin/python3"


class RosGzTrialHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RosGzRuntimeTests()
        self.fixture.setUp()
        self.directory = self.fixture.directory
        self.backend = OwnedBackend(self.fixture)
        self.root = self.directory / "final_root"
        self.root.mkdir()
        self.snapshot = self.directory / "configuration"
        self.snapshot.mkdir()
        self.registration = runtime.create_registration(self.fixture.overlay, self.fixture.repo, backend=self.backend)
        self.config = self.root / trial.ROS_GZ_CONFIG
        self.config.parent.mkdir()
        self.config.write_text(json.dumps(self.registration), encoding="utf-8")

    def tearDown(self):
        self.fixture.tearDown()

    def context(self):
        return trial.prepare_ros_gz_runtime(self.root, backend=self.backend)

    def register_plugin(self):
        plugin = self.directory / "allowed underlay/libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so"
        dependency = self.directory / "plugin system/libfastrtps.so"
        for path in (plugin, dependency):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x7fELF\x02\x01\x01\0" + path.name.encode() + b"\0" * 64)
        self.backend.plugin_dependencies[str(plugin)] = [dependency]
        registration = runtime.create_registration(self.fixture.overlay, self.fixture.repo,
            plugin_elf_paths=[plugin], backend=self.backend)
        self.config.write_text(json.dumps(registration), encoding="utf-8")
        return plugin, dependency

    def test_legacy_no_config_skips_without_probes_but_explicit_missing_fails(self):
        self.config.unlink()
        with mock.patch.object(runtime, "verify_registration") as verify:
            self.assertIsNone(trial.prepare_ros_gz_runtime(self.root))
            verify.assert_not_called()
        with self.assertRaises(FileNotFoundError):
            trial.prepare_ros_gz_runtime(self.root, "config/missing.json", backend=self.backend)

    def test_default_config_verified_and_exact_bytes_archived(self):
        context = self.context()
        trial.snapshot_ros_gz_runtime(context, self.snapshot)
        self.assertEqual((self.snapshot / "ros_gz_runtime_registration.json").read_bytes(), self.config.read_bytes())
        report = json.loads((self.snapshot / "ros_gz_runtime_preflight.json").read_text())
        self.assertEqual(report["registration_file_sha256"], context["sha256"])
        self.assertEqual(report["status"], "PASS")

    def test_patch_is_read_from_final_root_same_byte_copy(self):
        self.fixture.source.write_text("int main() { return 1; }\n", encoding="utf-8")
        self.fixture.patch.write_bytes(self.fixture.git("diff", "--binary", "HEAD", "--"))
        value = runtime.create_registration(self.fixture.overlay, self.fixture.repo,
            patch_path=self.fixture.patch, backend=self.backend)
        self.config.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "same-byte final-root copy"):
            self.context()
        patch = self.root / trial.ROS_GZ_PATCH
        patch.parent.mkdir()
        patch.write_bytes(self.fixture.patch.read_bytes())
        self.fixture.patch.unlink()
        self.assertEqual(self.context()["preflight"]["patch_verified_path"], str(patch.resolve()))

    def test_actual_bridge_proof_is_bound_to_owned_ancestor_chain(self):
        context = self.context()
        report = trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
            backend=self.backend, timeout_s=.2)
        self.assertEqual(report["process"]["pid"], self.backend.pid)
        self.assertEqual([row["pid"] for row in report["owned_launch"]["ancestor_chain"]],
                         [self.backend.leader, self.backend.middle, self.backend.pid])
        self.assertEqual(report["registration_file_sha256"], context["sha256"])
        self.assertTrue((self.snapshot / "ros_gz_runtime_actual.json").is_file())
        self.assertEqual(report["mapped_elf_count"], 4)

    def test_unrelated_bridge_not_discovered_and_wait_is_bounded(self):
        context = self.context()
        self.backend.links[self.backend.middle] = []  # Bridge exists, outside the owned subtree.
        self.backend.refresh_children()
        with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
            trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                backend=self.backend, timeout_s=.02)
        error = json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())
        self.assertIn("bounded startup wait", error["error"])
        self.assertFalse((self.snapshot / "ros_gz_runtime_actual.json").exists())

    def test_delayed_plugin_mappings_wait_before_single_expensive_verification(self):
        plugin, dependency = self.register_plugin()
        context = self.context()

        def complete_init(_):
            self.backend.maps.extend(self.backend.mapping(path) for path in (plugin, dependency))

        with mock.patch.object(trial.time, "sleep", side_effect=complete_init) as wait, \
                mock.patch.object(runtime, "verify_live_process", wraps=runtime.verify_live_process) as verify:
            report = trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                backend=self.backend, timeout_s=1.)
        wait.assert_called_once()
        verify.assert_called_once()
        self.assertEqual(report["mapped_elf_count"], 6)

    def test_missing_plugin_mappings_time_out_without_expensive_verification(self):
        plugin, dependency = self.register_plugin()
        context = self.context()
        with mock.patch.object(runtime, "verify_live_process") as verify:
            with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                    backend=self.backend, timeout_s=.02)
        verify.assert_not_called()
        error = json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())
        self.assertIn("bounded startup wait", error["error"])
        self.assertIn(str(plugin), error["error"])
        self.assertIn(str(dependency), error["error"])
        self.assertFalse((self.snapshot / "ros_gz_runtime_actual.json").exists())

    def test_foreign_ros_gz_mapping_is_immediately_rejected_even_while_plugin_pending(self):
        self.register_plugin()
        context = self.context()
        foreign = self.directory / "old overlay/libros_gz_bridge.so"
        foreign.parent.mkdir()
        foreign.write_bytes(self.fixture.bridge.read_bytes())
        self.backend.maps.append(self.backend.mapping(foreign))
        with mock.patch.object(trial.time, "sleep") as wait, mock.patch.object(runtime, "verify_live_process") as verify:
            with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                    backend=self.backend, timeout_s=1.)
        wait.assert_not_called()
        verify.assert_not_called()
        error = json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())
        self.assertIn("Unregistered/old ros_gz ELF", error["error"])

    def test_wrong_executable_or_deleted_mapping_is_not_pending_readiness(self):
        context = self.context()
        owned = trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)
        foreign = self.directory / "old overlay/parameter_bridge"
        foreign.parent.mkdir()
        foreign.write_bytes(self.fixture.executable.read_bytes())
        original = self.backend.exe_path
        with mock.patch.object(self.backend, "exe_path", side_effect=lambda pid: str(foreign) if pid == self.backend.pid else original(pid)):
            with self.assertRaisesRegex(RuntimeError, "executable differs"):
                trial.pending_ros_gz_mappings(context, owned, backend=self.backend)
        self.backend.maps[1]["path"] += " (deleted)"
        with self.assertRaisesRegex(RuntimeError, "ELF is deleted"):
            trial.pending_ros_gz_mappings(context, owned, backend=self.backend)

    def test_parent_identity_change_is_not_treated_as_readiness(self):
        self.backend.identities[self.backend.pid] = (999, self.backend.start_ticks)
        with self.assertRaisesRegex(RuntimeError, "parent identity changed"):
            trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_transient_child_and_thread_esrch_still_find_the_real_bridge(self):
        transient = 300
        self.backend.links[self.backend.leader].append(transient)
        self.backend.links[transient] = []
        self.backend.identities[transient] = (self.backend.leader, 333)
        self.backend.refresh_children()
        thread_file = self.backend.proc_root / str(self.backend.middle) / "task/201/children"
        thread_file.parent.mkdir()
        thread_file.write_text("", encoding="ascii")
        original_proc, original_exe = self.backend.proc_text, self.backend.exe_path
        original_children = trial._ros_gz_children
        for stage in ("stat", "exe", "tasks"):
            with self.subTest(child_disappears_during=stage):
                def proc(pid, filename):
                    if ((pid == transient and filename == "stat" and stage == "stat")
                            or (pid == self.backend.middle and filename == "task/201/children")):
                        raise ProcessLookupError(errno.ESRCH, "Fixture process/thread exited")
                    return original_proc(pid, filename)

                def executable(pid):
                    if pid == transient and stage == "exe":
                        raise ProcessLookupError(errno.ESRCH, "Fixture child exited")
                    return original_exe(pid)

                def children(pid, backend, budget):
                    if pid == transient and stage == "tasks":
                        raise ProcessLookupError(errno.ESRCH, "Fixture child exited")
                    return original_children(pid, backend, budget)

                with mock.patch.object(self.backend, "proc_text", side_effect=proc), \
                        mock.patch.object(self.backend, "exe_path", side_effect=executable), \
                        mock.patch.object(trial, "_ros_gz_children", side_effect=children):
                    owned = trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)
                self.assertEqual(owned["process"]["pid"], self.backend.pid)

    def test_leader_esrch_is_fatal_at_initial_and_final_identity_checks(self):
        original = self.backend.proc_text
        for failed_read in (1, 3):
            reads = 0

            def proc(pid, filename):
                nonlocal reads
                if pid == self.backend.leader and filename == "stat":
                    reads += 1
                    if reads == failed_read:
                        raise ProcessLookupError(errno.ESRCH, "Fixture leader exited")
                return original(pid, filename)

            with self.subTest(failed_leader_read=failed_read), \
                    mock.patch.object(self.backend, "proc_text", side_effect=proc):
                with self.assertRaises(ProcessLookupError):
                    trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_well_formed_dead_ordinary_children_do_not_block_real_bridge(self):
        transient = 300
        self.backend.links[self.backend.leader].append(transient)
        self.backend.identities[transient] = (self.backend.leader, 333)
        self.backend.refresh_children()
        original_exe = self.backend.exe_path

        def executable(pid):
            if pid == transient:
                raise AssertionError("A confirmed dead ordinary child has no executable probe")
            return original_exe(pid)

        for state in ("Z", "X"):
            self.backend.states[transient] = state
            with self.subTest(state=state), mock.patch.object(self.backend, "exe_path", side_effect=executable):
                owned = trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)
            self.assertEqual(owned["process"]["pid"], self.backend.pid)

    def test_malformed_dead_child_is_fatal_instead_of_being_skipped(self):
        transient = 300
        self.backend.links[self.backend.leader].append(transient)
        self.backend.identities[transient] = (self.backend.leader, 333)
        self.backend.refresh_children()
        original = self.backend.proc_text
        for state in ("Z", "X"):
            self.backend.states[transient] = state
            for malformed in ("truncated", "bad-start", "bad-parent"):
                def proc(pid, filename):
                    record = original(pid, filename)
                    if pid == transient and filename == "stat":
                        if malformed == "truncated":
                            return record.rsplit(" ", 1)[0]
                        if malformed == "bad-start":
                            return record.rsplit(" ", 1)[0] + " invalid"
                        return record.replace(state + " 100", state + " 1_00", 1)
                    return record

                with self.subTest(state=state, malformed=malformed), \
                        mock.patch.object(self.backend, "proc_text", side_effect=proc), \
                        self.assertRaises(runtime.RuntimeRegistrationError) as caught:
                    trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)
                self.assertNotIsInstance(caught.exception, runtime.ProcessNotAliveError)
                self.assertIn(f"pid={transient} state={state}", str(caught.exception))

    def test_dead_child_parent_mismatch_is_not_a_transient_lifecycle(self):
        transient = 300
        self.backend.links[self.backend.leader].append(transient)
        self.backend.identities[transient] = (999, 333)
        self.backend.refresh_children()
        for state in ("Z", "X"):
            self.backend.states[transient] = state
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, "dead process parent identity changed"):
                trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_leader_dead_state_is_fatal_at_every_identity_read(self):
        original = self.backend.proc_text
        for state in ("Z", "X"):
            for failed_read in (1, 2, 3):
                reads = 0

                def proc(pid, filename):
                    nonlocal reads
                    record = original(pid, filename)
                    if pid == self.backend.leader and filename == "stat":
                        reads += 1
                        if reads == failed_read:
                            return record.replace(") S ", ") " + state + " ", 1)
                    return record

                with self.subTest(state=state, failed_leader_read=failed_read), \
                        mock.patch.object(self.backend, "proc_text", side_effect=proc), \
                        self.assertRaises(runtime.ProcessNotAliveError):
                    trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_pinned_dead_bridge_cannot_be_lost_or_replaced_during_wait(self):
        self.register_plugin()  # Keep the selected bridge in initialization wait.
        context = self.context()
        replacement = 4321
        original_exe = self.backend.exe_path
        for state in ("Z", "X"):
            for add_replacement in (False, True):
                self.backend.states.clear()
                self.backend.links[self.backend.middle] = [self.backend.pid]
                self.backend.refresh_children()

                def exit_bridge(_):
                    self.backend.states[self.backend.pid] = state
                    if add_replacement:
                        self.backend.links[self.backend.middle].append(replacement)
                        self.backend.links[replacement] = []
                        self.backend.identities[replacement] = (self.backend.middle, 444)
                        self.backend.refresh_children()

                with self.subTest(state=state, replacement=add_replacement), \
                        mock.patch.object(self.backend, "exe_path", side_effect=lambda pid: str(self.fixture.executable) if pid == replacement else original_exe(pid)), \
                        mock.patch.object(trial.time, "sleep", side_effect=exit_bridge) as wait, \
                        mock.patch.object(runtime, "verify_live_process") as verify, \
                        self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                    trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                        backend=self.backend, timeout_s=1.)
                wait.assert_called_once()
                verify.assert_not_called()
                error = json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())
                self.assertIn("identity/ownership changed during startup wait", error["error"])
                self.assertFalse((self.snapshot / "ros_gz_runtime_actual.json").exists())

    def test_bridge_confirmed_by_executable_cannot_disappear_as_an_ordinary_child(self):
        original = trial._ros_gz_children

        def children(pid, backend, budget):
            if pid == self.backend.pid:
                raise ProcessLookupError(errno.ESRCH, "Fixture confirmed bridge exited")
            return original(pid, backend, budget)

        with mock.patch.object(trial, "_ros_gz_children", side_effect=children):
            with self.assertRaises(ProcessLookupError):
                trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_executable_confirmed_bridge_cannot_raise_a_skippable_dead_condition(self):
        original = trial._ros_gz_children
        process = runtime.parse_process_stat(self.backend.proc_text(self.backend.pid, "stat"), self.backend.pid)
        for state in ("Z", "X"):
            def children(pid, backend, budget):
                if pid == self.backend.pid:
                    raise runtime.ProcessNotAliveError(process, state)
                return original(pid, backend, budget)

            with self.subTest(state=state), \
                    mock.patch.object(trial, "_ros_gz_children", side_effect=children), \
                    self.assertRaises(runtime.ProcessNotAliveError):
                trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_pinned_bridge_esrch_cannot_switch_to_a_new_candidate(self):
        self.register_plugin()  # Keep the first bridge in the initialization wait.
        context = self.context()
        replacement = 4321
        departed = False
        original_proc, original_exe = self.backend.proc_text, self.backend.exe_path

        def replace_bridge(_):
            nonlocal departed
            departed = True
            self.backend.links[self.backend.middle] = [self.backend.pid, replacement]
            self.backend.links[replacement] = []
            self.backend.identities[replacement] = (self.backend.middle, 444)
            self.backend.refresh_children()

        def proc(pid, filename):
            if departed and pid == self.backend.pid and filename == "stat":
                raise ProcessLookupError(errno.ESRCH, "Fixture pinned bridge exited")
            return original_proc(pid, filename)

        with mock.patch.object(self.backend, "proc_text", side_effect=proc), \
                mock.patch.object(self.backend, "exe_path", side_effect=lambda pid: str(self.fixture.executable) if pid == replacement else original_exe(pid)), \
                mock.patch.object(trial.time, "sleep", side_effect=replace_bridge) as wait, \
                mock.patch.object(runtime, "verify_live_process") as verify:
            with self.assertRaisesRegex(RuntimeError, "could not be verified before unpause"):
                trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                    backend=self.backend, timeout_s=1.)
        wait.assert_called_once()
        verify.assert_not_called()
        error = json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())
        self.assertIn("identity/ownership changed during startup wait", error["error"])
        self.assertFalse((self.snapshot / "ros_gz_runtime_actual.json").exists())

    def test_permission_and_other_os_errors_are_not_disappearing_processes(self):
        original = self.backend.proc_text
        for code, error_type in ((errno.EACCES, PermissionError), (errno.EIO, OSError)):
            for stage in ("stat", "thread"):
                def proc(pid, filename):
                    if pid == self.backend.middle and filename == ("stat" if stage == "stat" else "task/200/children"):
                        raise error_type(code, "Fixture access failure")
                    return original(pid, filename)

                with self.subTest(errno=code, stage=stage), \
                        mock.patch.object(self.backend, "proc_text", side_effect=proc):
                    with self.assertRaises(error_type):
                        trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)

    def test_multiple_owned_bridges_and_bounds_are_rejected(self):
        other = 4321
        self.backend.links[self.backend.middle].append(other)
        self.backend.links[other] = []
        self.backend.identities[other] = (self.backend.middle, 444)
        self.backend.refresh_children()
        original = self.backend.exe_path
        with mock.patch.object(self.backend, "exe_path", side_effect=lambda pid: str(self.fixture.executable) if pid == other else original(pid)):
            with self.assertRaisesRegex(RuntimeError, "multiple parameter_bridge"):
                trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend)
        with self.assertRaisesRegex(RuntimeError, "process bound"):
            trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend, process_limit=1)
        with self.assertRaisesRegex(RuntimeError, "thread bound"):
            trial.find_owned_parameter_bridge(self.backend.leader, backend=self.backend, thread_limit=1)

    def test_ownership_is_rechecked_after_actual_elf_probe(self):
        context = self.context()
        original = runtime.verify_live_process

        def detached(*args, **kwargs):
            report = original(*args, **kwargs)
            self.backend.links[self.backend.middle] = []
            self.backend.refresh_children()
            return report

        with mock.patch.object(runtime, "verify_live_process", side_effect=detached):
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                trial.capture_owned_ros_gz_runtime(context, self.snapshot, self.backend.leader,
                    backend=self.backend, timeout_s=.1)
        self.assertIn("ownership/creation identity changed",
                      json.loads((self.snapshot / "ros_gz_runtime_actual_error.json").read_text())["error"])

    def test_after_verification_retains_file_drift_and_child_failure(self):
        context = self.context()
        self.assertIsNone(trial.verify_ros_gz_runtime_after(context, self.snapshot,
            ros_exit_code=0, ros_log="clean", backend=self.backend))
        error = trial.verify_ros_gz_runtime_after(context, self.snapshot,
            ros_exit_code=0, ros_log="parameter_bridge: process has died -11", backend=self.backend)
        self.assertIsInstance(error, RuntimeError)
        self.config.write_bytes(self.config.read_bytes() + b"\n")
        drift = trial.verify_ros_gz_runtime_after(context, self.snapshot,
            ros_exit_code=0, ros_log="clean", backend=self.backend)
        self.assertIn("file changed during trial", str(drift))

    def run_finally_fixture(self, original_error=None):
        """Execute the real main finally body with tiny archive/process stubs."""
        source = Path(trial.__file__).read_text(encoding="utf-8")
        main = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "main")
        block = next(node for node in main.body if isinstance(node, ast.Try) and node.finalbody)
        body = ast.parse("if original_error is not None: raise original_error").body
        fixture = ast.FunctionDef(name="finish_fixture", args=ast.arguments(posonlyargs=[], args=[],
            kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=[ast.Try(body=body, handlers=[], orelse=[], finalbody=deepcopy(block.finalbody))], decorator_list=[])
        events = []
        (self.directory / "ros.log").write_text("clean", encoding="utf-8")
        process = SimpleNamespace(poll=lambda: 0)
        failure = ValueError("runtime changed during shutdown")
        namespace = {**trial.__dict__, "original_error": original_error, "recording_spool": self.directory / "spool",
            "simulation_resumed": False, "output": self.directory, "snapshot": self.snapshot,
            "parameter_evidence": {}, "parameter_manifest": self.snapshot / "px4_parameters.json",
            "px4_root": self.directory, "magnetic_runtime": None, "ros_gz_runtime": {"fixture": True},
            "processes": {"ros": process, "bag": process, "monitor": process}, "logs": [],
            "stop": lambda *args, **kwargs: None,
            "snapshot_px4_parameters": lambda *args: {},
            "verify_ros_gz_runtime_after": lambda *args, **kwargs: events.append("verify") or failure,
            "finalize_recording": lambda *args, **kwargs: events.append("archive") or {"status": "PASS"}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fixture], type_ignores=[])), trial.__file__, "exec"), namespace)
        with self.assertRaises(RuntimeError if original_error is None else type(original_error)) as caught:
            namespace["finish_fixture"]()
        self.assertEqual(events, ["verify", "archive"])
        self.assertTrue((self.directory / "bag_integrity.json").is_file())
        return caught.exception, failure

    def test_runtime_cleanup_error_waits_until_recording_archive_finishes(self):
        caught, failure = self.run_finally_fixture()
        self.assertIs(caught.__cause__, failure)

    def test_runtime_cleanup_does_not_replace_original_flight_error(self):
        original = RuntimeError("original flight fault")
        caught, _ = self.run_finally_fixture(original)
        self.assertIs(caught, original)


if __name__ == "__main__":
    unittest.main()
