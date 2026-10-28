"""Read-only designated-target safety evaluation, independent of task-UUID claims.

This report certifies selection/lifecycle/control evidence only. Physical
identity accuracy requires separately validated GT labels and is explicitly
unavailable here. Run after sourcing ROS and this workspace's messages.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import evaluate_stage1_flight as base


@dataclass(frozen=True)
class Stage2Config:
    target_class: str = "person"
    require_occlusions: bool = True
    require_ambiguity: bool = False
    max_prediction_s: float = .75
    control_grace_s: float = .10
    max_evidence_gap_s: float = .5
    terminal_expectation: str = "tracking"

    def __post_init__(self):
        if self.terminal_expectation not in {"tracking", "hover"}:
            raise ValueError("terminal_expectation must be tracking or hover")


def operational(row):
    # Keep acquisition/output semantics for durations and freshness. Header
    # times can legally regress when timer predictions and image-backed
    # measurements interleave; reader-order receive-clock checks live in base.
    return base.Record(row.topic, max(row.time_s, row.received_sim_s)
                       if row.received_sim_s is not None else row.time_s,
                       row.message, row.received_sim_s, row.record_sequence)


def selection_valid(row, config):
    message = row.message
    received = base.finite(row.received_sim_s)
    stamp = base.stamp_s(message.header.stamp)
    numbers = [base.finite(getattr(message, name, None))
               for name in ("center_u_px", "center_v_px", "width_px", "height_px")]
    return (getattr(message, "action", None) == 0 and bool(str(getattr(message, "target_uuid", "")).strip())
            and str(getattr(message, "class_name", "")) in {"", config.target_class}
            and received is not None and stamp > 0 and -.05 <= received-stamp <= .60
            and all(value is not None for value in numbers) and numbers[2] > 0 and numbers[3] > 0)


def fresh_state(row, config):
    message = row.message
    received = base.finite(row.received_sim_s)
    age = base.finite(getattr(message, "prediction_age_s", None))
    stamp = base.stamp_s(message.header.stamp)
    return (message.state in {1, 2} and received is not None and age is not None and age >= 0
            and stamp <= received+.05 and age+max(0.0, received-stamp) <= config.max_prediction_s
            and str(getattr(message, "class_name", "")) == config.target_class
            and int(getattr(message, "track_id", 0)) > 0)


def _box_iou(first, second):
    ix = max(0, min(first[2], second[2])-max(first[0], second[0]))
    iy = max(0, min(first[3], second[3])-max(first[1], second[1]))
    area = ix*iy
    union = (first[2]-first[0])*(first[3]-first[1])+(second[2]-second[0])*(second[3]-second[1])-area
    return area/union if union > 0 else 0


def terminal_hover(states, statuses, commands, recorded_end, config, expected_uuid):
    """A deliberate ambiguity/loss stop must persist to the untrimmed end.

    A 5.2-second opportunity permits ordinary sample boundaries while each
    recorded stream must itself span at least five seconds. Missing control
    telemetry cannot count as a safe stop.
    """
    start = recorded_end-5.2
    groups = {"states": [row for row in states if start <= row.time_s <= recorded_end],
              "statuses": [row for row in statuses if start <= row.time_s <= recorded_end],
              "commands": [row for row in commands if start <= row.time_s <= recorded_end]}
    spans = {name: rows[-1].time_s-rows[0].time_s if rows else 0. for name,rows in groups.items()}
    gaps = {}
    for name, rows in groups.items():
        times = [start]+[row.time_s for row in rows]+[recorded_end]
        gaps[name] = max(second-first for first,second in zip(times,times[1:]))
    checks = {
        "all_streams_span_at_least_five_seconds": all(span >= 5.-1e-9 for span in spans.values()),
        "all_streams_cover_tail_without_gaps": all(gap <= config.max_evidence_gap_s for gap in gaps.values()),
        "states_remain_ambiguous_or_lost": bool(groups["states"]) and all(row.message.state in {3,4} for row in groups["states"]),
        "same_explicit_task_retained": bool(expected_uuid and groups["states"]) and all(
            row.message.target_uuid == expected_uuid for row in groups["states"]),
        "controller_remains_hover": bool(groups["statuses"]) and all(row.message.lifecycle == 4 for row in groups["statuses"]),
        "all_motion_commands_invalid": bool(groups["commands"]) and all(not row.message.valid for row in groups["commands"]),
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "start_s":start, "end_s":recorded_end,
            "scope":"Final ambiguity/loss stop; full recorded end retained", "checks":checks,
            "sample_counts":{name:len(rows) for name,rows in groups.items()},
            "spans_s":spans,"maximum_evidence_gaps_s":gaps,"expected_target_uuid":expected_uuid}


def evaluate(records, events, config=Stage2Config(), input_metadata=None):
    if not records:
        raise ValueError("No readable records")
    # Establish original reader/input order before sorting by operational time.
    # A timestamp alone cannot distinguish a pre-confirmation LOST from a
    # post-confirmation fault in the same simulation-clock tick.
    records = base.with_record_sequence(records)
    metadata = input_metadata or {}
    recorded_end = max(operational(row).time_s for row in records)
    order = lambda row: (row.time_s, row.record_sequence)
    states = sorted([operational(row) for row in records if row.topic == "/tracking/state"], key=order)
    statuses = sorted([operational(row) for row in records if row.topic == "/tracking/status"], key=order)
    commands = sorted([operational(row) for row in records if row.topic == "/tracking/command"], key=order)
    selections = sorted([operational(row) for row in records if row.topic == "/tracking/selection"], key=order)
    valid_selections = [row for row in selections if selection_valid(row, config)]
    selection_rows = []
    for request in valid_selections:
        uuid = request.message.target_uuid
        # The first return is a reader-order boundary. An active state recorded
        # after the request but timestamped before it must reject that request,
        # not disappear behind a time-window filter.
        first_entry = min(((index, row) for index, row in enumerate(states)
                           if row.record_sequence > request.record_sequence and row.message.state in {1, 2}),
                          key=lambda entry: entry[1].record_sequence, default=None)
        first_index, first = first_entry if first_entry is not None else (None, None)
        confirmed = bool(first is not None and first.message.state == 1 and fresh_state(first, config)
                         and request.time_s <= first.time_s <= request.time_s+3
                         and first.message.target_uuid == uuid)
        selection_rows.append({"request_s": request.time_s, "target_uuid": uuid, "confirmed": confirmed,
                               "request_record_sequence": request.record_sequence,
                               "first_active_s": first.time_s if first is not None else None,
                               "first_active_record_sequence": first.record_sequence if first is not None else None,
                               "confirmation_s": first.time_s if confirmed else None,
                               "confirmation_record_sequence": first.record_sequence if confirmed else None,
                               "confirmation_state_index": first_index if confirmed else None,
                               "image_stamp_s": base.stamp_s(first.message.header.stamp) if confirmed else None,
                               "track_id": int(first.message.track_id) if confirmed else None})
    initial = selection_rows[0] if selection_rows else None
    tracks, track_errors = [], []
    for row in records:
        if row.topic != "/tracking/tracks":
            continue
        try:
            payload = json.loads(row.message.data)
            if (payload.get("schema_version") != 1 or not isinstance(payload["tracks"], list)
                    or type(payload["projected"]) is not bool):
                raise ValueError("unsupported or incomplete snapshot schema")
            acquired, output = base.finite(payload["acquisition_s"]), base.finite(payload["output_s"])
            if acquired is None or output is None or acquired > output+1e-9:
                raise ValueError("invalid snapshot acquisition/output timestamps")
            if row.received_sim_s is None or output > row.received_sim_s+.05:
                raise ValueError("snapshot has no valid receive time")
            ids = [item["track_id"] for item in payload["tracks"]]
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate track ID within snapshot")
            for item in payload["tracks"]:
                if type(item["track_id"]) is not int or item["track_id"] <= 0:
                    raise ValueError("invalid track ID")
                box = item["bbox_xyxy"]
                if len(box) != 4 or any(base.finite(value) is None for value in box) or box[0] > box[2] or box[1] > box[3]:
                    raise ValueError("invalid track box")
                if type(item["matched"]) is not bool or type(item["depth_valid"]) is not bool:
                    raise ValueError("freshness flags must be booleans")
                if payload["projected"] and item["matched"]:
                    raise ValueError("projected snapshot cannot claim a fresh detection")
            tracks.append({"time_s": operational(row).time_s, "payload": payload})
        except (KeyError, TypeError, ValueError) as exc:
            track_errors.append({"time_s": operational(row).time_s, "reason": str(exc)})
    initial_link = None
    if initial is not None and initial["confirmed"]:
        selection = valid_selections[0].message
        box = [selection.center_u_px-selection.width_px/2, selection.center_v_px-selection.height_px/2,
               selection.center_u_px+selection.width_px/2, selection.center_v_px+selection.height_px/2]
        associated = [item for row in tracks if not row["payload"]["projected"]
                      and abs(row["payload"]["acquisition_s"]-initial["image_stamp_s"]) < 1e-6
                      and row["payload"]["target_uuid"] == initial["target_uuid"]
                      for item in row["payload"]["tracks"] if item["track_id"] == initial["track_id"] and item["matched"]]
        initial_link = any(_box_iou(box, item["bbox_xyxy"]) > .05 for item in associated)
    multiple = [row for row in tracks if not row["payload"]["projected"]
                and sum(item["matched"] and item["class_name"] == config.target_class
                        for item in row["payload"]["tracks"]) >= 2]
    uuid_changes, unauthorized = [], []
    previous_uuid, previous_change = "", -math.inf
    for row in states:
        uuid = str(getattr(row.message, "target_uuid", ""))
        if not uuid or uuid == previous_uuid:
            continue
        authorizers = [request for request in valid_selections
                       if previous_change < request.time_s <= row.time_s+.05 and request.message.target_uuid == uuid]
        uuid_changes.append({"time_s": row.time_s, "old_uuid": previous_uuid, "new_uuid": uuid,
                             "explicit_selection": bool(authorizers)})
        if not authorizers:
            unauthorized.append(uuid_changes[-1])
        previous_uuid, previous_change = uuid, row.time_s
    ambiguity_windows = []
    opened = None
    for row in states:
        ambiguous = row.message.state == 4 and bool(getattr(row.message, "target_uuid", ""))
        if ambiguous and opened is None:
            opened = row.time_s
        elif not ambiguous and opened is not None:
            ambiguity_windows.append((opened, row.time_s)); opened = None
    if opened is not None:
        ambiguity_windows.append((opened, recorded_end))
    ambiguity_results = []
    for start, end in ambiguity_windows:
        controls = [row for row in statuses if start+config.control_grace_s <= row.time_s < end]
        sent = [row for row in commands if start+config.control_grace_s <= row.time_s < end]
        enough_duration = end-start > config.control_grace_s
        suspended = (bool(controls and sent) and all(row.message.lifecycle == 4 for row in controls)
                     and all(not row.message.valid for row in sent)) if enough_duration else None
        if suspended:
            for group in (controls, sent):
                times = [start+config.control_grace_s]+[row.time_s for row in group]+[end]
                suspended = suspended and max(b-a for a,b in zip(times,times[1:])) <= config.max_evidence_gap_s
        ambiguity_results.append({"start_s": start, "end_s": end, "duration_s": end-start,
                                  "controller_hover_and_invalid_motion_commands": suspended,
                                  "control_samples": len(controls), "command_samples": len(sent)})
    geometric_ambiguity = any(row["payload"].get("target_status") == "ambiguous"
                             and row["payload"].get("target_track_id") in row["payload"].get("ambiguous_track_ids", [])
                             and bool(row["payload"].get("target_uuid")) for row in tracks)
    lost_start, unauthorized_recoveries, loss_latches = None, [], []
    for row in states:
        if row.message.state == 3 and lost_start is None:
            lost_start = row.time_s
        if lost_start is not None and row.message.state in {1, 2}:
            request = next((request for request in valid_selections
                            if lost_start <= request.time_s <= row.time_s+.05), None)
            if request is None:
                unauthorized_recoveries.append(row.time_s)
            else:
                loss_latches.append((lost_start, request.time_s))
                lost_start = None
    if lost_start is not None:
        loss_latches.append((lost_start, recorded_end))
    unauthorized_loss_controls = [row.time_s for start,end in loss_latches for row in statuses
                                  if start+config.control_grace_s <= row.time_s < end
                                  and row.message.lifecycle in {2, 3}]
    last_confirmed = next((row for row in reversed(selection_rows) if row["confirmed"]), None)
    tail = None
    if last_confirmed and config.terminal_expectation == "tracking":
        # Reselection must remain active through the *entire* remainder. A
        # no-reselection trial instead certifies an explicitly labelled tail;
        # earlier legitimate short ambiguity/occlusion is evaluated separately.
        start = last_confirmed["confirmation_s"]
        boundary_sequence = last_confirmed["confirmation_record_sequence"]
        boundary_index = last_confirmed["confirmation_state_index"]
        tail_window_start = None
        if len(selection_rows) == 1:
            tail_window_start = max(start, recorded_end-5.2)
            # This is a separately labelled terminal window, not a new task
            # confirmation. Anchor the first *recorded* state in the window,
            # regardless of state or UUID. Operational-time sorting can put
            # a later good record ahead of an earlier bad record when time
            # regresses; that must never move the reader-order boundary.
            anchor = min(((index, row) for index, row in enumerate(states)
                          if tail_window_start <= row.time_s <= recorded_end),
                         key=lambda entry: entry[1].record_sequence, default=None)
            if anchor is None:
                start, boundary_sequence, boundary_index = tail_window_start, None, None
            else:
                boundary_index, boundary = anchor
                start, boundary_sequence = boundary.time_s, boundary.record_sequence
        tail = base.post_reselection_tracking(states, statuses, {
            "confirmed": True, "confirmed_target_uuid": last_confirmed["target_uuid"],
            "confirmation_time_s": start,
            "confirmation_record_sequence": boundary_sequence,
            "confirmation_state_index": boundary_index,
        }, recorded_end, base.EvaluationConfig(target_class=config.target_class, max_prediction_s=config.max_prediction_s))
        tail["scope"] = "Full remainder after last explicit reselection" if len(selection_rows) > 1 else "Final sustained tracking tail"
        tail["selection_confirmation_time_s"] = last_confirmed["confirmation_s"]
        tail["selection_confirmation_record_sequence"] = last_confirmed["confirmation_record_sequence"]
        tail["tail_window_start_s"] = tail_window_start
    hover = terminal_hover(states, statuses, commands, recorded_end, config,
                           last_confirmed["target_uuid"] if last_confirmed else None) if config.terminal_expectation == "hover" else None
    diagnostics = []
    diagnostic_errors = []
    for row in records:
        if row.topic == "/tracking/detection_diagnostics":
            try:
                payload = json.loads(row.message.data)
                diagnostics.append({**payload, "has_candidate": bool(payload["detections"]),
                                    "valid_depth": any(item.get("depth_valid") for item in payload["detections"])})
            except (KeyError, TypeError, ValueError) as exc:
                diagnostic_errors.append(str(exc))
    occlusion_results = []
    for window in base.shutter_windows(events):
        occlusion_results.append(base.evaluate_occlusion(
            window, states, statuses,
            [operational(row) for row in records if row.topic == "/vehicle/odometry"], diagnostics,
            base.EvaluationConfig(target_class=config.target_class, max_prediction_s=config.max_prediction_s),
            recorded_end, selections, [event for event in events if event.get("kind") == "shutter_service_result"],
        ))
    vehicle_status = [row.message for row in records if row.topic in {"/fmu/out/vehicle_status_v1", "/fmu/out/vehicle_status"}]
    initial_request_order = order(valid_selections[0]) if initial else (math.inf, math.inf)
    early_active = [row.time_s for row in states if order(row) < initial_request_order and row.message.state in {1, 2}]
    early_controls = [row.time_s for row in statuses if order(row) < initial_request_order and row.message.lifecycle in {2, 3}]
    active_invalid = [row.time_s for row in states if row.message.state in {1, 2} and not fresh_state(row, config)]
    required_occlusions_present = (any(row["kind"] == "short" for row in occlusion_results)
                                  and any(row["kind"] == "long" for row in occlusion_results))
    checks = {
        "clock_recorded": metadata.get("clock_recorded") is True and metadata.get("clock_samples_read", 0) > 0,
        "input_decodes_without_errors": not metadata.get("read_errors") and not metadata.get("unavailable_types"),
        "armed_and_offboard_observed": (any(row.arming_state == 2 for row in vehicle_status)
                                       and any(row.nav_state == 14 for row in vehicle_status)) if vehicle_status else None,
        "initial_explicit_box_confirmed_fresh": initial["confirmed"] if initial else None,
        "initial_box_matches_selected_track_snapshot": initial_link,
        "no_tracking_before_initial_selection": not early_active and not early_controls,
        "multiple_same_class_fresh_tracks_observed": bool(multiple),
        "all_tracks_snapshots_present_and_valid": bool(tracks) and not track_errors,
        "task_uuid_changes_require_explicit_selection": not unauthorized if states else None,
        "long_loss_cannot_reactivate_without_explicit_selection": not unauthorized_recoveries,
        "long_loss_cannot_control_before_explicit_selection": not unauthorized_loss_controls,
        "active_states_remain_fresh": not active_invalid if states else None,
        "selected_geometric_ambiguity_observed_if_required": geometric_ambiguity if config.require_ambiguity or config.terminal_expectation == "hover" else True,
        "observed_ambiguities_suspend_control": all(row["controller_hover_and_invalid_motion_commands"] is True
                                                   for row in ambiguity_results if row["duration_s"] > config.control_grace_s),
        "required_short_and_long_occlusions_present": required_occlusions_present if config.require_occlusions else True,
        "recorded_occlusions_pass": all(row["result"] == "PASS" for row in occlusion_results) if occlusion_results else (None if config.require_occlusions else True),
        "detection_diagnostics_valid": not diagnostic_errors if diagnostics else None,
    }
    if config.terminal_expectation == "tracking":
        checks["final_sustained_tracking"] = tail["result"] == "PASS" if tail else None
    else:
        # Hover is an explicit ambiguity-scenario contract, never a way to
        # reinterpret an ordinary tracking failure as a successful follow.
        checks["terminal_hover_follows_selected_ambiguity"] = geometric_ambiguity and bool(ambiguity_results)
        checks["final_sustained_hover"] = hover["result"] == "PASS"
    outcome = "FAIL" if any(value is False for value in checks.values()) else (
        "INCOMPLETE_EVIDENCE" if any(value is None for value in checks.values()) else "PASS")
    return {"schema_version": 1, "evaluation_revision": base.EVALUATION_REVISION,
            "source": "OFFLINE_STAGE2_SAFETY_EVALUATION", "result": outcome,
            "scope": "Observed designated-target selection, state freshness, ambiguity suspension and loss/reselection control only",
            "configuration": config.__dict__, "inputs": metadata,
            "interval": {"recorded_end_s": recorded_end, "covers_recorded_trial_end": True}, "checks": checks,
            "selections": selection_rows, "uuid_changes": uuid_changes, "unauthorized_uuid_changes": unauthorized,
            "fresh_multi_track_acquisitions": len(multiple), "tracks_snapshot_count": len(tracks),
            "tracks_snapshot_errors": track_errors, "invalid_active_state_times_s": active_invalid,
            "unauthorized_recovery_times_s": unauthorized_recoveries,
            "unauthorized_control_after_loss_times_s": unauthorized_loss_controls,
            "ambiguity_windows": ambiguity_results, "geometric_ambiguity_observed": geometric_ambiguity,
            "sustained_tracking": tail, "terminal_hover": hover, "occlusions": occlusion_results,
            "physical_identity": {"evaluated": False, "reason": "Requires independently validated visible GT/image labels; unchanged task UUID is not evidence of physical identity"},
            "limitations": ["No GT identity, IDF1, HOTA, mAP or three-dimensional accuracy is certified by this safety report.",
                            "PASS is limited to the requested scenario coverage flags; full stage two requires both classes and separate crossing/ambiguity evidence."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--telemetry-jsonl", type=Path)
    parser.add_argument("--monitor-summary", type=Path)
    parser.add_argument("--target-class", choices=["person", "car"], default="person")
    parser.add_argument("--require-occlusions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-ambiguity", action="store_true")
    parser.add_argument("--terminal-expectation", choices=["tracking", "hover"], default="tracking",
                        help="hover is only for an explicit ambiguity/loss-stop scenario; requires selected ambiguity and >=5s terminal stop")
    args = parser.parse_args()
    base.TOPICS = tuple(dict.fromkeys(base.TOPICS+("/tracking/tracks",)))
    records, metadata = base.read_rosbag(args.bag)
    events, monitor = base.read_monitor_events(args.telemetry_jsonl, args.monitor_summary)
    metadata.update(telemetry_jsonl=str(args.telemetry_jsonl) if args.telemetry_jsonl else None,
                    monitor_summary=str(args.monitor_summary) if args.monitor_summary else None)
    report = evaluate(records, events, Stage2Config(args.target_class, args.require_occlusions, args.require_ambiguity,
                                                   terminal_expectation=args.terminal_expectation), metadata)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "checks": report["checks"], "report": str(args.output)}, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
