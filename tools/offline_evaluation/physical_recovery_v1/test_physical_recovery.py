"""Tiny synthetic JSON fixtures only: no original recordings or ROS imports."""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import physical_recovery as p


def nav(receive, source, uuid="old", actor_track=1, state=1):
    return {"kind": "navigation_state", "time_s": receive, "stamp_s": source,
            "target_uuid": uuid, "track_id": actor_track, "state": state,
            "prediction_age_s": 0., "position_m": [0., 0., 0.], "velocity_mps": [0., 0., 0.]}


def physical(source, uuid="old", actor="A", actor_track="1"):
    matching = {"status": "known", "physical_id": actor, "reason": "synthetic_independent_match"}
    return {"time_s": source, "target_uuid": uuid, "selected_track_id": actor_track,
            "expected_physical_id": "A", "matched_physical_id": actor,
            "status": "CORRECT" if actor == "A" else "WRONG_PHYSICAL_ACTOR",
            "match": matching, "matching": matching.copy()}


def fixture():
    tasks = {}
    for uuid, request, source, confirmed in (("old", .5, .4, .6), ("new", 8.3, 8.2, 8.4)):
        tasks[uuid] = {"request_time_s": request, "source_image_s": source,
                       "confirmation_time_s": confirmed, "confirmed": True,
                       "expected_physical_id": "A", "initial_mapping_known": True,
                       "duplicate_request_uuid": False}
    cells = [{"time_s": .5 + i * .1, "end_s": min(12., .5 + (i + 1) * .1),
              "target_uuid": "old" if i < 78 else "new", "outcome": "unknown", "reason": "synthetic_unknown_cell"}
             for i in range(115)]
    for uuid, task in tasks.items():
        task.update(scheduled_samples=sum(r["target_uuid"] == uuid for r in cells),
                    correct=0, wrong=0, unknown=sum(r["target_uuid"] == uuid for r in cells))
    audit = {"schema_version": 1, "sample_period_s": .1,
             "coverage_basis": "fixed_10hz_request_to_recorded_clock_end", "interval": {"start_s": .5, "end_s": 12.},
             "timeline": cells, "scheduled_samples": 115, "correct": 0, "wrong": 0, "unknown": 115,
             "requested_task_count": 2, "tasks": tasks}
    identity = {"schema_version": 1, "conservative_task_time_identity": audit,
                "tasks": {u: {"initial_mapping": {"physical_id": "A"}} for u in tasks},
                "selected_identity_timeline": [physical(2.25), physical(3.3), physical(8.35, "new")]}
    frames = [{"time_s": 1. + i * .1, "navigation_valid": True, "navigation_state": 2, "active": True}
              for i in range(111)]
    navigation = {"schema_version": 1,
                  "interval": {"start_s": 1., "end_s": 12., "navigation_evaluation_start_s": 1., "sample_period_s": .1},
                  "whole_interval": {"scheduled_samples": 111},
                  "kf_navigation": {"counts": {"scheduled_samples": 111, "valid_navigation_samples": 111}}}
    raw = [{"kind": "initial_selection_requested", "time_s": .5, "target_uuid": "old", "image_stamp_s": .4},
           {"kind": "shutter", "time_s": 2., "active": True, "request_id": 1},
           {"kind": "shutter", "time_s": 2.2, "active": False, "request_id": 2},
           {"kind": "shutter_hold_finished", "time_s": 2.21, "name": "short", "state": "complete", "close_request_id": 1, "open_request_id": 2},
           nav(2.3, 2.25), nav(3.4, 3.3),
           {"kind": "shutter", "time_s": 6., "active": True, "request_id": 3},
           {"kind": "shutter", "time_s": 7., "active": False, "request_id": 4},
           {"kind": "shutter_hold_finished", "time_s": 7.01, "name": "long", "state": "complete", "close_request_id": 3, "open_request_id": 4},
           {"kind": "explicit_reselection_requested", "time_s": 8.3, "target_uuid": "new", "image_stamp_s": 8.2},
           nav(8.4, 8.35, "new")]
    telemetry = [{"line_number": i + 1, "record": r} for i, r in enumerate(sorted(raw, key=lambda r: r["time_s"]))]
    slot = {"slot_id": "synthetic_slot", "opportunities": [{"id": "synthetic_slot:short", "kind": "short"},
            {"id": "synthetic_slot:long_explicit_reselection", "kind": "long_explicit_reselection"}]}
    return slot, identity, navigation, frames, {"end_sim_s": 12.}, telemetry


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.args = list(fixture())

    def events(self):
        return p.analyze_records(*self.args)["opportunities"]

    def test_guard_unknown_first_is_not_backfilled_by_later_same(self):
        event = self.events()[0]
        self.assertEqual(event["first_measured_original_outcome"], "UNKNOWN")
        self.assertEqual(event["first_measured"]["reason"], "original_inclusive_shutter_guard")
        self.assertAlmostEqual(event["original_confirmation_delay_s"], 1.2)
        self.assertTrue(event["confirmed_original_without_observed_different"])
        self.assertFalse(event["navigation_receive_stream_complete"])

    def test_wrong_then_same_keeps_first_wrong_and_vetoes_primary_numerator(self):
        self.args[-1] = [w for w in self.args[-1] if w["record"].get("stamp_s") != 2.25]
        self.args[1]["selected_identity_timeline"][1] = physical(3.3, actor="B")
        self.args[1]["selected_identity_timeline"].append(physical(3.5))
        self.args[-1].append({"line_number": 99, "record": nav(3.6, 3.5)})
        self.args[-1].sort(key=lambda w: w["record"]["time_s"])
        event = self.events()[0]
        self.assertEqual(event["first_measured_original_outcome"], "WRONG")
        self.assertEqual(len(event["different_from_original_evidence"]), 1)
        self.assertIsNotNone(event["first_supported_original"])
        self.assertFalse(event["confirmed_original_without_observed_different"])

    def test_explicit_other_actor_is_request_choice_not_tracker_switch(self):
        identity = self.args[1]
        identity["conservative_task_time_identity"]["tasks"]["new"]["expected_physical_id"] = "B"
        identity["tasks"]["new"]["initial_mapping"]["physical_id"] = "B"
        row = physical(8.35, "new", "B")
        row["expected_physical_id"] = "B"
        identity["selected_identity_timeline"][-1] = row
        event = self.events()[1]
        self.assertEqual(event["reselection_request_original_relation"], "DIFFERENT_FROM_ORIGINAL")
        self.assertEqual(event["first_measured_original_outcome"], "DIFFERENT_FROM_ORIGINAL")
        self.assertEqual(event["first_measured_requested_outcome"], "SAME")
        self.assertTrue(event["confirmed_requested_without_observed_wrong"])
        self.assertEqual(event["wrong_requested_actor_evidence"], [])

    def test_duplicate_identity_key_and_duplicate_navigation_key_are_unknown(self):
        identity = self.args[1]["selected_identity_timeline"]
        identity.append(copy.deepcopy(identity[1]))
        self.assertIsNone(self.events()[0]["first_supported_original"])
        self.args = list(fixture())
        self.args[-1].append({"line_number": 99, "record": nav(3.45, 3.3)})
        self.args[-1].sort(key=lambda w: w["record"]["time_s"])
        self.assertIsNone(self.events()[0]["first_supported_original"])

    def test_no_nearest_frame_or_active_predicted_substitution(self):
        self.args[1]["selected_identity_timeline"][1]["time_s"] = 3.300002
        self.assertIsNone(self.events()[0]["first_supported_original"])
        for wrapped in self.args[-1]:
            if wrapped["record"]["kind"] == "navigation_state":
                wrapped["record"]["state"] = 2
        self.assertTrue(self.events()[0]["no_eligible_measured"])

    def test_initial_request_is_not_explicit_reselection(self):
        self.args[-1] = [w for w in self.args[-1] if w["record"]["kind"] != "explicit_reselection_requested"]
        event = self.events()[1]
        self.assertEqual(event["evidence_status"], "INCOMPLETE_EVIDENCE")
        self.assertIsNone(event["requested_confirmation_delay_s"])

    def test_mapping_conflict_is_local_and_full_task_unknown_not_legacy_filled(self):
        identity = self.args[1]
        identity["tasks"]["new"]["initial_mapping"]["physical_id"] = "B"
        events = self.events()
        self.assertTrue(events[0]["confirmed_original_without_observed_different"])
        self.assertEqual(events[1]["evidence_status"], "INCOMPLETE_EVIDENCE")
        task = identity["conservative_task_time_identity"]["tasks"]["new"]
        task.update(expected_physical_id=None, initial_mapping_known=False)
        self.assertIsNone(self.events()[1]["requested_expected_physical_id"])

    def test_cleared_task_is_not_resurrected_from_latest_request(self):
        for cell in self.args[1]["conservative_task_time_identity"]["timeline"]:
            if p.us(cell["time_s"]) <= 2000000 < p.us(cell["end_s"]):
                cell["reason"] = "task_cleared_or_reset"
        event = self.events()[0]
        self.assertEqual(event["evidence_status"], "INCOMPLETE_EVIDENCE")
        self.assertFalse(event["confirmed_original_without_observed_different"])

    def test_clear_after_close_and_next_request_at_cutoff_cannot_confirm_old_task(self):
        for cell in self.args[1]["conservative_task_time_identity"]["timeline"]:
            if p.us(cell["time_s"]) == 3000000:
                cell["reason"] = "task_cleared_or_reset"
        self.assertIsNone(self.events()[0]["first_supported_original"])
        self.args = list(fixture())
        # A new request exactly at the otherwise eligible old message's receive
        # time cuts the old task's observation interval on the right.
        self.args[1]["conservative_task_time_identity"]["tasks"]["new"]["request_time_s"] = 3.4
        self.args[1]["conservative_task_time_identity"]["tasks"]["new"]["confirmation_time_s"] = 3.5
        event = self.events()[0]
        self.assertFalse(event["observation_end_inclusive"])
        self.assertIsNone(event["first_supported_original"])

    def test_receive_and_source_must_both_follow_open_and_age_is_not_point15(self):
        self.assertEqual(p.candidate_problem(nav(2.3, 2.1), 2.2, 5.2, "old"), "source_or_receive_outside_observation_window")
        self.assertIsNone(p.candidate_problem(nav(3.5, 3.3), 2.2, 5.2, "old"))
        self.assertEqual(p.candidate_problem(nav(3.5, 2.6), 2.2, 5.2, "old"), "invalid_or_stale_measurement_clock")
        self.assertEqual(p.candidate_problem(nav(3.5, 3.6), 2.2, 5.2, "old"), "invalid_or_stale_measurement_clock")

    def test_invalid_ids_nan_and_microsecond_rounding(self):
        for value in (0, True, -1, "01", "nan", None):
            self.assertRaises(ValueError, p.track, value)
        for payload in ('{"a":NaN}', '{"a":1e999}', '{"a":1,"a":2}'):
            self.assertRaises(ValueError, p.strict_json, payload)
        self.assertEqual(p.us(1.0000005), 1000000)
        self.assertEqual(p.us(1.0000015), 1000002)
        self.assertRaises(ValueError, p.us, float("nan"))

    def test_identity_and_navigation_denominators_cannot_be_shrunk(self):
        self.args[1]["conservative_task_time_identity"]["timeline"].pop()
        self.assertRaises(ValueError, self.events)
        self.args = list(fixture())
        self.args[3].pop()
        self.assertRaises(ValueError, self.events)

    def test_no_confirmation_is_null_and_short_recording_right_censored(self):
        self.args[4]["end_sim_s"] = 2.7
        event = self.events()[0]
        self.assertTrue(event["right_censored"])
        self.assertIsNone(event["original_confirmation_delay_s"])
        totals = p.summarize([{"opportunities": self.events()}])["all"]
        self.assertEqual(totals["registered_opportunities"], 2)
        self.assertEqual(totals["original_confirmation_delay_s"], {"n": 0, "N": 2, "mean": None, "minimum": None, "maximum": None})


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        root = self.base / "frozen"
        output = root / "results" / "formal120"
        output.mkdir(parents=True)
        trials = [{"id": f"{cls}_{group}_seed{seed}", "target_class": cls, "group": group,
                   "stage": int(group[5]), "seed": seed, "directory": str(output.parent / f"{cls}_{group}_seed{seed}")}
                  for cls in ("person", "car") for group in p.GROUPS for seed in range(1000, 1010)]
        self.plan = {"schema_version": 1, "study_kind": "POST_REPAIR_ENGINEERING_VALIDATION", "mode": "FORMAL",
                     "selected_classes": ["person", "car"], "selected_groups": list(p.GROUPS),
                     "selected_seeds": list(range(1000, 1010)), "trials": trials,
                     "frozen_root": str(root), "output": str(output), "source_hashes": {"synthetic.py": "a" * 64},
                     "development_probe_gate": {"synthetic_fixture_only": True}}
        self.plan["plan_sha256"] = p.digest_without(self.plan, "plan_sha256")
        self.plan_path = output / "plan.json"
        p.write_new(self.plan_path, self.plan)
        self.pin = {"path": str(self.plan_path), "sha256": hashlib.sha256(self.plan_path.read_bytes()).hexdigest()}

    def protocol(self):
        return p.make_protocol(self.pin)

    def start(self, protocol, delta):
        folder = self.plan_path.parent / "slots"
        folder.mkdir(exist_ok=True)
        trial = self.plan["trials"][0]
        stamp = p.utc(protocol["created_utc"]) + timedelta(seconds=delta)
        p.write_new(folder / (trial["id"] + ".started.json"),
                    {"id": trial["id"], "plan_sha256": self.plan["plan_sha256"], "started_utc": stamp.isoformat()})

    def test_exact40_slots80_registered_opportunities(self):
        protocol = self.protocol()
        self.assertEqual(len(protocol["slots"]), 40)
        self.assertEqual(protocol["registered_opportunities"], 80)
        self.assertEqual({s["group"] for s in protocol["slots"]}, set(p.SELECTED))
        self.assertEqual(p.validate_protocol(protocol)[1], [])

    def test_creation_rejects_any_original120_start_and_late_protocol(self):
        protocol = self.protocol()
        self.start(protocol, -1)
        self.assertRaises(ValueError, self.protocol)
        self.assertRaises(ValueError, p.validate_protocol, protocol)

    def test_changed_producer_rules_omitted_cells_or_plan_bytes_rejected(self):
        protocol = self.protocol()
        for changed in ("producer", "rule", "slots"):
            value = copy.deepcopy(protocol)
            if changed == "slots":
                value[changed].pop()
            else:
                value[changed]["modified"] = True
            self.assertRaises(ValueError, p.validate_protocol, value)
        self.plan_path.write_text(self.plan_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.assertRaises(ValueError, p.validate_protocol, protocol)

    def test_missing_all_reports_keeps80_and_every_source_path(self):
        protocol = self.protocol()
        slots = [p.analyze_slot(self.plan, slot) for slot in protocol["slots"]]
        totals = p.summarize(slots)["all"]
        self.assertEqual(totals["registered_opportunities"], 80)
        self.assertEqual(totals["supported_original_without_observed_different"], 0)
        self.assertEqual(totals["missing_or_invalid_events"], 80)
        self.assertTrue(all(len(slot["source_bindings"]) == 6 for slot in slots))
        self.assertTrue(all(set(event["source_hashes"]) == {"terminal", *p.FILES} for slot in slots for event in slot["opportunities"]))
        self.assertIsNone(totals["original_confirmation_delay_s"]["mean"])

    def test_original_output_and_existing_directory_cannot_be_written(self):
        self.assertRaises(ValueError, p.external_output, self.plan_path.parent / "appendix", self.plan)
        self.assertRaises(ValueError, p.external_output, self.base, self.plan)
        self.assertEqual(p.external_output(self.base / "new_attachment", self.plan), self.base / "new_attachment")

    def test_cross_platform_paths_are_not_absence_evidence(self):
        foreign = "/root/nonexistent_formal120/plan.json" if p.os.name == "nt" else "D:/nonexistent_formal120/plan.json"
        self.assertRaises(ValueError, p.native, foreign)

    def test_tiny_closed_sources_bind_hashes_preserve_fail_and_write80_rows(self):
        protocol = self.protocol()
        protocol["created_utc"] = "2000-01-01T00:00:00+00:00"  # Synthetic fixture, never an actual registration.
        protocol_path = self.base / "synthetic_protocol.json"
        p.write_new(protocol_path, protocol)
        binding = {"path": str(protocol_path), "sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest()}
        slot = protocol["slots"][0]
        directory = Path(slot["source_trial"])
        directory.mkdir()
        _, identity, navigation, frames, summary, telemetry = fixture()
        identity["source_trial"] = navigation["trial"] = str(directory)
        p.write_new(directory / p.FILES["identity"], identity)
        navigation["physical_identity_sha256"] = hashlib.sha256((directory / p.FILES["identity"]).read_bytes()).hexdigest()
        p.write_new(directory / p.FILES["navigation"], navigation)
        p.write_new(directory / p.FILES["summary"], summary)
        for role, records in (("navigation_frames", frames), ("telemetry", [w["record"] for w in telemetry])):
            (directory / p.FILES[role]).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        metadata = self.plan_path.parent / "slots"
        metadata.mkdir()
        p.write_new(metadata / (slot["slot_id"] + ".started.json"),
                    {"id": slot["slot_id"], "plan_sha256": self.plan["plan_sha256"], "started_utc": "2000-01-01T00:00:01Z"})
        terminal = {"id": slot["slot_id"], "plan_sha256": self.plan["plan_sha256"], "status": "FAIL",
                    "artifact_hashes": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in p.FILES.values()}}
        terminal["record_sha256"] = p.digest_without(terminal, "record_sha256")
        terminal_path = metadata / (slot["slot_id"] + ".json")
        p.write_new(terminal_path, terminal)
        terminal_before = terminal_path.read_bytes()
        report = p.analyze(binding)
        self.assertEqual(report["slots"][0]["original_terminal_status"], "FAIL")
        self.assertEqual(report["summary"]["all"]["registered_opportunities"], 80)
        self.assertEqual(report["observed_original_core_starts"], 1)
        self.assertEqual(report["formal_flights_started_by_this_tool"], 0)
        self.assertTrue(report["slots"][0]["opportunities"][0]["confirmed_original_without_observed_different"])
        output = self.base / "synthetic_attachment"
        output.mkdir()
        p.write_appendix(output, report)
        self.assertEqual(len((output / "physical_recovery.csv").read_text(encoding="utf-8").splitlines()), 81)
        self.assertEqual(terminal_path.read_bytes(), terminal_before)
        # Parseable byte tampering must not reuse the original report verdict.
        with (directory / p.FILES["identity"]).open("a", encoding="utf-8") as stream:
            stream.write(" ")
        invalid = p.analyze_slot(self.plan, slot)
        self.assertTrue(invalid["issues"])
        self.assertFalse(any(e["confirmed_original_without_observed_different"] for e in invalid["opportunities"]))


if __name__ == "__main__":
    unittest.main()
