#!/usr/bin/env python3
"""Configure an opt-in Gazebo ENU/gauss + patched PX4 FRD sensor contract.

The original world stays unchanged. Its magnetic_field value is preserved:
Gazebo 8.15 overwrites that initialization with its own geolocation lookup.
This is distinct from the older coherent_wmm world-declaration intervention.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from prepare_px4_magnetic_compatibility import (
    CONTRACT, PROJECT, PATCHED_SHA256, sha256, validate_runtime_manifest,
)

DEFAULT_LOOKUP = PROJECT / "config/gazebo_magnetic_reference.json"


def identity_pose(element: ET.Element, description: str, *, translation_allowed: bool = False) -> list[float]:
    pose = element.find("pose")
    values = [0.] * 6 if pose is None else [float(x) for x in (pose.text or "").split()]
    if (len(values) != 6 or not all(math.isfinite(x) for x in values)
            or any(abs(x) > 1e-12 for x in values[3 if translation_allowed else 0:])
            or (pose is not None and pose.attrib.get("relative_to"))):
        raise ValueError("unsupported nonidentity magnetic mount: " + description)
    return values


def sensor_mount_evidence(px4_root: Path, project_root: Path = PROJECT) -> dict:
    px4_models = Path(px4_root) / "Tools/simulation/gz/models"
    paths = {"x500_base": px4_models / "x500_base/model.sdf",
             "x500": px4_models / "x500/model.sdf"}
    custom = Path(project_root) / "ros2_ws/src/uav_tracking_bringup/models"
    paths.update({name: custom / name / "model.sdf" for name in ("x500_stage1", "x500_stage3")})
    models = {name: ET.parse(path).getroot().find("model") for name, path in paths.items()}
    base = models["x500_base"]
    if base is None:
        raise ValueError("x500_base model missing")
    body = base.find("link[@name='base_link']")
    if body is None:
        raise ValueError("base_link missing")
    sensors = base.findall(".//sensor[@type='magnetometer']")
    sensor = body.find("sensor[@name='magnetometer_sensor']")
    if len(sensors) != 1 or sensor is None or sensors[0] is not sensor:
        raise ValueError("expected exactly one body-mounted inherited magnetic sensor")
    poses = {"x500_base": identity_pose(base, "x500_base", translation_allowed=True),
             "base_link": identity_pose(body, "base_link", translation_allowed=True),
             "magnetometer_sensor": identity_pose(sensor, "magnetometer_sensor")}
    for name, inherited in (("x500", "x500_base"), ("x500_stage1", "x500"), ("x500_stage3", "x500")):
        model = models[name]
        if model is None:
            raise ValueError("missing inherited magnetic model: " + name)
        identity_pose(model, name, translation_allowed=True)
        includes = model.findall("include")
        if (len(includes) != 1 or includes[0].findtext("uri") != "model://" + inherited
                or includes[0].get("merge", "false") != "true"
                or model.find("link[@name='base_link']") is not None
                or model.findall(".//sensor[@type='magnetometer']")):
            raise ValueError("magnetic inheritance chain changed: " + name)
        identity_pose(includes[0], name + " include", translation_allowed=True)
    return {"sensor_orientation_in_body_flu": "identity", "poses_xyz_rpy": poses,
            "model_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "model_sha256": {name: sha256(path) for name, path in paths.items()}}


def configure_world(source_world: Path, runtime_world: Path, evidence_path: Path, *,
                    runtime_manifest: Path, lookup_json: Path = DEFAULT_LOOKUP) -> dict:
    source_world, runtime_world = Path(source_world).resolve(), Path(runtime_world).resolve()
    evidence_path = Path(evidence_path).resolve()
    if source_world == runtime_world or evidence_path in (source_world, runtime_world):
        raise ValueError("source, runtime world and evidence must be distinct")
    if runtime_world.exists() or evidence_path.exists():
        raise ValueError("new runtime world/evidence required; refuse overwrite")
    runtime = validate_runtime_manifest(runtime_manifest)
    lookup = json.loads(Path(lookup_json).read_text(encoding="utf-8"))
    if (lookup.get("contract") != CONTRACT or lookup.get("gazebo_sim_version") != "8.15.0"
            or lookup.get("gazebo_sim_commit") != "446a44335a45b704b4d36dabcc5508ee34eeb3d8"
            or lookup.get("gazebo_sim_source_sha256") != "4c2eab47814932a4df6b6255f46e379b1aa0feb41b248fd0ee13213d56a3016d"
            or runtime["bridge_source_sha256"] != PATCHED_SHA256):
        raise ValueError("unregistered Gazebo/PX4 source contract")
    tree = ET.parse(source_world)
    world = tree.getroot().find("world")
    if world is None:
        raise ValueError("world missing")
    spherical = world.find("spherical_coordinates")
    if spherical is None or spherical.findtext("world_frame_orientation") != "ENU":
        raise ValueError("declared ENU spherical coordinates required")
    for key, reference in (("latitude_deg", "reference_latitude_deg"), ("longitude_deg", "reference_longitude_deg")):
        value = float(spherical.findtext(key, "nan"))
        if not math.isfinite(value) or abs(value - float(lookup[reference])) > 1e-8:
            raise ValueError("unregistered magnetic reference location: " + key)
    if float(spherical.findtext("heading_deg", "0")) != 0.:
        raise ValueError("zero ENU world heading required")
    plugins = [p for p in world.findall("plugin") if p.get("name") == "gz::sim::systems::Magnetometer"]
    if len(plugins) != 1 or plugins[0].get("filename") != "gz-sim-magnetometer-system":
        raise ValueError("exactly one registered Gazebo magnetic system required")
    original_field = world.findtext("magnetic_field")
    if original_field is None:
        raise ValueError("world magnetic initialization missing")
    for name, value in (("use_earth_frame_ned", "false"), ("use_units_gauss", "true")):
        entries = plugins[0].findall(name)
        if len(entries) > 1:
            raise ValueError("duplicate magnetic plugin option: " + name)
        (entries[0] if entries else ET.SubElement(plugins[0], name)).text = value
    mounts = sensor_mount_evidence(Path(runtime["source_root"]))
    runtime_world.parent.mkdir(parents=True, exist_ok=True)
    payload = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
    with runtime_world.open("xb") as stream:
        stream.write(payload)
    result = {"schema_version": 1, "magnetic_environment": CONTRACT,
              "source_world": str(source_world), "runtime_world": str(runtime_world),
              "source_world_sha256": sha256(source_world), "runtime_world_sha256": sha256(runtime_world),
              "preserved_world_magnetic_field_initialization": original_field,
              "world_field_is_actual_runtime_input": False,
              "gazebo_lookup_reference": lookup, "lookup_sha256": sha256(lookup_json),
              "px4_runtime_manifest_path": str(Path(runtime_manifest).resolve()),
              "px4_runtime_manifest_sha256": sha256(runtime_manifest), "px4_runtime": runtime,
              "sensor_mount": mounts,
              "required_parameter_policy": "SENS_EN_MAGSIM=0; exactly one Gazebo magnetic publisher",
              "requires_actual_startup_log_marker": True,
              "claim_limit": "Coordinate contract intervention; lookup tables still differ; flight/ego validation pending"}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-world", required=True, type=Path)
    parser.add_argument("--output-world", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--px4-runtime-manifest", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(configure_world(args.input_world, args.output_world, args.evidence,
                                    runtime_manifest=args.px4_runtime_manifest), indent=2))


if __name__ == "__main__":
    main()
