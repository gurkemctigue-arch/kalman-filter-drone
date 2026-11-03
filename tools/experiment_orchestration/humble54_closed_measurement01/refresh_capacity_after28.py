"""Explicit capacity-only refresh of the authentic seven-plus-six-step windows.

Default describes the prepared operation without loading helpers or evidence.
Execution never measures trials, exports/calibrates, stages, builds or flies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MEASUREMENT = HERE / "run_closed_measurement.py"
MEASUREMENT_SHA = "f32bd4bc97e58a15417fb9757eceb7e7cf2de2cb4e16ac5df54d200a40bae3b0"
CONTINUATION = {
    "path": "/mnt/d/WSL/UAVHumble22-validation/humble54_probe02_closed_measurement_after07_01_continue_after28_01/terminal.json",
    "sha256": "fa9278fbfd89fcba878c421bf4197edebaa816d57304395b2e317e3249b87b7b"}
OLD_BUDGET_SHA = "2af067022931d87e5c1e74eccef8457f4d735dc7d17819d331ea9eadf6c94b4b"
R0_SHA = "6e259c6491fcf61f608f3ca4f702e6dac3b3003ff22ef4dc8bf6fa9aeadc500b"
CAPACITY_ERROR = "Unknown or negative physical/logical full280 budget; stop without staging"
SCOPE = "NATIVE_EXPLICIT_CAPACITY_REFRESH_AFTER_AUTHENTIC_7_PLUS_6_NOT_ADMISSION"
SIDECARS = ("online_equivalence.json", "native_state_audit.json", "truth_alignment.json")
DERIVED_MAX_BYTES = 16 * 1024**2


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fixed_module(path, pin):
    raw = Path(path).read_bytes()
    require(len(raw) <= 2 * 1024**2 and hashlib.sha256(raw).hexdigest() == pin,
            "Reviewed source changed: " + str(path))
    module = types.ModuleType("capacity_refresh_" + Path(path).stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def continuation_paths(p):
    q = dict(p)
    q["receipt"] = p["receipt"].with_name(p["receipt"].name + "_continue_after28_01")
    q["inventory"] = q["receipt"] / "physical_inventory.json"
    return q


def execution_window(terminal):
    return {key: terminal[key] for key in ("started_utc", "finished_utc", "returncode", "errors", "steps")}


def validate_continuation(terminal, first, proof, reused, m, old, p, q, inputs, v, guard, now):
    """Require the actual six zero exits followed only by the final capacity gate."""
    require(terminal.get("scope") == m.AFTER28_SCOPE
            and terminal.get("status") == "STOPPED_AFTER28_CONTINUATION_PARTIAL_OUTPUTS_RETAINED"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 2
            and terminal.get("interruptions") == [] and len(terminal.get("errors", [])) == 1
            and terminal["errors"][0].get("error") == "ValueError: " + CAPACITY_ERROR
            and terminal.get("automatic_retry") is False and terminal.get("formal_admission") is False
            and terminal.get("commit") == old.COMMIT and terminal.get("guard") == guard
            and terminal.get("actual_original_bindings") == m.REGISTERED_INPUTS,
            "Only the authentic six-step continuation with the sole final capacity refusal is eligible")
    require(terminal.get("source") == {"path": str(MEASUREMENT.resolve()), "sha256": MEASUREMENT_SHA}
            and terminal.get("original_failure_terminal") == m.AFTER28_TERMINAL
            and terminal.get("original_execution_window") == execution_window(first)
            and terminal.get("preserved_executed_source") == proof and terminal.get("reused_actual28") == reused,
            "Continuation source or preserved original seven-step evidence differs")
    require(terminal.get("inventory_output_choice") == {
        "original_uncreated_path": str(p["inventory"]), "actual_new_path": str(q["inventory"]),
        "reason": "Keep the entire original stopped receipt unchanged; calibration and budget retain their original uncreated paths."},
        "Continuation original/fresh inventory distinction changed")
    stamp = lambda value: v.timestamp(value, now)
    begun, finished = stamp(terminal["started_utc"]), stamp(terminal["finished_utc"])
    require(stamp(first["finished_utc"]) <= begun <= finished
            and begun <= stamp(terminal["errors"][0]["utc"]) <= finished,
            "Continuation chronology differs")
    v.linux_identity(terminal["owner_identity"])
    expected = [("native_idle", ["bash", p["idle"]])] + old.workflow_commands(q)[1:]
    require(len(terminal["steps"]) == len(expected) == 6, "Exactly six original successful continuation steps required")
    previous = begun
    for row, (name, argv) in zip(terminal["steps"], expected):
        require(row.get("id") == name and row.get("command") == list(map(str, argv))
                and type(row.get("returncode")) is int and row["returncode"] == 0
                and row.get("pid") == row["identity"]["pid"], "Continuation actual command/exit differs: " + name)
        v.linux_identity(row["identity"])
        require(row["identity"]["boot_id"] == terminal["owner_identity"]["boot_id"], "Continuation child boot differs")
        start, end = stamp(row["started_utc"]), stamp(row["finished_utc"])
        require(previous <= start <= end <= finished, "Continuation serial command chronology differs")
        previous = end
        for channel in ("stdout", "stderr"):
            path = q["receipt"] / (name + "." + channel + ".log")
            require(v.local_path(row[channel]).resolve(strict=True) == path.resolve(strict=True), "Continuation log relocated")
            inputs.bound({"path": row[channel], "sha256": old.sha(inputs.read_reference(row[channel]))})
    require(previous <= stamp(terminal["errors"][0]["utc"]), "Capacity error predates the budget child exit")
    bindings = terminal["input_bindings"]
    require(isinstance(bindings, list) and len(bindings) == 1107
            and sum(row == terminal["source"] for row in bindings) == 1
            and terminal["closure_audit"] in bindings and m.AFTER28_TERMINAL in bindings,
            "Authentic continuation input set differs")
    for item in bindings:
        inputs.bound(item)


def within_created(value, step, v, now):
    require(v.timestamp(step["started_utc"], now) <= v.timestamp(value["created_utc"], now)
            <= v.timestamp(step["finished_utc"], now), "Generated JSON UTC is outside its actual child window")


def negative_budget(budget, old, core, extension):
    """Earlier schema/provenance failures must never be mistaken for capacity."""
    try:
        old.positive_budget(budget, core, extension)
    except ValueError as error:
        require(str(error) == CAPACITY_ERROR, "Old budget fails before the final capacity gate: " + str(error))
    else:
        raise ValueError("Authentic original budget must remain negative")
    preview = budget["capacity_preview"]
    require(preview["fits_declared_logical_budget"] is True
            and any(row.get("fits_declared_physical_budget") is False for row in preview["volumes"].values()),
            "Original known physical deficit required; unknown capacity is not eligible")
    validate_preview(budget)


def validate_preview(budget):
    preview = budget["capacity_preview"]
    require(preview["scheduled_slots"] == 280 and type(preview["ext4_logical_free_bytes"]) is int
            and preview["ext4_logical_free_bytes"] >= 0, "Known complete280 logical capacity required")
    for row in preview["volumes"].values():
        require(all(type(row[key]) is int and row[key] >= 0 for key in ("free_bytes", "required_bytes"))
                and type(row["remaining_after_budget_bytes"]) is int
                and row["remaining_after_budget_bytes"] == row["free_bytes"] - row["required_bytes"]
                and type(row["fits_declared_physical_budget"]) is bool
                and row["fits_declared_physical_budget"] == (row["free_bytes"] >= row["required_bytes"]),
                "Unknown or inconsistent actual physical capacity")
    logical = preview["ext4_logical_free_bytes"] >= preview["volumes"][budget["storage"]["vhd_host"]["volume"]]["required_bytes"]
    require(type(preview["fits_declared_logical_budget"]) is bool
            and preview["fits_declared_logical_budget"] == logical, "Inconsistent actual logical capacity")


def same_budget_contract(before, after, inventory_binding):
    """Capacity changes must preserve every byte of the declared storage budget."""
    require(before["storage"] == after["storage"] and before["storage_sha256"] == after["storage_sha256"]
            and digest(after["storage"]) == after["storage_sha256"], "Capacity refresh changed storage/reserves/cells")
    excluded = {"created_utc", "provenance", "capacity_preview"}
    require({k: x for k, x in before.items() if k not in excluded}
            == {k: x for k, x in after.items() if k not in excluded}, "Budget non-capacity contract changed")
    a, b = before["provenance"], after["provenance"]
    excluded = {"physical_inventory", "small_inputs_sha256"}
    require({k: x for k, x in a.items() if k not in excluded}
            == {k: x for k, x in b.items() if k not in excluded}
            and b["physical_inventory"] == inventory_binding, "Budget original provenance changed")
    maps = []
    for provenance in (a, b):
        mapping = dict(provenance["small_inputs_sha256"])
        binding = provenance["physical_inventory"]
        require(mapping.pop(binding["path"], None) == binding["sha256"], "Missing inventory provenance digest")
        maps.append(mapping)
    require(maps[0] == maps[1], "Budget small inputs changed beyond the actual new inventory")
    a, b = before["capacity_preview"], after["capacity_preview"]
    excluded = {"volumes", "ext4_logical_free_bytes", "fits_declared_logical_budget"}
    require({k: x for k, x in a.items() if k not in excluded}
            == {k: x for k, x in b.items() if k not in excluded}
            and set(a["volumes"]) == set(b["volumes"]), "Budget capacity scope/volume set changed")
    excluded = {"free_bytes", "remaining_after_budget_bytes", "fits_declared_physical_budget"}
    for volume in a["volumes"]:
        require({k: x for k, x in a["volumes"][volume].items() if k not in excluded}
                == {k: x for k, x in b["volumes"][volume].items() if k not in excluded},
                "Physical identity or required budget changed: " + volume)
    validate_preview(after)


def inventory_identity(inventory):
    require(inventory.get("kind") == "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY"
            and inventory.get("evidence_scope") == "METADATA_ONLY_NOT_FORMAL_ADMISSION",
            "Actual non-admission storage inventory required")
    result = {k: x for k, x in inventory.items() if k not in {"created_utc", "volumes"}}
    result["volumes"] = sorted(({k: x for k, x in row.items() if k != "free_bytes"}
                                for row in inventory["volumes"]), key=lambda row: row["mount"])
    require(bool(result["volumes"]), "Actual volume identity required")
    return result


class DerivedArtifacts:
    """Hash only the eight exact JSON outputs authorized by authenticated R0.

    This never broadens Inputs' small-file gates and never parses arrays/audits.
    """
    def __init__(self, candidate, p, inputs, v):
        self.bindings = []
        require(candidate.get("kind") == "RELIABILITY_V4_DEVELOPMENT_CALIBRATION"
                and candidate.get("status") == "CANDIDATE_NOT_REGISTERED" and candidate.get("scope") == "DEVELOPMENT_ONLY"
                and set(candidate["classes"]) == set(candidate["provenance"]) == {"person", "car"},
                "Original two-class development R0 required")
        plan = dict(candidate["development_plan"]); declared_plan_sha = plan.pop("plan_sha256")
        core = inputs.json(plan)
        require(plan["path"] == str(p["core"].resolve(strict=True)) and core["plan_sha256"] == declared_plan_sha,
                "R0 development plan relocated or changed")
        for relative, pin in candidate["source_hashes"].items():
            require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "Unsafe R0 source reference")
            inputs.bound({"path": str(p["frozen"] / relative), "sha256": pin})
        policy = candidate["policy"]
        require(not Path(policy["path"]).is_absolute() and ".." not in Path(policy["path"]).parts, "Unsafe R0 policy reference")
        inputs.bound({"path": str(p["frozen"] / policy["path"]), "sha256": policy["sha256"]})
        for cls in ("person", "car"):
            record = candidate["provenance"][cls]
            require(record["slot_id"] == cls + "_stage1_velocity_seed004", "R0 uses another development slot")
            inputs.bound(record["terminal_record"])
            require(set(record["recording_evidence"]) == {"run_config.json", "bag_integrity.json"}, "R0 recording evidence differs")
            for item in record["recording_evidence"].values():
                inputs.bound(item)
            audit = record["verified_export_evidence"]
            require(audit.get("scope") == "DEVELOPMENT_ONLY"
                    and audit.get("kind") == "DEVELOPMENT_ONLY_FILE_HASH_SOURCE_BOUND_EXPORT_AND_ONLINE_AUDIT"
                    and set(audit["sidecar_sha256"]) == set(SIDECARS)
                    and digest({k: x for k, x in audit.items() if k != "evidence_sha256"}) == audit["evidence_sha256"],
                    "R0 verified export evidence changed")
            for relative, pin in audit["export_source_hashes"].items():
                require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "Unsafe export source reference")
                inputs.bound({"path": str(p["frozen"] / relative), "sha256": pin})
            directory = (p["calibration"] / (cls + "_export")).resolve(strict=True)
            paths = [(record["arrays"], directory / "arrays.json")]
            paths += [({"path": str(directory / name), "sha256": audit["sidecar_sha256"][name]}, directory / name) for name in SIDECARS]
            for item, expected in paths:
                path = v.local_path(item["path"])
                require(path.resolve(strict=True) == expected and path == expected,
                        "Only the exact original derived export paths are permitted")
                self.bindings.append({**item, "bytes": self._hash(path, item["sha256"])})

    @staticmethod
    def _hash(path, expected):
        require(re.fullmatch(r"[0-9a-f]{64}", expected) and path.is_file() and not path.is_symlink(), "Ordinary derived JSON and SHA required")
        before = path.stat(); h = hashlib.sha256()
        require(0 < before.st_size <= DERIVED_MAX_BYTES, "Derived artifact exceeds the independent16MiB limit")
        total = 0
        with path.open("rb") as stream:
            while True:
                # One sentinel byte detects growth without unbounded reads.
                chunk = stream.read(min(1024**2, before.st_size - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                require(total <= before.st_size, "Derived artifact grew beyond its initial size while hashing")
                h.update(chunk)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Derived artifact changed while hashing")
        require(total == before.st_size and h.hexdigest() == expected, "Original derived export SHA differs: " + str(path))
        return before.st_size

    def unchanged(self):
        for row in self.bindings:
            require(self._hash(Path(row["path"]), row["sha256"]) == row["bytes"], "Derived artifact size changed")


def fresh_paths(p, q, receipt):
    path = Path(receipt)
    require(path.is_absolute() and ".." not in path.parts and path == path.resolve()
            and path.parent.resolve(strict=True) == p["receipt"].parent.resolve(strict=True)
            and not path.exists() and not path.is_symlink(), "New exclusive external receipt under the existing validation parent required")
    for protected in (HERE.parents[2], p["frozen"], p["receipt"], q["receipt"], p["tools"], p["sizes"], p["calibration"], p["budget"].parent):
        actual = protected.resolve(strict=True)
        require(not path.is_relative_to(actual) and not actual.is_relative_to(path), "Refresh output overlaps protected evidence/source")
    r = dict(p)
    r.update(receipt=path, inventory=path / "physical_inventory.json", budget=path / "budget.json")
    return r


def run(*, receipt, reviewed_source_sha256):
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
            "Explicit existing UAVHumble22 required; no WSL launcher exists")
    require(reviewed_source_sha256 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == reviewed_source_sha256,
            "Exact independently reviewed capacity-refresh source SHA required")
    m = fixed_module(MEASUREMENT, MEASUREMENT_SHA)
    old = m.fixed_module(m.OLD08, m.OLD08_SHA)
    base = old.fixed_module(old.BASE, old.BASE_SHA)
    p = m.new_paths(old); q = continuation_paths(p)
    with base.linux_idle_guard() as guard:
        archive = base.binding(m.EXECUTED_SOURCE_ARCHIVE)
        require(archive["sha256"] == m.EXECUTED_SOURCE_SHA, "Original executed47 source archive changed")
        original = types.ModuleType("capacity_refresh_preserved47")
        original.__file__ = str(MEASUREMENT.resolve())
        exec(compile(m.EXECUTED_SOURCE_ARCHIVE.read_bytes(), original.__file__, "exec"), original.__dict__)
        audit, previous = m.closure_audit(m.REGISTERED_INPUTS, old)
        collector = m.fixed_module(m.REGISTERED_INPUTS["collector"]["path"], m.REGISTERED_INPUTS["collector"]["sha256"])
        v = collector.review_library(); inputs = m.after28_inputs(v, previous)
        inputs.bound(archive)
        first = inputs.json(m.AFTER28_TERMINAL)
        proof = m.validate_after28_terminal(first, original, old, p, inputs, v, guard, archive, datetime.now(timezone.utc))
        reused = m.verify_after28_products(old, p, first, inputs, v)
        continued = inputs.json(CONTINUATION)
        require(v.local_path(CONTINUATION["path"]).resolve(strict=True) == (q["receipt"] / "terminal.json").resolve(strict=True),
                "Authentic continuation terminal relocated")
        validate_continuation(continued, first, proof, reused, m, old, p, q, inputs, v, guard, datetime.now(timezone.utc))
        for terminal in (first, continued):
            saved = inputs.json(terminal["closure_audit"])
            require({k: x for k, x in saved.items() if k != "created_utc"}
                    == {k: x for k, x in audit.items() if k != "created_utc"}, "Fresh full16 closure differs from preserved window")
            require(v.timestamp(saved["created_utc"], datetime.now(timezone.utc))
                    <= v.timestamp(terminal["started_utc"], datetime.now(timezone.utc)), "Saved closure postdates original window")
        core, extension = base.binding(p["core"]), base.binding(p["extension"])
        budget_binding = {"path": str(p["budget"]), "sha256": OLD_BUDGET_SHA}
        candidate_binding = {"path": str(p["calibration"] / "R0_candidate.json"), "sha256": R0_SHA}
        require(budget_binding in continued["input_bindings"] and candidate_binding in continued["input_bindings"], "Original budget/R0 bindings missing")
        budget = inputs.json(budget_binding); candidate = inputs.json(candidate_binding)
        negative_budget(budget, old, core, extension)
        for path, pin in budget["provenance"]["small_inputs_sha256"].items():
            inputs.bound({"path": path, "sha256": pin})
        old_inventory = inputs.json(budget["provenance"]["physical_inventory"])
        for value, index in ((old_inventory, 1), (candidate, 4), (budget, 5)):
            within_created(value, continued["steps"][index], v, datetime.now(timezone.utc))
        derived = DerivedArtifacts(candidate, p, inputs, v)
        for cls, row in zip(("person", "car"), continued["steps"][2:4]):
            exported = inputs.json({"path": row["stdout"], "sha256": old.sha(inputs.read_reference(row["stdout"]))})
            require(all(exported.get(key) == "PASS" for key in ("status", "online_equivalence_status", "native_state_audit_status"))
                    and exported.get("scope") == "DEVELOPMENT_ONLY"
                    and exported.get("output") == str(p["calibration"] / (cls + "_export")), "Named original export did not pass")
        require(not p["inventory"].exists() and not p["inventory"].is_symlink(), "Original stopped receipt has been modified")
        r = fresh_paths(p, q, receipt)
        own = base.binding(Path(__file__).resolve())
        require(own["sha256"] == reviewed_source_sha256, "Capacity-refresh source changed before starting")
        inputs.bound(own)
        def unchanged():
            inputs.unchanged(); derived.unchanged()
        checked = types.SimpleNamespace(unchanged=unchanged)
        unchanged()
        r["receipt"].mkdir(exist_ok=False)
        state = {"schema_version": 1, "scope": SCOPE, "status": "STARTED_CAPACITY_ONLY_REFRESH",
            "started_utc": old.utc(), "source": own, "owner_identity": old.linux_identity(os.getpid()),
            "original_failure_terminal": m.AFTER28_TERMINAL, "continuation_failure_terminal": CONTINUATION,
            "original_execution_window": execution_window(first), "continuation_execution_window": execution_window(continued),
            "preserved_executed_source": proof, "reused_actual28": reused,
            "original_negative_budget": budget_binding, "original_R0_candidate": candidate_binding,
            "derived_input_bindings": derived.bindings, "guard": guard, "commit": old.COMMIT,
            "automatic_retry": False, "formal_admission": False, "steps": [], "interruptions": [], "errors": [],
            "claim_boundary": "Authentic stopped7 plus stopped6 windows preserved; only fresh idle, physical inventory and identical full280 budget. No staging/build/flight/admission."}
        environment = {**os.environ, "HUMBLE22_PROJECT_ROOT": str(p["frozen"]),
            "HUMBLE22_ROS_GZ_WS": "/root/uav_humble22/ros_gz_shutdown_A01_ws",
            "HUMBLE22_PX4_ROOT": "/root/uav_humble22/PX4-Autopilot-v4mag", "TMPDIR": "/tmp", "STAGE1_TRANSIENT_DIR": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        try:
            old.write_new(r["receipt"] / "started.json", state)
            old.write_new(r["receipt"] / "full16_closure_audit.json", audit)
            state["closure_audit"] = base.binding(r["receipt"] / "full16_closure_audit.json")
            inputs.bound(state["closure_audit"])
            require(v.timestamp(continued["finished_utc"], datetime.now(timezone.utc)) <= v.timestamp(state["started_utc"], datetime.now(timezone.utc)), "Refresh predates continuation closure")
            stdout = old.child_step(r, state, "native_idle", ["bash", p["idle"]], checked, environment=environment)
            idle = old.bound_generated(inputs, stdout)
            require(idle.get("kind") == "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY" and idle.get("matching_processes") == [], "Fresh native idle did not pass")
            commands = [(name, argv) for name, argv in old.workflow_commands(r) if name in {"physical_inventory", "full280_budget"}]
            require([name for name, _ in commands] == ["physical_inventory", "full280_budget"], "Only the two original storage commands are allowed")
            for name, argv in commands:
                old.child_step(r, state, name, argv, checked, environment=environment)
                if name == "physical_inventory":
                    inventory = old.bound_generated(inputs, r["inventory"])
                    state["new_inventory"] = base.binding(r["inventory"])
                    within_created(inventory, state["steps"][-1], v, datetime.now(timezone.utc))
                    require(inventory_identity(old_inventory) == inventory_identity(inventory), "Actual host/storage identity changed")
                else:
                    fresh = old.bound_generated(inputs, r["budget"])
                    state["new_budget"] = base.binding(r["budget"])
                    within_created(fresh, state["steps"][-1], v, datetime.now(timezone.utc))
                    same_budget_contract(budget, fresh, state["new_inventory"])
                    for path, pin in fresh["provenance"]["small_inputs_sha256"].items():
                        inputs.bound({"path": path, "sha256": pin})
                    old.positive_budget(fresh, core, extension)
            require(not p["inventory"].exists() and not p["inventory"].is_symlink(), "Original stopped receipt changed")
            unchanged()
            state["status"] = "COMPLETED_CAPACITY_REFRESH_POSITIVE_FULL280_NOT_ADMISSION"
        except BaseException as error:
            state["status"] = "STOPPED_CAPACITY_REFRESH_PARTIAL_OUTPUTS_RETAINED"
            state["errors"].append({"utc": old.utc(), "error": f"{type(error).__name__}: {error}"})
        finally:
            state["finished_utc"] = old.utc()
            state["returncode"] = 0 if state["status"].startswith("COMPLETED_CAPACITY_") else 2
            state["input_bindings"] = sorted(inputs.seen.values(), key=lambda row: row["path"])
            old.write_new(r["receipt"] / "terminal.json", state)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--receipt", type=Path, help="New external direct child of the existing validation directory")
    parser.add_argument("--reviewed-source-sha256")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "PREPARATION_DESCRIPTION_ONLY_NOT_STARTED", "scope": SCOPE,
            "preserved_windows": "actual seven-step size stop plus actual six-step final capacity stop",
            "sequence": ["native_idle", "physical_inventory", "full280_budget"],
            "storage_must_be_identical": True, "automatic_retry": False, "stage_build_formal": "NOT_AVAILABLE"}))
        return 0
    try:
        require(args.receipt is not None, "Explicit fresh external receipt required")
        result = run(receipt=args.receipt, reviewed_source_sha256=args.reviewed_source_sha256)
        print(json.dumps({"status": result["status"], "returncode": result["returncode"]}))
        return result["returncode"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "REFUSED_OR_STOPPED_NO_RETRY", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
