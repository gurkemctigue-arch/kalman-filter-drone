"""Record actual new-build FastCDR selection, isolation and generated CDR."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re

REGISTRATIONS = ("config/dds_runtime_humble22.json", "config/ros_gz_runtime_humble22.json",
                 "config/ros_gz_clock_runtime_humble22.json", "config/px4_magnetic_runtime.json",
                 "config/gazebo_magnetic_runtime_humble22.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiler_selection(text, expected):
    values = re.findall(r"^fastcdr_DIR:[^=\r\n]+=([^\r\n]+)$", text, re.MULTILINE)
    if len(values) != 1 or Path(values[0]).resolve() != Path(expected).resolve():
        raise ValueError("CMakeCache does not select the declared system FastCDR compiler package")
    return values[0]


def successful_suite(text):
    # unittest writes its summary to stderr. Buffered stdout from the tests can
    # arrive afterwards in a merged pipe, despite a successful process exit.
    summaries = re.findall(r"^Ran ([0-9]+) tests? in [^\r\n]+\r?\n\r?\n([^\r\n]+)", text, re.MULTILINE)
    if len(summaries) != 1 or int(summaries[0][0]) <= 0:
        raise ValueError("Full native unittest log must contain one successful suite result")
    result = re.fullmatch(r"OK(?: \(skipped=([0-9]+)\))?", summaries[0][1])
    if result is None:
        raise ValueError("Full native unittest log must contain one successful suite result")
    return {"tests": int(summaries[0][0]), "skipped": int(result.group(1) or 0)}


def verify_original_freeze(root):
    """Bind the actual zero build exit and recheck unchanged frozen bytes."""
    directory = root / "results/freeze_validation/source_integrity"
    report_path = directory / "source_frozen_integrity.json"
    report = json.loads(report_path.read_text())
    if not (report.get("status") == "PASS" and report.get("build_returncode") == 0
            and report.get("source_unchanged") is True and report.get("copy_identical") is True
            and Path(report["frozen"]).resolve() == root):
        raise ValueError("Original public freeze did not pass its source maps with a zero build/test exit")
    actual_path = directory / "frozen_actual.json"
    if digest(actual_path) != report["maps"]["frozen_actual.json"]["sha256"]:
        raise ValueError("Original frozen file map changed")
    expected = json.loads(actual_path.read_text())
    if Path(expected["frozen"]).resolve() != root:
        raise ValueError("Original file map belongs to another frozen root")
    helper_relative = "tools/diagnostics/reliability54_build01/source_integrity.py"
    helper_path = root / helper_relative
    if digest(helper_path) != expected["entries"][helper_relative]["sha256"]:
        raise ValueError("Original frozen integrity helper changed")
    specification = importlib.util.spec_from_file_location("original_frozen_source_integrity", helper_path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    current = module.file_map(root)
    link = root / "results"
    if not link.is_symlink() or link.resolve(strict=True) != Path(report["generated_results_link"]["expected_store"]).resolve(strict=True):
        raise ValueError("Original results link changed")
    current.pop("results")
    difference = module.differences(expected["entries"], current)
    if any(difference.values()):
        raise ValueError("Frozen bytes changed after original tests: " + json.dumps(difference))
    return {"report": str(report_path), "report_sha256": digest(report_path),
            "original_build_and_full_suite_returncode": 0, "current_frozen_bytes_unchanged": True,
            "complete_file_entries": len(current), "original_map_sha256": digest(actual_path)}


def record(root, reference, output=None):
    root, reference = root.resolve(strict=True), reference.resolve(strict=True)
    if root == reference or not re.fullmatch(r"/root/uav_tracking_fullplan_[a-zA-Z0-9_]+", str(root)):
        raise ValueError("Expected a new dedicated frozen root distinct from reference")
    validation_directory = root / "results/freeze_validation"
    output = validation_directory / "native_build_supplement.json" if output is None else output.resolve()
    if output.parent.resolve() != validation_directory.resolve() or output.suffix != ".json":
        raise ValueError("Supplement must be a new JSON in the original validation directory")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Native build supplement already exists")
    evidence = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "ACTUAL_COLD_BUILD_COMPILER_ISOLATION_AND_GENERATED_CDR_NOT_FLIGHT_ACCEPTANCE",
                "root": str(root), "reference": str(reference), "status": "FAIL",
                "validator": {"path": str(Path(__file__).resolve()), "sha256": digest(__file__)}}
    try:
        evidence["original_freeze_and_current_bytes"] = verify_original_freeze(root)
        registrations = {}
        for name in REGISTRATIONS:
            current, previous = root / name, reference / name
            value = digest(current)
            if value != digest(previous):
                raise ValueError("Runtime registration differs from reviewed reference: " + name)
            registrations[name] = {"path": str(current), "reference_path": str(previous), "sha256": value}
        evidence["runtime_registration_bytes"] = registrations
        cache = root / "ros2_ws/build/uav_tracking_interfaces/CMakeCache.txt"
        declared = "/opt/ros/humble/lib/cmake/fastcdr"
        selected = compiler_selection(cache.read_text(), declared)
        config = Path(declared) / "fastcdr-config.cmake"
        evidence["compiler_fastcdr"] = {"cmake_cache": str(cache), "cache_sha256": digest(cache),
                                         "selected_directory": selected, "config_sha256": digest(config)}
        isolation_path = root / "results/freeze_validation/import_isolation.json"
        isolation = json.loads(isolation_path.read_text())
        if isolation.get("isolated") is not True or Path(isolation["root"]).resolve() != root:
            raise ValueError("Public frozen module/ament isolation did not pass for this root")
        evidence["public_import_isolation"] = {"path": str(isolation_path), "sha256": digest(isolation_path), "isolated": True}
        from rclpy.serialization import serialize_message, deserialize_message
        from uav_tracking_interfaces.msg import TargetObservation, TargetObservationArray
        generated = Path(importlib.import_module(TargetObservation.__module__).__file__).resolve(strict=True)
        if not generated.is_relative_to(root / "ros2_ws"):
            raise ValueError("Generated CDR message imported from outside this new root")
        source = TargetObservation()
        source.header.stamp.sec, source.header.stamp.nanosec = 12, 300000000
        source.header.frame_id = "camera_optical_frame"
        source.candidate_id, source.acquisition_epoch = 7, 2**64 - 1
        source.surface_recovery_enabled, source.surface_measurement_supported = True, True
        source.navigation_exclusive_depth_complete = True
        source.navigation_exclusive_expected_pixel_count = source.navigation_exclusive_valid_pixel_count = 1
        source.navigation_exclusive_points_camera_m = [1.25, -2.5, 4.]
        frame = TargetObservationArray()
        frame.header, frame.observations = source.header, [source, TargetObservation()]
        wire = serialize_message(frame)
        decoded = deserialize_message(wire, TargetObservationArray)
        first, default = decoded.observations
        assert decoded.header == frame.header and first.header == source.header
        assert first.candidate_id == 7 and first.acquisition_epoch == 2**64 - 1
        assert first.surface_recovery_enabled and first.surface_measurement_supported
        assert first.navigation_exclusive_depth_complete
        assert first.navigation_exclusive_expected_pixel_count == first.navigation_exclusive_valid_pixel_count == 1
        assert list(first.navigation_exclusive_points_camera_m) == [1.25, -2.5, 4.]
        assert not default.surface_recovery_enabled and not default.surface_measurement_supported
        assert default.acquisition_epoch == 0 and not default.navigation_exclusive_depth_complete
        evidence["actual_generated_cdr"] = {"status": "PASS", "wire_bytes": len(wire),
                                           "generated_message_file": str(generated),
                                           "fields": ["uint64_epoch_max", "surface_flags", "exclusive_native_points", "independent_default_candidate"]}
        suite = root / "results/freeze_validation/unittest.log"
        evidence["full_suite"] = {"path": str(suite), "sha256": digest(suite),
                                  **successful_suite(suite.read_text()),
                                  "scope": "Public freeze reached supplement only after its full-suite exit code zero"}
        suite_environment = root / "results/freeze_validation/full_suite_environment.json"
        actual_environment = json.loads(suite_environment.read_text())
        if actual_environment["environment"].get("UAV_TRACKING_DDS_RUNTIME_CONFIG") != str(root / "config/dds_runtime_humble22.json"):
            raise ValueError("Full native suite did not inherit this frozen DDS registration")
        evidence["full_suite_environment"] = {"path": str(suite_environment), "sha256": digest(suite_environment),
                                                "receipt": actual_environment}
        evidence["environment"] = {name: os.environ.get(name) for name in (
            "ROS_DISTRO", "TMPDIR", "STAGE1_FASTCDR_CMAKE_DIR", "UAV_TRACKING_DDS_RUNTIME_CONFIG",
            "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH", "PYTHONPATH", "LD_LIBRARY_PATH")}
        evidence["status"] = "PASS"
    except BaseException as error:
        evidence["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"status": evidence["status"], "receipt": str(output)}), flush=True)
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="New independent supplement; existing reports are never overwritten")
    args = parser.parse_args()
    record(args.root, args.reference, args.output)
