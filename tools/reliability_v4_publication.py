"""Publish only the three prospective final-root planning registrations.

This explicit, separately invoked operation is not a flight or an admission.
Original DRAFT bytes and failed/partially recovered transactions are retained.
The existing frozen validators and fixed external audit guard remain authoritative.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

PLANNING = {
    "core": "planning/reliability-v4-preregistration.json",
    "extension": "planning/reliability-v4-extension-preregistration.json",
    "replay": "planning/reliability-v4-estimator-replay-preregistration.json",
}
INTEGRITY = "tools/diagnostics/reliability54_build01/source_integrity.py"
AUDIT_GUARD_PATH = "/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py"
AUDIT_GUARD_SHA256 = "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e"
COMMON = {"schema_version", "kind", "final_root", "audit_guard", "freeze_report", "frozen_map"}
FIELDS = {
    "protocols": COMMON | {"core_target", "extension_target", "core_gate", "extension_gate", "safety_assembly"},
    "replay": COMMON | {"protocol_publication", "core_plan", "replay_assembly"},
    "source-sidecar": COMMON | {"protocol_publication", "replay_publication", "admission", "native_validation"},
}
KIND = "RELIABILITY_V4_EXPLICIT_PLANNING_PUBLICATION_REQUEST"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    require(isinstance(value, str), "An actual timezone-aware UTC timestamp is required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "Naive registration timestamps are forbidden")
    return stamp.astimezone(timezone.utc)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binding(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), "A regular input file is required")
    return {"path": str(path), "sha256": sha(path)}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bound(value, *, json_data=True):
    require(isinstance(value, dict) and set(value) == {"path", "sha256"}
            and isinstance(value["path"], str) and Path(value["path"]).is_absolute()
            and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
            "An exact absolute path/sha256 binding is required")
    path = Path(value["path"])
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path
            and sha(path) == value["sha256"], "Bound input bytes/path changed: " + str(path))
    return (path, load(path)) if json_data else path


def recheck_inputs(request):
    for value in request.values():
        if isinstance(value, dict) and set(value) == {"path", "sha256"}:
            bound(value, json_data=False)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "Cannot import pinned helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def planning_file(root, label):
    path = root / PLANNING[label]
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path,
            "Canonical planning path must be an ordinary file inside final root")
    return path


def base_context(request, *, permitted_changes):
    root = Path(request["final_root"])
    require(root.is_absolute() and root.is_dir() and not root.is_symlink()
            and root.resolve(strict=True) == root, "Explicit canonical final root required")
    report_path, report = bound(request["freeze_report"])
    map_path, original_map = bound(request["frozen_map"])
    require(report.get("frozen") == str(root), "Cold-build report belongs to another actual root")
    results = (root / "results").resolve(strict=True)
    archive = results / "freeze_validation/source_integrity"
    require(report_path == archive / "source_frozen_integrity.json"
            and map_path == archive / "frozen_actual.json", "Use actual archived final-root cold-build originals")
    require(report.get("status") == "PASS" and report.get("scope") ==
            "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES"
            and report.get("frozen") == str(root) and report.get("source") != str(root)
            and report.get("errors") == [] and report.get("build_returncode") == 0
            and report.get("copy_identical") is True and report.get("source_unchanged") is True
            and report.get("source_pre_post") == {"added": [], "changed": [], "missing": []}
            and report.get("frozen_copy") == {"added": [], "changed": [], "missing": []},
            "A genuine successful DRAFT cold freeze of this new final root is required")
    require(original_map.get("frozen") == str(root)
            and report["maps"]["frozen_actual.json"]["sha256"] == request["frozen_map"]["sha256"],
            "Cold-build map/root binding differs")
    link = report.get("generated_results_link", {})
    require((root / "results").is_symlink() and link.get("path") == str(root / "results")
            and link.get("expected_store") == str(results) and os.readlink(root / "results") == link.get("target"),
            "Final results link must retain its original cold-build destination")
    entries = original_map.get("entries")
    require(isinstance(entries, dict) and entries and len(entries) == report.get("actual_frozen_entries")
            == report.get("actual_source_entries") == report.get("expected_entries"), "Complete original byte map required")
    for filename, expected_sha in (("source_before.json", report["before"]["sha256"]),
            ("source_after.json", report["maps"]["source_after.json"]["sha256"])):
        _, original = bound({"path": str(archive / filename), "sha256": expected_sha})
        require(original.get("source") == report["source"] and original.get("entries") == entries,
                "Original source pre/post and frozen maps must retain identical relative entries")
    helper = root / INTEGRITY
    require(helper.is_file() and not helper.is_symlink() and helper.resolve(strict=True) == helper
            and entries.get(INTEGRITY, {}).get("sha256") == sha(helper), "Original integrity helper bytes differ")
    integrity = import_file("publication_integrity_" + sha(helper), helper)
    integrity.validate_filters(root / "scripts/freeze_full_plan_workspace.sh")
    actual = integrity.file_map(root)
    require(actual.pop("results", None) == {"kind": "symlink", "target": link["target"]},
            "Generated results link absent or substituted in the complete current map")
    differences = integrity.differences(entries, actual)
    require(not differences["missing"] and not differences["added"]
            and set(differences["changed"]) == set(permitted_changes),
            "Current full source map has unexpected differences: " + str(differences))
    for label in PLANNING:
        path = planning_file(root, label)
        require(entries.get(PLANNING[label], {}).get("kind") == "file", "Original planning entry missing")
        if PLANNING[label] not in permitted_changes:
            require(sha(path) == entries[PLANNING[label]]["sha256"], "Unpublished DRAFT bytes changed")
    require(request["audit_guard"] == {"path": AUDIT_GUARD_PATH, "sha256": AUDIT_GUARD_SHA256},
            "Use the project's already accepted immutable snapshot_audit54 guard path and bytes")
    guard_path = bound(request["audit_guard"], json_data=False)
    require(guard_path.name == "reliability_v4_guard.py" and guard_path.parent.name == "tools"
            and not guard_path.is_relative_to(root), "The fixed separate audit guard is required")
    guard = import_file("publication_guard_" + sha(guard_path), guard_path)
    return root, results, entries, actual, integrity, guard


def assembly(outcome_binding, action, guard):
    path, outcome = bound(outcome_binding)
    require(path.name == "outcome.json" and outcome.get("schema_version") == 1
            and outcome.get("kind") == "RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME"
            and outcome.get("action") == action and outcome.get("status") == "ASSEMBLED_AND_VALIDATED_NOT_EXECUTED"
            and outcome.get("canonical_files_modified") is False and outcome.get("formal_attempts_started") == 0,
            "Original successful public registrar assembly outcome required")
    registrar = bound(outcome["registrar"], json_data=False)
    require(registrar == Path(guard.__file__).with_name("reliability_v4_register.py"),
            "Assembly must use the same fixed actual audit-tool root")
    start_path = path.with_name("started.json")
    start = load(start_path)
    require(start.get("kind") == "RELIABILITY_V4_REGISTRATION_ASSEMBLY_START"
            and start.get("action") == action and start.get("guard") == binding(guard.__file__)
            and start.get("registrar") == outcome["registrar"], "Original assembly start/tool binding differs")
    artifact_path, artifact = bound(outcome["artifact"])
    require(artifact_path.parent == path.parent and outcome["validated_bytes_sha256"] == outcome["artifact"]["sha256"],
            "The artifact must retain the exact bytes originally validated by registrar")
    require(utc(start["created_utc"]) <= utc(outcome["created_utc"]) <= now(), "Assembly chronology invalid")
    return path, outcome, start, artifact_path, artifact


def previous_publication(value, action, root, guard):
    path, receipt = bound(value)
    require(path.name == "outcome.json" and receipt.get("kind") == "RELIABILITY_V4_PLANNING_PUBLICATION_OUTCOME"
            and receipt.get("action") == action and receipt.get("status") == "PUBLISHED"
            and receipt.get("final_root") == str(root) and receipt.get("audit_guard") == binding(guard.__file__),
            "Actual successful earlier publication of this final root is required")
    for label, value in receipt["canonical_files"].items():
        require(bound(value, json_data=False) == planning_file(root, label), "Earlier canonical publication changed")
    return path, receipt


def protocol_candidates(core, extension, readiness, stamp):
    require(core.get("status") == extension.get("status") == "DRAFT_NOT_FROZEN_NOT_EXECUTED"
            and core.get("registration_utc") is None and extension.get("registration_utc") is None,
            "Never replace an existing protocol registration or partial publication")
    require(core.get("navigation_acceptance", {}).get("status") == "REGISTERED",
            "Engineering numerical requirements must already be separately registered")
    new_core, new_extension = deepcopy(core), deepcopy(extension)
    new_core.update(status="REGISTERED", registration_utc=stamp)
    new_extension.update(status="REGISTERED", registration_utc=stamp, development_readiness=deepcopy(readiness))
    for before, after, allowed in ((core, new_core, {"status", "registration_utc"}),
            (extension, new_extension, {"status", "registration_utc", "development_readiness"})):
        require({k: v for k, v in before.items() if k not in allowed}
                == {k: v for k, v in after.items() if k not in allowed}, "Publication changed experimental design")
    return new_core, new_extension


def prepare_protocols(request, root, guard):
    core_path, core = bound(request["core_target"])
    ext_path, extension = bound(request["extension_target"])
    require(core.get("mode") == "PROBE" and extension.get("mode") == "EXTENSION_PROBE"
            and core.get("frozen_root") == extension.get("frozen_root") == str(root)
            and core.get("selected_seeds") == extension.get("selected_seeds") == [4]
            and len(core.get("trials", [])) == 12 and len(extension.get("trials", [])) == 16
            and core["source_hashes"] == extension["source_hashes"], "Complete unexecuted final-root target snapshots required")
    runtime = guard.load_runtime(root, core)
    builder_path = root / "scripts/build_reliability_v4_probe_gate.py"
    require(core["source_hashes"].get("scripts/build_reliability_v4_probe_gate.py") == sha(builder_path),
            "Actual final-root gate builder differs from target snapshot")
    builder = guard.import_file("publication_actual_gate_builder", builder_path)
    stamp = now().isoformat()
    gate_bindings = {}
    for label, path, target, is_extension in (("core", core_path, core, False), ("extension", ext_path, extension, True)):
        builder.target_snapshot(path, extension=is_extension)
        require(all(row["status"] == "PENDING" for row in runtime.v4.read_slots(target).values()),
                "Target snapshots must never have been executed")
        artifact, gate = bound(request[label + "_gate"])
        generation = gate.get("generation", {})
        require(generation.get("target_plan_path") == str(path)
                and generation.get("target_plan_file_sha256") == sha(path)
                and generation.get("target_plan_sha256") == target["plan_sha256"], "Gate binds another target snapshot")
        for slot in gate.get("probe_slots", []):
            development = load(slot["plan_path"])
            require(Path(development["frozen_root"]).resolve(strict=True) != root,
                    "Development runtime root cannot be republished as the final root")
        context = builder.verification_context(target, artifact, gate, extension=is_extension, registration_utc=stamp)
        runtime.v4.validate_probe_gate(context, extensions=is_extension)
        gate_bindings[label] = {**binding(artifact), "evidence": gate}
    _, outcome, started, _, summary = assembly(request["safety_assembly"], "safety-summary", guard)
    require(started["inputs"]["target_plan"] == request["core_target"]
            and started["inputs"]["core_gate"] == request["core_gate"]
            and summary.get("kind") == "RELIABILITY_V4_FINAL_SAFETY_SUMMARY" and summary.get("result") == "PASS"
            and summary.get("bindings") == gate_bindings["core"]["evidence"]["bindings"]
            and len(summary.get("slots", [])) == 4 and all(s.get("result") == "PASS" for s in summary["slots"]),
            "Original four-safety summary must bind this actual target/core gate")
    require(utc(summary["created_utc"]) <= utc(outcome["created_utc"]) < utc(stamp),
            "Protocol registration must strictly follow the actual safety-summary assembly")
    original_core, original_ext = load(planning_file(root, "core")), load(planning_file(root, "extension"))
    candidates = protocol_candidates(original_core, original_ext, gate_bindings["extension"], stamp)
    runtime.v4.validate_protocol(candidates[0])
    runtime.v4.validate_navigation_gates(candidates[0]["navigation_acceptance"])
    runtime.v4.validate_extension_protocol(candidates[1], candidates[0], formal=True)
    require(runtime.v4.extension_design(candidates[1]) == runtime.v4.extension_design(original_ext),
            "Condition-extension design changed during publication")
    builder.target_snapshot(core_path, extension=False)
    builder.target_snapshot(ext_path, extension=True)
    return {label: (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            for label, value in zip(("core", "extension"), candidates)}


def prepare_replay(request, root, guard):
    _, previous = previous_publication(request["protocol_publication"], "protocols", root, guard)
    core_path, core = bound(request["core_plan"])
    require(core.get("mode") == "FORMAL" and core.get("frozen_root") == str(root)
            and len(core.get("trials", [])) == 120, "Actual complete formal core definition required")
    runtime = guard.load_runtime(root, core)
    runtime.v4.validate_plan(core, core_path)
    runtime.v4.verify_sources(core)
    rows = runtime.v4.read_slots(core)
    require(len(rows) == 120 and all(row["status"] == "PENDING" for row in rows.values()),
            "Replay publication must precede every formal attempt")
    _, outcome, started, candidate_path, candidate = assembly(request["replay_assembly"], "replay-config", guard)
    require(started["inputs"]["core_plan"] == request["core_plan"], "Replay assembly binds another formal core")
    archive = candidate_path.with_name("source_draft.original.json")
    original = planning_file(root, "replay")
    expected = previous["original_drafts"]["replay"]
    require(binding(original)["sha256"] == expected["sha256"] and archive.read_bytes() == original.read_bytes()
            and outcome["detail"]["source_draft_archive"] == binding(archive), "Original replay DRAFT bytes differ")
    require(load(original).get("status") == "DRAFT_NOT_FROZEN_NOT_EXECUTED", "Existing replay registration cannot be replaced")
    runtime.replay.validate_registered_config(candidate)
    runtime.replay.verify_registration_artifacts(candidate, source_root=root)
    require(candidate["freeze_requirements"]["final_engineering_plan_path"] == str(core_path)
            and candidate["freeze_requirements"]["final_engineering_plan_file_sha256"] == sha(core_path)
            and candidate["freeze_requirements"]["final_engineering_plan_digest"] == core["plan_sha256"],
            "Replay candidate binds another formal core definition")
    require(utc(core["created_utc"]) <= utc(candidate["registration"]["registered_utc"])
            <= utc(outcome["created_utc"]) <= now(), "Actual replay chronology invalid")
    return {"replay": candidate_path.read_bytes()}


def replace_bytes(path, data, expected):
    """One-file atomic replace on the planning filesystem; no cross-volume move."""
    require(sha(path) == expected, "Canonical bytes changed before publication")
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix="." + path.name + ".publication.", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        require(sha(path) == expected, "Canonical bytes changed while staging publication")
        os.replace(temporary, path)
        temporary = None
        require(path.read_bytes() == data, "Canonical publication readback differs")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_transaction(root, candidates, output):
    originals = {label: planning_file(root, label).read_bytes() for label in PLANNING}
    archives = {}
    archived_labels = PLANNING if set(candidates) == {"core", "extension"} else candidates
    for label in archived_labels:
        raw = originals[label]
        archive = output / (label + ".draft.original.json")
        with archive.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        archives[label] = binding(archive)
    touched = []
    try:
        for label, data in candidates.items():
            path = planning_file(root, label)
            # Record intent before replace, so readback errors also restore it.
            touched.append(label)
            replace_bytes(path, data, hashlib.sha256(originals[label]).hexdigest())
        return archives
    except BaseException as error:
        recovery = []
        for label in reversed(touched):
            path = planning_file(root, label)
            try:
                current = path.read_bytes()
                require(current in (originals[label], candidates[label]), "Concurrent unknown canonical bytes; refusing to overwrite")
                if current != originals[label]:
                    replace_bytes(path, originals[label], hashlib.sha256(current).hexdigest())
                recovery.append({"label": label, "restored": True, "current": binding(path)})
            except BaseException as recovery_error:
                recovery.append({"label": label, "restored": False, "error": repr(recovery_error)})
        write_new(output / "recovery.json", {"error": repr(error), "files": recovery,
            "all_restored": all(item["restored"] for item in recovery), "atomic_across_files": False})
        raise


def sidecar(request, root, entries, actual, integrity, guard, output):
    _, protocols = previous_publication(request["protocol_publication"], "protocols", root, guard)
    _, replay = previous_publication(request["replay_publication"], "replay", root, guard)
    native_path, native = bound(request["native_validation"])
    validation = (root / "results/freeze_validation").resolve(strict=True)
    require(native_path.parent == validation and native.get("status") == "PASS"
            and native.get("scope") == "ACTUAL_COLD_BUILD_COMPILER_ISOLATION_AND_GENERATED_CDR_NOT_FLIGHT_ACCEPTANCE"
            and native.get("root") == str(root) and native.get("reference") != str(root),
            "Actual successful final-root native cold-build supplement required")
    original = native["original_freeze_and_current_bytes"]
    require(Path(original["report"]).resolve(strict=True) == Path(request["freeze_report"]["path"])
            and original["report_sha256"] == request["freeze_report"]["sha256"]
            and original["original_map_sha256"] == request["frozen_map"]["sha256"]
            and original["current_frozen_bytes_unchanged"] is True,
            "Native supplement must retain its original DRAFT cold-build evidence, not a post-publication recheck")
    isolation_binding = {key: native["public_import_isolation"][key] for key in ("path", "sha256")}
    isolation_path = Path(isolation_binding["path"]).resolve(strict=True)
    isolation_binding["path"] = str(isolation_path)
    _, isolation = bound(isolation_binding)
    require(isolation_path == validation / "import_isolation.json" and isolation.get("isolated") is True
            and isolation.get("root") == str(root), "Original public import isolation is not bound to this final root")
    admission_path, admission = bound(request["admission"])
    require(admission.get("kind") == "RELIABILITY_V4_FORMAL_ADMISSION" and admission.get("final_root") == str(root)
            and admission.get("tool") == binding(guard.__file__), "Actual same-root/same-guard admission required")
    checked = guard.check(admission_path)
    require(checked.report.get("result") == "PASS" and checked.report.get("capacity", {}).get("pending_slots") == 280,
            "Complete pending280 read-only guard check required before final sidecar")
    require(not Path(admission["state_directory"]).exists(), "Final sidecar must precede initial admission or any flight")
    for label in PLANNING:
        archived = bound(protocols["original_drafts"][label], json_data=False)
        require(sha(archived) == entries[PLANNING[label]]["sha256"], "Published DRAFT archive differs from cold-build bytes")
    require(replay["original_drafts"]["replay"]["sha256"] == protocols["original_drafts"]["replay"]["sha256"],
            "The replay DRAFT changed between the two publication operations")
    final_entries = integrity.file_map(root)
    expected_link = load(request["freeze_report"]["path"])["generated_results_link"]
    require(final_entries.pop("results", None) == {"kind": "symlink", "target": expected_link["target"]}
            and (root / "results").resolve(strict=True) == validation.parent and final_entries == actual,
            "Source changed during final complete admission check")
    recheck_inputs(request)
    bound(isolation_binding, json_data=False)
    original_report = load(request["freeze_report"]["path"])
    for filename, expected_sha in (("source_before.json", original_report["before"]["sha256"]),
            ("source_after.json", original_report["maps"]["source_after.json"]["sha256"])):
        bound({"path": str(validation / "source_integrity" / filename), "sha256": expected_sha}, json_data=False)
    write_new(output / "registered_final_map.json", {"schema_version": 1, "created_utc": now().isoformat(),
        "frozen": str(root), "entries": final_entries, "rsync_exclusions": list(integrity.RSYNC_EXCLUSIONS)})
    report = {"schema_version": 1, "kind": "RELIABILITY_V4_REGISTERED_FULL_SOURCE_SIDECAR", "result": "PASS",
        "created_utc": now().isoformat(), "final_root": str(root), "original_freeze_report": request["freeze_report"],
        "original_draft_map": request["frozen_map"], "final_registered_map": binding(output / "registered_final_map.json"),
        "differences_from_draft": integrity.differences(entries, final_entries), "admission": request["admission"],
        "audit_guard": request["audit_guard"], "protocol_publication": request["protocol_publication"],
        "replay_publication": request["replay_publication"], "guard_check": checked.report,
        "native_validation": request["native_validation"], "original_import_isolation": isolation_binding,
        "original_source_before": binding(validation / "source_integrity/source_before.json"),
        "original_source_after": binding(validation / "source_integrity/source_after.json"),
        "original_cold_build_evidence_retained": True, "current_full_tree_equals_original_draft": False,
        "claim_boundary": "Current full map has exactly the three authorized planning publications. This is not an original cold-build unchanged claim, initial admission, or a flight result."}
    write_new(output / "registered_source_sidecar.json", report)
    return binding(output / "registered_source_sidecar.json")


def run(action, request_path, request_sha256, output_directory):
    request_path, request = bound({"path": str(Path(request_path).absolute()), "sha256": request_sha256})
    require(action in FIELDS and set(request) == FIELDS[action] and request.get("schema_version") == 1
            and request.get("kind") == KIND, "Explicit exact-schema planning publication request required")
    permitted = [] if action == "protocols" else [PLANNING["core"], PLANNING["extension"]]
    if action == "source-sidecar":
        permitted.append(PLANNING["replay"])
    root, results, entries, actual, integrity, guard = base_context(request, permitted_changes=permitted)
    output = Path(output_directory).absolute()
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir()
            and output.resolve().parent == results,
            "A fresh independent evidence directory in actual final results is required")
    output = output.resolve()
    # All semantic validators run before creating backups or changing canonical bytes.
    candidates = prepare_protocols(request, root, guard) if action == "protocols" else (
        prepare_replay(request, root, guard) if action == "replay" else {})
    bound({"path": str(request_path), "sha256": request_sha256}, json_data=False)
    recheck_inputs(request)
    output.mkdir(exist_ok=False)
    tool = binding(__file__)
    write_new(output / "started.json", {"schema_version": 1, "action": action, "created_utc": now().isoformat(),
        "request": binding(request_path), "tool": tool, "final_root": str(root), "audit_guard": request["audit_guard"],
        "atomic_across_files": False, "formal_attempts_started": 0})
    try:
        if action == "source-sidecar":
            detail = {"source_sidecar": sidecar(request, root, entries, actual, integrity, guard, output)}
        else:
            archives = publish_transaction(root, candidates, output)
            detail = {"original_drafts": archives,
                      "canonical_files": {label: binding(planning_file(root, label)) for label in candidates}}
        recheck_inputs(request)
        require(binding(__file__) == tool, "Publication helper changed during the operation")
        outcome = {"schema_version": 1, "kind": "RELIABILITY_V4_PLANNING_PUBLICATION_OUTCOME",
            "action": action, "status": "PUBLISHED", "created_utc": now().isoformat(), "final_root": str(root),
            "audit_guard": request["audit_guard"], "tool": tool, "request": binding(request_path), **detail,
            "atomic_across_files": False, "formal_attempts_started": 0,
            "claim_boundary": "Explicit planning publication only; no initial admission, simulation, or engineering acceptance is claimed."}
        write_new(output / "outcome.json", outcome)
        return outcome
    except BaseException as error:
        write_new(output / "outcome.json", {"schema_version": 1, "kind": "RELIABILITY_V4_PLANNING_PUBLICATION_OUTCOME",
            "action": action, "status": "FAILED_SEE_ORIGINALS_AND_RECOVERY", "created_utc": now().isoformat(),
            "final_root": str(root), "audit_guard": request["audit_guard"], "tool": tool, "error": repr(error),
            "formal_attempts_started": 0, "atomic_across_files": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=tuple(FIELDS))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.action, args.request, args.request_sha256, args.output_directory), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("Planning publication refused: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
