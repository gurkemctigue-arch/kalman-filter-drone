"""Review three car development slots from saved <=1 MiB JSON/log files only.

Reuses a SHA-pinned metadata-only helper. No algorithm/evaluator module, WSL,
ROS, native simulation, bag, model, telemetry or JSONL is imported/read/run.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN / "reliability_v4_humble54_core12_probe01_matrix"
PERSON = ROOT / "tools/experiment_orchestration/humble54_person6_closed01"
HELPER_SHA = "670269d573c95765ff99d0bfd71965e8e957d69993a55480f8e17e32df219e1e"
PRIOR_SHA = "b72182446ccd1be9bcfb77a9b684b5414db6abd160650b01404995f6f7ef4cad"
PLAN_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
MAP_SHA = "7c81219e94b774723e135fa0a696cab603811b298e24900de158f199a414a102"
IDS = ("car_stage1_velocity_seed004", "car_stage1_position_seed004", "car_stage2_crossing_seed004")


def main():
    started = datetime.now(timezone.utc).isoformat()
    source_path = PERSON / "collect_snapshot.py"
    assert source_path.is_file() and not source_path.is_symlink() and source_path.stat().st_size <= 1024 ** 2
    raw = source_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HELPER_SHA
    tree = ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert imports == {"datetime", "hashlib", "json", "math", "pathlib"}
    helper = types.ModuleType("sha_pinned_saved_metadata_helpers")
    helper.__file__ = str(source_path)
    exec(compile(raw, str(source_path), "exec"), helper.__dict__)
    helper.OUT = OUT
    prior_path = PERSON / "review_receipt.json"
    assert helper.binding(prior_path)["sha256"] == PRIOR_SHA
    prior = helper.load(prior_path)
    plan_path = MATRIX / "plan.json"
    plan = helper.load(plan_path)
    assert helper.binding(plan_path)["sha256"] == PLAN_SHA == prior["plan"]["sha256"]
    assert plan["plan_sha256"] == helper.digest(plan, "plan_sha256") == PLAN_DIGEST
    assert len(plan["trials"]) == 12 and tuple(t["id"] for t in plan["trials"][6:9]) == IDS
    assert all(t["target_class"] == "car" and t["seed"] == 4 and t["duration_s"] == 75 for t in plan["trials"][6:9])
    map_path = FROZEN / "freeze_validation/source_integrity/frozen_actual.json"
    assert helper.binding(map_path)["sha256"] == MAP_SHA
    entries = helper.load(map_path)["entries"]
    receipt = {"schema_version": 1, "kind": "CAR_THREE_ORIGINAL_DEVELOPMENT_SLOTS_SMALL_EVIDENCE_CLOSURE",
        "started_utc": started, "collector": helper.binding(Path(__file__)),
        "metadata_only_helper": helper.binding(source_path), "helper_imports": sorted(imports),
        "previous_person_review_pinned_for_plan_ancestry_only": helper.binding(prior_path),
        "plan": helper.binding(plan_path), "plan_digest": PLAN_DIGEST, "plan_digest_valid": True,
        "original_plan_denominator": 12, "reviewed_original_ordinals": [7, 8, 9],
        "registered_engineering_gates": plan["protocol"]["navigation_acceptance"], "slots": [],
        "limitations": [
            "Only these three car seed004 75-second development slots are reviewed; later slots and complete core12 closure are not inferred.",
            "No original person artifact set is rehashed; its existing receipt is pinned only for unchanged plan ancestry.",
            "No WSL/ROS/native/evaluator or algorithm module is started or imported; the executed helper is a pinned metadata-only saved-file reader.",
            "No bag, model, raw telemetry, JSONL, oversized ROS log or oversized physical-identity report is read or hashed.",
            "Physical identity counts are taken only from the small original slot summary; the oversized report and per-target_uuid coverage are not independently reviewed.",
            "A whole-task aggregate coverage above the registered threshold does not establish every requested task's coverage or the identity of unknown intervals.",
            "Source/native/behavior/runtime/cleanup/archive conclusions audit saved original reports, without raw bag re-evaluation.",
            "Saved source manifests do not prove the actual import location of every historical flight process.",
            "This is not formal research acceptance, a car population success rate, algorithm superiority, safety4 or extension16 completion."]}
    helper.copy(plan_path, Path("matrix/plan.json"), PLAN_SHA)
    helper.copy(map_path, Path("freeze_validation/frozen_actual.json"), MAP_SHA)
    helper.copy(source_path, Path("metadata_helper/person6_collect_snapshot.original.py"), HELPER_SHA)
    for trial in plan["trials"][6:9]:
        identifier = trial["id"]
        path = MATRIX / "slots" / (identifier + ".json")
        row = helper.load(path)
        assert row["record_sha256"] == helper.digest(row, "record_sha256") and row["plan_sha256"] == PLAN_DIGEST
        assert row["id"] == identifier and row["name"] == trial["name"]
        assert row["status"] == row["engineering_result"] == "PASS" and row["flight_exit_code"] == 0
        assert row["infrastructure_stop"] is False and row["infrastructure"]["reasons"] == []
        assert row["cleanup"]["residual_processes"] == []
        assert all(item["returncode"] == 0 and item["error"] is None for item in row["commands"])
        directory = FROZEN / row["name"]
        review = helper.new_slot_review(trial, row, directory, plan, entries)
        result = {"id": identifier, "original_slot": helper.binding(path), "original_finished_utc": row["finished_utc"],
            "status": row["status"], "engineering_result": row["engineering_result"], "flight_exit_code": 0,
            "infrastructure_stop": False, "slot_digest_and_plan_binding_valid": True,
            "navigation": helper.navigation(helper.load(directory / "navigation_reference_evaluation.json"), row,
                                            plan["protocol"]["navigation_acceptance"]), "small_evidence_review": review}
        if identifier == IDS[2]:
            physical = row["engineering_evidence"]["physical_identity"]
            diagnostic = row["engineering_evidence"]["diagnostic_frame_identity"]
            assert row["finished_utc"] == "2026-11-02T22:28:26.083633+00:00"
            assert (physical["correct"], physical["wrong"], physical["unknown"], physical["scheduled_samples"]) == (640, 0, 114, 754)
            assert physical["known_coverage"] == physical["retention_lower_bound"] == 640 / 754
            assert physical["requested_task_count"] == 2 and physical["unconfirmed_requested_tasks"] == []
            assert (diagnostic["frames"], diagnostic["correct"], diagnostic["wrong"], diagnostic["unknown"]) == (743, 644, 0, 99)
            result.update(full_task_identity_from_small_slot_only=physical,
                diagnostic_identity_separate_denominator_not_substituted=diagnostic,
                physical_report_and_per_uuid_independently_reviewed=False)
        helper.copy(path, Path("matrix/slots") / path.name)
        marker = MATRIX / "slots" / (identifier + ".started.json")
        helper.copy(marker, Path("matrix/slots") / marker.name)
        for item in review["small_artifact_bindings"]:
            artifact = Path(item["path"])
            helper.copy(artifact, Path("trials") / identifier / artifact.relative_to(directory), item["expected_sha256"])
        for log in sorted((MATRIX / "logs").glob(identifier + ".*.log")):
            helper.copy(log, Path("matrix/logs") / log.name)
        receipt["slots"].append(result)
    count = sum(len(item["small_evidence_review"]["small_artifact_bindings"]) for item in receipt["slots"])
    assert count == 127
    receipt.update(checked_original_small_artifact_count=count,
        all_checked_original_small_artifacts_copied=True,
        result="THREE_CAR_DEVELOPMENT_SLOTS_CONSISTENT_WITH_ORIGINAL_ENGINEERING_PASS",
        finished_utc=datetime.now(timezone.utc).isoformat())
    helper.write_json(OUT / "review_receipt.json", receipt)
    helper.write_json(OUT / "manifest.json", {"schema_version": 1, "kind": "READ_ONLY_ORIGINAL_SMALL_FILE_SNAPSHOT",
        "created_utc": receipt["finished_utc"], "original_file_count": len(helper.COPIED),
        "total_original_bytes": sum(item["source"]["bytes"] for item in helper.COPIED), "files": helper.COPIED})
    print(json.dumps({"result": receipt["result"], "checked_original_small_artifacts": count,
        "copied_originals": len(helper.COPIED), "copied_bytes": sum(item["source"]["bytes"] for item in helper.COPIED),
        "receipt": helper.binding(OUT / "review_receipt.json"), "manifest": helper.binding(OUT / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
