"""Disabled registration gate for the preserved probe02 continuation.

This source contains no actual prefix, owner-chain instance or approved unknown
exception. Root must register actual closed evidence and immutable source pins
before production use. The prepared collector source remains unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PROFILE_STATUS = "PREPARED_NOT_REGISTERED"
REGISTERED_PROFILE_SHA256 = None
CHAIN_VALIDATOR_SHA256 = None
CHAIN_VALIDATOR = ROOT / "tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_chain.py"
COLLECTOR = ROOT / "tools/experiment_orchestration/humble54_pending_collector05_source/collect_humble54_pending05.py"
PLAN = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
ENTRY = Path("D:/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh") if sys.platform == "win32" else Path("/mnt/d/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh")
NATIVE_OUTPUT = Path("/root/uav_tracking_collection54_probe02_owner05")
PINS = {
    "collector": "f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1",
    "plan": "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54",
    "entry": "d9cc1f1876a5ed9a358697b29644e7aa7a3c192e0bdd2a2a7d37c208e74f06a6",
    "runner": "069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11",
}
STABLE_CHAIN_FIELDS = ("status", "plan", "after_slot", "closed_ids", "pending_ids", "closed", "input_bindings")


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def small_json(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, "Small registered JSON required")
    value = json.loads(path.read_text(encoding="utf8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    require(isinstance(value, dict), "Registered profile must be an object")
    return value


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def check_registered_sources(profile_path):
    require(PROFILE_STATUS == "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN"
            and isinstance(REGISTERED_PROFILE_SHA256, str) and len(REGISTERED_PROFILE_SHA256) == 64
            and isinstance(CHAIN_VALIDATOR_SHA256, str) and len(CHAIN_VALIDATOR_SHA256) == 64,
            "No actual closed-prefix registration exists; production gate remains disabled")
    paths = {"collector": COLLECTOR, "plan": PLAN, "entry": ENTRY}
    for name, path in paths.items():
        require(sha(path) == PINS[name], "Registered source differs: " + name)
    require(sha(profile_path) == REGISTERED_PROFILE_SHA256, "Actual registered profile raw SHA differs")
    require(sha(CHAIN_VALIDATOR) == CHAIN_VALIDATOR_SHA256, "Actual chain-validator source raw SHA differs")
    plan = small_json(PLAN)
    runner = Path(plan["frozen_root"]) / "scripts/run_reliability_v4.py"
    require(sha(runner) == PINS["runner"], "Original frozen runner differs")
    return plan, runner


def check_chain_result(audit, plan, *, local_path=Path):
    require(audit.get("status") == "BOUND_PRESERVED_PREFIX_CHAIN", "Closed chain does not admit a partial continuation")
    original_plan = audit["plan"]
    require(local_path(original_plan["path"]).resolve(strict=True) == PLAN.resolve(strict=True)
            and original_plan["sha256"] == PINS["plan"]
            and original_plan["plan_sha256"] == plan["plan_sha256"], "Chain belongs to a different original plan")
    ids = [trial["id"] for trial in plan["trials"]]
    require(len(ids) == 16 and len(set(ids)) == 16, "Expected unchanged original sixteen-slot plan")
    closed = audit["closed_ids"]
    pending = audit["pending_ids"]
    require(isinstance(closed, list) and isinstance(pending, list) and 0 < len(closed) < len(ids)
            and closed == ids[:len(closed)] and pending == ids[len(closed):]
            and audit["after_slot"] == closed[-1], "Continuation is not the exact contiguous original closed prefix")
    require([row["id"] for row in audit["closed"]] == closed, "Closed evidence rows differ from the admitted prefix")
    require(isinstance(audit.get("input_bindings"), list) and audit["input_bindings"], "Chain input bindings are missing")
    return {name: audit[name] for name in STABLE_CHAIN_FIELDS}


class ChainBoundValidator:
    """Recheck the old closed chain before every unchanged original source scan.

    The chain validator does not inspect pending output paths, so new slots from
    this owner cannot make the old chain invalid. No marker/terminal pin is put
    into collector HISTORY; its unknown-evidence behavior stays unchanged.
    """
    def __init__(self, original, revalidate, admitted):
        self.original = original
        self.revalidate = revalidate
        self.admitted = admitted

    def __getattr__(self, name):
        return getattr(self.original, name)

    def source_hashes(self, root):
        require(self.revalidate() == self.admitted, "Previously admitted owner-chain evidence changed")
        return self.original.source_hashes(root)


def save_new(path, value):
    with Path(path).open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def publish_admission(path, value):
    """Publish a complete ext4 admission inode atomically without replacement."""
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)  # Same directory/filesystem; refuses any existing destination.
    finally:
        temporary.unlink(missing_ok=True)


def run(profile_path, output, execute):
    profile_path = profile_path.resolve(strict=True)
    plan, runner_path = check_registered_sources(profile_path)
    profile = small_json(profile_path)
    chain = module_at("humble54_registered05_owner_chain", CHAIN_VALIDATOR)
    collector = module_at("humble54_registered05_prepared_collector", COLLECTOR)
    original = module_at("humble54_registered05_original_runner", runner_path)

    def revalidate():
        check_registered_sources(profile_path)
        return check_chain_result(chain.validate_continuation_profile(profile), plan, local_path=chain.v.local_path)

    admitted = revalidate()
    validator = ChainBoundValidator(original, revalidate, admitted)
    pins = {"plan": PINS["plan"], "entry": PINS["entry"],
            "capture_profiles": collector.CAPTURE_PROFILES, "history": {},
            "minimum_prefix": len(admitted["closed_ids"])}
    _, closed, pending = collector.initial_check(PLAN, ENTRY, admitted["after_slot"], pins, validator)
    require([row["slot_id"] for row in closed] == admitted["closed_ids"]
            and [row["id"] for row in pending] == admitted["pending_ids"], "Original collector and chain prefix disagree")
    for observed, bound in zip(closed, admitted["closed"]):
        require(observed["original_marker"]["sha256"] == bound["marker"]["sha256"]
                and observed["original_terminal"]["sha256"] == bound["terminal"]["sha256"], "Original collector did not see the chain-bound raw records")
    if not execute:
        return {"status": "REGISTERED_CHECK_ONLY_NOT_STARTED", "after_slot": admitted["after_slot"],
                "closed_ids": admitted["closed_ids"], "pending_ids": admitted["pending_ids"], "returncode": 0}
    require(sys.platform == "linux" and output == NATIVE_OUTPUT, "Actual execution requires the fixed fresh native owner05 output")
    require(not output.exists(), "Native owner05 output must be entirely fresh")
    admission_path = output.with_name(output.name + ".admission.json")
    require(not admission_path.exists(), "Admission record must be entirely fresh")
    for prior in (Path(plan["frozen_root"]).resolve(), PLAN.parent.resolve(), Path(plan["results_root"]).resolve()):
        require(not output.resolve().is_relative_to(prior) and not prior.is_relative_to(output.resolve()), "Native output overlaps original frozen inputs or results")
    admission = {"scope": "REGISTERED_PREFIX_ADMISSION_BEFORE_NEW_OWNER05_CHILDREN", "utc": utc(),
                 "gate_source": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
                 "profile": {"path": str(profile_path), "sha256": REGISTERED_PROFILE_SHA256},
                 "chain_validator": {"path": str(CHAIN_VALIDATOR.resolve()), "sha256": CHAIN_VALIDATOR_SHA256},
                 "collector": {"path": str(COLLECTOR.resolve()), "sha256": PINS["collector"]},
                 "owner_identity": collector.process_binding(os.getpid()),
                 "plan": admitted["plan"], "after_slot": admitted["after_slot"],
                 "closed_ids": admitted["closed_ids"], "pending_ids": admitted["pending_ids"],
                 "chain_admission": admitted, "unknown_evidence_exceptions": {}, "automatic_retry": False}
    publish_admission(admission_path, admission)
    result = collector.collect(PLAN, ENTRY, admitted["after_slot"], output, pins, validator)
    revalidate()
    save_new(output / "registered_entry_terminal.json", {"finished_utc": utc(),
        "gate_source": admission["gate_source"], "profile": admission["profile"],
        "admission": {"path": str(admission_path), "sha256": sha(admission_path)},
        "native_terminal": {"path": str(output / "terminal.json"), "sha256": sha(output / "terminal.json")},
        "status": result["status"], "returncode": result["returncode"]})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=NATIVE_OUTPUT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(PROFILE_STATUS == "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN", "No actual closed-prefix registration exists; production gate remains disabled")
        result = run(args.profile, args.output, args.execute)
        print(json.dumps(result, allow_nan=False))
        return result.get("returncode", 0)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"status": "REFUSED_OR_STOPPED_NO_AUTOMATIC_RETRY", "error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
