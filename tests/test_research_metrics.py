from __future__ import annotations
import itertools
import unittest
import numpy as np
from uav_tracking.research_metrics import (detection_metrics,identity_metrics,maximum_assignment,
                                         paired_bootstrap,wilson_interval,numeric_summary)
from uav_tracking.research_labels import interpolate_pose,project_mesh,quaternion_matrix,target_mesh_points
from uav_tracking.research_replay import perturb,Perturbation,replay,fit_surface_anchor
from pathlib import Path


def obj(identity,box=(0,0,10,10),score=.9):
    return {"id":identity,"bbox":list(box),"class_name":"person","confidence":score}


class ResearchMetricTests(unittest.TestCase):
    def test_hungarian_matches_brute_force_rectangular(self):
        rng=np.random.default_rng(6)
        for n,m in [(2,3),(3,2),(3,3),(1,4)]:
            scores=rng.normal(size=(n,m))
            result=sum(scores[i,j] for i,j in maximum_assignment(scores))
            possible=([sum(scores[i,p[i]] for i in range(n)) for p in itertools.permutations(range(m),n)]
                      if n<=m else [sum(scores[p[j],j] for j in range(m)) for p in itertools.permutations(range(n),m)])
            self.assertAlmostEqual(result,max(possible))

    def test_perfect_and_absent_detection(self):
        perfect=detection_metrics([{"gt":[obj("gt")],"pred":[obj("p")]}])
        self.assertEqual(perfect["map50_95"],1)
        missed=detection_metrics([{"gt":[obj("gt")],"pred":[]}])
        self.assertEqual(missed["map50_95"],0)
        self.assertEqual(missed["classes"]["person"]["fn"],1)

    def test_false_positive_empty_frames_count(self):
        result=detection_metrics([{"gt":[],"pred":[obj("false",score=.99)]},
                                  {"gt":[obj("gt")],"pred":[obj("true",score=.9)]}])
        self.assertAlmostEqual(result["map50"],.5)
        self.assertEqual(result["classes"]["person"]["fp"],1)

    def test_task_uuid_cannot_hide_identity_switch(self):
        frames=[{"gt":[obj("A"),obj("B",(20,0,30,10))],
                 "pred":[obj("1"),obj("2",(20,0,30,10))],"selected_gt_id":"A","selected_track_id":"1"},
                {"gt":[obj("A"),obj("B",(20,0,30,10))],
                 "pred":[obj("2"),obj("1",(20,0,30,10))],"selected_gt_id":"A","selected_track_id":"1"}]
        result=identity_metrics(frames)
        self.assertEqual(result["id_switches"],2)
        self.assertAlmostEqual(result["idf1"],.5)
        self.assertAlmostEqual(result["selected_identity"]["retention_rate"],.5)
        self.assertLess(result["hota"],1)

    def test_missing_prediction_penalizes_idf1_and_hota(self):
        result=identity_metrics([{"gt":[obj("A")],"pred":[obj("1")]},
                                 {"gt":[obj("A")],"pred":[]}])
        self.assertAlmostEqual(result["idf1"],2/3)
        self.assertAlmostEqual(result["hota"],.5)

    def test_perfect_identity_and_no_ground_truth(self):
        result=identity_metrics([{"gt":[obj("A")],"pred":[obj("1")]}]*3)
        self.assertEqual(result["hota"],1)
        self.assertEqual(result["idf1"],1)
        self.assertIsNone(identity_metrics([{"gt":[],"pred":[]}])["hota"])

    def test_failures_and_missing_values_are_not_dropped(self):
        result=numeric_summary([1,None,3,float("nan")])
        self.assertEqual(result["missing_count"],2)
        self.assertEqual(result["mean"],2)
        interval=wilson_interval(1,10)
        self.assertLess(interval["ci95"][0],.1)
        self.assertGreater(interval["ci95"][1],.1)
        ci=paired_bootstrap([1,2,None],[2,3,4])
        self.assertEqual(ci["pairs"],2)
        self.assertEqual(ci["excluded_pairs"],1)
        self.assertEqual(ci["ci95"],[-1,-1])

    def test_interpolation_refuses_extrapolation(self):
        points=[{"time_s":t,"position_m":[t,0,0],"quaternion_xyzw":[0,0,0,1]} for t in (0,.1)]
        self.assertIsNone(interpolate_pose(points,.2))
        np.testing.assert_allclose(interpolate_pose(points,.05)[0],[.05,0,0])

    def test_projection_uses_geometry_not_detector_box(self):
        points=np.asarray([[-1,-1,10],[1,1,10]])
        result=project_mesh(points,(np.zeros(3),np.eye(3)),(np.zeros(3),np.eye(3)),[100,100,50,50],100,100)
        np.testing.assert_allclose(result["bbox"],[40,40,60,60])

    def test_real_meshes_load_with_plausible_metric_size(self):
        root=Path(__file__).resolve().parents[1]/"ros2_ws/src/uav_tracking_bringup/models"
        for name in ("person","car"):
            points,_meta=target_mesh_points(root,name)
            self.assertGreater(len(points),100)
            height=np.ptp(points[:,2])
            self.assertGreater(height,1)
            self.assertLess(height,2.5)

    def test_perturbation_pair_reproducibility(self):
        rows=[{"time_s":float(t),"arrival_s":float(t)+.1,"point_world_m":[1,2,3]} for t in range(20)]
        condition=Perturbation("combined",.1,.1,.1,.1,.1)
        self.assertEqual(perturb(rows,condition,2),perturb(rows,condition,2))
        self.assertNotEqual(perturb(rows,condition,2),perturb(rows,condition,3))

    def test_replay_does_not_backdate_delayed_measurements(self):
        truth=[(0,[0,0,0]),(1,[1,0,0]),(2,[2,0,0]),(3,[3,0,0])]
        rows=[{"time_s":t,"arrival_s":t+.2,"point_world_m":[t,0,0],"reference_samples":truth} for t in (0,1,2)]
        metric,outputs=replay(rows,"raw",anchor_m=[0,0,0],evaluation_start_s=0)
        self.assertAlmostEqual(metric["position_rmse_m"],.2)
        self.assertEqual(len(outputs),3)

    def test_replay_stale_predictions_are_missing_not_zero_errors(self):
        rows=[{"time_s":0,"arrival_s":0,"point_world_m":[0,0,0],"reference_samples":[(0,[0,0,0]),(2,[2,0,0])]},
              {"time_s":2,"arrival_s":2,"point_world_m":None,"reference_samples":[(0,[0,0,0]),(2,[2,0,0])]}]
        metric,_=replay(rows,"raw",anchor_m=[0,0,0],evaluation_start_s=0)
        self.assertEqual(metric["unavailable_frames"],1)
        self.assertEqual(metric["coverage"],.5)
        self.assertEqual(metric["result"],"FAIL_OR_INCOMPLETE")

    def test_anchor_calibration_excludes_holdout(self):
        rows=[{"time_s":i,"point_world_m":[i,0,1 if i<10 else 100],"truth_position_m":[i,0,0],"truth_rotation":np.eye(3).tolist()} for i in range(20)]
        anchor=fit_surface_anchor(rows,9)
        np.testing.assert_allclose(anchor["model_local_anchor_m"],[0,0,1])
        self.assertEqual(anchor["calibration_observations"],10)


if __name__=="__main__":
    unittest.main()
