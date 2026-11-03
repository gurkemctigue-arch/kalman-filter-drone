"""Disabled candidate consuming authentic stopped7 + stopped6 + positive refresh3.

Only read-only evidence checks and the unchanged source-staging core are wired.
No native run, output registration, owner, launcher, retry, build or flight is
enabled by this preparation. A positive budget snapshot is not current admission.
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
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_ENABLED = False
REGISTERED_INPUTS = {}
INPUT_NAMES = {"capacity_refresh_terminal", "capacity_refresh_budget"}
LEGACY = ROOT / "tools/staging/final55_after07_stage01/stage_after07.py"
LEGACY_SHA = "a7915583503beb87ed40ab0309df810558098a2cf157f36e766fbf2ba495069e"
REFRESH = ROOT / "tools/experiment_orchestration/humble54_closed_measurement01/refresh_capacity_after28.py"
REFRESH_SHA = "a67a90f7786a1c8e918cd8953d2447f77d0667cb74404d44813917daf3534002"
SCOPE = "CANDIDATE_AUTHENTIC_7_PLUS_6_AND_CAPACITY_REFRESH3_SOURCE_STAGING_ONLY"


def require(value, message):
    if not value:
        raise ValueError(message)


def fixed_module(path, pin):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Ordinary reviewed source required")
    before = path.stat()
    require(before.st_size <= 2 * 1024**2, "Refusing large source input")
    payload = path.read_bytes(); after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and hashlib.sha256(payload).hexdigest() == pin, "Reviewed source changed: " + str(path))
    module = types.ModuleType("capacity_stage_" + path.stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(payload, str(path), "exec"), module.__dict__)
    return module


def stable(value):
    return {key: item for key, item in value.items() if key != "created_utc"}


def binding_in(binding, rows, v):
    return any(row["sha256"] == binding["sha256"]
               and v.local_path(row["path"]).resolve(strict=True) == v.local_path(binding["path"]).resolve(strict=True)
               for row in rows)


class CombinedInputs:
    def __init__(self, inputs, derived):
        self.inputs, self.derived = inputs, derived

    def unchanged(self):
        self.inputs.unchanged()
        self.derived.unchanged()


def audit_history(refresh, measurement, old, base, guard):
    """Recheck original failed windows and products; never call either run()."""
    m = measurement
    p = m.new_paths(old); q = refresh.continuation_paths(p)
    archive = base.binding(m.EXECUTED_SOURCE_ARCHIVE)
    require(archive["sha256"] == m.EXECUTED_SOURCE_SHA, "Executed47 archive changed")
    original = types.ModuleType("capacity_stage_preserved47")
    original.__file__ = str(refresh.MEASUREMENT.resolve())
    exec(compile(m.EXECUTED_SOURCE_ARCHIVE.read_bytes(), original.__file__, "exec"), original.__dict__)
    audit, previous = m.closure_audit(m.REGISTERED_INPUTS, old)
    collector = m.fixed_module(m.REGISTERED_INPUTS["collector"]["path"], m.REGISTERED_INPUTS["collector"]["sha256"])
    v = collector.review_library(); inputs = m.after28_inputs(v, previous)
    inputs.bound(archive)
    first = inputs.json(m.AFTER28_TERMINAL)
    proof = m.validate_after28_terminal(first, original, old, p, inputs, v, guard, archive, datetime.now(timezone.utc))
    reused = m.verify_after28_products(old, p, first, inputs, v)
    continued = inputs.json(refresh.CONTINUATION)
    require(v.local_path(refresh.CONTINUATION["path"]).resolve(strict=True)
            == (q["receipt"] / "terminal.json").resolve(strict=True), "Original continuation terminal relocated")
    refresh.validate_continuation(continued, first, proof, reused, m, old, p, q, inputs, v, guard, datetime.now(timezone.utc))
    require(audit.get("status") == m.CLOSURE_STATUS and audit.get("pending_ids") == []
            and len(audit.get("closed_ids", [])) == len(set(audit["closed_ids"])) == 16,
            "Actual original full16 closure required")
    for terminal in (first, continued):
        saved = inputs.json(terminal["closure_audit"])
        require(stable(saved) == stable(audit), "Original full16 closure changed")
        require(v.timestamp(saved["created_utc"], datetime.now(timezone.utc))
                <= v.timestamp(terminal["started_utc"], datetime.now(timezone.utc))
                <= v.timestamp(terminal["finished_utc"], datetime.now(timezone.utc))
                <= v.timestamp(audit["created_utc"], datetime.now(timezone.utc)), "Original/fresh closure UTC differs")
    budget_binding = {"path": str(p["budget"]), "sha256": refresh.OLD_BUDGET_SHA}
    candidate_binding = {"path": str(p["calibration"] / "R0_candidate.json"), "sha256": refresh.R0_SHA}
    require(budget_binding in continued["input_bindings"] and candidate_binding in continued["input_bindings"], "Original budget/R0 bindings omitted")
    budget, candidate = inputs.json(budget_binding), inputs.json(candidate_binding)
    core, extension = base.binding(p["core"]), base.binding(p["extension"])
    refresh.negative_budget(budget, old, core, extension)
    for path, pin in budget["provenance"]["small_inputs_sha256"].items():
        inputs.bound({"path": path, "sha256": pin})
    inventory = inputs.json(budget["provenance"]["physical_inventory"])
    for item, index in ((inventory, 1), (candidate, 4), (budget, 5)):
        refresh.within_created(item, continued["steps"][index], v, datetime.now(timezone.utc))
    derived = refresh.DerivedArtifacts(candidate, p, inputs, v)
    for cls, row in zip(("person", "car"), continued["steps"][2:4]):
        exported = inputs.json({"path": row["stdout"], "sha256": old.sha(inputs.read_reference(row["stdout"]))})
        require(all(exported.get(key) == "PASS" for key in ("status", "online_equivalence_status", "native_state_audit_status"))
                and exported.get("scope") == "DEVELOPMENT_ONLY"
                and exported.get("output") == str(p["calibration"] / (cls + "_export")), "Original named export changed")
    require(not p["inventory"].exists() and not p["inventory"].is_symlink(), "Original stopped receipt has changed")
    return {"p": p, "q": q, "v": v, "inputs": inputs, "audit": audit, "first": first, "continued": continued,
        "proof": proof, "reused": reused, "old_budget": budget, "old_budget_binding": budget_binding,
        "R0_binding": candidate_binding, "old_inventory": inventory, "derived": derived,
        "core_binding": core, "extension_binding": extension}


def existing_refresh_paths(terminal_binding, budget_binding, context, v):
    """Consumption requires an existing independent receipt, never fresh_paths()."""
    p, q = context["p"], context["q"]
    terminal = v.local_path(terminal_binding["path"])
    require(terminal.is_file() and not terminal.is_symlink() and terminal == terminal.resolve(strict=True)
            and terminal.name == "terminal.json", "Canonical actual refresh terminal required")
    receipt = terminal.parent
    require(not receipt.is_symlink() and receipt.parent == p["receipt"].parent.resolve(strict=True),
            "Refresh receipt must be an actual external direct child of the validation parent")
    for protected in (ROOT, p["frozen"], p["receipt"], q["receipt"], p["tools"], p["sizes"], p["calibration"], p["budget"].parent):
        actual = protected.resolve(strict=True)
        require(not receipt.is_relative_to(actual) and not actual.is_relative_to(receipt), "Refresh receipt overlaps protected evidence/source")
    r = dict(p); r.update(receipt=receipt, inventory=receipt / "physical_inventory.json", budget=receipt / "budget.json")
    require(v.local_path(budget_binding["path"]) == r["budget"]
            and r["budget"].is_file() and not r["budget"].is_symlink()
            and r["budget"] == r["budget"].resolve(strict=True), "Registered budget must be this exact actual refresh budget")
    return r


def validate_refresh_terminal(terminal, terminal_binding, budget_binding, context, refresh, measurement, old, guard, now):
    c, m = context, measurement
    inputs, v = c["inputs"], c["v"]
    r = existing_refresh_paths(terminal_binding, budget_binding, c, v)
    source = {"path": str(REFRESH.resolve()), "sha256": REFRESH_SHA}
    require(terminal.get("schema_version") == 1 and terminal.get("scope") == refresh.SCOPE
            and terminal.get("status") == "COMPLETED_CAPACITY_REFRESH_POSITIVE_FULL280_NOT_ADMISSION"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 0
            and terminal.get("errors") == [] and terminal.get("interruptions") == []
            and terminal.get("automatic_retry") is False and terminal.get("formal_admission") is False
            and terminal.get("source") == source and terminal.get("guard") == guard and terminal.get("commit") == old.COMMIT,
            "Actual completed positive capacity-refresh terminal/source/guard required")
    require(terminal.get("original_failure_terminal") == m.AFTER28_TERMINAL
            and terminal.get("continuation_failure_terminal") == refresh.CONTINUATION
            and terminal.get("original_execution_window") == refresh.execution_window(c["first"])
            and terminal.get("continuation_execution_window") == refresh.execution_window(c["continued"])
            and terminal.get("preserved_executed_source") == c["proof"] and terminal.get("reused_actual28") == c["reused"]
            and terminal.get("original_negative_budget") == c["old_budget_binding"]
            and terminal.get("original_R0_candidate") == c["R0_binding"]
            and terminal.get("derived_input_bindings") == c["derived"].bindings,
            "Refresh omitted or altered the authentic original failed windows/products")
    stamp = lambda value: v.timestamp(value, now)
    begin, finish = stamp(terminal["started_utc"]), stamp(terminal["finished_utc"])
    require(stamp(c["continued"]["finished_utc"]) <= begin <= finish, "Refresh must follow the authentic stopped continuation")
    v.linux_identity(terminal["owner_identity"])
    expected = [("native_idle", ["bash", r["idle"]])]
    expected += [(name, argv) for name, argv in old.workflow_commands(r) if name in {"physical_inventory", "full280_budget"}]
    require([name for name, _ in expected] == ["native_idle", "physical_inventory", "full280_budget"]
            and len(terminal["steps"]) == 3, "Exactly three original refresh commands required")
    previous = begin
    for row, (name, argv) in zip(terminal["steps"], expected):
        require(row.get("id") == name and row.get("command") == list(map(str, argv))
                and type(row.get("returncode")) is int and row["returncode"] == 0
                and row.get("pid") == row["identity"]["pid"], "Refresh original command/actual zero exit differs: " + name)
        v.linux_identity(row["identity"])
        require(row["identity"]["boot_id"] == terminal["owner_identity"]["boot_id"], "Refresh child boot differs")
        started, ended = stamp(row["started_utc"]), stamp(row["finished_utc"])
        require(previous <= started <= ended <= finish, "Refresh serial command UTC differs")
        previous = ended
        for channel in ("stdout", "stderr"):
            path = r["receipt"] / (name + "." + channel + ".log")
            require(v.local_path(row[channel]) == path and path.is_file() and not path.is_symlink(), "Refresh original log path differs")
            inputs.bound({"path": row[channel], "sha256": old.sha(inputs.read_reference(row[channel]))})
    rows = terminal["input_bindings"]
    require(isinstance(rows, list) and rows and len(rows) == len({v.path_key(row["path"]) for row in rows}), "Unique actual refresh input bindings required")
    required = [source, m.AFTER28_TERMINAL, refresh.CONTINUATION, c["old_budget_binding"], c["R0_binding"],
        budget_binding, terminal["new_inventory"], terminal["closure_audit"]]
    required += c["history_bindings"]
    require(all(binding_in(item, rows, v) for item in required), "Refresh terminal omits its actual original input family")
    for item in rows:
        inputs.bound(item)
    require(terminal.get("new_budget") == budget_binding
            and terminal["new_inventory"]["path"] == str(r["inventory"])
            and terminal["closure_audit"]["path"] == str(r["receipt"] / "full16_closure_audit.json"), "Refresh generated bindings relocated")
    saved = inputs.json(terminal["closure_audit"])
    require(stable(saved) == stable(c["audit"]) and stamp(saved["created_utc"]) <= begin <= finish <= stamp(c["audit"]["created_utc"]),
            "Refresh saved/fresh full16 closure or chronology differs")
    idle = inputs.json({"path": terminal["steps"][0]["stdout"], "sha256": old.sha(inputs.read_reference(terminal["steps"][0]["stdout"]))})
    require(idle.get("kind") == "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY" and idle.get("matching_processes") == [], "Original refresh idle did not pass")
    inventory, budget = inputs.json(terminal["new_inventory"]), inputs.json(budget_binding)
    refresh.within_created(inventory, terminal["steps"][1], v, now)
    refresh.within_created(budget, terminal["steps"][2], v, now)
    require(refresh.inventory_identity(c["old_inventory"]) == refresh.inventory_identity(inventory), "Actual storage identity changed")
    refresh.same_budget_contract(c["old_budget"], budget, terminal["new_inventory"])
    require(budget.get("schema_version") == 1
            and budget["provenance"]["tool"]["sha256"] == old.TOOL_PINS["tools/reliability_v4_storage_budget.py"]
            and budget["provenance"]["guard_tool"]["sha256"] == old.TOOL_PINS["tools/reliability_v4_guard.py"], "Original budget producer/guard required")
    for path, pin in budget["provenance"]["small_inputs_sha256"].items():
        inputs.bound({"path": path, "sha256": pin})
    for role in ("assumptions", "physical_inventory", "tool", "guard_tool"):
        inputs.bound(budget["provenance"][role])
    for cell in budget["storage"]["cells"]:
        for role in ("development_size_evidence", "archive_evidence"):
            inputs.bound(cell[role])
    old.positive_budget(budget, c["core_binding"], c["extension_binding"])
    return {"preserved_original_step_count": 7, "preserved_continuation_step_count": 6, "closed_refresh_steps": 3,
        "original_failed_returncodes": [c["first"]["returncode"], c["continued"]["returncode"]],
        "refresh_terminal": terminal_binding, "positive_budget_snapshot": budget_binding,
        "storage_sha256": budget["storage_sha256"], "capacity_snapshot_age_seconds": (now - stamp(budget["created_utc"])).total_seconds(),
        "capacity_currently_revalidated": False, "formal_admission": False}


def stage_paths(legacy, prior, stage_directory, receipt_directory):
    require(stage_directory is not None and receipt_directory is not None, "Explicit fresh stage and receipt paths required")
    paths = legacy.production_paths(prior)
    paths.update(stage=Path(stage_directory), receipt=Path(receipt_directory))
    return paths


def validate_stage_outputs(paths, context, terminal_binding):
    """Keep new source/receipts and their sidecars out of all reused evidence."""
    p, q, v = context["p"], context["q"], context["v"]
    refreshed_receipt = v.local_path(terminal_binding["path"]).resolve(strict=True).parent
    protected = [ROOT, p["frozen"], p["receipt"], q["receipt"], refreshed_receipt,
        p["tools"], p["sizes"], p["calibration"], p["budget"].parent]
    roots = {root.absolute() for root in protected} | {root.resolve(strict=True) for root in protected}
    receipt = paths["receipt"]
    admission = receipt.with_name(receipt.name + ".admission.json")
    outcome = admission.with_name(admission.stem + ".driver_outcome.json")
    outputs = (paths["stage"], receipt, admission, outcome)
    actuals = [path.resolve() for path in outputs]
    require(len(set(actuals)) == 4 and all(not a.is_relative_to(b) and not b.is_relative_to(a)
            for index, a in enumerate(actuals) for b in actuals[index + 1:]), "Staging outputs and sidecars must be mutually independent")
    for path in outputs:
        require(path.is_absolute() and ".." not in path.parts and path.parent.is_dir()
                and not path.exists() and not path.is_symlink(), "Fresh explicit staging output or sidecar required: " + str(path))
        for actual in (path.absolute(), path.resolve()):
            require(all(not actual.is_relative_to(root) and not root.is_relative_to(actual) for root in roots),
                    "Staging output overlaps reused protected evidence/source: " + str(path))


def run_registered(*, execute_requested=False, reviewed_source_sha256=None, stage_directory=None, receipt_directory=None):
    require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == INPUT_NAMES,
            "Production disabled; actual positive refresh terminal and budget are not registered")
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22", "Explicit native UAVHumble22 required; no launcher exists")
    require(reviewed_source_sha256 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == reviewed_source_sha256,
            "Exact reviewed candidate source SHA required")
    legacy, refresh = fixed_module(LEGACY, LEGACY_SHA), fixed_module(REFRESH, REFRESH_SHA)
    base, prior = legacy.fixed_module(legacy.BASE, legacy.BASE_SHA), legacy.fixed_module(legacy.PRIOR, legacy.PRIOR_SHA)
    measurement = refresh.fixed_module(refresh.MEASUREMENT, refresh.MEASUREMENT_SHA)
    old = measurement.fixed_module(measurement.OLD08, measurement.OLD08_SHA)
    with base.linux_idle_guard() as guard:
        context = audit_history(refresh, measurement, old, base, guard)
        inputs, v = context["inputs"], context["v"]
        context["history_bindings"] = list(inputs.seen.values())
        terminal_binding, budget_binding = (REGISTERED_INPUTS[key] for key in ("capacity_refresh_terminal", "capacity_refresh_budget"))
        terminal = inputs.json(terminal_binding)
        checks = validate_refresh_terminal(terminal, terminal_binding, budget_binding, context, refresh, measurement, old, guard, datetime.now(timezone.utc))
        profile, _bundle = legacy.candidate_inputs(base, prior)
        for path, pin in ((LEGACY, LEGACY_SHA), (REFRESH, REFRESH_SHA), (legacy.BASE, legacy.BASE_SHA),
                          (legacy.PRIOR, legacy.PRIOR_SHA), (legacy.BUNDLE, legacy.BUNDLE_SHA),
                          (legacy.PROFILE_PATH, legacy.PROFILE_SHA), (legacy.CONTRACT, profile["contract_sha"]),
                          (refresh.MEASUREMENT, refresh.MEASUREMENT_SHA)):
            inputs.bound({"path": str(path), "sha256": pin})
        for name, _old_bytes, _old_sha, _new_bytes, pin in profile["overlays"]:
            inputs.bound({"path": str(legacy.ROOT / name), "sha256": pin})
        own = base.binding(Path(__file__).resolve())
        require(own["sha256"] == reviewed_source_sha256, "Candidate source changed before staging")
        inputs.bound(own)
        combined = CombinedInputs(inputs, context["derived"])
        paths = stage_paths(legacy, prior, stage_directory, receipt_directory)
        validate_stage_outputs(paths, context, terminal_binding)
        combined.unchanged()
        prepared = base.prepare(paths, profile)
        combined.unchanged()
        if not execute_requested:
            return {"status": "CAPACITY_REFRESH_CANDIDATE_PREFLIGHT_ONLY_NO_STAGING", "scope": SCOPE, "checks": checks, **base.summary(prepared)}
        admission_path = prepared["paths"]["receipt"].with_name(prepared["paths"]["receipt"].name + ".admission.json")
        admission = {"status": "ACTUAL_FAILED7_FAILED6_AND_POSITIVE_REFRESH3_BEFORE_SOURCE_STAGING_NOT_FORMAL_ADMISSION",
            "scope": SCOPE, "created_utc": datetime.now(timezone.utc).isoformat(), "source": own,
            "base_driver": {"path": str(legacy.BASE), "sha256": legacy.BASE_SHA},
            "outcome_helper": {"path": str(legacy.PRIOR), "sha256": legacy.PRIOR_SHA},
            "registered_inputs": REGISTERED_INPUTS, "original_failure_terminal": measurement.AFTER28_TERMINAL,
            "continuation_failure_terminal": refresh.CONTINUATION,
            "original_execution_window": refresh.execution_window(context["first"]),
            "continuation_execution_window": refresh.execution_window(context["continued"]),
            "capacity_refresh_execution_window": refresh.execution_window(terminal),
            "original_negative_budget": context["old_budget_binding"], "original_R0_candidate": context["R0_binding"],
            "recomputed_closure_audit": context["audit"], "checks": checks,
            "candidate_profile": {"path": str(legacy.PROFILE_PATH), "sha256": legacy.PROFILE_SHA},
            "derived_input_bindings": context["derived"].bindings,
            "input_bindings": sorted(inputs.seen.values(), key=lambda row: row["path"]),
            "capacity_currently_revalidated": False, "formal_admission": False, "automatic_retry": False}
        return prior.execute_with_outcome(base, prepared, combined, admission_path, admission)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--preflight", action="store_true")
    parser.add_argument("--reviewed-source-sha256")
    parser.add_argument("--stage-directory", type=Path)
    parser.add_argument("--receipt-directory", type=Path)
    args = parser.parse_args(argv)
    if not args.execute and not args.preflight:
        print(json.dumps({"status": "DISABLED_CANDIDATE_DESCRIPTION_ONLY_NOT_STARTED", "production_enabled": PRODUCTION_ENABLED,
            "registered_inputs": sorted(REGISTERED_INPUTS), "required_actual_inputs": sorted(INPUT_NAMES),
            "native_command_started": False, "outputs_created": False, "formal_admission": False}))
        return 0
    try:
        result = run_registered(execute_requested=args.execute, reviewed_source_sha256=args.reviewed_source_sha256,
            stage_directory=args.stage_directory, receipt_directory=args.receipt_directory)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "REFUSED_CAPACITY_REFRESH_CANDIDATE_NO_RETRY", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
