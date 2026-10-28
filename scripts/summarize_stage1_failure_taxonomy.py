"""Read bounded small evidence files and write a separate stage-one taxonomy.

No bags, telemetry, video, simulation, tests, evaluations, or original-ledger
writes are performed. Check failures describe recorded outcomes, not root causes.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


CONFIRMED_TRIAL = "fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08"
LEDGERS = (
    "fullplan_v3_online_estimators_repetition_report.json",
    "fullplan_v3_position_compatibility_repetition_report.json",
)


def read_small(path: Path, limit: int) -> tuple[object | None, dict]:
    info = {"path": str(path), "exists": path.is_file()}
    if not info["exists"]:
        return None, info
    stat = path.stat()
    info.update(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
    if stat.st_size > limit:
        return None, {**info, "error": f"file exceeds bounded read limit {limit}"}
    data = path.read_bytes()
    info["sha256"] = hashlib.sha256(data).hexdigest()
    try:
        return json.loads(data), info
    except (ValueError, UnicodeError) as error:
        return None, {**info, "error": f"{type(error).__name__}: {error}"}


def false_checks(checks: dict) -> list[str]:
    return sorted(key for key, value in checks.items() if value is False)


def availability(rows: list[dict], field: str) -> dict:
    keys = sorted({key for row in rows for key in row.get(field, {})})
    result = {}
    for key in keys:
        count = Counter()
        for row in rows:
            values = row.get(field, {})
            if key not in values:
                count["missing"] += 1
            elif values[key] is True:
                count["true"] += 1
            elif values[key] is False:
                count["false"] += 1
            elif values[key] is None:
                count["null"] += 1
            else:
                count["other"] += 1
        result[key] = {name: count[name] for name in ("true", "false", "null", "missing", "other")}
    return result


def event_summary(event: dict) -> dict:
    post = event.get("post_reselection_tracking") or {}
    return {
        "kind": event.get("kind"), "result": event.get("result"),
        "start_s": event.get("start_s"), "end_s": event.get("end_s"),
        "duration_s": event.get("duration_s"), "checks": event.get("checks", {}),
        "failed_checks": false_checks(event.get("checks", {})),
        "first_predicted_s": event.get("first_predicted_s"),
        "first_lost_s": event.get("first_lost_s"), "first_hover_s": event.get("first_hover_s"),
        "speed_at_shutter_start_mps": event.get("speed_at_shutter_start_mps"),
        "speed_at_hover_entry_mps": event.get("speed_at_hover_entry_mps"),
        "braking_from_motion_demonstrated": event.get("braking_from_motion_demonstrated"),
        "post_reselection_result": post.get("result"),
        "post_reselection_checks": post.get("checks", {}),
        "post_reselection_failed_checks": false_checks(post.get("checks", {})),
        "post_reselection_control_span_s": post.get("control_span_s"),
        "post_reselection_first_uuid_mismatch_s": post.get("first_uuid_mismatch_s"),
    }


def main(args) -> dict:
    root, output = args.root.resolve(strict=True), args.output.resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Output must be a new directory outside frozen formal results")
    ledger_records, snapshots = [], {}
    for name in LEDGERS:
        data, info = read_small(root / name, 2 * 1024**2)
        if data is None:
            raise ValueError(f"Unable to read bounded formal ledger: {info}")
        snapshots[name] = info
        ledger_records.extend((name, trial) for trial in data["trials"])
    names = [trial["name"] for _, trial in ledger_records]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate trial names in source ledgers")

    audit_root = root.parent
    independent, independent_info = read_small(audit_root / "infrastructure_audit_v3_seed08_attempt03/report.json", 128 * 1024)
    native, native_info = read_small(audit_root / "infrastructure_audit_v3_seed08_native/report.json", 128 * 1024)
    comparison, comparison_info = read_small(audit_root / "infrastructure_audit_v3_seed08_native/derivative_comparison.json", 16 * 1024)
    audit_confirmed = bool(
        independent and native and comparison
        and independent.get("source_unchanged") and native.get("source_unchanged")
        and CONFIRMED_TRIAL in independent.get("source_before", {}).get("path", "")
        and independent.get("source_before", {}).get("sha256") == native.get("source_before", {}).get("sha256")
        and independent.get("routes", {}).get("drvfs", {}).get("sqlite", {}).get("valid") is True
        and native.get("ros_reader_probes", {}).get("drvfs", {}).get("open_succeeded") is False
        and comparison.get("shorter_is_exact_prefix") is True
        and comparison.get("longer_extra_bytes") == 131072
    )

    rows = []
    for ledger_name, trial in ledger_records:
        name = trial["name"]
        if re.fullmatch(r"[A-Za-z0-9_]+", name) is None:
            raise ValueError("Unexpected trial path")
        trial_root = root / name
        offline, offline_info = read_small(trial_root / "offline_evaluation.json", 512 * 1024)
        monitor, monitor_info = read_small(trial_root / "summary.json", 128 * 1024)
        exits, exits_info = read_small(trial_root / "process_exit_codes.json", 16 * 1024)
        acceptance = trial.get("acceptance") or {}
        checks = acceptance.get("checks", {})
        quality = {
            "offline_json_readable": isinstance(offline, dict),
            "monitor_json_readable": isinstance(monitor, dict),
            "exit_codes_json_readable": isinstance(exits, dict),
            "evaluation_returncode_zero": trial.get("evaluation_returncode") == 0,
            "clock_recorded": (offline or {}).get("inputs", {}).get("clock_recorded"),
            "read_errors_empty": (offline or {}).get("inputs", {}).get("read_errors") == {} if offline else None,
            "unavailable_types_empty": (offline or {}).get("inputs", {}).get("unavailable_types") == {} if offline else None,
            "recorded_trial_end_covered": (offline or {}).get("interval", {}).get("covers_recorded_trial_end"),
        }
        readable_score = all(quality[key] is True for key in (
            "offline_json_readable", "evaluation_returncode_zero", "clock_recorded",
            "read_errors_empty", "unavailable_types_empty", "recorded_trial_end_covered"))
        offline_result = (offline or {}).get("acceptance", {}).get("result")
        if name == CONFIRMED_TRIAL and audit_confirmed:
            category = "CONFIRMED_INFRASTRUCTURE_FAILURE"
        elif readable_score and trial.get("result") == "PASS" and acceptance.get("passed") is True and offline_result == "PASS":
            category = "SCORED_PASS"
        elif readable_score and trial.get("result") == "FAIL" and acceptance.get("passed") is False and offline_result == "FAIL":
            category = "SCORED_FAIL"
        else:
            category = "INCOMPLETE_OR_UNKNOWN"
        row = {key: trial.get(key) for key in (
            "name", "target_class", "command_mode", "estimator_method", "seed", "condition",
            "result", "launch_returncode", "evaluation_returncode", "online_state_evaluation_status")}
        row.update(source_ledger=ledger_name, taxonomy=category, ledger_acceptance_passed=acceptance.get("passed"),
                   ledger_infrastructure_stop=(trial.get("infrastructure_failure") or {}).get("stop"),
                   ledger_infrastructure_reasons=(trial.get("infrastructure_failure") or {}).get("reasons"),
                   acceptance_checks=checks, failed_acceptance_checks=false_checks(checks),
                   missing_artifacts=acceptance.get("missing_artifacts"), evidence_quality=quality,
                   offline_acceptance=(offline or {}).get("acceptance"),
                   monitor={key: (monitor or {}).get(key) for key in (
                       "basic_flight_passed", "monitor_success", "termination_reason", "monitor_exit_code",
                       "armed_seen", "offboard_seen")}, process_exit_codes=exits,
                   events=[event_summary(event) for event in (offline or {}).get("occlusions", [])],
                   sources={"offline": offline_info, "monitor": monitor_info, "process_exit_codes": exits_info})
        if category == "CONFIRMED_INFRASTRUCTURE_FAILURE":
            row["confirmed_infrastructure_evidence"] = "independent SQLite valid; native D copy loses final 128 KiB and reproduces SQLite11; original formal evaluation unscored"
        if trial.get("evaluation_returncode") not in (None, 0):
            log = trial_root / "offline_evaluation.log"
            if log.is_file() and log.stat().st_size <= 64 * 1024:
                text = log.read_text(encoding="utf-8", errors="replace")
                row["bounded_evaluation_error_lines"] = [line for line in text.splitlines() if any(
                    token in line.lower() for token in ("error", "exception", "runtimeerror", "malformed", "traceback"))]
        rows.append(row)

    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['target_class']}/{row['command_mode']}/{row['estimator_method']}"].append(row)
    failed_rows = [row for row in rows if row["taxonomy"] == "SCORED_FAIL"]
    events = [event for row in rows for event in row["events"]]
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
        "scope": "100 original stage-one terminal rows only; separate observational taxonomy, no ledger rewrite, no deep-cause inference",
        "read_policy": "bounded small JSON and at most64KiB nonzero-evaluation logs; no bags, telemetry, video, simulations or evaluations",
        "terminal_count": len(rows), "ledger_results": dict(Counter(row["result"] for row in rows)),
        "taxonomy_counts": dict(Counter(row["taxonomy"] for row in rows)),
        "groups": {key: {"count": len(value), "ledger_results": dict(Counter(row["result"] for row in value)),
                          "taxonomy_counts": dict(Counter(row["taxonomy"] for row in value))} for key, value in sorted(groups.items())},
        "failed_acceptance_checks_among_scored_fail": dict(Counter(check for row in failed_rows for check in row["failed_acceptance_checks"])),
        "acceptance_check_availability_all100": availability(rows, "acceptance_checks"),
        "evidence_quality_availability_all100": availability(rows, "evidence_quality"),
        "event_check_availability": {kind: availability([event for event in events if event["kind"] == kind], "checks") for kind in ("short", "long")},
        "post_reselection_check_availability": availability([event for event in events if event["kind"] == "long"], "post_reselection_checks"),
        "online_state_evaluation_status": dict(Counter(str(row["online_state_evaluation_status"]) for row in rows)),
        "source_ledgers_before": snapshots,
        "infrastructure_audit_sources": {"independent": independent_info, "native": native_info, "comparison": comparison_info},
        "confirmed_seed08_infrastructure_audit_available": audit_confirmed,
        "limitations": ["Failed checks overlap and must not be added as independent failure counts",
                        "Per-event first times are within evaluation windows; equal event start does not prove the pre-event state",
                        "No target-identity ground-truth correctness or deep failure cause is inferred",
                        "Results are stage one only and must not be extrapolated to the planned166 trials",
                        "Explicitly skipped online-state accuracy is missing evidence, not zero error"],
        "trials": rows,
    }
    summary["source_ledgers_after"] = {name: read_small(root / name, 2 * 1024**2)[1] for name in LEDGERS}
    summary["source_ledgers_unchanged"] = summary["source_ledgers_before"] == summary["source_ledgers_after"]
    if not summary["source_ledgers_unchanged"]:
        raise RuntimeError("Source ledgers changed during this audit; refusing a mixed snapshot")
    output.mkdir(parents=True)
    (output / "failure_taxonomy.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 阶段一 100 次正式试验：逐项失败分类", "", summary["scope"], "",
             "原始台账结果：" + json.dumps(summary["ledger_results"], ensure_ascii=False),
             "独立分类：" + json.dumps(summary["taxonomy_counts"], ensure_ascii=False), "",
             "| 类别/控制/估计器 | 总数 | 台账PASS | 正常评分FAIL | 已确认基础设施异常 | 未知 |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, group in summary["groups"].items():
        counts = group["taxonomy_counts"]
        lines.append(f"| {key} | {group['count']} | {group['ledger_results'].get('PASS', 0)} | {counts.get('SCORED_FAIL', 0)} | {counts.get('CONFIRMED_INFRASTRUCTURE_FAILURE', 0)} | {counts.get('INCOMPLETE_OR_UNKNOWN', 0)} |")
    lines.extend(["", "检查失败次数（可重叠，分母为正常评分 FAIL）：", ""])
    lines.extend(f"- `{key}`：{count}" for key, count in sorted(summary["failed_acceptance_checks_among_scored_fail"].items()))
    lines.extend(["", "逐项记录（检查名是已记录的验收结果，不是根因）：", "",
                  "| 试验 | 原台账结果 | 分类 | 未通过的顶层检查 |", "|---|---|---|---|"])
    lines.extend(f"| {row['name']} | {row['result']} | {row['taxonomy']} | {', '.join(row['failed_acceptance_checks']) or '—'} |" for row in rows)
    lines.extend(["", "原台账前后指纹相同：" + str(summary["source_ledgers_unchanged"]), "",
                  "完整字段可用性、逐事件检查、原始小型证据指纹与限制见同目录 failure_taxonomy.json。", ""])
    (output / "failure_taxonomy.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = main(args)
    print(json.dumps({key: result[key] for key in ("terminal_count", "ledger_results", "taxonomy_counts", "source_ledgers_unchanged")}, ensure_ascii=False))
