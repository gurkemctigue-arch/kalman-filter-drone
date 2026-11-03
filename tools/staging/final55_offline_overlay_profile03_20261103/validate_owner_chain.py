"""Prepare read-only qualification of preserved attempts across closed owners.

No production chain or future frontier is instantiated. Default CLI is disabled.
Original source, native, recording, long-loss safety and unknown-value rules
come from the exact independently reviewed slot validator below.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import types


HERE = Path(__file__).resolve().parent
SLOT_LIBRARY_SHA256 = "b3c086db30afe243bfdac423c0302c0285ebd64c8d7e8cb24b388e40fd81d744"
PRODUCTION_ENABLED = False
PRODUCTION_PROFILE = {}
ORIGINAL_CHAIN_SHA256 = "9cbbfbbfccccac9096a5cc122a21d8578e0fcbb3148357602dcdb834b143d97a"
METADATA_STOP_ERROR = "ValueError: New unknown behavior evidence; root must inspect: short:detector_interruption_observed"
STABLE_CHAIN_FIELDS = ("status", "plan", "after_slot", "closed_ids", "pending_ids", "closed", "input_bindings")


def reviewed_slot_source():
    path = HERE / "validate_owner_closure.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == SLOT_LIBRARY_SHA256,
            "Reviewed slot validator source differs after import")
    reference = path.as_posix()
    if reference.startswith("/mnt/"):
        reference = v.windows_mounted_reference(reference)
    return {"path": reference, "sha256": SLOT_LIBRARY_SHA256}


def stable_chain(result):
    return {name: result[name] for name in STABLE_CHAIN_FIELDS}


def load_slot_library():
    path = HERE / "validate_owner_closure.py"
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SLOT_LIBRARY_SHA256:
        raise ValueError("Reviewed slot validator source differs")
    module = types.ModuleType("fixed_owner_chain_slot_library")
    module.__file__ = str(path)
    exec(compile(payload, str(path), "exec"), module.__dict__)
    return module


v = load_slot_library()
require = v.require


def stable_row(row):
    return {"id": row["slot_id"], "original_status": row["original_status"],
            "marker": row["original_marker"], "terminal": row["original_terminal"],
            "record_sha256": row["record_sha256"], "started_utc": row["original_started_utc"],
            "finished_utc": row["original_finished_utc"]}


def stable_proof(proof):
    return {key: proof[key] for key in ("id", "original_status", "marker", "terminal", "record_sha256", "started_utc", "finished_utc")}


def check_same_proof(actual, expected):
    for field in ("id", "original_status", "record_sha256", "started_utc", "finished_utc"):
        require(actual[field] == expected[field], "Preserved prefix identity changed: " + field)
    for field in ("marker", "terminal"):
        require(v.same_path(actual[field]["path"], expected[field]["path"])
                and actual[field]["sha256"] == expected[field]["sha256"], "Preserved original raw binding changed")


def canonical_result_reference(plan, reference):
    alias = plan["frozen_root"] + "/results/"
    return v.join(plan["results_root"], reference[len(alias):]) if reference.startswith(alias) else reference


def check_capture_binding(plan, trial, row, captures):
    # 05 adds this independent field when rechecking a prefix recorded by 04.
    # The stable original identity is compared separately; dictionaries need
    # not be byte-for-byte equal across these different audit implementations.
    if "capture_binding" not in row:
        return
    capture = row["capture_binding"]
    model = trial["model"]
    require(set(capture) == {"target_class", "model", "model_sha256", "capture_sha256", "entries", "path"}
            and capture["target_class"] == trial["target_class"] and capture["model"] == model
            and capture["model_sha256"] == plan["model_hashes"][model]
            and capture["capture_sha256"] == captures[model]["sha256"]
            and type(capture["entries"]) is int and capture["entries"] == 204
            and v.same_path(capture["path"], canonical_result_reference(plan, v.join(trial["directory"], "configuration/source_sha256.json"))),
            "New prefix capture audit contradicts the original per-model contract")


def audit_row(inputs, plan, trial, row, captures, now, segment_id, qualification, *, owner_started=None, metadata_review=None):
    reviewed_unknown = None if metadata_review is None else {
        "root_review": metadata_review, "exception": inputs.json(metadata_review)["historical_unknown"]}
    slot = v.validate_slot(inputs, plan, trial, row, captures, now, owner_started_utc=owner_started,
                           verify_unchanged=False, reviewed_unknown=reviewed_unknown)
    check_capture_binding(plan, trial, row, captures)
    return {**slot, "record_sha256": row["record_sha256"], "executed_by_segment": segment_id, "qualification": qualification}


def source_reference(path):
    reference = path.resolve().as_posix()
    return v.windows_mounted_reference(reference) if reference.startswith("/mnt/") else reference


def prior_validator(inputs, binding):
    """Execute exactly the validator that admitted this original segment."""
    original = HERE.parent / "final55_offline_overlay_profile02_20261103/validate_owner_chain.py"
    current = Path(__file__).resolve()
    allowed = {ORIGINAL_CHAIN_SHA256: source_reference(original), v.sha(current.read_bytes()): source_reference(current)}
    require(binding["sha256"] in allowed and v.same_path(binding["path"], allowed[binding["sha256"]]),
            "Segment used an unreviewed or relocated prefix validator")
    raw = inputs.bound(binding)
    module = types.ModuleType("pinned_segment_prior_validator")
    module.__file__ = str(v.local_path(binding["path"]))
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


def proof_metadata_review(shared, proof):
    original = shared["segments_by_id"][proof["executed_by_segment"]]
    return original["stop_evidence"]["root_review"] if original["disposition"] == "ROOT_REVIEWED_METADATA_STOP" else None


def launch(inputs, shared, segment, prefix, now, prior_profile, prior_result):
    plan, plan_binding = shared["plan"], shared["plan_binding"]
    sources = segment["source_files"]
    registered = bool(prefix)
    expected_sources = v.SOURCE_NAMES | ({"gate", "chain_validator", "registered_profile"} if registered else set())
    require(set(sources) == expected_sources and sources["plan"] == plan_binding, "Segment source/plan binding differs")
    for binding in sources.values():
        inputs.bound(binding)
    require(inputs.json(sources["plan"]) == plan, "Segment uses another plan")
    files = segment["launch_files"]
    expected_files = {"started", "first_monitor", "first_native"} | ({"registered_admission"} if registered else set())
    require(set(files) == expected_files, "Actual early launch evidence is missing")
    started, first_monitor, first_native = (inputs.json(files[key]) for key in ("started", "first_monitor", "first_native"))
    fields = (*v.DESCRIPTION_FIELDS, *(("registered_admission_unc",) if registered else ()))
    desc = {key: started[key] for key in fields}
    require(desc == segment["description"] and desc["pins"] == {key: value for key, value in sources.items() if key != "launcher"}
            and started.get("launcher_source") == sources["launcher"], "Segment invocation/source changed")
    after_slot = prefix[-1]["id"] if prefix else "__before_first__"
    require(segment["after_slot"] == after_slot and desc["automatic_retry"] is False
            and desc["global_power_policy_changed"] is False and desc["power_flags"] == 0x80000003,
            "Continuation does not use the exact preceding closed prefix")
    if registered:
        require(desc["scope"] == "WINDOWS_OWNER_OF_REGISTERED_PRESERVED_PREFIX_CONTINUATION"
                and v.same_path(desc["registered_admission_unc"], desc["owner_unc"] + ".admission.json"),
                "Registered continuation admission location differs")
        expected = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", v.mounted(sources["gate"]["path"]),
                    "--profile", v.mounted(sources["registered_profile"]["path"]), "--output", desc["native_owner"], "--execute"]
    else:
        expected = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", v.mounted(sources["collector"]["path"]),
                    "--plan", segment["native_plan_alias"], "--entry", v.mounted(sources["entry"]["path"]), "--after-slot", after_slot,
                    "--output", desc["native_owner"], "--execute"]
    require(desc["native_command"] == expected and desc["canonical_native_plan"] == v.mounted(sources["plan"]["path"])
            and desc["sources"] == {"events": v.join(desc["owner_unc"], "events.jsonl"),
                                    "ledger": v.join(desc["owner_unc"], "state.json"), "plan": sources["plan"]["path"]},
            "Segment native argv/canonical plan/monitor sources differ")
    require(started.get("status") == "STARTING" and started.get("errors") == [], "Segment launch is faulted")
    launch_time = v.timestamp(started["started_utc"], now)
    handle_time = v.timestamp(started["monitor_handle_acquired_utc"], now)
    require(v.windows_identity(started["launcher_identity"], now) <= launch_time
            <= v.windows_identity(started["monitor_identity"], now) <= handle_time, "Segment creation/handle chronology differs")
    lease = started["power_lease"]
    v.integer(lease.get("request_return"), "Power request result")
    require(lease.get("monitor_identity") == started["monitor_identity"] and lease.get("flags") == desc["power_flags"]
            and lease.get("global_power_policy_changed") is False and handle_time <= v.timestamp(lease.get("accepted_utc"), now),
            "Segment power lease is not bound")
    first_task = v.task_identity(first_monitor, desc, started["monitor_identity"], first_monitor["task"]["process"], now, finished=False)
    require(handle_time <= v.timestamp(first_task["started_utc"], now) <= v.timestamp(first_native["started_utc"], now), "Segment start chronology differs")
    v.linux_identity(first_native["owner_identity"])
    require(first_native.get("owner_pid") == first_native["owner_identity"]["pid"] and first_native.get("status") == "RUNNING"
            and first_native.get("collected") == [] and first_native.get("automatic_retry") is False
            and first_native.get("plan") == desc["canonical_native_plan"] and first_native.get("plan_sha256") == plan["plan_sha256"]
            and first_native.get("plan_file_sha256") == plan_binding["sha256"] and first_native.get("entry_sha256") == sources["entry"]["sha256"]
            and first_native.get("owner_source") == {"path": v.mounted(sources["collector"]["path"]), "sha256": sources["collector"]["sha256"]},
            "Segment early native source/identity/plan is not bound")
    initial = first_native["initial_closed"]
    require([row["slot_id"] for row in initial] == [proof["id"] for proof in prefix], "Early continuation prefix differs")
    for row, old, trial in zip(initial, prefix, plan["trials"]):
        check_same_proof(stable_row(row), stable_proof(old))
        checked = audit_row(inputs, plan, trial, row, shared["captures"], now, old["executed_by_segment"], old["qualification"],
                            metadata_review=proof_metadata_review(shared, old))
        check_same_proof(stable_proof(checked), stable_proof(old))
    admission = None
    if registered:
        registered_profile = inputs.json(sources["registered_profile"])
        require(registered_profile == prior_profile, "Registered gate profile does not describe exactly the preceding closed segments")
        validator = prior_validator(inputs, sources["chain_validator"])
        admitted = validator.validate_continuation_profile(registered_profile, inputs.read, now=now)
        require(admitted["plan"] == prior_result["plan"] and admitted["closed_ids"] == prior_result["closed_ids"]
                and admitted["pending_ids"] == prior_result["pending_ids"] and admitted["after_slot"] == after_slot,
                "Original pinned validator admitted another prefix")
        require([stable_proof(row) for row in admitted["closed"]] == [stable_proof(row) for row in prefix],
                "Original pinned validator did not bind the same original prefix evidence")
        for binding in admitted["input_bindings"]:
            inputs.bound(binding)
        admission = inputs.json(files["registered_admission"])
        history = {proof["id"]: proof["terminal"]["sha256"] for proof in prefix if proof_metadata_review(shared, proof) is not None}
        admission_scope = "REGISTERED_PREFIX_ADMISSION_BEFORE_NEW_OWNER06_CHILDREN" if history else "REGISTERED_PREFIX_ADMISSION_BEFORE_NEW_OWNER05_CHILDREN"
        require(v.same_path(files["registered_admission"]["path"], desc["native_owner"] + ".admission.json")
                and admission.get("scope") == admission_scope
                and admission.get("owner_identity") == first_native["owner_identity"]
                and admission.get("plan") == prior_result["plan"]
                and admission.get("after_slot") == after_slot and admission.get("closed_ids") == prior_result["closed_ids"]
                and admission.get("pending_ids") == prior_result["pending_ids"]
                and admission.get("chain_admission") == stable_chain(admitted)
                and admission.get("unknown_evidence_exceptions") == history and admission.get("automatic_retry") is False,
                "Registered gate early admission does not bind the actual preserved chain")
        for key, field in (("gate", "gate_source"), ("registered_profile", "profile"), ("chain_validator", "chain_validator"), ("collector", "collector")):
            require(admission.get(field) == {"path": v.mounted(sources[key]["path"]), "sha256": sources[key]["sha256"]},
                    "Registered gate admission source differs: " + key)
        require(v.timestamp(first_task["started_utc"], now) <= v.timestamp(admission["utc"], now)
                <= v.timestamp(first_native["started_utc"], now), "Gate admission was not recorded before new collection")
    return {"started": started, "first_monitor": first_monitor, "first_native": first_native,
            "description": desc, "launch_time": launch_time, "registered": registered, "admission": admission}


def envelope(inputs, segment, start, now, *, stopped):
    files = segment["closure_files"]
    require(set(files) == {"outer_terminal", "native_terminal", "monitor_final", "monitor_end", "events"}
            | ({"registered_entry_terminal"} if start["registered"] else set()), "Actual segment closure files missing")
    outer, native, final_monitor, end = (inputs.json(files[key]) for key in ("outer_terminal", "native_terminal", "monitor_final", "monitor_end"))
    started, first_monitor, first_native, desc = (start[key] for key in ("started", "first_monitor", "first_native", "description"))
    code = 2 if stopped else 0
    require(outer.get("status") == ("STOPPED_FAULT" if stopped else "COLLECTION_ENDED")
            and outer.get("native_collection_status") == native.get("status") == ("STOPPED_FAULT" if stopped else "COLLECTION_FINISHED")
            and outer.get("closure_verified") is True and outer.get("errors") == [], "Segment has no verified actual process closure")
    for key in desc:
        require(outer.get(key) == desc[key], "Final segment invocation changed")
    for key in ("started_utc", "launcher_source", "launcher_identity", "monitor_identity", "monitor_handle_acquired_utc"):
        require(outer.get(key) == started[key], "Segment identity changed after start")
    for key in ("monitor_exit_code", "wsl_exit_code", "monitor_popen_wait_exit_code", "monitor_final_popen_wait_exit_code",
                "monitor_final_handle_exit_code", "wsl_final_handle_exit_code"):
        require(type(outer.get(key)) is int and outer[key] == code, "Held-handle/Popen actual segment exits differ")
    artifacts = outer["artifacts"]
    require(set(artifacts) == v.ARTIFACT_NAMES | ({"first_registered_admission.json", "registered_entry_terminal.json"} if start["registered"] else set()),
            "Raw segment artifact set differs")
    copies = {}
    for name, expected_sha in artifacts.items():
        raw = inputs.bound({"path": v.join(desc["receipt_output"], name), "sha256": expected_sha})
        if name.endswith(".json"):
            copies[name] = v.parse(raw)
    require(copies["started.json"] == started and copies["first_monitor_state.json"] == first_monitor
            and copies["first_native_state.json"] == first_native and copies["native_terminal.json"] == native
            and copies["final_monitor_state.json"] == final_monitor, "Segment original/raw copy differs")
    require(files["native_terminal"]["sha256"] == artifacts["native_terminal.json"] == outer["native_owner_terminal_sha256"]
            and files["monitor_final"]["sha256"] == artifacts["final_monitor_state.json"], "Segment original/raw copy digest differs")
    require(outer.get("wsl_identity") == first_monitor["task"]["process"], "Owned WSL identity changed")
    # Generic task_identity requires exit0; preserve and check real exit2 here
    # without rewriting any source document or passing a modified copy to it.
    task = final_monitor["task"]
    require(final_monitor.get("monitor_process") == started["monitor_identity"] and final_monitor.get("sources") == desc["sources"]
            and final_monitor.get("tasks") == [task] and type(task.get("returncode")) is int and task["returncode"] == code
            and {key: value for key, value in task.items() if key not in {"returncode", "finished_utc"}}
            == {key: value for key, value in first_monitor["task"].items() if key not in {"returncode", "finished_utc"}},
            "Final generic monitor identity/task/exit differs")
    require(end.get("task") == task and end.get("tasks") == [task] and end.get("evidence_sources") == desc["sources"]
            and end.get("status") == ("STOPPED_FAULT" if stopped else "COMPLETED")
            and end.get("completion_scope") == "monitored_command", "Generic end summary does not match this actual segment")
    for key in ("owner_identity", "owner_source", "started_utc", "plan", "plan_sha256", "plan_file_sha256", "entry_sha256", "initial_closed"):
        require(native.get(key) == first_native[key], "Native source/prefix/identity changed after start")
    require(outer.get("native_owner_identity") == native["owner_identity"] == outer.get("first_native_owner_identity")
            and outer.get("first_native_owner_source") == native["owner_source"]
            and outer.get("first_native_started_utc") == native["started_utc"]
            and native.get("automatic_retry") is False and not native.get("child_may_still_be_active"), "Native owner/child closure is unsafe")
    require(type(native.get("returncode")) is int and native["returncode"] == code, "Native actual exit differs")
    v.integer(native.get("current_child", {}).get("returncode"), "Actual final child exit", zero=True)
    native_end = v.timestamp(native["finished_utc"], now)
    task_end = v.timestamp(task["finished_utc"], now)
    both = v.timestamp(outer["windows_handles_closed_observation_utc"], now)
    outer_end = v.timestamp(outer["finished_utc"], now)
    if start["registered"]:
        admission_binding = segment["launch_files"]["registered_admission"]
        gate_terminal = inputs.json(files["registered_entry_terminal"])
        require(copies["first_registered_admission.json"] == start["admission"]
                and artifacts["first_registered_admission.json"] == admission_binding["sha256"] == outer.get("first_registered_admission_sha256")
                and outer.get("first_registered_admission_owner_identity") == native["owner_identity"]
                and copies["registered_entry_terminal.json"] == gate_terminal
                and files["registered_entry_terminal"]["sha256"] == artifacts["registered_entry_terminal.json"] == outer.get("registered_entry_terminal_sha256")
                and v.same_path(files["registered_entry_terminal"]["path"], v.join(desc["native_owner"], "registered_entry_terminal.json"))
                and gate_terminal.get("gate_source") == start["admission"]["gate_source"]
                and gate_terminal.get("profile") == start["admission"]["profile"]
                and gate_terminal.get("admission") == admission_binding
                and gate_terminal.get("native_terminal") == files["native_terminal"]
                and gate_terminal.get("status") == native["status"] and type(gate_terminal.get("returncode")) is int and gate_terminal["returncode"] == code,
                "Registered gate/admission/native raw closure differs")
        require(v.timestamp(start["admission"]["utc"], now) <= v.timestamp(outer["first_registered_admission_observed_utc"], now) <= both
                and native_end <= v.timestamp(gate_terminal["finished_utc"], now) <= task_end,
                "Registered gate/early observation/held exit chronology differs")
    require(native_end <= task_end <= v.timestamp(end["generated_utc"], now) <= both <= outer_end, "Segment exit chronology differs")
    for name in ("monitor", "wsl"):
        acquired = v.timestamp(outer[name + "_handle_acquired_utc"], now)
        first = v.timestamp(outer[name + "_first_exit_observed_utc"], now)
        final = v.timestamp(outer[name + "_final_exit_observed_utc"], now)
        require(v.windows_identity(outer[name + "_identity"], now) <= acquired
                <= first and (name != "wsl" or v.timestamp(first_monitor["task"]["started_utc"], now) <= acquired)
                and (native_end if name == "wsl" else task_end) <= first <= both <= final <= outer_end,
                "Actual held-handle closure chronology differs")
    lease = outer["power_lease"]
    require({key: lease.get(key) for key in started["power_lease"]} == started["power_lease"], "Segment power binding changed")
    v.integer(lease.get("release_return"), "Power release result")
    require(both <= v.timestamp(lease["released_utc"], now) <= outer_end, "Power released before actual process exit")
    for key, expected in (("outer_terminal", v.join(desc["receipt_output"], "terminal.json")),
                          ("native_terminal", v.join(desc["native_owner"], "terminal.json")),
                          ("monitor_final", v.join(desc["monitor_output"], "monitor_state.json")),
                          ("monitor_end", v.join(desc["monitor_output"], "end_summary.json")),
                          ("events", v.join(desc["native_owner"], "events.jsonl"))):
        require(v.same_path(files[key]["path"], expected), "Closure file belongs to another segment")
    events = [v.parse(line) for line in inputs.bound(files["events"]).splitlines() if line.strip()]
    times = [v.timestamp(row.get("utc"), now) for row in events]
    require(times == sorted(times) and all(row.get("scope") == "SUPERVISED_PENDING_COLLECTION" for row in events), "Segment event source/chronology differs")
    return {"outer": outer, "native": native, "events": events, "times": times,
            "native_end": native_end, "task_end": task_end, "outer_end": outer_end}


def event_prefix(events, prefix):
    cursor = 1
    for proof in prefix:
        for kind in ("START_SLOT", "COMPLETE_SLOT"):
            row = events[cursor]
            require(row.get("event") == kind and row.get("slot") == proof["id"]
                    and row.get("executed_by_this_owner") is False
                    and row.get("event_semantics") == "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX"
                    and row.get("status") == proof["original_status"] and type(row.get("total")) is int and row["total"] == 16,
                    "Derived prefix was confused with a new actual invocation")
            projected = {"id": row["slot"], "original_status": row["status"], "marker": row["original_marker"],
                         "terminal": row["original_terminal"], "record_sha256": proof["record_sha256"],
                         "started_utc": row["original_started_utc"], "finished_utc": row["original_finished_utc"]}
            check_same_proof(projected, stable_proof(proof))
            cursor += 1
    return cursor


def actual_start(event, trial, segment):
    require(event.get("event") == "START_SLOT" and event.get("slot") == trial["id"]
            and event.get("executed_by_this_owner") is True and event.get("event_semantics") == "ACTUAL_CHILD_INVOCATION"
            and type(event.get("total")) is int and event["total"] == 16
            and event.get("command") == ["bash", v.mounted(segment["source_files"]["entry"]["path"]), trial["id"]],
            "Actual invocation event/command differs")
    v.integer(event.get("pid"), "Actual invocation PID")


def controlled_stop(inputs, shared, segment, start, closed, prior_prefix, frontier, frontier_start, env, now):
    evidence = segment["stop_evidence"]
    require(set(evidence) == {"root_review", "intent", "native_state", "windows_started", "signal_tool", "preflight", "signal_receipt", "prepared_source"},
            "Named actual controlled-stop review/intent/signal evidence is missing")
    review = inputs.json(evidence["root_review"])
    intent = inputs.json(evidence["intent"])
    before = inputs.json(evidence["native_state"])
    windows = inputs.json(evidence["windows_started"])
    preflight = inputs.json(evidence["preflight"])
    signal = inputs.json(evidence["signal_receipt"])
    inputs.bound(evidence["signal_tool"])
    inputs.bound(evidence["prepared_source"])
    native, outer, desc = env["native"], env["outer"], start["description"]
    review_time = v.timestamp(review.get("reviewed_utc"), now)
    require(review.get("schema_version") == 1 and review.get("status") == "ROOT_REVIEWED_CLOSED_FRONTIER_PRESERVED"
            and review.get("kind") == "CONTROLLED_SIGINT_COLLECTOR_ROLLOVER"
            and review.get("segment_id") == segment["segment_id"] and review.get("plan") == {**shared["plan_binding"], "plan_sha256": shared["plan"]["plan_sha256"]}
            and review.get("outer_terminal") == segment["closure_files"]["outer_terminal"]
            and review.get("native_terminal") == segment["closure_files"]["native_terminal"]
            and review.get("events") == segment["closure_files"]["events"]
            and review.get("intent") == evidence["intent"] and review.get("signal_receipt") == evidence["signal_receipt"]
            and review.get("frontier") == stable_row(frontier)
            and review.get("original_error") == native.get("error") == "KeyboardInterrupt: "
            and review.get("original_engineering_verdict_preserved") is True and env["outer_end"] <= review_time,
            "Actual root-reviewed controlled frontier is not fixed to these original files")
    require(intent.get("status") == "INTENT_REGISTERED_NOT_SIGNALLED"
            and intent.get("scope") == "CONTROLLED_COLLECTOR_ROLLOVER_WAIT_CURRENT_ORIGINAL_COMMAND_EXIT"
            and intent.get("signal") == "SIGINT" and intent.get("signal_target") == "POSITIVE_COLLECTOR_PID_ONLY"
            and intent.get("signal_tool_sha256") == evidence["signal_tool"]["sha256"]
            and intent.get("native_state_snapshot_sha256") == evidence["native_state"]["sha256"]
            and intent.get("windows_started_snapshot_sha256") == evidence["windows_started"]["sha256"]
            and intent.get("native_owner") == desc["native_owner"]
            and windows == start["started"] and intent.get("native_command") == desc["native_command"]
            and intent.get("monitor_identity") == start["started"]["monitor_identity"], "Pre-registered actual stop intent differs")
    require(intent.get("pins") == {"collector04": segment["source_files"]["collector"]["sha256"],
                                   "prepared05": evidence["prepared_source"]["sha256"], "plan": shared["plan_binding"]["sha256"]},
            "Stop intent changed its source/model correction scope")
    require(intent.get("owner_identity") == before.get("owner_identity") == native["owner_identity"]
            and before.get("owner_pid") == native["owner_identity"]["pid"]
            and before.get("status") == "RUNNING" and before.get("plan_file_sha256") == shared["plan_binding"]["sha256"]
            and before.get("owner_source") == native["owner_source"] and before.get("current_slot") == intent.get("current_slot") == frontier["slot_id"]
            and before.get("current_child") == intent.get("current_child") and before["current_child"].get("returncode") is None,
            "Intent was not captured from the actual live owner/frontier")
    require([stable_row(row) for row in before["collected"]] == [stable_row(row) for row in intent["closed_prefix"]]
            and len(before["collected"]) == len(closed) - len(prior_prefix), "Intent completed-prefix observation differs")
    for observed, proof in zip(before["collected"], closed[len(prior_prefix):]):
        check_same_proof(stable_row(observed), stable_proof(proof))
    expected_child = intent["current_child"]
    v.linux_identity(expected_child["identity"])
    require(expected_child["pid"] == expected_child["identity"]["pid"] == frontier_start["pid"]
            and expected_child["identity"]["boot_id"] == native["owner_identity"]["boot_id"]
            and expected_child["command"] == frontier_start["command"]
            and {key: native["current_child"].get(key) for key in ("pid", "identity", "command", "started_utc")}
            == {key: expected_child[key] for key in ("pid", "identity", "command", "started_utc")},
            "Controlled stop changed or signalled a different owned child")
    require(preflight.get("status") == "IDENTITY_CHECKED_BEFORE_SINGLE_PID_SIGNAL"
            and preflight.get("intent_sha256") == evidence["intent"]["sha256"]
            and preflight.get("signal_tool_sha256") == evidence["signal_tool"]["sha256"]
            and preflight.get("owner_identity") == native["owner_identity"]
            and preflight.get("child_identity") == expected_child["identity"]
            and preflight.get("child_ppid") == native["owner_identity"]["pid"]
            and preflight.get("signal_target_pid") == native["owner_identity"]["pid"]
            and preflight.get("signal") == "SIGINT", "Actual single-PID signal preflight differs")
    argv = preflight["actual_owner_argv"]
    require(PurePosixPath(argv[0]).name in {"python3", "python3.10"} and argv[1:] == intent["native_command"][5:], "Actual signalled collector argv differs")
    require(signal.get("status") == "SINGLE_PID_SIGINT_REQUEST_SENT" and signal.get("signal") == "SIGINT"
            and signal.get("os_kill_returned") is True and signal.get("signal_target_pid") == native["owner_identity"]["pid"]
            and signal.get("intent_sha256") == evidence["intent"]["sha256"] and signal.get("preflight_sha256") == evidence["preflight"]["sha256"],
            "Actual bound signal receipt missing")
    require(v.timestamp(frontier["original_started_utc"], now) <= v.timestamp(intent["registered_utc"], now)
            <= v.timestamp(preflight["utc"], now) <= v.timestamp(signal["utc"], now)
            <= v.timestamp(frontier["original_finished_utc"], now) <= v.timestamp(native["current_child"]["finished_utc"], now)
            <= env["native_end"] <= review_time and native.get("metadata_fault_child_exit_observed") is True,
            "Intent/signal/waited-child/root-review chronology differs")
    require(v.timestamp(native["started_utc"], now) <= v.timestamp(expected_child["started_utc"], now)
            <= v.timestamp(frontier_start["utc"], now), "Controlled frontier child start provenance differs")
    return review_time


def metadata_stop(inputs, shared, segment, frontier, frontier_start, exited, env, now):
    evidence = segment["stop_evidence"]
    require(set(evidence) == {"root_review"}, "Metadata stop must use its actual root review, without invented signal evidence")
    review = inputs.json(evidence["root_review"])
    native = env["native"]
    reviewed = v.timestamp(review.get("reviewed_utc"), now)
    require(review.get("schema_version") == 1
            and review.get("status") == "ROOT_REVIEWED_CLOSED_METADATA_FRONTIER_PRESERVED"
            and review.get("kind") == "SHORT_DETECTOR_UNKNOWN_COLLECTOR_STOP"
            and review.get("segment_id") == segment["segment_id"]
            and review.get("plan") == {**shared["plan_binding"], "plan_sha256": shared["plan"]["plan_sha256"]}
            and all(review.get(key) == segment["closure_files"][key] for key in ("outer_terminal", "native_terminal", "events"))
            and review.get("frontier") == stable_row(frontier)
            and review.get("original_error") == native.get("error") == METADATA_STOP_ERROR
            and review.get("original_engineering_verdict_preserved") is True
            and frontier["original_status"] == "INCOMPLETE_EVIDENCE" and env["outer_end"] <= reviewed,
            "Actual root-reviewed metadata frontier is not fixed to these original files")
    inputs.bound(review["short_input_review"])
    require(exited.get("event") == "CHILD_EXIT" and exited.get("slot") == frontier["slot_id"],
            "Metadata fault did not follow its actual original child exit")
    v.integer(exited.get("returncode"), "Metadata frontier actual child exit", zero=True)
    child = native["current_child"]
    v.linux_identity(child["identity"])
    require(child.get("pid") == child["identity"]["pid"] == frontier_start["pid"]
            and child["identity"]["boot_id"] == native["owner_identity"]["boot_id"]
            and child.get("command") == frontier_start["command"]
            and native.get("metadata_fault_child_exit_observed") is True
            and v.timestamp(native["started_utc"], now) <= v.timestamp(child["started_utc"], now) <= v.timestamp(frontier_start["utc"], now)
            and v.timestamp(frontier["original_finished_utc"], now) <= v.timestamp(exited["utc"], now)
            <= v.timestamp(child["finished_utc"], now) <= env["native_end"] <= reviewed,
            "Metadata frontier actual child/wait/source chronology differs")
    return reviewed


def result_for(profile, plan_binding, plan, prefix, summaries, inputs, library_binding):
    ids = [row["id"] for row in prefix]
    bindings = {**inputs.seen, v.path_key(library_binding["path"]): library_binding}
    return {"schema_version": 1, "status": "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION" if len(prefix) == 16 else "BOUND_PRESERVED_PREFIX_CHAIN",
            "plan": {**plan_binding, "plan_sha256": plan["plan_sha256"]}, "after_slot": ids[-1] if ids else "__before_first__",
            "closed_ids": ids, "pending_ids": [trial["id"] for trial in plan["trials"][len(prefix):]], "closed": prefix.copy(),
            "segments": summaries.copy(), "source_digest": profile["source_digest"],
            "input_bindings": sorted(bindings.values(), key=lambda row: v.path_key(row["path"])),
            "claim_boundary": "Execution attribution and preserved original prefix only. Faults and engineering FAIL/INCOMPLETE remain unchanged. No launch, retry, idle, cold-build or formal admission authorization."}


def validate_chain(profile, read=v.local_small_read, *, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    library_binding = reviewed_slot_source()
    inputs = v.Inputs(read)
    plan_binding = profile["plan"]
    plan = inputs.json(plan_binding)
    require(plan.get("plan_sha256") == profile["plan_digest"] == v.content_digest(plan, "plan_sha256")
            and plan.get("mode") == "EXTENSION_PROBE" and plan.get("selected_seeds") == [4]
            and len(plan["trials"]) == len({row["id"] for row in plan["trials"]}) == 16
            and v.sha(v.canonical(plan["source_hashes"])) == profile["source_digest"], "Fixed common full16 flight registration differs")
    inputs.bind_plan_results_alias(plan)
    captures = v.snapshot_capture_contract(profile, inputs, plan)
    shared = {"plan": plan, "plan_binding": plan_binding, "captures": captures}
    segments = profile["segments"]
    require(isinstance(segments, list) and 1 <= len(segments) <= 16
            and len({row["segment_id"] for row in segments}) == len(segments), "Unique actual closed segments required")
    shared["segments_by_id"] = {segment["segment_id"]: segment for segment in segments}
    prefix, summaries = [], []
    previous_qualified_end = None
    used_owners = set()
    for index, segment in enumerate(segments):
        require(len(prefix) < 16, "No new owner may rerun a complete matrix")
        prior_profile = {**profile, "segments": segments[:index]}
        prior_result = result_for(profile, plan_binding, plan, prefix, summaries, inputs, library_binding)
        start = launch(inputs, shared, segment, prefix, now, prior_profile, prior_result)
        if previous_qualified_end is not None:
            require(previous_qualified_end <= start["launch_time"], "Next owner started before previous closure and root review")
        owner_key = (start["description"]["native_owner"], start["first_native"]["owner_identity"]["boot_id"], start["first_native"]["owner_identity"]["start_ticks"])
        require(owner_key not in used_owners, "An owner was reused or relabelled")
        used_owners.add(owner_key)
        metadata_stopped = segment["disposition"] == "ROOT_REVIEWED_METADATA_STOP"
        stopped = segment["disposition"] == "ROOT_REVIEWED_CONTROLLED_STOP" or metadata_stopped
        require(stopped or segment["disposition"] == "COMPLETED", "Unsupported/unreviewed fault disposition")
        env = envelope(inputs, segment, start, now, stopped=stopped)
        native, outer, events, times = (env[key] for key in ("native", "outer", "events", "times"))
        k, collected = len(prefix), native["collected"]
        m = len(collected)
        require([row["slot_id"] for row in collected] == [trial["id"] for trial in plan["trials"][k:k + m]]
                and type(outer.get("collected_slots")) is int and outer["collected_slots"] == m,
                "Actual newly collected slice differs from its preserved prefix")
        require(events and events[0].get("event") == "COLLECTION_STARTED"
                and events[0].get("pending_ids") == [trial["id"] for trial in plan["trials"][k:]], "Actual owner initial pending order differs")
        cursor = event_prefix(events, prefix)
        new = []
        for offset, row in enumerate(collected):
            trial = plan["trials"][k + offset]
            proof = audit_row(inputs, plan, trial, row, captures, now, segment["segment_id"], "ACTUAL_COLLECTED", owner_started=native["started_utc"])
            first, exited, complete = events[cursor:cursor + 3]
            actual_start(first, trial, segment)
            require(exited.get("event") == "CHILD_EXIT" and exited.get("slot") == trial["id"], "Actual child-exit event missing")
            v.integer(exited.get("returncode"), "Actual child exit", zero=True)
            require(complete.get("event") == "COMPLETE_SLOT" and complete.get("slot") == trial["id"]
                    and complete.get("executed_by_this_owner") is True
                    and complete.get("event_semantics") == "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED"
                    and complete.get("status") == proof["original_status"] and complete.get("terminal_sha256") == proof["terminal"]["sha256"]
                    and type(complete.get("total")) is int and complete["total"] == 16
                    and v.timestamp(proof["finished_utc"], now) <= v.timestamp(exited["utc"], now), "Actual completed invocation provenance differs")
            new.append(proof)
            cursor += 3
        if stopped:
            require(k + m < 16 and len(events) == cursor + (3 if metadata_stopped else 2) and native.get("current_slot") == plan["trials"][k + m]["id"]
                    and events[-1].get("event") == "STOPPED_FAULT" and events[-1].get("error") == native.get("error")
                    and events[-1].get("slot") == native["current_slot"], "Stopped frontier event shape differs; no COMPLETE may be invented")
            trial = plan["trials"][k + m]
            actual_start(events[cursor], trial, segment)
            review = inputs.json(segment["stop_evidence"]["root_review"])
            frontier = review["frontier_record"]
            require(frontier["slot_id"] == trial["id"], "Review names another frontier")
            if metadata_stopped:
                previous_qualified_end = metadata_stop(inputs, shared, segment, frontier, events[cursor], events[cursor + 1], env, now)
                proof = audit_row(inputs, plan, trial, frontier, captures, now, segment["segment_id"],
                                  "ROOT_REVIEWED_METADATA_FRONTIER_INCOMPLETE_RETAINED", owner_started=native["started_utc"],
                                  metadata_review=segment["stop_evidence"]["root_review"])
            else:
                proof = audit_row(inputs, plan, trial, frontier, captures, now, segment["segment_id"], "ROOT_REVIEWED_FRONTIER_ORIGINAL_FAULT_RETAINED", owner_started=native["started_utc"])
                previous_qualified_end = controlled_stop(inputs, shared, segment, start, prefix + new, prefix,
                                                        frontier, events[cursor], env, now)
            prefix.extend(new + [proof])
        else:
            require(k + m == 16 and m > 0 and native.get("current_slot") is None and len(events) == cursor + 1
                    and events[-1].get("event") == "COLLECTION_FINISHED"
                    and type(events[-1].get("collected_slots")) is int and events[-1]["collected_slots"] == m,
                    "A completed segment did not close exactly its remaining pending slice")
            child = native["current_child"]
            v.linux_identity(child["identity"])
            require(child.get("pid") == child["identity"]["pid"] == first["pid"]
                    and child["identity"]["boot_id"] == native["owner_identity"]["boot_id"]
                    and child.get("command") == first["command"]
                    and v.timestamp(native["started_utc"], now) <= v.timestamp(child["started_utc"], now) <= v.timestamp(first["utc"], now)
                    and v.timestamp(new[-1]["finished_utc"], now) <= v.timestamp(child["finished_utc"], now)
                    <= v.timestamp(exited["utc"], now) <= env["native_end"],
                    "Completed owner final child is not the actual last original invocation")
            previous_qualified_end = env["outer_end"]
            prefix.extend(new)
        require(v.timestamp(native["started_utc"], now) <= times[0]
                and times[-2] <= env["native_end"] <= times[-1] <= env["task_end"], "Native terminal/event chronology differs")
        summaries.append({"segment_id": segment["segment_id"], "original_native_status": native["status"],
                          "disposition": segment["disposition"], "derived_prefix_count": k, "actual_collected_count": m,
                          "root_reviewed_frontier_count": 1 if stopped else 0, "outer_terminal": segment["closure_files"]["outer_terminal"]})
    ids = [row["id"] for row in prefix]
    require(ids == [trial["id"] for trial in plan["trials"][:len(prefix)]] and len(set(ids)) == len(ids), "Chain coverage has a gap or a rerun")
    inputs.unchanged()
    require(reviewed_slot_source() == library_binding, "Reviewed slot dependency changed during chain validation")
    return result_for(profile, plan_binding, plan, prefix, summaries, inputs, library_binding)


def validate_continuation_profile(profile, read=v.local_small_read, *, now=None):
    result = validate_chain(profile, read, now=now)
    require(result["status"] == "BOUND_PRESERVED_PREFIX_CHAIN" and 0 < len(result["closed_ids"]) < 16,
            "A nonempty incomplete preserved prefix is required for continuation")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-output", type=Path)
    parser.parse_args(argv)
    try:
        require(PRODUCTION_ENABLED, "Production owner-chain validation disabled; actual stop review and continuation profile are not fixed")
        raise v.Refused("No production chain profile is instantiated")
    except (OSError, v.Refused, ValueError) as error:
        print(json.dumps({"status": "REFUSED_NO_NATIVE_TASK_OR_OUTPUT", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
