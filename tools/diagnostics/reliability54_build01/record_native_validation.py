"""Record actual new-build FastCDR selection, isolation and generated CDR."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
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
    match = re.search(r"(?:^|\n)Ran ([1-9][0-9]*) tests? in [^\r\n]+\r?\n\r?\nOK(?: \(skipped=([0-9]+)\))?\s*\Z", text)
    if match is None:
        raise ValueError("Full native unittest log does not end with a successful suite result")
    return {"tests": int(match.group(1)), "skipped": int(match.group(2) or 0)}


def record(root, reference):
    root, reference = root.resolve(strict=True), reference.resolve(strict=True)
    if root == reference or not re.fullmatch(r"/root/uav_tracking_fullplan_[a-zA-Z0-9_]+", str(root)):
        raise ValueError("Expected a new dedicated frozen root distinct from reference")
    output = root / "results/freeze_validation/native_build_supplement.json"
    if output.exists() or output.is_symlink():
        raise FileExistsError("Native build supplement already exists")
    evidence = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "ACTUAL_COLD_BUILD_COMPILER_ISOLATION_AND_GENERATED_CDR_NOT_FLIGHT_ACCEPTANCE",
                "root": str(root), "reference": str(reference), "status": "FAIL"}
    try:
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
    args = parser.parse_args()
    record(args.root, args.reference)
