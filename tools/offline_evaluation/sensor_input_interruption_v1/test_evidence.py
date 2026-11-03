"""Tiny synthetic file fixtures; never ROS, real bags, actual images or inference."""

from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


SPEC = importlib.util.spec_from_file_location("sensor_input_interruption_evidence", Path(__file__).with_name("evidence.py"))
e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\x40\x40\x40" * 2) * 2)) + chunk(b"IEND", b""))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        for name in ("evaluate_stage1_flight.py", "sensor_fault_bridge.py"):
            path = self.source / "scripts" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# SYNTHETIC SOURCE FIXTURE, NOT REAL EVIDENCE\n", encoding="utf-8")
        self.matrix = self.root / "matrix"
        self.matrix.mkdir()
        self.results = self.root / "trials"
        self.results.mkdir()
        self.plan_path = self.matrix / "plan.json"
        self.trials = []
        for cls in ("person", "car"):
            for condition in ("dropout", "combined"):
                slot = cls + "_" + condition
                directory = self.results / slot
                directory.mkdir()
                flight = ["bash", "synthetic.sh", "--name", slot, "--class", cls,
                          "--condition", condition, "--seed", "4"]
                evaluations = [{"kind": kind, "report": str(directory / filename),
                                "command": ["python", kind, str(directory / filename)]}
                               for kind, filename in (("surface_flight", "flight_evaluation.json"),
                                                      ("source_clock", "px4_source_clock_report.json"),
                                                      ("native_startup", "native_startup_report.json"))]
                self.trials.append({"id": slot, "name": slot, "target_class": cls, "seed": 4,
                                    "condition": condition, "extension_condition": condition,
                                    "directory": str(directory), "flight_command": flight, "evaluations": evaluations})
        self.plan = {"mode": "EXTENSION_PROBE", "frozen_root": str(self.source), "output": str(self.matrix),
                     "results_root": str(self.results), "trials": self.trials,
                     "source_hashes": {"scripts/" + name: e._hash(self.source / "scripts" / name)
                                       for name in ("evaluate_stage1_flight.py", "sensor_fault_bridge.py")}}
        self.plan["plan_sha256"] = e._digest(self.plan)
        write_json(self.plan_path, self.plan)
        self.contract = {"schema_version": 1, "revision": e.REVISION, "scope": e.SCOPE,
                         "fault_algorithm": e.FAULT_ALGORITHM, "drop_window_ns": 200_000_000,
                         "drop_fraction": "0.10", "padding_s": "0.3",
                         "extractor_sha256_by_condition": {"dropout": "1" * 64, "combined": "2" * 64},
                         "source_plan": e._binding(self.plan_path),
                         "dev_slots": [{"slot_id": row["id"], "target_class": row["target_class"], "condition": row["condition"]}
                                       for row in self.trials]}
        self.extracts, self.reviews = {}, {}
        for trial in self.trials:
            self.make_trial(trial)

    def make_trial(self, trial):
        slot, directory = trial["id"], Path(trial["directory"])
        short_checks = {key: True for key in (*e.SHUTTER, *e.SHORT_ALGORITHM)}
        short_checks["detector_interruption_observed"] = None
        long_checks = {key: True for key in (*e.SHUTTER, *e.LONG_SAFETY, *e.LONG_ALGORITHM)}

        def occlusion(kind, start, end, ack, checks, result, close_id, open_id):
            return {"kind": kind, "start_s": start, "end_s": end, "complete": True,
                    "close_request_id": close_id, "open_request_id": open_id, "checks": checks,
                    "result": result, "shutter_execution": {"close_success": True, "open_success": True,
                        "close_ack_before_open_request": True, "close_request_id": close_id,
                        "open_request_id": open_id, "close_response_s": ack, "open_response_s": end + .02}}
        short = occlusion("short", 31.3, 31.58, 31.32, short_checks, "INCOMPLETE_EVIDENCE", 1, 3)
        short.update(diagnostic_frames_inside=0, candidate_free_frames_inside=0, valid_depth_frames_inside=0)
        surface = {"target_class": trial["target_class"], "configuration": {"max_prediction_s": .75},
                   "flight_evidence": {"armed_seen": True, "offboard_seen": True},
                   "detector": {"invalid_diagnostic_messages": 0},
                   "occlusions": [short, occlusion("long", 44.3, 47.38, 44.32, long_checks, "PASS", 4, 19)],
                   "acceptance": {"result": "INCOMPLETE_EVIDENCE", "missing_topics": [], "input_read_error_count": 0,
                        "clock_timebase_available": True, "short_occlusion_recorded": True,
                        "long_occlusion_recorded": True, "failed_events_retained": True}}
        write_json(directory / "flight_evaluation.json", surface)
        for filename in ("px4_source_clock_report.json", "native_startup_report.json"):
            write_json(directory / filename, {"evaluation_status": "PASS"})
        for filename in ("recording_closure.json", "bag_integrity.json"):
            write_json(directory / filename, {"status": "PASS"})
        write_json(directory / "configuration/sensor_faults.json", {"seed": 4, "drop_fraction": .1})
        (directory / "rosbag").mkdir()
        (directory / "rosbag/metadata.yaml").write_text("synthetic: true\n", encoding="utf-8")
        terminal = {"id": slot, "name": slot, "plan_sha256": self.plan["plan_sha256"],
                    "status": "INCOMPLETE_EVIDENCE", "engineering_evidence": {"incomplete": ["surface_flight"], "pending": []},
                    "execution_status": "COMPLETED", "infrastructure_stop": False, "flight_exit_code": 0,
                    "cleanup": {"residual_processes": []},
                    "commands": [{"kind": "flight", "command": trial["flight_command"], "returncode": 0, "error": None}],
                    "evaluations": [], "artifact_hashes": {}}
        self.write_terminal(trial, terminal)
        extraction = self.root / "extractions" / slot / "manifest.json"
        extraction.parent.mkdir(parents=True)
        self.extracts[slot] = extraction
        opportunities = []
        for tenth in range(9):
            ns = 31_000_000_000 + tenth * 100_000_000
            kept = tenth not in (2, 3, 4, 5)
            topics = [e.RAW_RGB, e.RAW_DEPTH] + ([e.RESEARCH_RGB, e.RESEARCH_DEPTH, e.DIAGNOSTIC] if kept else [])
            for topic in topics:
                row = {"topic": topic, "record_sequence": len(opportunities), "recording_timestamp_ns": 10**18 + ns,
                       "latest_read_clock_ns": ns + 20_000_000, "acquisition_ns": ns,
                       "acquisition_stamp_s_decimal": str(e.Decimal(ns) / 10**9)}
                if topic == e.DIAGNOSTIC:
                    row.update(header_ns=None, original_stamp_s_decimal=str(ns / 10**9),
                               original_diagnostic_json=json.dumps({"stamp_s": ns / 10**9, "acquisition_ns": ns}))
                else:
                    row.update(header_sec=31, header_nanosec=tenth * 100_000_000, header_ns=ns, width=2, height=2)
                if topic == e.RAW_RGB:
                    name = "raw_" + str(ns) + ".png"
                    (extraction.parent / name).write_bytes(png())
                    row.update(original_png=name, png_sha256=e._hash(extraction.parent / name))
                opportunities.append(row)
        (extraction.parent / "contact_sheet.png").write_bytes(png())
        manifest = {"schema_version": 1, "status": "PENDING_VISUAL_REVIEW", "visual_review": "PENDING_VISUAL_REVIEW",
                    "all_selected_topics_scanned": True, "absent_topics": [], "clock_regression_count": 0,
                    "topics_selected": list(e.TOPICS), "bag_reader": {"source_bag_read_only": True},
                    "source_root": str(self.source), "plan": str(self.plan_path), "plan_sha256": self.plan["plan_sha256"],
                    "slot_id": slot, "trial_name": slot, "trial_directory": str(directory),
                    "tool_sha256": self.contract["extractor_sha256_by_condition"][trial["condition"]],
                    "selection": {"start_s_decimal": "31.0", "end_s_decimal": "31.88", "inclusive": True,
                                  "success_or_failure_selection": False, "raw_rgb_hard_limit": 32},
                    "opportunities": opportunities,
                    "scanned_message_counts": {topic: 100 for topic in e.TOPICS},
                    "contact_sheet": {"file": "contact_sheet.png", "sha256": e._hash(extraction.parent / "contact_sheet.png")},
                    "finished_utc": "2026-11-03T00:00:00+00:00"}
        write_json(extraction, manifest)
        review = extraction.parent / "visual_review.json"
        self.reviews[slot] = review
        write_json(review, {"kind": "INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE",
                            "review_type": "DIRECT_IMAGE_REVIEW_AI", "reviewers": ["SYNTHETIC FIXTURE, NOT REAL REVIEW"],
                            "created_utc": "2026-11-03T00:01:00+00:00", "images": []})
        self.refresh(trial)

    def write_terminal(self, trial, terminal):
        directory = Path(trial["directory"])
        terminal["artifact_hashes"] = {path.relative_to(directory).as_posix(): e._hash(path)
                                      for path in directory.rglob("*") if path.is_file()}
        terminal["evaluations"] = []
        for spec in trial["evaluations"]:
            report = e._json(spec["report"])
            verdict = report["acceptance"]["result"] if spec["kind"] == "surface_flight" else report["evaluation_status"]
            terminal["evaluations"].append({"kind": spec["kind"], "report": spec["report"], "result": verdict,
                "reported_verdict": verdict, "report_sha256": e._hash(spec["report"]), "error": None,
                "execution": {"returncode": 0, "error": None, "command": spec["command"]}})
        terminal["record_sha256"] = e._digest(terminal, "record_sha256")
        write_json(self.matrix / "slots" / (trial["id"] + ".json"), terminal)

    def refresh(self, trial):
        slot, directory = trial["id"], Path(trial["directory"])
        terminal_path = self.matrix / "slots" / (slot + ".json")
        terminal = e._json(terminal_path)
        self.write_terminal(trial, terminal)
        terminal = e._json(terminal_path)
        surface = e._json(directory / "flight_evaluation.json")
        manifest = e._json(self.extracts[slot])
        manifest.update(original_terminal_status=terminal["status"], original_engineering_evidence=terminal["engineering_evidence"],
                        original_acceptance=surface["acceptance"], original_short_window=surface["occlusions"][0],
                        original_sensor_faults=e._json(directory / "configuration/sensor_faults.json"))
        inputs = [self.plan_path, terminal_path, directory / "flight_evaluation.json", directory / "recording_closure.json",
                  directory / "bag_integrity.json", directory / "configuration/sensor_faults.json", directory / "rosbag/metadata.yaml",
                  self.source / "scripts/evaluate_stage1_flight.py"]
        manifest["input_small_files"] = {str(path): {"bytes": path.stat().st_size, "sha256": e._hash(path)} for path in inputs}
        manifest["window_opportunity_counts"] = dict(Counter(row["topic"] for row in manifest["opportunities"]))
        manifest["exported_raw_rgb_count"] = manifest["window_opportunity_counts"][e.RAW_RGB]
        write_json(self.extracts[slot], manifest)
        review = e._json(self.reviews[slot])
        review["manifest"] = e._binding(self.extracts[slot])
        if not review["images"]:
            review["images"] = [{"file": row["original_png"], "sha256": row["png_sha256"], "acquisition_ns": row["acquisition_ns"],
                                 "observation": e.OBSCURED if row["acquisition_ns"] in (31_400_000_000, 31_500_000_000) else "TARGET_AND_SCENE_VISIBLE"}
                                for row in manifest["opportunities"] if row["topic"] == e.RAW_RGB]
        write_json(self.reviews[slot], review)

    def run_slot(self, slot="person_dropout"):
        return e.evaluate_slot(self.plan_path, slot, self.extracts[slot], self.reviews[slot], self.contract)

    def make_conditional_short_loss(self, slot="person_dropout"):
        def mutate(surface):
            surface["interval"] = {"end_s": 60.0}
            surface["configuration"]["recovery_window_s"] = 3.0
            short = surface["occlusions"][0]
            short.update(duration_s=short["end_s"] - short["start_s"], first_lost_s=32.0,
                         first_measured_after_open_s=None, recovery_after_open_s=None,
                         post_open_measured_missing_receive_time_count=0, result="FAIL")
            short["checks"].update(no_loss_during_short_occlusion=False, identity_preserved_on_observed_recovery=None)
            surface["acceptance"]["result"] = "FAIL"
        self.edit_surface(mutate, terminal_status="FAIL", slot=slot)
        trial = next(row for row in self.trials if row["id"] == slot)
        terminal = e._json(self.matrix / "slots" / (slot + ".json"))
        terminal["engineering_result"] = "FAIL"
        self.write_terminal(trial, terminal)
        self.refresh(trial)

    def edit_manifest(self, mutate, slot="person_dropout"):
        value = e._json(self.extracts[slot])
        mutate(value)
        write_json(self.extracts[slot], value)
        self.refresh(next(row for row in self.trials if row["id"] == slot))

    def edit_surface(self, mutate, terminal_status=None, slot="person_dropout"):
        trial = next(row for row in self.trials if row["id"] == slot)
        path = Path(trial["directory"]) / "flight_evaluation.json"
        surface = e._json(path)
        mutate(surface)
        write_json(path, surface)
        if terminal_status:
            terminal_path = self.matrix / "slots" / (slot + ".json")
            terminal = e._json(terminal_path)
            terminal["status"] = terminal_status
            write_json(terminal_path, terminal)
        self.refresh(trial)

    def matrix_manifest(self, slots=None):
        slots = list(self.extracts) if slots is None else slots
        path = self.root / "development_manifest.json"
        write_json(path, {"schema_version": 1, "contract_sha256": e._digest(self.contract),
                          "source_plan": self.contract["source_plan"],
                          "slots": [{"slot_id": slot, "extraction_manifest": e._binding(self.extracts[slot]),
                                     "visual_review": e._binding(self.reviews[slot])} for slot in slots]})
        return path

    def test_valid_slot_preserves_unknown_and_exact_drop_ledger(self):
        report = self.run_slot()
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertIsNone(report["original"]["occlusions"][0]["checks"]["detector_interruption_observed"])
        self.assertEqual(report["original"]["terminal_status"], "INCOMPLETE_EVIDENCE")
        self.assertEqual([row["expected_drop"] for row in report["drop_ledger"]], [False, False, True, True, True, True, False, False, False])
        self.assertEqual(report["short_window_opportunities"][e.RAW_RGB], [31_300_000_000, 31_400_000_000, 31_500_000_000])
        self.assertEqual(report["short_window_opportunities"][e.DIAGNOSTIC], [])
        self.assertNotIn("ready", report)

    def test_complete_fixed_four_cell_matrix(self):
        report = e.evaluate_development_manifest(self.matrix_manifest(), self.contract)
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertEqual(len(report["per_slot"]), 4)
        self.assertNotIn("ready", report)

    def test_partial_matrix_retains_per_slot_without_complete_status(self):
        report = e.evaluate_development_manifest(self.matrix_manifest(list(self.extracts)[:3]), self.contract)
        self.assertEqual(report["status"], e.INCOMPLETE)
        self.assertEqual(len(report["per_slot"]), 3)
        self.assertEqual(report["missing_slot_ids"], ["car_combined"])

    def test_duplicate_matrix_slot_rejected(self):
        report = e.evaluate_development_manifest(self.matrix_manifest(["person_dropout"] * 4), self.contract)
        self.assertEqual(report["status"], e.INCOMPLETE)

    def test_contract_cannot_select_only_successful_cells(self):
        self.contract["dev_slots"].pop()
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_unknown_slot_is_not_not_applicable(self):
        report = e.evaluate_slot(self.plan_path, "unknown", self.extracts["person_dropout"], self.reviews["person_dropout"], self.contract)
        self.assertEqual(report["status"], e.INCOMPLETE)

    def test_original_png_tampering_rejected(self):
        path = next(self.extracts["person_dropout"].parent.glob("raw_*.png"))
        path.write_bytes(path.read_bytes() + b"tamper")
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_contact_sheet_tampering_rejected(self):
        (self.extracts["person_dropout"].parent / "contact_sheet.png").write_bytes(b"tamper")
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_review_must_bind_actual_manifest(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        review["manifest"]["sha256"] = "0" * 64
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_brightness_classifier_is_not_direct_review(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        review["review_type"] = "AUTOMATIC_BRIGHTNESS_THRESHOLD"
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_old_review_without_explicit_type_is_not_silently_upgraded(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        review.pop("review_type")
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_review_needs_visible_scene_before_and_after(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        for row in review["images"]:
            row["observation"] = e.OBSCURED
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_review_obscured_frame_must_follow_close_ack(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        for row in review["images"]:
            row["observation"] = e.OBSCURED if row["acquisition_ns"] == 31_300_000_000 else "TARGET_AND_SCENE_VISIBLE"
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_unknown_short_behavior_is_not_replaced(self):
        self.edit_surface(lambda value: value["occlusions"][0]["checks"].update(prediction_observed=None))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_conditional_short_loss_requires_exact_opt_in_and_preserves_original_failure(self):
        self.make_conditional_short_loss()
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)
        for invalid in (None, True, False, "", "ALLOW_UNKNOWN_IDENTITY"):
            with self.subTest(invalid=invalid):
                self.contract["conditional_identity_rule"] = invalid
                self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)
        self.contract["conditional_identity_rule"] = e.CONDITIONAL_IDENTITY
        before = {str(path): e._hash(path) for path in self.root.rglob("*") if path.is_file()}
        report = self.run_slot()
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertEqual(report["original"]["terminal_status"], "FAIL")
        self.assertEqual(report["original"]["acceptance"]["result"], "FAIL")
        self.assertIsNone(report["original"]["occlusions"][0]["checks"]["identity_preserved_on_observed_recovery"])
        self.assertEqual(report["known_algorithm_failures"], ["surface:short:no_loss_during_short_occlusion=FAIL"])
        self.assertEqual(len(report["conditional_nonobservations"]), 1)
        proof = report["conditional_nonobservations"][0]
        self.assertEqual(proof["classification"], e.CONDITIONAL_IDENTITY)
        self.assertEqual(proof["original_engineering_result"], "FAIL")
        self.assertEqual(proof["identity_result"], "UNOBSERVED")
        self.assertEqual(proof["identity_switch_observed_or_excluded"], "NEITHER")
        self.assertIsNone(proof["value"])
        self.assertEqual(before, {str(path): e._hash(path) for path in self.root.rglob("*") if path.is_file()})
        matrix = e.evaluate_development_manifest(self.matrix_manifest(), self.contract)
        self.assertEqual(matrix["status"], e.CORROBORATED, matrix)
        self.assertEqual(len(matrix["per_slot"]), 4)
        self.assertEqual(sum(len(row["conditional_nonobservations"]) for row in matrix["per_slot"]), 1)

    def test_conditional_predicate_rejects_recovery_missing_clocks_and_undemonstrated_loss(self):
        self.make_conditional_short_loss()
        trial = self.trials[0]
        surface = e._json(Path(trial["directory"]) / "flight_evaluation.json")
        record = e._json(self.matrix / "slots" / (trial["id"] + ".json"))
        mutations = [
            lambda s, r: s["occlusions"][0]["checks"].update(no_loss_during_short_occlusion=True),
            lambda s, r: s["occlusions"][0]["checks"].update(no_loss_during_short_occlusion=None),
            lambda s, r: s["occlusions"][0].update(first_measured_after_open_s=32.0),
            lambda s, r: s["occlusions"][0].update(recovery_after_open_s=0.8),
            lambda s, r: s["occlusions"][0].pop("first_measured_after_open_s"),
            lambda s, r: s["occlusions"][0]["checks"].pop("identity_preserved_on_observed_recovery"),
            lambda s, r: s["occlusions"][0].update(post_open_measured_missing_receive_time_count=1),
            lambda s, r: s["occlusions"][0].update(post_open_measured_missing_receive_time_count=False),
            lambda s, r: s["occlusions"][0].pop("post_open_measured_missing_receive_time_count"),
            lambda s, r: s["occlusions"][0].update(first_lost_s=None),
            lambda s, r: s["occlusions"][0].update(first_lost_s=True),
            lambda s, r: s["occlusions"][0].update(first_lost_s=float("nan")),
            lambda s, r: s["occlusions"][0].update(first_lost_s=float("inf")),
            lambda s, r: s["occlusions"][0].update(first_lost_s=30.0),
            lambda s, r: s["occlusions"][0].update(first_lost_s=60.0),
            lambda s, r: s["occlusions"][0].update(duration_s=0.1),
            lambda s, r: s["configuration"].update(max_prediction_s=0.1),
            lambda s, r: s["configuration"].update(recovery_window_s=0.0),
            lambda s, r: s["interval"].update(end_s=30.0),
            lambda s, r: s["occlusions"][0].update(result="PASS"),
            lambda s, r: s["occlusions"][0].update(complete=False),
            lambda s, r: s["acceptance"].update(result="INCOMPLETE_EVIDENCE"),
            lambda s, r: r.update(status="PASS"),
            lambda s, r: r.update(engineering_result="PASS"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                changed, terminal = deepcopy(surface), deepcopy(record)
                mutate(changed, terminal)
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    e.conditional_identity_nonobservation(changed, changed["occlusions"][0], terminal)

    def test_conditional_opt_in_does_not_replace_other_nulls_or_safety_failures(self):
        self.make_conditional_short_loss()
        self.contract["conditional_identity_rule"] = e.CONDITIONAL_IDENTITY
        trial = self.trials[0]
        surface = e._json(Path(trial["directory"]) / "flight_evaluation.json")
        for index, key, value in ((0, "prediction_observed", None), (0, "no_loss_during_short_occlusion", None),
                                  (1, "prediction_observed", None), (1, "hover_observed_for_long_occlusion", False)):
            with self.subTest(index=index, key=key):
                changed = deepcopy(surface)
                changed["occlusions"][index]["checks"][key] = value
                write_json(Path(trial["directory"]) / "flight_evaluation.json", changed)
                self.refresh(trial)
                self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_known_short_algorithm_failure_is_preserved_not_censored(self):
        def mutate(value):
            value["occlusions"][0]["checks"]["prediction_observed"] = False
            value["occlusions"][0]["result"] = value["acceptance"]["result"] = "FAIL"
        self.edit_surface(mutate, terminal_status="FAIL")
        report = self.run_slot()
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertEqual(report["original"]["terminal_status"], "FAIL")
        self.assertIn("surface:short:prediction_observed=FAIL", report["known_algorithm_failures"])
        self.assertFalse(report["original"]["occlusions"][0]["checks"]["prediction_observed"])

    def test_known_long_algorithm_failure_can_coexist_with_input_evidence(self):
        def mutate(value):
            value["occlusions"][1]["checks"]["detector_interruption_observed"] = False
            value["occlusions"][1]["result"] = value["acceptance"]["result"] = "FAIL"
        self.edit_surface(mutate, terminal_status="FAIL")
        report = self.run_slot()
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertIn("surface:long:detector_interruption_observed=FAIL", report["known_algorithm_failures"])

    def test_long_safety_failure_cannot_be_replaced(self):
        self.edit_surface(lambda value: value["occlusions"][1]["checks"].update(hover_observed_for_long_occlusion=False))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_existing_completed_detector_check_needs_no_replacement(self):
        def mutate(value):
            short = value["occlusions"][0]
            short["checks"]["detector_interruption_observed"] = True
            short["diagnostic_frames_inside"] = 3
            short["result"] = value["acceptance"]["result"] = "PASS"
        self.edit_surface(mutate, terminal_status="PASS")
        self.assertEqual(self.run_slot()["status"], e.NOT_APPLICABLE)

    def test_evaluable_short_with_known_long_prediction_failure_needs_no_null_replacement(self):
        def mutate(value):
            short, long = value["occlusions"]
            short["checks"]["detector_interruption_observed"] = True
            short["diagnostic_frames_inside"] = 3
            short["result"] = "PASS"
            long["checks"]["prediction_observed"] = False
            long["result"] = value["acceptance"]["result"] = "FAIL"
        self.edit_surface(mutate, terminal_status="FAIL", slot="person_combined")
        report = self.run_slot("person_combined")
        self.assertEqual(report["status"], e.NOT_APPLICABLE, report)
        self.assertEqual(report["known_algorithm_failures"], ["surface:long:prediction_observed=FAIL"])
        self.assertEqual(report["original"]["terminal_status"], "FAIL")
        self.assertFalse(report["original"]["occlusions"][1]["checks"]["prediction_observed"])
        self.assertNotIn("ready", report)
        matrix = e.evaluate_development_manifest(self.matrix_manifest(), self.contract)
        self.assertEqual(matrix["status"], e.CORROBORATED, matrix)
        self.assertEqual(matrix["known_algorithm_failures"], [{"slot_id": "person_combined", "failures": ["surface:long:prediction_observed=FAIL"]}])

    def test_evaluable_false_detector_is_known_failure_without_null_replacement(self):
        def mutate(value):
            short = value["occlusions"][0]
            short["checks"]["detector_interruption_observed"] = False
            short["diagnostic_frames_inside"] = 3
            short["result"] = value["acceptance"]["result"] = "FAIL"
        self.edit_surface(mutate, terminal_status="FAIL")
        report = self.run_slot()
        self.assertEqual(report["status"], e.NOT_APPLICABLE, report)
        self.assertEqual(report["known_algorithm_failures"], ["surface:short:detector_interruption_observed=FAIL"])
        self.assertFalse(report["original_detector_interruption_observed"])
        self.assertEqual(report["original"]["terminal_status"], "FAIL")
        self.edit_surface(lambda value: value["occlusions"][0].update(diagnostic_frames_inside=0))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_review_utc_schema_accepts_z_and_rejects_naive_nonzero_and_numeric(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        review["created_utc"] = "2026-11-03T00:01:00Z"
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.CORROBORATED)
        for invalid in ("2026-11-03T00:01:00", "2026-11-03T08:01:00+08:00", 1793664060):
            with self.subTest(timestamp=invalid):
                review["created_utc"] = invalid
                write_json(path, review)
                self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_review_cannot_predate_completed_extraction(self):
        path = self.reviews["person_dropout"]
        review = e._json(path)
        review["created_utc"] = "2026-11-02T23:59:59+00:00"
        write_json(path, review)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_source_clock_failure_remains_strict(self):
        path = Path(self.trials[0]["directory"]) / "px4_source_clock_report.json"
        write_json(path, {"evaluation_status": "FAIL"})
        self.refresh(self.trials[0])
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_clock_regression_rejected(self):
        self.edit_manifest(lambda value: value.update(clock_regression_count=1))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_unfinished_scan_rejected(self):
        self.edit_manifest(lambda value: value.update(all_selected_topics_scanned=False))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_changed_extractor_sha_rejected(self):
        self.edit_manifest(lambda value: value.update(tool_sha256="0" * 64))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_missing_raw_depth_opportunity_is_real_missing_evidence(self):
        self.edit_manifest(lambda value: value["opportunities"].remove(next(row for row in value["opportunities"] if row["topic"] == e.RAW_DEPTH)))
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_research_delivery_must_match_exact_source_drop_ledger(self):
        def mutate(value):
            row = next(row for row in value["opportunities"] if row["topic"] == e.RESEARCH_RGB and row["acquisition_ns"] == 31_600_000_000)
            row.update(acquisition_ns=31_400_000_000, header_ns=31_400_000_000, header_nanosec=400_000_000,
                       acquisition_stamp_s_decimal="31.4")
        self.edit_manifest(mutate)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_diagnostic_json_exact_source_must_match(self):
        def mutate(value):
            row = next(row for row in value["opportunities"] if row["topic"] == e.DIAGNOSTIC)
            row["original_diagnostic_json"] = json.dumps({"stamp_s": 31.0, "acquisition_ns": 1})
        self.edit_manifest(mutate)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_worker_can_skip_delivered_keep_frame_without_invalidating_input_evidence(self):
        def mutate(value):
            value["opportunities"].remove(next(row for row in value["opportunities"]
                                              if row["topic"] == e.DIAGNOSTIC and row["acquisition_ns"] == 31_000_000_000))
        self.edit_manifest(mutate)
        report = self.run_slot()
        self.assertEqual(report["status"], e.CORROBORATED, report)
        self.assertEqual(report["delivered_without_diagnostic_acquisition_ns"], [31_000_000_000])

    def test_diagnostic_for_undelivered_input_is_rejected(self):
        def mutate(value):
            row = next(row for row in value["opportunities"] if row["topic"] == e.DIAGNOSTIC)
            row.update(acquisition_ns=31_400_000_000, acquisition_stamp_s_decimal="31.4", original_stamp_s_decimal="31.4",
                       original_diagnostic_json=json.dumps({"stamp_s": 31.4, "acquisition_ns": 31_400_000_000}))
        self.edit_manifest(mutate)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_worker_silence_without_any_pre_window_diagnostic_remains_incomplete(self):
        def mutate(value):
            value["opportunities"] = [row for row in value["opportunities"]
                                      if not (row["topic"] == e.DIAGNOSTIC and row["acquisition_ns"] < 31_300_000_000)]
        self.edit_manifest(mutate)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_original_report_cannot_change_without_terminal_binding(self):
        path = Path(self.trials[0]["directory"]) / "flight_evaluation.json"
        value = e._json(path)
        value["occlusions"][0]["checks"]["prediction_observed"] = False
        write_json(path, value)
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_original_fault_source_hash_must_stay_bound(self):
        (self.source / "scripts/sensor_fault_bridge.py").write_text("changed source", encoding="utf-8")
        self.assertEqual(self.run_slot()["status"], e.INCOMPLETE)

    def test_validator_does_not_write_or_modify_fixture_inputs(self):
        before = {str(path): e._hash(path) for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(self.run_slot()["status"], e.CORROBORATED)
        after = {str(path): e._hash(path) for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
