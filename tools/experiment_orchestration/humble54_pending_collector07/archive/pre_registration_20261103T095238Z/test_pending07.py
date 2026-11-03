"""Windows stdlib-only safety fixtures. No WSL, ROS, bags, or real launches."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


c = module_at("pending07_under_test", HERE / "collect_humble54_pending07.py")
old_tests = module_at("pending06_fixture_only", HERE.parent / "humble54_pending_collector06_source/test_collect_humble54_pending06.py")


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


class ConditionalRuleTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "tools/diagnostics/humble54_probe02_car_dropout_null_review01"
        self.surface = json.loads((base / "flight_evaluation.original.json").read_bytes())
        self.record = json.loads((base / "terminal.original.json").read_bytes())

    def qualify(self, surface=None, record=None):
        return c.behavior_qualification(surface or self.surface, record or self.record,
                                        "car_extension_dropout_seed004", "f" * 64, c.HISTORY)

    def test_actual_failed_trial_retains_null_and_behavior_failure_without_identity_claim(self):
        before = deepcopy((self.surface, self.record))
        result = self.qualify()
        self.assertIn("surface:short:no_loss_during_short_occlusion=FAIL", result["known_algorithm_failures"])
        conditional = result["conditional_nonobservations"]
        self.assertEqual(len(conditional), 1)
        self.assertEqual(conditional[0]["classification"], c.CONDITIONAL_IDENTITY)
        self.assertIsNone(conditional[0]["value"])
        self.assertEqual(conditional[0]["identity_result"], "UNOBSERVED")
        self.assertEqual(conditional[0]["identity_switch_observed_or_excluded"], "NEITHER")
        self.assertEqual((self.surface, self.record), before)

    def test_conditional_rule_rejects_missing_prerequisites_and_inconsistent_clocks(self):
        mutations = [
            lambda s, r: s["occlusions"][0]["checks"].update(no_loss_during_short_occlusion=True),
            lambda s, r: s["occlusions"][0]["checks"].update(no_loss_during_short_occlusion=None),
            lambda s, r: s["occlusions"][0].update(first_measured_after_open_s=32.0),
            lambda s, r: s["occlusions"][0].update(recovery_after_open_s=0.8),
            lambda s, r: s["occlusions"][0].update(post_open_measured_missing_receive_time_count=1),
            lambda s, r: s["occlusions"][0].update(post_open_measured_missing_receive_time_count=False),
            lambda s, r: s["occlusions"][0].pop("post_open_measured_missing_receive_time_count"),
            lambda s, r: s["occlusions"][0].pop("first_measured_after_open_s"),
            lambda s, r: s["occlusions"][0]["checks"].pop("identity_preserved_on_observed_recovery"),
            lambda s, r: s["occlusions"][0].update(first_lost_s=None),
            lambda s, r: s["occlusions"][0].update(first_lost_s=True),
            lambda s, r: s["occlusions"][0].update(first_lost_s=float("nan")),
            lambda s, r: s["occlusions"][0].update(first_lost_s=float("inf")),
            lambda s, r: s["occlusions"][0].update(first_lost_s=90.0),
            lambda s, r: s["occlusions"][0].update(first_lost_s=0.0),
            lambda s, r: s["occlusions"][0].update(duration_s=2.0),
            lambda s, r: s["occlusions"][0].update(result="PASS"),
            lambda s, r: s["occlusions"][0].update(complete=False),
            lambda s, r: s["acceptance"].update(result="INCOMPLETE_EVIDENCE"),
            lambda s, r: r.update(status="PASS", engineering_result="PASS"),
            lambda s, r: r.update(status="INCOMPLETE_EVIDENCE", engineering_result="INCOMPLETE_EVIDENCE"),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(case=index):
                surface, record = deepcopy(self.surface), deepcopy(self.record)
                mutation(surface, record)
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    self.qualify(surface, record)

    def test_every_other_required_unknown_and_long_safety_failure_still_stops(self):
        for kind, fields in (("short", ("detector_interruption_observed", "prediction_observed")),
                             ("long", (*c.LONG_ALGORITHM, *c.LONG_SAFE, *c.SHUTTER))):
            for key in fields:
                with self.subTest(kind=kind, field=key):
                    surface = deepcopy(self.surface)
                    next(row for row in surface["occlusions"] if row["kind"] == kind)["checks"][key] = None
                    with self.assertRaises(ValueError):
                        self.qualify(surface)
        surface = deepcopy(self.surface)
        surface["occlusions"][1]["checks"]["hover_observed_for_long_occlusion"] = False
        with self.assertRaises(ValueError):
            self.qualify(surface)

    def test_decoder_clock_or_missing_topic_defects_do_not_use_conditional_rule(self):
        for update in ({"missing_topics": ["/tracking/state"]}, {"input_read_error_count": 1}, {"clock_timebase_available": False}):
            with self.subTest(update=update):
                surface = deepcopy(self.surface)
                surface["acceptance"].update(update)
                with self.assertRaises(ValueError):
                    self.qualify(surface)


class FakeChildTests(unittest.TestCase):
    def setUp(self):
        self.fixture = old_tests.CollectorTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def make_conditional_template(self, slot):
        root = self.fixture.root / "templates" / slot
        record_path, surface_path = root / "terminal.json", root / "trial/surface.json"
        record, surface = c.load(record_path), c.load(surface_path)
        surface["interval"] = {"end_s": 10.0}
        surface["configuration"] = {"max_prediction_s": 0.75, "recovery_window_s": 3.0}
        surface["acceptance"]["result"] = "FAIL"
        short = surface["occlusions"][0]
        short.update(start_s=2.0, end_s=2.2, duration_s=0.2, first_lost_s=2.5,
                     first_measured_after_open_s=None, recovery_after_open_s=None,
                     post_open_measured_missing_receive_time_count=0, result="FAIL")
        short["checks"].update(no_loss_during_short_occlusion=False, identity_preserved_on_observed_recovery=None)
        write(surface_path, surface)
        entry = next(row for row in record["evaluations"] if row["kind"] == "surface_flight")
        entry.update(result="FAIL", reported_verdict="FAIL", report_sha256=c.sha(surface_path))
        record["artifact_hashes"]["surface.json"] = c.sha(surface_path)
        record.update(status="FAIL", engineering_result="FAIL")
        _, record["engineering_evidence"] = self.fixture.module.engineering_verdict(
            self.fixture.plan, next(row for row in self.fixture.plan["trials"] if row["id"] == slot),
            record["commands"][0], record["evaluations"])
        record["record_sha256"] = c.digest(record, "record_sha256")
        write(record_path, record)

    def collect(self, modes=None):
        f = self.fixture
        modes = modes or {}
        return c.collect(f.plan_path, f.entry, "closed", f.root / "owner07_fake", f.pins, f.module,
                         command_factory=lambda trial: [sys.executable, "-B", str(f.fake), str(f.root), trial["id"], modes.get(trial["id"], "ok")],
                         poll_s=0.01)

    def test_real_fake_children_continue_after_conditional_fail_and_retain_original_null(self):
        self.make_conditional_template("next")
        self.make_conditional_template("last")
        state = self.collect()
        self.assertEqual(state["status"], "COLLECTION_FINISHED")
        self.assertEqual(state["returncode"], 0)
        self.assertEqual([row["slot_id"] for row in state["collected"]], ["next", "last"])
        self.assertTrue(all(row["original_status"] == "FAIL" for row in state["collected"]))
        for slot in ("next", "last"):
            surface = c.load(self.fixture.results / slot / "surface.json")
            self.assertIsNone(surface["occlusions"][0]["checks"]["identity_preserved_on_observed_recovery"])
        self.assertEqual((self.fixture.root / "calls.txt").read_text().splitlines(), ["next", "last"])

    def test_unrelated_future_unknown_stops_after_real_child_exit_without_starting_next(self):
        self.fixture.template(self.fixture.plan["trials"][1], unknown=True)
        state = self.collect()
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(state["current_child"]["returncode"], 0)
        self.assertTrue(state["metadata_fault_child_exit_observed"])
        self.assertEqual((self.fixture.root / "calls.txt").read_text().splitlines(), ["next"])

    def test_nonzero_child_still_stops_even_with_a_conditional_fail_terminal(self):
        self.make_conditional_template("next")
        state = self.collect({"next": "exit_after"})
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertEqual(state["current_child"]["returncode"], 7)
        self.assertEqual(state["collected"], [])
        self.assertEqual((self.fixture.root / "calls.txt").read_text().splitlines(), ["next"])


class ActualSmallStopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checked = c.validate_profile(HERE / "prepared_profile07.json")

    def test_actual_small_check_binds_prefix11_five_pending_and_preserves_nonzero(self):
        self.assertEqual(len(self.checked["closed_ids"]), 11)
        self.assertEqual(len(self.checked["pending_ids"]), 5)
        self.assertEqual(self.checked["original_stop_returncode"], 2)
        self.assertFalse(self.checked["native_originals_checked"])
        self.assertFalse(c.PRODUCTION_ENABLED)

    def test_mutated_zero_exit_invented_frontier_completion_or_started08_are_rejected(self):
        checked = self.checked
        profile, v = checked["profile"], checked["library"]
        docs, hashes = {}, {}
        for name, binding in profile["closure_files"].items():
            raw = v.local_small_read(binding["path"])
            docs[name] = [v.parse(line) for line in raw.splitlines() if line.strip()] if name == "events06" else v.parse(raw)
            hashes[name] = binding["sha256"]
        changes = [
            lambda d: d["native_terminal06"].update(returncode=0),
            lambda d: d["terminal07"]["handles"]["outer"].update(exit_code=0),
            lambda d: d["terminal09"].update(child={"invented_started08": True}),
            lambda d: d["events06"][-1].update(event="COMPLETE_SLOT"),
            lambda d: d["native_terminal06"].update(collected=d["native_terminal06"]["collected"][:-1]),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                changed = deepcopy(docs)
                change(changed)
                with self.assertRaises(ValueError):
                    c.validate_stopped06(v, profile, checked["plan"], changed, hashes, profile["closed_prefix"])

    def test_production_execute_is_refused_before_profile_or_output_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must_not_exist"
            result = subprocess.run([sys.executable, "-B", str(HERE / "collect_humble54_pending07.py"),
                                     "--profile", str(output / "missing.json"), "--output", str(output), "--execute"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Production is disabled", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
