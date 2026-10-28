"""Freeze and run independent v4 engineering slots, once each, serially.

Plan/status and fixture tests use no ROS. Actual run is Linux-only and invokes
the frozen ROS environment wrapper. This script never changes a v3 ledger.
An evidence-complete navigation report is not an engineering PASS by itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("person", "car")
FORMAL_SEEDS = tuple(range(1000, 1010))
GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint",
          "stage3_active", "stage3_multi_active")
TERMINAL = {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING", "INFRASTRUCTURE_ERROR", "INTERRUPTED"}
PROTOCOL_PATH = "planning/reliability-v4-preregistration.json"
MAGNETIC_RUNTIME_PATH = "config/px4_magnetic_runtime.json"
MAGNETIC_CONTRACT = "gazebo_enu_flu_to_frd_v1"
SOURCE_CLOCK_HELPERS = ("scripts/evaluate_stage1_flight.py", *(
    "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/" + name
    for name in ("adapter_node.py", "source_clock.py", "frame_guard.py")))
HASH_FOLDERS = ("scripts", "uav_tracking", "ros2_ws/src", "config", "launch", "models", "patches")
HASH_SUFFIXES = {".py", ".sh", ".yaml", ".yml", ".sdf", ".msg", ".xml", ".config", ".cfg", ".txt",
                 ".toml", ".json", ".obj", ".dae", ".mtl", ".stl", ".mesh", ".material", ".png", ".jpg", ".pt", ".urdf", ".patch", ".gitattributes"}
PROBE_CHECKS = ("source_clock_independently_passed", "native_startup_independently_passed", "magnetic_runtime_and_loaded_libraries_verified",
                "base_link_navigation_performance_passed", "full_task_physical_identity_passed",
                "gimbal_feedback_passed", "original_safety_gates_preserved")
NATIVE_STARTUP_CHECKS = ("configuration_registered", "startup_parameter_values", "native_takeoff_command",
                       "command_sequence", "px4_mode_sequence", "pre_offboard_ground_readiness",
                       "handoff_readiness_and_settle", "visual_task_after_handoff", "full_recording_coverage")
OFFLINE_HELPERS = {"scripts/extract_research_recording.py", "uav_tracking/research_dynamics.py",
                   "uav_tracking/research_labels.py", "uav_tracking/research_metrics.py", "uav_tracking/stage2_identity.py"}
REPORT_PROVENANCE_HELPERS = {
    "navigation":("scripts/evaluate_stage1_flight.py", "scripts/evaluate_online_state_accuracy.py",
                  "scripts/extract_research_recording.py", "uav_tracking/research_dynamics.py", "uav_tracking/research_labels.py"),
    "physical_identity":("scripts/evaluate_stage1_flight.py", "scripts/extract_research_recording.py",
                         "uav_tracking/research_labels.py", "uav_tracking/research_metrics.py", "uav_tracking/stage2_identity.py"),
    "source_clock":SOURCE_CLOCK_HELPERS,
    "native_startup":("scripts/evaluate_stage1_flight.py",),
}


def offline_source_hashes(hashes):
    return {key:value for key,value in hashes.items()
            if key.startswith("scripts/evaluate_") or key in OFFLINE_HELPERS}


def flight_source_hashes(hashes):
    offline = offline_source_hashes(hashes)
    return {key:value for key,value in hashes.items()
            if key not in offline and key != "scripts/run_reliability_v4.py"}


def finite_number(value, name, *, minimum=None, maximum=None):
    if (type(value) not in {int, float} or not math.isfinite(value)
            or minimum is not None and value < minimum or maximum is not None and value > maximum):
        raise ValueError("Invalid finite numeric field: " + name)
    return value


def count(value, name, *, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or maximum is not None and value > maximum:
        raise ValueError("Invalid integer count: " + name)
    return value


def ratio(value, numerator, denominator, name):
    finite_number(value, name, minimum=0., maximum=1.)
    if not math.isclose(value, numerator / denominator, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Coverage/count disagreement: " + name)
    return value


def validate_navigation_gates(gates):
    """Validate registration, without choosing any performance threshold."""
    if not isinstance(gates, dict) or gates.get("status") != "REGISTERED":
        raise ValueError("Navigation performance gates must be REGISTERED before formal freeze/execution")
    for key in ("maximum_base_link_distance_rmse_m", "maximum_base_link_height_rmse_m"):
        finite_number(gates.get(key), key, minimum=0.)
    for key in ("minimum_valid_state_coverage", "minimum_truth_coverage", "minimum_physical_identity_coverage"):
        finite_number(gates.get(key), key, minimum=0., maximum=1.)
    if type(gates.get("require_final_window_settled")) is not bool:
        raise ValueError("require_final_window_settled must be an explicit boolean")


def required_evaluators(trial):
    kinds = {"source_clock", "native_startup", "surface_flight", "navigation"}
    if trial.get("group") in {"stage2_crossing", "stage3_multi_active"}:
        kinds.update(("selected_target_safety", "physical_identity"))
    if trial.get("group", "").startswith("stage3_"):
        kinds.add("gimbal")
    return kinds


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value, excluded=()):
    value = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"),
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token)))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: " + str(path))
    return value


def write_new(path, value):
    """Exclusive creation; existing evidence is never replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def source_hashes(root):
    root = Path(root)
    paths = []
    for folder in HASH_FOLDERS:
        for path in (root / folder).rglob("*"):
            if (path.is_file() and path.suffix.lower() in HASH_SUFFIXES
                    and not any(part in {"build", "install", "log", "__pycache__", ".git"}
                                or part.endswith(".egg-info") for part in path.relative_to(root).parts)):
                paths.append(path)
    paths.extend(path for path in root.iterdir() if path.is_file() and path.suffix in {".py", ".toml", ".cfg", ".xml", ".txt"})
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted(set(paths))}


def validate_protocol(protocol):
    exact = {"classes": list(CLASSES), "groups": list(GROUPS), "seeds": list(FORMAL_SEEDS),
             "formal_trial_count": 120, "duration_s": 45., "short_occlusion_s": .2,
             "long_occlusion_s": 3., "real_time_factor": .5, "max_inference_rate_hz": 10.,
             "monitor_tick_s": .02, "control_reference": "ground_footprint", "desired_height_m": 2.,
             "magnetic_environment": "gazebo_enu", "magnetic_runtime_manifest": MAGNETIC_RUNTIME_PATH,
             "propagate_vehicle_uncertainty": True,
             "px4_time_mode": "source_sim",
             "takeoff_mode": "px4_native",
             "takeoff_height_m": 3., "estimator_method": "adaptive_kf", "condition": "clean",
             "motion_profile_kind": "standard", "occlusions": True, "explicit_reselection": True,
             "vehicle_control_point": "base_link", "vehicle_control_point_offset_flu_m": [0., 0., .24]}
    for key, expected in exact.items():
        if protocol.get(key) != expected:
            raise ValueError("v4 engineering protocol differs at " + key)
    if protocol.get("magnetic_library_registration") not in {
            "config/gazebo_magnetic_runtime.json", "config/gazebo_magnetic_runtime_humble22.json"}:
        raise ValueError("An explicit per-environment Gazebo magnetic library registration is required")
    expected_gates = {"max_observation_age_s": .6, "max_prediction_duration_s": .75,
                      "mahalanobis_gate": 9.21, "lost_requires_explicit_reselection": True,
                      "runtime_ground_truth_forbidden": True}
    if protocol.get("safety_gates") != expected_gates:
        raise ValueError("The original safety gates cannot be relaxed")
    resources = protocol.get("resources", {})
    for cls, model, size, threads, distance in (("person", "yolo11n.pt", 320, 2, 5.), ("car", "yolo11s.pt", 640, 4, 9.)):
        if resources.get(cls) != {"model": "models/" + model, "inference_image_size": size,
                                  "inference_threads": threads, "desired_distance_m": distance}:
            raise ValueError("Frozen resource configuration differs for " + cls)


def wrapper_command(root, script, *args):
    return ["bash", str(root / "scripts/run_research_session.sh"), str(root / "scripts" / script), *map(str, args)]


def trial_spec(root, protocol, prefix, cls, group, seed, wall_timeout):
    multi = group in {"stage2_crossing", "stage3_multi_active"}
    stage = 1 if group.startswith("stage1_") else 2 if group == "stage2_crossing" else 3
    setting = protocol["resources"][cls]
    identifier = f"{cls}_{group}_seed{seed:03d}"
    spec = {"id": identifier, "name": f"{prefix}_{identifier}", "group": group, "target_class": cls,
            "seed": seed, "gazebo_seed": seed + 1, "stage": stage, "multi_target": group == "stage3_multi_active",
            "target_mode": "locked_target" if multi else "auto_unique", "association_mode": "hybrid_3d" if multi else "legacy",
            "initial_select": "middle" if multi else "none", "initial_min_candidates": 3 if multi else 2,
            "command_mode": "position" if group == "stage1_position" else "velocity",
            "takeoff_mode": "px4_native",
            "gimbal_mode": "active" if group in {"stage3_active", "stage3_multi_active"} else "midpoint",
            "scenario_kind": "crossing" if multi else "parallel", "duration_s": 45.,
            "speed_mps": random.Random(seed).uniform(.45, .55), "wall_timeout_s": wall_timeout,
            **deepcopy(setting)}
    command = wrapper_command(root, "run_stage1_trial.py", "--name", spec["name"], "--class", cls,
        "--stage", stage, "--seed", seed, "--speed-mps", repr(spec["speed_mps"]),
        "--duration", "45.0", "--condition", "clean", "--estimator-method", "adaptive_kf",
        "--command-mode", spec["command_mode"], "--target-mode", spec["target_mode"],
        "--association-mode", spec["association_mode"], "--initial-select", spec["initial_select"],
        "--initial-min-candidates", spec["initial_min_candidates"], "--gimbal-mode", spec["gimbal_mode"],
        "--scenario-kind", spec["scenario_kind"], "--real-time-factor", "0.5", "--max-inference-rate-hz", "10.0",
        "--monitor-tick-s", "0.02", "--control-reference", "ground_footprint", "--motion-profile-kind", "standard",
        "--model-path", root / setting["model"], "--inference-image-size", setting["inference_image_size"],
        "--inference-threads", setting["inference_threads"], "--desired-distance-m", setting["desired_distance_m"],
        "--takeoff-height-m", "3.0", "--takeoff-mode", "px4_native", "--wall-timeout", wall_timeout, "--render-backend", "egl",
        "--magnetic-environment", "gazebo_enu", "--magnetic-runtime-manifest", root / MAGNETIC_RUNTIME_PATH,
        "--magnetic-library-registration", root / protocol["magnetic_library_registration"],
        "--propagate-vehicle-uncertainty",
        "--px4-time-mode", "source_sim",
        "--occlusions", "--short-occlusion-s", "0.2", "--reselect-after-loss")
    if spec["multi_target"]:
        command.append("--multi-target")
    spec["flight_command"] = command
    world_name = f"stage3_multi_{cls}.sdf" if spec["multi_target"] else f"stage{stage}_flight_{cls}.sdf"
    spec["world_source"] = "ros2_ws/src/uav_tracking_bringup/worlds/" + world_name
    directory = root / "results" / spec["name"]
    spec["directory"] = str(directory)
    common = [directory / "rosbag", "--target-class", cls, "--telemetry-jsonl", directory / "telemetry.jsonl",
              "--monitor-summary", directory / "summary.json"]
    evaluations = []

    def add(kind, script, args, filename, dependencies=()):
        report = directory / filename
        evaluations.append({"kind": kind, "command": wrapper_command(root, script, *args, "--output", report),
                            "report": str(report), "script": "scripts/" + script,
                            "available_at_freeze": (root / "scripts" / script).is_file(),
                            "dependencies": list(dependencies)})

    add("source_clock", "evaluate_px4_source_clock.py", [directory], "px4_source_clock_report.json")
    add("native_startup", "evaluate_native_startup.py", [directory], "native_startup_report.json")
    add("surface_flight", "evaluate_stage1_flight.py", [*common, "--desired-distance-m", setting["desired_distance_m"],
        "--desired-height-m", "2.0"], "flight_evaluation.json")
    if multi:
        add("selected_target_safety", "evaluate_stage2_flight.py", [*common, "--require-occlusions",
            "--terminal-expectation", "tracking"], "stage2_evaluation.json")
    if stage == 3:
        add("gimbal", "evaluate_stage3_gimbal.py", [directory / "rosbag", "--mode", spec["gimbal_mode"]], "gimbal_evaluation.json")
    if multi:
        add("physical_identity", "evaluate_physical_identity.py", [directory, "--target-class", cls], "physical_identity.json")
    nav_args = [directory, "--target-class", cls]
    if multi:
        nav_args += ["--physical-identity-report", directory / "physical_identity.json"]
    add("navigation", "evaluate_navigation_reference.py", nav_args, "navigation_reference_evaluation.json",
        ["physical_identity"] if multi else [])
    spec["evaluations"] = evaluations
    return spec


def verify_external_runtime(root, manifest_path):
    """Prospective live source/ELF check only; never used by retrospective audit."""
    manifest = load(manifest_path)
    if manifest.get("evidence_scope") == "ORCHESTRATION_FIXTURE_ONLY" or manifest.get("fixture_only"):
        raise ValueError("Fixture magnetic runtime is not real flight evidence")
    path = Path(root) / "scripts/prepare_px4_magnetic_compatibility.py"
    spec = importlib.util.spec_from_file_location("frozen_v4_magnetic_verifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_runtime_manifest(Path(manifest_path))


def freeze_magnetic_runtime(root, hashes):
    path = Path(root) / MAGNETIC_RUNTIME_PATH
    if MAGNETIC_RUNTIME_PATH not in hashes or not path.is_file():
        raise ValueError("Verified isolated PX4 runtime manifest is not yet available; no manifest is fabricated")
    manifest = verify_external_runtime(root, path)
    return {"manifest_path":str(path), "manifest_sha256":sha(path), "manifest":manifest,
            "evidence_scope":manifest.get("evidence_scope", "VERIFIED_ISOLATED_RUNTIME_ARTIFACT"),
            "claim_limit":"Frozen source/ELF provenance; actual per-trial startup log and physical flight remain separate evidence"}


def freeze_magnetic_libraries(root, protocol, hashes):
    relative = protocol["magnetic_library_registration"]
    path = Path(root) / relative
    if relative not in hashes or not path.is_file():
        raise ValueError("Per-environment audited Gazebo magnetic library registration is not yet available")
    registration = load(path)
    lookup = load(Path(root) / "config/gazebo_magnetic_reference.json")
    source = registration.get("source_registration", {})
    expected_keys = ("gazebo_sim_version", "gazebo_sim_commit", "gazebo_sim_source_sha256",
                     "gazebo_sensors_version", "gazebo_sensors_commit", "gazebo_sensors_source_sha256")
    default_source = {key:lookup.get(key) for key in expected_keys}
    variants = lookup.get("audited_source_variants", [default_source])
    if (not isinstance(variants, list) or not variants
            or any(not isinstance(variant, dict) or set(variant) != set(expected_keys)
                   or any(not variant[key] for key in expected_keys) for variant in variants)):
        raise ValueError("Frozen magnetic source-variant allowlist is malformed")
    if (registration.get("schema_version") != 1 or registration.get("status") != "AUDITED_INSTALLED_PACKAGES"
            or not registration.get("environment_id")
            or {key:source.get(key) for key in expected_keys} not in variants):
        raise ValueError("Magnetic library registration does not match frozen source versions")
    environment = registration.get("environment", {})
    ros = "humble" if relative.endswith("_humble22.json") else "jazzy"
    if (environment.get("ros_distro") != ros or environment.get("os_id") != "ubuntu"
            or environment.get("os_version") != ("22.04" if ros == "humble" else "24.04")):
        raise ValueError("Magnetic library registration belongs to a different named ROS/Ubuntu environment")
    libraries = registration.get("libraries", {})
    for kind in ("gazebo_sim", "gazebo_sensors"):
        item = libraries.get(kind, {})
        if (not isinstance(item.get("path"), str) or not item["path"].startswith("/")
                or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256", "")))
                or not item.get("package") or not item.get("package_version")
                or item.get("package_file_md5_matches") is not True):
            raise ValueError("Incomplete audited magnetic library registration: " + kind)
    provenance = registration.get("package_repository_provenance", {})
    if any(not provenance.get(key) for key in ("repository", "authentication", "evidence")):
        raise ValueError("Magnetic library registration needs repository/authentication evidence")
    return {"registration_path":str(path), "registration_sha256":sha(path), "registration":registration,
            "claim_limit":"Per-environment installed package registration; actual loaded process ELFs must match per trial"}


def make_plan(root, output, prefix, *, formal=False, seeds=None, groups=None, classes=None, wall_timeout=300., probe_gate=None):
    root = Path(root).resolve(strict=True)
    output = Path(output)
    output = output if output.is_absolute() else root / output
    output = output.resolve()
    if not output.is_relative_to((root / "results").resolve()) or output == (root / "results").resolve():
        raise ValueError("A new output subdirectory inside this frozen root's results is required")
    if not re.fullmatch(r"reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,70}", prefix):
        raise ValueError("A new reliability_v4_NAME prefix is required")
    if not math.isfinite(wall_timeout) or wall_timeout <= 0:
        raise ValueError("wall_timeout must be positive and finite")
    protocol = load(root / PROTOCOL_PATH)
    validate_protocol(protocol)
    seeds = (list(protocol["seeds"]) if formal else [0]) if seeds is None else list(seeds)
    groups = list(GROUPS) if groups is None else list(groups)
    classes = list(CLASSES) if classes is None else list(classes)
    if (not seeds or len(set(seeds)) != len(seeds)
            or any(type(seed) is not int or not 0 <= seed < 4294967295 for seed in seeds)):
        raise ValueError("Seeds must be unique nonnegative registered integers")
    if not groups or len(set(groups)) != len(groups) or set(groups) - set(GROUPS):
        raise ValueError("Unknown or duplicate v4 groups")
    if not classes or len(set(classes)) != len(classes) or set(classes) - set(CLASSES):
        raise ValueError("Unknown or duplicate target classes")
    if not formal and set(seeds) & set(protocol["seeds"]):
        raise ValueError("Held-out formal seeds cannot be consumed by a development probe")
    gate = None
    if formal:
        if seeds != protocol["seeds"] or groups != list(GROUPS) or classes != list(CLASSES):
            raise ValueError("Formal v4 must contain exactly 2 classes x 6 groups x registered held-out seeds 1000..1009")
        validate_navigation_gates(protocol.get("navigation_acceptance"))
        if probe_gate is None:
            raise ValueError("Formal freeze requires explicit completed development-probe gate evidence")
        path = Path(probe_gate).resolve(strict=True)
        evidence = load(path)
        checks = evidence.get("checks")
        if (evidence.get("schema_version") != 2 or evidence.get("result") != "PASS"
                or evidence.get("ready_for_formal_reliability_v4") is not True
                or not isinstance(checks, dict) or set(checks) != set(PROBE_CHECKS)
                or any(value is not True for value in checks.values())):
            raise ValueError("Development probe gate has not passed")
        gate = {"path": str(path), "sha256": sha(path), "evidence": evidence}
    hashes = source_hashes(root)
    for required in ("scripts/run_stage1_trial.py", "scripts/run_research_session.sh", "scripts/ros_python.sh",
                     "scripts/evaluate_stage1_flight.py", "uav_tracking/research_failures.py",
                     "scripts/configure_gazebo_magnetic_contract.py", "scripts/prepare_px4_magnetic_compatibility.py",
                     "scripts/capture_gazebo_magnetic_libraries.py",
                     "scripts/px4_stage1_startup.sh", "scripts/run_stage1_flight.sh",
                     "scripts/evaluate_native_startup.py",
                     "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py",
                     "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/startup_readiness.py",
                     "config/gazebo_magnetic_reference.json", "patches/px4/gazebo_enu_flu_to_frd.patch",
                     "scripts/evaluate_px4_source_clock.py", *SOURCE_CLOCK_HELPERS):
        if required not in hashes:
            raise ValueError("Missing required frozen source: " + required)
    magnetic_runtime = freeze_magnetic_runtime(root, hashes)
    magnetic_libraries = freeze_magnetic_libraries(root, protocol, hashes)
    for cls in classes:
        if protocol["resources"][cls]["model"] not in hashes:
            raise ValueError("Missing frozen model weight for " + cls)
    trials = [trial_spec(root, protocol, prefix, cls, group, seed, wall_timeout)
              for cls in classes for group in groups for seed in seeds]
    for trial in trials:
        if trial["world_source"] not in hashes:
            raise ValueError("Missing frozen world source: " + trial["world_source"])
    if formal and len(trials) != 120:
        raise ValueError("Formal denominator must be exactly 120")
    if output.exists() or any(Path(trial["directory"]).exists() for trial in trials):
        raise ValueError("Plan/output/trial artifacts already exist; old results cannot be reused")
    plan = {"schema_version": 1, "study_kind": "POST_REPAIR_ENGINEERING_VALIDATION", "mode": "FORMAL" if formal else "PROBE",
            "created_utc": utc_now(), "frozen_root": str(root), "results_root": str((root / "results").resolve()),
            "output": str(output), "prefix": prefix, "protocol": protocol, "protocol_sha256": sha(root / PROTOCOL_PATH),
            "source_hashes": hashes, "model_hashes": {key: value for key, value in hashes.items() if key.endswith(".pt")},
            "config_hashes": {key: value for key, value in hashes.items() if key.endswith((".yaml", ".yml", ".json", ".sdf", ".msg"))},
            "development_probe_gate": gate, "selected_classes": classes, "selected_groups": groups, "selected_seeds": seeds,
            "magnetic_runtime_binding": magnetic_runtime,
            "magnetic_library_binding": magnetic_libraries,
            "trial_timeout_s": wall_timeout + 360., "evaluation_timeout_s": 1800., "trials": trials}
    if formal:
        validate_probe_gate(plan)
    plan["plan_sha256"] = digest(plan, ("plan_sha256",))
    return plan


def validate_plan(plan, path=None):
    if plan.get("schema_version") != 1 or plan.get("study_kind") != "POST_REPAIR_ENGINEERING_VALIDATION":
        raise ValueError("Not a v4 engineering plan")
    if plan.get("plan_sha256") != digest(plan, ("plan_sha256",)):
        raise ValueError("Frozen plan digest changed; do not edit a registered plan")
    validate_protocol(plan["protocol"])
    binding = plan.get("magnetic_runtime_binding", {})
    if (binding.get("manifest_path") != str(Path(plan["frozen_root"]) / MAGNETIC_RUNTIME_PATH)
            or binding.get("manifest_sha256") != plan["source_hashes"].get(MAGNETIC_RUNTIME_PATH)
            or not isinstance(binding.get("manifest"), dict)):
        raise ValueError("Frozen isolated magnetic runtime binding is missing or invalid")
    libraries = plan.get("magnetic_library_binding", {})
    relative = plan["protocol"]["magnetic_library_registration"]
    if (libraries.get("registration_path") != str(Path(plan["frozen_root"]) / relative)
            or libraries.get("registration_sha256") != plan["source_hashes"].get(relative)
            or not isinstance(libraries.get("registration"), dict)):
        raise ValueError("Frozen per-environment magnetic library binding is missing or invalid")
    if path is not None and Path(path).resolve() != Path(plan["output"]) / "plan.json":
        raise ValueError("Plan was moved away from its frozen output path")
    root = Path(plan["frozen_root"])
    names = [trial["name"] for trial in plan["trials"]]
    if not names or len(names) != len(set(names)):
        raise ValueError("Duplicate or empty trial set")
    expected = [trial_spec(root, plan["protocol"], plan["prefix"], cls, group, seed,
                          plan["trials"][0]["wall_timeout_s"])
                for cls in plan["selected_classes"] for group in plan["selected_groups"] for seed in plan["selected_seeds"]]
    # Availability is frozen evidence. Never recompute it from a later tree.
    for original, regenerated in zip(plan["trials"], expected):
        for previous, current in zip(original["evaluations"], regenerated["evaluations"]):
            current["available_at_freeze"] = previous["available_at_freeze"]
    if expected != plan["trials"]:
        raise ValueError("Registered trial commands/configuration differ from the v4 protocol")
    if plan["mode"] == "FORMAL" and (len(names) != 120 or plan["selected_classes"] != list(CLASSES)
            or plan["selected_groups"] != list(GROUPS) or plan["selected_seeds"] != plan["protocol"]["seeds"]
            or not plan.get("development_probe_gate")):
        raise ValueError("Formal plan denominator or development gate is invalid")
    if plan["mode"] == "FORMAL":
        validate_navigation_gates(plan["protocol"].get("navigation_acceptance"))
        validate_probe_gate(plan)
    if plan["mode"] == "PROBE" and set(plan["selected_seeds"]) & set(plan["protocol"]["seeds"]):
        raise ValueError("Held-out formal seeds cannot be consumed by a development probe")


def verify_sources(plan):
    root = Path(plan["frozen_root"])
    if (source_hashes(root) != plan["source_hashes"] or sha(root / PROTOCOL_PATH) != plan["protocol_sha256"]
            or load(root / PROTOCOL_PATH) != plan["protocol"]):
        raise ValueError("Frozen source/model/configuration changed; keep this plan and create a new revision")
    if str((root / "results").resolve()) != plan["results_root"]:
        raise ValueError("Frozen results storage binding changed")
    current = verify_external_runtime(root, root / MAGNETIC_RUNTIME_PATH)
    if current != plan["magnetic_runtime_binding"]["manifest"]:
        raise ValueError("Isolated PX4 runtime changed after plan freeze")


def persist_plan(plan):
    validate_plan(plan)
    output = Path(plan["output"])
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "plan.json", plan)


@contextmanager
def run_lock(output):
    """Machine-wide OS lock, plus an output lock; never unlink held paths."""
    handles = []
    try:
        machine_lock = Path("/tmp") if os.name == "posix" else Path(tempfile.gettempdir())
        for path in (machine_lock / "uav_tracking_reliability_v4_sitl.lock", Path(output) / ".run.lock"):
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    if handle.seek(0, os.SEEK_END) == 0:
                        handle.write(b"0"); handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                handle.close()
                raise
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            if os.name == "nt":
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def simulation_processes():
    if os.name != "posix" or not Path("/proc").is_dir():
        raise RuntimeError("Actual simulation runs require Linux /proc process evidence")
    found = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            fields = (proc / "stat").read_text().rpartition(")")[2].split()
            argv = [token.decode(errors="replace") for token in (proc / "cmdline").read_bytes().split(b"\0") if token]
            if not argv or fields[0] == "Z" or int(proc.name) == os.getpid():
                continue
            names = [Path(token).name for token in argv[:3]]
            active = (any(name in {"px4", "MicroXRCEAgent", "gz-sim-server"} or name.startswith("gz-sim-") for name in names)
                      or any(name in {"run_stage1_trial.py", "stage1_flight_monitor.py"} for name in names)
                      or ("gz" in names and "sim" in argv)
                      or ("ros2" in names and ("launch" in argv or ("bag" in argv and "record" in argv)))
                      or any("/install/lib/uav_tracking_" in token for token in argv[:3]))
            if active:
                found.append({"pid": int(proc.name), "state": fields[0], "argv": argv})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return found


def execute_command(command, log, root, timeout):
    """The child trial owns normal process cleanup; outer faults stop the batch."""
    started = utc_now()
    with Path(log).open("x", encoding="utf-8") as handle:
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=handle,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
            return {"command": command, "returncode": process.returncode, "started_utc": started,
                    "finished_utc": utc_now(), "log": str(log), "error": None}
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            # SIGINT lets the trial's own finally stop its separately owned
            # recorder/ROS/PX4/Gazebo groups and flush the recording. Killing
            # the wrapper immediately would bypass precisely that cleanup.
            cleanup = []
            for sent, grace in ((signal.SIGINT, 240), (signal.SIGTERM, 30), (getattr(signal, "SIGKILL", signal.SIGTERM), 10)):
                if process.poll() is not None:
                    break
                process.send_signal(sent)
                cleanup.append({"signal": int(sent), "grace_s": grace})
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    continue
            return {"command": command, "returncode": process.poll(), "started_utc": started, "finished_utc": utc_now(),
                    "log": str(log), "error": type(error).__name__, "outer_cleanup_actions": cleanup}


def infrastructure_evidence(directory, attempts):
    # Bind qualification code to this plan's source tree, including when the
    # orchestrator was invoked with a different working directory.
    path = Path(directory).parent.parent / "uav_tracking/research_failures.py"
    spec = importlib.util.spec_from_file_location("frozen_v4_failure_classifier", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.classify_infrastructure_failure(directory, evaluator_attempts=attempts)


def runtime_configuration(plan, trial):
    """Check actual archived arguments/parameters, not only the command text."""
    directory = Path(trial["directory"])
    errors = []
    try:
        config = load(directory / "run_config.json")
        expected = {key: trial[key] for key in ("name", "target_class", "stage", "seed", "speed_mps", "command_mode", "takeoff_mode",
            "gimbal_mode", "target_mode", "association_mode", "initial_select", "initial_min_candidates", "scenario_kind",
            "multi_target", "inference_image_size", "inference_threads", "desired_distance_m")}
        expected.update(duration=45., control_reference="ground_footprint", real_time_factor=.5,
            max_inference_rate_hz=10., monitor_tick_s=.02, condition="clean", estimator_method="adaptive_kf",
            occlusions=True, reselect_after_loss=True, short_occlusion_s=.2,
            magnetic_environment="gazebo_enu", magnetic_runtime_manifest=str(Path(plan["frozen_root"]) / MAGNETIC_RUNTIME_PATH),
            magnetic_library_registration=str(Path(plan["frozen_root"]) / plan["protocol"]["magnetic_library_registration"]),
            px4_time_mode="source_sim", propagate_vehicle_uncertainty=True,
            model_path=str(Path(plan["frozen_root"]) / trial["model"]),
            vehicle_control_point_offset_flu_m=[0., 0., .24])
        errors.extend("run_config:" + key for key, value in expected.items() if config.get(key) != value)
        path = directory / "configuration/runtime_parameters.yaml"
        try:
            parameters = load(path)  # JSON is also valid YAML; useful to pure fixtures.
        except ValueError:
            import yaml
            parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected_parameters = {
            "uav_tracking_detection": {"navigation_enabled": True, "depth_max_age_s": .02,
                "model_path": expected["model_path"], "inference_image_size": trial["inference_image_size"],
                "inference_threads": trial["inference_threads"], "max_inference_rate_hz": 10.},
            "uav_tracking_state_estimator": {"navigation_enabled": True, "target_mode": trial["target_mode"],
                "propagate_vehicle_uncertainty": True,
                "association_mode": trial["association_mode"], "max_observation_age_s": .60,
                "max_prediction_duration_s": .75, "mahalanobis_gate": 9.21, "estimator_method": "adaptive_kf"},
            # command_mode is overridden by the frozen launch argument after
            # loading this YAML. The archived CLI above binds that override.
            "uav_tracking_controller": {"state_topic": "/tracking/navigation_state",
                "desired_distance_m": trial["desired_distance_m"], "desired_height_m": 2., "prediction_timeout_s": .75},
            "uav_tracking_px4_adapter": {"use_sim_time": True, "odometry_timestamp_mode": "source_sim",
                "odometry_source_max_age_s": .50, "odometry_source_max_future_s": .05,
                "vehicle_odometry_topic": "/fmu/out/vehicle_odometry", "vehicle_odom_topic": "/vehicle/odometry",
                "odometry_timing_topic": "/vehicle/odometry_timing"},
            "uav_tracking_flight_supervisor": {"takeoff_mode":"px4_native", "takeoff_height_m":3.,
                                               "auto_start":True, "simulation_only":True},
        }
        for node, values in expected_parameters.items():
            actual = parameters.get(node, {}).get("ros__parameters", {})
            errors.extend(f"runtime_parameters:{node}:{key}" for key, value in values.items() if actual.get(key) != value)
        magnetic = magnetic_environment_evidence(plan, trial)
        errors.extend(magnetic["errors"])
        return {"errors": errors, "arguments": expected, "magnetic_environment": magnetic,
                "run_config_sha256": sha(directory / "run_config.json"), "runtime_parameters_sha256": sha(path)}
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        return {"errors": [*errors, f"runtime_configuration_unreadable:{type(error).__name__}:{error}"]}


def magnetic_environment_evidence(plan, trial):
    """Audit saved files against frozen source/ELF evidence, without live helpers."""
    errors = []
    root = Path(plan["frozen_root"])
    directory = Path(trial["directory"]) / "configuration"
    try:
        evidence = load(directory / "magnetic_environment.json")
        lookup_path = directory / "gazebo_magnetic_reference.json"
        runtime_path = directory / "runtime_world.sdf"
        lookup = load(lookup_path)
        frozen = plan["magnetic_runtime_binding"]
        expected_runtime = frozen["manifest"]
        manifest_path = directory / "px4_magnetic_runtime.json"
        copied_runtime = load(manifest_path)
        actual = load(directory / "px4_magnetic_runtime_actual.json")
        library_binding = plan["magnetic_library_binding"]
        registration_path = directory / "gazebo_magnetic_runtime_registration.json"
        registration = load(registration_path)
        loaded_path = directory / "gazebo_loaded_magnetic_libraries.json"
        loaded = load(loaded_path)
        if (sha(registration_path) != library_binding["registration_sha256"]
                or registration != library_binding["registration"]):
            errors.append("magnetic:copied_library_registration")
        if (loaded.get("schema_version") != 1 or loaded.get("verified") is not True
                or Path(loaded.get("registration_path", "")).resolve() != registration_path.resolve()
                or loaded.get("registration_sha256") != library_binding["registration_sha256"]
                or loaded.get("environment_id") != registration.get("environment_id")
                or loaded.get("expected_source_registration") != registration.get("source_registration")):
            errors.append("magnetic:loaded_library_registration_binding")
        leader = loaded.get("owned_leader_pid")
        if (type(leader) is not int or leader <= 0 or loaded.get("owned_session") != leader
                or loaded.get("owned_process_group") != leader):
            errors.append("magnetic:loaded_library_owned_process_scope")
        observed_processes = loaded.get("observed_processes", [])
        if (not observed_processes or any(not isinstance(item, dict) or type(item.get("pid")) is not int
                or item["pid"] <= 0 or item.get("session") != leader or item.get("process_group") != leader
                for item in observed_processes)):
            errors.append("magnetic:loaded_library_observed_process_scope")
        observed_pids = {item.get("pid") for item in observed_processes if isinstance(item, dict)}
        loaded_libraries = loaded.get("actual_loaded_libraries", [])
        for kind in ("gazebo_sim", "gazebo_sensors"):
            selected = [item for item in loaded_libraries if isinstance(item, dict) and item.get("kind") == kind]
            expected_library = library_binding["registration"]["libraries"][kind]
            if len(selected) != 1:
                errors.append("magnetic:loaded_library_instance_count:"+kind)
                continue
            item = selected[0]
            if item.get("mapped_path") != expected_library["path"] or item.get("sha256") != expected_library["sha256"]:
                errors.append("magnetic:loaded_library_path_or_hash:"+kind)
            if (type(item.get("bytes")) is not int or item["bytes"] <= 0
                    or type(item.get("inode")) is not int or item["inode"] <= 0
                    or not item.get("observed_pids")
                    or not set(item["observed_pids"]).issubset(observed_pids)):
                errors.append("magnetic:loaded_library_process_evidence:"+kind)
        if sha(manifest_path) != frozen["manifest_sha256"] or copied_runtime != expected_runtime:
            errors.append("magnetic:copied_runtime_manifest")
        if sha(lookup_path) != plan["config_hashes"]["config/gazebo_magnetic_reference.json"]:
            errors.append("magnetic:copied_lookup_hash")
        expected_paths = {"source_world": root / trial["world_source"], "runtime_world": runtime_path,
                          "px4_runtime_manifest_path": manifest_path}
        for key, expected in expected_paths.items():
            if key not in evidence or Path(evidence[key]).resolve() != expected.resolve():
                errors.append("magnetic:" + key + "_binding")
        expected_hashes = {"source_world_sha256": plan["source_hashes"][trial["world_source"]],
                           "runtime_world_sha256": sha(runtime_path), "lookup_sha256": sha(lookup_path),
                           "px4_runtime_manifest_sha256": frozen["manifest_sha256"]}
        errors.extend("magnetic:" + key for key, value in expected_hashes.items() if evidence.get(key) != value)
        if (evidence.get("magnetic_environment") != MAGNETIC_CONTRACT
                or evidence.get("gazebo_lookup_reference") != lookup or evidence.get("px4_runtime") != expected_runtime
                or evidence.get("world_field_is_actual_runtime_input") is not False):
            errors.append("magnetic:lookup_provenance_or_mode")
        immutable = ("schema_version", "contract", "operation", "source_root", "px4_commit", "bridge_source_sha256",
                     "patch_sha256", "dependencies", "tracked_dirty_paths", "binary_path", "binary_sha256",
                     "binary_bytes", "expected_startup_log_marker")
        errors.extend("magnetic:actual_runtime:"+key for key in immutable if key not in expected_runtime or actual.get(key) != expected_runtime[key])
        log_path = Path(trial["directory"]) / "px4.log"
        if (actual.get("actual_startup_log_verified") is not True
                or Path(actual.get("actual_startup_log_path", "")).resolve() != log_path.resolve()
                or actual.get("actual_startup_log_sha256") != sha(log_path)
                or expected_runtime["expected_startup_log_marker"] not in log_path.read_text(encoding="utf-8", errors="replace")):
            errors.append("magnetic:actual_startup_log_binding")
        overrides = load(directory / "px4_parameters.json").get("explicit_environment_overrides", {})
        if (overrides.get("SENS_EN_MAGSIM") != 0 or overrides.get("UXRCE_DDS_SYNCT") != 0
                or overrides.get("SENS_IMU_MODE") != 1):
            errors.append("magnetic:source_parameter_overrides")
        if overrides.get("MIS_TAKEOFF_ALT") != 3. or overrides.get("COM_TAKEOFF_ACT") != 0:
            errors.append("magnetic:native_takeoff_parameter_overrides")
        tree = ET.parse(runtime_path)
        world = tree.getroot().find("world")
        # The original world is copied by the trial. Retrospective qualification
        # never imports a current helper or requires a still-present PX4 tree.
        source_path = directory / Path(trial["world_source"]).name
        if sha(source_path) != plan["source_hashes"][trial["world_source"]]:
            errors.append("magnetic:copied_source_world_hash")
        source = ET.parse(source_path).getroot().find("world")
        initialization = source.findtext("magnetic_field")
        if (world.findtext("magnetic_field") != initialization
                or evidence.get("preserved_world_magnetic_field_initialization") != initialization):
            errors.append("magnetic:world_initialization_not_preserved")
        plugins = [p for p in world.findall("plugin") if p.get("name") == "gz::sim::systems::Magnetometer"]
        if (len(plugins) != 1 or plugins[0].get("filename") != "gz-sim-magnetometer-system"
                or [p.text for p in plugins[0].findall("use_earth_frame_ned")] != ["false"]
                or [p.text for p in plugins[0].findall("use_units_gauss")] != ["true"]):
            errors.append("magnetic:actual_plugin_frame_or_units")
        spherical = world.find("spherical_coordinates")
        # SDF defines an omitted heading_deg as zero. Match the frozen
        # configure_world declaration without changing the physical source.
        if spherical.findtext("world_frame_orientation") != "ENU" or float(spherical.findtext("heading_deg", "0")) != 0.:
            errors.append("magnetic:actual_world_frame")
        for coordinate in ("latitude_deg", "longitude_deg"):
            if not math.isclose(float(spherical.findtext(coordinate)), float(lookup["reference_"+coordinate]), abs_tol=1e-8, rel_tol=0.):
                errors.append("magnetic:actual_world_" + coordinate)
        if float(world.findtext("physics/real_time_factor", "nan")) != .5:
            errors.append("magnetic:final_world_real_time_factor")
        mounts = evidence.get("sensor_mount", {})
        if mounts.get("sensor_orientation_in_body_flu") != "identity":
            errors.append("magnetic:sensor_mount_orientation")
        for model in ("x500_stage1", "x500_stage3"):
            relative = f"ros2_ws/src/uav_tracking_bringup/models/{model}/model.sdf"
            if mounts.get("model_sha256", {}).get(model) != plan["source_hashes"].get(relative):
                errors.append("magnetic:sensor_mount_model_hash:"+model)
        return {"errors": errors, **expected_hashes, "contract":MAGNETIC_CONTRACT,
                "px4_commit":expected_runtime.get("px4_commit"), "binary_path":expected_runtime.get("binary_path"),
                "binary_sha256":expected_runtime.get("binary_sha256"), "actual_startup_log_sha256":actual.get("actual_startup_log_sha256"),
                "magnetic_library_registration_sha256":library_binding["registration_sha256"],
                "actual_loaded_libraries_sha256":sha(loaded_path), "environment_id":registration.get("environment_id"),
                "scope":"Saved runtime/source/log/manifest binding; no live PX4 or current configuration helper used in this audit"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as error:
        return {"errors": [*errors, f"magnetic_evidence_unreadable:{type(error).__name__}:{error}"]}


def read_evaluation(spec, execution, plan=None):
    path = Path(spec["report"])
    record = {"kind": spec["kind"], "report": str(path), "execution": execution}
    if not path.is_file():
        return {**record, "result": "MISSING", "error": "Evaluator produced no report"}
    try:
        report = load(path)
        kind = spec["kind"]
        expected_schema = 3 if kind in {"surface_flight", "gimbal"} else 1
        if type(report.get("schema_version")) is not int or report["schema_version"] != expected_schema:
            raise ValueError("Unexpected evaluator report schema: " + kind)
        if kind == "surface_flight":
            if report.get("schema_version") != 3:
                raise ValueError("Surface flight evaluator must retain schema 3")
            verdict = report["acceptance"]["result"]
        elif kind in {"physical_identity", "navigation", "source_clock", "native_startup"}:
            verdict = report["evaluation_status"]
        else:
            verdict = report["result"]
        allowed = ({"PASS", "FAIL", "INCOMPLETE"} if kind == "source_clock" else
                   {"RECORDED_WITH_CENSORED_FAILURES", "INCOMPLETE_EVIDENCE"} if kind == "navigation" else
                   {"RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS", "INCOMPLETE_EVIDENCE"} if kind == "physical_identity" else
                   {"PASS", "FAIL_OR_INCOMPLETE"} if kind == "gimbal" else
                   {"PASS", "FAIL", "INCOMPLETE_EVIDENCE"})
        if verdict not in allowed:
            raise ValueError("Unknown evaluator verdict: " + str(verdict))
        directory = path.parent.resolve()
        if kind in {"navigation", "physical_identity", "source_clock", "native_startup"}:
            bound = report.get("source_trial" if kind == "physical_identity" else "trial")
            if bound is None or Path(bound).resolve() != directory:
                raise ValueError("Evaluator report is not bound to this trial")
        else:
            inputs = report.get("inputs", report.get("metadata", {}))
            if not inputs.get("bag") or Path(inputs["bag"]).resolve() != directory / "rosbag":
                raise ValueError("Evaluator input bag is not bound to this trial")
        code = execution.get("returncode")
        negative = verdict in {"FAIL", "FAIL_OR_INCOMPLETE", "INCOMPLETE_EVIDENCE", "INCOMPLETE"}
        if code != 0 and not (code == 2 and negative and kind in {"navigation", "physical_identity", "selected_target_safety", "source_clock", "native_startup"}):
            raise ValueError("Evaluator return code contradicts its report")
        if kind == "native_startup":
            checks = report.get("checks")
            if (report.get("native_startup_pass") is not (verdict == "PASS")
                    or not isinstance(checks, dict) or set(checks) != set(NATIVE_STARTUP_CHECKS)
                    or any(value is not None and type(value) is not bool for value in checks.values())
                    or not isinstance(report.get("failures"), dict) or not isinstance(report.get("incomplete_evidence"), dict)
                    or verdict == "PASS" and (any(value is not True for value in checks.values())
                                             or report["failures"] or report["incomplete_evidence"])):
                raise ValueError("Native-startup verdict contradicts independent sequence/readiness evidence")
            if plan is not None:
                provenance = report.get("evaluation_source", {})
                evaluation_root = Path(spec.get("evaluation_root", plan["frozen_root"]))
                expected_helpers = {str(evaluation_root / helper):plan["source_hashes"].get(helper)
                                    for helper in REPORT_PROVENANCE_HELPERS[kind]}
                if (provenance.get("script_sha256") != plan["source_hashes"].get(spec["script"])
                        or provenance.get("dependencies") != expected_helpers):
                    raise ValueError("Native-startup evaluator/helper provenance differs from frozen evaluation")
        if kind == "source_clock":
            counts = report.get("counts", {})
            if report.get("schema_version") != 1 or not isinstance(counts, dict):
                raise ValueError("Invalid independent source-clock report schema")
            for key in ("raw_px4", "timing_diagnostics", "adapted_odometry", "claimed_accepted", "claimed_rejected",
                        "independently_matched_triplets"):
                count(counts.get(key), "source-clock " + key)
            if (report.get("source_clock_pass") is not (verdict == "PASS")
                    or verdict == "PASS" and (report.get("clock_domain_valid") is not True
                       or report.get("vehicle_frame_continuity_valid") is not True
                       or report.get("failures") or report.get("incomplete_evidence")
                       or counts["independently_matched_triplets"] < 3
                       or counts["independently_matched_triplets"] > min(counts[key] for key in
                           ("raw_px4", "timing_diagnostics", "adapted_odometry"))
                       or counts["claimed_accepted"] + counts["claimed_rejected"] != counts["timing_diagnostics"])):
                raise ValueError("Source-clock verdict contradicts independent evidence")
            if plan is not None:
                provenance = report.get("evaluation_source", {})
                if provenance.get("script_sha256") != plan["source_hashes"].get(spec["script"]):
                    raise ValueError("Source-clock evaluator hash differs from frozen evaluator")
                actual_helpers = provenance.get("dependencies", {})
                expected_helpers = {str(Path(spec.get("evaluation_root", plan["frozen_root"])) / helper):plan["source_hashes"].get(helper)
                                    for helper in SOURCE_CLOCK_HELPERS}
                if actual_helpers != expected_helpers:
                    raise ValueError("Source-clock helper hashes differ from frozen evaluation helpers")
        return {**record, "result": "INCOMPLETE_EVIDENCE" if verdict == "INCOMPLETE" else verdict,
                "reported_verdict":verdict, "report_sha256": sha(path), "error": None}
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {**record, "result": "INVALID", "error": str(error)}


def navigation_verdict(report, gates):
    """Apply only prospective registered performance gates, to base_link."""
    if report.get("evaluation_status") != "RECORDED_WITH_CENSORED_FAILURES":
        return "INCOMPLETE_EVIDENCE", {"reason": "Navigation evidence is incomplete"}
    try:
        if report.get("schema_version") != 1 or report.get("incomplete_reasons"):
            raise ValueError("Navigation schema/evidence is incomplete")
        reference, interval = report["reference"], report["interval"]
        if reference.get("controlled_vehicle_point") != "base_link":
            raise ValueError("Physical reference is not base_link")
        distance = finite_number(reference["desired_horizontal_distance_m"], "desired distance", minimum=0.)
        finite_number(reference["desired_height_m"], "desired height", minimum=0.)
        start = finite_number(interval["start_s"], "interval start")
        end = finite_number(interval["end_s"], "interval end")
        nav_start = finite_number(interval["navigation_evaluation_start_s"], "navigation start", minimum=start, maximum=end)
        dt = finite_number(interval["sample_period_s"], "sample period")
        if end <= start or not math.isclose(dt, .1, rel_tol=0., abs_tol=1e-12):
            raise ValueError("Navigation requires a positive full recorded interval at 10 Hz")
        whole, kf = report["whole_interval"], report["kf_navigation"]
        total = count(whole["scheduled_samples"], "whole scheduled samples", minimum=1)
        expected_total = int(math.floor((end - start) / dt + 1e-8)) + 1
        if total != expected_total:
            raise ValueError("Whole-interval denominator differs from the registered grid")
        matched = count(whole["matched_truth_samples"], "matched truth", minimum=1, maximum=total)
        count(whole["inactive_control_samples"], "inactive control", maximum=total)
        kf_total = count(kf["counts"]["scheduled_samples"], "KF scheduled samples", minimum=1)
        expected_kf = total - max(0, int(math.ceil((nav_start - start - 1e-9) / dt)))
        if kf_total != expected_kf:
            raise ValueError("KF denominator differs from post-calibration grid")
        kf_valid = count(kf["counts"].get("valid_navigation_samples", 0), "valid navigation samples", maximum=kf_total)
        ratio(kf["valid_state_coverage"], kf_valid, kf_total, "valid_state_coverage")
        for dimension in ("distance", "height"):
            metric = whole["metrics"][f"base_link_{dimension}_error_m"]
            if count(metric["count"], dimension + " metric count", minimum=1, maximum=total) != matched:
                raise ValueError("Physical metric count differs from matched truth")
            finite_number(metric["rmse"], dimension + " RMSE", minimum=0.)
            transient = whole["transients"]["base_link"][dimension]
            if count(transient["scheduled_samples"], "transient samples", minimum=1) != total:
                raise ValueError("Transient denominator differs from the whole interval")
            if count(transient["valid_truth_samples"], "transient truth", minimum=1, maximum=total) != matched:
                raise ValueError("Transient truth differs from physical metric count")
            ratio(transient["truth_coverage"], matched, total, "transient truth coverage")
            expected_band = max(.5, .1 * distance) if dimension == "distance" else .25
            for key, expected in (("band_m", expected_band), ("minimum_in_band_duration_s", 3.),
                                  ("observed_interval_s", end - start)):
                if not math.isclose(finite_number(transient[key], key), expected, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError("Transient metric definition differs at " + key)
            settled, censored = transient["settled_through_interval_end"], transient["settling_right_censored"]
            if type(settled) is not bool or type(censored) is not bool or settled == censored:
                raise ValueError("Settling/censoring flags contradict each other")
            if type(transient["duplicate_source_times"]) is not bool:
                raise ValueError("Missing transient duplicate-time evidence")
            if settled:
                if transient["duplicate_source_times"]:
                    raise ValueError("Duplicate timestamps cannot establish settling")
                finite_number(transient["settling_time_s"], "settling time", minimum=0., maximum=end - start - 3. + 1e-8)
            elif transient["settling_time_s"] is not None:
                raise ValueError("Censored settling time must remain null")
        measured = {"base_link_distance_rmse_m": whole["metrics"]["base_link_distance_error_m"]["rmse"],
                    "base_link_height_rmse_m": whole["metrics"]["base_link_height_error_m"]["rmse"],
                    "valid_state_coverage": kf["valid_state_coverage"],
                    "truth_coverage": matched / total}
        try:
            validate_navigation_gates(gates)
        except ValueError as error:
            return "EVALUATION_PENDING", {"reason": str(error), "measured":measured}
        checks = {"base_link_distance": measured["base_link_distance_rmse_m"] <= gates["maximum_base_link_distance_rmse_m"],
                  "base_link_height": measured["base_link_height_rmse_m"] <= gates["maximum_base_link_height_rmse_m"],
                  "navigation_coverage": measured["valid_state_coverage"] >= gates["minimum_valid_state_coverage"],
                  "truth_coverage": measured["truth_coverage"] >= gates["minimum_truth_coverage"]}
        if gates["require_final_window_settled"]:
            transients = whole["transients"]["base_link"]
            checks["final_distance_settled"] = transients["distance"]["settled_through_interval_end"] is True
            checks["final_height_settled"] = transients["height"]["settled_through_interval_end"] is True
        return ("PASS" if all(checks.values()) else "FAIL"), {"checks": checks, "measured": measured}
    except (ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError) as error:
        return "INCOMPLETE_EVIDENCE", {"reason": str(error)}


def physical_identity_verdict(report, gates):
    """Gate full requested-task time; keep frame-based evidence as a diagnostic."""
    evidence = {}
    try:
        if report.get("schema_version") != 1 or report.get("evaluation_status") != "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS":
            raise ValueError("Physical identity report is incomplete")
        legacy = report["conservative_selected_identity"]
        frames = count(legacy["frames"], "legacy identity frames")
        for key in ("correct", "wrong", "unknown"):
            count(legacy[key], "legacy identity " + key, maximum=frames)
        if sum(legacy[key] for key in ("correct", "wrong", "unknown")) != frames:
            raise ValueError("Legacy identity counts do not sum to frames")
        evidence["diagnostic_frame_identity"] = {key:legacy.get(key) for key in
            ("frames", "correct", "wrong", "unknown", "known_coverage", "retention_lower_bound")}
        if legacy["wrong"] > 0:
            return "FAIL", {**evidence, "reason":"Observed wrong physical actor in diagnostic-frame evidence"}
        physical = report["conservative_task_time_identity"]
        if (physical.get("schema_version") != 1
                or physical.get("evaluation_status") != "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS"
                or physical.get("coverage_basis") != "fixed_10hz_request_to_recorded_clock_end"):
            raise ValueError("Missing full requested-task physical identity time coverage")
        period = finite_number(physical["sample_period_s"], "identity sample period")
        start = finite_number(physical["interval"]["start_s"], "identity interval start")
        end = finite_number(physical["interval"]["end_s"], "identity interval end")
        clock = physical["recorded_clock"]
        clock_start = finite_number(clock["start_s"], "identity recorded clock start")
        clock_end = finite_number(clock["end_s"], "identity recorded clock end", minimum=clock_start)
        count(clock["messages"], "identity recorded clock messages", minimum=1)
        if not math.isclose(end, clock_end, rel_tol=0., abs_tol=1e-9):
            raise ValueError("Identity denominator does not retain the full recorded clock end")
        if end <= start or not math.isclose(period, .1, rel_tol=0., abs_tol=1e-12):
            raise ValueError("Invalid full requested-task interval/grid")
        total = count(physical["scheduled_samples"], "identity scheduled samples", minimum=1)
        if total != int(math.ceil((end - start) / period - 1e-9)):
            raise ValueError("Identity denominator differs from complete recorded time")
        for key in ("correct", "wrong", "unknown"):
            count(physical[key], "identity " + key, maximum=total)
        if sum(physical[key] for key in ("correct", "wrong", "unknown")) != total:
            raise ValueError("Identity counts do not sum to the full time denominator")
        ratio(physical["known_coverage"], physical["correct"] + physical["wrong"], total, "identity known coverage")
        ratio(physical["retention_lower_bound"], physical["correct"], total, "identity retention lower bound")
        tasks = physical["tasks"]
        if not isinstance(tasks, dict) or any(not isinstance(uuid, str) or not uuid for uuid in tasks):
            raise ValueError("Invalid requested-task UUID map")
        if count(physical["requested_task_count"], "requested tasks", minimum=1) != len(tasks):
            raise ValueError("Requested-task count differs from unique task identities")
        unconfirmed = physical["unconfirmed_requested_tasks"]
        if (not isinstance(unconfirmed, list) or any(not isinstance(uuid, str) for uuid in unconfirmed)
                or len(set(unconfirmed)) != len(unconfirmed) or set(unconfirmed) - set(tasks)):
            raise ValueError("Invalid unconfirmed-task list")
        totals = Counter()
        for uuid, task in tasks.items():
            if type(task["confirmed"]) is not bool or type(task["initial_mapping_known"]) is not bool:
                raise ValueError("Task confirmation/mapping must be explicit booleans")
            requested = finite_number(task["request_time_s"], "task request time", minimum=start, maximum=end)
            if task["duplicate_request_uuid"] is not False:
                raise ValueError("Repeated REQUEST UUID cannot establish a unique task")
            if task["confirmed"]:
                finite_number(task["confirmation_time_s"], "task confirmation time", minimum=requested, maximum=end)
                if uuid in unconfirmed:
                    raise ValueError("Confirmed task is listed as unconfirmed")
            elif task["confirmation_time_s"] is not None or uuid not in unconfirmed:
                raise ValueError("Unconfirmed task evidence is inconsistent")
            if task["initial_mapping_known"] != (isinstance(task["expected_physical_id"], str) and bool(task["expected_physical_id"])):
                raise ValueError("Task physical identity mapping is inconsistent")
            n = count(task["scheduled_samples"], "task scheduled samples", maximum=total)
            for key in ("correct", "wrong", "unknown"):
                totals[key] += count(task[key], "task " + key, maximum=n)
            if (not task["confirmed"] or not task["initial_mapping_known"]) and task["correct"] + task["wrong"]:
                raise ValueError("Unconfirmed or independently unmapped task cannot claim known physical identity")
            if sum(task[key] for key in ("correct", "wrong", "unknown")) != n:
                raise ValueError("Task identity counts do not sum")
            if n:
                ratio(task["known_coverage"], task["correct"] + task["wrong"], n, "task known coverage")
                ratio(task["retention_lower_bound"], task["correct"], n, "task retention lower bound")
            elif task["known_coverage"] is not None or task["retention_lower_bound"] is not None:
                raise ValueError("Zero-duration task coverage must remain null")
        if any(totals[key] != physical[key] for key in ("correct", "wrong", "unknown")):
            raise ValueError("Per-task identity counts disagree with full-task totals")
        if not math.isclose(start, min(task["request_time_s"] for task in tasks.values()), rel_tol=0., abs_tol=1e-9):
            raise ValueError("Identity denominator does not start at the first REQUEST")
        evidence["physical_identity"] = {key:physical[key] for key in
            ("coverage_basis", "sample_period_s", "interval", "scheduled_samples", "correct", "wrong", "unknown",
             "known_coverage", "retention_lower_bound", "requested_task_count", "unconfirmed_requested_tasks")}
        if physical["wrong"] > 0 or unconfirmed:
            return "FAIL", {**evidence, "reason":"Wrong physical identity or unconfirmed requested task"}
        try:
            validate_navigation_gates(gates)
        except ValueError as error:
            return "EVALUATION_PENDING", {**evidence, "reason":str(error)}
        return ("PASS" if physical["known_coverage"] >= gates["minimum_physical_identity_coverage"] else "FAIL"), evidence
    except (ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError) as error:
        return "INCOMPLETE_EVIDENCE", {**evidence, "reason":str(error)}


def engineering_verdict(plan, trial, flight, evaluations):
    if flight.get("error") or flight.get("returncode") != 0:
        return "FAIL", {"reason": "Flight invocation did not complete successfully"}
    kinds = [entry.get("kind") for entry in evaluations]
    required = required_evaluators(trial)
    if (set(kinds) != required or len(kinds) != len(set(kinds))):
        return "INCOMPLETE_EVIDENCE", {"reason":"Required independent evaluators missing, duplicated or unexpected",
            "missing_evaluators":sorted(required - set(kinds)), "provided_evaluators":kinds}
    pending = [entry["kind"] for entry in evaluations if entry["result"] == "EVALUATION_PENDING"]
    missing = [entry["kind"] for entry in evaluations if entry["result"] in {"MISSING", "INVALID", "INCOMPLETE_EVIDENCE"}]
    negative = [entry["kind"] for entry in evaluations if entry["result"] in {"FAIL", "FAIL_OR_INCOMPLETE"}]
    if negative:
        return "FAIL", {"negative_evaluators": negative, "pending": pending, "incomplete": missing}
    if missing:
        return "INCOMPLETE_EVIDENCE", {"incomplete": missing, "pending": pending}
    if pending:
        return "EVALUATION_PENDING", {"pending": pending}
    try:
        for entry in evaluations:
            spec = next(item for item in trial["evaluations"] if item["kind"] == entry["kind"])
            if (Path(entry["report"]).resolve() != Path(spec["report"]).resolve()
                    or entry.get("report_sha256") != sha(entry["report"])):
                raise ValueError("Evaluator artifact binding changed: " + entry["kind"])
            checked = read_evaluation(spec, entry["execution"], plan)
            if checked["result"] != entry["result"] or checked["result"] == "INVALID":
                raise ValueError("Independent evaluator evidence contradicts its entry: " + entry["kind"])
        clock = next(entry for entry in evaluations if entry["kind"] == "source_clock")
        if clock["result"] != "PASS":
            raise ValueError("An independently passing source-clock report is required")
        navigation = next(entry for entry in evaluations if entry["kind"] == "navigation")
        result, evidence = navigation_verdict(load(navigation["report"]), plan["protocol"]["navigation_acceptance"])
        identity = next((entry for entry in evaluations if entry["kind"] == "physical_identity"), None)
        if identity is not None:
            identity_result, identity_evidence = physical_identity_verdict(load(identity["report"]), plan["protocol"]["navigation_acceptance"])
            evidence.update(identity_evidence)
            if identity_result == "FAIL" or result == "FAIL":
                result = "FAIL"
            elif identity_result == "INCOMPLETE_EVIDENCE" or result == "INCOMPLETE_EVIDENCE":
                result = "INCOMPLETE_EVIDENCE"
            elif identity_result == "EVALUATION_PENDING":
                result = "EVALUATION_PENDING"
        return result, evidence
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        return "INCOMPLETE_EVIDENCE", {"reason":str(error)}


def artifact_hashes(directory):
    return {path.relative_to(directory).as_posix(): sha(path) for path in sorted(directory.rglob("*"))
            if path.is_file() and path.suffix in {".json", ".jsonl", ".yaml", ".yml", ".sdf", ".log", ".bson"}}


def validate_probe_gate(plan):
    """Recheck all 12 development cells; a named boolean alone is no evidence.

    References preserve the original immutable trial and record. Only the
    four provenance-bearing offline evaluators may receive a separately named
    override; their actual source/helper hashes must match this new evaluation
    revision. No bags are opened and no earlier record is rewritten here.
    """
    binding = plan.get("development_probe_gate", {})
    path = Path(binding.get("path", ""))
    if not path.is_file() or binding.get("sha256") != sha(path) or binding.get("evidence") != load(path):
        raise ValueError("Development probe gate artifact is missing or changed")
    gate = binding["evidence"]
    checks = gate.get("checks")
    if (gate.get("schema_version") != 2 or gate.get("result") != "PASS"
            or gate.get("ready_for_formal_reliability_v4") is not True
            or not isinstance(checks, dict) or set(checks) != set(PROBE_CHECKS)
            or any(value is not True for value in checks.values())):
        raise ValueError("Development probe gate needs every required named check")
    expected_binding = {
        "flight_source_hashes":flight_source_hashes(plan["source_hashes"]),
        "evaluation_source_hashes":offline_source_hashes(plan["source_hashes"]),
        "model_hashes":plan["model_hashes"],
        "magnetic_runtime_manifest_sha256":plan["magnetic_runtime_binding"]["manifest_sha256"],
        "magnetic_library_registration_sha256":plan["magnetic_library_binding"]["registration_sha256"],
        "navigation_acceptance_sha256":digest(plan["protocol"]["navigation_acceptance"]),
    }
    if gate.get("bindings") != expected_binding:
        raise ValueError("Development probe gate source/model/runtime/evaluator/threshold binding differs")
    slots = gate.get("probe_slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("Development probe gate requires immutable probe slot evidence")
    cache, seen, cells = {}, set(), set()
    for item in slots:
        if not isinstance(item, dict):
            raise ValueError("Invalid development probe slot reference")
        source = Path(item["plan_path"])
        source_key = str(source.resolve())
        if not source.is_file() or sha(source) != item.get("plan_file_sha256"):
            raise ValueError("Development probe plan file binding differs")
        if source_key not in cache:
            previous = load(source)
            if previous.get("mode") != "PROBE":
                raise ValueError("Only development PROBE trials can satisfy the development gate")
            validate_plan(previous, source)
            if (flight_source_hashes(previous["source_hashes"]) != expected_binding["flight_source_hashes"]
                    or previous["model_hashes"] != plan["model_hashes"]
                    or previous["magnetic_runtime_binding"]["manifest_sha256"] != expected_binding["magnetic_runtime_manifest_sha256"]
                    or previous["magnetic_library_binding"]["registration_sha256"] != expected_binding["magnetic_library_registration_sha256"]):
                raise ValueError("Development probe flight-critical source/model/runtime differs")
            cache[source_key] = previous, read_slots(previous)
        previous, records = cache[source_key]
        slot_id = item["slot_id"]
        if (source_key, slot_id) in seen:
            raise ValueError("Duplicate development probe slot reference")
        seen.add((source_key, slot_id))
        original = next((trial for trial in previous["trials"] if trial["id"] == slot_id), None)
        if original is None:
            raise ValueError("Unknown development probe slot")
        record = records[slot_id]
        if (record.get("status") not in TERMINAL or record.get("infrastructure_stop") is not False
                or record.get("execution_status") != "COMPLETED" or record.get("flight_exit_code") != 0
                or sha(record_path(previous, original)) != item.get("record_file_sha256")):
            raise ValueError("Development probe needs an independently completed immutable terminal record")
        if runtime_configuration(previous, original)["errors"]:
            raise ValueError("Development probe actual source-clock/safety/magnetic runtime configuration differs")
        evaluation_plan = deepcopy(previous)
        evaluation_plan["source_hashes"] = plan["source_hashes"]
        evaluation_plan["protocol"]["navigation_acceptance"] = plan["protocol"]["navigation_acceptance"]
        trial = deepcopy(original)
        entries = deepcopy(record.get("evaluations", []))
        overrides = item.get("evaluation_overrides", [])
        if not isinstance(overrides, list) or len({entry.get("kind") for entry in overrides}) != len(overrides):
            raise ValueError("Invalid/duplicate development probe evaluation overrides")
        for spec in trial["evaluations"]:
            kind = spec["kind"]
            override = next((entry for entry in overrides if entry.get("kind") == kind), None)
            if override is None:
                spec["evaluation_root"] = previous["frozen_root"]
                if previous["source_hashes"].get(spec["script"]) != plan["source_hashes"].get(spec["script"]):
                    raise ValueError("Changed offline evaluator needs a separately named provenance-bearing report")
            else:
                if kind not in REPORT_PROVENANCE_HELPERS:
                    raise ValueError("Only independently provenance-bearing evaluators support an override")
                report_path = Path(override["report"])
                if (report_path.resolve() == Path(spec["report"]).resolve()
                        or report_path.parent.resolve() != Path(trial["directory"]).resolve()
                        or not report_path.is_file() or sha(report_path) != override.get("report_sha256")):
                    raise ValueError("Offline override must preserve the old report and bind a new report in the same trial")
                spec["report"] = str(report_path)
                spec["evaluation_root"] = override["evaluation_root"]
                checked = read_evaluation(spec, override["execution"], evaluation_plan)
                entries = [entry for entry in entries if entry.get("kind") != kind] + [checked]
            if kind in REPORT_PROVENANCE_HELPERS:
                provenance = load(spec["report"]).get("evaluation_source", {})
                expected_helpers = {str(Path(spec["evaluation_root"]) / helper):plan["source_hashes"].get(helper)
                                    for helper in REPORT_PROVENANCE_HELPERS[kind]}
                if (provenance.get("script_sha256") != plan["source_hashes"].get(spec["script"])
                        or provenance.get("dependencies") != expected_helpers
                        or any(value is None for value in expected_helpers.values())):
                    raise ValueError("Offline probe evaluator/helper provenance differs")
        if set(entry.get("kind") for entry in overrides) - required_evaluators(trial):
            raise ValueError("Unexpected development probe evaluator override")
        flight = next((entry for entry in record.get("commands", []) if entry.get("kind") == "flight"), {})
        verdict, evidence = engineering_verdict(evaluation_plan, trial, flight, entries)
        if verdict != "PASS":
            raise ValueError("Development probe independent acceptance did not PASS: " + slot_id + " " + str(evidence))
        cells.add((trial["target_class"], trial["group"]))
    if cells != {(cls, group) for cls in CLASSES for group in GROUPS}:
        raise ValueError("Development probe gate must cover the complete 2-class x 6-group matrix")


def record_path(plan, trial, suffix="json"):
    return Path(plan["output"]) / "slots" / f"{trial['id']}.{suffix}"


def read_slots(plan, *, verify_artifacts=True):
    rows = {}
    for trial in plan["trials"]:
        path = record_path(plan, trial)
        started = record_path(plan, trial, "started.json")
        if path.exists():
            record = load(path)
            if (record.get("record_sha256") != digest(record, ("record_sha256",))
                    or record.get("plan_sha256") != plan["plan_sha256"] or record.get("id") != trial["id"]
                    or record.get("status") not in TERMINAL):
                raise ValueError("Terminal slot record changed or belongs to another plan: " + trial["id"])
            if verify_artifacts:
                for relative, expected in record.get("artifact_hashes", {}).items():
                    artifact = Path(trial["directory"]) / relative
                    if not artifact.is_file() or sha(artifact) != expected:
                        raise ValueError("Terminal trial evidence changed: " + str(artifact))
            rows[trial["id"]] = record
        elif started.exists():
            marker = load(started)
            if marker.get("plan_sha256") != plan["plan_sha256"] or marker.get("id") != trial["id"]:
                raise ValueError("Running marker belongs to another frozen slot")
            rows[trial["id"]] = {"id": trial["id"], "status": "RUNNING", "started": marker}
        else:
            if Path(trial["directory"]).exists():
                raise ValueError("Pending trial already has artifacts; refusing old result reuse: " + trial["name"])
            rows[trial["id"]] = {"id": trial["id"], "status": "PENDING"}
    return rows


def finalize(plan, trial, record):
    record.update(id=trial["id"], name=trial["name"], plan_sha256=plan["plan_sha256"], finished_utc=utc_now())
    directory = Path(trial["directory"])
    record["artifact_hashes"] = artifact_hashes(directory) if directory.is_dir() else {}
    record["record_sha256"] = digest(record, ("record_sha256",))
    write_new(record_path(plan, trial), record)


def status(plan):
    rows = read_slots(plan)
    counts = Counter(row["status"] for row in rows.values())
    return {"plan_sha256": plan["plan_sha256"], "mode": plan["mode"], "planned_count": len(rows),
            "status_counts": dict(counts), "terminal_count": sum(counts[key] for key in TERMINAL),
            "all_engineering_pass": bool(rows) and counts["PASS"] == len(rows),
            "exit_code_semantics": "Run exit zero means no orchestration/infrastructure stop; inspect all_engineering_pass and every terminal result separately.",
            "pending_ids": [key for key, row in rows.items() if row["status"] == "PENDING"],
            "scope": "New post-repair engineering slots; navigation/base_link evidence and unknown identity are retained. This is not a new v3 four-estimator comparison."}


def run_plan(plan, *, max_new_trials=0, command_runner=execute_command, process_probe=simulation_processes,
             infrastructure=infrastructure_evidence, resolution=None):
    """Consume only PENDING slots. All real commands are synchronous."""
    if type(max_new_trials) is not int or max_new_trials < 0:
        raise ValueError("max_new_trials must be a nonnegative integer")
    validate_plan(plan)
    with run_lock(plan["output"]):
        verify_sources(plan)
        rows = read_slots(plan)
        active = process_probe()
        if active:
            raise RuntimeError("A simulator/recorder/flight graph already exists: " + json.dumps(active))
        # An acquired lock proves the prior orchestrator is gone. Keep its
        # attempt as INTERRUPTED; do not make that slot pending again.
        interrupted = False
        for trial in plan["trials"]:
            if rows[trial["id"]]["status"] == "RUNNING":
                finalize(plan, trial, {"status": "INTERRUPTED", "execution_status": "INTERRUPTED",
                    "error": "Prior attempt ended without a terminal record; retained without retry",
                    "started": rows[trial["id"]]["started"], "infrastructure_stop": True,
                    "cleanup": {"residual_processes": active}, "evaluations": []})
                interrupted = True
        if interrupted:
            return {"started_this_invocation": 0, "stop": "INTERRUPTED_ATTEMPT_RETAINED", **status(plan)}
        blocked = [row["record_sha256"] for row in rows.values() if row.get("infrastructure_stop")]
        if blocked:
            if (not isinstance(resolution, dict) or resolution.get("result") != "PASS"
                    or set(resolution.get("resolved_record_sha256", [])) != set(blocked)):
                raise RuntimeError("Previous infrastructure stop requires diagnosis bound to its terminal record hashes")
        executed = 0
        for trial in plan["trials"]:
            if rows[trial["id"]]["status"] != "PENDING":
                continue
            if max_new_trials and executed >= max_new_trials:
                break
            verify_sources(plan)
            if process_probe():
                raise RuntimeError("Unexpected simulation process before the next pending slot")
            if Path(trial["directory"]).exists():
                raise ValueError("Pending trial artifacts appeared before execution")
            marker = {"id": trial["id"], "plan_sha256": plan["plan_sha256"], "started_utc": utc_now(),
                      "flight_command": trial["flight_command"], "infrastructure_resolution": resolution}
            write_new(record_path(plan, trial, "started.json"), marker)
            logdir = Path(plan["output"]) / "logs"
            logdir.mkdir(exist_ok=True)
            evaluations, commands = [], []
            record = {"started_utc": marker["started_utc"], "execution_status": "COMPLETED"}
            try:
                flight = command_runner(trial["flight_command"], logdir / f"{trial['id']}.flight.log",
                                        Path(plan["frozen_root"]), plan["trial_timeout_s"])
                commands.append({"kind": "flight", **flight})
                verify_sources(plan)
                residual = process_probe()
                infra = infrastructure(Path(trial["directory"]), [])
                runtime = runtime_configuration(plan, trial)
                stop = bool(residual) or bool(flight.get("error")) or infra["stop"] or bool(runtime["errors"])
                if not stop:
                    for spec in trial["evaluations"]:
                        if (not spec["available_at_freeze"] or any(
                            next((e for e in evaluations if e["kind"] == dependency), {}).get("result")
                            in {None, "MISSING", "INVALID", "EVALUATION_PENDING"} for dependency in spec["dependencies"])):
                            evaluations.append({"kind": spec["kind"], "report": spec["report"],
                                "result": "EVALUATION_PENDING", "error": "Missing at freeze or dependency unavailable"})
                            continue
                        if Path(spec["report"]).exists():
                            raise ValueError("Evaluator report already exists; refusing overwrite: " + spec["report"])
                        execution = command_runner(spec["command"], logdir / f"{trial['id']}.{spec['kind']}.log",
                                                   Path(plan["frozen_root"]), plan["evaluation_timeout_s"])
                        commands.append({"kind": spec["kind"], **execution})
                        entry = read_evaluation(spec, execution, plan)
                        evaluations.append(entry)
                        if (execution.get("error") or entry["result"] in {"MISSING", "INVALID"}
                                or execution.get("returncode") not in {0, 2}):
                            stop = True
                            break
                    attempts = [{"report": e["report"], "log": e["execution"]["log"],
                                 "returncode": e["execution"]["returncode"]}
                                for e in evaluations if "execution" in e]
                    infra = infrastructure(Path(trial["directory"]), attempts)
                    residual = process_probe()
                    stop = stop or infra["stop"] or bool(residual)
                verify_sources(plan)
                result, evidence = engineering_verdict(plan, trial, flight, evaluations)
                interrupted = any(command.get("error") == "KeyboardInterrupt" for command in commands)
                record.update(status="INTERRUPTED" if interrupted else "INFRASTRUCTURE_ERROR" if stop else result,
                    execution_status="INTERRUPTED" if interrupted else "COMPLETED", engineering_result=result,
                    engineering_evidence=evidence, infrastructure_stop=stop, infrastructure=infra,
                    cleanup={"residual_processes": residual, "process_exit_codes":
                        load(Path(trial["directory"]) / "process_exit_codes.json")
                        if (Path(trial["directory"]) / "process_exit_codes.json").is_file() else None},
                    flight_exit_code=flight.get("returncode"), runtime_configuration=runtime,
                    commands=commands, evaluations=evaluations)
            except BaseException as error:
                record.update(status="INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "INFRASTRUCTURE_ERROR",
                    execution_status="INTERRUPTED", error=f"{type(error).__name__}: {error}", infrastructure_stop=True,
                    commands=commands, evaluations=evaluations, cleanup={"residual_processes": process_probe()})
            finalize(plan, trial, record)
            executed += 1
            if record["infrastructure_stop"]:
                return {"started_this_invocation": executed, "stop": "INFRASTRUCTURE_STOP", **status(plan)}
        return {"started_this_invocation": executed, "stop": None, **status(plan)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("plan", help="Explicitly freeze a new plan; no simulation")
    create.add_argument("--frozen-root", type=Path, default=ROOT)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--prefix", required=True)
    mode = create.add_mutually_exclusive_group(required=True)
    mode.add_argument("--formal", action="store_true")
    mode.add_argument("--probe", action="store_true")
    create.add_argument("--seeds", type=int, nargs="+")
    create.add_argument("--groups", choices=GROUPS, nargs="+")
    create.add_argument("--classes", choices=CLASSES, nargs="+")
    create.add_argument("--wall-timeout", type=float, default=300.)
    create.add_argument("--probe-gate", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--max-new-trials", type=int, default=0)
    run.add_argument("--infrastructure-resolution", type=Path)
    show = subparsers.add_parser("status")
    show.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "plan":
        plan = make_plan(args.frozen_root, args.output, args.prefix, formal=args.formal, seeds=args.seeds,
                         groups=args.groups, classes=args.classes, wall_timeout=args.wall_timeout, probe_gate=args.probe_gate)
        persist_plan(plan)
        result = {"plan": str(Path(plan["output"]) / "plan.json"), **status(plan)}
    else:
        plan = load(args.plan)
        validate_plan(plan, args.plan)
        if args.action == "status":
            result = status(plan)
        else:
            if os.name != "posix":
                parser.error("Actual run requires the isolated Linux/ROS environment; plan/status are portable")
            result = run_plan(plan, max_new_trials=args.max_new_trials,
                              resolution=load(args.infrastructure_resolution) if args.infrastructure_resolution else None)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 2 if result.get("stop") else 0


if __name__ == "__main__":
    raise SystemExit(main())
