"""Thin all-actor/dynamic-camera adapter around the frozen detection APIs.

labels produces only raw-image/GT proposals, without detector predictions.
infer is a separately scheduled heavy task. review consumes independent
visible-label decisions, binding them to the unchanged schema2 cache API.
evaluate never infers, and retains every original280 slot in its denominator.
The old STATIC-only report verifier is deliberately not claimed compatible.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import prospective_detection_dataset as dataset

REVIEW_KIND = "INDEPENDENT_ALL_ACTOR_VISIBLE_LABEL_REVIEW_V1"
LABEL_KIND = "PREDICTION_FREE_ALL_ACTOR_LABEL_REVIEW_V1"
REPORT_KIND = "PROSPECTIVE_ALL_ACTOR_DYNAMIC_DETECTION_REPORT_V1"
require, sha, read, pin, canonical, write_new = dataset.require, dataset.sha, dataset.read, dataset.pin, dataset.canonical, dataset.write_new


def prepared(recordings, protocol_pin):
    rows, ids, names = [], set(), set()
    for path in recordings:
        source, protocol, _ = dataset.verify_recording(path, protocol_pin)
        name = Path(source["source_trial"]).name
        require(source["slot_id"] not in ids and name and name not in names, "Duplicate recording original slot/trial name")
        ids.add(source["slot_id"]); names.add(name)
        rows.append((Path(path), source, name, protocol))
    require(bool(rows), "At least one explicit recording required")
    return rows


def fresh_directory(path, protocol):
    path = dataset.assert_external_output(protocol,path)
    require(not path.exists(), "Fresh external output directory required")
    path.mkdir(parents=True)
    return path


def fullframe_tile(image, caption, cv2, np):
    """Keep the whole frame: no first-GT crop and no missing negative frames."""
    tile = np.full((300, 400, 3), 32, dtype=np.uint8)
    scale = min(390/image.shape[1], 260/image.shape[0])
    resized = cv2.resize(image, None, fx=scale, fy=scale)
    x, y = (400-resized.shape[1])//2, 32+(260-resized.shape[0])//2
    tile[y:y+resized.shape[0],x:x+resized.shape[1]] = resized
    cv2.putText(tile, caption, (5,20), cv2.FONT_HERSHEY_SIMPLEX, .42, (255,255,255), 1)
    return tile


def make_labels(rows, output):
    import cv2
    import numpy as np
    output = fresh_directory(output,rows[0][3])
    manifests = []
    for recording, source, name, _protocol in rows:
        folder = output/name; folder.mkdir()
        frames, tiles = [], []
        for frame in source["frames"]:
            key = f'{frame["time_s"]:.6f}'
            row = {"key": key, "source_acquisition_ns": frame["source_acquisition_ns"], "image_status": frame["image_status"],
                   "visible_geometry_eligible": frame["visible_label_eligible"], "all_expected_actor_ids": source["expected_actor_ids"],
                   "source_image": None, "label_overlay": None, "proposal_status": "PENDING_INDEPENDENT_VISIBLE_LABEL_REVIEW"}
            if frame["image_status"] == "PRESENT":
                image_path = recording.parent/frame["image_file"]
                image = cv2.imdecode(np.frombuffer(image_path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
                require(image is not None, "Cannot decode pinned original image")
                camera = frame.get("camera_info")
                if camera is not None:
                    require((image.shape[1],image.shape[0]) == (camera["width"],camera["height"]), "Pinned image shape disagrees with acquisition calibration")
                for obj in frame["gt"]:
                    x1,y1,x2,y2 = map(round,obj["bbox"])
                    cv2.rectangle(image,(x1,y1),(x2,y2),(255,160,0),2)
                    cv2.putText(image,obj["id"],(max(0,x1),max(18,y1)),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,160,0),1)
                cv2.putText(image,f"AMODAL proposals | eligible={frame['visible_label_eligible']} | review=PENDING",(6,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
                cv2.putText(image,f"opportunity={key} actualRGB={frame['source_time_s']:.9f}",(6,38),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
                overlay = folder/("label_"+key+".png")
                success,encoded = cv2.imencode(".png",image); require(success,"Label overlay encode failed")
                with overlay.open("xb") as stream:
                    stream.write(encoded.tobytes())
                row.update(source_image=pin(image_path), label_overlay=pin(overlay))
                tiles.append(fullframe_tile(image,f"{key} GT={len(frame['gt'])} eligible={frame['visible_label_eligible']}",cv2,np))
            else:
                empty = np.full((260,390,3),40,dtype=np.uint8)
                cv2.putText(empty,"MISSING ORIGINAL SOURCE RGB",(8,115),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
                tiles.append(fullframe_tile(empty,f"{key} retained missing opportunity",cv2,np))
            frames.append(row)
        sheets = []
        for start in range(0,len(tiles),12):
            sheet = np.full((3*300,4*400,3),20,dtype=np.uint8)
            for offset,tile in enumerate(tiles[start:start+12]):
                r,c = divmod(offset,4); sheet[r*300:(r+1)*300,c*400:(c+1)*400] = tile
            path = folder/f"all_actor_fullframe_sheet_{start//12:03d}.png"
            success,encoded = cv2.imencode(".png",sheet); require(success,"Contact sheet encode failed")
            with path.open("xb") as stream:
                stream.write(encoded.tobytes())
            sheets.append(pin(path))
        manifest = {"schema_version":1,"kind":LABEL_KIND,"recording":pin(recording),"protocol":source["protocol"],
                    "slot_id":source["slot_id"],"source_trial":source["source_trial"],"contains_predictions":False,
                    "producer_tools":dataset.tool_pins(),"frames":frames,"contact_sheets":sheets}
        write_new(folder/"label_review_manifest.json",manifest)
        manifests.append(pin(folder/"label_review_manifest.json"))
    write_new(output/"label_review_index.json",{"kind":LABEL_KIND,"manifests":manifests,"approval_status":"NONE_GENERATION_IS_NOT_REVIEW"})
    return manifests


def frozen_api(protocol):
    helpers = dataset.load_helpers(protocol["frozen_root"],protocol["helper_source_hashes"])
    return helpers["evaluate_detection_recordings"],helpers["uav_tracking.research_metrics"]


def cache_inputs(recording, source, protocol, args):
    api, metrics = frozen_api(protocol)
    args.settings_source = "recorded"
    configuration, evidence = api.inference_configuration(source,args,root=Path(protocol["frozen_root"]))
    provenance = api.input_provenance(recording,source,configuration,evidence,root=Path(protocol["frozen_root"]))
    return api,metrics,configuration,provenance


def infer(rows, output, args):
    """No flight launch; all PRESENT opportunities including negatives/exclusions."""
    output = fresh_directory(output,rows[0][3])
    reports,models = [],{}
    for recording,source,name,protocol in rows:
        if not any(f["image_status"] == "PRESENT" for f in source["frames"]):
            folder = output/name; folder.mkdir()
            report = {"kind":REPORT_KIND,"recording":pin(recording),"status":"UNOBSERVABLE_NO_PRESENT_IMAGES",
                      "prediction_cache":None,"inference":None,"sampled_opportunities":len(source["frames"]),
                      "present_images_inferred":0,"approval_status":"NO_INFERENCE_OR_METRIC_CLAIM"}
            write_new(folder/"inference_receipt.json",report); reports.append(report); continue
        import cv2
        import numpy as np
        import torch
        from ultralytics import YOLO
        api,_metrics,configuration,provenance = cache_inputs(recording,source,protocol,args)
        folder = output/name; folder.mkdir()
        model_key = (configuration["checkpoint_sha256"],configuration["threads"])
        if model_key not in models:
            model = YOLO(configuration["checkpoint"])
            model.add_callback("on_predict_start",lambda _predictor,n=configuration["threads"]:torch.set_num_threads(n))
            models[model_key] = model
        predictions,latencies = {},[]
        for frame in source["frames"]:
            if frame["image_status"] != "PRESENT":
                continue
            key = f'{frame["time_s"]:.6f}'
            image = cv2.imdecode(np.frombuffer((recording.parent/frame["image_file"]).read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
            require(image is not None,"Could not decode bound original source RGB")
            torch.set_num_threads(configuration["threads"]); start = time.perf_counter()
            result = models[model_key].predict(image,imgsz=configuration["image_size"],conf=configuration["confidence_floor"],
                iou=configuration["iou_nms"],classes=[configuration["class_id"]],device=configuration["device"],verbose=False)[0]
            latencies.append(time.perf_counter()-start)
            predictions[key] = [{"id":str(i),"bbox":box,"class_name":source["target_class"],"confidence":float(score)}
                                for i,(box,score) in enumerate(zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist()))]
        api.validate_predictions(predictions,provenance)
        _a,_m,_c,rechecked = cache_inputs(recording,source,protocol,args)
        require(canonical(rechecked) == canonical(provenance),"Recorded inputs changed during offline inference")
        dataset.verify_recording(recording,source["protocol"])
        cache = folder/"low_confidence_predictions.json"
        write_new(cache,{"schema_version":2,"provenance":provenance,"predictions":predictions})
        report = {"kind":REPORT_KIND,"recording":pin(recording),"prediction_cache":pin(cache),"inference":configuration,
                  "sampled_opportunities":len(source["frames"]),"present_images_inferred":len(predictions),
                  "timing_scope":"OFFLINE inference only; cannot be used as online flight FPS/end-to-end latency",
                  "wall_latency_median_s":float(np.median(latencies)) if latencies else None,
                  "approval_status":"PENDING_INDEPENDENT_LABEL_REVIEW"}
        write_new(folder/"inference_receipt.json",report); reports.append(report)
    write_new(output/"inference_index.json",{"kind":REPORT_KIND,"recordings":reports,"formal_flights_started":0})
    return reports


def validate_label_decisions(decisions, manifest, source, provenance):
    """Approvals bind raw images/all-actor labels; predictions are not review inputs."""
    require(decisions.get("schema_version") == 1 and decisions.get("kind") == REVIEW_KIND
            and decisions.get("independent_from_predictions") is True and decisions.get("reviewer_role") == "INDEPENDENT_VISIBLE_LABEL_REVIEWER"
            and isinstance(decisions.get("reviewer"),str) and bool(decisions["reviewer"].strip()), "Independent visible-label reviewer identity/attestation required")
    require(manifest.get("schema_version") == 1 and manifest.get("kind") == LABEL_KIND and manifest.get("contains_predictions") is False
            and manifest.get("producer_tools") == dataset.tool_pins() and manifest.get("source_trial") == source["source_trial"]
            and manifest.get("protocol") == source["protocol"] and manifest.get("slot_id") == source["slot_id"]
            and manifest.get("recording",{}).get("sha256") == provenance["recording"]["sha256"], "Label review belongs to another input")
    require(decisions.get("label_manifest_sha256") == canonical(manifest), "Decision must bind complete label manifest content")
    for sheet in manifest.get("contact_sheets",[]):
        require(sha(sheet["path"]) == sheet["sha256"],"Label sheet changed")
    by_key = {f'{frame["time_s"]:.6f}':frame for frame in source["frames"]}
    label_rows = {row["key"]:row for row in manifest["frames"]}
    require(len(label_rows) == len(manifest["frames"]) and set(label_rows) == set(by_key),"All opportunities must occur in label review manifest")
    for key,row in label_rows.items():
        require(row.get("source_acquisition_ns") == by_key[key]["source_acquisition_ns"]
                and row.get("image_status") == by_key[key]["image_status"]
                and row.get("all_expected_actor_ids") == source["expected_actor_ids"],"Label review opportunity/source/actor identity differs")
    available = {key for key,frame in by_key.items() if frame["image_status"] == "PRESENT"}
    rows = decisions.get("decisions")
    require(isinstance(rows,list) and len({row.get("key") for row in rows}) == len(rows),"Unique explicit per-image label decisions required")
    approved = []
    for row in rows:
        key = row.get("key")
        require(key in available and row.get("decision") in {"APPROVE_VISIBLE_LABELS", "REJECT", "UNKNOWN"}
                and isinstance(row.get("reason"),str) and bool(row["reason"].strip()), "Invalid or unexplained independent label decision")
        label = label_rows[key]
        image,overlay = label.get("source_image"),label.get("label_overlay")
        require(image and overlay and sha(image["path"]) == image["sha256"] == by_key[key]["image_sha256"]
                and sha(overlay["path"]) == overlay["sha256"], "Independent review image/overlay pin changed")
        require(row.get("source_image_sha256") == image["sha256"] and row.get("label_overlay_sha256") == overlay["sha256"]
                and row.get("all_expected_actor_ids") == source["expected_actor_ids"], "Review must consider the whole image and every actor")
        if row["decision"] == "APPROVE_VISIBLE_LABELS":
            require(by_key[key]["visible_label_eligible"] is True,"Geometry-ineligible/unknown frames cannot become approved visible labels")
            approved.append(key)
    return approved


def build_review(rows, cache_directory, decision_paths, output, args):
    require(len(rows) == len(decision_paths),"One independent decision file per explicit recording required")
    review = {"schema_version":1,"kind":REVIEW_KIND,"approved_frames":{},"cache_provenance_sha256":{},"independent_label_reviews":{}}
    dataset.assert_external_output(rows[0][3],output)
    for (recording,source,name,protocol),decision_path in zip(rows,decision_paths):
        api,_metrics,_configuration,provenance = cache_inputs(recording,source,protocol,args)
        api.load_prediction_cache(Path(cache_directory)/name/"low_confidence_predictions.json",provenance)
        decisions = read(decision_path)
        manifest = dataset.checked(decisions["label_manifest"])
        approved = validate_label_decisions(decisions,manifest,source,provenance)
        review["approved_frames"][name] = approved
        review["cache_provenance_sha256"][name] = canonical(provenance)
        review["independent_label_reviews"][name] = {"decisions":pin(decision_path),"label_manifest":decisions["label_manifest"],
                                                     "reviewer":decisions["reviewer"],"approved_keys":approved}
    write_new(output,review)
    return review


def check_independent_review(review, name, source, provenance):
    entry = review.get("independent_label_reviews",{}).get(name)
    if entry is None:
        return False
    decisions = dataset.checked(entry["decisions"]); manifest = dataset.checked(entry["label_manifest"])
    require(decisions["label_manifest"] == entry["label_manifest"],"Bound label review manifest differs")
    approved = validate_label_decisions(decisions,manifest,source,provenance)
    require(approved == entry["approved_keys"] == review["approved_frames"].get(name),"Review approval set changed")
    return True


def trial_report(recording, source, name, protocol, cache_directory, review, args):
    if not any(f["image_status"] == "PRESENT" for f in source["frames"]):
        return {"kind":REPORT_KIND,"slot_id":source["slot_id"],"source_trial":source["source_trial"],"target_class":source["target_class"],
                "recording":pin(recording),"protocol":source["protocol"],"prediction_cache":None,"input_provenance":None,
                "cache_provenance_sha256":None,"review_binding_status":"UNOBSERVABLE_NO_PRESENT_IMAGES",
                "independent_visible_label_review_valid":False,"sampled_opportunities":len(source["frames"]),"present_images":0,
                "geometric_eligible":0,"approved_eligible":0,"terminal":source["terminal"],"extraction_status":source["extraction_status"],
                "reason_counts":source["coverage"]["reason_counts"],"all_eligible_proposed_metrics":None,"reviewed_metrics":None,
                "publication_status":"UNOBSERVABLE_NO_PRESENT_IMAGES","inference":None,
                "label_review_counts":{"APPROVE_VISIBLE_LABELS":0,"REJECT":0,"UNKNOWN":0,"UNREVIEWED_PRESENT_IMAGES":0},
                "frames":[dict(f,pred=[],review_status="UNOBSERVABLE_NO_PRESENT_IMAGES") for f in source["frames"]]},[]
    api,metrics,configuration,provenance = cache_inputs(recording,source,protocol,args)
    cache_path = Path(cache_directory)/name/"low_confidence_predictions.json"
    predictions = api.load_prediction_cache(cache_path,provenance)
    binding = api.review_binding_status(review,name,provenance)
    independent = check_independent_review(review,name,source,provenance) if binding == "BOUND" else False
    eligible,approved,opportunities = [],[],[]
    approved_keys = set(review.get("approved_frames",{}).get(name,[])) if independent else set()
    review_counts = {"APPROVE_VISIBLE_LABELS":0,"REJECT":0,"UNKNOWN":0,"UNREVIEWED_PRESENT_IMAGES":len(predictions)}
    if independent:
        decisions = dataset.checked(review["independent_label_reviews"][name]["decisions"])["decisions"]
        for item in decisions:
            review_counts[item["decision"]] += 1
        review_counts["UNREVIEWED_PRESENT_IMAGES"] -= len(decisions)
    for frame in source["frames"]:
        key = f'{frame["time_s"]:.6f}'
        proposed = dict(frame,pred=predictions.get(key,[]),review_status="APPROVED" if key in approved_keys else "PENDING")
        opportunities.append(proposed)
        if frame["visible_label_eligible"] and frame["image_status"] == "PRESENT":
            eligible.append(proposed)
            if key in approved_keys:
                approved.append(proposed)
    report = {"kind":REPORT_KIND,"slot_id":source["slot_id"],"source_trial":source["source_trial"],"target_class":source["target_class"],
              "recording":pin(recording),"protocol":source["protocol"],"prediction_cache":pin(cache_path),
              "input_provenance":provenance,"cache_provenance_sha256":canonical(provenance),"review_binding_status":binding,
              "independent_visible_label_review_valid":independent,"sampled_opportunities":len(opportunities),"present_images":len(predictions),
              "geometric_eligible":len(eligible),"approved_eligible":len(approved),"terminal":source["terminal"],
              "extraction_status":source["extraction_status"],"reason_counts":source["coverage"]["reason_counts"],
              "all_eligible_proposed_metrics":metrics.detection_metrics(eligible),
              "reviewed_metrics":metrics.detection_metrics(approved) if approved else None,
              "publication_status":"REVIEWED_SUBSET_ONLY" if approved else "PENDING_INDEPENDENT_VISIBLE_LABEL_REVIEW",
              "inference":configuration,"label_review_counts":review_counts,"frames":opportunities}
    return report,approved


def evaluate(rows, cache_directory, review_file, output, args):
    output = fresh_directory(output,rows[0][3])
    review = read(review_file) if review_file else {}
    reports,aggregate,all_opportunities = [],[],[]
    protocol = rows[0][3]
    for recording,source,name,_protocol in rows:
        report,approved = trial_report(recording,source,name,protocol,cache_directory,review,args)
        write_new(output/(name+"_detection_report.json"),report)
        reports.append({k:v for k,v in report.items() if k != "frames"}); aggregate.extend(approved); all_opportunities.extend(report["frames"])
    _api,metrics = frozen_api(protocol)
    available = {source["slot_id"] for _,source,_,_ in rows}
    missing = [slot["slot_id"] for slot in protocol["slots"] if slot["slot_id"] not in available]
    summary = {"schema_version":1,"kind":REPORT_KIND,"protocol":rows[0][1]["protocol"],"original_planned_slots":280,
               "recording_slots_supplied":len(rows),"missing_original_slot_ids":missing,"all280_recordings_supplied":not missing,
               "recordings":reports,"scheduled_opportunities":len(all_opportunities),"reviewed_aggregate":metrics.detection_metrics(aggregate) if aggregate else None,
               "review_file":pin(review_file) if review_file else None,"producer_tools":dataset.tool_pins(),
               "claim_boundary":"Independent reviewed visible subset of rigid simulation meshes, including source-time dynamic stage3 camera. All original280 slots, failures, missing imagery/geometry, shutter and overlap exclusions remain explicit. Amodal proposals are not observed visible boxes. Offline inference does not establish online latency/FPS or whole-flight detector accuracy. The old report verifier does not validate the new prospective protocol/extraction semantics and this report structure, so an explicit external verifier is used."}
    write_new(output/"detection_report.json",summary)
    return summary


def verify_report(path, protocol_pin, args):
    """Recompute source/cache/review/metrics; no bags or inference are opened."""
    summary = read(path)
    require(summary.get("schema_version") == 1 and summary.get("kind") == REPORT_KIND and summary.get("protocol") == protocol_pin
            and summary.get("producer_tools") == dataset.tool_pins(),"Wrong prospective report/protocol/tool identity")
    rows = prepared([item["recording"]["path"] for item in summary["recordings"]],protocol_pin)
    protocol = rows[0][3]
    review_pin = summary.get("review_file")
    review = dataset.checked(review_pin) if review_pin else {}
    aggregate,total = [],0
    for row,saved in zip(rows,summary["recordings"]):
        recording,source,name,_protocol = row
        require(pin(recording) == saved["recording"],"Summary recording binding changed")
        cache_pin = saved.get("prediction_cache")
        cache_directory = None
        if cache_pin is not None:
            cache_path = Path(cache_pin["path"])
            require(cache_path.name == "low_confidence_predictions.json" and cache_path.parent.name == name,"Unexpected bound cache layout")
            cache_directory = cache_path.parent.parent
        actual,approved = trial_report(recording,source,name,protocol,cache_directory,review,args)
        require({k:v for k,v in actual.items() if k != "frames"} == saved,"Per-slot report/metrics/provenance differ from original sources/cache/review")
        require(read(Path(path).parent/(name+"_detection_report.json")) == actual,"Per-slot full opportunity report changed")
        aggregate.extend(approved); total += len(source["frames"])
    _api,metrics = frozen_api(protocol)
    supplied = {s["slot_id"] for _,s,_,_ in rows}
    missing = [s["slot_id"] for s in protocol["slots"] if s["slot_id"] not in supplied]
    require(summary["original_planned_slots"] == 280 and summary["recording_slots_supplied"] == len(rows)
            and summary["missing_original_slot_ids"] == missing and summary["all280_recordings_supplied"] == (not missing)
            and summary["scheduled_opportunities"] == total
            and summary["reviewed_aggregate"] == (metrics.detection_metrics(aggregate) if aggregate else None),"Original280 denominator/aggregate changed")
    return {"status":"VERIFIED_NEW_PROSPECTIVE_REPORT","report":pin(path),"original_planned_slots":280,
            "recording_slots_supplied":len(rows),"missing_original_slot_count":len(missing),"actual_inference":False,"actual_bag_reads":0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("describe","labels","infer","review","evaluate","verify-report"),nargs="?",default="describe")
    parser.add_argument("recordings",nargs="*",type=Path)
    parser.add_argument("--protocol",type=Path); parser.add_argument("--protocol-sha256")
    parser.add_argument("--output",type=Path); parser.add_argument("--cache-directory",type=Path)
    parser.add_argument("--label-decisions",nargs="*",type=Path); parser.add_argument("--review-file",type=Path)
    parser.add_argument("--report",type=Path)
    for category in ("person","car"):
        parser.add_argument(f"--{category}-model-path",type=Path); parser.add_argument(f"--{category}-image-size",type=int); parser.add_argument(f"--{category}-threads",type=int)
    parser.add_argument("--confidence-floor",type=float,default=.001); parser.add_argument("--iou-nms",type=float,default=.7)
    args = parser.parse_args(argv)
    if args.action == "describe":
        print(json.dumps({"kind":REPORT_KIND,"cache_schema":2,"settings_source":"recorded only","approval":"independent prediction-free visible-label review plus original cache provenance binding","actual_inference":False,"formal_attempts_started":0})); return 0
    require(args.protocol is not None and args.protocol_sha256,"Explicit protocol/SHA required")
    protocol_pin = {"path":str(args.protocol),"sha256":args.protocol_sha256}
    if args.action == "verify-report":
        require(args.report is not None,"Explicit new-kind report required")
        receipt = verify_report(args.report,protocol_pin,args)
        if args.output is not None:
            dataset.assert_external_output(dataset.checked(protocol_pin),args.output)
            write_new(args.output,receipt)
        print(json.dumps(receipt)); return 0
    require(args.output is not None,"Fresh output required")
    rows = prepared(args.recordings,protocol_pin)
    if args.action == "labels":
        make_labels(rows,args.output)
    elif args.action == "infer":
        infer(rows,args.output,args)
    else:
        require(args.cache_directory is not None,"Original bound cache directory required")
        if args.action == "review":
            require(args.label_decisions,"Actual independent visible-label decisions required; generation cannot approve")
            build_review(rows,args.cache_directory,args.label_decisions,args.output,args)
        else:
            evaluate(rows,args.cache_directory,args.review_file,args.output,args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
