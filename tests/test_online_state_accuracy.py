"""Independent ego alignment and timestamps must not hide online TF/latency error."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

scripts=Path(__file__).resolve().parents[1]/"scripts";sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location("online_accuracy",scripts/"evaluate_online_state_accuracy.py")
evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)


def trajectory(position, count=161):
    return [{"time_s":i*.05,"position_m":position(i*.05),"quaternion_xyzw":[0,0,0,1]} for i in range(count)]


class OnlineStateAccuracyTests(unittest.TestCase):
    def test_recorded_runtime_world_takes_precedence_over_source_world(self):
        with tempfile.TemporaryDirectory(dir=scripts.parent/"results",prefix="test_world_evidence_") as temporary:
            trial=Path(temporary);config=trial/"configuration";config.mkdir()
            world='<sdf><world name="test"><spherical_coordinates><world_frame_orientation>ENU</world_frame_orientation><heading_deg>0</heading_deg></spherical_coordinates></world></sdf>'
            (config/"stage3_flight_person.sdf").write_text(world)
            (config/"runtime_world.sdf").write_text(world)
            result=evaluation.declared_enu_evidence(trial,"person")
            self.assertEqual(Path(result["world_sdf"]).name,"runtime_world.sdf")
            self.assertEqual(result["world_selection"],"RECORDED_RUNTIME_WORLD")

    def test_old_stage3_recording_fallback_is_explicit_and_stage_specific(self):
        with tempfile.TemporaryDirectory(dir=scripts.parent/"results",prefix="test_world_fallback_") as temporary:
            root=Path(temporary);trial=root/"trial";trial.mkdir()
            (trial/"run_config.json").write_text(json.dumps({"stage":3,"multi_target":False}))
            world=root/"ros2_ws/src/uav_tracking_bringup/worlds/stage3_flight_person.sdf";world.parent.mkdir(parents=True)
            world.write_text('<sdf><world name="test"><spherical_coordinates><world_frame_orientation>ENU</world_frame_orientation><heading_deg>0</heading_deg></spherical_coordinates></world></sdf>')
            with patch.object(evaluation,"ROOT",root):result=evaluation.declared_enu_evidence(trial,"person")
            self.assertEqual(Path(result["world_sdf"]).name,"stage3_flight_person.sdf")
            self.assertEqual(result["world_selection"],"SOURCE_FALLBACK_FROM_RUN_CONFIG")
            self.assertIsNotNone(result["fallback_run_config_sha256"])

    def test_ego_calibration_is_frozen_and_body_origin_is_explicit(self):
        truth=evaluation.PoseSeries(trajectory(lambda t:[t,0,0]))
        rotation=evaluation.rpy_matrix(0,0,.4);shift=np.array([3.,-2.,1.]);body=np.array([0.,0.,.24])
        # map->world rotation .4 means body->map yaw -.4.
        q=[0,0,np.sin(-.2),np.cos(-.2)]
        odometry=[{"time_s":row["time_s"],"position_m":(rotation.T@(np.asarray(row["position_m"])+body-shift)+(np.array([.5,0,0]) if row["time_s"]>5 else 0)).tolist(),"quaternion_xyzw":q} for row in truth.rows]
        result=evaluation.freeze_ego_alignment(odometry,truth,body,np.eye(3),rotation_policy="ego_attitude_relation")
        np.testing.assert_allclose(result["rotation_world_from_map"],rotation,atol=1e-12)
        np.testing.assert_allclose(result["translation_world_from_map_m"],shift,atol=1e-12)
        self.assertLess(result["splits"]["calibration"]["position_error_m"]["rmse"],1e-12)
        self.assertAlmostEqual(result["splits"]["ego_holdout"]["position_error_m"]["rmse"],.5)

    def test_declared_enu_does_not_rotate_positions_by_heading_estimation_bias(self):
        truth=evaluation.PoseSeries(trajectory(lambda t:[t,0,0]))
        q=[0,0,np.sin(-.1),np.cos(-.1)]
        odometry=[{"time_s":row["time_s"],"position_m":row["position_m"],"quaternion_xyzw":q} for row in truth.rows]
        result=evaluation.freeze_ego_alignment(odometry,truth,np.zeros(3),np.eye(3))
        np.testing.assert_array_equal(result["rotation_world_from_map"],np.eye(3))
        self.assertEqual(result["splits"]["ego_holdout"]["position_error_m"]["rmse"],0.)
        self.assertAlmostEqual(result["splits"]["ego_holdout"]["attitude_error_rad"]["rmse"],.2)

    def test_receipt_latency_not_backdated_and_lost_stays_in_denominator(self):
        truth=evaluation.PoseSeries(trajectory(lambda t:[t,0,0]))
        alignment={"rotation_world_from_map":np.eye(3).tolist(),"translation_world_from_map_m":[0,0,0]}
        rows=[{"time_s":2.,"received_sim_s":2.2,"state":1,"prediction_age_s":0.,"frame_id":"map","position_m":[2,0,0],"velocity_mps":[1,0,0]},
              {"time_s":3.,"received_sim_s":3.,"state":3,"prediction_age_s":1.,"frame_id":"map","position_m":[2,0,0],"velocity_mps":[1,0,0]}]
        result=evaluation.score_states(rows,truth,alignment,np.zeros(3),evaluation_start_s=0)
        self.assertEqual(result["active_coverage"],.5)
        self.assertAlmostEqual(result["metrics"]["state_stamp_position_error_m"]["rmse"],0)
        self.assertAlmostEqual(result["metrics"]["receipt_clock_position_error_m"]["rmse"],.2)
        self.assertEqual(result["metrics"]["state_stamp_position_error_m"]["count"],1)

    def test_no_truth_extrapolation_or_wrong_frame_scoring(self):
        truth=evaluation.PoseSeries(trajectory(lambda t:[0,0,0]))
        self.assertIsNone(evaluation.anchor_truth(truth,-.1,np.zeros(3)))
        self.assertIsNone(evaluation.anchor_truth(truth,8.1,np.zeros(3)))
        self.assertIsNone(evaluation.anchor_truth(truth,0,np.zeros(3))[1])
        row={"time_s":1,"received_sim_s":1,"state":1,"prediction_age_s":0,"frame_id":"camera","position_m":[0,0,0],"velocity_mps":[0,0,0]}
        result=evaluation.score_states([row],truth,{"rotation_world_from_map":np.eye(3).tolist(),"translation_world_from_map_m":[0,0,0]},np.zeros(3),evaluation_start_s=0)
        self.assertEqual(result["counts"]["wrong_frame_opportunities"],1)
        self.assertEqual(result["metrics"]["state_stamp_position_error_m"]["count"],0)

    def test_multitarget_expected_actor_is_task_mapped_and_unknown_is_preserved(self):
        truth=evaluation.PoseSeries(trajectory(lambda t:[10,0,0]))
        alignment={"rotation_world_from_map":np.eye(3).tolist(),"translation_world_from_map_m":[0,0,0]}
        row={"time_s":1,"received_sim_s":1,"state":1,"prediction_age_s":0,"frame_id":"map","position_m":[0,0,0],"velocity_mps":[0,0,0]}
        states=[dict(row,target_uuid="requested_A"),dict(row,time_s=2,received_sim_s=2,target_uuid="unknown")]
        result=evaluation.score_states(states,{"requested_A":truth},alignment,np.zeros(3),evaluation_start_s=0)
        self.assertEqual(result["active_coverage"],1)
        self.assertEqual(result["position_reference_coverage"],.5)
        self.assertEqual(result["metrics"]["state_stamp_position_error_m"]["rmse"],10)
        self.assertEqual(result["counts"]["unknown_independent_task_identity_opportunities"],1)


if __name__=="__main__":unittest.main()
