"""Describe two completed small-file snapshots; never run a flight or evaluator.

Requires the active snapshot's independently supplied receipt SHA. Does not read
an original live slot, infer a missing result, align raw frames, or test a claim.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
MIDPOINT_SHA = "a0bbd0b698c908a8d10deb2abef6b0d5b7dcd61230fdbdf8b1b114efd7f84ad6"
PLAN_SHA = "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b"
PLAN_DIGEST = "3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31"


def read(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 ** 2
    return path.read_bytes()


def load(path):
    return json.loads(read(path).decode("utf-8-sig"))


def sha(path):
    return hashlib.sha256(read(path)).hexdigest()


def describe(mode, expected_sha):
    directory = BASE / (mode + "01")
    path = directory / "review_receipt.json"
    assert sha(path) == expected_sha
    receipt = load(path)
    assert receipt["id"] == "car_stage3_" + mode + "_seed004"
    assert receipt["original_status"] == receipt["engineering_result"] == "PASS"
    assert receipt["plan"]["sha256"] == PLAN_SHA and receipt["plan_digest"] == PLAN_DIGEST
    assert receipt["slot_digest_and_plan_binding_valid"] is True
    assert all(receipt["navigation"]["six_independently_compared_gates"].values())
    assert receipt["gimbal"]["mode"] == mode and receipt["gimbal"]["result"] == "PASS"
    plan = load(directory / "originals/matrix/plan.json")
    assert sha(directory / "originals/matrix/plan.json") == PLAN_SHA
    assert plan["plan_sha256"] == PLAN_DIGEST
    gimbal = receipt["gimbal"]
    assert gimbal["centering_source"] == "all_detections_in_single_target_world"
    return receipt, plan, {"receipt_sha256": expected_sha, "manifest_sha256": sha(directory / "manifest.json"),
        "id": receipt["id"], "original_finished_utc": receipt["original_finished_utc"],
        "original_status": receipt["original_status"], "navigation": receipt["navigation"],
        "gimbal": {key: gimbal[key] for key in ("mode", "result", "centering_source", "interval", "metrics", "image_timestamp_tf_coverage")}}


def difference(midpoint, active):
    return {"midpoint": midpoint, "active": active, "active_minus_midpoint": active - midpoint,
            "active_minus_midpoint_percent_of_midpoint": (active - midpoint) / midpoint * 100 if midpoint else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-receipt-sha256", required=True)
    args = parser.parse_args()
    assert len(args.active_receipt_sha256) == 64 and all(c in "0123456789abcdef" for c in args.active_receipt_sha256)
    middle, plan, mid = describe("midpoint", MIDPOINT_SHA)
    active, other_plan, act = describe("active", args.active_receipt_sha256)
    assert plan == other_plan
    mid_trial, active_trial = plan["trials"][9:11]
    assert mid_trial["id"] == middle["id"] and active_trial["id"] == active["id"]
    keys = ("target_class", "seed", "gazebo_seed", "stage", "multi_target", "target_mode", "association_mode",
        "initial_select", "initial_min_candidates", "command_mode", "takeoff_mode", "gazebo_render_driver", "scenario_kind",
        "duration_s", "speed_mps", "wall_timeout_s", "model", "inference_image_size", "inference_threads", "desired_distance_m",
        "navigation_correlated_two_face_bound", "navigation_exclusive_reference", "car_surface_recovery",
        "simulation_pacing_registration", "px4_adapter_publish_rate_hz", "split_clock_bridge", "world_source")
    comparisons = {key: mid_trial[key] == active_trial[key] for key in keys}
    assert all(comparisons.values()), "Trial design differs beyond gimbal mode; do not label this a controlled comparison"
    differences = {key: difference(mid["navigation"]["measured"][key], act["navigation"]["measured"][key])
        for key in ("base_link_distance_rmse_m", "base_link_height_rmse_m", "valid_state_coverage", "truth_coverage")}
    for name in ("detected_center_normalized_error", "true_image_horizon_error_rad"):
        for metric in ("rmse", "p95_absolute"):
            differences[name + "_" + metric] = difference(mid["gimbal"]["metrics"][name][metric], act["gimbal"]["metrics"][name][metric])
    result = {"schema_version": 1, "kind": "DESCRIPTIVE_ONE_SEED_CAR_GIMBAL_SAVED_REPORT_COMPARISON",
        "created_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": sha(Path(__file__)),
        "result": "RECORDED_DESCRIPTIVE_COMPARISON_NOT_STATISTICAL_ACCEPTANCE", "plan_sha256": PLAN_SHA,
        "plan_digest": PLAN_DIGEST, "same_registered_trial_fields": comparisons, "midpoint": mid, "active": act,
        "differences_active_minus_midpoint": differences,
        "limitations": [
            "One completed seed004 development trial per mode; no population reliability or significance/superiority claim.",
            "Each navigation record preserves its own complete fixed-grid interval and valid/truth denominators.",
            "Gimbal center errors are conditional on recorded detected boxes over each report's metric interval; missing detections are not silently counted as successful centering.",
            "Detection counts are not full-task identity coverage, and these single-target auto-unique slots provide no full-task physical identity report.",
            "The report intervals differ; these are original summary comparisons, not raw-frame aligned matched measurements.",
            "Lower centering error alone does not establish improved physical distance/height or valid-navigation coverage.",
            "No original reports, frozen sources, bags or live slots were changed; no native process, evaluator or raw-data reevaluation ran.",
            "This does not establish complete core12, safety4, extension16 or formal acceptance."]}
    output = BASE / "pair_comparison01.json"
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"result": result["result"], "output": str(output), "sha256": sha(output),
                      "differences": differences}, ensure_ascii=False))


if __name__ == "__main__":
    main()
