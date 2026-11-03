"""Small Windows contracts; no WSL, bag, model or real child is invoked."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("direct_measurement_contracts", HERE / "run_closed_measurement.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class PreparationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = s.fixed_module(s.OLD08, s.OLD08_SHA)

    def test_disabled_entry_refuses_before_any_read_or_subprocess(self):
        with patch.object(s, "PRODUCTION_ENABLED", False), patch.object(s, "REGISTERED_INPUTS", {}), \
             patch.object(s, "fixed_module", side_effect=AssertionError("No input read")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--continue-after28"]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
            with self.assertRaisesRegex(ValueError, "Production disabled"):
                s.run()

    def test_reused_original_functions_keep_exact_six_steps_and_recordings(self):
        p = s.new_paths(self.old)
        steps = self.old.workflow_commands(p)
        self.assertEqual([name for name, _ in steps], ["measure_actual28", "physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget"])
        self.assertEqual(self.old.COMMIT, "eedd8d9abcd6890b0bd5d0155f76ac08253426b9")
        self.assertEqual(self.old.ASSUMPTIONS_SHA, "bc0ef3a6549bb7421b1b6de64c17951c4d71af32114c94a8e4234ad42360b049")
        for target in ("person", "car"):
            argv = dict(steps)[target + "_velocity_export"]
            self.assertIn(str(p["frozen"] / ("results/reliability_v4_humble54_core12_probe01_" + target + "_stage1_velocity_seed004")), argv)
        for name in ("receipt", "tools", "sizes", "calibration", "budget"):
            self.assertIn("after07_01", str(p[name]))
        self.assertEqual(s.INPUT_NAMES, {"collector", "profile", "terminal", "events", "admission", "monitor_state", "launcher_terminal"})

    def test_original_positive_budget_preserves_unknown_negative_and_full280(self):
        old = self.old
        bindings = {label: {"path": "/fixture/" + label, "sha256": label[0] * 64} for label in ("core", "extension")}
        storage = {"cells": [{"matrix": matrix, "target_class": target, "condition": condition}
                    for matrix, groups in (("core", old.CORE_GROUPS), ("extension", old.EXTENSION_GROUPS))
                    for target in ("person", "car") for condition in groups]}
        budget = {"kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION", "admission_performed": False,
                  "storage": storage, "storage_sha256": old.sha(json.dumps(storage, sort_keys=True, separators=(",", ":")).encode()),
                  "provenance": {"development_plans": bindings, "assumptions": {"sha256": old.ASSUMPTIONS_SHA}},
                  "capacity_preview": {"scheduled_slots": 280, "fits_declared_logical_budget": True,
                                       "volumes": {"drive_D": {"fits_declared_physical_budget": True}}}}
        old.positive_budget(budget, bindings["core"], bindings["extension"])
        for value in (None, False, 1):
            changed = deepcopy(budget)
            changed["capacity_preview"]["volumes"]["drive_D"]["fits_declared_physical_budget"] = value
            before = deepcopy(changed)
            with self.assertRaisesRegex(ValueError, "Unknown or negative"):
                old.positive_budget(changed, bindings["core"], bindings["extension"])
            self.assertEqual(changed, before)
        changed = deepcopy(budget)
        changed["capacity_preview"]["scheduled_slots"] = 279
        with self.assertRaisesRegex(ValueError, "Unknown or negative"):
            old.positive_budget(changed, bindings["core"], bindings["extension"])

    def fixture(self):
        base = datetime(2020, 1, 1, tzinfo=timezone.utc)
        stamp = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()
        ids = ["fixture_" + str(index) for index in range(16)]
        rows = [{"slot_id": name, "original_status": "FAIL" if index == 10 else "PASS",
                 "terminal_sha256": str(index) * 64, "original_terminal": {"path": "/fixture/" + name + ".json", "sha256": str(index) * 64},
                 "original_marker": {"path": "/fixture/" + name + ".started.json", "sha256": "b" * 64},
                 "original_started_utc": stamp(-20), "original_finished_utc": stamp(-10)} for index, name in enumerate(ids)]
        events = [{"event": "COLLECTION_STARTED", "pending_ids": ids[11:], "utc": stamp(0)}]
        for row in rows[:11]:
            for kind in ("START_SLOT", "COMPLETE_SLOT"):
                events.append({"event": kind, "slot": row["slot_id"], "utc": stamp(len(events)),
                               "executed_by_this_owner": False, "event_semantics": "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX",
                               "status": row["original_status"], **{key: row[key] for key in ("original_terminal", "original_marker", "original_started_utc", "original_finished_utc")}})
        for index, row in enumerate(rows[11:]):
            second = len(events)
            row.update(original_started_utc=stamp(second + .1), original_finished_utc=stamp(second + .2))
            events.extend([
                {"event": "START_SLOT", "slot": row["slot_id"], "utc": stamp(second), "executed_by_this_owner": True,
                 "event_semantics": "ACTUAL_CHILD_INVOCATION", "command": ["bash", "/fixture/entry.sh", row["slot_id"]], "pid": 100 + index},
                {"event": "CHILD_EXIT", "slot": row["slot_id"], "utc": stamp(second + 1), "returncode": 0},
                {"event": "COMPLETE_SLOT", "slot": row["slot_id"], "utc": stamp(second + 2), "executed_by_this_owner": True,
                 "event_semantics": "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED", "terminal_sha256": row["terminal_sha256"], "status": row["original_status"]}])
        terminal = {"started_utc": stamp(-1), "finished_utc": stamp(37.5), "owner_identity": {"boot_id": "fixture_boot"},
                    "current_child": {"command": events[-3]["command"], "pid": 104, "identity": {"pid": 104, "boot_id": "fixture_boot"},
                                      "returncode": 0, "finished_utc": stamp(35.9)}}
        events.append({"event": "COLLECTION_FINISHED", "collected_slots": 5, "utc": stamp(38)})
        return events, rows, {"trials": [{"id": name} for name in ids]}, "/fixture/entry.sh", terminal, datetime.fromisoformat

    def test_exact_observed11_actual5_events_are_accepted_without_mutation(self):
        arguments = self.fixture()
        before = deepcopy(arguments[:-1])
        s.verify_events(*arguments)
        self.assertEqual(arguments[:-1], before)

    def test_prefix_observations_cannot_become_executed_slots(self):
        arguments = self.fixture()
        arguments[0][1]["executed_by_this_owner"] = True
        with self.assertRaisesRegex(ValueError, "derived observations"):
            s.verify_events(*arguments)

    def test_actual_nonzero_or_invented_completion_stops(self):
        for mutate in (lambda a: a[0][24].update(returncode=2),
                       lambda a: a[0][-1].update(collected_slots=16),
                       lambda a: a[0][23].update(command=["bash", "/fixture/other.sh", "fixture_11"]),
                       lambda a: a[4]["current_child"].update(returncode=2)):
            arguments = self.fixture()
            mutate(arguments)
            with self.assertRaises(ValueError):
                s.verify_events(*arguments)

    def test_missing_or_nonmonotonic_event_stream_stops(self):
        arguments = self.fixture()
        arguments[0].pop(2)
        with self.assertRaisesRegex(ValueError, "Exact eleven"):
            s.verify_events(*arguments)
        arguments = self.fixture()
        arguments[0][2]["utc"] = arguments[0][0]["utc"]
        with self.assertRaisesRegex(ValueError, "UTC order"):
            s.verify_events(*arguments)


if __name__ == "__main__":
    unittest.main(verbosity=2)
