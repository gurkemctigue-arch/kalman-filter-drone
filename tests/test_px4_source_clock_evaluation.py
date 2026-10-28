"""Clock claims need independent raw/diagnostic/odometry correspondence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_px4_source_clock as audit


def configuration():
    return {"px4_time_mode":"source_sim", "odometry_timestamp_mode":"source_sim", "use_sim_time":True,
            "uxrce_dds_synct":0, "odometry_source_max_age_s":.50, "odometry_source_max_future_s":.05,
            "vehicle_odometry_topic":audit.RAW_TOPIC, "vehicle_odom_topic":audit.ODOMETRY_TOPIC,
            "odometry_timing_topic":audit.TIMING_TOPIC}


def stamp(value):
    sec, nanosec = divmod(round(value*1e9), 1_000_000_000)
    return NS(sec=sec, nanosec=nanosec)


def clock_record(value):
    return audit.Record("/clock", value, NS(clock=stamp(value)), value)


def triplet(source, *, receipt=None, sample=None, publication=None, counter=0, locked=False,
            accepted=True, reason="validated_source_stamp", source_valid=True, frame_valid=True):
    receipt = source+.02 if receipt is None else receipt
    sample = round(source*1e6) if sample is None else sample
    publication = sample+4_000 if publication is None else publication
    raw = NS(timestamp_sample=sample, timestamp=publication, reset_counter=counter,
             pose_frame=1, velocity_frame=1, position=[1+source/10, 2., -3.], velocity=[.1, .2, .3], q=[1., 0., 0., 0.])
    p, v, q = audit.px4_odometry_to_enu(raw)
    odom = NS(header=NS(stamp=stamp(sample*1e-6), frame_id="map"), child_frame_id="base_link",
              pose=NS(pose=NS(position=NS(x=p[0], y=p[1], z=p[2]), orientation=NS(x=q[0], y=q[1], z=q[2], w=q[3]))),
              twist=NS(twist=NS(linear=NS(x=v[0], y=v[1], z=v[2]))))
    payload = {"schema_version":1, "mode":"source_sim", "accepted":accepted, "reason":reason,
               "output_s":receipt, "receipt_ros_s":receipt, "source_sample_s":sample*1e-6,
               "source_publication_s":publication*1e-6, "source_to_receipt_s":receipt-sample*1e-6,
               "odometry_header_s":sample*1e-6 if accepted else None, "source_time_valid":source_valid,
               "reset_counter":counter, "frame_locked":locked}
    if source_valid:
        payload.update(vehicle_frame_valid=frame_valid,
                       vehicle_frame_reason="vehicle_frame_valid" if frame_valid else reason)
    result = [audit.Record(audit.RAW_TOPIC, receipt, raw, receipt),
              audit.Record(audit.TIMING_TOPIC, receipt, NS(data=json.dumps(payload)), receipt)]
    if accepted:
        result.append(audit.Record(audit.ODOMETRY_TOPIC, sample*1e-6, odom, receipt+.005))
    return result


def clean_records():
    result = [clock_record(10.)]
    for i in range(4):
        result.extend(triplet(10.+i*.1))
        result.append(clock_record(10.03+i*.1))
    result.append(clock_record(10.35))
    return result


def mutate_diagnostic(row, **updates):
    payload = json.loads(row.message.data)
    payload.update(updates)
    row.message.data = json.dumps(payload)


class SourceClockEvaluationTests(unittest.TestCase):
    def test_complete_source_receipt_and_delivery_are_distinct_and_pass(self):
        report = audit.evaluate(clean_records(), configuration())
        self.assertEqual(report["evaluation_status"], "PASS", report)
        self.assertTrue(report["source_clock_pass"])
        self.assertTrue(report["clock_domain_valid"])
        self.assertTrue(report["vehicle_frame_continuity_valid"])
        self.assertEqual(report["counts"]["independently_matched_triplets"], 4)
        self.assertAlmostEqual(report["metrics"]["source_to_adapter_receipt_s"]["mean"], .02)
        self.assertAlmostEqual(report["metrics"]["source_to_odometry_recorder_s"]["mean"], .025)
        self.assertAlmostEqual(report["continuity"]["matched_adapted_odometry"]["tail_s"], .025)

    def test_correct_wrong_domain_rejection_is_a_failed_clock_trial(self):
        rows = clean_records()
        rows.extend(triplet(10.4, sample=1_793_219_000_000_000, publication=1_793_219_000_004_000,
            accepted=False, source_valid=False, reason="future_or_wrong_domain_source_timestamp"))
        rows.append(clock_record(10.45))
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertEqual(report["evaluation_status"], "FAIL", report)
        self.assertFalse(report["clock_domain_valid"])
        self.assertEqual(report["failures"]["source_rejected:future_or_wrong_domain_source_timestamp"], 1)

    def test_claimed_acceptance_cannot_bless_wrong_domain(self):
        rows = clean_records()
        rows.extend(triplet(10.4, sample=100_000_000, publication=100_004_000))
        rows.append(clock_record(10.45))
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertFalse(report["clock_domain_valid"])
        self.assertIn("diagnostic_disagrees_with_independent_clock_check", report["failures"])

    def test_matching_diagnostic_claim_without_raw_is_incomplete(self):
        rows = [row for row in clean_records() if row.topic not in (audit.RAW_TOPIC, audit.ODOMETRY_TOPIC)]
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertIsNone(report["clock_domain_valid"])
        self.assertEqual(report["incomplete_evidence"]["diagnostic_without_matching_raw_px4"], 4)

    def test_raw_and_diagnostic_without_adapted_output_cannot_pass(self):
        rows = [row for row in clean_records() if row.topic != audit.ODOMETRY_TOPIC]
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertTrue(report["clock_domain_valid"])
        self.assertEqual(report["incomplete_evidence"]["accepted_diagnostic_without_matching_adapted_odometry"], 4)

    def test_receipt_stamped_output_is_not_source_stamped_correspondence(self):
        rows = clean_records()
        for row in rows:
            if row.topic == audit.ODOMETRY_TOPIC:
                row.message.header.stamp = stamp(row.received_sim_s)
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertEqual(report["counts"]["independently_matched_triplets"], 0)

    def test_output_content_from_another_sample_cannot_satisfy_a_matching_header(self):
        rows = clean_records()
        for row in rows:
            if row.topic == audit.ODOMETRY_TOPIC:
                row.message.pose.pose.position.x += 2.
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertEqual(report["counts"]["independently_matched_triplets"], 0)

    def test_wrong_frame_and_child_origin_cannot_match(self):
        for attribute, value in (("frame_id", "odom"), ("child_frame_id", "model_origin")):
            with self.subTest(attribute=attribute):
                rows = clean_records()
                for row in rows:
                    if row.topic == audit.ODOMETRY_TOPIC:
                        if attribute == "frame_id":
                            row.message.header.frame_id = value
                        else:
                            row.message.child_frame_id = value
                self.assertFalse(audit.evaluate(rows, configuration())["source_clock_pass"])

    def test_source_regression_latches_and_cannot_resume_merely_on_a_later_stamp(self):
        rows = clean_records()
        rows.extend(triplet(10.4, sample=9_000_000, publication=9_004_000, accepted=False,
            source_valid=False, reason="source_clock_regression_restart_required"))
        # Online claim improperly resumed instead of keeping the reset latch.
        rows.extend(triplet(10.5))
        rows.append(clock_record(10.55))
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["clock_domain_valid"])
        self.assertIn("diagnostic_source_validity_disagrees", report["failures"])
        self.assertEqual(report["independent_reason_counts"]["source_clock_regression_restart_required"], 2)

    def test_recorded_clock_regression_is_not_hidden_by_monotonic_source_headers(self):
        rows = clean_records()+[clock_record(1.)]
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertFalse(report["clock_domain_valid"])
        self.assertEqual(report["failures"]["recorded_ros_clock_regression"], 1)

    def test_full_clock_tail_counts_stream_loss(self):
        rows = clean_records()+[clock_record(12.)]
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertGreater(report["continuity"]["matched_adapted_odometry"]["tail_s"], 1.5)
        self.assertIn("delivery_loss:matched_adapted_odometry", report["failures"])
        self.assertIn("delivery_loss:raw_px4", report["failures"])

    def test_late_delivery_is_retained_instead_of_backdating_to_source(self):
        rows = clean_records()
        for index, row in enumerate(rows):
            if row.topic == audit.ODOMETRY_TOPIC:
                rows[index] = audit.Record(row.topic, row.time_s, row.message, row.received_sim_s+.7)
        rows.append(clock_record(11.1))
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertIn("odometry_delivery_outside_source_freshness", report["failures"])
        self.assertAlmostEqual(report["metrics"]["source_to_odometry_recorder_s"]["mean"], .725)

    def test_missing_recorded_delivery_cannot_fall_back_to_the_header(self):
        rows = clean_records()
        for index, row in enumerate(rows):
            if row.topic == audit.ODOMETRY_TOPIC:
                rows[index] = audit.Record(row.topic, row.time_s, row.message, None)
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertIn("missing_recorded_delivery_clock:"+audit.ODOMETRY_TOPIC, report["incomplete_evidence"])

    def test_frame_reset_is_a_separate_failure_with_valid_clock_domain(self):
        rows = [clock_record(10.)]
        for index in range(3):
            rows.extend(triplet(10.+index*.1, locked=True))
            rows.append(clock_record(10.03+index*.1))
        rows.extend(triplet(10.3, counter=1, locked=True, accepted=False,
            reason="vehicle_frame_reset_restart_required", source_valid=True, frame_valid=False))
        rows.append(clock_record(10.35))
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertTrue(report["clock_domain_valid"])
        self.assertFalse(report["vehicle_frame_continuity_valid"])
        self.assertNotIn("diagnostic_disagrees_with_independent_clock_check", report["failures"])
        self.assertEqual(report["vehicle_frame_failures"]["vehicle_frame_reset_restart_required"], 1)

    def test_counter_wrap_is_a_reset_and_unlocked_startup_changes_are_allowed(self):
        for locked, expected in ((False, "PASS"), (True, "FAIL")):
            with self.subTest(locked=locked):
                rows = [clock_record(10.)]
                for index, counter in enumerate((255, 255, 255, 0)):
                    rows.extend(triplet(10.+index*.1, counter=counter, locked=locked,
                        accepted=not (locked and index==3),
                        reason="vehicle_frame_reset_restart_required" if locked and index==3 else "validated_source_stamp",
                        frame_valid=not (locked and index==3)))
                    rows.append(clock_record(10.03+index*.1))
                rows.append(clock_record(10.35))
                report = audit.evaluate(rows, configuration())
                self.assertEqual(report["evaluation_status"], expected, report)

    def test_frame_lock_cannot_be_cleared_after_activation(self):
        rows = clean_records()
        first = True
        for row in rows:
            if row.topic == audit.TIMING_TOPIC:
                mutate_diagnostic(row, frame_locked=first)
                first = False
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["vehicle_frame_continuity_valid"])
        self.assertIn("vehicle_frame_lock_was_cleared", report["failures"])

    def test_missing_frame_guard_claim_is_incomplete(self):
        rows = clean_records()
        for row in rows:
            if row.topic == audit.TIMING_TOPIC:
                payload = json.loads(row.message.data)
                del payload["frame_locked"]
                row.message.data = json.dumps(payload)
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertIsNone(report["vehicle_frame_continuity_valid"])

    def test_no_clock_records_cannot_be_replaced_by_claimed_diagnostic_times(self):
        rows = [row for row in clean_records() if row.topic != "/clock"]
        report = audit.evaluate(rows, configuration())
        self.assertFalse(report["source_clock_pass"])
        self.assertIn("missing_recorded_clock", report["incomplete_evidence"])

    def test_evaluator_provenance_hashes_actual_source_and_helpers(self):
        provenance = audit.evaluation_source_provenance()
        self.assertEqual(provenance["script_sha256"], hashlib.sha256(Path(audit.__file__).read_bytes()).hexdigest())
        self.assertEqual(len(provenance["dependencies"]), 4)
        for path, digest in provenance["dependencies"].items():
            self.assertEqual(digest, hashlib.sha256(Path(path).read_bytes()).hexdigest())


class RecordedClockConfigurationTests(unittest.TestCase):
    def write_configuration(self, root):
        config = configuration()
        (root/"configuration").mkdir()
        (root/"run_config.json").write_text(json.dumps({"px4_time_mode":config.pop("px4_time_mode")}), encoding="utf-8")
        synct = config.pop("uxrce_dds_synct")
        (root/"configuration/runtime_parameters.yaml").write_text(yaml.safe_dump({"uav_tracking_px4_adapter":{"ros__parameters":config}}), encoding="utf-8")
        (root/"configuration/px4_parameters.json").write_text(json.dumps({"explicit_environment_overrides":{"UXRCE_DDS_SYNCT":synct}}), encoding="utf-8")

    def test_requires_actual_recorded_source_sim_and_startup_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_configuration(root)
            config = audit.recorded_configuration(root)
            self.assertEqual(config["odometry_timestamp_mode"], "source_sim")
            self.assertEqual(len(config["recorded_configuration_evidence"]), 3)
            (root/"run_config.json").write_text('{"px4_time_mode":"receipt"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                audit.recorded_configuration(root)

    def test_missing_bounds_and_relaxed_original_bounds_are_rejected(self):
        for key, value in (("odometry_source_max_age_s", None), ("odometry_source_max_age_s", 1.),
                           ("odometry_source_max_future_s", .2), ("uxrce_dds_synct", 1),
                           ("use_sim_time", False), ("odometry_timing_topic", None)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                audit.evaluate(clean_records(), {**configuration(), key:value})

    def test_cli_without_recorded_configuration_writes_incomplete_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/"report.json"
            self.assertEqual(audit.main([str(root), "--output", str(output)]), 2)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["evaluation_status"], "INCOMPLETE")
            self.assertFalse(report["source_clock_pass"])
            self.assertIn("evaluation_source", report)


if __name__ == "__main__":
    unittest.main()
