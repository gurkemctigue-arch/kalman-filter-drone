"""Extract independent-pose replay and static-mesh GT from a recorded flight.

RGB snapshots are selected by time, never by detector success. The output
retains missed detections and rejected/ineligible label opportunities. Only
fully in-frame, shutter-free samples form the clearly labelled detection
subset; overlays require a separate visual review before metric publication.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluate_stage1_flight import open_bag_reader,stamp_s,read_monitor_events,shutter_windows
from uav_tracking.research_labels import quaternion_matrix,rpy_matrix,interpolate_pose,target_mesh_points,project_mesh


def pose_dict(transform):
    p,q=transform.transform.translation,transform.transform.rotation
    return {"time_s":stamp_s(transform.header.stamp),"position_m":[p.x,p.y,p.z],"quaternion_xyzw":[q.x,q.y,q.z,q.w]}


def source_hash(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        while chunk:=handle.read(4*1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def measurement_observation(available):
    """Keep every candidate; ambiguity gives no single replay measurement.

    A stage-one *scene* can still produce several detections of one vehicle.
    This offline extractor must neither abort detection evaluation nor use
    truth/confidence to choose a convenient observation for the legacy replay.
    """
    candidates = [{
        "candidate_id": int(item.candidate_id),
        "class_name": str(item.class_name),
        "acquisition_s": stamp_s(item.header.stamp),
        "confidence": float(item.confidence),
        "depth_valid": bool(item.depth_valid),
        "depth_m": float(item.depth_m),
        "depth_valid_ratio": float(item.depth_valid_ratio),
        "depth_std_m": float(item.depth_std_m),
        "position_camera_m": [float(getattr(item.position_camera_m, axis)) for axis in "xyz"],
        "bbox": [float(getattr(item, name)) for name in (
            "bbox_x_min_px", "bbox_y_min_px", "bbox_x_max_px", "bbox_y_max_px")],
    } for item in available]
    if len(available) != 1:
        reason = "multiple_candidates_no_single_measurement" if available else "no_observation"
        return None, {"observation_count": len(available), "observation_reason": reason,
                      "candidate_observations": candidates}
    observation = available[0]
    return observation, {"observation_count": 1,
                         "observation_reason": "unique_observation" if observation.depth_valid else "unique_invalid_depth",
                         "candidate_observations": candidates}


def camera_model_resources(root:Path) -> tuple[list[Path],str]:
    """Use the explicitly selected PX4 tree; never search another installation."""
    configured=os.environ.get("STAGE1_PX4_ROOT")
    px4=Path(configured if configured is not None else "/root/PX4-Autopilot")
    return [root/"ros2_ws/src/uav_tracking_bringup/models",px4/"Tools/simulation/gz/models"],(
        "STAGE1_PX4_ROOT" if configured is not None else "historical_default")


def camera_model_source_hashes(model:Path,resources:list[Path]) -> dict[str,str]:
    """Bind the expanded mount to each locally resolved included model SDF."""
    sources={}
    def visit(path):
        path=path.resolve(strict=True)
        if str(path) in sources:return
        sources[str(path)]=source_hash(path)
        for include in ET.parse(path).getroot().findall(".//include/uri"):
            uri=(include.text or "").strip()
            if not uri.startswith("model://"):
                raise ValueError("Unsupported camera model include URI: "+uri)
            relative=Path(uri[len("model://"):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid camera model include URI: "+uri)
            candidate=next((base/relative/"model.sdf" for base in resources
                            if (base/relative/"model.sdf").is_file()),None)
            if candidate is None:
                raise ValueError("Camera model include absent from declared resources: "+uri)
            visit(candidate)
    visit(model)
    return sources


def model_camera_mount(root:Path) -> tuple[np.ndarray,np.ndarray,dict]:
    """Resolve all merged SDF frames, including inherited x500_base .24 pose."""
    model=root/"ros2_ws/src/uav_tracking_bringup/models/x500_stage1/model.sdf"
    resources,selection=camera_model_resources(root)
    sources=camera_model_source_hashes(model,resources)
    resource=os.pathsep.join(str(path) for path in resources)
    env=dict(os.environ,GZ_SIM_RESOURCE_PATH=resource,SDF_PATH=resource)
    result=subprocess.run(["gz","sdf","-p",str(model)],capture_output=True,text=True,env=env,timeout=30,check=True)
    sdf=ET.fromstring(result.stdout)
    model_xml=sdf.find("model")
    frames={"__model__":(None,np.zeros(3),np.eye(3))}
    for item in model_xml:
        if item.tag not in {"link","frame","joint"}:
            continue
        name=item.attrib["name"]
        pose=item.find("pose")
        values=np.fromstring(pose.text if pose is not None and pose.text else "0 0 0 0 0 0",sep=" ")
        parent=pose.attrib.get("relative_to") if pose is not None else None
        if not parent:
            parent=item.attrib.get("attached_to","__model__") if item.tag=="frame" else "__model__"
        frames[name]=(parent,values[:3],rpy_matrix(*values[3:]))
    def resolve(name,seen=()):
        if name in seen or name not in frames:
            raise ValueError(f"Cannot resolve SDF frame {name}, known={list(frames)}")
        parent,p,r=frames[name]
        if parent is None:
            return p,r
        pp,pr=resolve(parent,seen+(name,))
        return pp+pr@p,pr@r
    position,rotation=resolve("tracking_camera_mount")
    # Gazebo camera sensor uses FLU optical axis +X; ROS optical +Z is the
    # fixed optical->FLU rotation. Pitch already lives in the resolved mount.
    optical=quaternion_matrix([-.5,.5,-.5,.5])
    return position,rotation@optical,{"camera_model_offset_m":position.tolist(),"camera_model_rotation":(rotation@optical).tolist(),
            "expanded_sdf_sha256":hashlib.sha256(result.stdout.encode()).hexdigest(),
            "resolved_model_sdf_sha256":sources,
            "declared_model_resource_roots":[str(path.resolve()) for path in resources],
            "px4_model_resource_selection":selection,
            "method":"gz sdf -p merged model/frame resolution; static model camera mount plus FLU<-optical; independent of PX4 odometry/TF position"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--target-class",choices=["person","car"],required=True)
    parser.add_argument("--sample-period-s",type=float,default=1.0)
    parser.add_argument("--max-images",type=int,default=45)
    parser.add_argument("--skip-images",action="store_true")
    args=parser.parse_args()
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    bag=args.trial/"rosbag"
    args.output.mkdir(parents=True,exist_ok=True)
    previous_path=args.output/"recording.json"
    previous=json.loads(previous_path.read_text()) if args.skip_images and previous_path.exists() else {}
    previous_images={round(f["time_s"],6):f.get("image_file") for f in previous.get("frames",[])}
    trajectories=defaultdict(list);observations=defaultdict(list);diagnostics=[];tracks=[];camera=None
    topics=["/clock","/tracking/observations","/tracking/detection_diagnostics","/tracking/tracks",
            "/ground_truth/poses","/ground_truth/vehicle_poses","/camera/color/camera_info"]
    with open_bag_reader(bag,rosbag2_py) as (reader,storage):
        types={t.name:t.type for t in reader.get_all_topics_and_types()}
        reader.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
        classes={t:get_message(types[t]) for t in topics if t in types}
        last_print=time.monotonic();counts=Counter()
        while reader.has_next():
            topic,data,_record_ns=reader.read_next()
            msg=deserialize_message(data,classes[topic]);counts[topic]+=1
            if topic.startswith("/ground_truth/"):
                for transform in msg.transforms:
                    trajectories[transform.child_frame_id.strip("/")].append(pose_dict(transform))
            elif topic=="/tracking/observations":
                observations[round(stamp_s(msg.header.stamp),6)].append(msg)
            elif topic=="/tracking/detection_diagnostics":
                diagnostics.append(json.loads(msg.data))
            elif topic=="/tracking/tracks":
                tracks.append(json.loads(msg.data))
            elif topic=="/camera/color/camera_info":
                camera={"width":msg.width,"height":msg.height,"intrinsics":[msg.k[0],msg.k[4],msg.k[2],msg.k[5]]}
            if time.monotonic()-last_print>15:
                print(f"metadata extracted {sum(counts.values())} messages",flush=True);last_print=time.monotonic()
    def choose(entity):
        candidates=[key for key in trajectories if key==entity or key.endswith("::"+entity) or key.rsplit("/",1)[-1]==entity]
        if len(candidates)!=1:
            raise ValueError(f"Expected unique truth {entity}; candidates={candidates}")
        return sorted(trajectories[candidates[0]],key=lambda r:r["time_s"])
    target=choose(f"target_{args.target_class}");vehicle=choose("stage1_uav")
    mount_p,mount_r,mount_info=model_camera_mount(ROOT)
    points,mesh_info=target_mesh_points(ROOT/"ros2_ws/src/uav_tracking_bringup/models",args.target_class)
    events,_metadata=read_monitor_events(args.trial/"telemetry.jsonl",args.trial/"summary.json")
    shutters=shutter_windows(events)
    rows=[];frames=[];next_image=-1.0
    for diag in sorted(diagnostics,key=lambda d:d["stamp_s"]):
        timestamp,arrival=float(diag["stamp_s"]),float(diag["completed_s"])
        vehicle_pose=interpolate_pose(vehicle,timestamp)
        target_pose=interpolate_pose(target,timestamp)
        arrival_pose=interpolate_pose(target,arrival)
        available=observations.get(round(timestamp,6),[])
        observation,observation_evidence=measurement_observation(available)
        point=None
        if vehicle_pose is not None:
            vp,vr=vehicle_pose;camera_pose=(vp+vr@mount_p,vr@mount_r)
            if observation is not None and observation.depth_valid:
                cp=observation.position_camera_m
                point=(camera_pose[0]+camera_pose[1]@np.asarray([cp.x,cp.y,cp.z])).tolist()
        else:
            camera_pose=None
        row={"time_s":timestamp,"arrival_s":arrival,"point_world_m":point,**observation_evidence,
             "confidence":float(observation.confidence) if observation else None,
             "valid_fraction":float(observation.depth_valid_ratio) if observation else 0.0,
             "depth_std_m":float(observation.depth_std_m) if observation else 0.0,
             "truth_position_m":target_pose[0].tolist() if target_pose else None,
             "truth_rotation":target_pose[1].tolist() if target_pose else None,
             "truth_arrival_s":arrival,"truth_arrival_position_m":arrival_pose[0].tolist() if arrival_pose else None,
             "truth_arrival_rotation":arrival_pose[1].tolist() if arrival_pose else None}
        rows.append(row)
        if camera_pose is not None and target_pose is not None and camera is not None:
            projection=project_mesh(points,target_pose,camera_pose,camera["intrinsics"],camera["width"],camera["height"])
        else:
            projection=None
        in_shutter=any(w["start_s"]-1.0<=timestamp<=(w["end_s"] or float("inf"))+1.0 for w in shutters)
        eligible=projection is not None and projection["fully_in_frame"] and not in_shutter
        row["calibration_eligible"]=eligible
        if timestamp>=next_image and len(frames)<args.max_images:
            next_image=timestamp+args.sample_period_s
            frame={"time_s":timestamp,"eligible_geometric_subset":eligible,
                   "exclusion_reason":"shutter_guard_interval" if in_shutter else "not_fully_in_frame_or_missing_pose" if not eligible else None,
                   "gt":[{"id":f"target_{args.target_class}","class_name":args.target_class,**projection}] if projection else [],
                   "pred":[{"id":str(index),"bbox":d["bbox"],"class_name":args.target_class,"confidence":d["confidence"]} for index,d in enumerate(diag["detections"])],
                   "image_file":previous_images.get(round(timestamp,6)),"review_status":"PENDING","label_source":"independent static render mesh and Gazebo pose; amodal"}
            frames.append(frame)
    dense_truth=[]
    for pose in target:
        dense_truth.append({"time_s":pose["time_s"],"position_m":pose["position_m"],"rotation":quaternion_matrix(pose["quaternion_xyzw"]).tolist()})
    if rows:
        rows[0]["truth_trajectory"]=dense_truth
    # RGB selected by the source frame timestamp; do not overlay diagnostics
    # from a nearby time as if they were synchronized boxes.
    if not args.skip_images:
        import cv2
        snapshots={round(frame["time_s"],6):frame for frame in frames}
        with open_bag_reader(bag,rosbag2_py) as (reader,_storage):
            reader.set_filter(rosbag2_py.StorageFilter(topics=["/camera/color/image_raw"]))
            image_type=get_message("sensor_msgs/msg/Image")
            written=0
            while reader.has_next():
                topic,data,_record_ns=reader.read_next()
                msg=deserialize_message(data,image_type)
                frame=snapshots.get(round(stamp_s(msg.header.stamp),6))
                if frame is None:
                    continue
                channels=3 if msg.encoding.lower() in ("rgb8","bgr8") else None
                if channels is None:
                    raise ValueError(f"Unsupported RGB encoding {msg.encoding}")
                image=np.frombuffer(msg.data,dtype=np.uint8).reshape(msg.height,msg.step)[:,:msg.width*channels].reshape(msg.height,msg.width,channels).copy()
                if msg.encoding.lower()=="rgb8":
                    image=cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
                stem=f"frame_{written:04d}_{frame['time_s']:.3f}"
                raw_path=args.output/f"{stem}.png"
                cv2.imwrite(str(raw_path),image)
                frame["image_file"]=raw_path.name
                for obj in frame["gt"]:
                    x1,y1,x2,y2=map(round,obj["bbox"])
                    cv2.rectangle(image,(x1,y1),(x2,y2),(255,160,0),2)
                for obj in frame["pred"]:
                    x1,y1,x2,y2=map(round,obj["bbox"])
                    cv2.rectangle(image,(x1,y1),(x2,y2),(0,220,0),1)
                cv2.putText(image,f"t={frame['time_s']:.3f} GT cyan / recorded YOLO green",(8,20),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
                cv2.putText(image,f"eligible={frame['eligible_geometric_subset']} review=PENDING",(8,40),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
                cv2.imwrite(str(args.output/f"{stem}_overlay.jpg"),image)
                written+=1
                if written%10==0:
                    print(f"saved {written}/{len(frames)} independent GT overlays",flush=True)
    report={"schema_version":1,"source_trial":str(args.trial.resolve()),"target_class":args.target_class,
            "extraction_command":[sys.executable,*sys.argv],
            "bag_storage":storage,"read_counts":dict(counts),"camera":camera,"mount":mount_info,"mesh":mesh_info,
            "recorded_detector_confidence_floor":.45,
            "legacy_replay_observation_policy":"Only exactly one recorded observation supplies a measurement; multiple candidates remain recorded, point_world_m=null. No truth/confidence selection. This is not the selected navigation KF replay interface.",
            "observation_reason_counts":dict(Counter(row["observation_reason"] for row in rows)),
            "detection_metric_readiness":"PENDING_VISUAL_REVIEW_AND_LOW_CONFIDENCE_OFFLINE_INFERENCE",
            "detection_subset_protocol":"One sample per second in chronological order, up to max_images; only independent GT full-frame geometry and +/-1s guarded shutter-free images are eligible. Images chosen irrespective of detector success. Projected boxes are amodal; visible-label equivalence must be visually checked. All opportunities and exclusions remain recorded.",
            "pose_interpolation":"bracketed linear translation and normalized shortest-arc quaternion interpolation; no extrapolation; max .10s bracket endpoint distance",
            "observations":rows,"frames":frames,"tracks":tracks,
            "source_hashes":{"metadata.yaml":source_hash(bag/"metadata.yaml"),"model.sdf":source_hash(Path(mesh_info["model_sdf"])),
                             **{str(Path(p).relative_to(ROOT)):source_hash(Path(p)) for p in mesh_info["sources"]}}}
    path=args.output/"recording.json"
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(f"Wrote {path}: {len(rows)} detector frame opportunities, {len(frames)} selected images, {sum(f['eligible_geometric_subset'] for f in frames)} eligible",flush=True)


if __name__=="__main__":
    main()
