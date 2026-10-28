"""Read existing matrix/report JSONs and bootstrap paired seed differences.

No simulation, inference, bag extraction or ROS imports are performed. Each
trial contributes one recorded summary value; frames are never treated as
independent repeats. Differences are always active minus midpoint.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def metric(name, source, path, unit, scope, direction="lower"):
    return {"name": name, "source": source, "path": path, "unit": unit, "scope": scope,
            "preferred_direction": direction}


METRICS = [
    metric("image_center_rmse", "gimbal", ["metrics", "detected_center_normalized_error", "rmse"], "normalized image distance", "Detector box centre; scope depends on recorded centering_source"),
    metric("image_center_p95", "gimbal", ["metrics", "detected_center_normalized_error", "p95_absolute"], "normalized image distance", "Detector box centre absolute 95th percentile"),
    metric("horizon_rmse_rad", "gimbal", ["metrics", "true_image_horizon_error_rad", "rmse"], "rad", "Independent Gazebo camera link pose after FOLLOW warmup"),
    metric("body_roll_rmse_rad", "gimbal", ["metrics", "true_body_roll_rad", "rmse"], "rad", "Excitation/context, not a gimbal accuracy score", None),
    metric("physics_feedback_angle_rmse_rad", "gimbal", ["geometry", "physics_link_angle_error_rad", "rmse"], "rad", "Physics link versus encoder forward kinematics"),
    metric("physics_feedback_translation_rmse_m", "gimbal", ["geometry", "physics_link_translation_error_m", "rmse"], "m", "Physics link versus encoder forward kinematics"),
    metric("tf_feedback_angle_rmse_rad", "gimbal", ["geometry", "tf_angle_error_rad", "rmse"], "rad", "Recorded dynamic TF versus source-time encoders"),
    metric("diagnostic_encoder_rmse_rad", "gimbal", ["physical_feedback", "diagnostic_encoder_error_rad", "rmse"], "rad", "Diagnostic measured angle versus raw encoder channel"),
    metric("image_time_tf_coverage", "gimbal", ["geometry", "image_timestamp_tf_coverage"], "fraction", "Images with both interpolatable dynamic TF links", "higher"),
    metric("estimated_follow_distance_rmse_m", "flight", ["controller", "estimated_horizontal_distance_error_m", "rmse"], "m", "Controller estimate during FOLLOW/PREDICT; not ground-truth accuracy"),
    metric("estimated_follow_height_rmse_m", "flight", ["controller", "estimated_height_error_m", "rmse"], "m", "Controller estimate during FOLLOW/PREDICT; not ground-truth accuracy"),
    metric("true_follow_distance_rmse_m", "flight", ["ground_truth", "active_tracking", "horizontal_distance_error_m", "rmse"], "m", "FOLLOW/PREDICT; uncorrected Gazebo model origins"),
    metric("true_follow_height_rmse_m", "flight", ["ground_truth", "active_tracking", "height_above_target_origin_error_m", "rmse"], "m", "FOLLOW/PREDICT; target model origin, not RGB-D surface"),
    metric("true_whole_interval_distance_rmse_m", "flight", ["ground_truth", "horizontal_distance_error_m", "rmse"], "m", "Entire flight evaluation interval, including loss/HOVER"),
    metric("vehicle_speed_mean_mps", "flight", ["flight_evidence", "vehicle_speed_mps", "mean"], "m/s", "Entire flight evaluation interval; not target speed error", None),
    metric("vehicle_speed_rms_mps", "flight", ["flight_evidence", "vehicle_speed_mps", "rmse"], "m/s", "RMS speed, not speed RMSE against a reference", None),
]
for axis, index in (("yaw", 0), ("pitch", 1), ("roll", 2)):
    METRICS.extend([
        metric(f"encoder_{axis}_span_rad", "gimbal", ["physical_feedback", "span_rad", index], "rad", "Real encoder range over recorded interval; not jitter", None),
        metric(f"command_encoder_{axis}_max_difference_rad", "gimbal", ["physical_feedback", "max_command_encoder_difference_rad", index], "rad", "Command/encoder physical lag evidence; not calibrated bandwidth or jitter", None),
    ])

FILES = {"flight": "flight_evaluation.json", "gimbal": "gimbal_evaluation.json",
         "stage2_safety": "stage2_evaluation.json", "auto_unique": "auto_unique_evaluation.json"}


def finite_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def value_at(report, path):
    try:
        value = report
        for key in path:
            value = value[key]
        return finite_value(value)
    except (KeyError, IndexError, TypeError):
        return None


def bootstrap_mean(differences: list[float], *, resamples: int = 10_000, seed: int = 20261027) -> dict[str, Any]:
    if resamples < 1:
        raise ValueError("bootstrap resamples must be positive")
    array = np.asarray(differences, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("bootstrap differences must be a finite vector")
    result = {"seed_pair_count": len(array), "mean_active_minus_midpoint": float(array.mean()) if len(array) else None,
              "sample_standard_deviation": float(array.std(ddof=1)) if len(array) >= 2 else None,
              "ci95_percentile": None, "bootstrap_resamples": resamples, "bootstrap_seed": seed,
              "recommended_ten_seed_pairs_met": len(array) >= 10}
    if len(array) < 2:
        result["ci_unavailable_reason"] = "At least two independent seed pairs are needed; one trial has no estimated repeat variability"
    else:
        indices = np.random.default_rng(seed).integers(0, len(array), size=(resamples, len(array)))
        means = array[indices].mean(axis=1)
        result["ci95_percentile"] = np.quantile(means, [.025, .975]).tolist()
        result["ci_unavailable_reason"] = None
    return result


def load_slot(slot: dict, project_root: Path) -> dict[str, Any]:
    trial = slot["trial"]
    expected = ["flight", "gimbal"] if trial["stage"] == 3 else [
        "auto_unique" if trial["scenario"] == "auto_unique" else "stage2_safety"]
    reports, provenance, errors = {}, {}, []
    entries = defaultdict(list)
    for entry in slot.get("evaluations", []):
        entries[entry.get("kind")].append(entry)
    for kind in expected:
        if len(entries[kind]) != 1 or not entries[kind][0].get("report"):
            errors.append({"kind": kind, "reason": "No unique report reference in this slot's evaluation record"})
            continue
        entry = entries[kind][0]
        declared = Path(entry["report"])
        relocated = project_root / "results" / trial["name"] / FILES[kind]
        path = declared if declared.is_file() else relocated
        if not path.is_file():
            errors.append({"kind": kind, "reason": "Referenced report is missing", "declared_path": str(declared)})
            continue
        try:
            raw = path.read_bytes()
            report = json.loads(raw.decode("utf-8"))
            if not isinstance(report, dict):
                raise ValueError("Report must be a JSON object")
            if report.get("schema_version") != (3 if kind == "flight" else 1):
                raise ValueError("Unsupported report schema")
            if kind == "gimbal" and report.get("mode") != trial["gimbal_mode"]:
                raise ValueError("Gimbal report mode differs from planned slot")
            if kind == "flight" and report.get("target_class") != trial["target_class"]:
                raise ValueError("Flight report class differs from planned slot")
            outcome = report["acceptance"]["result"] if kind == "flight" else report["result"]
            reports[kind] = report
            provenance[kind] = {"path": str(path), "declared_path": str(declared),
                                "sha256": hashlib.sha256(raw).hexdigest(), "outcome": outcome,
                                "evaluator_returncode": entry.get("returncode"), "relocated": path != declared}
        except (UnicodeError, OSError, KeyError, TypeError, ValueError) as error:
            errors.append({"kind": kind, "reason": str(error), "path": str(path)})
    verified_pass = (slot["status"] == "PASS" and not errors and len(reports) == len(expected)
                     and all(item["outcome"] == "PASS" and item["evaluator_returncode"] == 0 for item in provenance.values()))
    values = {spec["name"]: value_at(reports.get(spec["source"]), spec["path"]) for spec in METRICS} if trial["stage"] == 3 else {}
    return {"trial": trial, "slot_status": slot["status"], "verified_pass": verified_pass,
            "metrics": values, "report_provenance": provenance, "report_errors": errors,
            "centering_source": reports.get("gimbal", {}).get("centering_source"),
            "recorded_intervals": {kind: report.get("interval") for kind, report in reports.items()},
            "safety_checks": {kind: report.get("checks", {}) for kind, report in reports.items() if kind in {"stage2_safety", "auto_unique"}}}


def outcome_counts(rows: list[dict]) -> dict[str, Any]:
    counts = Counter(row["slot_status"] for row in rows)
    denominator = len(rows)
    failures = counts["FAIL"] + counts["INTERRUPTED"]
    return {"planned_slot_denominator": denominator, "status_counts": dict(counts),
            "failed_or_interrupted_slots": failures,
            "failure_fraction_of_all_planned_slots": failures / denominator if denominator else None,
            "verified_successes": sum(row["verified_pass"] for row in rows),
            "unverified_declared_passes": sum(row["slot_status"] == "PASS" and not row["verified_pass"] for row in rows),
            "pending_slots": counts["PENDING"],
            "running_slots": counts["RUNNING_FLIGHT"] + counts["RUNNING_EVALUATION"],
            "slots_with_unavailable_or_invalid_reports": sum(bool(row["report_errors"]) for row in rows)}


def build_report(manifest: dict[str, Any], project_root: Path, *, resamples: int = 10_000,
                 bootstrap_seed: int = 20261027) -> dict[str, Any]:
    if not isinstance(manifest.get("slots"), list):
        raise ValueError("Expected a complete matrix manifest with slots")
    rows = [load_slot(slot, project_root) for slot in manifest["slots"]]
    trial_ids = [row["trial"]["id"] for row in rows]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError("Manifest contains duplicate trial IDs")
    groups = defaultdict(list)
    for row in rows:
        trial = row["trial"]
        if trial["stage"] == 3:
            groups[(trial["target_class"], trial.get("pair_id"))].append(row)
    pairs = []
    for (category, pair_id), group in sorted(groups.items(), key=lambda item: str(item[0])):
        modes = {mode: [row for row in group if row["trial"].get("gimbal_mode") == mode]
                 for mode in ("midpoint", "active")}
        issues = []
        if not pair_id or len(group) != 2 or any(len(mode) != 1 for mode in modes.values()):
            issues.append("Exactly one planned midpoint and active slot with a nonempty pair_id are required")
        midpoint = modes["midpoint"][0] if len(modes["midpoint"]) == 1 else None
        active = modes["active"][0] if len(modes["active"]) == 1 else None
        if midpoint and active:
            ignored = {"id", "name", "gimbal_mode"}
            differing = [key for key in set(midpoint["trial"]) | set(active["trial"])
                         if key not in ignored and midpoint["trial"].get(key) != active["trial"].get(key)]
            if differing:
                issues.append("Planned pair parameters differ: " + ", ".join(sorted(differing)))
            if midpoint["centering_source"] != active["centering_source"]:
                issues.append("Recorded image-centering definitions differ")
        differences = {}
        for spec in METRICS:
            name = spec["name"]
            first = midpoint["metrics"].get(name) if midpoint else None
            second = active["metrics"].get(name) if active else None
            differences[name] = {"midpoint": first, "active": second,
                                 "active_minus_midpoint": second-first if first is not None and second is not None and not issues else None}
        pairs.append({"pair_id": pair_id, "target_class": category,
                      "seed": group[0]["trial"]["seed"], "compatible": not issues, "issues": issues,
                      "both_verified_pass": bool(midpoint and active and midpoint["verified_pass"] and active["verified_pass"]),
                      "slot_ids": [row["trial"]["id"] for row in group],
                      "slot_statuses": {row["trial"]["gimbal_mode"]: row["slot_status"] for row in group},
                      "differences": differences})
    comparisons = {}
    for category in sorted({row["trial"]["target_class"] for row in rows if row["trial"]["stage"] == 3}):
        selected = [pair for pair in pairs if pair["target_class"] == category]
        comparisons[category] = {"planned_seed_pair_denominator": len(selected), "metrics": {}}
        for spec in METRICS:
            name = spec["name"]
            cohorts = {}
            for cohort in ("all_observed_pairs", "both_successful_pairs", "failed_or_incomplete_observed_pairs"):
                included = [pair for pair in selected if pair["differences"][name]["active_minus_midpoint"] is not None
                            and (cohort == "all_observed_pairs"
                                 or (cohort == "both_successful_pairs" and pair["both_verified_pass"])
                                 or (cohort == "failed_or_incomplete_observed_pairs" and not pair["both_verified_pass"]))]
                statistics = bootstrap_mean([pair["differences"][name]["active_minus_midpoint"] for pair in included],
                                            resamples=resamples, seed=bootstrap_seed)
                statistics.update(pair_ids=[pair["pair_id"] for pair in included], seeds=[pair["seed"] for pair in included],
                                  unavailable_or_excluded_pair_count=len(selected)-len(included))
                cohorts[cohort] = statistics
            comparisons[category]["metrics"][name] = cohorts
    stage2_groups = defaultdict(list)
    stage3_groups = defaultdict(list)
    for row in rows:
        trial = row["trial"]
        if trial["stage"] == 2:
            stage2_groups[f"{trial['target_class']}/{trial['scenario']}"].append(row)
        else:
            stage3_groups[f"{trial['target_class']}/{trial['gimbal_mode']}"].append(row)
    return {"schema_version": 1, "source": "OFFLINE_STAGE23_PLANNED_SEED_PAIR_SUMMARY",
            "created_utc": datetime.now(timezone.utc).isoformat(), "plan_sha256": manifest.get("plan_sha256"),
            "bootstrap": {"resamples": resamples, "seed": bootstrap_seed, "confidence_level": .95,
                          "method": "Nonparametric percentile bootstrap of independent per-seed paired differences; mean active minus midpoint"},
            "outcomes": {"all_planned_slots": outcome_counts(rows),
                         "stage2_conditions": {key: outcome_counts(value) for key, value in sorted(stage2_groups.items())},
                         "stage3_modes": {key: outcome_counts(value) for key, value in sorted(stage3_groups.items())}},
            "metric_definitions": METRICS, "stage3_paired_comparisons": comparisons,
            "seed_pairs": pairs, "trial_measurements": rows,
            "requested_metrics_unavailable": {
                "control_command_jitter": "Current flight/gimbal JSONs contain no time-resolved command derivative or jitter summary; it cannot be reconstructed from speed RMS, joint span or maximum servo lag",
                "position_velocity_estimation_rmse": "Current flight reports leave these null without independent coordinate/measurement-anchor calibration"},
            "limitations": [
                "Failure fractions use every planned slot, including pending slots in the denominator; status counts separately expose unfinished work.",
                "All observed pairs retain available failed/partial-flight measurements. Missing outcomes are not imputed, so this is not a full intention-to-treat accuracy estimate.",
                "Both-successful results are success-conditional and must be presented with failure counts and all-observed results.",
                "Partial failed flights may have different recorded exposure; source intervals and report hashes remain in trial_measurements.",
                "Each frame summary contributes one value per trial. Ten thousand bootstrap draws do not create additional experimental repeats.",
                "Confidence intervals are unadjusted exploratory intervals across metrics; no multiple-comparison correction or p-value is claimed.",
                "Seed-dependent target speeds sample the pre-registered speed distribution; deterministic repeats do not establish generalization to arbitrary environments.",
                "Physical identity, IDF1/HOTA and detector mAP require the independent labelled-recording pipeline.",
            ]}


def save_report(report: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "statistics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "trial_measurements.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial_id", "target_class", "stage", "scenario", "seed", "gimbal_mode", "slot_status", "verified_pass", "metric", "value"])
        writer.writeheader()
        for row in report["trial_measurements"]:
            trial = row["trial"]
            for name, value in row["metrics"].items():
                writer.writerow({"trial_id": trial["id"], "target_class": trial["target_class"], "stage": trial["stage"],
                                 "scenario": trial["scenario"], "seed": trial["seed"], "gimbal_mode": trial["gimbal_mode"],
                                 "slot_status": row["slot_status"], "verified_pass": row["verified_pass"], "metric": name, "value": value})
    with (output / "seed_pair_differences.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pair_id", "target_class", "seed", "compatible", "both_verified_pass", "metric", "midpoint", "active", "active_minus_midpoint"])
        writer.writeheader()
        for pair in report["seed_pairs"]:
            for name, values in pair["differences"].items():
                writer.writerow({key: pair[key] for key in ("pair_id", "target_class", "seed", "compatible", "both_verified_pass")} | {"metric": name, **values})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=ROOT, help="Resolve recorded reports after relocating the project")
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20261027)
    args = parser.parse_args()
    if args.bootstrap_resamples < 1 or args.bootstrap_seed < 0:
        parser.error("bootstrap resamples must be positive and seed nonnegative")
    raw = args.manifest.read_bytes()
    report = build_report(json.loads(raw.decode("utf-8")), args.project_root,
                          resamples=args.bootstrap_resamples, bootstrap_seed=args.bootstrap_seed)
    report["manifest_provenance"] = {"path": str(args.manifest.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}
    save_report(report, args.output)
    print(json.dumps({"output": str(args.output), "outcomes": report["outcomes"]["all_planned_slots"],
                      "seed_pair_count": len(report["seed_pairs"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
