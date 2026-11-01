"""Read original v4 JSON evidence; never run, replay, or alter a flight.

Standard library only. Protocol creation is explicit and prospective. This is
an independent descriptive appendix, not a replacement for original gates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math
import os
from pathlib import Path
import re

KIND = "PROSPECTIVE_PHYSICAL_RECOVERY_APPENDIX_V1"
GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing",
          "stage3_midpoint", "stage3_active", "stage3_multi_active")
SELECTED = ("stage2_crossing", "stage3_multi_active")
EVENTS = {"shutter", "shutter_hold_finished", "shutter_schedule_failure",
          "shutter_service_result", "initial_selection_requested",
          "initial_selection_confirmed", "explicit_reselection_requested",
          "explicit_reselection_confirmed"}
FILES = {"identity": "physical_identity.json", "navigation": "navigation_reference_evaluation.json",
         "navigation_frames": "navigation_reference_evaluation.frames.jsonl",
         "telemetry": "telemetry.jsonl", "summary": "summary.json"}
RULE = {
    "key": ["source_image_microsecond", "target_uuid", "canonical_positive_track_id"],
    "microsecond_rule": "Decimal(str(seconds))*1000000; ROUND_HALF_EVEN; no nearest join",
    "duplicate_rule": "Every duplicate normalized navigation or identity key is ambiguous, even identical bytes",
    "short_window": "[original short open request, open+3 ROS simulation seconds]",
    "reselection_window": "[explicit_reselection_requested, request+3 ROS simulation seconds]; NEW descriptive window, not an old gate",
    "window_cutoff": "Earliest of deadline, next REQUEST, original monitor/navigation/identity recording endpoint; next-REQUEST cutoff is right-open",
    "lifecycle_rule": "Original CLEAR/RESET or uncertain task-boundary cells in the relevant context remain evidence; candidates after that evidence do not resurrect the old REQUEST",
    "physical_guard": "Preserve original shutter request intervals expanded by inclusive +/-1 second, including unclosed intervals",
    "candidate": "monitor navigation_state; state==1; matching requested UUID; finite vectors and nonnegative age; source<=receive+1e-8; age+receive-source<=0.75+1e-9; source and receive both >=anchor",
    "candidate_limit": "Monitor does not save frame_id. Observed-field eligibility does not reproduce complete original navigation_valid or active",
    "stream_gap_s": 0.15,
    "stream_gap_scope": "Receive-stream coverage diagnostic only; not a source-to-receive transport limit",
    "identity_rule": "Unique exact source/UUID/track join; match.status==known and physical_id present; prefer full-task requested-actor mapping; conflicting nonempty mappings are incomplete",
    "initial_selection": "Context only, never an explicit reselection opportunity",
    "first_and_later": "Keep first eligible MEASURED identity, later first supported original actor, and every observed different actor separately",
    "main_numerator": "Opportunity has supported original-actor evidence and no observed different-from-original evidence; UNKNOWN does not establish continuous identity safety",
    "main_denominator": "Every opportunity registered for all 40 selected original formal slots, including absent/stopped/incomplete trials",
    "reselection_semantics": "Different from original can be a legitimate new request; only mismatch against independently mapped NEW requested actor is wrong_requested_actor",
}
MAX_JSON = 32 * 1024 * 1024
MAX_LINE = 4 * 1024 * 1024
MAX_ROWS = 200000


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def us(value):
    require(number(value), "Nonfinite or nonnumeric ROS simulation time")
    return int((Decimal(str(value)) * 1000000).to_integral_value(rounding=ROUND_HALF_EVEN))


def text(value):
    require(isinstance(value, str) and bool(value) and value == value.strip(), "Missing/invalid identity string")
    return value


def track(value):
    require(type(value) is int or isinstance(value, str), "Invalid track ID type")
    value = str(value)
    require(re.fullmatch(r"[1-9][0-9]*", value) is not None, "Noncanonical/nonpositive track ID")
    return value


def key(stamp, uuid, track_id):
    return us(stamp), text(uuid), track(track_id)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def digest_without(value, field):
    return canonical({k: v for k, v in value.items() if k != field})


def strict_json(payload):
    def reject(value):
        raise ValueError("Nonfinite JSON number: " + value)
    def finite(value):
        result = float(value)
        require(math.isfinite(result), "Nonfinite JSON number")
        return result
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, "Duplicate JSON object key: " + name)
            result[name] = value
        return result
    return json.loads(payload, parse_constant=reject, parse_float=finite, object_pairs_hook=pairs)


def native(value):
    """Never interpret an inaccessible /root path as Windows proof of absence."""
    require(isinstance(value, str), "Native absolute path required")
    if os.name == "nt":
        require(not value.startswith("/"), "POSIX input path is not observable on this platform")
    else:
        require(re.match(r"^[A-Za-z]:", value) is None and "\\" not in value,
                "Windows input path is not observable on this platform")
    path = Path(value)
    require(path.is_absolute(), "Native absolute path required")
    return path.resolve()


class Inputs:
    """Full-file hash, bounded records, no unused telemetry retained."""
    def __init__(self):
        self.bindings = {}

    def read(self, role, path, *, lines=False, keep=None):
        path = native(str(path))
        binding = {"path": str(path), "status": "MISSING"}
        self.bindings[role] = binding
        require(path.is_file(), "Missing source: " + str(path))
        before = path.stat()
        h = hashlib.sha256()
        result = [] if lines else None
        error = None
        try:
            if lines:
                with path.open("rb") as stream:
                    line_no = 0
                    for line in iter(lambda: stream.readline(MAX_LINE + 1), b""):
                        line_no += 1
                        h.update(line)
                        if len(line) > MAX_LINE:
                            raise ValueError("Oversized JSONL record")
                        if not line.strip():
                            continue
                        row = strict_json(line)
                        require(isinstance(row, dict), "JSONL record must be an object")
                        if keep is None or keep(row):
                            result.append({"line_number": line_no, "record": row})
                            require(len(result) <= MAX_ROWS, "Too many retained rows; never truncate")
                binding.update(lines=line_no, retained=len(result))
            else:
                require(before.st_size <= MAX_JSON, "Oversized JSON document")
                payload = path.read_bytes()
                h.update(payload)
                result = strict_json(payload)
                require(isinstance(result, dict), "JSON document must be an object")
        except (ValueError, OSError, UnicodeError) as exc:
            error = exc
        after = path.stat()
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                "Input changed during complete read")
        if error is not None:
            # Bind invalid existing bytes too, without accepting parsed prefixes.
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            binding.update(status="INVALID", bytes=after.st_size, sha256=h.hexdigest(), error=str(error))
            raise ValueError(str(error))
        binding.update(status="COMPLETE", bytes=after.st_size, sha256=h.hexdigest())
        return result


def pinned(binding):
    require(set(binding) == {"path", "sha256"}, "Exact path/SHA binding required")
    reader = Inputs()
    result = reader.read("pinned", binding["path"])
    require(reader.bindings["pinned"]["sha256"] == binding["sha256"], "Pinned source changed")
    return result


def tool_pin():
    path = Path(__file__).resolve()
    return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_plan(plan, path):
    require(plan.get("schema_version") == 1 and plan.get("study_kind") == "POST_REPAIR_ENGINEERING_VALIDATION"
            and plan.get("mode") == "FORMAL", "Original FORMAL120 plan required")
    require(plan.get("plan_sha256") == digest_without(plan, "plan_sha256"), "Internal core plan digest changed")
    require(plan.get("selected_classes") == ["person", "car"] and plan.get("selected_groups") == list(GROUPS)
            and plan.get("selected_seeds") == list(range(1000, 1010)), "Full formal class/group/seed axes required")
    trials = plan.get("trials", [])
    require(len(trials) == 120 and len({t["id"] for t in trials}) == 120
            and len({t["directory"] for t in trials}) == 120, "Full original120 denominator/unique sources required")
    require({(t["target_class"], t["group"], t["seed"]) for t in trials} ==
            {(c, g, s) for c in ("person", "car") for g in GROUPS for s in range(1000, 1010)}, "Foreign/missing original cells")
    require(isinstance(plan.get("source_hashes"), dict) and bool(plan["source_hashes"])
            and bool(plan.get("development_probe_gate")), "Original registered development/source bindings required")
    root, output = native(plan["frozen_root"]), native(plan["output"])
    require(root.is_dir() and output.is_dir() and native(str(path)) == output / "plan.json",
            "Plan must be at its actual accessible original output path")
    list(output.iterdir())  # Absence is meaningful only in an observable native tree.
    observable_parents = set()
    for trial in trials:
        text(trial["id"])
        require(re.fullmatch(r"[A-Za-z0-9_]+", trial["id"]) is not None, "Unsafe original slot ID")
        require(type(trial["seed"]) is int and type(trial["stage"]) is int
                and trial["stage"] == int(trial["group"][5]), "Original stage/group mismatch")
        directory = native(trial["directory"])
        require(directory.parent.is_dir(), "Trial parent is inaccessible; absence cannot be established")
        if directory.parent not in observable_parents:
            list(directory.parent.iterdir())
            observable_parents.add(directory.parent)
    return plan


def slots_for(plan):
    return [{"slot_id": t["id"], "source_trial": t["directory"], "target_class": t["target_class"],
             "group": t["group"], "seed": t["seed"],
             "opportunities": [{"id": t["id"] + ":short", "kind": "short"},
                               {"id": t["id"] + ":long_explicit_reselection", "kind": "long_explicit_reselection"}]}
            for t in plan["trials"] if t["group"] in SELECTED]


def check_starts(plan, created=None):
    evidence = []
    slot_dir = native(plan["output"]) / "slots"
    if slot_dir.exists():
        require(slot_dir.is_dir(), "Original slots location is not a directory")
        list(slot_dir.iterdir())
    for trial in plan["trials"]:
        start = slot_dir / (trial["id"] + ".started.json")
        terminal = slot_dir / (trial["id"] + ".json")
        directory = native(trial["directory"])
        if created is None:
            require(not start.exists() and not terminal.exists() and not directory.exists()
                    and not directory.is_symlink(), "Protocol must precede every original formal START/product")
        elif start.exists():
            reader = Inputs()
            marker = reader.read("start", start)
            require(marker.get("id") == trial["id"] and marker.get("plan_sha256") == plan["plan_sha256"],
                    "Original START binding differs")
            began = utc(marker["started_utc"])
            require(created < began, "Supplement protocol is not earlier than all formal STARTs")
            evidence.append({"slot_id": trial["id"], **reader.bindings["start"], "started_utc": marker["started_utc"]})
        else:
            require(not terminal.exists() and not directory.exists(), "Formal products without preserved START cannot prove prospective order")
    return evidence


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, "UTC with explicit zero offset required")
    return parsed


def make_protocol(core_binding):
    plan = validate_plan(pinned(core_binding), core_binding["path"])
    check_starts(plan)
    slots = slots_for(plan)
    require(len(slots) == 40, "Exactly all40 multi-target original slots required")
    return {"schema_version": 1, "kind": KIND, "created_utc": datetime.now(timezone.utc).isoformat(),
            "core_plan": core_binding, "core_plan_digest": plan["plan_sha256"], "producer": tool_pin(),
            "rule": RULE, "slots": slots, "original_core_denominator": 120,
            "registered_slots": len(slots), "registered_opportunities": sum(len(s["opportunities"]) for s in slots),
            "all120_unattempted_at_creation": True,
            "scope": "Prospective independent appendix only; not formal admission, runtime control, or automatic ReID"}


def validate_protocol(protocol):
    require(protocol.get("schema_version") == 1 and protocol.get("kind") == KIND and protocol.get("rule") == RULE,
            "Foreign or modified supplementary protocol")
    require(protocol.get("producer") == tool_pin(), "Producer code SHA changed after prospective registration")
    plan = validate_plan(pinned(protocol["core_plan"]), protocol["core_plan"]["path"])
    require(protocol.get("core_plan_digest") == plan["plan_sha256"] and protocol.get("slots") == slots_for(plan)
            and protocol.get("registered_slots") == 40 and protocol.get("registered_opportunities") == 80
            and protocol.get("original_core_denominator") == 120 and protocol.get("all120_unattempted_at_creation") is True,
            "Supplement omitted/relabelled original planned opportunities")
    starts = check_starts(plan, utc(protocol["created_utc"]))
    return plan, starts


def external_output(path, plan, protocol_file=None):
    target = native(str(path))
    protected = [native(plan["frozen_root"]), native(plan["output"]),
                 (native(plan["frozen_root"]) / "results").resolve(), Path(__file__).resolve().parent]
    protected += [native(t["directory"]) for t in plan["trials"]]
    if protocol_file is not None:
        protected.append(native(str(protocol_file)))
    require(not any(target == p or target.is_relative_to(p) for p in protected), "New output is inside original/source evidence")
    require(not target.exists() and not target.is_symlink(), "Output must be an entirely new independent directory")
    return target


def identity_contract(report):
    audit = report["conservative_task_time_identity"]
    require(audit.get("schema_version") == 1 and audit.get("sample_period_s") == .1
            and audit.get("coverage_basis") == "fixed_10hz_request_to_recorded_clock_end", "Unsupported original identity grid")
    start, end = audit["interval"]["start_s"], audit["interval"]["end_s"]
    require(number(start) and number(end) and end > start, "Invalid original identity interval")
    cells = audit["timeline"]
    expected = max(1, math.ceil((end - start) / .1 - 1e-9))
    require(len(cells) == expected == audit["scheduled_samples"], "Original identity denominator is not conserved")
    for i, row in enumerate(cells):
        require(abs(row["time_s"] - (start + .1 * i)) <= 1e-7
                and abs(row["end_s"] - min(end, start + .1 * (i + 1))) <= 1e-7,
                "Missing/reordered original identity cells")
        text(row["target_uuid"])
        require(row["outcome"] in {"correct", "wrong", "unknown"} and isinstance(row["reason"], str), "Invalid identity cell")
    counts = Counter(r["outcome"] for r in cells)
    require(all(audit[k] == counts[k] for k in ("correct", "wrong", "unknown")), "Original identity outcome counts differ")
    tasks = audit["tasks"]
    require(type(audit["requested_task_count"]) is int and audit["requested_task_count"] >= len(tasks)
            and (audit["requested_task_count"] == len(tasks) or any(t.get("duplicate_request_uuid") is True for t in tasks.values())),
            "Original full-request mapping denominator differs")
    for uuid, task in tasks.items():
        text(uuid)
        us(task["request_time_s"])
        if task.get("confirmation_time_s") is not None:
            require(task["confirmation_time_s"] >= task["request_time_s"], "Confirmation predates its request")
        require(type(task.get("confirmed")) is bool and task["confirmed"] == (task.get("confirmation_time_s") is not None)
                and type(task.get("initial_mapping_known")) is bool
                and task["initial_mapping_known"] == (task.get("expected_physical_id") is not None)
                and type(task.get("duplicate_request_uuid")) is bool, "Original request mapping flags differ")
        subset = [r for r in cells if r["target_uuid"] == uuid]
        require(task["scheduled_samples"] == len(subset)
                and all(task[k] == sum(r["outcome"] == k for r in subset) for k in ("correct", "wrong", "unknown")),
                "Original per-task denominator differs")
    require(set(r["target_uuid"] for r in cells).issubset(tasks), "Identity cell has no registered request")
    return audit


def navigation_contract(report, frames):
    require(report.get("schema_version") == 1, "Unsupported original navigation schema")
    interval = report["interval"]
    start, end, cutoff = (interval[k] for k in ("start_s", "end_s", "navigation_evaluation_start_s"))
    require(all(number(v) for v in (start, end, cutoff)) and start <= cutoff <= end
            and interval["sample_period_s"] == .1, "Invalid original navigation grid")
    n = math.floor((end - start) / .1 + 1e-8) + 1
    require(len(frames) == n == report["whole_interval"]["scheduled_samples"], "Original navigation denominator differs")
    for i, row in enumerate(frames):
        require(number(row.get("time_s")) and abs(row["time_s"] - (start + i * .1)) <= 1e-7,
                "Missing/reordered original navigation point")
        require(type(row.get("navigation_valid")) is bool and type(row.get("active")) is bool
                and (type(row.get("navigation_state")) is int or row.get("navigation_state") is None),
                "Missing original navigation validity/state; active is not MEASURED")
        require((not row["navigation_valid"] or row["navigation_state"] in (1, 2))
                and (not row["active"] or row["navigation_valid"]), "Original navigation validity contradicts state/active")
    scoped = [r for r in frames if r["time_s"] >= cutoff - 1e-9]
    counts = report["kf_navigation"]["counts"]
    require(counts["scheduled_samples"] == len(scoped)
            and counts.get("valid_navigation_samples", 0) == sum(r["navigation_valid"] for r in scoped),
            "Original navigation validity denominator differs")
    return end


def mappings(report, audit):
    result = {}
    for uuid, task in audit["tasks"].items():
        expected = task.get("expected_physical_id")
        old = report.get("tasks", {}).get(uuid, {}).get("initial_mapping", {}).get("physical_id")
        problems = []
        if expected is not None:
            text(expected)
        if old is not None:
            text(old)
        if task.get("duplicate_request_uuid"):
            problems.append("duplicate_request_uuid")
        if expected is not None and old is not None and expected != old:
            problems.append("conflicting_full_task_and_legacy_mapping")
        # A full-request UNKNOWN is not filled from the observed-task subset.
        result[uuid] = {"expected_physical_id": expected if not problems else None, "issues": problems,
                        "full_task": task, "legacy_physical_id": old,
                        "legacy_initial_mapping": report.get("tasks", {}).get(uuid, {}).get("initial_mapping")}
    return result


def task_at(audit, when):
    eligible = [(us(t["request_time_s"]), u) for u, t in audit["tasks"].items() if us(t["request_time_s"]) <= us(when)]
    if not eligible:
        return None, ["no_registered_original_task"]
    latest = max(t for t, _ in eligible)
    uuids = [u for t, u in eligible if t == latest]
    if len(uuids) != 1:
        return None, ["ambiguous_task_request_boundary"]
    uuid = uuids[0]
    confirmed = audit["tasks"][uuid].get("confirmation_time_s")
    if confirmed is None or us(confirmed) > us(when):
        return uuid, ["original_task_not_confirmed_before_occlusion"]
    cells = [r for r in audit["timeline"] if us(r["time_s"]) <= us(when) < us(r["end_s"])]
    if len(cells) != 1 or cells[0]["target_uuid"] != uuid:
        return uuid, ["ambiguous_original_task_cell_at_occlusion"]
    if cells[0]["reason"] in {"task_cleared_or_reset", "task_boundary_within_time_cell", "request_not_yet_confirmed"}:
        return uuid, ["inactive_or_uncertain_original_task_at_occlusion:" + cells[0]["reason"]]
    return uuid, []


def shutters(events):
    result, active = [], None
    for wrapped in events:
        row = wrapped["record"]
        if row["kind"] != "shutter":
            continue
        require(type(row.get("active")) is bool, "Invalid original shutter state")
        if row["active"] and active is None:
            active = wrapped
        elif not row["active"] and active is not None:
            result.append({"start_s": active["record"]["time_s"], "end_s": row["time_s"]})
            active = None
    if active is not None:
        result.append({"start_s": active["record"]["time_s"], "end_s": None})
    return result


def episode(events, name):
    holds = [w for w in events if w["record"]["kind"] == "shutter_hold_finished" and w["record"].get("name") == name]
    require(len(holds) == 1, "Missing/duplicate original " + name + " hold completion")
    hold = holds[0]["record"]
    require(hold.get("state") == "complete", "Original shutter episode did not complete")
    linked = []
    for role, active in (("close", True), ("open", False)):
        request_id = hold.get(role + "_request_id")
        require(type(request_id) is int and request_id > 0, "Invalid original shutter request ID")
        rows = [w for w in events if w["record"]["kind"] == "shutter" and not w["record"].get("refresh")
                and not w["record"].get("cleanup") and w["record"].get("request_id") == request_id]
        require(len(rows) == 1 and rows[0]["record"].get("active") is active, "Missing/ambiguous original shutter linkage")
        failed = [w for w in events if (w["record"]["kind"] == "shutter_service_result"
                  and w["record"].get("request_id") == request_id and w["record"].get("success") is False)
                  or (w["record"]["kind"] == "shutter_schedule_failure" and w["record"].get("name") == name)]
        require(not failed, "Original failed shutter action cannot be replaced")
        linked.append(rows[0])
    require(us(linked[0]["record"]["time_s"]) < us(linked[1]["record"]["time_s"]), "Shutter clock order invalid")
    return {"hold": holds[0], "close": linked[0], "open": linked[1]}


def candidate_problem(row, anchor, end, uuid):
    if type(row.get("state")) is not int or row["state"] != 1:
        return "not_MEASURED"
    try:
        key(row["stamp_s"], row["target_uuid"], row["track_id"])
    except (ValueError, KeyError):
        return "invalid_source_or_identity_key"
    if row["target_uuid"] != uuid:
        return "requested_task_mismatch"
    age, received, source = row.get("prediction_age_s"), row["time_s"], row["stamp_s"]
    if not number(age) or age < 0 or source > received + 1e-8 or age + received - source > .75 + 1e-9:
        return "invalid_or_stale_measurement_clock"
    if not (us(anchor) <= us(source) <= us(received) <= us(end)):
        return "source_or_receive_outside_observation_window"
    if any(not isinstance(row.get(k), list) or len(row[k]) != 3 or not all(number(x) for x in row[k])
           for k in ("position_m", "velocity_mps")):
        return "missing_or_nonfinite_navigation_vector"
    return None


def identity_index(report):
    index = defaultdict(list)
    invalid = []
    for i, row in enumerate(report.get("selected_identity_timeline", [])):
        try:
            index[key(row["time_s"], row["target_uuid"], row["selected_track_id"])].append({"row_index": i, "record": row})
        except (ValueError, KeyError) as exc:
            invalid.append({"row_index": i, "record": row, "reason": str(exc)})
    return index, invalid


def physical_match(row, index, duplicate_nav, windows, mapping):
    exact = key(row["stamp_s"], row["target_uuid"], row["track_id"])
    matches = index.get(exact, [])
    result = {"join_key": list(exact), "identity_rows": matches, "physical_id": None, "reason": None}
    if duplicate_nav[exact] != 1:
        result["reason"] = "duplicate_navigation_exact_key"
    elif len(matches) != 1:
        result["reason"] = "no_exact_identity_key" if not matches else "duplicate_identity_exact_key"
    elif mapping["issues"]:
        result["reason"] = ";".join(mapping["issues"])
    elif any(us(w["start_s"]) - 1000000 <= exact[0] <= (us(w["end_s"]) + 1000000 if w["end_s"] is not None else math.inf) for w in windows):
        result["reason"] = "original_inclusive_shutter_guard"
    else:
        identity = matches[0]["record"]
        matching = identity.get("match", identity.get("matching", {}))
        if "match" in identity and "matching" in identity and identity["match"] != identity["matching"]:
            result["reason"] = "conflicting_match_aliases"
        elif (identity.get("expected_physical_id") is not None and mapping["expected_physical_id"] is not None
              and identity["expected_physical_id"] != mapping["expected_physical_id"]):
            result["reason"] = "identity_row_conflicts_with_full_task_mapping"
        elif matching.get("status") != "known" or matching.get("physical_id") is None:
            result["reason"] = matching.get("reason", "unknown_physical_geometry")
        elif identity.get("matched_physical_id") != matching["physical_id"]:
            result["reason"] = "conflicting_matched_physical_id"
        else:
            result["physical_id"] = text(matching["physical_id"])
    return result


def relation(actual, expected, different):
    return "UNKNOWN" if actual is None or expected is None else ("SAME" if actual == expected else different)


def empty_opportunity(spec, reason):
    return {**spec, "evidence_status": "INCOMPLETE_EVIDENCE", "issues": [reason], "candidates": [],
            "first_measured": None, "first_measured_original_outcome": "UNKNOWN",
            "first_supported_original": None, "first_supported_requested": None,
            "different_from_original_evidence": [], "wrong_requested_actor_evidence": [],
            "original_confirmation_delay_s": None, "requested_confirmation_delay_s": None,
            "confirmed_original_without_observed_different": False,
            "confirmed_requested_without_observed_wrong": False,
            "first_measured_requested_outcome": "UNKNOWN",
            "right_censored": None, "navigation_receive_stream_complete": False}


def analyze_opportunity(spec, events, nav, audit, maps, index, nav_duplicates, windows, end):
    result = empty_opportunity(spec, "not_evaluated")
    result["issues"] = []
    try:
        short = spec["kind"] == "short"
        context = episode(events, "short" if short else "long")
        close, opened = (context[k]["record"]["time_s"] for k in ("close", "open"))
        old_uuid, issues = task_at(audit, close)
        result.update(original_episode=context, old_target_uuid=old_uuid)
        result["issues"].extend(issues)
        require(old_uuid in maps, "Original physical request mapping missing")
        if short:
            uuid, anchor = old_uuid, opened
            if any(u != uuid and us(close) < us(t["request_time_s"]) <= us(anchor)
                   for u, t in audit["tasks"].items()):
                result["issues"].append("task_changed_during_short_occlusion")
        else:
            requests = [w for w in events if w["record"]["kind"] == "explicit_reselection_requested"]
            require(len(requests) == 1, "Missing/duplicate explicit reselection REQUEST; initial selection is not reselection")
            request = requests[0]
            result["original_reselection_request"] = request
            uuid, anchor = text(request["record"]["target_uuid"]), request["record"]["time_s"]
            require(us(anchor) >= us(opened), "Explicit reselection precedes long open request")
            require(uuid in maps, "New REQUEST absent from original full-task mapping")
            source = request["record"].get("image_stamp_s")
            require(number(source) and us(source) == us(audit["tasks"][uuid].get("source_image_s")),
                    "Explicit REQUEST source image differs from independent task mapping")
        old, new = maps[old_uuid], maps[uuid]
        result["issues"].extend(old["issues"] + new["issues"])
        next_requests = [t["request_time_s"] for u, t in audit["tasks"].items()
                         if u != uuid and us(t["request_time_s"]) > us(anchor)]
        stop = min([end, anchor + 3.] + next_requests)
        next_cutoff = min(next_requests) if next_requests else None
        right_open = next_cutoff is not None and us(next_cutoff) == us(stop)
        require(us(stop) >= us(anchor), "Recording stopped before the planned event anchor")
        result.update(new_target_uuid=uuid, old_mapping=old, new_mapping=new,
                      original_expected_physical_id=old["expected_physical_id"], requested_expected_physical_id=new["expected_physical_id"],
                      reselection_request_original_relation=None if short else relation(new["expected_physical_id"], old["expected_physical_id"], "DIFFERENT_FROM_ORIGINAL"),
                      anchor_s=anchor, planned_deadline_s=anchor + 3., observation_end_s=stop,
                      observation_end_inclusive=not right_open,
                      right_censored=us(stop) < us(anchor + 3.))
        lifecycle = [r for r in audit["timeline"] if r["target_uuid"] == uuid
                     and us(r["end_s"]) > us(close if short else anchor) and us(r["time_s"]) <= us(stop)
                     and r["reason"] in {"task_cleared_or_reset", "task_boundary_within_time_cell"}]
        result["original_lifecycle_cells"] = lifecycle
        in_window = [w for w in nav if us(anchor) <= us(w["record"]["time_s"]) <= us(stop)]
        receive_times = [us(w["record"]["time_s"]) for w in in_window]
        gaps = [b-a for a, b in zip([us(anchor)] + receive_times, receive_times + [us(stop)])]
        result["navigation_receive_stream_complete"] = bool(in_window and max(gaps) <= 150000 and not result["right_censored"])
        original_task_issues = tuple(result["issues"])
        for wrapped in in_window:
            row = wrapped["record"]
            problem = candidate_problem(row, anchor, stop, uuid)
            if problem is None and right_open and (us(row["time_s"]) >= us(stop) or us(row["stamp_s"]) >= us(stop)):
                problem = "next_REQUEST_cutoff_is_right_open"
            if problem is None and any(us(cell["time_s"]) <= us(row["time_s"]) for cell in lifecycle):
                problem = "task_cleared_reset_or_uncertain_boundary_before_candidate"
            item = {"navigation": wrapped, "source_s": row.get("stamp_s"), "receive_s": row["time_s"],
                    "eligibility_issue": problem, "physical_id": None,
                    "original_outcome": "UNKNOWN", "requested_outcome": "UNKNOWN"}
            if problem is None:
                item.update(physical_match(row, index, nav_duplicates, windows, new))
                if item.get("reason") in {"identity_row_conflicts_with_full_task_mapping", "conflicting_match_aliases",
                                          "conflicting_matched_physical_id"}:
                    result["issues"].append(item["reason"])
                if not original_task_issues:
                    item["original_outcome"] = relation(item["physical_id"], old["expected_physical_id"], "WRONG" if short else "DIFFERENT_FROM_ORIGINAL")
                    item["requested_outcome"] = relation(item["physical_id"], new["expected_physical_id"], "WRONG_REQUESTED_ACTOR")
            result["candidates"].append(item)
        eligible = [r for r in result["candidates"] if r["eligibility_issue"] is None]
        result["first_measured"] = eligible[0] if eligible else None
        result["first_measured_original_outcome"] = eligible[0]["original_outcome"] if eligible else "UNKNOWN"
        result["first_measured_requested_outcome"] = eligible[0]["requested_outcome"] if eligible else "UNKNOWN"
        result["no_eligible_measured"] = not eligible
        for target in ("original", "requested"):
            supported = next((r for r in eligible if r[target + "_outcome"] == "SAME"), None)
            result["first_supported_" + target] = supported
            result[target + "_confirmation_delay_s"] = ((us(supported["receive_s"]) - us(anchor)) / 1e6) if supported else None
        result["different_from_original_evidence"] = [r for r in eligible if r["original_outcome"] in {"WRONG", "DIFFERENT_FROM_ORIGINAL"}]
        result["wrong_requested_actor_evidence"] = [r for r in eligible if r["requested_outcome"] == "WRONG_REQUESTED_ACTOR"]
        result["confirmed_original_without_observed_different"] = bool(result["first_supported_original"] and not result["different_from_original_evidence"] and not result["issues"])
        result["confirmed_requested_without_observed_wrong"] = bool(result["first_supported_requested"] and not result["wrong_requested_actor_evidence"] and not result["issues"])
        result["evidence_status"] = "INCOMPLETE_EVIDENCE" if result["issues"] else "RECORDED_WITH_EXPLICIT_UNKNOWN_AND_CENSORING"
    except (ValueError, KeyError, TypeError) as exc:
        result["issues"].append(str(exc))
    return result


def analyze_records(slot, identity, navigation, frames, summary, telemetry):
    audit = identity_contract(identity)
    endpoints = [audit["interval"]["end_s"], navigation_contract(navigation, frames), summary["end_sim_s"]]
    require(all(number(value) for value in endpoints), "Missing original ROS simulation endpoint")
    end = min(endpoints)
    rows = [w["record"] for w in telemetry]
    require(all(number(r.get("time_s")) for r in rows), "Invalid monitor ROS simulation timestamp")
    require(all(b["time_s"] >= a["time_s"] for a, b in zip(rows, rows[1:])), "Monitor simulation clock regressed")
    nav = [w for w in telemetry if w["record"]["kind"] == "navigation_state"]
    counts = Counter()
    for wrapped in nav:
        row = wrapped["record"]
        if row.get("state") == 1:
            try:
                counts[key(row["stamp_s"], row["target_uuid"], row["track_id"]) ] += 1
            except (ValueError, KeyError):
                pass
    maps = mappings(identity, audit)
    index, invalid = identity_index(identity)
    events = [w for w in telemetry if w["record"]["kind"] in EVENTS]
    windows = shutters(events)
    output = [analyze_opportunity(spec, events, nav, audit, maps, index, counts, windows, end) for spec in slot["opportunities"]]
    return {"opportunities": output, "invalid_identity_keys": invalid, "original_events": events,
            "actual_event_counts": {"short_hold_completions": sum(r["kind"] == "shutter_hold_finished" and r.get("name") == "short" for r in rows),
                                    "long_hold_completions": sum(r["kind"] == "shutter_hold_finished" and r.get("name") == "long" for r in rows),
                                    "explicit_reselection_requests": sum(r["kind"] == "explicit_reselection_requested" for r in rows),
                                    "initial_selection_requests_context_only": sum(r["kind"] == "initial_selection_requested" for r in rows)},
            "recorded_observation_endpoint_s": end}


def analyze_slot(plan, slot):
    reader = Inputs()
    terminal_path = native(plan["output"]) / "slots" / (slot["slot_id"] + ".json")
    source_paths = {"terminal": terminal_path, **{role: native(slot["source_trial"]) / relative for role, relative in FILES.items()}}
    reader.bindings.update({role: {"path": str(path), "status": "NOT_READ"} for role, path in source_paths.items()})
    result = {**slot, "original_terminal_status": None, "issues": [], "source_bindings": reader.bindings,
              "registered_event_counts": {"short": 1, "long_context": 1, "explicit_reselection": 1},
              "actual_event_counts": {"short_hold_completions": None, "long_hold_completions": None,
                                      "explicit_reselection_requests": None, "initial_selection_requests_context_only": None},
              "opportunities": [empty_opportunity(s, "missing_original_terminal_or_sources") for s in slot["opportunities"]]}
    try:
        terminal = reader.read("terminal", terminal_path)
        require(terminal.get("id") == slot["slot_id"] and terminal.get("plan_sha256") == plan["plan_sha256"]
                and terminal.get("record_sha256") == digest_without(terminal, "record_sha256"), "Original terminal binding/digest invalid")
        result["original_terminal_status"] = terminal.get("status")
        objects = {}
        for role, relative in FILES.items():
            lines = role in {"telemetry", "navigation_frames"}
            keep = (lambda r: r.get("kind") in EVENTS | {"navigation_state"}) if role == "telemetry" else None
            objects[role] = reader.read(role, native(slot["source_trial"]) / relative, lines=lines, keep=keep)
            require(terminal.get("artifact_hashes", {}).get(relative) == reader.bindings[role]["sha256"], "Original terminal artifact hash missing/different: " + relative)
        require(objects["navigation"].get("physical_identity_sha256") == reader.bindings["identity"]["sha256"], "Original navigation->physical report SHA binding differs")
        require(native(objects["identity"]["source_trial"]) == native(slot["source_trial"])
                and native(objects["navigation"]["trial"]) == native(slot["source_trial"]), "Original report trial source differs")
        frames = [w["record"] for w in objects["navigation_frames"]]
        result.update(analyze_records(slot, objects["identity"], objects["navigation"], frames, objects["summary"], objects["telemetry"]))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result["issues"].append(str(exc))
    for opportunity in result["opportunities"]:
        opportunity["source_hashes"] = {role: binding.get("sha256") for role, binding in reader.bindings.items()}
        opportunity["registered_opportunity_count"] = 1
        opportunity["slot_actual_event_counts"] = result["actual_event_counts"]
    return result


def summarize(slots):
    opportunities = [r for slot in slots for r in slot["opportunities"]]
    result = {}
    for kind in ("short", "long_explicit_reselection", "all"):
        rows = [r for r in opportunities if kind == "all" or r["kind"] == kind]
        n = len(rows)
        delays = [r["original_confirmation_delay_s"] for r in rows if r.get("original_confirmation_delay_s") is not None]
        requested_delays = [r["requested_confirmation_delay_s"] for r in rows if r.get("requested_confirmation_delay_s") is not None]
        confirmed = sum(r["confirmed_original_without_observed_different"] for r in rows)
        result[kind] = {"registered_opportunities": n, "supported_original_without_observed_different": confirmed,
                        "descriptive_lower_bound": confirmed / n if n else None,
                        "ever_supported_original": sum(r.get("first_supported_original") is not None for r in rows),
                        "known_different_from_original_opportunities": sum(bool(r["different_from_original_evidence"]) for r in rows),
                        "wrong_requested_actor_opportunities": sum(bool(r["wrong_requested_actor_evidence"]) for r in rows),
                        "supported_requested_without_observed_wrong": sum(r["confirmed_requested_without_observed_wrong"] for r in rows),
                        "first_measured_original_outcomes": dict(Counter(r["first_measured_original_outcome"] for r in rows)),
                        "right_censored": sum(r["right_censored"] is True for r in rows),
                        "missing_or_invalid_events": sum(r["evidence_status"] == "INCOMPLETE_EVIDENCE" for r in rows),
                        "original_confirmation_delay_s": {"n": len(delays), "N": n,
                            "mean": math.fsum(delays) / len(delays) if delays else None,
                            "minimum": min(delays) if delays else None, "maximum": max(delays) if delays else None},
                        "requested_confirmation_delay_s": {"n": len(requested_delays), "N": n,
                            "mean": math.fsum(requested_delays) / len(requested_delays) if requested_delays else None},
                        "claim_boundary": "Observed descriptive lower bound; UNKNOWN is retained and does not prove continuous identity safety. Explicit selection of another actor is not a system ID switch."}
    result["actual_event_counts"] = {}
    for name in ("short_hold_completions", "long_hold_completions", "explicit_reselection_requests", "initial_selection_requests_context_only"):
        known = [s["actual_event_counts"][name] for s in slots if s.get("actual_event_counts", {}).get(name) is not None]
        result["actual_event_counts"][name] = {"observed_count_in_known_slots": sum(known), "known_slots": len(known), "planned_slots": len(slots)}
    return result


def analyze(protocol_binding):
    protocol = pinned(protocol_binding)
    plan, starts = validate_protocol(protocol)
    slots = [analyze_slot(plan, s) for s in protocol["slots"]]
    return {"schema_version": 1, "kind": KIND, "scope": "INDEPENDENT_PHYSICAL_RECOVERY_APPENDIX_NOT_ORIGINAL_VERDICTS",
            "evaluation_status": "DESCRIPTIVE_APPENDIX_WITH_EXPLICIT_UNKNOWN_AND_MISSING_OPPORTUNITIES",
            "created_utc": datetime.now(timezone.utc).isoformat(), "protocol_binding": protocol_binding,
            "producer": tool_pin(), "rule": RULE, "original_start_bindings": starts, "slots": slots,
            "summary": summarize(slots), "formal_flights_started_by_this_tool": 0,
            "observed_original_core_starts": len(starts),
            "limitations": ["Monitor frame_id was not recorded: full original navigation_valid is not reproduced",
                "No 10 Hz grid overlap, UUID equality, active state, or later same identity fills missing source-image evidence",
                "Explicit reselection is user/test-script assisted, not automatic ReID",
                "All original PASS/FAIL, identity cells and input files remain unchanged"]}


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def write_appendix(directory, report):
    write_new(directory / "physical_recovery.json", report)
    columns = ["slot_id", "opportunity_id", "kind", "original_terminal_status", "evidence_status",
               "reselection_request_original_relation", "first_measured_original_outcome", "first_measured_requested_outcome",
               "original_confirmation_delay_s", "requested_confirmation_delay_s",
               "right_censored", "confirmed_original_without_observed_different"]
    with (directory / "physical_recovery.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for slot in report["slots"]:
            for event in slot["opportunities"]:
                writer.writerow({"slot_id": slot["slot_id"], "opportunity_id": event["id"],
                                 "original_terminal_status": slot["original_terminal_status"],
                                 **{k: event.get(k) for k in columns if k in event and k != "opportunity_id"}})
    totals = report["summary"]["all"]
    body = ("# Independent physical recovery appendix\n\n"
            "Original results are unchanged. Monitor frame_id is unavailable; eligibility covers recorded fields only.\n\n"
            f"Registered opportunities: {totals['registered_opportunities']}. Supported original actor with no observed different actor: "
            f"{totals['supported_original_without_observed_different']}/{totals['registered_opportunities']}. "
            "UNKNOWN remains in this descriptive denominator; it does not prove continuous identity safety.\n\n"
            f"Original-actor confirmation times: n/N={totals['original_confirmation_delay_s']['n']}/{totals['registered_opportunities']}; "
            "unconfirmed observations remain null. Explicit selection of a different actor is not automatically a tracker identity switch.\n\n"
            "[Event table](physical_recovery.csv) / [Full original keys, hashes and evidence](physical_recovery.json)\n")
    with (directory / "physical_recovery.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "protocol", "analyze"), nargs="?", default="describe")
    parser.add_argument("--core-plan"); parser.add_argument("--core-sha256")
    parser.add_argument("--protocol"); parser.add_argument("--protocol-sha256")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    if args.action == "describe":
        print(json.dumps({"kind": KIND, "rule": RULE, "producer": tool_pin(), "actual_protocol_created": False,
                          "bag_reads": 0, "formal_flights_started_by_this_tool": 0}, ensure_ascii=False))
        return 0
    require(args.output_dir is not None, "Explicit new external output directory required")
    if args.action == "protocol":
        require(args.core_plan and args.core_sha256, "Explicit actual FORMAL120 path/SHA required")
        report = make_protocol({"path": str(native(args.core_plan)), "sha256": args.core_sha256})
        plan = pinned(report["core_plan"])
        output = external_output(args.output_dir, plan)
        # A second native check immediately before publication; never backdate.
        check_starts(plan)
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / "physical_recovery_protocol.json", report)
    else:
        require(args.protocol and args.protocol_sha256, "Explicit prospective protocol path/SHA required")
        binding = {"path": str(native(args.protocol)), "sha256": args.protocol_sha256}
        protocol = pinned(binding)
        plan, _ = validate_protocol(protocol)
        output = external_output(args.output_dir, plan, args.protocol)
        report = analyze(binding)
        validate_protocol(protocol)  # Inputs/START order must still bind at publication.
        output.mkdir(parents=True, exist_ok=False)
        write_appendix(output, report)
    print(json.dumps({"output": str(output), "scope": KIND, "original_results_changed": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit("INCOMPLETE_EVIDENCE: " + str(error))
