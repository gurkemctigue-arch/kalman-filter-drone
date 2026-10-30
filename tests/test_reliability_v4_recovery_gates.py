"""Recovery-policy admission regressions using inert files, never flights."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tests import test_reliability_v4_guard as safety
from tests import test_reliability_v4_probe_gate as probes

builder = probes.builder
v4 = builder.v4
guard = safety.guard


def policy_plan(*, enabled=None):
    resources = {cls: {} for cls in v4.CLASSES}
    if enabled is not None:
        resources["car"][v4.CAR_SURFACE_RECOVERY_FIELD] = {
            **deepcopy(v4.CAR_SURFACE_RECOVERY_V1), "enabled": enabled}
    return {"protocol": {"resources": resources, "navigation_acceptance": {"fixture": True},
                         "real_time_factor": .25, "flight_wall_timeout_s": 600.},
            "source_hashes": {"uav_tracking/detection.py": "1" * 64}, "model_hashes": {},
            "magnetic_runtime_binding": {"manifest_sha256": "2" * 64,
                "manifest": {"evidence_scope": "ORCHESTRATION_FIXTURE_ONLY"}},
            "magnetic_library_binding": {"registration_sha256": "3" * 64}}


def pacing_plan(*, declared=False):
    plan = policy_plan()
    if declared:
        protocol = plan["protocol"]
        protocol[v4.SIMULATION_PACING_FIELD] = deepcopy(v4.SIMULATION_PACING_V1)
        protocol["real_time_factor"] = v4.SIMULATION_PACING_V1["real_time_factor"]
        protocol["flight_wall_timeout_s"] = v4.SIMULATION_PACING_V1["flight_wall_timeout_s"]
    return plan


def bind_recovery_safety(context, runtime, summary, facts):
    """Add complete synthetic declarations and archives to all four slots."""
    runtime.v4.car_surface_recovery_runtime_evidence = v4.car_surface_recovery_runtime_evidence
    registry = guard.load(facts["registry"]["path"])
    for cls, resource in context.core["protocol"]["resources"].items():
        resource[v4.CAR_SURFACE_RECOVERY_FIELD] = {
            **deepcopy(v4.CAR_SURFACE_RECOVERY_V1), "enabled": cls == "car"}
    context.gate_bindings["car_surface_recovery_sha256"] = v4.digest(
        v4.car_surface_recovery_summary(context.core["protocol"]))
    for slot in facts["slots"]:
        enabled = slot["target_class"] == "car"
        config_binding = slot["evidence"]["run_config"]
        config = guard.load(config_binding["path"])
        config.update(car_surface_recovery=enabled,
                      car_surface_recovery_method=v4.CAR_SURFACE_RECOVERY_V1["method"])
        slot["evidence"]["run_config"] = safety.write(Path(config_binding["path"]), config)
        parameter_path = Path(slot["evidence"]["runtime_parameters"]["path"])
        parameters = yaml.safe_load(parameter_path.read_text(encoding="utf-8"))
        detector = parameters["uav_tracking_detection"]["ros__parameters"]
        detector.update(v4.CAR_SURFACE_RECOVERY_RUNTIME_PARAMETERS)
        detector["car_surface_recovery_enabled"] = enabled
        parameter_path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
        slot["evidence"]["runtime_parameters"] = guard.file_binding(parameter_path)
        if enabled:
            slot["executions"]["flight"]["argv"].append(v4.CAR_SURFACE_RECOVERY_FLAG)
        next(row for row in registry["trials"] if row["id"] == slot["id"])["flight_argv"] = list(
            slot["executions"]["flight"]["argv"])
    facts["registry"] = safety.write(Path(facts["registry"]["path"]), registry)


class RecoveryProbeGateTests(unittest.TestCase):
    def test_bindings_preserve_legacy_bytes_and_bind_explicit_effective_policy(self):
        legacy = builder.bindings(policy_plan())
        self.assertEqual(set(legacy), {"flight_source_hashes", "evaluation_source_hashes", "model_hashes",
            "magnetic_runtime_manifest_sha256", "magnetic_library_registration_sha256",
            "navigation_acceptance_sha256"})
        off = builder.bindings(policy_plan(enabled=False))
        on = builder.bindings(policy_plan(enabled=True))
        self.assertEqual({k: value for k, value in off.items() if k != "car_surface_recovery_sha256"}, legacy)
        self.assertEqual(off["car_surface_recovery_sha256"], v4.digest(
            v4.car_surface_recovery_summary(policy_plan()["protocol"])))
        self.assertNotEqual(off["car_surface_recovery_sha256"], on["car_surface_recovery_sha256"])

    def test_legacy_and_explicit_off_are_the_same_effective_flight_policy(self):
        for left, right in ((None, False), (False, None), (True, True)):
            with self.subTest(left=left, right=right):
                builder.matching_recovery_policy(policy_plan(enabled=left), policy_plan(enabled=right))

    def test_core_and_extension_refuse_off_on_mismatch_before_reading_any_slot(self):
        for extension in (False, True):
            for target_on in (False, True):
                with self.subTest(extension=extension, target_on=target_on), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "immutable_probe.json"
                    path.write_text('{"scope":"INERT_POLICY_MISMATCH_FIXTURE"}', encoding="utf-8")
                    original = path.read_bytes()
                    target = policy_plan(enabled=target_on)
                    previous = policy_plan(enabled=not target_on)
                    self.assertEqual(target["source_hashes"], previous["source_hashes"])
                    with patch.object(builder, "read_plan", return_value=(path, previous)), \
                            patch.object(v4, "read_slots", side_effect=AssertionError("Must refuse before slot reads")), \
                            self.assertRaisesRegex(ValueError, "car_surface_recovery policy"):
                        builder.assemble(target, [path], extension=extension,
                            registration_utc=v4.utc_now() if extension else None)
                    self.assertEqual(path.read_bytes(), original)

    def test_gimbal_registration_cannot_qualify_a_different_recovery_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "probe.json"
            target, previous = policy_plan(enabled=True), policy_plan()
            output = Path(tmp) / "must_not_publish.json"
            with patch.object(builder, "target_snapshot", return_value=(path, target, {})), \
                    patch.object(builder, "read_plan", return_value=(path, previous)), \
                    self.assertRaisesRegex(ValueError, "car_surface_recovery policy"):
                builder.register_gimbal_reevaluations(path, path, output)
            self.assertFalse(output.exists())


class RecoverySafetyGateTests(unittest.TestCase):
    def test_historical_runner_accepts_only_implicit_off_archives_and_cli(self):
        runtime = SimpleNamespace(v4=SimpleNamespace())
        for present in (False, True):
            config = {"car_surface_recovery": False} if present else {}
            detector = {"car_surface_recovery_enabled": False} if present else {}
            self.assertFalse(guard.car_surface_recovery_evidence(runtime, {}, "car", config,
                {"uav_tracking_detection": {"ros__parameters": detector}}, []))
        for bad in (True, 0, 1, "false", None):
            for location in ("config", "yaml"):
                with self.subTest(bad=bad, location=location), self.assertRaises(guard.Refusal):
                    guard.car_surface_recovery_evidence(runtime, {}, "car",
                        {"car_surface_recovery": bad} if location == "config" else {},
                        {"uav_tracking_detection": {"ros__parameters":
                            {"car_surface_recovery_enabled": bad} if location == "yaml" else {}}}, [])
        for command in ([v4.CAR_SURFACE_RECOVERY_FLAG], [v4.CAR_SURFACE_RECOVERY_FLAG + "=false"]):
            with self.subTest(command=command), self.assertRaises(guard.Refusal):
                guard.car_surface_recovery_evidence(runtime, {}, "car", {}, {}, command)

    def test_explicit_declaration_requires_the_shared_frozen_validator_even_when_off(self):
        runtime = SimpleNamespace(v4=SimpleNamespace())
        for enabled in (False, True):
            resource = policy_plan(enabled=enabled)["protocol"]["resources"]["car"]
            with self.subTest(enabled=enabled), self.assertRaisesRegex(guard.Refusal, "shared validator"):
                guard.car_surface_recovery_evidence(runtime, resource, "car", {}, {}, [])

    def test_four_safety_slots_accept_consistent_person_off_and_car_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, context, runtime, summary, facts, calls = safety.safety_fixture(Path(tmp))
            bind_recovery_safety(context, runtime, summary, facts)
            safety.SafetyTests.refresh(manifest, summary, facts)
            guard.validate_safety(manifest, context, runtime)
            self.assertEqual(len(calls), 4)
            self.assertEqual({(s["target_class"], s["case"]) for s in facts["slots"]},
                             {(cls, case) for cls in guard.CLASSES for case in guard.SAFETY_CASES})

    def test_every_safety_slot_refuses_semantic_archive_or_prospective_cli_substitution(self):
        for index in range(4):
            for defect in ("strict_config_bool", "missing_yaml_parameter", "cli_equals_bypass"):
                with self.subTest(index=index, defect=defect), tempfile.TemporaryDirectory() as tmp:
                    manifest, context, runtime, summary, facts, _ = safety.safety_fixture(Path(tmp))
                    bind_recovery_safety(context, runtime, summary, facts)
                    slot = facts["slots"][index]
                    if defect == "strict_config_bool":
                        binding = slot["evidence"]["run_config"]
                        config = guard.load(binding["path"])
                        config["car_surface_recovery"] = int(config["car_surface_recovery"])
                        slot["evidence"]["run_config"] = safety.write(Path(binding["path"]), config)
                    elif defect == "missing_yaml_parameter":
                        path = Path(slot["evidence"]["runtime_parameters"]["path"])
                        parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
                        parameters["uav_tracking_detection"]["ros__parameters"].pop("surface_max_roi_pixels")
                        path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
                        slot["evidence"]["runtime_parameters"] = guard.file_binding(path)
                    else:
                        # Rebind BOTH prospective and actual argv: hashes and
                        # registry equality cannot replace policy validation.
                        command = slot["executions"]["flight"]["argv"]
                        if v4.CAR_SURFACE_RECOVERY_FLAG in command:
                            command.remove(v4.CAR_SURFACE_RECOVERY_FLAG)
                        command.append(v4.CAR_SURFACE_RECOVERY_FLAG + "=false")
                        registry = guard.load(facts["registry"]["path"])
                        next(row for row in registry["trials"] if row["id"] == slot["id"])["flight_argv"] = list(command)
                        facts["registry"] = safety.write(Path(facts["registry"]["path"]), registry)
                    safety.SafetyTests.refresh(manifest, summary, facts)
                    with self.assertRaisesRegex(guard.Refusal, "Safety car surface recovery"):
                        guard.validate_safety(manifest, context, runtime)


class SimulationPacingProbeGateTests(unittest.TestCase):
    def test_legacy_binding_shape_stays_unchanged_and_declared_pacing_is_bound(self):
        legacy = builder.bindings(pacing_plan())
        declared = builder.bindings(pacing_plan(declared=True))
        self.assertNotIn("simulation_pacing_sha256", legacy)
        self.assertEqual(declared.pop("simulation_pacing_sha256"),
                         v4.digest(v4.simulation_pacing_summary(pacing_plan(declared=True)["protocol"])))
        self.assertEqual(declared, legacy)

    def test_core_and_extension_reject_both_same_source_pacing_mismatch_directions(self):
        for extension in (False, True):
            for target_new in (False, True):
                with self.subTest(extension=extension, target_new=target_new), tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary)/"immutable_pacing_probe.json"
                    path.write_text('{"scope":"INERT_PACING_POLICY_FIXTURE"}', encoding="utf-8")
                    original = path.read_bytes()
                    target, previous = pacing_plan(declared=target_new), pacing_plan(declared=not target_new)
                    self.assertEqual(target["source_hashes"], previous["source_hashes"])
                    with patch.object(builder, "read_plan", return_value=(path, previous)), \
                            patch.object(v4, "read_slots", side_effect=AssertionError("Mismatch must precede slot reads")), \
                            self.assertRaisesRegex(ValueError, "simulation pacing policy"):
                        builder.assemble(target, [path], extension=extension,
                            registration_utc=v4.utc_now() if extension else None)
                    self.assertEqual(path.read_bytes(), original)

    def test_gimbal_registration_also_refuses_different_registered_pacing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"probe.json"
            output = Path(temporary)/"must_not_publish.json"
            target, previous = pacing_plan(declared=True), pacing_plan()
            with patch.object(builder, "target_snapshot", return_value=(path, target, {})), \
                    patch.object(builder, "read_plan", return_value=(path, previous)), \
                    self.assertRaisesRegex(ValueError, "simulation pacing policy"):
                builder.register_gimbal_reevaluations(path, path, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
