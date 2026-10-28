"""Evaluate real-recorded observations with frozen class anchors and paired faults.

Calibration: first 20% of eligible valid observations in each class's velocity
recording (fully visible geometry, outside guarded shutter intervals).
Evaluation: all later opportunities in that recording plus ALL samples of the
independent position recording. Calibration eligibility never uses YOLO score.
No inference prediction, smoother output, or test-flight residual fits labels.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uav_tracking.research_replay import fit_surface_anchor,benchmark_recording


def residual_summary(rows,anchor,start):
    errors=[];origin_errors=[];views=[]
    for row in rows:
        if row["time_s"]<start or row.get("point_world_m") is None or row.get("truth_position_m") is None:
            continue
        point=np.asarray(row["point_world_m"]);origin=np.asarray(row["truth_position_m"])
        reference=origin+np.asarray(row["truth_rotation"])@anchor
        errors.append(float(np.linalg.norm(point-reference)))
        origin_errors.append(float(np.linalg.norm(point-origin)))
    return {"holdout_observations":len(errors),
            "calibrated_anchor_residual_rmse_m":float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            "calibrated_anchor_residual_p95_m":float(np.percentile(errors,95)) if errors else None,
            "uncalibrated_model_origin_difference_rmse_m":float(np.sqrt(np.mean(np.square(origin_errors)))) if origin_errors else None,
            "reference_validity":"Model-local fixed anchor is an approximation of view-dependent depth surface. Large holdout residual flags limited validity and is never corrected from holdout data."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings",nargs="+",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seeds",type=int,default=10)
    args=parser.parse_args()
    recordings=[json.loads(path.read_text()) for path in args.recordings]
    anchors={}
    for data in recordings:
        name=data["source_trial"]
        category=data["target_class"]
        if "velocity" not in name or category in anchors:
            continue
        rows=data["observations"]
        eligible=[r for r in rows if r.get("calibration_eligible",True) and r.get("point_world_m") is not None and r.get("truth_position_m") is not None]
        count=max(10,int(np.ceil(.2*len(eligible))))
        if len(eligible)<count:
            raise ValueError("Insufficient geometrically eligible calibration observations")
        anchor=fit_surface_anchor(rows,eligible[count-1]["time_s"])
        anchor["calibration_source_trial"]=name
        anchor["calibration_fraction_of_eligible_observations"]=.2
        anchor["calibration_eligibility"]="Independent mesh fully-in-frame geometry and outside +/-1s shutter guard; valid raw depth is necessary to fit an anchor. No score/output-quality threshold or holdout residual influences this selection."
        anchors[category]=anchor
    args.output.mkdir(parents=True,exist_ok=True)
    reports=[];metrics=[]
    for data in recordings:
        name=Path(data["source_trial"]).name
        category=data["target_class"]
        anchor=dict(anchors[category])
        same_source=data["source_trial"]==anchor["calibration_source_trial"]
        anchor["evaluation_split"]="source_temporal_holdout" if same_source else "entire_independent_recording_holdout"
        anchor["frozen_calibration_end_s"]=anchor["calibration_end_s"]
        if not same_source:
            anchor["calibration_end_s"]=data["observations"][0]["time_s"]-1e-3
        report=benchmark_recording(data["observations"],anchor,seeds=range(args.seeds))
        report["source_trial"]=data["source_trial"]
        report["target_class"]=category
        report["holdout_anchor_check"]=residual_summary(data["observations"],np.asarray(anchor["model_local_anchor_m"]),anchor["calibration_end_s"]+1e-6)
        path=args.output/f"{name}_paired_replay.json"
        path.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        reports.append({"source_trial":name,"report":path.name,"holdout_anchor_check":report["holdout_anchor_check"],"groups":report["groups"]})
        metrics.extend({"source_trial":name,"target_class":category,**{k:v for k,v in row.items() if k!="perturbation"}} for row in report["trials"])
        print(f"{name}: {len(report['trials'])} paired results, holdout anchor RMSE={report['holdout_anchor_check']['calibrated_anchor_residual_rmse_m']}",flush=True)
    with (args.output/"paired_replay_metrics.csv").open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(metrics[0]))
        writer.writeheader();writer.writerows(metrics)
    result={"schema_version":1,"scope":"Real recorded observations; conditional offline fault replay, not independently repeated flight results; class anchors trained only in first 20% of geometrically eligible valid observations of velocity recording",
            "anchors":anchors,"recordings":reports,"metric_records":len(metrics),
            "seed_count_per_fault_condition":args.seeds,"recorded_condition_repeats":1,
            "research_claim_boundary":"Calibrated surface-anchor errors are distinct from independently calibrated physical model-center position/velocity accuracy. Confidence intervals condition on the particular source recordings. All fault seeds, losses and unavailable outputs remain in reports."}
    (args.output/"research_report.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(f"Saved {args.output/'research_report.json'}",flush=True)


if __name__=="__main__":
    main()
