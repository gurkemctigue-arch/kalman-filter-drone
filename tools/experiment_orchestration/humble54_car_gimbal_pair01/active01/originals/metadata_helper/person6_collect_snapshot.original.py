"""Archive six person slots and review new slots 4--6 using small saved files only.

No ROS, WSL, native program, evaluator, project module, bag, JSONL or model is
opened or executed. Earlier first-three detailed checks are reused by receipt SHA.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN / "reliability_v4_humble54_core12_probe01_matrix"
PRIOR = ROOT / "tools/diagnostics/humble54_core12_first3_review01"
PRIOR_SHA = "edfd8ceb84b7d66c805d961c3986debfeca62ac08aa8c54da517add9e07a9019"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
IDS = (
    "person_stage1_velocity_seed004", "person_stage1_position_seed004",
    "person_stage2_crossing_seed004", "person_stage3_midpoint_seed004",
    "person_stage3_active_seed004", "person_stage3_multi_active_seed004",
)
CAP = 1024 ** 2
CACHE = {}
COPIED = []


def read(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.suffix.lower() in {".json", ".log", ".py", ".md"}, str(path)
    assert path.stat().st_size <= CAP, str(path)
    if path not in CACHE:
        CACHE[path] = path.read_bytes()
    return CACHE[path]


def load(path):
    return json.loads(read(path).decode("utf-8-sig"))


def binding(path):
    data = read(path)
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def digest(data, field):
    encoded = json.dumps({k: v for k, v in data.items() if k != field},
                         sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def copy(path, relative, expected=None):
    source = binding(path)
    if expected is not None:
        assert source["sha256"] == expected, str(path)
    destination = OUT / "originals" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(read(path))
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == source["sha256"]
    COPIED.append({"snapshot_path": destination.relative_to(OUT).as_posix(),
                   "source": source, "expected_source_sha256": expected,
                   "copied_byte_for_byte": True})
    return source


def navigation(nav, row, gates):
    whole, kf = nav["whole_interval"], nav["kf_navigation"]
    transient = whole["transients"]["base_link"]
    measured = {
        "base_link_distance_rmse_m": whole["metrics"]["base_link_distance_error_m"]["rmse"],
        "base_link_height_rmse_m": whole["metrics"]["base_link_height_error_m"]["rmse"],
        "valid_state_coverage": kf["valid_state_coverage"],
        "truth_coverage": whole["matched_truth_samples"] / whole["scheduled_samples"],
    }
    checks = {
        "base_link_distance": measured["base_link_distance_rmse_m"] <= gates["maximum_base_link_distance_rmse_m"],
        "base_link_height": measured["base_link_height_rmse_m"] <= gates["maximum_base_link_height_rmse_m"],
        "navigation_coverage": measured["valid_state_coverage"] >= gates["minimum_valid_state_coverage"],
        "truth_coverage": measured["truth_coverage"] >= gates["minimum_truth_coverage"],
        "final_distance_settled": transient["distance"]["settled_through_interval_end"] is True,
        "final_height_settled": transient["height"]["settled_through_interval_end"] is True,
    }
    assert measured == row["engineering_evidence"]["measured"]
    assert checks == row["engineering_evidence"]["checks"] and all(checks.values())
    interval = nav["interval"]
    assert whole["scheduled_samples"] == math.floor((interval["end_s"] - interval["start_s"]) / .1 + 1e-8) + 1
    assert kf["valid_state_coverage"] == kf["counts"]["valid_navigation_samples"] / kf["counts"]["scheduled_samples"]
    return {"measured": measured, "six_independently_compared_gates": checks,
            "original_status": nav["evaluation_status"], "interval": interval,
            "scheduled_samples": whole["scheduled_samples"],
            "matched_truth_samples": whole["matched_truth_samples"],
            "valid_navigation_samples": kf["counts"]["valid_navigation_samples"],
            "navigation_denominator": kf["counts"]["scheduled_samples"],
            "final_transients": {key: {name: transient[key][name] for name in
                ("band_m", "minimum_in_band_duration_s", "settled_through_interval_end",
                 "settling_right_censored", "settling_time_s", "duplicate_source_times")}
                for key in ("distance", "height")}}


def new_slot_review(trial, row, directory, plan, entries):
    result = {"small_artifact_bindings": [], "oversized_json_logs_not_read_or_hashed": []}
    for name, expected in row["artifact_hashes"].items():
        path = directory / name
        assert path.resolve().is_relative_to(directory.resolve()), name
        if path.suffix.lower() not in {".json", ".log"}:
            continue
        size = path.stat().st_size
        if size > CAP:
            result["oversized_json_logs_not_read_or_hashed"].append({"path": str(path), "bytes": size})
            continue
        actual = binding(path)
        assert actual["sha256"] == expected, str(path)
        result["small_artifact_bindings"].append({**actual, "expected_sha256": expected, "matches": True})
    result["original_evaluations"] = []
    for item in row["evaluations"]:
        path = directory / Path(item["report"]).name
        evidence = {"kind": item["kind"], "slot_result": item["result"],
                    "execution_code": item["execution"]["returncode"],
                    "execution_error": item["execution"]["error"]}
        assert evidence["execution_code"] == 0 and evidence["execution_error"] is None
        if path.stat().st_size > CAP:
            evidence.update(report_read_or_hashed=False, reason="Above 1 MiB; only small slot summary and log inspected")
            result["original_evaluations"].append(evidence)
            continue
        report = load(path)
        status = report.get("evaluation_status", report.get("result", report.get("acceptance", {}).get("result")))
        assert binding(path)["sha256"] == item["report_sha256"] and status == item["result"]
        evidence.update(report=binding(path), report_matches_slot=True, recorded_status=status)
        source = report.get("evaluation_source")
        if source:
            spec = next(spec for spec in trial["evaluations"] if spec["kind"] == item["kind"])
            assert source["script_sha256"] == plan["source_hashes"][spec["script"]]
            assert source["dependencies"] and all(value == plan["source_hashes"][name.removeprefix(plan["frozen_root"] + "/")]
                for name, value in source["dependencies"].items())
            evidence.update(saved_script_sha_matches_plan=True, saved_dependencies_match_plan=True)
        if item["kind"] == "source_clock":
            assert report["source_clock_pass"] is report["clock_domain_valid"] is report["vehicle_frame_continuity_valid"] is True
            assert not report["failures"] and not report["incomplete_evidence"]
            evidence.update(counts=report["counts"], failures=report["failures"], incomplete=report["incomplete_evidence"])
        if item["kind"] in {"native_startup", "gimbal", "selected_target_safety"}:
            assert report["checks"] and all(value is True for value in report["checks"].values())
            evidence["all_saved_checks_true"] = report["checks"]
            if item["kind"] == "native_startup":
                assert report["native_startup_pass"] is True and len(report["checks"]) == 9
                assert not report["failures"] and not report["incomplete_evidence"]
            if item["kind"] == "selected_target_safety":
                evidence["physical_identity_scope"] = report["physical_identity"]
                assert report["physical_identity"]["evaluated"] is False
        result["original_evaluations"].append(evidence)
    config = load(directory / "run_config.json")
    comparisons = {key: config.get(key) == trial[key] for key in (
        "name", "target_class", "stage", "seed", "speed_mps", "command_mode", "takeoff_mode", "gimbal_mode",
        "target_mode", "association_mode", "initial_select", "initial_min_candidates", "scenario_kind", "multi_target",
        "inference_image_size", "inference_threads", "desired_distance_m", "gazebo_render_driver", "split_clock_bridge",
        "px4_adapter_publish_rate_hz")}
    comparisons.update(duration=config["duration"] == trial["duration_s"], wall_timeout=config["wall_timeout"] == trial["wall_timeout_s"],
        model=config["model_path"] == plan["frozen_root"] + "/" + trial["model"],
        real_time_factor=config["real_time_factor"] == plan["protocol"]["real_time_factor"],
        flight_argv=row["commands"][0]["command"] == trial["flight_command"])
    stream, registered = config["supervisor_stream_timing"], trial["supervisor_stream_timing"]
    comparisons["stream_source_ages"] = all(stream[key] == registered[key] for key in
        ("stream_timestamp_mode", "odometry_source_max_age_s", "odometry_source_max_future_s", "command_source_max_age_s", "command_source_max_future_s"))
    comparisons["stream_wall_timeouts"] = stream["odometry_timeout_s"] == registered["odometry_timeout_wall_s"] and stream["command_timeout_s"] == registered["command_timeout_wall_s"]
    assert all(comparisons.values()) and row["runtime_configuration"]["errors"] == []
    snapshot = load(directory / "configuration/source_sha256.json")
    expected = {name: entry["sha256"] for name, entry in entries.items() if entry["kind"] == "file"
        and name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(name).suffix in {".py", ".sh", ".msg"}}
    for name in (trial["model"], "config/dds_runtime_humble22.json"):
        expected[name] = plan["source_hashes"][name]
    assert snapshot == expected
    subsystems = {key: value["errors"] for key, value in row["runtime_configuration"].items()
                  if isinstance(value, dict) and "errors" in value}
    assert all(value == [] for value in subsystems.values())
    exit_codes = load(directory / "process_exit_codes.json")
    assert exit_codes == row["cleanup"]["process_exit_codes"]
    observer = load(directory / "owned_stop_observer.json")
    assert observer["status"] == "EVIDENCE_COMPLETE" and observer["errors"] == []
    saved_statuses = {name: load(directory / name)["status"] for name in (
        "recording_closure.json", "recording_closure_observer.json", "bag_integrity.json",
        "configuration/dds_runtime_summary.json", "configuration/dds_runtime_after.json",
        "configuration/ros_gz_runtime_after.json", "configuration/ros_gz_clock_runtime_after.json")}
    assert all(value == ("CLOSED" if name == "recording_closure_observer.json" else "PASS")
               for name, value in saved_statuses.items())
    result.update(runtime_plan_comparisons=comparisons, saved_runtime_subsystem_errors=subsystems,
        saved_runtime_and_archive_statuses=saved_statuses, cleanup=row["cleanup"], owned_stop_observer={
            "status": observer["status"], "runtime_acceptance": observer["runtime_acceptance"], "errors": observer["errors"]},
        source_snapshot={"count": len(snapshot), "original_scanner_plus_model_dds_exact_match": True,
            "extra_count": len(set(snapshot) - set(plan["source_hashes"]))})
    return result


def collect():
    started = datetime.now(timezone.utc).isoformat()
    prior = load(PRIOR / "review_receipt.json")
    assert binding(PRIOR / "review_receipt.json")["sha256"] == PRIOR_SHA
    assert prior["checked_small_artifact_count"] == 127
    plan = load(MATRIX / "plan.json")
    assert plan["plan_sha256"] == digest(plan, "plan_sha256") == PLAN_DIGEST
    assert len(plan["trials"]) == 12 and tuple(t["id"] for t in plan["trials"][:6]) == IDS
    assert all(t["target_class"] == "person" and t["seed"] == 4 and t["duration_s"] == 75 for t in plan["trials"][:6])
    map_path = FROZEN / "freeze_validation/source_integrity/frozen_actual.json"
    assert binding(map_path)["sha256"] == prior["original_frozen_map"]["sha256"]
    entries = load(map_path)["entries"]
    gates = plan["protocol"]["navigation_acceptance"]
    receipt = {"schema_version": 1, "kind": "PERSON_FIRST6_SAVED_SMALL_EVIDENCE_CLOSURE_NOT_FORMAL_ACCEPTANCE",
        "started_utc": started, "collector": binding(Path(__file__)), "plan": binding(MATRIX / "plan.json"),
        "plan_digest": PLAN_DIGEST, "plan_digest_valid": True, "original_plan_denominator": 12,
        "scope": "Six person development slots at seed004; full small-artifact review is new only for slots 4--6",
        "prior_first3": {"receipt": binding(PRIOR / "review_receipt.json"), "reused_checked_small_artifact_count": 127,
                         "complete_127_artifact_set_rehashed": False},
        "registered_engineering_gates": gates, "slots": [],
        "limitations": [
            "No WSL, ROS, native process, evaluator or project module was started/imported.",
            "No bag, JSONL, telemetry, model, VHD, oversized ROS log or oversized physical-identity report was read or hashed.",
            "Full-task physical identity is copied only from small original slot summaries; neither oversized report nor per-task identity was independently reviewed here.",
            "The root's separate third-slot per-task documentation remains separate; these six-slot findings do not absorb it.",
            "Saved source manifests are not proof of each historical flight process's actual import location.",
            "Cleanup, source/native, gimbal, behavior and archive findings audit saved original reports, without raw bag re-evaluation.",
            "Six same-seed person development PASS slots do not establish car reliability, all 12-core completion, safety4, extension16, formal admission or algorithm superiority.",
            "The independent car-position probe is not included. No original record was modified."]}
    copy(MATRIX / "plan.json", Path("matrix/plan.json"), prior["plan"]["sha256"])
    copy(map_path, Path("freeze_validation/frozen_actual.json"), prior["original_frozen_map"]["sha256"])
    for name in ("review_receipt.json", "collect_small_evidence.py", "README.md"):
        copy(PRIOR / name, Path("prior_first3") / name, PRIOR_SHA if name == "review_receipt.json" else None)
    selected = ("run_config.json", "summary.json", "navigation_reference_evaluation.json", "px4_source_clock_report.json",
        "native_startup_report.json", "flight_evaluation.json", "recording_closure.json", "recording_closure_observer.json",
        "bag_integrity.json", "owned_stop_observer.json", "process_exit_codes.json", "configuration/source_sha256.json")
    for index, trial in enumerate(plan["trials"][:6]):
        identifier = trial["id"]
        slot_path = MATRIX / "slots" / (identifier + ".json")
        row = load(slot_path)
        assert row["record_sha256"] == digest(row, "record_sha256") and row["plan_sha256"] == PLAN_DIGEST
        assert row["id"] == identifier and row["name"] == trial["name"]
        assert row["status"] == row["engineering_result"] == "PASS" and row["flight_exit_code"] == 0
        assert row["infrastructure_stop"] is False and row["infrastructure"]["reasons"] == []
        assert row["cleanup"]["residual_processes"] == []
        assert all(item["returncode"] == 0 and item["error"] is None for item in row["commands"])
        directory = FROZEN / row["name"]
        evidence = {"id": identifier, "original_slot": binding(slot_path), "status": row["status"],
            "flight_exit_code": row["flight_exit_code"], "infrastructure_stop": False,
            "slot_digest_and_plan_binding_valid": True,
            "navigation": navigation(load(directory / "navigation_reference_evaluation.json"), row, gates)}
        if index < 3:
            old = prior["slots"][index]
            assert old["id"] == identifier and old["original_slot"]["sha256"] == binding(slot_path)["sha256"]
            assert old["measured"] == evidence["navigation"]["measured"]
            evidence["detailed_small_artifact_review"] = {"reused_from_pinned_first3_receipt": True,
                "checked_small_artifact_count": len(old["small_artifacts"]),
                "original_evaluation_statuses": old["original_evaluation_statuses"], "cleanup": old["cleanup"]}
        else:
            evidence["new_small_artifact_review"] = new_slot_review(trial, row, directory, plan, entries)
        physical = row["engineering_evidence"].get("physical_identity")
        if physical:
            diagnostic = row["engineering_evidence"]["diagnostic_frame_identity"]
            assert physical["correct"] + physical["wrong"] + physical["unknown"] == physical["scheduled_samples"]
            assert physical["known_coverage"] == (physical["correct"] + physical["wrong"]) / physical["scheduled_samples"]
            evidence["full_task_identity_from_original_small_slot_only"] = physical
            evidence["diagnostic_identity_different_denominator_not_substituted"] = diagnostic
            evidence["oversized_identity_report_and_per_task_independently_reviewed"] = False
            if index == 5:
                assert (physical["correct"], physical["wrong"], physical["unknown"], physical["scheduled_samples"]) == (648, 0, 106, 754)
                assert (diagnostic["correct"], diagnostic["wrong"], diagnostic["unknown"], diagnostic["frames"]) == (650, 0, 103, 753)
        copy(slot_path, Path("matrix/slots") / slot_path.name)
        copy(MATRIX / "slots" / (identifier + ".started.json"), Path("matrix/slots") / (identifier + ".started.json"))
        names = set(selected)
        names.update(name for name in row["artifact_hashes"] if name.startswith("configuration/") and name.endswith(".json"))
        names.update(Path(item["report"]).name for item in row["evaluations"] if item["kind"] in {"gimbal", "selected_target_safety"})
        for name in sorted(names):
            copy(directory / name, Path("trials") / identifier / name, row["artifact_hashes"][name])
        for path in sorted((MATRIX / "logs").glob(identifier + ".*.log")):
            copy(path, Path("matrix/logs") / path.name)
        receipt["slots"].append(evidence)
    assert len(receipt["slots"]) == 6
    receipt["new_slots_4_to_6_checked_small_artifact_count"] = sum(
        len(s["new_small_artifact_review"]["small_artifact_bindings"]) for s in receipt["slots"][3:])
    assert receipt["new_slots_4_to_6_checked_small_artifact_count"] == 130
    receipt["result"] = "SIX_PERSON_DEVELOPMENT_SLOTS_CONSISTENT_WITH_ORIGINAL_ENGINEERING_PASS"
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(OUT / "review_receipt.json", receipt)
    write_json(OUT / "manifest.json", {"schema_version": 1, "kind": "READ_ONLY_ORIGINAL_SMALL_FILE_SNAPSHOT",
        "created_utc": receipt["finished_utc"], "original_file_count": len(COPIED),
        "total_original_bytes": sum(item["source"]["bytes"] for item in COPIED), "files": COPIED})
    print(json.dumps({"result": receipt["result"], "new_small_artifact_checks": 130,
        "copied_files": len(COPIED), "copied_bytes": sum(item["source"]["bytes"] for item in COPIED),
        "review_receipt": binding(OUT / "review_receipt.json"), "manifest": binding(OUT / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    collect()
