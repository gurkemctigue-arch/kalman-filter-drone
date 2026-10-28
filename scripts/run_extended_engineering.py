"""Freeze and serially run 16 engineering flights outside the 166-flight study.

Only --plan-only avoids simulation. Each condition has one independent
flight, not ten repetitions. Existing/failed/interrupted evidence is never
overwritten or retried. Run with scripts/ros_python.sh in the ROS checkout.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys
from typing import Any, Callable

from run_full_plan_research import process_lock, source_hashes
from run_stage23_matrix import utc_now, write_json
from uav_tracking.research_failures import classify_infrastructure_failure

ROOT = Path(__file__).resolve().parents[1]
FAULTS = ("depth_noise", "depth_holes", "dropout", "latency", "combined")
STATUSES = {"PENDING", "RUNNING_FLIGHT", "RUNNING_EVALUATION", "PASS", "FAIL", "INTERRUPTED"}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def plan_trials(prefix: str, preregistration: dict) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", prefix):
        raise ValueError("prefix must contain only letters, numbers, '_' or '-'")
    motion = preregistration["motion_extension"]
    if (motion["classes"] != ["person", "car"] or motion["control_modes"] != ["velocity", "position"]
            or motion["estimator_methods"] != ["adaptive_kf"] or motion["motion_profile_kind"] != "speed_changes"
            or motion["expected_trials"] != 4):
        raise ValueError("Motion extension differs from the existing four-flight preregistration")
    resources = preregistration["resource_configuration"]
    rtf = resources["real_time_factor"]
    if isinstance(rtf, bool) or not isinstance(rtf, (int, float)) or not math.isfinite(rtf) or not 0 < rtf <= 1:
        raise ValueError("Preregistered real-time factor must be finite and in (0,1]")
    for category in ("person", "car"):
        size, threads = (resources[category][key] for key in ("inference_image_size", "inference_threads"))
        if type(size) is not int or size < 128 or size % 32 or type(threads) is not int or threads < 1:
            raise ValueError("Preregistered detector resources are invalid")
        if not resources[category].get("weights"):
            raise ValueError("Preregistered weights path is required")
    trials = []

    def add(category, coverage, *, mode="velocity", condition="clean", distance=None, profile="standard"):
        setting = resources[category]
        label = condition if coverage == "online_fault" else coverage
        identifier = f"{category}_{label}_{mode}_seed000"
        trials.append({"id": identifier, "name": f"{prefix}_{identifier}", "stage": 1,
                       "target_class": category, "coverage": coverage, "condition": condition,
                       "command_mode": mode, "estimator_method": "adaptive_kf", "seed": 0,
                       "speed_mps": random.Random(0).uniform(.45, .55), "motion_profile_kind": profile,
                       "duration_s": 45., "occlusions": True, "reselect_after_loss": True,
                       "target_mode": "auto_unique", "desired_distance_m": distance if distance is not None else (9. if category == "car" else 5.),
                       "desired_height_m": 2., "takeoff_height_m": 3., "real_time_factor": rtf,
                       "inference_image_size": setting["inference_image_size"], "inference_threads": setting["inference_threads"],
                       "weights": setting["weights"], "scope": "single_flight_engineering_extension",
                       "independent_repeats_per_condition": 1})

    for category in motion["classes"]:
        for mode in motion["control_modes"]:
            add(category, "speed_changes", mode=mode, profile=motion["motion_profile_kind"])
    for condition in FAULTS:
        for category in ("person", "car"):
            add(category, "online_fault", condition=condition)
    for category, distance in (("person", 7.), ("car", 12.)):
        add(category, "long_distance", distance=distance)
    return trials


def frozen_plan(prefix: str, preregistration_path: Path, *, root: Path = ROOT,
                wall_timeout: float = 300., render_backend: str = "egl") -> dict:
    if not math.isfinite(wall_timeout) or wall_timeout <= 0 or render_backend not in {"egl", "wslg"}:
        raise ValueError("Wall timeout must be positive/finite and render backend egl or wslg")
    raw = preregistration_path.read_bytes()
    preregistration = json.loads(raw.decode("utf-8"))
    trials = plan_trials(prefix, preregistration)
    return {"prefix": prefix, "preregistration_sha256": hashlib.sha256(raw).hexdigest(),
            "resources": preregistration["resource_configuration"], "source_hashes": source_hashes(root),
            "wall_timeout_s": wall_timeout, "render_backend": render_backend, "trials": trials,
            "primary_166_included": False, "expected_trials": 16,
            "protocol": "Four preregistered motion extensions + ten online fault engineering flights + two longer-distance flights. One flight per condition, adaptive KF only. Whole recorded schema-3 flight acceptance with short/long shutter and explicit reselection. No automatic retries, no overwrite; failures and missing metrics remain visible. Not ten independent repeats per fault/distance/motion condition."}


def manifest_for(plan: dict) -> dict:
    return {"schema_version": 1, "source": "EXTENDED_ENGINEERING_16_FLIGHTS", "created_utc": utc_now(),
            "plan_sha256": digest(plan), "plan": plan,
            "slots": [{"trial": trial, "status": "PENDING"} for trial in plan["trials"]]}


def validate_manifest(manifest: dict) -> None:
    plan = manifest["plan"]
    if (manifest.get("schema_version") != 1 or manifest.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
            or manifest.get("plan_sha256") != digest(plan)):
        raise ValueError("Stored engineering plan does not match its declared digest")
    trials, slots = plan["trials"], manifest["slots"]
    if len(trials) != 16 or len({trial["name"] for trial in trials}) != 16 or len(slots) != 16:
        raise ValueError("Engineering plan must retain exactly sixteen distinct slots")
    if [slot.get("trial") for slot in slots] != trials or any(slot.get("status") not in STATUSES for slot in slots):
        raise ValueError("Slot binding/status differs from the frozen engineering plan")


def flight_command(trial: dict, plan: dict, *, root: Path = ROOT, python: str = sys.executable) -> list[str]:
    weights = Path(trial["weights"])
    if not weights.is_absolute():
        weights = root / weights
    return [python, str(root / "scripts/run_stage1_trial.py"), "--name", trial["name"], "--stage", "1",
            "--class", trial["target_class"], "--seed", str(trial["seed"]), "--speed-mps", str(trial["speed_mps"]),
            "--condition", trial["condition"], "--command-mode", trial["command_mode"],
            "--estimator-method", trial["estimator_method"], "--target-mode", trial["target_mode"],
            "--motion-profile-kind", trial["motion_profile_kind"], "--duration", str(trial["duration_s"]),
            "--desired-distance-m", str(trial["desired_distance_m"]), "--takeoff-height-m", str(trial["takeoff_height_m"]),
            "--real-time-factor", str(trial["real_time_factor"]), "--inference-image-size", str(trial["inference_image_size"]),
            "--inference-threads", str(trial["inference_threads"]), "--model-path", str(weights),
            "--wall-timeout", str(plan["wall_timeout_s"]), "--render-backend", plan["render_backend"],
            "--occlusions", "--reselect-after-loss"]


def evaluation_command(trial: dict, *, root: Path = ROOT, python: str = sys.executable) -> tuple[list[str], Path]:
    directory = root / "results" / trial["name"]
    report = directory / "offline_evaluation.json"
    return [python, str(root / "scripts/evaluate_stage1_flight.py"), str(directory / "rosbag"),
            "--target-class", trial["target_class"], "--desired-distance-m", str(trial["desired_distance_m"]),
            "--desired-height-m", str(trial["desired_height_m"]), "--telemetry-jsonl", str(directory / "telemetry.jsonl"),
            "--monitor-summary", str(directory / "summary.json"), "--output", str(report)], report


def report_outcome(path: Path, trial: dict) -> dict:
    try:
        raw = path.read_bytes()
        report = json.loads(raw.decode("utf-8"))
        configuration = report["configuration"]
        if report.get("schema_version") != 3:
            raise ValueError("Engineering acceptance requires schema 3")
        if any(configuration.get(key) != trial[key] for key in ("target_class", "desired_distance_m", "desired_height_m")):
            raise ValueError("Evaluation configuration differs from the actual flight target/distance/height")
        if configuration.get("start_s") is not None or configuration.get("end_s") is not None:
            raise ValueError("Engineering evaluation must retain the full recorded interval")
        return {"result": report["acceptance"]["result"], "report": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(), "error": None}
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
        return {"result": "MISSING_OR_INVALID", "report": str(path), "error": str(error)}


def summary(manifest: dict) -> dict:
    counts = Counter(slot["status"] for slot in manifest["slots"])
    return {"schema_version": 1, "plan_sha256": manifest["plan_sha256"], "updated_utc": utc_now(),
            "planned_trials": 16, "status_counts": dict(counts), "primary_166_included": False,
            "all_planned_trials_pass": counts["PASS"] == 16,
            "pending_ids": [slot["trial"]["id"] for slot in manifest["slots"] if slot["status"] == "PENDING"],
            "failed_or_interrupted_ids": [slot["trial"]["id"] for slot in manifest["slots"] if slot["status"] in {"FAIL", "INTERRUPTED"}],
            "scope": "One engineering flight per condition. Pending/failed/interrupted slots remain in the sixteen-slot ledger; no claim of ten independent repetitions per extension condition."}


def execute(manifest: dict, output: Path, *, root: Path = ROOT, stop_after: int = 0,
            runner: Callable[..., Any] = subprocess.run) -> int:
    validate_manifest(manifest)
    if stop_after < 0:
        raise ValueError("stop-after must be nonnegative")

    def save():
        manifest["updated_utc"] = utc_now()
        write_json(output / "manifest.json", manifest)
        write_json(output / "summary.json", summary(manifest))

    def infrastructure_stop(slot: dict, directory: Path, phase: str) -> bool:
        qualification = classify_infrastructure_failure(directory)
        slot["infrastructure_failure"] = qualification
        slot.setdefault("infrastructure_checks", []).append(
            {"phase": phase, "time_utc": utc_now(), "qualification": qualification})
        if not qualification["stop"]:
            save()
            return False
        if phase == "after_flight":
            slot["evaluations"].append({"kind": "infrastructure", "result": "MISSING", "returncode": None,
                                        "error": "Required infrastructure evidence unavailable; see infrastructure_failure"})
        slot.update(status="FAIL", finished_utc=utc_now(),
                    error="Infrastructure qualification failed; remaining planned slots retained pending")
        save()
        path = output / "infrastructure_stops.json"
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(history, list):
            raise ValueError("Infrastructure stop history must be a list; refusing to overwrite")
        history.append({"time_utc": utc_now(), "plan_sha256": manifest["plan_sha256"], "phase": phase,
                        "trial_id": slot["trial"]["id"], "trial_name": slot["trial"]["name"],
                        "infrastructure_failure": qualification,
                        "action": "Stop current invocation; retain failed trial and remaining PENDING slots. Resume pending work only after diagnosis; never retry failed names automatically."})
        write_json(path, history)
        return True

    for slot in manifest["slots"]:
        if slot["status"] in {"RUNNING_FLIGHT", "RUNNING_EVALUATION"}:
            slot.update(status="INTERRUPTED", finished_utc=utc_now(),
                        error="Prior engineering process ended during this slot; preserved without retry")
    save()
    attempted = 0
    for slot in manifest["slots"]:
        if slot["status"] != "PENDING" or stop_after and attempted >= stop_after:
            continue
        attempted += 1
        trial = slot["trial"]
        directory = root / "results" / trial["name"]
        slot.update(status="RUNNING_FLIGHT", started_utc=utc_now(), commands=[], evaluations=[])
        save()
        if directory.exists():
            slot.update(status="FAIL", finished_utc=utc_now(),
                        error="Trial directory exists; refusing to overwrite or adopt unrelated evidence")
            save()
            continue

        def command_run(kind, command):
            log = output / "logs" / f"{trial['id']}_{kind}.log"
            record = {"kind": kind, "argv": command, "started_utc": utc_now(), "returncode": None, "log": str(log)}
            slot["commands"].append(record)
            save()
            log.parent.mkdir(parents=True, exist_ok=True)
            try:
                with log.open("x", encoding="utf-8") as handle:
                    process = runner(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT, check=False)
                record["returncode"] = process.returncode
            except (OSError, subprocess.SubprocessError) as error:
                record["error"] = str(error)
            record["finished_utc"] = utc_now()
            save()
            return record["returncode"]

        try:
            flight_code = command_run("sitl", flight_command(trial, manifest["plan"], root=root))
            # The trial runner has exited and cleaned up its processes. A
            # genuine infrastructure failure must not consume later slots.
            if infrastructure_stop(slot, directory, "after_flight"):
                break
            slot["status"] = "RUNNING_EVALUATION"
            save()
            if (directory / "rosbag/metadata.yaml").is_file():
                command, report = evaluation_command(trial, root=root)
                eval_code = command_run("flight_eval", command)
                slot["evaluations"].append({"kind": "schema3_flight", "returncode": eval_code, **report_outcome(report, trial)})
            else:
                slot["evaluations"].append({"kind": "schema3_flight", "returncode": None,
                                            "result": "MISSING", "error": "No readable bag metadata"})
            # Complete metadata can still name undecodable core streams.
            # Ordinary target-loss/ambiguity/accuracy FAIL verdicts continue.
            if infrastructure_stop(slot, directory, "after_evaluation"):
                break
            slot["status"] = "PASS" if flight_code == 0 and all(
                row["returncode"] == 0 and row["result"] == "PASS" for row in slot["evaluations"]) else "FAIL"
            slot["finished_utc"] = utc_now()
            save()
        except KeyboardInterrupt:
            slot.update(status="INTERRUPTED", finished_utc=utc_now(), error="KeyboardInterrupt; no automatic retry")
            save()
            raise
    return attempted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="extended_engineering_v2")
    parser.add_argument("--output", type=Path, default=ROOT / "results/extended_engineering_v2_matrix")
    parser.add_argument("--preregistration", type=Path, default=ROOT / "planning/online_estimator_preregistration.json")
    parser.add_argument("--wall-timeout", type=float, default=300.)
    parser.add_argument("--render-backend", choices=["egl", "wslg"], default="egl")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after", type=int, default=0, help="Maximum new slots; zero runs all pending")
    args = parser.parse_args()
    if args.stop_after < 0:
        parser.error("stop-after must be nonnegative")
    try:
        # Share the actual full-plan writer lock, so these flights cannot run
        # concurrently with the primary study through its orchestrator.
        with process_lock(ROOT):
            plan = frozen_plan(args.prefix, args.preregistration, wall_timeout=args.wall_timeout,
                               render_backend=args.render_backend)
            path = args.output / "manifest.json"
            if path.exists():
                if not args.resume:
                    parser.error("Manifest exists; use --resume or a new prefix/output")
                manifest = json.loads(path.read_text(encoding="utf-8"))
                validate_manifest(manifest)
                if manifest["plan_sha256"] != digest(plan):
                    parser.error("Resources, preregistration or source hashes changed; preserve old results and use a new prefix/output")
            else:
                if args.resume:
                    parser.error("Cannot resume without a manifest")
                manifest = manifest_for(plan)
                write_json(path, manifest)
                write_json(args.output / "summary.json", summary(manifest))
            if not args.plan_only:
                execute(manifest, args.output, stop_after=args.stop_after)
            result = summary(manifest)
            print(json.dumps(result, indent=2))
            return 2 if result["failed_or_interrupted_ids"] else 0
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
