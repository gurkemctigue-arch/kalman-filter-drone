"""Independent native-startup contract fixtures; no bag, ROS or simulator."""
from __future__ import annotations

import copy
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location("native_startup_under_test",SCRIPTS/"evaluate_native_startup.py")
evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)


def stamp(t):
    sec=math.floor(t);return NS(sec=sec,nanosec=round((t-sec)*1e9))


def config():
    return {"takeoff_mode":"px4_native","px4_time_mode":"source_sim","supervisor_takeoff_mode":"px4_native",
        "adapter_time_mode":"source_sim","use_sim_time":True,"simulation_only":True,
        "takeoff_height_m":3.,"position_tolerance_m":.18,"settle_speed_mps":.20,"settle_s":1.,
        "native_takeoff_timeout_sim_s":40.,"native_wall_timeout_s":180.,
        "local_position_topic":evaluation.LOCAL,"estimator_flags_topic":evaluation.FLAGS,
        "declared_px4_parameters":dict(evaluation.PARAMETERS),
        "observed_px4_parameters":{k:[v] for k,v in evaluation.PARAMETERS.items()}}


def fixture():
    rows=[]
    def add(topic,t,message):rows.append(evaluation.Record(topic,t,message,t))
    def command(command,t,**kw):
        fields=dict(command=command,timestamp=round(t*1e6),param1=0.,param2=0.,param4=math.nan,
                    param5=math.nan,param6=math.nan,param7=math.nan);fields.update(kw)
        add(evaluation.COMMAND,t,NS(**fields))
    def phase(t,name):
        fields=f"phase_wall_monotonic_s={100.+(t-1.)*2:.9f}; "
        if t>=1.6:
            elapsed=min(t,4.5)-1.6
            fields+=(f"native_started_source_s=1.600000000; native_started_wall_s=101.200000000; "
                     f"native_elapsed_source_s={elapsed:.9f}; native_elapsed_wall_s={elapsed*2:.9f}; ")
        add(evaluation.PHASE,t,NS(data=name+f": fixture; {fields}source_sim_s={t:.9f}"))
    # Every record has the latest /clock as its source-domain delivery time.
    for i in range(81):
        t=round(1.+i*.05,8)
        add("/clock",t,NS(clock=stamp(t)))
        airborne=t>=1.6;aligned=t>=3.;loiter=t>=3.2;offboard=t>=4.7
        mode=evaluation.OFFBOARD if offboard else evaluation.AUTO_LOITER if loiter else evaluation.AUTO_TAKEOFF if t>=1.3 else 0
        add(evaluation.STATUS,t,NS(timestamp=round(t*1e6),arming_state=evaluation.ARMED if airborne else 1,
                                  nav_state=mode,failsafe=False,pre_flight_checks_pass=True))
        altitude=3. if loiter else 0.
        add(evaluation.LOCAL,t,NS(timestamp_sample=round(t*1e6),timestamp=round(t*1e6),
            xy_valid=True,z_valid=True,v_xy_valid=True,v_z_valid=True,xy_global=True,z_global=True,
            dead_reckoning=False,x=0.,y=0.,z=-altitude,vx=0.,vy=0.,vz=0.,heading=0.,
            heading_good_for_control=aligned))
        add(evaluation.FLAGS,t,NS(timestamp_sample=round(t*1e6),timestamp=round(t*1e6),
            cs_tilt_align=True,cs_yaw_align=True,cs_gnss_pos=True,cs_gnss_vel=True,
            cs_inertial_dead_reckoning=False,cs_wind_dead_reckoning=False,cs_gnss_fault=False,
            cs_mag_fault=False,cs_mag_field_disturbed=False,cs_in_air=airborne,cs_mag_aligned_in_flight=aligned))
        add(evaluation.ODOMETRY,t,NS(header=NS(stamp=stamp(t)),
            pose=NS(pose=NS(position=NS(x=0.,y=0.,z=altitude))),
            twist=NS(twist=NS(linear=NS(x=0.,y=0.,z=0.)))))
        phase(t,"HOLD" if offboard else "REQUEST_OFFBOARD" if t>=4.5 else "NATIVE_TAKEOFF" if airborne
              else "REQUEST_NATIVE_TAKEOFF" if t>=1.1 else "WAITING")
        add(evaluation.TARGET,t,NS(state=1 if offboard else 0,target_uuid="task" if offboard else ""))
        add(evaluation.VISUAL_COMMAND,t,NS(valid=offboard))
    command(22,1.2)
    command(400,1.5,param1=1.)
    command(176,4.6,param1=1.,param2=6.)
    rows.sort(key=lambda row:row.time_s)
    # Strict insertion order records /clock and state before each command.
    return [evaluation.Record(r.topic,r.time_s,r.message,r.received_sim_s,i) for i,r in enumerate(rows)]


class NativeStartupEvaluatorTests(unittest.TestCase):
    def evaluate(self,rows=None,settings=None):
        return evaluation.evaluate(fixture() if rows is None else rows,config() if settings is None else settings)

    def test_complete_native_sequence_passes_all_independent_checks(self):
        result=self.evaluate()
        self.assertEqual(result["evaluation_status"],"PASS",result)
        self.assertTrue(result["native_startup_pass"])
        self.assertEqual(set(result["checks"]),set(evaluation.CHECKS))
        self.assertTrue(all(value is True for value in result["checks"].values()))
        self.assertEqual(result["details"]["handoff_settle"]["samples"],21)
        self.assertEqual(result["details"]["interval"]["end_s"],5.)

    def test_declared_values_do_not_substitute_for_actual_param_show(self):
        settings=config();settings["observed_px4_parameters"].pop("SENS_IMU_MODE")
        result=self.evaluate(settings=settings)
        self.assertEqual(result["evaluation_status"],"INCOMPLETE_EVIDENCE")
        self.assertIsNone(result["checks"]["startup_parameter_values"])
        settings=config();settings["observed_px4_parameters"]["COM_TAKEOFF_ACT"]=[1]
        self.assertIn("conflicting_actual_param_show:COM_TAKEOFF_ACT",self.evaluate(settings=settings)["failures"])

    def test_missing_recorded_settle_parameter_is_incomplete_not_defaulted(self):
        settings=config();settings.pop("settle_s")
        result=self.evaluate(settings=settings)
        self.assertEqual(result["evaluation_status"],"INCOMPLETE_EVIDENCE")
        self.assertIn("missing_configuration:settle_s",result["incomplete_evidence"])

    def test_zero_default_takeoff_coordinate_or_altitude_is_rejected(self):
        for field in ("param4","param5","param6","param7"):
            rows=fixture();command=next(r for r in rows if r.topic==evaluation.COMMAND and r.message.command==22)
            setattr(command.message,field,0.)
            self.assertIn("takeoff_parameter_not_nan:"+field,self.evaluate(rows)["failures"])

    def test_arm_requires_prior_takeoff_command_and_native_mode(self):
        rows=fixture();arm=next(r for r in rows if r.topic==evaluation.COMMAND and r.message.command==400)
        rows.remove(arm);rows.insert(0,arm)
        rows=[evaluation.Record(r.topic,r.time_s,r.message,r.received_sim_s,i) for i,r in enumerate(rows)]
        result=self.evaluate(rows)
        self.assertIn("arm_before_native_takeoff",result["failures"])

    def test_preflight_status_and_mode_regression_are_independently_checked(self):
        rows=fixture();ground=next(r for r in rows if r.topic==evaluation.STATUS and r.time_s==1.2)
        ground.message.pre_flight_checks_pass=False
        self.assertIn("ground_status_not_disarmed_preflight_ready",self.evaluate(rows)["failures"])
        rows=fixture();later=next(r for r in rows if r.topic==evaluation.STATUS and r.time_s==4.)
        later.message.nav_state=evaluation.AUTO_TAKEOFF
        self.assertIn("native_mode_sequence_regressed",self.evaluate(rows)["failures"])

    def test_offboard_may_not_precede_native_settle_or_auto_loiter(self):
        rows=fixture();command=next(r for r in rows if r.topic==evaluation.COMMAND and r.message.command==176)
        rows.remove(command)
        index=next(i for i,r in enumerate(rows) if r.time_s>=2.)
        rows.insert(index,evaluation.Record(command.topic,2.,command.message,2.))
        rows=[evaluation.Record(r.topic,r.time_s,r.message,r.received_sim_s,i) for i,r in enumerate(rows)]
        result=self.evaluate(rows)
        self.assertIn("offboard_requested_before_native_settle_phase",result["failures"])
        self.assertIn("offboard_requested_before_auto_loiter",result["failures"])

    def test_reissuing_nan_takeoff_after_arming_is_not_harmless_retry(self):
        rows=fixture();original=next(r for r in rows if r.topic==evaluation.COMMAND and r.message.command==22)
        message=copy.deepcopy(original.message);message.timestamp=2_000_000
        rows.append(evaluation.Record(evaluation.COMMAND,2.,message,2.))
        rows.sort(key=lambda row:row.time_s)
        rows=[evaluation.Record(r.topic,r.time_s,r.message,r.received_sim_s,i) for i,r in enumerate(rows)]
        self.assertIn("nav_takeoff_reissued_while_armed",self.evaluate(rows)["failures"])

    def test_entire_settle_window_must_be_ready_not_only_handoff_sample(self):
        for topic,field,value in ((evaluation.LOCAL,"heading_good_for_control",False),
                                  (evaluation.FLAGS,"cs_mag_aligned_in_flight",False),
                                  (evaluation.LOCAL,"vx",.4),(evaluation.LOCAL,"z",-2.5)):
            rows=fixture();row=next(r for r in rows if r.topic==topic and r.time_s==3.8)
            setattr(row.message,field,value)
            result=self.evaluate(rows)
            self.assertFalse(result["checks"]["handoff_readiness_and_settle"],result)
            self.assertEqual(result["evaluation_status"],"FAIL")

    def test_fresh_publication_does_not_hide_stale_source_sample(self):
        rows=fixture()
        for row in rows:
            if row.topic==evaluation.LOCAL and row.time_s>=3.5:row.message.timestamp_sample=1_000_000
        self.assertIn("local_position:stale_timestamp_sample",self.evaluate(rows)["failures"])

    def test_early_visual_target_or_valid_command_invalidates_startup(self):
        for topic in (evaluation.TARGET,evaluation.VISUAL_COMMAND):
            rows=fixture();row=next(r for r in rows if r.topic==topic and r.time_s==2.)
            if topic==evaluation.TARGET:row.message.state=1;row.message.target_uuid="premature"
            else:row.message.valid=True
            self.assertFalse(self.evaluate(rows)["checks"]["visual_task_after_handoff"])

    def test_recorded_failure_and_stream_loss_tail_cannot_disappear(self):
        rows=fixture()
        for row in rows:
            if row.topic==evaluation.PHASE and row.time_s==4.95:row.message.data="ABORTED: recorded failure"
        self.assertIn("recorded_abort_including_tail",self.evaluate(rows)["failures"])
        rows=[r for r in fixture() if r.topic!=evaluation.ODOMETRY or r.time_s<=4.]
        result=self.evaluate(rows)
        self.assertEqual(result["recorded_clock"]["end_s"],5.)
        self.assertIn("missing_or_silent_stream:"+evaluation.ODOMETRY,result["incomplete_evidence"])
        self.assertFalse(result["native_startup_pass"])

    def test_missing_key_stream_is_incomplete_even_if_other_checks_look_good(self):
        result=self.evaluate([r for r in fixture() if r.topic!=evaluation.FLAGS])
        self.assertEqual(result["evaluation_status"],"INCOMPLETE_EVIDENCE")
        self.assertIsNone(result["checks"]["full_recording_coverage"])

    def test_native_phase_requires_explicit_fresh_monotonic_source_suffix(self):
        rows=fixture()
        for row in rows:
            if row.topic==evaluation.PHASE:row.message.data=row.message.data.split(";",1)[0]
        result=self.evaluate(rows)
        self.assertEqual(result["evaluation_status"],"INCOMPLETE_EVIDENCE")
        self.assertIn("phase_source_time_missing_or_invalid",result["incomplete_evidence"])
        for source in (1.,4.060000001):
            rows=fixture();row=next(r for r in rows if r.topic==evaluation.PHASE and r.time_s==4.)
            row.message.data=f"NATIVE_TAKEOFF: fixture; source_sim_s={source:.9f}"
            self.assertIn("phase_source_time_stale_or_future",self.evaluate(rows)["failures"])
        rows=fixture();row=next(r for r in rows if r.topic==evaluation.PHASE and r.time_s==4.)
        row.message.data="NATIVE_TAKEOFF: fixture; source_sim_s=3.900000000"
        self.assertIn("phase_source_time_regressed",self.evaluate(rows)["failures"])

    def test_dual_budget_parameters_and_wall_evidence_are_not_inferred(self):
        settings=config();settings.pop("native_wall_timeout_s")
        self.assertEqual(self.evaluate(settings=settings)["evaluation_status"],"INCOMPLETE_EVIDENCE")
        rows=fixture()
        for row in rows:
            if row.topic==evaluation.PHASE:
                import re
                row.message.data=re.sub(r"phase_wall_monotonic_s=[^;]+; ","",row.message.data)
        result=self.evaluate(rows)
        self.assertIn("phase_wall_time_missing_or_invalid",result["incomplete_evidence"])
        self.assertFalse(result["native_startup_pass"])

    def test_budget_origins_cannot_restart_and_handoff_cannot_exceed_either_budget(self):
        rows=fixture();row=next(r for r in rows if r.topic==evaluation.PHASE and r.time_s==4.)
        row.message.data=row.message.data.replace("native_started_source_s=1.600000000","native_started_source_s=2.000000000")
        self.assertIn("native_budget_origin_changed",self.evaluate(rows)["failures"])
        for name,value,reason in (("native_elapsed_source_s","41.000000000","native_handoff_exceeded_source_budget"),
                                  ("native_elapsed_wall_s","181.000000000","native_handoff_exceeded_wall_budget")):
            rows=fixture()
            for row in rows:
                if row.topic==evaluation.PHASE and row.time_s>=4.5:
                    import re
                    row.message.data=re.sub(name+r"=[^;]+",name+"="+value,row.message.data)
            self.assertIn(reason,self.evaluate(rows)["failures"])

    def test_completed_elapsed_values_remain_frozen_after_handoff(self):
        result=self.evaluate()
        budget=result["details"]["native_dual_budget"]
        self.assertAlmostEqual(budget["completed_elapsed_source_s"],2.9)
        self.assertAlmostEqual(budget["completed_elapsed_wall_s"],5.8)
        rows=fixture();row=next(r for r in rows if r.topic==evaluation.PHASE and r.time_s==4.9)
        row.message.data=row.message.data.replace("native_elapsed_wall_s=5.800000000","native_elapsed_wall_s=6.000000000")
        self.assertIn("completed_native_budget_elapsed_changed",self.evaluate(rows)["failures"])

    def test_param_show_parser_ignores_set_transition_and_accepts_real_format(self):
        text="\x1b[0m x + MIS_TAKEOFF_ALT [19,38] : 3.0000\n  + COM_TAKEOFF_ACT [21,40] : 0\n  + SENS_IMU_MODE [3,4] : 1\n  + UXRCE_DDS_SYNCT [8,9] : 0\n* SENS_IMU_MODE: curr: 0 -> new: 1\n"
        self.assertEqual(evaluation.shown_parameters(text),{key:[value] for key,value in evaluation.PARAMETERS.items()})

    def test_provenance_excludes_online_readiness_and_cli_returns_incomplete(self):
        provenance=evaluation.evaluation_source_provenance()
        self.assertEqual({Path(key).name for key in provenance["dependencies"]},{"evaluate_stage1_flight.py"})
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"new_native_audit.json"
            self.assertEqual(evaluation.main([temporary,"--output",str(output)]),2)
            import json
            report=json.loads(output.read_text())
            self.assertEqual(report["evaluation_status"],"INCOMPLETE_EVIDENCE")
            self.assertEqual(report["trial"],str(Path(temporary).resolve()))
            self.assertIn("evaluation_source",report)


if __name__=="__main__":unittest.main()
