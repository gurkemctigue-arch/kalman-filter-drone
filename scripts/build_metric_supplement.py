"""Expose metrics already computed in per-flight JSON; never opens ROS bags.

Standard library only. Optional derived state JSONL gives prediction error
inside requested SHORT shutter windows; ordinary timer predictions alone
must not be mislabeled as occlusion samples. Main 166 and engineering 16
remain separate, and frame/window counts never become independent repeats.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}
SPECS = (
    ("online_position_rmse_m", "在线锚点位置 RMSE / m", "online", "online_state_accuracy.metrics.state_stamp_position_error_m.rmse"),
    ("online_position_p95_m", "逐飞行在线锚点位置误差 p95 / m", "online", "online_state_accuracy.metrics.state_stamp_position_error_m.p95"),
    ("online_velocity_rmse_mps", "在线锚点速度 RMSE / m/s", "online", "online_state_accuracy.metrics.state_stamp_velocity_error_mps.rmse"),
    ("online_velocity_p95_mps", "逐飞行在线锚点速度误差 p95 / m/s", "online", "online_state_accuracy.metrics.state_stamp_velocity_error_mps.p95"),
    ("receipt_position_rmse_m", "接收时刻锚点位置 RMSE / m", "online", "online_state_accuracy.metrics.receipt_clock_position_error_m.rmse"),
    ("receipt_velocity_rmse_mps", "接收时刻锚点速度 RMSE / m/s", "online", "online_state_accuracy.metrics.receipt_clock_velocity_error_mps.rmse"),
    ("state_available_fraction", "全部状态机会中的有效状态比例", "online", "online_state_accuracy.active_coverage"),
    ("position_reference_fraction", "全部状态机会中的位置参考覆盖率", "online", "online_state_accuracy.position_reference_coverage"),
    ("velocity_command_jitter_rms_mps2", "速度命令变化率 RMS / m/s²", "online", "control_jitter.velocity_command_delta_over_dt_mps2.rmse"),
    ("yaw_command_jitter_rms_radps2", "偏航角速度命令变化率 RMS / rad/s²", "online", "control_jitter.yaw_rate_delta_over_dt_radps2.rmse"),
    ("detector_processed_sim_fps", "处理帧率 / 仿真 s（非墙钟 FPS）", "basic", "detector.processed_fps_in_sim_time"),
    ("detector_inference_wall_mean_s", "纯推理墙钟时间均值 / s", "basic", "detector.inference_wall_s.mean"),
    ("detector_inference_wall_p95_s", "逐飞行纯推理墙钟时间 p95 / s", "basic", "detector.inference_wall_s.p95"),
    ("image_to_detector_sim_mean_s", "图像至检测完成延迟均值 / 仿真 s", "basic", "detector.acquisition_to_completed_sim_latency_s.mean"),
    ("image_to_detector_sim_p95_s", "逐飞行图像至检测完成延迟 p95 / 仿真 s", "basic", "detector.acquisition_to_completed_sim_latency_s.p95"),
    ("whole_distance_rmse_m", "整段模型原点距离 RMSE / m", "dynamics", "whole_interval.distance_error_m.rmse"),
    ("whole_height_rmse_m", "整段模型原点高度 RMSE / m", "dynamics", "whole_interval.height_error_m.rmse"),
    ("image_center_rmse_px", "检测条件下画面中心 RMSE / px", "dynamics", "visual_control_metrics.detected_center_error_px.rmse"),
    ("image_center_p95_px", "逐飞行检测条件下画面中心误差 p95 / px", "dynamics", "visual_control_metrics.detected_center_error_px.p95"),
    ("image_center_observed_fraction", "全部检测机会中的中心观测覆盖率", "dynamics", "visual_control_metrics.observed_center_coverage"),
    ("image_to_first_command_sim_mean_s", "图像至首跟踪命令延迟均值 / 仿真 s", "dynamics", "visual_control_metrics.image_to_first_tracking_command_sim_s.mean"),
    ("image_to_first_command_sim_p95_s", "逐飞行图像至首跟踪命令延迟 p95 / 仿真 s", "dynamics", "visual_control_metrics.image_to_first_tracking_command_sim_s.p95"),
    ("physical_retention_lower_bound", "保守物理身份保持下界（非UUID连续率）", "physical", "conservative_selected_identity.retention_lower_bound"),
    ("physical_identity_known_fraction", "保守物理身份已知覆盖率", "physical", "conservative_selected_identity.known_coverage"),
    ("requested_identity_correct_all_opportunities", "请求个体全部任务机会 CORRECT 比例", "physical", "selected_physical_identity_all.correct_fraction_all_task_opportunities"),
)
LABELS = {key: label for key, label, _, _ in SPECS}
LABELS.update({
    "initial_distance_overshoot_m": "初始距离反侧超调 / m",
    "initial_height_overshoot_m": "初始高度反侧超调 / m",
    "initial_distance_settling_s": "仅已稳定的初始距离稳定时间 / s",
    "initial_height_settling_s": "仅已稳定的初始高度稳定时间 / s",
    "explicit_selection_confirmation_fraction": "显式新任务重选确认比例（非ReID）",
    "explicit_selection_confirmation_mean_s": "已确认显式重选任务时间均值 / s（非ReID）",
    "short_post_open_measured_recovery_fraction": "短遮挡开幕后测量恢复观测比例（含身份未知）",
    "short_same_task_identity_preserved_fraction": "已观测恢复且身份检查已知条件下原轨迹/任务保持比例",
    "short_same_task_recovery_mean_s": "原轨迹/任务保持的短遮挡恢复时间均值 / 仿真 s",
    "short_same_task_recovery_p95_s": "逐飞行原轨迹/任务保持的短遮挡恢复时间 p95 / 仿真 s",
    "short_shutter_predicted_position_rmse_m": "短快门请求窗内 PREDICTED 锚点位置 RMSE / m",
    "short_shutter_predicted_position_p95_m": "短快门请求窗内 PREDICTED 锚点位置误差 p95 / m",
    "short_shutter_predicted_velocity_rmse_mps": "短快门请求窗内 PREDICTED 锚点速度 RMSE / m/s",
})
SHORT_RECOVERY_COUNT_KEYS = (
    "short_requested_windows", "observed_recovery_windows", "same_track_and_task_confirmed_windows",
    "changed_track_or_task_windows", "unknown_identity_on_observed_recovery_windows",
    "unobserved_or_untimed_recovery_windows", "identity_flag_without_valid_timing_windows",
    "conditional_identity_denominator_windows",
)
SHORT_RECOVERY_DEFINITION = (
    "Saved SHORT requested-shutter windows only. recovery_after_open_s uses the evaluator's post-open "
    "measured state with source/receive simulation timestamps. identity_preserved_on_observed_recovery "
    "checks the original track_id AND target_uuid, not independent physical identity. Timing conditions "
    "on observed recovery and that check being true; the identity fraction conditions on observed recovery "
    "with a known boolean identity check. Unknown/missing evidence remains separate. This is neither "
    "explicit new-UUID reselection nor long-absence automatic ReID; windows are not independent flights."
)
for subset in ("amodal_simulation_mot", "unoccluded_geometry_mot"):
    for metric in ("hota", "idf1", "id_switches"):
        LABELS[f"task_mean_{subset}_{metric}"] = f"先任务均值再按飞行统计：{subset}/{metric}"


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def mapping(value):
    return value if isinstance(value, dict) else {}


def object_rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def field(data, path):
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data if finite(data) else None


def stats(values):
    all_values = list(values)
    values = sorted(value for value in all_values if finite(value))
    return {"flight_slots": len(all_values), "valid_flights": len(values), "missing_flights": len(all_values) - len(values),
            "mean": statistics.mean(values) if values else None,
            "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
            "median": statistics.median(values) if values else None}


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * fraction
    return ordered[math.floor(index)] + (ordered[math.ceil(index)] - ordered[math.floor(index)]) * (index - math.floor(index))


class Reader:
    def __init__(self):
        self.sources = []

    def json(self, path, *, required=False):
        path = Path(path)
        item = {"path": str(path.resolve()), "exists": path.is_file()}
        self.sources.append(item)
        if not item["exists"]:
            if required:
                raise ValueError("Required JSON missing: " + str(path))
            return {}
        if path.suffix != ".json" or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Expected a small JSON source: " + str(path))
        raw = path.read_bytes()
        item.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        def invalid(value):
            raise ValueError("Non-finite JSON token: " + value)
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=invalid)
        if not isinstance(data, dict):
            raise ValueError("Expected object: " + str(path))
        return data


def short_prediction_metrics(path, windows, sources):
    usable = [window for window in object_rows(windows) if window.get("kind") == "short"
              and finite(window.get("start_s")) and finite(window.get("end_s"))
              and window["end_s"] > window["start_s"]]
    counts = {"short_requested_windows": len(usable), "state_opportunities": 0,
              "predicted_state_opportunities": 0, "position_reference_samples": 0, "velocity_reference_samples": 0}
    item = {"path": str(path.resolve()), "exists": path.is_file()}
    sources.append(item)
    if not path.is_file() or not usable:
        return {}, {**counts, "evidence_status": "MISSING_STATE_SIDECAR" if not path.is_file() else "NO_SHORT_REQUESTED_WINDOW"}
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("State sidecar unexpectedly exceeds 64 MiB: " + str(path))
    positions, velocities = [], []
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for raw in handle:
            digest.update(raw)
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError("State sidecar row must be a JSON object: " + str(path))
            timestamp = row.get("time_s")
            if not finite(timestamp) or not any(window["start_s"] <= timestamp <= window["end_s"] for window in usable):
                continue
            counts["state_opportunities"] += 1
            if row.get("state") != 2 or not finite(row.get("prediction_age_s")) or not 0 <= row["prediction_age_s"] <= .75:
                continue
            counts["predicted_state_opportunities"] += 1
            if finite(row.get("state_stamp_position_error_m")):
                positions.append(row["state_stamp_position_error_m"])
            if finite(row.get("state_stamp_velocity_error_mps")):
                velocities.append(row["state_stamp_velocity_error_mps"])
    item.update(bytes=path.stat().st_size, sha256=digest.hexdigest())
    counts.update(position_reference_samples=len(positions), velocity_reference_samples=len(velocities),
                  evidence_status="RECORDED_CONDITIONAL_ON_REQUEST_WINDOW_AND_PREDICTED_STATE")
    return {"short_shutter_predicted_position_rmse_m": math.sqrt(statistics.mean(x * x for x in positions)) if positions else None,
            "short_shutter_predicted_position_p95_m": percentile(positions, .95),
            "short_shutter_predicted_velocity_rmse_mps": math.sqrt(statistics.mean(x * x for x in velocities)) if velocities else None}, counts


def short_same_task_recovery(basic):
    """Expose saved lifecycle continuity without inventing physical identity."""
    metrics = {name: None for name in (
        "short_post_open_measured_recovery_fraction", "short_same_task_identity_preserved_fraction",
        "short_same_task_recovery_mean_s", "short_same_task_recovery_p95_s")}
    evidence = {key: None for key in SHORT_RECOVERY_COUNT_KEYS}
    evidence.update(definition=SHORT_RECOVERY_DEFINITION, windows=[],
                    source_report_result=basic.get("result", mapping(basic.get("acceptance")).get("result")))
    raw = basic.get("occlusions")
    if not isinstance(raw, list) or any(not isinstance(window, dict) for window in raw):
        evidence["evidence_status"] = "MISSING_OR_INVALID_OCCLUSION_REPORT"
        return metrics, evidence
    windows = [window for window in raw if window.get("kind") == "short"]
    counts = dict.fromkeys(SHORT_RECOVERY_COUNT_KEYS, 0)
    counts["short_requested_windows"] = len(windows)
    same_task_latencies = []
    for window in windows:
        latency = field(window, "recovery_after_open_s")
        latency = latency if latency is not None and latency >= 0 else None
        raw_identity = mapping(window.get("checks")).get("identity_preserved_on_observed_recovery")
        identity = raw_identity if type(raw_identity) is bool else None
        observed = latency is not None
        evidence["windows"].append({
            "start_s": field(window, "start_s"), "end_s": field(window, "end_s"),
            "result": window.get("result"), "recovery_after_open_s": latency,
            "identity_preserved_on_observed_recovery": identity,
            "recovery_observed": observed,
        })
        if not observed:
            counts["unobserved_or_untimed_recovery_windows"] += 1
            counts["identity_flag_without_valid_timing_windows"] += identity is not None
            continue
        counts["observed_recovery_windows"] += 1
        if identity is None:
            counts["unknown_identity_on_observed_recovery_windows"] += 1
        else:
            counts["conditional_identity_denominator_windows"] += 1
            if identity:
                counts["same_track_and_task_confirmed_windows"] += 1
                same_task_latencies.append(latency)
            else:
                counts["changed_track_or_task_windows"] += 1
    evidence.update(counts)
    evidence["evidence_status"] = "RECORDED_SHORT_WINDOW_CONDITIONAL_EVIDENCE" if windows else "NO_SHORT_REQUESTED_WINDOW_RECORDED"
    if windows:
        metrics["short_post_open_measured_recovery_fraction"] = counts["observed_recovery_windows"] / len(windows)
    denominator = counts["conditional_identity_denominator_windows"]
    if denominator:
        metrics["short_same_task_identity_preserved_fraction"] = counts["same_track_and_task_confirmed_windows"] / denominator
    if same_task_latencies:
        metrics["short_same_task_recovery_mean_s"] = statistics.mean(same_task_latencies)
        metrics["short_same_task_recovery_p95_s"] = percentile(same_task_latencies, .95)
    return metrics, evidence


def group_short_same_task_recovery(flights):
    evidence = [mapping(row.get("short_same_task_recovery_evidence")) for row in flights]
    available = [row for row in evidence if type(row.get("short_requested_windows")) is int]
    result = {key: sum(row[key] for row in available) if available else None for key in SHORT_RECOVERY_COUNT_KEYS}
    result.update(listed_flights=len(flights), flights_with_occlusion_reports=len(available),
                  flights_with_short_windows=sum(row["short_requested_windows"] > 0 for row in available),
                  flights_missing_or_nonterminal=len(flights) - len(available),
                  evidence_status_counts=dict(Counter(row.get("evidence_status", "NONTERMINAL_OR_MISSING") for row in evidence)),
                  definition=SHORT_RECOVERY_DEFINITION)
    windows, known = result["short_requested_windows"], result["conditional_identity_denominator_windows"]
    result["pooled_observed_recovery_fraction"] = result["observed_recovery_windows"] / windows if windows else None
    result["pooled_identity_preserved_fraction_given_observed_known_identity"] = result["same_track_and_task_confirmed_windows"] / known if known else None
    return result


def mot_metric(task, subset, key):
    report = mapping(mapping(task).get(subset))
    frames, gt, predictions = (field(report, name) for name in ("frames", "gt_detections", "predicted_detections"))
    if frames is None or frames <= 0 or gt is None or predictions is None or gt < 0 or predictions < 0 or gt + predictions <= 0:
        return None
    return field(report, key)


def metric_evidence_status(flight, metric, include_state_frames):
    if flight.get("result") not in TERMINAL:
        return "NONTERMINAL"
    physical = metric.startswith("task_mean_") or any(key == metric and family == "physical" for key, _, family, _ in SPECS)
    if physical and (flight.get("stage") != 2 or flight.get("scenario") == "auto_unique"):
        return "NOT_APPLICABLE_NO_SELECTED_PHYSICAL_IDENTITY_TASK"
    if "report_files" not in flight:
        return "MISSING_FLIGHT_DIRECTORY"
    if metric.startswith("short_shutter_predicted_") and not include_state_frames:
        return "NOT_REQUESTED_STATE_SIDECAR"
    if metric.startswith(("short_same_task_", "short_shutter_predicted_")) or metric == "short_post_open_measured_recovery_fraction":
        evidence = mapping(flight.get("short_same_task_recovery_evidence"))
        if evidence.get("evidence_status") == "NO_SHORT_REQUESTED_WINDOW_RECORDED":
            return "NOT_APPLICABLE_NO_SHORT_REQUESTED_WINDOW"
        if evidence.get("evidence_status") == "MISSING_OR_INVALID_OCCLUSION_REPORT":
            return "MISSING_OR_INVALID_BASIC_REPORT"
    if finite(flight["metrics"].get(metric)):
        return "RECORDED"
    return "MISSING_OR_UNOBSERVED_CONDITIONAL_EVIDENCE"


def extract_metrics(reports):
    metrics = {key: field(reports[family], path) for key, _, family, path in SPECS}
    dynamics = reports["dynamics"]
    windows = object_rows(dynamics.get("windows"))
    initial = next((window for window in windows if window.get("kind") == "initial_follow_before_first_shutter"), {})
    censoring = {}
    for axis in ("distance", "height"):
        value = mapping(initial.get(axis))
        flag = value.get("settling_right_censored")
        censoring[axis] = "RIGHT_CENSORED" if flag is True else "OBSERVED_SETTLED" if flag is False else "MISSING_WINDOW"
        metrics[f"initial_{axis}_overshoot_m"] = field(value, "opposite_side_overshoot_m")
        metrics[f"initial_{axis}_settling_s"] = field(value, "settling_time_s") if flag is False else None
    selections = [window for window in windows if window.get("kind") == "explicit_selection"]
    latencies = [window.get("first_measured_confirmation_after_request_s") for window in selections]
    observed = [value for value in latencies if finite(value) and value >= 0]
    recovery = {"explicit_selection_windows": len(selections), "observed_confirmation_windows": len(observed),
                "confirmation_censored": sum(window.get("confirmation_censored") is True for window in selections),
                "missing_confirmation_status": sum(type(window.get("confirmation_censored")) is not bool for window in selections),
                "definition": "Confirmation of an explicit new task UUID; not automatic recognition of the original physical actor"}
    metrics["explicit_selection_confirmation_fraction"] = len(observed) / len(selections) if selections else None
    metrics["explicit_selection_confirmation_mean_s"] = statistics.mean(observed) if observed else None
    identity_counts = mapping(mapping(reports["physical"].get("selected_physical_identity_all")).get("counts"))
    for subset in ("amodal_simulation_mot", "unoccluded_geometry_mot"):
        for key in ("hota", "idf1", "id_switches"):
            # The frozen MOT helper returns id_switches=0 on an empty input.
            # With no scored frames/detections that is no identity evidence.
            tasks = mapping(reports["physical"].get("tasks"))
            values = [mot_metric(task, subset, key) for task in tasks.values()]
            usable = [value for value in values if value is not None]
            name = f"task_mean_{subset}_{key}"
            metrics[name] = statistics.mean(usable) if usable else None
    return metrics, censoring, recovery, identity_counts


def build(summary_path, trial_root, *, engineering_manifest=None, plan_path=None, include_state_frames=False):
    reader = Reader()
    summary = reader.json(summary_path, required=True)
    if summary.get("schema_version") != 1 or summary.get("planned_flights") != 166:
        raise ValueError("Expected schema-1 explicit 166-flight main summary")
    rows = summary.get("trials", [])
    if len({row.get("name") for row in rows}) != len(rows):
        raise ValueError("Duplicate main trial names")
    if plan_path is not None:
        plan = reader.json(plan_path, required=True)
        plan_rows = plan.get("trials", [])
        if (plan.get("schema_version") != 1 or plan.get("plan_sha256") != summary.get("plan_sha256")
                or len(plan_rows) != 166 or {row.get("name") for row in plan_rows} != {row.get("name") for row in rows}):
            raise ValueError("Summary is not bound to the supplied frozen main plan")
    inputs = [("main166", row) for row in rows]
    if engineering_manifest is not None:
        extension = reader.json(engineering_manifest, required=True)
        slots = extension.get("slots", [])
        if (extension.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
                or extension.get("plan", {}).get("expected_trials") != 16 or len(slots) != 16
                or [slot.get("trial") for slot in slots] != extension.get("plan", {}).get("trials")
                or extension.get("plan_sha256") != hashlib.sha256(json.dumps(extension.get("plan"), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()):
            raise ValueError("Expected independently bound 16 engineering slots")
        inputs += [("engineering16", {**slot["trial"], "result": slot.get("status", "UNKNOWN")}) for slot in slots]
    if len({row.get("name") for _, row in inputs}) != len(inputs):
        raise ValueError("Main/engineering trial names overlap or repeat")
    flights = []
    for cohort, row in inputs:
        name = row.get("name", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,180}", name):
            raise ValueError("Invalid recorded trial name")
        output = {key: row.get(key) for key in ("name", "stage", "target_class", "command_mode", "estimator_method", "scenario", "gimbal_mode", "seed", "coverage", "condition", "result")}
        output.update(cohort=cohort, metrics={}, evidence_notes=[])
        flights.append(output)
        if row.get("result") not in TERMINAL:
            output["evidence_notes"].append("Nonterminal flight: metrics excluded; not a success or failure")
            continue
        directory = Path(trial_root) / name
        if not directory.is_dir():
            output["evidence_notes"].append("Flight result directory missing")
            continue
        if row.get("stage") == 2 and row.get("scenario") == "auto_unique":
            basic_name = "auto_unique_evaluation.json"
        else:
            basic_name = "stage2_evaluation.json" if row.get("stage") == 2 else "flight_evaluation.json" if row.get("stage") == 3 else "offline_evaluation.json"
        reports = {}
        output["report_files"] = {}
        for family, filename in (("basic", basic_name), ("online", "online_state_accuracy_v2.json"),
                                 ("dynamics", "follow_dynamics.json"), ("physical", "physical_identity.json")):
            path = directory / filename
            reports[family] = reader.json(path)
            output["report_files"][family] = next(item for item in reversed(reader.sources) if item["path"] == str(path.resolve()))
            if not path.is_file():
                output["evidence_notes"].append(f"Missing {family} report: {filename}")
            if reports[family].get("evaluation_status") == "INCOMPLETE_EVIDENCE":
                output["evidence_notes"].append(f"Incomplete {family} report: {reports[family].get('reason', 'reason unavailable')}")
        if reports["online"] and reports["online"].get("schema_version") != 2:
            reports["online"] = {}
            output["evidence_notes"].append("Online source schema is not 2; primary online metrics missing")
        if row.get("stage") == 2 and not reports["basic"].get("detector"):
            output["evidence_notes"].append("Stage-two safety JSON does not contain detector FPS/inference timing; not derivable from this JSON")
        metrics, censoring, recovery, identity_counts = extract_metrics(reports)
        output.update(metrics=metrics, settling_evidence=censoring, explicit_selection_evidence=recovery,
                      selected_physical_identity_counts=identity_counts)
        short_metrics, short_evidence = short_same_task_recovery(reports["basic"])
        metrics.update(short_metrics)
        output["short_same_task_recovery_evidence"] = short_evidence
        if include_state_frames:
            predicted, prediction_counts = short_prediction_metrics(directory / "online_state_accuracy_v2.frames.jsonl",
                                                                    reports["basic"].get("occlusions", []), reader.sources)
            metrics.update(predicted)
            output["short_shutter_prediction_evidence"] = prediction_counts
    metric_names = sorted(LABELS)
    for flight in flights:
        flight["metric_evidence_statuses"] = {
            metric: metric_evidence_status(flight, metric, include_state_frames) for metric in metric_names}
    grouped = defaultdict(list)
    for row in flights:
        label = (row.get("estimator_method") if row.get("stage") == 1 else row.get("scenario") if row.get("stage") == 2 else row.get("gimbal_mode")) or "unspecified"
        if row["cohort"] == "engineering16":
            label += "/" + str(row.get("coverage")) + "/" + str(row.get("condition"))
        key = f"{row['cohort']}/s{row.get('stage')}/{row.get('target_class')}/{row.get('command_mode')}/{label}"
        grouped[key].append(row)
    groups = {}
    for key, values in sorted(grouped.items()):
        groups[key] = {"planned_or_listed_flights": len(values), "status_counts": dict(Counter(row.get("result", "UNKNOWN") for row in values)),
                       "settling_evidence": {axis: dict(Counter(row.get("settling_evidence", {}).get(axis, "NONTERMINAL_OR_MISSING") for row in values)) for axis in ("distance", "height")},
                       "short_same_task_recovery_evidence": group_short_same_task_recovery(values),
                       "metric_evidence_status_counts": {metric: dict(Counter(row["metric_evidence_statuses"][metric] for row in values)) for metric in metric_names},
                       "metrics": {metric: stats(row["metrics"].get(metric) for row in values) for metric in metric_names}}
    return {"schema_version": 1, "source": "PER_FLIGHT_JSON_METRIC_SUPPLEMENT", "source_plan_sha256": summary.get("plan_sha256"),
            "main_planned_flights": 166, "main_listed_flights": len(rows), "engineering_listed_flights": len(inputs) - len(rows),
            "main_status_counts": dict(Counter(row.get("result", "UNKNOWN") for row in rows)),
            "all_main_flights_terminal": len(rows) == 166 and all(row.get("result") in TERMINAL for row in rows),
            "include_state_frames": include_state_frames, "metric_labels": LABELS, "groups": groups, "flights": flights,
            "sources": reader.sources, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "claim_boundary": "Main 166 and engineering 16 remain separate. Mean/SD summarize per-flight scalars, including measurable failures; per-flight p95 values are not pooled frame quantiles. Missing and nonterminal metrics are not zero. Online state references frozen calibrated visible-surface anchors with ego-only map alignment. Prediction subset uses PREDICTED states (state sidecar time_s is TargetState header simulation time) in SHORT shutter request/response windows, not independently measured rendered visibility or all timer predictions. Detector timing/FPS is simulation-clock or pure inference wall time as named, never wall end-to-end or PX4 response. Short recovery checks only original track_id and target_uuid continuity; timing and identity denominators are conditional and do not prove physical identity or automatic ReID. Explicit new-task selection is separate. Geometry identity metrics retain unknown/unobserved intervals and do not certify audited visible labels. No bag reads, inference, simulator, bootstrap or source-result writes."}


def markdown(data):
    def n(value):
        return f"{value:.6g}" if finite(value) else "缺失"
    lines = ["# 逐飞行指标补充表", "", "只引用已有逐飞行 JSON；主166与独立16不合并。以下均值±SD以整次飞行为单位；每行含有效/缺失飞行数，失败飞行有可测值时保留。逐飞行 p95 的均值不是合并帧 p95。", "",
             "在线误差为已冻结校准的可见表面锚点，非独立模型中心精度；短快门请求窗不是精确渲染可见性标签。仿真帧率、纯推理墙钟时间及图像至命令仿真延迟分别解释。显式新任务重选确认不等于原个体自动 ReID。", ""]
    for key, group in data["groups"].items():
        lines += ["## " + key, "", "状态：`" + json.dumps(group["status_counts"], ensure_ascii=False, sort_keys=True) + "`；稳定时间证据：`" + json.dumps(group["settling_evidence"], ensure_ascii=False, sort_keys=True) + "`。", "",
                  "原任务短遮挡恢复条件分母：`" + json.dumps(group["short_same_task_recovery_evidence"], ensure_ascii=False, sort_keys=True) + "`。", "",
                  "| 指标 | 有效飞行 | 缺失飞行 | 飞行均值 | 飞行间样本SD |", "| --- | --- | --- | --- | --- |"]
        for metric, value in group["metrics"].items():
            lines.append(f"| {data['metric_labels'][metric]} | {value['valid_flights']} | {value['missing_flights']} | {n(value['mean'])} | {n(value['sample_sd'])} |")
        lines.append("")
    lines += ["短遮挡恢复只检查原 track_id 与 target_uuid 连续。时间仅在观测到恢复且二者保持时统计；身份保持比例仅以已观测恢复且布尔检查已知的窗口为分母，未恢复/未知/缺失单列；不证明独立物理身份，不等于新 UUID 显式重选或完整 ReID。", "",
              "完整逐飞行值、删失/身份机会计数与输入来源 SHA 保存在同名 JSON；缺失值不等于零误差。检测 Precision/Recall/AP 继续引用独立审核的历史静态子集，不能扩展为正式166总体检测准确率。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--trial-root", type=Path, required=True)
    parser.add_argument("--engineering-manifest", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--include-state-frames", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.suffix != ".json":
            raise ValueError("--output must be .json")
        data = build(args.summary, args.trial_root, engineering_manifest=args.engineering_manifest, plan_path=args.plan, include_state_frames=args.include_state_frames)
        targets = (args.output, args.output.with_suffix(".md"), args.output.with_suffix(".csv"))
        sources = {Path(source["path"]).resolve() for source in data["sources"]}
        if any(target.exists() or target.resolve() in sources for target in targets):
            raise ValueError("Output already exists or would overwrite source evidence; use a new output name")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        args.output.with_suffix(".md").write_text(markdown(data), encoding="utf-8")
        fields = ("cohort", "name", "stage", "target_class", "command_mode", "estimator_method", "scenario", "gimbal_mode", "seed", "coverage", "condition", "result", *sorted(LABELS))
        with args.output.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows({**row, **row["metrics"]} for row in data["flights"])
        print(json.dumps({"json": str(args.output), "markdown": str(args.output.with_suffix('.md')), "listed_flights": len(data["flights"])}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
