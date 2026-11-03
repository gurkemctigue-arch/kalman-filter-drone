"""Prepare final55 from actual after07 measurements, without the old owner chain.

Disabled until the three actual measurement/budget bindings exist and are
reviewed. Reuse pinned base staging and candidate04 outcome publication only.
No WSL launcher, build, flight, owner, trigger or evidence exception exists.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION_ENABLED = False
REGISTERED_INPUTS = {}
INPUT_NAMES = {"measurement_source", "measurement_terminal", "budget"}
BASE = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
BASE_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
PRIOR = ROOT / "tools/staging/final55_profile03_driver_candidate04/stage_profile02.py"
PRIOR_SHA = "082ed8b6fc229cc1d188f27e4b896a4864695dfbcaf65c57fe06fcf9d28e4f7f"
BUNDLE = ROOT / "tools/diagnostics/humble54_conditional_identity_optin01/stage_wiring_candidates01.json"
BUNDLE_SHA = "58db85f8e36802df4f7a99e51f6dcef2fa78b89c2e165dc1097ea725902eeaef"
PROFILE_PATH = HERE / "prepared_stage_profile.json"
PROFILE_SHA = "71102c0cb104202f8ffed55147a80956c892e58f89938933ea30d436edc4e254"
CONTRACT = HERE / "contracts/contract_probe02_conditional_identity01.json"


def require(value, message):
    if not value:
        raise ValueError(message)


def raw(path, expected):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2 * 1024 * 1024,
            "Ordinary small reviewed input required: " + str(path))
    payload = path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == expected, "Reviewed input SHA differs: " + str(path))
    return payload


def fixed_module(path, expected):
    payload = raw(path, expected)
    module = types.ModuleType("after07_stage_" + Path(path).stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(payload, str(path), "exec"), module.__dict__)
    return module


def build_candidate_profile(base, prior, bundle):
    """Use actual four file candidates; keep every original before pin."""
    require(bundle["inputs"]["base_stage"]["sha256"] == BASE_SHA
            and bundle["inputs"]["candidate04"]["sha256"] == PRIOR_SHA
            and bundle.get("validated_overlay_rows") == 10, "Wrong reviewed ten-row candidate bundle")
    changes = {row["path"]: row for row in bundle["after_pins_requiring_update"]}
    require(len(changes) == 4 and len(base.OVERLAYS) == 10, "Exact four updated after-pins required")
    rows = []
    for name, old_bytes, old_sha, new_bytes, new_sha in base.OVERLAYS:
        if name in changes:
            change = changes[name]
            require((change["registered_after_bytes"], change["registered_after_sha256"]) == (new_bytes, new_sha)
                    and change["candidate_after"]["path"] == name, "Candidate replaced an unrelated overlay row")
            new_bytes, new_sha = change["candidate_after"]["bytes"], change["candidate_after"]["sha256"]
        rows.append([name, old_bytes, old_sha, new_bytes, new_sha])
    require(set(changes) | set(bundle["six_other_overlay_paths_match_registered_after_pins"])
            == {row[0] for row in rows}, "Ten overlay path set changed")
    profile = deepcopy(base.PROFILE)
    profile.update(prior.OVERRIDES)
    contract = bundle["contract_derivation"]
    profile.update(overlays=rows, module_sha=bundle["external_module_sha_candidate"],
                   contract_sha=contract["candidate_sha256"], contract_digest=contract["candidate_canonical_sha256"])
    maps = bundle["metadata_derived_stage_profile_candidates"]
    require((maps["source_entries"], maps["scanner_entries"], maps["flight_entries"]) == (308, 185, 277)
            and maps.get("flight_map_unchanged") is True, "Original source/scanner/flight denominators changed")
    profile.update(overlay_source_digest=maps["overlay_source_digest"], overlay_scanner_digest=maps["overlay_scanner_digest"])
    return json.loads(json.dumps(profile, allow_nan=False))


def candidate_inputs(base, prior):
    bundle = base.load(BUNDLE)
    raw(BUNDLE, BUNDLE_SHA)
    profile = json.loads(raw(PROFILE_PATH, PROFILE_SHA))
    require(profile == build_candidate_profile(base, prior, bundle), "Prepared profile does not match actual candidate files")
    for name, _, _, byte_count, pin in profile["overlays"]:
        require(len(raw(ROOT / name, pin)) == byte_count, "Overlay payload bytes differ: " + name)
    contract = base.load(CONTRACT)
    require(raw(CONTRACT, profile["contract_sha"]) == bundle["contract_derivation"]["candidate_utf8"].encode("utf-8")
            and base.digest(contract) == profile["contract_digest"], "New derived contract bytes/canonical digest differ")
    original_spec = bundle["contract_derivation"]["original_unchanged"]
    original = json.loads(raw(ROOT / original_spec["path"], original_spec["sha256"]))
    require({key: value for key, value in contract.items() if key != "conditional_identity_rule"} == original
            and set(contract) - set(original) == {"conditional_identity_rule"}
            and contract["conditional_identity_rule"] == "CONDITIONAL_UNOBSERVED_AFTER_DEMONSTRATED_SHORT_LOSS",
            "Derived contract changed more than the one reviewed opt-in field")
    return profile, bundle


def stable_audit(audit):
    """Fresh actual creation UTC is the sole allowed recomputation difference."""
    return {key: value for key, value in audit.items() if key != "created_utc"}


def binding_in(binding, rows, v):
    return any(row["sha256"] == binding["sha256"]
               and v.local_path(row["path"]).resolve(strict=True) == v.local_path(binding["path"]).resolve(strict=True)
               for row in rows)


def validate_terminal(terminal, measurement, old, p, source_binding, budget_binding, inputs, v, guard, now):
    require(terminal.get("scope") == measurement.SCOPE
            and terminal.get("status") == "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION"
            and type(terminal.get("returncode")) is int and terminal["returncode"] == 0
            and terminal.get("errors") == [] and terminal.get("interruptions") == []
            and terminal.get("automatic_retry") is False and terminal.get("formal_admission") is False
            and terminal.get("commit") == old.COMMIT and terminal.get("guard") == guard
            and terminal.get("source") == source_binding
            and terminal.get("actual_original_bindings") == measurement.REGISTERED_INPUTS,
            "Actual complete measurement terminal/source/guard is required")
    v.linux_identity(terminal["owner_identity"])
    stamp = lambda value: v.timestamp(value, now)
    start, finish = stamp(terminal["started_utc"]), stamp(terminal["finished_utc"])
    require(start <= finish, "Measurement terminal UTC order differs")
    bindings = terminal["input_bindings"]
    require(isinstance(bindings, list) and bindings, "Complete original measurement input bindings required")
    for binding in bindings:
        inputs.bound(binding)
    require(all(binding_in(binding, bindings, v) for binding in (source_binding, budget_binding, terminal["closure_audit"])),
            "Original input bindings omit this source, saved closure audit or budget")
    expected = [("native_idle", ["bash", p["idle"]])]
    expected += [("tool_" + str(index), ["git", "-C", measurement.ROOT, "show", old.COMMIT + ":" + relative])
                 for index, relative in enumerate(old.TOOL_PINS)]
    expected += old.workflow_commands(p)
    require(len(terminal["steps"]) == len(expected) == 12, "Exact idle, five source copies and six workflow steps required")
    previous = start
    for row, (label, argv) in zip(terminal["steps"], expected):
        require(row.get("id") == label and row.get("command") == list(map(str, argv))
                and type(row.get("returncode")) is int and row["returncode"] == 0
                and row.get("pid") == row["identity"]["pid"], "Original measurement step/command/real exit differs: " + label)
        v.linux_identity(row["identity"])
        begun, ended = stamp(row["started_utc"]), stamp(row["finished_utc"])
        require(previous <= begun <= ended <= finish, "Measurement serial step chronology differs")
        previous = ended
        for channel in ("stdout", "stderr"):
            expected_log = p["receipt"] / (label + "." + channel + ".log")
            require(Path(row[channel]).resolve(strict=True) == expected_log.resolve(strict=True)
                    and expected_log.is_file() and not expected_log.is_symlink(), "Original step log relocated or missing")
    return {"closed_steps": 12, "workflow_steps": [name for name, _ in old.workflow_commands(p)],
            "preserved_source": source_binding, "preserved_budget": budget_binding}


def production_paths(prior):
    p = prior.production_paths()
    p.update(stage=Path("/root/uav_tracking_final55_stage_after07_01"),
             receipt=Path("/mnt/d/WSL/UAVHumble22-validation/final55_stage_after07_01"), contract=CONTRACT)
    return p


def run_registered(*, execute_requested=False):
    require(PRODUCTION_ENABLED and set(REGISTERED_INPUTS) == INPUT_NAMES,
            "Production disabled; actual measurement source, terminal and positive budget are not registered")
    base, prior = fixed_module(BASE, BASE_SHA), fixed_module(PRIOR, PRIOR_SHA)
    with base.linux_idle_guard() as guard:
        source = REGISTERED_INPUTS["measurement_source"]
        measurement = fixed_module(source["path"], source["sha256"])
        require(measurement.PRODUCTION_ENABLED is True and set(measurement.REGISTERED_INPUTS) == measurement.INPUT_NAMES,
                "Only the actual registered after07 measurement source is permitted")
        old = measurement.fixed_module(measurement.OLD08, measurement.OLD08_SHA)
        collector = measurement.fixed_module(measurement.REGISTERED_INPUTS["collector"]["path"],
                                             measurement.REGISTERED_INPUTS["collector"]["sha256"])
        v = collector.review_library()
        p = measurement.new_paths(old)
        terminal_binding, budget_binding = REGISTERED_INPUTS["measurement_terminal"], REGISTERED_INPUTS["budget"]
        require(v.local_path(terminal_binding["path"]).resolve(strict=True) == (p["receipt"] / "terminal.json").resolve(strict=True)
                and v.local_path(budget_binding["path"]).resolve(strict=True) == p["budget"].resolve(strict=True),
                "Actual fixed after07 measurement terminal and budget originals required")
        terminal = v.parse(v.local_small_read(terminal_binding["path"]))
        require(terminal.get("actual_original_bindings") == measurement.REGISTERED_INPUTS,
                "Measurement terminal is bound to different original collector evidence")
        audit, inputs = measurement.closure_audit(terminal["actual_original_bindings"], old)
        closure_bindings = list(inputs.seen.values())
        require(inputs.json(terminal_binding) == terminal, "Measurement terminal changed during native closure recheck")
        now = datetime.now(timezone.utc)
        checks = validate_terminal(terminal, measurement, old, p, source, budget_binding, inputs, v, guard, now)
        require(all(binding_in(binding, terminal["input_bindings"], v) for binding in closure_bindings),
                "Original terminal omits part of its actual collector closure input family")
        saved_audit = inputs.json(terminal["closure_audit"])
        require(audit.get("status") == measurement.CLOSURE_STATUS and audit.get("pending_ids") == []
                and len(audit.get("closed_ids", [])) == len(set(audit["closed_ids"])) == 16
                and stable_audit(audit) == stable_audit(saved_audit),
                "Fresh full16 closure differs from the original saved measurement audit")
        require(v.timestamp(saved_audit["created_utc"], now) <= v.timestamp(terminal["started_utc"], now)
                <= v.timestamp(terminal["finished_utc"], now) <= v.timestamp(audit["created_utc"], now),
                "Saved/fresh actual full16 audit creation chronology differs")
        budget = inputs.json(budget_binding)
        core, extension = base.binding(p["core"]), base.binding(p["extension"])
        old.positive_budget(budget, core, extension)
        require(budget.get("schema_version") == 1
                and budget["provenance"]["tool"]["sha256"] == old.TOOL_PINS["tools/reliability_v4_storage_budget.py"]
                and budget["provenance"]["guard_tool"]["sha256"] == old.TOOL_PINS["tools/reliability_v4_guard.py"],
                "Budget producer is not the original fixed storage tool/guard")
        for path, pin in budget["provenance"]["small_inputs_sha256"].items():
            inputs.bound({"path": path, "sha256": pin})
        for role in ("assumptions", "physical_inventory", "tool", "guard_tool"):
            inputs.bound(budget["provenance"][role])
        for cell in budget["storage"]["cells"]:
            for role in ("development_size_evidence", "archive_evidence"):
                inputs.bound(cell[role])
        require(v.timestamp(terminal["started_utc"], now) <= v.timestamp(budget["created_utc"], now)
                <= v.timestamp(terminal["finished_utc"], now), "Budget was not produced during this actual measurement")
        profile, bundle = candidate_inputs(base, prior)
        for path, pin in ((BASE, BASE_SHA), (PRIOR, PRIOR_SHA), (BUNDLE, BUNDLE_SHA),
                          (PROFILE_PATH, PROFILE_SHA), (CONTRACT, profile["contract_sha"])):
            inputs.bound({"path": str(path), "sha256": pin})
        inputs.bound(source)
        inputs.bound(base.binding(Path(__file__).resolve()))
        prepared = base.prepare(production_paths(prior), profile)
        inputs.unchanged()
        if not execute_requested:
            return {"status": "AFTER07_PREFLIGHT_ONLY_NO_STAGING", "checks": checks, **base.summary(prepared)}
        admission_path = prepared["paths"]["receipt"].with_name(prepared["paths"]["receipt"].name + ".admission.json")
        admission = {"status": "ACTUAL_AFTER07_FULL16_AND_POSITIVE_FULL280_BUDGET_BEFORE_STAGING_NOT_FORMAL_ADMISSION",
                     "created_utc": datetime.now(timezone.utc).isoformat(), "source": base.binding(Path(__file__).resolve()),
                     "base_driver": {"path": str(BASE), "sha256": BASE_SHA},
                     "outcome_helper": {"path": str(PRIOR), "sha256": PRIOR_SHA}, "registered_inputs": REGISTERED_INPUTS,
                     "saved_measurement_closure_audit": terminal["closure_audit"], "recomputed_closure_audit": audit,
                     "checks": checks, "candidate_profile": {"path": str(PROFILE_PATH), "sha256": PROFILE_SHA},
                     "input_bindings": sorted(inputs.seen.values(), key=lambda row: row["path"]),
                     "formal_admission": False, "automatic_retry": False}
        return prior.execute_with_outcome(base, prepared, inputs, admission_path, admission)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not PRODUCTION_ENABLED:
        print(json.dumps({"status": "DISABLED_WAITING_ACTUAL_AFTER07_MEASUREMENT_AND_POSITIVE_BUDGET",
                          "registered_inputs": sorted(REGISTERED_INPUTS), "outputs_created": False,
                          "native_command_started": False, "stage_build_formal": "NOT_STARTED"}))
        return 2 if args.execute else 0
    try:
        print(json.dumps(run_registered(execute_requested=args.execute), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "REFUSED_AFTER07_STAGING_NOT_STARTED_OR_PARTIALS_RETAINED",
                          "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
