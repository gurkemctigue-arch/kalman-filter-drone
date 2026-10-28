"""Build an honest Chinese study report from small, already recorded JSON files.

Standard library only. Never starts simulation, inference, plots, bag readers,
or the study summarizer. Missing/unfinished evidence is a reportable outcome.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}
OFFLINE_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED", "NOT_APPLICABLE_NO_SELECTED_TASK"}
SUPPLEMENT_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED"}
LEDGER_ROLES = ("main_summary", "main_plan", "offline_manifest", "engineering_manifest", "supplement_manifest")
COMPLETION_ROLES = (*LEDGER_ROLES, "metric_supplement")
REQUIRED_METRIC_KEYS = {
    "online_position_rmse_m", "online_position_p95_m", "online_velocity_rmse_mps", "online_velocity_p95_mps",
    "detector_processed_sim_fps", "detector_inference_wall_mean_s", "image_to_detector_sim_mean_s",
    "whole_distance_rmse_m", "whole_height_rmse_m", "image_center_rmse_px", "image_to_first_command_sim_mean_s",
    "velocity_command_jitter_rms_mps2", "initial_distance_overshoot_m", "initial_height_overshoot_m",
    "initial_distance_settling_s", "initial_height_settling_s", "physical_retention_lower_bound",
    "task_mean_unoccluded_geometry_mot_hota", "task_mean_unoccluded_geometry_mot_idf1", "task_mean_unoccluded_geometry_mot_id_switches",
    "short_shutter_predicted_position_rmse_m", "short_shutter_predicted_position_p95_m", "short_shutter_predicted_velocity_rmse_mps",
    "short_post_open_measured_recovery_fraction", "short_same_task_identity_preserved_fraction", "short_same_task_recovery_mean_s", "short_same_task_recovery_p95_s",
    "explicit_selection_confirmation_fraction", "explicit_selection_confirmation_mean_s",
}
CONDITIONS = {
    "all_measurable_recorded_pairs": "全部可测配对（含失败飞行）",
    "all_recorded_pairs": "全部已记录配对",
    "conditional_both_flight_pass": "双方 PASS 的条件配对",
}
METRICS = {
    "horizontal_rmse_m": "整段模型原点跟随距离 RMSE / m",
    "height_rmse_m": "整段模型原点高度 RMSE / m",
    "online_state_anchor_position_rmse_m": "实际在线表面锚点位置 RMSE / m",
    "online_state_coverage": "状态可用率",
    "command_jitter_rms_mps2": "速度命令变化率 RMS / m/s²",
    "detected_center_normalized_error_rmse": "检测条件下画面中心归一化 RMSE",
    "true_image_horizon_error_rad_rmse": "真实画面水平误差 RMSE / rad",
    "failure_indicator": "非 PASS 指示量",
    "initial_distance_settling_time_s": "初始距离稳定时间 / s（仅已稳定）",
    "initial_height_settling_time_s": "初始高度稳定时间 / s（仅已稳定）",
    "initial_distance_unsettled_indicator": "初始距离未稳定指示量",
    "initial_height_unsettled_indicator": "初始高度未稳定指示量",
    "initial_distance_opposite_side_overshoot_m": "初始距离反侧超调 / m",
    "initial_height_opposite_side_overshoot_m": "初始高度反侧超调 / m",
    "explicit_selection_mean_confirmation_latency_s": "逐飞行重选确认平均时间 / s",
    "follow_visual_observed_center_coverage": "检测中心观测覆盖率",
    "follow_visual_detected_center_error_px_rmse": "检测中心 RMSE / px",
    "follow_visual_detected_center_normalized_error_rmse": "检测中心归一化 RMSE",
    "follow_visual_image_to_first_tracking_command_sim_s_mean": "逐飞行图像至首条跟踪命令均值 / 仿真 s",
    "follow_visual_image_to_first_tracking_command_sim_s_p95": "逐飞行图像至首条跟踪命令 p95 / 仿真 s",
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def number(value):
    if value is None:
        return "缺失"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    return f"{value:.6g}" if finite(value) else str(value)


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def table(headers, rows):
    values = ["| " + " | ".join(cell(h) for h in headers) + " |",
              "| " + " | ".join("---" for _ in headers) + " |"]
    values.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(values) + "\n" if len(values) > 2 else "暂无可报告记录。\n"


def interval(data):
    bounds = data.get("ci95")
    return "[" + ", ".join(number(v) for v in bounds) + "]" if isinstance(bounds, list) and len(bounds) == 2 else "缺失"


def estimate(data):
    data = data or {}
    return f"{number(data.get('mean'))} ± {number(data.get('std'))}（有效 {number(data.get('valid_count'))}，缺失 {number(data.get('missing_count'))}）"


def terminal_failure_rate(counts):
    """Wilson interval over terminal flights; pending/running are not outcomes."""
    total = sum(counts[status] for status in TERMINAL)
    failures = total - counts["PASS"]
    if not total:
        return {"failures": 0, "total": 0, "rate": None, "ci95": None}
    rate = failures / total
    z = 1.959963984540054
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return {"failures": failures, "total": total, "rate": rate,
            "ci95": [max(0., center - half), min(1., center + half)]}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_matches(source, record):
    """Match a frozen source by path when possible, or by byte identity across OSes.

    Supplementary manifests are produced inside the frozen Linux checkout while the
    final report may be built from the Windows worktree.  The same file therefore
    legitimately has paths such as ``/mnt/d/...`` and ``D:\\...``.  SHA-256 plus
    byte count is the authoritative identity in that case; the basename keeps a
    same-content file from being silently assigned to a different ledger role.
    """
    if source.get("exists") is not True or record.get("exists") is not True:
        return False
    if source.get("bytes") != record.get("bytes") or source.get("sha256") != record.get("sha256"):
        return False
    try:
        if Path(source.get("path", "")).resolve() == Path(record.get("path", "")).resolve():
            return True
    except (OSError, TypeError, ValueError):
        pass
    # PureWindowsPath recognizes both separators even when this runs on Linux.
    source_name = PureWindowsPath(source.get("path", "")).name
    record_name = PureWindowsPath(record.get("path", "")).name
    return bool(source_name and source_name == record_name)


def validate_supplement_ledger(summary, plan, offline, engineering, supplement, source_records):
    """Check the small saved ledgers; never run an evaluator or inspect a bag."""
    result = {"complete": False, "terminal_slots": 0, "status_counts": {}, "problems": []}
    problems = result["problems"]
    required = {"main_summary": summary, "main_plan": plan, "offline_manifest": offline,
                "engineering_manifest": engineering, "supplement_manifest": supplement}
    missing = [role for role in LEDGER_ROLES if required[role] is None]
    if missing:
        problems.append("最终交付缺少显式台账输入：" + ", ".join(missing))
        return result
    try:
        if len({record.get("path") for record in source_records.values()}) != 5:
            problems.append("最终五份台账输入必须是不同文件")
        plan_trials = plan.get("trials", [])
        names = [trial.get("name") for trial in plan_trials]
        canonical = {key: value for key, value in plan.items() if key not in {"created_utc", "plan_sha256"}}
        if (plan.get("schema_version") != 1 or plan.get("plan_sha256") != digest(canonical)
                or len(names) != 166 or len(set(names)) != 166 or any(not isinstance(name, str) for name in names)
                or summary.get("plan_sha256") != plan.get("plan_sha256")
                or {row.get("name") for row in summary["trials"]} != set(names)):
            problems.append("最终主计划摘要或准确 166 个任务名绑定无效")
        by_name = {row["name"]: row for row in summary["trials"]}
        fields = ("stage", "target_class", "seed", "command_mode", "estimator_method", "scenario", "gimbal_mode", "matrix", "condition")
        if any(by_name.get(trial.get("name"), {}).get(key) != trial[key]
               for trial in plan_trials for key in fields if key in trial):
            problems.append("主汇总的逐任务阶段、类别、seed 或配置与计划不一致")
        offline_rows = offline.get("trials", {})
        if (offline.get("schema_version") != 1 or offline.get("plan_sha256") != plan.get("plan_sha256")
                or set(offline_rows) != set(names)
                or any(row.get("name") != name or row.get("status") not in OFFLINE_TERMINAL for name, row in offline_rows.items())
                or dict(Counter(row.get("status") for row in offline_rows.values())) != summary.get("offline_status_counts")):
            problems.append("最终主离线清单未准确绑定 166 个终态及汇总计数")
        extra_plan = engineering.get("plan", {})
        extra_trials = extra_plan.get("trials", [])
        extra_names = [trial.get("name") for trial in extra_trials]
        extra_slots = engineering.get("slots", [])
        if (engineering.get("schema_version") != 1 or engineering.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS"
                or engineering.get("plan_sha256") != digest(extra_plan) or extra_plan.get("expected_trials") != 16
                or extra_plan.get("primary_166_included") is not False or len(extra_trials) != 16
                or len(set(extra_names)) != 16 or any(not isinstance(name, str) for name in extra_names)
                or set(names) & set(extra_names) or not plan.get("source_hashes")
                or extra_plan.get("source_hashes") != plan.get("source_hashes")
                or extra_plan.get("preregistration_sha256") != plan.get("preregistration_sha256")
                or [slot.get("trial") for slot in extra_slots] != extra_trials
                or any(slot.get("status") not in TERMINAL for slot in extra_slots)):
            problems.append("最终独立 16 项工程清单摘要、来源或任务终态绑定无效")
        supplement_plan = supplement.get("plan", {})
        slots = supplement.get("slots", [])
        counts = Counter(slot.get("status", "UNKNOWN") for slot in slots)
        result.update(status_counts=dict(counts), terminal_slots=sum(counts[status] for status in SUPPLEMENT_TERMINAL),
                      plan_sha256=supplement.get("plan_sha256"))
        if (supplement.get("schema_version") != 1 or supplement.get("source") != "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT"
                or supplement.get("plan_sha256") != digest(supplement_plan)
                or supplement_plan.get("frozen_root") != plan.get("frozen_root")
                or supplement_plan.get("source_main_plan_sha256") != plan.get("plan_sha256")
                or supplement_plan.get("source_engineering_plan_sha256") != engineering.get("plan_sha256")
                or supplement_plan.get("trials") != extra_trials or len(slots) != 16
                or [slot.get("trial") for slot in slots] != extra_trials
                or any(slot.get("status") not in SUPPLEMENT_TERMINAL for slot in slots)):
            problems.append("独立 16 项补充后处理尚未全部终态，或未绑定当前两份冻结计划")
        for slot in slots:
            if slot.get("status") != "RECORDED":
                continue
            tasks = slot.get("tasks", [])
            if (len(tasks) != 2 or {task.get("kind") for task in tasks} != {"online_state_accuracy", "follow_dynamics"}
                    or any(task.get("status") not in {"RECORDED", "PREEXISTING_RECORDED_REPORT"}
                           or (task.get("status") == "RECORDED" and task.get("returncode") != 0) for task in tasks)):
                problems.append("已记录补充槽缺少两项有效后处理任务：" + str(slot.get("trial", {}).get("name")))
        # Supplement freezes exact input bytes, not only the canonical plan IDs.
        expected = {role: record for role, record in source_records.items()
                    if role != "supplement_manifest" and record.get("exists") is True}
        matched = set()
        for source in supplement_plan.get("sources", []):
            # Evaluators, wrappers and the anchor are outside this four-ledger check.
            try:
                direct = [role for role, record in expected.items()
                          if Path(source.get("path", "")).resolve() == Path(record.get("path", "")).resolve()]
            except (OSError, TypeError, ValueError):
                direct = []
            if direct:
                role = direct[0]
                if role in matched or not source_matches(source, expected[role]):
                    problems.append("补充输入 SHA/大小绑定不匹配或重复：" + str(source.get("path", "")))
                matched.add(role)
                continue
            candidates = [role for role, record in expected.items() if source_matches(source, record)]
            if not candidates:
                continue
            role = candidates[0]
            if role in matched:
                problems.append("补充输入 SHA/大小绑定不匹配或重复：" + str(source.get("path", "")))
            if len(candidates) > 1:
                problems.append("补充输入 SHA/大小绑定存在歧义：" + str(source.get("path", "")))
            matched.add(role)
        if len(expected) != 4 or matched != set(expected):
            problems.append("补充清单缺少当前 summary、plan、offline、工程 manifest 的准确来源 SHA")
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        problems.append("最终台账结构无效：" + str(error))
    result["complete"] = not problems
    return result


def validate_metric_supplement(metric, summary, plan, engineering, source_records):
    result = {"complete": False, "problems": []}
    problems = result["problems"]
    if any(value is None for value in (metric, plan, engineering)):
        problems.append("最终交付缺少已生成且绑定的逐飞行指标补充 JSON")
        return result
    try:
        flights = metric.get("flights", [])
        main_rows = summary["trials"]
        extra_slots = engineering["slots"]
        expected = {("main166", row["name"]): row["result"] for row in main_rows}
        expected.update({("engineering16", slot["trial"]["name"]): slot["status"] for slot in extra_slots})
        actual = {(row.get("cohort"), row.get("name")): row.get("result") for row in flights}
        if (metric.get("schema_version") != 1 or metric.get("source") != "PER_FLIGHT_JSON_METRIC_SUPPLEMENT"
                or metric.get("source_plan_sha256") != plan.get("plan_sha256")
                or metric.get("main_planned_flights") != 166 or metric.get("main_listed_flights") != 166
                or metric.get("engineering_listed_flights") != 16 or metric.get("all_main_flights_terminal") is not True
                or metric.get("include_state_frames") is not True or len(flights) != 182
                or len(actual) != 182 or actual != expected or any(status not in TERMINAL for status in actual.values())
                or not isinstance(metric.get("metric_labels"), dict) or not metric["metric_labels"]
                or not REQUIRED_METRIC_KEYS.issubset(metric["metric_labels"])
                or not isinstance(metric.get("groups"), dict) or not metric["groups"]):
            problems.append("指标补充未覆盖准确 166+16 终态任务、短遮挡状态侧车或当前主计划")
        original_rows = {("main166", row["name"]): row for row in main_rows}
        original_rows.update({("engineering16", slot["trial"]["name"]): slot["trial"] for slot in extra_slots})
        grouping_fields = ("stage", "target_class", "seed", "command_mode", "estimator_method", "scenario", "gimbal_mode", "coverage", "condition")
        if any(row.get(key) != original_rows.get((row.get("cohort"), row.get("name")), {}).get(key)
               for row in flights for key in grouping_fields):
            problems.append("指标补充中的任务分组配置与当前逐飞行台账不一致")
        listed = 0
        for group in metric.get("groups", {}).values():
            size = group.get("planned_or_listed_flights")
            if type(size) is not int or size < 1:
                problems.append("指标分组缺少真实飞行计数")
                continue
            listed += size
            for key in metric.get("metric_labels", {}):
                value = group.get("metrics", {}).get(key, {})
                statuses = group.get("metric_evidence_status_counts", {}).get(key, {})
                if (type(value.get("valid_flights")) is not int or type(value.get("missing_flights")) is not int
                        or value["valid_flights"] < 0 or value["missing_flights"] < 0
                        or value["valid_flights"] + value["missing_flights"] != size
                        or not statuses or any(type(count) is not int or count < 0 for count in statuses.values())
                        or sum(statuses.values()) != size
                        or sum(count for status, count in statuses.items() if status.startswith("NOT_APPLICABLE")) > value["missing_flights"]):
                    problems.append("指标分组缺失有效/缺失/不适用分母：" + key)
                    break
        if listed != 182:
            problems.append("指标分组未覆盖准确 182 个真实飞行单位")
        required_roles = ("main_summary", "main_plan", "engineering_manifest")
        current = {role: source_records[role] for role in required_roles}
        matched = set()
        for source in metric.get("sources", []):
            try:
                direct = [role for role, record in current.items()
                          if Path(source.get("path", "")).resolve() == Path(record.get("path", "")).resolve()]
            except (OSError, TypeError, ValueError):
                direct = []
            if direct:
                role = direct[0]
                if role in matched or not source_matches(source, current[role]):
                    problems.append("指标补充输入 SHA/大小绑定不匹配或重复：" + str(source.get("path", "")))
                matched.add(role)
                continue
            candidates = [role for role, record in current.items() if source_matches(source, record)]
            if not candidates:
                continue
            role = candidates[0]
            if role in matched:
                problems.append("指标补充输入 SHA/大小绑定不匹配或重复：" + str(source.get("path", "")))
            if len(candidates) > 1:
                problems.append("指标补充输入 SHA/大小绑定存在歧义：" + str(source.get("path", "")))
            matched.add(role)
        if len(current) != 3 or matched != set(current):
            problems.append("指标补充缺少当前 summary、plan、工程 manifest 的准确来源 SHA")
        result.update(main_flights=metric.get("main_listed_flights"), engineering_flights=metric.get("engineering_listed_flights"),
                      source_plan_sha256=metric.get("source_plan_sha256"))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        problems.append("指标补充结构无效：" + str(error))
    result["complete"] = not problems
    return result


def metric_tables(metric, validation):
    lines = ["## 逐飞行完整指标表", ""]
    if not validation["complete"]:
        return lines + ["未提供绑定当前台账的完整指标补充；不能复报过期或其它研究的数值。缺失值不填零。", ""]
    lines += ["以下直接引用已保存的分组表，以整次飞行为统计单位；主166与独立16分组保留，均值±样本SD不是合并帧指标。逐飞行p95的均值不是全部帧的p95。来源missing_flights包含不适用；本表依据已保存的证据状态将不适用单列，其余无有效值计为缺失，不重算均值/SD。有效数为0时均值/SD缺失。", "",
              "检测FPS与图像至命令延迟按字段所注明的仿真时间解释；纯推理耗时采用墙钟。状态误差以可见表面锚点为参考。短快门预测只在请求窗与PREDICTED状态相交处评分，不能当作独立可见性真值。", ""]
    labels = metric["metric_labels"]
    for name, group in sorted(metric["groups"].items()):
        rows = []
        for key, value in sorted(group.get("metrics", {}).items()):
            statuses = group.get("metric_evidence_status_counts", {}).get(key, {})
            not_applicable = sum(count for status, count in statuses.items() if status.startswith("NOT_APPLICABLE"))
            missing = value.get("missing_flights")
            missing = missing - not_applicable if type(missing) is int else None
            rows.append((labels.get(key, key), number(value.get("valid_flights")), number(missing), number(not_applicable),
                         number(value.get("mean")), number(value.get("sample_sd"))))
        lines += ["### " + name, "",
                  "列入飞行：" + number(group.get("planned_or_listed_flights")) + "；状态：`"
                  + json.dumps(group.get("status_counts", {}), ensure_ascii=False, sort_keys=True) + "`。", "",
                  table(("指标", "有效飞行", "缺失飞行", "不适用飞行", "飞行均值", "飞行间样本SD"), rows),
                  "稳定/删失证据：`" + json.dumps(group.get("settling_evidence", {}), ensure_ascii=False, sort_keys=True) + "`。", ""]
        if "short_same_task_recovery_evidence" in group:
            recovery = group["short_same_task_recovery_evidence"]
            lines += ["短遮挡原任务恢复条件分母（short_same_task_recovery_evidence）：", "",
                      table(("已保存的证据计数/条件比例", "数值"),
                            ((key, json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else number(value))
                             for key, value in recovery.items() if not isinstance(value, (list, str)))), ""]
    lines += ["短遮挡恢复统计必须同时阅读请求窗、已观测恢复、身份已知/未知及未恢复计数；原track_id/target_uuid连续只证明记录的任务/轨迹保持，不代替独立物理身份。显式新UUID重选确认另列，均不等于长时ReID自动认回。", ""]
    return lines


class Sources:
    def __init__(self, output):
        self.output = Path(output)
        self.records = []

    def read(self, path, label, *, required=False):
        if path is None:
            self.records.append({"label": label, "path": None, "exists": False})
            return None
        path = Path(path)
        record = {"label": label, "path": str(path.resolve()), "exists": path.is_file()}
        self.records.append(record)
        if not path.is_file():
            if required:
                raise ValueError(f"缺少必需的 {label}: {path}")
            return None
        if path.suffix.lower() != ".json" or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError(f"仅接受不超过 32 MiB 的小型 JSON: {path}")
        raw = path.read_bytes()
        record.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        try:
            record["report_relative_path"] = os.path.relpath(path.resolve(), self.output.parent.resolve()).replace(os.sep, "/")
        except ValueError:
            pass  # Cross-volume reports can be read, but cannot be final Word inputs.
        def invalid(token):
            raise ValueError("JSON 中有非有限数值: " + token)
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=invalid)
        if not isinstance(data, dict):
            raise ValueError(f"{label} 必须是 JSON 对象")
        return data

    def link(self, path, label=None):
        if path is None or not Path(path).is_file():
            return f"{label or '证据'}：未提供或文件缺失"
        path = Path(path)
        try:
            relative = os.path.relpath(path.resolve(), self.output.parent.resolve()).replace(os.sep, "/")
        except ValueError:
            return f"{label or path.name}：位于另一磁盘卷，请将报告放到证据所在卷后重新生成"
        return f"[{str(label or path.name).replace(']', '')}]({quote(relative, safe='/.:_-')})"


def paired_rows(groups, *, stage):
    rows = []
    for name, group in sorted(groups.items()):
        outcomes = dict(group.get("outcomes", {})) if stage == 1 else group.get("active_minus_midpoint", {})
        if stage == 1 and "failure_indicator_difference" in group:
            outcomes["failure_indicator"] = {"all_recorded_pairs": group["failure_indicator_difference"]}
        for metric, conditions in sorted(outcomes.items()):
            for condition, result in conditions.items():
                if not isinstance(result, dict) or "pairs" not in result:
                    continue
                rows.append((name, METRICS.get(metric, metric), CONDITIONS.get(condition, condition),
                             number(result.get("pairs")), number(result.get("excluded_pairs")),
                             number(result.get("mean_difference")), interval(result)))
    return rows


def failure_reason(row):
    source = row.get("flight_phase_evidence", row)
    reasons = [str(source[key]) for key in ("error", "acceptance_error", "interruption_reason", "evaluation_skipped_reason") if source.get(key)]
    qualification = source.get("infrastructure_failure") or {}
    reasons.extend(str(item.get("code", "")) + ": " + str(item.get("message", "")) for item in qualification.get("reasons", []))
    acceptance = source.get("acceptance") or {}
    reasons.extend("验收项未通过: " + key for key, value in acceptance.get("checks", {}).items() if value is False)
    if acceptance.get("missing_artifacts"):
        reasons.append("缺少产物: " + ", ".join(acceptance["missing_artifacts"]))
    for evaluation in source.get("evaluations", []):
        if evaluation.get("result") != "PASS":
            reasons.append(f"{evaluation.get('kind', '评价')}: {evaluation.get('result', '缺失')} {evaluation.get('error') or ''}")
    return "; ".join(reasons) or "汇总未包含细项；请查看原始评价 JSON，不能据此编造原因"


def build_report(summary_path, output_path, *, engineering_manifest=None, engineering_summary=None,
                 plan_path=None, environment_path=None, detection_path=None, review_path=None,
                 offline_manifest_path=None, supplement_manifest_path=None, metric_supplement_path=None,
                 trial_root=None, videos=(), evidence=()):
    """Return Markdown and provenance; this function never writes a file."""
    sources = Sources(output_path)
    summary = sources.read(summary_path, "166 次主研究汇总", required=True)
    if summary.get("schema_version") != 1 or summary.get("planned_flights") != 166:
        raise ValueError("需要 schema_version=1、planned_flights=166 的主研究汇总")
    rows = summary.get("trials")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("主汇总 trials 必须为逐飞行对象列表")
    names = [row.get("name") for row in rows]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
        raise ValueError("逐飞行名称缺失或重复，不能生成可信分母")
    extra = sources.read(engineering_manifest, "16 次扩展工程清单")
    extra_summary = sources.read(engineering_summary, "16 次扩展工程汇总")
    plan = sources.read(plan_path, "冻结研究计划")
    offline_manifest = sources.read(offline_manifest_path, "166 次主离线清单")
    supplement_manifest = sources.read(supplement_manifest_path, "16 次补充后处理清单")
    metric_supplement = sources.read(metric_supplement_path, "逐飞行完整指标补充")
    environment = sources.read(environment_path, "环境清单")
    detection = sources.read(detection_path, "历史检测子集评价")
    review = sources.read(review_path, "历史检测标签目视审核")
    extra_slots = (extra or {}).get("slots", [])
    if not isinstance(extra_slots, list) or any(not isinstance(slot, dict) for slot in extra_slots):
        raise ValueError("扩展清单 slots 必须为对象列表")
    problems = []
    detection_review_bound = False
    if detection and review:
        review_source = next(record for record in sources.records if record["path"] == str(Path(review_path).resolve()))
        detection_review_bound = detection.get("review_file_sha256") == review_source.get("sha256")
        if not detection_review_bound:
            problems.append("检测评价未绑定当前审核清单的原字节 SHA；检测数值不予复报")
    if extra and (extra.get("source") != "EXTENDED_ENGINEERING_16_FLIGHTS" or (extra.get("plan") or {}).get("expected_trials") != 16):
        problems.append("扩展清单未声明独立 16 槽协议，不能认证该分母")
    if extra:
        extra_names = [slot.get("trial", {}).get("name") for slot in extra_slots]
        planned_extra = (extra.get("plan") or {}).get("trials", [])
        if (len(extra_names) != len(set(extra_names)) or any(not isinstance(name, str) for name in extra_names)
                or [slot.get("trial") for slot in extra_slots] != planned_extra):
            problems.append("扩展槽重复、名称缺失或与冻结计划绑定不一致")
    if extra and extra_summary and extra.get("plan_sha256") != extra_summary.get("plan_sha256"):
        problems.append("扩展汇总与清单的计划 SHA 不一致")
    if plan and plan.get("plan_sha256") != summary.get("plan_sha256"):
        problems.append("主汇总与冻结计划 SHA 不一致")
    counts = Counter(row.get("result", "UNKNOWN") for row in rows)
    extra_counts = Counter(slot.get("status", "UNKNOWN") for slot in extra_slots)
    main_terminal = sum(counts[status] for status in TERMINAL)
    extra_terminal = sum(extra_counts[status] for status in TERMINAL)
    offline = summary.get("offline_status_counts", {})
    offline_total = sum(value for value in offline.values() if type(value) is int and value >= 0)
    offline_terminal = sum(value for key, value in offline.items() if key in OFFLINE_TERMINAL and type(value) is int and value >= 0)
    if offline_total != offline_terminal:
        problems.append("离线评价仍有运行中、待执行或无法识别的状态")
    if dict(counts) != summary.get("status_counts", {}):
        problems.append("主汇总状态计数与逐次条目不一致")
    if extra_summary and dict(extra_counts) != extra_summary.get("status_counts", {}):
        problems.append("扩展汇总状态计数与逐次清单不一致")
    role_paths = dict(zip(COMPLETION_ROLES, (summary_path, plan_path, offline_manifest_path,
                                           engineering_manifest, supplement_manifest_path, metric_supplement_path)))
    completion_sources = {}
    for role, path in role_paths.items():
        if path is not None:
            record = next(record for record in sources.records if record["path"] == str(Path(path).resolve()))
            completion_sources[role] = {**record, "role": role}
    supplement_ledger = validate_supplement_ledger(summary, plan, offline_manifest, extra, supplement_manifest,
                                                  {role: record for role, record in completion_sources.items() if role in LEDGER_ROLES})
    metric_validation = validate_metric_supplement(metric_supplement, summary, plan, extra, completion_sources)
    problems.extend(supplement_ledger["problems"])
    problems.extend(metric_validation["problems"])
    complete = (not problems and len(rows) == main_terminal == 166 and len(extra_slots) == extra_terminal == 16
                and offline_terminal == 166 and summary.get("all_offline_slots_attempted") is True
                and extra is not None and (extra.get("plan") or {}).get("expected_trials") == 16
                and supplement_ledger["complete"] and metric_validation["complete"])
    lines = ["# 无人机目标跟踪与自主跟随：研究结果报告", "",
             "报告状态：" + ("执行台账已覆盖全部 182 槽、主研究 166 项离线评价及独立 16 项补充后处理（包含负结果）。" if complete else "未完成。当前输入尚不能证明全部 166+16 飞行槽、主离线 166 项及补充后处理 16 项均已执行并绑定。"), "",
             "执行完成、工程验收 PASS 和算法性能优劣分别判断。本报告只引用已有 JSON，不重新评价 rosbag，也不把缺失、未执行或未稳定填为零。", "",
             "本报告的终态失败率是执行/工程台账中的非 PASS 比例，可能同时包含可评分的跟随或身份失败、基础设施故障和录制证据不足，不能统称为算法失败率。损坏、截断或无法解码的 bag 仍保留在执行台账与失败分母，但不能据此提供完整算法性能评分；相应缺失指标不填零。原因分型须引用独立诊断及其审计范围，少量代表记录不能代替全部试验的原因审计。", "",
             f"主计划 SHA：`{summary.get('plan_sha256', '缺失')}`。输入更新时间：{summary.get('updated_utc', '缺失')}。", "",
             sources.link(summary_path, "主研究原始汇总") + "；" + sources.link(engineering_manifest, "扩展工程逐次清单") + "；" + sources.link(engineering_summary, "扩展工程汇总") + "。", "",
             "## 样本分母和完成进度", "",
             "主 166 槽含 80 次 velocity 四方法比较、20 次 adaptive position 兼容、20 次阶段二交叉、6 次阶段二工程安全和 40 次阶段三云台配对。另 16 槽为 4 次加减速、10 次在线故障和 2 次远距离工程检查；每个扩展条件仅 1 次，不能写成 10 次重复。", "",
             table(("台账", "计划", "逐次条目", "终态（含失败）", "PASS", "FAIL", "INCOMPLETE", "INTERRUPTED", "PENDING", "其他/运行中"),
                   (("主研究", 166, len(rows), main_terminal, counts["PASS"], counts["FAIL"], counts["INCOMPLETE"], counts["INTERRUPTED"], counts["PENDING"], sum(v for k, v in counts.items() if k not in TERMINAL | {"PENDING"})),
                    ("独立扩展", 16, len(extra_slots), extra_terminal, extra_counts["PASS"], extra_counts["FAIL"], extra_counts["INCOMPLETE"], extra_counts["INTERRUPTED"], extra_counts["PENDING"], sum(v for k, v in extra_counts.items() if k not in TERMINAL | {"PENDING"}))))]
    if problems:
        lines += ["输入一致性问题：" + "；".join(problems) + "。", ""]
    lines += ["主研究离线状态：`" + json.dumps(offline, ensure_ascii=False, sort_keys=True) + "`。已记录终态 " + str(offline_terminal) + "/166；INCOMPLETE_EVIDENCE 和 INTERRUPTED 仍是证据局限，不能当作完整有效结果。NOT_APPLICABLE_NO_SELECTED_TASK 对应有意不选目标的唯一实例歧义试验，不应伪造目标状态误差。", ""]
    lines += ["独立补充后处理状态：`" + json.dumps(supplement_ledger["status_counts"], ensure_ascii=False, sort_keys=True)
              + "`。终态 " + str(supplement_ledger["terminal_slots"]) + "/16；INCOMPLETE_EVIDENCE 和 INTERRUPTED 保留为缺证据/中断，不能认证相应性能已测得。",
              sources.link(supplement_manifest_path, "补充逐槽与来源 SHA 清单") + "。", ""]
    groups = {}
    for row in rows:
        groups.setdefault((str(row.get("stage", "未知")), row.get("target_class", "未知")), Counter())[row.get("result", "UNKNOWN")] += 1
    lines += [table(("阶段", "类别", "列入条目", "PASS", "非 PASS 终态", "待执行/运行中"),
                    ((stage, category, sum(group.values()), group["PASS"], sum(group[s] for s in TERMINAL - {"PASS"}),
                      sum(v for k, v in group.items() if k not in TERMINAL)) for (stage, category), group in sorted(groups.items()))),
              "未在逐次列表出现的计划槽不能假装已完成。失败率与覆盖率以真实试验/机会为分母，图像帧、重选任务和离线噪声种子均不是额外独立飞行。", "",
              "## 阶段一：四方法在线比较", ""]
    stage1 = summary.get("stage1_joined_statistics", {})
    stage1_counts = {}
    for row in rows:
        if row.get("stage") == 1:
            key = f"{row.get('target_class', '未知')}_{row.get('command_mode', '未知')}"
            if row.get("estimator_method"):
                key += "_" + str(row["estimator_method"])
            stage1_counts.setdefault(key, Counter())[row.get("result", "UNKNOWN")] += 1
    stage1_groups = stage1.get("groups", {})
    stage1_rows, stage1_source_rows = [], []
    for key in sorted(set(stage1_groups) | set(stage1_counts)):
        group = stage1_groups.get(key, {})
        counts = stage1_counts.get(key, Counter())
        failure = terminal_failure_rate(counts)
        stage1_rows.append((key, sum(counts.values()), failure["total"], counts["PASS"], failure["failures"], counts["PENDING"],
                            sum(value for status, value in counts.items() if status not in TERMINAL | {"PENDING"}),
                            number(failure["rate"]) + " " + interval(failure),
                            estimate(group.get("horizontal_distance_error_rmse_m")), estimate(group.get("online_state_anchor_position_rmse_m")),
                            estimate(group.get("online_state_coverage"))))
        if group:
            saved = group.get("failure_rate") or {}
            all_terminal = bool(counts) and failure["total"] == sum(counts.values())
            stage1_source_rows.append((key, f"{number(saved.get('failures'))}/{number(saved.get('total'))}",
                                       number(saved.get("rate")) if all_terminal else "缺失",
                                       interval(saved) if all_terminal else "缺失"))
    lines += [table(("类别/模式/方法", "列入条目", "终态分母", "PASS", "非 PASS 终态", "PENDING", "其他/运行中", "终态失败率及 Wilson 95%CI", "整段距离 RMSE 均值±SD", "在线锚点 RMSE 均值±SD", "状态可用率均值±SD"), stage1_rows),
              "阶段一按逐飞行的类别、控制模式和估计方法重新统计终态失败率；PENDING、运行中及未知状态不计成功或失败，零终态的率及区间缺失。性能均值和缺失数仍引用原 groups，不用终态筛选替换已有的可测性能结果。", "",
              table(("类别/模式/方法", "已保存非 PASS/已开始（仅来源诊断）", "已保存率（全终态时）", "已保存 Wilson 95%CI（全终态时）"), stage1_source_rows),
              "原已保存失败率可能包含运行中状态，只作来源诊断；可核对逐飞行条目全终态时才显示其原率及区间。", "",
              "下表差值方向统一为 adaptive − baseline。保留全部可测配对（含失败飞行），另列双方 PASS 的条件结果；缺失配对只记为排除数。置信区间从原汇总逐项引用，不重新抽样、不预先认定自适应 KF 最优。区间为探索性比较，未作多重比较校正。", "",
              table(("比较", "指标", "条件", "完整配对 n", "排除 n", "差值均值", "95%CI"), paired_rows(stage1.get("paired_comparisons", {}), stage=1)),
              "## 阶段二：指定个体与物理身份", "",
              "任务预期个体由初始 REQUEST 框与独立物理真值建立，UUID/稳定轨迹编号本身不是身份保持证据。下表机会数与整次飞行数分开；没有观测到错误匹配不能认证 unknown 或无新鲜匹配区间。", ""]
    identity_rows, identity_failure_rows, identity_source_rows, mot_rows = [], [], [], []
    for category, group in sorted(summary.get("stage2_crossing_statistics", {}).items()):
        identity_counts = group.get("selected_physical_counts", {})
        no_fresh = sum(value for key, value in identity_counts.items() if key == "NOT_OBSERVED" or key.startswith("NO_FRESH"))
        unknown = sum(value for key, value in identity_counts.items() if key.startswith("UNKNOWN"))
        identity_rows.append((category, number(group.get("recorded_trials")), len(group.get("planned_seeds", [])),
                              number(group.get("all_detection_opportunities")), number(group.get("all_task_opportunities")),
                              number(identity_counts.get("CORRECT", 0)), number(identity_counts.get("WRONG_PHYSICAL_ACTOR", 0)),
                              no_fresh, unknown, number(group.get("physical_reports_missing_or_incomplete")),
                              json.dumps(identity_counts, ensure_ascii=False, sort_keys=True)))
        crossing_rows = [row for row in rows if row.get("stage") == 2 and row.get("scenario") == "crossing"
                         and row.get("target_class") == category]
        if not crossing_rows:
            per_seed = group.get("per_seed", [])
            if isinstance(per_seed, list) and all(isinstance(row, dict) for row in per_seed):
                crossing_rows = per_seed
        crossing_counts = Counter(row.get("result", "UNKNOWN") for row in crossing_rows)
        failure = terminal_failure_rate(crossing_counts)
        identity_failure_rows.append((category, len(crossing_rows), failure["total"], crossing_counts["PASS"],
                                      failure["failures"], crossing_counts["PENDING"],
                                      sum(value for status, value in crossing_counts.items() if status not in TERMINAL | {"PENDING"}),
                                      number(failure["rate"]), interval(failure)))
        saved = group.get("failure_rate") or {}
        all_terminal = bool(crossing_rows) and failure["total"] == len(crossing_rows)
        identity_source_rows.append((category,
                                     f"{number(saved.get('failures'))}/{number(saved.get('total'))}",
                                     number(saved.get("rate")) if all_terminal else "缺失",
                                     interval(saved) if all_terminal else "缺失"))
        mot_rows.extend((category, metric, estimate(value), interval(value.get("mean_bootstrap95") or {}))
                        for metric, value in sorted(group.get("trial_statistics", {}).items()) if not metric.endswith("id_switches"))
    lines += [table(("类别", "已开始飞行", "计划种子", "全部检测机会", "全部任务机会", "CORRECT", "WRONG", "未观测/NO_FRESH", "UNKNOWN", "物理报告缺失/不完整", "原始类别计数"), identity_rows),
              table(("类别", "逐飞行条目", "终态分母", "PASS", "非 PASS 终态", "PENDING", "其他/运行中", "终态失败率", "Wilson 95%CI"), identity_failure_rows),
              "阶段二主结果从 summary.trials 中的同类别 crossing 飞行计算；缺少此列表时使用该组 per_seed。失败率分母仅含 PASS、FAIL、INCOMPLETE、INTERRUPTED，后三类计非 PASS 终态；PENDING、运行中和未知状态不计成功或失败，零终态的率及区间保持缺失。该分母不含另外 6 次工程安全检查。", "",
              table(("类别", "已保存非 PASS/已开始（仅来源诊断）", "已保存率（全终态时）", "已保存 Wilson 95%CI（全终态时）"), identity_source_rows),
              "来源诊断保留原 failure_rate 的分子和分母，其分母为非 PENDING 的已开始飞行，可能含运行中或未知状态。只有可核对逐飞行条目全部进入终态时才显示其原率和区间；否则保持缺失，不能把原字段用于失败率主结论。", "",
              table(("类别", "逐任务均值再按飞行统计的指标", "飞行均值±SD（含缺失数）", "整次飞行均值 bootstrap 95%CI"), mot_rows),
              "HOTA/IDF1/ID Switch 只描述其注明的几何标签集合；amodal 与无重叠几何子集分别报告，缺少真值的帧不能编为空真值。每个交叉 seed 当前只有一种关联配置，不能凭空写成两种关联算法的配对对照；多目标/遮挡标签仍需其独立可见性审核。", "",
              "原冻结summary的ID Switch聚合没有排除无帧/无几何标签任务的0，故此处不复报该旧聚合为主要结果。原始JSON保留；主要ID Switch数值与有效/缺失飞行数采用下文完整指标表，其提取器明确排除了空任务。HOTA/IDF1也须阅读各自有效/缺失分母。", "",
              "## 阶段三：主动云台与中位云台", ""]
    gimbal_counts = {}
    for row in rows:
        if row.get("stage") == 3:
            key = (str(row.get("target_class", "未知")), str(row.get("gimbal_mode", "未知")))
            gimbal_counts.setdefault(key, Counter())[row.get("result", "UNKNOWN")] += 1
    gimbal_failure_rows = []
    for (category, mode), group in sorted(gimbal_counts.items()):
        failure = terminal_failure_rate(group)
        gimbal_failure_rows.append((category, mode, sum(group.values()), failure["total"], group["PASS"],
                                    failure["failures"], group["PENDING"],
                                    sum(value for status, value in group.items() if status not in TERMINAL | {"PENDING"}),
                                    number(failure["rate"]), interval(failure)))
    lines += [table(("类别", "云台模式", "列入条目", "终态分母", "PASS", "非 PASS 终态", "PENDING", "其他/运行中", "终态失败率", "Wilson 95%CI"), gimbal_failure_rows),
              "阶段三失败率从逐飞行真实结果计算，分母仅含 PASS、FAIL、INCOMPLETE、INTERRUPTED；后三类计为非 PASS 终态。PENDING、运行中及未知状态均不计成功或失败，零终态时失败率及区间保持缺失。Wilson 区间以独立飞行为单位，不把图像帧或云台反馈样本当作重复。", "",
              "差值方向为 active − midpoint，配对单位为同类别、同 seed 的两次独立飞行。画面中心误差条件于检测可见，必须同时查看观测样本数和覆盖率。置信区间跨零或缺失时，不能写成已证实改善。", "",
              table(("类别", "指标", "条件", "完整配对 n", "排除 n", "差值均值", "95%CI"), paired_rows(summary.get("stage3_paired_statistics", {}), stage=3))]
    dynamics_rows, visual_rows, recovery_rows = [], [], []
    for key, group in sorted(summary.get("follow_dynamics_statistics", {}).items()):
        for axis, label in (("distance", "距离"), ("height", "高度")):
            value = group.get(f"initial_{axis}_settling", {})
            dynamics_rows.append((key, label, number(group.get("flight_units")), number(group.get("dynamics_recorded")),
                                  number(value.get("observed_settled")), number(value.get("right_censored")), number(value.get("missing_window")),
                                  estimate(value.get("observed_settling_time_s"))))
        visual = group.get("visual_control_statistics", {})
        stats = visual.get("whole_flight_statistics", {})
        visual_rows.append((key, number(visual.get("reports_available")), number(visual.get("reports_missing")),
                            number(visual.get("detection_opportunities_total")), number(visual.get("center_observed_samples_total")),
                            number(visual.get("pooled_observed_center_coverage")),
                            estimate(stats.get("follow_visual_observed_center_coverage")),
                            number(visual.get("source_images_with_first_tracking_command_total")),
                            estimate(stats.get("follow_visual_image_to_first_tracking_command_sim_s_mean"))))
        recovery_rows.append((key, number(group.get("explicit_selection_windows")),
                              number(group.get("explicit_selection_confirmation_censored")),
                              estimate(group.get("flight_mean_observed_confirmation_latency_s"))))
    lines += ["## 稳定时间、删失与视觉控制链路", "",
              "稳定时间只对观察窗口内持续满足条件的飞行计算。未稳定属于右删失，窗口缺失另记；二者均不能填成 0 s。运动目标任务瞬态不是静态阶跃响应。", "",
              table(("组", "轴", "飞行数", "瞬态报告", "已稳定", "右删失/未稳定", "窗口缺失", "仅已稳定时间均值±SD / s"), dynamics_rows),
              table(("组", "显式重选任务窗口", "确认右删失", "逐飞行已观测确认时间均值±SD / s"), recovery_rows),
              "显式重新框选后的确认与离场后自动 ReID 重捕获不是同一任务；任务窗口数也不是独立重复数。确认时间仅对已观察到确认的任务计算，须与确认删失数一起阅读。", "",
              table(("组", "视觉报告", "缺失报告", "检测机会", "中心观测", "机会加权覆盖率", "逐飞行覆盖率均值±SD", "首命令源图像数", "逐飞行首命令平均延迟均值±SD / 仿真 s"), visual_rows),
              "视觉误差来自检测框中心，不是独立物理中心标注精度。首命令延迟以 state.header − prediction_age_s 重建被接受的源图像时刻，按任务/轨迹/图像去重，结束于同目标 active FOLLOW/PREDICT 命令；它不代表 PX4/执行器响应或墙钟实时能力。", "",
              "## 独立 16 次扩展工程试验", "",
              table(("试验", "覆盖条件", "类别/控制模式", "登记 seed", "状态", "评价原因"),
                    ((slot.get("trial", {}).get("name", "缺失"), slot.get("trial", {}).get("coverage", "缺失"),
                      str(slot.get("trial", {}).get("target_class", "缺失")) + "/" + str(slot.get("trial", {}).get("command_mode", "缺失")),
                      number(slot.get("trial", {}).get("seed")), slot.get("status", "UNKNOWN"),
                      failure_reason(slot) if slot.get("status") not in {"PASS", "PENDING"} else "—") for slot in extra_slots)),
              "扩展单次检查不并入 166 主研究分母，不给它伪造十次重复的置信区间；失败、未起飞、空 bag 和环境早停均保留。", ""]
    lines += metric_tables(metric_supplement, metric_validation)
    lines += ["## 历史静态 132 标签子集的适用范围", ""]
    approved = (review or {}).get("approved_frames", {})
    reviewed_count = sum(len(values) for values in approved.values() if isinstance(values, list))
    if detection and review and detection_review_bound:
        lines += [f"当前审核清单列出 {reviewed_count} 个批准帧（历史完整子集为 132）；它们来自四份既有 stage1_final_v2 录制，不是本次新增的独立飞行。", ""]
        label_rows = []
        for recording in detection.get("recordings", []):
            category = recording.get("target_class", "未知")
            metrics = (recording.get("reviewed_metrics") or {}).get("classes", {}).get(category, {})
            source = str(recording.get("source_trial", "缺失")).replace("\\", "/").rsplit("/", 1)[-1]
            label_rows.append((source, category, number(recording.get("approved_eligible")), number(metrics.get("confidence_threshold")),
                               number(metrics.get("precision")), number(metrics.get("recall")), number(metrics.get("fn")),
                               number(metrics.get("ap50")), number(metrics.get("ap50_95"))))
        lines += [table(("源录制", "类别", "批准帧", "运行阈值", "Precision", "Recall", "FN", "AP50", "AP50:95"), label_rows)]
        aggregate = detection.get("reviewed_aggregate")
        if isinstance(aggregate, dict):
            classes = aggregate.get("classes", {})
            lines += ["以下直接引用已有 `reviewed_aggregate` 的合并子集结果，没有对逐录制 AP 求平均，也没有重跑检测。", "",
                      table(("合并批准子集帧", "当前审核批准帧", "有标注类别数", "mAP50", "mAP50:95"),
                            [(number(aggregate.get("frames")), reviewed_count,
                              sum(finite(value.get("ground_truth_objects")) and value["ground_truth_objects"] > 0 for value in classes.values()),
                              number(aggregate.get("map50")), number(aggregate.get("map50_95")))]),
                      table(("合并子集类别", "GT物体数", "运行阈值", "TP", "FP", "FN", "Precision", "Recall", "AP50", "AP50:95"),
                            ((category, number(metrics.get("ground_truth_objects")), number(metrics.get("confidence_threshold")),
                              number(metrics.get("tp")), number(metrics.get("fp")), number(metrics.get("fn")),
                              number(metrics.get("precision")), number(metrics.get("recall")), number(metrics.get("ap50")), number(metrics.get("ap50_95")))
                             for category, metrics in sorted(classes.items()))),
                      "mAP 只覆盖上述批准帧与有标注类别，GT 物体数和运行阈值另列；不能外推为正式 166 次或多目标遮挡检测 mAP。", ""]
            if aggregate.get("frames") != reviewed_count:
                lines += ["合并子集帧数与当前审核批准帧数不一致；保留两份来源数值，不能声称它们已对应同一审核范围。", ""]
        else:
            lines += ["未提供已审核的合并子集结果，mAP 缺失；不能由逐录制 AP 的平均值补造。", ""]
    elif detection and review:
        lines += ["检测评价保存的审核 SHA 与当前审核清单不匹配或缺失；逐录制 AP/P/R 与合并 mAP 均未复报。同样的帧数量不能证明相同帧ID或审核范围。", ""]
    else:
        lines += ["未同时提供检测评价和逐帧审核 JSON，当前报告不能复核历史 132 标签的分母或复报其数值。", ""]
    lines += ["该子集只覆盖完整入镜、避开遮挡保护窗口的静态渲染对象；单人逐图审核不是多标注者一致性或实例掩膜验证。它不能代表多目标、遮挡、真实世界或整段飞行检测性能。AP 使用低阈值完整 PR 曲线，运行 Precision/Recall 使用实际阈值；高 AP 不能掩盖运行阈值下的漏检，也不能把逐录制 AP 简单平均称为合并数据集 AP。", "",
              sources.link(detection_path, "检测子集原始评价") + "；" + sources.link(review_path, "逐帧审核清单") + "。", "",
              "## 环境、可移植性与解释边界", ""]
    if plan:
        resources = plan.get("resources", {})
        lines += ["冻结资源（计划值）：请求 RTF=" + number(resources.get("real_time_factor")) +
                  "；行人推理尺寸/线程=" + number(resources.get("person", {}).get("inference_image_size")) + "/" + number(resources.get("person", {}).get("inference_threads")) +
                  "；汽车=" + number(resources.get("car", {}).get("inference_image_size")) + "/" + number(resources.get("car", {}).get("inference_threads")) + "。实际达到的速率和时延须以各试验记录为准。", ""]
    if environment:
        ros = environment.get("ros_gazebo", {})
        lines += ["环境清单中的 ROS 发行版：" + str(ros.get("ros_distro", "缺失")) + "。具体操作系统、Gazebo、PX4/px4_msgs commit 和二进制哈希以链接的环境清单为准。", ""]
    else:
        lines += ["未提供环境清单，当前报告不重新认证具体版本。已有工程工作采用 Ubuntu 24.04 / ROS 2 Jazzy、Gazebo Harmonic、PX4 v1.17.0；它不能冒称原计划 Ubuntu 22.04 / Humble 组合已经验证。", ""]
    lines += ["正式登记 seed s 映射为 Gazebo 非零 seed s+1；运行参数 YAML、运行 world 和 PX4 before/after BSON 的哈希须随原始记录保留。算法与平台适配分离提供迁移接口，仍需在新平台重测坐标系、时间、RGB-D、通信、算力和失效保护。减慢仿真不能证明墙钟实时、实机飞行、任意开放搜索或自动避障；第一版不含完整 ReID。", "",
              "状态误差以冻结的可见表面锚点为参考，不是独立模型中心精度。初始无人机平移校准与后段 ego holdout 分开；理想真值 ego 重放与实际在线控制状态不能互换。", "",
              sources.link(plan_path, "冻结计划与源码哈希") + "；" + sources.link(environment_path, "环境清单") + "。", "",
              "## 逐次失败或不完整附录", ""]
    trial_root = Path(trial_root) if trial_root is not None else Path(summary_path).parent.parent
    failed_rows = []
    for row in rows:
        if row.get("result") in {"PASS", "PENDING"}:
            continue
        name = row["name"]
        directory = trial_root / name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) else None
        links = []
        if directory is not None:
            for filename in ("summary.json", "offline_evaluation.json", "stage2_evaluation.json", "flight_evaluation.json", "gimbal_evaluation.json", "physical_identity.json", "follow_dynamics.json", "online_state_accuracy_v2.json"):
                if (directory / filename).is_file():
                    links.append(sources.link(directory / filename, filename))
        failed_rows.append((name, row.get("result", "UNKNOWN"), failure_reason(row), " / ".join(links) or "未找到本地原始评价"))
    lines += [table(("主研究试验", "状态", "已有原因（不猜测）", "相对证据链接"), failed_rows),
              "无附录行仅表示当前输入中未记录非 PASS 终态，不能据此把 PENDING、缺少的条目或离线证据缺失写成成功。扩展失败见其独立逐次表。", "",
              "## 视频与补充证据", ""]
    links = [sources.link(path) for path in (*videos, *evidence)]
    if not videos:
        lines += ["未显式提供演示视频；报告不把不存在的视频当作已交付。", ""]
    lines += ["\n".join("- " + link for link in links) if links else "暂无显式补充链接。", "",
              "视频与补充证据只作为验收入口。独立 cleanup 工程探针用于检查新版进程退出与资源清理，不并入冻结主研究 166 槽或独立扩展 16 槽的分母，也不替换原有失败记录。", "",
              "## 复现与来源", "",
              "复现须使用原冻结 Linux 根目录、准确 prefix 和与已保存计划一致的 output 原始文本，并经 run_research_session.sh 将临时文件放在研究结果盘；已有计划使用 --resume，失败名字不重飞。具体命令与就绪前提见补充证据中的本轮交付运行说明，不使用省略 prefix/output 的默认版本命令。发现基础设施故障后先诊断并核对逐槽 guard，不能因台账尚有 PENDING 就直接继续。改变冻结代码或协议须使用新根/前缀。", "",
              "本报告输入 JSON 的 SHA-256：", "",
              table(("来源", "是否存在", "SHA-256", "链接"),
                    ((record["label"], "是" if record["exists"] else "否", record.get("sha256", "缺失"), sources.link(record["path"], record["label"])) for record in sources.records)),
              "报告生成器只读上述小型 JSON、检查已指定证据文件是否存在，并输出 Markdown 与来源清单。没有启动仿真、YOLO、绘图、正式汇总或 bag 分析。", ""]
    provenance = {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
                  "source_plan_sha256": summary.get("plan_sha256"), "execution_ledger_complete": complete,
                  "completion_contract_version": 2, "supplement_ledger": supplement_ledger,
                  "metric_supplement": metric_validation,
                  "completion_sources": list(completion_sources.values()),
                  "input_consistency_problems": problems, "inputs": sources.records,
                  "report_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return "\n".join(lines), provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engineering-manifest", type=Path)
    parser.add_argument("--engineering-summary", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--offline-manifest", type=Path)
    parser.add_argument("--supplement-manifest", type=Path)
    parser.add_argument("--metric-supplement", type=Path)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--detection", type=Path, default=ROOT / "results/detection_research/detection_report.json")
    parser.add_argument("--review", type=Path, default=ROOT / "results/detection_research/visual_review.json")
    parser.add_argument("--trial-root", type=Path)
    parser.add_argument("--video", type=Path, action="append", default=[])
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.output.suffix.lower() != ".md":
        parser.error("--output 必须为 .md 文件")
    try:
        text, provenance = build_report(args.summary, args.output, engineering_manifest=args.engineering_manifest,
            engineering_summary=args.engineering_summary, plan_path=args.plan, environment_path=args.environment,
            detection_path=args.detection, review_path=args.review, offline_manifest_path=args.offline_manifest,
            supplement_manifest_path=args.supplement_manifest, metric_supplement_path=args.metric_supplement,
            trial_root=args.trial_root,
            videos=args.video, evidence=args.evidence)
        sidecar = args.output.with_suffix(".sources.json")
        inputs = {Path(record["path"]).resolve() for record in provenance["inputs"] if record["path"]}
        if any(target.resolve() in inputs for target in (args.output, sidecar)):
            raise ValueError("输出会覆盖输入 JSON，已拒绝")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        provenance["report_sha256"] = hashlib.sha256(args.output.read_bytes()).hexdigest()
        sidecar.write_text(json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(args.output), "sources": str(sidecar), "execution_ledger_complete": provenance["execution_ledger_complete"]}, ensure_ascii=False))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
