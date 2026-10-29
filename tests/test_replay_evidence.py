"""File/source audit gates use synthetic reports, not real calibration or bags."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_replay_comparison import cli, cli_fixture, replay, seal, trial_fixture, write
from uav_tracking.replay_export import verify_state_cycles


PARAMETERS = {"gate_threshold":9.21, "process_acceleration_std":1., "measurement_noise_std":[.05,.05,.1],
              "initial_velocity_covariance":4., "default_dt":1./30., "max_age_s":.75}


def fixture(root, *, config=None, source_root=None, cls="person", seed=1000):
    """Explicit fake formal bindings for tests; no scientific parameter choice."""
    root = root.resolve()
    if config is None:
        config, source_root, _ = cli_fixture(root)
        for name in replay.EXPORT_SOURCE_FILES:
            path = source_root/name; path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():path.write_text("# PURE_EVIDENCE_FIXTURE_ONLY\n", encoding="utf-8")
        schema = "ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg"
        (source_root/schema).write_bytes((Path(__file__).resolve().parents[1]/schema).read_bytes())
        config["freeze_requirements"]["evaluation_source_hashes"] = {
            name:cli.file_sha256(source_root/name) for name in replay.EXPORT_SOURCE_FILES}
        freeze = config["freeze_requirements"]
        freeze["flight_source_hashes"].update({name:freeze["evaluation_source_hashes"][name] for name in replay.ONLINE_FLIGHT_SOURCE_FILES})
        plan_path = Path(freeze["final_engineering_plan_path"])
        plan = cli.load(plan_path); plan["source_hashes"] = deepcopy(freeze["flight_source_hashes"])
        plan.pop("plan_sha256"); plan["plan_sha256"] = replay.canonical_sha256(plan)
        write(plan_path, plan)
        freeze.update(final_engineering_plan_digest=plan["plan_sha256"],final_engineering_plan_file_sha256=cli.file_sha256(plan_path))
        seal(config)
    trial = trial_fixture(config, cls=cls, seed=seed)
    for name in ("measurements", "output_events", "task_events"):
        for row in trial[name]:
            for field in ("source_s", "available_s", "state_source_s"):
                if field in row:row[field] += 5.
    for row in trial["truth_samples"]:row["time_s"] += 5.
    trial["interval"].update(follow_start_s=6., alignment_end_s=5., recorded_clock_end_s=8.)
    trial["task_events"] = []
    records, pairs = [], []
    for index, (measurement, event) in enumerate(zip(trial["measurements"], trial["output_events"])):
        sequence = event["record_sequence"]
        measurement["record_sequence"] = sequence
        event.update(native_delivery_verified=True, diagnostic_proxy_available_s=event["available_s"])
        trial["task_events"].append({"record_sequence":sequence, "source_s":measurement["available_s"],
            "available_s":measurement["available_s"], "action":"bind" if index == 0 else "state",
            "target_uuid":"task-A", "track_id":7, "state":"tracking"})
        age = event["state_source_s"]-measurement["source_s"]
        wire_age = struct.unpack("f", struct.pack("f", age))[0]
        delivered = wire_age+event["available_s"]-event["state_source_s"]
        records.append({"record_sequence":sequence, "measurement_repeated":False, "update_reproduced":True,
            "output_reproduced":True, "mismatches":[], "acquisition_s":measurement["source_s"],
            "output_s":event["state_source_s"], "output_publication_s":event["source_s"],
            "reproduced_output":{"valid":True,"measurement_age_s":age,"output_measurement_source_s":measurement["source_s"]}})
        pairs.append({"diagnostic_record_sequence":sequence, "native_state_record_sequence":sequence-1,
            "native_state_received_sim_s":event["available_s"], "native_state_availability_s":event["available_s"],
            "native_state_measurement_age_s":wire_age, "delivered_measurement_age_s":delivered,
            "delivery_within_prediction_horizon":True})
    total = len(records)
    online = {"schema_version":1, "audit_kind":"ONLINE_NAVIGATION_DIAGNOSTIC_REPRODUCTION",
        "evaluation_status":"PASS", "online_equivalence_pass":True, "absolute_tolerance":1e-8,
        "relative_tolerance":0., "recorder_clock_future_tolerance_s":.05, "uses_ground_truth":False,
        "issues":[], "runtime_kf_parameters":PARAMETERS, "records":records,
        "navigation_estimator_source":{"sha256":config["freeze_requirements"]["evaluation_source_hashes"][
            "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py"]},
        "counts":{"diagnostics":total,"distinct_measurements":total,"repeated_measurements":0,
                  "updates_reproduced":total,"outputs_reproduced":total}}
    native = {"status":"PASS", "pairs":pairs, "diagnostic_count":total, "native_state_count":total,
        "differences":[], "numeric_contract":verify_state_cycles([], [])["numeric_contract"]}
    truth = {"alignment":{"rotation_policy":"declared_enu","rotation_world_from_map":np.eye(3).tolist(),
            "translation_world_from_map_m":[1.,-1.,.2], "calibration_start_s":0., "calibration_end_s":5.,
            "splits":{"calibration":{"pairs":100},"ego_holdout":{"pairs":20}}},
        "target_reference":"independent single actor ground-footprint/model origin", "target_actor":"target_"+cls,
        "position_anchor_m":[0.,0.,0.],"velocity_symmetric_derivative_half_window_s":.05}
    trial["export_audit"] = {"scope":"FORMAL", "status":"PASS", "online_equivalence":"PASS", "native_state_audit":"PASS",
        "source_hashes":deepcopy(config["freeze_requirements"]["evaluation_source_hashes"]),
        "diagnostic_cycles":total,"deduplicated_measurements":total,"cached_measurement_repeats":0,
        "fixed_online_constructor_parameters":PARAMETERS,"recorded_archive_message_count":total*10,
        "bag_reader":{"clock_recorded":True,"clock_records_preserved":True,"clock_samples_read":100,
                      "source_bag_read_only":True,"read_errors":{},"unavailable_types":{}}}
    directory = root/trial["slot_id"]; directory.mkdir()
    path = directory/"arrays.json"
    documents = {"online_equivalence.json":online,"native_state_audit.json":native,"truth_alignment.json":truth}
    bind_payload(trial, documents)
    save(path, trial, documents)
    return config, source_root, path, trial, documents


def bind_payload(trial, documents):
    binding = {"schema_version":1, "canonical_payload_sha256":replay.replay_payload_sha256(trial),
               "excluded_circular_audit_fields":sorted(replay.PAYLOAD_EXCLUDED_FIELDS)}
    for document in documents.values():document["replay_payload_binding"] = deepcopy(binding)


def save(path, trial, documents):
    for name, value in documents.items():
        write(path.parent/name, value)
        trial[replay.EXPORT_SIDECARS[name]] = cli.file_sha256(path.parent/name)
    write(path, trial)


class ReplayEvidenceTests(unittest.TestCase):
    def test_resealed_arrays_cannot_substitute_measurement_identity_covariance_tasks_outputs_or_truth(self):
        for defect in ("position", "geometry_R", "pose_R", "measurement_uuid", "measurement_track", "reference_valid",
                       "measurement_time", "task_identity", "task_action", "output_time", "truth", "interval"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                config, source_root, path, trial, documents = fixture(Path(tmp))
                if defect == "position":trial["measurements"][0]["position_world_m"][0] += 100.
                elif defect == "geometry_R":trial["measurements"][0]["R_geometry_world_m2"][0][0] *= 2.
                elif defect == "pose_R":trial["measurements"][0]["R_pose_world_m2"][0][0] += .1
                elif defect == "measurement_uuid":trial["measurements"][0]["target_uuid"] = "substituted"
                elif defect == "measurement_track":trial["measurements"][0]["track_id"] += 1
                elif defect == "reference_valid":trial["measurements"][0]["reference_valid"] = False
                elif defect == "measurement_time":trial["measurements"][0]["available_s"] += .01
                elif defect == "task_identity":trial["task_events"][0]["target_uuid"] = "substituted"
                elif defect == "task_action":trial["task_events"][0]["action"] = "clear"
                elif defect == "output_time":trial["output_events"][0]["available_s"] += .01
                elif defect == "truth":trial["truth_samples"][0]["position_world_m"][0] += 100.
                else:trial["interval"]["recorded_clock_end_s"] += .1
                save(path, trial, documents)
                with self.assertRaisesRegex(ValueError, "exact measurement/task/output/truth"):
                    cli.verify_export_evidence(path, trial, config, source_root=source_root)

    def test_development_gate_is_explicit_and_cannot_promote_a_formal_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, source_root, path, trial, documents = fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, "Development audit cannot"):
                cli.verify_export_evidence(path, trial, config, source_root=source_root, development_only=True)
            trial.update(seed=4,slot_id="DEVELOPMENT_ONLY_FIXTURE",engineering_status="DEVELOPMENT_ONLY_NO_FORMAL_VERDICT")
            trial["export_audit"]["scope"] = "DEVELOPMENT_ONLY"
            bind_payload(trial, documents); save(path, trial, documents)
            with self.assertRaises(ValueError):cli.verify_export_evidence(path, trial, config, source_root=source_root)
            evidence = cli.verify_export_evidence(path, trial, config, source_root=source_root, development_only=True)
            self.assertEqual(evidence["kind"], replay.DEVELOPMENT_EXPORT_EVIDENCE_KIND)
            self.assertTrue(replay.export_evidence_issues(trial, config, evidence))

    def test_all_three_actual_files_sources_and_cycle_rows_are_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, source_root, path, trial, _ = fixture(Path(tmp))
            evidence = cli.verify_export_evidence(path, trial, config, source_root=source_root)
            report = replay.replay_trial(trial, config, export_evidence=evidence)
            self.assertEqual(report["evaluation_status"], replay.VERIFIED_REPLAY_STATUS)
            self.assertEqual(report["pending"], [])
            self.assertEqual(report["engineering_status"], "FAIL")
            self.assertEqual(evidence["counts"]["output_cycles"], 11)
            self.assertEqual(set(evidence["sidecar_sha256"]), set(replay.EXPORT_SIDECARS))
            summary = replay.paired_trial_summary([report], config)
            self.assertEqual(summary["verified_trial_reports"], 1)
            self.assertFalse(summary["complete_verified_matrix"])

    def test_missing_or_changed_file_and_changed_executable_source_are_rejected(self):
        for defect in ("missing", "changed", "source", "message"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                config, source_root, path, trial, documents = fixture(Path(tmp))
                if defect == "missing":(path.parent/"online_equivalence.json").unlink()
                elif defect == "changed":write(path.parent/"native_state_audit.json", {"status":"PASS"})
                elif defect == "source":(source_root/replay.EXPORT_SOURCE_FILES[0]).write_text("changed")
                else:
                    schema = source_root/"ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg"
                    schema.write_text(schema.read_text().replace("float32 prediction_age_s", "float64 prediction_age_s"))
                with self.assertRaises((ValueError, FileNotFoundError)):
                    cli.verify_export_evidence(path, trial, config, source_root=source_root)

    def test_resealed_pass_reports_cannot_hide_missing_counts_rows_sources_timing_or_truth_contract(self):
        cases = ("empty_pass", "online_count", "online_rows", "online_repeat", "online_source", "online_tolerance", "uses_truth",
                 "native_reuse", "native_age", "native_count", "native_wire", "clock", "scope",
                 "truth_rotation", "truth_duration", "truth_derivative", "truth_actor", "delivery", "parameters", "flight_source")
        for defect in cases:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                config, source_root, path, trial, docs = fixture(Path(tmp))
                online, native, truth = (docs[key] for key in ("online_equivalence.json","native_state_audit.json","truth_alignment.json"))
                if defect == "empty_pass":docs["online_equivalence.json"] = {"evaluation_status":"PASS", "online_equivalence_pass":True}
                elif defect == "online_count":online["counts"]["outputs_reproduced"] -= 1
                elif defect == "online_rows":online["records"].pop()
                elif defect == "online_repeat":online["records"][0]["update_reproduced"] = False
                elif defect == "online_source":online["navigation_estimator_source"]["sha256"] = "a"*64
                elif defect == "online_tolerance":online["absolute_tolerance"] = 1e-5
                elif defect == "uses_truth":online["uses_ground_truth"] = True
                elif defect == "native_reuse":native["pairs"][1]["native_state_record_sequence"] = native["pairs"][0]["native_state_record_sequence"]
                elif defect == "native_age":native["pairs"][0]["native_state_measurement_age_s"] += 1e-9
                elif defect == "native_count":native["native_state_count"] -= 1
                elif defect == "native_wire":native["numeric_contract"]["measurement_age_s"] = "float64"
                elif defect == "clock":trial["export_audit"]["bag_reader"]["clock_records_preserved"] = False
                elif defect == "scope":trial["export_audit"]["scope"] = "DEVELOPMENT_ONLY"
                elif defect == "truth_rotation":truth["alignment"]["rotation_policy"] = "target_fit"
                elif defect == "truth_duration":truth["alignment"]["calibration_start_s"] = 1.
                elif defect == "truth_derivative":truth["velocity_symmetric_derivative_half_window_s"] = .1
                elif defect == "truth_actor":truth["target_actor"] = "nearest_actor"
                elif defect == "delivery":trial["output_events"][0]["available_s"] -= .01
                elif defect == "parameters":online["runtime_kf_parameters"] = {"gate_threshold":9.21,"max_age_s":.75}
                elif defect == "flight_source":config["freeze_requirements"]["flight_source_hashes"][replay.ONLINE_FLIGHT_SOURCE_FILES[0]] = "a"*64
                save(path, trial, docs)
                with self.assertRaises(ValueError):cli.verify_export_evidence(path, trial, config, source_root=source_root)

    def test_core_never_promotes_a_bool_or_another_trial_receipt_and_metrics_still_compute(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, source_root, path, trial, _ = fixture(Path(tmp))
            baseline = replay.replay_trial(trial, config)
            evidence = cli.verify_export_evidence(path, trial, config, source_root=source_root)
            for wrong in (True, {"status":"PASS","verified":True}, {**evidence,"counts":{}},
                          {**evidence,"trial_input_sha256":"a"*64}):
                report = replay.replay_trial(trial, config, export_evidence=wrong)
                self.assertEqual(report["evaluation_status"], "COMPUTED_PENDING_ONLINE_EQUIVALENCE")
                self.assertEqual(report["metrics"], baseline["metrics"])
                self.assertTrue(report["export_evidence_issues"])

    def test_cli_keeps_computed_pending_reports_when_sidecar_evidence_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config, source_root, path, trial, _ = fixture(root)
            (path.parent/"online_equivalence.json").unlink()
            manifest = {"schema_version":1,"slots":{slot:None for slot in replay.scheduled_slots()}}
            manifest["slots"][trial["slot_id"]] = {"path":str(path),"sha256":cli.file_sha256(path)}
            manifest_path = root/"inputs.json"; write(manifest_path, manifest)
            summary = cli.run(config, manifest_path, root/"run", source_root=source_root)
            self.assertEqual(summary["available_trial_reports"], 1)
            self.assertEqual(summary["verified_trial_reports"], 0)
            self.assertEqual(len(summary["missing_or_invalid_inputs"]), 19)
            report = cli.load(root/"run"/(trial["slot_id"]+".json"))
            self.assertEqual(report["evaluation_status"], "COMPUTED_PENDING_ONLINE_EQUIVALENCE")
            self.assertTrue(report["export_evidence_issues"])
            artifact = summary["trial_report_artifacts"][0]
            self.assertEqual(artifact["slot_id"],trial["slot_id"])
            self.assertEqual(artifact["sha256"],cli.file_sha256(root/"run"/artifact["path"]))
            config_artifact = summary["registered_configuration_artifact"]
            self.assertEqual(config_artifact["sha256"],cli.file_sha256(root/"run"/config_artifact["path"]))

    def test_cli_exit_zero_requires_a_complete_verified_matrix(self):
        for complete, expected in ((False, 2), (True, 0)):
            with self.subTest(complete=complete), patch.object(cli,"load", return_value={}), \
                    patch.object(cli,"run", return_value={"complete_verified_matrix":complete,"missing_or_invalid_inputs":[]}), \
                    redirect_stdout(io.StringIO()):
                result = cli.main(["run","--configuration","fixture.json","--inputs-manifest","fixture-manifest.json","--output","unused"])
                self.assertEqual(result, expected)

    def test_complete_pair_claim_requires_every_audited_slot_and_preserves_failed_flights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config, source_root, path, trial, _ = fixture(root)
            reports = []
            for cls in replay.CLASSES:
                for seed in replay.SEEDS:
                    if cls != "person" or seed != 1000:
                        _, _, path, trial, _ = fixture(root, config=config, source_root=source_root, cls=cls, seed=seed)
                    evidence = cli.verify_export_evidence(path, trial, config, source_root=source_root)
                    reports.append(replay.replay_trial(trial, config, export_evidence=evidence))
            summary = replay.paired_trial_summary(reports, config)
            self.assertEqual(summary["verified_trial_reports"], 20)
            self.assertTrue(summary["complete_verified_matrix"])
            self.assertEqual(summary["evaluation_status"], replay.VERIFIED_REPLAY_STATUS)
            self.assertEqual(summary["classes"]["person"]["engineering_status_counts"], {"FAIL":10})
            reports[0]["export_evidence"] = None
            pending = replay.paired_trial_summary(reports, config)
            self.assertEqual(pending["verified_trial_reports"], 19)
            self.assertFalse(pending["complete_verified_matrix"])
            contrast = pending["classes"]["person"]["contrasts"]["geometry_adaptive_kf_minus_fixed_kf"]
            self.assertEqual(contrast["finite_pairs"], 10)
            self.assertEqual(contrast["verified_pairs"], 9)
            self.assertFalse(contrast["complete_ten_pair_matrix"])


if __name__ == "__main__":unittest.main()
