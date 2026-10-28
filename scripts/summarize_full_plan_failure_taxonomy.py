"""Create a separate small-report-only taxonomy for the frozen166-flight plan.

Default output requires every planned slot to be terminal. --trial creates a
clearly labelled selected-trial snapshot; --allow-partial explicitly permits a
partial snapshot. Nothing launches, evaluates, retries, or edits formal records.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from summarize_stage1_failure_taxonomy import read_small, false_checks


TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INTERRUPTED"}


def snapshot_read(path: Path, limit: int, snapshots: dict) -> tuple[object | None, dict]:
    """Register every actual small-source read, including missing paths."""
    data, info = read_small(path, limit)
    info["read_limit_bytes"] = limit
    key = str(path)
    if key in snapshots and snapshots[key] != info:
        raise RuntimeError(f"Small source changed between reads: {path}")
    snapshots[key] = info
    return data, info


def required(path: Path, limit: int, snapshots: dict) -> dict:
    data, info = snapshot_read(path, limit, snapshots)
    if not isinstance(data, dict):
        raise ValueError(f"Required bounded JSON unavailable: {info}")
    return data


def report_summary(data: dict, kind: str) -> dict:
    metadata = data.get("inputs", data.get("metadata", {}))
    result = data.get("acceptance", {}).get("result") if kind == "flight" else data.get("result")
    checks = data.get("checks", {})
    return {
        "kind": kind, "result": result, "checks": checks,
        "failed_checks": false_checks(checks),
        "null_checks": sorted(key for key, value in checks.items() if value is None),
        "clock_recorded": metadata.get("clock_recorded"),
        "clock_samples_read": metadata.get("clock_samples_read"),
        "read_errors": metadata.get("read_errors"),
        "unavailable_types": metadata.get("unavailable_types"),
        "channel_errors": data.get("channel_errors"), "interval": data.get("interval"),
        "tracks_snapshot_count": data.get("tracks_snapshot_count"),
        "tracks_snapshot_errors": data.get("tracks_snapshot_errors", data.get("snapshot_errors")),
        "sustained_tracking": data.get("sustained_tracking"),
        "terminal_hover": data.get("terminal_hover"), "physical_identity": data.get("physical_identity"),
        "selection_count": len(data.get("selections", [])), "selections": data.get("selections"),
        "failed_event_checks": [{"kind": event.get("kind"), "failed_checks": false_checks(event.get("checks", {}))}
                                for event in data.get("occlusions", []) if event.get("result") != "PASS"],
        "limitations": data.get("limitations"),
    }


def classify_stage23(root: Path, spec: dict, slot: dict, snapshots: dict) -> dict:
    status, name = slot.get("status", "PENDING"), spec["name"]
    row = {"name": name, "stage": spec["stage"], "target_class": spec["target_class"],
           "scenario": spec["scenario"], "seed": spec["seed"], "gimbal_mode": spec.get("gimbal_mode"),
           "result": status, "source": "stage23 manifest", "reports": [], "sources": {}}
    if status not in TERMINAL:
        return {**row, "taxonomy": "NOT_TERMINAL", "observation_tags": []}
    directory = root / name
    monitor, monitor_info = snapshot_read(directory / "summary.json", 128 * 1024, snapshots)
    exits, exits_info = snapshot_read(directory / "process_exit_codes.json", 16 * 1024, snapshots)
    source_hashes, source_info = snapshot_read(directory / "configuration/source_sha256.json", 128 * 1024, snapshots)
    row.update(monitor=monitor, process_exit_codes=exits,
               archived_stage2_evaluator_sha256=(source_hashes or {}).get("scripts/evaluate_stage2_flight.py"),
               sources={"monitor": monitor_info, "exit_codes": exits_info, "archived_source_hashes": source_info},
               ledger_infrastructure_failure=slot.get("infrastructure_failure"),
               saved_evaluations=slot.get("evaluations", []))
    expected = [("auto_unique", "auto_unique_evaluation.json")] if spec["scenario"] == "auto_unique" else (
        [("stage2_safety", "stage2_evaluation.json")] if spec["stage"] == 2 else
        [("flight", "flight_evaluation.json"), ("gimbal", "gimbal_evaluation.json")])
    errors = []
    for kind, filename in expected:
        data, info = snapshot_read(directory / filename, 1024**2, snapshots)
        row["sources"][kind] = info
        if not isinstance(data, dict):
            errors.append(f"{kind}: absent/unreadable bounded JSON")
            continue
        report = report_summary(data, kind)
        row["reports"].append(report)
        if (report["clock_recorded"] is not True or report["read_errors"] != {}
                or report["unavailable_types"] != {} or report.get("channel_errors")):
            errors.append(f"{kind}: required decode/clock evidence unavailable")
        evaluations = [item for item in slot.get("evaluations", []) if item.get("kind") == kind]
        if (len(evaluations) != 1 or evaluations[0].get("result") != report["result"]
                or evaluations[0].get("returncode") not in (0, 2) or evaluations[0].get("error")):
            errors.append(f"{kind}: saved evaluator row/result/returncode mismatch or exception")
    outcomes = [report["result"] for report in row["reports"]]
    if (slot.get("infrastructure_failure") or {}).get("stop") is True:
        category = "REPORTED_INFRASTRUCTURE_FAILURE"
    elif errors or len(row["reports"]) != len(expected):
        category = "INCOMPLETE_OR_UNKNOWN"
    elif any(outcome in {"FAIL_OR_INCOMPLETE", "INCOMPLETE_EVIDENCE", "INCOMPLETE"} for outcome in outcomes):
        category = "SCORED_NEGATIVE_OR_INCOMPLETE"
    elif status == "PASS" and all(outcome == "PASS" for outcome in outcomes):
        category = "SCORED_PASS"
    elif status == "FAIL" and any(outcome == "FAIL" for outcome in outcomes):
        category = "SCORED_FAIL"
    else:
        category = "INCOMPLETE_OR_UNKNOWN"
    tags = []
    if any(report.get("tracks_snapshot_errors") for report in row["reports"]):
        tags.append("SNAPSHOT_VALIDATION_ERROR_RECORDED")
    if any((report.get("sustained_tracking") or {}).get("result") == "FAIL" for report in row["reports"]):
        tags.append("SUSTAINED_TRACKING_CHECK_FAILED")
    return {**row, "taxonomy": category, "evidence_errors": errors, "observation_tags": tags}


def main(args) -> dict:
    root, output = args.root.resolve(strict=True), args.output.resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Output must be new and outside frozen formal results")
    snapshots = {}
    plan = required(root / "full_plan_research_v3/plan.json", 2 * 1024**2, snapshots)
    specs = plan["trials"]
    names = [spec["name"] for spec in specs]
    if len(names) != 166 or len(set(names)) != 166 or any(re.fullmatch(r"[A-Za-z0-9_]+", name) is None for name in names):
        raise ValueError("Frozen plan must contain exactly166 distinct safe names")
    if args.trial and not set(args.trial).issubset(names):
        raise ValueError("Requested trial is not in the frozen166-flight plan")
    selected = [spec for spec in specs if not args.trial or spec["name"] in args.trial]
    stage1_rows = {}
    if any(spec["stage"] == 1 for spec in selected):
        stage1 = required(args.stage1_taxonomy.resolve(strict=True), 2 * 1024**2, snapshots)
        stage1_rows = {row["name"]: row for row in stage1["trials"]}
        expected_stage1 = {spec["name"] for spec in specs if spec["stage"] == 1}
        if set(stage1_rows) != expected_stage1 or not stage1.get("source_ledgers_unchanged"):
            raise ValueError("Stage-one taxonomy does not match the frozen100-trial subset")
        for filename, previous in stage1["source_ledgers_before"].items():
            required(root / filename, 2 * 1024**2, snapshots)
            if snapshots[str(root / filename)]["sha256"] != previous["sha256"]:
                raise ValueError("Formal stage-one ledger differs from the independent100-row snapshot")
    slots = {}
    if any(spec["stage"] != 1 for spec in selected):
        manifest = required(root / "full_plan_research_v3/stage23_matrix/manifest.json", 8 * 1024**2, snapshots)
        slots = {slot["trial"]["name"]: slot for slot in manifest["slots"]}
        if set(slots) != {spec["name"] for spec in specs if spec["stage"] != 1}:
            raise ValueError("Stage23 manifest does not match the frozen66-trial subset")
    rows = []
    for spec in selected:
        if spec["stage"] == 1:
            rows.append({**stage1_rows[spec["name"]], "stage": 1, "scenario": spec["scenario"],
                         "source": "independent100-row taxonomy validated against unchanged source ledgers"})
        else:
            rows.append(classify_stage23(root, spec, slots[spec["name"]], snapshots))
    nonterminal = [row["name"] for row in rows if row["result"] not in TERMINAL]
    if nonterminal and not args.allow_partial:
        raise ValueError(f"{len(nonterminal)} selected slots are not terminal; final output refused. Use --allow-partial only for an explicit snapshot")
    after = {}
    for path, info in snapshots.items():
        # Reapply the original bound. Missing/created/deleted/invalid JSON
        # transitions remain fingerprint differences instead of being ignored.
        snapshot_read(Path(path), info["read_limit_bytes"], after)
    if snapshots != after:
        raise RuntimeError("Plan or source manifest changed during this snapshot; no mixed report was written")
    grouped = defaultdict(list)
    for row in rows:
        grouped[f"stage{row['stage']}/{row['target_class']}/{row.get('scenario') or 'unspecified'}"].append(row)
    result = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "SELECTED_TRIALS_SNAPSHOT" if args.trial else ("PARTIAL166_SNAPSHOT" if nonterminal else "FINAL166_TERMINAL_TAXONOMY"),
        "is_final166": len(rows) == 166 and not nonterminal, "planned_total": 166, "selected_count": len(rows),
        "frozen_plan_sha256": plan.get("plan_sha256"), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ledger_result_counts": dict(Counter(row["result"] for row in rows)),
        "taxonomy_counts": dict(Counter(row["taxonomy"] for row in rows)),
        "groups": {key: dict(Counter(row["taxonomy"] for row in group)) for key, group in sorted(grouped.items())},
        "source_snapshots_before": snapshots, "source_snapshots_after": after, "source_snapshots_unchanged": True,
        "snapshot_coverage": "All small source files actually read in this invocation, including attempted missing paths; original per-source bounds are reapplied",
        "nonterminal_names": nonterminal,
        "limits": ["Small saved JSON only; no bag, telemetry, video, simulation, evaluation or retries",
                   "FAIL returncode2 is a scored negative when a valid saved evaluator report says FAIL",
                   "FAIL_OR_INCOMPLETE remains explicitly ambiguous; no forced algorithm-failure classification",
                   "REPORTED infrastructure is a ledger flag, not an independently confirmed root cause",
                   "Snapshot errors and tracking failures may coexist; no causal link is inferred",
                   "Task UUID consistency does not certify physical identity; offline research remains separate"],
        "trials": rows,
    }
    output.mkdir(parents=True)
    (output / "failure_taxonomy.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Frozen plan failure taxonomy", "", f"Scope: {result['scope']}; selected {len(rows)}/166; is_final166={result['is_final166']}",
             "", "Original result counts: " + json.dumps(result["ledger_result_counts"]),
             "Taxonomy: " + json.dumps(result["taxonomy_counts"]), "",
             "| Trial | Original result | Taxonomy | Failed saved checks |", "|---|---|---|---|"]
    for row in rows:
        failures = row.get("failed_acceptance_checks", []) + [f"{report['kind']}:{check}" for report in row.get("reports", []) for check in report["failed_checks"]]
        lines.append(f"| {row['name']} | {row['result']} | {row['taxonomy']} | {', '.join(failures) or '—'} |")
    (output / "failure_taxonomy.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage1-taxonomy", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results/stage1_failure_taxonomy_v3_100/failure_taxonomy.json")
    parser.add_argument("--trial", action="append", help="Select a frozen trial without claiming a final166 report")
    parser.add_argument("--allow-partial", action="store_true")
    outcome = main(parser.parse_args())
    print(json.dumps({key: outcome[key] for key in ("scope", "is_final166", "selected_count", "ledger_result_counts", "taxonomy_counts", "source_snapshots_unchanged")}))
