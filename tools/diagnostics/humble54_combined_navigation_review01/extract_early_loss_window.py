"""Reuse the pinned exporter for the fixed early-loss window, after native idle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types


EXTRACTOR_SHA = "364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4"
PLAN_SHA = "f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055"
TERMINAL_SHA = "596db684d39afe1eb561b710550541728a71e5e6c564118a1206d204c557c677"
IDLE_SHA = "87c0d015a92eafc3211bd9d2fdb5cf9231332a761d5b656c78419cb002ca1e2b"
SLOT = "person_extension_combined_seed004"


def checked_bytes(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Pinned source changed: " + str(path))
    return data


def specialize_manifest(manifest, wrapper):
    if manifest["slot_id"] != SLOT:
        raise ValueError("This fixed diagnostic applies only to the original person combined slot")
    manifest["original_short_window_not_selection_basis"] = manifest.pop("original_short_window")
    manifest["selection"] = {
        "start_s_decimal": "33.8", "end_s_decimal": "35.2", "inclusive": True,
        "basis": "Fixed source acquisition window around the already observed first LOST; all recorded opportunities retained",
        "raw_rgb_hard_limit": 32, "success_or_failure_selection": False,
    }
    manifest["extraction_kind"] = "POST_HOC_EARLY_LOSS_INPUT_DELIVERY_DIAGNOSIS_NOT_SHORT_SHUTTER_EVIDENCE"
    manifest["wrapper"] = wrapper
    manifest["claim_boundary"] += (
        " This wrapper changes only the descriptive extraction window. The original short-shutter "
        "window is retained separately and is not the image-selection basis. This export cannot "
        "be used as the fixed short-shutter sensor evidence attachment. Expected DROP and actual "
        "delivery must be compared separately; no original FAIL is changed."
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--execute-after-native-idle", action="store_true")
    parser.add_argument("--describe", action="store_true")
    args, rest = parser.parse_known_args(argv)
    if args.describe or not args.execute_after_native_idle:
        print(json.dumps({"status": "PREPARED_NOT_EXECUTED", "slot_id": SLOT,
                          "source_window_s": [33.8, 35.2], "experimental_inputs_opened": False}))
        return 0
    if sys.platform != "linux" or os.environ.get("WSL_DISTRO_NAME") != "UAVHumble22":
        raise ValueError("Actual extraction requires native UAVHumble22")
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    helper = root / "tools/diagnostics/humble54_dropout_gap01/extract_short_window.py"
    code = checked_bytes(helper, EXTRACTOR_SHA)
    idle = Path("/mnt/d/WSL/UAVHumble22-validation/check_humble54_native_idle02.sh")
    checked_bytes(idle, IDLE_SHA)
    subprocess.run(["bash", str(idle)], check=True)
    module = types.ModuleType("humble54_bound_early_loss_input_exporter")
    module.__file__ = str(helper)
    sys.modules[module.__name__] = module
    exec(compile(code, str(helper), "exec"), module.__dict__)
    original_bind = module.bind_inputs
    wrapper = {"path": str(Path(__file__).resolve()),
               "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "invocation_utc": datetime.now(timezone.utc).isoformat(),
               "bound_helper_sha256": EXTRACTOR_SHA, "idle_query_sha256": IDLE_SHA}

    def bind(source, plan, slot):
        if slot != SLOT:
            raise ValueError("Only the original bound slot is permitted")
        checked_bytes(plan, PLAN_SHA)
        checked_bytes(plan.parent / "slots" / (slot + ".json"), TERMINAL_SHA)
        manifest, bag, reader = original_bind(source, plan, slot)
        return specialize_manifest(manifest, wrapper), bag, reader

    module.bind_inputs = bind
    sys.argv = [str(helper), *rest]
    module.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
