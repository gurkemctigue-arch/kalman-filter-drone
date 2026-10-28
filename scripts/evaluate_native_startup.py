"""Independent recorded native-PX4 takeoff -> Offboard startup audit.

The pure evaluate(records, config) API needs no ROS. The CLI reads only clock,
PX4 state/commands, adapted odometry and tracking phase/state/commands. No GT,
images, simulator entity identities or online readiness implementation enter
the audit. The full recorded clock tail is retained, including failed trials.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from numbers import Integral, Real
from pathlib import Path
import re
import sys

import yaml

import evaluate_stage1_flight as bag_tools
from evaluate_stage1_flight import Record, stamp_s, vector

ROOT = Path(__file__).resolve().parents[1]
LOCAL = "/fmu/out/vehicle_local_position_v1"
FLAGS = "/fmu/out/estimator_status_flags"
STATUS = "/fmu/out/vehicle_status_v1"
COMMAND = "/fmu/in/vehicle_command"
ODOMETRY = "/vehicle/odometry"
PHASE = "/tracking/flight_phase"
TARGET = "/tracking/state"
VISUAL_COMMAND = "/tracking/command"
TOPICS = ("/clock", LOCAL, FLAGS, STATUS, COMMAND, ODOMETRY, PHASE, TARGET, VISUAL_COMMAND)
CHECKS = ("configuration_registered", "startup_parameter_values", "native_takeoff_command",
          "command_sequence", "px4_mode_sequence", "pre_offboard_ground_readiness",
          "handoff_readiness_and_settle", "visual_task_after_handoff", "full_recording_coverage")
PARAMETERS = {"MIS_TAKEOFF_ALT":3., "COM_TAKEOFF_ACT":0, "SENS_IMU_MODE":1, "UXRCE_DDS_SYNCT":0}
# PX4 pin d6f12ad: versioned VehicleStatus constants; no online-node import.
ARMED, AUTO_LOITER, AUTO_TAKEOFF, OFFBOARD = 2, 4, 17, 14
TAKEOFF_COMMAND, ARM_COMMAND, MODE_COMMAND = 22, 400, 176
EPS = 1e-9


def finite(value):
    return float(value) if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)) else None


def evaluation_source_provenance():
    script = Path(__file__).resolve()
    dependency = script.parent / "evaluate_stage1_flight.py"
    return {"script":str(script), "script_sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
            "dependencies":{str(dependency):hashlib.sha256(dependency.read_bytes()).hexdigest()},
            "scope":"Independent offline native-startup logic plus compression-safe bag reader; no online readiness helper, GT or simulator API"}


def shown_parameters(text):
    """Parse actual `param show` lines, excluding `param set ... curr -> new`."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    result = {}
    for name in PARAMETERS:
        pattern = r"(?m)^[^\n]*\b" + name + r"\s*\[-?\d+,-?\d+\]\s*:\s*([-+0-9.eE]+)\s*$"
        result[name] = [float(match) for match in re.findall(pattern, clean)]
    return result


def phase_source_time(message):
    """Only an explicit source suffix is evidence; never infer from receipt."""
    text=getattr(message,"data",None)
    if not isinstance(text,str) or text.count("source_sim_s=")!=1:return None
    match=re.search(r"; source_sim_s=([-+0-9.eE]+)\s*$",text)
    if match is None:return None
    try:value=float(match.group(1))
    except ValueError:return None
    return value if math.isfinite(value) and value>0 else None


def phase_number(message, name):
    text=getattr(message,"data","")
    if not isinstance(text,str) or text.count(name+"=")!=1:return None
    match=re.search(r"(?:^|; )"+re.escape(name)+r"=([-+0-9.eE]+)(?:;|$)",text)
    if match is None:return None
    try:value=float(match.group(1))
    except ValueError:return None
    return value if math.isfinite(value) else None


def recorded_configuration(trial):
    trial = Path(trial)
    paths = {"run_config":trial / "run_config.json", "runtime_parameters":trial / "configuration/runtime_parameters.yaml",
             "px4_parameters":trial / "configuration/px4_parameters.json", "px4_log":trial / "px4.log"}
    run = json.loads(paths["run_config"].read_text(encoding="utf-8"))
    saved = yaml.safe_load(paths["runtime_parameters"].read_text(encoding="utf-8"))
    supervisor = saved["uav_tracking_flight_supervisor"]["ros__parameters"]
    adapter = saved["uav_tracking_px4_adapter"]["ros__parameters"]
    declared = json.loads(paths["px4_parameters"].read_text(encoding="utf-8"))["explicit_environment_overrides"]
    return {"takeoff_mode":run.get("takeoff_mode"), "px4_time_mode":run.get("px4_time_mode"),
            "supervisor_takeoff_mode":supervisor.get("takeoff_mode"),
            "adapter_time_mode":adapter.get("odometry_timestamp_mode"),
            "use_sim_time":supervisor.get("use_sim_time"), "simulation_only":supervisor.get("simulation_only"),
            "takeoff_height_m":supervisor.get("takeoff_height_m"),
            "position_tolerance_m":supervisor.get("takeoff_position_tolerance_m"),
            "settle_speed_mps":supervisor.get("native_settle_speed_mps"), "settle_s":supervisor.get("native_settle_s"),
            "native_takeoff_timeout_sim_s":supervisor.get("native_takeoff_timeout_sim_s"),
            "native_wall_timeout_s":supervisor.get("native_wall_timeout_s"),
            "local_position_topic":supervisor.get("local_position_topic"),
            "estimator_flags_topic":supervisor.get("estimator_flags_topic"),
            "declared_px4_parameters":declared,
            "observed_px4_parameters":shown_parameters(paths["px4_log"].read_text(encoding="utf-8", errors="replace")),
            "recorded_configuration_evidence":{name:{"path":str(path.resolve()),
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in paths.items()}}


def _source_issues(message, now, prefix, age_limit):
    bad, missing = [], []
    values = {}
    for field in ("timestamp_sample", "timestamp"):
        value = getattr(message, field, None)
        if value is None:
            missing.append(prefix + ":missing_" + field)
        elif not isinstance(value, Integral) or isinstance(value, bool) or not 0 < value < 2**64:
            bad.append(prefix + ":invalid_" + field)
        else:
            values[field] = int(value) * 1e-6
            age = now-values[field]
            if age < -.05-EPS:bad.append(prefix + ":future_" + field)
            elif age > age_limit+EPS:bad.append(prefix + ":stale_" + field)
    if len(values) == 2 and values["timestamp_sample"] > values["timestamp"]+EPS:
        bad.append(prefix + ":sample_after_publication")
    return bad, missing


def _readiness(local, flags, now, *, inflight):
    """Independent transcription of the documented contract, not node replay."""
    bad, missing = [], []
    for message,name,limit in ((local,"local_position",.50),(flags,"estimator_flags",1.50)):
        if message is None:
            missing.append(name + ":missing_message");continue
        b,m = _source_issues(message,now,name,limit);bad += b;missing += m
    requirements = [(local,"local_position",True,("xy_valid","z_valid","v_xy_valid","v_z_valid","xy_global","z_global")),
                    (local,"local_position",False,("dead_reckoning",)),
                    (flags,"estimator_flags",True,("cs_tilt_align","cs_yaw_align","cs_gnss_pos","cs_gnss_vel")),
                    (flags,"estimator_flags",False,("cs_inertial_dead_reckoning","cs_wind_dead_reckoning",
                                                     "cs_gnss_fault","cs_mag_fault","cs_mag_field_disturbed"))]
    if inflight:
        requirements += [(local,"local_position",True,("heading_good_for_control",)),
                         (flags,"estimator_flags",True,("cs_in_air","cs_mag_aligned_in_flight"))]
    for message,name,expected,fields in requirements:
        if message is None:continue
        for field in fields:
            value = getattr(message,field,None)
            if type(value) is not bool:missing.append(name + ":unknown_" + field)
            elif value != expected:bad.append(name + ":not_ready_" + field)
    if local is not None:
        for field in ("x","y","z","vx","vy","vz","heading"):
            if finite(getattr(local,field,None)) is None:bad.append("local_position:invalid_"+field)
    return bad, missing


def evaluate(records, config):
    rows = bag_tools.with_record_sequence(list(records))
    rows.sort(key=lambda row:row.record_sequence)
    failures, incomplete = Counter(), Counter()
    checks = {key:True for key in CHECKS}
    details, frames, streams, clocks = {}, [], defaultdict(list), []

    def issue(check, reason, *, absent=False):
        (incomplete if absent else failures)[reason] += 1
        if absent and checks[check] is not False:checks[check] = None
        elif not absent:checks[check] = False

    expected_config = {"takeoff_mode":"px4_native", "px4_time_mode":"source_sim",
        "supervisor_takeoff_mode":"px4_native", "adapter_time_mode":"source_sim",
        "use_sim_time":True, "simulation_only":True, "local_position_topic":LOCAL,"estimator_flags_topic":FLAGS}
    for key,expected in expected_config.items():
        if key not in config or config[key] is None:issue("configuration_registered","missing_configuration:"+key,absent=True)
        elif type(config[key]) is not type(expected) or config[key] != expected:
            issue("configuration_registered","conflicting_configuration:"+key)
    numeric = {"takeoff_height_m":3., "position_tolerance_m":.18,"settle_speed_mps":.20,"settle_s":1.,
               "native_takeoff_timeout_sim_s":40.,"native_wall_timeout_s":180.}
    for key,expected in numeric.items():
        value = finite(config.get(key))
        if value is None:issue("configuration_registered","missing_configuration:"+key,absent=True)
        elif not math.isclose(value,expected,rel_tol=0.,abs_tol=EPS):issue("configuration_registered","unregistered_configuration:"+key)
    for key,expected in PARAMETERS.items():
        declared = config.get("declared_px4_parameters",{}).get(key)
        observed = config.get("observed_px4_parameters",{}).get(key,[])
        if finite(declared) is None:issue("startup_parameter_values","missing_declared_parameter:"+key,absent=True)
        elif not math.isclose(float(declared),expected,abs_tol=EPS):issue("startup_parameter_values","conflicting_declared_parameter:"+key)
        if not isinstance(observed,list) or not observed:
            issue("startup_parameter_values","missing_actual_param_show:"+key,absent=True)
        elif any(finite(value) is None or not math.isclose(float(value),expected,abs_tol=EPS) for value in observed):
            issue("startup_parameter_values","conflicting_actual_param_show:"+key)
    previous_clock = None
    for row in rows:
        if row.topic not in TOPICS:continue
        if row.topic == "/clock":
            try:value = finite(stamp_s(row.message.clock))
            except (AttributeError,ValueError,TypeError):value = None
            if value is None:issue("full_recording_coverage","invalid_recorded_clock",absent=True)
            else:
                if previous_clock is not None and value < previous_clock-EPS:
                    issue("full_recording_coverage","recorded_clock_epoch_reset")
                previous_clock = value;clocks.append(value)
        else:
            if finite(row.received_sim_s) is None:
                issue("full_recording_coverage","missing_delivery_clock:"+row.topic,absent=True)
            else:streams[row.topic].append(row)
    for topic in TOPICS:
        if topic == "/clock":
            if not clocks:issue("full_recording_coverage","missing_recorded_clock",absent=True)
        elif not streams[topic]:issue("full_recording_coverage","missing_stream:"+topic,absent=True)

    def delivered(row):return float(row.received_sim_s)
    phase_times={}
    previous_phase_source=None
    previous_phase_wall=None
    for row in streams[PHASE]:
        source=phase_source_time(row.message)
        phase_times[row.record_sequence]=source
        if source is None:
            issue("full_recording_coverage","phase_source_time_missing_or_invalid",absent=True)
        else:
            age=delivered(row)-source
            if not -.05-EPS<=age<=.50+EPS:
                issue("full_recording_coverage","phase_source_time_stale_or_future")
            if previous_phase_source is not None and source<previous_phase_source-EPS:
                issue("full_recording_coverage","phase_source_time_regressed")
            previous_phase_source=source
        wall=phase_number(row.message,"phase_wall_monotonic_s")
        if wall is None or wall<=0:issue("full_recording_coverage","phase_wall_time_missing_or_invalid",absent=True)
        else:
            if previous_phase_wall is not None and wall<previous_phase_wall-EPS:
                issue("full_recording_coverage","phase_monotonic_wall_time_regressed")
            previous_phase_wall=wall
    def latest(topic,timestamp,sequence=None):
        available=[r for r in streams[topic] if delivered(r)<=timestamp+EPS
                   and (sequence is None or r.record_sequence<sequence)]
        return max(available,key=lambda r:(delivered(r),r.record_sequence)) if available else None
    def phase(row):return str(getattr(row.message,"data","")).split(":",1)[0].strip()
    def cmd(row):return getattr(row.message,"command",None)
    def armed_mode(row,mode):
        return getattr(row.message,"arming_state",None)==ARMED and getattr(row.message,"nav_state",None)==mode
    takeoffs=[r for r in streams[COMMAND] if cmd(r)==TAKEOFF_COMMAND]
    arms=[r for r in streams[COMMAND] if cmd(r)==ARM_COMMAND and finite(getattr(r.message,"param1",None))==1.]
    offboard_commands=[r for r in streams[COMMAND] if cmd(r)==MODE_COMMAND
        and finite(getattr(r.message,"param1",None))==1. and finite(getattr(r.message,"param2",None))==6.]
    request_native=[r for r in streams[PHASE] if phase(r)=="REQUEST_NATIVE_TAKEOFF"]
    request_offboard=[r for r in streams[PHASE] if phase(r)=="REQUEST_OFFBOARD"]
    holds=[r for r in streams[PHASE] if phase(r) in ("HOLD","FOLLOW")]
    modes={name:next((r for r in streams[STATUS] if armed_mode(r,mode)),None)
           for name,mode in (("AUTO_TAKEOFF",AUTO_TAKEOFF),("AUTO_LOITER",AUTO_LOITER),("OFFBOARD",OFFBOARD))}
    for values,check,name in ((takeoffs,"native_takeoff_command","nav_takeoff"),(arms,"command_sequence","arm"),
        (offboard_commands,"command_sequence","offboard_command"),(request_native,"pre_offboard_ground_readiness","request_native_phase"),
        (request_offboard,"handoff_readiness_and_settle","request_offboard_phase"),(holds,"visual_task_after_handoff","hold_phase")):
        if not values:issue(check,"missing_"+name,absent=True)
    for name,row in modes.items():
        if row is None:issue("px4_mode_sequence","missing_armed_mode:"+name,absent=True)
    for row in takeoffs:
        for field in ("param4","param5","param6","param7"):
            value=getattr(row.message,field,None)
            if value is None:issue("native_takeoff_command","missing_takeoff_"+field,absent=True)
            elif not isinstance(value,Real) or not math.isnan(float(value)):
                issue("native_takeoff_command","takeoff_parameter_not_nan:"+field)
        earlier=latest(STATUS,delivered(row),row.record_sequence)
        if earlier and getattr(earlier.message,"arming_state",None)==ARMED:
            issue("native_takeoff_command","nav_takeoff_reissued_while_armed")
    if takeoffs:
        first=takeoffs[0]
        for row in arms:
            if row.record_sequence<=first.record_sequence:issue("command_sequence","arm_before_native_takeoff")
            prior=latest(STATUS,delivered(row),row.record_sequence)
            if prior is None:issue("command_sequence","arm_mode_evidence_missing",absent=True)
            elif getattr(prior.message,"nav_state",None)!=AUTO_TAKEOFF:
                issue("command_sequence","arm_before_auto_takeoff_mode")
    if all(modes.values()):
        if not (modes["AUTO_TAKEOFF"].record_sequence<modes["AUTO_LOITER"].record_sequence<modes["OFFBOARD"].record_sequence):
            issue("px4_mode_sequence","native_mode_order_invalid")
    if takeoffs:
        stage=0
        for row in streams[STATUS]:
            if row.record_sequence<takeoffs[0].record_sequence or getattr(row.message,"arming_state",None)!=ARMED:continue
            mode=getattr(row.message,"nav_state",None)
            rank={AUTO_TAKEOFF:0,AUTO_LOITER:1,OFFBOARD:2}.get(mode)
            if rank is None:issue("px4_mode_sequence","unexpected_armed_mode_in_recorded_startup_or_tail")
            elif rank<stage:issue("px4_mode_sequence","native_mode_sequence_regressed")
            else:stage=rank
    if request_offboard:
        handoff=request_offboard[0]
        for row in offboard_commands:
            if row.record_sequence<handoff.record_sequence:issue("command_sequence","offboard_requested_before_native_settle_phase")
            if not modes["AUTO_LOITER"] or row.record_sequence<modes["AUTO_LOITER"].record_sequence:
                issue("command_sequence","offboard_requested_before_auto_loiter")
    for row in streams[PHASE]:
        if phase(row)=="ABORTED":issue("full_recording_coverage","recorded_abort_including_tail")
        if phase(row)=="TAKEOFF":issue("px4_mode_sequence","legacy_offboard_takeoff_phase_in_native_trial")
    native_phases=[r for r in streams[PHASE] if phase(r)=="NATIVE_TAKEOFF"]
    if not native_phases:issue("px4_mode_sequence","missing_native_takeoff_phase",absent=True)
    else:
        first_native=native_phases[0]
        source_origin=phase_number(first_native.message,"native_started_source_s")
        wall_origin=phase_number(first_native.message,"native_started_wall_s")
        origin_valid=all(value is not None and value>0 for value in (source_origin,wall_origin))
        if not origin_valid:issue("full_recording_coverage","native_budget_origins_missing_or_invalid",absent=True)
        frozen_elapsed=None
        for row in streams[PHASE]:
            if row.record_sequence<first_native.record_sequence:continue
            source=phase_times[row.record_sequence];wall=phase_number(row.message,"phase_wall_monotonic_s")
            origin_s=phase_number(row.message,"native_started_source_s");origin_w=phase_number(row.message,"native_started_wall_s")
            elapsed_s=phase_number(row.message,"native_elapsed_source_s");elapsed_w=phase_number(row.message,"native_elapsed_wall_s")
            if any(value is None for value in (origin_s,origin_w,elapsed_s,elapsed_w)):
                issue("full_recording_coverage","native_dual_budget_evidence_missing",absent=True);continue
            if not origin_valid:continue
            if abs(origin_s-source_origin)>EPS or abs(origin_w-wall_origin)>EPS:
                issue("full_recording_coverage","native_budget_origin_changed")
            if elapsed_s<0 or elapsed_w<0:issue("full_recording_coverage","native_elapsed_negative")
            if source is not None and origin_s+elapsed_s>source+EPS:
                issue("full_recording_coverage","native_reported_source_elapsed_after_phase")
            if wall is not None and origin_w+elapsed_w>wall+EPS:
                issue("full_recording_coverage","native_reported_wall_elapsed_after_phase")
            if phase(row)=="NATIVE_TAKEOFF":
                if source is not None and abs(source-origin_s-elapsed_s)>EPS:
                    issue("full_recording_coverage","native_active_source_elapsed_inconsistent")
                if wall is not None and abs(wall-origin_w-elapsed_w)>EPS:
                    issue("full_recording_coverage","native_active_wall_elapsed_inconsistent")
            elif phase(row) in ("REQUEST_OFFBOARD","HOLD","FOLLOW","ABORTED"):
                if frozen_elapsed is None:frozen_elapsed=(elapsed_s,elapsed_w)
                elif abs(frozen_elapsed[0]-elapsed_s)>EPS or abs(frozen_elapsed[1]-elapsed_w)>EPS:
                    issue("full_recording_coverage","completed_native_budget_elapsed_changed")
            if phase(row)=="REQUEST_OFFBOARD":
                source_limit=finite(config.get("native_takeoff_timeout_sim_s"));wall_limit=finite(config.get("native_wall_timeout_s"))
                if source_limit is not None and elapsed_s>source_limit+EPS:
                    issue("handoff_readiness_and_settle","native_handoff_exceeded_source_budget")
                if wall_limit is not None and elapsed_w>wall_limit+EPS:
                    issue("handoff_readiness_and_settle","native_handoff_exceeded_wall_budget")
        details["native_dual_budget"]={"source_origin_s":source_origin,"monotonic_wall_origin_s":wall_origin,
            "source_limit_s":config.get("native_takeoff_timeout_sim_s"),"wall_limit_s":config.get("native_wall_timeout_s"),
            "completed_elapsed_source_s":frozen_elapsed[0] if frozen_elapsed else None,
            "completed_elapsed_wall_s":frozen_elapsed[1] if frozen_elapsed else None,
            "method":"Explicit independent source and monotonic wall origins/elapsed values, never a fitted real-time factor. Steady-clock watchdog implementation is not inferred solely from a successful recording."}
    if takeoffs and clocks:
        start,end=delivered(takeoffs[0]),clocks[-1]
        details["interval"]={"start_s":start,"end_s":end,"basis":"first recorded native takeoff command through full recorded clock end"}
        coverage={}
        hold_time=delivered(holds[0]) if holds else end
        for topic,limit in ((LOCAL,.50),(FLAGS,1.50),(STATUS,1.),(ODOMETRY,.50),(PHASE,.50),
                            (TARGET,.50),(VISUAL_COMMAND,.50)):
            begin=hold_time if topic in (TARGET,VISUAL_COMMAND) else start
            times=sorted(delivered(r) for r in streams[topic] if begin<=delivered(r)<=end)
            prior=latest(topic,begin)
            if prior is not None and (not times or delivered(prior)<times[0]):times.insert(0,delivered(prior))
            edges=[begin,*[t for t in times if t>=begin],end]
            gaps=[{"start_s":a,"end_s":b,"duration_s":b-a} for a,b in zip(edges,edges[1:]) if b-a>limit+EPS]
            if not times or gaps:issue("full_recording_coverage","missing_or_silent_stream:"+topic,absent=True)
            coverage[topic]={"start_s":begin,"end_s":end,"maximum_gap_s":max((b-a for a,b in zip(edges,edges[1:])),default=None),
                "maximum_allowed_gap_s":limit,"tail_s":end-times[-1] if times else end-begin,"gaps":gaps}
        details["stream_coverage"]=coverage
    if takeoffs:
        event=takeoffs[0];now=finite(getattr(event.message,"timestamp",None))
        now=now*1e-6 if now is not None else None
        if now is None:issue("pre_offboard_ground_readiness","missing_native_command_source_time",absent=True)
        else:
            local=latest(LOCAL,delivered(event),event.record_sequence);flags=latest(FLAGS,delivered(event),event.record_sequence)
            bad,missing=_readiness(local.message if local else None,flags.message if flags else None,now,inflight=False)
            for reason in bad:issue("pre_offboard_ground_readiness",reason)
            for reason in missing:issue("pre_offboard_ground_readiness",reason,absent=True)
            ground_status=latest(STATUS,delivered(event),event.record_sequence)
            if ground_status is None:issue("pre_offboard_ground_readiness","ground_status_missing",absent=True)
            else:
                publication=finite(getattr(ground_status.message,"timestamp",None))
                if publication is None:issue("pre_offboard_ground_readiness","ground_status_source_time_missing",absent=True)
                elif not -.05-EPS<=now-publication*1e-6<=1.+EPS:
                    issue("pre_offboard_ground_readiness","ground_status_stale_or_future")
                if (getattr(ground_status.message,"arming_state",None)==ARMED
                        or getattr(ground_status.message,"pre_flight_checks_pass",None) is not True
                        or getattr(ground_status.message,"failsafe",None) is not False):
                    issue("pre_offboard_ground_readiness","ground_status_not_disarmed_preflight_ready")
            details["ground_readiness"]={"time_s":now,"failures":bad,"missing_evidence":missing}
    goal=None
    if request_native:
        native_source=phase_times[request_native[0].record_sequence]
        anchor=latest(ODOMETRY,native_source,request_native[0].record_sequence) if native_source is not None else None
        if anchor is None:issue("handoff_readiness_and_settle","missing_ground_odometry_anchor",absent=True)
        else:
            try:
                x,y,z=vector(anchor.message.pose.pose.position)
                if not all(math.isfinite(v) for v in (x,y,z)):raise ValueError("nonfinite")
                if not -.05-EPS<=native_source-stamp_s(anchor.message.header.stamp)<=.50+EPS:
                    issue("handoff_readiness_and_settle","ground_odometry_anchor_stale_or_future")
                height=finite(config.get("takeoff_height_m"))
                if height is not None:
                    goal=(y,x,-(z+height))
                    details["ground_anchor"]={"received_sim_s":delivered(anchor),"position_enu_m":[x,y,z],"goal_ned_m":list(goal),
                        "method":"Latest recorded causal adapted odometry before REQUEST_NATIVE_TAKEOFF; ENU->NED axis mapping, no GT or fitted offset"}
            except (AttributeError,ValueError,TypeError):issue("handoff_readiness_and_settle","invalid_ground_odometry_anchor",absent=True)
    if (request_offboard and phase_times[request_offboard[0].record_sequence] is not None and goal is not None
            and all(finite(config.get(key)) is not None for key in numeric)):
        handoff=request_offboard[0];finish=phase_times[handoff.record_sequence];begin=finish-float(config["settle_s"])
        points=[begin+i*.05 for i in range(int(round(float(config["settle_s"])/.05))+1)]
        def check_handoff(now,sequence=None):
            local=latest(LOCAL,now,sequence);flags=latest(FLAGS,now,sequence);status=latest(STATUS,now,sequence);odom=latest(ODOMETRY,now,sequence)
            bad,missing=_readiness(local.message if local else None,flags.message if flags else None,now,inflight=True)
            if status is None:missing.append("handoff:missing_vehicle_status")
            else:
                if not armed_mode(status,AUTO_LOITER):bad.append("handoff:not_armed_auto_loiter")
                if getattr(status.message,"failsafe",None) is not False:bad.append("handoff:status_failsafe_or_unknown")
                publication=finite(getattr(status.message,"timestamp",None))
                if publication is None:missing.append("handoff:missing_status_source_time")
                elif not -.05-EPS<=now-publication*1e-6<=1.+EPS:bad.append("handoff:stale_or_future_status")
            error=speed=None
            if local:
                position=[finite(getattr(local.message,key,None)) for key in ("x","y","z")]
                velocity=[finite(getattr(local.message,key,None)) for key in ("vx","vy","vz")]
                if all(v is not None for v in (*position,*velocity)):
                    error=math.sqrt(sum((v-g)**2 for v,g in zip(position,goal)));speed=math.sqrt(sum(v*v for v in velocity))
                    if error>float(config["position_tolerance_m"])+EPS:bad.append("handoff:position_not_settled")
                    if speed>float(config["settle_speed_mps"])+EPS:bad.append("handoff:speed_not_settled")
            if odom is None:missing.append("handoff:missing_adapted_odometry")
            else:
                try:
                    age=now-stamp_s(odom.message.header.stamp)
                    if not -.05-EPS<=age<=.50+EPS:bad.append("handoff:stale_or_future_adapted_odometry")
                    op=vector(odom.message.pose.pose.position);ov=vector(odom.message.twist.twist.linear)
                    if not all(math.isfinite(v) for v in (*op,*ov)):bad.append("handoff:nonfinite_adapted_odometry")
                    if math.sqrt(sum((v-g)**2 for v,g in zip((op[1],op[0],-op[2]),goal)))>float(config["position_tolerance_m"])+EPS:
                        bad.append("handoff:adapted_position_not_settled")
                    if math.sqrt(sum(v*v for v in ov))>float(config["settle_speed_mps"])+EPS:bad.append("handoff:adapted_speed_not_settled")
                except (AttributeError,ValueError,TypeError):missing.append("handoff:invalid_adapted_odometry")
            return {"time_s":now,"position_error_m":error,"speed_mps":speed,"failures":bad,"missing_evidence":missing,"ready":not bad and not missing}
        for point in points:
            frame=check_handoff(point,handoff.record_sequence);frames.append(frame)
            for reason in frame["failures"]:issue("handoff_readiness_and_settle",reason)
            for reason in frame["missing_evidence"]:issue("handoff_readiness_and_settle",reason,absent=True)
        for event in offboard_commands:
            timestamp=finite(getattr(event.message,"timestamp",None))
            if timestamp is None:issue("handoff_readiness_and_settle","offboard_command_missing_source_time",absent=True)
            else:
                frame=check_handoff(timestamp*1e-6,event.record_sequence);frames.append({**frame,"at_offboard_command":True})
                for reason in frame["failures"]:issue("handoff_readiness_and_settle",reason)
                for reason in frame["missing_evidence"]:issue("handoff_readiness_and_settle",reason,absent=True)
        details["handoff_settle"]={"start_s":begin,"end_s":finish,"sample_period_s":.05,"samples":len(points),
            "position_tolerance_m":config["position_tolerance_m"],"speed_limit_mps":config["settle_speed_mps"],
            "ready_samples":sum(frame["ready"] for frame in frames if not frame.get("at_offboard_command"))}
    if holds:
        hold=holds[0]
        if not modes["OFFBOARD"] or hold.record_sequence<modes["OFFBOARD"].record_sequence:
            issue("visual_task_after_handoff","visual_phase_before_confirmed_offboard")
    visual_boundary=holds[0].record_sequence if holds else float("inf")
    for row in streams[TARGET]:
        if row.record_sequence<visual_boundary:
            if (getattr(row.message,"state",None) in (1,2) or bool(getattr(row.message,"target_uuid",""))
                    or getattr(row.message,"target_visible",False)):
                issue("visual_task_after_handoff","valid_visual_target_before_native_handoff")
    for row in streams[VISUAL_COMMAND]:
        if row.record_sequence<visual_boundary and getattr(row.message,"valid",None) is True:
            issue("visual_task_after_handoff","valid_visual_command_before_native_handoff")
    details["events"]={"first_nav_takeoff_s":delivered(takeoffs[0]) if takeoffs else None,
        "first_arm_s":delivered(arms[0]) if arms else None,"request_offboard_s":delivered(request_offboard[0]) if request_offboard else None,
        "request_native_source_s":phase_times[request_native[0].record_sequence] if request_native else None,
        "request_offboard_source_s":phase_times[request_offboard[0].record_sequence] if request_offboard else None,
        "first_offboard_command_s":delivered(offboard_commands[0]) if offboard_commands else None,
        "first_hold_s":delivered(holds[0]) if holds else None,
        "armed_modes":{name:delivered(row) if row else None for name,row in modes.items()}}
    status="FAIL" if failures else "INCOMPLETE_EVIDENCE" if incomplete else "PASS"
    return {"schema_version":1,"evaluation_status":status,"native_startup_pass":status=="PASS","checks":checks,
        "configuration":config,"counts":{topic:len(streams[topic]) for topic in TOPICS if topic!="/clock"},
        "recorded_clock":{"messages":len(clocks),"start_s":clocks[0] if clocks else None,"end_s":clocks[-1] if clocks else None},
        "failures":dict(failures),"incomplete_evidence":dict(incomplete),"details":details,"frames":frames,
        "claim_boundary":"PASS establishes this recorded native startup/configuration/causal handoff and full-stream evidence contract only. It does not certify target-following accuracy or general estimator readiness. All recorded failure phases and silent tails remain; no GT, entity IDs, offset fit or online readiness replay."}


def read_records(path):
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as error:
        raise RuntimeError("Source ROS, px4_msgs and the project before reading a native-startup bag") from error
    rows,errors,clock=[],Counter(),None
    with bag_tools.open_bag_reader(Path(path),rosbag2_py) as (reader,metadata):
        types={item.name:item.type for item in reader.get_all_topics_and_types() if item.name in TOPICS}
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(types)))
        classes={topic:get_message(kind) for topic,kind in types.items()}
        sequence=0
        while reader.has_next():
            topic,data,_=reader.read_next()
            try:
                message=deserialize_message(data,classes[topic])
                if topic=="/clock":clock=stamp_s(message.clock)
                rows.append(Record(topic,clock if clock is not None else 0.,message,clock,sequence))
            except Exception as error:errors[f"{topic}: {type(error).__name__}: {error}"]+=1
            sequence+=1
    return rows,{**metadata,"bag":str(Path(path).resolve()),"topic_types":types,"read_errors":dict(errors),
                 "scope":"Only startup commands/state/clock/phase/odometry/visual activation; no GT, images or simulator entity names"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        config=recorded_configuration(args.trial);rows,metadata=read_records(args.trial/"rosbag")
        result=evaluate(rows,config);result["bag"]=metadata
        if metadata["read_errors"]:
            result["incomplete_evidence"]["bag_read_errors"]=sum(metadata["read_errors"].values())
            result["checks"]["full_recording_coverage"]=None;result["native_startup_pass"]=False
            if result["evaluation_status"]=="PASS":result["evaluation_status"]="INCOMPLETE_EVIDENCE"
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:
        result={"schema_version":1,"evaluation_status":"INCOMPLETE_EVIDENCE","native_startup_pass":False,
            "checks":{key:None for key in CHECKS},"failures":{},"incomplete_evidence":{"configuration_or_input_error":str(error)}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames=result.pop("frames",[]);sidecar=args.output.with_suffix(".frames.jsonl")
    sidecar.write_text("".join(json.dumps(row,allow_nan=False)+"\n" for row in frames),encoding="utf-8")
    result.update(trial=str(args.trial.resolve()),frames_path=str(sidecar),evaluation_source=evaluation_source_provenance())
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["evaluation_status"],"native_startup_pass":result["native_startup_pass"],"output":str(args.output)}))
    return 0 if result["native_startup_pass"] else 2


if __name__=="__main__":raise SystemExit(main())
