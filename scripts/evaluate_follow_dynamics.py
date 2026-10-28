"""Offline GT follow transients and explicit-selection recovery, retaining failures."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_stage1_flight import read_rosbag, read_monitor_events, shutter_windows, summary
import evaluate_stage1_flight as bag_tools
from evaluate_online_state_accuracy import PoseSeries
from extract_research_recording import pose_dict
from uav_tracking.research_dynamics import transient_metrics


def recorded_configuration(trial, target_class):
    config=json.loads((trial/"run_config.json").read_text())
    stage=int(config.get("stage",1))
    runtime=trial/"configuration/runtime_parameters.yaml"
    snapshot=trial/"configuration"/f"stage{stage}_tracking_{target_class}.yaml"
    path=runtime if runtime.is_file() else snapshot
    if not path.is_file():raise ValueError("No recorded controller parameter snapshot; reference distances cannot be assumed")
    controller=yaml.safe_load(path.read_text())["uav_tracking_controller"]["ros__parameters"]
    for key in ("desired_distance_m","desired_height_m"):
        value=controller.get(key)
        if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError("Missing/invalid recorded controller reference: "+key)
        override=config.get(key)
        if override is not None:
            if runtime.is_file() and not math.isclose(value,override,abs_tol=1e-6):
                raise ValueError("run_config contradicts the actual runtime controller reference: "+key)
            value=float(override)
        config[key]=float(value)
    config["target_class"]=target_class
    config["controller_reference_evidence"]={"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                                             "selection":"RECORDED_RUNTIME_PARAMETERS" if runtime.is_file() else "RECORDED_CLASS_SNAPSHOT_WITH_EXPLICIT_OVERRIDES"}
    return config


def visual_metrics(records, states, statuses, start_s, end_s, *, multi=False):
    diagnostics=[];snapshots={};invalid=0
    for row in records:
        if row.topic not in {"/tracking/detection_diagnostics","/tracking/tracks"}:continue
        try:
            payload=json.loads(row.message.data)
            if row.topic=="/tracking/detection_diagnostics":
                if start_s<=payload["stamp_s"]<=end_s:diagnostics.append(payload)
            elif not payload.get("projected",True):snapshots[round(float(payload["acquisition_s"]),6)]=payload
        except (ValueError,TypeError,KeyError):invalid+=1
    pixels=[];normalized=[];selected_missing=0
    for diagnostic in diagnostics:
        try:
            width,height=diagnostic["image_size"]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (width,height)):raise ValueError("Invalid image dimensions")
            if multi:
                snap=snapshots.get(round(diagnostic["stamp_s"],6),{})
                boxes=[t["bbox_xyxy"] for t in snap.get("tracks",[]) if t.get("matched") and t["track_id"]==snap.get("target_track_id")]
            else:boxes=[d["bbox"] for d in diagnostic["detections"]]
            if len(boxes)!=1:selected_missing+=1;continue
            x1,y1,x2,y2=boxes[0]
            if not all(math.isfinite(v) for v in boxes[0]) or x2<=x1 or y2<=y1:raise ValueError("Invalid selected box")
            du,dv=(x1+x2)/2-width/2,(y1+y2)/2-height/2
            pixels.append(math.hypot(du,dv));normalized.append(math.hypot(du/width,dv/height))
        except (ValueError,TypeError,KeyError):invalid+=1
    state_times=[t for t,_ in states];first_latency={}
    for t,status in statuses:
        if not start_s<=t<=end_s or status.lifecycle not in (2,3):continue
        index=bisect_right(state_times,t)-1
        if index<0 or t-state_times[index]>.15:continue
        state=states[index][1]
        state_stamp=state.header.stamp.sec+state.header.stamp.nanosec*1e-9
        # Predicted states carry output time plus the age since the last
        # accepted image. Controllers may run after the short MEASURED
        # publication and consume this prediction as their first command.
        source=round(state_stamp-float(state.prediction_age_s),6)
        age=t-source
        if (state.state not in (1,2) or state.track_id==0 or state.track_id!=status.track_id
                or not start_s<=source<=end_s or not 0<=age<=.75):continue
        key=(str(state.target_uuid),int(state.track_id),round(source,9))
        first_latency.setdefault(key,t-source)
    return {"detection_opportunities":len(diagnostics),"center_observed_samples":len(pixels),
            "no_unique_or_fresh_selected_box":selected_missing,"invalid_visual_payloads":invalid,
            "observed_center_coverage":len(pixels)/len(diagnostics) if diagnostics else None,
            "detected_center_error_px":summary(pixels),"detected_center_normalized_error":summary(normalized),
            "image_to_first_tracking_command_sim_s":summary(first_latency.values()),
            "source_images_with_first_tracking_command":len(first_latency),
            "definition":"Box-center error uses one unique detection or the designated fresh matched track at the exact source image time; empty frames remain in the detection-opportunity denominator. It is conditional on observed detector boxes, not annotated physical center accuracy. Latency is acquisition to the first same-track active FOLLOW/PREDICT controller status (published with its command), deduplicated by task/track/accepted source image. The accepted image time is state.header minus prediction_age_s (rounded to microseconds); intervening timer predictions are not new images. Holds/failsafe are excluded. It includes estimator/controller delivery, ends before PX4/actuator response, and is a simulation-clock metric, not wall-time real-time capability."}


def evaluate(records, config, *, physical=None, events=None):
    events=events or []
    trajectories=defaultdict(list)
    states=[];statuses=[];selections=[]
    follow=None
    for row in sorted(records,key=lambda r:r.time_s):
        operational=max(row.time_s,row.received_sim_s) if row.received_sim_s is not None else row.time_s
        if row.topic.startswith("/ground_truth/"):
            for transform in row.message.transforms:
                trajectories[transform.child_frame_id.strip("/")].append(pose_dict(transform))
        elif row.topic=="/tracking/flight_phase" and row.message.data.split(":",1)[0].strip()=="FOLLOW" and follow is None:
            follow=operational
        elif row.topic=="/tracking/state":
            states.append((max(row.time_s,row.received_sim_s) if row.received_sim_s is not None else row.time_s,row.message))
        elif row.topic=="/tracking/status":statuses.append((operational,row.message))
        elif row.topic=="/tracking/selection" and row.message.action==0:selections.append((operational,row.message))
    if follow is None or not records:
        return {"evaluation_status":"INCOMPLETE_EVIDENCE","reason":"No FOLLOW handoff; no takeoff is certified by this evaluator"}
    end=max(max(r.time_s,r.received_sim_s if r.received_sim_s is not None else r.time_s) for r in records)
    def series(name):
        keys=[k for k in trajectories if k==name or k.endswith("::"+name) or k.rsplit("/",1)[-1]==name]
        return PoseSeries(trajectories[keys[0]]) if len(keys)==1 else None
    vehicle=series("stage1_uav")
    multi=config.get("stage")==2 or config.get("multi_target",False)
    mapping={uuid:task.get("initial_mapping",{}).get("physical_id") for uuid,task in (physical or {}).get("tasks",{}).items()}
    targets={name:series(name) for name in set(mapping.values()) if name}
    single=None if multi else series("target_"+config["target_class"])
    states.sort(key=lambda r:r[0]);statuses.sort(key=lambda r:r[0])
    selections.sort(key=lambda r:r[0]);selection_times=[r[0] for r in selections]
    state_times=[r[0] for r in states];status_times=[r[0] for r in statuses]
    distance=config["desired_distance_m"]
    height=config["desired_height_m"]
    def preceding(rows,times,t):
        index=bisect_right(times,t)-1
        return rows[index][1] if index>=0 and t-times[index]<=.15 else None
    samples=[]
    for i in range(int(math.floor((end-follow)/.1))+1):
        t=follow+i*.1
        state=preceding(states,state_times,t);status=preceding(statuses,status_times,t)
        request_index=bisect_right(selection_times,t)-1
        # A known requested physical actor persists even if the state stream
        # disappears; otherwise failure tails would silently lose GT errors.
        task_uuid=str(selections[request_index][1].target_uuid) if request_index>=0 else None
        identity=mapping.get(task_uuid) if multi else None
        target=targets.get(identity) if multi else single
        vp=vehicle.at(t) if vehicle is not None else None
        tp=target.at(t) if target is not None else None
        d=h=None
        if vp is not None and tp is not None:
            d=float(math.hypot(*(tp[0]-vp[0])[:2])-distance)
            h=float(vp[0][2]-tp[0][2]-height)
        measurement_age=(float(state.prediction_age_s)+t-(state.header.stamp.sec+state.header.stamp.nanosec*1e-9)) if state is not None else None
        active=bool(status is not None and state is not None and int(status.lifecycle) in (2,3)
                    and int(state.state) in (1,2) and 0<=measurement_age<=.75
                    and status.track_id==state.track_id and state.track_id!=0)
        samples.append({"time_s":t,"distance_error_m":d,"height_error_m":h,"active":active,
                        "target_uuid":str(state.target_uuid) if state is not None else None,
                        "reference_task_uuid":task_uuid,"expected_physical_id":identity})
    shutters=shutter_windows(events)
    first_shutter=min([end]+[w["start_s"] for w in shutters if w["start_s"]>follow]
                      +[t for t,_ in selections if t>follow])
    windows=[{"kind":"initial_follow_before_first_shutter","start_s":follow,"end_s":first_shutter}]
    # Every explicit selection is retained; later requests delimit earlier
    # requests. No successful tail is selected after seeing the errors.
    requests=sorted((t,msg) for t,msg in selections if t>=follow)
    for i,(t,msg) in enumerate(requests):
        window_end=requests[i+1][0] if i+1<len(requests) else end
        windows.append({"kind":"explicit_selection","target_uuid":str(msg.target_uuid),"start_s":t,"end_s":window_end})
    for window in windows:
        for key,band in (("distance",max(.5,.1*distance)),("height",.25)):
            scoped=[{"time_s":r["time_s"],
                     "error_m":r[key+"_error_m"] if window["kind"]!="explicit_selection" or r["reference_task_uuid"]==window["target_uuid"] else None,
                     "active":r["active"] and (window["kind"]!="explicit_selection" or r["target_uuid"]==window["target_uuid"])} for r in samples]
            window[key]=transient_metrics(scoped,window["start_s"],window["end_s"],band_m=band) if window["end_s"]>window["start_s"] else None
        if window["kind"]=="explicit_selection":
            confirm=next((t for t,msg in states if t>=window["start_s"] and t<=window["end_s"] and str(msg.target_uuid)==window["target_uuid"] and int(msg.state)==1
                          and 0<=float(msg.prediction_age_s)+(t-(msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9))<=.75),None)
            window["first_measured_confirmation_after_request_s"]=confirm-window["start_s"] if confirm is not None else None
            window["confirmation_censored"]=confirm is None
    return {"evaluation_status":"RECORDED_WITH_CENSORED_FAILURES","interval":{"start_s":follow,"end_s":end},
            "visual_control_metrics":visual_metrics(records,states,statuses,follow,end,multi=multi),
            "reference":{"desired_horizontal_distance_m":distance,"desired_height_above_model_origin_m":height,
                         "recorded_parameters":config.get("controller_reference_evidence"),
                         "truth":"Independent Gazebo UAV/target model origins, bracketed at fixed 10 Hz; no estimated target used as truth",
                         "multi_target_mapping":"Independent initial REQUEST-box physical identity report; unknown mapping remains missing" if multi else "Unique target model"},
            "whole_interval":{"scheduled_samples":len(samples),"matched_truth_samples":sum(r["distance_error_m"] is not None for r in samples),
                              "distance_error_m":summary(r["distance_error_m"] for r in samples),"height_error_m":summary(r["height_error_m"] for r in samples),
                              "inactive_control_samples":sum(not r["active"] for r in samples)},
            "windows":windows,"frames":samples,
            "claim_boundary":"Moving-target task transients, not stationary reference step tests. Model-origin errors include the physical difference from the controller's RGB-D visible-surface anchor; they are not localization bias or the controller's own anchor errors. Car height settling can therefore remain censored from reference geometry alone. Initial window ends at the first commanded occlusion or next task request by protocol. Whole-interval errors retain all later occlusion/loss/hover. Explicit selections are separate UUID-scoped windows, with missing truth and unachieved settling retained as right-censored. Phases/status/requests use max(source stamp, receive /clock), so late delivery cannot backdate control. These metrics do not override flight safety acceptance."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial",type=Path);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--target-class",choices=["person","car"],required=True)
    parser.add_argument("--physical-identity-report",type=Path)
    args=parser.parse_args()
    config=recorded_configuration(args.trial,args.target_class)
    physical=json.loads(args.physical_identity_report.read_text()) if args.physical_identity_report else None
    bag_tools.TOPICS=tuple(dict.fromkeys(bag_tools.TOPICS+("/tracking/tracks",)))
    records,metadata=read_rosbag(args.trial/"rosbag")
    events,_=read_monitor_events(args.trial/"telemetry.jsonl",args.trial/"summary.json")
    result=evaluate(records,config,physical=physical,events=events)
    frames=result.pop("frames",[])
    result.update(schema_version=1,trial=str(args.trial),bag=metadata,
                  physical_identity_sha256=hashlib.sha256(args.physical_identity_report.read_bytes()).hexdigest() if args.physical_identity_report else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sidecar=args.output.with_suffix(".frames.jsonl")
    with sidecar.open("w") as handle:
        for row in frames:handle.write(json.dumps(row,allow_nan=False)+"\n")
    result["frame_sidecar"]=str(sidecar)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":result["evaluation_status"],"output":str(args.output)},indent=2))
    return 0 if result["evaluation_status"]=="RECORDED_WITH_CENSORED_FAILURES" else 2


if __name__=="__main__":raise SystemExit(main())
