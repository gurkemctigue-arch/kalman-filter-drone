"""Public safety owner regressions: inert temporary fixtures, never flights."""
from contextlib import nullcontext
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import run_reliability_v4_safety as safety

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_safety_guard_fixtures", ROOT / "tests/test_reliability_v4_guard.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
guard = safety.guard


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return guard.file_binding(path)


def dds_files(root, directory, *, split=False, identities=None):
    """Minimal inert shape matching archived actual DDS report schemas."""
    names = ("flight_tf_fastdds", "flight_tf_fastcdr", "rmw_fastrtps_cpp", "rmw_fastrtps_shared_cpp", "agent_fastdds", "agent_fastcdr")
    record = {"realpath": str(root / "inert.so"), "sha256": "a" * 64, "bytes": 123}
    registration = {"elf_files": {name: dict(record) for name in names}}
    registration_path = root / "config/dds_runtime_humble22.json"
    reg = write(registration_path, registration)
    write(directory / "configuration/dds_runtime_registration.json", registration)
    roles = ("flight_tf", "bridge_data", "bridge_clock", "agent") if split else ("flight_tf", "bridge", "agent")
    processes = {}
    for index, role in enumerate(roles):
        process = {"pid": 100 + index, "start_ticks": 200 + index}
        if identities and role in identities:
            process = identities[role]
        families = ("dds", "cdr") if role == "agent" else ("dds", "cdr", "rmw_cpp", "rmw_shared")
        processes[role] = {"status": "PASS", "fixture_only": False, "registration_sha256": reg["sha256"],
            "role": "bridge" if role.startswith("bridge") else role, "process": process,
            "owned_launch": {"process": process}, "mapped_elfs": {name: dict(record) for name in families}}
    for phase in ("preflight", "actual", "after", "summary"):
        report = {"status": "PASS", "registration_sha256": reg["sha256"], "fixture_only": False}
        if phase == "actual":
            report["processes"] = processes
        if phase == "after":
            report.update(ros_exit_code=0, agent_exit_code=-2)
        write(directory / ("configuration/dds_runtime_" + phase + ".json"), report)
    return reg


def lifecycle_fixture(root, *, linked=False):
    root = root.resolve()
    _, old, runtime, _, facts, _ = fixtures.safety_fixture(root, linked=linked)
    plan, dev = old.development, Path(old.development["frozen_root"])
    plan["protocol"] = old.core["protocol"]
    reader = guard.import_file("public_safety_actual_report_reader", ROOT / "scripts/run_reliability_v4.py")
    evaluators = {"source_clock": "scripts/evaluate_px4_source_clock.py", "native_startup": "scripts/evaluate_native_startup.py"}
    for relative in set(evaluators.values()) | {name for kind in evaluators for name in reader.REPORT_PROVENANCE_HELPERS[kind]}:
        source = dev / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Inert evaluator provenance fixture; never executed\n", encoding="utf-8")
        plan["source_hashes"][relative] = guard.sha(source)
    registry = guard.load(facts["registry"]["path"])
    registry["split_clock_bridge"] = plan["split_clock_bridge"] = False
    audit = root / "audit"
    audit.mkdir()
    templates = {}
    for trial, slot in zip(registry["trials"], facts["slots"]):
        directory = Path(trial["directory"])
        reg = dds_files(dev, directory)
        plan["source_hashes"]["config/dds_runtime_humble22.json"] = reg["sha256"]
        config = guard.load(directory / "run_config.json")
        config.update(split_clock_bridge=False, dds_runtime_registration=reg["path"])
        write(directory / "run_config.json", config)
        sources = guard.load(directory / "configuration/source_sha256.json")
        sources.update({name: digest for name, digest in plan["source_hashes"].items()
                        if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(name).suffix in {".py", ".sh", ".msg"}})
        sources["config/dds_runtime_humble22.json"] = reg["sha256"]
        write(directory / "configuration/source_sha256.json", sources)
        for kind, script in evaluators.items():
            report = {"schema_version": 1, "evaluation_status": "PASS", "trial": str(directory),
                "failures": {}, "incomplete_evidence": {}, "evaluation_source": {
                    "script_sha256": plan["source_hashes"][script], "dependencies": {
                        str(dev / name): plan["source_hashes"][name] for name in reader.REPORT_PROVENANCE_HELPERS[kind]}}}
            if kind == "source_clock":
                report.update(source_clock_pass=True, clock_domain_valid=True, vehicle_frame_continuity_valid=True,
                    counts={"raw_px4": 3, "timing_diagnostics": 3, "adapted_odometry": 3, "claimed_accepted": 3,
                            "claimed_rejected": 0, "independently_matched_triplets": 3})
            else:
                report.update(native_startup_pass=True, checks={name: True for name in reader.NATIVE_STARTUP_CHECKS})
            write(directory / safety.report_files(trial)[kind], report)
        trial["flight_argv"].append("--no-split-clock-bridge")
        trial["execution_commands"] = {kind: list(value["argv"]) for kind, value in slot["executions"].items()}
        trial["execution_commands"]["flight"] = trial["flight_argv"]
        trial["settings"] = {name: config[name] for name in ("target_mode", "association_mode")}
        trial["name"] = directory.name
        trial["split_clock_bridge"] = False
        templates[trial["id"]] = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        shutil.rmtree(directory)
    write(old.development_path, plan)
    registry["source_core_plan"] = {**guard.file_binding(old.development_path), "plan_sha256": plan["plan_sha256"]}
    for name in ("normal_owner_terminal", "normal_owner_state"):
        registry[name] = write(root / (name + ".json"), {"inert_fixture": True})
    registry["original_core_records"] = []
    registry_path = audit / "registry.json"
    write(registry_path, registry)
    actual_batch = guard.import_file("inert_public_safety_owner", ROOT / "scripts/run_reliability_v4_batch.py")
    calls = []
    failure = {}
    def execute(argv, log, cwd, timeout):
        trial = next(t for t in registry["trials"] if argv in t["execution_commands"].values())
        kind = next(k for k, value in trial["execution_commands"].items() if value == argv)
        calls.append((trial["id"], kind))
        log.write_text("Inert unit fixture; no command executed\n", encoding="utf-8")
        if failure.get("kind") == kind and isinstance(failure.get("raise"), BaseException):
            raise failure["raise"]
        directory = Path(trial["directory"])
        reports = safety.report_files(trial)
        selected = templates[trial["id"]]
        for relative, raw in selected.items():
            if (kind == "flight" and relative not in [reports[k] for k in safety.COMMANDS[1:]]) or relative == reports.get(kind):
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        code = 0
        if failure.get("kind") == kind:
            code = failure.get("returncode", 0)
            if failure.get("report_fail"):
                report = guard.load(directory / reports[kind])
                report["checks"][next(iter(report["checks"]))] = False
                report["result"] = "FAIL"
                write(directory / reports[kind], report)
            if failure.get("mutate_report"):
                path = directory / reports[kind]
                report = guard.load(path)
                failure["mutate_report"](report)
                write(path, report)
        return {"command": list(argv), "returncode": code, "started_utc": fixtures.guard.now().isoformat(),
                "finished_utc": fixtures.guard.now().isoformat(), "log": str(log), "error": failure.get("receipt_error")}
    runner = runtime.v4
    runner.execute_command = execute
    runner.utc_now = lambda: guard.now().isoformat()
    runner.verify_sources = lambda plan: None
    runner.run_lock = lambda output: nullcontext()
    runner.simulation_processes = lambda: []
    runner.POSTPROCESSING_TIMEOUT_S = 10
    runner.read_evaluation = reader.read_evaluation
    plan["evaluation_timeout_s"] = 10
    # Rebind the original input after the test-only timeout was added.
    write(old.development_path, plan)
    registry["source_core_plan"] = {**guard.file_binding(old.development_path), "plan_sha256": plan["plan_sha256"]}
    registry["flight_source_hashes"] = deepcopy(old.gate_bindings["flight_source_hashes"])
    write(registry_path, registry)
    context = SimpleNamespace(root=dev, runner=runner, runtime=runtime, plan=plan, batch=actual_batch,
        core_path=old.development_path, bindings=old.gate_bindings)
    return context, registry, registry_path, calls, failure


class PublicSafetyLifecycleTests(unittest.TestCase):
    def invoke(self, context, registry, path):
        with patch.object(safety, "checked_registry", return_value=(context, registry, path)):
            return safety.run(path, guard.sha(path))

    def test_four_original_slots_pass_actual_full_guard_and_readonly_check(self):
        with tempfile.TemporaryDirectory() as folder:
            context, registry, path, calls, _ = lifecycle_fixture(Path(folder))
            result = self.invoke(context, registry, path)
            self.assertEqual(result["status"], "COMPLETED", result)
            self.assertEqual(len(calls), 20)
            for trial in registry["trials"]:
                for kind in ("source_clock", "native_startup"):
                    report = guard.load(Path(trial["directory"]) / safety.report_files(trial)[kind])
                    self.assertEqual(report["evaluation_status"], "PASS")
                    self.assertNotIn("result", report)
            with patch.object(safety, "checked_registry", return_value=(context, registry, path)):
                checked = safety.check(path, guard.sha(path))
            self.assertTrue(checked["all_four_original_pass"])
            self.assertFalse(checked["formal_seed_use_authorized"])

    def test_first_algorithm_failure_runs_tail_retains_original_and_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            context, registry, path, calls, failure = lifecycle_fixture(Path(folder))
            failure.update(kind="specialized", returncode=2, report_fail=True)
            result = self.invoke(context, registry, path)
            self.assertEqual(result["status"], "STOPPED_FAULT")
            self.assertEqual([k for _, k in calls], list(safety.COMMANDS))
            self.assertEqual((result["attempted_count"], result["pending_count"]), (1, 3))
            self.assertEqual(result["slots"][0]["status"], "FAIL")
            self.assertEqual(guard.load(Path(registry["trials"][0]["directory"]) / "auto_unique_evaluation_v2.json")["result"], "FAIL")

    def test_source_command_failure_and_interrupt_keep_missing_evidence_and_no_retry(self):
        for kind, exception in (("source_clock", None), ("flight", KeyboardInterrupt("inert interruption")),
                                ("flight", "KeyboardInterrupt")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                context, registry, path, calls, failure = lifecycle_fixture(Path(folder))
                failure.update(kind=kind, returncode=2)
                if isinstance(exception, str):
                    failure["receipt_error"] = exception
                elif exception:
                    failure["raise"] = exception
                result = self.invoke(context, registry, path)
                self.assertEqual(result["status"], "STOPPED_FAULT")
                self.assertEqual(result["attempted_count"], 1)
                facts = guard.load(path.parent / "slots_facts.json")
                self.assertTrue(facts["slots"][0]["missing_evidence"])
                before = list(calls)
                with self.assertRaises(ValueError):
                    self.invoke(context, registry, path)
                self.assertEqual(calls, before)

    def test_cleanup_probe_error_is_retained_in_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            context, registry, path, calls, _ = lifecycle_fixture(Path(folder))
            context.runner.simulation_processes = lambda: (_ for _ in ()).throw(RuntimeError("inert proc failure"))
            result = self.invoke(context, registry, path)
            self.assertEqual(result["status"], "STOPPED_FAULT")
            self.assertIn("inert proc failure", result["cleanup"]["error"])
            self.assertEqual(calls, [])
            self.assertEqual(guard.load(path.parent / "owner_terminal.json")["status"], "STOPPED_FAULT")

    def test_readonly_check_refuses_truncated_slots_or_changed_receipt(self):
        for mutate in ("truncate", "receipt"):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as folder:
                context, registry, path, _, _ = lifecycle_fixture(Path(folder))
                self.assertEqual(self.invoke(context, registry, path)["status"], "COMPLETED")
                if mutate == "truncate":
                    terminal = guard.load(path.parent / "execution_terminal.json")
                    terminal["slots"] = []
                    write(path.parent / "execution_terminal.json", terminal)
                else:
                    receipt = path.parent / (registry["trials"][0]["id"] + "_flight.execution.json")
                    receipt.write_text('{}', encoding="utf-8")
                with patch.object(safety, "checked_registry", return_value=(context, registry, path)), self.assertRaises(ValueError):
                    safety.check(path, guard.sha(path))


class RawEvaluatorSchemaSafetyTests(unittest.TestCase):
    invoke = PublicSafetyLifecycleTests.invoke

    def test_source_and_native_missing_confused_or_failed_status_never_pass(self):
        for kind in ("source_clock", "native_startup"):
            for variant in ("missing", "result_only", "failed_with_result_pass", "contradictory_pass"):
                with self.subTest(kind=kind, variant=variant), tempfile.TemporaryDirectory() as folder:
                    context, registry, path, calls, failure = lifecycle_fixture(Path(folder))
                    def mutate(report):
                        if variant in {"missing", "result_only"}:
                            del report["evaluation_status"]
                            if variant == "result_only":
                                report.update(result="PASS", status="PASS")
                        elif variant == "failed_with_result_pass":
                            report.update(evaluation_status="FAIL", result="PASS", failures={"inert_failure": 1})
                            report[kind + "_pass"] = False
                            if kind == "native_startup":
                                report["checks"][next(iter(report["checks"]))] = False
                        else:
                            report[kind + "_pass"] = False
                    failure.update(kind=kind, mutate_report=mutate)
                    result = self.invoke(context, registry, path)
                    self.assertEqual(result["status"], "STOPPED_FAULT", result)
                    self.assertEqual((result["attempted_count"], result["pending_count"]), (1, 3))
                    self.assertEqual([command for _, command in calls], list(safety.COMMANDS))
                    original = guard.load(path.parent / (registry["trials"][0]["id"] + ".json"))
                    self.assertEqual(original["status"], "INFRASTRUCTURE_ERROR")
                    self.assertIn("Independent safety clock/native evaluation did not PASS", original["error"])

    def test_specialist_and_tail_still_require_result_and_preserve_algorithm_fail(self):
        for kind in ("specialized", "terminal_speed"):
            for variant in ("missing", "status_only", "fail_with_status_pass"):
                with self.subTest(kind=kind, variant=variant), tempfile.TemporaryDirectory() as folder:
                    context, registry, path, calls, failure = lifecycle_fixture(Path(folder))
                    def mutate(report):
                        if variant in {"missing", "status_only"}:
                            del report["result"]
                            if variant == "status_only":
                                report.update(status="PASS", evaluation_status="PASS")
                        else:
                            report.update(result="FAIL", status="PASS", evaluation_status="PASS")
                            report["checks"][next(iter(report["checks"]))] = False
                    failure.update(kind=kind, mutate_report=mutate)
                    result = self.invoke(context, registry, path)
                    self.assertEqual(result["status"], "STOPPED_FAULT", result)
                    self.assertEqual([command for _, command in calls], list(safety.COMMANDS))
                    original = guard.load(path.parent / (registry["trials"][0]["id"] + ".json"))
                    self.assertEqual(original["status"], "FAIL" if variant == "fail_with_status_pass" else "INFRASTRUCTURE_ERROR")
                    if variant != "fail_with_status_pass":
                        self.assertIn("Safety report verdict/complete check set contradicts evidence", original["error"])


class ResultsSymlinkSafetyTests(unittest.TestCase):
    invoke = PublicSafetyLifecycleTests.invoke

    def linked_fixture(self, root):
        try:
            fixture = lifecycle_fixture(root, linked=True)
        except OSError:
            if os.name != "nt":
                raise
            self.skipTest("Native results-symlink regression requires Windows symlink privilege or Linux")
        if not (fixture[0].root / "results").is_symlink():
            self.skipTest("Native results-symlink regression requires Windows symlink privilege or Linux")
        return fixture

    def test_native_results_symlink_resolves_only_command_contract_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            context, registry, path, calls, _ = self.linked_fixture(Path(folder))
            lexical = [Path(trial["directory"]) for trial in registry["trials"]]
            self.assertTrue(all(directory != directory.resolve(strict=False) for directory in lexical))
            with patch.object(guard, "safety_command_contract", wraps=guard.safety_command_contract) as contract, \
                    patch.object(context.runner, "infrastructure_evidence", wraps=context.runner.infrastructure_evidence) as infrastructure:
                result = self.invoke(context, registry, path)
            self.assertEqual(result["status"], "COMPLETED", result)
            self.assertEqual(len(calls), 20)
            # Slot audits and final summary both execute the unchanged guard.
            self.assertEqual([call.args[3] for call in contract.call_args_list],
                             [directory.resolve(strict=True) for directory in lexical] * 2)
            self.assertEqual([call.args[0] for call in infrastructure.call_args_list], lexical * 2)
            self.assertTrue(all((directory.parent.parent / "uav_tracking/research_failures.py").is_file()
                                for directory in lexical))
            with patch.object(safety, "checked_registry", return_value=(context, registry, path)):
                self.assertTrue(safety.check(path, guard.sha(path))["all_four_original_pass"])

    def test_native_results_symlink_still_refuses_substituted_source_and_native_evaluators(self):
        for kind in ("source_clock", "native_startup"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                context, registry, path, calls, _ = self.linked_fixture(Path(folder))
                registry["trials"][0]["execution_commands"][kind][2] = "scripts/other_evaluator.py"
                write(path, registry)
                result = self.invoke(context, registry, path)
                self.assertEqual(result["status"], "STOPPED_FAULT", result)
                self.assertEqual((result["attempted_count"], result["pending_count"]), (1, 3))
                self.assertEqual([command for _, command in calls], list(safety.COMMANDS))
                original = guard.load(path.parent / (registry["trials"][0]["id"] + ".json"))
                self.assertEqual(original["status"], "INFRASTRUCTURE_ERROR")
                self.assertIn("Safety command does not execute the bound frozen source/native evaluator", original["error"])


class SplitClockSafetyTests(unittest.TestCase):
    def test_legacy_absence_accepted_but_hidden_or_nonbool_switches_rejected(self):
        self.assertFalse(guard.safety_split_clock_evidence({}, {}, {}, [], Path("unused")))
        for plan, registry, config, argv in (({}, {}, {"split_clock_bridge": True}, []),
                ({"split_clock_bridge": 1}, {"split_clock_bridge": True}, {}, []),
                ({"split_clock_bridge": True}, {"split_clock_bridge": False}, {}, []),
                ({}, {}, {}, ["--split-clock-bridge"]), ({}, {}, {}, ["--no-split-clock-bridge=true"])):
            with self.subTest(plan=plan, argv=argv), self.assertRaises(ValueError):
                guard.safety_split_clock_evidence(plan, registry, config, argv, Path("unused"))

    def test_explicit_false_requires_actual_matching_dds_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            directory = root / "trial"
            reg = dds_files(root, directory)
            plan = {"split_clock_bridge": False, "frozen_root": str(root), "source_hashes": {"config/dds_runtime_humble22.json": reg["sha256"]}}
            config = {"split_clock_bridge": False, "dds_runtime_registration": reg["path"]}
            registry = {"split_clock_bridge": False}
            self.assertFalse(guard.safety_split_clock_evidence(plan, registry, config, ["--no-split-clock-bridge"], directory))
            actual_path = directory / "configuration/dds_runtime_actual.json"
            actual = guard.load(actual_path)
            del actual["processes"]["flight_tf"]
            write(actual_path, actual)
            with self.assertRaises(ValueError):
                guard.safety_split_clock_evidence(plan, registry, config, ["--no-split-clock-bridge"], directory)

    def test_original_full_guard_legacy_fixture_still_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, context, runtime, *_ = fixtures.safety_fixture(Path(folder))
            guard.validate_safety(manifest, context, runtime)

    def test_split_true_binds_both_bridge_roles_maps_yaml_and_dds(self):
        for broken in (None, "symlink_install", "same_pid", "yaml", "map", "after", "dds_role", "missing_bridge"):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                directory = root / "trial"
                sources, contracts, identities = {}, {}, {}
                for index, (role, prefix, filename, node) in enumerate((
                        ("data", "ros_gz_runtime", "stage2_data_bridge.yaml", "uav_tracking_gz_bridge"),
                        ("clock", "ros_gz_clock_runtime", "clock_bridge.yaml", "uav_tracking_clock_bridge"))):
                    source = root / "ros2_ws/src/uav_tracking_bringup/config" / filename
                    installed = root / "ros2_ws/install/share/uav_tracking_bringup/config" / filename
                    copied = directory / "configuration" / filename
                    for path in (source, installed, copied):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b'# inert bridge fixture\n')
                    if broken == "symlink_install":
                        installed.unlink()
                        try:
                            installed.symlink_to(source)
                        except OSError:
                            if os.name != "nt":
                                raise
                            self.skipTest("Native symlink-install regression requires Windows symlink privilege or Linux")
                    sources[source.relative_to(root).as_posix()] = guard.sha(source)
                    contracts[role] = {"node_name": node, "config_file": str(installed), "config_sha256": guard.sha(source)}
                    process = {"pid": 801 + index, "start_ticks": 901 + index}
                    identities["bridge_" + role] = process
                    elf = {"real_path": str(root / "inert_bridge.so"), "sha256": "b" * 64}
                    registration = {"registration_digest": "c" * 64, "executable": elf, "dependencies": []}
                    relative = "config/" + prefix + "_humble22.json"
                    reg = write(root / relative, registration)
                    sources[relative] = reg["sha256"]
                    write(directory / ("configuration/" + prefix + "_registration.json"), registration)
                    for phase in ("preflight", "actual", "after"):
                        report = {"status": "PASS", "fixture_only": False, "registration_digest": registration["registration_digest"],
                            "registration_file_sha256": reg["sha256"]}
                        if phase == "actual":
                            report.update(scope="LIVE_PID_EXE_AND_MAPS_MATCH_REGISTERED_ROS_GZ_RUNTIME", process=process,
                                owned_launch={"process": process, "bridge_role": role, **contracts[role]},
                                mapped_elfs=[{"path": elf["real_path"], "sha256": elf["sha256"], "deleted": False}])
                        if phase == "after":
                            report["ros_exit_code"] = 0
                        write(directory / ("configuration/" + prefix + "_" + phase + ".json"), report)
                reg = dds_files(root, directory, split=True, identities=identities)
                sources["config/dds_runtime_humble22.json"] = reg["sha256"]
                plan = {"split_clock_bridge": True, "frozen_root": str(root), "source_hashes": sources}
                config = {"split_clock_bridge": True, "bridge_process_contract": contracts, "dds_runtime_registration": reg["path"],
                    "ros_gz_runtime_registration": str(root / "config/ros_gz_runtime_humble22.json"),
                    "ros_gz_clock_runtime_registration": str(root / "config/ros_gz_clock_runtime_humble22.json")}
                if broken in {"same_pid", "map", "after", "missing_bridge"}:
                    phase = "after" if broken == "after" else "actual"
                    path = directory / ("configuration/ros_gz_clock_runtime_" + phase + ".json")
                    report = guard.load(path)
                    if broken == "same_pid":
                        report["process"] = report["owned_launch"]["process"] = identities["bridge_data"]
                    elif broken == "map":
                        report["mapped_elfs"][0]["sha256"] = "0" * 64
                    elif broken == "after":
                        report["ros_exit_code"] = -15
                    else:
                        path.unlink()
                    if broken != "missing_bridge":
                        write(path, report)
                elif broken == "yaml":
                    (directory / "configuration/clock_bridge.yaml").write_bytes(b'changed\n')
                elif broken == "dds_role":
                    path = directory / "configuration/dds_runtime_actual.json"
                    report = guard.load(path)
                    del report["processes"]["bridge_clock"]
                    write(path, report)
                call = lambda: guard.safety_split_clock_evidence(plan, {"split_clock_bridge": True}, config,
                    ["--split-clock-bridge"], directory)
                if broken in {None, "symlink_install"}:
                    self.assertTrue(call())
                else:
                    with self.assertRaises(ValueError):
                        call()


class PublicSafetyRegistrationTests(unittest.TestCase):
    def test_canonical12_requires_every_original_pass_matching_owner_and_independent_native_reports(self):
        batch = guard.import_file("public_safety_core_owner_fixture", ROOT / "scripts/run_reliability_v4_batch.py")
        for broken in (None, "short_plan", "owner", "owner_hash", "slot_fail", "native_missing", "native_fail", "residual"):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                sources = {}
                for name in ("scripts/run_reliability_v4.py", "scripts/run_reliability_v4_batch.py"):
                    path = root / name
                    path.parent.mkdir(exist_ok=True)
                    path.write_text('# inert frozen source\n', encoding="utf-8")
                    sources[name] = guard.sha(path)
                trials, rows = [], {}
                for cls in guard.CLASSES:
                    for group in guard.GROUPS:
                        identifier = cls + "_" + group + "_seed004"
                        specs, evaluations = [], []
                        for kind in ("source_clock", "native_startup"):
                            report = write(root / "reports" / (identifier + "_" + kind + ".json"), {"result": "PASS"})
                            specs.append({"kind": kind, "report": report["path"]})
                            evaluations.append({"kind": kind, "result": "PASS", "error": None,
                                "report": report["path"], "report_sha256": report["sha256"],
                                "execution": {"returncode": 0, "error": None}})
                        trial = {"id": identifier, "target_class": cls, "group": group, "seed": 4, "evaluations": specs}
                        trials.append(trial)
                        rows[identifier] = {"status": "PASS", "engineering_result": "PASS", "infrastructure_stop": False,
                            "execution_status": "COMPLETED", "flight_exit_code": 0, "runtime_configuration": {"errors": []},
                            "cleanup": {"residual_processes": []}, "evaluations": evaluations, "commands": [{"kind": "flight"}]}
                        write(root / "slots" / (identifier + ".json"), rows[identifier])
                plan = {"frozen_root": str(root), "mode": "PROBE", "selected_seeds": [4], "selected_classes": list(guard.CLASSES),
                    "selected_groups": list(guard.GROUPS), "trials": trials, "split_clock_bridge": True,
                    "plan_sha256": "a" * 64, "source_hashes": sources}
                if broken == "short_plan":
                    plan["trials"] = trials[:-1]
                core = write(root / "core.json", plan)
                owner = {"scope": "THIN_OWNER_OF_UNCHANGED_NORMAL_V4_RUNNER", "status": "COMPLETED", "policy": "core",
                    "plan": core["path"], "plan_file_sha256": core["sha256"], "plan_sha256": plan["plan_sha256"],
                    "all_engineering_pass": True, "all_slots_terminal": True, "status_counts": {"PASS": 12},
                    "pending_ids": [], "active_slot": None, "source_hashes": sources,
                    "owner": {"pid": 99999999, "start_ticks": 123, "boot_id": "inert-boot", "creation_identity_scope": "LINUX_PROC_START_TICKS_AND_BOOT_ID"}}
                if broken == "owner":
                    owner["status"] = "STOPPED_FAULT"
                elif broken == "owner_hash":
                    owner["plan_file_sha256"] = "0" * 64
                elif broken == "slot_fail":
                    rows[trials[0]["id"]]["status"] = "FAIL"
                elif broken == "native_missing":
                    rows[trials[0]["id"]]["evaluations"].pop()
                elif broken == "native_fail":
                    rows[trials[0]["id"]]["evaluations"][1]["result"] = "FAIL"
                owner_path = root / "owner" / "owner_terminal.json"
                write(owner_path, owner)
                write(owner_path.with_name("owner_state.json"), owner)
                runner = SimpleNamespace(CLASSES=guard.CLASSES, GROUPS=guard.GROUPS,
                    validate_plan=lambda *a: None, verify_sources=lambda *a: None, read_slots=lambda *a: rows,
                    engineering_verdict=lambda *a: ("PASS", []), runtime_configuration=lambda *a: {"errors": []},
                    record_path=lambda p, t: root / "slots" / (t["id"] + ".json"),
                    required_evaluators=lambda t: {"source_clock", "native_startup"},
                    read_evaluation=lambda spec, *a: {"result": "PASS", "report_sha256": guard.sha(spec["report"])},
                    simulation_processes=lambda: [{"pid": 987}] if broken == "residual" else [])
                def imported(name, path):
                    return batch if name == "safety_same_root_normal_batch" else SimpleNamespace(bindings=lambda p: {"inert_fixture": True})
                with patch.object(safety, "ROOT", root), patch.object(guard, "__file__", str(root / "tools/reliability_v4_guard.py")), \
                        patch.object(guard, "load_runtime", return_value=SimpleNamespace(v4=runner)), patch.object(guard, "import_file", side_effect=imported):
                    if broken is None:
                        context = safety.load_core(core["path"], owner_path)
                        self.assertEqual(len(context.closure["original_core_records"]), 12)
                        self.assertTrue(context.closure["all_original_core_cells_pass"])
                    else:
                        with self.assertRaises(ValueError):
                            safety.load_core(core["path"], owner_path)

    def test_registration_freezes_original_card_tail_four_slots_and_five_commands(self):
        runner = guard.import_file("public_safety_definition_runner", ROOT / "scripts/run_reliability_v4.py")
        for split in (False, True):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                results = root / "results"
                results.mkdir()
                card = root / "planning/reliability-v4-ambiguity-execution.md"
                card.parent.mkdir()
                card.write_bytes((ROOT / "planning/reliability-v4-ambiguity-execution.md").read_bytes())
                protocol = guard.load(ROOT / "planning/reliability-v4-preregistration.json")
                plan = {"protocol": protocol, "source_hashes": {name: "a" * 64 for name in
                    ("config/dds_runtime_humble22.json", "config/ros_gz_runtime_humble22.json", "config/ros_gz_clock_runtime_humble22.json")},
                    "split_clock_bridge": split, "results_root": str(results), "plan_sha256": "b" * 64}
                core = write(root / "core.json", plan)
                owner = write(root / "core_owner.json", {"inert_fixture": True})
                closure = {"source_core_plan": {**core, "plan_sha256": plan["plan_sha256"]},
                    "normal_owner_terminal": owner, "normal_owner_state": owner, "original_core_records": []}
                context = SimpleNamespace(root=root, runner=runner, plan=plan, closure=closure)
                audit = results / "safety_audit"
                with patch.object(safety, "load_core", return_value=context):
                    registered = safety.register(core["path"], owner["path"], audit, "reliability_v4_public_safety_fixture")
                    registry = guard.load(registered["path"])
                    safety.checked_registry(registered["path"], registered["sha256"])
                    with self.assertRaises(ValueError):
                        safety.register(core["path"], owner["path"], audit, "reliability_v4_public_safety_fixture")
                    changed = deepcopy(registry)
                    changed["trials"][0]["execution_commands"]["flight"].append("--occlusions")
                    altered = write(Path(registered["path"]), changed)
                    with self.assertRaises(ValueError):
                        safety.checked_registry(altered["path"], altered["sha256"])
                self.assertEqual((audit / "execution_card.md").read_bytes(), card.read_bytes())
                self.assertEqual((audit / "terminal_hover_speed.py").read_bytes(), guard.safety_tail_code(card))
                self.assertEqual(len(registry["trials"]), 4)
                for trial in registry["trials"]:
                    self.assertEqual(set(trial["execution_commands"]), set(safety.COMMANDS))
                    self.assertIn("--split-clock-bridge" if split else "--no-split-clock-bridge", trial["flight_argv"])
                    self.assertNotIn("--occlusions", trial["flight_argv"])
                    self.assertNotIn("--reselect-after-loss", trial["flight_argv"])


if __name__ == "__main__":
    unittest.main()
