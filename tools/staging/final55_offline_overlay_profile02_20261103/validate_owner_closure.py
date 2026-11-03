"""Validate actual owner04 small evidence; never run a native command or stage.

Production full validation stays disabled until root reviews real closure pins.
Synthetic callers supply in-memory evidence; no arbitrary profile CLI exists.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re


HERE = Path(__file__).resolve().parent
PRODUCTION_FULL_VALIDATION_ENABLED = False
LAUNCH_BINDINGS_SHA256 = "19cf8d4dd1fba4c35570ec0fcdd5fa2210366f751cb67121a7bc608bc0b42036"
# No closure binding is instantiated before the real run closes and root reviews it.
PRODUCTION_CLOSURE_PROFILE = {}
MAX_SMALL_BYTES = 2 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
DESCRIPTION_FIELDS = (
    "scope", "claim_boundary", "pins", "task_id", "native_owner", "owner_unc",
    "canonical_native_plan", "monitor_output", "receipt_output", "sources",
    "native_command", "monitor_command", "power_flags", "power_scope",
    "global_power_policy_changed", "automatic_retry",
)
ARTIFACT_NAMES = {
    "started.json", "state.json", "first_monitor_state.json", "first_native_state.json",
    "native_terminal.json", "final_monitor_state.json", "monitor_stdout.log", "monitor_stderr.log",
}
SOURCE_NAMES = {"launcher", "monitor", "collector", "entry", "plan"}
ALLOWED_ENGINEERING = {"PASS", "FAIL", "INCOMPLETE_EVIDENCE"}
SHUTTER_CHECKS = ("recorded_close_event", "shutter_close_service_succeeded", "shutter_open_service_succeeded", "shutter_close_ack_before_open_request")
LONG_SAFE_CHECKS = ("lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion", "sustained_low_speed_after_hover",
                    "no_automatic_recovery_after_long_loss", "no_tracking_control_before_reselection_after_long_loss")
BEHAVIOR_CHECKS = {
    "short": ("detector_interruption_observed", "prediction_observed", "no_loss_during_short_occlusion", "identity_preserved_on_observed_recovery"),
    "long": ("detector_interruption_observed", "prediction_observed", "sustained_tracking_after_reselection"),
}
APPROVED_NESTED17 = tuple("ros2_ws/src/uav_tracking_nodes/build/lib/" + name for name in (
    "uav_tracking/__init__.py", "uav_tracking/control/__init__.py", "uav_tracking/control/follow_controller.py",
    "uav_tracking/control/gimbal_controller.py", "uav_tracking/core/__init__.py", "uav_tracking/core/geometry.py",
    "uav_tracking/core/kalman.py", "uav_tracking/core/models.py", "uav_tracking/core/target_manager.py",
    "uav_tracking/experiments.py", "uav_tracking/simulation.py", "uav_tracking_nodes/__init__.py",
    "uav_tracking_nodes/controller_node.py", "uav_tracking_nodes/detector_node.py", "uav_tracking_nodes/state_estimator_node.py")) + (
    "ros2_ws/src/uav_tracking_px4_adapter/build/lib/uav_tracking_px4_adapter/__init__.py",
    "ros2_ws/src/uav_tracking_px4_adapter/build/lib/uav_tracking_px4_adapter/adapter_node.py")


class Refused(ValueError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def integer(value, label, *, zero=False):
    require(type(value) is int and (value == 0 if zero else value > 0), "Invalid integer " + label)
    return value


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def content_digest(value, field):
    return sha(canonical({key: item for key, item in value.items() if key != field}))


def parse(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    result = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(Refused("Nonfinite JSON")))
    require(isinstance(result, dict), "JSON object required")
    return result


def timestamp(value, now):
    require(isinstance(value, str), "Missing actual UTC")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None and result.utcoffset() == timedelta(0) and result <= now,
            "UTC must be actual, explicit UTC and not future")
    return result


def path_key(value):
    require(isinstance(value, str) and value != "", "Path string required")
    windows = bool(re.match(r"[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")
    path = PureWindowsPath(value) if windows else PurePosixPath(value)
    require(path.is_absolute() and ".." not in path.parts, "Absolute canonical reference required")
    return path.as_posix()


def same_path(left, right):
    return path_key(left) == path_key(right)


def join(root, name):
    require(isinstance(name, str) and PurePosixPath(name).as_posix() == name
            and not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
            and "\\" not in name, "Unsafe relative evidence path")
    windows = bool(re.match(r"[A-Za-z]:[\\/]", root)) or root.startswith("\\\\")
    return str((PureWindowsPath(root) if windows else PurePosixPath(root)) / name)


def mounted(value):
    path = PureWindowsPath(value)
    require(re.fullmatch(r"[A-Za-z]:", path.drive) is not None, "Drive-qualified Windows source required")
    return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


def windows_mounted_reference(reference):
    require(reference.startswith("/mnt/") and len(reference) > 7
            and reference[5].isalpha() and reference[6] == "/", "Unsupported mount")
    return reference[5].upper() + ":/" + reference[7:]


def local_path(reference):
    path_key(reference)
    if os.name == "nt" and reference.startswith("/mnt/"):
        path = Path(windows_mounted_reference(reference))
    elif os.name == "nt" and reference.startswith("/root/"):
        path = Path("\\\\wsl.localhost\\UAVHumble22" + reference.replace("/", "\\"))
    elif os.name != "nt" and re.match(r"[A-Za-z]:[\\/]", reference):
        path = Path(mounted(reference))
    elif os.name != "nt" and reference.startswith("\\\\wsl.localhost\\UAVHumble22\\"):
        path = Path("/" + reference.split("UAVHumble22\\", 1)[1].replace("\\", "/"))
    else:
        path = Path(reference)
    return path


def local_small_read(reference):
    """Read one small file; caller uses only authenticated explicit references."""
    path = local_path(reference)
    require(path.is_file() and not path.is_symlink(), "Ordinary small file required")
    before = path.stat()
    require(before.st_size <= MAX_SMALL_BYTES, "Refusing large input")
    payload = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Input changed while reading")
    return payload


class Inputs:
    def __init__(self, read):
        self.read = read
        self.seen = {}
        self.results_aliases = {}

    def bind_plan_results_alias(self, plan):
        """Bind only this authenticated plan's frozen-root/results alias.

        Windows UNC does not reliably traverse the Linux results symlink.
        Preserve original references/digests and redirect only that exact
        results subtree to the canonical results_root saved in the plan.
        Other /root paths, including external owners, are not redirected.
        """
        require(plan.get("plan_sha256") == content_digest(plan, "plan_sha256"), "Authenticated plan digest required for results alias")
        frozen = PurePosixPath(plan["frozen_root"])
        store = PurePosixPath(plan["results_root"])
        output = PurePosixPath(plan["output"])
        require(frozen.is_absolute() and store.is_absolute() and ".." not in frozen.parts and ".." not in store.parts
                and re.match(r"^/mnt/[a-z]/", str(store)) and output.parent == store,
                "Canonical authenticated plan results mapping required")
        alias, canonical_store = str(frozen / "results"), str(store)
        require(alias != canonical_store and (alias not in self.results_aliases or self.results_aliases[alias] == canonical_store),
                "Conflicting frozen results alias")
        self.results_aliases[alias] = canonical_store

    def read_reference(self, reference):
        for alias, store in self.results_aliases.items():
            if reference.startswith(alias + "/"):
                relative = reference[len(alias) + 1:]
                return self.read(join(store, relative))
        return self.read(reference)

    def bound(self, binding):
        require(set(binding) == {"path", "sha256"} and isinstance(binding["sha256"], str)
                and HEX.fullmatch(binding["sha256"]), "Actual fixed file binding required")
        path_key(binding["path"])
        payload = self.read_reference(binding["path"])
        require(isinstance(payload, bytes) and len(payload) <= MAX_SMALL_BYTES
                and sha(payload) == binding["sha256"], "Raw evidence/source SHA differs: " + binding["path"])
        key = path_key(binding["path"])
        require(key not in self.seen or self.seen[key] == binding, "Conflicting bindings for one path")
        self.seen[key] = binding.copy()
        return payload

    def json(self, binding):
        return parse(self.bound(binding))

    def unchanged(self):
        for binding in self.seen.values():
            require(sha(self.read_reference(binding["path"])) == binding["sha256"], "Evidence changed during validation")


def windows_identity(value, now):
    integer(value.get("pid"), "Windows PID")
    token = value.get("start_token")
    require(isinstance(token, str) and re.fullmatch(r"windows_filetime:[1-9][0-9]{0,19}", token),
            "Creation-bound Windows handle identity required")
    require(value.get("alive") is True and not value.get("error"), "Identity must be captured alive without error")
    created = timestamp(value.get("created_utc"), now)
    # The generic monitor used floating seconds, so allow one microsecond of
    # conversion rounding, never an unrelated creation timestamp.
    creation = int(token.split(":")[1])
    expected = datetime.fromtimestamp((creation - 116444736000000000) / 1e7, timezone.utc)
    require(abs((created - expected).total_seconds()) <= 0.000001, "FILETIME and creation UTC differ")
    return created


def linux_identity(value):
    integer(value.get("pid"), "Linux PID")
    integer(value.get("start_ticks"), "Linux start ticks")
    require(isinstance(value.get("boot_id"), str) and re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value["boot_id"]), "Linux boot identity required")


def task_identity(state, desc, monitor, wsl, now, *, finished):
    require(state.get("monitor_process") == monitor and state.get("sources") == desc["sources"],
            "Monitor creation identity or sources differ")
    task = state["task"]
    require(task.get("id") == desc["task_id"] and task.get("label") == desc["task_id"]
            and task.get("phase") == "simulation" and task.get("monitor_kind") == "owned_child"
            and task.get("process") == wsl and state.get("tasks") == [task], "Monitor task/owned process differs")
    started = timestamp(task.get("started_utc"), now)
    require(windows_identity(wsl, now) <= started, "Task precedes actual owned process creation")
    timestamp(state.get("heartbeat_utc"), now)
    if finished:
        integer(task.get("returncode"), "Monitor task exit", zero=True)
        require(started <= timestamp(task.get("finished_utc"), now), "Monitor task finish precedes start")
    else:
        require(task.get("finished_utc") is None and task.get("returncode") is None, "Early monitor state is already terminal")
    return task


def snapshot_capture_contract(profile, inputs, plan):
    """Derive original54 captures from authenticated small snapshot metadata.

    The capture has 204 entries: scanner185 + named historical17 + explicit
    DDS + the trial's selected model. It is distinct from registered source308.
    No model, source tree or build directory is read or changed here.
    """
    contract = inputs.json(profile["snapshot_audit_contract"])
    require(contract.get("kind") == "RELIABILITY_V4_FROZEN_SNAPSHOT_AUDIT_CONTRACT"
            and contract.get("rule") == "ORIGINAL_RUN_STAGE1_PY_SH_MSG_SCAN_PLUS_SELECTED_MODEL_AND_EXPLICIT_DDS"
            and contract.get("frozen_root") == plan["frozen_root"], "Original snapshot-audit contract differs")
    core = inputs.json({key: contract["core_plan"][key] for key in ("path", "sha256")})
    require(core.get("plan_sha256") == contract["core_plan"]["plan_sha256"] == content_digest(core, "plan_sha256")
            and core.get("mode") == "PROBE" and core.get("source_hashes") == plan["source_hashes"],
            "Snapshot contract/core registration differs")
    before = inputs.json(contract["source_before"])
    entries = before["entries"]
    require(len(entries) == 1585 and all(row.get("kind") == "file" and HEX.fullmatch(row.get("sha256", "")) for row in entries.values()),
            "Original exact complete-map schema/count differs")
    scanned = {name: row["sha256"] for name, row in entries.items()
               if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and PurePosixPath(name).suffix in {".py", ".sh", ".msg"}}
    nested = {name for name in scanned if "/build/" in name}
    require(nested == set(APPROVED_NESTED17) and len(scanned) == 202, "Original scanner185 plus named historical17 differs")
    registered = {name: value for name, value in scanned.items() if name not in nested}
    require(len(registered) == 185 and all(plan["source_hashes"].get(name) == value for name, value in registered.items()),
            "Original scanner185 differs from registered flight source")
    class_contract = profile["class_model_contract"]
    models = {}
    for trial in plan["trials"]:
        target_class = trial["target_class"]
        require(target_class in class_contract, "Unknown capture target class")
        expected_class = class_contract[target_class]
        model = trial["model"]
        require(model == expected_class["model"] == plan["protocol"]["resources"][target_class]["model"]
                and plan["model_hashes"].get(model) == expected_class["model_sha256"],
                "Trial class/model/protocol/model-SHA selection differs")
        models[model] = expected_class["capture_sha256"]
    result = {}
    for model in models:
        require(not PurePosixPath(model).is_absolute() and ".." not in PurePosixPath(model).parts
                and "\\" not in model and model.startswith("models/"), "Selected model must be a registered relative path")
        expected = {**scanned, **{name: entries[name]["sha256"] for name in ("config/dds_runtime_humble22.json", model)}}
        require(len(expected) == 204 and len(set(expected) & set(plan["source_hashes"])) == 187
                and set(expected) - set(plan["source_hashes"]) == set(APPROVED_NESTED17)
                and all(plan["source_hashes"][name] == value for name, value in expected.items() if name in plan["source_hashes"]),
                "Exact original capture204/registered308 relation differs")
        raw_pin = models[model]
        require(isinstance(raw_pin, str) and HEX.fullmatch(raw_pin), "Actual per-model capture raw SHA required")
        result[model] = {"entries": expected, "sha256": raw_pin}
    return result


def slot_evaluation_integrity(inputs, trial, terminal, now):
    kinds = {"source_clock", "native_startup", "surface_flight", "navigation"}
    specs, entries = trial["evaluations"], terminal["evaluations"]
    require(len(specs) == len(entries) == 4 and {row["kind"] for row in specs} == {row["kind"] for row in entries} == kinds,
            "Original independent evaluator set differs")
    reports = {}
    flight_finished = timestamp(next(row for row in terminal["commands"] if row.get("kind") == "flight")["finished_utc"], now)
    for spec in specs:
        entry = next(row for row in entries if row["kind"] == spec["kind"])
        relative = PurePosixPath(spec["report"]).relative_to(PurePosixPath(trial["directory"])).as_posix()
        raw_sha = terminal["artifact_hashes"][relative]
        require(same_path(entry["report"], spec["report"]) and entry.get("report_sha256") == raw_sha
                and entry.get("error") is None and entry["execution"].get("error") is None
                and entry["execution"].get("command") == spec["command"], "Original evaluator command/report/raw binding differs")
        integer(entry["execution"].get("returncode"), "Original evaluator exit", zero=True)
        require(flight_finished <= timestamp(entry["execution"].get("started_utc"), now)
                <= timestamp(entry["execution"].get("finished_utc"), now)
                <= timestamp(terminal["finished_utc"], now), "Original evaluator chronology differs")
        report = inputs.json({"path": spec["report"], "sha256": raw_sha})
        verdict = report["acceptance"]["result"] if spec["kind"] == "surface_flight" else report["evaluation_status"]
        require(entry.get("result") == entry.get("reported_verdict") == verdict
                and verdict in {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "RECORDED_WITH_CENSORED_FAILURES"},
                "Original evaluator is pending/invalid or contradicts its report")
        if spec["kind"] in {"source_clock", "native_startup"}:
            require(verdict == "PASS", "Source-clock/native-startup evidence did not pass")
        reports[spec["kind"]] = report
    surface = reports["surface_flight"]
    acceptance = surface["acceptance"]
    require(acceptance.get("missing_topics") == [] and acceptance.get("clock_timebase_available") is True
            and all(acceptance.get(key) is True for key in ("short_occlusion_recorded", "long_occlusion_recorded", "failed_events_retained"))
            and surface.get("flight_evidence", {}).get("armed_seen") is True and surface["flight_evidence"].get("offboard_seen") is True,
            "Original recording/flight evidence is incomplete")
    integer(acceptance.get("input_read_error_count"), "Original input decode errors", zero=True)
    integer(surface.get("detector", {}).get("invalid_diagnostic_messages"), "Original diagnostic decode errors", zero=True)
    windows = surface["occlusions"]
    require(len(windows) == 2 and {row["kind"] for row in windows} == {"short", "long"}, "Original short/long window set differs")
    for row in windows:
        checks = row["checks"]
        required = (*SHUTTER_CHECKS, *(LONG_SAFE_CHECKS if row["kind"] == "long" else ()))
        require(row.get("complete") is True and all(checks.get(key) is True for key in required), "Original shutter/long-loss safety is incomplete or failed")
        require(all(type(checks.get(key)) is bool for key in BEHAVIOR_CHECKS[row["kind"]]),
                "Unknown behavior evidence retained; a separate named review is required")
    return reports


def validate_slot(inputs, plan, trial, row, capture_contract, now, *, owner_started_utc=None, verify_unchanged=True):
    """Validate one actual original attempt independently of owner chain shape.

    Does not claim owner closure or authorize a continuation. Future owners can
    audit the same preserved attempt without rewriting its engineering result.
    """
    inputs.bind_plan_results_alias(plan)
    expected_marker = join(plan["output"], "slots/" + trial["id"] + ".started.json")
    expected_terminal = join(plan["output"], "slots/" + trial["id"] + ".json")
    require(same_path(row["original_marker"]["path"], expected_marker)
            and same_path(row["original_terminal"]["path"], expected_terminal), "Slot references another plan or original attempt")
    marker, terminal = inputs.json(row["original_marker"]), inputs.json(row["original_terminal"])
    require(marker.get("id") == terminal.get("id") == trial["id"]
            and marker.get("plan_sha256") == terminal.get("plan_sha256") == plan["plan_sha256"]
            and marker.get("flight_command") == trial["flight_command"]
            and terminal.get("name") == trial["name"] and marker.get("started_utc") == terminal.get("started_utc") == row["original_started_utc"]
            and terminal.get("finished_utc") == row["original_finished_utc"], "Original START/terminal/plan identity differs")
    require(terminal.get("record_sha256") == row.get("record_sha256") == content_digest(terminal, "record_sha256")
            and row.get("terminal_sha256") == row["original_terminal"]["sha256"], "Slot terminal digest/raw binding differs")
    require(terminal.get("status") in ALLOWED_ENGINEERING and terminal.get("engineering_result") == terminal["status"] == row.get("original_status")
            and terminal.get("execution_status") == "COMPLETED" and terminal.get("infrastructure_stop") is False
            and terminal.get("infrastructure", {}).get("stop") is False and terminal.get("cleanup", {}).get("residual_processes") == []
            and terminal.get("runtime_configuration", {}).get("errors") == []
            and row.get("unobserved_checks") == [], "Original slot is interrupted/pending/unknown/unsafe")
    integer(terminal.get("flight_exit_code"), "Flight exit", zero=True)
    flight = [command for command in terminal["commands"] if command.get("kind") == "flight"]
    require(len(flight) == 1 and flight[0].get("command") == trial["flight_command"] and flight[0].get("error") is None,
            "Original flight command/error differs")
    integer(flight[0].get("returncode"), "Original flight command exit", zero=True)
    start_time, finish_time = timestamp(marker["started_utc"], now), timestamp(terminal["finished_utc"], now)
    require(start_time <= timestamp(flight[0]["started_utc"], now) <= timestamp(flight[0]["finished_utc"], now) <= finish_time,
            "Original flight chronology differs")
    if owner_started_utc is not None:
        require(timestamp(owner_started_utc, now) <= start_time, "Original attempt precedes its executing owner")
    expected_capture = capture_contract[trial["model"]]
    for relative in ("recording_closure.json", "bag_integrity.json", "configuration/source_sha256.json"):
        raw_sha = terminal["artifact_hashes"][relative]
        value = inputs.json({"path": join(trial["directory"], relative), "sha256": raw_sha})
        if relative == "configuration/source_sha256.json":
            require(raw_sha == expected_capture["sha256"] and value == expected_capture["entries"],
                    "Actual capture differs from exact original204 per-model snapshot contract")
        else:
            require(value.get("status") == "PASS", "Recording closure/integrity failed")
    runtime = terminal["runtime_configuration"]
    for relative, field in (("run_config.json", "run_config_sha256"), ("configuration/runtime_parameters.yaml", "runtime_parameters_sha256")):
        require(terminal["artifact_hashes"][relative] == runtime[field], "Runtime metadata binding differs")
        inputs.bound({"path": join(trial["directory"], relative), "sha256": runtime[field]})
    slot_evaluation_integrity(inputs, trial, terminal, now)
    if verify_unchanged:
        inputs.unchanged()
    return {"id": trial["id"], "original_status": terminal["status"], "marker": row["original_marker"],
            "terminal": row["original_terminal"], "started_utc": marker["started_utc"], "finished_utc": terminal["finished_utc"]}


def validate_launch(profile, read=local_small_read, *, now=None, inputs=None):
    now = datetime.now(timezone.utc) if now is None else now
    inputs = Inputs(read) if inputs is None else inputs
    sources = profile["source_files"]
    require(set(sources) == SOURCE_NAMES, "All five fixed source/plan files required")
    for binding in sources.values():
        inputs.bound(binding)
    plan = inputs.json(sources["plan"])
    require(plan.get("plan_sha256") == profile["plan_digest"] == content_digest(plan, "plan_sha256")
            and plan.get("mode") == "EXTENSION_PROBE" and plan.get("selected_seeds") == [4]
            and len(plan["trials"]) == 16 and len({row["id"] for row in plan["trials"]}) == 16,
            "Fixed complete probe02 registration differs")
    require(sha(canonical(plan["source_hashes"])) == profile["source_digest"], "Flight/source registration differs")
    files = profile["launch_files"]
    require(set(files) == {"started", "first_monitor", "first_native"}, "Three actual fixed launch files required")
    started = inputs.json(files["started"])
    first_monitor = inputs.json(files["first_monitor"])
    first_native = inputs.json(files["first_native"])
    desc = {key: started[key] for key in DESCRIPTION_FIELDS}
    require(desc == profile["description"], "Fixed actual invocation description differs")
    require(desc["pins"] == {key: value for key, value in sources.items() if key != "launcher"}
            and started.get("launcher_source") == sources["launcher"], "Actual source pins differ")
    require(desc["scope"] == "WINDOWS_OWNER_OF_PINNED_NEW_COMPLETE_DEVELOPMENT_MATRIX"
            and desc["automatic_retry"] is False and desc["global_power_policy_changed"] is False
            and desc["power_flags"] == 0x80000003, "Wrong owner/retry/power scope")
    require(same_path(desc["canonical_native_plan"], mounted(sources["plan"]["path"]))
            and desc["sources"] == {"events": join(desc["owner_unc"], "events.jsonl"),
                                    "ledger": join(desc["owner_unc"], "state.json"), "plan": sources["plan"]["path"]},
            "Canonical plan or monitor sources differ")
    native_command = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B",
                      mounted(sources["collector"]["path"]), "--plan", profile["native_plan_alias"],
                      "--entry", mounted(sources["entry"]["path"]), "--after-slot", "__before_first__",
                      "--output", desc["native_owner"], "--execute"]
    require(desc["native_command"] == native_command, "Full16 owned native command differs")
    require(started.get("status") == "STARTING" and started.get("errors") == [], "Actual launch was not clean")
    launcher_created = windows_identity(started["launcher_identity"], now)
    monitor_created = windows_identity(started["monitor_identity"], now)
    launch_time = timestamp(started["started_utc"], now)
    handle_time = timestamp(started["monitor_handle_acquired_utc"], now)
    require(launcher_created <= launch_time <= monitor_created <= handle_time, "Monitor launch/handle chronology differs")
    lease = started["power_lease"]
    integer(lease.get("request_return"), "Power request result")
    require(lease.get("monitor_identity") == started["monitor_identity"] and lease.get("flags") == desc["power_flags"]
            and lease.get("global_power_policy_changed") is False
            and handle_time <= timestamp(lease.get("accepted_utc"), now), "Power lease binding differs")
    wsl = first_monitor["task"]["process"]
    task = task_identity(first_monitor, desc, started["monitor_identity"], wsl, now, finished=False)
    require(handle_time <= timestamp(task["started_utc"], now), "Monitor handle was not acquired before task start")
    linux_identity(first_native["owner_identity"])
    require(first_native.get("owner_pid") == first_native["owner_identity"]["pid"]
            and first_native.get("status") == "RUNNING" and first_native.get("initial_closed") == []
            and first_native.get("collected") == [] and first_native.get("automatic_retry") is False,
            "New matrix launch reused an old prefix or terminal")
    require(first_native.get("owner_source") == {"path": mounted(sources["collector"]["path"]), "sha256": sources["collector"]["sha256"]}
            and first_native.get("plan") == desc["canonical_native_plan"]
            and first_native.get("plan_file_sha256") == sources["plan"]["sha256"]
            and first_native.get("plan_sha256") == profile["plan_digest"]
            and first_native.get("entry_sha256") == sources["entry"]["sha256"], "Early native owner/source/plan differs")
    require(timestamp(task["started_utc"], now) <= timestamp(first_native["started_utc"], now), "Native owner precedes its monitor task")
    return {"inputs": inputs, "plan": plan, "started": started, "first_monitor": first_monitor,
            "first_native": first_native, "description": desc, "now": now}


def validate(profile, read=local_small_read, *, now=None):
    """Read-only validation API; production CLI additionally requires fixed admission.

    Receipt SHA values come only from actual files reviewed by root. Tests use
    explicitly synthetic in-memory bindings, never real process/flight states.
    """
    required = {"outer_terminal", "native_terminal", "monitor_final", "monitor_end", "events"}
    require(set(profile.get("closure_files", {})) == required, "Actual fixed full closure bindings are missing")
    context = validate_launch(profile, read, now=now)
    inputs, plan, started, first_monitor, first_native, desc, now = (
        context[key] for key in ("inputs", "plan", "started", "first_monitor", "first_native", "description", "now"))
    closure = profile["closure_files"]
    outer = inputs.json(closure["outer_terminal"])
    require(outer.get("status") == "COLLECTION_ENDED" and outer.get("closure_verified") is True
            and outer.get("errors") == [] and outer.get("native_collection_status") == "COLLECTION_FINISHED",
            "Owner is pending/faulted or closure is not established")
    for key in DESCRIPTION_FIELDS:
        require(outer.get(key) == desc[key], "Final invocation description changed: " + key)
    for key in ("started_utc", "launcher_source", "launcher_identity", "monitor_identity", "monitor_handle_acquired_utc"):
        require(outer.get(key) == started[key], "Final launch identity/source changed: " + key)
    for key in ("monitor_exit_code", "wsl_exit_code", "monitor_popen_wait_exit_code", "monitor_final_popen_wait_exit_code",
                "monitor_final_handle_exit_code", "wsl_final_handle_exit_code"):
        integer(outer.get(key), key, zero=True)
    artifacts = outer["artifacts"]
    require(set(artifacts) == ARTIFACT_NAMES, "Outer raw artifact set is incomplete or unexpected")
    documents = {}
    for name, expected_sha in artifacts.items():
        payload = inputs.bound({"path": join(desc["receipt_output"], name), "sha256": expected_sha})
        if name.endswith(".json"):
            documents[name] = parse(payload)
    require(documents["started.json"] == started and documents["first_monitor_state.json"] == first_monitor
            and documents["first_native_state.json"] == first_native, "Original launch copies differ")
    native = inputs.json(closure["native_terminal"])
    final_monitor = inputs.json(closure["monitor_final"])
    end = inputs.json(closure["monitor_end"])
    require(native == documents["native_terminal.json"] and final_monitor == documents["final_monitor_state.json"],
            "Original terminal and archived raw copy differ")
    require(closure["native_terminal"]["sha256"] == artifacts["native_terminal.json"] == outer["native_owner_terminal_sha256"]
            and closure["monitor_final"]["sha256"] == artifacts["final_monitor_state.json"], "Raw original/copy SHA differs")
    require(outer.get("wsl_identity") == first_monitor["task"]["process"], "Owned WSL creation identity differs")
    final_task = task_identity(final_monitor, desc, started["monitor_identity"], outer["wsl_identity"], now, finished=True)
    require({key: value for key, value in final_task.items() if key not in {"finished_utc", "returncode"}}
            == {key: value for key, value in first_monitor["task"].items() if key not in {"finished_utc", "returncode"}},
            "Final task differs from actual started task")
    require(end.get("status") == "COMPLETED" and end.get("completion_scope") == "monitored_command"
            and end.get("task") == final_task and end.get("tasks") == [final_task]
            and end.get("evidence_sources") == desc["sources"], "Generic end summary belongs to another task or is not complete")
    end_generated = timestamp(end.get("generated_utc"), now)
    for key in ("owner_identity", "owner_source", "started_utc", "plan", "plan_sha256", "plan_file_sha256", "entry_sha256"):
        require(native.get(key) == first_native[key], "Native owner changed after actual start: " + key)
    require(outer.get("native_owner_identity") == native["owner_identity"] == outer.get("first_native_owner_identity")
            and outer.get("first_native_owner_source") == native["owner_source"]
            and outer.get("first_native_started_utc") == native["started_utc"], "Outer/native early-to-final bindings differ")
    require(native.get("status") == "COLLECTION_FINISHED" and native.get("current_slot") is None
            and native.get("initial_closed") == [] and native.get("automatic_retry") is False
            and not native.get("child_may_still_be_active"), "Native collector is pending/unsafe or reused old slots")
    integer(native.get("returncode"), "Native owner returncode", zero=True)
    integer(native.get("current_child", {}).get("returncode"), "Last owned child returncode", zero=True)
    expected_ids = [trial["id"] for trial in plan["trials"]]
    collected = native["collected"]
    require([row.get("slot_id") for row in collected] == expected_ids and len(set(expected_ids)) == 16
            and type(outer.get("collected_slots")) is int and outer["collected_slots"] == 16,
            "New complete full16 coverage/order differs")
    capture_contract = snapshot_capture_contract(profile, inputs, plan)
    slots = [validate_slot(inputs, plan, trial, row, capture_contract, now, owner_started_utc=native["started_utc"], verify_unchanged=False)
             for trial, row in zip(plan["trials"], collected)]
    event_payload = inputs.bound(closure["events"])
    events = [parse(line) for line in event_payload.splitlines() if line.strip()]
    require(len(events) == 50 and events[0].get("event") == "COLLECTION_STARTED"
            and events[0].get("pending_ids") == expected_ids and events[-1].get("event") == "COLLECTION_FINISHED"
            and type(events[-1].get("collected_slots")) is int and events[-1]["collected_slots"] == 16,
            "Exact full16 actual invocation event set differs")
    event_times = [timestamp(event.get("utc"), now) for event in events]
    require(event_times == sorted(event_times) and all(event.get("scope") == "SUPERVISED_PENDING_COLLECTION" for event in events),
            "Event source or monotonic chronology differs")
    for index, (slot, trial) in enumerate(zip(slots, plan["trials"])):
        start, exit_row, complete = events[1 + 3 * index:4 + 3 * index]
        require([item.get("event") for item in (start, exit_row, complete)] == ["START_SLOT", "CHILD_EXIT", "COMPLETE_SLOT"]
                and all(item.get("slot") == slot["id"] for item in (start, exit_row, complete)), "Slot event order/identity differs")
        integer(start.get("pid"), "Owned single-slot PID")
        require(start.get("command") == ["bash", mounted(profile["source_files"]["entry"]["path"]), slot["id"]]
                and start.get("executed_by_this_owner") is True and complete.get("executed_by_this_owner") is True
                and start.get("event_semantics") == "ACTUAL_CHILD_INVOCATION"
                and complete.get("event_semantics") == "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED"
                and type(start.get("total")) is int and start["total"] == 16
                and type(complete.get("total")) is int and complete["total"] == 16
                and complete.get("status") == slot["original_status"]
                and complete.get("terminal_sha256") == slot["terminal"]["sha256"], "Actual invocation event provenance differs")
        integer(exit_row.get("returncode"), "Actual child event exit", zero=True)
        # Popen precedes START event publication. A scheduled child may write
        # its marker before that event; event order is not launch clock order.
        require(timestamp(slot["finished_utc"], now) <= timestamp(exit_row["utc"], now)
                <= timestamp(complete["utc"], now), "Event/slot completion chronology differs")
    last_child = native["current_child"]
    last_start, last_exit = events[-4], events[-3]
    linux_identity(last_child.get("identity", {}))
    require(last_child.get("pid") == last_start["pid"] == last_child["identity"]["pid"]
            and last_child["identity"]["boot_id"] == native["owner_identity"]["boot_id"]
            and last_child.get("command") == last_start["command"]
            and timestamp(last_child.get("started_utc"), now) <= timestamp(last_start["utc"], now)
            and timestamp(slots[-1]["finished_utc"], now) <= timestamp(last_child.get("finished_utc"), now)
            <= timestamp(last_exit["utc"], now), "Last owned native child identity/command/exit differs")
    native_end = timestamp(native["finished_utc"], now)
    task_end = timestamp(final_task["finished_utc"], now)
    both_closed = timestamp(outer["windows_handles_closed_observation_utc"], now)
    outer_end = timestamp(outer["finished_utc"], now)
    require(timestamp(native["started_utc"], now) <= event_times[0]
            and event_times[-2] <= native_end <= event_times[-1] <= task_end <= both_closed <= outer_end,
            "Collector/event/task/outer closure chronology differs")
    require(task_end <= end_generated <= both_closed, "Generic end-summary generation chronology differs")
    for name in ("monitor", "wsl"):
        acquired = timestamp(outer[name + "_handle_acquired_utc"], now)
        first_exit = timestamp(outer[name + "_first_exit_observed_utc"], now)
        final_exit = timestamp(outer[name + "_final_exit_observed_utc"], now)
        created = windows_identity(outer[name + "_identity"], now)
        # The faster external poll can observe WSL exit before the generic
        # monitor records task.finished_utc on its next one-second poll.
        earliest_exit = native_end if name == "wsl" else task_end
        require(created <= acquired <= timestamp(slots[0]["started_utc"], now)
                and earliest_exit <= first_exit <= both_closed <= final_exit <= outer_end,
                "Creation-bound held-handle chronology differs")
    require(timestamp(first_native["started_utc"], now) <= timestamp(outer["first_native_state_observed_utc"], now)
            <= timestamp(slots[0]["started_utc"], now), "Early native binding was not observed before first slot")
    lease = outer["power_lease"]
    require({key: lease.get(key) for key in started["power_lease"]} == started["power_lease"], "Power lease changed after launch")
    integer(lease.get("release_return"), "Power release result")
    require(both_closed <= timestamp(lease.get("released_utc"), now) <= outer_end, "Power lease released before actual exit")
    require(same_path(closure["outer_terminal"]["path"], join(desc["receipt_output"], "terminal.json"))
            and same_path(closure["native_terminal"]["path"], join(desc["native_owner"], "terminal.json"))
            and same_path(closure["monitor_final"]["path"], join(desc["monitor_output"], "monitor_state.json"))
            and same_path(closure["monitor_end"]["path"], join(desc["monitor_output"], "end_summary.json"))
            and same_path(closure["events"]["path"], join(desc["native_owner"], "events.jsonl")), "Closure references another invocation")
    inputs.unchanged()
    return {"schema_version": 1, "status": "PASS_OWNER_CLOSURE_ONLY_NOT_ENGINEERING_ADMISSION",
            "validated_utc": now.isoformat(), "plan": {**profile["source_files"]["plan"], "plan_sha256": plan["plan_sha256"]},
            "input_bindings": list(inputs.seen.values()), "slot_count": 16, "slots": slots,
            "preserved_engineering_counts": dict(Counter(slot["original_status"] for slot in slots)),
            "protected_roots": [plan["frozen_root"], str(PurePosixPath(plan["output"]).parent), desc["native_owner"],
                                desc["receipt_output"], desc["monitor_output"]],
            "claim_boundary": "Owner execution closure only. Original FAIL/INCOMPLETE remain unchanged. Native idle, cold build, four-slot sensor evidence, navigation28 gates and formal admission are separate."}


def load_production(*, include_closure=False):
    require(HEX.fullmatch(LAUNCH_BINDINGS_SHA256), "Actual launch profile is not fixed")
    payload = (HERE / "actual_launch_bindings.json").read_bytes()
    require(sha(payload) == LAUNCH_BINDINGS_SHA256, "Fixed actual launch profile differs")
    profile = parse(payload)
    project = str(PureWindowsPath(profile["source_files"]["launcher"]["path"]).parents[3])
    profile["snapshot_audit_contract"] = {
        "path": join(project, "tools/diagnostics/safety54_schema_recovery03_archive01/native/snapshot_audit54_contract03.json"),
        "sha256": "0d5bc8770c039615249caeeabd2b18598564a4cf50ae31e4023f4e47ae7a30ef",
    }
    profile["class_model_contract"] = {
        "person": {"model": "models/yolo11n.pt", "model_sha256": "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1",
                   "capture_sha256": "0094a5013801e67fb6ae692cef785b190272708d71bfb0cd4a3349a0eb09ee46"},
        "car": {"model": "models/yolo11m_car_sim_train20_04.pt", "model_sha256": "bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c",
                "capture_sha256": "c003f1b86e56bc548b4a1f50d890950320d879dbf205b7c86c574c427c28009c"},
    }
    if include_closure:
        bindings = parse(Inputs(local_small_read).bound(PRODUCTION_CLOSURE_PROFILE))
        require(bindings.get("schema_version") == 1
                and bindings.get("scope") == "ACTUAL_CLOSURE_BINDINGS_ONLY_NOT_FORMAL_ADMISSION"
                and bindings.get("actual_launch_profile_sha256") == LAUNCH_BINDINGS_SHA256,
                "Actual closure belongs to another launch or is not reviewed")
        profile["closure_files"] = bindings["closure_files"]
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-launch", action="store_true", help="Read actual fixed launch files only; cannot establish closure")
    parser.add_argument("--receipt-output", type=Path, help="Fresh absolute file; only after enabled complete validation")
    args = parser.parse_args(argv)
    try:
        if not args.check_launch:
            require(PRODUCTION_FULL_VALIDATION_ENABLED, "Production full validation disabled until actual fixed closure bindings are reviewed")
        require(not args.check_launch or args.receipt_output is None, "Launch-only check cannot write a closure receipt")
        profile = load_production(include_closure=not args.check_launch)
        if args.check_launch:
            context = validate_launch(profile)
            context["inputs"].unchanged()
            result = {"status": "PASS_ACTUAL_LAUNCH_ONLY_NOT_CLOSURE", "closure_bound": False,
                      "input_bindings": list(context["inputs"].seen.values()), "claim_boundary": "Actual start only; current running states are not closure."}
        else:
            result = validate(profile)
            result["validator_source"] = {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__).read_bytes())}
            if args.receipt_output:
                output = args.receipt_output
                require(output.is_absolute() and not output.exists() and not output.is_symlink() and output.parent.is_dir(), "Fresh absolute receipt file required")
                canonical_output = output.parent.resolve(strict=True) / output.name
                require(all(not canonical_output.is_relative_to(local_path(root)) for root in result["protected_roots"]),
                        "Closure receipt must stay outside frozen and original evidence roots")
                with output.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
                    handle.write("\n")
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, Refused, KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        print(json.dumps({"status": "REFUSED_NO_STAGING_OR_NATIVE_TASK", "error": f"{type(error).__name__}: {error}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
