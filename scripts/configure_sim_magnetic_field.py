"""Declare a coherent simulation field from the firmware-pinned PX4 WMM.

No flight/target truth is used. ``generate`` compiles the official firmware
lookup; ``configure`` changes only an explicitly distinct output world copy.
Nothing sets PX4 estimator parameters or changes a hardware configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PINNED_PX4_COMMIT = "d6f12ad1c4f70ad3230afd7d86e971421e02fef4"
PINNED_TABLE_SHA256 = "3e985cba6a1fd9b246d628bf1d24b843b306a5a6d60ec69900188ec535a3b8cb"
PINNED_LOOKUP_SHA256 = "d8014b57ada04212633b83c4ed42d9649bca7eedbf78aa7238a655145c9fe292"
DEFAULT_LOOKUP = ROOT / "config/px4_wmm_reference.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def field_enu(declination_deg, inclination_deg, strength_tesla):
    values = [float(value) for value in (declination_deg, inclination_deg, strength_tesla)]
    if not all(math.isfinite(value) for value in values) or values[2] <= 0 or not -90 <= values[1] <= 90:
        raise ValueError("Finite field angles and positive strength are required")
    declination, inclination = map(math.radians, values[:2])
    horizontal = values[2] * math.cos(inclination)
    # PX4/WMM: declination positive east of North, inclination positive Down.
    return [horizontal * math.sin(declination), horizontal * math.cos(declination),
            -values[2] * math.sin(inclination)]


def generate_lookup(px4_root, latitude_deg, longitude_deg, *, compiler="c++"):
    """Run exact firmware WMM C++ code at the declared GPS coordinates."""
    px4_root = Path(px4_root)
    latitude = float(latitude_deg); longitude = float(longitude_deg)
    if not math.isfinite(latitude) or not -90 <= latitude <= 90 or not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Latitude/longitude must be finite and in WGS84 angular bounds")
    commit = subprocess.check_output(["git", "-C", str(px4_root), "rev-parse", "HEAD"], text=True).strip()
    directory = px4_root / "src/lib/world_magnetic_model"
    lookup = directory / "geo_mag_declination.cpp"; table = directory / "geo_magnetic_tables.hpp"
    if commit != PINNED_PX4_COMMIT or sha256(table) != PINNED_TABLE_SHA256 or sha256(lookup) != PINNED_LOOKUP_SHA256:
        raise ValueError("PX4 commit or WMM source hash differs from the registered firmware; register a new protocol first")
    # Official lookup only needs math::constrain. An isolated equivalent
    # scalar helper avoids importing PX4's platform/matrix build machinery;
    # the original WMM .cpp and tables are compiled without alteration.
    with tempfile.TemporaryDirectory(prefix="px4_wmm_lookup_") as temporary:
        root = Path(temporary); (root / "mathlib").mkdir()
        (root / "mathlib/mathlib.h").write_text(
            "#pragma once\nnamespace math { template<class T> constexpr T constrain(T v,T lo,T hi) "
            "{ return v < lo ? lo : (v > hi ? hi : v); } }\n", encoding="utf-8")
        driver = root / "lookup_main.cpp"
        driver.write_text(
            '#include <iostream>\n#include <iomanip>\n#include <cstdlib>\n#include "geo_mag_declination.h"\n'
            'int main(int argc,char**argv){if(argc!=3)return 2;float lat=std::strtof(argv[1],nullptr);'
            'float lon=std::strtof(argv[2],nullptr);std::cout<<std::setprecision(12)'
            '<<get_mag_declination_degrees(lat,lon)<<" "<<get_mag_inclination_degrees(lat,lon)<<" "'
            '<<get_mag_strength_tesla(lat,lon)<<"\\n";}\n', encoding="utf-8")
        executable = root / "lookup"
        subprocess.run([compiler, "-std=c++17", "-O2", "-I", str(root), "-I", str(directory),
                        str(driver), str(lookup), "-o", str(executable)], check=True, capture_output=True, text=True, timeout=30)
        result = subprocess.check_output([str(executable), repr(latitude), repr(longitude)], text=True, timeout=10)
    declination, inclination, strength = map(float, result.split())
    return {"schema_version":1, "model":"PX4 firmware WMM-2020 table, source epoch 2024.41257",
            "latitude_deg":latitude, "longitude_deg":longitude,
            "declination_deg":declination, "inclination_deg":inclination, "strength_tesla":strength,
            "magnetic_field_enu_tesla":field_enu(declination, inclination, strength),
            "px4_commit":commit, "table_sha256":sha256(table), "lookup_cpp_sha256":sha256(lookup),
            "lookup_source":"src/lib/world_magnetic_model/geo_mag_declination.cpp",
            "table_source":"src/lib/world_magnetic_model/geo_magnetic_tables.hpp",
            "source_url":"https://github.com/PX4/PX4-Autopilot/tree/" + commit + "/src/lib/world_magnetic_model",
            "evaluation":"Official pinned C++ lookup compiled unchanged; isolated math::constrain scalar helper only. Float32 firmware inputs and bilinear tables; no trajectory, ego error or target truth.",
            "scope":"Simulation physical environment declaration matching firmware WMM; never a hardware estimator override."}


def configure_world(input_world, output_world, evidence_path, *, lookup_json=DEFAULT_LOOKUP):
    """Change a runtime copy and save source/new vectors plus provenance."""
    input_world = Path(input_world); output_world = Path(output_world); evidence_path = Path(evidence_path)
    if input_world.resolve() == output_world.resolve():
        raise ValueError("Source world must be preserved; choose a distinct runtime output copy")
    if evidence_path.resolve() in {input_world.resolve(), output_world.resolve(), Path(lookup_json).resolve()}:
        raise ValueError("Evidence must have a distinct path")
    lookup = json.loads(Path(lookup_json).read_text(encoding="utf-8"))
    if (lookup.get("px4_commit") != PINNED_PX4_COMMIT or lookup.get("table_sha256") != PINNED_TABLE_SHA256
            or lookup.get("lookup_cpp_sha256") != PINNED_LOOKUP_SHA256):
        raise ValueError("Unregistered WMM lookup provenance")
    tree = ET.parse(input_world); worlds = tree.getroot().findall("world")
    if len(worlds) != 1:
        raise ValueError("Exactly one world is required")
    world = worlds[0]; spherical = world.find("spherical_coordinates")
    if spherical is None or spherical.findtext("world_frame_orientation") != "ENU" or float(spherical.findtext("heading_deg", "0")) != 0:
        raise ValueError("Coherent field conversion requires explicitly declared zero-heading ENU world coordinates")
    latitude = float(spherical.findtext("latitude_deg")); longitude = float(spherical.findtext("longitude_deg"))
    if not all(math.isfinite(value) for value in (latitude, longitude)):
        raise ValueError("Finite declared latitude/longitude required")
    if not math.isclose(latitude, float(lookup["latitude_deg"]), abs_tol=1e-8, rel_tol=0.) or not math.isclose(longitude, float(lookup["longitude_deg"]), abs_tol=1e-8, rel_tol=0.):
        raise ValueError("World location differs from registered lookup; generate a new official lookup for that location")
    element = world.find("magnetic_field")
    if element is None or not element.text:
        raise ValueError("An explicit original magnetic field is required for a reviewable change")
    original = [float(value) for value in element.text.split()]
    if len(original) != 3 or not all(math.isfinite(value) for value in original) or math.sqrt(sum(value * value for value in original)) == 0:
        raise ValueError("Original magnetic field must be a finite nonzero three-vector")
    replacement = field_enu(lookup["declination_deg"], lookup["inclination_deg"], lookup["strength_tesla"])
    declared = lookup.get("magnetic_field_enu_tesla")
    if not isinstance(declared, list) or len(declared) != 3 or any(not math.isclose(float(a), b, rel_tol=1e-9, abs_tol=1e-15) for a, b in zip(declared, replacement)):
        raise ValueError("Lookup angles/strength contradict its declared ENU vector")
    original_strength = math.sqrt(sum(value * value for value in original))
    evidence = {"schema_version":1, "magnetic_environment":"coherent_wmm",
                "source_world":str(input_world), "source_world_sha256":sha256(input_world),
                "runtime_world":str(output_world), "lookup_json":str(lookup_json), "lookup_json_sha256":sha256(lookup_json),
                "latitude_deg":latitude, "longitude_deg":longitude, "world_frame":"ENU", "world_heading_deg":0.,
                "source_magnetic_field_enu_tesla":original, "new_magnetic_field_enu_tesla":replacement,
                "source_declination_deg":math.degrees(math.atan2(original[0], original[1])),
                "source_inclination_deg":math.degrees(math.atan2(-original[2], math.hypot(*original[:2]))),
                "source_strength_tesla":original_strength,
                "lookup":lookup,
                "change_boundary":"Only the runtime world copy's magnetic_field is changed. No estimator parameter, target/ego truth, or real hardware setting is used or changed."}
    element.text = " ".join(format(value, ".15g") for value in replacement)
    output_world.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_world, encoding="utf-8", xml_declaration=True)
    evidence["runtime_world_sha256"] = sha256(output_world)
    evidence_path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Compile official pinned firmware lookup offline")
    generate.add_argument("--px4-root", type=Path, required=True)
    generate.add_argument("--latitude-deg", type=float, required=True)
    generate.add_argument("--longitude-deg", type=float, required=True)
    generate.add_argument("--output", type=Path, required=True)
    configure = commands.add_parser("configure", help="Write a distinct coherent runtime world copy")
    configure.add_argument("--input-world", type=Path, required=True)
    configure.add_argument("--output-world", type=Path, required=True)
    configure.add_argument("--evidence", type=Path, required=True)
    configure.add_argument("--lookup-json", type=Path, default=DEFAULT_LOOKUP)
    args = parser.parse_args()
    if args.command == "generate":
        result = generate_lookup(args.px4_root, args.latitude_deg, args.longitude_deg)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    else:
        result = configure_world(args.input_world, args.output_world, args.evidence, lookup_json=args.lookup_json)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
