"""Classify definite experiment infrastructure failures from small artifacts.

Call only after a trial's processes have exited. This never opens a bag
database or infers infrastructure failure from a target tracking verdict.
Missing/contradictory evidence is reported without inventing flight state.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

CORE_TOPICS = ("/clock", "/vehicle/odometry")
EVALUATOR_REPORTS = ("offline_evaluation.json", "flight_evaluation.json", "stage2_evaluation.json",
                     "auto_unique_evaluation.json", "gimbal_evaluation.json")
CORE_PROCESSES = {"gazebo", "agent", "px4", "ros", "bag", "sensor_faults"}
CRASH_CODES = {-4, -6, -7, -11, 132, 134, 135, 139}
MIN_VEHICLE_SPAN_S = 10.
NO_TAKEOFF_ALTITUDE_M = .5
LOG_SAMPLE_BYTES = 256 * 1024
RECORDING_ERROR = re.compile(
    r"database disk image is malformed|file is not a database|sqlite(?:3)?[. :].*(?:error|exception)"
    r"|disk i/o error|input/output error|no space left on device|read-only file system"
    r"|(?:zstd|zstandard|decompress(?:ion)?).*(?:error|failed|corrupt)|failed to decompress", re.IGNORECASE)
EVALUATOR_EXCEPTION = re.compile(r"Traceback \(most recent call last\):|Fatal Python error:|terminate called after throwing")
EVALUATOR_CRASH = re.compile(r"Segmentation fault|Bus error|Aborted \(core dumped\)|core dumped", re.IGNORECASE)
ROS_CHILD_EXIT = re.compile(r"\bprocess has died\b.*?\bexit code\s+(-?\d+)\b")
COMPLETED_VERDICTS = {"PASS", "FAIL", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "FAIL_OR_INCOMPLETE",
                      "RECORDED_WITH_CENSORED_FAILURES", "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS"}
NEGATIVE_VERDICTS = {"FAIL", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "FAIL_OR_INCOMPLETE"}
NAMED_EVALUATORS = {
    "px4_source_clock_report.json": ("source_clock", "evaluate_px4_source_clock.py"),
    "px4_source_clock_evaluation.json": ("source_clock", "evaluate_px4_source_clock.py"),
    "native_startup_report.json": ("native_startup", "evaluate_native_startup.py"),
    "native_startup_evaluation.json": ("native_startup", "evaluate_native_startup.py"),
    "navigation_reference_evaluation.json": ("navigation", "evaluate_navigation_reference.py"),
    "physical_identity.json": ("physical_identity", "evaluate_physical_identity.py"),
}


def completed_evaluator_verdict(path: Path, report: Any) -> str | None:
    """Recognize saved report completion, independently of engineering PASS.

    Named v4 status reports require their version, trial binding, provenance
    shape and consistent result fields. Recorded navigation/identity reports
    retain censored/unknown observations; their accuracy/identity gates are
    applied by the engineering evaluator, never by this execution classifier.
    """
    if not isinstance(report, dict):
        return None
    if "evaluation_status" not in report:
        acceptance = report.get("acceptance")
        verdict = acceptance.get("result") if isinstance(acceptance, dict) else None
        if verdict is None:
            verdict = report.get("result")
        return verdict if isinstance(verdict, str) and verdict in NEGATIVE_VERDICTS | {"PASS"} else None
    named = NAMED_EVALUATORS.get(path.name)
    if named is None or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        return None
    kind, script = named
    provenance = report.get("evaluation_source")
    bound = report.get("source_trial" if kind == "physical_identity" else "trial")
    if (not isinstance(provenance, dict) or not isinstance(provenance.get("script"), str)
            or Path(provenance["script"]).name != script
            or not re.fullmatch(r"[a-f0-9]{64}", str(provenance.get("script_sha256", "")))
            or not isinstance(provenance.get("dependencies"), dict)
            or not isinstance(bound, str) or Path(bound).resolve() != path.parent.resolve()):
        return None
    verdict = report["evaluation_status"]
    if not isinstance(verdict, str):
        return None
    if kind in {"source_clock", "native_startup"}:
        allowed = {"PASS", "FAIL", "INCOMPLETE" if kind == "source_clock" else "INCOMPLETE_EVIDENCE"}
        if (verdict not in allowed or report.get(kind + "_pass") is not (verdict == "PASS")
                or not isinstance(report.get("incomplete_evidence"), dict)):
            return None
        failures = report.get("failures", {})
        if not isinstance(failures, dict):
            return None
        if verdict == "PASS" and (failures or report["incomplete_evidence"]):
            return None
        if verdict == "FAIL" and not failures:
            return None
        if verdict in NEGATIVE_VERDICTS - {"FAIL"} and not report["incomplete_evidence"]:
            return None
        if kind == "source_clock" and verdict == "PASS" and (
                report.get("clock_domain_valid") is not True
                or report.get("vehicle_frame_continuity_valid") is not True
                or not isinstance(report.get("counts"), dict)):
            return None
        if kind == "native_startup":
            checks = report.get("checks")
            if (not isinstance(checks, dict) or not checks
                    or any(value is not None and type(value) is not bool for value in checks.values())
                    or verdict == "PASS" and any(value is not True for value in checks.values())
                    or verdict == "FAIL" and not any(value is False for value in checks.values())):
                return None
        return verdict
    if verdict == "INCOMPLETE_EVIDENCE":
        return verdict if (isinstance(report.get("reason"), str) and report["reason"]
                           or isinstance(report.get("incomplete_reasons"), list) and report["incomplete_reasons"]) else None
    if kind == "navigation":
        if (verdict == "RECORDED_WITH_CENSORED_FAILURES" and report.get("incomplete_reasons") == []
                and all(isinstance(report.get(key), dict) for key in ("interval", "whole_interval", "kf_navigation"))):
            return verdict
    elif kind == "physical_identity":
        if (verdict == "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS"
                and all(isinstance(report.get(key), dict) for key in
                        ("tasks", "conservative_selected_identity", "conservative_task_time_identity"))):
            return verdict
    return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _phase(value: Any) -> str | None:
    return value.split(":", 1)[0].strip().upper() if isinstance(value, str) else None


def _json_safe(value: Any) -> Any:
    # Python's JSON decoder tolerates NaN/Infinity in a damaged input. Keep
    # the anomaly visible without breaking the caller's strict JSON ledger.
    if isinstance(value, float) and not math.isfinite(value):
        return f"NONFINITE:{value}"
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _recording_pass_problem(name: str, report: dict) -> str | None:
    """Check the producer's PASS contract; never infer engineering success."""
    if report.get("error"):
        return "PASS report also records an error"
    if name == "recording_closure.json":
        if report.get("scope") != "WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE":
            return "Unknown recording-closure scope"
        pause = report.get("pause_request")
        observations = report.get("observations")
        final = observations[-1] if isinstance(observations, list) and observations else None
        if (not isinstance(pause, dict) or pause.get("command_pause") is not True
                or type(pause.get("returncode")) is not int or pause["returncode"] != 0
                or not isinstance(pause.get("response"), str) or "true" not in pause["response"]):
            return "PASS closure lacks a successful pause acknowledgement"
        if (not isinstance(final, dict) or final.get("ready") is not True
                or final.get("failures") != [] or final.get("errors") != []
                or final.get("missing_truth_frames_at_final_clock", []) != []):
            return "PASS closure lacks a ready, failure-free final observation"
        if (report.get("observer_cleanup_completed") is not True
                or _finite(report.get("closed_streams_elapsed_wall_s")) is None
                or report["closed_streams_elapsed_wall_s"] < 0):
            return "PASS closure lacks completed stream/observer closure"
    else:
        if report.get("policy") != "ext4_sqlite_close_standard_zstd_verified_native_read":
            return "Unknown recording-integrity policy"
        raw, native = report.get("raw_validation"), report.get("native_reader_validation")
        if (type(report.get("recorder_exit_code")) is not int or report["recorder_exit_code"] != 0
                or not isinstance(raw, dict) or raw.get("status") != "PASS"
                or not isinstance(native, dict) or native.get("status") != "PASS"
                or native.get("full_stream_read") is not True
                or type(raw.get("message_count")) is not int or raw["message_count"] <= 0
                or type(native.get("message_count")) is not int or native["message_count"] != raw["message_count"]
                or not isinstance(raw.get("topic_counts"), dict) or not raw["topic_counts"]
                or native.get("topic_counts") != raw["topic_counts"]):
            return "PASS archive lacks consistent successful raw/native validation"
        compressed = report.get("compressed_files")
        if (not isinstance(compressed, list) or not compressed
                or any(not isinstance(item, dict) or item.get("zstd_test") != "PASS" for item in compressed)
                or not re.fullmatch(r"[a-f0-9]{64}", str(report.get("published_metadata_sha256", "")))):
            return "PASS archive lacks compressed-file or published-metadata evidence"
    return None


def classify_recording_artifacts(trial_dir: Path) -> dict:
    """Read only closure/archive JSON; absent legacy artifacts stay unknown.

    This branch is also usable for a separately named, JSON-only diagnosis of
    an immutable failed trial. A valid PASS only avoids this branch's stop.
    """
    directory = Path(trial_dir).resolve()
    reasons, files, reports = [], {}, {}
    for name, label in (("recording_closure.json", "RECORDING_CLOSURE"),
                        ("bag_integrity.json", "RECORDING_INTEGRITY")):
        path = directory / name
        files[name] = {"exists": path.exists()}
        if not path.exists():
            reports[name] = {"status": "MISSING_LEGACY_UNKNOWN"}
            continue
        try:
            raw = path.read_bytes()
            files[name].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            report = json.loads(raw.decode("utf-8-sig"))
            if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
                    or report["schema_version"] != 1 or not isinstance(report.get("status"), str)
                    or not report["status"]):
                raise ValueError("Expected a schema-v1 recording report with explicit status")
            reports[name] = {key: report.get(key) for key in ("schema_version", "status", "error", "scope", "policy")}
            if report["status"] != "PASS":
                reasons.append({"code": label + "_FAILED", "source": name,
                    "message": "Recording report explicitly did not pass: " + report["status"]})
            else:
                problem = _recording_pass_problem(name, report)
                if problem:
                    raise ValueError(problem)
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            reports.setdefault(name, {})["validation_error"] = str(error)
            reasons.append({"code": "INVALID_" + label + "_REPORT", "source": name,
                            "message": "Present recording report is unreadable or inconsistent: " + str(error)})
    return _json_safe({"stop": bool(reasons), "reasons": reasons, "files": files, "reports": reports,
        "scope": "Closure/archive JSON only; no bag or telemetry reads, and no engineering PASS conclusion"})


def classify_infrastructure_failure(trial_dir: Path, *, evaluator_attempts: list[dict] | None = None) -> dict:
    """Return ``{stop: bool, reasons: list[dict], evidence: dict}``.

    Each reason has ``code``, ``message`` and ``source``. The caller keeps
    the failed trial and remaining PENDING slots; this function is read-only.
    A low altitude alone, a nonzero monitor exit, missing FOLLOW, ordinary
    ambiguity/target loss, or a completed evaluator FAIL are never sufficient.
    Optional attempt records bind external matrix logs to their report paths;
    root-level evaluator-stem .log files are discovered automatically.
    """
    directory = Path(trial_dir).resolve()
    reasons: list[dict] = []
    evidence: dict = {"trial_dir": str(directory), "files": {}, "parse_errors": [],
                      "policy": {"minimum_vehicle_span_for_no_takeoff_s": MIN_VEHICLE_SPAN_S,
                                 "no_takeoff_altitude_below_m": NO_TAKEOFF_ALTITUDE_M,
                                 "called_after_process_exit": True,
                                 "tracking_failures_are_not_infrastructure": True}}

    def reason(code, message, source):
        if not any(item["code"] == code and item["source"] == source for item in reasons):
            reasons.append({"code": code, "message": message, "source": source})

    def read_json(name):
        path = directory / name
        evidence["files"][name] = {"exists": path.is_file()}
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
            evidence["files"][name].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            value = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except (OSError, UnicodeError, ValueError) as error:
            evidence["parse_errors"].append({"source": name, "error": str(error)})
            return None

    recording = classify_recording_artifacts(directory)
    evidence["recording_artifacts"] = recording
    evidence["files"].update(recording["files"])
    for item in recording["reasons"]:
        reason(item["code"], item["message"], item["source"])

    monitor = read_json("summary.json") or {}
    evidence["monitor"] = {key: monitor.get(key) for key in (
        "termination_reason", "monitor_exit_code", "basic_flight_passed", "armed_seen", "offboard_seen",
        "start_sim_s", "end_sim_s", "follow_start_s", "max_vehicle_altitude_m")}
    aborted_sources = []
    if (monitor.get("termination_reason") == "flight_aborted"
            or any(_phase(monitor.get(key)) == "ABORTED" for key in ("phase", "final_phase", "flight_phase"))):
        aborted_sources.append("summary.json")

    exits = read_json("process_exit_codes.json") or {}
    evidence["process_exit_codes"] = exits
    for process in sorted(CORE_PROCESSES):
        code = exits.get(process)
        if type(code) is int and code in CRASH_CODES:
            reason("CORE_PROCESS_CRASH", f"Core process {process} recorded crash exit code {code}",
                   f"process_exit_codes.json:{process}")

    # ros2 launch can exit zero while one of its children raises on shutdown.
    # Keep the child's explicit failure even when the parent looked healthy.
    ros_log = directory / "ros.log"
    evidence["ros_child_exit_audit"] = {"log_exists":ros_log.is_file(), "unexpected_exits":[]}
    if ros_log.is_file():
        try:
            size = ros_log.stat().st_size
            with ros_log.open("rb") as handle:
                if size <= LOG_SAMPLE_BYTES:
                    raw = handle.read(LOG_SAMPLE_BYTES)
                else:
                    head = handle.read(LOG_SAMPLE_BYTES // 4)
                    handle.seek(-3 * LOG_SAMPLE_BYTES // 4, 2)
                    raw = head + b"\n[bounded log sample gap]\n" + handle.read(3 * LOG_SAMPLE_BYTES // 4)
            audit = evidence["ros_child_exit_audit"]
            audit.update(log_bytes=size, sampled_bytes=len(raw), sample_sha256=hashlib.sha256(raw).hexdigest())
            for line in raw.decode("utf-8-sig", errors="replace").splitlines():
                match = ROS_CHILD_EXIT.search(line)
                if match is not None and int(match[1]) not in {0, -2, -15, 130, 143}:
                    if len(audit["unexpected_exits"]) < 20:
                        audit["unexpected_exits"].append({"exit_code":int(match[1]), "text":line[:1000]})
            if audit["unexpected_exits"]:
                reason("ROS_CHILD_PROCESS_FAILURE", "ROS launch reports an unexpected child exit; parent exit zero does not prove clean shutdown", "ros.log")
        except OSError as error:
            evidence["parse_errors"].append({"source":"ros.log", "error":str(error)})

    telemetry_path = directory / "telemetry.jsonl"
    evidence["files"]["telemetry.jsonl"] = {"exists": telemetry_path.is_file()}
    telemetry = {"lines": 0, "decoded_records": 0, "malformed_lines": 0, "vehicle_samples": 0,
                 "first_vehicle_time_s": None, "last_vehicle_time_s": None, "vehicle_span_s": None,
                 "max_vehicle_altitude_m": None, "phases": [], "abort_events": []}
    vehicle_times, vehicle_altitudes = [], []
    if telemetry_path.is_file():
        hasher = hashlib.sha256()
        try:
            with telemetry_path.open("rb") as handle:
                for line_number, raw in enumerate(handle, 1):
                    hasher.update(raw)
                    telemetry["lines"] += 1
                    try:
                        row = json.loads(raw.decode("utf-8-sig"))
                        if not isinstance(row, dict):
                            raise ValueError("Expected telemetry object")
                    except (UnicodeError, ValueError):
                        telemetry["malformed_lines"] += 1
                        continue
                    telemetry["decoded_records"] += 1
                    phase = _phase(row.get("phase"))
                    if phase and phase not in telemetry["phases"]:
                        telemetry["phases"].append(phase)
                    if row.get("kind") in {"phase", "telemetry", "supervisor", "flight_phase"} and phase == "ABORTED":
                        if len(telemetry["abort_events"]) < 10:
                            telemetry["abort_events"].append({"line": line_number, "time_s": row.get("time_s"),
                                                               "detail": row.get("detail", row.get("reason"))})
                        aborted_sources.append(f"telemetry.jsonl:{line_number}")
                    if row.get("kind") not in {"telemetry", "vehicle", "vehicle_odometry"}:
                        continue
                    time = _finite(row.get("time_s"))
                    position = row.get("position")
                    if (time is not None and isinstance(position, list) and len(position) == 3
                            and all(_finite(value) is not None for value in position)):
                        vehicle_times.append(time)
                        vehicle_altitudes.append(float(position[2]))
            evidence["files"]["telemetry.jsonl"]["sha256"] = hasher.hexdigest()
        except OSError as error:
            evidence["parse_errors"].append({"source": "telemetry.jsonl", "error": str(error)})
    if vehicle_times:
        telemetry.update(vehicle_samples=len(vehicle_times), first_vehicle_time_s=min(vehicle_times),
                         last_vehicle_time_s=max(vehicle_times), vehicle_span_s=max(vehicle_times)-min(vehicle_times),
                         max_vehicle_altitude_m=max(vehicle_altitudes))
    evidence["telemetry"] = telemetry
    if aborted_sources:
        reason("SUPERVISOR_ABORTED", "Flight supervisor explicitly entered ABORTED; subsequent trials must wait for diagnosis",
               aborted_sources[0])

    bag = directory / "rosbag"
    metadata_path = bag / "metadata.yaml"
    bag_evidence: dict = {"metadata_exists": metadata_path.is_file(), "topic_message_counts": None,
                          "declared_files": [], "missing_files": [], "metadata_parse_available": True}
    evidence["bag"] = bag_evidence
    if not metadata_path.is_file():
        reason("MISSING_BAG_METADATA", "Required recording has no rosbag/metadata.yaml", "rosbag/metadata.yaml")
    else:
        try:
            import yaml
        except ImportError:
            bag_evidence["metadata_parse_available"] = False
            evidence["parse_errors"].append({"source": "rosbag/metadata.yaml", "error": "Optional PyYAML unavailable; topic absence is unknown"})
        else:
            try:
                raw = metadata_path.read_bytes()
                bag_evidence["sha256"] = hashlib.sha256(raw).hexdigest()
                document = yaml.safe_load(raw.decode("utf-8-sig"))
                information = document["rosbag2_bagfile_information"]
                topics = information["topics_with_message_count"]
                if not isinstance(topics, list):
                    raise ValueError("Expected complete bag topic list")
                counts = {}
                for item in topics:
                    name, count = item["topic_metadata"]["name"], item["message_count"]
                    if not isinstance(name, str) or type(count) is not int or count < 0:
                        raise ValueError("Invalid bag topic name/count")
                    counts[name] = count
                bag_evidence["topic_message_counts"] = counts
                if information.get("message_count") == 0:
                    reason("EMPTY_BAG", "Recorder reports zero messages", "rosbag/metadata.yaml:message_count")
                for topic, code in (("/clock", "MISSING_CLOCK"), ("/vehicle/odometry", "MISSING_VEHICLE_ODOMETRY")):
                    if counts.get(topic, 0) == 0:
                        reason(code, f"Full recording contains no messages on required topic {topic}",
                               f"rosbag/metadata.yaml:{topic}")
                declared_files = information.get("relative_file_paths", [])
                if not isinstance(declared_files, list) or any(not isinstance(name, str) for name in declared_files):
                    raise ValueError("Invalid bag relative file list")
                bag_evidence["declared_files"] = declared_files
                for name in declared_files:
                    candidate = (bag / name).resolve()
                    if not candidate.is_relative_to(bag.resolve()):
                        raise ValueError("Bag data file path escapes its recording directory")
                    if not candidate.is_file():
                        bag_evidence["missing_files"].append(name)
                if bag_evidence["missing_files"]:
                    reason("MISSING_BAG_FILE", "Recorder-declared bag data file is missing", "rosbag/metadata.yaml:relative_file_paths")
            except (OSError, UnicodeError, KeyError, TypeError, ValueError, yaml.YAMLError) as error:
                evidence["parse_errors"].append({"source": "rosbag/metadata.yaml", "error": str(error)})
                reason("INVALID_BAG_METADATA", "Required bag metadata is unreadable or malformed", "rosbag/metadata.yaml")

    evaluator_evidence = []
    reports = {}
    for name in EVALUATOR_REPORTS:
        report = read_json(name)
        reports[(directory / name).resolve()] = report
        if report is None:
            continue
        metadata = report.get("inputs", report.get("metadata"))
        if not isinstance(metadata, dict):
            continue
        entry = {"source": name, "schema_version": report.get("schema_version"),
                 "clock_recorded": metadata.get("clock_recorded"), "clock_samples_read": metadata.get("clock_samples_read"),
                 "unavailable_types": metadata.get("unavailable_types"), "read_errors": metadata.get("read_errors"),
                 "core_topics_present": None}
        evaluator_evidence.append(entry)
        if metadata.get("clock_recorded") is False or metadata.get("clock_samples_read") == 0:
            reason("MISSING_CLOCK", "Evaluator explicitly records no available/readable simulation clock", f"{name}:inputs")
        types = metadata.get("topic_types")
        if isinstance(types, dict):
            entry["core_topics_present"] = {topic: topic in types for topic in CORE_TOPICS}
            for topic, code in (("/clock", "MISSING_CLOCK"), ("/vehicle/odometry", "MISSING_VEHICLE_ODOMETRY")):
                if topic not in types:
                    reason(code, f"Evaluator input type inventory lacks required topic {topic}", f"{name}:topic_types")
        unavailable, errors = metadata.get("unavailable_types"), metadata.get("read_errors")
        if isinstance(unavailable, dict) and any(topic in unavailable for topic in CORE_TOPICS):
            reason("CORE_TOPIC_UNREADABLE", "Required clock/vehicle message type is unavailable to the evaluator", f"{name}:unavailable_types")
        if isinstance(errors, dict) and any(any(key.startswith(topic + ":") for topic in CORE_TOPICS) for key in errors):
            reason("CORE_TOPIC_UNREADABLE", "Evaluator failed to decode a required clock/vehicle stream", f"{name}:read_errors")
    evidence["evaluators"] = evaluator_evidence

    attempts = [{"report": str(directory / name), "log": str(directory / Path(name).with_suffix(".log"))}
                for name in EVALUATOR_REPORTS if (directory / Path(name).with_suffix(".log")).is_file()]
    attempts.extend(evaluator_attempts or [])
    execution_evidence = []
    for attempt in attempts:
        report_path = Path(attempt["report"])
        log_path = Path(attempt["log"]) if attempt.get("log") else None
        if not report_path.is_absolute():
            report_path = directory / report_path
        if log_path is not None and not log_path.is_absolute():
            log_path = directory / log_path
        report_path = report_path.resolve()
        if report_path not in reports:
            reports[report_path] = read_json(str(report_path))
        report = reports[report_path]
        verdict = completed_evaluator_verdict(report_path, report)
        complete = verdict in COMPLETED_VERDICTS
        code = attempt.get("returncode")
        entry = {"report": str(report_path), "report_exists": report_path.is_file(),
                 "completed_report_verdict": verdict, "returncode": code, "log": str(log_path) if log_path else None,
                 "signals": [], "verdict_scope": "Report completion only; recorded statuses do not assert engineering PASS"}
        execution_evidence.append(entry)
        source = str(log_path) if log_path else str(report_path)
        if not complete:
            reason("EVALUATOR_REPORT_MISSING_OR_INVALID", "An evaluator attempt has no completed parseable report", str(report_path))
        if type(code) is int and code in CRASH_CODES:
            reason("EVALUATOR_PROCESS_CRASH", f"Evaluator recorded crash exit code {code}", source)
        elif type(code) is int and code != 0 and not (complete and code == 2 and verdict in NEGATIVE_VERDICTS):
            reason("EVALUATOR_EXECUTION_FAILED", "Evaluator exited nonzero without a completed failure report", source)
        if attempt.get("error") and not complete:
            reason("EVALUATOR_EXECUTION_FAILED", "Evaluator invocation failed without a completed report", source)
        if log_path is None or not log_path.is_file():
            continue
        try:
            size = log_path.stat().st_size
            with log_path.open("rb") as handle:
                if size <= LOG_SAMPLE_BYTES:
                    raw = handle.read(LOG_SAMPLE_BYTES)
                    scheme = "complete"
                else:
                    head = handle.read(LOG_SAMPLE_BYTES // 4)
                    handle.seek(-3 * LOG_SAMPLE_BYTES // 4, 2)
                    raw = head + b"\n[bounded log sample gap]\n" + handle.read(3 * LOG_SAMPLE_BYTES // 4)
                    scheme = "first64KiB_last192KiB"
            entry.update(log_bytes=size, sampled_bytes=len(raw), sample_scheme=scheme,
                         sample_sha256=hashlib.sha256(raw).hexdigest())
            kinds = set()
            for line_number, line in enumerate(raw.decode("utf-8-sig", errors="replace").splitlines(), 1):
                marker = ("recording_io_error" if RECORDING_ERROR.search(line) else
                          "process_crash" if EVALUATOR_CRASH.search(line) else
                          "unhandled_exception" if EVALUATOR_EXCEPTION.search(line) else None)
                if marker:
                    kinds.add(marker)
                    if len(entry["signals"]) < 20:
                        entry["signals"].append({"kind": marker, "sample_line": line_number, "text": line[:1000]})
            entry["detected_signal_kinds"] = sorted(kinds)
            if "recording_io_error" in kinds:
                reason("EVALUATOR_RECORDING_IO_FAILURE", "Evaluator log explicitly reports database, archive or recording I/O failure", source)
            if "process_crash" in kinds:
                reason("EVALUATOR_PROCESS_CRASH", "Evaluator log explicitly records a process crash", source)
            if "unhandled_exception" in kinds:
                reason("EVALUATOR_EXCEPTION_AFTER_REPORT" if complete else "EVALUATOR_EXCEPTION_WITHOUT_REPORT",
                       "Evaluator log contains an unhandled exception; a saved verdict does not certify clean execution", source)
        except OSError as error:
            entry["log_read_error"] = str(error)
            evidence["parse_errors"].append({"source": str(log_path), "error": str(error)})
    evidence["evaluator_execution"] = execution_evidence

    altitude_candidates = [_finite(monitor.get("max_vehicle_altitude_m")), _finite(telemetry["max_vehicle_altitude_m"])]
    observed = [value for value in altitude_candidates if value is not None]
    max_altitude = max(observed) if observed else None
    # A genuinely observed takeoff overrides a contradictory low summary.
    # Summary simulation duration alone is not a vehicle-observation span.
    span = _finite(telemetry["vehicle_span_s"])
    sufficient_vehicle_window = telemetry["vehicle_samples"] >= 2 and span is not None and span >= MIN_VEHICLE_SPAN_S
    if max_altitude is not None and max_altitude < NO_TAKEOFF_ALTITUDE_M and (sufficient_vehicle_window or aborted_sources):
        reason("NO_TAKEOFF", f"Observed maximum altitude {max_altitude:.3f} m remained below {NO_TAKEOFF_ALTITUDE_M:.2f} m with a recorded vehicle window or explicit abort",
               "telemetry.jsonl" if sufficient_vehicle_window else "summary.json/explicit_abort")
    evidence["no_takeoff_assessment"] = {"maximum_observed_altitude_m": max_altitude,
                                         "sufficient_vehicle_window": sufficient_vehicle_window,
                                         "explicit_abort": bool(aborted_sources)}
    return {"stop": bool(reasons), "reasons": reasons, "evidence": _json_safe(evidence)}
