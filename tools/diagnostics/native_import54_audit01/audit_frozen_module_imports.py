"""Posthoc import-path audit; never evidence of historical flight imports.

Only --derive-only is intended for Windows. Native execution must use the
original Humble54 environment and python -B. No model, node or main is called.
The selected modules come solely from differing original-map copy pairs.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import traceback

CLAIM = "CURRENT_POSTHOC_IMPORT_PATH_AND_SOURCE_BYTES_ONLY_NOT_HISTORICAL_FLIGHT_PROOF"
ROOT54 = "/root/uav_tracking_fullplan_v4_humble54"
LIMIT = 16 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT, "Missing/linked/oversized audit input: " + str(path))
    raw = path.read_bytes()
    return {"path": str(path.resolve(strict=True)), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    binding(path)
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))
    require(isinstance(result, dict), "JSON object required")
    return result


def scanned(name):
    return name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and PurePosixPath(name).suffix in {".py", ".sh", ".msg"}


def module_name(canonical):
    parts = PurePosixPath(canonical).with_suffix("").parts
    if parts[0] == "uav_tracking":
        python_parts = parts
        prefix = PurePosixPath()
    else:
        require(len(parts) >= 5 and parts[:2] == ("ros2_ws", "src") and parts[2] == parts[3],
                "No reviewed Python package layout for canonical counterpart: " + canonical)
        python_parts = parts[3:]
        prefix = PurePosixPath(*parts[:3])
    if python_parts[-1] == "__init__":
        python_parts = python_parts[:-1]
    require(python_parts and all(part.isidentifier() for part in python_parts), "Invalid derived Python module name")
    parents = {".".join(python_parts[:index]): (prefix / PurePosixPath(*python_parts[:index]) / "__init__.py").as_posix()
               for index in range(1, len(python_parts))}
    return ".".join(python_parts), parents


def derive(plan, frozen):
    require(plan.get("frozen_root") == frozen.get("frozen") == ROOT54, "Actual original Humble54 root required")
    entries, sources = frozen.get("entries"), plan.get("source_hashes")
    require(isinstance(entries, dict) and entries and isinstance(sources, dict) and sources, "Original complete map/source registration missing")
    for name, entry in entries.items():
        path = PurePosixPath(name)
        require(name and "\\" not in name and ":" not in name and not path.is_absolute()
                and path.as_posix() == name and ".." not in path.parts, "Noncanonical original map name")
        require(isinstance(entry, dict), "Invalid original entry metadata")
    for name, digest in sources.items():
        require(entries.get(name, {}).get("kind") == "file" and entries[name].get("sha256") == digest,
                "Registered canonical hash differs from original full map: " + name)
    extras = {name: entry for name, entry in entries.items() if scanned(name) and name not in sources}
    comparisons, modules, packages = [], {}, {}
    for name, entry in sorted(extras.items()):
        tail = name.partition("/build/lib/")[2]
        matches = [key for key in sources if tail and (key == tail or key.endswith("/" + tail))]
        require(entry.get("kind") == "file" and len(matches) == 1, "Original extra has no unique registered canonical counterpart: " + name)
        canonical = matches[0]
        expected = entries[canonical]
        different = entry["sha256"] != expected["sha256"]
        pair = {"original_extra": name, "canonical_source": canonical, "original_extra_metadata": entry,
                "canonical_metadata": expected, "different_bytes": different}
        if different:
            require(PurePosixPath(canonical).suffix == ".py", "Differing counterpart is not an importable Python source")
            module, parents = module_name(canonical)
            require(module not in modules, "Duplicate differing module derivation")
            modules[module] = {"canonical_source": canonical, "expected": expected, "original_extra": name}
            packages.update(parents)
            pair["derived_module"] = module
        comparisons.append(pair)
    require(modules, "No differing original copies found; no import audit selected")
    for name, canonical in packages.items():
        require(canonical in sources and entries[canonical]["kind"] == "file", "Registered canonical package initializer missing: " + name)
    return {"original_extra_count": len(extras), "differing_module_count": len(modules), "comparisons": comparisons,
            "modules": modules, "packages": packages}


def source_evidence(root, name, metadata):
    path = root / name
    require(path.resolve(strict=True) == path and path.is_file() and not path.is_symlink(), "Changed/linked original source path: " + name)
    actual = binding(path)
    return {**actual, "expected": metadata, "matches_expected": type(metadata.get("bytes")) is int
            and actual["bytes"] == metadata["bytes"] and actual["sha256"] == metadata["sha256"]}


def observe_sources(root, names, entries):
    observations = {}
    for name in sorted(names):
        try:
            observations[name] = source_evidence(root, name, entries[name])
        except Exception as error:
            observations[name] = {"expected": entries[name], "matches_expected": False,
                                  "error_type": type(error).__name__, "error": str(error)}
    return observations


def audit_native(plan, frozen, derivation, record, plan_path, map_path):
    require(os.name == "posix" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22"
            and os.environ.get("ROS_DISTRO") == "humble", "Original UAVHumble22/Humble environment required")
    require(sys.version_info[:2] == (3, 10) and sys.flags.dont_write_bytecode == 1 and sys.dont_write_bytecode is True
            and Path(sys.prefix).resolve() == Path("/root/uav_humble22/venv"), "Original Python 3.10 venv with explicit -B required")
    root = Path(ROOT54).resolve(strict=True)
    require(str(root) == ROOT54, "Actual canonical frozen root required")
    require(Path(plan_path).resolve() == (Path(plan["output"]) / "plan.json").resolve(strict=True)
            and Path(map_path).resolve() == (root / "results/freeze_validation/source_integrity/frozen_actual.json").resolve(strict=True),
            "Actual original core plan and freeze-map paths required")
    entries = frozen["entries"]
    checked = {pair["original_extra"] for pair in derivation["comparisons"]}
    checked.update(value["canonical_source"] for value in derivation["modules"].values())
    checked.update(derivation["packages"].values())
    record["source_scope"] = "ORIGINAL_EXTRA_COPIES_AND_DERIVED_MODULES_WITH_CANONICAL_PACKAGE_INITIALIZERS"
    record["sources_before"] = observe_sources(root, checked, entries)
    require(all(item["matches_expected"] for item in record["sources_before"].values()), "Current source path/bytes/size differ from original before imports")
    for module, selection in sorted(derivation["modules"].items()):
        evidence = {"module": module, **selection, "already_in_sys_modules": module in sys.modules, "result": "NOT_ATTEMPTED"}
        record["module_results"].append(evidence)
        try:
            imported = importlib.import_module(module)
            original_file = Path(imported.__file__)
            actual = original_file.resolve(strict=True)
            evidence.update(reported_file=str(original_file), resolved_file=str(actual),
                            cached_file=getattr(imported, "__cached__", None),
                            loader_type=type(getattr(imported, "__loader__", None)).__name__)
            require(actual == root / selection["canonical_source"], "Imported module is a historical copy or has the wrong canonical path")
            evidence["actual_source"] = source_evidence(root, selection["canonical_source"], selection["expected"])
            require(evidence["actual_source"]["matches_expected"], "Imported canonical source bytes/size changed")
            if "rclpy" in imported.__dict__:
                evidence["ros_imports_ready"] = imported.rclpy is not None and getattr(imported, "Node", object) is not object
                require(evidence["ros_imports_ready"], "ROS adapter imported its development fallback instead of actual Humble dependencies")
            evidence["result"] = "PASS"
        except BaseException as error:
            evidence.update(result="ERROR", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
    record["package_results"] = []
    for module, canonical in sorted(derivation["packages"].items()):
        package = sys.modules.get(module)
        evidence = {"package": module, "canonical_source": canonical, "result": "ERROR"}
        record["package_results"].append(evidence)
        try:
            actual = Path(package.__file__).resolve(strict=True)
            paths = [Path(value).resolve(strict=True) for value in package.__path__]
            evidence.update(resolved_file=str(actual), resolved_package_paths=[str(value) for value in paths])
            require(actual == root / canonical and paths == [actual.parent], "Imported package path escaped its original canonical package")
            evidence["actual_source"] = source_evidence(root, canonical, entries[canonical])
            require(evidence["actual_source"]["matches_expected"], "Imported canonical package bytes/size changed")
            evidence["result"] = "PASS"
        except Exception as error:
            evidence.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    record["sources_after"] = observe_sources(root, checked, entries)
    require(record["sources_before"] == record["sources_after"], "Audited source paths/bytes changed during imports")
    require(len(record["module_results"]) == derivation["differing_module_count"]
            and all(item["result"] == "PASS" for item in record["module_results"] + record["package_results"]),
            "At least one current module/package import audit failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--frozen-map", type=Path, required=True)
    parser.add_argument("--frozen-map-sha256", required=True)
    parser.add_argument("--derive-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    own_directory = Path(__file__).resolve().parent
    require(output.is_relative_to(own_directory) and output != own_directory and output.suffix == ".json"
            and not output.exists(), "Independent new JSON inside this external audit directory required")
    # Reserve exclusively before work so exceptions are recorded without touching
    # any original receipt, source or target process. No target entrypoint is called.
    with output.open("x", encoding="utf-8") as handle:
        record = {"schema_version": 1, "kind": "FROZEN_MODULE_CURRENT_IMPORT_SOURCE_AUDIT", "claim_boundary": CLAIM,
            "started_utc": datetime.now(timezone.utc).isoformat(), "result": "ERROR", "derive_only": args.derive_only,
            "python": {"executable": sys.executable, "version": sys.version, "prefix": sys.prefix,
                       "dont_write_bytecode": sys.dont_write_bytecode, "flag_B": sys.flags.dont_write_bytecode},
            "environment": {key: os.environ.get(key) for key in ("WSL_DISTRO_NAME", "ROS_DISTRO", "PYTHONPATH", "AMENT_PREFIX_PATH", "LD_LIBRARY_PATH")},
            "sys_path": list(sys.path), "module_results": [], "script": binding(__file__), "argv": sys.argv}
        record["project_modules_before"] = sorted(name for name in sys.modules if name.startswith(("uav_tracking", "uav_tracking_nodes", "uav_tracking_px4_adapter")))
        code = 2
        try:
            record["inputs"] = {"plan": binding(args.plan), "frozen_map": binding(args.frozen_map)}
            require(record["inputs"]["plan"]["sha256"] == args.plan_sha256
                    and record["inputs"]["frozen_map"]["sha256"] == args.frozen_map_sha256, "Original plan/map SHA differs from explicit input pins")
            plan, frozen = load(args.plan), load(args.frozen_map)
            record["derivation"] = derive(plan, frozen)
            if args.derive_only:
                record["result"] = "DERIVATION_ONLY_NO_TARGET_IMPORT_OR_NATIVE_VALIDATION"
            else:
                audit_native(plan, frozen, record["derivation"], record, args.plan, args.frozen_map)
                record["result"] = "PASS_CURRENT_IMPORT_AUDIT_ONLY"
            require(record["inputs"] == {"plan": binding(args.plan), "frozen_map": binding(args.frozen_map)}
                    and record["script"] == binding(__file__), "Audit input/script changed during execution")
            code = 0
        except BaseException as error:
            record.update(result="INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "ERROR",
                          error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
            code = 130 if isinstance(error, KeyboardInterrupt) else 2
        finally:
            record["project_modules_after"] = sorted(name for name in sys.modules if name.startswith(("uav_tracking", "uav_tracking_nodes", "uav_tracking_px4_adapter")))
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            record["exit_code"] = code
            json.dump(record, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps({"output": str(output), "result": record["result"], "exit_code": code,
                          "claim_boundary": CLAIM}, indent=2))
        return code


if __name__ == "__main__":
    raise SystemExit(main())
