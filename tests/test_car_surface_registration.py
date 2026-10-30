"""Prospective surface-policy bindings; synthetic files only, no flights/bags."""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reliability_v4_runner as fixtures

v4 = fixtures.v4


def normalized_paths(value):
    if isinstance(value, str):
        return value.replace("\\", "/")
    if isinstance(value, list):
        return [normalized_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized_paths(item) for key, item in value.items()}
    return value


class CarSurfaceRegistrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.legacy = fixtures.fixture(self.root)

    def declare(self, enabled=True):
        protocol = deepcopy(self.legacy)
        for cls in v4.CLASSES:
            protocol["resources"][cls][v4.CAR_SURFACE_RECOVERY_FIELD] = {
                **deepcopy(v4.CAR_SURFACE_RECOVERY_V1), "enabled": enabled and cls == "car"}
        fixtures.write(self.root / v4.PROTOCOL_PATH, protocol)
        return protocol

    def make(self, **kwargs):
        return fixtures.plan(self.root, classes=list(v4.CLASSES), seeds=[4], persist=False, **kwargs)

    def archive(self, trial):
        fixtures.FakeCommands()(trial["flight_command"], self.root / (trial["id"] + ".log"), self.root, 1.)
        directory = Path(trial["directory"])
        config_path = directory / "run_config.json"
        parameters_path = directory / "configuration/runtime_parameters.yaml"
        config, parameters = v4.load(config_path), v4.load(parameters_path)
        enabled = v4.CAR_SURFACE_RECOVERY_FLAG in trial["flight_command"]
        config.update(car_surface_recovery=enabled, car_surface_recovery_method="component_centroid_v1")
        parameters["uav_tracking_detection"]["ros__parameters"].update(
            car_surface_recovery_enabled=enabled, **v4.CAR_SURFACE_RECOVERY_RUNTIME_PARAMETERS)
        fixtures.write(config_path, config)
        fixtures.write(parameters_path, parameters)
        return config_path, parameters_path, config, parameters

    def test_legacy_trial_exact_hash_and_no_mutated_default_fields(self):
        before = deepcopy(self.legacy)
        trial = v4.trial_spec(Path("LEGACY_FROZEN_ROOT"), self.legacy,
                              "reliability_v4_legacy_surface", "car", "stage2_crossing", 4, 600.)
        # Captured against the pre-change runner, with slash normalization only.
        self.assertEqual(v4.digest(normalized_paths(trial)),
                         "37bb3da92a9fc27516a4220592d864c0ab885ed537ed0b273878e4a8322372e3")
        self.assertNotIn(v4.CAR_SURFACE_RECOVERY_FIELD, trial)
        self.assertNotIn(v4.CAR_SURFACE_RECOVERY_FLAG, trial["flight_command"])
        self.assertEqual(v4.car_surface_recovery_summary(self.legacy),
                         {cls: {"enabled": False} for cls in v4.CLASSES})
        self.assertFalse(v4.car_surface_recovery_declared(self.legacy))
        self.assertEqual(self.legacy, before)

    def test_fixed_contract_matches_actual_trial_parameters_and_hardcoded_prior(self):
        source = ast.parse((fixtures.ROOT / "scripts/run_stage1_trial.py").read_text(encoding="utf-8"))
        declaration = next(node.value for node in source.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "CAR_SURFACE_RECOVERY_PARAMETERS"
                                   for target in node.targets))
        self.assertEqual(ast.literal_eval(declaration), v4.CAR_SURFACE_RECOVERY_RUNTIME_PARAMETERS)
        detector = ast.parse((fixtures.ROOT / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py")
                             .read_text(encoding="utf-8"))
        call = next(node for node in ast.walk(detector) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "NavigationPrior")
        self.assertEqual([ast.literal_eval(arg) for arg in call.args],
                         ["car", *v4.CAR_SURFACE_RECOVERY_V1["family_dimensions_m"]])
        std = next(item.value for item in call.keywords if item.arg == "dimension_std_m")
        self.assertEqual(list(ast.literal_eval(std)), v4.CAR_SURFACE_RECOVERY_V1["family_dimension_std_m"])

    def test_only_complete_fixed_car_contract_is_allowed_and_normalization_is_detached(self):
        for enabled in (False, True):
            protocol = self.declare(enabled)
            v4.validate_protocol(protocol)
            self.assertTrue(v4.car_surface_recovery_declared(protocol))
            summary = v4.car_surface_recovery_summary(protocol)
            self.assertIs(summary["car"]["enabled"], enabled)
            self.assertEqual(summary["person"], {"enabled": False})
            if enabled:
                summary["car"]["family_dimensions_m"][0] = 999.
                self.assertEqual(protocol["resources"]["car"][v4.CAR_SURFACE_RECOVERY_FIELD]
                                 ["family_dimensions_m"], [4.5, 1.8, 1.5])
        defects = {"enabled": 1, "method": "other", "revision": "v2",
                   "surface_max_visible_boxes": 64., "surface_max_image_pixels": True,
                   "surface_max_roi_pixels": 100, "surface_tf_timeout_s": float("nan"),
                   "surface_geometry_frame": "odom", "family_dimensions_m": [4.6, 1.8, 1.5],
                   "family_dimension_std_m": [.45, .18, .16], "source_time_tf_required": 1,
                   "measurement_noise": "calibrated", "depth_validity": "min <= Z <= max"}
        for key, value in defects.items():
            with self.subTest(key=key):
                protocol = self.declare()
                protocol["resources"]["car"][v4.CAR_SURFACE_RECOVERY_FIELD][key] = value
                with self.assertRaisesRegex(ValueError, v4.CAR_SURFACE_RECOVERY_FIELD):
                    v4.validate_protocol(protocol)
        for declaration in (None, True, {}, {"enabled": True}, {**v4.CAR_SURFACE_RECOVERY_V1, "extra": 1}):
            protocol = self.declare()
            protocol["resources"]["car"][v4.CAR_SURFACE_RECOVERY_FIELD] = declaration
            with self.assertRaises(ValueError):
                v4.validate_protocol(protocol)
        protocol = self.declare()
        protocol["resources"]["person"][v4.CAR_SURFACE_RECOVERY_FIELD]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "only car"):
            v4.validate_protocol(protocol)
        protocol = self.declare()
        protocol["resources"]["car"]["inference_threads"] = 8
        with self.assertRaisesRegex(ValueError, "resource"):
            v4.validate_protocol(protocol)

    def test_all_twelve_core_specs_bind_exact_opt_in_without_consuming_heldout_seeds(self):
        self.declare()
        frozen = self.make(groups=list(v4.GROUPS))
        self.assertEqual(len(frozen["trials"]), 12)
        self.assertEqual(frozen["mode"], "PROBE")
        self.assertEqual(frozen["selected_seeds"], [4])
        v4.validate_plan(frozen)
        for trial in frozen["trials"]:
            enabled = trial["target_class"] == "car"
            self.assertEqual(v4.car_surface_recovery_trial_binding(frozen, trial), (enabled, True))
            self.assertEqual(trial["flight_command"].count(v4.CAR_SURFACE_RECOVERY_FLAG), int(enabled))
            self.assertIs(trial[v4.CAR_SURFACE_RECOVERY_FIELD]["enabled"], enabled)
        with self.assertRaisesRegex(ValueError, "Held-out"):
            fixtures.plan(self.root, seeds=[1000], persist=False)
        with self.assertRaisesRegex(ValueError, "REGISTERED"):
            fixtures.make_fixture_plan(self.root, "results/not_formal", "reliability_v4_not_formal", formal=True)

    def test_resealed_trial_or_command_cannot_bypass_registration(self):
        self.declare()
        original = self.make()
        for defect in ("missing_spec", "false_spec", "dimension", "missing_cli", "duplicate_cli", "assignment_cli", "protocol"):
            with self.subTest(defect=defect):
                frozen = deepcopy(original)
                trial = next(item for item in frozen["trials"] if item["target_class"] == "car")
                if defect == "missing_spec":
                    trial.pop(v4.CAR_SURFACE_RECOVERY_FIELD)
                elif defect == "false_spec":
                    trial[v4.CAR_SURFACE_RECOVERY_FIELD]["enabled"] = False
                elif defect == "dimension":
                    trial[v4.CAR_SURFACE_RECOVERY_FIELD]["family_dimensions_m"][0] = 4.6
                elif defect == "missing_cli":
                    trial["flight_command"].remove(v4.CAR_SURFACE_RECOVERY_FLAG)
                elif defect == "duplicate_cli":
                    trial["flight_command"].append(v4.CAR_SURFACE_RECOVERY_FLAG)
                elif defect == "assignment_cli":
                    trial["flight_command"].append(v4.CAR_SURFACE_RECOVERY_FLAG + "=true")
                else:
                    frozen["protocol"]["resources"]["car"][v4.CAR_SURFACE_RECOVERY_FIELD]["enabled"] = False
                frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
                with self.assertRaises(ValueError):
                    v4.validate_plan(frozen)
                self.assertTrue(v4.runtime_configuration(frozen, trial)["errors"])

    def test_legacy_plan_rejects_even_an_unregistered_false_trial_field(self):
        frozen = self.make()
        trial = frozen["trials"][0]
        trial[v4.CAR_SURFACE_RECOVERY_FIELD] = {**deepcopy(v4.CAR_SURFACE_RECOVERY_V1), "enabled": False}
        frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
        with self.assertRaises(ValueError):
            v4.validate_plan(frozen)

    def test_legacy_archives_allow_absent_or_false_but_refuse_hidden_or_mistyped_enablement(self):
        frozen = self.make()
        trial = frozen["trials"][0]
        config_path, parameters_path, config, parameters = self.archive(trial)
        self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
        for mapping in (config, parameters["uav_tracking_detection"]["ros__parameters"]):
            for key in list(mapping):
                if key == "car_surface_recovery" or key == "car_surface_recovery_enabled" or key in v4.CAR_SURFACE_RECOVERY_RUNTIME_PARAMETERS:
                    mapping.pop(key)
        fixtures.write(config_path, config)
        fixtures.write(parameters_path, parameters)
        self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
        for location in ("arguments", "yaml"):
            for value in (True, 0, 1, "false", None):
                with self.subTest(location=location, value=value):
                    arguments, runtime = deepcopy(config), deepcopy(parameters)
                    if location == "arguments":
                        arguments["car_surface_recovery"] = value
                        expected = "run_config:car_surface_recovery"
                    else:
                        runtime["uav_tracking_detection"]["ros__parameters"]["car_surface_recovery_enabled"] = value
                        expected = "runtime_parameters:uav_tracking_detection:car_surface_recovery_enabled"
                    fixtures.write(config_path, arguments)
                    fixtures.write(parameters_path, runtime)
                    self.assertIn(expected, v4.runtime_configuration(frozen, trial)["errors"])

    def test_explicit_on_and_off_require_actual_activation_method_and_fixed_parameters(self):
        self.declare()
        frozen = self.make()
        for trial in frozen["trials"]:
            config_path, parameters_path, config, parameters = self.archive(trial)
            self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
            required = [("arguments", "car_surface_recovery"), ("arguments", "car_surface_recovery_method"),
                        ("yaml", "car_surface_recovery_enabled"),
                        *(("yaml", key) for key in v4.CAR_SURFACE_RECOVERY_RUNTIME_PARAMETERS)]
            for location, key in required:
                for defect in ("missing", "wrong"):
                    with self.subTest(cls=trial["target_class"], location=location, key=key, defect=defect):
                        arguments, runtime = deepcopy(config), deepcopy(parameters)
                        target = arguments if location == "arguments" else runtime["uav_tracking_detection"]["ros__parameters"]
                        if defect == "missing":
                            target.pop(key)
                        else:
                            target[key] = 1 if type(target[key]) is bool else "unregistered"
                        fixtures.write(config_path, arguments)
                        fixtures.write(parameters_path, runtime)
                        label = ("run_config:" if location == "arguments" else "runtime_parameters:uav_tracking_detection:") + key
                        self.assertIn(label, v4.runtime_configuration(frozen, trial)["errors"])
            fixtures.write(config_path, config)
            fixtures.write(parameters_path, parameters)

    def test_extensions_inherit_the_same_policy_for_all_sixteen_specs(self):
        self.declare()
        extension = v4.load(fixtures.ROOT / v4.EXTENSION_PROTOCOL_PATH)
        fixtures.write(self.root / v4.EXTENSION_PROTOCOL_PATH, extension)
        with patch.object(v4, "verify_external_runtime", side_effect=fixtures.fixture_runtime_verifier):
            frozen = v4.make_extension_plan(self.root, "results/extensions", "reliability_v4_surface_extensions", seeds=[4])
        self.assertEqual(len(frozen["trials"]), 16)
        self.assertEqual(frozen["mode"], "EXTENSION_PROBE")
        self.assertEqual(frozen["selected_seeds"], [4])
        v4.validate_plan(frozen)
        for trial in frozen["trials"]:
            self.assertEqual(v4.car_surface_recovery_trial_binding(frozen, trial),
                             (trial["target_class"] == "car", True))
        car = next(item for item in frozen["trials"] if item["target_class"] == "car")
        car["flight_command"].remove(v4.CAR_SURFACE_RECOVERY_FLAG)
        frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
        with self.assertRaises(ValueError):
            v4.validate_plan(frozen)

    def test_runner_gate_refuses_recovery_on_off_both_ways_before_reading_slot_records(self):
        for index, (target_on, previous_on) in enumerate(((True, False), (False, True), (None, True), (True, None))):
            with self.subTest(target=target_on, previous=previous_on):
                target_protocol, previous_protocol = deepcopy(self.legacy), deepcopy(self.legacy)
                for protocol, enabled in ((target_protocol, target_on), (previous_protocol, previous_on)):
                    if enabled is not None:
                        protocol["resources"]["car"][v4.CAR_SURFACE_RECOVERY_FIELD] = {
                            **deepcopy(v4.CAR_SURFACE_RECOVERY_V1), "enabled": enabled}
                target = {"protocol": target_protocol, "source_hashes": {}, "model_hashes": {},
                          "magnetic_runtime_binding": {"manifest_sha256": "1" * 64},
                          "magnetic_library_binding": {"registration_sha256": "2" * 64}}
                previous = {**deepcopy(target), "protocol": previous_protocol, "mode": "PROBE"}
                source = self.root / ("direct_probe_" + str(index) + ".json")
                fixtures.write(source, previous)
                bindings = {"flight_source_hashes": {}, "evaluation_source_hashes": {}, "model_hashes": {},
                            "magnetic_runtime_manifest_sha256": "1" * 64,
                            "magnetic_library_registration_sha256": "2" * 64,
                            "navigation_acceptance_sha256": v4.digest(target_protocol["navigation_acceptance"])}
                if v4.car_surface_recovery_declared(target_protocol):
                    bindings["car_surface_recovery_sha256"] = v4.digest(v4.car_surface_recovery_summary(target_protocol))
                gate = {"schema_version": 2, "result": "PASS", "ready_for_formal_reliability_v4": True,
                        "checks": {name: True for name in v4.PROBE_CHECKS}, "bindings": bindings,
                        "probe_slots": [{"plan_path": str(source), "plan_file_sha256": v4.sha(source), "slot_id": "inert"}]}
                artifact = self.root / ("direct_gate_" + str(index) + ".json")
                fixtures.write(artifact, gate)
                target["development_probe_gate"] = {"path": str(artifact), "sha256": v4.sha(artifact), "evidence": gate}
                with patch.object(v4, "validate_plan"), \
                        patch.object(v4, "read_slots", side_effect=AssertionError("Refuse before record reads")), \
                        self.assertRaisesRegex(ValueError, "car surface recovery policy differs"):
                    v4.validate_probe_gate(target)


if __name__ == "__main__":
    unittest.main()
