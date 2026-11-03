"""Produce compact, line-referenced facts from the actual bounded extraction."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main():
    folder = Path(__file__).resolve().parent
    source = folder / "actual_windows01.json"
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "acfc758bc1e39429b137791402a925e2c7074d3aa0475391851604f707460501"
    data = json.loads(raw)
    output = folder / "window_findings01.json"
    if output.exists():
        raise FileExistsError("Keep original findings")
    cases = []
    for case in data["cases"]:
        attempts, detections, states, controls = [], [], [], []
        for entry in case["rows"]:
            r = entry["record"]
            origin = {"original_line": entry["original_line"], "original_byte_offset": entry["original_byte_offset"]}
            if r["kind"] == "tracks":
                for track in r["tracks"]:
                    if track.get("selected") and track.get("measurement_diagnostics_current_frame"):
                        m = track["measurement_diagnostics"]
                        attempts.append({**origin, "time_s": r["time_s"], "acquisition_s": r["acquisition_s"],
                                         "track_id": track["track_id"], "accepted": m["accepted"],
                                         "mahalanobis_squared": m.get("mahalanobis_squared"),
                                         "gate_threshold": m.get("gate_threshold"),
                                         "rejected_measurements": track["rejected_measurements"]})
            elif r["kind"] == "detection":
                detections.append({**origin, **{k: r.get(k) for k in (
                    "time_s", "stamp_s", "completed_s", "rgb_received_s", "depth_received_s", "worker_started_s",
                    "input_age_at_submit_s", "acquisition_gap_s", "inference_wall_s")},
                    "candidates": [{k: d.get(k) for k in ("candidate_id", "confidence", "depth_valid", "depth_valid_ratio")}
                                   for d in r["detections"]]})
            elif r["kind"] == "target_state":
                states.append({**origin, **{k: r[k] for k in ("time_s", "stamp_s", "state", "track_id", "prediction_age_s")}})
            elif r["kind"] == "control_status":
                controls.append({**origin, **r})
        lost = next(r for r in states if r["state"] == 3)
        last = max((r for r in attempts if r["accepted"] and r["time_s"] < lost["time_s"]), key=lambda r:r["time_s"])
        next_detection = min((r for r in detections if r["stamp_s"] > last["acquisition_s"]
                              and any(d["depth_valid"] for d in r["candidates"])), key=lambda r:r["stamp_s"])
        hover = next(r for r in controls if r["lifecycle"] == 4)
        cases.append({
            "slot": case["slot"], "terminal_sha256": case["terminal_sha256"],
            "original_engineering_result_retained": case["original_engineering_result"],
            "original_telemetry": {k: case[k] for k in ("source", "source_sha256", "source_bytes", "source_lines")},
            "window_inclusive_sim_s": case["window_inclusive_sim_s"],
            "selected_current_frame_update_attempts": attempts,
            "detections": detections,
            "last_selected_accepted_update_before_loss": last,
            "first_depth_valid_detection_after_last_accepted_source": next_detection,
            "first_surface_lost_in_window": lost,
            "first_controller_hover_in_window": hover,
            "prediction_limit_s_unchanged": 0.75,
            "nominal_expiry_s": last["acquisition_s"] + 0.75,
            "source_gap_s": next_detection["stamp_s"] - last["acquisition_s"],
            "last_source_to_next_detector_completed_sim_s": next_detection["completed_s"] - last["acquisition_s"],
            "current_selected_attempt_count": len(attempts),
            "current_selected_rejected_attempt_count": sum(not a["accepted"] for a in attempts),
        })
    result = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "ACTUAL_CLOSED_TELEMETRY_COMPACT_POST_HOC_FACTS_ONLY",
        "extraction_file_sha256": hashlib.sha256(raw).hexdigest(), "extraction_bytes": len(raw),
        "summary_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": cases,
        "claim_boundary": "time_s and detector fields retain recorded simulation-time semantics; inference_wall_s is only its recorded local duration. No physical E2E or exact DDS receipt is inferred. Committed/current selected-filter diagnostics do not expose every candidate-pair association score. No original FAIL/null changes and no readiness admission follows."
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bytes": output.stat().st_size,
                      "cases": [{"slot": c["slot"], "last_accepted_source_s": c["last_selected_accepted_update_before_loss"]["acquisition_s"],
                                 "next_detection_completed_sim_s": c["first_depth_valid_detection_after_last_accepted_source"]["completed_s"],
                                 "first_hover_sim_s": c["first_controller_hover_in_window"]["time_s"],
                                 "current_selected_rejected_attempts": c["current_selected_rejected_attempt_count"]} for c in cases]}))


if __name__ == "__main__":
    main()
