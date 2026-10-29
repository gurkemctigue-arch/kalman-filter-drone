"""Admit at most one already frozen v4 slot; never repair or retry a trial.

This is an outer tool, deliberately outside the runner's flight-source scan.
JSON admission files bind this tool separately. No bag is opened or hashed.
Actual execution is Linux/WSL only; all checks precede the runner's started file.
See planning/reliability-v4-guard-inputs.md for the explicit input contracts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import uuid

MIN_RESERVE = 8 * 1024**3
MAX_SMALL_FILE = 128 * 1024**2
CLASSES = ("person", "car")
GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint", "stage3_active", "stage3_multi_active")
CONDITIONS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")
SAFETY_CASES = ("auto_unique_multi", "locked_ambiguity")
DELIVERIES = ("offline_replay20", "videos12", "detection_audit", "figures_documents", "runtime_logs")
SPEED_CHECKS = ("input_decode_complete", "odom_tail_spans_five_seconds", "odom_tail_covers_original_end",
                "all_observed_odom_speeds_le_0_30_mps", "gt_tail_spans_five_seconds", "gt_tail_covers_original_end",
                "last_gt_equals_final_clock", "all_gt_secant_speeds_le_0_30_mps")
AUTO_CHECKS = ("clock_recorded", "input_decodes_without_errors", "fresh_multi_box_evidence_is_persistent",
               "track_snapshot_messages_valid", "no_explicit_selection", "never_automatically_tracks_a_candidate",
               "never_issues_follow_control", "all_motion_commands_invalid", "armed_and_offboard_observed",
               "all_final_streams_span_five_seconds", "all_final_streams_cover_tail", "final_state_is_ambiguous",
               "final_controller_is_hover", "actual_final_vehicle_speed_below_threshold")
LOCKED_CHECKS = ("clock_recorded", "input_decodes_without_errors", "armed_and_offboard_observed",
                 "initial_explicit_box_confirmed_fresh", "initial_box_matches_selected_track_snapshot",
                 "no_tracking_before_initial_selection", "multiple_same_class_fresh_tracks_observed",
                 "all_tracks_snapshots_present_and_valid", "task_uuid_changes_require_explicit_selection",
                 "long_loss_cannot_reactivate_without_explicit_selection", "long_loss_cannot_control_before_explicit_selection",
                 "active_states_remain_fresh", "selected_geometric_ambiguity_observed_if_required",
                 "observed_ambiguities_suspend_control", "required_short_and_long_occlusions_present",
                 "recorded_occlusions_pass", "detection_diagnostics_valid", "terminal_hover_follows_selected_ambiguity",
                 "final_sustained_hover")


class Refusal(ValueError):
    """A missing or inconsistent prerequisite; no flight is authorized."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sealed(value, field):
    return canonical({key: item for key, item in value.items() if key != field})


def utc(value):
    require(isinstance(value, str), "Explicit UTC time is required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Refusal("Invalid UTC time") from error
    require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, "Time must explicitly use UTC")
    return stamp


def now():
    return datetime.now(timezone.utc)


def integer(value, name, *, minimum=0):
    require(type(value) is int and value >= minimum, "Invalid integer bytes/count: " + name)
    return value


def sha(path, *, limit=MAX_SMALL_FILE):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Missing/linked evidence file: " + str(path))
    require(path.stat().st_size <= limit, "Evidence exceeds small-file limit; bags are not guard inputs: " + str(path))
    require(not any(part in {"rosbag", "rosbag_raw"} for part in path.parts)
            and path.suffix.lower() not in {".zstd", ".zst", ".db3", ".mcap", ".vhdx"}, "Bag/VHD hashing is forbidden")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= MAX_SMALL_FILE, "Missing/oversized JSON: " + str(path))
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Refusal("Nonfinite JSON: " + value)))
    require(isinstance(data, dict), "JSON object required: " + str(path))
    return data


def bound(binding, *, json_data=True):
    require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, "Evidence binding requires exactly path/sha256")
    path = Path(binding["path"])
    require(path.is_absolute(), "Evidence path must be absolute")
    require(isinstance(binding["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", binding["sha256"]) is not None,
            "Evidence SHA256 is required")
    require(sha(path) == binding["sha256"], "Evidence SHA256 changed: " + str(path))
    return (path.resolve(strict=True), load(path)) if json_data else path.resolve(strict=True)


def file_binding(path):
    return {"path": str(Path(path).resolve(strict=True)), "sha256": sha(path)}


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Cannot import frozen helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_runtime(root, core):
    """Verify helpers before import; the frozen validators remain authoritative."""
    names = {"v4": "scripts/run_reliability_v4.py", "replay": "scripts/run_estimator_replay_v4.py",
             "calibration": "scripts/calibrate_estimator_replay_v4.py"}
    for relative in names.values():
        require(sha(root / relative) == core["source_hashes"].get(relative), "Frozen helper source differs: " + relative)
    sys.path[:0] = [str(root), str(root / "scripts")]
    v4 = import_file("run_reliability_v4", root / names["v4"])
    replay = import_file("run_estimator_replay_v4", root / names["replay"])
    calibration = import_file("guard_frozen_calibration", root / names["calibration"])
    for name in ("uav_tracking.replay_comparison", "uav_tracking.core.kalman", "uav_tracking.core.models"):
        location = Path(sys.modules[name].__file__).resolve(strict=True)
        require(location.is_relative_to(root), "Frozen import escaped final root: " + name)
    return SimpleNamespace(v4=v4, replay=replay, calibration=calibration)


def no_fixture(data, label):
    require("FIXTURE" not in str(data.get("evidence_scope", "")).upper(), "Fixture cannot admit formal execution: " + label)


def read_plans(manifest):
    core_path, core = bound(manifest["plans"]["core"])
    extension_path, extension = bound(manifest["plans"]["extension"])
    require(core.get("mode") == "FORMAL" and extension.get("mode") == "EXTENSION_FORMAL", "Both immutable formal plans are required")
    root = Path(manifest["final_root"]).resolve(strict=True)
    require(core.get("frozen_root") == str(root) == extension.get("frozen_root"), "Formal root binding differs")
    require(len(core.get("trials", [])) == 120 and len(extension.get("trials", [])) == 160, "Complete 120+160 plans required")
    for label, plan, groups in (("core", core, GROUPS), ("extension", extension, CONDITIONS)):
        cells = {(trial["target_class"], trial["group"] if label == "core" else trial["extension_condition"], trial["seed"])
                 for trial in plan["trials"]}
        require(cells == {(cls, group, seed) for cls in CLASSES for group in groups for seed in range(1000, 1010)},
                "Incomplete/duplicate held-out matrix: " + label)
        require(len({trial["id"] for trial in plan["trials"]}) == len(plan["trials"]), "Duplicate trial ID")
        require(plan.get("plan_sha256") == sealed(plan, "plan_sha256"), "Formal plan digest changed")
        require(Path(plan["output"]).resolve() / "plan.json" == (core_path if label == "core" else extension_path), "Moved formal plan")
    require(core["source_hashes"] == extension["source_hashes"] and core["model_hashes"] == extension["model_hashes"],
            "Core/extension final source/model differs")
    reference = extension["core_reference_binding"]
    require(reference.get("path") == str(core_path) and reference.get("sha256") == manifest["plans"]["core"]["sha256"]
            and reference.get("plan_sha256") == core["plan_sha256"], "Extension does not bind actual core file")
    return SimpleNamespace(root=root, core=core, extension=extension, core_path=core_path, extension_path=extension_path)


def validate_registrations(manifest, context, runtime):
    v4, replay = runtime.v4, runtime.replay
    registration_times = []
    for name in ("core", "extension"):
        path, data = bound(manifest["registrations"][name])
        expected_path = context.root / (v4.PROTOCOL_PATH if name == "core" else v4.EXTENSION_PROTOCOL_PATH)
        require(path == expected_path, "Registration must be the actual final-root protocol: " + name)
        expected = context.core["protocol"] if name == "core" else context.core["extension_protocol_binding"]["protocol"]
        require(data == expected and data.get("status") == "REGISTERED", "Protocol is not genuinely REGISTERED: " + name)
        stamp = utc(data.get("registration_utc"))
        require(stamp <= utc(context.core["created_utc"]) and stamp <= now(), "Protocol registration follows formal freeze")
        registration_times.append(stamp)
    replay_path, configuration = bound(manifest["registrations"]["replay"])
    require(replay_path == context.root / "planning/reliability-v4-estimator-replay-preregistration.json", "Replay registration must be the actual final-root file")
    no_fixture(configuration, "replay")
    parameters = replay.validate_registered_config(configuration)
    replay.verify_registration_artifacts(configuration, source_root=context.root)
    require(configuration["freeze_requirements"]["final_engineering_plan_path"] == str(context.core_path), "Replay binds another core plan")
    stamp = parameters["registered_utc"]
    require(utc(context.core["created_utc"]) <= stamp <= now(), "Replay must be registered after core definition and before flight")
    registration_times.append(stamp)
    require(max(registration_times) <= utc(manifest["created_utc"]) <= now(), "Admission manifest must follow all registrations and cannot be future dated")
    context.replay_configuration = configuration
    context.registration_times = registration_times
    for name, plan, path in (("core", context.core, context.core_path), ("extension", context.extension, context.extension_path)):
        no_fixture(plan["magnetic_runtime_binding"]["manifest"], name + " runtime")
        no_fixture(plan["magnetic_library_binding"]["registration"], name + " library")
    # EXTENSION_FORMAL validation already validates the actual bound core plan
    # transitively. Avoid a second full traversal/hash of its recorded evidence.
    v4.validate_plan(context.extension, context.extension_path)
    # Both plans have the identical manifest; do not rehash final sources twice.
    v4.verify_sources(context.core)


def validate_development(manifest, context, runtime):
    v4, replay, calibration = runtime.v4, runtime.replay, runtime.calibration
    core_gate = context.core["development_probe_gate"]
    extension_gate = context.core["extension_protocol_binding"]["protocol"]["development_readiness"]
    for label, binding, expected in (("core", core_gate, 12), ("extension", extension_gate, 16)):
        _, gate = bound({key: binding[key] for key in ("path", "sha256")})
        require(gate == binding["evidence"] and gate.get("result") == "PASS" and len(gate.get("probe_slots", [])) == expected,
                "Actual complete development gate required: " + label)
        no_fixture(gate, label + " gate")
    candidate_path, candidate = bound(manifest["calibration"])
    require(candidate.get("kind") == "RELIABILITY_V4_DEVELOPMENT_CALIBRATION"
            and candidate.get("status") == "CANDIDATE_NOT_REGISTERED" and candidate.get("scope") == "DEVELOPMENT_ONLY",
            "Actual development-only candidate calibration required")
    dev_binding = candidate["development_plan"]
    dev_path, dev = bound({key: dev_binding[key] for key in ("path", "sha256")})
    require(dev_binding["plan_sha256"] == dev["plan_sha256"] and dev.get("mode") == "PROBE"
            and dev.get("selected_seeds") == [4] and dev.get("selected_classes") == list(CLASSES)
            and dev.get("selected_groups") == list(GROUPS), "Calibration must use canonical complete seed004 core12")
    require({item["plan_path"] for item in core_gate["evidence"]["probe_slots"]} == {str(dev_path)}, "Core gate and R0 canonical source differ")
    require({item["slot_id"] for item in core_gate["evidence"]["probe_slots"]} == {trial["id"] for trial in dev["trials"]},
            "Canonical calibration development matrix differs")
    v4.validate_plan(dev, dev_path)
    records = v4.read_slots(dev, verify_artifacts=False)
    sources = {name: v4.sha(context.root / name) for name in replay.EXPORT_SOURCE_FILES}
    audit_config = {"freeze_requirements": {"evaluation_source_hashes": sources,
        "offline_replay_source_hashes": {name: sources[name] for name in replay.SOURCE_FILES}, "flight_source_hashes": dev["source_hashes"]}}
    evidence = context.replay_configuration["freeze_requirements"]["development_calibration_evidence"]
    require(evidence["artifact_hashes"].get(str(candidate_path)) == manifest["calibration"]["sha256"], "Replay does not bind actual candidate calibration")
    for cls in CLASSES:
        provenance = candidate["provenance"][cls]
        slot_id = f"{cls}_stage1_velocity_seed004"
        trial_spec = next(trial for trial in dev["trials"] if trial["id"] == slot_id)
        record_path, record = bound(provenance["terminal_record"])
        require(provenance["slot_id"] == slot_id and record_path == v4.record_path(dev, trial_spec).resolve()
                and record == records[slot_id] and record.get("execution_status") == "COMPLETED"
                and record.get("infrastructure_stop") is False and record.get("flight_exit_code") == 0,
                "Canonical calibration slot is incomplete or substituted")
        arrays_path, arrays = bound(provenance["arrays"])
        require(arrays.get("seed") == 4 and arrays.get("target_class") == cls and arrays.get("group") == "stage1_velocity"
                and arrays.get("slot_id") == "DEVELOPMENT_ONLY_" + trial_spec["name"], "R0 arrays belong to another development slot")
        require(calibration.bind_named_recording(trial_spec, record, arrays) == provenance["recording_evidence"], "Calibration recording provenance differs")
        receipt = replay.verify_export_evidence(arrays_path, arrays, audit_config, source_root=context.root, development_only=True)
        require(receipt == provenance["verified_export_evidence"], "Calibration export receipt differs")
        require(calibration.geometry_statistics(arrays) == candidate["classes"][cls], "R0 statistics no longer reproduce actual arrays")
    expected = candidate["candidate_parameters"]
    registered = context.replay_configuration["calibration"]
    require(all(registered.get(key) == value for key, value in expected.items()), "Registered estimator parameters differ from actual development candidate")
    require(utc(candidate["created_utc"]) <= context.registration_times[-1], "Calibration follows replay registration")
    policy = Path(dev["frozen_root"])/candidate["policy"]["path"]
    require(sha(policy) == candidate["policy"]["sha256"]
            and candidate["source_hashes"].get("scripts/calibrate_estimator_replay_v4.py")
            == context.core["source_hashes"].get("scripts/calibrate_estimator_replay_v4.py"), "Calibration policy/helper provenance differs")
    context.development = dev
    context.development_path = dev_path
    context.gate_bindings = core_gate["evidence"]["bindings"]


def all_checks(data, names, label):
    checks = data.get("checks", {})
    require(isinstance(checks, dict) and set(names) <= set(checks) and all(value is True for value in checks.values()),
            "Required checks missing/negative/unknown: " + label)


def validate_execution(execution, *, after=None):
    require(isinstance(execution, dict) and type(execution.get("returncode")) is int and execution["returncode"] == 0
            and execution.get("error") is None, "Safety command did not finish successfully")
    command = execution.get("argv")
    require(isinstance(command, list) and bool(command) and all(isinstance(item, str) and item for item in command), "Original command argv required")
    start, end = utc(execution["started_utc"]), utc(execution["finished_utc"])
    require(start <= end <= now() and (after is None or start >= after), "Safety execution chronology differs")
    bound(execution["log"], json_data=False)
    return start, end


def option(command, flag):
    require(command.count(flag) == 1 and command.index(flag)+1 < len(command), "Missing/duplicate command option: " + flag)
    return command[command.index(flag)+1]


def safety_command_contract(executions, artifacts, dev_root, directory, cls, case):
    prefix = ["bash", str(dev_root/"scripts/run_research_session.sh")]
    def actual_script(command, script):
        if len(command) < 3 or command[:2] != prefix:
            return False
        argument = Path(command[2])
        return (argument if argument.is_absolute() else dev_root/argument).resolve() == (dev_root/"scripts"/script).resolve()
    for kind, script in (("source_clock", "evaluate_px4_source_clock.py"), ("native_startup", "evaluate_native_startup.py")):
        command = executions[kind]["argv"]
        require(actual_script(command, script) and len(command) >= 4
                and Path(command[3]).resolve() == directory and Path(option(command, "--output")).resolve() == artifacts[kind][0],
                "Safety command does not execute the bound frozen source/native evaluator")
    command = executions["specialized"]["argv"]
    script = "run_stage23_matrix.py" if case == "auto_unique_multi" else "evaluate_stage2_flight.py"
    require(actual_script(command, script)
            and option(command, "--target-class") == cls and Path(option(command, "--output")).resolve() == artifacts["specialized"][0],
            "Safety specialist command/source/output differs")
    if case == "auto_unique_multi":
        require(Path(option(command, "--evaluate-auto-unique")).resolve() == directory/"rosbag", "Unique-mode evaluator bag differs")
    else:
        require(len(command) >= 4 and Path(command[3]).resolve() == directory/"rosbag"
                and "--no-require-occlusions" in command and "--require-ambiguity" in command
                and option(command, "--terminal-expectation") == "hover"
                and Path(option(command, "--telemetry-jsonl")).resolve() == directory/"telemetry.jsonl"
                and Path(option(command, "--monitor-summary")).resolve() == directory/"summary.json", "Selected-ambiguity evaluator flags/recording differ")
    command = executions["terminal_speed"]["argv"]
    code_path = bound(executions["terminal_speed"]["code_script"], json_data=False)
    card = dev_root/"planning/reliability-v4-ambiguity-execution.md"
    text = card.read_text(encoding="utf-8")
    marker = '<<\'PY\'\n'
    require(text.count(marker) == 1 and "\nPY\n" in text.split(marker,1)[1], "Frozen safety-card audit code is not uniquely defined")
    code = text.split(marker,1)[1].split("\nPY\n",1)[0]+"\n"
    require(code_path.read_bytes() == code.encode("utf-8"), "Executed hover-speed code differs from frozen reviewed safety card")
    require(len(command) == 5 and command[:2] == prefix and (command[2] == "-" or Path(command[2]).resolve() == code_path)
            and Path(command[3]).resolve() == directory and Path(command[4]).resolve() == card.resolve(), "Hover-speed original command/stdin differs")


def validate_safety(manifest, context, runtime):
    path, summary = bound(manifest["safety"])
    require(summary.get("schema_version") == 1 and summary.get("kind") == "RELIABILITY_V4_FINAL_SAFETY_SUMMARY"
            and summary.get("result") == "PASS" and summary.get("evidence_scope") == "REAL_RECORDED_DEVELOPMENT_EVIDENCE",
            "Actual four-slot safety summary is required")
    require(summary.get("bindings") == context.gate_bindings, "Safety final flight/evaluation/model/runtime bindings differ")
    _, facts = bound(summary["source_facts"])
    require(facts.get("schema_version") == 1 and facts.get("kind") == "RELIABILITY_V4_SAFETY_EXECUTION_FACTS"
            and facts.get("slots") == summary.get("slots") and facts.get("result") == "PASS"
            and facts.get("evidence_scope") == "REAL_RECORDED_DEVELOPMENT_EVIDENCE"
            and facts.get("planned_count") == 4 and facts.get("attempted_count") == 4 and facts.get("pending_count") == 0,
            "Safety summary changed/incompletely attempts original execution facts")
    _, registry = bound(facts["registry"])
    require(registry.get("schema_version") == 1 and registry.get("kind") == "RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY",
            "Actual prospective four-safety registry required")
    source = registry["source_core_plan"]
    source_path, source_plan = bound({key:source[key] for key in ("path", "sha256")})
    require(source_path == context.development_path and source_plan == context.development
            and source["plan_sha256"] == context.development["plan_sha256"]
            and registry["flight_source_hashes"] == context.gate_bindings["flight_source_hashes"], "Safety registry binds a different canonical development plan/source")
    card_path = bound(registry["execution_card"], json_data=False)
    require(card_path == Path(context.development["frozen_root"])/"planning/reliability-v4-ambiguity-execution.md", "Safety registry card path differs")
    tail_path = bound(registry["tail_script"], json_data=False)
    bound(registry["driver"], json_data=False)
    require(utc(registry["created_utc"]) <= utc(facts["created_utc"]) <= utc(summary["created_utc"]), "Safety registry/facts/summary chronology differs")
    registered_trials = registry.get("trials", [])
    require(len(registered_trials) == 4 and len({item["id"] for item in registered_trials}) == 4, "Safety registry must prospectively name four distinct slots")
    slots = summary.get("slots", [])
    require(len(slots) == 4 and {(s.get("target_class"), s.get("case")) for s in slots} == {(c, k) for c in CLASSES for k in SAFETY_CASES},
            "Both classes and both actual ambiguity safety cases required")
    directories = set()
    for slot in slots:
        cls, case = slot["target_class"], slot["case"]
        require(slot.get("id") == f"{cls}_{case}_seed004" and slot.get("seed") == 4 and slot.get("result") == "PASS", "Safety slot identity/result differs")
        directory = Path(slot["trial_directory"]).resolve(strict=True)
        require(directory.is_relative_to(Path(context.development["results_root"]).resolve()) and directory not in directories,
                "Safety directory is outside final development storage or duplicated")
        directories.add(directory)
        registered = next((item for item in registered_trials if item["id"] == slot["id"]), None)
        require(registered is not None and Path(registered["directory"]).resolve() == directory
                and (registered["target_class"],registered["case"],registered["seed"]) == (cls,case,4), "Safety registry slot substituted")
        artifacts = {}
        for name, binding in slot["evidence"].items():
            if Path(binding["path"]).suffix.lower() in {".yaml", ".yml"}:
                artifact_path = bound(binding, json_data=False)
                import yaml
                data = yaml.safe_load(artifact_path.read_text(encoding="utf-8"))
                require(isinstance(data, dict), "Safety runtime YAML must contain an object")
            else:
                artifact_path, data = bound(binding)
            require(artifact_path.is_relative_to(directory), "Safety evidence is outside its original trial")
            artifacts[name] = (artifact_path, data)
        required = {"run_config", "source_snapshot", "runtime_parameters", "bag_integrity", "recording_closure", "process_exit_codes",
                    "source_clock", "native_startup", "specialized", "terminal_speed", "rendering", "magnetic"}
        require(required <= artifacts.keys(), "Safety evidence files are incomplete")
        expected_names = {"run_config":"run_config.json", "source_snapshot":"configuration/source_sha256.json",
            "runtime_parameters":"configuration/runtime_parameters.yaml", "bag_integrity":"bag_integrity.json",
            "recording_closure":"recording_closure.json", "process_exit_codes":"process_exit_codes.json",
            "source_clock":"px4_source_clock_report.json", "native_startup":"native_startup_report.json",
            "terminal_speed":"terminal_hover_speed_evaluation.json", "rendering":"configuration/gazebo_rendering_libraries.json",
            "magnetic":"configuration/magnetic_environment.json"}
        require(all(artifacts[name][0] == directory / relative for name, relative in expected_names.items()), "Safety artifact path substituted")
        configuration = artifacts["run_config"][1]
        dev_root = Path(context.development["frozen_root"])
        lexical_directory = dev_root/"results"/directory.name
        require(lexical_directory.resolve(strict=True) == directory, "Original lexical frozen trial path no longer resolves to physical evidence")
        resource = context.core["protocol"]["resources"][cls]
        expected = {"target_class":cls, "stage":2, "seed":4, "command_mode":"velocity", "gimbal_mode":"midpoint",
            "target_mode":"auto_unique" if case == "auto_unique_multi" else "locked_target",
            "association_mode":"legacy" if case == "auto_unique_multi" else "hybrid_3d",
            "initial_select":"none" if case == "auto_unique_multi" else "middle",
            "initial_min_candidates":2 if case == "auto_unique_multi" else 3,
            "scenario_kind":"parallel" if case == "auto_unique_multi" else "ambiguity",
            "duration":35. if case == "auto_unique_multi" else 50., "condition":"clean", "motion_profile_kind":"standard",
            "takeoff_mode":"px4_native", "takeoff_height_m":3., "control_reference":"ground_footprint",
            "real_time_factor":.5, "max_inference_rate_hz":10., "monitor_tick_s":.02,
            "gazebo_render_driver":"llvmpipe", "px4_time_mode":"source_sim", "magnetic_environment":"gazebo_enu",
            "propagate_vehicle_uncertainty":True, "occlusions":False, "reselect_after_loss":False,
            "no_follow_duration_s":35. if case == "auto_unique_multi" else None,
            "supervisor_status_timestamp_mode":"source_sim", "supervisor_status_source_max_age_s":1.,
            "supervisor_status_source_max_future_s":.05, "supervisor_status_timeout_wall_s":10.,
            "vehicle_control_point_offset_flu_m":[0.,0.,.24], "model_path":str(dev_root/resource["model"]),
            "inference_image_size":resource["inference_image_size"], "inference_threads":resource["inference_threads"],
            "desired_distance_m":resource["desired_distance_m"]}
        require(all(configuration.get(key) == value for key, value in expected.items()), "Safety recorded configuration differs: " + slot["id"])
        snapshot = artifacts["source_snapshot"][1]
        expected_sources = {key:value for key,value in context.development["source_hashes"].items()
                            if key.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(key).suffix in {".py", ".sh", ".msg"}}
        expected_sources[resource["model"]] = context.development["source_hashes"][resource["model"]]
        require(snapshot == expected_sources, "Safety actual saved source/model snapshot differs")
        exits = artifacts["process_exit_codes"][1]
        require({"gazebo", "agent", "px4", "bag", "monitor", "ros"} <= exits.keys()
                and all(type(code) is int and code in ({0, -2} if process == "agent" else {0}) for process,code in exits.items()),
                "Safety owned child process failed or remains running; only owned agent SIGINT -2 is allowed")
        parameters = artifacts["runtime_parameters"][1]
        node_checks = {
            "uav_tracking_detection":{"navigation_enabled":True, "depth_max_age_s":.02},
            "uav_tracking_state_estimator":{"target_mode":expected["target_mode"], "association_mode":expected["association_mode"],
                "max_observation_age_s":.6, "max_prediction_duration_s":.75, "mahalanobis_gate":9.21, "navigation_enabled":True,
                "propagate_vehicle_uncertainty":True},
            "uav_tracking_controller":{"state_topic":"/tracking/navigation_state", "desired_height_m":2., "prediction_timeout_s":.75},
            "uav_tracking_px4_adapter":{"use_sim_time":True, "odometry_timestamp_mode":"source_sim", "odometry_source_max_age_s":.5,
                "odometry_source_max_future_s":.05, "vehicle_odometry_topic":"/fmu/out/vehicle_odometry", "vehicle_odom_topic":"/vehicle/odometry"},
            "uav_tracking_flight_supervisor":{"takeoff_mode":"px4_native", "status_timestamp_mode":"source_sim",
                "status_source_max_age_s":1., "status_source_max_future_s":.05, "status_timeout_s":10.}}
        require(all(parameters.get(node, {}).get("ros__parameters", {}).get(key) == value
                    for node, values in node_checks.items() for key, value in values.items()), "Actual safety runtime YAML safety contract differs")
        executions = slot.get("executions", {})
        require(set(executions) == {"flight", "source_clock", "native_startup", "specialized", "terminal_speed"}, "Safety command execution ledger incomplete")
        _, flight_end = validate_execution(executions["flight"])
        flight_argv = executions["flight"]["argv"]
        require(flight_argv == registered["flight_argv"] and utc(executions["flight"]["started_utc"]) >= utc(registry["created_utc"]), "Safety actual flight differs from prospective registry")
        require(len(flight_argv) >= 3 and flight_argv[:3] == ["bash", str(dev_root/"scripts/run_research_session.sh"), str(dev_root/"scripts/run_stage1_trial.py")]
                and option(flight_argv,"--name") == directory.name and option(flight_argv,"--class") == cls
                and int(option(flight_argv,"--seed")) == 4 and option(flight_argv,"--target-mode") == expected["target_mode"]
                and option(flight_argv,"--scenario-kind") == expected["scenario_kind"]
                and "--occlusions" not in flight_argv and "--reselect-after-loss" not in flight_argv, "Safety flight invocation does not name original frozen trial/mode")
        for kind in ("source_clock", "native_startup", "specialized", "terminal_speed"):
            _, finished = validate_execution(executions[kind], after=flight_end)
            require(finished <= utc(facts["created_utc"]) <= utc(summary["created_utc"]), "Safety facts/summary predates actual evaluation")
        safety_command_contract(executions, artifacts, dev_root, directory, cls, case)
        require(bound(executions["terminal_speed"]["code_script"], json_data=False) == tail_path, "Executed safety audit script differs from prospective registry")
        for kind in ("source_clock", "native_startup"):
            spec = {"kind":kind, "script":"scripts/evaluate_px4_source_clock.py" if kind == "source_clock" else "scripts/evaluate_native_startup.py",
                    "report":str(artifacts[kind][0]), "evaluation_root":str(dev_root)}
            execution = {**executions[kind], "log":executions[kind]["log"]["path"]}
            require(runtime.v4.read_evaluation(spec, execution, context.core)["result"] == "PASS", "Independent safety source/native evaluation failed")
        trial = {"directory":str(directory), "world_source":f"ros2_ws/src/uav_tracking_bringup/worlds/stage2_flight_{cls}.sdf"}
        require(not runtime.v4.gazebo_rendering_evidence(directory, "llvmpipe")["errors"], "Safety renderer is not independently verified")
        require(not runtime.v4.magnetic_environment_evidence(context.development, trial)["errors"], "Safety magnetic runtime is not independently verified")
        # The existing helper locates its frozen classifier through lexical
        # root/results/trial. Resolving the results symlink loses that root.
        infra = runtime.v4.infrastructure_evidence(lexical_directory, [])
        require(infra.get("stop") is False, "Safety recording/infrastructure did not pass")
        specialized = artifacts["specialized"][1]
        require(specialized.get("result") == "PASS" and Path(specialized.get("inputs", {}).get("bag", "")).resolve() == directory/"rosbag", "Safety specialty report not bound to original recording")
        if case == "auto_unique_multi":
            require(specialized.get("schema_version") == 2 and specialized.get("source") == "OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY"
                    and specialized.get("target_class") == cls, "Actual unique-instance multiple-candidate report required")
            all_checks(specialized, AUTO_CHECKS, case)
        else:
            require(specialized.get("schema_version") == 1 and specialized.get("source") == "OFFLINE_STAGE2_SAFETY_EVALUATION"
                    and specialized.get("geometric_ambiguity_observed") is True
                    and specialized.get("configuration", {}).get("target_class") == cls
                    and specialized.get("configuration", {}).get("require_ambiguity") is True
                    and specialized.get("configuration", {}).get("terminal_expectation") == "hover", "Actual selected geometric ambiguity required")
            all_checks(specialized, LOCKED_CHECKS, case)
        speed = artifacts["terminal_speed"][1]
        require(speed.get("schema_version") == 1 and speed.get("result") == "PASS"
                and Path(speed.get("trial", "")).resolve() == directory, "Independent physical hover-speed supplement missing")
        all_checks(speed, SPEED_CHECKS, "terminal speed")
        require(speed["interval"]["end_s"] - speed["interval"]["start_s"] >= 5.2-1e-9, "Full original 5.2s hover tail required")
        final_clock = artifacts["recording_closure"][1]["observations"][-1]["last_clock_ns"]/1e9
        require(abs(speed["interval"]["end_s"] - final_clock) < 1e-9, "Hover-speed interval does not reach original exact recorded Clock")
    require(utc(summary["created_utc"]) <= min(context.registration_times[:2]), "Safety summary must precede formal protocol registration")
    context.safety_path = path


def windows_mount(path):
    value = str(path).replace("\\", "/")
    if value.startswith("//?/"):
        value = value[4:]
    require(re.match(r"^[A-Za-z]:/", value) is not None, "WSL VHD registry path must be on a local Windows drive")
    return "/mnt/" + value[0].lower() + value[2:]


class NativeStorage:
    """Never use the virtual /root free count as Windows physical capacity."""
    @staticmethod
    def powershell(script):
        executable = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        require(executable.is_file(), "Windows PowerShell is required to verify actual volume/VHD identities")
        script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); " + script
        result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=20, check=False)
        require(result.returncode == 0 and bool(result.stdout.strip()), "Windows volume/VHD query failed")
        return json.loads(result.stdout.lstrip("\ufeff"))

    def vhd_path(self, distribution):
        require(os.environ.get("WSL_DISTRO_NAME") == distribution and re.fullmatch(r"[A-Za-z0-9_.-]+", distribution), "Current WSL distribution differs")
        code = ("$x=@(Get-ChildItem -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Lxss' | "
                "ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } | "
                f"Where-Object {{ $_.DistributionName -eq '{distribution}' }}); "
                "if($x.Count -ne 1){exit 3}; $x | Select-Object DistributionName,BasePath,VhdFileName | ConvertTo-Json -Compress")
        result = self.powershell(code)
        require(result.get("DistributionName") == distribution, "WSL registry distribution differs")
        filename = result.get("VhdFileName") or "ext4.vhdx"
        require(isinstance(filename, str) and re.fullmatch(r"[A-Za-z0-9_.-]+\.vhdx", filename), "Unsupported VHD filename")
        return Path(windows_mount(result["BasePath"]) + "/" + filename).resolve(strict=True)

    @staticmethod
    def filesystem(path):
        result = subprocess.run(["findmnt", "--json", "--target", str(path), "--output", "TARGET,SOURCE,FSTYPE"],
                                capture_output=True, text=True, timeout=10, check=False)
        require(result.returncode == 0, "Cannot verify actual mounted filesystem")
        entries = json.loads(result.stdout).get("filesystems", [])
        require(len(entries) == 1, "Ambiguous mounted filesystem")
        return entries[0]

    def volume(self, specification):
        mount = Path(specification["mount"])
        require(re.fullmatch(r"/mnt/[a-z]", str(mount)), "Capacity must query an actual /mnt/<drive> mount")
        actual = self.filesystem(mount)
        require(actual.get("target") == str(mount) and actual.get("fstype") in {"9p", "drvfs"}
                and str(actual.get("source", "")).upper().startswith(mount.name.upper() + ":"), "Capacity path is not the declared Windows drive mount")
        identity = self.powershell(f"Get-Volume -DriveLetter '{mount.name.upper()}' -ErrorAction Stop | Select-Object -ExpandProperty UniqueId | ConvertTo-Json -Compress")
        require(identity == specification["windows_volume_id"], "Actual Windows volume identity changed")
        available = os.statvfs(mount)
        return {"mount":str(mount), "windows_volume_id":identity, "free_bytes":available.f_bavail * available.f_frsize}

    def logical_free(self, root):
        require(self.filesystem(root).get("fstype") == "ext4", "Final source/build root must be on actual WSL ext4")
        available = os.statvfs(root)
        return available.f_bavail * available.f_frsize


def bytes_map(value, volumes, label):
    require(isinstance(value, dict) and set(value) == volumes, "Every actual physical volume must be explicit: " + label)
    return {key:integer(item, label+":"+key) for key,item in value.items()}


def trial_bytes(directory, declared_files):
    """Stat the bound accounting list, including bag sizes, without tree scans."""
    total = 0
    for relative, expected in declared_files.items():
        item = Path(relative)
        require(not item.is_absolute() and ".." not in item.parts, "Unsafe development accounting path")
        path = directory/item
        require(path.resolve(strict=True).is_relative_to(directory.resolve(strict=True)) and not path.is_symlink(), "Linked/outside accounting input")
        actual = path.stat().st_size
        require(actual == expected, "Recorded development accounting size changed")
        total += actual
    return total


def slot_rows(context, runtime):
    rows = {label:runtime.v4.read_slots(getattr(context, label), verify_artifacts=False) for label in ("core", "extension")}
    starts = []
    for label in rows:
        for row in rows[label].values():
            require(row["status"] != "RUNNING", "Original RUNNING attempt must be finalized/diagnosed without retry before guard admission")
            if row["status"] != "PENDING":
                stamp = utc(row.get("started_utc") or row.get("started", {}).get("started_utc"))
                starts.append(stamp)
    return rows, starts


def validate_storage(manifest, context, runtime, rows, backend):
    storage = manifest["storage"]
    specifications = storage["volumes"]
    require(isinstance(specifications, list) and bool(specifications), "Actual physical volume specifications required")
    volumes = {item["id"] for item in specifications}
    require(len(volumes) == len(specifications), "Duplicate physical volume ID")
    measurements = {item["id"]:backend.volume(item) for item in specifications}
    require(len({item["windows_volume_id"] for item in measurements.values()}) == len(volumes), "Same Windows volume declared twice; aggregate it once")
    mounts = {item["id"]:Path(item["mount"]).resolve(strict=True) for item in specifications}
    results = Path(context.core["results_root"]).resolve(strict=True)
    require(results == (context.root/"results").resolve(strict=True)
            and results == Path(context.extension["results_root"]).resolve(strict=True), "Actual results symlink/storage changed")
    results_volume = storage["results_volume"]
    require(results_volume in volumes and results.is_relative_to(mounts[results_volume]), "Results path is outside its declared physical volume")
    vhd = storage["vhd_host"]
    require(vhd["volume"] in volumes and Path(vhd["path"]).resolve(strict=True) == backend.vhd_path(vhd["distribution"])
            and Path(vhd["path"]).resolve().is_relative_to(mounts[vhd["volume"]]), "Actual registry-backed VHD host volume/path differs")
    require(volumes == {results_volume, vhd["volume"]}, "Declare exactly the actual results and VHD host volumes")
    peak = bytes_map(storage["temporary_peak_bytes"], volumes, "temporary peak")
    rule = storage["temporary_bound_rule"]
    require(rule.get("revision") == "three_raw_two_compressed_plus_margin_v1" and bool(rule.get("basis")),
            "Explicit conservative archive-derived temporary bound required; do not invent a peak measurement")
    margins = bytes_map(rule["extra_bytes_by_volume"], volumes, "temporary bound margin")
    for name in ("raw_growth_factor", "compressed_growth_factor"):
        require(type(rule.get(name)) in {int,float} and math.isfinite(rule[name]) and rule[name] >= 1., "Temporary growth factor must be explicit and >=1")
    derived_peak = {key:0 for key in volumes}
    reserve = {key:max(MIN_RESERVE, peak[key]) for key in volumes}
    fixed = {key:0 for key in volumes}
    require(set(storage["delivery_reservations"]) == set(DELIVERIES), "All remaining delivery/log budgets must be explicit")
    for purpose, entry in storage["delivery_reservations"].items():
        values = bytes_map(entry["bytes_by_volume"], volumes, purpose)
        require(sum(values.values()) > 0 and isinstance(entry.get("basis"), str) and bool(entry["basis"].strip()), "Unbudgeted delivery purpose: " + purpose)
        for key in volumes:
            fixed[key] += values[key]
    extra = bytes_map(storage["additional_remaining_bytes"], volumes, "remaining build/other budget")
    for key in volumes:
        fixed[key] += extra[key]
    cells, budgets = storage["cells"], {}
    expected_cells = {(label, cls, group) for label, groups in (("core", GROUPS), ("extension", CONDITIONS)) for cls in CLASSES for group in groups}
    require(len(cells) == 28 and {(c["matrix"], c["target_class"], c["condition"]) for c in cells} == expected_cells,
            "Complete 28-cell development-based budget required for all 280 slots")
    # Load each immutable development plan once; never multiply its reads by cells.
    plan_cache, development_cells = {}, {}
    for label in ("core", "extension"):
        gate = context.core["development_probe_gate"]["evidence"] if label == "core" else context.core["extension_protocol_binding"]["protocol"]["development_readiness"]["evidence"]
        for reference in gate["probe_slots"]:
            if reference["plan_path"] not in plan_cache:
                plan_cache[reference["plan_path"]] = runtime.v4.load(reference["plan_path"])
            plan = plan_cache[reference["plan_path"]]
            trial = next(t for t in plan["trials"] if t["id"] == reference["slot_id"])
            group = trial["group"] if label == "core" else trial["extension_condition"]
            key = (label, trial["target_class"], group)
            require(key not in development_cells, "Duplicate budget development cell")
            development_cells[key] = trial
    pending = {key:0 for key in volumes}
    full = {key:0 for key in volumes}
    for cell in cells:
        key = (cell["matrix"], cell["target_class"], cell["condition"])
        values = bytes_map(cell["persistent_bytes_by_volume"], volumes, ":".join(key))
        require(isinstance(cell.get("basis"), str) and bool(cell["basis"].strip()), "Explicit per-cell growth allowance/basis required")
        _, sample = bound(cell["development_size_evidence"])
        matched = development_cells.get(key)
        require(matched is not None and sample.get("trial") == matched["directory"], "Budget sample does not name the actual registered development cell")
        observed = integer(sample.get("total_trial_bytes"), "development size", minimum=1)
        require(sample.get("scope") == "FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE" and isinstance(sample.get("files"), dict)
                and observed == sum(integer(value, "recorded file size") for value in sample["files"].values()), "Incomplete actual development size evidence")
        actual_bytes = trial_bytes(Path(matched["directory"]), sample["files"])
        require(values[results_volume] >= max(observed, actual_bytes), "Persistent budget is below actual complete development recording")
        archive_path, archive = bound(cell["archive_evidence"])
        directory = Path(matched["directory"])
        require(archive_path == (directory/"bag_integrity.json").resolve() and archive.get("status") == "PASS"
                and archive.get("policy") == "ext4_sqlite_close_standard_zstd_verified_native_read"
                and archive.get("raw_validation", {}).get("status") == "PASS"
                and archive.get("native_reader_validation", {}).get("full_stream_read") is True, "Actual development archive sizes required")
        compressed = archive.get("compressed_files", [])
        require(bool(compressed) and len({item["path"] for item in compressed}) == len(compressed), "Archive size evidence is empty/duplicated")
        raw_bytes = sum(integer(item.get("raw_bytes"), "original raw SQLite bytes", minimum=1) for item in compressed)
        compressed_bytes = sum(integer(item.get("bytes"), "compressed SQLite bytes", minimum=1) for item in compressed)
        raw_files = archive["raw_validation"].get("files", [])
        require(raw_bytes == sum(integer(item.get("bytes"), "raw archive file bytes", minimum=1) for item in raw_files), "Original raw/compressed size correspondence differs")
        for item in compressed:
            relative = Path(item["path"])
            require(not relative.is_absolute() and ".." not in relative.parts and (directory/"rosbag"/relative).is_file()
                    and (directory/"rosbag"/relative).stat().st_size == item["bytes"], "Original compressed size changed; no bag hashing performed")
        derived = 3 * math.ceil(raw_bytes * rule["raw_growth_factor"]) + 2 * math.ceil(compressed_bytes * rule["compressed_growth_factor"])
        for volume in volumes:
            derived_peak[volume] = max(derived_peak[volume], derived + margins[volume])
        budgets[key] = values
        plan = getattr(context, key[0])
        matching = [trial for trial in plan["trials"] if trial["target_class"] == key[1]
                    and (trial["group"] if key[0] == "core" else trial["extension_condition"]) == key[2]]
        require(len(matching) == 10, "Per-cell scheduled denominator differs from ten")
        unattempted = sum(rows[key[0]][trial["id"]]["status"] == "PENDING" for trial in matching)
        for volume in volumes:
            full[volume] += 10 * values[volume]
            pending[volume] += unattempted * values[volume]
    capacity = {}
    for volume in volumes:
        require(peak[volume] >= derived_peak[volume], "Declared temporary peak is below the conservative actual-archive-derived bound")
        required = pending[volume] + fixed[volume] + reserve[volume]
        free = integer(measurements[volume]["free_bytes"], "physical free")
        require(free >= required, f"Insufficient physical volume {volume}: free={free}, required={required}; no slot started")
        capacity[volume] = {**measurements[volume], "full_280_persistent_bytes":full[volume], "unattempted_persistent_bytes":pending[volume],
                            "remaining_build_delivery_bytes":fixed[volume], "temporary_reserve_bytes":reserve[volume],
                            "derived_temporary_bound_bytes":derived_peak[volume], "required_bytes":required}
    logical_free = backend.logical_free(context.root)
    require(logical_free >= pending[vhd["volume"]] + fixed[vhd["volume"]] + reserve[vhd["volume"]],
            "Insufficient ext4 logical space in addition to physical host gate")
    return {"volumes":capacity, "ext4_logical_free_bytes":logical_free,
            "scheduled_slots":280, "pending_slots":sum(row["status"] == "PENDING" for matrix in rows.values() for row in matrix.values())}


def validate_resolution(binding, plan, rows):
    blocked = {row["record_sha256"] for row in rows.values() if row.get("infrastructure_stop")}
    if not blocked:
        require(binding is None, "Resolution supplied for a plan with no infrastructure stop")
        return None
    require(binding is not None, "Original infrastructure stop needs a separately bound diagnosis; no retry")
    path, report = bound(binding)
    require(report.get("result") == "PASS" and set(report.get("resolved_record_sha256", [])) == blocked
            and report.get("plan_sha256") == plan["plan_sha256"], "Infrastructure resolution does not bind every original stopped record")
    require(bool(report.get("evidence")), "Actual infrastructure diagnosis evidence required")
    for artifact in report["evidence"]:
        bound(artifact, json_data=False)
    require(utc(report["created_utc"]) <= now()
            and all(utc(report["created_utc"]) > utc(row["finished_utc"]) for row in rows.values() if row.get("infrastructure_stop")),
            "Infrastructure diagnosis precedes failure")
    return path


def validate_initial(manifest, context, rows, starts, state):
    initial_path = state/"initial_admission.json"
    require(all(stamp > utc(manifest["created_utc"]) and stamp > max(context.registration_times) for stamp in starts),
            "A formal flight preceded the complete admission/three registrations")
    if initial_path.exists():
        initial = load(initial_path)
        require(initial.get("kind") == "RELIABILITY_V4_INITIAL_FULL280_ADMISSION" and initial.get("receipt_sha256") == sealed(initial, "receipt_sha256")
                and initial.get("manifest_sha256") == manifest["manifest_sha256"]
                and initial.get("tool") == manifest["tool"] and initial.get("initial_pending_slots") == 280,
                "Original complete-280 admission receipt changed or belongs to another manifest/tool")
        require(not starts or utc(initial["created_utc"]) <= min(starts), "First capacity admission followed first flight")
    else:
        require(not starts and all(row["status"] == "PENDING" for matrix in rows.values() for row in matrix.values()),
                "Cannot retrofit a first full-280 budget after any formal attempt")


def check(manifest_path, *, backend=None, resolutions=None, runtime_loader=load_runtime):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = load(manifest_path)
    require(manifest.get("schema_version") == 1 and manifest.get("kind") == "RELIABILITY_V4_FORMAL_ADMISSION"
            and manifest.get("manifest_sha256") == sealed(manifest, "manifest_sha256"), "Missing/changed sealed admission manifest")
    tool = bound(manifest["tool"], json_data=False)
    require(tool == Path(__file__).resolve(), "Admission binds another guard executable")
    context = read_plans(manifest)
    state = Path(manifest["state_directory"]).resolve()
    require(state.is_relative_to(Path(context.core["results_root"]).resolve()) and state != Path(context.core["results_root"]).resolve(),
            "Independent guard state must be in final results storage")
    require(not any(state.is_relative_to(Path(trial["directory"]).resolve()) for plan in (context.core, context.extension) for trial in plan["trials"]),
            "Guard state must not modify a trial artifact tree")
    runtime = runtime_loader(context.root, context.core)
    validate_registrations(manifest, context, runtime)
    validate_development(manifest, context, runtime)
    validate_safety(manifest, context, runtime)
    rows, starts = slot_rows(context, runtime)
    validate_initial(manifest, context, rows, starts, state)
    resolution_paths = {label:validate_resolution((resolutions or {}).get(label), getattr(context,label), rows[label]) for label in rows}
    capacity = validate_storage(manifest, context, runtime, rows, backend or NativeStorage())
    # Core first. A terminal algorithm FAIL is retained, not automatically retried.
    label = next((name for name in ("core", "extension") if any(row["status"] == "PENDING" for row in rows[name].values())), None)
    trial = next((t for t in getattr(context,label)["trials"] if rows[label][t["id"]]["status"] == "PENDING"), None) if label else None
    command = None
    if label:
        command = ["bash", str(context.root/"scripts/run_research_session.sh"), str(context.root/"scripts/run_reliability_v4.py"),
                   "run", "--plan", str(getattr(context,label+"_path")), "--max-new-trials", "1"]
        if resolution_paths[label]:
            command += ["--infrastructure-resolution", str(resolution_paths[label])]
    report = {"schema_version":1, "kind":"RELIABILITY_V4_GUARD_ADMISSION_CHECK", "result":"PASS", "created_utc":now().isoformat(),
              "manifest":file_binding(manifest_path), "manifest_sha256":manifest["manifest_sha256"], "tool":manifest["tool"],
              "next_matrix":label, "next_slot_id":trial["id"] if trial else None, "capacity":capacity, "command":command,
              "claim_boundary":"Admission only; no flight, engineering outcome, retry or formal completion is implied."}
    return SimpleNamespace(manifest=manifest, context=context, runtime=runtime, rows=rows, state=state, report=report)


@contextmanager
def guard_lock():
    require(os.name == "posix", "Actual execution requires Linux/WSL")
    import fcntl
    with Path("/tmp/uav_tracking_reliability_v4_guard.lock").open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refusal("Another formal admission guard owns the execution window") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def execute_one(manifest_path, *, backend=None, resolutions=None, command_runner=subprocess.run, checker=check):
    with guard_lock():
        admission = checker(manifest_path, backend=backend, resolutions=resolutions)
        report = admission.report
        if report["command"] is None:
            return {**report, "execution":"NO_PENDING_SLOTS", "started_this_invocation":0}
        # A refused check above creates no state, runner process or started marker.
        admission.state.mkdir(parents=True, exist_ok=True)
        initial = admission.state/"initial_admission.json"
        if not initial.exists():
            data = {"schema_version":1, "kind":"RELIABILITY_V4_INITIAL_FULL280_ADMISSION", "created_utc":now().isoformat(),
                    "manifest_sha256":admission.manifest["manifest_sha256"], "tool":admission.manifest["tool"],
                    "initial_pending_slots":report["capacity"]["pending_slots"], "capacity":report["capacity"]}
            require(data["initial_pending_slots"] == 280, "First admission must budget every one of 280 unattempted slots")
            data["receipt_sha256"] = sealed(data, "receipt_sha256")
            write_new(initial, data)
        invocation = admission.state/(now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex)
        invocation.mkdir(exist_ok=False)
        write_new(invocation/"admission.json", report)
        code, error = None, None
        try:
            with (invocation/"runner.log").open("x", encoding="utf-8") as output:
                result = command_runner(report["command"], cwd=admission.context.root, stdout=output, stderr=subprocess.STDOUT, check=False)
                code = result.returncode
        except BaseException as exception:
            error = type(exception).__name__ + ": " + str(exception)
        plan = getattr(admission.context, report["next_matrix"])
        try:
            after = admission.runtime.v4.read_slots(plan, verify_artifacts=False)
        except (OSError, ValueError, KeyError, TypeError) as exception:
            outcome = {"result":"STOP", "error":"Post-run immutable record audit failed: "+str(exception), "returncode":code,
                       "slot_id":report["next_slot_id"], "runner_log":file_binding(invocation/"runner.log")}
            write_new(invocation/"outcome.json", outcome)
            return outcome
        before = admission.rows[report["next_matrix"]]
        changed = [key for key in before if before[key]["status"] == "PENDING" and after[key]["status"] != "PENDING"]
        expected_change = changed == [report["next_slot_id"]]
        outcome = {"schema_version":1, "kind":"RELIABILITY_V4_GUARD_SINGLE_INVOCATION", "created_utc":now().isoformat(),
                   "result":"COMPLETED" if code == 0 and error is None and expected_change else "STOP", "returncode":code, "error":error,
                   "slot_id":report["next_slot_id"], "started_this_invocation":len(changed),
                   "preserved_status":after[report["next_slot_id"]]["status"], "runner_log":file_binding(invocation/"runner.log"),
                   "admission":file_binding(invocation/"admission.json"), "next_action":"Recheck all prerequisites and current physical capacity before any next PENDING slot; never retry this slot."}
        if not expected_change:
            outcome["error"] = "Frozen runner did not consume exactly the one admitted PENDING slot; retain all records"
        if outcome["preserved_status"] == "RUNNING" or after[report["next_slot_id"]].get("infrastructure_stop") is True:
            outcome["result"] = "STOP"
        updated_rows = {**admission.rows, report["next_matrix"]:after}
        try:
            outcome["capacity_after"] = validate_storage(admission.manifest, admission.context, admission.runtime,
                                                          updated_rows, backend or NativeStorage())
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exception:
            outcome["capacity_after"] = {"result":"REFUSED", "reason":str(exception)}
            outcome["result"] = "STOP"
        write_new(invocation/"outcome.json", outcome)
        return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "run-one", "storage-probe"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Exclusive new check receipt; never a replacement")
    parser.add_argument("--distribution", help="storage-probe only: current WSL distribution name")
    parser.add_argument("--mount", action="append", help="storage-probe only: actual /mnt/<drive>; repeat for distinct volumes")
    for label in ("core", "extension"):
        parser.add_argument("--"+label+"-resolution", type=Path)
        parser.add_argument("--"+label+"-resolution-sha256")
    args = parser.parse_args(argv)
    try:
        if args.action == "storage-probe":
            require(args.manifest is None and args.distribution is not None and bool(args.mount), "storage-probe requires distribution/mounts, no formal manifest")
            backend = NativeStorage()
            volumes = []
            for mount in args.mount:
                require(re.fullmatch(r"/mnt/[a-z]", mount), "Storage inventory requires an actual Windows drive mount")
                identity = backend.powershell(f"Get-Volume -DriveLetter '{mount[-1].upper()}' -ErrorAction Stop | Select-Object -ExpandProperty UniqueId | ConvertTo-Json -Compress")
                volumes.append(backend.volume({"mount":mount,"windows_volume_id":identity}))
            result = {"schema_version":1, "kind":"RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY", "created_utc":now().isoformat(),
                      "evidence_scope":"METADATA_ONLY_NOT_FORMAL_ADMISSION", "volumes":volumes,
                      "vhd_host":{"distribution":args.distribution,"path":str(backend.vhd_path(args.distribution))}}
            if args.output:
                write_new(args.output,result)
            print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
            return 0
        require(args.manifest is not None and args.distribution is None and args.mount is None, "Formal check/run-one requires manifest; storage inventory options are separate")
        resolutions = {}
        for label in ("core", "extension"):
            path, digest = getattr(args,label+"_resolution"), getattr(args,label+"_resolution_sha256")
            require((path is None) == (digest is None), "Resolution path and SHA256 must be supplied together")
            if path:
                resolutions[label] = {"path":str(path.resolve(strict=True)), "sha256":digest}
        if args.action == "run-one":
            require(args.output is None, "run-one writes its own exclusive state receipts")
            result = execute_one(args.manifest, resolutions=resolutions)
        else:
            result = check(args.manifest, resolutions=resolutions).report
            if args.output:
                write_new(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if result.get("result") == "STOP" else 0
    except (OSError, ValueError, KeyError, TypeError, ImportError, StopIteration, subprocess.SubprocessError) as error:
        print(json.dumps({"result":"REFUSED", "error":type(error).__name__+": "+str(error), "new_slot_authorized":False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
