"""Low-confidence offline YOLO evaluation against independent mesh labels.

Writes proposed metrics plus contact sheets. Publication is explicitly
pending visual review until --review-file records approved frame timestamps.
Every exclusion and every missed prediction remains in the report.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uav_tracking.research_metrics import detection_metrics


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError("Non-finite JSON: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid)


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-file", type=Path)
    parser.add_argument("--reuse-predictions", action="store_true")
    parser.add_argument("--settings-source", choices=["historical", "recorded", "explicit"], default="historical",
                        help="Historical defaults: person320/car480, two threads. Recorded reads each saved trial configuration.")
    for category in ("person", "car"):
        parser.add_argument(f"--{category}-model-path", type=Path)
        parser.add_argument(f"--{category}-image-size", type=int)
        parser.add_argument(f"--{category}-threads", type=int)
    parser.add_argument("--confidence-floor", type=float, default=.001)
    parser.add_argument("--iou-nms", type=float, default=.7)
    return parser


def inference_configuration(source, args, *, root=ROOT):
    """Resolve offline settings without importing Torch, YOLO, OpenCV or ROS.

    Recorded mode checks effective YAML against non-null CLI run overrides and
    requires the selected weights to match the original flight's model hash.
    A CLI model path may relocate identical bytes; it cannot replace weights.
    """
    category = source.get("target_class")
    if category not in {"person", "car"}:
        raise ValueError("Expected person or car recording")
    class_id = 0 if category == "person" else 2
    model_override = getattr(args, category + "_model_path")
    size_override = getattr(args, category + "_image_size")
    threads_override = getattr(args, category + "_threads")
    evidence = {}
    model_key = None
    expected_model_sha = None
    if args.settings_source == "recorded":
        trial = Path(source["source_trial"])
        paths = {"run_config": trial / "run_config.json",
                 "runtime_parameters": trial / "configuration/runtime_parameters.yaml",
                 "flight_source_hashes": trial / "configuration/source_sha256.json"}
        if any(not path.is_file() for path in paths.values()):
            raise ValueError("Recorded inference settings are incomplete; saved run_config, runtime YAML and model hash manifest are required")
        import yaml
        run = read_json(paths["run_config"])
        runtime = yaml.safe_load(paths["runtime_parameters"].read_text(encoding="utf-8-sig"))
        parameters = runtime["uav_tracking_detection"]["ros__parameters"]
        if (run.get("target_class") != category or parameters.get("class_name") != category
                or type(parameters.get("class_id")) is not int or parameters["class_id"] != class_id):
            raise ValueError("Recorded detector class disagrees with recording")
        for key in ("model_path", "inference_image_size", "inference_threads"):
            if key not in parameters or (run.get(key) is not None and run[key] != parameters[key]):
                raise ValueError("Saved run override and runtime detector parameters disagree: " + key)
        if parameters.get("inference_device", "cpu") != "cpu":
            raise ValueError("This offline evaluator supports recorded CPU settings only")
        model = Path(parameters["model_path"])
        size, threads = parameters["inference_image_size"], parameters["inference_threads"]
        if ((size_override is not None and size_override != size)
                or (threads_override is not None and threads_override != threads)):
            raise ValueError("Recorded image size/threads cannot be changed by CLI; use explicit mode for another offline experiment")
        manifest = read_json(paths["flight_source_hashes"])
        model_name = model.as_posix()
        matches = [key for key in manifest if model_name == key or model_name.endswith("/" + key)]
        if len(matches) != 1:
            raise ValueError("Saved flight model hash is missing or ambiguous")
        model_key = matches[0]
        expected_model_sha = manifest[model_key]
        evidence = {key: {"path": str(path.resolve()), "sha256": file_sha256(path)} for key, path in paths.items()}
        evidence["saved_model"] = {"path": str(model), "manifest_key": model_key, "sha256": expected_model_sha}
        evidence["recorded_online_confidence_threshold"] = parameters.get("confidence_threshold")
    elif args.settings_source == "explicit":
        if model_override is None or size_override is None or threads_override is None:
            raise ValueError("Explicit settings require model path, image size and threads for each supplied category")
        model, size, threads = model_override, size_override, threads_override
    else:
        model = Path(root) / "models" / ("yolo11n.pt" if category == "person" else "yolo11s.pt")
        size, threads = (320 if category == "person" else 480), 2
        model = model_override if model_override is not None else model
        size = size_override if size_override is not None else size
        threads = threads_override if threads_override is not None else threads
    if type(size) is not int or size < 128 or size % 32 or type(threads) is not int or threads < 1:
        raise ValueError("Image size must be a multiple of 32 >=128; threads must be a positive integer")
    if any(type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 1
           for value in (args.confidence_floor, args.iou_nms)):
        raise ValueError("Confidence floor and IoU must be finite and in (0,1]")
    if model_override is not None:
        model = model_override
    if not model.is_absolute():
        model = Path(root) / model
    if not model.is_file() and model_override is None and model_key is not None:
        # Relocated checkout: only the archived model hash can authorize reuse.
        model = Path(root) / model_key
    if not model.is_file():
        raise ValueError("Actual model file is unavailable; refusing YOLO auto-download: " + str(model))
    actual_sha = file_sha256(model)
    if expected_model_sha is not None and actual_sha != expected_model_sha:
        raise ValueError("Actual model SHA256 disagrees with saved flight model hash")
    configuration = {"target_class": category, "class_id": class_id,
                     "checkpoint": str(model.resolve()), "checkpoint_sha256": actual_sha,
                     "image_size": size, "threads": threads, "confidence_floor": float(args.confidence_floor),
                     "iou_nms": float(args.iou_nms), "device": "cpu", "settings_source": args.settings_source}
    return configuration, evidence


def input_provenance(recording, source, configuration, configuration_evidence, *, root=ROOT):
    """Bind all image opportunities, including absent and ineligible inputs."""
    recording = Path(recording)
    images = []
    keys = set()
    for frame in source["frames"]:
        timestamp = frame["time_s"]
        if type(timestamp) not in {int, float} or not math.isfinite(timestamp):
            raise ValueError("Non-finite image timestamp")
        key = f"{timestamp:.6f}"
        if key in keys:
            raise ValueError("Duplicate rounded frame timestamp; prediction keys would alias")
        keys.add(key)
        relative = frame.get("image_file")
        path = recording.parent / relative if isinstance(relative, str) and relative else None
        exists = path is not None and path.is_file()
        images.append({"key": key, "image_file": relative, "status": "PRESENT" if exists else "MISSING",
                       "sha256": file_sha256(path) if exists else None,
                       "bytes": path.stat().st_size if exists else None})
    return {"schema_version": 1,
            "recording": {"path": str(recording.resolve()), "sha256": file_sha256(recording)},
            "source_files": {"scripts/evaluate_detection_recordings.py": file_sha256(Path(root) / "scripts/evaluate_detection_recordings.py"),
                             "uav_tracking/research_metrics.py": file_sha256(Path(root) / "uav_tracking/research_metrics.py")},
            "inference": configuration, "configuration_evidence": configuration_evidence, "input_images": images}


def validate_predictions(predictions, provenance):
    required = {item["key"] for item in provenance["input_images"] if item["status"] == "PRESENT"}
    if not isinstance(predictions, dict) or set(predictions) != required:
        raise ValueError("Prediction cache must cover every present source image, with no foreign rows")
    for rows in predictions.values():
        if not isinstance(rows, list):
            raise ValueError("Prediction rows must be lists, including empty missed detections")
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or row.get("class_name") != provenance["inference"]["target_class"]:
                raise ValueError("Prediction class mismatch")
            if not isinstance(row.get("id"), str) or row["id"] in ids:
                raise ValueError("Invalid or duplicate prediction ID")
            ids.add(row["id"])
            box, score = row.get("bbox"), row.get("confidence")
            if (not isinstance(box, list) or len(box) != 4
                    or any(type(value) not in {int, float} or not math.isfinite(value) for value in box)
                    or box[2] < box[0] or box[3] < box[1]
                    or type(score) not in {int, float} or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError("Invalid cached box/confidence")


def load_prediction_cache(path, provenance):
    cached = read_json(path)
    if (not isinstance(cached, dict) or type(cached.get("schema_version")) is not int or cached["schema_version"] != 2
            or set(cached) != {"schema_version", "provenance", "predictions"}):
        raise ValueError("Legacy/unbound prediction cache cannot be reused; preserve it and use a new output directory for fresh inference")
    if canonical_sha256(cached["provenance"]) != canonical_sha256(provenance):
        raise ValueError("Prediction cache provenance differs from the model, settings, source code, recording or input images")
    validate_predictions(cached["predictions"], provenance)
    return cached["predictions"]


def review_binding_status(review, trial_name, provenance):
    """Old timestamp-only approvals remain pending instead of approving new images."""
    expected = canonical_sha256(provenance)
    actual = review.get("cache_provenance_sha256", {}).get(trial_name)
    if actual == expected:
        approved = review.get("approved_frames", {}).get(trial_name, [])
        available = {item["key"] for item in provenance["input_images"] if item["status"] == "PRESENT"}
        if (not isinstance(approved, list) or any(not isinstance(key, str) for key in approved)
                or len(set(approved)) != len(approved) or not set(approved) <= available):
            raise ValueError("Bound review must list unique present source image keys")
    return "BOUND" if actual == expected else "PENDING_INPUT_BINDING"


def write_image(cv2,path,image):
    success,encoded=cv2.imencode(path.suffix,image)
    if not success:raise ValueError(f"Could not encode {path}")
    path.write_bytes(encoded.tobytes())


def main(argv=None):
    args=build_parser().parse_args(argv)
    prepared=[]
    names=set()
    for recording in args.recordings:
        source=read_json(recording)
        name=Path(source["source_trial"]).name
        if not name or name in names:
            raise ValueError("Duplicate/empty source trial name would alias output caches")
        names.add(name)
        configuration,evidence=inference_configuration(source,args)
        provenance=input_provenance(recording,source,configuration,evidence)
        cache_path=args.output/name/"low_confidence_predictions.json"
        if args.reuse_predictions:
            if not cache_path.is_file():
                raise ValueError("Bound prediction cache is missing; reuse never runs inference")
            cached=load_prediction_cache(cache_path,provenance)
        else:
            if cache_path.exists():
                raise ValueError("Existing prediction cache retained; use --reuse-predictions or a new output directory")
            cached={}
        prepared.append((recording,source,name,configuration,provenance,cached))
    import cv2
    if not args.reuse_predictions:
        import torch
        from ultralytics import YOLO
    args.output.mkdir(parents=True,exist_ok=True)
    review=read_json(args.review_file) if args.review_file else {}
    aggregate=[];reports=[];models={}
    for recording,source,name,configuration,provenance,cached in prepared:
        category=source["target_class"]
        folder=args.output/name;folder.mkdir(exist_ok=True)
        checkpoint=Path(configuration["checkpoint"])
        model_key=(configuration["checkpoint_sha256"],configuration["threads"])
        if not args.reuse_predictions and model_key not in models:
            model=YOLO(str(checkpoint))
            model.add_callback("on_predict_start",lambda _predictor,n=configuration["threads"]:torch.set_num_threads(n))
            models[model_key]=model
        model=models.get(model_key)
        cache_path=folder/"low_confidence_predictions.json"
        review_status=review_binding_status(review,name,provenance)
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
                torch.set_num_threads(configuration["threads"])
                output=model.predict(image,imgsz=configuration["image_size"],conf=configuration["confidence_floor"],iou=configuration["iou_nms"],
                                     classes=[configuration["class_id"]],device=configuration["device"],verbose=False)[0]
                inference_times.append(time.perf_counter()-start)
                boxes=output.boxes
                cached[key]=[{"id":str(i),"bbox":box,"class_name":category,"confidence":float(score)}
                             for i,(box,score) in enumerate(zip(boxes.xyxy.cpu().tolist(),boxes.conf.cpu().tolist()))]
            proposed=dict(frame,pred=cached[key])
            approved=review_status=="BOUND" and key in review.get("approved_frames",{}).get(name,[])
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
        validate_predictions(cached,provenance)
        current_configuration,current_evidence=inference_configuration(source,args)
        current_provenance=input_provenance(recording,source,current_configuration,current_evidence)
        if canonical_sha256(current_provenance)!=canonical_sha256(provenance):
            raise ValueError("Model, source, saved configuration or image inputs changed during evaluation")
        if not args.reuse_predictions:
            cache_path.write_text(json.dumps({"schema_version":2,"provenance":provenance,"predictions":cached},indent=2,allow_nan=False)+"\n",encoding="utf-8")
        for start in range(0,len(tiles),12):
            page=np.full((3*240,4*256,3),25,dtype=np.uint8)
            for offset,tile in enumerate(tiles[start:start+12]):
                row,column=divmod(offset,4)
                page[row*240:(row+1)*240,column*256:(column+1)*256]=tile
            write_image(cv2,folder/f"contact_sheet_{start//12:02d}.jpg",page)
        approved_frames=[f for f in frames if f["review_status"]=="APPROVED"]
        report={"source_trial":source["source_trial"],"target_class":category,"sampled_opportunities":len(source["frames"]),
                "recording_manifest_sha256":provenance["recording"]["sha256"],
                "prediction_cache_sha256":file_sha256(cache_path),
                "prediction_cache_schema_version":2,"input_provenance":provenance,
                "cache_provenance_sha256":canonical_sha256(provenance),
                "review_binding_status":review_status,
                "geometric_eligible":len(frames),"approved_eligible":len(approved_frames),"excluded":excluded,
                "all_eligible_proposed_metrics":detection_metrics(frames),
                "reviewed_metrics":detection_metrics(approved_frames) if approved_frames else None,
                "publication_status":"REVIEWED_SUBSET_ONLY" if approved_frames else "PENDING_VISUAL_REVIEW",
                "checkpoint":str(checkpoint),"checkpoint_sha256":configuration["checkpoint_sha256"],
                "inference":{**configuration,
                             "executed_during_this_command":not args.reuse_predictions,
                             "timing_scope":"Offline low-confidence inference only; not online flight FPS/latency",
                             "wall_latency_median_s":float(np.median(inference_times)) if inference_times else None},
                "labels":"Independent static mesh projection at exact source image time; only fully in-frame, shutter-guard-free samples; no YOLO output used as GT. Eligible images were selected chronologically from inference opportunities including empty online detector outputs.",
                "frames":frames}
        (folder/"detection_report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        aggregate.extend(approved_frames);reports.append({k:v for k,v in report.items() if k!="frames"})
    result={"schema_version":1,"recordings":reports,"reviewed_aggregate":detection_metrics(aggregate) if aggregate else None,
            "review_file":str(args.review_file) if args.review_file else None,
            "review_file_sha256":hashlib.sha256(args.review_file.read_bytes()).hexdigest() if args.review_file else None,
                "claim_boundary":"Metrics describe a reviewed, fully-visible, static-rendered simulation subset, not real-world/general detector performance or formal-flight overall accuracy. Low-confidence offline inference settings are explicit, including historical defaults when selected. Geometric/occlusion exclusions are listed; no success-only frame selection. Recorded online detections are not reused to create GT."}
    (args.output/"detection_report.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(f"Saved {args.output/'detection_report.json'}",flush=True)


if __name__=="__main__":
    main()
