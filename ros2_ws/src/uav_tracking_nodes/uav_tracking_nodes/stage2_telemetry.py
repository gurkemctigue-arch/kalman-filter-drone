"""Plain, GT-free snapshots for offline association and identity evaluation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def track_snapshot(result: Any, *, target_uuid: str | None, acquisition_s: float,
                   output_s: float, frame_id: str, projected: bool) -> dict:
    """Serialize only measurements and tracker state, with explicit timing.

    A retained last box is not a new detection. Offline evaluation must use
    ``matched`` plus ``last_detection_s`` and the acquisition stamp rather
    than counting retained or projected boxes as fresh true positives.
    """
    tracks = []
    selected_id = result.target.track_id if result.target is not None else None
    for track in result.tracks:
        detection = track.last_detection
        measurement_diagnostics = getattr(track, "last_measurement_diagnostics", {})
        tracks.append({
            "track_id": track.track_id,
            "class_name": str(track.class_id),
            "bbox_xyxy": list(track.bbox),
            "confidence": track.confidence,
            "state": track.state.value,
            "matched": bool(track._matched_this_frame and not projected),
            "depth_valid": bool(detection is not None and detection.position_3d is not None),
            "position_world_m": None if track.position_3d is None else list(track.position_3d),
            "velocity_world_mps": None if track.velocity_3d is None else list(track.velocity_3d),
            "last_detection_s": track.last_update_timestamp,
            "last_measurement_s": track.last_measurement_timestamp,
            "candidate_id": None if detection is None else detection.metadata.get("candidate_id"),
            "selected": track.track_id == selected_id,
            "ambiguous": track.track_id in result.ambiguous_track_ids,
            "rejected_measurements": track.rejected_measurements,
            "measurement_diagnostics": deepcopy(measurement_diagnostics),
            "measurement_diagnostics_current_frame": bool(
                not projected and measurement_diagnostics
                and measurement_diagnostics.get("measurement_timestamp_s") == acquisition_s
            ),
        })
    return {
        "schema_version": 1, "acquisition_s": float(acquisition_s),
        "output_s": float(output_s), "state_frame": frame_id,
        "projected": bool(projected), "target_uuid": target_uuid or "",
        "target_track_id": selected_id, "target_status": result.status.value,
        "associations": [list(pair) for pair in result.associations],
        "ambiguous_track_ids": list(result.ambiguous_track_ids),
        "ambiguous_detection_indices": list(result.ambiguous_detection_indices),
        "merge_uncertainty_detection_indices": list(result.merge_uncertainty_detection_indices),
        "tracks": tracks,
    }
