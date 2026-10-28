"""Read only scalar messages around first following/loss; never start ROS nodes."""

import argparse
from bisect import bisect_left
from collections import Counter
import json
from pathlib import Path

import evaluate_stage1_flight as evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-s", type=float, default=5.0)
    args = parser.parse_args()
    evaluation.TOPICS = ("/clock", "/tracking/state", "/tracking/observations", "/tracking/status",
                         "/tracking/detection_diagnostics", "/tracking/flight_phase", "/tf", "/tf_static")
    records, metadata = evaluation.read_rosbag(args.bag)
    follow = next(row.time_s for row in records if row.topic == "/tracking/flight_phase"
                  and row.message.data.split(":", 1)[0] == "FOLLOW")
    start, end = follow - 1.0, follow + args.window_s
    states, observations, diagnostics, tf_rows = [], [], [], []
    last_state, last_rejected = None, None
    for row in records:
        message = row.message
        receive = row.received_sim_s
        if row.topic in {"/tf", "/tf_static"}:
            for transform in message.transforms:
                tf_rows.append({"topic": row.topic, "stamp_s": evaluation.stamp_s(transform.header.stamp),
                                "received_s": receive, "parent": transform.header.frame_id,
                                "child": transform.child_frame_id,
                                "translation": evaluation.vector(transform.transform.translation),
                                "rotation_xyzw": [getattr(transform.transform.rotation, axis) for axis in "xyzw"]})
        if row.topic == "/tracking/state":
            operational = max(row.time_s, receive) if receive is not None else row.time_s
            if start <= operational <= end:
                rejected = int(message.rejected_measurements)
                if message.state != last_state or message.state == 1 or rejected != last_rejected:
                    states.append({"acquisition_or_output_s": row.time_s, "received_s": receive,
                                   "state": int(message.state), "track_id": int(message.track_id),
                                   "prediction_age_s": float(message.prediction_age_s), "rejected": rejected,
                                   "position_map": evaluation.vector(message.position_m),
                                   "velocity_map": evaluation.vector(message.velocity_mps)})
                last_state, last_rejected = message.state, rejected
        elif row.topic == "/tracking/observations" and start <= row.time_s <= end:
            observations.append({"acquired_s": row.time_s, "received_s": receive,
                                 "receive_lag_s": receive - row.time_s if receive is not None else None,
                                 "depth_valid": bool(message.depth_valid), "depth_m": float(message.depth_m),
                                 "depth_std_m": float(message.depth_std_m), "valid_ratio": float(message.depth_valid_ratio),
                                 "confidence": float(message.confidence),
                                 "position_camera": evaluation.vector(message.position_camera_m),
                                 "bbox": [float(message.bbox_x_min_px), float(message.bbox_y_min_px),
                                          float(message.bbox_x_max_px), float(message.bbox_y_max_px)]})
        elif row.topic == "/tracking/detection_diagnostics":
            payload = json.loads(message.data)
            if start <= payload["stamp_s"] <= end:
                diagnostics.append({**payload, "received_s": receive})
    base_tf = sorted([row for row in tf_rows if row["child"] == "base_link"], key=lambda row: row["stamp_s"])
    base_times = [row["stamp_s"] for row in base_tf]
    for observation in observations:
        index = bisect_left(base_times, observation["acquired_s"])
        observation["tf_source_bracket_s"] = base_times[max(index - 1, 0):index + 1]
        delivered = [row for row in base_tf if row["received_s"] is not None
                     and observation["received_s"] is not None and row["received_s"] <= observation["received_s"]]
        observation["latest_tf_stamp_at_recorded_observation_receive_s"] = delivered[-1]["stamp_s"] if delivered else None
    report = {"follow_start_s": follow, "window": [start, end], "inputs": metadata,
              "topic_counts": dict(Counter(row.topic for row in records)), "states": states,
              "observations": observations, "diagnostics": diagnostics,
              "tf_summary": {"frames": dict(Counter(row["parent"] + "->" + row["child"] for row in tf_rows)),
                             "static": [row for row in tf_rows if row["topic"] == "/tf_static"],
                             "max_base_tf_gap_s": max((right - left for left, right in zip(base_times, base_times[1:])), default=None)},
              "notes": ["Message receive time is the latest bag /clock and has clock-sample uncertainty; no wall/sim time substitution.",
                        "TF availability at bag receipt approximates recorder ordering, not the estimator's callback receipt ordering."]}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"report": str(args.output), "follow_start_s": follow,
                      "states": states, "observations": observations, "tf_summary": report["tf_summary"]}, indent=2))


if __name__ == "__main__":
    main()
