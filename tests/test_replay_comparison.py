"""Array-only comparison fixtures; never formal flights, ROS or bag reads."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from uav_tracking import replay_comparison as replay

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("estimator_replay_cli_fixture", ROOT / "scripts/run_estimator_replay_v4.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def registered_fixture():
    """Explicit fake preregistration for pure tests, not real study evidence."""
    config = json.loads((ROOT / "planning/reliability-v4-estimator-replay-preregistration.json").read_text(encoding="utf-8"))
    config.update(status="REGISTERED", evidence_scope="PURE_REPLAY_FIXTURE_ONLY")
    calibration = config["calibration"]
    calibration.update(status="REGISTERED", R0_sensor_world_m2_by_class={cls:(np.eye(3)*.3).tolist() for cls in replay.CLASSES},
        Q_model_and_parameters={"model":"piecewise_constant_acceleration","acceleration_std_mps2":.2},
        P0_matrix_and_initial_velocity_policy={"covariance_6x6":np.eye(6).tolist(),
            "velocity_policy":"registered_constant","initial_velocity_mps":[1.,0.,0.]},
        ema_alpha=.35, common_support_truth_coverage_requirement=.2,
        common_gate_R_and_initialization_policy={"measurement_covariance":"geometry_plus_pose", "initialization":"common_P0","threshold_squared":9.21})
    freeze = config["freeze_requirements"]
    freeze.update(final_engineering_plan_path="/fixture_not_real/plan.json", final_engineering_plan_file_sha256="a"*64,
        final_engineering_plan_digest="b"*64, flight_source_hashes={"fixture/flight.py":"c"*64},
        model_hashes={"fixture_model.pt":"d"*64},
        runtime_and_magnetic_bindings={"px4_runtime_manifest_sha256":"e"*64,"magnetic_library_registration_sha256":"f"*64},
        offline_replay_source_hashes={name:"1"*64 for name in replay.SOURCE_FILES},
        evaluation_source_hashes={"fixture/offline_evaluator.py":"2"*64},
        registered_estimator_parameters={"sha256":replay.canonical_sha256(calibration)},
        development_calibration_evidence={"scope":"DEVELOPMENT_ONLY","artifact_hashes":{"fixture_development.json":"3"*64}})
    config["registration"] = {"registered_utc":"2026-10-20T00:00:00Z"}
    seal(config)
    return config


def seal(config):
    config["freeze_requirements"]["registered_estimator_parameters"] = {"sha256":replay.canonical_sha256(config["calibration"])}
    config["registration"]["configuration_sha256"] = replay.configuration_digest(config)


def trial_fixture(config, *, cls="person", seed=1000, end=3.):
    freeze = config["freeze_requirements"]
    measurements, outputs = [], []
    for i in range(11):
        t = round(1.+i*.1, 8)
        measurements.append({"acquisition_id":f"frame-{i}","source_s":t,"available_s":t+.01,"record_sequence":10+i*3,
            "target_uuid":"task-A","track_id":7,"reference_valid":True,"reference_reason":"declared_ground_reference",
            "position_world_m":[t-1.+(.04 if i==4 else 0.),0.,0.],
            "R_geometry_world_m2":(np.eye(3)*(.01 if i<5 else .4)).tolist(),
            "R_pose_world_m2":(np.eye(3)*.02).tolist()})
        outputs.append({"source_s":t+.02,"state_source_s":t+.02,"available_s":t+.03,"record_sequence":11+i*3})
    return {"schema_version":1,"evidence_scope":"PURE_REPLAY_FIXTURE_ONLY","slot_id":f"{cls}_stage1_velocity_seed{seed}",
        "group":"stage1_velocity","target_class":cls,"seed":seed,"flight_started_utc":"2026-10-28T00:00:00Z",
        "engineering_status":"FAIL", "bindings":{**{key:deepcopy(freeze[key]) for key in
            ("final_engineering_plan_digest","flight_source_hashes","model_hashes","runtime_and_magnetic_bindings")},
            "recording_artifact_hashes":{"fixture_array_source.json":"4"*64},"immutable_slot_record_sha256":"5"*64},
        "interval":{"follow_start_s":1.,"alignment_end_s":0.,"recorded_clock_end_s":end},
        "task_events":[{"source_s":.9,"available_s":.9,"record_sequence":0,"action":"bind","state":"tracking","target_uuid":"task-A","track_id":7}],
        "measurements":measurements,"output_events":outputs,
        "truth_frame":"map","truth_alignment_basis":"declared_enu_vehicle_only_frozen","truth_alignment_evidence_sha256":"6"*64,
        "truth_samples":[{"time_s":1.+i*.1,"target_uuid":"task-A","position_world_m":[i*.1,0.,0.],
                          "velocity_world_mps":[1.,0.,0.],"short_occlusion":1.6<=1.+i*.1<=1.8}
                         for i in range(int(round((end-1.)/.1))+1)]}


def write(path, payload):
    Path(path).write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")


def cli_fixture(root):
    config = registered_fixture()
    source_root = root / "sources"
    for name in replay.SOURCE_FILES:
        path = source_root/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("# PURE_REPLAY_FIXTURE_ONLY; never executed\n",encoding="utf-8")
    plan = {"mode":"FORMAL","source_hashes":config["freeze_requirements"]["flight_source_hashes"],
        "model_hashes":config["freeze_requirements"]["model_hashes"],
        "magnetic_runtime_binding":{"manifest_sha256":"e"*64},"magnetic_library_binding":{"registration_sha256":"f"*64},
        "trials":[{"id":f"{cls}_stage1_velocity_seed{seed}","group":"stage1_velocity","target_class":cls,"seed":seed}
                  for cls in replay.CLASSES for seed in replay.SEEDS],"evidence_scope":"PURE_REPLAY_FIXTURE_ONLY"}
    plan["plan_sha256"] = replay.canonical_sha256(plan)
    plan_path = root/"fixture_plan.json";write(plan_path,plan)
    freeze = config["freeze_requirements"]
    freeze.update(final_engineering_plan_path=str(plan_path),final_engineering_plan_file_sha256=cli.file_sha256(plan_path),
        final_engineering_plan_digest=plan["plan_sha256"],
        offline_replay_source_hashes={name:cli.file_sha256(source_root/name) for name in replay.SOURCE_FILES})
    seal(config)
    manifest = {"schema_version":1,"slots":{slot:None for slot in replay.scheduled_slots()}}
    path = root/"fixture_manifest.json";write(path,manifest)
    return config,source_root,path


class ReplayComparisonTests(unittest.TestCase):
    def test_draft_never_resolves_defaults_or_enters_replay(self):
        draft = json.loads((ROOT/"planning/reliability-v4-estimator-replay-preregistration.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError,"REGISTERED"):
            replay.replay_trial({},draft)
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli,"input_manifest",side_effect=AssertionError("held-out input consumed")):
            with self.assertRaisesRegex(ValueError,"REGISTERED"):
                cli.run(draft,Path(tmp)/"unread.json",Path(tmp)/"uncreated")
            self.assertFalse((Path(tmp)/"uncreated").exists())

    def test_explicit_parameters_and_prospective_bindings_are_mandatory(self):
        config = registered_fixture()
        replay.validate_registered_config(config)
        for field in ("R0_sensor_world_m2_by_class","Q_model_and_parameters","P0_matrix_and_initial_velocity_policy",
                      "ema_alpha","common_gate_R_and_initialization_policy","common_support_truth_coverage_requirement"):
            with self.subTest(field=field):
                broken = deepcopy(config);broken["calibration"].pop(field);seal(broken)
                with self.assertRaises((ValueError,KeyError,TypeError)):
                    replay.validate_registered_config(broken)
        broken = deepcopy(config);broken["calibration"]["ema_alpha"] = .7
        with self.assertRaisesRegex(ValueError,"digest changed"):
            replay.validate_registered_config(broken)
        trial = trial_fixture(config);trial["flight_started_utc"] = "2026-10-19T23:59:59Z"
        with self.assertRaisesRegex(ValueError,"precede"):
            replay.replay_trial(trial,config)
        trial = trial_fixture(config);trial["bindings"]["model_hashes"] = {"other.pt":"1"*64}
        with self.assertRaisesRegex(ValueError,"model_hashes"):
            replay.replay_trial(trial,config)

    def test_four_methods_use_same_inputs_preserve_failure_and_remain_pending(self):
        config = registered_fixture();trial = trial_fixture(config)
        report = replay.replay_trial(trial,config)
        self.assertEqual(report["engineering_status"],"FAIL")
        self.assertEqual(report["evaluation_status"],"COMPUTED_PENDING_ONLINE_EQUIVALENCE")
        self.assertEqual(set(report["metrics"]["methods"]),set(replay.METHODS))
        self.assertEqual(report["metrics"]["scheduled_samples"],21)
        self.assertLess(report["metrics"]["methods"]["raw"]["valid_state_coverage"],1.)
        self.assertEqual(len([r for r in report["replay"]["measurement_audit"] if r["accepted"]]),11)
        json.dumps(report,allow_nan=False)

    def test_truth_perturbation_changes_only_metrics_never_acceptance_or_states(self):
        config = registered_fixture();trial = trial_fixture(config)
        first = replay.replay_trial(trial,config)
        changed = deepcopy(trial)
        for row in changed["truth_samples"]:row["position_world_m"][0] += 1000.
        second = replay.replay_trial(changed,config)
        self.assertEqual(first["replay"],second["replay"])
        self.assertGreater(second["metrics"]["methods"]["raw"]["position_rmse_m"],999.)

    def test_publication_and_delivery_are_causal_and_carried_state_is_not_reprojected(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["measurements"] = [dict(trial["measurements"][0],available_s=1.2)]
        trial["output_events"] = [
            {"source_s":1.05,"state_source_s":1.05,"available_s":1.06,"record_sequence":100},
            {"source_s":1.25,"state_source_s":1.25,"available_s":1.3,"record_sequence":101}]
        report = replay.replay_trial(trial,config)
        frames = report["replay"]["frames"]
        self.assertFalse(frames[2]["methods"]["fixed_kf"]["valid"])
        self.assertTrue(frames[3]["methods"]["fixed_kf"]["valid"])
        self.assertAlmostEqual(frames[3]["methods"]["fixed_kf"]["position_world_m"][0],.25)
        self.assertAlmostEqual(frames[4]["methods"]["fixed_kf"]["position_world_m"][0],.25)
        self.assertFalse(frames[5]["methods"]["fixed_kf"]["valid"])

    def test_state_header_is_distinct_from_publication_and_delivery(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["measurements"] = [dict(trial["measurements"][0],available_s=1.05)]
        trial["output_events"] = [{"source_s":1.05,"state_source_s":1.,"available_s":1.06,"record_sequence":101}]
        report = replay.replay_trial(trial,config)
        frame = report["replay"]["frames"][1]
        self.assertTrue(frame["methods"]["fixed_kf"]["valid"])
        self.assertEqual(frame["methods"]["fixed_kf"]["position_world_m"],[0.,0.,0.])
        self.assertEqual(frame["delivered_output_source_s"],1.)
        self.assertEqual(frame["delivered_output_publication_s"],1.05)
        # A 50 ms prediction to publication would incorrectly improve this error.
        self.assertEqual(frame["methods"]["raw"]["position_world_m"],frame["methods"]["fixed_kf"]["position_world_m"])

    def test_compound_cycles_share_actual_sequence_without_later_cycle_leakage(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["task_events"] = [dict(trial["task_events"][0],source_s=1.,available_s=1.05,record_sequence=10),
            {"source_s":1.02,"available_s":1.05,"record_sequence":11,"action":"state","state":"tracking","target_uuid":"task-A","track_id":7}]
        trial["measurements"] = [dict(trial["measurements"][0],available_s=1.05,record_sequence=10),
            dict(trial["measurements"][1],source_s=1.02,available_s=1.05,record_sequence=11,position_world_m=[.4,0.,0.])]
        trial["output_events"] = [
            {"source_s":1.05,"state_source_s":1.,"available_s":1.09,"record_sequence":10},
            {"source_s":1.05,"state_source_s":1.02,"available_s":1.21,"record_sequence":11}]
        report = replay.replay_trial(trial,config)
        frames = report["replay"]["frames"]
        self.assertEqual(frames[1]["methods"]["raw"]["position_world_m"],[0.,0.,0.])
        self.assertEqual(frames[1]["methods"]["fixed_kf"]["position_world_m"],[0.,0.,0.])
        self.assertEqual(frames[2]["methods"]["raw"]["position_world_m"],[0.,0.,0.])
        self.assertEqual(frames[3]["methods"]["raw"]["position_world_m"],[.4,0.,0.])
        self.assertEqual(sum(row["accepted"] for row in report["replay"]["measurement_audit"]),2)

    def test_equal_covariance_kfs_and_alpha_one_raw_ema_are_identical(self):
        config = registered_fixture();config["calibration"]["ema_alpha"] = 1.;seal(config)
        trial = trial_fixture(config)
        for row in trial["measurements"]:row["R_geometry_world_m2"] = deepcopy(config["calibration"]["R0_sensor_world_m2_by_class"]["person"])
        report = replay.replay_trial(trial,config)
        for frame in report["replay"]["frames"]:
            self.assertEqual(frame["methods"]["fixed_kf"],frame["methods"]["geometry_adaptive_kf"])
            self.assertEqual(frame["methods"]["raw"],frame["methods"]["ema"])

    def test_prediction_expiry_is_retained_even_while_output_stream_continues(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["output_events"] += [{"source_s":2.1+i*.1,"state_source_s":2.1+i*.1,"available_s":2.1+i*.1,"record_sequence":400+i} for i in range(10)]
        report = replay.replay_trial(trial,config)
        self.assertTrue(report["replay"]["frames"][17]["methods"]["raw"]["valid"])
        self.assertFalse(report["replay"]["frames"][18]["methods"]["raw"]["valid"])
        self.assertEqual(report["replay"]["frames"][18]["validity_reason"],"prediction_expired")

    def test_common_gate_rejects_outlier_for_every_method_and_keeps_rejected_evidence(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["measurements"][5]["position_world_m"] = [100.,0.,0.]
        trial["measurements"][2]["fusion_accepted"] = False  # Recorded online decision is not the offline gate.
        report = replay.replay_trial(trial,config)
        audit = report["replay"]["measurement_audit"]
        self.assertTrue(audit[2]["accepted"])
        self.assertFalse(audit[5]["accepted"])
        self.assertEqual(audit[5]["reason"],"common_mahalanobis_gate")
        self.assertEqual(sum(r["accepted"] for r in audit),10)
        self.assertLess(report["metrics"]["methods"]["raw"]["position_rmse_m"],1.)

    def test_pose_covariance_is_added_once_and_fixed_sensor_R_stays_fixed(self):
        config = registered_fixture();trial = trial_fixture(config)
        report = replay.replay_trial(trial,config)
        audit = report["replay"]["measurement_audit"]
        for row in (audit[0],audit[6]):
            np.testing.assert_allclose(row["R_fixed_world_m2"],np.eye(3)*.32)
            np.testing.assert_allclose(row["R_adaptive_world_m2"],np.asarray(row["R_geometry_world_m2"])+np.eye(3)*.02)
        self.assertFalse(np.array_equal(audit[0]["R_adaptive_world_m2"],audit[6]["R_adaptive_world_m2"]))

    def test_empty_invalid_duplicate_stale_nonmonotonic_and_silent_tail_remain(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["measurements"][2].update(reference_valid=False,reference_reason="empty_frame",position_world_m=None)
        duplicate = deepcopy(trial["measurements"][0]);duplicate.update(record_sequence=100,available_s=1.05)
        stale = deepcopy(trial["measurements"][0]);stale.update(acquisition_id="stale",record_sequence=101,source_s=.5,available_s=1.5)
        old = deepcopy(trial["measurements"][0]);old.update(acquisition_id="old",record_sequence=102,source_s=1.1,available_s=1.4)
        trial["measurements"] += [duplicate,stale,old]
        report = replay.replay_trial(trial,config)
        reasons = report["replay"]["measurement_counts"]
        self.assertEqual(reasons["invalid_reference:empty_frame"],1)
        self.assertEqual(reasons["duplicate_acquisition"],1)
        self.assertEqual(reasons["stale_observation"],1)
        self.assertEqual(reasons["nonmonotonic_acquisition"],1)
        self.assertEqual(report["replay"]["interval"]["end_s"],3.)
        self.assertFalse(any(state["valid"] for state in report["replay"]["frames"][-1]["methods"].values()))

    def test_preselection_empty_frames_have_no_invented_identity_and_remain_counted(self):
        config = registered_fixture();trial = trial_fixture(config)
        trial["measurements"].insert(0,{"acquisition_id":"before-selection","source_s":.8,"available_s":.81,
            "record_sequence":1,"target_uuid":"","track_id":0,"reference_valid":False,"reference_reason":"empty_frame"})
        report = replay.replay_trial(trial,config)
        first = report["replay"]["measurement_audit"][0]
        self.assertEqual(first["reason"],"not_selected_task")
        self.assertFalse(first["accepted"])
        self.assertEqual(len(report["replay"]["measurement_audit"]),12)
        self.assertEqual(sum(row["accepted"] for row in report["replay"]["measurement_audit"]),11)
        self.assertEqual(report["metrics"]["scheduled_samples"],21)

    def test_lost_task_requires_new_uuid_and_cannot_match_truth_for_old_task(self):
        config = registered_fixture();trial = trial_fixture(config)
        lost = {"source_s":1.5,"available_s":1.5,"record_sequence":200,"action":"state","state":"lost","target_uuid":"task-A","track_id":7}
        trial["task_events"].append(lost)
        report = replay.replay_trial(trial,config)
        self.assertTrue(all(not f["methods"]["raw"]["valid"] for f in report["replay"]["frames"][5:]))
        trial["task_events"].append({"source_s":1.7,"available_s":1.7,"record_sequence":201,"action":"bind","state":"tracking","target_uuid":"task-A","track_id":7})
        with self.assertRaisesRegex(ValueError,"new explicit task UUID"):
            replay.replay_trial(trial,config)
        trial["task_events"][-1]["target_uuid"] = "task-B"
        for row in trial["measurements"]:
            if row["source_s"]>=1.7:row["target_uuid"]="task-B"
        report = replay.replay_trial(trial,config)
        self.assertTrue(any(f["methods"]["raw"]["valid"] for f in report["replay"]["frames"][8:]))
        self.assertLess(report["metrics"]["common_position_samples"],sum(f["methods"]["raw"]["valid"] for f in report["replay"]["frames"]))
        trial["task_events"] += [
            {"source_s":1.8,"available_s":1.8,"record_sequence":202,"action":"state","state":"lost","target_uuid":"task-B","track_id":7},
            {"source_s":1.9,"available_s":1.9,"record_sequence":203,"action":"bind","state":"tracking","target_uuid":"task-A","track_id":7}]
        with self.assertRaisesRegex(ValueError,"new explicit task UUID"):
            replay.replay_trial(trial,config)

    def test_first_bind_preserves_ambiguous_or_lost_state_in_one_compound_event(self):
        config = registered_fixture()
        for state in ("ambiguous","lost"):
            with self.subTest(state=state):
                trial = trial_fixture(config);trial["task_events"][0]["state"] = state
                report = replay.replay_trial(trial,config)
                self.assertEqual(sum(row["accepted"] for row in report["replay"]["measurement_audit"]),0)
                self.assertEqual(report["metrics"]["methods"]["raw"]["valid_samples"],0)
                self.assertIn("visual_"+state,report["replay"]["measurement_counts"])
        trial = trial_fixture(config);trial["task_events"][0].pop("state")
        with self.assertRaises(KeyError):replay.replay_trial(trial,config)

    def test_truth_gaps_are_null_metrics_not_zero_and_recovered_visual_state_does_not_fix_old_output(self):
        config = registered_fixture();trial = trial_fixture(config);trial["truth_samples"] = []
        report = replay.replay_trial(trial,config)
        self.assertIsNone(report["metrics"]["methods"]["raw"]["position_rmse_m"])
        self.assertEqual(report["metrics"]["common_position_samples"],0)
        self.assertGreater(report["metrics"]["methods"]["raw"]["valid_samples"],0)
        trial = trial_fixture(config);trial["output_events"] = [
            {"source_s":1.2,"state_source_s":1.2,"available_s":1.2,"record_sequence":300}]
        trial["task_events"] += [
            {"source_s":1.15,"available_s":1.15,"record_sequence":200,"action":"state","state":"ambiguous","target_uuid":"task-A","track_id":7},
            {"source_s":1.25,"available_s":1.25,"record_sequence":201,"action":"state","state":"tracking","target_uuid":"task-A","track_id":7}]
        report = replay.replay_trial(trial,config)
        self.assertFalse(report["replay"]["frames"][3]["methods"]["raw"]["valid"])
        self.assertEqual(report["replay"]["frames"][3]["validity_reason"],"carried_output_invalid")

    def test_malformed_covariance_record_order_and_truth_alignment_are_rejected(self):
        config = registered_fixture()
        for defect in ("negative_R","nonsymmetric_R","nan_R","duplicate_sequence","future_record","truth_alignment","initial_P0"):
            with self.subTest(defect=defect):
                trial = trial_fixture(config);settings = deepcopy(config)
                if defect=="negative_R":trial["measurements"][0]["R_pose_world_m2"][0][0] = -1.
                elif defect=="nonsymmetric_R":trial["measurements"][0]["R_pose_world_m2"][0][1] = .1
                elif defect=="nan_R":trial["measurements"][0]["R_pose_world_m2"][0][0] = float("nan")
                elif defect=="duplicate_sequence":trial["measurements"][1]["record_sequence"] = trial["measurements"][0]["record_sequence"]
                elif defect=="future_record":trial["output_events"][0]["available_s"] = 4.
                elif defect=="truth_alignment":trial["truth_alignment_basis"] = "target_fitted"
                else:settings["calibration"]["P0_matrix_and_initial_velocity_policy"]["covariance_6x6"][0][0] = -1.;seal(settings)
                with self.assertRaises(ValueError):replay.replay_trial(trial,settings)

    def test_no_output_opportunities_never_invents_a_fresh_stream(self):
        config = registered_fixture();trial = trial_fixture(config);trial["output_events"] = []
        report = replay.replay_trial(trial,config)
        self.assertEqual(report["metrics"]["scheduled_samples"],21)
        self.assertEqual(report["metrics"]["methods"]["raw"]["valid_samples"],0)
        self.assertIsNone(report["metrics"]["methods"]["raw"]["position_rmse_m"])
        self.assertFalse(report["common_support_requirement_met"])

    def test_trial_block_bootstrap_keeps_twenty_denominator_and_missing_failures(self):
        config = registered_fixture();base = replay.replay_trial(trial_fixture(config),config)
        reports = []
        for index,seed in enumerate(replay.SEEDS):
            row = deepcopy(base);row.update(slot_id=f"person_stage1_velocity_seed{seed}",seed=seed)
            for method in replay.METHODS:row["metrics"]["methods"][method]["position_rmse_m"] = 2. + (index*.1 if method=="geometry_adaptive_kf" else 1.)
            reports.append(row)
        summary = replay.paired_trial_summary(reports,config)
        contrast = summary["classes"]["person"]["contrasts"]["geometry_adaptive_kf_minus_fixed_kf"]
        self.assertEqual(contrast["finite_pairs"],10)
        self.assertAlmostEqual(contrast["mean_difference"],-.55)
        self.assertEqual(summary["classes"]["person"]["engineering_status_counts"],{"FAIL":10})
        self.assertIsNotNone(contrast["ci95"])
        self.assertEqual(summary["classes"]["car"]["available_trial_reports"],0)
        self.assertEqual(summary["scheduled_trials"],20)
        self.assertEqual(summary,replay.paired_trial_summary(reports,config))
        fewer = replay.paired_trial_summary(reports[:2],config)
        self.assertEqual(fewer["classes"]["person"]["contrasts"]["geometry_adaptive_kf_minus_fixed_kf"]["finite_pairs"],2)
        self.assertFalse(fewer["classes"]["person"]["contrasts"]["geometry_adaptive_kf_minus_fixed_kf"]["complete_ten_pair_matrix"])
        with self.assertRaisesRegex(ValueError,"duplicate"):
            replay.paired_trial_summary(reports+[reports[0]],config)

    def test_no_trial_variation_does_not_produce_a_spurious_precise_ci(self):
        config = registered_fixture();report = replay.replay_trial(trial_fixture(config),config)
        summary = replay.paired_trial_summary([report],config)
        contrast = summary["classes"]["person"]["contrasts"]["geometry_adaptive_kf_minus_fixed_kf"]
        self.assertEqual(contrast["finite_pairs"],1)
        self.assertIsNone(contrast["ci95"])


class ReplayCliTests(unittest.TestCase):
    def test_plan_and_inventory_do_not_open_trial_contents(self):
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(cli.main(["plan"]),0)
        self.assertIn("PLAN_ONLY",captured.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);_,_,manifest_path = cli_fixture(root)
            unknown = root/"outcomes.json";unknown.write_text("UNREAD OUTCOME CONTENT",encoding="utf-8")
            manifest = cli.load(manifest_path);manifest["slots"][replay.scheduled_slots()[0]] = {"path":str(unknown),"sha256":"a"*64};write(manifest_path,manifest)
            original = cli.load
            def guarded(path):
                if Path(path)==unknown:raise AssertionError("Inventory opened held-out outcomes")
                return original(path)
            with patch.object(cli,"load",side_effect=guarded):result = cli.inventory(manifest_path)
            self.assertEqual(result["slots"][replay.scheduled_slots()[0]]["state"],"FILE_PRESENT_UNREAD")

    def test_cli_artifact_binding_checks_precede_heldout_input_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);config,source_root,manifest = cli_fixture(root)
            (source_root/replay.SOURCE_FILES[0]).write_text("changed source",encoding="utf-8")
            with patch.object(cli,"input_manifest",side_effect=AssertionError("Held-out input consumed")):
                with self.assertRaisesRegex(ValueError,"implementation"):
                    cli.run(config,manifest,root/"new_output",source_root=source_root)
            self.assertFalse((root/"new_output").exists())

    def test_cli_preserves_missing_and_invalid_slots_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);config,source_root,manifest_path = cli_fixture(root)
            trial = trial_fixture(config);path = root/"fixture_trial.json";write(path,trial)
            manifest = cli.load(manifest_path)
            manifest["slots"][trial["slot_id"]] = {"path":path.name,"sha256":cli.file_sha256(path)}
            bad = root/"wrong_hash.json";bad.write_text("{}",encoding="utf-8")
            manifest["slots"][replay.scheduled_slots()[1]] = {"path":bad.name,"sha256":"0"*64};write(manifest_path,manifest)
            output = root/"new_output"
            summary = cli.run(config,manifest_path,output,source_root=source_root)
            self.assertEqual(summary["available_trial_reports"],1)
            self.assertEqual(len(summary["missing_or_invalid_inputs"]),19)
            self.assertIn("hash differs",summary["missing_or_invalid_inputs"][0]["reason"])
            self.assertEqual(cli.load(output/"summary.json")["scheduled_trials"],20)
            before = (output/"summary.json").read_bytes()
            with self.assertRaises(FileExistsError):cli.run(config,manifest_path,output,source_root=source_root)
            self.assertEqual((output/"summary.json").read_bytes(),before)


if __name__=="__main__":unittest.main()
