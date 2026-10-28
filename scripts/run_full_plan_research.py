"""Frozen 166-flight study and serial offline analysis; no invented repetitions.

Uses the existing 80+20 estimator preregistration and the existing 66-slot
stage-two/three plan. Failed flights are never overwritten/retried. Offline
identity/state analysis runs after flights; summaries join these results back
to the actual seed-level flight records, retaining the flight-phase history.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_stage1_repetitions import trial_specs,aggregate as stage1_statistics,retain_interrupted_rows
from run_stage23_matrix import plan_trials,write_json,summarize as stage23_summary
from uav_tracking.research_metrics import numeric_summary,paired_bootstrap,wilson_interval

VISUAL_SCALARS=("detection_opportunities","center_observed_samples","observed_center_coverage",
                "source_images_with_first_tracking_command")
VISUAL_SUMMARIES=("detected_center_error_px","detected_center_normalized_error",
                  "image_to_first_tracking_command_sim_s")
VISUAL_PAIRED_FIELDS=("follow_visual_observed_center_coverage","follow_visual_detected_center_error_px_rmse",
                      "follow_visual_detected_center_normalized_error_rmse",
                      "follow_visual_image_to_first_tracking_command_sim_s_mean",
                      "follow_visual_image_to_first_tracking_command_sim_s_p95")


def now():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def valid_follow_dynamics_report(report):
    """Old schema-1 transient-only files remain history, not complete reports."""
    if not isinstance(report,dict) or report.get("schema_version")!=1 or report.get("evaluation_status")!="RECORDED_WITH_CENSORED_FAILURES":return False
    visual=report.get("visual_control_metrics")
    return (isinstance(visual,dict) and all(key in visual for key in VISUAL_SCALARS)
            and all(isinstance(visual.get(key),dict) and {"count","mean","rmse","p95"}<=set(visual[key]) for key in VISUAL_SUMMARIES))


@contextmanager
def process_lock(root):
    """One mutating full-plan orchestrator per checkout, across all outputs.

    The file remains after release: deleting a lock pathname can create two
    independently locked inodes. OS locks release automatically on a crash.
    """
    path=root/"results/.full_plan_research.lock";path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a+b") as handle:
        if os.name=="nt":
            import msvcrt
            if handle.seek(0,os.SEEK_END)==0:handle.write(b"0");handle.flush()
            handle.seek(0)
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise RuntimeError("Another full-plan writer is active in this checkout; no manifest was reconciled or changed") from error
        else:
            import fcntl
            try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise RuntimeError("Another full-plan writer is active in this checkout; no manifest was reconciled or changed") from error
        try:
            handle.seek(0);handle.truncate();handle.write(f"pid={os.getpid()} started={now()}\n".encode());handle.flush()
            yield
        finally:
            if os.name=="nt":handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def source_hashes(root):
    paths=[]
    runtime_suffixes={".py",".sh",".yaml",".yml",".sdf",".msg",".xml",".config",".cfg",".txt",".toml",
                      ".obj",".dae",".mtl",".stl",".mesh",".material",".png",".jpg",".jpeg",".bmp",".tif",".tiff",".urdf",".pt"}
    for folder in ("scripts","uav_tracking","ros2_ws/src","config","launch","models"):
        for path in (root/folder).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in runtime_suffixes:continue
            if any(part in {"build","install","log","__pycache__",".git"} or part.endswith(".egg-info") for part in path.relative_to(root).parts):continue
            paths.append(path)
    paths.extend(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {".py",".toml",".cfg",".xml",".txt"})
    return {path.relative_to(root).as_posix():sha(path) for path in sorted(set(paths))}


def make_plan(root,prefix,output,wall_timeout=300.):
    prereg_path=root/"planning/online_estimator_preregistration.json"
    prereg=load(prereg_path);resources=prereg["resource_configuration"]
    matrices=[];trials=[]
    for key,suffix in (("primary_matrix","online_estimators"),("position_compatibility_matrix","position_compatibility")):
        source=prereg[key];subprefix=f"{prefix}_{suffix}"
        specs=trial_specs(subprefix,source["seeds"],source["classes"],source["control_modes"],source["condition"],source["estimator_methods"])
        if len(specs)!=source["expected_trials"]:raise ValueError("Preregistered stage-one denominator mismatch")
        for row in specs:
            setting=resources[row["target_class"]]
            row.update(stage=1,scenario="unique_instance",motion_profile_kind=source["motion_profile_kind"],
                       real_time_factor=resources["real_time_factor"],inference_image_size=setting["inference_image_size"],
                       inference_threads=setting["inference_threads"],scope="repeated_research",matrix=key)
        matrices.append({"kind":"stage1","key":key,"prefix":subprefix,
                         "report":str(root/"results"/f"{subprefix}_repetition_report.json"),"trial_names":[s["name"] for s in specs]})
        trials.extend(specs)
    subprefix=f"{prefix}_stage23"
    specs=plan_trials(subprefix,prereg["primary_matrix"]["seeds"],real_time_factor=resources["real_time_factor"],
                      car_image_size=resources["car"]["inference_image_size"],car_threads=resources["car"]["inference_threads"])
    if len(specs)!=66:raise ValueError("Expected existing 66-slot stage-two/three protocol, not an expanded study")
    for row in specs:row["matrix"]="stage23"
    matrices.append({"kind":"stage23","key":"stage23","prefix":subprefix,"output":str(output/"stage23_matrix"),
                     "report":str(output/"stage23_matrix/manifest.json"),"trial_names":[s["name"] for s in specs]})
    trials.extend(specs)
    if len(trials)!=166:raise ValueError("The primary denominator must be exactly 166")
    return {"schema_version":1,"prefix":prefix,"frozen_root":str(root),"created_utc":now(),
            "preregistration_sha256":sha(prereg_path),"source_hashes":source_hashes(root),
            "resources":resources,"wall_timeout_s":wall_timeout,"matrices":matrices,"trials":trials,
            "protocol":"Existing 80 velocity estimator interventions +20 adaptive position compatibility +66 stage2/3 slots. One simulator at a time. All offline physical/state analysis after flight phase. No automatic retries or overwrite. Optional engineering motion/fault extensions remain outside this primary 166 denominator."}


def plan_digest(plan):
    return hashlib.sha256(json.dumps({key:value for key,value in plan.items() if key not in {"created_utc","plan_sha256"}},sort_keys=True,separators=(",",":")).encode()).hexdigest()


def validate_plan(plan):
    if plan.get("plan_sha256")!=plan_digest(plan):
        raise ValueError("Stored plan content does not match its declared digest; preserve this evidence and investigate")
    names=[trial["name"] for trial in plan["trials"]]
    if len(names)!=166 or len(set(names))!=166:
        raise ValueError("Stored full-plan trial set must contain exactly 166 distinct names")


def validate_offline_manifest(manifest,plan):
    if manifest.get("schema_version")!=1 or manifest.get("plan_sha256")!=plan["plan_sha256"]:
        raise ValueError("Offline manifest does not belong to this frozen plan")
    expected={trial["name"] for trial in plan["trials"]}
    rows=manifest.get("trials")
    if not isinstance(rows,dict) or set(rows)-expected or any(row.get("name")!=name for name,row in rows.items()):
        raise ValueError("Offline manifest contains unknown or inconsistent trial names")


def flight_records(plan):
    result={}
    for matrix in plan["matrices"]:
        data=load(Path(matrix["report"])) or {}
        if matrix["kind"]=="stage1":
            for row in data.get("trials",[]):result[row["name"]]={"status":row["result"],"row":row}
        else:
            for slot in data.get("slots",[]):result[slot["trial"]["name"]]={"status":slot["status"],"row":slot}
    return result


def matrix_command(matrix,plan,root,remaining):
    r=plan["resources"]
    if matrix["kind"]=="stage1":
        names=set(matrix["trial_names"]);specs=[s for s in plan["trials"] if s["name"] in names]
        conditions={s["condition"] for s in specs};motion_profiles={s["motion_profile_kind"] for s in specs}
        if len(conditions)!=1 or len(motion_profiles)!=1:raise ValueError("A child stage-one matrix must have one frozen condition and motion profile")
        command=[sys.executable,str(root/"scripts/run_stage1_repetitions.py"),"--prefix",matrix["prefix"],
                 "--seeds",*map(str,dict.fromkeys(s["seed"] for s in specs)),
                 "--classes",*dict.fromkeys(s["target_class"] for s in specs),
                 "--modes",*sorted({s["command_mode"] for s in specs}),"--estimators",*dict.fromkeys(s["estimator_method"] for s in specs),
                 "--condition",next(iter(conditions)),"--motion-profile-kind",next(iter(motion_profiles)),"--real-time-factor",str(r["real_time_factor"]),
                 "--car-image-size",str(r["car"]["inference_image_size"]),"--car-threads",str(r["car"]["inference_threads"]),
                 "--person-image-size",str(r["person"]["inference_image_size"]),"--person-threads",str(r["person"]["inference_threads"]),
                 "--wall-timeout",str(plan["wall_timeout_s"]),"--skip-online-state-evaluation"]
        if Path(matrix["report"]).exists():command.append("--resume")
    else:
        command=[sys.executable,str(root/"scripts/run_stage23_matrix.py"),"--prefix",matrix["prefix"],"--output",matrix["output"],
                 "--seeds",*map(str,dict.fromkeys(s["seed"] for s in plan["trials"] if s["matrix"]=="stage23")),
                 "--real-time-factor",str(r["real_time_factor"]),"--car-image-size",str(r["car"]["inference_image_size"]),
                 "--car-threads",str(r["car"]["inference_threads"]),"--wall-timeout",str(plan["wall_timeout_s"])]
        if Path(matrix["report"]).exists():command.append("--resume")
    if remaining:command.extend(["--stop-after",str(remaining)])
    return command


def run_logged(command,log,root):
    log.parent.mkdir(parents=True,exist_ok=True)
    print("Starting: "+" ".join(command),flush=True)
    with log.open("x",encoding="utf-8") as handle:
        process=subprocess.run(command,cwd=root,stdout=handle,stderr=subprocess.STDOUT,check=False)
    return {"argv":command,"returncode":process.returncode,"log":str(log),"finished_utc":now()}


def execute_flights(plan,output,root,stop_after):
    attempted=0
    for matrix in plan["matrices"]:
        # The child normally repairs old RUNNING slots when it executes.
        # A crash on its final slot leaves no PENDING slot, so reconcile that
        # bookkeeping here without launching or retrying any trial.
        if matrix["kind"]=="stage1":
            child=load(Path(matrix["report"]))
            if child:
                names=[row["name"] for row in child.get("trials",[])]
                if len(names)!=len(set(names)) or set(names)-set(matrix["trial_names"]):raise ValueError("Child stage1 report contains foreign or duplicate trial names")
                if retain_interrupted_rows(child["trials"]):write_json(Path(matrix["report"]),stage1_statistics(child["trials"],len(matrix["trial_names"])))
        else:
            child=load(Path(matrix["report"]))
            if child:
                expected=set(matrix["trial_names"])
                names=[slot["trial"]["name"] for slot in child.get("slots",[])]
                if len(names)!=len(set(names)) or set(names)!=expected:raise ValueError("Child stage23 manifest trial set differs from frozen parent")
                changed=False
                for slot in child["slots"]:
                    if slot["status"] in {"RUNNING_FLIGHT","RUNNING_EVALUATION"}:
                        slot.update(status="INTERRUPTED",error="Previous matrix process ended before this slot completed; parent bookkeeping resume, no retry",finished_utc=now())
                        changed=True
                if changed:
                    child["updated_utc"]=now();write_json(Path(matrix["report"]),child)
                    write_json(Path(matrix["output"])/"summary.json",stage23_summary(child))
        before=flight_records(plan)
        pending=[name for name in matrix["trial_names"] if before.get(name,{}).get("status","PENDING")=="PENDING"]
        if not pending:continue
        if stop_after and attempted>=stop_after:break
        remaining=max(0,stop_after-attempted) if stop_after else 0
        command=matrix_command(matrix,plan,root,remaining)
        log=output/"logs"/f"{matrix['key']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.log"
        record=run_logged(command,log,root)
        history=load(output/"flight_commands.json") or [];history.append(record);write_json(output/"flight_commands.json",history)
        after=flight_records(plan)
        added=sum(after.get(name,{}).get("status","PENDING")!="PENDING" and before.get(name,{}).get("status","PENDING")=="PENDING" for name in matrix["trial_names"])
        attempted+=added
        stopped=[name for name in matrix["trial_names"] if before.get(name,{}).get("status","PENDING")=="PENDING"
                 and after.get(name,{}).get("row",{}).get("infrastructure_failure",{}).get("stop") is True]
        if stopped:
            path=output/"infrastructure_stops.json";history=load(path) or []
            history.append({"time_utc":now(),"matrix":matrix["key"],"trial_names":stopped,
                            "evidence":{name:after[name]["row"]["infrastructure_failure"] for name in stopped},
                            "action":"Stop current invocation before any later matrix; failures retained, pending slots may resume after environment repair without retrying failed names"})
            write_json(path,history)
            print("Infrastructure stop: "+", ".join(stopped)+"; all remaining matrices deferred",flush=True)
            break
        if not added and record["returncode"]!=0:raise RuntimeError("Child matrix failed before recording a new trial; inspect its log, do not silently skip planned slots")
    return attempted


def execute_offline(plan,output,root,allow_partial=False):
    flights=flight_records(plan)
    unfinished=[t["name"] for t in plan["trials"] if flights.get(t["name"],{}).get("status","PENDING") in {"PENDING","RUNNING_FLIGHT","RUNNING_EVALUATION"}]
    if unfinished and not allow_partial:raise ValueError("Offline phase requires finished flight slots; use explicit --allow-partial-offline only in a simulator-free analysis window")
    if any(row["status"] in {"RUNNING_FLIGHT","RUNNING_EVALUATION"} for row in flights.values()):raise ValueError("Refusing offline CPU work while a child manifest reports an active flight/evaluator")
    path=output/"offline_manifest.json";manifest=load(path) or {"schema_version":1,"plan_sha256":plan["plan_sha256"],"trials":{}}
    validate_offline_manifest(manifest,plan)
    for row in manifest["trials"].values():
        if row.get("status")=="RUNNING_ANALYSIS":row.update(status="INTERRUPTED",reason="Previous analysis process ended before completing this slot; retained without silent retry")
    # Persist bookkeeping even when the interrupted slot was the last one
    # and the loop below has no new analysis to execute.
    write_json(path,manifest)
    for trial in plan["trials"]:
        name=trial["name"]
        if name in manifest["trials"] or flights.get(name,{}).get("status","PENDING")=="PENDING":continue
        directory=root/"results"/name
        row={"name":name,"flight_status":flights[name]["status"],"status":"RUNNING_ANALYSIS","commands":[],"started_utc":now()}
        manifest["trials"][name]=row;write_json(path,manifest)
        if not (directory/"rosbag/metadata.yaml").exists():
            row.update(status="INCOMPLETE_EVIDENCE",reason="No readable recorded bag; failed flight retained")
            write_json(path,manifest);continue
        commands=[]
        physical=directory/"physical_identity.json"
        if trial["stage"]==2 and trial.get("scenario")!="auto_unique":
            commands.append(("physical_identity",[sys.executable,str(root/"scripts/evaluate_physical_identity.py"),str(directory),"--target-class",trial["target_class"],"--output",str(physical)],physical))
        if trial.get("scenario")=="auto_unique":
            row.update(status="NOT_APPLICABLE_NO_SELECTED_TASK",reason="Unique-instance ambiguity test intentionally has no selected physical target; flight safety remains evaluated separately")
            write_json(path,manifest);continue
        online=directory/"online_state_accuracy_v2.json"
        command=[sys.executable,str(root/"scripts/evaluate_online_state_accuracy.py"),str(directory),"--target-class",trial["target_class"],"--output",str(online),
                 "--vehicle-model","x500_stage3" if trial["stage"]==3 else "x500_stage1"]
        if trial["stage"]==2:command.extend(["--physical-identity-report",str(physical)])
        commands.append(("online_state_accuracy",command,online))
        dynamics=directory/"follow_dynamics.json"
        dynamics_command=[sys.executable,str(root/"scripts/evaluate_follow_dynamics.py"),str(directory),
                          "--target-class",trial["target_class"],"--output",str(dynamics)]
        if trial["stage"]==2:dynamics_command.extend(["--physical-identity-report",str(physical)])
        commands.append(("follow_dynamics",dynamics_command,dynamics))
        for kind,command,report in commands:
            if report.exists():
                try:prior=load(report)
                except (ValueError,OSError):prior={}
                if kind=="online_state_accuracy":valid=prior.get("schema_version")==2 and "online_state_accuracy" in prior
                elif kind=="follow_dynamics":valid=valid_follow_dynamics_report(prior)
                else:valid=prior.get("evaluation_status")=="RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS" and "tasks" in prior
                record={"kind":kind,"report":str(report),"status":"PREEXISTING_RECORDED_REPORT" if valid else "INCOMPLETE_EVIDENCE","report_sha256":sha(report)}
            else:
                record={"kind":kind,"report":str(report),**run_logged(command,output/"logs"/f"{name}_{kind}.log",root)}
                record["status"]="RECORDED" if record["returncode"]==0 and report.exists() else "INCOMPLETE_EVIDENCE"
                if kind=="follow_dynamics" and record["status"]=="RECORDED":
                    try:valid=valid_follow_dynamics_report(load(report))
                    except (ValueError,OSError):valid=False
                    if not valid:record["status"]="INCOMPLETE_EVIDENCE"
                if report.exists():record["report_sha256"]=sha(report)
            row["commands"].append(record);write_json(path,manifest)
        row["status"]="RECORDED" if all(c["status"] in {"RECORDED","PREEXISTING_RECORDED_REPORT"} for c in row["commands"]) else "INCOMPLETE_EVIDENCE"
        row["finished_utc"]=now();write_json(path,manifest)
    return manifest


def mean_ci(values):
    result=numeric_summary(values)
    if result["valid_count"]>=2:
        result["mean_bootstrap95"]=paired_bootstrap(values,[0.]*len(values))
        result["mean_bootstrap95"]["method"]="Single-sample percentile bootstrap of whole flight/seed units; no algorithm comparator"
    else:result["mean_bootstrap95"]=None
    return result


def pair_outcomes(rows,left,right,field):
    methods={method:{r["seed"]:r for r in rows if r["gimbal_mode"]==method} for method in (left,right)}
    seeds=sorted(set(methods[left])|set(methods[right]))
    a=[methods[left].get(seed) for seed in seeds];b=[methods[right].get(seed) for seed in seeds]
    return {"seed_units":seeds,
            "all_measurable_recorded_pairs":paired_bootstrap([r.get(field) if r else None for r in a],[r.get(field) if r else None for r in b]),
            "conditional_both_flight_pass":paired_bootstrap([r.get(field) if r and s and r["result"]==s["result"]=="PASS" else None for r,s in zip(a,b)],
                                                           [s.get(field) if r and s and r["result"]==s["result"]=="PASS" else None for r,s in zip(a,b)])}


def dynamics_trial_fields(report):
    """One row per real flight; task windows are never independent repeats."""
    result={"follow_dynamics_status":report.get("evaluation_status")}
    visual=report.get("visual_control_metrics")
    result["follow_visual_report_available"]=valid_follow_dynamics_report(report)
    if result["follow_visual_report_available"]:
        result.update({"follow_visual_"+key:visual.get(key) for key in VISUAL_SCALARS})
        for metric in VISUAL_SUMMARIES:
            source=visual.get(metric) or {}
            for statistic in ("count","mean","rmse","p95"):
                result[f"follow_visual_{metric}_{statistic}"]=source.get(statistic)
    windows=report.get("windows",[])
    initial=next((w for w in windows if w.get("kind")=="initial_follow_before_first_shutter"),{})
    for axis in ("distance","height"):
        source=initial.get(axis) or {}
        for field in ("opposite_side_overshoot_m","settling_time_s","settling_right_censored","truth_coverage","observed_interval_s"):
            result[f"initial_{axis}_{field}"]=source.get(field)
        flag=source.get("settling_right_censored")
        result[f"initial_{axis}_unsettled_indicator"]=float(flag) if type(flag) is bool else None
    selections=[w for w in windows if w.get("kind")=="explicit_selection"]
    latencies=[w.get("first_measured_confirmation_after_request_s") for w in selections]
    finite_latencies=[value for value in latencies if value is not None and math.isfinite(value)]
    result.update(explicit_selection_windows=len(selections),explicit_selection_confirmed=len(finite_latencies),
                  explicit_selection_confirmation_censored=sum(w.get("confirmation_censored") is True for w in selections),
                  explicit_selection_mean_confirmation_latency_s=float(np.mean(finite_latencies)) if finite_latencies else None)
    return result


def dynamics_statistics(rows):
    groups=defaultdict(list)
    for row in rows:
        if row["result"]=="PENDING":continue
        label=(row.get("estimator_method") if row["stage"]==1 else row.get("gimbal_mode") if row["stage"]==3 else row.get("scenario")) or "unspecified"
        key=f"s{row['stage']}_{row['target_class']}_{row.get('command_mode','velocity')}_{label}"
        groups[key].append(row)
    result={}
    for key,group in groups.items():
        data={"flight_units":len(group),"dynamics_recorded":sum(r.get("follow_dynamics_status")=="RECORDED_WITH_CENSORED_FAILURES" for r in group),
              "flight_failure_rate":wilson_interval(sum(r["result"]!="PASS" for r in group),len(group))}
        for axis in ("distance","height"):
            flags=[r.get(f"initial_{axis}_settling_right_censored") for r in group]
            data[f"initial_{axis}_settling"]={"right_censored":sum(flag is True for flag in flags),"observed_settled":sum(flag is False for flag in flags),
                                                    "missing_window":sum(type(flag) is not bool for flag in flags),
                                                    "observed_settling_time_s":numeric_summary(r.get(f"initial_{axis}_settling_time_s") for r in group)}
            for field in ("opposite_side_overshoot_m","truth_coverage"):
                data[f"initial_{axis}_{field}"]=numeric_summary(r.get(f"initial_{axis}_{field}") for r in group)
        data["explicit_selection_windows"]=sum(r.get("explicit_selection_windows",0) for r in group)
        data["explicit_selection_confirmation_censored"]=sum(r.get("explicit_selection_confirmation_censored",0) for r in group)
        data["flight_mean_observed_confirmation_latency_s"]=numeric_summary(r.get("explicit_selection_mean_confirmation_latency_s") for r in group)
        opportunities=sum(r.get("follow_visual_detection_opportunities") or 0 for r in group)
        observed=sum(r.get("follow_visual_center_observed_samples") or 0 for r in group)
        data["visual_control_statistics"]={
            "reports_available":sum(r.get("follow_visual_report_available") is True for r in group),
            "reports_missing":sum(r.get("follow_visual_report_available") is not True for r in group),
            "detection_opportunities_total":opportunities,"center_observed_samples_total":observed,
            "pooled_observed_center_coverage":observed/opportunities if opportunities else None,
            "source_images_with_first_tracking_command_total":sum(r.get("follow_visual_source_images_with_first_tracking_command") or 0 for r in group),
            "whole_flight_statistics":{field:numeric_summary(r.get(field) for r in group) for field in VISUAL_PAIRED_FIELDS}}
        data["claim_boundary"]="Whole flights/seeds are units; task windows and observed images are not independent repetitions. Settling-time summaries condition on observed settling and must be read with right-censored/missing counts. Null is never zero. Moving-target task transient, not stationary reference step response. Visual error conditions on observed detector boxes; per-flight coverage and opportunity-weighted pooled coverage stay explicit. Image-to-first-tracking-command latency uses simulation time and ends before PX4/actuator response; it is not wall-time latency."
        result[key]=data
    return result


def consolidated_summary(plan,output,root):
    flights=flight_records(plan);rows=[];crossings=defaultdict(list);gimbals=defaultdict(list)
    for trial in plan["trials"]:
        source=flights.get(trial["name"],{"status":"PENDING","row":{}})
        row={**trial,"result":source["status"],"flight_phase_evidence":source["row"]}
        directory=root/"results"/trial["name"]
        dynamics=load(directory/"follow_dynamics.json")
        if dynamics:row.update(dynamics_trial_fields(dynamics))
        online=load(directory/"online_state_accuracy_v2.json")
        if online and online.get("schema_version")==2:
            state=online["online_state_accuracy"];metrics=state["metrics"]
            row.update(online_state_anchor_position_rmse_m=metrics["state_stamp_position_error_m"]["rmse"],
                       online_state_coverage=state["active_coverage"],online_state_reference_coverage=state.get("position_reference_coverage"),
                       command_jitter_rms_mps2=online["control_jitter"]["velocity_command_delta_over_dt_mps2"]["rmse"],
                       online_state_report=str(directory/"online_state_accuracy_v2.json"))
        if trial["stage"]==1:
            row.update({key:source["row"].get(key) for key in ("horizontal_rmse_m","height_rmse_m")})
        if trial["stage"]==2:
            physical=load(directory/"physical_identity.json")
            if physical:
                row["physical_identity_status"]=physical.get("evaluation_status")
                row["selected_physical_identity_all"]=physical.get("selected_physical_identity_all")
                row["all_detection_opportunities"]=physical.get("opportunities")
                row["geometric_unoccluded_opportunities"]=physical.get("geometric_unoccluded_opportunities")
                tasks=list(physical.get("tasks",{}).values())
                for subset,label in (("amodal_simulation_mot","amodal"),("unoccluded_geometry_mot","unoccluded_geometry")):
                    for metric in ("hota","idf1","id_switches"):
                        numbers=[task[subset][metric] for task in tasks if task.get(subset,{}).get(metric) is not None]
                        row[f"mean_task_{label}_{metric}"]=float(np.mean(numbers)) if numbers else None
                row["task_count"]=len(tasks)
            if trial.get("scenario")=="crossing":crossings[trial["target_class"]].append(row)
        if trial["stage"]==3:
            report=load(directory/"gimbal_evaluation.json")
            for key in ("detected_center_normalized_error","true_image_horizon_error_rad"):
                row[key+"_rmse"]=report.get("metrics",{}).get(key,{}).get("rmse") if report else None
                row[key+"_observed_samples"]=report.get("metrics",{}).get(key,{}).get("count") if report else None
            gimbals[trial["target_class"]].append(row)
        rows.append(row)
    crossing_summary={}
    for category,group in crossings.items():
        attempted=[r for r in group if r["result"]!="PENDING"]
        counts=Counter()
        for row in attempted:counts.update((row.get("selected_physical_identity_all") or {}).get("counts",{}))
        total=sum(counts.values());known=counts["CORRECT"]+counts["WRONG_PHYSICAL_ACTOR"]
        crossing_summary[category]={"planned_seeds":[r["seed"] for r in group],"recorded_trials":len(attempted),
            "failure_rate":wilson_interval(sum(r["result"]!="PASS" for r in attempted),len(attempted)),
            "all_detection_opportunities":sum(r.get("all_detection_opportunities") or 0 for r in attempted),
            "all_task_opportunities":total,"selected_physical_counts":dict(counts),
            "correct_fraction_all_task_opportunities":counts["CORRECT"]/total if total else None,
            "known_match_correct_fraction":counts["CORRECT"]/known if known else None,
            "physical_reports_missing_or_incomplete":sum(not (r.get("selected_physical_identity_all") or {}).get("frames") for r in attempted),
            "trial_statistics":{key:mean_ci([r.get(key) for r in attempted]) for key in
                                ("mean_task_amodal_hota","mean_task_amodal_idf1","mean_task_amodal_id_switches",
                                 "mean_task_unoccluded_geometry_hota","mean_task_unoccluded_geometry_idf1","mean_task_unoccluded_geometry_id_switches")},
            "per_seed":[{key:value for key,value in r.items() if key!="flight_phase_evidence"} for r in group],
            "claim_boundary":"One crossing algorithm configuration per seed in the existing 66-slot plan: report seed-level metrics and intervals, not an invented paired algorithm comparison. HOTA/IDF1 are task means within each flight, then flight-level statistics; unknown physical intervals remain in all-task denominator. Geometry-MOT labels still require separate visual validation for visible-object claims."}
    gimbal_summary={category:{"active_minus_midpoint":{field:pair_outcomes(group,"active","midpoint",field) for field in
        ("detected_center_normalized_error_rmse","true_image_horizon_error_rad_rmse","online_state_anchor_position_rmse_m","online_state_coverage",*VISUAL_PAIRED_FIELDS)},
        "per_seed":[{key:value for key,value in r.items() if key!="flight_phase_evidence"} for r in group],
        "claim_boundary":"Real paired seed units, active minus midpoint. Detected-center error conditions on observed detections; its sample counts and all-opportunity state coverage remain alongside it. Failures/missing pairs are explicit."} for category,group in gimbals.items()}
    attempted=[r for r in rows if r["result"]!="PENDING"]
    stage1=[r for r in rows if r["stage"]==1 and r["result"]!="PENDING"]
    offline=load(output/"offline_manifest.json") or {}
    if offline:validate_offline_manifest(offline,plan)
    result={"schema_version":1,"plan_sha256":plan["plan_sha256"],"updated_utc":now(),"planned_flights":166,
            "status_counts":dict(Counter(r["result"] for r in rows)),"recorded_or_attempted_flights":len(attempted),
            "all_flights_attempted":len(attempted)==166,"all_flights_pass":len(attempted)==166 and all(r["result"]=="PASS" for r in attempted),
            "all_flight_slots_terminal":len(attempted)==166 and all(r["result"] in {"PASS","FAIL","INCOMPLETE","INTERRUPTED"} for r in attempted),
            "offline_status_counts":dict(Counter(r.get("status","INTERRUPTED") for r in offline.get("trials",{}).values())),
            "all_offline_slots_attempted":len(offline.get("trials",{}))==166 and all(r.get("status")!="RUNNING_ANALYSIS" for r in offline.get("trials",{}).values()),
            "stage1_joined_statistics":stage1_statistics(stage1,100),"stage2_crossing_statistics":crossing_summary,
            "stage3_paired_statistics":gimbal_summary,"follow_dynamics_statistics":dynamics_statistics(rows),"trials":rows,
            "claim_boundary":"Complete execution means all planned evidence is attempted and failures retained, not that all safety/quality claims passed. Offline results are joined here while original flight-phase EXPLICITLY_SKIPPED online statuses remain unchanged as history. No ReID, runtime GT, wall-time real-time or independent model-center claim."}
    write_json(output/"summary.json",result);return result


def execute_requested_phase(args,parser):
    plan_path=args.output/"plan.json";existing=load(plan_path)
    if existing:validate_plan(existing)
    if existing and args.phase=="summarize":plan=existing
    else:
        candidate=make_plan(ROOT,args.prefix,args.output,args.wall_timeout);candidate["plan_sha256"]=plan_digest(candidate)
        if existing:
            if not args.resume:parser.error("Frozen plan already exists; use --resume; no trial outputs will be overwritten")
            if existing["plan_sha256"]!=candidate["plan_sha256"]:parser.error("Source/protocol/resources differ from frozen plan; preserve it and use a new root/prefix/output")
            plan=existing
        else:
            plan=candidate;write_json(plan_path,plan)
    if args.phase in ("flights","all"):execute_flights(plan,args.output,ROOT,args.stop_after)
    if args.phase=="offline":execute_offline(plan,args.output,ROOT,args.allow_partial_offline)
    elif args.phase=="all":
        current=flight_records(plan)
        pending=any(current.get(t["name"],{}).get("status","PENDING")=="PENDING" for t in plan["trials"])
        if not pending or args.allow_partial_offline:execute_offline(plan,args.output,ROOT,args.allow_partial_offline)
        else:print("Offline analysis deferred until all planned flights are attempted; checkpoint preserved.",flush=True)
    result=consolidated_summary(plan,args.output,ROOT)
    print(json.dumps({key:result[key] for key in ("planned_flights","recorded_or_attempted_flights","status_counts","all_flights_attempted","all_flights_pass","offline_status_counts")},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("plan","flights","offline","summarize","all"),default="plan")
    parser.add_argument("--output",type=Path,default=ROOT/"results/full_plan_research_v2")
    parser.add_argument("--prefix",default="fullplan_v2")
    parser.add_argument("--wall-timeout",type=float,default=300.)
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--stop-after",type=int,default=0,help="Maximum new flights; zero attempts all remaining existing slots")
    parser.add_argument("--allow-partial-offline",action="store_true")
    args=parser.parse_args()
    if args.stop_after<0 or not math.isfinite(args.wall_timeout) or args.wall_timeout<=0:parser.error("Invalid stop-after/wall-timeout")
    if args.phase=="summarize":execute_requested_phase(args,parser)
    else:
        with process_lock(ROOT):execute_requested_phase(args,parser)


if __name__=="__main__":main()
