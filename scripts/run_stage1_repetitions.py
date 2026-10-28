"""Sequential, resumable real SITL repeats; each planned trial is counted once.

Run from the frozen research checkout. Failed outputs are preserved, never
retried under the same name. ``--resume`` evaluates existing bags or retains
recorded failures; it does not silently replace an unsuccessful repetition.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uav_tracking.research_metrics import numeric_summary, wilson_interval, paired_bootstrap
from uav_tracking.research_failures import classify_infrastructure_failure


def trial_specs(prefix: str, seeds: list[int], classes: list[str], modes: list[str], condition: str,
                estimators: list[str] | None=None) -> list[dict]:
    return [{"name": f"{prefix}_{category}_{mode}"+(f"_{estimator}" if estimator else "")+f"_seed{seed:02d}", "target_class": category,
             "command_mode": mode, "seed": seed, "condition": condition}
             | ({"estimator_method":estimator} if estimator else {})
            for seed in seeds for category in classes for mode in modes for estimator in (estimators or [None])]


def aggregate(rows: list[dict], expected: int) -> dict:
    groups = {}
    for row in rows:
        key = f'{row["target_class"]}_{row["command_mode"]}'+(f'_{row["estimator_method"]}' if row.get("estimator_method") else "")
        groups.setdefault(key, []).append(row)
    summaries = {}
    for key, group in groups.items():
        passed = sum(r.get("result") == "PASS" for r in group)
        summaries[key] = {"planned_or_started": len(group), "pass": passed,
                          "failure_rate": wilson_interval(len(group)-passed, len(group)),
                          "horizontal_distance_error_rmse_m": numeric_summary(r.get("horizontal_rmse_m") for r in group),
                          "height_error_rmse_m": numeric_summary(r.get("height_rmse_m") for r in group),
                          "online_state_anchor_position_rmse_m":numeric_summary(r.get("online_state_anchor_position_rmse_m") for r in group),
                          "online_state_coverage":numeric_summary(r.get("online_state_coverage") for r in group),
                          "command_jitter_rms_mps2":numeric_summary(r.get("command_jitter_rms_mps2") for r in group)}
    paired={}
    strata={}
    for row in rows:
        if row.get("estimator_method"):
            key=f'{row["target_class"]}_{row["command_mode"]}_{row["condition"]}_{row.get("motion_profile_kind","standard")}'
            strata.setdefault(key,{}).setdefault(row["estimator_method"],{})[row["seed"]]=row
    outcomes=("horizontal_rmse_m","height_rmse_m","online_state_anchor_position_rmse_m","online_state_coverage","command_jitter_rms_mps2",
              "initial_distance_opposite_side_overshoot_m","initial_height_opposite_side_overshoot_m",
              "initial_distance_settling_time_s","initial_height_settling_time_s",
              "initial_distance_unsettled_indicator","initial_height_unsettled_indicator","explicit_selection_mean_confirmation_latency_s",
              "follow_visual_observed_center_coverage","follow_visual_detected_center_error_px_rmse",
              "follow_visual_detected_center_normalized_error_rmse","follow_visual_image_to_first_tracking_command_sim_s_mean",
              "follow_visual_image_to_first_tracking_command_sim_s_p95")
    for key,methods in strata.items():
        if "adaptive_kf" not in methods:continue
        for baseline in ("raw","ema","fixed_kf"):
            if baseline not in methods:continue
            seeds=sorted(set(methods["adaptive_kf"])|set(methods[baseline]))
            a=[methods["adaptive_kf"].get(seed) for seed in seeds]
            b=[methods[baseline].get(seed) for seed in seeds]
            comparison={"seed_units":seeds,"outcomes":{},
                        "failure_indicator_difference":paired_bootstrap([float(r["result"]!="PASS") if r else None for r in a],
                                                                         [float(r["result"]!="PASS") if r else None for r in b])}
            for metric in outcomes:
                comparison["outcomes"][metric]={
                    "all_measurable_recorded_pairs":paired_bootstrap([r.get(metric) if r else None for r in a],[r.get(metric) if r else None for r in b]),
                    "conditional_both_flight_pass":paired_bootstrap([r.get(metric) if r and s and r["result"]==s["result"]=="PASS" else None for r,s in zip(a,b)],
                                                                    [s.get(metric) if r and s and r["result"]==s["result"]=="PASS" else None for r,s in zip(a,b)])}
            paired[key+"_adaptive_minus_"+baseline]=comparison
    return {"schema_version": 1, "expected_trials": expected, "recorded_trials": len(rows),
            "complete": len(rows) == expected, "groups": summaries, "paired_comparisons":paired,"trials": rows,
            "paired_statistics":"Adaptive minus baseline; 10,000 bootstrap resamples of complete seed/flight pairs. Whole-interval measurable outcomes retain failed flights when available; both-PASS conditional outcomes are separate and cannot replace failure rates. Missing or not-yet-recorded pairs remain excluded counts, never zero. Intervals are exploratory and not adjusted for multiple comparisons.",
            "scope": "Independent real SITL launches with seeded scene/fault parameters; all failed/incomplete launches remain in denominator. RMSE summaries disclose missing values, and do not impute failures as zero.",
            "updated_utc": datetime.now(timezone.utc).isoformat()}


def retain_interrupted_rows(rows: list[dict]) -> bool:
    changed=False
    for row in rows:
        if row.get("result") in {"RUNNING_FLIGHT","RUNNING_EVALUATION"}:
            row.update(result="INTERRUPTED",interrupted_phase=row["result"],
                       interruption_reason="Previous repetition process ended before completing this slot; evidence retained without automatic retry")
            changed=True
    return changed


def save_report(path: Path, rows: list[dict], expected: int) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(aggregate(rows,expected),indent=2,allow_nan=False)+"\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="stage1_repetitions_v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--classes", nargs="+", choices=["person","car"], default=["person","car"])
    parser.add_argument("--modes", nargs="+", choices=["velocity","position"], default=["velocity","position"])
    parser.add_argument("--condition", default="clean", choices=["clean","depth_noise","depth_holes","dropout","latency","combined"])
    parser.add_argument("--estimators",nargs="+",choices=["raw","ema","fixed_kf","adaptive_kf"])
    parser.add_argument("--motion-profile-kind",choices=["standard","speed_changes"],default="standard")
    parser.add_argument("--real-time-factor",type=float,default=.5)
    parser.add_argument("--car-image-size",type=int,default=640)
    parser.add_argument("--car-threads",type=int,default=4)
    parser.add_argument("--person-image-size",type=int,default=320)
    parser.add_argument("--person-threads",type=int,default=2)
    parser.add_argument("--skip-online-state-evaluation",action="store_true")
    parser.add_argument("--duration", type=float, default=45)
    parser.add_argument("--wall-timeout", type=float, default=300)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after",type=int,default=None,
                        help="Stop after this many newly recorded trials; preserve full planned denominator and resume later")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Seeds must be unique; duplicate seeds cannot count as independent repeats")
    if args.stop_after is not None and args.stop_after<0:
        parser.error("--stop-after must be nonnegative")
    if args.estimators and len(set(args.estimators))!=len(args.estimators):
        parser.error("Estimator methods must be unique")
    if not 0 < args.real_time_factor <= 1:
        parser.error("real-time-factor must be in (0,1]")
    if min(args.car_threads,args.person_threads)<1:
        parser.error("Detector thread counts must be positive")
    if any(size<128 or size%32 for size in (args.car_image_size,args.person_image_size)):
        parser.error("Detector image sizes must be multiples of 32 and at least 128")
    specs = trial_specs(args.prefix, args.seeds, args.classes, args.modes, args.condition,args.estimators)
    for spec in specs:
        spec["motion_profile_kind"]=args.motion_profile_kind
        spec["real_time_factor"]=args.real_time_factor
        spec["inference_image_size"]=args.car_image_size if spec["target_class"]=="car" else args.person_image_size
        spec["inference_threads"]=args.car_threads if spec["target_class"]=="car" else args.person_threads
    report_path = ROOT/"results"/f"{args.prefix}_repetition_report.json"
    if report_path.exists() and not args.resume and not args.dry_run:
        parser.error("Report exists; choose a new prefix or --resume to retain recorded results")
    previous = json.loads(report_path.read_text()) if args.resume and report_path.exists() else {}
    interrupted=retain_interrupted_rows(previous.get("trials",[]))
    completed = {r["name"]: r for r in previous.get("trials", [])}
    for spec in specs:
        if spec["name"] not in completed:continue
        old=completed[spec["name"]]
        changes=[key for key in ("condition","motion_profile_kind","real_time_factor","inference_image_size","inference_threads","estimator_method")
                 if old.get(key)!=spec.get(key)]
        if changes:
            parser.error(f"Refusing to mix configurations in {args.prefix}: {spec['name']} differs in {changes}; use a new prefix and retain the old report")
    if interrupted and not args.dry_run:save_report(report_path,list(completed.values()),len(specs))
    rows = []
    new_trials = 0
    for index, spec in enumerate(specs):
        name = spec["name"]
        output = ROOT/"results"/name
        command = ["bash",str(ROOT/"scripts/run_stage1_trial.sh"),"--name",name,
                   "--class",spec["target_class"],"--command-mode",spec["command_mode"],
                   "--seed",str(spec["seed"]),"--condition",spec["condition"],
                   "--duration",str(args.duration),"--wall-timeout",str(args.wall_timeout),
                   "--occlusions","--reselect-after-loss",
                   "--real-time-factor",str(spec["real_time_factor"]),
                   "--inference-image-size",str(spec["inference_image_size"]),
                   "--inference-threads",str(spec["inference_threads"])]
        if spec.get("estimator_method"):
            command.extend(["--estimator-method",spec["estimator_method"]])
        if args.motion_profile_kind!="standard":
            command.extend(["--motion-profile-kind",args.motion_profile_kind])
        print(f'[{index+1}/{len(specs)}] {name}', flush=True)
        if args.dry_run:
            print(json.dumps(command), flush=True)
            continue
        if name in completed:
            rows.append(completed[name])
            continue
        if args.stop_after is not None and new_trials >= args.stop_after:
            # Include later previously completed records too, without
            # starting any additional simulation in this invocation.
            rows.extend(completed[s["name"]] for s in specs[index:] if s["name"] in completed)
            break
        row = {**spec,"result":"RUNNING_FLIGHT","launch_returncode":None,"evaluation_returncode":None}
        if output.exists() and not args.resume:
            raise FileExistsError(f"Refusing to overwrite {output}")
        # Persist even the first slot before launching an external process.
        # A crash cannot leave an unregistered flight directory that resume
        # would accidentally rerun or mistake for a fresh trial.
        save_report(report_path,rows+[row],len(specs))
        started = time.monotonic()
        if not output.exists():
            process = subprocess.run(command, cwd=ROOT)
            row["launch_returncode"] = process.returncode
        row["wall_duration_s"] = time.monotonic()-started
        row["result"]="RUNNING_EVALUATION"
        save_report(report_path,rows+[row],len(specs))
        infrastructure=classify_infrastructure_failure(output)
        row["infrastructure_failure"]=infrastructure
        if infrastructure["stop"]:
            row["result"]="FAIL"
            row["evaluation_skipped_reason"]="Infrastructure qualification failed; preserve this failure and leave remaining planned flights pending"
            rows.append(row);new_trials+=1;save_report(report_path,rows,len(specs))
            print(f"{name}: infrastructure stop; remaining planned slots stay pending",flush=True)
            break
        offline = output/"offline_evaluation.json"
        if (output/"rosbag/metadata.yaml").exists():
            evaluation = ["bash",str(ROOT/"scripts/evaluate_stage1_flight.sh"),str(output/"rosbag"),
                          "--output",str(offline),"--target-class",spec["target_class"],
                          "--desired-distance-m",str(9.0 if spec["target_class"]=="car" else 5.0),
                          "--telemetry-jsonl",str(output/"telemetry.jsonl"),"--monitor-summary",str(output/"summary.json")]
            with (output/"offline_evaluation.log").open("w") as log:
                result = subprocess.run(evaluation, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        env=dict(os.environ,STAGE1_PROJECT_ROOT=str(ROOT)))
            row["evaluation_returncode"] = result.returncode
        # Metadata can list a stream whose actual messages cannot be decoded.
        # Recheck the evaluator's input evidence before another analysis or
        # flight, while preserving an ordinary tracking FAIL as an outcome.
        infrastructure=classify_infrastructure_failure(output)
        row["infrastructure_failure"]=infrastructure
        if infrastructure["stop"]:
            row["result"]="FAIL"
            row["evaluation_skipped_reason"]="Evaluator exposed unavailable core recording evidence; remaining planned flights retained pending"
            rows.append(row);new_trials+=1;save_report(report_path,rows,len(specs))
            print(f"{name}: infrastructure stop after evaluation; remaining planned slots stay pending",flush=True)
            break
        if offline.exists():
            data = json.loads(offline.read_text())
            occlusions = data.get("occlusions", [])
            # Identical schema-3 acceptance checks to the final engineering
            # matrix, not an optimistic inference from a zero launcher code.
            try:
                from summarize_stage1_acceptance import trial_report
                accepted = trial_report(output)
                row["acceptance"] = accepted
                row["result"] = "PASS" if accepted["passed"] else "FAIL"
            except (ImportError, AttributeError, TypeError, KeyError) as exc:
                row["result"] = "INCOMPLETE"
                row["acceptance_error"] = f"{type(exc).__name__}: {exc}"
            truth = data.get("ground_truth",{})
            row["ground_truth_reference"] = "Whole recorded interval; distance between Gazebo model origins minus requested following distance. Not target-anchor estimation RMSE. HOVER and failures remain included."
            row["horizontal_rmse_m"] = truth.get("horizontal_distance_error_m",{}).get("rmse")
            row["height_rmse_m"] = truth.get("height_above_target_origin_error_m",{}).get("rmse")
            row["offline_report"] = str(offline.relative_to(ROOT))
        if (output/"rosbag/metadata.yaml").exists() and not args.skip_online_state_evaluation:
            online=output/"online_state_accuracy_v2.json"
            online_command=["bash",str(ROOT/"scripts/research_env.sh"),str(ROOT/"scripts/evaluate_online_state_accuracy.py"),
                            str(output),"--target-class",spec["target_class"],"--output",str(online)]
            with (output/"online_state_accuracy.log").open("w") as log:
                result=subprocess.run(online_command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                      env=dict(os.environ,STAGE1_PROJECT_ROOT=str(ROOT)))
            row["online_state_evaluation_returncode"]=result.returncode
            row["online_state_evaluation_status"]="RECORDED" if result.returncode==0 and online.exists() else "INCOMPLETE_EVIDENCE"
            if result.returncode==0 and online.exists():
                data=json.loads(online.read_text())
                row["online_state_report"]=str(online.relative_to(ROOT))
                metrics=data["online_state_accuracy"]["metrics"]
                row["online_state_anchor_position_rmse_m"]=metrics["state_stamp_position_error_m"]["rmse"]
                row["online_state_receipt_anchor_position_rmse_m"]=metrics["receipt_clock_position_error_m"]["rmse"]
                row["online_state_coverage"]=data["online_state_accuracy"]["active_coverage"]
                row["command_jitter_rms_mps2"]=data["control_jitter"]["velocity_command_delta_over_dt_mps2"]["rmse"]
                row["ego_holdout_position_rmse_m"]=data["ego_alignment"]["splits"]["ego_holdout"]["position_error_m"]["rmse"]
        elif args.skip_online_state_evaluation:
            row["online_state_evaluation_status"]="EXPLICITLY_SKIPPED"
        if row["result"]=="RUNNING_EVALUATION":row["result"]="INCOMPLETE"
        if row["launch_returncode"] not in (None,0) or row["evaluation_returncode"] not in (None,0):
            row["result"] = "FAIL"
        rows.append(row)
        new_trials += 1
        save_report(report_path,rows,len(specs))
        print(f'{name}: {row["result"]}; report {report_path}', flush=True)
    if not args.dry_run:
        save_report(report_path,rows,len(specs))


if __name__ == "__main__":
    main()
