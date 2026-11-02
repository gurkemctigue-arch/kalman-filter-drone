"""First-three archived small-JSON/log review; no original evaluator is run."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN / "reliability_v4_humble54_core12_probe01_matrix"
IDS = ("person_stage1_velocity_seed004", "person_stage1_position_seed004", "person_stage2_crossing_seed004")
CAP = 1024**2


def load(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= CAP, str(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def binding(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= CAP, str(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def digest(data, field):
    return hashlib.sha256(json.dumps({k: v for k, v in data.items() if k != field},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def scanned(name):
    return name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(name).suffix in {".py", ".sh", ".msg"}


def collect():
    receipt = {"schema_version": 1, "kind": "FIRST3_ARCHIVED_SMALL_EVIDENCE_INDEPENDENT_REVIEW",
        "started_utc": datetime.now(timezone.utc).isoformat(), "collector": binding(Path(__file__)),
        "scope": "Only the named three original slots and JSON/log artifacts at most 1 MiB; no ROS/native/evaluator/target imports",
        "limitations": ["No bag, telemetry, JSONL sidecar, model binary, VHD or oversized ROS log was read or hashed.",
            "The 1663576-byte physical_identity.json was not read or hashed by this review; its slot summary and small original log were inspected.",
            "Recorded source manifests do not prove every historical flight-process import location.",
            "Native/source-clock/closure/archive conclusions here audit saved original reports; raw frames and bags were not re-evaluated.",
            "No owner terminal or completion of any later slot, safety4, extension or formal matrix is inferred."],
        "slots": [], "checked_small_artifact_count": 0}
    plan_path = MATRIX / "plan.json"
    plan = load(plan_path)
    receipt["plan"] = binding(plan_path)
    assert plan["plan_sha256"] == digest(plan, "plan_sha256")
    receipt["plan_digest_valid"] = True
    receipt["planned_slot_count"] = len(plan["trials"])
    gates = plan["protocol"]["navigation_acceptance"]
    receipt["registered_engineering_gates"] = gates
    frozen_map = FROZEN / "freeze_validation/source_integrity/frozen_actual.json"
    entries = load(frozen_map)["entries"]
    receipt["original_frozen_map"] = binding(frozen_map)
    for identifier in IDS:
        path = MATRIX / "slots" / (identifier + ".json")
        row = load(path)
        trial = next(item for item in plan["trials"] if item["id"] == identifier)
        directory = FROZEN / row["name"]
        result = {"id": identifier, "original_slot": binding(path), "original_trial_directory": str(directory),
                  "status": row["status"], "engineering_result": row["engineering_result"], "small_artifacts": [], "oversized_json_logs_skipped": []}
        assert row["record_sha256"] == digest(row, "record_sha256") and row["plan_sha256"] == plan["plan_sha256"]
        result["slot_digest_and_plan_binding_valid"] = True
        for name, expected in row["artifact_hashes"].items():
            artifact = directory / name
            if artifact.suffix.lower() not in {".json", ".log"}:
                continue
            if artifact.stat().st_size > CAP:
                result["oversized_json_logs_skipped"].append({"path": str(artifact), "bytes": artifact.stat().st_size, "read_or_hashed": False})
                continue
            actual = binding(artifact)
            actual.update(expected_sha256=expected, matches=actual["sha256"] == expected)
            result["small_artifacts"].append(actual)
            assert actual["matches"], str(artifact)
        receipt["checked_small_artifact_count"] += len(result["small_artifacts"])
        nav = load(directory / "navigation_reference_evaluation.json")
        whole, kf = nav["whole_interval"], nav["kf_navigation"]
        transients = whole["transients"]["base_link"]
        measured = {"base_link_distance_rmse_m": whole["metrics"]["base_link_distance_error_m"]["rmse"],
                    "base_link_height_rmse_m": whole["metrics"]["base_link_height_error_m"]["rmse"],
                    "valid_state_coverage": kf["valid_state_coverage"], "truth_coverage": whole["matched_truth_samples"] / whole["scheduled_samples"]}
        checks = {"base_link_distance": measured["base_link_distance_rmse_m"] <= gates["maximum_base_link_distance_rmse_m"],
                  "base_link_height": measured["base_link_height_rmse_m"] <= gates["maximum_base_link_height_rmse_m"],
                  "navigation_coverage": measured["valid_state_coverage"] >= gates["minimum_valid_state_coverage"],
                  "truth_coverage": measured["truth_coverage"] >= gates["minimum_truth_coverage"],
                  "final_distance_settled": transients["distance"]["settled_through_interval_end"] is True,
                  "final_height_settled": transients["height"]["settled_through_interval_end"] is True}
        assert measured == row["engineering_evidence"]["measured"] and checks == row["engineering_evidence"]["checks"] and all(checks.values())
        interval = nav["interval"]
        assert whole["scheduled_samples"] == int(math.floor((interval["end_s"] - interval["start_s"]) / .1 + 1e-8)) + 1 == 752
        assert kf["valid_state_coverage"] == kf["counts"]["valid_navigation_samples"] / kf["counts"]["scheduled_samples"]
        result.update(measured=measured, independently_compared_engineering_checks=checks,
                      navigation_grid={"interval": interval, "scheduled_samples": whole["scheduled_samples"], "matched_truth_samples": whole["matched_truth_samples"],
                                       "valid_navigation_samples": kf["counts"]["valid_navigation_samples"], "navigation_denominator": kf["counts"]["scheduled_samples"]},
                      final_transients={key: {name: transients[key][name] for name in ("band_m", "minimum_in_band_duration_s", "settled_through_interval_end", "settling_right_censored", "settling_time_s", "duplicate_source_times")} for key in ("distance", "height")})
        result["original_evaluation_statuses"] = {item["kind"]: item["result"] for item in row["evaluations"]}
        result["small_original_evaluations"] = []
        for item in row["evaluations"]:
            report_path = directory / Path(item["report"]).name
            if report_path.stat().st_size > CAP:
                continue
            report = load(report_path)
            status = report.get("evaluation_status", report.get("result", report.get("acceptance", {}).get("result")))
            proof = {"kind": item["kind"], "report": binding(report_path), "recorded_status": status,
                     "report_matches_slot": binding(report_path)["sha256"] == item["report_sha256"] and status == item["result"],
                     "execution_code": item["execution"]["returncode"], "execution_error": item["execution"]["error"]}
            assert proof["report_matches_slot"] and proof["execution_code"] == 0 and proof["execution_error"] is None
            source = report.get("evaluation_source")
            if source:
                spec = next(spec for spec in trial["evaluations"] if spec["kind"] == item["kind"])
                proof["script_matches_plan"] = source["script_sha256"] == plan["source_hashes"][spec["script"]]
                proof["dependency_bindings"] = source["dependencies"]
                proof["all_recorded_dependency_hashes_match_plan"] = bool(source["dependencies"]) and all(value == plan["source_hashes"][name.removeprefix(plan["frozen_root"] + "/")] for name, value in source["dependencies"].items())
                assert proof["script_matches_plan"] and proof["all_recorded_dependency_hashes_match_plan"]
            if item["kind"] == "source_clock":
                proof.update(counts=report["counts"], clock_domain_valid=report["clock_domain_valid"], vehicle_frame_continuity_valid=report["vehicle_frame_continuity_valid"], failures=report["failures"], incomplete=report["incomplete_evidence"])
                assert report["source_clock_pass"] is True and report["clock_domain_valid"] is True and report["vehicle_frame_continuity_valid"] is True and not report["failures"] and not report["incomplete_evidence"]
            if item["kind"] == "native_startup":
                proof.update(checks=report["checks"], failures=report["failures"], incomplete=report["incomplete_evidence"])
                assert report["native_startup_pass"] is True and len(report["checks"]) == 9 and all(value is True for value in report["checks"].values()) and not report["failures"] and not report["incomplete_evidence"]
            result["small_original_evaluations"].append(proof)
        config = load(directory / "run_config.json")
        comparisons = {key: config.get(key) == trial[key] for key in ("name", "target_class", "stage", "seed", "speed_mps", "command_mode", "takeoff_mode", "gimbal_mode", "target_mode", "association_mode", "initial_select", "initial_min_candidates", "scenario_kind", "multi_target", "inference_image_size", "inference_threads", "desired_distance_m", "gazebo_render_driver", "split_clock_bridge", "px4_adapter_publish_rate_hz")}
        comparisons.update(duration=config["duration"] == trial["duration_s"], wall_timeout=config["wall_timeout"] == trial["wall_timeout_s"], model=config["model_path"] == plan["frozen_root"] + "/" + trial["model"], real_time_factor=config["real_time_factor"] == plan["protocol"]["real_time_factor"], flight_argv=row["commands"][0]["command"] == trial["flight_command"])
        stream, registered = config["supervisor_stream_timing"], trial["supervisor_stream_timing"]
        comparisons["stream_source_ages"] = all(stream[key] == registered[key] for key in ("stream_timestamp_mode", "odometry_source_max_age_s", "odometry_source_max_future_s", "command_source_max_age_s", "command_source_max_future_s"))
        comparisons["stream_wall_timeouts"] = stream["odometry_timeout_s"] == registered["odometry_timeout_wall_s"] and stream["command_timeout_s"] == registered["command_timeout_wall_s"]
        assert all(comparisons.values()) and row["runtime_configuration"]["errors"] == []
        snapshot = load(directory / "configuration/source_sha256.json")
        expected = {name: entry["sha256"] for name, entry in entries.items() if scanned(name) and entry["kind"] == "file"}
        for name in (trial["model"], "config/dds_runtime_humble22.json"):
            expected[name] = plan["source_hashes"][name]
        assert snapshot == expected
        extras = {name: value for name, value in snapshot.items() if name not in plan["source_hashes"]}
        result.update(runtime_plan_comparisons=comparisons, saved_runtime_subsystem_errors={key: value["errors"] for key, value in row["runtime_configuration"].items() if isinstance(value, dict) and "errors" in value}, source_snapshot={"count": len(snapshot), "exact_original_scanner_and_model_dds_match": True, "extra_count": len(extras), "extra_sources": extras}, infrastructure_stop=row["infrastructure_stop"], infrastructure_reasons=row["infrastructure"]["reasons"], cleanup=row["cleanup"], recording_closure_status=load(directory / "recording_closure.json")["status"], recorded_bag_integrity_status=load(directory / "bag_integrity.json")["status"])
        assert row["status"] == row["engineering_result"] == "PASS" and row["infrastructure_stop"] is False and row["cleanup"]["residual_processes"] == []
        if identifier == IDS[2]:
            result["full_task_identity_from_original_small_slot"] = row["engineering_evidence"]["physical_identity"]
            result["diagnostic_frame_identity_from_original_small_slot"] = row["engineering_evidence"]["diagnostic_frame_identity"]
            behavior = load(directory / "stage2_evaluation.json")
            result["stage2_behavior_checks"] = behavior["checks"]
            result["stage2_behavior_identity_scope"] = behavior["physical_identity"]
            assert all(value is True for value in behavior["checks"].values())
        receipt["slots"].append(result)
    assert receipt["checked_small_artifact_count"] == 127
    receipt["root_supplied_per_task_values_not_independently_read"] = {
        "source": "Root agent directly read the oversized original physical_identity.json and supplied these figures in the task message; this reviewer did not read that file.",
        "tasks_as_ordered_by_root": [{"order": 1, "correct": 219, "wrong": 0, "unknown": 103, "total": 322, "known_coverage": 219 / 322},
                                    {"order": 2, "correct": 430, "wrong": 0, "unknown": 1, "total": 431, "known_coverage": 430 / 431}],
        "arithmetic_sum_only_checked": {"correct": 219 + 430, "wrong": 0, "unknown": 103 + 1, "total": 322 + 431},
        "interpretation": "Aggregate coverage exceeds 0.8; task 1 coverage does not. No claim that every task exceeds 0.8."}
    receipt["result"] = "FIRST3_SMALL_EVIDENCE_CONSISTENT_WITH_ORIGINAL_RECORDED_ENGINEERING_PASS"
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    target = OUTPUT / "review_receipt.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"receipt": str(target), "result": receipt["result"], "checked_small_artifact_count": receipt["checked_small_artifact_count"]}))


if __name__ == "__main__":
    collect()
