"""Independent, bounded saved-file audit; never imports project/collector code."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SNAP = ROOT / "tools/experiment_orchestration/humble54_car3_closed01"
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
CAP = 1024 ** 2
READS = {}
IDS = ("car_stage1_velocity_seed004", "car_stage1_position_seed004", "car_stage2_crossing_seed004")
PINS = {
    "manifest.json": "2c37b655ef0e255ce78e10ce5edabd15ae74da29c412520c6d8ed24bf65af1cb",
    "review_receipt.json": "cced77d0a290985b54c590c88a7e22872cfd1817fa8d8c66ff1886519b2693b0",
    "collect_snapshot.py": "65ccb90be1e97ccfedd6836283d4424552d6a21ba60da7d8b61d3f3943c480cf",
}


def read(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.suffix.lower() in {".json", ".log", ".py", ".md"}, str(path)
    assert path.stat().st_size <= CAP, str(path)
    if path not in READS:
        READS[path] = path.read_bytes()
    return READS[path]


def load(path):
    return json.loads(read(path).decode("utf-8-sig"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binding(path):
    data = read(path)
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def record_digest(data, field):
    return sha(json.dumps({k: v for k, v in data.items() if k != field},
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def main():
    started = datetime.now(timezone.utc).isoformat()
    for name, expected in PINS.items():
        assert sha(read(SNAP / name)) == expected, name
    # Parse only. Do not execute either the author collector or its helper.
    for path in (SNAP / "collect_snapshot.py", SNAP / "originals/metadata_helper/person6_collect_snapshot.original.py"):
        ast.parse(read(path).decode("utf-8-sig"), feature_version=(3, 10))
    manifest = load(SNAP / "manifest.json")
    author = load(SNAP / "review_receipt.json")
    helper = ROOT / "tools/experiment_orchestration/humble54_person6_closed01/collect_snapshot.py"
    allowed_source_roots = (FROZEN.resolve(), helper.parent.resolve())
    copied, original_by_path = {}, {}
    for item in manifest["files"]:
        relative = Path(item["snapshot_path"])
        assert not relative.is_absolute() and relative.parts[0] == "originals"
        target = SNAP / relative
        assert target.resolve().is_relative_to((SNAP / "originals").resolve())
        original = Path(item["source"]["path"])
        assert original.is_absolute() and any(original.resolve().is_relative_to(root) for root in allowed_source_roots)
        original_bytes, copied_bytes = read(original), read(target)
        assert original_bytes == copied_bytes, str(relative)
        observed = {"bytes": len(original_bytes), "sha256": sha(original_bytes)}
        assert observed["bytes"] == item["source"]["bytes"]
        assert observed["sha256"] == item["source"]["sha256"]
        assert item["copied_byte_for_byte"] is True
        assert item["expected_source_sha256"] in (None, observed["sha256"])
        key = relative.as_posix()
        assert key not in copied and str(original.resolve()) not in original_by_path
        copied[key] = observed
        original_by_path[str(original.resolve())] = key
    assert len(copied) == manifest["original_file_count"] == 153
    assert sum(item["bytes"] for item in copied.values()) == manifest["total_original_bytes"] == 3407808
    actual_files = {path.relative_to(SNAP).as_posix() for path in (SNAP / "originals").rglob("*") if path.is_file()}
    assert actual_files == set(copied)
    plan = load(SNAP / "originals/matrix/plan.json")
    assert plan["plan_sha256"] == record_digest(plan, "plan_sha256") == author["plan_digest"] == "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
    assert binding(SNAP / "originals/matrix/plan.json")["sha256"] == author["plan"]["sha256"] == "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
    assert len(plan["trials"]) == author["original_plan_denominator"] == 12
    assert tuple(trial["id"] for trial in plan["trials"][6:9]) == IDS
    assert tuple(slot["id"] for slot in author["slots"]) == IDS
    assert author["reviewed_original_ordinals"] == [7, 8, 9]
    gates = plan["protocol"]["navigation_acceptance"]
    assert gates == author["registered_engineering_gates"] and gates["require_final_window_settled"] is True
    frozen_map = load(SNAP / "originals/freeze_validation/frozen_actual.json")["entries"]
    # Pin the old review only for ancestry; do not traverse/re-hash its person artifacts.
    prior_path = Path(author["previous_person_review_pinned_for_plan_ancestry_only"]["path"])
    assert binding(prior_path) == author["previous_person_review_pinned_for_plan_ancestry_only"]
    assert load(prior_path)["plan"]["sha256"] == author["plan"]["sha256"]
    total_checked, slots, excluded = 0, [], []
    for trial, saved in zip(plan["trials"][6:9], author["slots"]):
        identifier = trial["id"]
        base = SNAP / "originals/trials" / identifier
        row_path = SNAP / "originals/matrix/slots" / (identifier + ".json")
        row = load(row_path)
        assert trial["target_class"] == "car" and trial["seed"] == 4 and trial["duration_s"] == 75
        assert row["record_sha256"] == record_digest(row, "record_sha256")
        assert row["plan_sha256"] == plan["plan_sha256"] and row["id"] == identifier and row["name"] == trial["name"]
        assert binding(row_path)["sha256"] == saved["original_slot"]["sha256"]
        assert row["status"] == row["engineering_result"] == saved["status"] == saved["engineering_result"] == "PASS"
        assert row["flight_exit_code"] == 0 and row["infrastructure_stop"] is False and row["infrastructure"]["reasons"] == []
        assert row["cleanup"]["residual_processes"] == []
        assert all(command["returncode"] == 0 and command["error"] is None for command in row["commands"])
        assert row["commands"][0]["command"] == trial["flight_command"]
        directory = FROZEN / row["name"]
        eligible = {}
        for name, expected in row["artifact_hashes"].items():
            source = directory / name
            assert source.resolve().is_relative_to(directory.resolve())
            if source.suffix.lower() not in {".json", ".log"}:
                continue
            size = source.stat().st_size
            if size > CAP:
                excluded.append({"path": str(source), "bytes": size, "read_or_hashed": False})
                continue
            copied_name = original_by_path[str(source.resolve())]
            assert copied_name == "originals/trials/" + identifier + "/" + Path(name).as_posix()
            assert copied[copied_name]["sha256"] == expected
            eligible[str(source.resolve())] = expected
        checked = saved["small_evidence_review"]["small_artifact_bindings"]
        assert len(checked) == len(eligible)
        assert {str(Path(item["path"]).resolve()): item["sha256"] for item in checked} == eligible
        assert all(item["matches"] is True and item["sha256"] == item["expected_sha256"] for item in checked)
        total_checked += len(checked)
        nav = load(base / "navigation_reference_evaluation.json")
        whole, kf = nav["whole_interval"], nav["kf_navigation"]
        transients = whole["transients"]["base_link"]
        measured = {
            "base_link_distance_rmse_m": whole["metrics"]["base_link_distance_error_m"]["rmse"],
            "base_link_height_rmse_m": whole["metrics"]["base_link_height_error_m"]["rmse"],
            "valid_state_coverage": kf["counts"]["valid_navigation_samples"] / kf["counts"]["scheduled_samples"],
            "truth_coverage": whole["matched_truth_samples"] / whole["scheduled_samples"],
        }
        assert all(math.isfinite(value) for value in measured.values())
        assert measured["valid_state_coverage"] == kf["valid_state_coverage"]
        checks = {
            "base_link_distance": measured["base_link_distance_rmse_m"] <= gates["maximum_base_link_distance_rmse_m"],
            "base_link_height": measured["base_link_height_rmse_m"] <= gates["maximum_base_link_height_rmse_m"],
            "navigation_coverage": measured["valid_state_coverage"] >= gates["minimum_valid_state_coverage"],
            "truth_coverage": measured["truth_coverage"] >= gates["minimum_truth_coverage"],
            "final_distance_settled": transients["distance"]["settled_through_interval_end"] is True,
            "final_height_settled": transients["height"]["settled_through_interval_end"] is True,
        }
        assert checks == row["engineering_evidence"]["checks"] == saved["navigation"]["six_independently_compared_gates"]
        assert all(checks.values()) and measured == row["engineering_evidence"]["measured"] == saved["navigation"]["measured"]
        assert whole["scheduled_samples"] == math.floor((nav["interval"]["end_s"] - nav["interval"]["start_s"]) / .1 + 1e-8) + 1
        statuses, source_bindings = {}, []
        for evaluation in row["evaluations"]:
            name = Path(evaluation["report"]).name
            kind = evaluation["kind"]
            assert evaluation["execution"]["returncode"] == 0 and evaluation["execution"]["error"] is None
            original = directory / name
            if original.stat().st_size > CAP:
                assert kind == "physical_identity" and not (base / name).exists()
                statuses[kind] = {"slot_status_only": evaluation["result"], "report_read_or_hashed": False}
                continue
            report = load(base / name)
            assert sha(read(base / name)) == evaluation["report_sha256"]
            status = report.get("evaluation_status", report.get("result", report.get("acceptance", {}).get("result")))
            assert status == evaluation["result"]
            statuses[kind] = status
            if "evaluation_source" in report:
                spec = next(spec for spec in trial["evaluations"] if spec["kind"] == kind)
                source = report["evaluation_source"]
                assert source["script_sha256"] == plan["source_hashes"][spec["script"]]
                assert source["dependencies"] and all(value == plan["source_hashes"][key.removeprefix(plan["frozen_root"] + "/")]
                    for key, value in source["dependencies"].items())
                source_bindings.append(kind)
            if kind == "source_clock":
                assert report["source_clock_pass"] is report["clock_domain_valid"] is report["vehicle_frame_continuity_valid"] is True
                assert report["failures"] == {} and report["incomplete_evidence"] == {}
            if kind in {"native_startup", "selected_target_safety"}:
                assert report["checks"] and all(value is True for value in report["checks"].values())
                if kind == "native_startup":
                    assert len(report["checks"]) == 9 and report["native_startup_pass"] is True
                    assert report["failures"] == {} and report["incomplete_evidence"] == {}
                else:
                    assert report["physical_identity"]["evaluated"] is False
        config = load(base / "run_config.json")
        fields = ("name", "target_class", "stage", "seed", "speed_mps", "command_mode", "takeoff_mode", "gimbal_mode",
                  "target_mode", "association_mode", "initial_select", "initial_min_candidates", "scenario_kind", "multi_target",
                  "inference_image_size", "inference_threads", "desired_distance_m", "gazebo_render_driver", "split_clock_bridge",
                  "px4_adapter_publish_rate_hz")
        assert all(config.get(key) == trial[key] for key in fields)
        assert config["duration"] == trial["duration_s"] and config["wall_timeout"] == trial["wall_timeout_s"]
        assert config["model_path"] == plan["frozen_root"] + "/" + trial["model"]
        assert config["real_time_factor"] == plan["protocol"]["real_time_factor"]
        stream, registered = config["supervisor_stream_timing"], trial["supervisor_stream_timing"]
        assert all(stream[key] == registered[key] for key in ("stream_timestamp_mode", "odometry_source_max_age_s", "odometry_source_max_future_s", "command_source_max_age_s", "command_source_max_future_s"))
        assert stream["odometry_timeout_s"] == registered["odometry_timeout_wall_s"] and stream["command_timeout_s"] == registered["command_timeout_wall_s"]
        assert row["runtime_configuration"]["errors"] == []
        assert all(value["errors"] == [] for value in row["runtime_configuration"].values() if isinstance(value, dict) and "errors" in value)
        source_snapshot = load(base / "configuration/source_sha256.json")
        expected = {name: entry["sha256"] for name, entry in frozen_map.items() if entry["kind"] == "file"
                    and name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and Path(name).suffix in {".py", ".sh", ".msg"}}
        for name in (trial["model"], "config/dds_runtime_humble22.json"):
            expected[name] = plan["source_hashes"][name]
        assert source_snapshot == expected
        assert load(base / "process_exit_codes.json") == row["cleanup"]["process_exit_codes"]
        observer = load(base / "owned_stop_observer.json")
        assert observer["status"] == "EVIDENCE_COMPLETE" and observer["errors"] == []
        saved_statuses = {name: load(base / name)["status"] for name in (
            "recording_closure.json", "recording_closure_observer.json", "bag_integrity.json",
            "configuration/dds_runtime_summary.json", "configuration/dds_runtime_after.json",
            "configuration/ros_gz_runtime_after.json", "configuration/ros_gz_clock_runtime_after.json")}
        assert all(value == ("CLOSED" if name == "recording_closure_observer.json" else "PASS") for name, value in saved_statuses.items())
        item = {"id": identifier, "original_status": row["status"], "slot_digest": row["record_sha256"],
                "checked_original_small_artifacts_all_copied": len(checked), "navigation_measured": measured,
                "six_navigation_gates": checks, "saved_evaluation_statuses": statuses,
                "saved_evaluator_source_bindings_checked": source_bindings, "source_snapshot_count": len(source_snapshot),
                "saved_runtime_and_archive_statuses": saved_statuses, "cleanup": row["cleanup"],
                "owned_stop_observer": {key: observer[key] for key in ("status", "runtime_acceptance", "errors")}}
        if identifier == IDS[2]:
            physical = row["engineering_evidence"]["physical_identity"]
            diagnostic = row["engineering_evidence"]["diagnostic_frame_identity"]
            assert physical == saved["full_task_identity_from_small_slot_only"]
            assert diagnostic == saved["diagnostic_identity_separate_denominator_not_substituted"]
            assert (physical["scheduled_samples"], physical["correct"], physical["wrong"], physical["unknown"]) == (754, 640, 0, 114)
            assert sum(physical[key] for key in ("correct", "wrong", "unknown")) == physical["scheduled_samples"]
            assert physical["known_coverage"] == physical["retention_lower_bound"] == 640 / 754
            assert physical["requested_task_count"] == 2 and physical["unconfirmed_requested_tasks"] == []
            assert (diagnostic["frames"], diagnostic["correct"], diagnostic["wrong"], diagnostic["unknown"]) == (743, 644, 0, 99)
            assert diagnostic["known_coverage"] == diagnostic["retention_lower_bound"] == 644 / 743
            assert saved["physical_report_and_per_uuid_independently_reviewed"] is False
            item.update(full_task_identity_small_summary_only=physical, separate_diagnostic_identity=diagnostic,
                        oversized_physical_report_and_per_uuid_reviewed=False)
        slots.append(item)
    assert total_checked == author["checked_original_small_artifact_count"] == 127
    result = {"schema_version": 1, "kind": "INDEPENDENT_BOUNDED_CAR3_SNAPSHOT_REVIEW",
              "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
              "reviewer_script": binding(Path(__file__)), "reviewed_input_pins": PINS,
              "result": "ACCEPTED_WITH_EXPLICIT_SAVED_EVIDENCE_BOUNDARIES", "findings": [],
              "snapshot_originals_checked_byte_for_byte": len(copied), "snapshot_original_bytes": manifest["total_original_bytes"],
              "checked_original_small_artifacts_all_present": total_checked, "plan_digest": plan["plan_sha256"],
              "original_plan_denominator": len(plan["trials"]), "reviewed_ordinals": [7, 8, 9],
              "slots": slots, "excluded_metadata_only": excluded, "checked_copy_bindings": copied,
              "limitations": [
                  "No WSL, native simulation, ROS, evaluator, author collector or project algorithm is executed/imported.",
                  "All file reads are guarded at <=1 MiB; no bag, model, JSONL, raw telemetry or oversized physical report/log is read or hashed.",
                  "Saved source/native/behavior/runtime/cleanup/archive reports are checked without raw bag re-evaluation.",
                  "Source snapshots do not establish each historical process's actual import location.",
                  "Physical identity is checked only against the original small slot summary, with UNKNOWN and original denominators retained.",
                  "Full-task 640/0/114/754 and diagnostic 644/0/99/743 remain separate; aggregate coverage does not establish each requested UUID task passed.",
                  "The prior person receipt is pinned solely for plan ancestry; its original artifact set is not revisited.",
                  "This accepts three development-slot small-evidence snapshots, not core12 completion, formal research acceptance, population reliability, safety4, extension16 or algorithm superiority."]}
    destination = OUT / "independent_review_receipt.json"
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"result": result["result"], "receipt": binding(destination), "files": len(copied), "bytes": manifest["total_original_bytes"], "artifacts": total_checked}, ensure_ascii=True))


if __name__ == "__main__":
    main()
