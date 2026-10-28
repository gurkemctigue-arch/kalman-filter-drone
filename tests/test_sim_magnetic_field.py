"""Simulation field coherency must follow declared physics, never flight GT."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import configure_sim_magnetic_field as magnetic


WORLD = ('<sdf version="1.10"><world name="test"><gravity>0 0 -9.81</gravity>'
         '<magnetic_field>6e-6 2.3e-5 -4.2e-5</magnetic_field><spherical_coordinates>'
         '<world_frame_orientation>ENU</world_frame_orientation><latitude_deg>47.397971</latitude_deg>'
         '<longitude_deg>8.546164</longitude_deg><heading_deg>0</heading_deg>'
         '</spherical_coordinates><model name="untouched"><pose>1 2 3 0 0 0</pose></model></world></sdf>')


class SimulationMagneticFieldTests(unittest.TestCase):
    def test_north_east_and_inclination_axis_conventions(self):
        cases = [(0, 0, [0, 1, 0]), (90, 0, [1, 0, 0]), (0, 90, [0, 0, -1]), (0, -90, [0, 0, 1])]
        for declination, inclination, expected in cases:
            with self.subTest(declination=declination, inclination=inclination):
                actual = magnetic.field_enu(declination, inclination, 1.)
                for value, reference in zip(actual, expected):
                    self.assertAlmostEqual(value, reference, places=12)

    def test_pinned_manifest_was_generated_by_official_cpp_for_current_location(self):
        lookup = json.loads(magnetic.DEFAULT_LOOKUP.read_text(encoding="utf-8"))
        self.assertEqual(lookup["px4_commit"], magnetic.PINNED_PX4_COMMIT)
        self.assertAlmostEqual(lookup["declination_deg"], 3.40576529503, places=10)
        self.assertAlmostEqual(lookup["inclination_deg"], 63.1574668884, places=9)
        self.assertAlmostEqual(lookup["strength_tesla"], 4.82388168166e-5, places=15)
        vector = magnetic.field_enu(lookup["declination_deg"], lookup["inclination_deg"], lookup["strength_tesla"])
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in vector)), lookup["strength_tesla"], places=16)
        self.assertAlmostEqual(math.degrees(math.atan2(vector[0], vector[1])), lookup["declination_deg"], places=12)

    def test_only_runtime_copy_field_changes_and_complete_provenance_is_saved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "source.sdf"; output = root / "configuration/runtime_world.sdf"
            evidence_path = root / "configuration/magnetic_environment.json"
            source.write_text(WORLD, encoding="utf-8"); before = source.read_bytes()
            result = magnetic.configure_world(source, output, evidence_path)
            self.assertEqual(source.read_bytes(), before)
            source_xml = ET.fromstring(before); output_xml = ET.parse(output).getroot()
            source_xml.find("world/magnetic_field").text = output_xml.findtext("world/magnetic_field")
            self.assertEqual(ET.tostring(source_xml), ET.tostring(output_xml))
            field = [float(value) for value in output_xml.findtext("world/magnetic_field").split()]
            self.assertAlmostEqual(math.degrees(math.atan2(field[0], field[1])), 3.40576529503, places=10)
            self.assertEqual(result["source_world_sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(result["runtime_world_sha256"], magnetic.sha256(output))
            self.assertEqual(result["source_magnetic_field_enu_tesla"], [6e-6, 2.3e-5, -4.2e-5])
            self.assertEqual(result, json.loads(evidence_path.read_text(encoding="utf-8")))
            self.assertAlmostEqual(result["source_declination_deg"] - result["lookup"]["declination_deg"], 11.2151086936, places=9)

    def test_source_world_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.sdf"; source.write_text(WORLD, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "distinct runtime"):
                magnetic.configure_world(source, source, Path(temporary) / "evidence.json")
            self.assertEqual(source.read_text(encoding="utf-8"), WORLD)

    def test_changed_location_axes_missing_field_and_nonfinite_input_are_rejected(self):
        for world in (WORLD.replace("47.397971", "47.4"), WORLD.replace("ENU", "NED"),
                      WORLD.replace("<heading_deg>0", "<heading_deg>5"),
                      WORLD.replace("<magnetic_field>6e-6 2.3e-5 -4.2e-5</magnetic_field>", ""),
                      WORLD.replace("6e-6 2.3e-5 -4.2e-5", "nan 0 1")):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root / "source.sdf"; source.write_text(world, encoding="utf-8")
                with self.assertRaises(ValueError):
                    magnetic.configure_world(source, root / "runtime.sdf", root / "evidence.json")
                self.assertFalse((root / "runtime.sdf").exists())

    def test_unregistered_lookup_or_inconsistent_field_manifest_is_rejected(self):
        for field, value in (("px4_commit", "unregistered"), ("table_sha256", "wrong"),
                             ("magnetic_field_enu_tesla", [0, 0, 1])):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root / "source.sdf"; source.write_text(WORLD, encoding="utf-8")
                lookup = json.loads(magnetic.DEFAULT_LOOKUP.read_text(encoding="utf-8")); lookup[field] = value
                manifest = root / "lookup.json"; manifest.write_text(json.dumps(lookup), encoding="utf-8")
                with self.assertRaises(ValueError):
                    magnetic.configure_world(source, root / "runtime.sdf", root / "evidence.json", lookup_json=manifest)

    def test_invalid_physical_values_never_produce_a_vector(self):
        for values in ((0, 0, 0), (0, 0, -1), (0, 91, 1), (math.nan, 0, 1), (0, 0, math.inf)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                magnetic.field_enu(*values)


if __name__ == "__main__":
    unittest.main()
