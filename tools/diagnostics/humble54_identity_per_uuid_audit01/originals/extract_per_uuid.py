"""One-use descriptive extraction from four existing identity JSON reports.

No evaluator import/run or raw data. Reports open once each, sequentially.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

PREPARED_SHA = "0d728975c11aac0816d9a2d633eec600f4622ba375e356056b8bdb8450f2a9c4"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stat_pin(path):
    s = path.stat()
    return {"bytes": s.st_size, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
            "device": s.st_dev, "inode": s.st_ino}


def small(path, expected=None):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 ** 2
    raw = path.read_bytes()
    if expected is not None:
        assert sha(raw) == expected
    return raw


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def same_number(actual, expected):
    assert (actual is None and expected is None) or (actual is not None and expected is not None
        and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)), (actual, expected)


def extract(case, prepared):
    slot_path = Path(case["slot"]["path"])
    slot = json.loads(small(slot_path, case["slot"]["sha256"]).decode("utf-8-sig"))
    record = {k: v for k, v in slot.items() if k != "record_sha256"}
    assert sha(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")) == slot["record_sha256"] == case["record_sha256"]
    assert slot["plan_sha256"] == prepared["plan_digest"] and slot["status"] == case["slot_original_status"]
    path = Path(case["report"]["path"])
    assert path.is_file() and not path.is_symlink()
    before = stat_pin(path)
    assert before["bytes"] == case["report"]["stat_bytes_only"] <= prepared["report_cap_bytes"]
    # The only opening/read of this physical report. Both SHA checks use this buffer.
    raw = path.read_bytes()
    before_parse_sha = sha(raw)
    assert before_parse_sha == case["report"]["expected_sha256_from_terminal"]
    report = json.loads(raw.decode("utf-8-sig"))
    assert report["schema_version"] == 1 and report["evaluation_status"] == "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS"
    sources = prepared["evaluator_source_and_direct_dependencies"]
    provenance = report["evaluation_source"]
    assert provenance["script_sha256"] == sources["scripts/evaluate_physical_identity.py"]["sha256"]
    for name, binding in sources.items():
        if name == "scripts/evaluate_physical_identity.py":
            continue
        matches = [value for key, value in provenance["dependencies"].items() if key.replace("\\", "/").endswith("/" + name)]
        assert matches == [binding["sha256"]], name
    full = report["conservative_task_time_identity"]
    expected = case["expected_full_task_summary"]
    diagnostic = report["conservative_selected_identity"]
    for key, value in expected.items():
        assert full[key] == value, (case["id"], key)
    for key, value in case["expected_separate_diagnostic_summary"].items():
        assert diagnostic[key] == value, (case["id"], "diagnostic", key)
    assert full["coverage_basis"] == "fixed_10hz_request_to_recorded_clock_end"
    assert full["evaluation_status"] == "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS"
    period, interval = full["sample_period_s"], full["interval"]
    assert period == .1
    total = max(1, int(math.ceil((interval["end_s"] - interval["start_s"]) / period - 1e-9)))
    cells = full["timeline"]
    assert len(cells) == full["scheduled_samples"] == total
    tasks = full["tasks"]
    assert len(tasks) == full["requested_task_count"]
    counts, reasons, all_reasons = defaultdict(Counter), defaultdict(Counter), Counter()
    spans, runs, current_run = {}, defaultdict(list), None
    for index, cell in enumerate(cells):
        uuid, outcome, reason = cell["target_uuid"], cell["outcome"], cell["reason"]
        assert uuid in tasks and outcome in {"correct", "wrong", "unknown"}
        same_number(cell["time_s"], interval["start_s"] + index * period)
        same_number(cell["end_s"], min(interval["end_s"], interval["start_s"] + (index + 1) * period))
        counts[uuid][outcome] += 1
        spans.setdefault(uuid, {"start_s": cell["time_s"], "end_s": cell["end_s"]})["end_s"] = cell["end_s"]
        if outcome == "unknown":
            reasons[uuid][reason] += 1
            all_reasons[reason] += 1
            if current_run is not None and current_run[0] == uuid and current_run[1]["reason"] == reason:
                current_run[1]["end_s"] = cell["end_s"]
                current_run[1]["cells"] += 1
            else:
                run = {"start_s": cell["time_s"], "end_s": cell["end_s"], "cells": 1, "reason": reason}
                runs[uuid].append(run)
                current_run = (uuid, run)
        else:
            current_run = None
    assert dict(all_reasons) == full["unknown_reason_counts"]
    diagnostics_by_uuid, diagnostic_reasons = defaultdict(Counter), defaultdict(Counter)
    for frame in diagnostic["outcomes"]:
        uuid, outcome = frame["target_uuid"], frame["outcome"]
        assert uuid in tasks and outcome in {"correct", "wrong", "unknown"}
        diagnostics_by_uuid[uuid][outcome] += 1
        if outcome == "unknown":
            diagnostic_reasons[uuid][str(frame.get("reason"))] += 1
    assert len(diagnostic["outcomes"]) == diagnostic["frames"]
    task_rows = []
    for uuid, task in sorted(tasks.items(), key=lambda item: (item[1]["request_time_s"], item[0])):
        c = {key: counts[uuid][key] for key in ("correct", "wrong", "unknown")}
        n = sum(c.values())
        assert n == task["scheduled_samples"] and all(c[key] == task[key] for key in c)
        known = (c["correct"] + c["wrong"]) / n if n else None
        lower = c["correct"] / n if n else None
        same_number(known, task["known_coverage"])
        same_number(lower, task["retention_lower_bound"])
        assert sum(reasons[uuid].values()) == c["unknown"]
        d = {key: diagnostics_by_uuid[uuid][key] for key in ("correct", "wrong", "unknown")}
        d["frames"] = sum(d.values())
        d["unknown_frame_reason_counts"] = dict(diagnostic_reasons[uuid])
        task_rows.append({"target_uuid": uuid,
            "request_time_s": task["request_time_s"], "source_image_s": task["source_image_s"],
            "confirmation_time_s": task["confirmation_time_s"], "confirmed": task["confirmed"],
            "initial_mapping_known": task["initial_mapping_known"], "expected_physical_id": task["expected_physical_id"],
            "duplicate_request_uuid": task["duplicate_request_uuid"],
            "allocated_cell_span": spans.get(uuid), "scheduled_samples": n, **c,
            "known_coverage": known, "retention_lower_bound": lower,
            "unknown_cell_reason_counts": dict(reasons[uuid]), "unknown_cell_runs": runs[uuid],
            "diagnostic_frames_separate_denominator": d,
            "acceptance_threshold_applied": False, "per_task_acceptance_result": "NOT_DEFINED_DESCRIPTIVE_ONLY"})
    for key in ("correct", "wrong", "unknown"):
        assert sum(row[key] for row in task_rows) == full[key]
        assert sum(row["diagnostic_frames_separate_denominator"][key] for row in task_rows) == diagnostic[key]
    assert sum(row["scheduled_samples"] for row in task_rows) == full["scheduled_samples"]
    assert sum(row["diagnostic_frames_separate_denominator"]["frames"] for row in task_rows) == diagnostic["frames"]
    after_parse_sha, after = sha(raw), stat_pin(path)
    assert after == before and after_parse_sha == before_parse_sha
    return {"id": case["id"], "slot": case["slot"], "slot_original_status": slot["status"],
        "report": {"path": str(path), "bytes": len(raw), "sha256_before_parse": before_parse_sha,
            "sha256_after_parse_same_buffer": after_parse_sha, "stat_before": before, "stat_after": after,
            "physical_report_opened_once": True,
            "pin_semantics": "Terminal expected SHA matched the single read buffer; buffer SHA rechecked after parse and path stat unchanged. No second post-read file hash."},
        "evaluation_source": provenance, "full_task_aggregate": {key: full[key] for key in
            ("coverage_basis", "sample_period_s", "interval", "scheduled_samples", "correct", "wrong", "unknown", "known_coverage", "retention_lower_bound", "requested_task_count", "unconfirmed_requested_tasks", "unknown_reason_counts", "evaluation_status", "semantics")},
        "diagnostic_aggregate_separate_denominator": case["expected_separate_diagnostic_summary"],
        "per_target_uuid": task_rows,
        "reconciliation": {"full_timeline_vs_task_summaries_vs_slot": True,
            "unknown_reason_counts_vs_timeline": True, "diagnostic_frames_vs_slot": True,
            "original_evaluator_source_and_dependencies_match_prepared_plan": True},
        "interpretation": "Unknown reasons describe saved evaluator evidence categories, not detector/communication root causes or continuous physical identity certainty."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root-idle-signal", required=True)
    args = parser.parse_args()
    assert args.root_idle_signal.strip()
    base = Path(__file__).resolve().parent
    prepared_path = base / "inputs_prepared.json"
    prepared = json.loads(small(prepared_path, PREPARED_SHA).decode("utf-8"))
    project = Path(prepared["plan"]["path"]).parents[3].resolve()
    output = args.output_dir.resolve()
    assert not output.is_relative_to(project) and not output.exists()
    small(Path(prepared["plan"]["path"]), prepared["plan"]["sha256"])
    for binding in prepared["evaluator_source_and_direct_dependencies"].values():
        small(Path(binding["path"]), binding["sha256"])
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    write(output / "execution_started.json", {"started_utc": started, "root_idle_signal": args.root_idle_signal,
        "script_sha256": sha(small(Path(__file__))), "inputs_prepared_sha256": PREPARED_SHA,
        "scope": "EXISTING_REPORT_DESCRIPTIVE_EXTRACTION_NOT_EVALUATION_OR_ACCEPTANCE"})
    cases = []
    try:
        for index, case in enumerate(prepared["cases"], 1):
            result = extract(case, prepared)
            write(output / (str(index).zfill(2) + "_" + case["id"] + ".json"), result)
            cases.append(result)
        summary = {"schema_version": 1, "kind": "FOUR_EXISTING_CORE_REPORTS_PER_UUID_DESCRIPTIVE_AUDIT",
            "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "result": "RECONCILED_DESCRIPTIVE_EXTRACTION_NO_PER_UUID_ACCEPTANCE_THRESHOLD",
            "physical_reports_opened_once_each_sequentially": len(cases), "plan": prepared["plan"],
            "inputs_prepared_sha256": PREPARED_SHA, "script_sha256": sha(small(Path(__file__))), "cases": cases,
            "boundaries": ["No evaluator, source, original report, slot or acceptance result was changed.",
                "Full fixed-grid cells and diagnostic frames are different denominators and remain separate.",
                "No per-target_uuid numerical acceptance threshold is introduced or inferred from the aggregate gate.",
                "Unknown intervals remain unknown; reason labels are recorded evidence categories, not causal attribution.",
                "No bag, model, telemetry, native/WSL/ROS or evaluator execution; no new labeling or geometric reevaluation.",
                "Source provenance pins do not prove every historical runtime import; one seed does not establish population reliability."]}
        write(output / "summary.json", summary)
        lines = ["# Existing Humble54 identity reports: per UUID", "", "Descriptive extraction only; no per UUID acceptance threshold.", "",
            "| Case | UUID | Correct | Wrong | Unknown | Full grid | Known coverage | Diagnostic frames |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for case in cases:
            for row in case["per_target_uuid"]:
                coverage = "unknown" if row["known_coverage"] is None else format(row["known_coverage"], ".6f")
                lines.append("| " + " | ".join(str(value) for value in (case["id"], row["target_uuid"], row["correct"], row["wrong"], row["unknown"], row["scheduled_samples"], coverage, row["diagnostic_frames_separate_denominator"]["frames"])) + " |")
        lines += ["", "Full unknown-cell reasons and contiguous runs are in summary.json. Diagnostic unknown-frame reasons are separate and do not explain every full-grid cell.",
            "", "Four reports were opened once each, in sequence. Each buffer matched its original terminal SHA; buffer SHA was rechecked after parsing and file metadata stayed unchanged. No second file-content hash was performed.", ""]
        with (output / "summary.md").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))
        write(output / "execution_terminal.json", {"result": summary["result"], "finished_utc": summary["finished_utc"],
            "reports_completed": len(cases), "summary_sha256": sha(small(output / "summary.json")), "exit_code": 0})
        print(json.dumps({"result": summary["result"], "output": str(output), "summary_sha256": sha(small(output / "summary.json")),
            "rows": [{"id": case["id"], "tasks": [{key: row[key] for key in ("target_uuid", "scheduled_samples", "correct", "wrong", "unknown", "known_coverage", "unknown_cell_reason_counts")} for row in case["per_target_uuid"]]} for case in cases]}, ensure_ascii=False))
    except Exception as error:
        write(output / "execution_failed.json", {"result": "FAILED_EXTRACTION_PRESERVED", "finished_utc": datetime.now(timezone.utc).isoformat(),
            "completed_reports": len(cases), "error_type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    main()
