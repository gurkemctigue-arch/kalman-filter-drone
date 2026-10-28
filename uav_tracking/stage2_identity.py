"""Conservative offline physical-identity checks for a selected image track.

This module is never imported by runtime tracking. GT is supplied explicitly
by an offline evaluator and is never used to choose or update a live target.
"""

from __future__ import annotations

from typing import Any, Sequence

from .research_metrics import iou_matrix


def physical_identity_match(selected_bbox: Sequence[float] | None, gt_objects: list[dict], *,
                            class_name: str, fresh: bool, externally_occluded: bool | None,
                            minimum_iou: float = .5) -> dict[str, Any]:
    """Return an ID only for one nonoverlapping, fully visible GT candidate.

    A projected mesh box is amodal. Positive overlap with another same-class
    GT box makes visibility uncertain, even when one IoU is highest. A known
    shutter or unknown shutter state also prevents an identity certificate.
    This deliberately sacrifices coverage instead of resolving impossible
    image evidence using nearest model centre, ground-truth motion or UUID.
    """
    if not 0 < minimum_iou <= 1:
        raise ValueError("minimum_iou must be in (0,1]")
    result = {"status": "unknown", "physical_id": None, "reason": None,
              "candidate_ids": [], "iou": None, "minimum_iou": minimum_iou}
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
    if any(overlap > 0 for index, overlap in enumerate(gt_overlaps) if index != chosen):
        return {**result, "reason": "same_class_gt_projection_overlap"}
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
