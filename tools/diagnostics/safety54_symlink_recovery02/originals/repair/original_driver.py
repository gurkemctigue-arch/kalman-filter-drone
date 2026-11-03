"""Register and execute four original ambiguity safety trials using public APIs.

The canonical core plan and its completed normal batch owner are inputs. No
historical candidate, run-core receipt, formal admission or retry is invented.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import reliability_v4_guard as guard

KIND = "RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY"
SCOPE = "PUBLIC_NORMAL_SOURCE_SAFETY4_DEVELOPMENT_ONLY"
COMMANDS = ("flight", "source_clock", "native_startup", "specialized", "terminal_speed")
FILES = {"run_config": "run_config.json", "source_snapshot": "configuration/source_sha256.json",
         "runtime_parameters": "configuration/runtime_parameters.yaml", "bag_integrity": "bag_integrity.json",
         "recording_closure": "recording_closure.json", "process_exit_codes": "process_exit_codes.json",
         "source_clock": "px4_source_clock_report.json", "native_startup": "native_startup_report.json",
         "terminal_speed": "terminal_hover_speed_evaluation.json",
         "rendering": "configuration/gazebo_rendering_libraries.json", "magnetic": "configuration/magnetic_environment.json"}
require, load, binding, write_new = guard.require, guard.load, guard.file_binding, guard.write_new


def load_core(core_path, owner_path, *, snapshot_audit_contract=None):
    core_path, owner_path = Path(core_path).resolve(strict=True), Path(owner_path).resolve(strict=True)
    plan, terminal = load(core_path), load(owner_path)
    root = Path(plan["frozen_root"]).resolve(strict=True)
    if snapshot_audit_contract is None:
        require(root == ROOT and Path(guard.__file__).resolve() == root / "tools/reliability_v4_guard.py",
                "Use the actual same-root frozen safety tool and guard")
    else:
        _, _, audited = guard.snapshot_audit_context(snapshot_audit_contract, plan, core_path, driver_path=__file__)
        require(audited["audit_tool_root"] == ROOT, "Explicit actual safety audit-tool root differs")
    runtime = guard.load_runtime(root, plan)
    runner = runtime.v4
    if snapshot_audit_contract is not None:
        require(Path(runner.__file__).resolve(strict=True) == root / "scripts/run_reliability_v4.py"
                and runner.ROOT == root, "Actual frozen runtime runner/root differs from explicit audit contract")
    runner.validate_plan(plan, core_path)
    runner.verify_sources(plan)
    require(plan.get("mode") == "PROBE" and plan.get("selected_seeds") == [4]
            and plan.get("selected_classes") == list(runner.CLASSES)
            and plan.get("selected_groups") == list(runner.GROUPS) and len(plan.get("trials", [])) == 12
            and {(t["target_class"], t["group"], t["seed"]) for t in plan["trials"]}
            == {(cls, group, 4) for cls in runner.CLASSES for group in runner.GROUPS},
            "Safety requires the actual complete canonical seed004 core12")
    require(type(plan.get("split_clock_bridge")) is bool, "Public safety requires an explicit core split-clock declaration")
    batch_path = root / "scripts/run_reliability_v4_batch.py"
    require(guard.sha(batch_path) == plan["source_hashes"].get("scripts/run_reliability_v4_batch.py"),
            "Frozen normal batch owner source differs")
    batch = guard.import_file("safety_same_root_normal_batch", batch_path)
    require(owner_path.name == "owner_terminal.json" and terminal.get("scope") == "THIN_OWNER_OF_UNCHANGED_NORMAL_V4_RUNNER"
            and terminal.get("status") == "COMPLETED" and terminal.get("policy") == "core"
            and terminal.get("plan") == str(core_path) and terminal.get("plan_file_sha256") == guard.sha(core_path)
            and terminal.get("plan_sha256") == plan["plan_sha256"] and terminal.get("all_engineering_pass") is True
            and terminal.get("all_slots_terminal") is True and terminal.get("status_counts") == {"PASS": 12}
            and terminal.get("pending_ids") == [] and terminal.get("active_slot") is None
            and load(owner_path.with_name("owner_state.json")) == terminal,
            "Actual completed matching normal core owner required")
    expected = {name: plan["source_hashes"].get(name) for name in
                ("scripts/run_reliability_v4.py", "scripts/run_reliability_v4_batch.py")}
    require(terminal.get("source_hashes") == expected and all(expected.values()), "Core owner source binding differs")
    identity = terminal.get("owner", {})
    require(type(identity.get("pid")) is int and type(identity.get("start_ticks")) is int
            and isinstance(identity.get("boot_id"), str) and bool(identity["boot_id"])
            and identity.get("creation_identity_scope") == "LINUX_PROC_START_TICKS_AND_BOOT_ID",
            "Original Linux owner creation identity required")
    proc = Path("/proc") / str(identity["pid"]) / "stat"
    if proc.is_file() and Path("/proc/sys/kernel/random/boot_id").read_text().strip() == identity.get("boot_id"):
        fields = proc.read_text().rpartition(")")[2].split()
        require(fields[0] in {"Z", "X"} or int(fields[19]) != identity["start_ticks"], "Original core owner is still alive")
    rows = runner.read_slots(plan)
    records = []
    for trial in plan["trials"]:
        row = rows[trial["id"]]
        require(row.get("status") == row.get("engineering_result") == "PASS"
                and batch.check_slot(runner, plan, trial, row, "core") is None,
                "Every original core slot/source/native/runtime/cleanup must independently PASS: " + trial["id"])
        flight = next(item for item in row["commands"] if item.get("kind") == "flight")
        require(runner.engineering_verdict(plan, trial, flight, row["evaluations"])[0] == "PASS"
                and runner.runtime_configuration(plan, trial)["errors"] == [],
                "Core original acceptance or archived runtime no longer passes: " + trial["id"])
        records.append(binding(runner.record_path(plan, trial)))
    require(not runner.simulation_processes(), "Residual simulation before safety admission")
    gate_builder = guard.import_file("safety_same_root_gate_builder", root / "scripts/build_reliability_v4_probe_gate.py")
    closure = {"source_core_plan": {**binding(core_path), "plan_sha256": plan["plan_sha256"]},
               "normal_owner_terminal": binding(owner_path), "normal_owner_state": binding(owner_path.with_name("owner_state.json")),
               "original_core_records": records, "all_original_core_cells_pass": True,
               "owner_creation_identity": identity, "cleanup": {"residual_processes": []}}
    return SimpleNamespace(root=root, runner=runner, runtime=runtime, batch=batch, plan=plan, core_path=core_path,
                           closure=closure, bindings=gate_builder.bindings(plan), snapshot_audit_contract=snapshot_audit_contract)


def report_files(trial):
    return {**FILES, "specialized": "auto_unique_evaluation_v2.json" if trial["case"] == "auto_unique_multi"
            else "stage2_evaluation.json"}


def definitions(context, prefix, audit):
    runner, plan, root = context.runner, context.plan, context.root
    require(re.fullmatch(r"reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,65}", prefix), "Fresh safety prefix required")
    result = []
    for cls in runner.CLASSES:
        resource = plan["protocol"]["resources"][cls]
        for case in guard.SAFETY_CASES:
            auto = case == "auto_unique_multi"
            identifier = f"{cls}_{case}_seed004"
            name = prefix + "_" + identifier
            directory = root / "results" / name
            settings = {"name": name, "target_class": cls, "stage": 2, "seed": 4, "condition": "clean",
                "estimator_method": "adaptive_kf", "command_mode": "velocity", "gimbal_mode": "midpoint",
                "real_time_factor": plan["protocol"]["real_time_factor"], "max_inference_rate_hz": 10., "monitor_tick_s": .02,
                "control_reference": "ground_footprint", "motion_profile_kind": "standard", "model_path": str(root / resource["model"]),
                "inference_image_size": resource["inference_image_size"], "inference_threads": resource["inference_threads"],
                "desired_distance_m": resource["desired_distance_m"], "takeoff_height_m": 3., "takeoff_mode": "px4_native",
                "wall_timeout": plan["protocol"]["flight_wall_timeout_s"], "render_backend": "egl",
                "gazebo_render_driver": plan["protocol"]["gazebo_render_driver"], "magnetic_environment": "gazebo_enu",
                "magnetic_runtime_manifest": str(root / runner.MAGNETIC_RUNTIME_PATH),
                "magnetic_library_registration": str(root / plan["protocol"]["magnetic_library_registration"]),
                "propagate_vehicle_uncertainty": True, "px4_time_mode": "source_sim",
                "target_mode": "auto_unique" if auto else "locked_target", "association_mode": "legacy" if auto else "hybrid_3d",
                "scenario_kind": "parallel" if auto else "ambiguity", "initial_select": "none" if auto else "middle",
                "initial_min_candidates": 2 if auto else 3, "duration": 35. if auto else 50.}
            if auto:
                settings["no_follow_duration_s"] = 35.
            prefix_command = ["bash", str(root / "scripts/run_research_session.sh")]
            flight = prefix_command + [str(root / "scripts/run_stage1_trial.py")]
            for key, value in settings.items():
                flight.append("--class" if key == "target_class" else "--" + key.replace("_", "-"))
                if value is not True:
                    flight.append(str(value))
            for enabled, flag in ((runner.correlated_two_face_setting(resource, cls), runner.CORRELATED_BOUND_FLAG),
                    (runner.car_surface_recovery_setting(resource, cls)["enabled"], runner.CAR_SURFACE_RECOVERY_FLAG),
                    (runner.exclusive_navigation_setting(resource, cls), runner.EXCLUSIVE_NAVIGATION_FLAG)):
                if enabled:
                    flight.append(flag)
            pacing = runner.simulation_pacing_summary(plan["protocol"])
            if runner.PX4_ADAPTER_PUBLISH_RATE_FIELD in pacing:
                flight += [runner.PX4_ADAPTER_PUBLISH_RATE_FLAG, str(pacing[runner.PX4_ADAPTER_PUBLISH_RATE_FIELD])]
            flight += ["--split-clock-bridge" if plan["split_clock_bridge"] else "--no-split-clock-bridge"]
            for flag, relative in (("--ros-gz-runtime-registration", "config/ros_gz_runtime_humble22.json"),
                    ("--dds-runtime-registration", "config/dds_runtime_humble22.json")):
                require(relative in plan["source_hashes"], "Frozen safety runtime registration missing: " + relative)
                flight += [flag, str(root / relative)]
            if plan["split_clock_bridge"]:
                flight += ["--ros-gz-clock-runtime-registration", str(root / "config/ros_gz_clock_runtime_humble22.json")]
            if runner.SUPERVISOR_STREAM_FIELD in plan["protocol"]:
                flight += [runner.SUPERVISOR_STREAM_FLAG, "source_sim"]
            trial = {"id": identifier, "name": name, "directory": str(directory), "target_class": cls,
                     "case": case, "seed": 4, "settings": settings, "split_clock_bridge": plan["split_clock_bridge"],
                     "flight_argv": flight}
            files = report_files(trial)
            specialized = ([str(root / "scripts/run_stage23_matrix.py"), "--evaluate-auto-unique", str(directory / "rosbag")]
                if auto else [str(root / "scripts/evaluate_stage2_flight.py"), str(directory / "rosbag"),
                    "--telemetry-jsonl", str(directory / "telemetry.jsonl"), "--monitor-summary", str(directory / "summary.json"),
                    "--no-require-occlusions", "--require-ambiguity", "--terminal-expectation", "hover"])
            trial["execution_commands"] = {"flight": flight,
                **{kind: prefix_command + [str(root / script), str(directory), "--output", str(directory / files[kind])]
                   for kind, script in (("source_clock", "scripts/evaluate_px4_source_clock.py"),
                                        ("native_startup", "scripts/evaluate_native_startup.py"))},
                "specialized": prefix_command + specialized + ["--target-class", cls, "--output", str(directory / files["specialized"])],
                "terminal_speed": prefix_command + [str(audit / "terminal_hover_speed.py"), str(directory), str(audit / "execution_card.md")]}
            result.append(trial)
    return result


def register(core_path, owner_path, output, prefix, *, snapshot_audit_contract=None):
    options = {} if snapshot_audit_contract is None else {"snapshot_audit_contract": snapshot_audit_contract}
    context = load_core(core_path, owner_path, **options)
    output = Path(output).resolve()
    results = Path(context.plan["results_root"]).resolve()
    require(output.is_relative_to(results) and output != results and output.parent.is_dir() and not output.exists(),
            "New independent safety audit inside actual results storage required")
    trials = definitions(context, prefix, output)
    require(not any(output.is_relative_to(Path(t["directory"]).resolve()) or Path(t["directory"]).exists()
                    for t in trials), "Original safety trial already exists or overlaps audit; no retry")
    card = context.root / "planning/reliability-v4-ambiguity-execution.md"
    code, raw = guard.safety_tail_code(card), card.read_bytes()
    output.mkdir(exist_ok=False)
    (output / "execution_card.md").write_bytes(raw)
    (output / "terminal_hover_speed.py").write_bytes(code)
    registry = {"schema_version": 1, "kind": KIND, "scope": SCOPE, "created_utc": context.runner.utc_now(),
        "prefix": prefix, "trials": trials, **context.closure, "core_completed_prerequisite": context.closure,
        "flight_source_hashes": context.runner.flight_source_hashes(context.plan["source_hashes"]),
        "split_clock_bridge": context.plan["split_clock_bridge"], "driver": binding(__file__), "validator": binding(guard.__file__),
        "execution_card": binding(output / "execution_card.md"), "tail_script": binding(output / "terminal_hover_speed.py"),
        "formal_seeds_consumed": False, "automatic_retry": False}
    if snapshot_audit_contract is not None:
        registry["snapshot_audit_contract"] = snapshot_audit_contract
    guard.verified_safety_card(registry, context.root)
    write_new(output / "registry.json", registry)
    return binding(output / "registry.json")


def checked_registry(path, expected_sha):
    path = Path(path).resolve(strict=True)
    require(guard.sha(path) == expected_sha, "Prospective registry SHA differs")
    registry = load(path)
    require(registry.get("schema_version") == 1 and registry.get("kind") == KIND and registry.get("scope") == SCOPE,
            "Public prospective safety registry required")
    options = ({"snapshot_audit_contract": registry["snapshot_audit_contract"]} if "snapshot_audit_contract" in registry else {})
    context = load_core(registry["source_core_plan"]["path"], registry["normal_owner_terminal"]["path"], **options)
    require(registry.get("core_completed_prerequisite") == context.closure
            and all(registry.get(k) == v for k, v in context.closure.items())
            and registry.get("driver") == binding(__file__) and registry.get("validator") == binding(guard.__file__)
            and registry.get("flight_source_hashes") == context.runner.flight_source_hashes(context.plan["source_hashes"])
            and type(registry.get("split_clock_bridge")) is bool
            and registry["split_clock_bridge"] is context.plan["split_clock_bridge"]
            and registry.get("trials") == definitions(context, registry["prefix"], path.parent),
            "Original registry/core/tool/runtime binding changed")
    guard.verified_safety_card(registry, context.root)
    return context, registry, path


def immutable_inputs(context, registry, path, expected_sha):
    require(guard.sha(path) == expected_sha, "Prospective safety registry changed")
    for key in ("source_core_plan", "normal_owner_terminal", "normal_owner_state"):
        guard.bound({name: registry[key][name] for name in ("path", "sha256")})
    for item in registry["original_core_records"]:
        guard.bound(item)
    context.runner.verify_sources(context.plan)
    if "snapshot_audit_contract" in registry:
        guard.snapshot_audit_context(registry["snapshot_audit_contract"], context.plan, context.core_path, driver_path=__file__)


def slot_facts(row, registry):
    trial, evidence, missing = row["trial"], {}, []
    directory = Path(trial["directory"])
    files = report_files(trial)
    if registry["split_clock_bridge"]:
        for prefix in ("ros_gz_runtime", "ros_gz_clock_runtime", "dds_runtime"):
            for phase in ("registration", "preflight", "actual", "after"):
                files[prefix + "_" + phase] = "configuration/" + prefix + "_" + phase + ".json"
        files["dds_runtime_summary"] = "configuration/dds_runtime_summary.json"
    else:
        for phase in ("registration", "preflight", "actual", "after", "summary"):
            files["dds_runtime_" + phase] = "configuration/dds_runtime_" + phase + ".json"
    for kind, relative in files.items():
        path = directory / relative
        if path.is_file() and not path.is_symlink():
            evidence[kind] = binding(path)
        else:
            missing.append(kind)
    executions = {}
    for kind, receipt in row["executions"].items():
        value = {"argv": receipt["command"], **{key: receipt.get(key) for key in
            ("started_utc", "finished_utc", "returncode", "error")},
            "outer_cleanup_actions": receipt.get("outer_cleanup_actions", [])}
        for key, candidate in (("log", receipt.get("log")),
                ("outer_receipt", row["execution_receipts"].get(kind, {}).get("path"))):
            if candidate and Path(candidate).is_file() and not Path(candidate).is_symlink():
                value[key] = binding(candidate)
            else:
                missing.append(kind + "_" + key)
        if kind == "terminal_speed":
            value["code_script"] = registry["tail_script"]
        executions[kind] = value
    missing.extend("execution_" + kind for kind in COMMANDS if kind not in executions)
    return {**{key: trial[key] for key in ("id", "target_class", "case", "seed")},
        "trial_directory": str(directory), "result": row["status"], "original_status": row["status"],
        "evidence": evidence, "executions": executions, "missing_evidence": missing,
        "infrastructure_stop": row["infrastructure_stop"], "original_error": row.get("error")}


def audit_slot(context, registry, trial, row):
    runner, directory = context.runner, Path(trial["directory"])
    fact = slot_facts(row, registry)
    require(not fact["missing_evidence"] and set(row["executions"]) == set(COMMANDS), "Incomplete safety command/evidence denominator")
    reports = {kind: load(directory / report_files(trial)[kind]) for kind in COMMANDS[1:]}
    for kind in ("source_clock", "native_startup"):
        spec = {"kind": kind, "script": "scripts/evaluate_px4_source_clock.py" if kind == "source_clock"
                else "scripts/evaluate_native_startup.py", "report": str(directory / report_files(trial)[kind]),
                "evaluation_root": str(context.root)}
        require(runner.read_evaluation(spec, row["executions"][kind], context.plan)["result"] == "PASS",
                "Independent safety clock/native evaluation did not PASS")
    for kind, checks in (("specialized", guard.AUTO_CHECKS if trial["case"] == "auto_unique_multi" else guard.LOCKED_CHECKS),
                         ("terminal_speed", guard.SPEED_CHECKS)):
        report = reports[kind]
        require(set(report.get("checks", {})) == set(checks) and all(type(v) is bool for v in report["checks"].values())
                and report.get("result") == ("PASS" if all(report["checks"].values()) else "FAIL"),
                "Safety report verdict/complete check set contradicts evidence")
    tail = reports["terminal_speed"]
    final = load(directory / "recording_closure.json")["observations"][-1]["last_clock_ns"] / 1e9
    require(abs(tail["interval"]["end_s"] - tail["interval"]["start_s"] - 5.2) < 1e-9
            and abs(tail["interval"]["end_s"] - final) < 1e-9, "Original complete5.2s final-Clock tail required")
    config = load(directory / "run_config.json")
    require(all(config.get(key) == value for key, value in trial["settings"].items())
            and config.get("occlusions") is False and config.get("reselect_after_loss") is False,
            "Actual safety configuration differs from registered command")
    sources = {key: value for key, value in context.plan["source_hashes"].items()
               if key.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(key).suffix in {".py", ".sh", ".msg"}}
    resource = context.plan["protocol"]["resources"][trial["target_class"]]
    sources[resource["model"]] = context.plan["source_hashes"][resource["model"]]
    sources["config/dds_runtime_humble22.json"] = context.plan["source_hashes"]["config/dds_runtime_humble22.json"]
    snapshot_evidence = guard.source_snapshot_evidence(load(directory / FILES["source_snapshot"]), sources, registry, context.plan, context.core_path)
    if "snapshot_audit_contract" in registry:
        row["source_snapshot_audit"] = snapshot_evidence
    exits = load(directory / FILES["process_exit_codes"])
    require({"gazebo", "agent", "px4", "bag", "monitor", "ros"} <= exits.keys()
            and all(type(code) is int and code in ({0, -2} if name == "agent" else {0}) for name, code in exits.items()),
            "Actual safety owned child shutdown failed")
    import yaml
    parameters = yaml.safe_load((directory / FILES["runtime_parameters"]).read_text(encoding="utf-8"))
    expected_nodes = {
        "uav_tracking_detection": {"navigation_enabled": True, "depth_max_age_s": .02},
        "uav_tracking_state_estimator": {"target_mode": trial["settings"]["target_mode"],
            "association_mode": trial["settings"]["association_mode"], "max_observation_age_s": .6,
            "max_prediction_duration_s": .75, "mahalanobis_gate": 9.21, "navigation_enabled": True,
            "propagate_vehicle_uncertainty": True},
        "uav_tracking_controller": {"state_topic": "/tracking/navigation_state", "desired_height_m": 2., "prediction_timeout_s": .75},
        "uav_tracking_px4_adapter": {"use_sim_time": True, "odometry_timestamp_mode": "source_sim",
            "odometry_source_max_age_s": .5, "odometry_source_max_future_s": .05,
            "vehicle_odometry_topic": "/fmu/out/vehicle_odometry", "vehicle_odom_topic": "/vehicle/odometry"},
        "uav_tracking_flight_supervisor": {"takeoff_mode": "px4_native", "status_timestamp_mode": "source_sim",
            "status_source_max_age_s": 1., "status_source_max_future_s": .05, "status_timeout_s": 10.,
            "requested_simulation_real_time_factor": context.plan["protocol"]["real_time_factor"]}}
    require(all(parameters.get(node, {}).get("ros__parameters", {}).get(key) == value
                for node, values in expected_nodes.items() for key, value in values.items()), "Actual safety runtime YAML differs")
    guard.geometry_bound_evidence(resource, trial["target_class"], config, parameters, trial["flight_argv"])
    guard.car_surface_recovery_evidence(context.runtime, resource, trial["target_class"], config, parameters, trial["flight_argv"])
    guard.exclusive_navigation_evidence(context.runtime, resource, trial["target_class"], config, parameters, trial["flight_argv"])
    guard.simulation_pacing_evidence(context.runtime, context.plan["protocol"], config, parameters, trial["flight_argv"])
    guard.safety_split_clock_evidence(context.plan, registry, config, trial["flight_argv"], directory)
    artifacts = {}
    for name, item in fact["evidence"].items():
        artifact = Path(item["path"])
        artifacts[name] = (artifact, parameters if name == "runtime_parameters" else load(artifact))
    guard.safety_command_contract(fact["executions"], artifacts, context.root, directory, trial["target_class"], trial["case"],
                                  execution_card=Path(registry["execution_card"]["path"]))
    last_end = guard.utc(registry["created_utc"])
    for kind in COMMANDS:
        execution = fact["executions"][kind]
        require(execution["argv"] == trial["execution_commands"][kind], "Safety command differs from prospective registry")
        # A complete ordinary algorithm FAIL is preserved, after the tail was executed.
        last_start = guard.utc(execution["started_utc"])
        require(last_start >= last_end, "Safety commands overlap or predate registry")
        last_end = guard.utc(execution["finished_utc"])
        require(last_end >= last_start, "Safety execution time runs backwards")
        guard.bound(execution["log"], json_data=False)
    require(not runner.gazebo_rendering_evidence(directory, "llvmpipe")["errors"]
            and not runner.magnetic_environment_evidence(context.plan, {"directory": str(directory),
                "world_source": f"ros2_ws/src/uav_tracking_bringup/worlds/stage2_flight_{trial['target_class']}.sdf"})["errors"],
            "Actual safety renderer or magnetic evidence failed")
    specialty = reports["specialized"]
    require(Path(specialty.get("inputs", {}).get("bag", "")).resolve() == (directory / "rosbag").resolve(), "Safety specialty recording differs")
    if trial["case"] == "auto_unique_multi":
        require(specialty.get("schema_version") == 2 and specialty.get("source") == "OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY"
                and specialty.get("target_class") == trial["target_class"], "Wrong unique-instance report schema")
    else:
        require(specialty.get("schema_version") == 1 and specialty.get("source") == "OFFLINE_STAGE2_SAFETY_EVALUATION"
                and specialty.get("configuration", {}).get("target_class") == trial["target_class"]
                and specialty.get("configuration", {}).get("require_ambiguity") is True
                and specialty.get("configuration", {}).get("terminal_expectation") == "hover", "Wrong selected-ambiguity report schema")
    require(tail.get("schema_version") == 1 and Path(tail.get("trial", "")).resolve() == directory.resolve(), "Wrong physical tail report schema")
    infra = runner.infrastructure_evidence(directory, [{"report": str(directory / report_files(trial)[kind]),
        "log": row["executions"][kind]["log"], "returncode": row["executions"][kind]["returncode"]} for kind in COMMANDS[1:]])
    require(infra.get("stop") is False, "Safety infrastructure/recording failed")
    return "PASS" if all(report["result"] == "PASS" for report in reports.values()) else "FAIL"


def summary_and_validate(context, registry_path, facts_path, summary_path):
    facts = load(facts_path)
    require(facts.get("result") == "PASS" and facts.get("attempted_count") == 4 and facts.get("pending_count") == 0,
            "Four original passing safety slots required")
    summary = {"schema_version": 1, "kind": "RELIABILITY_V4_FINAL_SAFETY_SUMMARY", "result": "PASS",
        "evidence_scope": "REAL_RECORDED_DEVELOPMENT_EVIDENCE", "created_utc": context.runner.utc_now(),
        "bindings": context.bindings, "source_facts": binding(facts_path), "slots": facts["slots"],
        "validation_scope": "DEVELOPMENT_ONLY_NOT_FORMAL_ADMISSION"}
    write_new(summary_path, summary)
    validation_context = SimpleNamespace(core=context.plan, development=context.plan, development_path=context.core_path,
        gate_bindings=context.bindings, registration_times=[guard.now(), guard.now()])
    guard.validate_safety({"safety": binding(summary_path)}, validation_context, context.runtime)
    require(not context.runner.simulation_processes(), "Residual simulation after full safety validation")
    return binding(summary_path)


@contextmanager
def interrupt_cleanup():
    previous = signal.getsignal(signal.SIGTERM)
    def interrupt(_signal, _frame):
        raise KeyboardInterrupt("Safety owner received termination; original command owns cleanup")
    signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def run(path, expected_sha):
    context, registry, path = checked_registry(path, expected_sha)
    audit, runner = path.parent, context.runner
    require(not any((audit / name).exists() for name in ("owner_started.json", "execution_terminal.json", "slots_facts.json"))
            and not any(Path(t["directory"]).exists() or (audit / (t["id"] + ".started.json")).exists()
                        or (audit / (t["id"] + ".json")).exists() for t in registry["trials"]),
            "Existing safety attempt retained; no retry or overwrite")
    with runner.run_lock(audit), interrupt_cleanup():
        return run_owned(context, registry, path, expected_sha)


def run_owned(context, registry, path, expected_sha):
    audit, runner = path.parent, context.runner
    owner = context.batch.Owner(audit, {"schema_version": 1, "scope": SCOPE, "status": "RUNNING",
        "owner": context.batch.process_identity(), "registry": binding(path), "started_this_invocation": 0,
        "active_slot": None, "all_engineering_pass": False})
    completed, started, stop, active = [], [], None, None
    try:
        try:
            for trial in registry["trials"]:
                immutable_inputs(context, registry, path, expected_sha)
                require(not runner.simulation_processes(), "Residual runtime before safety slot")
                active = trial["id"]
                write_new(audit / (active + ".started.json"), {"created_utc": runner.utc_now(), "registry": binding(path), "trial": trial})
                started.append(active)
                row = {"id": active, "trial": trial, "status": "INFRASTRUCTURE_ERROR", "infrastructure_stop": True,
                       "executions": {}, "execution_receipts": {}, "error": None}
                try:
                    owner.event("safety_slot_started", active_slot=active, started_this_invocation=len(started))
                    owner.monitor_event("START_SLOT", slot=active, total=4)
                    for kind in COMMANDS:
                        if kind != "flight":
                            require(not (Path(trial["directory"]) / report_files(trial)[kind]).exists(), "Original safety report already exists")
                        timeout = (context.plan["protocol"]["flight_wall_timeout_s"] + runner.POSTPROCESSING_TIMEOUT_S
                                   if kind == "flight" else context.plan["evaluation_timeout_s"])
                        receipt = runner.execute_command(trial["execution_commands"][kind], audit / (active + "_" + kind + ".log"), context.root, timeout)
                        row["executions"][kind] = receipt
                        receipt_path = audit / (active + "_" + kind + ".execution.json")
                        write_new(receipt_path, receipt)
                        row["execution_receipts"][kind] = binding(receipt_path)
                        if receipt.get("error") == "KeyboardInterrupt":
                            raise KeyboardInterrupt("Original executor interrupted after owned cleanup")
                        allowed = {0, 2} if kind in {"specialized", "terminal_speed"} else {0}
                        require(receipt.get("returncode") in allowed and receipt.get("error") is None
                                and receipt.get("outer_cleanup_actions", []) == [] and not runner.simulation_processes(),
                                "Original safety command or cleanup failed: " + kind)
                    row["status"] = audit_slot(context, registry, trial, row)
                    row["infrastructure_stop"] = False
                except BaseException as error:
                    row["error"] = type(error).__name__ + ": " + str(error)
                    if isinstance(error, KeyboardInterrupt):
                        row["status"] = "INTERRUPTED"
                finally:
                    try:
                        residual = runner.simulation_processes()
                        immutable_inputs(context, registry, path, expected_sha)
                        require(not residual, "Residual runtime after safety slot")
                        row["cleanup"] = {"residual_processes": residual}
                    except BaseException as error:
                        row["cleanup_error"] = type(error).__name__ + ": " + str(error)
                        row["infrastructure_stop"] = True
                        row["status"] = "INFRASTRUCTURE_ERROR"
                    row["finished_utc"] = runner.utc_now()
                    fact = slot_facts(row, registry)
                    row["execution_facts"] = fact
                    terminal_path = audit / (active + ".json")
                    write_new(terminal_path, row)
                    completed.append({"id": active, "status": row["status"], "terminal": binding(terminal_path), "fact": fact})
                    owner.monitor_event("COMPLETE_SLOT", slot=active, status=row["status"])
                    owner.event("safety_slot_terminal", active_slot=None, slot=active, original_status=row["status"])
                require(row["status"] == "PASS" and row["infrastructure_stop"] is False, "Safety slot did not PASS; retained without retry")
                require(not owner.heartbeat_error, "Safety owner heartbeat failed")
        finally:
            # Stop the writer before committing lifecycle verdicts, so all
            # terminal records agree if a heartbeat failed during the last slot.
            owner.stop.set()
            owner.thread.join(timeout=10.)
            require(not owner.thread.is_alive() and not owner.heartbeat_error, "Safety owner heartbeat failed to close")
    except BaseException as error:
        stop = type(error).__name__ + ": " + str(error)
    cleanup = {}
    try:
        cleanup["residual_processes"] = runner.simulation_processes()
        require(not cleanup["residual_processes"], "Residual runtime after safety execution")
    except BaseException as error:
        cleanup["error"] = type(error).__name__ + ": " + str(error)
        stop = stop or cleanup["error"]
    facts = {"schema_version": 1, "kind": "RELIABILITY_V4_SAFETY_EXECUTION_FACTS",
        "evidence_scope": "REAL_RECORDED_DEVELOPMENT_EVIDENCE", "created_utc": runner.utc_now(),
        "result": "PASS" if len(completed) == 4 and stop is None else "FAIL", "registry": binding(path),
        "slots": [{**item["fact"], "original_terminal": item["terminal"]} for item in completed],
        "planned_count": 4, "attempted_count": len(started), "pending_count": 4 - len(started),
        "unclosed_started_ids": [identifier for identifier in started if identifier not in {item["id"] for item in completed}]}
    write_new(audit / "slots_facts.json", facts)
    validation = {"started_utc": runner.utc_now(), "result": "NOT_RUN", "error": stop}
    if facts["result"] == "PASS":
        try:
            validation["summary"] = summary_and_validate(context, path, audit / "slots_facts.json", audit / "development_validation_summary.json")
            validation.update(result="PASS", error=None)
        except BaseException as error:
            stop = type(error).__name__ + ": " + str(error)
            validation.update(result="FAIL", error=stop)
    validation["finished_utc"] = runner.utc_now()
    write_new(audit / "development_guard_validation.json", validation)
    terminal = {"schema_version": 1, "scope": SCOPE, "finished_utc": runner.utc_now(),
        "status": "COMPLETED" if stop is None and validation["result"] == "PASS" else "STOPPED_FAULT",
        "returncode": 0 if stop is None and validation["result"] == "PASS" else 2, "stop_reason": stop,
        "planned_count": 4, "attempted_count": len(started), "pending_count": 4 - len(started),
        "unclosed_started_ids": facts["unclosed_started_ids"],
        "slots": [{key: item[key] for key in ("id", "status", "terminal")} for item in completed],
        "registry": binding(path), "facts": binding(audit / "slots_facts.json"),
        "guard_validation": binding(audit / "development_guard_validation.json"), "cleanup": cleanup,
        "formal_seeds_consumed": False, "automatic_retry": False}
    write_new(audit / "execution_terminal.json", terminal)
    owner.finish(terminal["status"], reason=stop, all_engineering_pass=terminal["returncode"] == 0,
                 planned_count=4, attempted_count=len(started), pending_count=4-len(started),
                 execution_terminal=binding(audit / "execution_terminal.json"))
    return terminal


def check(path, expected_sha):
    context, registry, path = checked_registry(path, expected_sha)
    audit = path.parent
    terminal, validation, facts = (load(audit / name) for name in
        ("execution_terminal.json", "development_guard_validation.json", "slots_facts.json"))
    require(terminal.get("status") == "COMPLETED" and terminal.get("returncode") == 0
            and terminal.get("stop_reason") is None and terminal.get("cleanup") == {"residual_processes": []}
            and terminal.get("attempted_count") == 4 and terminal.get("pending_count") == 0
            and terminal.get("facts") == binding(audit / "slots_facts.json")
            and terminal.get("guard_validation") == binding(audit / "development_guard_validation.json")
            and terminal.get("registry") == binding(path) and facts.get("registry") == binding(path)
            and len(terminal.get("slots", [])) == len(facts.get("slots", [])) == len(registry["trials"]) == 4
            and validation.get("result") == "PASS", "Original safety lifecycle did not complete successfully")
    owner = load(audit / "owner_terminal.json")
    require(owner == load(audit / "owner_state.json") and owner.get("status") == "COMPLETED"
            and owner.get("all_engineering_pass") is True and owner.get("registry") == binding(path)
            and owner.get("execution_terminal") == binding(audit / "execution_terminal.json"), "Safety owner lifecycle differs")
    for trial, item, fact in zip(registry["trials"], terminal["slots"], facts["slots"]):
        record_path, row = guard.bound(item["terminal"])
        require(record_path == audit / (trial["id"] + ".json") and row.get("trial") == trial
                and row.get("status") == "PASS" and row.get("infrastructure_stop") is False
                and row.get("cleanup") == {"residual_processes": []}
                and {**slot_facts(row, registry), "original_terminal": item["terminal"]} == fact,
                "Original safety record/commands/facts changed")
        marker = load(audit / (trial["id"] + ".started.json"))
        require(marker.get("registry") == binding(path) and marker.get("trial") == trial, "Original started marker differs")
        require(set(row["executions"]) == set(row["execution_receipts"]) == set(COMMANDS), "Original command receipt denominator differs")
        for kind in COMMANDS:
            receipt_path, receipt = guard.bound(row["execution_receipts"][kind])
            require(receipt_path == audit / (trial["id"] + "_" + kind + ".execution.json")
                    and receipt == row["executions"][kind] and receipt.get("command") == trial["execution_commands"][kind],
                    "Original execution receipt or registered command differs")
    summary_path = audit / "development_validation_summary.json"
    require(validation.get("summary") == binding(summary_path), "Original safety validation summary changed")
    context_for_guard = SimpleNamespace(core=context.plan, development=context.plan, development_path=context.core_path,
        gate_bindings=context.bindings, registration_times=[guard.now(), guard.now()])
    guard.validate_safety({"safety": binding(summary_path)}, context_for_guard, context.runtime)
    return {"result": "PASS", "registry": binding(path), "facts": binding(audit / "slots_facts.json"),
            "execution_terminal": binding(audit / "execution_terminal.json"), "all_four_original_pass": True,
            "formal_seed_use_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("register")
    create.add_argument("--core-plan", type=Path, required=True)
    create.add_argument("--core-owner", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--prefix", required=True)
    create.add_argument("--snapshot-audit-contract", type=Path)
    create.add_argument("--snapshot-audit-contract-sha256")
    for action in ("run", "check"):
        command = sub.add_parser(action)
        command.add_argument("--registry", type=Path, required=True)
        command.add_argument("--registry-sha256", required=True)
    args = parser.parse_args(argv)
    if os.name != "posix":
        parser.error("Actual safety registration/execution/check requires the isolated Linux environment")
    try:
        if args.action == "register":
            require(bool(args.snapshot_audit_contract) == bool(args.snapshot_audit_contract_sha256),
                    "Explicit snapshot audit contract path and SHA must be supplied together")
            contract = ({"path": str(args.snapshot_audit_contract.resolve(strict=True)), "sha256": args.snapshot_audit_contract_sha256}
                        if args.snapshot_audit_contract else None)
            result = register(args.core_plan, args.core_owner, args.output, args.prefix, snapshot_audit_contract=contract)
        else:
            result = (run if args.action == "run" else check)(args.registry, args.registry_sha256)
        print(json.dumps(result, indent=2, allow_nan=False))
        return result.get("returncode", 0)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, StopIteration) as error:
        print(json.dumps({"result": "REFUSED", "error": type(error).__name__ + ": " + str(error),
                          "formal_seed_use_authorized": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
