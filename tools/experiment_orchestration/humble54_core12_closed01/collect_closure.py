"""Close core12 using original small summaries and the last slot's small reports.

Earlier artifact suites are referenced by SHA rather than duplicated/rehashed.
No WSL/native/evaluator/algorithm/model/bag/raw telemetry/JSONL is read or run.
"""
import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN / "reliability_v4_humble54_core12_probe01_matrix"
OWNER = FROZEN / "humble54_core12_owner01"
HELPER = ROOT / "tools/experiment_orchestration/humble54_person6_closed01/collect_snapshot.py"
HELPER_SHA = "670269d573c95765ff99d0bfd71965e8e957d69993a55480f8e17e32df219e1e"
PLAN_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
MAP_SHA = "7c81219e94b774723e135fa0a696cab603811b298e24900de158f199a414a102"
PRIOR = (
    ("humble54_person6_closed01", "", "b72182446ccd1be9bcfb77a9b684b5414db6abd160650b01404995f6f7ef4cad", "7fec24229759613d5185003cf62e3874ee68aa296d4050c6f7f89c8b7165de4c"),
    ("humble54_car3_closed01", "", "cced77d0a290985b54c590c88a7e22872cfd1817fa8d8c66ff1886519b2693b0", "2c37b655ef0e255ce78e10ce5edabd15ae74da29c412520c6d8ed24bf65af1cb"),
    ("humble54_car_gimbal_pair01", "midpoint01", "a0bbd0b698c908a8d10deb2abef6b0d5b7dcd61230fdbdf8b1b114efd7f84ad6", "1a1d492112a9e9009d16ec38e18fe55ebb59cd438ee1abdb4b282ba344cde517"),
    ("humble54_car_gimbal_pair01", "active01", "d1ef033efefade312c2cc6ab78bc0040f69893b2bdc5b0f715991b3b0e37435e", "28baf44b632ee1d9828419a1b70b318f63271960c427adc4421fdf815b1f4bd2"),
)


def main():
    started = datetime.now(timezone.utc).isoformat()
    assert HELPER.is_file() and not HELPER.is_symlink() and HELPER.stat().st_size <= 1024 ** 2
    raw = HELPER.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HELPER_SHA
    tree = ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert imports == {"datetime", "hashlib", "json", "math", "pathlib"}
    helper = types.ModuleType("pinned_bounded_metadata_helpers")
    helper.__file__ = str(HELPER)
    exec(compile(raw, str(HELPER), "exec"), helper.__dict__)
    helper.OUT = OUT
    references = []
    reviewed_before = {}
    for name, suffix, receipt_sha, manifest_sha in PRIOR:
        directory = ROOT / "tools/experiment_orchestration" / name / suffix
        for filename, expected in (("review_receipt.json", receipt_sha), ("manifest.json", manifest_sha)):
            path = directory / filename
            binding = helper.binding(path)
            assert binding["sha256"] == expected
            references.append({"role": "EXISTING_PRIOR_SMALL_EVIDENCE_SNAPSHOT_NOT_RECOPIED", **binding})
        previous = helper.load(directory / "review_receipt.json")
        assert previous["plan"]["sha256"] == PLAN_SHA and previous["plan_digest"] == PLAN_DIGEST
        slots = previous.get("slots", [previous])
        for row in slots:
            assert row["id"] not in reviewed_before
            reviewed_before[row["id"]] = row
    assert len(reviewed_before) == 11
    plan_path = MATRIX / "plan.json"
    plan = helper.load(plan_path)
    assert helper.binding(plan_path)["sha256"] == PLAN_SHA
    assert plan["plan_sha256"] == helper.digest(plan, "plan_sha256") == PLAN_DIGEST
    assert len(plan["trials"]) == 12
    archived_plan = ROOT / "tools/experiment_orchestration/humble54_person6_closed01/originals/matrix/plan.json"
    assert helper.binding(archived_plan)["sha256"] == PLAN_SHA
    references.append({"role": "IDENTICAL_PLAN_ALREADY_ARCHIVED_NOT_RECOPIED", **helper.binding(archived_plan)})
    map_path = ROOT / "tools/experiment_orchestration/humble54_person6_closed01/originals/freeze_validation/frozen_actual.json"
    assert helper.binding(map_path)["sha256"] == MAP_SHA
    entries = helper.load(map_path)["entries"]
    references.extend(({"role": "PINNED_FROZEN_MAP_ALREADY_ARCHIVED_NOT_RECOPIED", **helper.binding(map_path)},
                       {"role": "PINNED_METADATA_ONLY_READER_NOT_RECOPIED", **helper.binding(HELPER)}))
    owner_terminal = helper.load(OWNER / "owner_terminal.json")
    owner_state = helper.load(OWNER / "owner_state.json")
    owner_started = helper.load(OWNER / "owner_started.json")
    assert helper.read(OWNER / "owner_terminal.json") == helper.read(OWNER / "owner_state.json")
    assert owner_terminal == owner_state
    assert owner_terminal["status"] == "COMPLETED" and owner_terminal["all_engineering_pass"] is True
    assert owner_terminal["planned_count"] == owner_terminal["started_this_invocation"] == 12
    assert owner_terminal["all_slots_terminal"] is True and owner_terminal["active_slot"] is None
    assert owner_terminal["status_counts"] == {"PASS": 12} and owner_terminal["pending_ids"] == []
    assert owner_terminal["finished_utc"] == "2026-11-02T23:28:42.041710+00:00"
    assert owner_terminal["plan_file_sha256"] == owner_started["plan_file_sha256"] == PLAN_SHA
    assert owner_terminal["plan_sha256"] == owner_started["plan_sha256"] == PLAN_DIGEST
    assert owner_started["owner"] == owner_terminal["owner"]
    assert owner_terminal["source_hashes"] == owner_started["source_hashes"]
    assert all(value == plan["source_hashes"][name] for name, value in owner_terminal["source_hashes"].items())
    normal = owner_terminal["normal_result"]
    assert normal["stop"] is None and normal["terminal_count"] == 12 and normal["all_engineering_pass"] is True
    assert normal["status_counts"] == {"PASS": 12} and normal["pending_ids"] == []
    progress_path = ROOT / "results/project_progress/humble54_core12_run01/progress.json"
    progress = helper.load(progress_path)
    assert progress["status"] == "COMPLETED" and progress["completion_scope"] == "monitored_command"
    assert progress["task"]["returncode"] == 0 and progress["process_check"]["verified_alive"] is False
    pe = progress["evidence"]
    assert pe["state"] == "COMPLETED" and pe["planned_slots"] == pe["attempted_slots"] == pe["recorded_terminal_slots"] == 12
    assert pe["status_counts"] == {"PASS": 12} and pe["unattempted_slots"] == 0
    assert pe["errors"] == [] and pe["attempted_without_terminal"] == [] and pe["current_slot"] is None
    rows = []
    for ordinal, trial in enumerate(plan["trials"], 1):
        path = MATRIX / "slots" / (trial["id"] + ".json")
        row = helper.load(path)
        assert row["id"] == trial["id"] and row["name"] == trial["name"]
        assert row["record_sha256"] == helper.digest(row, "record_sha256") and row["plan_sha256"] == PLAN_DIGEST
        assert row["status"] == row["engineering_result"] == "PASS" and row["flight_exit_code"] == 0
        assert row["infrastructure_stop"] is False and row["infrastructure"]["reasons"] == []
        assert row["cleanup"]["residual_processes"] == [] and all(row["engineering_evidence"]["checks"].values())
        evidence = {"ordinal": ordinal, "id": row["id"], "original_slot": helper.binding(path),
            "original_finished_utc": row["finished_utc"], "original_status": row["status"],
            "engineering_result": row["engineering_result"], "flight_exit_code": 0,
            "infrastructure_stop": False, "slot_digest_and_plan_binding_valid": True,
            "original_engineering_evidence": row["engineering_evidence"], "cleanup_residual_processes": []}
        if ordinal < 12:
            before = reviewed_before[row["id"]]
            assert before["original_slot"]["sha256"] == helper.binding(path)["sha256"]
            assert before["navigation"]["measured"] == row["engineering_evidence"]["measured"]
            evidence["prior_snapshot_original_slot_binding_matches"] = True
            evidence["prior_raw_artifacts_rehashed"] = False
        else:
            last_trial, last_row, last_path = trial, row, path
        rows.append(evidence)
    identifier = "car_stage3_multi_active_seed004"
    assert last_row["id"] == owner_terminal["completed_slot"] == pe["last_slot"] == identifier
    directory = FROZEN / last_row["name"]
    review = helper.new_slot_review(last_trial, last_row, directory, plan, entries)
    nav = helper.navigation(helper.load(directory / "navigation_reference_evaluation.json"), last_row,
                            plan["protocol"]["navigation_acceptance"])
    physical = last_row["engineering_evidence"]["physical_identity"]
    diagnostic = last_row["engineering_evidence"]["diagnostic_frame_identity"]
    assert (physical["correct"], physical["wrong"], physical["unknown"], physical["scheduled_samples"]) == (614, 0, 139, 753)
    assert physical["known_coverage"] == physical["retention_lower_bound"] == 614 / 753
    assert physical["requested_task_count"] == 2 and physical["unconfirmed_requested_tasks"] == []
    assert (diagnostic["frames"], diagnostic["correct"], diagnostic["wrong"], diagnostic["unknown"]) == (714, 619, 0, 95)
    gimbal = helper.load(directory / "gimbal_evaluation.json")
    assert gimbal["result"] == "PASS" and gimbal["mode"] == "active"
    for name, binding in gimbal["input_bindings"].items():
        assert helper.binding(directory / Path(binding["path"]).name)["sha256"] == binding["sha256"]
    selected = ("run_config.json", "summary.json", "navigation_reference_evaluation.json", "px4_source_clock_report.json",
        "native_startup_report.json", "flight_evaluation.json", "stage2_evaluation.json", "gimbal_evaluation.json",
        "configuration/source_sha256.json", "recording_closure.json", "recording_closure_observer.json", "bag_integrity.json",
        "owned_stop_observer.json", "process_exit_codes.json", "configuration/dds_runtime_summary.json",
        "configuration/dds_runtime_after.json", "configuration/ros_gz_runtime_after.json", "configuration/ros_gz_clock_runtime_after.json")
    for name in selected:
        helper.copy(directory / name, Path("last_trial") / name, last_row["artifact_hashes"][name])
    helper.copy(last_path, Path("matrix/slots") / last_path.name)
    marker = MATRIX / "slots" / (identifier + ".started.json")
    helper.copy(marker, Path("matrix/slots") / marker.name)
    for name in ("owner_terminal.json", "owner_state.json", "owner_started.json"):
        helper.copy(OWNER / name, Path("owner") / name)
    helper.copy(progress_path, Path("progress/progress.json"))
    log = MATRIX / "logs" / (identifier + ".physical_identity.log")
    helper.copy(log, Path("matrix/logs") / log.name)
    receipt = {"schema_version": 1, "kind": "CORE12_ORIGINAL_DEVELOPMENT_CLOSURE_WITH_LAST_SLOT_MINIMAL_SNAPSHOT",
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "collector": helper.binding(Path(__file__)), "metadata_only_helper": helper.binding(HELPER), "helper_imports": sorted(imports),
        "plan": helper.binding(plan_path), "plan_digest": PLAN_DIGEST, "original_plan_denominator": 12,
        "owner_terminal": helper.binding(OWNER / "owner_terminal.json"), "owner_current_state_byte_equal_terminal": True,
        "owner_original_status": owner_terminal["status"], "all_original_engineering_pass": True,
        "owner_finished_utc": owner_terminal["finished_utc"], "owner_and_plan_source_hashes_match": True,
        "monitored_command_exit_zero": True, "monitored_command_only_is_not_project_acceptance": True,
        "all12_original_slot_summaries": rows, "previous_11_small_evidence_references_not_recopied": references,
        "last_slot_small_evidence_review": review, "last_slot_navigation": nav,
        "last_slot_gimbal": {key: gimbal[key] for key in ("result", "mode", "centering_source", "interval", "checks", "metrics", "metric_notes")},
        "last_slot_gimbal_input_bindings_match_small_originals": True,
        "last_slot_full_task_identity_from_small_original_slot_only": physical,
        "last_slot_diagnostic_identity_separate_denominator": diagnostic,
        "last_slot_oversized_identity_report_and_per_uuid_independently_reviewed": False,
        "last_slot_checked_small_artifact_count": len(review["small_artifact_bindings"]),
        "last_slot_selected_small_artifact_copies": len(selected), "all_checked_last_slot_artifacts_copied": False,
        "result": "TWELVE_ORIGINAL_ENGINEERING_PASS_DEVELOPMENT_SLOTS_CONSISTENT_WITH_OWNER_AND_SAVED_SMALL_EVIDENCE",
        "limitations": [
            "12 PASS means these twelve original same-seed development engineering slots, not formal multi-seed research acceptance or population success rate.",
            "Earlier eleven detailed artifact suites are reused by pinned receipts/manifests; their raw artifacts are neither recopied nor rehashed here.",
            "The last slot's bounded small artifacts are checked, but only eighteen essential trial reports plus owner/slot/progress evidence are copied.",
            "The oversized last physical_identity.json and ROS log are not read or hashed; identity counts come only from the original small slot summary.",
            "Whole-task 753 samples and diagnostic 714 frames remain separate; aggregate identity coverage cannot prove each requested target_uuid's coverage or identify unknown intervals.",
            "Navigation report status RECORDED_WITH_CENSORED_FAILURES and physical identity status RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS are retained.",
            "No WSL/native/ROS/inference/evaluator/algorithm is started or imported; no model, bag, raw telemetry or JSONL is read.",
            "Saved source lists do not prove every historical flight process import location; no raw-data reevaluation is performed.",
            "This snapshot does not perform a live global process audit; saved per-slot cleanup evidence and the completed owner are separate from root's live audit.",
            "This does not complete safety4, extension16, calibration, protocol sealing, storage admission, four-estimator comparisons or formal acceptance."]}
    helper.write_json(OUT / "review_receipt.json", receipt)
    helper.write_json(OUT / "manifest.json", {"schema_version": 1, "kind": "MINIMAL_LAST_SLOT_AND_OWNER_ORIGINAL_SMALL_FILE_SNAPSHOT",
        "created_utc": receipt["finished_utc"], "original_file_count": len(helper.COPIED),
        "total_original_bytes": sum(item["source"]["bytes"] for item in helper.COPIED), "files": helper.COPIED,
        "external_evidence_references": references})
    print(helper.json.dumps({"result": receipt["result"], "last_slot_checked_small_artifacts": len(review["small_artifact_bindings"]),
        "copied_originals": len(helper.COPIED), "copied_bytes": sum(item["source"]["bytes"] for item in helper.COPIED),
        "receipt": helper.binding(OUT / "review_receipt.json"), "manifest": helper.binding(OUT / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
