"""Registration assembly regressions with inert temporary files, never flights.

Frozen-runtime doubles are explicit. Real guard provenance/statistics checks are
retained where exercised; none of these fixture outputs is real registration.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from tests import test_reliability_v4_guard as fixtures

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registration_assembly_fixture", ROOT / "tools/reliability_v4_register.py")
register = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(register)


def write(path, value):
    return fixtures.write(path, value)


def safety_inputs(root):
    _, context, runtime, _, facts, _ = fixtures.safety_fixture(root)
    for slot in facts["slots"]:
        path = Path(slot["evidence"]["recording_closure"]["path"])
        closure = register.guard.load(path)
        closure["status"] = "PASS"
        slot["evidence"]["recording_closure"] = write(path, closure)
    write(root / "facts.json", facts)
    gate = write(root / "gate.json", {"bindings": context.gate_bindings})
    return {"target_plan": context.development_path, "core_gate": Path(gate["path"]),
            "facts": root / "facts.json"}, context, runtime, facts


def replay_inputs(root):
    _, context, runtime, candidate, records = fixtures.calibration_fixture(root)
    final = context.root
    results = final / "results"
    results.mkdir()
    development_path = Path(candidate["development_plan"]["path"])
    development = register.guard.load(development_path)
    development["results_root"] = str((development_path.parent / "results").resolve())
    development["plan_sha256"] = register.guard.sealed(development, "plan_sha256")
    candidate["development_plan"] = {**write(development_path, development), "plan_sha256": development["plan_sha256"]}
    for cls in register.guard.CLASSES:
        provenance = candidate["provenance"][cls]
        receipt = provenance["verified_export_evidence"]
        receipt["sidecar_sha256"] = {}
        for name in ("online_equivalence.json", "native_state_audit.json", "truth_alignment.json"):
            sidecar = Path(provenance["arrays"]["path"]).parent / name
            receipt["sidecar_sha256"][name] = write(sidecar, {"inert_fixture_only": True})["sha256"]
    policy = Path(development["frozen_root"]) / runtime.calibration.POLICY
    policy.parent.mkdir(exist_ok=True)
    policy.write_text("# inert fixture policy, not real calibration\n", encoding="utf-8")
    candidate["policy"] = {"path": runtime.calibration.POLICY, "sha256": register.guard.sha(policy)}
    helper = final / "scripts/calibrate_estimator_replay_v4.py"
    helper.parent.mkdir(exist_ok=True)
    helper.write_text("# inert helper fixture, never imported\n", encoding="utf-8")
    candidate["source_hashes"] = {"scripts/calibrate_estimator_replay_v4.py": register.guard.sha(helper)}
    candidate["candidate_parameters"].update(
        Q_model_and_parameters={"model": "piecewise_constant_acceleration", "acceleration_std_mps2": 1.},
        P0_matrix_and_initial_velocity_policy={"covariance_6x6": [[float(i == j) for j in range(6)] for i in range(6)],
            "velocity_policy": "registered_constant", "initial_velocity_mps": [0., 0., 0.]},
        common_gate_R_and_initialization_policy={"measurement_covariance": "geometry_plus_pose", "initialization": "common_P0", "threshold_squared": 9.21},
        common_support_truth_coverage_requirement=.8)
    candidate_path = root / "candidate.json"
    write(candidate_path, candidate)
    draft_path = final / register.REPLAY_PATH
    draft_path.parent.mkdir(exist_ok=True)
    draft_path.write_bytes((ROOT / register.REPLAY_PATH).read_bytes())
    core = context.core
    core.update(mode="FORMAL", frozen_root=str(final), results_root=str(results), created_utc=fixtures.T,
        plan_sha256="d" * 64, model_hashes={"model.pt": "e" * 64},
        magnetic_runtime_binding={"manifest_sha256": "a" * 64},
        magnetic_library_binding={"registration_sha256": "b" * 64})
    core["source_hashes"].update({"fixture_helper.py": register.guard.sha(final / "fixture_helper.py"),
        "flight_only.py": "f" * 64, "scripts/calibrate_estimator_replay_v4.py": register.guard.sha(helper)})
    core["trials"] = [{"id": f"{cls}_{group}_seed{seed}", "directory": str(results / f"{cls}_{group}_{seed}")}
                      for cls in register.guard.CLASSES for group in register.guard.GROUPS for seed in range(1000, 1010)]
    core_path = results / "core/plan.json"
    write(core_path, core)
    runtime.v4.verify_sources = Mock()
    runtime.v4.read_slots = lambda plan, **kwargs: ({trial["id"]: {"status": "PENDING"} for trial in plan["trials"]}
                                                   if plan.get("mode") == "FORMAL" else records)
    from uav_tracking import replay_comparison
    runtime.replay.EXPORT_SIDECARS = replay_comparison.EXPORT_SIDECARS
    runtime.replay.canonical_sha256 = replay_comparison.canonical_sha256
    runtime.replay.configuration_digest = replay_comparison.configuration_digest
    # The exact real parameter validator is used. The separate artifact checker
    # is a recorded delegation boundary; real R0/sidecar checks below still run.
    runtime.replay.validate_registered_config = replay_comparison.validate_registered_config
    runtime.replay.verify_registration_artifacts = Mock()
    # The pure configuration validator needs the four actual source-map keys.
    for name in replay_comparison.SOURCE_FILES:
        path = final / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# inert replay helper fixture\n", encoding="utf-8")
        core["source_hashes"][name] = register.guard.sha(path)
    runtime.replay.SOURCE_FILES = replay_comparison.SOURCE_FILES
    # Include all replay keys in the audit source set so the real guard's
    # cross-map construction remains meaningful with these inert helpers.
    runtime.replay.EXPORT_SOURCE_FILES = ("fixture_helper.py", *replay_comparison.SOURCE_FILES)
    write(core_path, core)
    return {"core_plan": core_path, "candidate": candidate_path}, context, runtime, candidate, draft_path


class GeometrySafetyAssemblyTests(unittest.TestCase):
    def test_matching_new_geometry_archives_assemble_without_changing_facts(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs, context, runtime, facts = safety_inputs(root)
                fixtures.bind_geometry_safety_fixture(context, facts, car=enabled)
                write(inputs['facts'], facts)
                original = inputs['facts'].read_bytes()
                with patch.object(register, 'gate_context', return_value=(runtime, context)):
                    result = register.run_action('safety-summary', inputs, root/'assembled')
                self.assertEqual(register.guard.load(result['artifact']['path'])['slots'], facts['slots'])
                self.assertEqual(inputs['facts'].read_bytes(), original)

    def test_off_safety_does_not_prove_a_new_on_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, context, runtime, _facts = safety_inputs(root)
            context.core['protocol']['resources']['car'][register.guard.CORRELATED_BOUND_FIELD] = True
            with patch.object(register, 'gate_context', return_value=(runtime, context)), \
                    self.assertRaisesRegex(ValueError, 'Safety geometry'):
                register.run_action('safety-summary', inputs, root/'refused')
            self.assertFalse((root/'refused/safety_summary_candidate.json').exists())

    def test_rebinding_hashes_cannot_hide_unregistered_runtime_enablement(self):
        for location in ('arguments', 'yaml', 'argv'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs, context, runtime, facts = safety_inputs(root)
                slot = next(row for row in facts['slots'] if row['target_class'] == 'car')
                if location == 'arguments':
                    binding = slot['evidence']['run_config']; data = register.guard.load(binding['path'])
                    data['correlated_two_face_bound'] = True
                    slot['evidence']['run_config'] = write(Path(binding['path']), data)
                elif location == 'yaml':
                    binding = slot['evidence']['runtime_parameters']; path = Path(binding['path'])
                    data = yaml.safe_load(path.read_text(encoding='utf-8'))
                    data['uav_tracking_state_estimator']['ros__parameters'][register.guard.CORRELATED_BOUND_FIELD] = True
                    path.write_text(yaml.safe_dump(data), encoding='utf-8')
                    slot['evidence']['runtime_parameters'] = register.guard.file_binding(path)
                else:
                    argv = slot['executions']['flight']['argv']; argv.append(register.guard.CORRELATED_BOUND_FLAG)
                    registry = register.guard.load(facts['registry']['path'])
                    next(row for row in registry['trials'] if row['id'] == slot['id'])['flight_argv'] = argv
                    facts['registry'] = write(Path(facts['registry']['path']), registry)
                write(inputs['facts'], facts)
                with patch.object(register, 'gate_context', return_value=(runtime, context)), \
                        self.assertRaisesRegex(ValueError, 'Safety geometry'):
                    register.run_action('safety-summary', inputs, root/'refused')

    def test_new_explicit_off_still_requires_yaml_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, context, runtime, facts = safety_inputs(root)
            fixtures.bind_geometry_safety_fixture(context, facts, car=False)
            slot = facts['slots'][0]
            binding = slot['evidence']['runtime_parameters']; path = Path(binding['path'])
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['uav_tracking_state_estimator']['ros__parameters'].pop(register.guard.CORRELATED_BOUND_FIELD)
            path.write_text(yaml.safe_dump(data), encoding='utf-8')
            slot['evidence']['runtime_parameters'] = register.guard.file_binding(path)
            write(inputs['facts'], facts)
            with patch.object(register, 'gate_context', return_value=(runtime, context)), \
                    self.assertRaisesRegex(ValueError, 'Safety geometry.*missing'):
                register.run_action('safety-summary', inputs, root/'refused')


class SafetyAssemblyTests(unittest.TestCase):
    def test_resource_mismatch_cannot_publish_a_safety_candidate_after_hash_rebinding(self):
        for defect in ("config_rtf", "config_wall", "supervisor_rtf", "flight_rtf", "flight_wall"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs, context, runtime, facts = safety_inputs(root)
                slot = facts["slots"][0]
                if defect.startswith("config_"):
                    binding = slot["evidence"]["run_config"]; data = register.guard.load(binding["path"])
                    key = "real_time_factor" if defect == "config_rtf" else "wall_timeout"
                    data[key] = .5 if key == "real_time_factor" else 300.
                    slot["evidence"]["run_config"] = write(Path(binding["path"]), data)
                elif defect == "supervisor_rtf":
                    binding = slot["evidence"]["runtime_parameters"]; path = Path(binding["path"])
                    data = yaml.safe_load(path.read_text())
                    data["uav_tracking_flight_supervisor"]["ros__parameters"]["requested_simulation_real_time_factor"] = .5
                    path.write_text(yaml.safe_dump(data), encoding="utf-8")
                    slot["evidence"]["runtime_parameters"] = register.guard.file_binding(path)
                else:
                    argv = slot["executions"]["flight"]["argv"]
                    flag = "--real-time-factor" if defect == "flight_rtf" else "--wall-timeout"
                    argv[argv.index(flag)+1] = "0.5" if defect == "flight_rtf" else "300.0"
                    registry = register.guard.load(facts["registry"]["path"])
                    next(row for row in registry["trials"] if row["id"] == slot["id"])["flight_argv"] = argv
                    facts["registry"] = write(Path(facts["registry"]["path"]), registry)
                write(inputs["facts"], facts)
                with patch.object(register, "gate_context", return_value=(runtime, context)), \
                        self.assertRaisesRegex(ValueError, "simulation resources"):
                    register.run_action("safety-summary", inputs, root / "refused")
                self.assertFalse((root / "refused/safety_summary_candidate.json").exists())

    def test_preserves_original_slots_and_real_sigint_without_fabricated_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, context, runtime, facts = safety_inputs(root)
            original = inputs["facts"].read_bytes()
            with patch.object(register, "gate_context", return_value=(runtime, context)), \
                    patch.object(register.guard, "validate_safety", side_effect=AssertionError("No registration timestamp exists yet")):
                result = register.run_action("safety-summary", inputs, root / "assembled")
            summary = register.guard.load(result["artifact"]["path"])
            self.assertEqual(summary["slots"], facts["slots"])
            codes = register.guard.load(summary["slots"][0]["evidence"]["process_exit_codes"]["path"])
            self.assertEqual(codes["agent"], -2)
            self.assertEqual(inputs["facts"].read_bytes(), original)
            self.assertEqual(result["detail"]["full_safety_validation"], "PENDING_SEAL_WITH_REAL_PROTOCOL_REGISTRATIONS")
            self.assertNotIn("registration_times", summary)
            self.assertFalse((root / "assembled/.validation/unpublished.json").exists())

    def test_changed_real_report_and_negative_safety_check_refuse_publication(self):
        for changed_bytes in (True, False):
            with self.subTest(changed_bytes=changed_bytes), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs, context, runtime, facts = safety_inputs(root)
                binding = facts["slots"][0]["evidence"]["specialized"]
                path = Path(binding["path"])
                report = register.guard.load(path)
                report["checks"][register.guard.AUTO_CHECKS[0]] = False
                new_binding = write(path, report)
                if not changed_bytes:
                    binding.update(new_binding)
                    write(inputs["facts"], facts)
                with patch.object(register, "gate_context", return_value=(runtime, context)), self.assertRaises(ValueError):
                    register.run_action("safety-summary", inputs, root / "refused")
                self.assertFalse((root / "refused/safety_summary_candidate.json").exists())
                self.assertEqual(register.guard.load(root / "refused/outcome.json")["status"], "REFUSED_NO_PUBLISHED_ARTIFACT")

    def test_failure_or_missing_attempt_is_not_relabelled_as_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, context, runtime, facts = safety_inputs(root)
            facts.update(result="FAIL", attempted_count=3, pending_count=1)
            write(inputs["facts"], facts)
            with patch.object(register, "gate_context", return_value=(runtime, context)), self.assertRaises(ValueError):
                register.run_action("safety-summary", inputs, root / "refused")
            self.assertFalse((root / "refused/safety_summary_candidate.json").exists())

    def test_missing_or_nonreal_scope_cannot_be_upgraded_to_real_recorded_evidence(self):
        for scope in (None, "UNDECLARED_CANDIDATE", "ORCHESTRATION_FIXTURE_ONLY"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs, context, runtime, facts = safety_inputs(root)
                if scope is None:
                    facts.pop("evidence_scope")
                else:
                    facts["evidence_scope"] = scope
                write(inputs["facts"], facts)
                with patch.object(register, "gate_context", return_value=(runtime, context)), self.assertRaises(ValueError):
                    register.run_action("safety-summary", inputs, root / "refused")
                self.assertFalse((root / "refused/safety_summary_candidate.json").exists())

    def test_source_tree_and_original_plan_matrix_outputs_are_refused_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, _, _, _ = safety_inputs(root)
            target = register.guard.load(inputs["target_plan"])
            target["output"] = str(Path(inputs["target_plan"]).parent)
            write(inputs["target_plan"], target)
            # This test only exercises location checks. Keep the separate
            # prospective source binding accurate after the fixture mutation.
            facts = register.guard.load(inputs["facts"])
            registry_path = Path(facts["registry"]["path"])
            registry = register.guard.load(registry_path)
            registry["source_core_plan"].update(write(inputs["target_plan"], target))
            facts["registry"] = write(registry_path, registry)
            write(inputs["facts"], facts)
            for destination in (ROOT / "config/forbidden_registration_assembly", Path(target["output"]) / "forbidden_assembly"):
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "source/build|plan matrix"):
                    register.run_action("safety-summary", inputs, destination)
                self.assertFalse(destination.exists())

    def test_output_inside_original_trial_rejected_before_creating_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, _, _, facts = safety_inputs(root)
            destination = Path(facts["slots"][0]["trial_directory"]) / "bad_assembly"
            with self.assertRaisesRegex(ValueError, "independent"):
                register.run_action("safety-summary", inputs, destination)
            self.assertFalse(destination.exists())


class ReplayAssemblyTests(unittest.TestCase):
    def test_full_plan_source_map_real_r0_and_exact_original_draft_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, context, runtime, candidate, draft_path = replay_inputs(root)
            original = draft_path.read_bytes()
            with patch.object(register.guard, "load_runtime", return_value=runtime):
                result = register.run_action("replay-config", inputs, root / "assembled")
            configuration = register.guard.load(result["artifact"]["path"])
            self.assertEqual(configuration["freeze_requirements"]["flight_source_hashes"], context.core["source_hashes"])
            self.assertIn("flight_only.py", configuration["freeze_requirements"]["flight_source_hashes"])
            self.assertEqual(configuration["calibration"]["R0_sensor_world_m2_by_class"], candidate["candidate_parameters"]["R0_sensor_world_m2_by_class"])
            self.assertEqual(draft_path.read_bytes(), original)
            self.assertEqual((root / "assembled/source_draft.original.json").read_bytes(), original)
            self.assertEqual(runtime.replay.verify_export_evidence.call_count, 2)
            self.assertIn(str(inputs["candidate"].resolve()), configuration["freeze_requirements"]["development_calibration_evidence"]["artifact_hashes"])
            self.assertEqual(configuration["methods"]["ema"]["alpha"], configuration["calibration"]["ema_alpha"])
            runtime.replay.verify_registration_artifacts.assert_called_once()

    def test_hash_shaped_candidate_cannot_replace_recomputed_geometry_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, _, runtime, candidate, draft_path = replay_inputs(root)
            candidate["classes"]["person"]["R0_sensor_world_m2"][0][0] += 100.
            write(inputs["candidate"], candidate)
            original = draft_path.read_bytes()
            with patch.object(register.guard, "load_runtime", return_value=runtime), self.assertRaisesRegex(ValueError, "statistics"):
                register.run_action("replay-config", inputs, root / "refused")
            self.assertFalse((root / "refused/replay_configuration_candidate.json").exists())
            self.assertEqual(draft_path.read_bytes(), original)

    def test_real_sidecar_bytes_are_checked_before_registration_candidate_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, _, runtime, candidate, _ = replay_inputs(root)
            path = Path(candidate["provenance"]["person"]["arrays"]["path"]).parent / "native_state_audit.json"
            path.write_text('{"changed":true}', encoding="utf-8")
            with patch.object(register.guard, "load_runtime", return_value=runtime), self.assertRaisesRegex(ValueError, "changed"):
                register.run_action("replay-config", inputs, root / "refused")
            self.assertFalse((root / "refused/replay_configuration_candidate.json").exists())

    def test_formal_attempt_is_refused_before_calibration_arrays_are_considered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, _, runtime, _, _ = replay_inputs(root)
            runtime.v4.read_slots = lambda *args, **kwargs: {"already_started": {"status": "FAIL"}}
            with patch.object(register.guard, "load_runtime", return_value=runtime), self.assertRaisesRegex(ValueError, "precede every formal"):
                register.run_action("replay-config", inputs, root / "refused")
            runtime.replay.verify_export_evidence.assert_not_called()


class SealAssemblyTests(unittest.TestCase):
    def request(self, root):
        manifest, _ = fixtures.plans(root)
        state = root / "results/guard_state"
        request = {"schema_version": 1, "kind": "RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST",
            **manifest, "registrations": {}, "calibration": {}, "safety": {}, "storage": {}, "state_directory": str(state)}
        path = root / "request.json"
        write(path, request)
        return path, state

    def test_only_a_complete_read_only_guard_check_can_publish_identical_sealed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, state = self.request(root)
            validated = {}

            def check(path):
                validated.update(register.guard.load(path))
                return SimpleNamespace(report={"result": "PASS", "capacity": {"pending_slots": 280}})

            with patch.object(register.guard, "check", side_effect=check), \
                    patch.object(register.guard, "execute_one", side_effect=AssertionError("Never fly")):
                result = register.run_action("seal", {"request": request}, root / "results/sealed")
            artifact = register.guard.load(result["artifact"]["path"])
            self.assertEqual(artifact, validated)
            self.assertEqual(artifact["manifest_sha256"], register.guard.sealed(artifact, "manifest_sha256"))
            self.assertEqual(artifact["tool"], register.guard.file_binding(register.guard.__file__))
            self.assertFalse(state.exists())
            self.assertFalse((root / "results/sealed/.validation/unpublished.json").exists())
            self.assertEqual(register.guard.load(root / "results/sealed/started.json")["registrar"], register.guard.file_binding(register.__file__))

    def test_real_guard_refusal_leaves_reason_and_no_usable_manifest_or_admission_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, state = self.request(root)
            with patch.object(register.guard, "check", side_effect=register.guard.Refusal("Actual safety or physical capacity is missing")), self.assertRaises(ValueError):
                register.run_action("seal", {"request": request}, root / "results/refused")
            self.assertFalse((root / "results/refused/final_admission.json").exists())
            self.assertFalse((root / "results/refused/.validation/unpublished.json").exists())
            self.assertFalse(state.exists())
            self.assertIn("physical capacity", register.guard.load(root / "results/refused/outcome.json")["error"])

    def test_no_manifest_refit_overwrite_or_caller_supplied_registration_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, state = self.request(root)
            data = register.guard.load(request)
            data["created_utc"] = "2099-01-01T00:00:00Z"
            write(request, data)
            with patch.object(register.guard, "check") as check, self.assertRaisesRegex(ValueError, "caller cannot supply time"):
                register.run_action("seal", {"request": request}, root / "results/refused")
            check.assert_not_called()
            with self.assertRaisesRegex(ValueError, "reuse"):
                register.run_action("seal", {"request": request}, root / "results/refused")
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
