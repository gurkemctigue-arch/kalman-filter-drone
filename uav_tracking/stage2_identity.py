"""Conservative offline physical-identity checks for a selected image track.

This module is never imported by runtime tracking. GT is supplied explicitly
by an offline evaluator and is never used to choose or update a live target.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from .research_metrics import iou_matrix

FRONT_VISIBILITY_RULE = "whole_static_mesh_optical_z_front_v1"
FRONT_VISIBILITY_MARGIN_M = .05


def _front_visibility_certificate(truth, chosen, overlapping, class_name, evidence):
    """Certify a sufficient whole-mesh ordering, never choose an actor by depth."""
    certificate = {"rule_revision": FRONT_VISIBILITY_RULE, "status": "UNKNOWN",
                   "margin_m": FRONT_VISIBILITY_MARGIN_M, "reason": None,
                   "chosen_id": str(truth[chosen]["id"]), "depth_bounds_m": {}, "pairs": []}
    required = {"schema_version": 1, "class_name": class_name,
                "depth_coordinate": "camera_optical_z_m", "mesh_geometry": "complete_static_render_mesh"}
    flags = ("independent_camera_geometry_complete", "all_expected_actors_projected",
             "source_time_geometry_exact", "static_mesh_projection_supported", "closed_scene_occluders_complete")
    if (not isinstance(evidence, dict) or any(evidence.get(key) != value for key, value in required.items())
            or type(evidence.get("schema_version")) is not int
            or type(evidence.get("source_image_s")) not in (int, float)
            or not math.isfinite(evidence["source_image_s"])
            or any(evidence.get(key) is not True for key in flags)):
        certificate["reason"] = "missing_or_incomplete_front_visibility_evidence"
        return certificate
    expected = evidence.get("expected_actor_ids")
    if (not isinstance(expected, list) or len(expected) != 3
            or any(not isinstance(value, str) or not value for value in expected)
            or len(set(expected)) != 3 or set(expected) != {str(item["id"]) for item in truth}):
        certificate["reason"] = "missing_or_mismatched_expected_same_class_actors"
        return certificate
    certificate["projection_evidence"] = evidence
    for item in truth:
        bounds = item.get("depth_range_m")
        if (not isinstance(bounds, (list, tuple)) or len(bounds) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in bounds)
                or not .10 < bounds[0] <= bounds[1]):
            certificate["reason"] = "invalid_or_missing_whole_mesh_depth_range"
            return certificate
        certificate["depth_bounds_m"][str(item["id"])] = [float(value) for value in bounds]
    selected_max = certificate["depth_bounds_m"][str(truth[chosen]["id"])][1]
    for index in overlapping:
        identity = str(truth[index]["id"])
        other_min = certificate["depth_bounds_m"][identity][0]
        gap = other_min - selected_max
        certificate["pairs"].append({"other_id": identity, "other_min_z_m": other_min,
                                      "chosen_max_z_m": selected_max, "depth_gap_m": gap,
                                      "strictly_behind_margin": other_min > selected_max + FRONT_VISIBILITY_MARGIN_M})
    if not all(pair["strictly_behind_margin"] for pair in certificate["pairs"]):
        certificate["reason"] = "whole_mesh_front_order_not_strictly_proven"
        return certificate
    certificate.update(status="CERTIFIED", reason="all_overlapping_actors_strictly_behind_whole_selected_mesh")
    return certificate


def physical_identity_match(selected_bbox: Sequence[float] | None, gt_objects: list[dict], *,
                            class_name: str, fresh: bool, externally_occluded: bool | None,
                            minimum_iou: float = .5,
                            front_visibility_evidence: dict | None = None) -> dict[str, Any]:
    """Return a unique image match with independently supported visibility.

    A projected mesh box is amodal. Positive overlap with another same-class
    GT box makes visibility uncertain unless exact-source, complete static
    mesh evidence proves the entire chosen actor is in front. A known
    shutter or unknown shutter state also prevents an identity certificate.
    This deliberately sacrifices coverage instead of resolving impossible
    image evidence using nearest model centre, ground-truth motion or UUID.
    """
    if not 0 < minimum_iou <= 1:
        raise ValueError("minimum_iou must be in (0,1]")
    result = {"status": "unknown", "physical_id": None, "reason": None,
              "candidate_ids": [], "iou": None, "minimum_iou": minimum_iou,
              "foreground_visibility_certificate": None}
    if not fresh or selected_bbox is None:
        return {**result, "reason": "no_fresh_selected_detection"}
    if externally_occluded is not False:
        return {**result, "reason": "known_or_unresolved_external_occlusion"}
    truth = [item for item in gt_objects if item["class_name"] == class_name]
    if len({str(item["id"]) for item in truth}) != len(truth):
        raise ValueError("Physical GT IDs must be unique within each frame")
    overlaps = iou_matrix([selected_bbox], [item["bbox"] for item in truth])[0]
    candidates = [index for index, overlap in enumerate(overlaps) if overlap >= minimum_iou-1e-12]
    result["candidate_ids"] = [str(truth[index]["id"]) for index in candidates]
    if len(candidates) != 1:
        return {**result, "reason": "multiple_feasible_physical_ids" if candidates else "no_matching_physical_id"}
    chosen = candidates[0]
    result["iou"] = float(overlaps[chosen])
    if truth[chosen].get("fully_in_frame") is not True:
        return {**result, "reason": "partial_or_unverified_gt_extent"}
    gt_overlaps = iou_matrix([truth[chosen]["bbox"]], [item["bbox"] for item in truth])[0]
    overlapping = [index for index, overlap in enumerate(gt_overlaps) if index != chosen and overlap > 0]
    if overlapping:
        certificate = _front_visibility_certificate(truth, chosen, overlapping, class_name, front_visibility_evidence)
        result["foreground_visibility_certificate"] = certificate
        if certificate["status"] != "CERTIFIED":
            return {**result, "reason": "same_class_gt_projection_overlap"}
        return {**result, "status": "known", "physical_id": str(truth[chosen]["id"]),
                "reason": "unique_image_match_with_whole_mesh_front_certificate"}
    return {**result, "status": "known", "physical_id": str(truth[chosen]["id"]), "reason": "unique_unoccluded_image_match"}


def selected_identity_summary(frames: list[dict]) -> dict[str, Any]:
    """Retain every requested frame; unknown identity is a distinct outcome.

    Inputs carry ``target_uuid``, the independently established
    ``expected_physical_id`` for that explicit task, and the conservative
    ``match`` result above. A UUID defines a task boundary only. A new task is
    never counted as a physical ID switch from the previous task.
    """
    correct = wrong = unknown = switches = 0
    previous_by_task = {}
    task_expected = {}
    outcomes = []
    for frame in frames:
        uuid = str(frame["target_uuid"])
        expected = frame.get("expected_physical_id")
        expected = None if expected is None else str(expected)
        if uuid in task_expected and task_expected[uuid] != expected:
            raise ValueError("Expected physical identity cannot change within one task UUID")
        task_expected[uuid] = expected
        match = frame["match"]
        physical = match.get("physical_id") if match.get("status") == "known" else None
        if expected is None or physical is None:
            unknown += 1
            outcome = "unknown"
        else:
            physical = str(physical)
            outcome = "correct" if physical == expected else "wrong"
            correct += outcome == "correct"
            wrong += outcome == "wrong"
            switches += uuid in previous_by_task and previous_by_task[uuid] != physical
            previous_by_task[uuid] = physical
        outcomes.append({"time_s": frame.get("time_s"), "target_uuid": uuid,
                         "expected_physical_id": expected, "physical_id": physical,
                         "outcome": outcome, "reason": match.get("reason")})
    total, known = len(frames), correct+wrong
    return {"frames": total, "correct": correct, "wrong": wrong, "unknown": unknown,
            "known_coverage": known/total if total else None,
            "retention_lower_bound": correct/total if total else None,
            "agreement_on_known_frames": correct/known if known else None,
            "observed_physical_identity_switches_within_task": switches,
            "task_count": len(task_expected), "outcomes": outcomes,
            "semantics": "Unknown/occluded frames remain in total; retention_lower_bound is not the same as conditional agreement. UUID partitions explicit tasks and never supplies physical identity."}
