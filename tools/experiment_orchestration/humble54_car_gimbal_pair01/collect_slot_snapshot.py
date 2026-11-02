"""Snapshot one completed car gimbal PASS slot using bounded saved metadata.

Each mode writes a new, exclusive directory. Missing/unfinished/failed originals
are never labeled PASS. This script starts no native process or evaluator.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
FROZEN = ROOT / "results/frozen_fullplan_v4_humble54"
MATRIX = FROZEN / "reliability_v4_humble54_core12_probe01_matrix"
HELPER = ROOT / "tools/experiment_orchestration/humble54_person6_closed01/collect_snapshot.py"
HELPER_SHA = "670269d573c95765ff99d0bfd71965e8e957d69993a55480f8e17e32df219e1e"
PLAN_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"
MAP_SHA = "7c81219e94b774723e135fa0a696cab603811b298e24900de158f199a414a102"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("midpoint", "active"))
    mode = parser.parse_args().mode
    started = datetime.now(timezone.utc).isoformat()
    assert HELPER.is_file() and not HELPER.is_symlink() and HELPER.stat().st_size <= 1024 ** 2
    raw = HELPER.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HELPER_SHA
    tree = ast.parse(raw.decode("utf-8-sig"), feature_version=(3, 10))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert imports == {"datetime", "hashlib", "json", "math", "pathlib"}
    helper = types.ModuleType("pinned_metadata_only_saved_file_helpers")
    helper.__file__ = str(HELPER)
    exec(compile(raw, str(HELPER), "exec"), helper.__dict__)
    out = BASE / (mode + "01")
    helper.OUT = out
    plan_path = MATRIX / "plan.json"
    plan = helper.load(plan_path)
    assert helper.binding(plan_path)["sha256"] == PLAN_SHA
    assert plan["plan_sha256"] == helper.digest(plan, "plan_sha256") == PLAN_DIGEST
    ordinal = 10 if mode == "midpoint" else 11
    trial = plan["trials"][ordinal - 1]
    identifier = "car_stage3_" + mode + "_seed004"
    assert len(plan["trials"]) == 12 and trial["id"] == identifier
    assert trial["target_class"] == "car" and trial["seed"] == 4 and trial["duration_s"] == 75
    assert trial["gimbal_mode"] == mode and trial["stage"] == 3 and trial["multi_target"] is False
    assert trial["target_mode"] == "auto_unique"
    slot_path = MATRIX / "slots" / (identifier + ".json")
    if not slot_path.is_file():
        raise SystemExit("Original terminal slot does not exist; no output created")
    row = helper.load(slot_path)
    assert row["id"] == identifier and row["name"] == trial["name"]
    assert row["record_sha256"] == helper.digest(row, "record_sha256") and row["plan_sha256"] == PLAN_DIGEST
    assert row["status"] == row["engineering_result"] == "PASS", "No snapshot acceptance for non-PASS original"
    assert row["flight_exit_code"] == 0 and row["infrastructure_stop"] is False
    assert row["infrastructure"]["reasons"] == [] and row["cleanup"]["residual_processes"] == []
    assert all(c["returncode"] == 0 and c["error"] is None for c in row["commands"])
    map_path = FROZEN / "freeze_validation/source_integrity/frozen_actual.json"
    assert helper.binding(map_path)["sha256"] == MAP_SHA
    entries = helper.load(map_path)["entries"]
    directory = FROZEN / row["name"]
    review = helper.new_slot_review(trial, row, directory, plan, entries)
    nav = helper.navigation(helper.load(directory / "navigation_reference_evaluation.json"), row,
                            plan["protocol"]["navigation_acceptance"])
    gimbal_path = directory / "gimbal_evaluation.json"
    gimbal = helper.load(gimbal_path)
    assert gimbal["mode"] == mode and gimbal["result"] == "PASS"
    assert gimbal["centering_source"] == "all_detections_in_single_target_world"
    assert all(value is True for value in gimbal["checks"].values())
    for name, binding in gimbal["input_bindings"].items():
        source_path = directory / Path(binding["path"]).name
        assert helper.binding(source_path)["sha256"] == binding["sha256"]
    gimbal_summary = {"original_report": helper.binding(gimbal_path), "result": gimbal["result"],
        "mode": mode, "centering_source": gimbal["centering_source"], "interval": gimbal["interval"],
        "checks": gimbal["checks"], "metrics": gimbal["metrics"],
        "image_timestamp_tf_coverage": gimbal["geometry"]["image_timestamp_tf_coverage"],
        "input_bindings_match_small_originals": True, "metric_notes": gimbal["metric_notes"]}
    assert "physical_identity" not in row["engineering_evidence"]
    out.mkdir(exist_ok=False)
    helper.copy(plan_path, Path("matrix/plan.json"), PLAN_SHA)
    helper.copy(map_path, Path("freeze_validation/frozen_actual.json"), MAP_SHA)
    helper.copy(HELPER, Path("metadata_helper/person6_collect_snapshot.original.py"), HELPER_SHA)
    helper.copy(slot_path, Path("matrix/slots") / slot_path.name)
    marker = MATRIX / "slots" / (identifier + ".started.json")
    helper.copy(marker, Path("matrix/slots") / marker.name)
    for item in review["small_artifact_bindings"]:
        artifact = Path(item["path"])
        helper.copy(artifact, Path("trial") / artifact.relative_to(directory), item["expected_sha256"])
    for log in sorted((MATRIX / "logs").glob(identifier + ".*.log")):
        helper.copy(log, Path("matrix/logs") / log.name)
    receipt = {"schema_version": 1, "kind": "ONE_CAR_GIMBAL_ORIGINAL_SLOT_SMALL_EVIDENCE_CLOSURE",
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "collector": helper.binding(Path(__file__)), "metadata_only_helper": helper.binding(HELPER),
        "helper_imports": sorted(imports), "plan": helper.binding(plan_path), "plan_digest": PLAN_DIGEST,
        "original_plan_denominator": 12, "reviewed_original_ordinal": ordinal, "id": identifier,
        "original_slot": helper.binding(slot_path), "original_finished_utc": row["finished_utc"],
        "original_status": row["status"], "engineering_result": row["engineering_result"],
        "slot_digest_and_plan_binding_valid": True, "navigation": nav, "gimbal": gimbal_summary,
        "small_evidence_review": review, "checked_original_small_artifact_count": len(review["small_artifact_bindings"]),
        "all_checked_original_small_artifacts_copied": True,
        "result": "ONE_ORIGINAL_CAR_GIMBAL_DEVELOPMENT_PASS_CONSISTENT_WITH_SMALL_EVIDENCE",
        "limitations": [
            "Only this completed original 75-second seed004 development slot is reviewed; no other slot is assigned any result.",
            "No native, WSL, ROS, simulation, inference, algorithm or evaluator module was started/imported.",
            "No bag, model, raw telemetry, JSONL or oversized ROS log was read or hashed.",
            "Review audits saved original small reports, not a raw-data reevaluation or a proof of every historical process import location.",
            "No physical-identity full-task report exists in this auto-unique single-target slot; no identity-coverage result is inferred.",
            "Gimbal centering metrics use detected boxes on their recorded metric interval and sampled detections, not an annotated full-task denominator.",
            "Navigation uses its own full fixed-grid interval/coverage, not the gimbal detection denominator.",
            "One seed does not establish gimbal superiority, population reliability, formal acceptance, safety4 or extension16 completion."]}
    helper.write_json(out / "review_receipt.json", receipt)
    helper.write_json(out / "manifest.json", {"schema_version": 1, "kind": "READ_ONLY_ORIGINAL_SMALL_FILE_SNAPSHOT",
        "created_utc": receipt["finished_utc"], "original_file_count": len(helper.COPIED),
        "total_original_bytes": sum(item["source"]["bytes"] for item in helper.COPIED), "files": helper.COPIED})
    print(helper.json.dumps({"id": identifier, "result": receipt["result"],
        "checked_original_small_artifacts": receipt["checked_original_small_artifact_count"],
        "copied_originals": len(helper.COPIED), "copied_bytes": sum(x["source"]["bytes"] for x in helper.COPIED),
        "receipt": helper.binding(out / "review_receipt.json"), "manifest": helper.binding(out / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
