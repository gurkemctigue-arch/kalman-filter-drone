import math
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

import yaml

from uav_tracking.research_dynamics import transient_metrics

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from evaluate_follow_dynamics import evaluate, recorded_configuration, visual_metrics
from evaluate_stage1_flight import Record


class FollowDynamicsTests(unittest.TestCase):
    def rows(self,values,active=True):
        return [{"time_s":i*.1,"error_m":value,"active":active} for i,value in enumerate(values)]

    def test_overshoot_and_final_settling(self):
        rows=self.rows([2.]*10+[-.8]*10+[.2]*41)
        result=transient_metrics(rows,0,6,band_m=.5)
        self.assertAlmostEqual(result["opposite_side_overshoot_m"],.8)
        self.assertAlmostEqual(result["settling_time_s"],2.)
        self.assertFalse(result["settling_right_censored"])

    def test_negative_initial_error_overshoots_positive_side(self):
        result=transient_metrics(self.rows([-2.,-1.,.7]+[0.]*40),0,4.2,band_m=.5)
        self.assertAlmostEqual(result["opposite_side_overshoot_m"],.7)

    def test_initially_on_reference_has_no_defined_overshoot_direction(self):
        result=transient_metrics(self.rows([0.]*51),0,5,band_m=.5)
        self.assertIsNone(result["opposite_side_overshoot_m"])
        self.assertEqual(result["settling_time_s"],0)

    def test_late_failure_censors_an_earlier_successful_band_entry(self):
        rows=self.rows([.1]*61);rows[-1]["active"]=False
        result=transient_metrics(rows,0,6,band_m=.5)
        self.assertEqual(result["first_sustained_in_band_time_s"],0.)
        self.assertIsNone(result["settling_time_s"])
        self.assertTrue(result["settling_right_censored"])

    def test_missing_truth_breaks_settling_and_remains_in_coverage(self):
        rows=self.rows([.1]*61);rows[40]["error_m"]=None
        result=transient_metrics(rows,0,6,band_m=.5)
        self.assertIsNone(result["settling_time_s"])
        self.assertAlmostEqual(result["truth_coverage"],60/61)

    def test_gap_or_missing_tail_cannot_certify_stability(self):
        rows=self.rows([.1]*61)
        for broken in (rows[:40],rows[:40]+rows[50:]):
            self.assertIsNone(transient_metrics(broken,0,6,band_m=.5)["settling_time_s"])

    def test_missing_initial_truth_does_not_pick_later_sign(self):
        result=transient_metrics(self.rows([None]+[.1]*50),0,5,band_m=.5)
        self.assertIsNone(result["initial_direction"])
        self.assertIsNone(result["opposite_side_overshoot_m"])

    def test_duplicate_times_fail_stability(self):
        rows=self.rows([.1]*61);rows.insert(10,dict(rows[9]))
        result=transient_metrics(rows,0,6,band_m=.5)
        self.assertTrue(result["duplicate_source_times"])
        self.assertIsNone(result["settling_time_s"])

    def test_invalid_parameters_rejected(self):
        for band in (0,-1,math.nan):
            with self.assertRaises(ValueError):transient_metrics([],0,5,band_m=band)

    def test_recorded_car_reference_comes_from_actual_runtime_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp);(trial/"configuration").mkdir()
            (trial/"run_config.json").write_text(json.dumps({"stage":1,"desired_distance_m":None}))
            path=trial/"configuration/runtime_parameters.yaml"
            path.write_text(yaml.safe_dump({"uav_tracking_controller":{"ros__parameters":{"desired_distance_m":9.,"desired_height_m":2.}}}))
            config=recorded_configuration(trial,"car")
            self.assertEqual(config["desired_distance_m"],9.)
            (trial/"run_config.json").write_text(json.dumps({"stage":1,"desired_distance_m":8.}))
            with self.assertRaises(ValueError):recorded_configuration(trial,"car")

    def test_no_snapshot_never_invents_a_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp);(trial/"run_config.json").write_text('{}')
            with self.assertRaises(ValueError):recorded_configuration(trial,"person")

    def test_visual_empty_frames_and_all_candidates_do_not_become_selected_centers(self):
        def record(topic,value):return Record(topic,1.,NS(data=json.dumps(value)),1.)
        diagnostic={"stamp_s":1.,"image_size":[640,480],"detections":[{"bbox":[300,220,340,260]},{"bbox":[20,20,60,60]}]}
        records=[record("/tracking/detection_diagnostics",diagnostic),
                 record("/tracking/detection_diagnostics",{**diagnostic,"stamp_s":2.,"detections":[]}),
                 record("/tracking/tracks",{"acquisition_s":1.,"projected":False,"target_track_id":2,
                     "tracks":[{"track_id":1,"matched":True,"bbox_xyxy":[20,20,60,60]},
                               {"track_id":2,"matched":True,"bbox_xyxy":[300,220,340,260]}]})]
        result=visual_metrics(records,[],[],0,3,multi=True)
        self.assertEqual(result["detection_opportunities"],2)
        self.assertEqual(result["observed_center_coverage"],.5)
        self.assertEqual(result["detected_center_error_px"]["rmse"],0.)
        self.assertIsNone(visual_metrics(records,[],[],0,3)["detected_center_error_px"]["rmse"])

    def test_first_command_latency_uses_received_state_and_deduplicates_image(self):
        state=NS(header=NS(stamp=NS(sec=1,nanosec=0)),state=1,track_id=2,target_uuid="t",prediction_age_s=0.)
        states=[(1.2,state)]
        statuses=[(1.1,NS(lifecycle=2,track_id=2)),(1.25,NS(lifecycle=2,track_id=2)),(1.3,NS(lifecycle=2,track_id=2))]
        result=visual_metrics([],states,statuses,0,2)
        self.assertEqual(result["source_images_with_first_tracking_command"],1)
        self.assertAlmostEqual(result["image_to_first_tracking_command_sim_s"]["mean"],.25)
        # No MEASURED status happened between the estimator timer and the
        # controller timer; its first real command uses the predicted state.
        predicted=NS(header=NS(stamp=NS(sec=1,nanosec=200000000)),state=2,track_id=2,target_uuid="t",prediction_age_s=.2)
        prediction_result=visual_metrics([],[(1.2,predicted)],[(1.25,NS(lifecycle=3,track_id=2)),(1.3,NS(lifecycle=3,track_id=2))],0,2)
        self.assertEqual(prediction_result["source_images_with_first_tracking_command"],1)
        self.assertAlmostEqual(prediction_result["image_to_first_tracking_command_sim_s"]["mean"],.25)

    def test_multitarget_truth_requires_independent_mapping_not_selected_estimate(self):
        def stamp(t):return NS(sec=int(t),nanosec=round((t-int(t))*1e9))
        def point(x,y,z):return NS(x=x,y=y,z=z)
        def transform(name,t,x,z):return NS(child_frame_id=name,header=NS(stamp=stamp(t),frame_id="world"),transform=NS(translation=point(x,0,z),rotation=NS(x=0,y=0,z=0,w=1)))
        records=[Record("/tracking/flight_phase",0,NS(data="FOLLOW"),0),
                 Record("/tracking/selection",0,NS(action=0,target_uuid="task"),0)]
        for i in range(61):
            t=i*.1
            records.append(Record("/ground_truth/poses",t,NS(transforms=[transform("stage1_uav",t,0,2),transform("stage2_car_1",t,9,0)]),t))
            records.append(Record("/tracking/state",t,NS(target_uuid="task",state=1,track_id=1,prediction_age_s=0.,header=NS(stamp=stamp(t))),t))
            records.append(Record("/tracking/status",t,NS(lifecycle=2,track_id=1),t))
        config={"stage":2,"target_class":"car","desired_distance_m":9.,"desired_height_m":2.}
        missing=evaluate(records,config)
        self.assertEqual(missing["whole_interval"]["matched_truth_samples"],0)
        self.assertIsNone(missing["windows"][0]["distance"]["settling_time_s"])
        mapped=evaluate(records,config,physical={"tasks":{"task":{"initial_mapping":{"physical_id":"stage2_car_1"}}}})
        self.assertEqual(mapped["whole_interval"]["matched_truth_samples"],61)
        self.assertAlmostEqual(mapped["whole_interval"]["distance_error_m"]["rmse"],0.)
        self.assertEqual(mapped["windows"][0]["distance"]["settling_time_s"],0.)
        lost_stream=[r for r in records if r.topic!="/tracking/state" or r.time_s<3.]
        loss_result=evaluate(lost_stream,config,physical={"tasks":{"task":{"initial_mapping":{"physical_id":"stage2_car_1"}}}})
        self.assertEqual(loss_result["whole_interval"]["matched_truth_samples"],61)
        self.assertIsNone(loss_result["windows"][0]["distance"]["settling_time_s"])
        delayed=[Record(r.topic,r.time_s,r.message,r.time_s+2. if r.topic=="/tracking/status" else r.received_sim_s) for r in records]
        delayed_result=evaluate(delayed,config,physical={"tasks":{"task":{"initial_mapping":{"physical_id":"stage2_car_1"}}}})
        self.assertFalse(any(r["active"] for r in delayed_result["frames"] if r["time_s"]<2.))
        self.assertIsNone(delayed_result["windows"][0]["distance"]["settling_time_s"])
        records.append(Record("/tracking/selection",1.,NS(action=0,target_uuid="unconfirmed_new_request"),1.))
        failed_request=evaluate(records,config,physical={"tasks":{"task":{"initial_mapping":{"physical_id":"stage2_car_1"}}}})
        self.assertEqual(failed_request["windows"][0]["end_s"],1.)
        requested=failed_request["windows"][-1]
        self.assertIsNone(requested["distance"]["settling_time_s"])
        self.assertEqual(requested["distance"]["truth_coverage"],0.)
        self.assertTrue(requested["confirmation_censored"])


if __name__=="__main__":unittest.main()
