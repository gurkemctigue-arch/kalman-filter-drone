"""Analytical sensor/bridge physics and isolated preparation guard fixtures.

These tests model the pinned upstream operations; they do not pretend to run
Gazebo, observe an EKF instance, or establish the cause of a flight failure.
"""
from __future__ import annotations

import hashlib
import difflib
import json
import math
from pathlib import Path
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_px4_magnetic_compatibility as preparation
import configure_gazebo_magnetic_contract as configuration

LEGACY_BRIDGE = np.array([[0., -1., 0.], [-1., 0., 0.], [0., 0., 1.]])
FLU_TO_FRD = np.diag([1., -1., -1.])


def world_from_body(roll, pitch, yaw):
    sr, cr, sp, cp, sy, cy = math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw), math.cos(yaw)
    return np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                     [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr], [-sp, cp*sr, cp*cr]])


def field_enu(declination, inclination, strength=1.):
    d, i = math.radians(declination), math.radians(inclination)
    return strength * np.array([math.cos(i)*math.sin(d), math.cos(i)*math.cos(d), -math.sin(i)])


class MagneticFramePhysicsTests(unittest.TestCase):
    def test_body_frd_axes_at_level_east_have_physical_east_south_down_components(self):
        world = np.array([1., 2., -3.])
        np.testing.assert_array_equal(FLU_TO_FRD @ world, [1., -2., 3.])
        np.testing.assert_array_equal(LEGACY_BRIDGE @ world, [-2., -1., -3.])

    def test_corrected_enu_gauss_contract_matches_physical_axes_for_arbitrary_attitudes(self):
        rng = np.random.default_rng(412)
        for _ in range(128):
            roll, pitch, yaw = rng.uniform(-math.pi, math.pi, 3)
            rotation = world_from_body(roll, pitch, yaw)
            world_gauss = field_enu(rng.uniform(-180., 180.), rng.uniform(-89., 89.), rng.uniform(.1, .7))
            # Independent physical projection on body forward/right/down axes.
            forward, right, down = rotation[:, 0], -rotation[:, 1], -rotation[:, 2]
            expected = np.array([world_gauss @ forward, world_gauss @ right, world_gauss @ down])
            gazebo_sensor = rotation.T @ world_gauss
            np.testing.assert_allclose(FLU_TO_FRD @ gazebo_sensor, expected, atol=1e-14)

    def test_only_changing_world_plugin_to_enu_leaves_a_frame_error(self):
        field = field_enu(2.5638489723205566, 63.252586364746094, .4807400894165039)
        for attitude in ((0., 0., 0.), (.3, -.2, .8), (-.4, .25, -1.)):
            rotation = world_from_body(*attitude)
            expected = FLU_TO_FRD @ rotation.T @ field
            self.assertGreater(np.linalg.norm(LEGACY_BRIDGE @ rotation.T @ field - expected), .1)

    def test_no_proper_sensor_mount_rotation_can_turn_the_legacy_reflection_into_frd(self):
        self.assertAlmostEqual(np.linalg.det(LEGACY_BRIDGE), -1.)
        self.assertAlmostEqual(np.linalg.det(FLU_TO_FRD), 1.)
        required_mount = (LEGACY_BRIDGE.T @ FLU_TO_FRD).T
        self.assertAlmostEqual(np.linalg.det(required_mount), -1.)
        world = field_enu(2.5, 63., .48)
        required_world_vectors = [r @ LEGACY_BRIDGE.T @ FLU_TO_FRD @ r.T @ world
                                  for r in (np.eye(3), world_from_body(.35, -.2, .8), world_from_body(-.5, .4, -1.3))]
        self.assertGreater(np.linalg.norm(required_world_vectors[0] - required_world_vectors[1]), .01)

    def test_legacy_level_heading_prediction_uses_sum_of_two_distinct_declinations(self):
        reference = json.loads(configuration.DEFAULT_LOOKUP.read_text(encoding="utf-8"))
        dg, dp = reference["lookup_declination_deg"], reference["px4_lookup_declination_deg"]
        enu = field_enu(dg, reference["lookup_inclination_deg"])
        # Pinned default plugin gives NED vector components to the ENU world.
        legacy_world = np.array([enu[1], enu[0], -enu[2]])
        for yaw in (-2.3, -.4, 0., 1.5, 2.9):
            mag = LEGACY_BRIDGE @ world_from_body(0., 0., yaw).T @ legacy_world
            inferred_ned_yaw = math.atan2(-mag[1], mag[0]) + math.radians(dp)
            inferred_enu_yaw = math.pi / 2. - inferred_ned_yaw
            error = (inferred_enu_yaw-yaw+math.pi) % (2*math.pi)-math.pi
            self.assertAlmostEqual(math.degrees(error), -dg-dp, places=10)
        self.assertAlmostEqual(-dg-dp, -5.969614267350556, places=9)
        self.assertAlmostEqual(dp-dg, .8419163227094435, places=10)

    def test_gauss_contract_does_not_silently_supply_tesla_to_px4(self):
        world_tesla = field_enu(3., 63., 4.8e-5)
        rotation = world_from_body(.3, -.4, .8)
        actual = FLU_TO_FRD @ rotation.T @ (world_tesla * 1e4)
        self.assertAlmostEqual(np.linalg.norm(actual), .48, places=12)
        self.assertAlmostEqual(np.linalg.norm(actual) / np.linalg.norm(world_tesla), 1e4, places=9)


WORLD = ('<sdf version="1.9"><world name="fixture"><magnetic_field>6e-6 2.3e-5 -4.2e-5</magnetic_field>'
         '<spherical_coordinates><world_frame_orientation>ENU</world_frame_orientation><latitude_deg>47.397971</latitude_deg>'
         '<longitude_deg>8.546164</longitude_deg></spherical_coordinates><plugin filename="gz-sim-magnetometer-system" '
         'name="gz::sim::systems::Magnetometer"/><model name="untouched"><pose>1 2 3 0 0 0</pose></model></world></sdf>')


class MagneticPreparationGuardTests(unittest.TestCase):
    def test_final_runtime_must_match_initial_binary_source_and_dependency_binding(self):
        expected = {"contract": preparation.CONTRACT, "px4_commit": preparation.PINNED_COMMIT,
                    "bridge_source_sha256": preparation.PATCHED_SHA256, "patch_sha256": preparation.PATCH_SHA256,
                    "source_root": "/isolated", "binary_path": "/isolated/px4", "binary_sha256": "initial",
                    "binary_bytes": 100, "dependencies": {"module": {"commit": "pinned"}},
                    "tracked_dirty_paths": [preparation.BRIDGE.as_posix()]}
        preparation.assert_runtime_unchanged(expected, {**expected, "actual_startup_log_verified": True})
        for key, value in (("binary_sha256", "recompiled"), ("source_root", "/different"),
                           ("binary_path", "/elsewhere/px4"), ("dependencies", {})):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                preparation.assert_runtime_unchanged(expected, {**expected, key: value})

    def apply_fixture(self, base):
        original, isolated = base / "original", base / "isolated"
        bridge = original / preparation.BRIDGE; bridge.parent.mkdir(parents=True)
        bridge.write_bytes(b"original bridge\n")
        preparation.git(original, "init")
        preparation.git(original, "config", "core.autocrlf", "false")
        preparation.git(original, "add", preparation.BRIDGE.as_posix())
        preparation.git(original, "-c", "user.name=Fixture", "-c", "user.email=fixture@invalid", "commit", "-m", "fixture")
        commit = preparation.git(original, "rev-parse", "HEAD")
        shutil.copytree(original, isolated)
        content = "".join(difflib.unified_diff(["original bridge\n"], ["patched bridge\n"],
                           fromfile="a/" + preparation.BRIDGE.as_posix(), tofile="b/" + preparation.BRIDGE.as_posix()))
        fixture_patch = base / "fixture.patch"; fixture_patch.write_bytes(content.encode())
        manifest = base / "copy.json"
        data = {"source": str(original.resolve()), "destination": str(isolated.resolve()),
                "commit": commit, "tracked_clean": True, "source_unchanged": True, "network_used": False,
                "file_method": "independent copy2 files; relative symlinks preserved",
                "excluded_source_root_directories": ["build", "install", "log"],
                "submodule_status_sha256": hashlib.sha256(b"").hexdigest(), "submodule_states": []}
        manifest.write_text(json.dumps(data))
        constants = {"PINNED_COMMIT": commit, "PATCH": fixture_patch,
                     "PATCH_SHA256": hashlib.sha256(content.encode()).hexdigest(),
                     "ORIGINAL_SHA256": hashlib.sha256(b"original bridge\n").hexdigest(),
                     "PATCHED_SHA256": hashlib.sha256(b"patched bridge\n").hexdigest()}
        return original, isolated, manifest, constants

    def test_registered_patch_applies_only_to_independent_isolated_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, isolated, manifest, constants = self.apply_fixture(Path(temporary).resolve())
            with patch.multiple(preparation, **constants):
                result = preparation.apply_isolated(original, isolated, manifest)
            self.assertEqual((original / preparation.BRIDGE).read_bytes(), b"original bridge\n")
            self.assertEqual((isolated / preparation.BRIDGE).read_bytes(), b"patched bridge\n")
            self.assertTrue(result["original_unchanged"])
            self.assertFalse(result["build_executed"])
            self.assertEqual(result["isolated_after"]["tracked_dirty_paths"], [preparation.BRIDGE.as_posix()])

    def test_copy_manifest_dependency_mismatch_stops_before_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, isolated, manifest, constants = self.apply_fixture(Path(temporary).resolve())
            data = json.loads(manifest.read_text()); data["submodule_status_sha256"] = "changed"; manifest.write_text(json.dumps(data))
            with patch.multiple(preparation, **constants), self.assertRaisesRegex(ValueError, "dependency evidence"):
                preparation.apply_isolated(original, isolated, manifest)
            self.assertEqual((isolated / preparation.BRIDGE).read_bytes(), b"original bridge\n")

    def test_registered_patch_bytes_and_marker_are_frozen(self):
        self.assertEqual(hashlib.sha256(preparation.PATCH.read_bytes()).hexdigest(), preparation.PATCH_SHA256)
        self.assertIn(preparation.MARKER, preparation.PATCH.read_text(encoding="utf-8"))

    def test_plan_rejects_same_nested_parent_and_preexisting_destination_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); source = base / "original"; source.mkdir()
            occupied = base / "occupied"; occupied.mkdir(); (occupied / "keep").write_text("keep")
            before = sorted(str(p) for p in base.rglob("*"))
            for target in (source, source / "new", base, occupied):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    preparation.plan(source, target)
            self.assertEqual(before, sorted(str(p) for p in base.rglob("*")))

    def test_runtime_requires_elf_and_compiled_contract_marker(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(preparation, "check_source", return_value={}):
            base = Path(temporary); binary = base / preparation.BINARY; binary.parent.mkdir(parents=True)
            for payload in (b"not ELF", b"\x7fELF original binary"):
                binary.write_bytes(payload)
                with self.assertRaises(ValueError):
                    preparation.verify_runtime(base)
            binary.write_bytes(b"\x7fELF fixture\x00" + preparation.MARKER.encode())
            result = preparation.verify_runtime(base)
            self.assertFalse(result["actual_startup_log_verified"])
            log = base / "px4.log"; log.write_text("original startup")
            with self.assertRaises(ValueError):
                preparation.verify_runtime(base, log)
            log.write_text(preparation.MARKER)
            self.assertTrue(preparation.verify_runtime(base, log)["actual_startup_log_verified"])

    def test_both_custom_models_must_inherit_an_identity_body_magnetometer(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); px4 = base / "px4"; project = base / "project"
            p = px4 / "Tools/simulation/gz/models/x500_base/model.sdf"; p.parent.mkdir(parents=True)
            p.write_text('<sdf><model name="x500_base"><pose>0 0 .24 0 0 0</pose><link name="base_link">'
                         '<sensor name="magnetometer_sensor" type="magnetometer"/></link></model></sdf>')
            for name, parent, root in (("x500", "x500_base", px4 / "Tools/simulation/gz/models"),
                                     ("x500_stage1", "x500", project / "ros2_ws/src/uav_tracking_bringup/models"),
                                     ("x500_stage3", "x500", project / "ros2_ws/src/uav_tracking_bringup/models")):
                out = root / name / "model.sdf"; out.parent.mkdir(parents=True)
                out.write_text(f'<sdf><model name="{name}"><include merge="true"><uri>model://{parent}</uri></include></model></sdf>')
            result = configuration.sensor_mount_evidence(px4, project)
            self.assertEqual(result["sensor_orientation_in_body_flu"], "identity")
            text = p.read_text(); p.write_text(text.replace('type="magnetometer"/>', 'type="magnetometer"><pose>0 0 0 0 .1 0</pose></sensor>'))
            with self.assertRaisesRegex(ValueError, "nonidentity magnetic mount"):
                configuration.sensor_mount_evidence(px4, project)

    def test_world_intervention_preserves_initial_field_and_changes_only_plugin_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); source = base / "source.sdf"; source.write_text(WORLD)
            manifest = base / "runtime.json"; manifest.write_text("fixture")
            runtime = {"source_root": str(base), "bridge_source_sha256": preparation.PATCHED_SHA256}
            with patch.object(configuration, "validate_runtime_manifest", return_value=runtime), patch.object(configuration, "sensor_mount_evidence", return_value={"fixture": True}):
                result = configuration.configure_world(source, base / "world.sdf", base / "evidence.json", runtime_manifest=manifest)
            self.assertEqual(source.read_text(), WORLD)
            before, after = ET.fromstring(WORLD), ET.parse(base / "world.sdf").getroot()
            plugin = after.find("world/plugin")
            self.assertEqual(plugin.findtext("use_earth_frame_ned"), "false")
            self.assertEqual(plugin.findtext("use_units_gauss"), "true")
            for key in ("use_earth_frame_ned", "use_units_gauss"):
                plugin.remove(plugin.find(key))
            self.assertEqual(ET.tostring(before), ET.tostring(after))
            self.assertFalse(result["world_field_is_actual_runtime_input"])
            self.assertIn("lookup tables still differ", result["claim_limit"])

    def test_world_rejects_heading_location_and_runtime_contract_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); manifest = base / "runtime.json"; manifest.write_text("fixture")
            runtime = {"source_root": str(base), "bridge_source_sha256": preparation.PATCHED_SHA256}
            for text in (WORLD.replace("8.546164", "8.5"), WORLD.replace("ENU", "NED"),
                         WORLD.replace("</spherical_coordinates>", "<heading_deg>1</heading_deg></spherical_coordinates>")):
                source = base / "source.sdf"; source.write_text(text)
                with patch.object(configuration, "validate_runtime_manifest", return_value=runtime), self.assertRaises(ValueError):
                    configuration.configure_world(source, base / "world.sdf", base / "evidence.json", runtime_manifest=manifest)
                self.assertFalse((base / "world.sdf").exists())


if __name__ == "__main__":
    unittest.main()
