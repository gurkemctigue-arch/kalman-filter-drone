"""Check small profile02 preparation metadata; staging is deliberately disabled.

No subprocesses, native source map reads, model reads, staging or registration.
The actual owner launch/closure files and collector pins are not yet bound.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import types


PROJECT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE_SHA256 = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
EXTENSION_SHA256 = "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"
EXTENSION_DIGEST = "837e533b75800c4c3fdd19f4937d55d92e50fe833da5c6b8801494dfbc77d15b"
CONTRACT_SHA256 = "11bcebbe460eecc24c9c5bc920f977b421013c9df862f60e667e5ee07f3625e3"
CONTRACT_DIGEST = "7c689e742d0a5451ac995b1a1bd2efa14ad6f74c14e2056359877f18cafd868e"
CREATION_SHA256 = "11502f9654847188e9b73003843ccba471e76b1ada8564a99463f5da45e5c2b9"
OVERRIDES = {
    "extension_sha": EXTENSION_SHA256,
    "extension_digest": EXTENSION_DIGEST,
    "contract_sha": CONTRACT_SHA256,
    "contract_digest": CONTRACT_DIGEST,
}


class Refused(ValueError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def small_file(root, relative, expected_sha):
    path = root / relative
    require(not path.is_symlink() and path.is_file(), "Ordinary small metadata file required: " + relative)
    payload = path.read_bytes()
    require(len(payload) < 1024 * 1024 and sha(payload) == expected_sha, "Fixed small metadata pin differs: " + relative)
    return payload


def check(project=PROJECT):
    """Return a prospective profile; it is never passed to the staging driver."""
    project = Path(project)
    base_relative = "tools/staging/final55_offline_overlay_20261103/stage.py"
    base_payload = small_file(project, base_relative, BASE_SHA256)
    # Exact reviewed source bytes bypass .pyc. Its __main__ never runs here.
    base = types.ModuleType("fixed_profile01_metadata_only")
    base.__file__ = str(project / base_relative)
    exec(compile(base_payload, base.__file__, "exec"), base.__dict__)
    profile = deepcopy(base.PROFILE)
    profile.update(OVERRIDES)
    require({key for key in profile if profile[key] != base.PROFILE[key]} == set(OVERRIDES),
            "Only four reviewed prospective profile pins may differ")
    extension_relative = "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
    extension = json.loads(small_file(project, extension_relative, EXTENSION_SHA256))
    require(extension.get("plan_sha256") == EXTENSION_DIGEST
            and sha(canonical({key: value for key, value in extension.items() if key != "plan_sha256"})) == EXTENSION_DIGEST,
            "New plan content digest differs")
    require(extension.get("mode") == "EXTENSION_PROBE" and extension.get("selected_seeds") == [4]
            and len(extension.get("trials", [])) == 16, "New complete extension16 registration differs")
    contract_relative = "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.json"
    contract = json.loads(small_file(project, contract_relative, CONTRACT_SHA256))
    require(sha(canonical(contract)) == CONTRACT_DIGEST
            and contract.get("source_plan") == {"path": extension["output"] + "/plan.json", "sha256": EXTENSION_SHA256},
            "New external contract source binding differs")
    old_relative = "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical02.json"
    old = json.loads(small_file(project, old_relative, base.PROFILE["contract_sha"]))
    expected = deepcopy(old)
    expected["source_plan"] = contract["source_plan"]
    require(contract == expected, "New contract changes more than source_plan")
    creation_relative = "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.creation.json"
    creation = json.loads(small_file(project, creation_relative, CREATION_SHA256))
    require(creation["new_contract"]["sha256"] == CONTRACT_SHA256
            and creation["new_contract"]["canonical_sha256"] == CONTRACT_DIGEST
            and creation["source_plan"]["sha256"] == EXTENSION_SHA256
            and creation["change_paths"] == ["source_plan.path", "source_plan.sha256"],
            "Actual creation provenance differs")
    cells = [{"slot_id": trial["id"], "target_class": trial["target_class"], "condition": trial["extension_condition"]}
             for trial in extension["trials"] if trial.get("extension_condition") in {"dropout", "combined"}]
    require(contract["dev_slots"] == cells and len(cells) == 4, "New four evidence cells differ")
    return {
        "status": "PREPARATION_METADATA_VALID_NOT_EXECUTABLE",
        "profile_id": "final55_offline_overlay_profile02_preparation_20261103",
        "profile_overrides": OVERRIDES,
        "owner_closure_bound": False,
        "collector_production_pins_bound": False,
        "claim_boundary": "Small metadata preparation only. No staging, cold build, native task, evaluator, flight, gate or formal registration.",
    }


def refuse_execution():
    raise Refused("profile02 preparation is disabled: actual fixed collector pins and independently observed Windows owner/WSL exit closure are not reviewed or bound; no staging is available")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Always refused by this preparation-only tool")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            refuse_execution()
        print(json.dumps(check(), indent=2, allow_nan=False))
        return 0
    except (OSError, Refused, KeyError, TypeError, ValueError, SyntaxError) as error:
        print(json.dumps({"status": "REFUSED_NO_STAGING_OR_NATIVE_TASK", "error": f"{type(error).__name__}: {error}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
