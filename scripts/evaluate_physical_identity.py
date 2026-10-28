"""Independent offline physical-identity evaluation of stage-two recordings.

Runtime nodes never see these Gazebo actor names. Boxes come from actual
static render meshes and camera/actor GT poses. MOT metrics and designated
identity safety are separate: a multi-GT match is UNKNOWN for selected identity
even when a benchmark's one-to-one assignment chooses one of the candidates.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_stage1_flight import open_bag_reader,stamp_s,read_monitor_events,shutter_windows
from extract_research_recording import model_camera_mount,pose_dict
from uav_tracking.research_labels import target_mesh_points,interpolate_pose,project_mesh,quaternion_matrix
from uav_tracking.research_metrics import identity_metrics,iou_matrix
from uav_tracking.stage2_identity import physical_identity_match,selected_identity_summary


def bracketed_local_pose(rows,timestamp,max_gap_s=.10):
    """Local camera/link geometry at image source time, never latest or extrapolated."""
    times=[row["time_s"] for row in rows]
    index=bisect_left(times,timestamp)
    if index<len(rows) and abs(times[index]-timestamp)<1e-9:return interpolate_pose(rows,timestamp)
    if index==0 or index==len(rows) or times[index]-times[index-1]>max_gap_s:return None
    return interpolate_pose(rows,timestamp,tolerance_s=max_gap_s)


def dynamic_camera_pose(timestamp,vehicle,base_links,camera_links,camera_tf):
    """Independent physics camera GT, corroborated by recorded source-time TF.

    camera_link is already the optical frame in this project. Its local TF
    must therefore NOT receive another FLU-to-optical rotation. The separate
    Gazebo tracking_camera_mount link is FLU and does receive that rotation.
    map->base_link TF/PX4 odometry and command angles never enter this path.
    """
    try:
        poses=[interpolate_pose(vehicle,timestamp),bracketed_local_pose(base_links,timestamp),
               bracketed_local_pose(camera_links,timestamp),bracketed_local_pose(camera_tf,timestamp)]
    except (TypeError,ValueError):return None,{"status":"UNKNOWN","reason":"invalid_dynamic_camera_geometry"}
    names=("vehicle_gt","physical_base_link_gt","physical_camera_link_gt","feedback_camera_tf")
    missing=[name for name,pose in zip(names,poses) if pose is None]
    if missing:return None,{"status":"UNKNOWN","reason":"missing_bracketed_dynamic_camera_geometry","missing":missing}
    if any(not np.isfinite(position).all() or not np.isfinite(rotation).all() for position,rotation in poses):
        return None,{"status":"UNKNOWN","reason":"invalid_dynamic_camera_geometry"}
    (world_p,world_r),(base_p,base_r),(camera_p,camera_r),(tf_p,tf_r)=poses
    optical=quaternion_matrix([-.5,.5,-.5,.5])
    independent_body_p=base_r.T@(camera_p-base_p)
    independent_body_r=base_r.T@camera_r@optical
    translation=float(np.linalg.norm(tf_p-independent_body_p))
    angle=float(np.arccos(np.clip((np.trace(tf_r.T@independent_body_r)-1)/2,-1,1)))
    audit={"status":"KNOWN","source_image_s":timestamp,"tf_translation_error_m":translation,"tf_angle_error_rad":angle,
           "method":"Bracketed physical model-relative camera/base link GT and vehicle world GT, cross-checked with bracketed feedback-source base_link<-camera_link optical TF; no runtime map pose or commanded gimbal angles"}
    # Same independently declared tolerances as the physical-gimbal evaluator.
    if translation>=.005 or angle>=.03:
        audit.update(status="UNKNOWN",reason="feedback_camera_tf_disagrees_with_independent_physics")
        return None,audit
    return (world_p+world_r@camera_p,world_r@camera_r@optical),audit


def build_identity_frames(diagnostics,track_snapshots,gt_at,*,selections=None,shutters=None):
    """Pure helper for test fixtures and recorded data; no simulator calls."""
    selections=selections or [];shutters=shutters or []
    snapshots={round(float(s["acquisition_s"]),6):s for s in track_snapshots if not s.get("projected",True)}
    tasks={};frames=[];selected_rows=[];last_uuid="";missing_snapshots=0
    selection_by_uuid={str(s["target_uuid"]):s for s in selections}
    for diagnostic in sorted(diagnostics,key=lambda row:row["stamp_s"]):
        timestamp=float(diagnostic["stamp_s"])
        snapshot=snapshots.get(round(timestamp,6))
        truth=gt_at(timestamp)
        gt=truth.get("gt",[])
        truth_complete=truth.get("truth_complete",True)
        fresh=[]
        if snapshot is None:
            missing_snapshots+=1
        else:
            fresh=[{"id":str(t["track_id"]),"bbox":t["bbox_xyxy"],"class_name":t["class_name"],"confidence":t["confidence"]}
                   for t in snapshot["tracks"] if t["matched"] and not snapshot["projected"]]
        uuid=str(snapshot.get("target_uuid", "")) if snapshot else last_uuid
        track_id=str(snapshot.get("target_track_id", "")) if snapshot else None
        for item in fresh:item["selected"]=item["id"]==track_id
        selected=next((p for p in fresh if p["id"]==track_id),None)
        in_shutter=any(w["start_s"]-1 <= timestamp <= (w["end_s"] or float("inf"))+1 for w in shutters)
        # This frame-level subset cannot silently turn occlusion into a
        # false-positive score by removing just the hidden object's GT.
        visible=(truth.get("all_fully_in_frame",False) and not truth.get("overlap",True) and not in_shutter)
        frame={"time_s":timestamp,"gt":gt,"pred":fresh,"visible_geometry_eligible":visible,
               "acquisition_s":timestamp,"shutter_guard":in_shutter,"truth_complete":truth_complete,"truth_reason":truth.get("reason"),"target_uuid":uuid}
        if truth.get("camera_geometry") is not None:frame["camera_geometry"]=truth["camera_geometry"]
        if uuid and uuid not in tasks:
            request=selection_by_uuid.get(uuid)
            selection_overlap=None
            if request and selected is not None:
                selection_overlap=float(iou_matrix([request["bbox"]],[selected["bbox"]])[0,0])
            image_time=request.get("image_stamp_s") if request else None
            valid_source=bool(request and type(image_time) in (int,float)
                              and -.05<=request["time_s"]-image_time<=.60)
            source_truth=gt_at(float(image_time)) if valid_source else {"gt":[]}
            source_occluded=any(w["start_s"]-1<=image_time<=(w["end_s"] or float("inf"))+1 for w in shutters) if valid_source else None
            # Establish the requested actor from the REQUEST box at its own
            # source image time. Using the track's chosen box here would
            # relabel an initially wrong association as the intended actor.
            matching=physical_identity_match(request["bbox"] if request else None,source_truth.get("gt",[]),
                class_name=request.get("class_name", "") if request else "",fresh=valid_source,
                externally_occluded=source_occluded if source_truth.get("truth_complete",True) else None)
            if not source_truth.get("truth_complete",True):matching["reason"]="incomplete_independent_ground_truth"
            corroborated=bool(valid_source)
            tasks[uuid]={"first_fresh_image_s":timestamp,"initial_track_id":track_id,
                         "physical_id":matching["physical_id"] if corroborated else None,
                         "initial_geometric_match":matching,"selection_corroborated":corroborated,
                         "selection_source_image_s":image_time,
                         "selection_box_iou_with_selected_track":selection_overlap,
                         "initialization_status":"CONFIRMED" if corroborated and matching["physical_id"] else "UNKNOWN"}
        if uuid and uuid in tasks:
            expected=tasks[uuid]["physical_id"]
            if selected is None:
                matching={"physical_id":None,"status":"unknown","reason":"no_fresh_selected_detection"}
            else:
                matching=physical_identity_match(selected["bbox"],gt,class_name=selected["class_name"],fresh=True,
                                                 externally_occluded=in_shutter if truth_complete else None)
                if not truth_complete:matching["reason"]="incomplete_independent_ground_truth"
            physical=matching["physical_id"]
            if expected is None:
                status="UNKNOWN_TASK_INITIAL_ID"
            elif selected is None:
                status="NOT_OBSERVED"
            elif physical is None:
                status="UNKNOWN_GEOMETRY"
            else:
                status="CORRECT" if physical==expected else "WRONG_PHYSICAL_ACTOR"
            selected_rows.append({"time_s":timestamp,"target_uuid":uuid,"expected_physical_id":expected,
                                  "selected_track_id":track_id,"matched_physical_id":physical,"status":status,
                                  "visible_geometry_eligible":visible,"matching":matching,"match":matching})
            if expected is not None:
                frame["selected_gt_id"]=expected
                frame["selected_track_id"]=track_id
            frame["expected_physical_id"]=expected
            frame["selected_physical_match"]=matching
        frames.append(frame)
        last_uuid=uuid
    return frames,tasks,selected_rows,missing_snapshots


def selected_summary(rows):
    counts={key:sum(row["status"]==key for row in rows) for key in
            ("CORRECT","WRONG_PHYSICAL_ACTOR","NOT_OBSERVED","UNKNOWN_GEOMETRY","UNKNOWN_TASK_INITIAL_ID")}
    known=counts["CORRECT"]+counts["WRONG_PHYSICAL_ACTOR"]
    return {"frames":len(rows),"counts":counts,
            "correct_fraction_all_task_opportunities":counts["CORRECT"]/len(rows) if rows else None,
            "known_match_correct_fraction":counts["CORRECT"]/known if known else None,
            "unknown_or_unobserved_fraction":(len(rows)-known)/len(rows) if rows else None,
            "safety_result":"FAIL" if counts["WRONG_PHYSICAL_ACTOR"] else "NO_OBSERVED_WRONG_MATCH" if known else "INCOMPLETE_EVIDENCE",
            "interpretation":"NO_OBSERVED_WRONG_MATCH does not certify unknown/occluded intervals. Multiple plausible GT actors are UNKNOWN, not arbitrarily assigned by nearest position, highest IoU, or stable task UUID."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial",type=Path)
    parser.add_argument("--target-class",choices=["person","car"],required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--write-frames",action="store_true")
    parser.add_argument("--vehicle-model",choices=["x500_stage1","x500_stage3"],default=None)
    parser.add_argument("--camera-mount-mode",choices=["auto","fixed","gimbal"],default="auto")
    args=parser.parse_args()
    config_path=args.trial/"run_config.json"
    run_config=json.loads(config_path.read_text()) if config_path.is_file() else {}
    is_stage3=args.vehicle_model=="x500_stage3" or run_config.get("stage")==3
    if is_stage3 and args.camera_mount_mode=="fixed":raise ValueError("Stage-three physical gimbal recordings cannot use a fixed camera truth mount")
    dynamic=is_stage3 or args.camera_mount_mode=="gimbal"
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    topics=["/tracking/tracks","/tracking/detection_diagnostics","/tracking/selection",
            "/ground_truth/poses","/ground_truth/vehicle_poses","/camera/color/camera_info","/tf"]
    trajectories=defaultdict(list);diagnostics=[];snapshots=[];selections=[];camera=None;counts=defaultdict(int)
    local_camera_tf=[];physical_links=defaultdict(list);invalid_link_parents=Counter()
    with open_bag_reader(args.trial/"rosbag",rosbag2_py) as (reader,metadata):
        types={t.name:t.type for t in reader.get_all_topics_and_types()}
        reader.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
        classes={t:get_message(types[t]) for t in topics if t in types}
        last_print=time.monotonic()
        while reader.has_next():
            topic,data,_ns=reader.read_next();msg=deserialize_message(data,classes[topic]);counts[topic]+=1
            if topic.startswith("/ground_truth/"):
                for transform in msg.transforms:
                    trajectories[transform.child_frame_id.strip("/")].append(pose_dict(transform))
                    child=transform.child_frame_id.replace("::","/").strip("/").rsplit("/",1)[-1]
                    if child in {"base_link","tracking_camera_mount"}:
                        parent=transform.header.frame_id.replace("::","/").strip("/").rsplit("/",1)[-1]
                        if parent=="stage1_uav":physical_links[child].append(pose_dict(transform))
                        else:invalid_link_parents[f"{parent}->{child}"]+=1
            elif topic=="/tf":
                for transform in msg.transforms:
                    if (transform.header.frame_id.strip("/"),transform.child_frame_id.strip("/"))==("base_link","camera_link"):
                        local_camera_tf.append(pose_dict(transform))
            elif topic=="/tracking/tracks":snapshots.append(json.loads(msg.data))
            elif topic=="/tracking/detection_diagnostics":diagnostics.append(json.loads(msg.data))
            elif topic=="/tracking/selection" and msg.action==0:
                selections.append({"time_s":stamp_s(msg.header.stamp),"target_uuid":msg.target_uuid,
                                   "bbox":[msg.center_u_px-msg.width_px/2,msg.center_v_px-msg.height_px/2,
                                           msg.center_u_px+msg.width_px/2,msg.center_v_px+msg.height_px/2]})
            elif topic=="/camera/color/camera_info":
                camera={"width":msg.width,"height":msg.height,"intrinsics":[msg.k[0],msg.k[4],msg.k[2],msg.k[5]]}
            if time.monotonic()-last_print>15:
                print(f"read {sum(counts.values())} identity/truth messages",flush=True);last_print=time.monotonic()
    def key_for(entity):
        keys=[key for key in trajectories if key==entity or key.endswith("::"+entity) or key.rsplit("/",1)[-1]==entity]
        if len(keys)!=1:raise ValueError(f"Missing/ambiguous GT {entity}: {keys}")
        return keys[0]
    vehicle=sorted(trajectories[key_for("stage1_uav")],key=lambda r:r["time_s"])
    targets={f"stage2_{args.target_class}_{i}":sorted(trajectories[key_for(f"stage2_{args.target_class}_{i}")],key=lambda r:r["time_s"]) for i in range(3)}
    points,mesh=target_mesh_points(ROOT/"ros2_ws/src/uav_tracking_bringup/models",args.target_class)
    for rows in [local_camera_tf,*physical_links.values()]:rows.sort(key=lambda row:row["time_s"])
    if dynamic:
        mount={"mode":"physical_gimbal_source_time","vehicle_model":"x500_stage3" if is_stage3 else args.vehicle_model,
               "dynamic_camera_tf_samples":len(local_camera_tf),"physical_base_link_gt_samples":len(physical_links["base_link"]),
               "physical_camera_link_gt_samples":len(physical_links["tracking_camera_mount"]),"invalid_link_parent_counts":dict(invalid_link_parents),
               "maximum_interpolation_gap_s":.10,"tf_vs_physics_maximum_translation_m":.005,"tf_vs_physics_maximum_angle_rad":.03,
               "method":"Independent vehicle world and model-relative physical camera/base link GT at image source time, cross-validated against local feedback-driven optical TF; no fixed-mount fallback"}
    else:mount_p,mount_r,mount=model_camera_mount(ROOT)
    events,_=read_monitor_events(args.trial/"telemetry.jsonl",args.trial/"summary.json")
    shutters=shutter_windows(events)
    # Image source timestamps are test-driver/UI metadata, not inferred from
    # the first successfully selected track. Missing linkage remains unknown.
    telemetry=[json.loads(line) for line in (args.trial/"telemetry.jsonl").read_text().splitlines() if line.strip()]
    for request in selections:
        matches=[event for event in telemetry if event.get("kind") in ("initial_selection_requested","explicit_reselection_requested")
                 and event.get("target_uuid")==request["target_uuid"] and type(event.get("image_stamp_s")) in (int,float)]
        request["class_name"]=args.target_class
        request["image_stamp_s"]=matches[0]["image_stamp_s"] if len(matches)==1 else None
    def gt_at(timestamp):
        pose=interpolate_pose(vehicle,timestamp)
        if pose is None or camera is None:
            return {"gt":[],"all_fully_in_frame":False,"truth_complete":False,"reason":"missing_bracketed_camera_truth"}
        camera_geometry=None
        if dynamic:
            camera_pose,camera_geometry=dynamic_camera_pose(timestamp,vehicle,physical_links["base_link"],physical_links["tracking_camera_mount"],local_camera_tf)
            if camera_pose is None:
                return {"gt":[],"all_fully_in_frame":False,"truth_complete":False,"reason":camera_geometry["reason"],"camera_geometry":camera_geometry}
        else:
            p,r=pose;camera_pose=(p+r@mount_p,r@mount_r)
        gt=[];complete=True;truth_complete=True
        for identity,trajectory in targets.items():
            target=interpolate_pose(trajectory,timestamp)
            if target is None:
                complete=False;truth_complete=False;continue
            projection=project_mesh(points,target,camera_pose,camera["intrinsics"],camera["width"],camera["height"])
            if projection:
                gt.append({"id":identity,"class_name":args.target_class,**projection})
                complete=complete and projection["fully_in_frame"]
            else:
                complete=False
        overlaps=iou_matrix([g["bbox"] for g in gt],[g["bbox"] for g in gt])
        np.fill_diagonal(overlaps,0)
        return {"gt":gt,"all_fully_in_frame":complete,"truth_complete":truth_complete,"overlap":bool(np.any(overlaps>.01)),
                "reason":"static_mesh_projection_amodal","camera_geometry":camera_geometry}
    frames,tasks,selected,missing=build_identity_frames(diagnostics,snapshots,gt_at,selections=selections,shutters=shutters)
    visible=[frame for frame in frames if frame["visible_geometry_eligible"]]
    # Standard association metrics must be evaluated within explicit tasks;
    # a legitimate reselect is never counted as an identity switch across tasks.
    task_results={}
    for uuid,task in tasks.items():
        task_frames=[f for f in frames if f["target_uuid"]==uuid]
        mot_frames=[f for f in task_frames if f["truth_complete"]]
        task_visible=[f for f in task_frames if f["visible_geometry_eligible"]]
        task_rows=[r for r in selected if r["target_uuid"]==uuid]
        task_results[uuid]={"initial_mapping":task,"opportunities":len(task_frames),
                            "mot_truth_complete_opportunities":len(mot_frames),"mot_unscorable_missing_truth_opportunities":len(task_frames)-len(mot_frames),
                            "amodal_simulation_mot":identity_metrics(mot_frames),
                            "unoccluded_geometry_mot":identity_metrics(task_visible),
                            "selected_physical_identity_all":selected_summary(task_rows),
                            "selected_physical_identity_unoccluded":selected_summary([r for r in task_rows if r["visible_geometry_eligible"]]),
                            "conservative_selected_identity":selected_identity_summary(task_rows)}
    result={"schema_version":1,"evaluation_status":"RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS","source_trial":str(args.trial.resolve()),"target_class":args.target_class,
            "inputs":{"counts":dict(counts),"storage":metadata,"command":[sys.executable,*sys.argv]},
            "camera":camera,"mount":mount,"mesh":mesh,"opportunities":len(frames),
            "camera_geometry_status_counts":dict(Counter((frame.get("camera_geometry") or {}).get("status","FIXED_MOUNT") for frame in frames)),
            "missing_fresh_snapshot_opportunities":missing,"geometric_unoccluded_opportunities":len(visible),
            "tasks":task_results,"selected_physical_identity_all":selected_summary(selected),
            "selected_physical_identity_unoccluded":selected_summary([r for r in selected if r["visible_geometry_eligible"]]),
            "conservative_selected_identity":selected_identity_summary(selected),
            "selected_identity_timeline":selected,
            "label_protocol":"Exact-source-time independent static render mesh projection, Gazebo actor and camera GT. Physical-gimbal recordings use bracketed independent actual camera-link/vehicle GT cross-checked against bracketed local feedback TF, never a static mount or latest/command pose. Missing dynamic geometry remains unknown and in selected-task denominators; frames without complete independent GT are unscorable in MOT rather than invented empty-GT false positives. Full/amodal metrics are explicitly diagnostic. The unoccluded geometry subset requires all three targets fully in frame, no pair of GT boxes with IoU>.01, and outside +/-1s shutter guards. Independent visual review remains necessary to publish as visible detection labels.",
            "freshness_protocol":"Only non-projected track snapshots with matched=true count as detected tracks. Empty diagnostic frames remain in denominator; stale stored boxes cannot become true positives.",
            "selected_identity_protocol":"Expected actor is established independently from the user's/test script's REQUEST box at its recorded source image_stamp_s, never from the tracker-selected box. Missing source time or uncertain request-to-GT mapping makes the task UNKNOWN. Each fresh selected track box is then independently compared against that expected actor. Physical matches require a unique full-in-frame IoU>=.5 candidate, no positive overlap with other same-class actors and no shutter guard. Ambiguous crossings are UNKNOWN. No nearest-3D shortcut, no UUID identity inference.",
            "metric_reference":"Portable HOTA/IDF1/CLEAR implementation validated against pinned official TrackEval formulas on 60 random 15-frame sequences, all 19 HOTA alpha values; see research_validation/trackeval_comparison.json"}
    if args.write_frames:result["frames"]=frames
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sidecar=args.output.with_suffix(".frames.jsonl")
    with sidecar.open("w") as handle:
        for frame in frames:handle.write(json.dumps(frame,allow_nan=False)+"\n")
    result["frame_sidecar"]=str(sidecar)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(f"Physical identity: {len(frames)} opportunities, {len(tasks)} tasks; {result['selected_physical_identity_all']}",flush=True)


if __name__=="__main__":
    try:
        main()
    except ValueError as error:
        # Failed/early-aborted trials must remain visible in research manifests,
        # rather than disappearing because no independent GT was recorded.
        if "--output" in sys.argv:
            output=Path(sys.argv[sys.argv.index("--output")+1])
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps({"schema_version":1,"evaluation_status":"INCOMPLETE_EVIDENCE",
                "reason":str(error),"command":[sys.executable,*sys.argv],
                "selected_physical_identity_all":None,
                "interpretation":"No physical identity conclusion is possible; failed trial retained, not scored as correct or as zero error."},indent=2)+"\n")
        print(f"INCOMPLETE_EVIDENCE: {error}",flush=True)
        raise SystemExit(2)
