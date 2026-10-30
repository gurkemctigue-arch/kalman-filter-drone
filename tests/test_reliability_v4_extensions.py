"""Prospective extension scheduling and immutable evidence; no ROS or flights."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reliability_v4_runner as fixtures

v4 = fixtures.v4


def extension_fixture(root, *, registered=False):
    fixtures.fixture(root, gates=registered)
    extension = v4.load(fixtures.ROOT / v4.EXTENSION_PROTOCOL_PATH)
    fixtures.write(root / v4.EXTENSION_PROTOCOL_PATH, extension)
    return extension


def make(root, *, output="results/extensions", prefix="reliability_v4_extension_fixture", **kwargs):
    with patch.object(v4, "verify_external_runtime", side_effect=fixtures.fixture_runtime_verifier):
        return v4.make_extension_plan(root, output, prefix, **kwargs)


class ExtensionCommands(fixtures.FakeCommands):
    """Only synthetic fixtures; never accepted by the real runtime verifier."""
    def __init__(self, *, algorithm_failure=False, **kwargs):
        super().__init__(surface="FAIL" if algorithm_failure else "PASS", **kwargs)
        self.algorithm_failure = algorithm_failure

    def __call__(self, command, log, root, timeout):
        result = super().__call__(command, log, root, timeout)
        script = Path(command[2]).name
        if script == "run_stage1_trial.py":
            config_path = root/"results"/command[command.index("--name")+1]/"run_config.json"
            config = v4.load(config_path)
            config["motion_profile_kind"] = command[command.index("--motion-profile-kind")+1]
            fixtures.write(config_path, config)
        elif script == "evaluate_stage1_flight.py":
            path = Path(command[command.index("--output")+1]); report = v4.load(path)
            report["acceptance"].update(missing_topics=[],input_read_error_count=0,clock_timebase_available=True,
                short_occlusion_recorded=True,long_occlusion_recorded=True,failed_events_retained=True)
            report.update(flight_evidence={"armed_seen":True,"offboard_seen":True},detector={"invalid_diagnostic_messages":0})
            report["occlusions"] = []
            for kind in ("short", "long"):
                checks = {key:True for key in ("recorded_close_event", "shutter_close_service_succeeded", "shutter_open_service_succeeded",
                    "shutter_close_ack_before_open_request", "detector_interruption_observed", "prediction_observed",
                    "lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion", "sustained_low_speed_after_hover",
                    "no_automatic_recovery_after_long_loss", "no_tracking_control_before_reselection_after_long_loss",
                    "sustained_tracking_after_reselection", "no_loss_during_short_occlusion", "identity_preserved_on_observed_recovery")}
                if self.algorithm_failure and kind == "short":checks["no_loss_during_short_occlusion"] = False
                report["occlusions"].append({"kind":kind,"checks":checks})
            fixtures.write(path, report)
        elif script == "evaluate_navigation_reference.py":
            path = Path(command[command.index("--output")+1]); report = v4.load(path)
            config = v4.load(path.parent/"run_config.json"); distance = config["desired_distance_m"]
            report["reference"]["desired_horizontal_distance_m"] = distance
            report["whole_interval"]["transients"]["base_link"]["distance"]["band_m"] = max(.5,.1*distance)
            if self.algorithm_failure:report["whole_interval"]["metrics"]["base_link_distance_error_m"]["rmse"] = 10.
            fixtures.write(path, report)
        return result


def registered_fixture(root, *, algorithm_failure=False):
    """Exercise both development matrices before synthesizing test registration."""
    extension_fixture(root, registered=True)
    core_gate = fixtures.fixture_probe_gate(root)
    development = make(root, seeds=[4], output="results/extension_development", prefix="reliability_v4_extension_development")
    v4.persist_plan(development)
    result = fixtures.run(development, ExtensionCommands(algorithm_failure=algorithm_failure))
    if result["terminal_count"] != 16 or result["stop"]:
        raise AssertionError(result)
    gate = {"schema_version":2,"result":"PASS","ready_for_formal_condition_extensions":True,
        "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY", "checks":{key:True for key in v4.EXTENSION_PROBE_CHECKS},
        "bindings":v4.load(core_gate)["bindings"], "probe_slots":[], "known_algorithm_failures":[]}
    for trial in development["trials"]:
        record = v4.read_slots(development)[trial["id"]]
        item = {"plan_path":str(Path(development["output"])/"plan.json"),
                "plan_file_sha256":v4.sha(Path(development["output"])/"plan.json"), "slot_id":trial["id"],
                "record_file_sha256":v4.sha(v4.record_path(development,trial))}
        gate["probe_slots"].append(item)
        flight = next(command for command in record["commands"] if command["kind"] == "flight")
        failures = v4.extension_algorithm_failures(development,trial,flight,record["evaluations"])
        if failures:gate["known_algorithm_failures"].append({"plan_path":item["plan_path"],"slot_id":trial["id"],"failures":failures})
    gate_path = root/"extension_probe_gate.json"; fixtures.write(gate_path,gate)
    extension = v4.load(root/v4.EXTENSION_PROTOCOL_PATH)
    extension.update(status="REGISTERED",registration_utc=v4.utc_now(),
        development_readiness={"path":str(gate_path),"sha256":v4.sha(gate_path),"evidence":gate})
    fixtures.write(root/v4.EXTENSION_PROTOCOL_PATH,extension)
    core = fixtures.make_fixture_plan(root,"results/core_formal","reliability_v4_core_formal",formal=True,probe_gate=core_gate)
    v4.persist_plan(core)
    return core_gate, Path(core["output"])/"plan.json"


class CorrelatedBoundExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        extension_fixture(self.root)

    def declare(self):
        protocol = v4.load(self.root/v4.PROTOCOL_PATH)
        for cls in v4.CLASSES:
            protocol["resources"][cls][v4.CORRELATED_BOUND_FIELD] = cls == "car"
        fixtures.write(self.root/v4.PROTOCOL_PATH, protocol)

    def test_class_geometry_setting_survives_every_extension_condition(self):
        self.declare()
        frozen = make(self.root, seeds=[4])
        v4.validate_plan(frozen)
        self.assertEqual(len(frozen["trials"]), 16)
        for trial in frozen["trials"]:
            enabled = trial["target_class"] == "car"
            self.assertIs(trial[v4.CORRELATED_BOUND_FIELD], enabled)
            self.assertEqual(trial["flight_command"].count(v4.CORRELATED_BOUND_FLAG), int(enabled))
            self.assertEqual(v4.correlated_two_face_trial_binding(frozen, trial), (enabled, True))

    def test_extension_runtime_requires_both_registered_bool_archives(self):
        self.declare()
        frozen = make(self.root, seeds=[4], conditions=["latency"])
        for trial in frozen["trials"]:
            ExtensionCommands()(trial["flight_command"], self.root/(trial["id"]+".log"), self.root, 1.)
            self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
            directory = Path(trial["directory"])
            config_path = directory/"run_config.json"
            yaml_path = directory/"configuration/runtime_parameters.yaml"
            config, parameters = v4.load(config_path), v4.load(yaml_path)
            for location in ("arguments", "yaml"):
                arguments, runtime = deepcopy(config), deepcopy(parameters)
                if location == "arguments":arguments.pop("correlated_two_face_bound")
                else:runtime["uav_tracking_state_estimator"]["ros__parameters"].pop(v4.CORRELATED_BOUND_FIELD)
                fixtures.write(config_path, arguments); fixtures.write(yaml_path, runtime)
                label = ("run_config:correlated_two_face_bound" if location == "arguments" else
                         "runtime_parameters:uav_tracking_state_estimator:"+v4.CORRELATED_BOUND_FIELD)
                self.assertIn(label, v4.runtime_configuration(frozen, trial)["errors"])

    def test_resealed_extension_cannot_change_class_or_cli_opt_in(self):
        self.declare()
        original = make(self.root, seeds=[4], conditions=["latency"], classes=["car"])
        for defect in ("missing_spec", "off_spec", "cli", "resource"):
            with self.subTest(defect=defect):
                frozen = deepcopy(original); trial = frozen["trials"][0]
                if defect == "missing_spec":trial.pop(v4.CORRELATED_BOUND_FIELD)
                elif defect == "off_spec":trial[v4.CORRELATED_BOUND_FIELD] = False
                elif defect == "cli":trial["flight_command"].remove(v4.CORRELATED_BOUND_FLAG)
                else:frozen["protocol"]["resources"]["car"][v4.CORRELATED_BOUND_FIELD] = False
                frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
                with self.assertRaises(ValueError):v4.validate_plan(frozen)

    def test_old_extension_is_off_and_hidden_runtime_enablement_is_rejected(self):
        frozen = make(self.root, seeds=[4], conditions=["latency"], classes=["car"])
        trial = frozen["trials"][0]
        self.assertNotIn(v4.CORRELATED_BOUND_FIELD, trial)
        ExtensionCommands()(trial["flight_command"], self.root/"legacy.log", self.root, 1.)
        directory = Path(trial["directory"])
        config_path, yaml_path = directory/"run_config.json", directory/"configuration/runtime_parameters.yaml"
        config, parameters = v4.load(config_path), v4.load(yaml_path)
        config.pop("correlated_two_face_bound")
        estimator = parameters["uav_tracking_state_estimator"]["ros__parameters"]
        estimator.pop(v4.CORRELATED_BOUND_FIELD)
        fixtures.write(config_path, config); fixtures.write(yaml_path, parameters)
        self.assertEqual(v4.runtime_configuration(frozen, trial)["errors"], [])
        estimator[v4.CORRELATED_BOUND_FIELD] = True
        fixtures.write(yaml_path, parameters)
        self.assertIn("runtime_parameters:uav_tracking_state_estimator:"+v4.CORRELATED_BOUND_FIELD,
                      v4.runtime_configuration(frozen, trial)["errors"])


class ExtensionTests(unittest.TestCase):
    def test_draft_generates_sixteen_development_cells_without_heldout_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            result = make(root, seeds=[4])
            v4.validate_plan(result)
            self.assertEqual(result["mode"], "EXTENSION_PROBE")
            self.assertEqual(len(result["trials"]), 16)
            self.assertEqual(len({trial["name"] for trial in result["trials"]}), 16)
            self.assertEqual({trial["seed"] for trial in result["trials"]}, {4})
            for trial in result["trials"]:
                self.assertNotIn("extension", trial["comparison_reference_id"])
                self.assertEqual(trial["comparison_reference_id"],
                    f'{trial["target_class"]}_{trial["group"]}_seed004')
                self.assertIn(trial["name"], trial["directory"])
                for evaluation in trial["evaluations"]:
                    self.assertIn(trial["name"], evaluation["report"])
                    self.assertNotIn(f'reliability_v4_extension_fixture_{trial["comparison_reference_id"]}',
                                     evaluation["report"])

    def test_each_condition_changes_only_declared_flight_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension = extension_fixture(root)
            historical_duration = {**extension, "duration_s": 45.}
            with self.assertRaisesRegex(ValueError, "duration_s"):
                v4.validate_extension_protocol(historical_duration, v4.load(root / v4.PROTOCOL_PATH))
            result = make(root, seeds=[4])
            for trial in result["trials"]:
                command = trial["flight_command"]
                option = lambda name: command[command.index(name) + 1]
                self.assertEqual(trial["duration_s"], 75.)
                self.assertEqual(float(option("--duration")), 75.)
                self.assertEqual(float(option("--real-time-factor")), .25)
                self.assertEqual(float(option("--wall-timeout")), 600.)
                self.assertEqual(result["trial_timeout_s"], 2400.)
                self.assertEqual(option("--condition"), trial["condition"])
                self.assertEqual(option("--motion-profile-kind"), trial["motion_profile_kind"])
                self.assertEqual(float(option("--desired-distance-m")), trial["desired_distance_m"])
                self.assertEqual(option("--takeoff-mode"), "px4_native")
                self.assertEqual(option("--gazebo-render-driver"), "llvmpipe")
                self.assertIn("--occlusions", command)
                self.assertIn("--reselect-after-loss", command)
                if trial["extension_condition"] == "speed_changes_position":
                    self.assertEqual(trial["command_mode"], "position")
                else:
                    self.assertEqual(trial["command_mode"], "velocity")
                if trial["extension_condition"] == "far_distance":
                    expected = 7. if trial["target_class"] == "person" else 12.
                    self.assertEqual(trial["desired_distance_m"], expected)
                    surface = next(item for item in trial["evaluations"] if item["kind"] == "surface_flight")
                    cmd = surface["command"]
                    self.assertEqual(float(cmd[cmd.index("--desired-distance-m") + 1]), expected)

    def test_development_cannot_consume_any_formal_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            with self.assertRaisesRegex(ValueError, "Held-out"):
                make(root, seeds=[1000])

    def test_draft_blocks_formal_before_runtime_or_data_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            with patch.object(v4, "make_plan", side_effect=AssertionError("must reject draft first")):
                with self.assertRaisesRegex(ValueError, "REGISTERED"):
                    make(root, formal=True)

    def test_formal_has_exact_160_cells_and_same_core_seed_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate, reference = registered_fixture(root)
            result = make(root, formal=True, probe_gate=gate, reference_plan=reference)
            v4.validate_plan(result)
            self.assertEqual(result["mode"], "EXTENSION_FORMAL")
            self.assertEqual(len(result["trials"]), 160)
            self.assertEqual({trial["seed"] for trial in result["trials"]}, set(v4.FORMAL_SEEDS))
            self.assertEqual(len({trial["comparison_reference_id"] for trial in result["trials"]}), 40)
            for condition in v4.EXTENSION_CONDITIONS:
                self.assertEqual(sum(t["extension_condition"] == condition for t in result["trials"]), 20)

    def test_formal_cannot_drop_conditions_or_skip_development_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate, reference = registered_fixture(root)
            with self.assertRaisesRegex(ValueError, "complete"):
                make(root, formal=True, conditions=["latency"],reference_plan=reference)
            with self.assertRaisesRegex(ValueError, "development-probe"):
                make(root, formal=True,reference_plan=reference)
            with self.assertRaisesRegex(ValueError, "reference-plan"):
                make(root, formal=True,probe_gate=gate)

    def test_status_boolean_without_utc_and_real_readiness_cannot_register_core_or_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension = extension_fixture(root,registered=True)
            extension["status"] = "REGISTERED"; fixtures.write(root/v4.EXTENSION_PROTOCOL_PATH,extension)
            for operation in (lambda:make(root,formal=True),
                              lambda:fixtures.make_fixture_plan(root,"results/core","reliability_v4_core",formal=True)):
                with self.assertRaisesRegex(ValueError,"UTC"):
                    operation()
            extension["registration_utc"] = v4.utc_now(); fixtures.write(root/v4.EXTENSION_PROTOCOL_PATH,extension)
            with self.assertRaisesRegex(ValueError,"readiness"):
                fixtures.make_fixture_plan(root,"results/core","reliability_v4_core",formal=True)

    def test_draft_extensions_also_block_new_core_formal_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            with self.assertRaisesRegex(ValueError,"REGISTERED"):
                fixtures.make_fixture_plan(root,"results/core","reliability_v4_core",formal=True)

    def test_known_stress_algorithm_failures_are_registered_and_do_not_select_successful_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate, reference = registered_fixture(root,algorithm_failure=True)
            result = make(root,formal=True,probe_gate=gate,reference_plan=reference)
            known = result["extension_protocol_binding"]["protocol"]["development_readiness"]["evidence"]["known_algorithm_failures"]
            self.assertEqual(len(known),16)
            self.assertTrue(all(len(item["failures"]) == 2 for item in known))
            self.assertEqual(len(result["trials"]),160)

    def test_core_reference_and_registration_must_match_actual_frozen_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate, reference = registered_fixture(root)
            original = make(root,formal=True,probe_gate=gate,reference_plan=reference)
            for defect in ("file_hash", "digest", "reference_id", "source", "core_registration", "late_registration"):
                with self.subTest(defect=defect):
                    result = deepcopy(original)
                    if defect == "file_hash":result["core_reference_binding"]["sha256"] = "0"*64
                    elif defect == "digest":result["core_reference_binding"]["plan_sha256"] = "0"*64
                    elif defect == "reference_id":result["core_reference_binding"]["reference_ids"].pop()
                    elif defect == "source":result["source_hashes"]["scripts/run_stage1_trial.py"] = "0"*64
                    elif defect == "core_registration":result["extension_protocol_binding"]["sha256"] = "0"*64
                    else:result["extension_protocol_binding"]["protocol"]["registration_utc"] = "2999-01-01T00:00:00+00:00"
                    result["plan_sha256"] = v4.digest(result,("plan_sha256",))
                    with self.assertRaises(ValueError):v4.validate_plan(result)

    def test_readiness_cannot_omit_slots_or_known_failures_after_hash_reseal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate, reference = registered_fixture(root,algorithm_failure=True)
            original = make(root,formal=True,probe_gate=gate,reference_plan=reference)
            for defect in ("subset", "hide_failure", "missing_check", "time"):
                with self.subTest(defect=defect):
                    result = deepcopy(original); extension = result["extension_protocol_binding"]["protocol"]
                    binding = extension["development_readiness"]; evidence = binding["evidence"]
                    if defect == "subset":evidence["probe_slots"].pop()
                    elif defect == "hide_failure":evidence["known_algorithm_failures"].pop()
                    elif defect == "missing_check":evidence["checks"].pop(v4.EXTENSION_PROBE_CHECKS[0])
                    else:extension["registration_utc"] = "2000-01-01T00:00:00+00:00"
                    fixtures.write(Path(binding["path"]),evidence); binding["sha256"] = v4.sha(binding["path"])
                    result["plan_sha256"] = v4.digest(result,("plan_sha256",))
                    with self.assertRaises(ValueError):v4.validate_plan(result)

    def test_stress_failure_policy_never_accepts_missing_recording_or_unsafe_long_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root,registered=True)
            plan = make(root,seeds=[4],classes=["person"],conditions=["dropout"])
            v4.persist_plan(plan); fixtures.run(plan,ExtensionCommands(algorithm_failure=True))
            trial = plan["trials"][0]; record = v4.read_slots(plan)[trial["id"]]
            flight = next(item for item in record["commands"] if item["kind"] == "flight")
            spec = next(item for item in trial["evaluations"] if item["kind"] == "surface_flight")
            path = Path(spec["report"]); original = v4.load(path)
            for defect in ("missing_topics", "read_errors", "invalid_diagnostic", "hover", "braking", "automatic_recovery", "missing_prediction"):
                with self.subTest(defect=defect):
                    report = deepcopy(original)
                    if defect == "missing_topics":report["acceptance"]["missing_topics"] = ["/tracking/state"]
                    elif defect == "read_errors":report["acceptance"]["input_read_error_count"] = 1
                    elif defect == "invalid_diagnostic":report["detector"]["invalid_diagnostic_messages"] = True
                    elif defect == "hover":report["occlusions"][1]["checks"]["hover_observed_for_long_occlusion"] = False
                    elif defect == "braking":report["occlusions"][1]["checks"]["sustained_low_speed_after_hover"] = False
                    elif defect == "automatic_recovery":report["occlusions"][1]["checks"]["no_automatic_recovery_after_long_loss"] = False
                    else:report["occlusions"][0]["checks"]["prediction_observed"] = None
                    fixtures.write(path,report)
                    entries = deepcopy(record["evaluations"])
                    next(item for item in entries if item["kind"] == "surface_flight")["report_sha256"] = v4.sha(path)
                    with self.assertRaises(ValueError):v4.extension_algorithm_failures(plan,trial,flight,entries)

    def test_plan_rejects_tampered_command_even_after_digest_resealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            original = make(root, conditions=["latency"], classes=["person"], seeds=[4])
            for defect in ("condition", "reference", "distance", "denominator"):
                with self.subTest(defect=defect):
                    result = deepcopy(original)
                    trial = result["trials"][0]
                    if defect == "condition":
                        cmd = trial["flight_command"]; cmd[cmd.index("--condition") + 1] = "clean"
                    elif defect == "reference":
                        trial["comparison_reference_id"] = "person_stage1_velocity_seed999"
                    elif defect == "distance":
                        trial["desired_distance_m"] = 12.
                    else:
                        result["trials"].append(deepcopy(trial))
                    result["plan_sha256"] = v4.digest(result, ("plan_sha256",))
                    with self.assertRaises(ValueError):
                        v4.validate_plan(result)

    def test_extension_protocol_is_bound_at_every_source_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension = extension_fixture(root)
            result = make(root, seeds=[4])
            extension["sampling_policy"] += " changed"
            fixtures.write(root / v4.EXTENSION_PROTOCOL_PATH, extension)
            with self.assertRaisesRegex(ValueError, "extension protocol changed"):
                v4.verify_sources(result)

    def test_existing_artifacts_are_not_reused_as_new_extension_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); extension_fixture(root)
            result = make(root, conditions=["latency"], classes=["person"], seeds=[4])
            Path(result["trials"][0]["directory"]).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "already exist"):
                make(root, conditions=["latency"], classes=["person"], seeds=[4])


if __name__ == "__main__":
    unittest.main()
