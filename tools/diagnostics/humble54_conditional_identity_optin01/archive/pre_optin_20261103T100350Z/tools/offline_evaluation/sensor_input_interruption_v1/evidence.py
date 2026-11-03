"""Read-only corroboration of upstream input interruption, never flight acceptance.

No ROS, bag reader, image inference, image brightness classifier or file writes.
Paths must already be valid in the caller's environment; no path translation.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import struct


REVISION = "sensor_input_interruption_v1"
CORROBORATED = "UPSTREAM_INPUT_INTERRUPTION_CORROBORATED"
NOT_APPLICABLE = "NOT_APPLICABLE"
INCOMPLETE = "INCOMPLETE"
SCOPE = "DEVELOPMENT_EVIDENCE_ONLY_NOT_FORMAL_ADMISSION"
FAULT_ALGORITHM = "SHA256_SEED_COLON_WINDOW_FIRST8_UINT64_DIV_2POW64_LT_FLOAT_FRACTION_V1"
RAW_RGB = "/camera/color/image_raw"
RAW_DEPTH = "/camera/aligned_depth_to_color/image_raw"
RESEARCH_RGB = "/research/camera/color/image_raw"
RESEARCH_DEPTH = "/research/camera/aligned_depth_to_color/image_raw"
DIAGNOSTIC = "/tracking/detection_diagnostics"
TOPICS = ("/clock", RAW_RGB, RAW_DEPTH, RESEARCH_RGB, RESEARCH_DEPTH, DIAGNOSTIC)
CELLS = {(cls, condition) for cls in ("person", "car") for condition in ("dropout", "combined")}
SHUTTER = ("recorded_close_event", "shutter_close_service_succeeded",
           "shutter_open_service_succeeded", "shutter_close_ack_before_open_request")
SHORT_ALGORITHM = ("prediction_observed", "no_loss_during_short_occlusion",
                   "identity_preserved_on_observed_recovery")
LONG_SAFETY = ("lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion",
               "sustained_low_speed_after_hover", "no_automatic_recovery_after_long_loss",
               "no_tracking_control_before_reselection_after_long_loss")
LONG_ALGORITHM = ("detector_interruption_observed", "prediction_observed",
                  "sustained_tracking_after_reselection")
VISIBLE = {"ONE_PERSON_AND_SCENE_VISIBLE_IN_CONTACT_SHEET",
           "ONE_CAR_AND_SCENE_VISIBLE_IN_CONTACT_SHEET", "TARGET_AND_SCENE_VISIBLE"}
OBSCURED = "SCENE_OBSCURED_NEAR_BLACK_TARGET_NOT_VISIBLE"
BOUNDARY = ("Input/stimulus evidence only. Original terminal, acceptance, checks and nulls are unchanged. "
            "Absent input is not an empty detector result. Occlusion and injected dropout effects are not "
            "separately identified. No engineering PASS, physical identity truth, navigation acceptance, "
            "formal readiness or formal execution is asserted; caller retains its navigation and safety gates.")


class EvidenceError(ValueError):
    pass


def _require(value, message):
    if not value:
        raise EvidenceError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value, exclude=None):
    if exclude is not None:
        value = {key: item for key, item in value.items() if key != exclude}
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            result.update(block)
    return result.hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _json(path):
    path = Path(path).resolve(strict=True)
    _require(path.is_file() and path.stat().st_size <= 1024 * 1024, "Missing/oversized small JSON: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError("Nonfinite JSON: " + value)))
    _require(isinstance(value, dict), "Expected JSON object: " + str(path))
    return value


def _sha(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "Invalid SHA256")
    return value


def _binding(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": _hash(path)}


def _bound(binding):
    _require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, "Expected exact path/SHA binding")
    _sha(binding["sha256"])
    path = Path(binding["path"]).resolve(strict=True)
    _require(_binding(path) == binding, "File path/SHA binding differs: " + str(path))
    return path


def _same(first, second):
    return Path(first).resolve(strict=True) == Path(second).resolve(strict=True)


def _one(rows, predicate, label):
    _require(isinstance(rows, list), "Expected list: " + label)
    matches = [row for row in rows if isinstance(row, dict) and predicate(row)]
    _require(len(matches) == 1, "Expected exactly one " + label)
    return matches[0]


def _int(value, label, minimum=0):
    _require(type(value) is int and value >= minimum, "Invalid integer: " + label)
    return value


def _decimal(value):
    _require(type(value) in {int, float, str, Decimal}, "Invalid decimal source time")
    result = Decimal(str(value))
    _require(result.is_finite(), "Nonfinite decimal source time")
    return result


def _utc(value):
    _require(isinstance(value, str) and bool(value.strip()), "Explicit UTC timestamp string required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, "Explicit UTC time required")
    return stamp


def _contract(contract):
    _require(isinstance(contract, dict), "An explicit contract is required")
    _require(contract.get("schema_version") == 1 and contract.get("revision") == REVISION
             and contract.get("scope") == SCOPE, "Wrong explicit evidence contract revision/scope")
    _require(contract.get("fault_algorithm") == FAULT_ALGORITHM
             and type(contract.get("drop_window_ns")) is int and contract["drop_window_ns"] == 200_000_000,
             "Contract must bind the original 200 ms SHA256 dropout algorithm")
    _require(_decimal(contract["drop_fraction"]) == Decimal("0.10")
             and _decimal(contract["padding_s"]) == Decimal("0.3"), "Contract differs from source fault/extraction design")
    tools = contract["extractor_sha256_by_condition"]
    _require(set(tools) == {"dropout", "combined"}, "Both explicit extractor SHAs are required")
    for value in tools.values():
        _sha(value)
    plan_path = _bound(contract["source_plan"])
    plan = _json(plan_path)
    _require(_digest(plan, "plan_sha256") == plan.get("plan_sha256"), "Original plan content digest differs")
    _require(plan.get("mode") == "EXTENSION_PROBE", "This module consumes development EXTENSION_PROBE evidence only")
    _require(_same(plan["output"], plan_path.parent), "Use the original plan in its original matrix")
    slots = contract["dev_slots"]
    _require(isinstance(slots, list) and len(slots) == 4, "Contract must fix all four development slots")
    seen, cells = set(), set()
    for row in slots:
        _require(set(row) == {"slot_id", "target_class", "condition"}, "Invalid fixed development slot declaration")
        slot = row["slot_id"]
        _require(isinstance(slot, str) and re.fullmatch(r"[A-Za-z0-9_-]+", slot) is not None and slot not in seen,
                 "Invalid/duplicate fixed slot ID")
        trial = _one(plan["trials"], lambda item: item.get("id") == slot, "planned fixed slot")
        cell = (row["target_class"], row["condition"])
        _require(cell in CELLS and cell not in cells and trial.get("target_class") == cell[0]
                 and trial.get("condition") == trial.get("extension_condition") == cell[1], "Fixed four-cell design differs from original plan")
        seen.add(slot)
        cells.add(cell)
    _require(cells == CELLS, "Contract must cover person/car x dropout/combined")
    return plan_path, plan


def _report(contract):
    return {"schema_version": 1, "revision": REVISION, "scope": SCOPE, "status": INCOMPLETE,
            "contract_sha256": _digest(contract), "module_sha256": _hash(__file__),
            "claim_boundary": BOUNDARY, "errors": [], "known_algorithm_failures": []}


def _artifact(directory, terminal, relative):
    path = (directory / relative).resolve(strict=True)
    _require(path.is_relative_to(directory), "Original artifact escapes trial")
    _require(_hash(path) == terminal["artifact_hashes"][relative], "Original artifact SHA differs: " + relative)
    return path


def _original(plan_path, plan, slot_id, result):
    trial = _one(plan["trials"], lambda row: row.get("id") == slot_id, "planned slot")
    directory = Path(trial["directory"]).resolve(strict=True)
    _require(directory.name == trial["name"] and _same(directory.parent, plan["results_root"]), "Original trial directory/name differs")
    terminal_path = plan_path.parent / "slots" / (slot_id + ".json")
    terminal = _json(terminal_path)
    result["original"] = {"terminal_status": terminal.get("status"), "engineering_evidence": deepcopy(terminal.get("engineering_evidence"))}
    _require(_digest(terminal, "record_sha256") == terminal.get("record_sha256"), "Original terminal content digest differs")
    _require(terminal.get("id") == slot_id and terminal.get("name") == trial["name"]
             and terminal.get("plan_sha256") == plan["plan_sha256"]
             and terminal.get("execution_status") == "COMPLETED" and terminal.get("infrastructure_stop") is False
             and type(terminal.get("flight_exit_code")) is int and terminal["flight_exit_code"] == 0
             and terminal.get("cleanup", {}).get("residual_processes") == [], "Original flight is not successfully closed")
    flight = _one(terminal["commands"], lambda row: row.get("kind") == "flight", "original flight command")
    _require(flight.get("error") is None and type(flight.get("returncode")) is int and flight["returncode"] == 0
             and flight.get("command") == trial["flight_command"], "Original successful flight command differs")
    argv = flight["command"]
    for flag, expected in (("--name", trial["name"]), ("--class", trial["target_class"]),
                           ("--condition", trial["condition"]), ("--seed", str(trial["seed"]))):
        _require(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv) and argv[argv.index(flag) + 1] == expected,
                 "Original flight argument differs: " + flag)
    bindings = {"plan": _binding(plan_path), "terminal": _binding(terminal_path)}
    reports = {}
    for kind, filename in (("surface_flight", "flight_evaluation.json"),
                           ("source_clock", "px4_source_clock_report.json"), ("native_startup", "native_startup_report.json")):
        path = _artifact(directory, terminal, filename)
        report = _json(path)
        spec = _one(trial["evaluations"], lambda row: row.get("kind") == kind, "original evaluation specification")
        entry = _one(terminal["evaluations"], lambda row: row.get("kind") == kind, "original evaluation entry")
        verdict = report["acceptance"]["result"] if kind == "surface_flight" else report["evaluation_status"]
        _require(_same(spec["report"], path) and _same(entry["report"], path)
                 and entry.get("report_sha256") == _hash(path)
                 and entry.get("result") == entry.get("reported_verdict") == verdict
                 and entry.get("error") is None and entry["execution"].get("error") is None
                 and type(entry["execution"].get("returncode")) is int and entry["execution"]["returncode"] == 0
                 and entry["execution"].get("command") == spec["command"], "Original evaluator entry/source differs: " + kind)
        if kind != "surface_flight":
            _require(verdict == "PASS", "Original source-clock/native-startup report did not PASS")
        reports[kind] = report
        bindings[filename] = _binding(path)
    for filename in ("recording_closure.json", "bag_integrity.json"):
        path = _artifact(directory, terminal, filename)
        _require(_json(path).get("status") == "PASS", "Original closed-recording/integrity report did not PASS")
        bindings[filename] = _binding(path)
    for filename in ("configuration/sensor_faults.json", "rosbag/metadata.yaml"):
        path = _artifact(directory, terminal, filename)
        bindings[filename] = _binding(path)
    faults = _json(directory / "configuration/sensor_faults.json")
    _require(type(faults.get("seed")) is int and faults["seed"] == trial["seed"]
             and _decimal(faults.get("drop_fraction")) == Decimal("0.10"), "Original sensor-fault seed/fraction differs")
    for relative in ("scripts/evaluate_stage1_flight.py", "scripts/sensor_fault_bridge.py"):
        path = Path(plan["frozen_root"]) / relative
        _require(_hash(path) == plan["source_hashes"][relative], "Original reader/fault source SHA differs")
        bindings[relative] = _binding(path)
    surface = reports["surface_flight"]
    result["original"].update(acceptance=deepcopy(surface["acceptance"]), occlusions=deepcopy(surface["occlusions"]))
    result["input_bindings"] = bindings
    _require(surface.get("target_class") == trial["target_class"], "Original surface class differs")
    acceptance = surface["acceptance"]
    _require(acceptance.get("missing_topics") == [] and type(acceptance.get("input_read_error_count")) is int
             and acceptance["input_read_error_count"] == 0 and acceptance.get("clock_timebase_available") is True
             and all(acceptance.get(key) is True for key in ("short_occlusion_recorded", "long_occlusion_recorded", "failed_events_retained"))
             and surface.get("flight_evidence", {}).get("armed_seen") is True
             and surface.get("flight_evidence", {}).get("offboard_seen") is True
             and type(surface.get("detector", {}).get("invalid_diagnostic_messages")) is int
             and surface["detector"]["invalid_diagnostic_messages"] == 0, "Original surface recording/clock/decoder evidence is incomplete")
    _require(len(surface["occlusions"]) == 2, "Original report must contain exactly one short and one long occlusion")
    short = _one(surface["occlusions"], lambda row: row.get("kind") == "short", "short occlusion")
    long = _one(surface["occlusions"], lambda row: row.get("kind") == "long", "long occlusion")
    for row in (short, long):
        start, end = _decimal(row["start_s"]), _decimal(row["end_s"])
        ack = row["shutter_execution"]
        _require(row.get("complete") is True and start < end
                 and all(row["checks"].get(key) is True for key in SHUTTER)
                 and ack.get("close_success") is True and ack.get("open_success") is True
                 and ack.get("close_ack_before_open_request") is True
                 and ack["close_request_id"] == row["close_request_id"] and ack["open_request_id"] == row["open_request_id"]
                 and start <= _decimal(ack["close_response_s"]) < end <= _decimal(ack["open_response_s"]), "Original shutter/ACK evidence is incomplete")
    _require(0 < _decimal(short["end_s"]) - _decimal(short["start_s"]) <= _decimal(surface["configuration"]["max_prediction_s"])
             < _decimal(long["end_s"]) - _decimal(long["start_s"]), "Original short/long classification differs")
    _require(all(long["checks"].get(key) is True for key in LONG_SAFETY), "Original long-loss/hover/reselection safety did not PASS")
    for row, keys in ((short, SHORT_ALGORITHM), (long, LONG_ALGORITHM)):
        for key in keys:
            value = row["checks"].get(key)
            _require(type(value) is bool, "Additional required behavior check is unknown: " + row["kind"] + ":" + key)
            if value is False:
                result["known_algorithm_failures"].append("surface:" + row["kind"] + ":" + key + "=FAIL")
    _require(long.get("result") == ("FAIL" if any(long["checks"][key] is False for key in LONG_ALGORITHM) else "PASS"),
             "Original long result contradicts its preserved checks")
    return trial, directory, terminal, surface, short, faults


def _extraction(path, contract, plan_path, plan, trial, directory, terminal, surface, short, result):
    manifest = _json(path)
    result["extraction_manifest"] = _binding(path)
    _require(manifest.get("schema_version") == 1 and manifest.get("status") == "PENDING_VISUAL_REVIEW"
             and manifest.get("visual_review") == "PENDING_VISUAL_REVIEW" and manifest.get("error") is None
             and manifest.get("all_selected_topics_scanned") is True and manifest.get("absent_topics") == []
             and type(manifest.get("clock_regression_count")) is int and manifest["clock_regression_count"] == 0
             and manifest.get("topics_selected") == list(TOPICS)
             and manifest.get("bag_reader", {}).get("source_bag_read_only") is True, "Extractor is incomplete, errored, or has clock/topic problems")
    _require(manifest.get("tool_sha256") == contract["extractor_sha256_by_condition"][trial["condition"]]
             and manifest.get("slot_id") == trial["id"] and manifest.get("trial_name") == trial["name"]
             and _same(manifest["source_root"], plan["frozen_root"]) and _same(manifest["plan"], plan_path)
             and _same(manifest["trial_directory"], directory) and manifest.get("plan_sha256") == plan["plan_sha256"]
             and manifest.get("original_terminal_status") == terminal["status"]
             and _digest(manifest["original_engineering_evidence"]) == _digest(terminal["engineering_evidence"])
             and _digest(manifest["original_acceptance"]) == _digest(surface["acceptance"])
             and _digest(manifest["original_short_window"]) == _digest(short), "Extractor source/original-result binding differs")
    expected = {item["path"]: {"bytes": Path(item["path"]).stat().st_size, "sha256": item["sha256"]}
                for key, item in result["input_bindings"].items()
                if key not in {"px4_source_clock_report.json", "native_startup_report.json", "scripts/sensor_fault_bridge.py"}}
    _require(manifest.get("input_small_files") == expected, "Extractor small-file provenance differs")
    _require(_digest(manifest["original_sensor_faults"]) == _digest(_json(directory / "configuration/sensor_faults.json")), "Extractor original faults differ")
    lo = _decimal(short["start_s"]) - _decimal(contract["padding_s"])
    hi = _decimal(short["end_s"]) + _decimal(contract["padding_s"])
    selection = manifest["selection"]
    _require(_decimal(selection["start_s_decimal"]) == lo and _decimal(selection["end_s_decimal"]) == hi
             and selection.get("inclusive") is True and selection.get("success_or_failure_selection") is False
             and type(selection.get("raw_rgb_hard_limit")) is int and selection["raw_rgb_hard_limit"] == 32,
             "Extractor selection changed or selected successful frames")
    rows, by_topic, previous_sequence, previous_clock = manifest["opportunities"], {topic: [] for topic in TOPICS[1:]}, -1, -1
    _require(isinstance(rows, list), "Invalid opportunity list")
    images, image_names = [], set()
    for row in rows:
        topic = row["topic"]
        _require(topic in by_topic, "Unexpected extraction opportunity topic")
        sequence = _int(row["record_sequence"], "record_sequence")
        clock = _int(row["latest_read_clock_ns"], "latest_read_clock_ns")
        ns = _int(row["acquisition_ns"], "acquisition_ns")
        _int(row["recording_timestamp_ns"], "recording_timestamp_ns")
        _require(sequence > previous_sequence and clock >= previous_clock, "Opportunity reader order/receive clock regressed")
        previous_sequence, previous_clock = sequence, clock
        _require(lo <= Decimal(ns) / 1_000_000_000 <= hi
                 and _decimal(row["acquisition_stamp_s_decimal"]) == Decimal(ns) / 1_000_000_000,
                 "Opportunity acquisition stamp/window differs")
        if topic == DIAGNOSTIC:
            payload = json.loads(row["original_diagnostic_json"], object_pairs_hook=_pairs)
            _require(type(payload.get("acquisition_ns")) is int and payload["acquisition_ns"] == ns
                     and row.get("header_ns") is None
                     and _decimal(row["original_stamp_s_decimal"]) == _decimal(payload["stamp_s"]), "Diagnostic exact acquisition source differs")
        else:
            sec, nano = _int(row["header_sec"], "header sec"), _int(row["header_nanosec"], "header nanosec")
            _require(nano < 1_000_000_000 and sec * 1_000_000_000 + nano == row.get("header_ns") == ns,
                     "Image integer source header differs")
        by_topic[topic].append(ns)
        if topic == RAW_RGB:
            filename = row["original_png"]
            _require(isinstance(filename, str) and Path(filename).name == filename and filename not in image_names,
                     "Every PNG opportunity must have its own simple local filename")
            image_names.add(filename)
            png = (Path(path).parent / filename).resolve(strict=True)
            _require(png.parent == Path(path).parent.resolve() and _hash(png) == _sha(row["png_sha256"]), "Original PNG path/hash differs")
            with png.open("rb") as handle:
                header = handle.read(24)
            _require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR"
                     and struct.unpack(">II", header[16:24]) == (row["width"], row["height"]), "PNG signature/dimensions differ")
            images.append({"file": filename, "sha256": row["png_sha256"], "acquisition_ns": ns})
    counts = {topic: len(by_topic[topic]) for topic in TOPICS[1:]}
    _require(manifest.get("window_opportunity_counts") == counts
             and all(type(value) is int for value in manifest["window_opportunity_counts"].values())
             and type(manifest.get("exported_raw_rgb_count")) is int and manifest["exported_raw_rgb_count"] == len(images)
             and 0 < len(images) <= 32, "Extraction count/export coverage differs")
    _require(set(manifest["scanned_message_counts"]) == set(TOPICS), "Full-scan topic counts differ")
    for topic in TOPICS:
        _require(_int(manifest["scanned_message_counts"][topic], "scanned count", 1) >= counts.get(topic, 0), "Full-scan count underreports window")
    _require(Counter(by_topic[RAW_RGB]) == Counter(by_topic[RAW_DEPTH]), "Raw RGB/depth opportunities are not exactly paired")
    sheet = manifest["contact_sheet"]
    _require(Path(sheet["file"]).name == sheet["file"], "Contact sheet must be a simple local filename")
    sheet_path = (Path(path).parent / sheet["file"]).resolve(strict=True)
    _require(sheet_path.parent == Path(path).parent.resolve() and _hash(sheet_path) == _sha(sheet["sha256"]),
             "Actual reviewed contact sheet path/hash differs")
    result["window_opportunity_counts"] = counts
    return manifest, by_topic, images


def _review(path, extraction_path, images, short, target_class, result):
    review = _json(path)
    result["visual_review"] = _binding(path)
    _require(review.get("kind") == "INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE"
             and review.get("review_type") in {"DIRECT_IMAGE_REVIEW_AI", "DIRECT_IMAGE_REVIEW_HUMAN"}
             and isinstance(review.get("reviewers"), list) and bool(review["reviewers"])
             and all(isinstance(actor, str) and bool(actor.strip()) for actor in review["reviewers"]), "Direct human/AI image reviewer provenance is required")
    _utc(review["created_utc"])
    _require(_bound(review["manifest"]) == Path(extraction_path).resolve(strict=True), "Review extraction manifest differs")
    _require(_utc(review["created_utc"]) >= _utc(_json(extraction_path)["finished_utc"]), "Review predates the completed extraction")
    _require(isinstance(review.get("images"), list) and len(review["images"]) == len(images), "Review must retain every original image opportunity")
    observations = []
    for actual, declared in zip(images, review["images"]):
        _require(all(declared.get(key) == value for key, value in actual.items())
                 and type(declared.get("acquisition_ns")) is int, "Review image/order/time/hash source differs")
        observation = declared["observation"]
        _require(observation in VISIBLE | {OBSCURED}, "Unspecified direct visual observation")
        _require(not (target_class == "car" and observation.startswith("ONE_PERSON"))
                 and not (target_class == "person" and observation.startswith("ONE_CAR")), "Review target class differs")
        observations.append((Decimal(actual["acquisition_ns"]) / 1_000_000_000, observation))
    ack = _decimal(short["shutter_execution"]["close_response_s"])
    start, end = _decimal(short["start_s"]), _decimal(short["end_s"])
    blocked = [str(stamp) for stamp, observation in observations if ack <= stamp < end and observation == OBSCURED]
    _require(blocked and any(stamp < start and observation in VISIBLE for stamp, observation in observations)
             and any(stamp >= end and observation in VISIBLE for stamp, observation in observations),
             "Need directly reviewed obscured frame after close ACK/before open request, plus visible scene before/after")
    result["reviewed_obscured_acquisition_s"] = blocked


def _drop_ledger(by_topic, faults, short, result):
    seed, fraction = faults["seed"], float(faults["drop_fraction"])
    retained, dropped, ledger = [], [], []
    for ns in by_topic[RAW_RGB]:
        window = ns // 200_000_000
        first = hashlib.sha256(f"{seed}:{window}".encode()).digest()[:8]
        drop = int.from_bytes(first, "big") / 2**64 < fraction
        (dropped if drop else retained).append(ns)
        ledger.append({"acquisition_ns": ns, "window": window, "first8_sha256_hex": first.hex(), "expected_drop": drop})
    for topic in (RESEARCH_RGB, RESEARCH_DEPTH):
        _require(Counter(by_topic[topic]) == Counter(retained), "Recorded research opportunities differ from exact planned keep/drop ledger: " + topic)
    diagnostics = Counter(by_topic[DIAGNOSTIC])
    delivered = Counter(by_topic[RESEARCH_RGB]) & Counter(by_topic[RESEARCH_DEPTH])
    _require(all(count <= delivered[ns] for ns, count in diagnostics.items()),
             "Diagnostic acquisition opportunities were not actually delivered in both research streams")
    start, end = _decimal(short["start_s"]), _decimal(short["end_s"])
    inside = [ns for ns in by_topic[RAW_RGB] if start <= Decimal(ns) / 1_000_000_000 <= end]
    _require(inside and all(ns in dropped for ns in inside), "Short-window raw inputs were not all planned dropped opportunities")
    _require(any(Decimal(ns) / 1_000_000_000 < start for ns in retained)
             and any(Decimal(ns) / 1_000_000_000 > end for ns in retained), "Need retained research/diagnostic input opportunities before and after")
    _require(any(Decimal(ns) / 1_000_000_000 < start for ns in diagnostics)
             and any(Decimal(ns) / 1_000_000_000 > end for ns in diagnostics),
             "Need at least one actually delivered diagnostic opportunity before and after")
    result["drop_ledger"] = ledger
    result["delivered_without_diagnostic_acquisition_ns"] = sorted((delivered - diagnostics).elements())
    result["short_window_opportunities"] = {topic: [ns for ns in stamps if start <= Decimal(ns) / 1_000_000_000 <= end]
                                              for topic, stamps in by_topic.items()}
    _require(all(not result["short_window_opportunities"][topic] for topic in (RESEARCH_RGB, RESEARCH_DEPTH, DIAGNOSTIC)),
             "Short-window downstream input/diagnostics are not absent")


def evaluate_slot(plan_path: Path, slot_id: str, extraction_manifest_path: Path,
                  visual_review_path: Path, contract: dict) -> dict:
    """Return stimulus corroboration separately from preserved behavior outcomes.

    Known algorithm False values remain known failures. Other required nulls,
    source/recording failures, long safety failures or binding problems are
    INCOMPLETE. NOT_APPLICABLE is only a fully checked existing detector outcome.
    """
    result = _report(contract)
    result["slot_id"] = slot_id
    try:
        original_plan, plan = _contract(contract)
        _require(_same(original_plan, plan_path), "Caller plan differs from explicit four-slot contract")
        _one(contract["dev_slots"], lambda row: row["slot_id"] == slot_id, "contract slot")
        trial, directory, terminal, surface, short, faults = _original(original_plan, plan, slot_id, result)
        observed = short["checks"].get("detector_interruption_observed")
        count = _int(short["diagnostic_frames_inside"], "original short diagnostic count")
        if type(observed) is bool and count > 0:
            if observed is False:
                result["known_algorithm_failures"].append("surface:short:detector_interruption_observed=FAIL")
            expected_short = "FAIL" if observed is False or any(short["checks"][key] is False for key in SHORT_ALGORITHM) else "PASS"
            expected_acceptance = "FAIL" if result["known_algorithm_failures"] else "PASS"
            _require(short.get("result") == expected_short and surface["acceptance"].get("result") == expected_acceptance,
                     "Original evaluable short/surface outcome contradicts its preserved checks")
            result.update(status=NOT_APPLICABLE, reason="Original short detector check already has recorded diagnostic evidence",
                          original_detector_interruption_observed=observed,
                          behavior_validity="KNOWN_ALGORITHM_FAILURES_RETAINED" if result["known_algorithm_failures"] else "ORIGINAL_OBSERVED_CHECKS_PRESERVED")
            return result
        _require(observed is None and count == 0
                 and _int(short["candidate_free_frames_inside"], "original short candidate-free count") == 0
                 and _int(short["valid_depth_frames_inside"], "original short valid-depth count") == 0,
                 "Only the original zero-input short detector null can receive corroboration")
        expected_short = "FAIL" if any(short["checks"][key] is False for key in SHORT_ALGORITHM) else "INCOMPLETE_EVIDENCE"
        _require(short.get("result") == expected_short, "Original short result contradicts its preserved checks")
        expected_acceptance = "FAIL" if result["known_algorithm_failures"] else "INCOMPLETE_EVIDENCE"
        _require(surface["acceptance"].get("result") == expected_acceptance
                 and terminal.get("status") in {"FAIL", "INCOMPLETE_EVIDENCE"}, "Original outcome/null reporting is contradictory")
        manifest, by_topic, images = _extraction(Path(extraction_manifest_path), contract, original_plan, plan,
                                                  trial, directory, terminal, surface, short, result)
        _review(Path(visual_review_path), Path(extraction_manifest_path), images, short, trial["target_class"], result)
        _drop_ledger(by_topic, faults, short, result)
        result.update(status=CORROBORATED, detector_check_observability="UNOBSERVABLE_NO_RECORDED_INPUT_OPPORTUNITY",
                      original_detector_interruption_observed=None,
                      behavior_validity="KNOWN_ALGORITHM_FAILURES_RETAINED" if result["known_algorithm_failures"] else "ORIGINAL_OBSERVED_CHECKS_PRESERVED")
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, ArithmeticError, struct.error) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    return result


def evaluate_development_manifest(manifest_path: Path, contract: dict) -> dict:
    """Check every fixed development cell; partial matrices can never be complete."""
    result = _report(contract)
    result["per_slot"] = []
    try:
        plan_path, _ = _contract(contract)
        manifest = _json(manifest_path)
        result["development_manifest"] = _binding(manifest_path)
        _require(manifest.get("schema_version") == 1 and manifest.get("contract_sha256") == _digest(contract)
                 and manifest.get("source_plan") == contract["source_plan"], "Development manifest contract/source differs")
        entries = manifest["slots"]
        _require(isinstance(entries, list), "Development slots must be a list")
        expected = {row["slot_id"] for row in contract["dev_slots"]}
        seen = set()
        for entry in entries:
            slot = entry["slot_id"]
            _require(slot in expected and slot not in seen, "Unknown/duplicate development slot; outcomes cannot be selected")
            seen.add(slot)
            extract, review = _bound(entry["extraction_manifest"]), _bound(entry["visual_review"])
            result["per_slot"].append(evaluate_slot(plan_path, slot, extract, review, contract))
        result["missing_slot_ids"] = sorted(expected - seen)
        _require(seen == expected, "All four predetermined person/car x dropout/combined slots are required")
        _require(all(row["status"] in {CORROBORATED, NOT_APPLICABLE} for row in result["per_slot"]), "One or more development cells lack sufficient evidence")
        result["status"] = CORROBORATED if any(row["status"] == CORROBORATED for row in result["per_slot"]) else NOT_APPLICABLE
        result["known_algorithm_failures"] = [{"slot_id": row["slot_id"], "failures": row["known_algorithm_failures"]}
                                               for row in result["per_slot"] if row["known_algorithm_failures"]]
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, ArithmeticError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    return result
