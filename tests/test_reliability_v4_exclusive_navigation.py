"""Prospective E-only measurement policy cannot borrow legacy admission."""
from copy import deepcopy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import yaml

from tests import test_reliability_v4_runner as runner
from tests import test_reliability_v4_probe_gate as probes
from tests import test_reliability_v4_guard as safety

v4, builder, guard = runner.v4, probes.builder, safety.guard


def archives(enabled):
    return ({"exclusive_navigation_reference": enabled},
            {name: {"ros__parameters": {"navigation_exclusive_enabled": enabled}}
             for name in ("uav_tracking_detection", "uav_tracking_state_estimator")})


def bind_safety_policy(context, runtime, facts):
    runtime.v4.exclusive_navigation_runtime_evidence = v4.exclusive_navigation_runtime_evidence
    registry = guard.load(facts["registry"]["path"])
    for cls, resource in context.core["protocol"]["resources"].items():
        resource[v4.EXCLUSIVE_NAVIGATION_FIELD] = cls == "car"
    context.gate_bindings["exclusive_navigation_sha256"] = v4.digest(v4.exclusive_navigation_summary(context.core["protocol"]))
    for slot in facts["slots"]:
        enabled = slot["target_class"] == "car"
        config_path = Path(slot["evidence"]["run_config"]["path"])
        config = guard.load(config_path)
        config["exclusive_navigation_reference"] = enabled
        slot["evidence"]["run_config"] = safety.write(config_path, config)
        parameter_path = Path(slot["evidence"]["runtime_parameters"]["path"])
        parameters = yaml.safe_load(parameter_path.read_text(encoding="utf-8"))
        for name in ("uav_tracking_detection", "uav_tracking_state_estimator"):
            parameters[name]["ros__parameters"]["navigation_exclusive_enabled"] = enabled
        parameter_path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
        slot["evidence"]["runtime_parameters"] = guard.file_binding(parameter_path)
        if enabled:
            slot["executions"]["flight"]["argv"].append(v4.EXCLUSIVE_NAVIGATION_FLAG)
        next(row for row in registry["trials"] if row["id"] == slot["id"])["flight_argv"] = list(slot["executions"]["flight"]["argv"])
    facts["registry"] = safety.write(Path(facts["registry"]["path"]), registry)


class ExclusiveNavigationRegistrationTests(unittest.TestCase):
    def test_policy_bool_is_strict_and_person_cannot_enable(self):
        self.assertFalse(v4.exclusive_navigation_setting({}, "car"))
        for enabled in (False, True):
            self.assertIs(v4.exclusive_navigation_setting({v4.EXCLUSIVE_NAVIGATION_FIELD: enabled}, "car"), enabled)
        for cls, value in [("person", True)]+[("car", x) for x in (0, 1, "false", None)]:
            with self.subTest(cls=cls, value=value), self.assertRaises(ValueError):
                v4.exclusive_navigation_setting({v4.EXCLUSIVE_NAVIGATION_FIELD: value}, cls)

    def test_generated_plan_binds_each_class_and_exact_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.fixture(root)
            protocol = v4.load(root/v4.PROTOCOL_PATH)
            for cls in v4.CLASSES:
                protocol["resources"][cls][v4.EXCLUSIVE_NAVIGATION_FIELD] = cls == "car"
            runner.write(root/v4.PROTOCOL_PATH, protocol)
            plan = runner.plan(root, classes=["person", "car"], groups=["stage2_crossing"], seeds=[4], persist=False)
            v4.validate_plan(plan)
            for trial in plan["trials"]:
                enabled = trial["target_class"] == "car"
                self.assertEqual(v4.exclusive_navigation_trial_binding(plan, trial), (enabled, True))
                self.assertEqual(trial["flight_command"].count(v4.EXCLUSIVE_NAVIGATION_FLAG), int(enabled))
                for defect in ("missing_spec", "int_spec", "duplicate_flag", "equals_flag"):
                    bad = deepcopy(trial)
                    if defect == "missing_spec": bad.pop(v4.EXCLUSIVE_NAVIGATION_FIELD)
                    elif defect == "int_spec": bad[v4.EXCLUSIVE_NAVIGATION_FIELD] = int(enabled)
                    else: bad["flight_command"].append(v4.EXCLUSIVE_NAVIGATION_FLAG + ("=true" if defect == "equals_flag" else ""))
                    with self.subTest(cls=trial["target_class"], defect=defect), self.assertRaises(ValueError):
                        v4.exclusive_navigation_trial_binding(plan, bad)

    def test_both_runtime_nodes_and_config_are_bound_without_legacy_default_injection(self):
        for enabled in (False, True):
            resource = {v4.EXCLUSIVE_NAVIGATION_FIELD: enabled}
            config, params = archives(enabled)
            argv = [v4.EXCLUSIVE_NAVIGATION_FLAG] if enabled else []
            self.assertEqual(v4.exclusive_navigation_runtime_evidence(resource, "car", config, params, argv)["errors"], [])
            for location in ("config", "uav_tracking_detection", "uav_tracking_state_estimator"):
                for bad_value in (None, 0, 1, "true", not enabled):
                    c, p = deepcopy(config), deepcopy(params)
                    values, key = ((c, "exclusive_navigation_reference") if location == "config" else
                                   (p[location]["ros__parameters"], "navigation_exclusive_enabled"))
                    if bad_value is None: values.pop(key)
                    else: values[key] = bad_value
                    with self.subTest(enabled=enabled, location=location, bad=bad_value):
                        self.assertTrue(v4.exclusive_navigation_runtime_evidence(resource, "car", c, p, argv)["errors"])
        self.assertEqual(v4.exclusive_navigation_runtime_evidence({}, "car", {}, {}, [])["errors"], [])
        c, p = archives(True)
        self.assertTrue(v4.exclusive_navigation_runtime_evidence({}, "car", c, p, [])["errors"])

    def test_probe_admission_distinguishes_old_and_new_measurement_domains(self):
        base = {"protocol": {"resources": {cls: {} for cls in v4.CLASSES}}}
        on = deepcopy(base)
        on["protocol"]["resources"]["car"][v4.EXCLUSIVE_NAVIGATION_FIELD] = True
        with self.assertRaisesRegex(ValueError, "exclusive navigation"):
            builder.matching_recovery_policy(on, base)
        off = deepcopy(base)
        off["protocol"]["resources"]["car"][v4.EXCLUSIVE_NAVIGATION_FIELD] = False
        builder.matching_recovery_policy(base, off)

    def test_old_safety_validator_cannot_admit_explicit_new_declaration(self):
        runtime = SimpleNamespace(v4=SimpleNamespace())
        self.assertFalse(guard.exclusive_navigation_evidence(runtime, {}, "car", {}, {}, []))
        for enabled in (False, True):
            config, params = archives(enabled)
            with self.assertRaisesRegex(guard.Refusal, "shared validator"):
                guard.exclusive_navigation_evidence(runtime, {v4.EXCLUSIVE_NAVIGATION_FIELD: enabled},
                    "car", config, params, [v4.EXCLUSIVE_NAVIGATION_FLAG] if enabled else [])

    def test_shared_safety_validator_binds_actual_archives_and_cli(self):
        runtime = SimpleNamespace(v4=SimpleNamespace(exclusive_navigation_runtime_evidence=v4.exclusive_navigation_runtime_evidence))
        for enabled in (False, True):
            resource = {v4.EXCLUSIVE_NAVIGATION_FIELD: enabled}
            config, params = archives(enabled)
            argv = [v4.EXCLUSIVE_NAVIGATION_FLAG] if enabled else []
            self.assertIs(guard.exclusive_navigation_evidence(runtime, resource, "car", config, params, argv), enabled)
            params["uav_tracking_detection"]["ros__parameters"]["navigation_exclusive_enabled"] = not enabled
            with self.assertRaises(guard.Refusal):
                guard.exclusive_navigation_evidence(runtime, resource, "car", config, params, argv)

    def test_four_original_safety_slots_require_same_registered_measurement_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, context, runtime, summary, facts, calls = safety.safety_fixture(Path(tmp))
            bind_safety_policy(context, runtime, facts)
            safety.SafetyTests.refresh(manifest, summary, facts)
            guard.validate_safety(manifest, context, runtime)
            self.assertEqual(len(calls), 4)
            car_slot = next(slot for slot in facts["slots"] if slot["target_class"] == "car")
            path = Path(car_slot["evidence"]["runtime_parameters"]["path"])
            params = yaml.safe_load(path.read_text(encoding="utf-8"))
            params["uav_tracking_state_estimator"]["ros__parameters"]["navigation_exclusive_enabled"] = False
            path.write_text(yaml.safe_dump(params), encoding="utf-8")
            car_slot["evidence"]["runtime_parameters"] = guard.file_binding(path)
            safety.SafetyTests.refresh(manifest, summary, facts)
            with self.assertRaisesRegex(guard.Refusal, "exclusive navigation"):
                guard.validate_safety(manifest, context, runtime)


if __name__ == "__main__":
    unittest.main()
