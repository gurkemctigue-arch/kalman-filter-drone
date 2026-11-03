"""In-memory metadata-stop chains; no WSL, bags, or native commands."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "final55_offline_overlay_profile02_20261103"
with patch.object(sys, "path", [str(OLD), *sys.path]):
    spec = importlib.util.spec_from_file_location("original_chain_fixture_support", OLD / "test_owner_chain.py")
    original_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_tests)

spec = importlib.util.spec_from_file_location("metadata_stop_chain_tests", HERE / "validate_owner_chain.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
v = c.v
utc, NOW = original_tests.utc, original_tests.NOW


class MetadataFixture:
    def __init__(self):
        self.f = original_tests.ChainFixture().add_registered_completion()
        f, b = self.f, self.f.b
        self.profile, self.read = f.profile, f.a.read
        source = {"path": c.source_reference(OLD / "validate_owner_chain.py"), "sha256": c.ORIGINAL_CHAIN_SHA256}
        f.a.put(source["path"], (OLD / "validate_owner_chain.py").read_bytes())
        original_library = OLD / "validate_owner_closure.py"
        f.a.put(c.source_reference(original_library), original_library.read_bytes())
        new_library = HERE / "validate_owner_closure.py"
        f.a.put(c.source_reference(new_library), new_library.read_bytes())
        seg = self.profile["segments"][1]
        for target in (seg["source_files"], b.profile["source_files"]):
            target["chain_validator"] = source
        for target in (seg["description"], b.profile["description"], b.started):
            target["pins"]["chain_validator"] = source
        f.admission["chain_validator"] = {"path": v.mounted(source["path"]), "sha256": source["sha256"]}
        self.frontier = deepcopy(b.native["collected"][0])
        trial = f.plan["trials"][2]
        terminal = v.parse(self.read(self.frontier["original_terminal"]["path"]))
        surface = next(row for row in terminal["evaluations"] if row["kind"] == "surface_flight")
        report = v.parse(self.read(surface["report"]))
        report["occlusions"][0]["checks"]["detector_interruption_observed"] = None
        report["acceptance"]["result"] = "INCOMPLETE_EVIDENCE"
        surface["report_sha256"] = b.put(surface["report"], report)["sha256"]
        surface.update(result="INCOMPLETE_EVIDENCE", reported_verdict="INCOMPLETE_EVIDENCE")
        terminal["artifact_hashes"]["surface_flight.json"] = surface["report_sha256"]
        terminal["record_sha256"] = v.content_digest(terminal, "record_sha256")
        self.frontier.update(original_terminal=b.put(self.frontier["original_terminal"]["path"], terminal),
                             record_sha256=terminal["record_sha256"], unobserved_checks=["surface:short:detector_interruption_observed=HISTORICAL_UNKNOWN_RETAINED"])
        self.frontier["terminal_sha256"] = self.frontier["original_terminal"]["sha256"]
        b.native_end = 1174
        b.events = [*b.events[:7], {"event": "STOPPED_FAULT", "utc": utc(1175), "scope": "SUPERVISED_PENDING_COLLECTION",
                                  "slot": trial["id"], "error": c.METADATA_STOP_ERROR}]
        b.native.update(status="STOPPED_FAULT", current_slot=trial["id"], collected=[], returncode=2, finished_utc=utc(1174),
                        error=c.METADATA_STOP_ERROR, metadata_fault_child_exit_observed=True,
                        current_child={"pid": 2002, "identity": {"pid": 2002, "boot_id": b.boot, "start_ticks": 2002},
                                       "command": b.events[-3]["command"], "started_utc": utc(1130),
                                       "finished_utc": utc(1173), "returncode": 0})
        f.close_at(b, stopped=True)
        f.refresh_b()
        seg["disposition"] = "ROOT_REVIEWED_METADATA_STOP"
        self.short = b.put("C:/fixture/metadata_stop/short_input_review.json", {
            "status": "UPSTREAM_INPUT_INTERRUPTION_CORROBORATED", "slot_id": trial["id"], "errors": [],
            "known_algorithm_failures": [], "original_engineering_verdict_preserved": True,
            "original": {"terminal_status": "INCOMPLETE_EVIDENCE"},
            "input_bindings": {"terminal": self.frontier["original_terminal"],
                               "surface_flight.json": {"path": surface["report"], "sha256": surface["report_sha256"]}},
            "extraction_manifest": b.put("C:/fixture/metadata_stop/manifest.json", {"fixture": True}),
            "visual_review": b.put("C:/fixture/metadata_stop/visual.json", {"fixture": True})})
        self.refresh_review()

    def refresh_review(self):
        seg = self.profile["segments"][1]
        self.review = {"schema_version": 1, "status": "ROOT_REVIEWED_CLOSED_METADATA_FRONTIER_PRESERVED",
                       "kind": "SHORT_DETECTOR_UNKNOWN_COLLECTOR_STOP", "segment_id": seg["segment_id"], "reviewed_utc": utc(1190),
                       "plan": {**self.profile["plan"], "plan_sha256": self.f.plan["plan_sha256"]},
                       **{key: seg["closure_files"][key] for key in ("outer_terminal", "native_terminal", "events")},
                       "frontier_record": deepcopy(self.frontier), "frontier": c.stable_row(self.frontier),
                       "original_error": c.METADATA_STOP_ERROR, "original_engineering_verdict_preserved": True,
                       "short_input_review": self.short,
                       "historical_unknown": {"slot_id": self.frontier["slot_id"], "terminal": self.frontier["original_terminal"],
                                              "field": "surface:short:detector_interruption_observed", "value": None,
                                              "unobserved_checks": self.frontier["unobserved_checks"], "original_status": "INCOMPLETE_EVIDENCE"}}
        seg["stop_evidence"] = {"root_review": self.f.a.put("C:/fixture/metadata_stop/root_review.json", self.review)}

    def refresh(self):
        self.f.refresh_b()
        self.refresh_review()


class MetadataStopChainTests(unittest.TestCase):
    def test_actual_exit_then_unknown_stop_keeps_incomplete_and_old_admission(self):
        f = MetadataFixture()
        result = c.validate_continuation_profile(f.profile, f.read, now=NOW)
        self.assertEqual(len(result["closed"]), 3)
        self.assertEqual(result["closed"][-1]["original_status"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["segments"][-1]["actual_collected_count"], 0)
        self.assertEqual(result["segments"][-1]["original_native_status"], "STOPPED_FAULT")
        self.assertIn(c.reviewed_slot_source(), result["input_bindings"])
        old_inputs = f.f.admission["chain_admission"]["input_bindings"]
        self.assertNotIn(c.reviewed_slot_source(), old_inputs)
        self.assertTrue(any(row["sha256"] == "945717313097725eba537f9078297f3e91e32bfdde89e810ed01ae7a2a3d546f" for row in old_inputs))

    def test_missing_child_exit_or_invented_complete_refuses(self):
        for defect in ("no_exit", "complete"):
            f = MetadataFixture()
            if defect == "no_exit":
                del f.f.b.events[-2]
            else:
                f.f.b.events[-2]["event"] = "COMPLETE_SLOT"
            f.refresh()
            with self.assertRaises(ValueError):
                c.validate_chain(f.profile, f.read, now=NOW)

    def test_metadata_stop_cannot_be_relabelled_controlled_signal(self):
        f = MetadataFixture()
        f.profile["segments"][1]["disposition"] = "ROOT_REVIEWED_CONTROLLED_STOP"
        with self.assertRaises(ValueError):
            c.validate_chain(f.profile, f.read, now=NOW)

    def test_wrong_terminal_or_unknown_field_cannot_inherit_review(self):
        for key, value in (("field", "surface:long:detector_interruption_observed"), ("terminal", {"path": "/wrong/terminal.json", "sha256": "f" * 64})):
            f = MetadataFixture()
            f.review["historical_unknown"][key] = value
            f.profile["segments"][1]["stop_evidence"]["root_review"] = f.f.a.put("C:/fixture/metadata_stop/root_review.json", f.review)
            with self.assertRaises(ValueError):
                c.validate_chain(f.profile, f.read, now=NOW)

    def test_prior_admission_cannot_be_replaced_by_new_library_snapshot(self):
        f = MetadataFixture()
        f.f.admission["chain_admission"]["input_bindings"].append(c.reviewed_slot_source())
        f.refresh()
        with self.assertRaises(ValueError):
            c.validate_chain(f.profile, f.read, now=NOW)

    def test_unreviewed_prior_validator_source_refuses(self):
        f = MetadataFixture()
        binding = f.f.a.put("C:/fixture/unreviewed_validator.py", b"raise AssertionError('must never execute')\n")
        for target in (f.profile["segments"][1]["source_files"], f.f.b.profile["source_files"]):
            target["chain_validator"] = binding
        for target in (f.profile["segments"][1]["description"], f.f.b.profile["description"], f.f.b.started):
            target["pins"]["chain_validator"] = binding
        f.refresh()
        with self.assertRaisesRegex(ValueError, "unreviewed or relocated prefix validator"):
            c.validate_chain(f.profile, f.read, now=NOW)


if __name__ == "__main__":
    unittest.main()
