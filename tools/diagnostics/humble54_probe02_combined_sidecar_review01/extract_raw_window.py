"""Export the probe02 first-loss raw input window using the reviewed exporter.

Explicit native idle execution only; no simulation, inference or rescoring.
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


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "tools/diagnostics/humble54_dropout_gap01/extract_short_window.py"
HELPER_SHA = "364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4"
GUARD = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
GUARD_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"
PLAN_SHA = "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"
TERMINAL_SHA = "f57d22dff4989c8bbb45b56ba2151d66e52b5689984cd0a0104f531d4749b655"
SLOT = "person_extension_combined_seed004"


def checked(path, expected):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 1024**2:
        raise ValueError("Bounded ordinary small source required")
    with path.open("rb") as stream:
        raw = stream.read(1024**2 + 1)
    if len(raw) > 1024**2 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Pinned input differs: " + str(path))
    return raw


def module(path, digest, name):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    sys.modules[name] = result
    exec(compile(checked(path, digest), str(path), "exec"), result.__dict__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--execute-after-native-idle", action="store_true")
    parser.add_argument("--describe", action="store_true")
    args, rest = parser.parse_known_args()
    if args.describe or not args.execute_after_native_idle:
        print(json.dumps({"status": "PREPARED_NOT_EXECUTED", "slot": SLOT,
                          "window_source_s": [33.8, 35.2], "bag_opened": False,
                          "purpose": "RAW_INPUT_DELIVERY_DIAGNOSIS_NOT_SHORT_SHUTTER_SENSOR_ATTACHMENT"}))
        return 0
    if sys.platform != "linux" or os.environ.get("WSL_DISTRO_NAME") != "UAVHumble22":
        raise ValueError("Native UAVHumble22 execution required")
    helper = module(HELPER, HELPER_SHA, "probe02_bound_raw_window_exporter")
    guard = module(GUARD, GUARD_SHA, "probe02_existing_native_idle_guard")
    bind_original = helper.bind_inputs
    wrapper = {"path": str(Path(__file__).resolve()),
               "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "invocation_utc": datetime.now(timezone.utc).isoformat(),
               "helper_sha256": HELPER_SHA, "native_guard_sha256": GUARD_SHA}

    def bind(source, plan, slot):
        if slot != SLOT:
            raise ValueError("Only the original probe02 person combined slot is permitted")
        checked(plan, PLAN_SHA)
        checked(plan.parent / "slots" / (slot + ".json"), TERMINAL_SHA)
        manifest, bag, reader = bind_original(source, plan, slot)
        manifest["original_short_window_not_selection_basis"] = manifest.pop("original_short_window")
        manifest["selection"] = {
            "start_s_decimal": "33.8", "end_s_decimal": "35.2", "inclusive": True,
            "basis": "Post-hoc bounded source window surrounding first LOST in the existing small sidecars",
            "raw_rgb_hard_limit": 32, "success_or_failure_selection": False}
        manifest["extraction_kind"] = "POST_HOC_EARLY_LOSS_INPUT_DELIVERY_DIAGNOSIS_NOT_SHORT_SHUTTER_EVIDENCE"
        manifest["wrapper"] = wrapper
        manifest["claim_boundary"] += " This is first-loss diagnosis only; it cannot serve as the fixed short-shutter sensor4 attachment. Expected DROP and actual recorded input/output are separate. No original FAIL changes."
        return manifest, bag, reader

    helper.bind_inputs = bind
    with guard.linux_idle_guard() as idle:
        wrapper["actual_idle_guard"] = idle
        original_argv = sys.argv
        try:
            sys.argv = [str(HELPER), *rest]
            helper.main()
        finally:
            sys.argv = original_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
