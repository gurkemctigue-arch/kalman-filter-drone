"""Explicit CPU pacing revision; tiny synthetic files, no ROS or flight runs."""
from copy import deepcopy
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_guard as guard_fixtures

v4 = fixtures.v4


class SimulationPacingRegistrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.legacy = fixtures.fixture(self.root)

    def declare(self):
        protocol = deepcopy(self.legacy)
        protocol[v4.SIMULATION_PACING_FIELD] = deepcopy(v4.SIMULATION_PACING_V1)
        protocol.update(real_time_factor=.125, flight_wall_timeout_s=1000.)
        fixtures.write(self.root / v4.PROTOCOL_PATH, protocol)
        return protocol

    def make(self, **options):
        return fixtures.make_fixture_plan(self.root, "results/pacing", "reliability_v4_pacing",
                                          classes=list(v4.CLASSES), seeds=[4], **options)

    def test_legacy_default_and_probe_overrides_are_unchanged(self):
        before = deepcopy(self.legacy)
        frozen = self.make(groups=["stage1_velocity"])
        self.assertFalse(v4.simulation_pacing_declared(self.legacy))
        self.assertEqual(v4.simulation_pacing_summary(self.legacy),
                         {"real_time_factor": .25, "flight_wall_timeout_s": 600.})
        for trial in frozen["trials"]:
            self.assertNotIn(v4.SIMULATION_PACING_FIELD, trial)
            self.assertEqual(trial["wall_timeout_s"], 600.)
            command = trial["flight_command"]
            self.assertEqual(command[command.index("--real-time-factor") + 1], "0.25")
            self.assertEqual(command[command.index("--wall-timeout") + 1], "600.0")
        self.assertEqual(frozen["trial_timeout_s"], 2400.)
        other = self.make(groups=["stage1_velocity"], wall_timeout=241.5)
        self.assertEqual(other["trials"][0]["wall_timeout_s"], 241.5)
        self.assertEqual(self.legacy, before)
        v4.validate_plan(frozen)
        v4.validate_plan(other)

    def test_new_registration_requires_exact_dict_and_paired_top_values(self):
        protocol = self.declare()
        v4.validate_protocol(protocol)
        summary = v4.simulation_pacing_summary(protocol)
        self.assertTrue(v4.simulation_pacing_declared(protocol))
        self.assertEqual(summary, v4.SIMULATION_PACING_V1)
        summary["real_time_factor"] = .5
        self.assertEqual(protocol[v4.SIMULATION_PACING_FIELD]["real_time_factor"], .125)
        for declaration in (None, True, {}, {"revision": v4.SIMULATION_PACING_V1["revision"]},
                            {**v4.SIMULATION_PACING_V1, "extra": 1}):
            with self.subTest(declaration=declaration):
                changed = deepcopy(protocol)
                changed[v4.SIMULATION_PACING_FIELD] = declaration
                with self.assertRaisesRegex(ValueError, v4.SIMULATION_PACING_FIELD):
                    v4.validate_protocol(changed)
        for key, values in (("revision", ("other",)), ("real_time_factor", (.25, True, float("nan"))),
                            ("flight_wall_timeout_s", (600., True, float("inf"))),
                            ("max_inference_rate_hz", (5., True)),
                            ("physical_identity_sample_period_s", (.2, True)),
                            ("follow_duration_s", (37.5, True)),
                            ("scope", ("hardware_realtime",)), ("safety_source_time_gates", ("relaxed",))):
            for value in values:
                changed = deepcopy(protocol)
                changed[v4.SIMULATION_PACING_FIELD][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, v4.SIMULATION_PACING_FIELD):
                    v4.validate_protocol(changed)
        for declared in (False, True):
            for rtf, wall in ((.125, 600.), (.25, 1000.), (.5, 1000.), (True, 1000.), (.125, True),
                              (float("nan"), 1000.), (.125, float("inf"))):
                changed = deepcopy(protocol if declared else self.legacy)
                changed.update(real_time_factor=rtf, flight_wall_timeout_s=wall)
                with self.subTest(declared=declared, rtf=rtf, wall=wall), self.assertRaises(ValueError):
                    v4.validate_protocol(changed)
        undeclared = deepcopy(self.legacy)
        undeclared.update(real_time_factor=.125, flight_wall_timeout_s=1000.)
        with self.assertRaisesRegex(ValueError, v4.SIMULATION_PACING_FIELD):
            v4.validate_protocol(undeclared)

    def test_new_twelve_core_and_sixteen_extension_specs_inherit_fixed_pacing(self):
        protocol = self.declare()
        core = self.make(groups=list(v4.GROUPS))
        self.assertEqual(len(core["trials"]), 12)
        extension = v4.load(fixtures.ROOT / v4.EXTENSION_PROTOCOL_PATH)
        fixtures.write(self.root / v4.EXTENSION_PROTOCOL_PATH, extension)
        with patch.object(v4, "verify_external_runtime", side_effect=fixtures.fixture_runtime_verifier):
            extensions = v4.make_extension_plan(self.root, "results/pacing_extensions", "reliability_v4_pacing_extensions", seeds=[4])
        self.assertEqual(len(extensions["trials"]), 16)
        for frozen in (core, extensions):
            self.assertEqual(frozen["trial_timeout_s"], 2800.)
            self.assertEqual(frozen["postprocessing_timeout_s"], 1800.)
            self.assertEqual(frozen["evaluation_timeout_s"], 1800.)
            self.assertEqual(frozen["selected_seeds"], [4])
            self.assertEqual(frozen["protocol"]["safety_gates"], self.legacy["safety_gates"])
            self.assertEqual(frozen["protocol"]["supervisor_status_timing"], self.legacy["supervisor_status_timing"])
            v4.validate_plan(frozen)
            for trial in frozen["trials"]:
                self.assertEqual(trial[v4.SIMULATION_PACING_FIELD], protocol[v4.SIMULATION_PACING_FIELD])
                self.assertEqual(v4.simulation_pacing_trial_binding(frozen, trial), v4.SIMULATION_PACING_V1)
                self.assertEqual(trial["duration_s"], 75.)
                command = trial["flight_command"]
                for flag, value in (("--real-time-factor", .125), ("--wall-timeout", 1000.),
                                    ("--max-inference-rate-hz", 10.)):
                    self.assertEqual(command.count(flag), 1)
                    self.assertEqual(float(command[command.index(flag) + 1]), value)
        for wall in (600., 999., 1001., True, float("nan")):
            with self.subTest(wall=wall), self.assertRaises(ValueError):
                self.make(groups=["stage1_velocity"], wall_timeout=wall)

    def test_cli_defaults_to_new_protocol_budget_without_creating_formal_or_running_flights(self):
        self.declare()
        with patch.object(v4, "verify_external_runtime", side_effect=fixtures.fixture_runtime_verifier), redirect_stdout(io.StringIO()):
            self.assertEqual(v4.main(["plan", "--frozen-root", str(self.root), "--output", "results/cli",
                "--prefix", "reliability_v4_pacing_cli", "--probe", "--seeds", "4",
                "--groups", "stage1_velocity", "--classes", "car"]), 0)
        frozen = v4.load(self.root / "results/cli/plan.json")
        self.assertEqual(frozen["mode"], "PROBE")
        self.assertEqual(frozen["trials"][0]["wall_timeout_s"], 1000.)
        self.assertEqual(frozen["trial_timeout_s"], 2800.)
        with self.assertRaisesRegex(ValueError, "Held-out"):
            fixtures.make_fixture_plan(self.root, "results/heldout", "reliability_v4_pacing_heldout", seeds=[1000])
        with self.assertRaisesRegex(ValueError, "REGISTERED"):
            fixtures.make_fixture_plan(self.root, "results/formal", "reliability_v4_pacing_formal", formal=True)

    def test_resealed_trial_cannot_hide_changed_pacing_spec_or_argv(self):
        self.declare()
        original = self.make(groups=["stage1_velocity"])
        for defect in ("missing_spec", "spec", "wall", "rtf", "inference", "duplicate", "assignment"):
            frozen = deepcopy(original)
            trial = frozen["trials"][0]
            command = trial["flight_command"]
            if defect == "missing_spec":
                trial.pop(v4.SIMULATION_PACING_FIELD)
            elif defect == "spec":
                trial[v4.SIMULATION_PACING_FIELD]["real_time_factor"] = .25
            elif defect == "wall":
                trial["wall_timeout_s"] = 600.
                command[command.index("--wall-timeout") + 1] = "600.0"
                frozen["trial_timeout_s"] = 2400.
            elif defect in {"rtf", "inference"}:
                flag = "--real-time-factor" if defect == "rtf" else "--max-inference-rate-hz"
                command[command.index(flag) + 1] = "0.25" if defect == "rtf" else "5.0"
            elif defect == "duplicate":
                command.extend(["--real-time-factor", "0.125"])
            else:
                command.append("--real-time-factor=0.125")
            frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                v4.validate_plan(frozen)
            self.assertTrue(v4.runtime_configuration(frozen, trial)["errors"])

    def test_runtime_configuration_checks_actual_rtf_budget_supervisor_and_world(self):
        self.declare()
        frozen = self.make(groups=["stage1_velocity"])
        trial = frozen["trials"][0]
        fixtures.FakeCommands()(trial["flight_command"], self.root / "runtime.log", self.root, 1.)
        directory = Path(trial["directory"])
        config_path = directory / "run_config.json"
        parameters_path = directory / "configuration/runtime_parameters.yaml"
        world_path = directory / "configuration/runtime_world.sdf"
        magnetic_path = directory / "configuration/magnetic_environment.json"
        config, parameters, world = v4.load(config_path), v4.load(parameters_path), world_path.read_bytes()
        magnetic = v4.load(magnetic_path)
        self.assertEqual(config["real_time_factor"], .125)
        self.assertEqual(config["wall_timeout"], 1000.)
        self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
        for defect, label in (("rtf", "run_config:real_time_factor"), ("wall", "run_config:wall_timeout"),
                              ("supervisor", "requested_simulation_real_time_factor"),
                              ("world", "magnetic:final_world_real_time_factor"), ("age", "max_observation_age_s")):
            arguments, runtime = deepcopy(config), deepcopy(parameters)
            world_path.write_bytes(world)
            evidence = deepcopy(magnetic)
            if defect in {"rtf", "wall"}:
                arguments["real_time_factor" if defect == "rtf" else "wall_timeout"] = .25 if defect == "rtf" else 600.
            elif defect == "supervisor":
                runtime["uav_tracking_flight_supervisor"]["ros__parameters"]["requested_simulation_real_time_factor"] = .25
            elif defect == "age":
                runtime["uav_tracking_state_estimator"]["ros__parameters"]["max_observation_age_s"] = 1.2
            else:
                tree = ET.fromstring(world)
                tree.find("world/physics/real_time_factor").text = ".25"
                ET.ElementTree(tree).write(world_path)
                evidence["runtime_world_sha256"] = v4.sha(world_path)
            fixtures.write(config_path, arguments)
            fixtures.write(parameters_path, runtime)
            fixtures.write(magnetic_path, evidence)
            with self.subTest(defect=defect):
                self.assertTrue(any(label in error for error in v4.runtime_configuration(frozen, trial)["errors"]))

    def test_guard_four_safety_slots_inherit_new_protocol_pair(self):
        # Existing guard reads these values from the validated final protocol.
        with tempfile.TemporaryDirectory() as temporary:
            manifest, context, runtime, summary, facts, calls = guard_fixtures.safety_fixture(Path(temporary))
            context.core["protocol"].update(real_time_factor=.125, flight_wall_timeout_s=1000.,
                simulation_pacing_registration=deepcopy(v4.SIMULATION_PACING_V1))
            context.gate_bindings["simulation_pacing_sha256"] = v4.digest(v4.simulation_pacing_summary(context.core["protocol"]))
            registry = guard_fixtures.guard.load(facts["registry"]["path"])
            for slot in facts["slots"]:
                binding = slot["evidence"]["run_config"]
                config = guard_fixtures.guard.load(binding["path"])
                config.update(real_time_factor=.125, wall_timeout=1000.)
                slot["evidence"]["run_config"] = guard_fixtures.write(Path(binding["path"]), config)
                path = Path(slot["evidence"]["runtime_parameters"]["path"])
                import yaml
                parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
                parameters["uav_tracking_flight_supervisor"]["ros__parameters"]["requested_simulation_real_time_factor"] = .125
                path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
                slot["evidence"]["runtime_parameters"] = guard_fixtures.guard.file_binding(path)
                command = slot["executions"]["flight"]["argv"]
                command[command.index("--real-time-factor") + 1] = "0.125"
                command[command.index("--wall-timeout") + 1] = "1000.0"
                next(item for item in registry["trials"] if item["id"] == slot["id"])["flight_argv"] = list(command)
            facts["registry"] = guard_fixtures.write(Path(facts["registry"]["path"]), registry)
            guard_fixtures.SafetyTests.refresh(manifest, summary, facts)
            guard_fixtures.guard.validate_safety(manifest, context, runtime)
            self.assertEqual(len(calls), 4)

    def test_runner_gate_refuses_cross_pacing_evidence_in_both_directions(self):
        new = self.declare()
        for index, (target_protocol, previous_protocol) in enumerate(((new, self.legacy), (self.legacy, new))):
            target = {"protocol": deepcopy(target_protocol), "source_hashes": {}, "model_hashes": {},
                      "magnetic_runtime_binding": {"manifest_sha256": "1" * 64},
                      "magnetic_library_binding": {"registration_sha256": "2" * 64}}
            previous = {**deepcopy(target), "protocol": deepcopy(previous_protocol), "mode": "PROBE"}
            source = self.root / ("pacing_probe_" + str(index) + ".json")
            fixtures.write(source, previous)
            bindings = {"flight_source_hashes": {}, "evaluation_source_hashes": {}, "model_hashes": {},
                        "magnetic_runtime_manifest_sha256": "1" * 64,
                        "magnetic_library_registration_sha256": "2" * 64,
                        "navigation_acceptance_sha256": v4.digest(target_protocol["navigation_acceptance"])}
            if v4.simulation_pacing_declared(target_protocol):
                bindings["simulation_pacing_sha256"] = v4.digest(v4.simulation_pacing_summary(target_protocol))
            gate = {"schema_version": 2, "result": "PASS", "ready_for_formal_reliability_v4": True,
                    "checks": {name: True for name in v4.PROBE_CHECKS}, "bindings": bindings,
                    "probe_slots": [{"plan_path": str(source), "plan_file_sha256": v4.sha(source), "slot_id": "inert"}]}
            artifact = self.root / ("pacing_gate_" + str(index) + ".json")
            fixtures.write(artifact, gate)
            target["development_probe_gate"] = {"path": str(artifact), "sha256": v4.sha(artifact), "evidence": gate}
            with self.subTest(target=target_protocol["real_time_factor"]), patch.object(v4, "validate_plan"), \
                    patch.object(v4, "read_slots", side_effect=AssertionError("Refuse before record reads")), \
                    self.assertRaisesRegex(ValueError, "simulation pacing differs"):
                v4.validate_probe_gate(target)


if __name__ == "__main__":
    unittest.main()
