"""Conservative candidate-only three-DDS-edge lineage reducer. No ROS import."""
from collections import Counter, defaultdict
from indexed_reduction import EventIndex, OutcomeIndex, read_events
import hashlib
import json
from pathlib import Path
import statistics

from observer import load_probe
from typed_message import valid_snapshot


def _one(rows, label):
    if len(rows) != 1:
        raise ValueError(label)
    return rows[0]


def reduce_events(events, *, probe_path, begin_ns, end_ns, native_complete=True):
    probe = load_probe(probe_path)
    # The proven clock/metadata/graph/window predicate is reused byte-for-byte.
    # Only its PoseStamped-specific complete-field validator is replaced in this
    # private in-memory module by the small tracking message validator.
    probe.valid_pose_stamped_fields = valid_snapshot
    ordered = sorted(events, key=lambda e: (e.get("recorded_monotonic_ns", -1), e.get("event_id", "")))
    events = [{**event, "event_index": index} for index, event in enumerate(ordered)]
    global_reasons = []
    if type(begin_ns) is not int or type(end_ns) is not int or not 0 <= begin_ns < end_ns:
        raise ValueError("invalid actual bench monotonic interval")
    if not native_complete:
        global_reasons.append("native_session_not_cleanly_complete")
    ids = [e.get("event_id") for e in events]
    if None in ids or len(ids) != len(set(ids)):
        global_reasons.append("missing_or_duplicate_event_id")
    starts = [e for e in events if e.get("kind") == "process_start"]
    if {e.get("process") for e in starts} != {"detector", "estimator", "controller", "adapter", "replay", "monitor"}:
        global_reasons.append("missing_process_start")
    if (not starts or None in {e.get("boot_id") for e in starts}
            or len({e.get("boot_id") for e in starts}) != 1):
        global_reasons.append("monotonic_clock_domain_not_bound")
    if len(starts)!=6 or any(e.get("monotonic_clock",{}).get("monotonic") is not True
                            or e.get("monotonic_clock",{}).get("adjustable") is not False for e in starts):
        global_reasons.append("monotonic_clock_properties_or_start_count_invalid")
    if any(e.get("runtime_gate_passed") is not True for e in starts if e.get("process") in {"detector","estimator","controller","adapter"}):
        global_reasons.append("original_c7_runtime_gate_missing")
    for role in ("detector", "estimator", "controller", "adapter"):
        finals = [e for e in events if e.get("process") == role and e.get("kind") == "observer_final"]
        shutdown = [e for e in events if e.get("process") == role and e.get("kind") == "executor_shutdown"]
        if len(finals) != 1 or any(e.get("trace_dropped") != 0 or e.get("trace_errors") != []
                                   or e.get("instrumentation_errors") != [] for e in finals):
            global_reasons.append("missing_or_incomplete_trace:" + role)
        if len(shutdown) != 1 or shutdown[0].get("returned") is not True or shutdown[0].get("exception") is not None:
            global_reasons.append("executor_shutdown_not_true:" + role)
    if any(e.get("kind") in {"hook_error", "trace_failure"} for e in events):
        global_reasons.append("instrumentation_error")
    for role in ("replay","monitor"):
        finals=[e for e in events if e.get("process")==role and e.get("kind")=="process_final"]
        if len(finals)!=1 or finals[0].get("trace_dropped")!=0 or finals[0].get("trace_errors")!=[]:
            global_reasons.append("missing_or_incomplete_trace:"+role)
    scans=[e for e in events if e.get("kind")=="fmu_scan"]
    if (not scans or min(e["recorded_monotonic_ns"] for e in scans)>=begin_ns
            or max(e["recorded_monotonic_ns"] for e in scans)<=end_ns
            or any(e.get("publishers")!=[] for e in scans)):
        global_reasons.append("real_fmu_publisher_scan_missing_or_nonempty")
    by_process = defaultdict(list)
    for event in events:
        if type(event.get("local_index")) is not int:
            global_reasons.append("missing_local_event_counter")
        else:
            by_process[event.get("process")].append(event["local_index"])
    for role, indexes in by_process.items():
        if sorted(indexes) != list(range(1, max(indexes)+1)):
            global_reasons.append("trace_event_gap_or_duplicate:" + str(role))
    inside = lambda e: begin_ns <= e["recorded_monotonic_ns"] <= end_ns
    data = [e for e in events if inside(e)]
    callbacks = defaultdict(list)
    for event in data:
        if event["kind"] == "callback":
            callbacks[event.get("object_token")].append(event)
    lookup = EventIndex(data)
    by_index = {e["event_index"]: e for e in events}
    edge_reports, associations = {}, {}
    for phase in ("detection", "state", "command"):
        graph = [e for e in events if e["kind"] == "graph" and e.get("phase") == phase]
        previous = [e for e in graph if e["recorded_monotonic_ns"] < begin_ns]
        following = [e for e in graph if e["recorded_monotonic_ns"] > end_ns]
        selected = [e for e in data if e.get("phase") == phase and e["kind"] in {"publish", "take", "graph", "controlled_writers"}]
        selected += previous[-1:] + following[:1]
        # Lifecycle observations bracket replay, and name actual owned nodes.
        selected += [e for e in events if e["kind"] == "controlled_writers" and e.get("phase") == phase and not inside(e)]
        result = probe.assess(sorted(selected, key=lambda e:e["recorded_monotonic_ns"]), phase)
        edge_reports[phase] = result
        for pair in result["pairs"]:
            take = by_index[pair["take_event_index"]]
            associations[take["event_id"]] = (pair, by_index[pair["publish_event_indices"][0]]
                                                   if len(pair["publish_event_indices"]) == 1 else None)
    def preceding_publish(callback, phase):
        if (callback.get("phase") != phase or callback.get("same_object_as_original_take") is not True
                or callback.get("complete_typed_fields_match_take") is not True):
            raise ValueError("callback_original_take_object_or_fields_missing:"+phase)
        pair, publication = associations.get(callback.get("take_event_id"), ({}, None))
        if pair.get("status") != "OBSERVED_CANDIDATE" or publication is None:
            raise ValueError("dds_edge_not_candidate:"+phase+":"+",".join(pair.get("reasons", ["missing_take"])))
        if publication["recorded_monotonic_ns"] > callback["entered_ns"]:
            # Synchronous publish may finish after the take/callback has begun;
            # use the actual before anchor for necessary publish causality.
            if publication["before"]["monotonic_before_ns"] > callback["entered_ns"]:
                raise ValueError("publish_begins_after_callback:"+phase)
        return publication
    def only_kind(kind, key, value):
        return _one(lookup.find(kind, key, value), "missing_or_ambiguous_"+kind)
    outcomes = []
    categories = Counter()
    for end in [e for e in data if e["kind"] == "callback" and e.get("phase") == "command"]:
        row = {"adapter_callback_event_id": end["event_id"], "status": "UNKNOWN", "reasons": list(dict.fromkeys(global_reasons)),
               "t0_monotonic_ns": None, "t1_monotonic_ns": end.get("entered_ns"), "latency_ns": None}
        try:
            command = preceding_publish(end, "command")
            mode, valid = command.get("command_mode"), command.get("command_valid")
            category = "FOLLOW" if valid is True and mode in (1, 2) else {0:"HOLD", 3:"SEARCH", 4:"FAILSAFE"}.get(mode, "OTHER")
            categories[category] += 1
            row["command_category"] = category
            if category != "FOLLOW":
                raise ValueError("command_is_not_follow")
            target_callback = _one(callbacks.get(command.get("target_token"), []), "actual_controller_target_callback_missing_or_ambiguous")
            state = preceding_publish(target_callback, "state")
            source_token = state.get("source_frame_token")
            if source_token is None or state.get("project_valid") is not True:
                raise ValueError("navigation_accepted_source_or_valid_project_missing")
            accepted = only_kind("navigation_update", "event_id", state.get("accepted_update_event_id"))
            project = only_kind("navigation_project", "project_token", state.get("project_token"))
            if (accepted.get("accepted") is not True or accepted.get("source_frame_token") != source_token
                    or project.get("source_frame_token") != source_token
                    or project.get("accepted_update_event_id") != accepted["event_id"]):
                raise ValueError("navigation_acceptance_project_lineage_mismatch")
            if lookup.navigation_replaced(accepted, project):
                raise ValueError("navigation_source_replaced_or_cleared_before_project")
            frame_callback = _one(callbacks.get(source_token, []), "accepted_source_frame_callback_missing_or_ambiguous")
            frame = preceding_publish(frame_callback, "detection")
            job = frame.get("snapshot_token")
            if job is None:
                raise ValueError("actual_worker_snapshot_missing")
            selected = only_kind("snapshot", "snapshot_token", job)
            submitted = only_kind("submit", "snapshot_token", job)
            worker = only_kind("worker_start", "snapshot_token", job)
            if submitted.get("accepted") is not True:
                raise ValueError("worker_submission_not_accepted")
            rgb = only_kind("sensor_callback", "image_token", selected.get("rgb_token"))
            depth = only_kind("sensor_callback", "image_token", selected.get("depth_token"))
            if rgb.get("sensor") != "rgb" or depth.get("sensor") != "depth":
                raise ValueError("snapshot_sensor_types_mismatch")
            t0, t1 = max(rgb["entered_ns"], depth["entered_ns"]), end["entered_ns"]
            chain_times = [t0, selected["recorded_monotonic_ns"], worker["recorded_monotonic_ns"],
                           frame["before"]["monotonic_before_ns"], frame_callback["entered_ns"],
                           accepted["recorded_monotonic_ns"], project["recorded_monotonic_ns"],
                           state["before"]["monotonic_before_ns"], target_callback["entered_ns"],
                           command["before"]["monotonic_before_ns"], t1]
            if any(type(v) is not int or v < 0 for v in chain_times) or chain_times != sorted(chain_times):
                raise ValueError("necessary_pipeline_causality_or_clock_fields_invalid")
            row.update(snapshot_token=job, rgb_token=selected["rgb_token"], accepted_update_event_id=accepted["event_id"],
                       t0_monotonic_ns=t0, t1_monotonic_ns=t1)
            if not row["reasons"]:
                row.update(status="CANDIDATE_SOFTWARE_LATENCY", latency_ns=t1-t0)
        except (ValueError, TypeError, KeyError) as error:
            row["reasons"].append(str(error))
            if "command_category" not in row:
                categories["UNCLASSIFIED_MISSING_EDGE"] += 1
        outcomes.append(row)
    outcome_lookup = OutcomeIndex(outcomes)
    opportunities = []
    for rgb in [e for e in data if e["kind"] == "sensor_callback" and e.get("sensor") == "rgb"]:
        selected = lookup.find("snapshot", "rgb_token", rgb["image_token"])
        reached = outcome_lookup.find(rgb["image_token"])
        opportunities.append({"rgb_callback_event_id":rgb["event_id"], "image_token":rgb["image_token"],
                              "selected_snapshot_count":len(selected), "candidate_command_count":len(reached),
                              "first_candidate_latency_ns":min((e["latency_ns"] for e in reached), default=None),
                              "outcome":"CANDIDATE" if reached else "UNKNOWN",
                              "reason":None if reached else "NO_COMPLETE_FOLLOW_CANDIDATE_FOR_THIS_RECEIVED_RGB"})
    values = sorted(e["latency_ns"] for e in outcomes if e["status"] == "CANDIDATE_SOFTWARE_LATENCY")
    def percentile(q):
        return values[min(len(values)-1, int((len(values)-1)*q+0.5))] if values else None
    ledger = Counter(e["kind"] for e in data)
    reasons = Counter(reason for row in outcomes for reason in row["reasons"])
    replay_counts=Counter(e.get("input_kind","UNKNOWN") for e in data if e["kind"]=="replay_input")
    replay_summaries=[e for e in events if e["kind"]=="replay_finished"]
    return {"schema_version":1, "scope":"CONTROLLED_CANDIDATE_SOFTWARE_PIPELINE_ONLY_NOT_PHYSICAL_E2E",
            "status":"CANDIDATE_OBSERVED_IN_THIS_BENCH_ONLY" if values else "NOT_OBSERVED",
            "metric":"bench_rgbd_callback_to_adapter_callback_monotonic_ns", "begin_ns":begin_ns, "end_ns":end_ns,
            "edges":edge_reports, "opportunity_counts":dict(ledger), "command_categories":dict(categories),
            "replayed_input_counts_by_kind":dict(replay_counts), "replay_summaries":replay_summaries,
            "replay_to_sensor_callback_association":"NOT_OBSERVED; input publication counts and received callbacks are separate denominators, without a claimed per-image DDS join",
            "adapter_callback_count":len(outcomes), "candidate_command_count":len(values),
            "unknown_command_count":len(outcomes)-len(values), "unknown_reasons":dict(reasons),
            "received_rgb_count":len(opportunities), "rgb_with_candidate_count":sum(r["outcome"]=="CANDIDATE" for r in opportunities),
            "candidate_subset_statistics_ns":{"median":statistics.median(values) if values else None,
                                              "p95":percentile(.95), "max":max(values, default=None)},
            "commands":outcomes, "rgb_opportunities":opportunities,
            "historical_strict_changed":False, "historical_strict_unknown":"1857/1857_UNCHANGED",
            "physical_e2e":"NOT_OBSERVED", "graph_boundary":"POLLED_EXTERNAL_WRITER_ABSENCE_NOT_PROVEN",
            "claim_boundary":"Every DDS edge is only a controlled candidate. Candidate subset statistics are not whole-pipeline performance; unknowns, non-FOLLOW commands, losses and all received RGB opportunities remain disclosed."}


def reduce_files(paths, **kwargs):
    events, bindings = [], []
    events.extend(read_events(paths, bindings))
    result = reduce_events(events, **kwargs)
    result["trace_bindings"] = bindings
    return result
