"""Direct serial measurement after the new collector07 really closes.

Prepared only. Future inputs are intentionally absent. Reuse the exact old08
workflow_commands / child_step / positive_budget, never its incompatible old07
closure or old run(). No owner/trigger chain, staging, build or formal launch.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ENABLED = True
REGISTERED_INPUTS = {
    "collector": {
        "path": "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/tools/experiment_orchestration/humble54_pending_collector07/collect_humble54_pending07.py",
        "sha256": "7d2523325bca8ef520fe0e5a7bd78da355943099e3f45efee2c3ad4e870cdd9b"
    },
    "profile": {
        "path": "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/tools/experiment_orchestration/humble54_pending_collector07/registered_profile07.json",
        "sha256": "c36f17363874173ee7fed08d482a68f518fd44cffd581d757de09ccd649ded55"
    },
    "terminal": {
        "path": "/root/uav_tracking_collection54_probe02_owner07/terminal.json",
        "sha256": "34a60e0bc189c0b1845e0d4a0dc85388e968a53a666e2cfdeedb46eb48e03432"
    },
    "events": {
        "path": "/root/uav_tracking_collection54_probe02_owner07/events.jsonl",
        "sha256": "d1bf63bf661e0358f6e94881e13da7178c9fb78d052438a3cbe0a9b8a9a460d4"
    },
    "admission": {
        "path": "/root/uav_tracking_collection54_probe02_owner07.admission.json",
        "sha256": "3a6d5b731bb28948301a513292a08bb94fafc5a0d8f1540a0270493f774c6208"
    },
    "monitor_state": {
        "path": "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/monitor_humble54_probe02_owner07/monitor_state.json",
        "sha256": "1bb851051d292495cc9e951035e105fe94cfe555a7d12b86a2a0ec541d5055cf"
    },
    "launcher_terminal": {
        "path": "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/diagnostics/humble54_pending_collector07_launcher01/terminal.json",
        "sha256": "8f5056620e21b60860d9d8785b79eab0c74a243071f08d039711f166b5d771e9"
    }
}
INPUT_NAMES = {"collector", "profile", "terminal", "events", "admission", "monitor_state", "launcher_terminal"}
OLD08 = ROOT / "tools/experiment_orchestration/humble54_closed_followon_runner08/run_followon08.py"
OLD08_SHA = "df0e1b3ac56611b63de98ba2fc8782a2a687b79691e44ad18d9e69eb74831db6"
LAUNCHER = ROOT / "tools/experiment_orchestration/humble54_pending_collector07/launch_windows07.py"
LAUNCHER_SHA = "3cfd98f01d6d9373aa01c45fd691ffd5a34e8dd1d3363edd12a990280322c923"
SCOPE = "NATIVE_SERIAL_AFTER_COLLECTOR07_ACTUAL28_R0_BUDGET_ONLY"
CLOSURE_STATUS = "FULL16_AFTER_COLLECTOR07_CLOSED_NOT_ENGINEERING_ADMISSION"
AFTER28_SCOPE = "NATIVE_EXPLICIT_AFTER28_SIZE_BINDING_CONTINUATION_NOT_ADMISSION"
EXECUTED_SOURCE_SHA = "47fcbd727debbdb418bb9fbb1cc6a5abeb9806855f6331709c8590c688232433"
EXECUTED_SOURCE_ARCHIVE = Path(__file__).resolve().parent / "continue_after28_01/run_closed_measurement.executed_47fcbd.py"
AFTER28_TERMINAL = {
    "path": "/mnt/d/WSL/UAVHumble22-validation/humble54_probe02_closed_measurement_after07_01/terminal.json",
    "sha256": "fadaead9a3ba1b4f2d45c7df4ab05fd055fce33c24e8900b24d78112ab704b5c"}
AFTER28_SUMMARY_SHA = "cac0d6bf42920dce4e59b9bb490e3bacc96cd8aaf57d4b50fc5b9b27dc459403"
AFTER28_LARGE_JSON = {
    "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/frozen_fullplan_v4_humble54/reliability_v4_humble54_core12_probe01_car_stage2_crossing_seed004/physical_identity.json": {
        "bytes": 3066769, "sha256": "0c2d32eec9e5017852e8f079fa01914cfbb2e8a812b3fe3d2c6fa2e04d671d28"},
    "/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/frozen_fullplan_v4_humble54/reliability_v4_humble54_core12_probe01_car_stage3_multi_active_seed004/physical_identity.json": {
        "bytes": 7660044, "sha256": "58aab55dea538bf9120bddc6015e16ca237f3a241929877fc547900179692521"}}


def require(value, message):
    if not value:
        raise ValueError(message)


def fixed_module(path, expected):
    raw = Path(path).read_bytes()
    require(len(raw) <= 2 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == expected,
            "Reviewed source changed: " + str(path))
    module = types.ModuleType("direct_measurement_" + Path(path).stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def new_paths(old):
    p = old.paths()
    results = p["frozen"] / "results"
    p.update(receipt=Path("/mnt/d/WSL/UAVHumble22-validation/humble54_probe02_closed_measurement_after07_01"),
             tools=Path("/root/uav_tracking_storage_measure54_probe02_after07_01"),
             sizes=results / "full28_storage_measurement_probe02_after07_01",
             calibration=results / "reliability_v4_humble54_development_calibration_probe02_after07_01",
             budget=results / "full280_storage_budget_probe02_after07_01/budget.json")
    p["inventory"] = p["receipt"] / "physical_inventory.json"
    return p


def verify_events(events, rows, plan, entry, terminal, timestamp):
    """Pure small-event audit; eleven observations are not new invocations."""
    ids = [row["id"] for row in plan["trials"]]
    require(len(rows) == len(ids) == 16 and len(events) == 39,
            "Exact eleven observed plus five actually invoked slot events required")
    require(events[0].get("event") == "COLLECTION_STARTED" and events[0].get("pending_ids") == ids[11:],
            "Collector07 original pending order differs")
    cursor = 1
    for row in rows[:11]:
        for kind in ("START_SLOT", "COMPLETE_SLOT"):
            event = events[cursor]
            require(event.get("event") == kind and event.get("slot") == row["slot_id"]
                    and event.get("executed_by_this_owner") is False
                    and event.get("event_semantics") == "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX"
                    and event.get("status") == row["original_status"]
                    and event.get("original_terminal") == row["original_terminal"]
                    and event.get("original_marker") == row["original_marker"]
                    and event.get("original_started_utc") == row["original_started_utc"]
                    and event.get("original_finished_utc") == row["original_finished_utc"],
                    "Original eleven derived observations changed or became invocations")
            cursor += 1
    for row in rows[11:]:
        start, exited, complete = events[cursor:cursor + 3]
        require(start.get("event") == "START_SLOT" and start.get("slot") == row["slot_id"]
                and start.get("executed_by_this_owner") is True
                and start.get("event_semantics") == "ACTUAL_CHILD_INVOCATION"
                and start.get("command") == ["bash", entry, row["slot_id"]]
                and type(start.get("pid")) is int and start["pid"] > 0
                and exited.get("event") == "CHILD_EXIT" and exited.get("slot") == row["slot_id"]
                and type(exited.get("returncode")) is int and exited["returncode"] == 0
                and complete.get("event") == "COMPLETE_SLOT" and complete.get("slot") == row["slot_id"]
                and complete.get("executed_by_this_owner") is True
                and complete.get("event_semantics") == "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED"
                and complete.get("terminal_sha256") == row["terminal_sha256"]
                and complete.get("status") == row["original_status"]
                and timestamp(terminal["started_utc"]) <= timestamp(row["original_started_utc"])
                <= timestamp(row["original_finished_utc"]) <= timestamp(exited["utc"]),
                "Remaining-five actual invocation or original exit/record differs")
        cursor += 3
    require(events[-1].get("event") == "COLLECTION_FINISHED"
            and events[-1].get("collected_slots") == 5, "Actual five-slot collection did not finish")
    times = [timestamp(row["utc"]) for row in events]
    require(times == sorted(times) and timestamp(terminal["started_utc"]) <= times[0]
            and timestamp(terminal["finished_utc"]) <= times[-1], "Collector07 event UTC order differs")
    child, final_start = terminal["current_child"], events[-4]
    require(child.get("command") == final_start["command"]
            and child.get("pid") == child["identity"]["pid"] == final_start["pid"]
            and type(child.get("returncode")) is int and child["returncode"] == 0
            and child["identity"]["boot_id"] == terminal["owner_identity"]["boot_id"]
            and timestamp(rows[-1]["original_finished_utc"]) <= timestamp(child["finished_utc"])
            <= timestamp(events[-3]["utc"]) <= timestamp(terminal["finished_utc"]), "Actual last child closure differs")


def closure_audit(bindings, old):
    """Native small evidence + original full-source checks, no subprocess.

    Interface: seven actual registered bindings named by INPUT_NAMES. The
    collector source supplies its own registered profile SHA and exact original
    eleven pins. Never manufacture the incompatible chain03 profile schema.
    """
    require(set(bindings) == INPUT_NAMES, "Seven actual original input bindings required")
    collector_path = Path(bindings["collector"]["path"])
    c = fixed_module(collector_path, bindings["collector"]["sha256"])
    v = c.review_library()
    inputs = v.Inputs(v.local_small_read)
    for binding in bindings.values():
        inputs.bound(binding)
    profile_path = v.local_path(bindings["profile"]["path"])
    require(c.PRODUCTION_ENABLED is True and c.PROFILE_STATUS == "REGISTERED_DEVELOPMENT_PREFIX11"
            and c.REGISTERED_PROFILE_SHA256 == bindings["profile"]["sha256"],
            "Actual registered collector07/profile required")
    checked = c.validate_profile(profile_path, native_originals=True, pending_pristine=False)
    profile, plan = checked["profile"], checked["plan"]
    inputs.bind_plan_results_alias(plan)
    for binding in checked["inputs"].seen.values():
        inputs.bound(binding)
    for role, expected in (("terminal", Path(profile["native_output"]) / "terminal.json"),
                           ("events", Path(profile["native_output"]) / "events.jsonl"),
                           ("admission", Path(profile["native_output"] + ".admission.json")),
                           ("monitor_state", v.local_path(profile["windows_monitor_output"]) / "monitor_state.json")):
        require(v.local_path(bindings[role]["path"]).resolve(strict=True) == expected.resolve(strict=True),
                "Actual collector07 input relocated: " + role)
    require(v.local_path(bindings["launcher_terminal"]["path"]).resolve(strict=True)
            == (ROOT / "results/diagnostics/humble54_pending_collector07_launcher01/terminal.json").resolve(strict=True),
            "Existing collector07 launcher original terminal required")
    terminal = inputs.json(bindings["terminal"])
    admission = inputs.json(bindings["admission"])
    monitor = inputs.json(bindings["monitor_state"])
    launcher = inputs.json(bindings["launcher_terminal"])
    events = [v.parse(line) for line in inputs.bound(bindings["events"]).splitlines() if line.strip()]
    now = datetime.now(timezone.utc)
    stamp = lambda value: v.timestamp(value, now)
    def same_binding(actual, expected):
        return (actual.get("sha256") == expected.get("sha256")
                and v.local_path(actual["path"]).resolve(strict=True) == v.local_path(expected["path"]).resolve(strict=True))
    v.linux_identity(terminal["owner_identity"])
    v.linux_identity(terminal["current_child"]["identity"])
    require(terminal.get("scope") == c.SCOPE and terminal.get("status") == "COLLECTION_FINISHED"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 0
            and terminal.get("current_slot") is None and terminal.get("automatic_retry") is False
            and terminal.get("formal_admission") is False and not terminal.get("child_may_still_be_active")
            and not terminal.get("error")
            and terminal.get("owner_pid") == terminal["owner_identity"]["pid"]
            and terminal.get("owner_source") == {"path": str(collector_path.resolve()), "sha256": bindings["collector"]["sha256"]}
            and terminal.get("plan_sha256") == plan["plan_sha256"]
            and terminal.get("plan_file_sha256") == c.PLAN_SHA and terminal.get("entry_sha256") == c.ENTRY_SHA
            and same_binding(terminal["continuation_admission"], bindings["admission"])
            and terminal.get("conditional_identity_rule") == c.CONDITIONAL_IDENTITY,
            "Collector07 actual native completion/source/admission differs")
    require(v.local_path(terminal["plan"]).resolve(strict=True)
            == v.local_path(profile["sources"]["plan"]["path"]).resolve(strict=True),
            "Actual collector07 terminal refers to another original plan")
    ids = [trial["id"] for trial in plan["trials"]]
    require(admission.get("scope") == "DEVELOPMENT_PREFIX11_ADMISSION_AFTER_TRUE_STOPPED06"
            and same_binding(admission["profile"], bindings["profile"])
            and same_binding(admission["collector"], terminal["owner_source"])
            and admission.get("owner_identity") == terminal["owner_identity"]
            and admission.get("closed_ids") == ids[:11] and admission.get("pending_ids") == ids[11:]
            and type(admission.get("original_stop_returncode")) is int and admission["original_stop_returncode"] == 2
            and admission.get("automatic_retry") is False and admission.get("formal_admission") is False,
            "Actual early prefix11/five admission differs")
    original = c.fixed_module("after07_original_runner", Path(plan["frozen_root"]) / "scripts/run_reliability_v4.py", c.RUNNER_SHA)
    chain = c.fixed_module("after07_original_chain03", v.local_path(profile["sources"]["old_chain03"]["path"]),
                           profile["sources"]["old_chain03"]["sha256"])
    module = c.PreservedProfileModule(original, profile_path.resolve(), chain,
                                     c.load(v.local_path(profile["sources"]["old_profile06"]["path"])))
    require(module.source_hashes(Path(plan["frozen_root"])) == plan["source_hashes"], "Original live full source map changed")
    rows = [c.check_record(module, plan, trial, c.CAPTURE_PROFILES, c.HISTORY) for trial in plan["trials"]]
    require(terminal.get("initial_closed") == rows[:11] and terminal.get("collected") == rows[11:],
            "Actual eleven observed/five collected record proofs differ")
    for row, bound in zip(rows[:11], profile["closed_prefix"]):
        require(row["terminal_sha256"] == bound["terminal"]["sha256"]
                and row["original_marker"]["sha256"] == bound["marker"]["sha256"], "Original eleven pins changed")
    for trial, row in zip(plan["trials"], rows):
        for binding in (row["original_terminal"], row["original_marker"]):
            inputs.bound(binding)
        record = inputs.json(row["original_terminal"])
        for name in c.SMALL_ARTIFACTS:
            inputs.bound({"path": str(Path(trial["directory"]) / name), "sha256": record["artifact_hashes"][name]})
    entry = str(v.local_path(profile["sources"]["entry"]["path"]))
    verify_events(events, rows, plan, entry, terminal, stamp)
    task = monitor["task"]
    for identity in (monitor["monitor_process"], task["process"], launcher["launcher_identity"], launcher["owned_monitor_identity"]):
        v.windows_identity(identity, now)
    require(monitor.get("tasks") == [task] and task.get("monitor_kind") == "owned_child"
            and type(task.get("returncode")) is int and task["returncode"] == 0
            and type(task["process"].get("pid")) is int and task["process"]["pid"] > 0
            and bool(task["process"].get("start_token")) and bool(monitor["monitor_process"].get("start_token"))
            and stamp(terminal["finished_utc"]) <= stamp(events[-1]["utc"]) <= stamp(task["finished_utc"])
            and stamp(task["started_utc"]) <= stamp(task["finished_utc"]),
            "Existing monitor did not retain the actual owned WSL child zero exit")
    for role, expected in (("events", bindings["events"]["path"]),
                           ("ledger", str(Path(profile["native_output"]) / "state.json")),
                           ("plan", profile["sources"]["plan"]["path"])):
        require(v.local_path(monitor["sources"][role]).resolve(strict=True) == v.local_path(expected).resolve(strict=True),
                "Existing monitor observes a different collector07 source")
    require(launcher.get("status") == "OWNED_MONITOR_ENDED"
            and type(launcher.get("returncode")) is int and launcher["returncode"] == 0
            and launcher.get("closure_verified") is True and launcher.get("errors") == []
            and launcher.get("automatic_retry") is False
            and type(launcher.get("owned_monitor_returncode")) is int and launcher["owned_monitor_returncode"] == 0
            and {key: launcher["owned_monitor_identity"][key] for key in ("pid", "start_token")}
            == {key: monitor["monitor_process"][key] for key in ("pid", "start_token")}
            and launcher.get("native_owner_identity") == terminal["owner_identity"]
            and launcher.get("native_collection_status") == "COLLECTION_FINISHED"
            and type(launcher.get("native_collection_returncode")) is int and launcher["native_collection_returncode"] == 0
            and launcher.get("native_terminal", {}).get("sha256") == bindings["terminal"]["sha256"]
            and launcher.get("monitor_final", {}).get("sha256") == bindings["monitor_state"]["sha256"]
            and same_binding(launcher["pins"]["collector"], bindings["collector"])
            and same_binding(launcher["pins"]["registered_profile"], bindings["profile"])
            and same_binding(launcher["pins"]["monitor"], profile["sources"]["monitor"])
            and same_binding(launcher["pins"]["plan"], profile["sources"]["plan"])
            and same_binding(launcher["source"], {"path": str(LAUNCHER), "sha256": LAUNCHER_SHA})
            and launcher.get("monitor_final_task") == task
            and stamp(launcher["started_utc"]) <= stamp(terminal["started_utc"])
            and stamp(task["finished_utc"]) <= stamp(launcher["owned_monitor_finished_utc"])
            <= stamp(launcher["finished_utc"]),
            "Existing launcher has no actual zero Popen/native/monitor closure")
    inputs.bound(launcher["source"])
    for role in ("monitor_final", "monitor_end", "native_terminal"):
        inputs.bound(launcher[role])
    end = inputs.json(launcher["monitor_end"])
    require(end.get("status") == "COMPLETED" and end.get("task") == task,
            "Original existing monitor end summary does not match its final task")
    receipt_root = v.local_path(bindings["launcher_terminal"]["path"]).parent
    expected_artifacts = {"monitor_final.json": bindings["monitor_state"]["sha256"],
                          "monitor_end.json": launcher["monitor_end"]["sha256"],
                          "native_terminal.json": bindings["terminal"]["sha256"]}
    require(launcher.get("artifacts") == expected_artifacts, "Existing launcher original raw-copy hashes differ")
    for name, pin in expected_artifacts.items():
        inputs.bound({"path": str(receipt_root / name), "sha256": pin})
    lease = launcher["power_lease"]
    require(type(lease.get("thread_id")) is int and lease["thread_id"] > 0
            and lease.get("release_thread_id") == lease["thread_id"] and lease.get("flags") == 0x80000003
            and lease.get("global_power_policy_changed") is False
            and type(lease.get("request_return")) is int and lease["request_return"] != 0
            and lease.get("released_utc") and type(lease.get("release_return")) is int
            and lease["release_return"] != 0
            and stamp(launcher["started_utc"]) <= stamp(lease["requested_utc"])
            <= stamp(terminal["started_utc"]) <= stamp(launcher["owned_monitor_finished_utc"])
            <= stamp(lease["released_utc"])
            <= stamp(launcher["finished_utc"]), "Original launcher temporary power lease release is incomplete")
    require(module.source_hashes(Path(plan["frozen_root"])) == plan["source_hashes"], "Source map changed during closure audit")
    inputs.unchanged()
    return {"schema_version": 1, "status": CLOSURE_STATUS, "created_utc": old.utc(),
            "plan": profile["sources"]["plan"], "closed_ids": ids, "pending_ids": [],
            "closed": rows, "actual_original_bindings": bindings, "original_owner06_returncode": 2,
            "original_verdicts_preserved": True, "formal_admission": False,
            "claim_boundary": "New collector07 completion plus preserved eleven original slots; not an old07 profile or engineering acceptance."}, inputs


def after28_inputs(v, previous):
    """Keep both original size gates; expand only two fixed original JSONs.

    The same exact reader is used by inherited read_reference()/unchanged().
    Authenticated root/results aliases remain the original Inputs behavior.
    """
    def read(reference):
        fixed = AFTER28_LARGE_JSON.get(reference)
        if fixed is None:
            return v.local_small_read(reference)
        path = v.local_path(reference)
        require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path,
                "Ordinary canonical allowlisted identity JSON required")
        before = path.stat()
        require(before.st_size == fixed["bytes"] and before.st_size <= 8 * 1024**2,
                "Exact allowlisted identity JSON size differs")
        payload = path.read_bytes()
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                "Allowlisted identity JSON changed while reading")
        require(len(payload) == fixed["bytes"] and v.sha(payload) == fixed["sha256"],
                "Exact allowlisted identity JSON SHA differs")
        return payload

    class ExactInputs(v.Inputs):
        def bound(self, binding):
            fixed = AFTER28_LARGE_JSON.get(binding.get("path")) if isinstance(binding, dict) else None
            if fixed is None:
                return super().bound(binding)
            require(set(binding) == {"path", "sha256"} and binding["sha256"] == fixed["sha256"],
                    "Only the two exact original identity bindings may exceed 2 MiB")
            v.path_key(binding["path"])
            payload = self.read_reference(binding["path"])
            require(isinstance(payload, bytes) and len(payload) == fixed["bytes"]
                    and len(payload) <= 8 * 1024**2 and v.sha(payload) == binding["sha256"],
                    "Exact allowlisted identity binding differs")
            key = v.path_key(binding["path"])
            require(key not in self.seen or self.seen[key] == binding, "Conflicting bindings for one path")
            self.seen[key] = binding.copy()
            return payload

    result = ExactInputs(read)
    result.seen = {key: value.copy() for key, value in previous.seen.items()}
    result.results_aliases = previous.results_aliases.copy()
    return result


def validate_after28_terminal(terminal, original, old, p, inputs, v, guard, archive_binding, now):
    """Only this authentic seven-step large-input stop may be continued."""
    require(terminal.get("scope") == original.SCOPE
            and terminal.get("status") == "STOPPED_DIRECT_MEASUREMENT_PARTIAL_OUTPUTS_RETAINED"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 2
            and terminal.get("interruptions") == [] and len(terminal.get("errors", [])) == 1
            and terminal["errors"][0].get("error") == "Refused: Refusing large input"
            and terminal.get("automatic_retry") is False and terminal.get("formal_admission") is False
            and terminal.get("commit") == old.COMMIT and terminal.get("guard") == guard
            and terminal.get("actual_original_bindings") == REGISTERED_INPUTS,
            "Only the original exact after28 large-input stop is eligible")
    source = terminal["source"]
    require(source.get("sha256") == EXECUTED_SOURCE_SHA
            and v.local_path(source["path"]).resolve(strict=True) == Path(__file__).resolve()
            and archive_binding["sha256"] == EXECUTED_SOURCE_SHA
            and original.PRODUCTION_ENABLED is True and original.REGISTERED_INPUTS == REGISTERED_INPUTS
            and original.new_paths(old) == p,
            "Original executed source, archive or actual collector bindings differ")
    v.linux_identity(terminal["owner_identity"])
    stamp = lambda value: v.timestamp(value, now)
    start, finish = stamp(terminal["started_utc"]), stamp(terminal["finished_utc"])
    require(start <= finish and start <= stamp(terminal["errors"][0]["utc"]) <= finish,
            "Original stop chronology differs")
    expected = [("native_idle", ["bash", p["idle"]])]
    expected += [("tool_" + str(index), ["git", "-C", original.ROOT, "show", old.COMMIT + ":" + relative])
                 for index, relative in enumerate(old.TOOL_PINS)]
    expected += old.workflow_commands(p)[:1]
    require(len(terminal["steps"]) == len(expected) == 7, "Exactly seven successful original steps required")
    previous = start
    for row, (label, argv) in zip(terminal["steps"], expected):
        require(row.get("id") == label and row.get("command") == list(map(str, argv))
                and type(row.get("returncode")) is int and row["returncode"] == 0
                and row.get("pid") == row["identity"]["pid"], "Original actual step differs: " + label)
        v.linux_identity(row["identity"])
        require(row["identity"]["boot_id"] == terminal["owner_identity"]["boot_id"], "Original child boot differs")
        begun, ended = stamp(row["started_utc"]), stamp(row["finished_utc"])
        require(previous <= begun <= ended <= finish, "Original serial step chronology differs")
        previous = ended
        for channel in ("stdout", "stderr"):
            path = p["receipt"] / (label + "." + channel + ".log")
            require(v.local_path(row[channel]).resolve(strict=True) == path.resolve(strict=True), "Original step log relocated")
            payload = inputs.read_reference(row[channel])
            inputs.bound({"path": row[channel], "sha256": old.sha(payload)})
    require(previous <= stamp(terminal["errors"][0]["utc"]), "Original error predates completed measurement")
    bindings = terminal["input_bindings"]
    require(isinstance(bindings, list) and sum(row == source for row in bindings) == 1,
            "Exactly one original executed self-source binding required")
    for binding in bindings:
        # This one source path now contains the reviewed continuation. Preserve
        # its original reference and verify the exact executed bytes in archive.
        inputs.bound(archive_binding if binding == source else binding)
    require(terminal["closure_audit"] in bindings, "Original saved closure audit binding missing")
    return {"terminal_source_original_reference": source, "executed_source_archive": archive_binding,
            "original_step_count": 7, "original_failure_preserved": True}


def verify_after28_products(old, p, terminal, inputs, v):
    summary_binding = {"path": str(p["sizes"] / "summary.json"), "sha256": AFTER28_SUMMARY_SHA}
    require(summary_binding in terminal["input_bindings"], "Original terminal does not bind the actual28 summary")
    measured = inputs.json(summary_binding)
    require(measured.get("planned_count") == measured.get("measured_count") == 28
            and measured.get("payload_content_reads") is False and measured.get("capacity_admission_performed") is False
            and isinstance(measured.get("receipts"), list) and len(measured["receipts"]) == 28
            and isinstance(measured.get("small_input_bindings"), dict) and len(measured["small_input_bindings"]) == 690,
            "Original complete28/690 measurement required")
    seen = set()
    for binding in measured["receipts"]:
        path = v.local_path(binding["path"]).resolve(strict=True)
        require(path.parent == p["sizes"].resolve(strict=True) and path not in seen, "Original size receipt set differs")
        seen.add(path)
        inputs.json(binding)
    for path, item in measured["small_input_bindings"].items():
        require(set(item) == {"sha256", "bag_metadata"} and type(item["bag_metadata"]) is bool,
                "Original measured small-input declaration differs: " + path)
        inputs.bound({"path": path, "sha256": item["sha256"]})
    require(all(path in measured["small_input_bindings"]
                and measured["small_input_bindings"][path]["sha256"] == fixed["sha256"]
                for path, fixed in AFTER28_LARGE_JSON.items()), "Original exact two large-input declarations differ")
    for relative, pin in old.TOOL_PINS.items():
        inputs.bound({"path": str(p["tools"] / relative), "sha256": pin})
        index = list(old.TOOL_PINS).index(relative)
        inputs.bound({"path": str(p["receipt"] / ("tool_" + str(index) + ".stdout.log")), "sha256": pin})
    return {"summary": summary_binding, "verified_receipts": 28, "verified_small_input_bindings": 690,
            "large_identity_json_count": 2, "repeated_measurement_invocations": 0, "repeated_tool_copy_invocations": 0}


def run_after28(*, reviewed_source_sha256):
    require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == INPUT_NAMES, "Actual collector07 registration required")
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
            "Run explicitly inside existing UAVHumble22; no WSL launcher exists")
    require(reviewed_source_sha256 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == reviewed_source_sha256,
            "Exact independently reviewed continuation source SHA required")
    old = fixed_module(OLD08, OLD08_SHA)
    base = old.fixed_module(old.BASE, old.BASE_SHA)
    p = new_paths(old)
    with base.linux_idle_guard() as guard:
        archive_binding = base.binding(EXECUTED_SOURCE_ARCHIVE)
        require(archive_binding["sha256"] == EXECUTED_SOURCE_SHA, "Exact executed source archive required")
        raw = EXECUTED_SOURCE_ARCHIVE.read_bytes()
        original = types.ModuleType("after28_preserved_executed_measurement")
        original.__file__ = str(Path(__file__).resolve())
        exec(compile(raw, original.__file__, "exec"), original.__dict__)
        audit, previous_inputs = closure_audit(REGISTERED_INPUTS, old)
        collector = fixed_module(REGISTERED_INPUTS["collector"]["path"], REGISTERED_INPUTS["collector"]["sha256"])
        v = collector.review_library()
        inputs = after28_inputs(v, previous_inputs)
        inputs.bound(archive_binding)
        terminal = inputs.json(AFTER28_TERMINAL)
        require(v.local_path(AFTER28_TERMINAL["path"]).resolve(strict=True)
                == (p["receipt"] / "terminal.json").resolve(strict=True), "Original stopped terminal relocated")
        proof = validate_after28_terminal(terminal, original, old, p, inputs, v, guard, archive_binding, datetime.now(timezone.utc))
        saved = inputs.json(terminal["closure_audit"])
        require({k: x for k, x in saved.items() if k != "created_utc"}
                == {k: x for k, x in audit.items() if k != "created_utc"}, "Fresh full16 closure differs from original")
        require(v.timestamp(saved["created_utc"], datetime.now(timezone.utc))
                <= v.timestamp(terminal["started_utc"], datetime.now(timezone.utc))
                <= v.timestamp(terminal["finished_utc"], datetime.now(timezone.utc))
                <= v.timestamp(audit["created_utc"], datetime.now(timezone.utc)), "Saved/fresh closure chronology differs")
        reused = verify_after28_products(old, p, terminal, inputs, v)
        q = dict(p)
        q["receipt"] = p["receipt"].with_name(p["receipt"].name + "_continue_after28_01")
        q["inventory"] = q["receipt"] / "physical_inventory.json"
        for path in (q["receipt"], p["calibration"], p["budget"].parent, p["inventory"]):
            require(not path.exists() and not path.is_symlink() and path.parent.is_dir(),
                    "Continuation output conflict; no overwrite or retry: " + str(path))
        own = base.binding(Path(__file__).resolve())
        require(own["sha256"] == reviewed_source_sha256, "Continuation source changed before starting")
        inputs.bound(own)
        inputs.unchanged()
        q["receipt"].mkdir(exist_ok=False)
        old.write_new(q["receipt"] / "full16_closure_audit.json", audit)
        closure = base.binding(q["receipt"] / "full16_closure_audit.json")
        inputs.bound(closure)
        state = {"schema_version": 1, "scope": AFTER28_SCOPE, "status": "STARTED_EXPLICIT_AFTER28_CONTINUATION",
            "started_utc": old.utc(), "source": own, "owner_identity": old.linux_identity(os.getpid()),
            "actual_original_bindings": REGISTERED_INPUTS, "original_failure_terminal": AFTER28_TERMINAL,
            "original_execution_window": {key: terminal[key] for key in ("started_utc", "finished_utc", "returncode", "errors", "steps")},
            "preserved_executed_source": proof, "reused_actual28": reused, "closure_audit": closure,
            "guard": guard, "commit": old.COMMIT, "steps": [], "interruptions": [], "errors": [],
            "inventory_output_choice": {"original_uncreated_path": str(p["inventory"]), "actual_new_path": str(q["inventory"]),
                "reason": "Keep the entire original stopped receipt unchanged; calibration and budget retain their original uncreated paths."},
            "automatic_retry": False, "formal_admission": False,
            "claim_boundary": "Preserved original failed seven-step window plus actual fresh idle/five-step continuation, never a fabricated successful12."}
        environment = {**os.environ, "HUMBLE22_PROJECT_ROOT": str(p["frozen"]),
            "HUMBLE22_ROS_GZ_WS": "/root/uav_humble22/ros_gz_shutdown_A01_ws",
            "HUMBLE22_PX4_ROOT": "/root/uav_humble22/PX4-Autopilot-v4mag", "TMPDIR": "/tmp", "STAGE1_TRANSIENT_DIR": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        try:
            old.write_new(q["receipt"] / "started.json", state)
            stdout = old.child_step(q, state, "native_idle", ["bash", p["idle"]], inputs, environment=environment)
            idle = old.bound_generated(inputs, stdout)
            require(idle.get("kind") == "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY" and idle.get("matching_processes") == [],
                    "Actual fresh native idle query did not pass")
            for label, argv in old.workflow_commands(q)[1:]:
                stdout = old.child_step(q, state, label, argv, inputs, environment=environment)
                if label == "physical_inventory":
                    inventory = old.bound_generated(inputs, q["inventory"])
                    require(inventory.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
                            and inventory.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION" and inventory.get("volumes"),
                            "Actual physical inventory required")
                elif label.endswith("_velocity_export"):
                    require(old.bound_generated(inputs, stdout).get("status") == "PASS", "Original named export evidence failed")
                elif label == "R0_candidate":
                    candidate = old.bound_generated(inputs, p["calibration"] / "R0_candidate.json")
                    require(candidate.get("status") == "CANDIDATE_NOT_REGISTERED" and candidate.get("scope") == "DEVELOPMENT_ONLY"
                            and set(candidate["classes"]) == {"person", "car"}, "Original development R0 candidate required")
                elif label == "full280_budget":
                    budget = old.bound_generated(inputs, p["budget"])
                    old.positive_budget(budget, base.binding(p["core"]), base.binding(p["extension"]))
                    for path, pin in budget["provenance"]["small_inputs_sha256"].items():
                        inputs.bound({"path": path, "sha256": pin})
            require(not p["inventory"].exists(), "Original stopped receipt must remain untouched")
            inputs.unchanged()
            state["status"] = "COMPLETED_AFTER28_CONTINUATION_CALIBRATION_BUDGET_NOT_ADMISSION"
        except BaseException as error:
            state["status"] = "STOPPED_AFTER28_CONTINUATION_PARTIAL_OUTPUTS_RETAINED"
            state["errors"].append({"utc": old.utc(), "error": f"{type(error).__name__}: {error}"})
        finally:
            state["finished_utc"] = old.utc()
            state["returncode"] = 0 if state["status"].startswith("COMPLETED_AFTER28_") else 2
            state["input_bindings"] = sorted(inputs.seen.values(), key=lambda row: row["path"])
            old.write_new(q["receipt"] / "terminal.json", state)
        return state


def run():
    require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == INPUT_NAMES,
            "Production disabled; actual completed collector07 inputs are not registered")
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
            "Run explicitly inside existing UAVHumble22; no WSL launcher exists")
    old = fixed_module(OLD08, OLD08_SHA)
    base = old.fixed_module(old.BASE, old.BASE_SHA)
    p = new_paths(old)
    with base.linux_idle_guard() as guard:
        audit, inputs = closure_audit(REGISTERED_INPUTS, old)
        for path, pin in ((OLD08, OLD08_SHA), (old.BASE, old.BASE_SHA),
                          (p["core"], old.CORE_SHA), (p["extension"], old.EXTENSION_SHA),
                          (p["registry"], old.REGISTRY_SHA), (p["native"], old.NATIVE_SHA),
                          (p["assumptions"], old.ASSUMPTIONS_SHA), (p["idle"], old.IDLE_SHA),
                          (p["audit_guard"], old.TOOL_PINS["tools/reliability_v4_guard.py"]),
                          (p["frozen"] / "results/humble54_core12_owner01/owner_terminal.json", "966b51475b492b4975d13fddd7b36e54fb1ecfce78580be1ba13bcda063c731c")):
            inputs.bound({"path": str(path), "sha256": pin})
        for name, pin in old.FROZEN_PINS.items():
            inputs.bound({"path": str(p["frozen"] / name), "sha256": pin})
        self_binding = base.binding(Path(__file__).resolve())
        inputs.bound(self_binding)
        old.fresh_outputs(p)
        inputs.unchanged()
        p["receipt"].mkdir(exist_ok=False)
        old.write_new(p["receipt"] / "full16_closure_audit.json", audit)
        closure_binding = base.binding(p["receipt"] / "full16_closure_audit.json")
        inputs.bound(closure_binding)
        state = {"schema_version": 1, "scope": SCOPE, "status": "STARTED_DIRECT_MEASUREMENT",
                 "started_utc": old.utc(), "source": self_binding, "owner_identity": old.linux_identity(os.getpid()),
                 "actual_original_bindings": REGISTERED_INPUTS, "closure_audit": closure_binding,
                 "guard": guard, "commit": old.COMMIT, "steps": [], "interruptions": [], "errors": [],
                 "automatic_retry": False, "formal_admission": False,
                 "claim_boundary": "Actual28, two original named velocity exports, development R0 and full280 budget only."}
        environment = {**os.environ, "HUMBLE22_PROJECT_ROOT": str(p["frozen"]),
                       "HUMBLE22_ROS_GZ_WS": "/root/uav_humble22/ros_gz_shutdown_A01_ws",
                       "HUMBLE22_PX4_ROOT": "/root/uav_humble22/PX4-Autopilot-v4mag", "TMPDIR": "/tmp", "STAGE1_TRANSIENT_DIR": "/tmp",
                       "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        try:
            old.write_new(p["receipt"] / "started.json", state)
            idle = old.child_step(p, state, "native_idle", ["bash", p["idle"]], inputs, environment=environment)
            query = old.bound_generated(inputs, idle)
            require(query.get("kind") == "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY" and query.get("matching_processes") == [], "Actual native idle query did not pass")
            p["tools"].mkdir(exist_ok=False)
            (p["tools"] / "tools").mkdir()
            for index, (relative, pin) in enumerate(old.TOOL_PINS.items()):
                stdout = old.child_step(p, state, "tool_" + str(index), ["git", "-C", ROOT, "show", old.COMMIT + ":" + relative], inputs, environment=environment)
                raw = inputs.read_reference(str(stdout))
                require(old.sha(raw) == pin, "Fixed original storage tool changed: " + relative)
                with (p["tools"] / relative).open("xb") as handle:
                    handle.write(raw)
                inputs.bound({"path": str(p["tools"] / relative), "sha256": pin})
            for label, argv in old.workflow_commands(p):
                stdout = old.child_step(p, state, label, argv, inputs, environment=environment)
                if label == "measure_actual28":
                    measured = old.bound_generated(inputs, p["sizes"] / "summary.json")
                    require(measured.get("planned_count") == measured.get("measured_count") == 28 and len(measured["receipts"]) == 28
                            and measured.get("payload_content_reads") is False and measured.get("capacity_admission_performed") is False,
                            "Original complete actual28 measurement required")
                    for binding in measured["receipts"]:
                        inputs.bound(binding)
                    for path, item in measured["small_input_bindings"].items():
                        inputs.bound({"path": path, "sha256": item["sha256"]})
                elif label == "physical_inventory":
                    inventory = old.bound_generated(inputs, p["inventory"])
                    require(inventory.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
                            and inventory.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION" and inventory.get("volumes"), "Actual physical inventory required")
                elif label.endswith("_velocity_export"):
                    require(old.bound_generated(inputs, stdout).get("status") == "PASS", "Original named export evidence failed")
                elif label == "R0_candidate":
                    calibration = old.bound_generated(inputs, p["calibration"] / "R0_candidate.json")
                    require(calibration.get("status") == "CANDIDATE_NOT_REGISTERED" and calibration.get("scope") == "DEVELOPMENT_ONLY"
                            and set(calibration["classes"]) == {"person", "car"}, "Original development R0 candidate required")
                elif label == "full280_budget":
                    budget = old.bound_generated(inputs, p["budget"])
                    old.positive_budget(budget, base.binding(p["core"]), base.binding(p["extension"]))
                    for path, pin in budget["provenance"]["small_inputs_sha256"].items():
                        inputs.bound({"path": path, "sha256": pin})
            inputs.unchanged()
            state["status"] = "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION"
        except BaseException as error:
            state["status"] = "STOPPED_DIRECT_MEASUREMENT_PARTIAL_OUTPUTS_RETAINED"
            state["errors"].append({"utc": old.utc(), "error": f"{type(error).__name__}: {error}"})
        finally:
            state["finished_utc"] = old.utc()
            state["returncode"] = 0 if state["status"] == "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION" else 2
            state["input_bindings"] = sorted(inputs.seen.values(), key=lambda row: row["path"])
            old.write_new(p["receipt"] / "terminal.json", state)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--continue-after28", action="store_true", help="Only the authentic seven-step size-binding stop; preserve the original failed window")
    parser.add_argument("--reviewed-source-sha256", help="Exact reviewed source SHA required for explicit continuation")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "PREPARATION_DESCRIPTION_ONLY_NOT_STARTED", "production_enabled": PRODUCTION_ENABLED,
                          "registered_inputs": sorted(REGISTERED_INPUTS), "required_actual_inputs": sorted(INPUT_NAMES),
                          "original_runner08_sha256": OLD08_SHA,
                          "continue_after28_requested": args.continue_after28,
                          "sequence": ["new collector07 actual full16 closure", "locked native idle", "fixed original tools", "measure_actual28", "physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget"],
                          "automatic_retry": False, "stage_build_formal": "NOT_AVAILABLE"}))
        return 0
    try:
        require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == INPUT_NAMES,
                "Production disabled; actual completed collector07 inputs are not registered")
        result = run_after28(reviewed_source_sha256=args.reviewed_source_sha256) if args.continue_after28 else run()
        print(json.dumps({"status": result["status"], "returncode": result["returncode"]}))
        return result["returncode"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "REFUSED_OR_STOPPED_NO_RETRY", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
