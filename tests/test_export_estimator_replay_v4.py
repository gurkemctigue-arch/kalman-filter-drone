"""Exporter fixtures use synthetic records and mocked ROS reads, never bags."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np
import yaml

from tests.test_replay_export import cycle, native

ROOT = Path(__file__).resolve().parents[1]
_paths = list(sys.path)
try:
    sys.path.insert(0, str(ROOT/"scripts"))
    SPEC = importlib.util.spec_from_file_location("export_estimator_replay_fixture", ROOT/"scripts/export_estimator_replay_v4.py")
    cli = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(cli)
finally:
    sys.path[:] = _paths


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def seal_terminal(terminal):
    terminal["record_sha256"] = cli.canonical_sha256({k:v for k, v in terminal.items() if k != "record_sha256"})


def formal_fixture(root):
    trial = (root/"trial").resolve(); trial.mkdir()
    raw = {"seed":1000, "target_class":"person", "stage":1, "command_mode":"velocity", "multi_target":False}
    for relative in ("run_config.json", "bag_integrity.json", "configuration/runtime_parameters.yaml", "rosbag/metadata.yaml"):
        write(trial/relative, raw if relative == "run_config.json" else {"scope":"PURE_SYNTHETIC_FIXTURE_ONLY"})
    slot = "person_stage1_velocity_seed1000"
    plan = {"plan_sha256":"p"*64, "output":str(root/"plan"), "trials":[
        {"id":slot, "directory":str(trial), "group":"stage1_velocity", "target_class":"person", "seed":1000}]}
    plan_path = root/"plan.json"; write(plan_path, plan)
    terminal = {"id":slot, "plan_sha256":plan["plan_sha256"], "status":"FAIL", "started_utc":"2026-10-28T00:00:00Z",
        "artifact_hashes":{p.relative_to(trial).as_posix():cli.file_sha256(p) for p in trial.rglob("*") if p.is_file()}}
    seal_terminal(terminal)
    terminal_path = Path(plan["output"])/"slots"/(slot+".json"); write(terminal_path, terminal)
    sources = {"fixture/export.py":"a"*64}
    registration = {"freeze_requirements":{"evaluation_source_hashes":sources, "final_engineering_plan_path":str(plan_path)}}
    return trial, raw, slot, plan, terminal_path, terminal, registration, sources


def stamp(value):
    sec = int(value); return NS(sec=sec, nanosec=int(round((value-sec)*1e9)))


def record(topic, sequence, receipt, message):
    return cli.bag_tools.Record(topic, receipt, message, receipt, sequence)


def recorded_fixture(*, corrupt_output=False):
    row = cycle(3)
    row.update(reference_kind="person_ground_contact", heading_source="not_required",
        initial_velocity_world_mps=[0.,0.,0.], fusion_accepted=True, fusion_reason="initialized",
        state_reason="tracking",
        output_covariance_world_6x6=np.diag([.11,.11,.11,4.,4.,4.]).tolist())
    if corrupt_output:row["output_position_world_m"][0] += 2.
    state = native(row)
    vector = lambda xyz:NS(x=xyz[0], y=xyz[1], z=xyz[2])
    message = NS(header=NS(stamp=stamp(row["output_s"]), frame_id="map"), target_uuid=state["target_uuid"],
        track_id=state["track_id"], state=state["state"], position_m=vector(state["position_world_m"]),
        velocity_mps=vector(state["velocity_world_mps"]), prediction_age_s=0.,
        covariance=np.asarray(state["covariance_world_6x6"]).reshape(-1).tolist())
    return [record("/clock", 0, 0., NS(clock=stamp(0.))),
        record("/tracking/flight_phase", 1, .5, NS(data="FOLLOW: fixture; source_sim_s=0.5")),
        record("/clock", 2, 1.04, NS(clock=stamp(1.04))),
        record(cli.DIAGNOSTIC, 3, 1.04, NS(data=json.dumps(row))),
        record("/clock", 4, 2., NS(clock=stamp(2.))), record(cli.NATIVE, 5, 2., message),
        record("/clock", 6, 4., NS(clock=stamp(4.)))]


class ExportEstimatorReplayTests(unittest.TestCase):
    def test_formal_binding_preserves_failed_slot_and_binds_every_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial, raw, slot, plan, path, terminal, registration, sources = formal_fixture(Path(tmp))
            with patch.object(cli, "validate_registered_config", return_value={"registered_utc":datetime(2026,10,20,tzinfo=timezone.utc)}), \
                 patch.object(cli, "verify_registration_artifacts"):
                _, _, result = cli.formal_slot(trial, raw, registration, slot, sources)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["record_sha256"], terminal["record_sha256"])

    def test_wrong_slot_status_class_seed_late_registration_or_changed_artifact_is_rejected(self):
        for defect in ("id", "status", "class", "seed", "late", "artifact", "missing_binding", "evaluation_revision"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                trial, raw, slot, plan, path, terminal, registration, sources = formal_fixture(Path(tmp))
                if defect == "id":terminal["id"] = "other-slot"
                elif defect == "status":terminal["status"] = "RUNNING"
                elif defect == "class":raw["target_class"] = "car"
                elif defect == "seed":raw["seed"] = 1001
                elif defect == "late":terminal["started_utc"] = "2026-10-19T00:00:00Z"
                elif defect == "artifact":write(trial/"bag_integrity.json", {"changed":True})
                elif defect == "missing_binding":del terminal["artifact_hashes"]["configuration/runtime_parameters.yaml"]
                elif defect == "evaluation_revision":registration["freeze_requirements"]["evaluation_source_hashes"] = {}
                seal_terminal(terminal); write(path, terminal)
                with patch.object(cli, "validate_registered_config", return_value={"registered_utc":datetime(2026,10,20,tzinfo=timezone.utc)}), \
                     patch.object(cli, "verify_registration_artifacts"), self.assertRaises(ValueError):
                    cli.formal_slot(trial, raw, registration, slot, sources)

    def test_registration_must_precede_first_selected_slot_and_nested_interruption_start_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial, raw, slot, plan, path, terminal, registration, sources = formal_fixture(Path(tmp))
            terminal.update(status="INTERRUPTED", started={"started_utc":terminal.pop("started_utc")})
            seal_terminal(terminal); write(path, terminal)
            with patch.object(cli, "validate_registered_config", return_value={"registered_utc":datetime(2026,10,20,tzinfo=timezone.utc)}), \
                 patch.object(cli, "verify_registration_artifacts"):
                self.assertEqual(cli.formal_slot(trial, raw, registration, slot, sources)[2]["started_utc"], "2026-10-28T00:00:00Z")
                other = "car_stage1_velocity_seed1000"
                plan["trials"].append({"id":other, "group":"stage1_velocity"})
                write(Path(registration["freeze_requirements"]["final_engineering_plan_path"]), plan)
                write(Path(plan["output"])/"slots"/(other+".started.json"), {"started_utc":"2026-10-18T00:00:00Z"})
                with self.assertRaisesRegex(ValueError, "first selected"):
                    cli.formal_slot(trial, raw, registration, slot, sources)

    def test_held_out_missing_or_draft_registration_and_string_seed_stop_before_ros_read(self):
        for defect in ("missing", "draft", "string_seed"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                trial, raw, slot, *_ = formal_fixture(Path(tmp))
                registration = None
                if defect == "draft":
                    registration = Path(tmp)/"draft.json"; write(registration, {"schema_version":1, "status":"DRAFT"})
                if defect == "string_seed":raw["seed"] = "1000"; write(trial/"run_config.json", raw)
                with patch.object(cli.bag_tools, "read_rosbag", side_effect=AssertionError("held-out bag opened")) as reader:
                    with self.assertRaises(ValueError):cli.export(trial, Path(tmp)/"new", registration=registration, slot_id=slot)
                reader.assert_not_called()

    def test_clock_only_tail_and_actual_native_delivery_are_preserved(self):
        diagnostics, states, interval = cli.recorded_inputs(recorded_fixture())
        self.assertEqual(interval, {"follow_start_s":.5, "recorded_clock_end_s":4.})
        self.assertEqual(diagnostics[0]["record_sequence"], 3)
        self.assertEqual(states[0]["received_sim_s"], 2.)
        self.assertEqual(states[0]["measurement_age_s"], 0.)
        self.assertEqual(states[0]["frame_id"], "map")

    def test_missing_regressed_or_nonfinite_full_clock_is_rejected(self):
        for defect in ("missing", "regressed", "nonfinite"):
            rows = recorded_fixture()
            if defect == "missing":rows = [row for row in rows if row.topic != "/clock"]
            elif defect == "regressed":rows[-1].message.clock = stamp(1.)
            else:rows[-1].message.clock = NS(sec=float("nan"), nanosec=0)
            with self.subTest(defect=defect), self.assertRaises(ValueError):cli.recorded_inputs(rows)

    def test_development_export_wires_online_audit_native_availability_and_full_clock(self):
        self._run_export_fixture(False)

    def test_corrupt_online_output_retains_fail_instead_of_certifying_normalization(self):
        self._run_export_fixture(True)

    def test_archive_requires_hashed_unique_files_and_complete_native_count_check(self):
        for defect in (None, "empty", "native_read", "count", "metadata_files", "bytes"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                trial = Path(tmp).resolve(); bag = trial/"rosbag"; bag.mkdir()
                compressed = bag/"synthetic.db3.zstd"
                compressed.write_bytes(b"PURE FIXTURE; NOT A REAL BAG OR ZSTD FRAME")
                metadata = {"rosbag2_bagfile_information":{"relative_file_paths":[compressed.name]}}
                metadata_path = bag/"metadata.yaml"; metadata_path.write_text(yaml.safe_dump(metadata))
                raw = {"status":"PASS", "message_count":1, "topic_counts":{"/clock":1}}
                integrity = {"status":"PASS", "policy":"ext4_sqlite_close_standard_zstd_verified_native_read",
                    "compressed_files":[{"path":compressed.name, "sha256":cli.file_sha256(compressed)}],
                    "published_metadata_sha256":cli.file_sha256(metadata_path), "raw_validation":raw,
                    "native_reader_validation":{**raw,"full_stream_read":True}}
                if defect == "empty":integrity["compressed_files"] = []
                elif defect == "native_read":integrity["native_reader_validation"]["full_stream_read"] = False
                elif defect == "count":integrity["native_reader_validation"]["message_count"] = 2
                elif defect == "metadata_files":
                    metadata["rosbag2_bagfile_information"]["relative_file_paths"] = ["other.db3.zstd"]
                    metadata_path.write_text(yaml.safe_dump(metadata)); integrity["published_metadata_sha256"] = cli.file_sha256(metadata_path)
                elif defect == "bytes":compressed.write_bytes(b"changed")
                write(trial/"bag_integrity.json", integrity)
                if defect is None:self.assertEqual(cli.validate_recording_archive(trial)["status"], "PASS")
                else:
                    with self.assertRaises(ValueError):cli.validate_recording_archive(trial)

    def test_truth_alignment_is_vehicle_only_and_silent_tail_stays_unscored(self):
        def transform(name, timestamp, x):
            return NS(child_frame_id=name, header=NS(stamp=stamp(timestamp)), transform=NS(
                translation=NS(x=x,y=0.,z=0.), rotation=NS(x=0.,y=0.,z=0.,w=1.)))
        rows = []
        for index in range(31):
            time = index*.1
            rows.append(record("/ground_truth/poses", 2*index, time,
                NS(transforms=[transform("stage1_uav",time,3.), transform("target_person",time,10.+time)])))
            rows.append(record("/vehicle/odometry", 2*index+1, time,
                NS(header=NS(stamp=stamp(time),frame_id="map"), child_frame_id="base_link",
                    pose=NS(pose=NS(position=NS(x=0.,y=0.,z=0.),orientation=NS(x=0.,y=0.,z=0.,w=1.))))))
        alignment = {"rotation_world_from_map":np.eye(3).tolist(), "translation_world_from_map_m":[3.,0.,0.], "calibration_end_s":1.}
        task = [{"source_s":0.,"available_s":0.,"record_sequence":0,"action":"bind","target_uuid":"task-a","track_id":1,"state":"tracking"}]
        with patch.object(cli, "freeze_ego_alignment", return_value=alignment) as freeze:
            interval, samples, evidence = cli.independent_truth(rows, {"target_class":"person","vehicle_control_point_offset_flu_m":[0.,0.,0.]},
                {"follow_start_s":.5,"recorded_clock_end_s":4.}, task)
        self.assertEqual(interval["recorded_clock_end_s"], 4.)
        self.assertEqual(len(samples), 31)
        self.assertAlmostEqual(samples[0]["position_world_m"][0], 8.)
        self.assertTrue(all(row["position_world_m"] is None for row in samples if row["time_s"] > 3.+1e-8))
        odometry, vehicle, *_ = freeze.call_args.args
        self.assertEqual(len(odometry), 31)
        self.assertTrue(all(row["position_m"] == [0.,0.,0.] for row in odometry))
        self.assertTrue(all(row["position_m"] == [3.,0.,0.] for row in vehicle.rows))
        self.assertEqual(freeze.call_args.kwargs, {"calibration_duration_s":5.})
        self.assertNotIn("target", str(freeze.call_args.kwargs))

    def _run_export_fixture(self, corrupt):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); trial = root/"dev"; trial.mkdir()
            write(trial/"run_config.json", {"seed":4,"stage":1,"target_class":"person","command_mode":"velocity","multi_target":False})
            write(trial/"bag_integrity.json", {"scope":"MOCKED_SYNTHETIC_RECORDS_ONLY"})
            runtime = {"uav_tracking_state_estimator":{"ros__parameters":{"mahalanobis_gate":9.21,"process_noise_accel_mps2":1.}}}
            path = trial/"configuration/runtime_parameters.yaml"; path.parent.mkdir(); path.write_text(yaml.safe_dump(runtime))
            rows = recorded_fixture(corrupt_output=corrupt)
            # This opaque sentinel can reach only the independent scorer, never the KF.
            rows.append(record("/ground_truth/poses", 7, 4., NS(opaque_truth="OFFLINE_ONLY")))
            metadata = {"read_errors":{}, "unavailable_types":[], "clock_records_preserved":True}
            original_topics = cli.bag_tools.TOPICS
            def truth(records, config, interval, tasks):
                self.assertEqual(interval["recorded_clock_end_s"], 4.)
                self.assertTrue(any(row.topic.startswith("/ground_truth/") for row in records))
                return {**interval,"alignment_end_s":0.}, [], {"scope":"SYNTHETIC_MOCKED_SCORER_ONLY"}
            with patch.object(cli, "validate_recording_archive", return_value={"raw_validation":{"message_count":len(rows)}}), \
                 patch.object(cli, "recorded_configuration", return_value={"target_class":"person"}), \
                 patch.object(cli.bag_tools, "read_rosbag", return_value=(rows, metadata)) as reader, \
                 patch.object(cli, "independent_truth", side_effect=truth), \
                 patch.object(cli, "evaluate_navigation_reproduction", wraps=cli.evaluate_navigation_reproduction) as online:
                result = cli.export(trial, root/"export")
            reader.assert_called_once_with(trial/"rosbag", preserve_clock=True)
            self.assertEqual(cli.bag_tools.TOPICS, original_topics)
            self.assertEqual(result["status"], "FAIL" if corrupt else "PASS")
            self.assertEqual(result["scope"], "DEVELOPMENT_ONLY")
            self.assertNotIn("opaque_truth", str(online.call_args))
            arrays = json.loads((root/"export/arrays.json").read_text(encoding="utf-8"))
            event = arrays["output_events"][0]
            self.assertEqual(event["available_s"], 2.)
            self.assertEqual(event["diagnostic_proxy_available_s"], 1.05)
            self.assertTrue(event["native_delivery_verified"])
            self.assertEqual(arrays["interval"]["recorded_clock_end_s"], 4.)
            self.assertEqual(arrays["engineering_status"], "DEVELOPMENT_ONLY_NO_FORMAL_VERDICT")
            self.assertEqual(arrays["export_audit"]["online_equivalence"], "FAIL" if corrupt else "PASS")
            schema = "ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg"
            self.assertIn(schema, cli.SOURCE_FILES)
            self.assertEqual(arrays["export_audit"]["source_hashes"][schema], cli.file_sha256(ROOT/schema))
            from uav_tracking.replay_comparison import EXPORT_SOURCE_FILES
            self.assertEqual(set(cli.SOURCE_FILES), set(EXPORT_SOURCE_FILES))


if __name__ == "__main__":unittest.main()
