"""Low-confidence offline YOLO evaluation against independent mesh labels.

Writes proposed metrics plus contact sheets. Publication is explicitly
pending visual review until --review-file records approved frame timestamps.
Every exclusion and every missed prediction remains in the report.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uav_tracking.research_metrics import detection_metrics


def write_image(cv2,path,image):
    success,encoded=cv2.imencode(path.suffix,image)
    if not success:raise ValueError(f"Could not encode {path}")
    path.write_bytes(encoded.tobytes())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings",nargs="+",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--review-file",type=Path)
    parser.add_argument("--reuse-predictions",action="store_true")
    args=parser.parse_args()
    import cv2
    if not args.reuse_predictions:
        import torch
        from ultralytics import YOLO
    args.output.mkdir(parents=True,exist_ok=True)
    review=json.loads(args.review_file.read_text()) if args.review_file else {}
    aggregate=[];reports=[];models={}
    for recording in args.recordings:
        source=json.loads(recording.read_text())
        name=Path(source["source_trial"]).name
        category=source["target_class"]
        folder=args.output/name;folder.mkdir(exist_ok=True)
        checkpoint=ROOT/"models"/("yolo11n.pt" if category=="person" else "yolo11s.pt")
        if not args.reuse_predictions and category not in models:
            model=YOLO(str(checkpoint))
            model.add_callback("on_predict_start",lambda _predictor:torch.set_num_threads(2))
            models[category]=model
        model=models.get(category)
        cache_path=folder/"low_confidence_predictions.json"
        cached=json.loads(cache_path.read_text()) if args.reuse_predictions and cache_path.exists() else {}
        frames=[];excluded=[];tiles=[];inference_times=[]
        for index,frame in enumerate(source["frames"]):
            key=f'{frame["time_s"]:.6f}'
            image_path=recording.parent/(frame["image_file"] or "missing_image")
            if not image_path.exists():
                excluded.append({"time_s":frame["time_s"],"reason":"selected source RGB image not recorded"})
                continue
            # OpenCV's native Windows path reader cannot open Chinese paths.
            image=cv2.imdecode(np.frombuffer(image_path.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
            if image is None:raise ValueError(f"Could not decode source image {image_path}")
            if key not in cached:
                if args.reuse_predictions:
                    raise ValueError(f"Frozen prediction missing for {name} at {key}; refusing silent re-inference during review")
                start=time.perf_counter()
                output=model.predict(image,imgsz=320 if category=="person" else 480,conf=.001,iou=.7,
                                     classes=[0 if category=="person" else 2],device="cpu",verbose=False)[0]
                inference_times.append(time.perf_counter()-start)
                boxes=output.boxes
                cached[key]=[{"id":str(i),"bbox":box,"class_name":category,"confidence":float(score)}
                             for i,(box,score) in enumerate(zip(boxes.xyxy.cpu().tolist(),boxes.conf.cpu().tolist()))]
            proposed=dict(frame,pred=cached[key])
            approved=key in review.get("approved_frames",{}).get(name,[])
            proposed["review_status"]="APPROVED" if approved else "PENDING"
            if frame["eligible_geometric_subset"]:
                frames.append(proposed)
                for obj in frame["gt"]:
                    x1,y1,x2,y2=map(round,obj["bbox"])
                    cv2.rectangle(image,(x1,y1),(x2,y2),(255,160,0),2)
                for obj in proposed["pred"]:
                    if obj["confidence"]<.45:
                        continue
                    x1,y1,x2,y2=map(round,obj["bbox"])
                    cv2.rectangle(image,(x1,y1),(x2,y2),(0,220,0),1)
                cv2.putText(image,f"{index} t={frame['time_s']:.3f} GT cyan YOLO green",(5,20),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
                overlay_path=folder/f"review_{index:03d}_{key}.jpg"
                write_image(cv2,overlay_path,image)
                gt=frame["gt"][0]["bbox"]
                x1,y1,x2,y2=gt
                pad=max(x2-x1,y2-y1)*.15+5
                x1,y1=max(0,int(x1-pad)),max(0,int(y1-pad))
                x2,y2=min(image.shape[1],int(x2+pad)),min(image.shape[0],int(y2+pad))
                crop=image[y1:y2,x1:x2]
                scale=min(236/crop.shape[1],206/crop.shape[0])
                crop=cv2.resize(crop,None,fx=scale,fy=scale)
                tile=np.full((240,256,3),45,dtype=np.uint8)
                cx,cy=(256-crop.shape[1])//2,28+(206-crop.shape[0])//2
                tile[cy:cy+crop.shape[0],cx:cx+crop.shape[1]]=crop
                cv2.putText(tile,f"#{index} t={frame['time_s']:.3f}",(5,18),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
                tiles.append(tile)
            else:
                excluded.append({"time_s":frame["time_s"],"reason":frame["exclusion_reason"]})
            if index%10==0:
                print(f"{name}: offline YOLO {index+1}/{len(source['frames'])}",flush=True)
        cache_path.write_text(json.dumps(cached,indent=2)+"\n")
        for start in range(0,len(tiles),12):
            page=np.full((3*240,4*256,3),25,dtype=np.uint8)
            for offset,tile in enumerate(tiles[start:start+12]):
                row,column=divmod(offset,4)
                page[row*240:(row+1)*240,column*256:(column+1)*256]=tile
            write_image(cv2,folder/f"contact_sheet_{start//12:02d}.jpg",page)
        approved_frames=[f for f in frames if f["review_status"]=="APPROVED"]
        report={"source_trial":source["source_trial"],"target_class":category,"sampled_opportunities":len(source["frames"]),
                "recording_manifest_sha256":hashlib.sha256(recording.read_bytes()).hexdigest(),
                "prediction_cache_sha256":hashlib.sha256(cache_path.read_bytes()).hexdigest(),
                "geometric_eligible":len(frames),"approved_eligible":len(approved_frames),"excluded":excluded,
                "all_eligible_proposed_metrics":detection_metrics(frames),
                "reviewed_metrics":detection_metrics(approved_frames) if approved_frames else None,
                "publication_status":"REVIEWED_SUBSET_ONLY" if approved_frames else "PENDING_VISUAL_REVIEW",
                "checkpoint":str(checkpoint),"checkpoint_sha256":hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                "inference":{"confidence_floor":.001,"iou_nms":.7,"image_size":320 if category=="person" else 480,"threads":2,
                             "executed_during_this_command":not args.reuse_predictions,
                             "wall_latency_median_s":float(np.median(inference_times)) if inference_times else None},
                "labels":"Independent static mesh projection at exact source image time; only fully in-frame, shutter-guard-free samples; no YOLO output used as GT. Eligible images were selected chronologically from inference opportunities including empty online detector outputs.",
                "frames":frames}
        (folder/"detection_report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        aggregate.extend(approved_frames);reports.append({k:v for k,v in report.items() if k!="frames"})
    result={"schema_version":1,"recordings":reports,"reviewed_aggregate":detection_metrics(aggregate) if aggregate else None,
            "review_file":str(args.review_file) if args.review_file else None,
            "review_file_sha256":hashlib.sha256(args.review_file.read_bytes()).hexdigest() if args.review_file else None,
            "claim_boundary":"Metrics describe a reviewed, fully-visible, static-rendered simulation subset, not real-world/general detector performance. Geometric/occlusion exclusions are listed; no success-only frame selection. Recorded online detections are not reused to create GT."}
    (args.output/"detection_report.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(f"Saved {args.output/'detection_report.json'}",flush=True)


if __name__=="__main__":
    main()
