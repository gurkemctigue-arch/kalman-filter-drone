"""Offline audit of the ONLINE map-frame state, with independently frozen ego alignment.

Unlike the recorded-estimator replay, this evaluates the actual /tracking/state
used by the controller, including PX4 odometry and runtime TF errors. Neither
target measurements nor target truth may determine the map-to-world alignment.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_stage1_flight import read_rosbag, summary, vector
import evaluate_stage1_flight as bag_tools
from extract_research_recording import camera_model_resources, camera_model_source_hashes, pose_dict
from uav_tracking.research_labels import interpolate_pose, quaternion_matrix, rpy_matrix


class PoseSeries:
    """Bracketed interpolation with cached times; never extrapolate GT."""
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r["time_s"])
        self.times = [r["time_s"] for r in self.rows]

    def at(self, timestamp):
        index = bisect_left(self.times, timestamp)
        return interpolate_pose(self.rows[max(0,index-1):index+1], timestamp)


def rotation_error_rad(left, right):
    return float(np.arccos(np.clip((np.trace(left.T @ right)-1)/2, -1, 1)))


def freeze_ego_alignment(odometry, vehicle_truth, body_offset_m, body_rotation,
                         calibration_duration_s=5.,rotation_policy="declared_enu"):
    """First fixed-duration ego-only calibration, followed by untouched holdout."""
    matched = []
    for row in odometry:
        truth = vehicle_truth.at(row["time_s"])
        if truth is None:
            continue
        p, r = truth
        matched.append((row, p+r@body_offset_m, r@body_rotation))
    if len(matched) < 10:
        raise ValueError("Insufficient independently bracketed vehicle odometry/GT pairs")
    start = matched[0][0]["time_s"]
    end = start+calibration_duration_s
    train = [m for m in matched if m[0]["time_s"] <= end]
    if len(train) < 10 or matched[-1][0]["time_s"] <= end:
        raise ValueError("Need at least ten calibration pairs and a later ego holdout")
    if rotation_policy=="declared_enu":
        # Source contract, not a fit selected by whichever gives lower error:
        # Gazebo ENU -> PX4 NED -> our ROS ENU preserves the world axes.
        rotation=np.eye(3)
    elif rotation_policy=="ego_attitude_relation":
        matrices = [r@quaternion_matrix(row["quaternion_xyzw"]).T for row, _p, r in train]
        u, _singular, vt = np.linalg.svd(np.mean(matrices, axis=0))
        correction = np.eye(3); correction[2,2] = np.linalg.det(u@vt)
        rotation = u@correction@vt
    else:raise ValueError("Unsupported rotation policy")
    translation = np.median([p-rotation@np.asarray(row["position_m"]) for row,p,_r in train], axis=0)
    splits = {}
    for name, subset in (("calibration",train),("ego_holdout",[m for m in matched if m[0]["time_s"] > end])):
        splits[name] = {
            "pairs":len(subset),
            "position_error_m":summary(np.linalg.norm(rotation@np.asarray(row["position_m"])+translation-p) for row,p,_r in subset),
            "attitude_error_rad":summary(rotation_error_rad(rotation@quaternion_matrix(row["quaternion_xyzw"]),r) for row,_p,r in subset)}
    timeline=[];last_saved=-float("inf")
    for row,p,r in matched:
        if row["time_s"]-last_saved<.5:continue
        estimated_r=rotation@quaternion_matrix(row["quaternion_xyzw"])
        timeline.append({"time_s":row["time_s"],"map_position_m":list(row["position_m"]),"gt_body_position_m":p.tolist(),
                         "aligned_position_error_vector_m":(rotation@np.asarray(row["position_m"])+translation-p).tolist(),
                         "estimated_yaw_rad":float(np.arctan2(estimated_r[1,0],estimated_r[0,0])),
                         "true_yaw_rad":float(np.arctan2(r[1,0],r[0,0])),
                         "attitude_error_rad":rotation_error_rad(estimated_r,r)})
        last_saved=row["time_s"]
    return {"rotation_world_from_map":rotation.tolist(), "translation_world_from_map_m":translation.tolist(),
            "calibration_start_s":start, "calibration_end_s":end, "splits":splits,
            "rotation_policy":rotation_policy,"timeline_approx_2hz":timeline,
            "method":("Fixed identity rotation from declared Gazebo/PX4/ROS ENU source contract; " if rotation_policy=="declared_enu" else "Sensitivity only: ego attitude relations projected onto SO(3); estimated heading bias may incorrectly rotate GNSS position axes. ")+
                     "Componentwise median translation from ego-only first 5 s by default. No target data or holdout refit."}


def declared_enu_evidence(trial,target_class):
    names=sorted((trial/"configuration").glob("*.sdf"))
    worlds=[]
    for path in names:
        xml=ET.parse(path).getroot()
        world=xml.find("world")
        if world is not None:worlds.append((path,world))
    runtime=[row for row in worlds if row[0].name=="runtime_world.sdf"]
    run_config=trial/"run_config.json";config_sha=None
    if runtime:
        worlds=runtime;selection="RECORDED_RUNTIME_WORLD"
    elif len(worlds)==1:selection="RECORDED_SINGLE_WORLD"
    elif worlds:
        raise ValueError("Multiple recorded worlds without an explicit runtime_world.sdf; refuse to substitute a different world")
    else:
        config=json.loads(run_config.read_text()) if run_config.is_file() else {}
        if run_config.is_file():config_sha=hashlib.sha256(run_config.read_bytes()).hexdigest()
        stage=int(config.get("stage",1))
        if stage not in {1,2,3}:raise ValueError("Unsupported source-fallback simulation stage")
        world_kind="stage3_multi" if stage==3 and config.get("multi_target") is True else f"stage{stage}_flight"
        fallback=ROOT/"ros2_ws/src/uav_tracking_bringup/worlds"/f"{world_kind}_{target_class}.sdf"
        worlds=[(fallback,ET.parse(fallback).getroot().find("world"))]
        selection="SOURCE_FALLBACK_FROM_RUN_CONFIG" if config else "SOURCE_FALLBACK_STAGE1_DEFAULT"
    path,world=worlds[0]
    spherical=world.find("spherical_coordinates")
    if spherical is None or spherical.findtext("world_frame_orientation")!="ENU" or float(spherical.findtext("heading_deg","0"))!=0:
        raise ValueError("Declared ENU identity rotation requires explicit ENU world spherical coordinates with zero heading")
    return {"world_sdf":str(path),"world_sdf_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "world_selection":selection,"fallback_run_config_sha256":config_sha,
            "world_evidence_boundary":"Recorded runtime snapshot preferred. Older recordings without any world snapshot explicitly use current stage-specific source fallback; this is source-contract evidence, not a claimed historical runtime-world checksum.",
            "source_contract":"Gazebo world spherical_coordinates ENU with heading_deg=0; GPS north/east/up feed PX4 local NED; adapter reverses NED->ENU. Origin may differ; heading estimation error is not a world-axis calibration.",
            "px4_commit":"d6f12ad1c4f70ad3230afd7d86e971421e02fef4",
            "source_references":["PX4 src/modules/simulation/gz_bridge/GZBridge.cpp:545 (ENU position -> NED y,x,-z)",
                                 "PX4 GZBridge.cpp:713-742 (NavSat north/east/up; GPS noise)",
                                 "PX4 src/modules/ekf2/EKF2.cpp:1687-1688 (POSE_FRAME_NED, EKF position)",
                                 "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/adapter_node.py:148-154 (inverse NED/FRD -> ENU/FLU)"]}


def odometry_diagnostics(raw):
    changes=[];samples=[];last_counter=None;last_time=-float("inf")
    for row in raw:
        counter=row.get("reset_counter")
        if last_counter is not None and counter!=last_counter:changes.append({"time_s":row["time_s"],"before":last_counter,"after":counter})
        if counter is not None:last_counter=counter
        if row["time_s"]-last_time>=1.:
            samples.append(row);last_time=row["time_s"]
    return {"messages":len(raw),"reset_counter_changes":changes,"samples_approx_1hz":samples,
            "interpretation":"reset_counter transitions report PX4 odometry reset evidence; zero transitions does not exclude continuous GNSS/heading estimation drift. Latest recorded /clock maps receipt time, not raw PX4 boot timestamps."}


def anchor_truth(series, timestamp, anchor, derivative_half_window_s=.05):
    pose = series.at(timestamp)
    if pose is None:
        return None
    position = pose[0]+pose[1]@anchor
    before, after = series.at(timestamp-derivative_half_window_s), series.at(timestamp+derivative_half_window_s)
    velocity = None
    if before is not None and after is not None:
        velocity = ((after[0]+after[1]@anchor)-(before[0]+before[1]@anchor))/(2*derivative_half_window_s)
    return position, velocity


def score_states(states, target_truth, alignment, anchor, *, evaluation_start_s, max_age_s=.75):
    rotation = np.asarray(alignment["rotation_world_from_map"])
    translation = np.asarray(alignment["translation_world_from_map_m"])
    rows = []; counts = defaultdict(int)
    for state in states:
        if state["time_s"] <= evaluation_start_s:
            continue
        counts["all_state_opportunities"] += 1
        age=state["prediction_age_s"]
        row = {"time_s":state["time_s"], "received_sim_s":state.get("received_sim_s"),
               "state":state["state"], "prediction_age_s":float(age) if np.isfinite(age) else None}
        active = state["state"] in (1,2) and np.isfinite(age) and 0 <= age <= max_age_s
        if not active:
            counts["unavailable_state_opportunities"] += 1
            row["reason"] = "uninitialized_lost_ambiguous_or_stale"
            rows.append(row); continue
        if state.get("frame_id") != "map":
            counts["wrong_frame_opportunities"] += 1
            row["reason"] = "unexpected_state_frame"; rows.append(row); continue
        if not np.isfinite(state["position_m"]).all() or not np.isfinite(state["velocity_mps"]).all():
            counts["nonfinite_state_opportunities"] += 1
            row["reason"]="nonfinite_state_vector";rows.append(row);continue
        counts["active_state_opportunities"] += 1
        estimated_p = rotation@np.asarray(state["position_m"])+translation
        estimated_v = rotation@np.asarray(state["velocity_mps"])
        reference_series=target_truth.get(state.get("target_uuid","")) if isinstance(target_truth,dict) else target_truth
        if reference_series is None:
            counts["unknown_independent_task_identity_opportunities"]+=1
            row["reason"]="expected_actor_not_independently_established_from_request"
            rows.append(row);continue
        for name, timestamp in (("state_stamp",state["time_s"]),("receipt_clock",state.get("received_sim_s"))):
            if timestamp is None or timestamp < state["time_s"]-.05:
                counts[name+"_missing_or_invalid_time"] += 1; continue
            truth = anchor_truth(reference_series, timestamp, anchor)
            if truth is None:
                counts[name+"_missing_bracketed_truth"] += 1; continue
            row[name+"_position_error_m"] = float(np.linalg.norm(estimated_p-truth[0]))
            if truth[1] is not None:
                row[name+"_velocity_error_mps"] = float(np.linalg.norm(estimated_v-truth[1]))
        if state.get("received_sim_s") is not None:
            row["state_delivery_age_s"] = state["received_sim_s"]-state["time_s"]
        rows.append(row)
    metrics = {key:summary(row.get(key) for row in rows) for key in
               ("state_stamp_position_error_m","state_stamp_velocity_error_mps",
                "receipt_clock_position_error_m","receipt_clock_velocity_error_mps","state_delivery_age_s")}
    total = counts["all_state_opportunities"]
    return {"counts":dict(counts),"active_coverage":counts["active_state_opportunities"]/total if total else None,
            "position_reference_coverage":metrics["state_stamp_position_error_m"]["count"]/total if total else None,
            "metrics":metrics,"frames":rows,
            "time_semantics":"State-stamp errors evaluate the timestamp carried by the actual published state. Receipt-clock errors compare the SAME carried position/velocity to GT at latest recorded /clock; no backward correction or ideal extrapolation hides delivery age. Receipt time is quantized by /clock recording cadence.",
            "reference_semantics":"Frozen calibrated visible-surface anchor, not independent physical model-center accuracy. GT anchor velocity uses symmetric +/-0.05 s finite difference including target rotation, with bracketed interpolation and no extrapolation. All LOST/ambiguous/stale opportunities remain in coverage denominator."}


def command_jitter(commands):
    acceleration = []; yaw_acceleration = []; gaps = []
    for a,b in zip(commands, commands[1:]):
        dt = b["time_s"]-a["time_s"]
        if not (0 < dt <= .2 and a["valid"] and b["valid"] and a["mode"] == b["mode"] == 1):
            continue
        acceleration.append(float(np.linalg.norm(np.asarray(b["linear_mps"])-a["linear_mps"])/dt))
        yaw_acceleration.append(abs(b["yaw_rate_radps"]-a["yaw_rate_radps"])/dt)
        gaps.append(dt)
    return {"velocity_command_delta_over_dt_mps2":summary(acceleration),
            "yaw_rate_delta_over_dt_radps2":summary(yaw_acceleration),"paired_command_dt_s":summary(gaps),
            "definition":"Adjacent valid velocity commands within 0.2 s and same velocity mode, including tracking transients. This is command variation, not measured vehicle acceleration. HOLD/position/failsafe commands are excluded and counted separately.",
            "all_commands":len(commands),"valid_velocity_commands":sum(c["valid"] and c["mode"]==1 for c in commands)}


def body_frame_mount(model_path):
    resources,selection=camera_model_resources(ROOT)
    sources=camera_model_source_hashes(model_path,resources)
    resource=os.pathsep.join(str(path) for path in resources)
    result=subprocess.run(["gz","sdf","-p",str(model_path)],capture_output=True,text=True,timeout=30,
                          check=True,env=dict(os.environ,GZ_SIM_RESOURCE_PATH=resource,SDF_PATH=resource))
    model=ET.fromstring(result.stdout).find("model")
    frames={"__model__":(None,np.zeros(3),np.eye(3))}
    for item in model:
        if item.tag not in ("link","frame","joint"): continue
        pose=item.find("pose");values=np.fromstring(pose.text if pose is not None and pose.text else "0 0 0 0 0 0",sep=" ")
        parent=pose.attrib.get("relative_to") if pose is not None else None
        parent=parent or (item.attrib.get("attached_to","__model__") if item.tag=="frame" else "__model__")
        frames[item.attrib["name"]]=(parent,values[:3],rpy_matrix(*values[3:]))
    def resolve(name,seen=()):
        if name not in frames or name in seen: raise ValueError(f"Invalid expanded SDF frame {name}")
        parent,p,r=frames[name]
        if parent is None:return p,r
        pp,pr=resolve(parent,seen+(name,));return pp+pr@p,pr@r
    p,r=resolve("base_link")
    return p,r,{"model":str(model_path),"expanded_sdf_sha256":hashlib.sha256(result.stdout.encode()).hexdigest(),
                "resolved_model_sdf_sha256":sources,
                "declared_model_resource_roots":[str(path.resolve()) for path in resources],
                "px4_model_resource_selection":selection,
                "body_frame":"base_link","model_to_body_position_m":p.tolist(),"model_to_body_rotation":r.tolist()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial",type=Path)
    parser.add_argument("--target-class",choices=("person","car"),required=True)
    parser.add_argument("--anchor-report",type=Path,default=ROOT/"results/recorded_estimator_research/research_report.json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--calibration-duration-s",type=float,default=5.)
    parser.add_argument("--vehicle-model",default="x500_stage1")
    parser.add_argument("--physical-identity-report",type=Path,
                        help="Stage-two REQUEST-box independent task-to-actor mapping; unknown tasks stay unscored")
    args=parser.parse_args()
    if args.calibration_duration_s <= 0: parser.error("Calibration duration must be positive")
    bag_tools.TOPICS=tuple(dict.fromkeys(bag_tools.TOPICS+("/fmu/out/vehicle_odometry",)))
    records,metadata=read_rosbag(args.trial/"rosbag")
    trajectories=defaultdict(list);odometry=[];states=[];commands=[];raw_odometry=[]
    for record in records:
        msg=record.message
        if record.topic.startswith("/ground_truth/"):
            for transform in msg.transforms:trajectories[transform.child_frame_id.strip("/")].append(pose_dict(transform))
        elif record.topic=="/vehicle/odometry":
            q=msg.pose.pose.orientation
            odometry.append({"time_s":record.time_s,"position_m":vector(msg.pose.pose.position),"quaternion_xyzw":[q.x,q.y,q.z,q.w]})
        elif record.topic=="/tracking/state":
            states.append({"time_s":record.time_s,"received_sim_s":record.received_sim_s,"frame_id":msg.header.frame_id,
                           "target_uuid":str(msg.target_uuid),
                           "state":msg.state,"prediction_age_s":float(msg.prediction_age_s),
                           "position_m":vector(msg.position_m),"velocity_mps":vector(msg.velocity_mps)})
        elif record.topic=="/tracking/command":
            commands.append({"time_s":record.time_s,"valid":msg.valid,"mode":msg.mode,
                             "linear_mps":vector(msg.linear_mps),"yaw_rate_radps":float(msg.yaw_rate_radps)})
        elif record.topic=="/fmu/out/vehicle_odometry":
            raw_odometry.append({"time_s":record.time_s,"reset_counter":int(msg.reset_counter),"quality":int(msg.quality),
                                 "pose_frame":int(msg.pose_frame),"velocity_frame":int(msg.velocity_frame),
                                 "position_variance_m2":[float(v) if np.isfinite(v) else None for v in msg.position_variance],
                                 "orientation_variance_rad2":[float(v) if np.isfinite(v) else None for v in msg.orientation_variance]})
    def series(name):
        keys=[key for key in trajectories if key==name or key.endswith("::"+name) or key.rsplit("/",1)[-1]==name]
        if len(keys)!=1:raise ValueError(f"Missing/ambiguous independent GT {name}: {keys}")
        return PoseSeries(trajectories[keys[0]])
    body_p,body_r,mount=body_frame_mount(ROOT/"ros2_ws/src/uav_tracking_bringup/models"/args.vehicle_model/"model.sdf")
    evidence=declared_enu_evidence(args.trial,args.target_class)
    odometry.sort(key=lambda r:r["time_s"])
    vehicle_truth=series("stage1_uav")
    alignment=freeze_ego_alignment(odometry,vehicle_truth,body_p,body_r,args.calibration_duration_s)
    sensitivity=freeze_ego_alignment(odometry,vehicle_truth,body_p,body_r,args.calibration_duration_s,rotation_policy="ego_attitude_relation")
    anchor_data=json.loads(args.anchor_report.read_text())["anchors"][args.target_class]
    evaluation_start=alignment["calibration_end_s"]
    if Path(anchor_data["calibration_source_trial"]).name==args.trial.name:
        evaluation_start=max(evaluation_start,anchor_data["calibration_end_s"])
    if args.physical_identity_report:
        physical=json.loads(args.physical_identity_report.read_text())
        target_truth={uuid:series(task["initial_mapping"]["physical_id"]) for uuid,task in physical.get("tasks",{}).items()
                      if task.get("initial_mapping",{}).get("physical_id")}
    else:target_truth=series("target_"+args.target_class)
    scored=score_states(sorted(states,key=lambda r:r["time_s"]),target_truth,alignment,
                        np.asarray(anchor_data["model_local_anchor_m"]),evaluation_start_s=evaluation_start)
    frames=scored.pop("frames")
    sensitivity_scored=score_states(sorted(states,key=lambda r:r["time_s"]),target_truth,sensitivity,
                                    np.asarray(anchor_data["model_local_anchor_m"]),evaluation_start_s=evaluation_start)
    sensitivity_scored.pop("frames")
    result={"schema_version":2,"trial":str(args.trial.resolve()),"target_class":args.target_class,"bag":metadata,
            "ego_alignment":alignment,"body_mount":mount,"frozen_surface_anchor":anchor_data,
            "declared_frame_evidence":evidence,"raw_px4_odometry_diagnostics":odometry_diagnostics(raw_odometry),
            "independent_task_identity_report_sha256":hashlib.sha256(args.physical_identity_report.read_bytes()).hexdigest() if args.physical_identity_report else None,
            "attitude_derived_alignment_sensitivity":{"ego_alignment":sensitivity,"online_state_accuracy":sensitivity_scored,
                "interpretation":"Retained schema-1 sensitivity, not primary: treating estimated initial heading bias as a map-axis rotation is incompatible with the declared GNSS ENU axes contract. No holdout outcomes choose the primary transform."},
            "anchor_report_sha256":hashlib.sha256(args.anchor_report.read_bytes()).hexdigest(),
            "evaluation_start_s":evaluation_start,"online_state_accuracy":scored,
            "control_jitter":command_jitter(sorted(commands,key=lambda r:r["time_s"])),
            "claim_boundary":"Actual online map-frame state includes runtime odometry/TF. Primary uses source-declared identical ENU axes and vehicle-only first-segment translation calibration, with held-out ego residuals. Attitude-derived rotation is retained separately as sensitivity. No target/holdout data select or refit alignment. Target anchor remains a calibrated surface approximation; no independent model-center accuracy claim.",
            "command":[sys.executable,*sys.argv]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sidecar=args.output.with_suffix(".frames.jsonl")
    with sidecar.open("w") as handle:
        for frame in frames:handle.write(json.dumps(frame,allow_nan=False)+"\n")
    result["frame_sidecar"]=str(sidecar)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"output":str(args.output),"ego_holdout":alignment["splits"]["ego_holdout"],"online":scored},allow_nan=False),flush=True)


if __name__=="__main__":main()
