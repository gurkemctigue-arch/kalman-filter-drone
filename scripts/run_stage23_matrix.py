"""Pre-register and serially execute the real stage-two/three SITL study.

No ROS imports or simulation are needed for --plan-only. Run actual trials
with scripts/ros_python.sh so the subprocess evaluators use installed ROS
interfaces. Failed/interrupted slots are retained and never retried here.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uav_tracking.research_failures import classify_infrastructure_failure


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def plan_trials(prefix: str, seeds: list[int], *, real_time_factor: float = 1.,
                car_image_size: int = 480, car_threads: int = 2) -> list[dict[str, Any]]:
    """Freeze all 66 default slots, including engineering safety scenarios."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", prefix):
        raise ValueError("prefix must contain only letters, numbers, '_' or '-'")
    if not seeds or len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
        raise ValueError("seeds must be nonempty, distinct and nonnegative")
    if not math.isfinite(real_time_factor) or not 0 < real_time_factor <= 1:
        raise ValueError("real-time factor must be finite and in (0,1]")
    if car_image_size < 32 or car_image_size % 32 or car_threads < 1:
        raise ValueError("car image size must be a positive multiple of 32; threads must be positive")
    trials = []

    def add(stage, category, scenario, seed, *, gimbal="midpoint", engineering=False):
        auto = scenario == "auto_unique"
        label = gimbal if stage == 3 else ("auto" if auto else "locked")
        suffix = f"s{stage}_{category}_{scenario}_{label}_seed{seed:03d}"
        trial = {
            "id": suffix, "name": f"{prefix}_{suffix}", "stage": stage, "target_class": category,
            "scenario": scenario, "scenario_kind": "parallel" if auto or stage == 3 else scenario,
            "seed": seed, "speed_mps": random.Random(seed).uniform(.45, .55),
            "condition": "clean", "command_mode": "velocity", "estimator_method": "adaptive_kf",
            "target_mode": "auto_unique" if auto or stage == 3 else "locked_target",
            "initial_select": "none" if auto or stage == 3 else "middle",
            "initial_min_candidates": 2 if auto or stage == 3 else 3,
            "gimbal_mode": gimbal, "occlusions": stage == 3 or scenario == "parallel",
            "reselect_after_loss": stage == 3 or scenario == "parallel",
            "duration_s": 35.0 if auto else (50.0 if scenario == "ambiguity" else 43.0),
            "no_follow_duration_s": 35.0 if auto else None,
            "desired_distance_m": 9.0 if category == "car" else 5.0, "takeoff_height_m": 3.0,
            "real_time_factor": real_time_factor,
            "inference_image_size": car_image_size if category == "car" else 320,
            "inference_threads": car_threads if category == "car" else 2,
            "terminal_expectation": "hover" if scenario in {"ambiguity", "auto_unique"} else "tracking",
            "scope": "engineering_safety" if engineering else "repeated_research",
            "pair_id": f"s3_{category}_seed{seed:03d}" if stage == 3 else None,
        }
        trials.append(trial)

    for category in ("person", "car"):
        for seed in seeds:
            add(2, category, "crossing", seed)
    for scenario in ("parallel", "ambiguity", "auto_unique"):
        for category in ("person", "car"):
            add(2, category, scenario, seeds[0], engineering=True)
    for category in ("person", "car"):
        for seed in seeds:
            for gimbal in ("midpoint", "active"):
                add(3, category, "gimbal", seed, gimbal=gimbal)
    return trials


def flight_command(trial: dict[str, Any], *, root: Path = ROOT, python: str = sys.executable,
                   wall_timeout: float = 300, render_backend: str = "egl") -> list[str]:
    command = [python, str(root / "scripts/run_stage1_trial.py"), "--name", trial["name"],
               "--stage", str(trial["stage"]), "--class", trial["target_class"],
               "--seed", str(trial["seed"]), "--speed-mps", repr(trial["speed_mps"]),
               "--condition", trial["condition"], "--command-mode", trial["command_mode"],
               "--estimator-method", trial["estimator_method"], "--target-mode", trial["target_mode"],
               "--initial-select", trial["initial_select"], "--gimbal-mode", trial["gimbal_mode"],
               "--initial-min-candidates", str(trial["initial_min_candidates"]),
               "--scenario-kind", trial["scenario_kind"], "--duration", str(trial["duration_s"]),
               "--desired-distance-m", str(trial["desired_distance_m"]),
               "--takeoff-height-m", str(trial["takeoff_height_m"]),
               "--real-time-factor", str(trial["real_time_factor"]),
               "--inference-image-size", str(trial["inference_image_size"]),
               "--inference-threads", str(trial["inference_threads"]),
               "--wall-timeout", str(wall_timeout), "--render-backend", render_backend]
    if trial["no_follow_duration_s"] is not None:
        command.extend(["--no-follow-duration-s", str(trial["no_follow_duration_s"])])
    if trial["occlusions"]:
        command.append("--occlusions")
    if trial["reselect_after_loss"]:
        command.append("--reselect-after-loss")
    return command


def evaluation_commands(trial: dict[str, Any], *, root: Path = ROOT,
                        python: str = sys.executable) -> list[tuple[str, list[str], Path]]:
    directory = root / "results" / trial["name"]
    bag = directory / "rosbag"
    if trial["scenario"] == "auto_unique":
        report = directory / "auto_unique_evaluation.json"
        return [("auto_unique", [python, str(root / "scripts/run_stage23_matrix.py"),
                                  "--evaluate-auto-unique", str(bag), "--target-class", trial["target_class"],
                                  "--output", str(report)], report)]
    common = [str(bag), "--target-class", trial["target_class"], "--telemetry-jsonl", str(directory / "telemetry.jsonl"),
              "--monitor-summary", str(directory / "summary.json")]
    if trial["stage"] == 2:
        report = directory / "stage2_evaluation.json"
        command = [python, str(root / "scripts/evaluate_stage2_flight.py"), *common,
                   "--require-occlusions" if trial["occlusions"] else "--no-require-occlusions",
                   "--terminal-expectation", trial["terminal_expectation"],
                   "--output", str(report)]
        if trial["scenario"] == "ambiguity":
            command.append("--require-ambiguity")
        return [("stage2_safety", command, report)]
    flight_report = directory / "flight_evaluation.json"
    gimbal_report = directory / "gimbal_evaluation.json"
    return [
        ("flight", [python, str(root / "scripts/evaluate_stage1_flight.py"), *common,
                    "--desired-distance-m", str(trial["desired_distance_m"]), "--desired-height-m", "2.0",
                    "--output", str(flight_report)], flight_report),
        ("gimbal", [python, str(root / "scripts/evaluate_stage3_gimbal.py"), str(bag),
                    "--mode", trial["gimbal_mode"], "--output", str(gimbal_report)], gimbal_report),
    ]


def evaluate_auto_unique(records, metadata: dict[str, Any], target_class: str) -> dict[str, Any]:
    """Require observed multi-box ambiguity and actual sustained stopped flight.

    An empty UUID is deliberately not a pass criterion. All streams cover
    the untrimmed final 5.2 seconds, and physics odometry proves the stop.
    """
    import evaluate_stage1_flight as base
    import evaluate_stage2_flight as stage2

    rows = sorted((stage2.operational(row) for row in records), key=lambda row: row.time_s)
    end = max((row.time_s for row in rows), default=0.)
    start = end - 5.2
    topics = {topic: [row for row in rows if row.topic == topic] for topic in (
        "/tracking/state", "/tracking/status", "/tracking/command", "/vehicle/odometry")}
    tail = {topic: [row for row in group if start <= row.time_s <= end] for topic, group in topics.items()}
    gaps, spans = {}, {}
    for topic, group in tail.items():
        times = [start] + [row.time_s for row in group] + [end]
        gaps[topic] = max((b-a for a, b in zip(times, times[1:])), default=math.inf)
        spans[topic] = group[-1].time_s-group[0].time_s if group else 0.
    multiple_times, snapshot_errors = [], []
    projected_snapshots = 0
    for row in rows:
        if row.topic != "/tracking/tracks":
            continue
        try:
            payload = json.loads(row.message.data)
            acquired, output = base.finite(payload["acquisition_s"]), base.finite(payload["output_s"])
            received = base.finite(row.received_sim_s)
            if (payload.get("schema_version") != 1 or type(payload["projected"]) is not bool
                    or acquired is None or output is None or acquired > output
                    or received is None or output > received + .05):
                raise ValueError("invalid track snapshot timing")
            # Timer projections retain the last real acquisition stamp even
            # after prolonged ambiguity/loss. They cannot supply fresh boxes,
            # but an old source stamp alone does not make them malformed.
            if not payload["projected"] and received - acquired > .75:
                raise ValueError("stale fresh-detection track snapshot")
            projected_snapshots += int(payload["projected"])
            fresh = [item for item in payload["tracks"] if item["class_name"] == target_class
                     and item["matched"] is True and not payload["projected"]]
            for item in fresh:
                box = item["bbox_xyxy"]
                if (len(box) != 4 or any(base.finite(x) is None for x in box)
                        or box[0] >= box[2] or box[1] >= box[3]):
                    raise ValueError("invalid candidate box")
            if len(fresh) >= 2 and len({item["track_id"] for item in fresh}) == len(fresh):
                multiple_times.append(acquired)
        except (KeyError, TypeError, ValueError) as error:
            snapshot_errors.append({"time_s": row.time_s, "reason": str(error)})
    states, statuses, commands = (topics[name] for name in ("/tracking/state", "/tracking/status", "/tracking/command"))
    speeds = [base._speed(row) for row in tail["/vehicle/odometry"]]
    vehicle = [row.message for row in rows if row.topic in {"/fmu/out/vehicle_status", "/fmu/out/vehicle_status_v1"}]
    checks = {
        "clock_recorded": metadata.get("clock_recorded") is True and metadata.get("clock_samples_read", 0) > 0,
        "input_decodes_without_errors": not metadata.get("read_errors") and not metadata.get("unavailable_types"),
        "fresh_multi_box_evidence_is_persistent": len(set(multiple_times)) >= 3 and max(multiple_times, default=0)-min(multiple_times, default=0) >= 1.,
        "track_snapshot_messages_valid": bool(multiple_times) and not snapshot_errors,
        "no_explicit_selection": not any(row.topic == "/tracking/selection" and getattr(row.message, "action", None) == 0 for row in rows),
        "never_automatically_tracks_a_candidate": bool(states) and all(row.message.state not in {1, 2} for row in states),
        "never_issues_follow_control": bool(statuses) and all(row.message.lifecycle not in {2, 3} for row in statuses),
        "all_motion_commands_invalid": bool(commands) and all(row.message.valid is False for row in commands),
        "armed_and_offboard_observed": any(row.arming_state == 2 for row in vehicle) and any(row.nav_state == 14 for row in vehicle),
        "all_final_streams_span_five_seconds": all(span >= 5.-1e-9 for span in spans.values()),
        "all_final_streams_cover_tail": all(gap <= .5 for gap in gaps.values()),
        "final_state_is_ambiguous": bool(tail["/tracking/state"]) and all(row.message.state == 4 for row in tail["/tracking/state"]),
        "final_controller_is_hover": bool(tail["/tracking/status"]) and all(row.message.lifecycle == 4 for row in tail["/tracking/status"]),
        "actual_final_vehicle_speed_below_threshold": bool(speeds) and all(math.isfinite(speed) and speed <= .30 for speed in speeds),
    }
    return {"schema_version": 2, "source": "OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY",
            "evaluator_version": "2_projected_source_age_is_not_detection_freshness",
            "result": "PASS" if all(checks.values()) else "FAIL", "target_class": target_class,
            "checks": checks, "inputs": metadata, "interval": {"start_s": start, "recorded_end_s": end},
            "fresh_multi_box_acquisitions": len(set(multiple_times)), "snapshot_errors": snapshot_errors,
            "projected_snapshot_count": projected_snapshots,
            "snapshot_timestamp_policy": "All snapshots require valid acquisition/output/receive timing; only non-projected detections require source age <= 0.75 s. Projections never count as fresh multi-box evidence.",
            "final_stream_spans_s": spans, "final_stream_maximum_gap_s": gaps,
            "actual_final_vehicle_speed_mps": base.summary(speeds),
            "scope": "Multiple candidates must cause ambiguity, suspended follow control and an actual sustained hover; UUID emptiness is not identity/safety evidence"}


def report_outcome(path: Path, kind: str) -> tuple[str, str | None]:
    if not path.is_file():
        return "MISSING", "evaluator did not produce its planned report"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if kind == "flight":
            if report.get("schema_version") != 3:
                return "FAIL", "stage-three flight acceptance requires schema 3"
            outcome = report["acceptance"]["result"]
        else:
            outcome = report["result"]
        return str(outcome), None
    except (KeyError, TypeError, ValueError) as error:
        return "INVALID", str(error)


def summarize(manifest: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(slot["status"] for slot in manifest["slots"])
    return {"schema_version": 1, "updated_utc": utc_now(), "plan_sha256": manifest["plan_sha256"],
            "planned_count": len(manifest["slots"]), "status_counts": dict(counts),
            "all_planned_trials_pass": bool(manifest["slots"]) and counts["PASS"] == len(manifest["slots"]),
            "missing_or_unexecuted_ids": [slot["trial"]["id"] for slot in manifest["slots"] if slot["status"] == "PENDING"],
            "failed_or_interrupted_ids": [slot["trial"]["id"] for slot in manifest["slots"] if slot["status"] in {"FAIL", "INTERRUPTED"}],
            "scope_note": "Flight/safety acceptance only. Physical identity labels and paired statistical analysis require their separate recorded-data pipeline."}


def execute(manifest: dict[str, Any], output: Path, *, root: Path = ROOT, stop_after: int = 0,
            only_stage: int | None = None, only_class: str | None = None,
            only_scenario: str | None = None,
            runner: Callable[..., Any] = subprocess.run) -> None:
    """Blocking serial command execution: evaluations finish before next flight."""
    def save():
        manifest["updated_utc"] = utc_now()
        write_json(output / "manifest.json", manifest)
        write_json(output / "summary.json", summarize(manifest))

    # A crash can leave either running state persisted. Retain it, do not
    # overwrite its trial directory or silently count it as completed.
    for slot in manifest["slots"]:
        if slot["status"] in {"RUNNING_FLIGHT", "RUNNING_EVALUATION"}:
            slot.update(status="INTERRUPTED", error="Previous matrix process ended before this slot completed")
    save()
    executed = 0
    for slot in manifest["slots"]:
        trial = slot["trial"]
        if (slot["status"] != "PENDING" or (only_stage is not None and trial["stage"] != only_stage)
                or (only_class is not None and trial["target_class"] != only_class)):
            continue
        if only_scenario is not None and trial["scenario"] != only_scenario:
            continue
        if stop_after and executed >= stop_after:
            break
        executed += 1
        directory = root / "results" / trial["name"]
        slot.update(started_utc=utc_now(), status="RUNNING_FLIGHT", commands=[], evaluations=[])
        save()
        if directory.exists():
            slot.update(status="FAIL", error="Planned trial directory already exists; refusing to overwrite or adopt unrecorded evidence", finished_utc=utc_now())
            save()
            continue

        def command_run(kind, command):
            record = {"kind": kind, "argv": command, "started_utc": utc_now(), "returncode": None}
            slot["commands"].append(record)
            save()
            path = output / "logs" / f"{trial['id']}_{kind}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("x", encoding="utf-8") as log:
                    process = runner(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=False)
                record["returncode"] = process.returncode
            except (OSError, subprocess.SubprocessError) as error:
                record["error"] = str(error)
            record["finished_utc"] = utc_now()
            record["log"] = str(path)
            save()
            return record.get("returncode")

        try:
            code = command_run("sitl", flight_command(trial, root=root,
                               wall_timeout=manifest["protocol"]["wall_timeout_s"],
                               render_backend=manifest["protocol"]["render_backend"]))
            infrastructure=classify_infrastructure_failure(directory)
            slot["infrastructure_failure"]=infrastructure
            if infrastructure["stop"]:
                slot["evaluations"].append({"kind":"infrastructure","result":"MISSING","error":"Required simulation/vehicle qualification evidence unavailable; see infrastructure_failure"})
                slot.update(status="FAIL",error="Infrastructure qualification failed; remaining planned slots retained pending",finished_utc=utc_now())
                save()
                break
            # Even a failed flight can have a useful partial bag. Evaluation
            # failures are retained independently, then the matrix continues.
            slot["status"] = "RUNNING_EVALUATION"
            save()
            if (directory / "rosbag" / "metadata.yaml").is_file():
                for kind, command, report_path in evaluation_commands(trial, root=root):
                    eval_code = command_run(kind, command)
                    outcome, error = report_outcome(report_path, kind)
                    slot["evaluations"].append({"kind": kind, "returncode": eval_code,
                                                "result": outcome, "error": error, "report": str(report_path)})
                    save()
            else:
                slot["evaluations"].append({"kind": "all", "result": "MISSING", "error": "No readable bag metadata"})
            # A bag may have complete metadata but unreadable core messages.
            # Only explicit input evidence triggers the infrastructure guard;
            # algorithm/evaluation FAIL results continue to the next slot.
            infrastructure=classify_infrastructure_failure(directory)
            slot["infrastructure_failure"]=infrastructure
            if infrastructure["stop"]:
                slot.update(status="FAIL",error="Evaluator exposed unavailable core recording evidence; remaining planned slots retained pending",finished_utc=utc_now())
                save()
                break
            expected = 2 if trial["stage"] == 3 else 1
            slot["status"] = "PASS" if (code == 0 and len(slot["evaluations"]) == expected
                and all(row["result"] == "PASS" and row.get("returncode") == 0 for row in slot["evaluations"])) else "FAIL"
            slot["finished_utc"] = utc_now()
            save()
        except KeyboardInterrupt:
            slot.update(status="INTERRUPTED", error="KeyboardInterrupt; no automatic retry", finished_utc=utc_now())
            save()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/stage23_matrix")
    parser.add_argument("--prefix", default="stage23_research_v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--wall-timeout", type=float, default=300.)
    parser.add_argument("--render-backend", choices=["egl", "wslg"], default="egl")
    parser.add_argument("--real-time-factor", type=float, default=1.)
    parser.add_argument("--car-image-size", type=int, default=480)
    parser.add_argument("--car-threads", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--stop-after", type=int, default=0, help="Maximum new flights this invocation; zero means all pending")
    parser.add_argument("--only-stage", type=int, choices=[2, 3])
    parser.add_argument("--only-class", choices=["person", "car"])
    parser.add_argument("--only-scenario", choices=["crossing", "parallel", "ambiguity", "auto_unique", "gimbal"])
    parser.add_argument("--evaluate-auto-unique", type=Path, metavar="BAG", help=argparse.SUPPRESS)
    parser.add_argument("--target-class", choices=["person", "car"], default="person", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.evaluate_auto_unique:
        import evaluate_stage1_flight as base
        base.TOPICS = tuple(dict.fromkeys(base.TOPICS + ("/tracking/tracks",)))
        records, metadata = base.read_rosbag(args.evaluate_auto_unique)
        report = evaluate_auto_unique(records, metadata, args.target_class)
        write_json(args.output, report)
        print(json.dumps({"result": report["result"], "checks": report["checks"]}))
        return 0 if report["result"] == "PASS" else 2
    if args.stop_after < 0 or not math.isfinite(args.wall_timeout) or args.wall_timeout <= 0:
        parser.error("stop-after must be nonnegative and wall-timeout positive/finite")
    try:
        planned = plan_trials(args.prefix, args.seeds, real_time_factor=args.real_time_factor,
                              car_image_size=args.car_image_size, car_threads=args.car_threads)
    except ValueError as error:
        parser.error(str(error))
    protocol = {"prefix": args.prefix, "seeds": args.seeds, "wall_timeout_s": args.wall_timeout,
                "render_backend": args.render_backend, "no_automatic_retries": True,
                "stage3_reselect_after_loss": True, "evaluators_run_after_flight_serially": True,
                "resources": {"real_time_factor": args.real_time_factor,
                              "person_inference_image_size": 320, "person_inference_threads": 2,
                              "car_inference_image_size": args.car_image_size, "car_inference_threads": args.car_threads}}
    frozen = json.dumps({"protocol": protocol, "trials": planned}, sort_keys=True, separators=(",", ":"))
    plan_hash = hashlib.sha256(frozen.encode()).hexdigest()
    manifest_path = args.output / "manifest.json"
    if manifest_path.exists():
        if not args.resume:
            parser.error("manifest already exists; use --resume to continue pending slots")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["plan_sha256"] != plan_hash:
            parser.error("requested configuration differs from frozen protocol; use a new prefix/output")
    else:
        if args.resume:
            parser.error("cannot resume without an existing manifest")
        manifest = {"schema_version": 1, "created_utc": utc_now(), "plan_sha256": plan_hash,
                    "protocol": protocol, "slots": [{"trial": trial, "status": "PENDING"} for trial in planned]}
        write_json(manifest_path, manifest)
        write_json(args.output / "summary.json", summarize(manifest))
    if not args.plan_only:
        execute(manifest, args.output, stop_after=args.stop_after,
                only_stage=args.only_stage, only_class=args.only_class, only_scenario=args.only_scenario)
    summary = summarize(manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if summary["failed_or_interrupted_ids"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
