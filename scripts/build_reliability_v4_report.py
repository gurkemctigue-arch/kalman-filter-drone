"""Build a source-bound v4 report/plan package; never opens ROS bags or models.

DRAFT is explicitly DEVELOPMENT_ONLY. FINAL records complete 120+160 execution,
including failures and insufficient evidence; it never means all trials passed.
Saved JSON summaries are reproduced from their original sources before use.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import summarize_reliability_v4 as snapshot  # noqa: E402
import run_estimator_replay_v4 as replay_cli  # noqa: E402
import evaluate_detection_recordings as detection_cli  # noqa: E402
from uav_tracking.research_metrics import detection_metrics  # noqa: E402
from uav_tracking.replay_comparison import (  # noqa: E402
    EXPORT_SIDECARS, canonical_sha256, paired_trial_summary, replay_trial,
    scheduled_slots, validate_registered_config,
)

KIND = "RELIABILITY_V4_DOCUMENT_PACKAGE"
TERMINAL = snapshot.v4.TERMINAL
SUMMARY_METRICS = {
    "base_link_distance_rmse_m": "物理距离RMSE / m",
    "base_link_height_rmse_m": "物理高度RMSE / m",
    "base_link_distance_p95_m": "物理距离95%绝对误差分位数 / m",
    "base_link_height_p95_m": "物理高度95%绝对误差分位数 / m",
    "base_link_distance_overshoot_m": "物理距离反向超调 / m",
    "base_link_height_overshoot_m": "物理高度反向超调 / m",
    "base_link_distance_settling_s": "已观测物理距离稳定时间 / s",
    "base_link_height_settling_s": "已观测物理高度稳定时间 / s",
    "kf_position_rmse_m": "导航位置RMSE / m",
    "kf_velocity_rmse_mps": "导航速度RMSE / m/s",
    "kf_position_p95_m": "导航位置误差p95 / m",
    "kf_velocity_p95_mps": "导航速度误差p95 / m/s",
    "velocity_command_jitter_rms_mps2": "速度命令变化率RMS / m/s²",
    "position_command_rate_rms_mps": "位置设定值变化率RMS / m/s",
    "position_command_second_difference_rms_mps2": "位置设定值二阶差分RMS / m/s²",
    "yaw_command_jitter_rms_radps2": "偏航速度命令变化率RMS / rad/s²",
    "image_center_rmse_px": "检测画面中心RMSE / px",
    "image_center_normalized_rmse": "检测画面中心归一化RMSE",
    "image_center_observed_coverage": "检测画面中心观测覆盖",
    "image_to_first_command_sim_mean_s": "图像至首条跟踪命令均值 / 仿真s",
    "image_to_first_command_sim_p95_s": "图像至首条跟踪命令p95 / 仿真s",
    "short_requested_shutter_prediction_position_rmse_m": "短遮挡请求窗预测位置RMSE / m",
    "short_requested_shutter_valid_prediction_coverage": "短遮挡请求窗有效预测覆盖",
    "short_post_open_measured_recovery_observed_fraction": "短请求窗测量恢复观察比例",
    "short_same_track_task_observed_recovery_fraction": "短请求窗同track与UUID操作层恢复观察下界",
    "short_same_track_task_recovery_fraction_given_known_recovery": "已恢复且检查已知条件下同track与UUID比例",
    "short_same_track_task_recovery_mean_s": "同track与UUID已观测操作层恢复均时 / s",
    "short_same_track_task_recovery_p95_s": "同track与UUID已观测操作层恢复p95 / s",
    "explicit_selection_observed_confirmation_fraction": "显式选框截至窗口末已观察确认比例",
    "explicit_selection_observed_confirmation_mean_s": "显式选框已确认时间均值 / s",
    "explicit_selection_observed_confirmation_p95_s": "显式选框已确认时间p95 / s",
    "navigation_valid_coverage": "导航有效覆盖",
    "physical_follow_truth_coverage": "独立物理真值覆盖",
    "detector_processed_sim_fps": "检测处理帧率 / 仿真FPS",
    "detector_inference_wall_mean_s": "检测处理链墙钟耗时均值 / s",
    "gimbal_detected_center_normalized_rmse": "画面中心归一化RMSE",
    "gimbal_true_horizon_rmse_rad": "真实地平线RMSE / rad",
    "physical_task_time_known_coverage": "完整任务身份已知覆盖",
    "physical_task_time_retention_lower_bound": "完整任务身份保持下界",
    "physical_task_time_wrong_samples": "完整任务独立物理身份错误样本数",
    "physical_task_time_unknown_samples": "完整任务独立物理身份unknown样本数",
    "task_mean_unoccluded_geometry_mot_hota": "无遮挡几何子集HOTA",
    "task_mean_unoccluded_geometry_mot_idf1": "无遮挡几何子集IDF1",
}


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    data = Path(path).read_bytes()
    if len(data) > 128 * 1024 * 1024:
        raise ValueError("JSON source exceeds 128 MiB: " + str(path))
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON " + token)))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return value


class Sources:
    def __init__(self):
        self.records = []

    def add(self, path, role, *, required=True):
        path = Path(path).resolve()
        exists = path.is_file()
        if required and not exists:
            raise ValueError("Missing source: " + str(path))
        record = {"path": str(path), "role": role, "exists": exists,
                  "bytes": path.stat().st_size if exists else None,
                  "sha256": sha(path) if exists else None}
        self.records.append(record)
        return record

    def read(self, path, role):
        self.add(path, role)
        return strict_json(path)

    def unchanged(self):
        for record in self.records:
            path = Path(record["path"])
            if path.is_file() is not record["exists"]:
                raise ValueError("Source availability changed during build: " + str(path))
            if record["exists"] and (path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]):
                raise ValueError("Source changed during build: " + str(path))


def verify_snapshot(summary_path, core_path, extension_path, sources):
    saved = sources.read(summary_path, "engineering_summary")
    if saved.get("schema_version") != 1:
        raise ValueError("Unsupported engineering summary schema")
    settings = saved["bootstrap"]
    actual = snapshot.summary(core_path, extension_path, resamples=settings["resamples"], seed=settings["rng_seed"])
    def stable(value):
        return {key: item for key, item in value.items() if key != "generated_utc"}
    if stable(saved) != stable(actual):
        raise ValueError("Engineering summary differs from immutable plan/slot/report reconstruction")
    for record in actual["sources"]:
        observed = sources.add(record["path"], "engineering_" + record["kind"])
        if observed["sha256"] != record["sha256"]:
            raise ValueError("Engineering source changed after summary verification")
    for relative, expected in actual["implementation_sources"].items():
        if sources.add(ROOT / relative, "engineering_summary_implementation")["sha256"] != expected:
            raise ValueError("Summary implementation source changed")
    return saved


def verify_replay(summary_path, manifest_path, configuration_path, sources, *, source_root=ROOT):
    """Verify saved array results, never infer or decode bags; retain missing slots."""
    saved = sources.read(summary_path, "replay_summary")
    config = sources.read(configuration_path, "replay_registration")
    validate_registered_config(config)  # Must precede opening any outcome arrays.
    provenance = replay_cli.verify_registration_artifacts(config, source_root=source_root)
    sources.add(config["freeze_requirements"]["final_engineering_plan_path"], "replay_core_plan")
    sources.add(manifest_path, "replay_input_manifest")
    if saved.get("input_manifest_file_sha256") != sha(manifest_path):
        raise ValueError("Replay input manifest changed")
    slots = replay_cli.input_manifest(manifest_path)
    missing_rows = saved.get("missing_or_invalid_inputs")
    if not isinstance(missing_rows, list):
        raise ValueError("Replay needs explicit attempted/missing terminal bookkeeping")
    missing = {}
    for item in missing_rows:
        slot, reason = item.get("slot_id"), item.get("reason")
        if slot not in slots or slot in missing or not isinstance(reason, str):
            raise ValueError("Duplicate/unknown replay missing slot")
        missing[slot] = reason
    reports, outcomes, artifacts = [], [], []
    for slot in scheduled_slots():
        report_path = Path(summary_path).parent / (slot + ".json")
        item = slots[slot]
        if report_path.is_file():
            if slot in missing or item is None:
                raise ValueError("Replay slot has both report and missing declaration")
            report = sources.read(report_path, "replay_trial_report")
            array_path = Path(item["path"])
            if sources.add(array_path, "replay_array")["sha256"] != item["sha256"]:
                raise ValueError("Replay array hash changed")
            trial = strict_json(array_path)
            receipt, audit_errors = None, []
            try:
                receipt = replay_cli.verify_export_evidence(array_path, trial, config, source_root=source_root)
            except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
                audit_errors.append(f"{type(error).__name__}:{error}")
            for filename in EXPORT_SIDECARS:
                sources.add(array_path.parent / filename, "replay_export_audit", required=False)
            rebuilt = replay_trial(trial, config, export_evidence=receipt)
            rebuilt["export_evidence_issues"].extend(audit_errors)
            rebuilt["evaluation_source"] = provenance
            rebuilt["input_file_sha256"] = item["sha256"]
            if report != rebuilt:
                raise ValueError("Saved replay result differs from bound arrays/registration/audits: " + slot)
            reports.append(report)
            artifacts.append({"slot_id": slot, "path": report_path.name, "sha256": sha(report_path)})
            outcomes.append({"slot_id": slot, "status": report["evaluation_status"],
                             "engineering_status": report["engineering_status"],
                             "common_support_met": report["common_support_requirement_met"],
                             "reason": "; ".join(report.get("export_evidence_issues", [])) or None})
        else:
            reason = missing.get(slot)
            expected = "MISSING_DECLARED" if item is None else "INCOMPLETE_OR_INVALID_INPUT:"
            if reason is None or (reason != expected if item is None else not reason.startswith(expected)):
                raise ValueError("Replay slot is unattempted or lacks an explicit terminal reason: " + slot)
            sources.add(report_path, "replay_missing_report", required=False)
            outcomes.append({"slot_id": slot, "status": "MISSING_DECLARED" if item is None else "INCOMPLETE_OR_INVALID_INPUT",
                             "engineering_status": None, "common_support_met": None, "reason": reason})
    rebuilt_summary = paired_trial_summary(reports, config)
    rebuilt_summary.update(missing_or_invalid_inputs=missing_rows, evaluation_source=provenance,
                           input_manifest_file_sha256=sha(manifest_path), trial_report_artifacts=artifacts,
                           registered_configuration_artifact={"path": "registered_configuration.json", "sha256": sha(configuration_path)})
    if saved != rebuilt_summary:
        raise ValueError("Replay summary differs from all twenty bound terminal outcomes")
    return saved, config, outcomes


def final_gate(summary, replay, config, outcomes, core_path):
    for cohort, mode, count in (("core", "FORMAL", 120), ("extension", "EXTENSION_FORMAL", 160)):
        group = summary.get("cohorts", {}).get(cohort, {})
        rows = [row for row in summary.get("trials", []) if row.get("cohort") == cohort]
        if (group.get("mode") != mode or group.get("planned_slots") != count or len(rows) != count
                or len({row["slot_id"] for row in rows}) != count
                or any(row["status"] not in TERMINAL for row in rows)
                or group.get("terminal_slots") != count or group.get("all_slots_terminal") is not True):
            raise ValueError("FINAL requires actual immutable terminal " + mode + " " + str(count) + "-slot execution")
    if (summary["bootstrap"]["resamples"] != 10000 or summary["bootstrap"]["rng_seed"] != 20261029):
        raise ValueError("FINAL bootstrap must use prospectively fixed 10000/20261029 settings")
    if replay is None or config is None or len(outcomes) != 20 or {row["slot_id"] for row in outcomes} != set(scheduled_slots()):
        raise ValueError("FINAL requires all twenty registered replay slots, including explicit missing terminals")
    if "FIXTURE" in str(config.get("evidence_scope", "")).upper():
        raise ValueError("Fixture replay registration cannot enter a FINAL report")
    freeze = config["freeze_requirements"]
    if (Path(freeze["final_engineering_plan_path"]).resolve() != Path(core_path).resolve()
            or freeze["final_engineering_plan_file_sha256"] != sha(core_path)
            or freeze["final_engineering_plan_digest"] != summary["cohorts"]["core"]["plan_sha256"]):
        raise ValueError("Replay registration is not bound to this actual core plan")


def verify_figures(path, summary_path, replay_path, sources, *, final=False):
    if path is None:
        return [], ["尚未提供新版图表manifest"]
    manifest = sources.read(path, "figures_manifest")
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "RELIABILITY_V4_FIGURES"
            or manifest.get("summary_sha256") != sha(summary_path)):
        raise ValueError("Figures do not bind this exact v4 summary")
    if final and (manifest.get("scope") == "FIXTURE_ONLY" or manifest.get("fixture_only") is True):
        raise ValueError("Fixture figures cannot enter a FINAL document")
    if manifest.get("replay_summary_sha256") is not None and (
            replay_path is None or manifest["replay_summary_sha256"] != sha(replay_path)):
        raise ValueError("Figures do not bind this exact replay summary")
    implementations = manifest.get("source_hashes")
    if not isinstance(implementations, dict) or "scripts/build_reliability_v4_figures.py" not in implementations:
        raise ValueError("Figure implementation provenance is missing")
    for relative, expected in implementations.items():
        implementation = (ROOT / relative).resolve()
        if Path(relative).is_absolute() or not implementation.is_relative_to(ROOT):
            raise ValueError("Figure implementation path escapes source root")
        if sources.add(implementation, "figure_implementation")["sha256"] != expected:
            raise ValueError("Figure implementation hash changed")
    for item in manifest.get("input_sources", []):
        if sources.add(item["path"], "figure_input")["sha256"] != item["sha256"]:
            raise ValueError("Figure input source changed")
    figures, seen = [], set()
    base = Path(path).resolve().parent
    for item in manifest.get("figures", []) + manifest.get("csv", []):
        relative = item.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError("Figure artifact needs a relative local path")
        artifact = (base / relative).resolve()
        if not artifact.is_relative_to(base) or artifact in seen:
            raise ValueError("Duplicate/escaping figure artifact")
        seen.add(artifact)
        observed = sources.add(artifact, "figure_artifact")
        if observed["sha256"] != item.get("sha256") or observed["bytes"] != item.get("bytes"):
            raise ValueError("Figure artifact changed")
        if final and item.get("scope") == "FIXTURE_ONLY":
            raise ValueError("Fixture artifact cannot enter FINAL")
        role = item.get("source_role")
        if role not in {"engineering_summary", "verified_estimator_replay", "replay"}:
            raise ValueError("Unknown figure source_role")
        if role in {"verified_estimator_replay", "replay"} and (
                replay_path is None or manifest.get("replay_summary_sha256") is None
                or strict_json(replay_path).get("complete_verified_matrix") is not True):
            raise ValueError("Replay figure has no complete verified replay source binding")
        if artifact.suffix.lower() == ".png":
            figures.append({"type": "figure", "path": str(artifact), "sha256": observed["sha256"],
                            "bytes": observed["bytes"], "caption": str(item.get("caption", artifact.name)),
                            "scope": str(item.get("scope", "范围见绘图来源"))})
    return figures, manifest.get("pending", [])


def verify_detection(report_path, review_path, sources, *, source_root=ROOT):
    """Bind reviewed static-subset metrics without inference, image decode or bag I/O."""
    report = sources.read(report_path, "detection_report")
    review = sources.read(review_path, "detection_review")
    if (report.get("schema_version") != 1 or not isinstance(report.get("recordings"), list)
            or not report["recordings"] or report.get("review_file_sha256") != sha(review_path)
            or report.get("review_file") is None
            or Path(report["review_file"]).resolve() != Path(review_path).resolve()):
        raise ValueError("Detection report must bind the actual supplied review file")
    aggregate, audited, names = [], [], set()
    for declared in report["recordings"]:
        name = Path(str(declared.get("source_trial", "")).replace("\\", "/").rstrip("/")).name
        if not name or name in {".", ".."} or name in names:
            raise ValueError("Duplicate/invalid detection recording name")
        names.add(name)
        folder = Path(report_path).resolve().parent / name
        trial_report = sources.read(folder / "detection_report.json", "detection_trial_report")
        if {key: value for key, value in trial_report.items() if key != "frames"} != declared:
            raise ValueError("Detection aggregate differs from its original trial report")
        provenance = trial_report.get("input_provenance", {})
        if (provenance.get("schema_version") != 1 or trial_report.get("prediction_cache_schema_version") != 2
                or trial_report.get("cache_provenance_sha256") != canonical_sha256(provenance)):
            raise ValueError("Detection cache provenance is missing or changed")
        recording_path = Path(provenance["recording"]["path"])
        source = sources.read(recording_path, "detection_recording_manifest")
        if (sha(recording_path) != provenance["recording"]["sha256"]
                or trial_report.get("recording_manifest_sha256") != sha(recording_path)
                or source.get("source_trial") != trial_report.get("source_trial")
                or source.get("target_class") != trial_report.get("target_class")):
            raise ValueError("Detection recording/class/source binding differs")
        configuration = provenance["inference"]
        category = source["target_class"]
        if category not in {"person", "car"}:
            raise ValueError("Unsupported detection class")
        args = detection_cli.build_parser().parse_args([str(recording_path), "--output", str(Path(report_path).parent),
            "--settings-source", configuration["settings_source"], "--" + category + "-model-path", configuration["checkpoint"],
            "--" + category + "-image-size", str(configuration["image_size"]),
            "--" + category + "-threads", str(configuration["threads"]),
            "--confidence-floor", str(configuration["confidence_floor"]), "--iou-nms", str(configuration["iou_nms"])])
        actual_configuration, evidence = detection_cli.inference_configuration(source, args, root=Path(source_root))
        rebuilt = detection_cli.input_provenance(recording_path, source, actual_configuration, evidence, root=Path(source_root))
        if rebuilt != provenance:
            raise ValueError("Detection source/model/settings/images differ from cached provenance")
        for relative, expected in provenance["source_files"].items():
            if sources.add(Path(source_root) / relative, "detection_implementation")["sha256"] != expected:
                raise ValueError("Detection implementation hash changed")
        if sources.add(configuration["checkpoint"], "detection_model")["sha256"] != configuration["checkpoint_sha256"]:
            raise ValueError("Detection model hash changed")
        def record_evidence(value):
            if isinstance(value, dict):
                if "manifest_key" in value:
                    return  # Saved logical path may be relocated; the actual model SHA was verified above.
                if "path" in value and "sha256" in value:
                    if sources.add(value["path"], "detection_saved_configuration")["sha256"] != value["sha256"]:
                        raise ValueError("Detection saved configuration changed")
                else:
                    for item in value.values():
                        record_evidence(item)
        record_evidence(evidence)
        cache_path = folder / "low_confidence_predictions.json"
        if sources.add(cache_path, "detection_prediction_cache")["sha256"] != trial_report.get("prediction_cache_sha256"):
            raise ValueError("Detection prediction cache hash changed")
        cache = strict_json(cache_path)
        if cache.get("schema_version") != 2 or cache.get("provenance") != provenance:
            raise ValueError("Detection cache has no exact schema2 provenance")
        predictions = detection_cli.load_prediction_cache(cache_path, provenance)
        binding = detection_cli.review_binding_status(review, name, provenance)
        frames, excluded = [], []
        opportunities = {item["key"]: item for item in provenance["input_images"]}
        for frame in source["frames"]:
            key = f"{frame['time_s']:.6f}"
            image = opportunities[key]
            image_path = recording_path.parent / frame["image_file"] if frame.get("image_file") else None
            if image_path is not None:
                sources.add(image_path, "detection_source_image", required=image["status"] == "PRESENT")
            if image["status"] != "PRESENT":
                excluded.append({"time_s": frame["time_s"], "reason": "selected source RGB image not recorded"})
                continue
            if not frame["eligible_geometric_subset"]:
                excluded.append({"time_s": frame["time_s"], "reason": frame["exclusion_reason"]})
                continue
            approved = binding == "BOUND" and key in review.get("approved_frames", {}).get(name, [])
            frames.append(dict(frame, pred=predictions[key], review_status="APPROVED" if approved else "PENDING"))
        approved = [frame for frame in frames if frame["review_status"] == "APPROVED"]
        expected = {"sampled_opportunities": len(source["frames"]), "geometric_eligible": len(frames),
                    "approved_eligible": len(approved), "excluded": excluded, "frames": frames,
                    "review_binding_status": binding, "reviewed_metrics": detection_metrics(approved) if approved else None,
                    "all_eligible_proposed_metrics": detection_metrics(frames),
                    "publication_status": "REVIEWED_SUBSET_ONLY" if approved else "PENDING_VISUAL_REVIEW",
                    "checkpoint": configuration["checkpoint"], "checkpoint_sha256": configuration["checkpoint_sha256"]}
        if any(trial_report.get(key) != value for key, value in expected.items()):
            raise ValueError("Detection reviewed metrics/frames/approval/denominators differ from original bound inputs")
        if any(trial_report.get("inference", {}).get(key) != value for key, value in configuration.items()):
            raise ValueError("Detection report inference declaration differs")
        aggregate.extend(approved)
        audited.append({"name": name, "target_class": category, "sampled_opportunities": len(source["frames"]),
                        "geometric_eligible": len(frames), "approved_eligible": len(approved), "excluded": len(excluded),
                        "review_binding_status": binding, "reviewed_metrics": expected["reviewed_metrics"]})
    if report.get("reviewed_aggregate") != (detection_metrics(aggregate) if aggregate else None):
        raise ValueError("Detection aggregate metrics differ from approved subset")
    return {"status": "REVIEWED_STATIC_SUBSET_ONLY" if aggregate else "PENDING_VISUAL_REVIEW",
            "recordings": audited, "reviewed_aggregate": report["reviewed_aggregate"],
            "classes_without_reviewed_frames": sorted({"person", "car"} - {row["target_class"] for row in audited if row["approved_eligible"] > 0}),
            "claim_boundary": "Reviewed fully-visible static-rendered subset only; not the overall 280-flight detector accuracy"}


def fmt(value):
    if value is None:
        return "缺失"
    if type(value) is bool:
        return "是" if value else "否"
    if snapshot.finite(value):
        return f"{value:.5g}"
    return str(value)


def paragraph(text):
    return {"type": "paragraph", "text": str(text)}


def heading(text, level=1):
    return {"type": "heading", "text": text, "level": level}


def table(headers, rows):
    return {"type": "table", "headers": headers, "rows": [[fmt(value) for value in row] for row in rows]}


def markdown_blocks(text):
    """Small, explicit plan subset; no HTML, active content or remote images."""
    blocks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"(#{1,3})\s+(.+)", line)
        if match:
            if len(match[1]) > 1:
                blocks.append(heading(match[2], len(match[1]) - 1))
        elif line.startswith("- "):
            blocks.append({"type": "bullet", "text": line[2:]})
        elif line.startswith(("<", "![", "```", "|")):
            raise ValueError("Unsupported active/complex plan Markdown; use headings, paragraphs and bullets")
        else:
            blocks.append(paragraph(line))
    return blocks


def report_blocks(summary, replay, outcomes, *, final=False, detection=None):
    blocks = [heading("结果适用范围"), paragraph(
        "本报告记录v4仿真研究。" + ("120个核心槽与160个独立扩展槽已记入终态，全部失败和缺证均保留；执行台账齐备不等于工程全部通过。" if final else
        "当前为DEVELOPMENT_ONLY开发草稿，正式实验未完成的部分保留待完成；任何示例或夹具都不构成正式结果。")),
        paragraph("算法只读取RGB-D、TF与PX4状态。真值只用于独立离线评价。surface链的置信度/深度质量自适应R与navigation的R_geometry+R_pose是两套定义；本轮四法研究比较同一录制测量下的导航状态估计，不能推断四方法的闭环控制改善。"),
        heading("执行与证据分母"), table(["队列", "模式", "计划", "终态", "工程PASS", "报告缺证槽"],
            [[name, item["mode"], item["planned_slots"], item["terminal_slots"], item["status_counts"].get("PASS", 0), item["report_issues_slots"]]
             for name, item in summary["cohorts"].items()]),
        table(["队列", "原状态", "槽数"], [[name, status, count] for name, item in summary["cohorts"].items()
                                             for status, count in sorted(item["status_counts"].items())]),
        paragraph("PENDING/RUNNING不计成功或失败；EVALUATION_PENDING虽已记入运行终态，仍代表评价尚缺。不存在的指标为缺失；FAILED但可测的飞行仍进入全部有限配对。右删失的稳定时间不能填零。"),
        heading("物理跟随、导航与覆盖")]
    for metric, label in SUMMARY_METRICS.items():
        blocks.append(heading(label, 2))
        rows = []
        for group in summary["groups"]:
            kind = snapshot.METRICS.get(metric, ("physical_identity" if metric.startswith("task_mean_") else "navigation", ""))[0]
            if metric in snapshot.RECOVERY_METRICS and metric.startswith("short_"):
                kind = "surface_flight"
            applicable = group.get("evaluator_status_counts", {}).get(kind, {})
            if applicable == {"NOT_APPLICABLE": group["planned_slots"]}:
                continue
            value = group["metrics"].get(metric)
            if not value:
                continue
            rows.append([group["cohort"], group["target_class"] + "/" + group["group"] + "/" + group["condition"],
                         f"{value['n']}/{value['n_slots']}", value["mean"], value["sample_sd"], value["median"]])
        blocks.append(table(["队列", "类别/组/工况", "有效/计划", "均值", "样本SD", "中位数"], rows) if rows else
                      paragraph("此输入没有适用组；不作为缺失或零误差。"))
    blocks += [heading("操作层恢复、显式选框与分母"), paragraph(
        "同track_id与target_uuid恢复只表示操作层连续，不能称独立物理身份重捕获或ReID；独立物理身份保持下界、错误与unknown另列。短请求窗测量恢复观察比例以全部已记录短窗为分母；同track与UUID观察下界也以全部短窗为分母。条件恢复比例仅用已观察恢复且身份检查为布尔值的窗口。未观察、时间缺失或身份未知均单列，不能当作已完整观察的失败。surface原报告没有完整恢复观察期限与连续覆盖证明，不能由空恢复时间推断失败。"),
        paragraph("以下为窗口池化原始计数；上面的均值/SD按整次飞行计算，不是池化窗口率。source缺失保留缺失，实际保存空窗口列表才计0窗。显式选框包含初始选择和重新选择；已观察确认比例分母为已确认加原报告显式右删失，缺失/不一致单列。右删失不是失败，已确认时间仅条件于实际确认，不能称长丢失自动重捕获时间。"),
        table(["队列/类别/组/工况", "短窗", "测量恢复", "同track/UUID", "已变更", "身份未知", "未观察/无时间", "检查已知分母"],
            [["/".join(str(group[key]) for key in ("cohort", "target_class", "group", "condition")),
              *[group["recovery_evidence"]["short_requested_shutter"][name] for name in (
                  "requested_windows", "observed_recovery_windows", "same_track_task_recovery_windows",
                  "changed_track_or_task_recovery_windows", "unknown_identity_on_observed_recovery_windows",
                  "unobserved_or_untimed_recovery_windows", "known_identity_on_observed_recovery_windows")]]
             for group in summary["groups"]]),
        table(["队列/类别/组/工况", "显式选框窗", "已确认", "右删失", "缺失/不一致", "已知分母"],
            [["/".join(str(group[key]) for key in ("cohort", "target_class", "group", "condition")),
              *[group["recovery_evidence"]["explicit_selection"][name] for name in (
                  "requested_windows", "observed_confirmation_windows", "confirmation_right_censored_windows",
                  "missing_or_inconsistent_windows", "classified_confirmation_windows")]]
             for group in summary["groups"]]),
        table(["队列/类别/组/工况", "短窗时间字段缺失/非法", "无有效恢复时间却有身份标志"],
            [["/".join(str(group[key]) for key in ("cohort", "target_class", "group", "condition")),
              group["recovery_evidence"]["short_requested_shutter"]["missing_or_invalid_timing_windows"],
              group["recovery_evidence"]["short_requested_shutter"]["identity_flag_without_valid_timing_windows"]]
             for group in summary["groups"]]),
        table(["队列/类别/组/工况", "窗口类型", "来源状态及飞行数"],
            [["/".join(str(group[key]) for key in ("cohort", "target_class", "group", "condition")), kind,
              "; ".join(f"{state}: {count}" for state, count in sorted(value["source_status_counts"].items()))]
             for group in summary["groups"] for kind, value in group["recovery_evidence"].items()]),
        paragraph("位置设定值变化率和二阶差分只取间隔不超过0.2 s且连续valid mode=2的命令；含有意跟随与重新选框瞬态。它们不是机体实测速度/加速度，也不是纯噪声。速度与位置控制命令分别统计。"),
        heading("稳定时间与删失"), table(["队列/类别/组/工况", "方向", "状态及槽数"],
        [["/".join(str(group[key]) for key in ("cohort", "target_class", "group", "condition")), dimension,
          "; ".join(f"{state}: {count}" for state, count in sorted(group["settling"][dimension].items()))]
         for group in summary["groups"] for dimension in ("distance", "height")]),
        heading("工程配对比较"), paragraph("配对以同类别、同seed整次试验为单位。差为左侧减右侧；误差类负值表示较小，覆盖率/FPS不能沿用该方向解释。区间条件于实际有限配对，双方PASS子集另列。单个或退化配对不制造置信精度。")]
    for comparison in summary["paired_comparisons"]:
        blocks.append(heading(comparison["target_class"] + ": " + comparison["comparison"], 2))
        rows = []
        for metric, values in comparison["metrics"].items():
            if metric not in SUMMARY_METRICS:
                continue
            for subset in ("all_finite_pairs", "both_pass_pairs"):
                value = values[subset]
                rows.append([SUMMARY_METRICS[metric], subset, f"{value['n']}/{value['n_slots']}",
                             value["mean"], value["ci95"], value["ci_status"]])
        blocks.append(table(["指标", "条件子集", "有效/计划", "平均差", "95%CI", "区间状态"], rows))
    blocks += [heading("同测量四估计器研究"), paragraph(
        "原始测量、EMA、固定传感器R0加同一R_pose的KF、逐观测R_geometry加同一R_pose的KF使用相同因果门控与任务生命周期。R0、Q、P0、初速度、EMA和共同支持门必须来自开发集并前瞻登记。完整计划为两类各10条录制；帧和bootstrap抽样不是独立重复。")]
    if replay is None:
        blocks.append(paragraph("未提供已登记的四法结果与全部20槽来源；该研究仍待完成，不能给出正式比较结论。"))
    else:
        blocks.append(table(["类别", "计划", "有报告", "已核验报告", "缺失槽"],
            [[cls, value["scheduled_trials"], value["available_trial_reports"], value["verified_trial_reports"], len(value["missing_slots"])]
             for cls, value in replay["classes"].items()]))
        blocks.append(table(["类别", "比较", "有限/10", "核验/10", "平均差 / m", "95%CI"],
            [[cls, name, f"{value['finite_pairs']}/10", f"{value['verified_pairs']}/10", value["mean_difference"], value["ci95"]]
             for cls, group in replay["classes"].items() for name, value in group["contrasts"].items()]))
        blocks.append(paragraph("完整已核验十对矩阵：" + fmt(replay["complete_verified_matrix"]) +
                                "。缺失或共同支持不足时，只报告明确条件下的描述结果，不能称完成十次有效配对。"))
        blocks.append(table(["四法槽", "原结果/缺失终态", "工程状态", "共同支持", "原因"],
            [[row["slot_id"], row["status"], row["engineering_status"], row["common_support_met"], row["reason"]] for row in outcomes]))
    blocks += [heading("检测、身份与性能解释"), paragraph(
        "检测处理FPS按仿真时间；检测处理链墙钟耗时包含图像转换、YOLO调用、深度与导航采样及发布调用，不是纯网络推理耗时；采集至完成延迟按仿真时间，不能混为实时性能。Precision/Recall/mAP须另用冻结配置和经审核可见标签；没有该证据则保持待完成，不能从候选可用率推算。HOTA/IDF1为任务级几何诊断，完整投影框与无遮挡子集分开；显式重选不称自动ReID。"),
        paragraph("短遮挡预测表采用short_requested_shutter请求时间窗，不能单独证明该时刻像素被遮挡。实际遮挡证据、同一物理个体保持和恢复率须结合原surface遮挡评价及独立身份评价；UUID连续不证明重识别成功。"),
        heading("全部计划槽与缺证"), table(["队列", "槽ID", "原终态", "距离稳定", "高度稳定", "缺证数"],
            [[row["cohort"], row["slot_id"], row["status"], row["settling"]["distance"], row["settling"]["height"], len(row["report_issues"])]
             for row in summary["trials"]]),
        heading("限制与后续迁移"), paragraph(
        "本研究仅覆盖登记仿真、目标类别、距离、轨迹与算力条件；无实机飞行、自动避障、开放环境搜索或完整ReID结论。汽车几何尺寸先验、RGB-D标定、定位协方差、时钟、算力与控制时延迁移到实机后均需重新验证。全部槽已尝试、证据充分和工程通过分别记账，不能互相替代。")]
    failures = snapshot.at(summary, "extension_registration.development_known_algorithm_failures")
    if failures:
        blocks += [heading("保留的开发负结果"), paragraph(json.dumps(failures, ensure_ascii=False))]
    issues = [[row["slot_id"], issue.get("kind"), issue.get("reason"), issue.get("result")]
              for row in summary["trials"] for issue in row["report_issues"]]
    if issues:
        blocks += [heading("原评价缺证原因"), table(["槽ID", "评价类型", "原原因", "原结果"], issues)]
    blocks += [heading("独立检测审核子集")]
    if detection is None:
        blocks.append(paragraph("PENDING：尚未提供实际来源绑定的检测报告与审核文件，不报告Precision/Recall/mAP。"))
    else:
        blocks += [paragraph(detection["status"] + "：仅适用于经审核、完整入画、静态渲染的仿真子集；不代表全部280次飞行、遮挡条件或真实环境总体检测精度。"),
            table(["录制/类别", "采样机会", "几何合格", "审核合格", "排除", "审核绑定"],
                [[row["name"] + "/" + row["target_class"], row["sampled_opportunities"], row["geometric_eligible"],
                  row["approved_eligible"], row["excluded"], row["review_binding_status"]] for row in detection["recordings"]])]
        if detection["classes_without_reviewed_frames"]:
            blocks.append(paragraph("尚无审核合格帧的类别：" + ", ".join(detection["classes_without_reviewed_frames"]) + "；对应精度保持待完成。"))
        rows = []
        for recording in detection["recordings"]:
            for cls, metrics in (recording["reviewed_metrics"] or {}).get("classes", {}).items():
                rows.append([recording["name"] + "/" + cls, metrics.get("ground_truth_objects"), metrics.get("precision"),
                             metrics.get("recall"), metrics.get("ap50"), metrics.get("ap50_95")])
        blocks.append(table(["录制/类别", "GT数量", "Precision", "Recall", "AP50", "AP50:95"], rows) if rows else
                      paragraph("审核绑定不足或无批准的合格帧，指标保持缺失。"))
        aggregate = detection["reviewed_aggregate"]
        if aggregate is not None:
            blocks += [table(["批准子集帧数", "子集mAP50", "子集mAP50:95"],
                             [[aggregate["frames"], aggregate["map50"], aggregate["map50_95"]]]),
                       paragraph("P/R采用原评价器0.45置信度、0.50 IoU工作点；AP采用声明的缓存预测和101点recall约定。原推理阈值、模型、尺寸与线程见来源工件，不外推到整体飞行。")]
    return blocks


def md_escape(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(document):
    lines = ["# " + document["title"], "", document["status_label"], ""]
    for block in document["blocks"]:
        kind = block["type"]
        if kind == "heading":
            lines += ["#" * (block["level"] + 1) + " " + block["text"], ""]
        elif kind in {"paragraph", "bullet"}:
            lines += [("- " if kind == "bullet" else "") + block["text"], ""]
        elif kind == "table":
            lines += ["| " + " | ".join(md_escape(value) for value in block["headers"]) + " |",
                      "| " + " | ".join("---" for _ in block["headers"]) + " |"]
            lines += ["| " + " | ".join(md_escape(value) for value in row) + " |" for row in block["rows"]]
            lines += [""]
        elif kind == "figure":
            lines += [block["caption"] + "（" + block["scope"] + "；源图SHA " + block["sha256"] + "）", ""]
    return "\n".join(lines)


def render_html(document, base=None):
    esc = html.escape
    body = ["<h1>" + esc(document["title"]) + "</h1><p class='notice'>" + esc(document["status_label"]) + "</p>"]
    for block in document["blocks"]:
        kind = block["type"]
        if kind == "heading":
            level = block["level"] + 1
            body.append(f"<h{level}>" + esc(block["text"]) + f"</h{level}>")
        elif kind in {"paragraph", "bullet"}:
            body.append("<p>" + esc(block["text"]) + "</p>")
        elif kind == "table":
            body.append("<div class='table'><table><thead><tr>" + "".join("<th>" + esc(value) + "</th>" for value in block["headers"]) +
                        "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + esc(value) + "</td>" for value in row) + "</tr>" for row in block["rows"]) + "</tbody></table></div>")
        elif kind == "figure":
            if base is not None:
                try:
                    url = quote(Path(os.path.relpath(block["path"], base)).as_posix(), safe="/")
                except ValueError:
                    url = Path(block["path"]).as_uri()
                body.append("<img style='max-width:100%;height:auto' src='" + esc(url, quote=True) + "' alt='" + esc(block["caption"], quote=True) + "'>")
            body.append("<p>" + esc(block["caption"] + "；" + block["scope"]) + "</p>")
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>" + esc(document["title"]) + "</title><style>body{max-width:1200px;margin:30px auto;padding:0 20px;font:16px/1.7 system-ui;color:#172339}"
            ".notice{background:#fff1cf;padding:14px}.table{overflow-x:auto}table{border-collapse:collapse;font-size:13px;width:100%}th,td{border:1px solid #d7dfea;padding:7px;overflow-wrap:anywhere}th{background:#e4edf7}</style>" + "".join(body) + "</html>")


def build(summary_path, core_path, extension_path=None, *, mode="draft", replay_summary=None,
          replay_manifest=None, replay_configuration=None, figures_manifest=None,
          plan_path=ROOT / "docs/FINAL_PLAN_V4.md", replay_source_root=ROOT,
          detection_report=None, detection_review=None, detection_source_root=ROOT):
    if mode not in {"draft", "final"}:
        raise ValueError("Unknown document mode")
    sources = Sources()
    summary = verify_snapshot(summary_path, core_path, extension_path, sources)
    replay = config = None
    outcomes = []
    if any(value is not None for value in (replay_summary, replay_manifest, replay_configuration)):
        if not all(value is not None for value in (replay_summary, replay_manifest, replay_configuration)):
            raise ValueError("Replay summary, input manifest and registration are required together")
        replay, config, outcomes = verify_replay(replay_summary, replay_manifest, replay_configuration, sources, source_root=replay_source_root)
    if mode == "final":
        final_gate(summary, replay, config, outcomes, core_path)
    figures, pending = verify_figures(figures_manifest, summary_path, replay_summary, sources, final=mode == "final")
    detection = None
    if detection_report is not None or detection_review is not None:
        if detection_report is None or detection_review is None:
            raise ValueError("Detection report and actual review file are required together")
        detection = verify_detection(detection_report, detection_review, sources, source_root=detection_source_root)
    sources.add(plan_path, "final_plan_content")
    plan_blocks = markdown_blocks(Path(plan_path).read_text(encoding="utf-8-sig"))
    label = "FINAL_EXECUTION_REPORT：280槽执行台账齐备；失败与证据局限保留，不等于工程全部通过。" if mode == "final" else "DEVELOPMENT_ONLY：开发草稿；不作为正式实验完成证明。"
    documents = {
        "plan": {"title": "基于YOLO11与卡尔曼滤波的RGB-D云台无人机目标跟踪与自主跟随——最终方案（v4）",
                 "status_label": label, "blocks": plan_blocks},
        "report": {"title": "RGB-D云台无人机目标跟踪与自主跟随仿真研究报告（v4）",
                   "status_label": label, "blocks": report_blocks(summary, replay, outcomes, final=mode == "final", detection=detection) + figures},
    }
    source_rows = [[record["role"], record["path"], record["sha256"] or "缺失"] for record in sources.records
                   if record["role"] in {"engineering_summary", "engineering_plan", "replay_summary", "replay_registration", "replay_input_manifest", "figures_manifest", "final_plan_content", "detection_report", "detection_review"}]
    for document in documents.values():
        document["blocks"] += [heading("来源索引"), table(["来源角色", "原路径", "SHA-256"], source_rows),
                                paragraph("完整来源大小、hash、缺失和实现身份见sources.json；图表与原始记录保持独立版本。")]
    sources.add(Path(__file__), "report_builder_implementation")
    sources.add(ROOT / "scripts/build_reliability_v4_documents.cjs", "document_renderer_implementation")
    result = {"schema_version": 1, "kind": KIND, "generated_utc": datetime.now(timezone.utc).isoformat(),
              "mode": mode, "scope": "FORMAL_EXECUTION_LEDGER_COMPLETE" if mode == "final" else "DEVELOPMENT_ONLY",
              "completion": {"all_280_slots_terminal": mode == "final", "all_engineering_pass": summary["all_engineering_pass"],
                             "replay_all_20_slots_accounted": len(outcomes) == 20,
                             "replay_complete_verified_matrix": replay.get("complete_verified_matrix") if replay else False,
                             "project_acceptance_claimed": False},
              "cohorts": summary["cohorts"], "replay_outcomes": outcomes,
              "detection_status": detection["status"] if detection else "PENDING_NOT_PROVIDED",
              "request": {"summary_path": str(Path(summary_path).resolve()), "core_path": str(Path(core_path).resolve()),
                          "extension_path": str(Path(extension_path).resolve()) if extension_path else None,
                          "mode": mode, "replay_summary": str(Path(replay_summary).resolve()) if replay_summary else None,
                          "replay_manifest": str(Path(replay_manifest).resolve()) if replay_manifest else None,
                          "replay_configuration": str(Path(replay_configuration).resolve()) if replay_configuration else None,
                          "figures_manifest": str(Path(figures_manifest).resolve()) if figures_manifest else None,
                          "plan_path": str(Path(plan_path).resolve()), "replay_source_root": str(Path(replay_source_root).resolve()),
                          "detection_report": str(Path(detection_report).resolve()) if detection_report else None,
                          "detection_review": str(Path(detection_review).resolve()) if detection_review else None,
                          "detection_source_root": str(Path(detection_source_root).resolve())},
              "pending_figures": pending, "documents": documents, "sources": sources.records,
              "validation": "SOURCES_RECONSTRUCTED_NO_ROS_BAG_OR_MODEL_INFERENCE",
              "rendering": "NOT_RENDERED: final DOCX/PDF and per-page visual review remain required"}
    sources.unchanged()
    return result, sources


def write_package(package, sources, output):
    output = Path(output)
    sources.unchanged()
    output.mkdir(parents=True, exist_ok=False)
    files = []
    for role, document in package["documents"].items():
        for suffix, renderer in (("md", render_markdown), ("html", lambda content: render_html(content, output))):
            path = output / (role + "." + suffix)
            path.write_text(renderer(document), encoding="utf-8")
            files.append({"path": path.name, "sha256": sha(path), "bytes": path.stat().st_size})
    package["document_package_sha256"] = canonical_sha256(package)
    path = output / "documents.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    files.append({"path": path.name, "sha256": sha(path), "bytes": path.stat().st_size})
    index = {"schema_version": 1, "kind": "RELIABILITY_V4_REPORT_SOURCES", "mode": package["mode"],
             "scope": package["scope"], "document_package_sha256": package["document_package_sha256"],
             "sources": sources.records, "outputs": files}
    sources.unchanged()
    (output / "sources.json").write_text(json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def verify_package(path):
    saved = strict_json(path)
    if saved.get("kind") != KIND or saved.get("schema_version") != 1:
        raise ValueError("Not a v4 document package")
    digest = saved.get("document_package_sha256")
    if digest != canonical_sha256({key: value for key, value in saved.items() if key != "document_package_sha256"}):
        raise ValueError("Document structure digest changed")
    rebuilt, sources = build(**saved["request"])
    stable = lambda value: {key: item for key, item in value.items() if key not in {"generated_utc", "document_package_sha256"}}
    if stable(rebuilt) != stable(saved):
        raise ValueError("Document package differs from its original bound evidence")
    index = strict_json(Path(path).parent / "sources.json")
    if (index.get("kind") != "RELIABILITY_V4_REPORT_SOURCES" or index.get("sources") != saved["sources"]
            or index.get("document_package_sha256") != digest or index.get("mode") != saved["mode"]):
        raise ValueError("Document source index disagrees")
    expected_names = {"plan.md", "report.md", "plan.html", "report.html", "documents.json"}
    if {item.get("path") for item in index.get("outputs", [])} != expected_names or len(index["outputs"]) != 5:
        raise ValueError("Document package output index is incomplete")
    for item in index["outputs"]:
        output = Path(path).parent / item["path"]
        if not output.is_file() or sha(output) != item["sha256"] or output.stat().st_size != item["bytes"]:
            raise ValueError("Saved document output changed")
        if output.suffix in {".md", ".html"}:
            role = output.stem
            expected = render_markdown(saved["documents"][role]) if output.suffix == ".md" else render_html(saved["documents"][role], output.parent)
            if output.read_text(encoding="utf-8") != expected:
                raise ValueError("Saved Markdown/HTML differs from bound document content")
    sources.unchanged()
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-package", type=Path, help="Reconstruct a saved source-bound package; no DOCX is rendered")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--core-plan", type=Path)
    parser.add_argument("--extension-plan", type=Path)
    parser.add_argument("--mode", choices=("draft", "final"), default="draft")
    parser.add_argument("--replay-summary", type=Path)
    parser.add_argument("--replay-input-manifest", type=Path)
    parser.add_argument("--replay-configuration", type=Path)
    parser.add_argument("--replay-source-root", type=Path, default=ROOT)
    parser.add_argument("--figures-manifest", type=Path)
    parser.add_argument("--detection-report", type=Path)
    parser.add_argument("--detection-review-file", type=Path)
    parser.add_argument("--detection-source-root", type=Path, default=ROOT)
    parser.add_argument("--plan-content", type=Path, default=ROOT / "docs/FINAL_PLAN_V4.md")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_package:
            package = verify_package(args.verify_package)
            print(json.dumps({"validation": "PACKAGE_EVIDENCE_RECONSTRUCTED", "mode": package["mode"],
                              "sha256": package["document_package_sha256"]}))
            return 0
        if args.summary is None or args.core_plan is None or args.output is None:
            parser.error("--summary, --core-plan and --output are required for a new package")
        package, sources = build(args.summary, args.core_plan, args.extension_plan, mode=args.mode,
            replay_summary=args.replay_summary, replay_manifest=args.replay_input_manifest,
            replay_configuration=args.replay_configuration, replay_source_root=args.replay_source_root,
            figures_manifest=args.figures_manifest, plan_path=args.plan_content, detection_report=args.detection_report,
            detection_review=args.detection_review_file, detection_source_root=args.detection_source_root)
        write_package(package, sources, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({"mode": package["mode"], "scope": package["scope"], "output": str(args.output),
                      "rendering": package["rendering"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
