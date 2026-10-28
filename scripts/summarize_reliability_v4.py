"""Read-only trial-level summaries of immutable v4 core/extension plans.

No ROS, bag reader, model inference or simulator. Hash/slot verification uses
the v4 runner; finite measurements never change an engineering verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import html
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("reliability_v4_summary_runner", ROOT / "scripts/run_reliability_v4.py")
v4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v4)

# Exact current evaluator paths. No alternative visible-surface/model-origin
# metric is silently substituted when a new navigation metric is absent.
METRICS = {
    "base_link_distance_rmse_m": ("navigation", "whole_interval.metrics.base_link_distance_error_m.rmse"),
    "base_link_height_rmse_m": ("navigation", "whole_interval.metrics.base_link_height_error_m.rmse"),
    "base_link_distance_p95_m": ("navigation", "whole_interval.metrics.base_link_distance_error_m.p95"),
    "base_link_height_p95_m": ("navigation", "whole_interval.metrics.base_link_height_error_m.p95"),
    "kf_position_rmse_m": ("navigation", "kf_navigation.metrics.kf_position_error_m.rmse"),
    "kf_velocity_rmse_mps": ("navigation", "kf_navigation.metrics.kf_velocity_error_mps.rmse"),
    "kf_position_p95_m": ("navigation", "kf_navigation.metrics.kf_position_error_m.p95"),
    "kf_velocity_p95_mps": ("navigation", "kf_navigation.metrics.kf_velocity_error_mps.p95"),
    "navigation_valid_coverage": ("navigation", "kf_navigation.valid_state_coverage"),
    "navigation_position_truth_coverage": ("navigation", "kf_navigation.position_truth_coverage"),
    "navigation_velocity_truth_coverage": ("navigation", "kf_navigation.velocity_truth_coverage"),
    "detector_processed_sim_fps": ("surface_flight", "detector.processed_fps_in_sim_time"),
    "detector_inference_wall_mean_s": ("surface_flight", "detector.inference_wall_s.mean"),
    "detector_inference_wall_p95_s": ("surface_flight", "detector.inference_wall_s.p95"),
    "image_to_detector_sim_mean_s": ("surface_flight", "detector.acquisition_to_completed_sim_latency_s.mean"),
    "image_to_detector_sim_p95_s": ("surface_flight", "detector.acquisition_to_completed_sim_latency_s.p95"),
    "gimbal_detected_center_normalized_rmse": ("gimbal", "metrics.detected_center_normalized_error.rmse"),
    "gimbal_true_horizon_rmse_rad": ("gimbal", "metrics.true_image_horizon_error_rad.rmse"),
    "gimbal_image_timestamp_tf_coverage": ("gimbal", "geometry.image_timestamp_tf_coverage"),
    "gimbal_encoder_error_rmse_rad": ("gimbal", "physical_feedback.diagnostic_encoder_error_rad.rmse"),
    "physical_task_time_known_coverage": ("physical_identity", "conservative_task_time_identity.known_coverage"),
    "physical_task_time_retention_lower_bound": ("physical_identity", "conservative_task_time_identity.retention_lower_bound"),
    "physical_task_time_wrong_samples": ("physical_identity", "conservative_task_time_identity.wrong"),
    "physical_task_time_unknown_samples": ("physical_identity", "conservative_task_time_identity.unknown"),
    "physical_diagnostic_known_coverage": ("physical_identity", "conservative_selected_identity.known_coverage"),
}
for _dimension in ("distance", "height"):
    METRICS[f"base_link_{_dimension}_overshoot_m"] = (
        "navigation", f"whole_interval.transients.base_link.{_dimension}.opposite_side_overshoot_m")
EXTRA_METRICS = [f"base_link_{dimension}_settling_s" for dimension in ("distance", "height")]
EXTRA_METRICS += [f"task_mean_{subset}_{metric}" for subset in ("amodal_simulation_mot", "unoccluded_geometry_mot")
                  for metric in ("hota", "idf1", "id_switches")]
METRIC_NAMES = list(METRICS) + EXTRA_METRICS + ["physical_follow_truth_coverage"]
PAIRED_METRICS = [name for name in METRIC_NAMES if not name.endswith("_samples")]
STATUS_CATEGORY = {"INFRASTRUCTURE_ERROR": "INFRA", "INCOMPLETE_EVIDENCE": "INCOMPLETE"}


def finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def at(value, path):
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def numeric(value, path):
    item = at(value, path)
    return float(item) if finite(item) else None


def stats(values):
    values = list(values)
    available = [value for value in values if finite(value)]
    return {"n_slots": len(values), "n": len(available), "n_missing": len(values) - len(available),
            "mean": statistics.mean(available) if available else None,
            "sample_sd": statistics.stdev(available) if len(available) > 1 else None,
            "median": statistics.median(available) if available else None}


def settling(report, dimension):
    transient = at(report, f"whole_interval.transients.base_link.{dimension}")
    if not isinstance(transient, dict):
        return None, "MISSING"
    settled, censored = transient.get("settled_through_interval_end"), transient.get("settling_right_censored")
    value = transient.get("settling_time_s")
    if settled is True and censored is False and finite(value) and value >= 0:
        return float(value), "SETTLED"
    if settled is False and censored is True and value is None:
        return None, "RIGHT_CENSORED"
    return None, "INCONSISTENT"


def extract_metrics(reports):
    metrics = {name: numeric(reports.get(kind), path) for name, (kind, path) in METRICS.items()}
    for name, value in metrics.items():
        bounded = "coverage" in name or name.endswith("retention_lower_bound")
        if value is not None and (value < 0 or bounded and value > 1):
            metrics[name] = None
    censoring = {}
    for dimension in ("distance", "height"):
        metrics[f"base_link_{dimension}_settling_s"], censoring[dimension] = settling(reports.get("navigation"), dimension)
    nav = reports.get("navigation", {})
    total = numeric(nav, "whole_interval.scheduled_samples")
    matched = numeric(nav, "whole_interval.matched_truth_samples")
    metrics["physical_follow_truth_coverage"] = matched / total if total and matched is not None and 0 <= matched <= total else None
    physical = reports.get("physical_identity", {})
    tasks = physical.get("tasks", {})
    if not isinstance(tasks, dict):
        tasks = {}
    for subset in ("amodal_simulation_mot", "unoccluded_geometry_mot"):
        for metric in ("hota", "idf1", "id_switches"):
            values = []
            for task in tasks.values():
                mot = task.get(subset, {}) if isinstance(task, dict) else {}
                if (numeric(mot, "frames") or 0) <= 0:
                    continue
                # An empty geometric GT/prediction task is not evidence of zero switches.
                if (numeric(mot, "gt_detections") or 0) + (numeric(mot, "predicted_detections") or 0) <= 0:
                    continue
                value = numeric(mot, metric)
                if value is not None and value >= 0 and (metric == "id_switches" or value <= 1):
                    values.append(value)
            metrics[f"task_mean_{subset}_{metric}"] = statistics.mean(values) if values else None
    return metrics, censoring


def report_documents(plan, trial, record):
    """Read only registered, immutable, hash-bound report JSON, never loose files."""
    documents, sources, issues = {}, [], []
    expected = {item["kind"]: item for item in trial["evaluations"]}
    entries = record.get("evaluations", [])
    if not isinstance(entries, list):
        raise ValueError("Malformed terminal evaluator records")
    seen = set()
    for entry in entries:
        kind = entry.get("kind")
        if kind in seen or kind not in expected:
            raise ValueError("Duplicate/unexpected immutable evaluator kind: " + str(kind))
        seen.add(kind)
        if entry.get("error") or not entry.get("report_sha256"):
            issues.append({"kind": kind, "reason": entry.get("error") or "MISSING_BOUND_REPORT", "result": entry.get("result")})
            continue
        path = Path(entry.get("report", ""))
        if path.resolve() != Path(expected[kind]["report"]).resolve() or path.suffix.lower() != ".json":
            raise ValueError("Evaluator report is not the frozen trial report")
        try:
            relative = path.resolve().relative_to(Path(trial["directory"]).resolve()).as_posix()
        except ValueError as error:
            raise ValueError("Evaluator report escapes trial directory") from error
        actual = v4.sha(path)
        # Runner records use platform-native relative keys; accept the exact
        # native spelling too, without weakening the path/content binding.
        native_relative = str(path.resolve().relative_to(Path(trial["directory"]).resolve()))
        archived = record.get("artifact_hashes", {}).get(relative, record.get("artifact_hashes", {}).get(native_relative))
        if actual != entry["report_sha256"] or actual != archived:
            raise ValueError("Evaluator report/terminal artifact SHA256 changed")
        report = v4.load(path)
        expected_schema = 3 if kind in {"surface_flight", "gimbal"} else 1
        if type(report.get("schema_version")) is not int or report["schema_version"] != expected_schema:
            issues.append({"kind": kind, "reason": "UNSUPPORTED_REPORT_SCHEMA"})
            continue
        # read_evaluation independently checks trial binding, verdict/return
        # code, and provenance-bearing source/native reports against this plan.
        checked = v4.read_evaluation(expected[kind], entry.get("execution", {}), plan)
        if checked.get("error") or checked.get("result") != entry.get("result"):
            issues.append({"kind": kind, "reason": checked.get("error") or "RECORDED_VERDICT_DISAGREES"})
            continue
        documents[kind] = report
        sources.append({"kind": kind, "path": str(path.resolve()), "sha256": actual})
    for kind in expected.keys() - seen:
        issues.append({"kind": kind, "reason": "NO_IMMUTABLE_EVALUATOR_ENTRY"})
    return documents, sources, issues


def read_cohort(path, cohort):
    path = Path(path).resolve(strict=True)
    plan = v4.load(path)
    v4.validate_plan(plan, path)
    extension = plan["mode"].startswith("EXTENSION_")
    if extension != (cohort == "extension"):
        raise ValueError("Core/extension plan assigned to the wrong cohort")
    records = v4.read_slots(plan)
    rows, source_files = [], [{"path": str(path), "sha256": v4.sha(path), "kind": "plan"}]
    for trial in plan["trials"]:
        record = records[trial["id"]]
        status = record["status"]
        reports, sources, issues = ({}, [], [])
        if status in v4.TERMINAL:
            reports, sources, issues = report_documents(plan, trial, record)
            record_file = v4.record_path(plan, trial)
            source_files.append({"path": str(record_file.resolve()), "sha256": v4.sha(record_file), "kind": "slot"})
        elif status == "RUNNING":
            marker = v4.record_path(plan, trial, "started.json")
            source_files.append({"path": str(marker.resolve()), "sha256": v4.sha(marker), "kind": "running_marker"})
        metrics, censoring = extract_metrics(reports)
        evaluation_status = {kind: report.get("evaluation_status", at(report, "acceptance.result") if kind == "surface_flight" else report.get("result"))
                             for kind, report in reports.items()}
        rows.append({"cohort": cohort, "slot_id": trial["id"], "name": trial["name"],
            "target_class": trial["target_class"], "seed": trial["seed"], "group": trial["group"],
            "condition": trial.get("extension_condition", plan["protocol"]["condition"]),
            "sensor_condition": trial.get("condition", plan["protocol"]["condition"]),
            "motion_profile_kind": trial.get("motion_profile_kind", plan["protocol"]["motion_profile_kind"]),
            "desired_distance_m": trial["desired_distance_m"], "command_mode": trial["command_mode"],
            "comparison_reference_id": trial.get("comparison_reference_id"),
            "status": status, "status_category": STATUS_CATEGORY.get(status, status),
            "engineering_result": record.get("engineering_result"),
            "infrastructure_stop": record.get("infrastructure_stop"), "flight_exit_code": record.get("flight_exit_code"),
            "evaluation_status": evaluation_status, "metrics": metrics, "settling": censoring,
            "report_issues": issues, "sources": sources})
        rows[-1]["required_evaluator_kinds"] = [item["kind"] for item in trial["evaluations"]]
        source_files.extend(sources)
    return plan, rows, source_files


def grouped(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["target_class"], row["group"], row["condition"])].append(row)
    return [{"cohort": key[0], "target_class": key[1], "group": key[2], "condition": key[3],
             "planned_slots": len(items), "status_counts": dict(Counter(item["status"] for item in items)),
             "status_category_counts": dict(Counter(item["status_category"] for item in items)),
             "metrics": {name: stats(item["metrics"][name] for item in items) for name in METRIC_NAMES},
             "settling": {dimension: dict(Counter(item["settling"][dimension] for item in items)) for dimension in ("distance", "height")},
             "evaluator_status_counts": {kind: dict(Counter(item["evaluation_status"].get(kind, "MISSING" if kind in item["required_evaluator_kinds"] else "NOT_APPLICABLE") for item in items))
                                         for kind in ("source_clock", "native_startup", "surface_flight", "navigation", "gimbal", "physical_identity")}}
            for key, items in sorted(groups.items())]


def paired_estimate(values, resamples, seed):
    summary = stats(values)
    finite_values = np.asarray([value for value in values if finite(value)], dtype=float)
    informative = len(finite_values) >= 2 and np.ptp(finite_values) > 1e-12
    if informative:
        indices = np.random.default_rng(seed).integers(0, len(finite_values), (resamples, len(finite_values)))
        interval = np.percentile(finite_values[indices].mean(axis=1), [2.5, 97.5]).tolist()
    else:
        interval = None
    return {**summary, "ci95": interval,
            "ci_status": "PAIRED_TRIAL_PERCENTILE_BOOTSTRAP" if informative else "INSUFFICIENT_OR_DEGENERATE_TRIAL_VARIATION"}


def paired_comparison(name, category, pairs, *, resamples, seed):
    results = {}
    for metric in PAIRED_METRICS:
        values, successful, evidence = [], [], []
        for registered_seed, left_id, right_id, left, right in pairs:
            a = left["metrics"].get(metric) if left else None
            b = right["metrics"].get(metric) if right else None
            difference = a - b if finite(a) and finite(b) else None
            both_pass = left is not None and right is not None and left["status"] == right["status"] == "PASS"
            values.append(difference)
            successful.append(difference if both_pass else None)
            evidence.append({"seed": registered_seed, "left_id": left_id, "right_id": right_id,
                             "left_status": left["status"] if left else "NOT_SCHEDULED_IN_CORE_PLAN",
                             "right_status": right["status"] if right else "NOT_SCHEDULED_IN_CORE_PLAN",
                             "difference": difference, "both_engineering_pass": both_pass})
        results[metric] = {"all_finite_pairs": paired_estimate(values, resamples, seed),
                           "both_pass_pairs": paired_estimate(successful, resamples, seed), "pairs": evidence}
    return {"comparison": name, "target_class": category, "difference_direction": "left_minus_right",
            "planned_pairs_in_matrix": len(pairs), "formal_pairs_per_condition": 10, "metrics": results}


def comparisons(core, extension, core_plan, *, resamples, seed):
    core_by_id = {row["slot_id"]: row for row in core}
    result = []
    for left_group, right_group in (("stage3_active", "stage3_midpoint"), ("stage1_position", "stage1_velocity")):
        if not {left_group, right_group} <= set(core_plan["selected_groups"]):
            continue
        for category in core_plan["selected_classes"]:
            pairs = []
            for registered_seed in core_plan["selected_seeds"]:
                left = f"{category}_{left_group}_seed{registered_seed:03d}"
                right = f"{category}_{right_group}_seed{registered_seed:03d}"
                pairs.append((registered_seed, left, right, core_by_id.get(left), core_by_id.get(right)))
            result.append(paired_comparison(left_group + "_minus_" + right_group, category, pairs, resamples=resamples, seed=seed))
    extension_groups = defaultdict(list)
    for row in extension:
        reference = core_by_id.get(row["comparison_reference_id"])
        if reference and (reference["target_class"] != row["target_class"] or reference["seed"] != row["seed"] or reference["group"] != row["group"]):
            raise ValueError("Extension comparison_reference_id does not identify the same class/seed/reference group")
        extension_groups[(row["target_class"], row["condition"])].append(
            (row["seed"], row["slot_id"], row["comparison_reference_id"], row, reference))
    for (category, condition), pairs in sorted(extension_groups.items()):
        result.append(paired_comparison("extension_" + condition + "_minus_clean_reference", category,
                                       sorted(pairs, key=lambda item: item[0]), resamples=resamples, seed=seed))
    return result


def cohort_counts(rows):
    counts = Counter(row["status"] for row in rows)
    terminal = sum(counts[state] for state in v4.TERMINAL)
    return {"planned_slots": len(rows), "terminal_slots": terminal,
            "status_counts": dict(counts), "status_category_counts": dict(Counter(row["status_category"] for row in rows)),
            "all_slots_terminal": bool(rows) and terminal == len(rows),
            "all_engineering_pass": bool(rows) and counts["PASS"] == len(rows),
            "all_required_report_documents_available": bool(rows) and terminal == len(rows) and not any(row["report_issues"] for row in rows),
            "report_issues_slots": sum(bool(row["report_issues"]) for row in rows)}


def require_reference_binding(extension_plan, core_plan, core_path):
    binding = extension_plan.get("core_reference_binding")
    if extension_plan["mode"] != "EXTENSION_FORMAL" and binding is None:
        return
    if (not isinstance(binding, dict) or Path(binding.get("path", "")).resolve() != Path(core_path).resolve()
            or binding.get("sha256") != v4.sha(Path(core_path))
            or binding.get("plan_sha256") != core_plan["plan_sha256"]
            or binding.get("reference_ids") != sorted({trial["comparison_reference_id"] for trial in extension_plan["trials"]})):
        raise ValueError("Summary core plan is not the actual frozen extension reference")


def extension_context(plan):
    protocol = at(plan, "extension_protocol_binding.protocol")
    if not isinstance(protocol, dict):
        return None
    return {"status": protocol.get("status"), "registration_utc": protocol.get("registration_utc"),
            "development_known_algorithm_failures": at(protocol, "development_readiness.evidence.known_algorithm_failures"),
            "scope": "Disclosed development failures are retained independently; never counted as formal slots or overwritten"}


def summary(core_path, extension_path=None, *, resamples=10000, seed=20261029):
    if type(resamples) is not int or not 100 <= resamples <= 100000 or type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap resamples must be 100..100000 and seed a nonnegative integer")
    core_plan, core, sources = read_cohort(core_path, "core")
    extension, extension_plan = [], None
    if extension_path is not None:
        extension_plan, extension, additional = read_cohort(extension_path, "extension")
        require_reference_binding(extension_plan, core_plan, core_path)
        for field in ("model_hashes",):
            if core_plan[field] != extension_plan[field]:
                raise ValueError("Core/extension model binding differs")
        if v4.flight_source_hashes(core_plan["source_hashes"]) != v4.flight_source_hashes(extension_plan["source_hashes"]):
            raise ValueError("Core/extension flight-critical sources differ; no paired comparison")
        if core_plan["protocol"] != extension_plan["protocol"] or any(
            core_plan[key][field] != extension_plan[key][field] for key, field in (
                ("magnetic_runtime_binding", "manifest_sha256"), ("magnetic_library_binding", "registration_sha256"))):
            raise ValueError("Core/extension protocol/runtime/renderer bindings differ")
        sources.extend(additional)
    rows = core + extension
    cohorts = {"core": {"mode": core_plan["mode"], "plan_sha256": core_plan["plan_sha256"], **cohort_counts(core)}}
    if extension_plan is not None:
        cohorts["extension"] = {"mode": extension_plan["mode"], "plan_sha256": extension_plan["plan_sha256"], **cohort_counts(extension)}
    complete = all(item["all_slots_terminal"] for item in cohorts.values())
    return {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_status": "ALL_PLANNED_SLOTS_TERMINAL" if complete else "PARTIAL_EXECUTION_RETAINED",
            "cohorts": cohorts, "all_engineering_pass": all(item["all_engineering_pass"] for item in cohorts.values()),
            "extension_registration": extension_context(extension_plan or core_plan),
            "trials": rows, "groups": grouped(rows),
            "paired_comparisons": comparisons(core, extension, core_plan, resamples=resamples, seed=seed),
            "bootstrap": {"resamples": resamples, "rng_seed": seed, "ci": .95, "unit": "paired trial/seed blocks, never image frames",
                          "scope": "Descriptive conditional intervals; finite-pair and both-PASS subsets are reported separately"},
            "sources": sources,
            "implementation_sources": {"scripts/summarize_reliability_v4.py": v4.sha(Path(__file__)),
                                       "scripts/run_reliability_v4.py": v4.sha(ROOT / "scripts/run_reliability_v4.py")},
            "claim_boundary": "Read-only snapshot of immutable slot verdicts. Terminal execution is not project acceptance or all-PASS. Missing evidence stays null; right-censored settling is not zero. Finite failed flights remain in all-finite paired results. Sim-time FPS/latency, wall inference, visible centering and physical base_link errors are distinct. HOTA/IDF1 task means are diagnostic and retain original visibility definitions; explicit reselection is not ReID. A running study is not an atomic cross-plan snapshot."}


def write_csv(path, fieldnames, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_html(report):
    esc = lambda value: html.escape(str(value))
    fmt = lambda value: "缺失" if value is None else f"{value:.5g}" if finite(value) else esc(value)
    counts = "".join(f"<li>{esc(name)} ({esc(item['mode'])}): {item['terminal_slots']}/{item['planned_slots']}终态；{esc(item['status_counts'])}</li>"
                     for name, item in report["cohorts"].items())
    table = "".join("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in (row["cohort"], row["target_class"], row["group"], row["condition"], row["seed"], row["status"]))
                    + "".join(f"<td>{fmt(row['metrics'][metric])}</td>" for metric in ("base_link_distance_rmse_m", "base_link_height_rmse_m", "kf_position_rmse_m"))
                    + f"<td>{esc(row['settling']['distance'])}</td></tr>" for row in report["trials"])
    return "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>v4结果快照</title><style>body{font:15px system-ui;margin:24px;color:#18212c}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cdd5df;padding:6px;text-align:left}th{background:#edf3fa;position:sticky;top:0}.notice{background:#fff4d1;padding:12px}</style>" \
        + f"<h1>v4结果快照：{esc(report['evaluation_status'])}</h1><p class='notice'>执行终态不等于工程全部通过。未完成槽、失败、缺失和稳定时间删失均保留；空白CSV单元表示缺失。</p><ul>{counts}</ul>" \
        + "<p><a href='summary.json'>完整JSON与证据hash</a> · <a href='trials.csv'>逐槽CSV</a> · <a href='group_metrics.csv'>分组均值/SD/缺失</a> · <a href='paired_differences.csv'>配对统计/条件区间</a> · <a href='paired_trial_differences.csv'>每seed配对差</a></p>" \
        + "<p>误差单位m；下表为独立base_link物理距离/高度与navigation KF位置。完整统计、身份/云台/检测指标和配对分母见JSON/CSV。</p><table><thead><tr>" \
        + "".join(f"<th>{label}</th>" for label in ("队列", "类别", "组", "工况", "seed", "原终态", "距离RMSE", "高度RMSE", "KF位置RMSE", "距离稳定状态")) \
        + f"</tr></thead><tbody>{table}</tbody></table><p>{esc(report['claim_boundary'])}</p></html>"


def write_report(report, output):
    output = Path(output)
    # Verify every small input used again before publishing a new snapshot.
    for source in report["sources"]:
        if v4.sha(Path(source["path"])) != source["sha256"]:
            raise ValueError("Immutable input changed during summary: " + source["path"])
    output.mkdir(parents=True, exist_ok=False)
    v4.write_new(output / "summary.json", report)
    metadata = ["cohort", "slot_id", "target_class", "seed", "group", "condition", "sensor_condition", "motion_profile_kind",
                "desired_distance_m", "command_mode", "comparison_reference_id", "status", "status_category", "engineering_result",
                "infrastructure_stop", "flight_exit_code"]
    write_csv(output / "trials.csv", metadata + METRIC_NAMES + ["distance_settling_status", "height_settling_status", "evaluator_status", "report_issues"],
              [{**{name: row.get(name) for name in metadata}, **row["metrics"],
                "distance_settling_status": row["settling"]["distance"], "height_settling_status": row["settling"]["height"],
                "evaluator_status": json.dumps(row["evaluation_status"], sort_keys=True),
                "report_issues": json.dumps(row["report_issues"], sort_keys=True)} for row in report["trials"]])
    write_csv(output / "group_metrics.csv", ["cohort", "target_class", "group", "condition", "metric", "n_slots", "n", "n_missing", "mean", "sample_sd", "median"],
              [{**{key: group[key] for key in ("cohort", "target_class", "group", "condition")}, "metric": metric, **value}
               for group in report["groups"] for metric, value in group["metrics"].items()])
    paired = []
    for comparison in report["paired_comparisons"]:
        for metric, values in comparison["metrics"].items():
            for subset in ("all_finite_pairs", "both_pass_pairs"):
                value = values[subset]
                paired.append({"comparison": comparison["comparison"], "target_class": comparison["target_class"], "metric": metric,
                               "subset": subset, "formal_pairs_per_condition": 10, **{key: value[key] for key in ("n_slots", "n", "n_missing", "mean", "sample_sd", "median", "ci_status")},
                               "ci95_low": value["ci95"][0] if value["ci95"] else None,
                               "ci95_high": value["ci95"][1] if value["ci95"] else None})
    write_csv(output / "paired_differences.csv", ["comparison", "target_class", "metric", "subset", "formal_pairs_per_condition", "n_slots", "n", "n_missing", "mean", "sample_sd", "median", "ci_status", "ci95_low", "ci95_high"], paired)
    write_csv(output / "paired_trial_differences.csv", ["comparison", "target_class", "metric", "seed", "left_id", "right_id", "left_status", "right_status", "difference", "both_engineering_pass"],
              [{"comparison": comparison["comparison"], "target_class": comparison["target_class"], "metric": metric, **pair}
               for comparison in report["paired_comparisons"] for metric, value in comparison["metrics"].items() for pair in value["pairs"]])
    (output / "index.html").write_text(render_html(report), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-plan", type=Path, required=True)
    parser.add_argument("--extension-plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-resamples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20261029)
    args = parser.parse_args(argv)
    try:
        report = summary(args.core_plan, args.extension_plan, resamples=args.bootstrap_resamples, seed=args.bootstrap_seed)
        write_report(report, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({"evaluation_status": report["evaluation_status"], "cohorts": report["cohorts"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
