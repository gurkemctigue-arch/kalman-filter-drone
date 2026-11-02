"""Split-mode plan/runtime/gate fixtures; no actual flight or bag access."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts import build_reliability_v4_probe_gate as builder
from tests import test_reliability_v4_runner as fixtures


v4 = fixtures.v4
FIELD = v4.SPLIT_CLOCK_BRIDGE_FIELD
ON, OFF = "--split-clock-bridge", "--no-split-clock-bridge"
MISSING = object()


class SplitBridgePlanningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="split_bridge_planning_fixture_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        fixtures.fixture(self.root, gates=True)

    def make(self, *, suffix="split", groups=None, classes=None):
        return fixtures.plan(self.root, groups=groups, classes=classes, seeds=[4],
                             suffix=suffix, persist=False)

    @staticmethod
    def rehash(plan):
        plan["plan_sha256"] = v4.digest(plan, ("plan_sha256",))
        return plan

    def mode(self, plan, value):
        changed = deepcopy(plan)
        if value is MISSING:
            changed.pop(FIELD, None)
        else:
            changed[FIELD] = value
        for trial in changed["trials"]:
            trial["flight_command"] = [argument for argument in trial["flight_command"]
                                       if argument not in {ON, OFF}]
            if value is MISSING:
                trial.pop(FIELD, None)
            else:
                trial[FIELD] = value
                trial["flight_command"].append(ON if value else OFF)
        return self.rehash(changed)

    def materialize_runtime(self, plan):
        trial = plan["trials"][0]
        fake = fixtures.FakeCommands()
        fake(trial["flight_command"], self.root / "fixture_flight.log", self.root, plan["trial_timeout_s"])
        self.assertEqual(fake.calls, [trial["flight_command"]])
        self.assertEqual(v4.runtime_configuration(plan, trial)["errors"], [])
        return trial, Path(trial["directory"]) / "run_config.json"

    def gate_target(self):
        path = fixtures.fixture_probe_gate(self.root)
        target = self.make(suffix="gate_target")
        target["development_probe_gate"] = {
            "path": str(path), "sha256": v4.sha(path), "evidence": v4.load(path),
        }
        self.rehash(target)
        return target, path

    def test_new_plans_explicitly_enable_split_mode_for_every_core_group_and_class(self):
        frozen = self.make(groups=list(v4.GROUPS), classes=list(v4.CLASSES))
        self.assertIs(frozen[FIELD], True)
        self.assertEqual(len(frozen["trials"]), 12)
        for trial in frozen["trials"]:
            self.assertIs(trial[FIELD], True)
            self.assertEqual(trial["flight_command"].count(ON), 1)
            self.assertNotIn(OFF, trial["flight_command"])
            self.assertEqual(v4.split_clock_bridge_trial_binding(frozen, trial), (True, True))
        v4.validate_plan(frozen)

    def test_plan_setting_accepts_only_bools_and_absent_legacy_defaults_false(self):
        self.assertIs(v4.split_clock_bridge_setting({}), False)
        for value in (True, False):
            self.assertIs(v4.split_clock_bridge_setting({FIELD: value}), value)
        for value in (0, 1, "true", "false", None, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                v4.split_clock_bridge_setting({FIELD: value})

    def test_legacy_plan_validation_preserves_absent_flags_and_original_commands(self):
        legacy = self.mode(self.make(), MISSING)
        before = deepcopy(legacy)
        v4.validate_plan(legacy)
        self.assertEqual(legacy, before)
        self.assertNotIn(FIELD, legacy)
        for trial in legacy["trials"]:
            self.assertNotIn(FIELD, trial)
            self.assertNotIn(ON, trial["flight_command"])
            self.assertNotIn(OFF, trial["flight_command"])
            self.assertEqual(v4.split_clock_bridge_trial_binding(legacy, trial), (False, False))

    def test_explicit_false_requires_the_negative_flag_and_boolean_trial_binding(self):
        frozen = self.mode(self.make(), False)
        v4.validate_plan(frozen)
        for trial in frozen["trials"]:
            self.assertIs(trial[FIELD], False)
            self.assertEqual(trial["flight_command"].count(OFF), 1)
            self.assertNotIn(ON, trial["flight_command"])
            self.assertEqual(v4.split_clock_bridge_trial_binding(frozen, trial), (False, True))

    def test_trial_flag_omission_duplication_and_opposite_flag_are_rejected(self):
        for enabled in (True, False):
            frozen = self.mode(self.make(), enabled)
            original = frozen["trials"][0]
            flag, opposite = (ON, OFF) if enabled else (OFF, ON)
            for defect in ("missing", "duplicate", "both", "opposite"):
                with self.subTest(enabled=enabled, defect=defect):
                    trial = deepcopy(original)
                    if defect == "missing":
                        trial["flight_command"].remove(flag)
                    elif defect == "duplicate":
                        trial["flight_command"].append(flag)
                    elif defect == "both":
                        trial["flight_command"].append(opposite)
                    else:
                        trial["flight_command"][trial["flight_command"].index(flag)] = opposite
                    with self.assertRaises(ValueError):
                        v4.split_clock_bridge_trial_binding(frozen, trial)

    def test_explicit_trial_field_cannot_be_missing_nonboolean_or_opposite(self):
        for enabled in (True, False):
            frozen = self.mode(self.make(), enabled)
            for value in (MISSING, not enabled, int(enabled), "true", None):
                with self.subTest(enabled=enabled, value=value):
                    trial = deepcopy(frozen["trials"][0])
                    if value is MISSING:
                        trial.pop(FIELD)
                    else:
                        trial[FIELD] = value
                    with self.assertRaises(ValueError):
                        v4.split_clock_bridge_trial_binding(frozen, trial)

    def test_legacy_trial_cannot_silently_gain_any_explicit_field_or_flag(self):
        legacy = self.mode(self.make(), MISSING)
        for field, flag in ((True, None), (False, None), (0, None), (MISSING, ON), (MISSING, OFF)):
            with self.subTest(field=field, flag=flag):
                trial = deepcopy(legacy["trials"][0])
                if field is not MISSING:
                    trial[FIELD] = field
                if flag:
                    trial["flight_command"].append(flag)
                with self.assertRaises(ValueError):
                    v4.split_clock_bridge_trial_binding(legacy, trial)

    def test_rehashing_a_partially_changed_plan_does_not_authorize_mode_drift(self):
        original = self.make()
        for defect in ("top_only", "trial_only", "command_only", "legacy_top_only"):
            with self.subTest(defect=defect):
                changed = deepcopy(original)
                if defect == "top_only":
                    changed[FIELD] = False
                elif defect == "trial_only":
                    changed["trials"][0][FIELD] = False
                elif defect == "command_only":
                    command = changed["trials"][0]["flight_command"]
                    command[command.index(ON)] = OFF
                else:
                    changed.pop(FIELD)
                self.rehash(changed)
                with self.assertRaises(ValueError):
                    v4.validate_plan(changed)

    def test_split_runtime_config_requires_explicit_true_and_rejects_bool_aliases(self):
        frozen = self.make()
        trial, path = self.materialize_runtime(frozen)
        original = v4.load(path)
        for value in (MISSING, False, 0, 1, "true", "false", None):
            with self.subTest(value=value):
                config = deepcopy(original)
                if value is MISSING:
                    config.pop(FIELD)
                else:
                    config[FIELD] = value
                fixtures.write(path, config)
                self.assertIn("run_config:split_clock_bridge", v4.runtime_configuration(frozen, trial)["errors"])

    def test_explicit_false_runtime_requires_present_false(self):
        frozen = self.mode(self.make(), False)
        trial, path = self.materialize_runtime(frozen)
        original = v4.load(path)
        self.assertIs(original[FIELD], False)
        for value in (MISSING, True, 0, 1, "false", None):
            with self.subTest(value=value):
                config = deepcopy(original)
                if value is MISSING:
                    config.pop(FIELD)
                else:
                    config[FIELD] = value
                fixtures.write(path, config)
                self.assertIn("run_config:split_clock_bridge", v4.runtime_configuration(frozen, trial)["errors"])

    def test_legacy_runtime_accepts_missing_or_false_but_rejects_true_and_integers(self):
        legacy = self.mode(self.make(), MISSING)
        trial, path = self.materialize_runtime(legacy)
        original = v4.load(path)
        for value in (MISSING, False, True, 0, 1, "false", None):
            with self.subTest(value=value):
                config = deepcopy(original)
                if value is MISSING:
                    config.pop(FIELD)
                else:
                    config[FIELD] = value
                fixtures.write(path, config)
                errors = v4.runtime_configuration(legacy, trial)["errors"]
                if value is MISSING or value is False:
                    self.assertEqual(errors, [])
                else:
                    self.assertIn("run_config:split_clock_bridge", errors)

    def test_builder_bindings_include_explicit_mode_and_preserve_legacy_absence(self):
        frozen = self.make()
        for value in (True, False, MISSING):
            with self.subTest(value=value):
                binding = builder.bindings(self.mode(frozen, value))
                if value is MISSING:
                    self.assertNotIn(FIELD, binding)
                else:
                    self.assertIs(binding[FIELD], value)

    def test_probe_matching_rejects_different_effective_bridge_process_modes(self):
        frozen = self.make()
        on, off, legacy = (self.mode(frozen, value) for value in (True, False, MISSING))
        builder.matching_pacing_policy(on, deepcopy(on))
        builder.matching_pacing_policy(off, legacy)
        for target, previous in ((on, off), (off, on), (on, legacy), (legacy, on)):
            with self.subTest(target=target.get(FIELD, "legacy"), previous=previous.get(FIELD, "legacy")):
                with self.assertRaisesRegex(ValueError, "clock bridge process mode"):
                    builder.matching_pacing_policy(target, previous)

    def test_real_probe_gate_accepts_matching_split_evidence_but_rejects_mode_change(self):
        # Every command here is FakeCommands; this exercises only immutable
        # fixture reports and gate provenance, never ROS or a real flight.
        target, _path = self.gate_target()
        v4.validate_probe_gate(target)
        different = self.mode(target, False)
        with self.assertRaisesRegex(ValueError, "binding differs"):
            v4.validate_probe_gate(different)

    def test_rebound_gate_file_cannot_omit_forge_or_integer_alias_the_mode(self):
        target, path = self.gate_target()
        original = v4.load(path)
        for value in (MISSING, False, 1, "true"):
            with self.subTest(value=value):
                evidence = deepcopy(original)
                if value is MISSING:
                    evidence["bindings"].pop(FIELD)
                else:
                    evidence["bindings"][FIELD] = value
                fixtures.write(path, evidence)
                changed = deepcopy(target)
                changed["development_probe_gate"] = {
                    "path": str(path), "sha256": v4.sha(path), "evidence": evidence,
                }
                self.rehash(changed)
                with self.assertRaises(ValueError):
                    v4.validate_probe_gate(changed)


if __name__ == "__main__":
    unittest.main()
