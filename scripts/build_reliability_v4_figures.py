"""Standalone v4 PNG/PDF/SVG and raw CSV from explicit JSON summaries only.

No ROS, bags, model inference, flight execution or parameter selection. Failure,
pending and censored slots stay in every applicable trial denominator. Replay
plots require a complete verified summary and hash-bound trial/config files.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uav_tracking.replay_comparison import (  # noqa: E402
    VERIFIED_REPLAY_STATUS, METHODS, canonical_sha256, configuration_digest,
    paired_trial_summary, scheduled_slots, validate_registered_config,
)

CLASSES = ("person", "car")
GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint", "stage3_active", "stage3_multi_active")
CONDITIONS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")
STATUSES = ("PASS", "FAIL", "INTERRUPTED", "INFRASTRUCTURE_ERROR", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING", "RUNNING", "PENDING")
TERMINAL = set(STATUSES)-{"RUNNING", "PENDING"}
SETTLING = ("SETTLED", "RIGHT_CENSORED", "INCONSISTENT", "MISSING")
COLORS = {"PASS":"#007a5e", "FAIL":"#c43835", "INTERRUPTED":"#765aab", "INFRASTRUCTURE_ERROR":"#d18100",
          "INCOMPLETE_EVIDENCE":"#74828c", "EVALUATION_PENDING":"#a6b4c0", "RUNNING":"#287bb5", "PENDING":"#e2e7ec",
          "SETTLED":"#007a5e", "RIGHT_CENSORED":"#d18100", "INCONSISTENT":"#c43835", "MISSING":"#c5cdd5"}
METRIC_FAMILIES = {
    "navigation_errors": [("base_link_distance_rmse_m","Distance RMSE (m)"),("base_link_height_rmse_m","Height RMSE (m)"),
                          ("kf_position_rmse_m","Online KF position RMSE (m)"),("kf_velocity_rmse_mps","Online KF velocity RMSE (m/s)")],
    "coverage": [("navigation_valid_coverage","Valid navigation / scheduled samples"),("physical_follow_truth_coverage","Physical truth / scheduled samples"),
                 ("navigation_position_truth_coverage","Position truth coverage"),("navigation_velocity_truth_coverage","Velocity truth coverage")],
    "settling_observed": [("base_link_distance_settling_s","Observed distance settling (s)"),("base_link_height_settling_s","Observed height settling (s)")],
    "gimbal": [("gimbal_detected_center_normalized_rmse","Detected center RMSE (normalized)"),("gimbal_true_horizon_rmse_rad","True horizon RMSE (rad)"),
               ("gimbal_image_timestamp_tf_coverage","Acquisition-time TF coverage"),("gimbal_encoder_error_rmse_rad","Encoder feedback RMSE (rad)")],
    "identity": [("physical_task_time_known_coverage","Requested-task known coverage"),("physical_task_time_retention_lower_bound","Identity retention lower bound"),
                 ("task_mean_amodal_simulation_mot_idf1","Task-mean amodal diagnostic IDF1"),("task_mean_amodal_simulation_mot_hota","Task-mean amodal diagnostic HOTA"),
                 ("task_mean_unoccluded_geometry_mot_idf1","Task-mean unoccluded IDF1"),("task_mean_unoccluded_geometry_mot_hota","Task-mean unoccluded HOTA")],
    "identity_counts": [("task_mean_amodal_simulation_mot_id_switches","Task-mean amodal diagnostic ID switches"),
                        ("task_mean_unoccluded_geometry_mot_id_switches","Task-mean unoccluded ID switches"),
                        ("physical_task_time_wrong_samples","Wrong physical identity (score-grid samples)"),
                        ("physical_task_time_unknown_samples","Unknown physical identity (score-grid samples)")],
    "performance": [("detector_processed_sim_fps","Processed FPS (simulation time)"),("detector_inference_wall_mean_s","Inference mean (wall s)"),
                    ("detector_inference_wall_p95_s","Inference p95 (wall s)"),("image_to_detector_sim_mean_s","Image-to-detector mean (simulation s)"),
                    ("image_to_detector_sim_p95_s","Image-to-detector p95 (simulation s)"),
                    ("image_to_first_command_sim_mean_s","Image-to-first-command mean (simulation s)"),
                    ("image_to_first_command_sim_p95_s","Image-to-first-command p95 (simulation s)")],
    "control_jitter": [("velocity_command_jitter_rms_mps2","Velocity-command derivative RMS (m/s^2)"),
                       ("yaw_command_jitter_rms_radps2","Yaw-command derivative RMS (rad/s^2)")],
    "image_center": [("image_center_rmse_px","Observed image-center RMSE (px)"),
                     ("image_center_normalized_rmse","Observed image-center RMSE (normalized)"),
                     ("image_center_observed_coverage","Image-center observed coverage")],
    "shutter_prediction": [("short_requested_shutter_prediction_position_rmse_m","Prediction position RMSE in short requested-shutter windows (m)"),
                           ("short_requested_shutter_valid_prediction_coverage","Valid prediction / requested-window samples")],
}
SOURCE_FILES = ("scripts/build_reliability_v4_figures.py", "scripts/summarize_reliability_v4.py",
                "scripts/run_reliability_v4.py", "scripts/run_estimator_replay_v4.py", "uav_tracking/replay_comparison.py")


def require(condition, reason):
    if not condition:raise ValueError(reason)


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def count(value):
    require(type(value) is int and value >= 0,"Invalid nonnegative count")
    return value


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
    return digest.hexdigest()


def load(path):
    require(Path(path).suffix.lower() == ".json","Only explicit JSON inputs are accepted; no bag reader")
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"),
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError("Nonfinite JSON: "+token)))
    require(isinstance(value,dict),"Expected a JSON object")
    return value


def label(row):
    return row["target_class"]+" / "+(row["condition"] if row["cohort"] == "extension" else row["group"])


def comparison_label(category,name):
    names = {"stage3_active_minus_stage3_midpoint":"active - midpoint", "stage1_position_minus_stage1_velocity":"position - velocity"}
    if name.startswith("extension_"):name = name[len("extension_"):].replace("_minus_clean_reference"," - clean")
    return category+" / "+names.get(name,name)


def validate_summary(report):
    require(type(report.get("schema_version")) is int and report["schema_version"] == 1,"Unsupported engineering summary schema")
    cohorts, rows = report.get("cohorts"), report.get("trials")
    require(isinstance(cohorts,dict) and "core" in cohorts and not set(cohorts)-{"core","extension"},"Missing/separate core and extension cohorts")
    require(isinstance(rows,list) and bool(rows),"Summary has no planned trial rows")
    seen = set()
    for row in rows:
        require(isinstance(row,dict) and row.get("cohort") in cohorts and row.get("target_class") in CLASSES,"Invalid trial cohort/class")
        require(row.get("group") in GROUPS and type(row.get("seed")) is int and row["seed"] >= 0,"Invalid trial group/seed")
        cohort = row["cohort"]
        if cohort == "extension":
            require(row.get("condition") in CONDITIONS,"Unknown extension condition")
            expected_group = "stage1_position" if row["condition"] == "speed_changes_position" else "stage1_velocity"
            require(row["group"] == expected_group,"Extension reference control mode differs")
            identifier = f"{row['target_class']}_extension_{row['condition']}_seed{row['seed']:03d}"
        else:identifier = f"{row['target_class']}_{row['group']}_seed{row['seed']:03d}"
        require(row.get("slot_id") == identifier and (cohort,identifier) not in seen,"Changed/duplicate trial identity")
        seen.add((cohort,identifier))
        require(row.get("status") in STATUSES,"Unknown original trial verdict")
        require(isinstance(row.get("metrics"),dict) and isinstance(row.get("settling"),dict),"Missing metrics/censoring")
        for metric,value in row["metrics"].items():
            require(isinstance(metric,str) and (value is None or finite(value) and value >= 0),"Invalid/negative trial metric")
            if value is not None and ("coverage" in metric or metric.endswith(("_idf1","_hota","retention_lower_bound"))):
                require(value <= 1.,"Coverage/identity proportion exceeds one")
        sample_counts = row.get("metric_sample_counts",{})
        require(isinstance(sample_counts,dict),"Metric error-sample counts must be a separate mapping")
        for metric,value in sample_counts.items():
            require(metric in row["metrics"],"Error-sample count is assigned to an unknown metric")
            if value is not None:count(value)
        for dimension in ("distance","height"):
            state = row["settling"].get(dimension)
            require(state in SETTLING,"Missing explicit settling censoring state")
            value = row["metrics"].get(f"base_link_{dimension}_settling_s")
            require((state == "SETTLED" and finite(value) and value >= 0) or (state != "SETTLED" and value is None),
                    "Censored/missing settling cannot become a finite zero")
    for cohort,metadata in cohorts.items():
        selected = [row for row in rows if row["cohort"] == cohort]
        expected_mode = {"core":{"FORMAL","PROBE"},"extension":{"EXTENSION_FORMAL","EXTENSION_PROBE"}}[cohort]
        require(metadata.get("mode") in expected_mode,"Cohort mode is not explicitly formal/development")
        counts = Counter(row["status"] for row in selected)
        declared = metadata.get("status_counts",{})
        require(isinstance(declared,dict) and not set(declared)-set(STATUSES),"Unknown cohort status category")
        for value in declared.values():count(value)
        require({key:value for key,value in declared.items() if value} == dict(counts),"Cohort status denominator disagrees with rows")
        require(count(metadata.get("planned_slots")) == len(selected)
                and count(metadata.get("terminal_slots")) == sum(counts[state] for state in TERMINAL),"Planned/terminal denominator changed")
        if metadata["mode"].endswith("FORMAL"):
            expected = {(cls,item,seed) for cls in CLASSES for item in (GROUPS if cohort == "core" else CONDITIONS) for seed in range(1000,1010)}
            actual = {(row["target_class"],row["group"] if cohort == "core" else row["condition"],row["seed"]) for row in selected}
            require(actual == expected,"A formal summary must retain the full 120/160 planned matrix")
    require(isinstance(report.get("paired_comparisons"),list),"Missing explicit paired-comparison list")
    validate_pairs(report)
    return report


def validate_pairs(report):
    by_id = {row["slot_id"]:row for row in report["trials"]}
    seen = set()
    for comparison in report["paired_comparisons"]:
        key = (comparison.get("comparison"),comparison.get("target_class"))
        require(key not in seen and key[1] in CLASSES,"Duplicate/unknown paired comparison")
        seen.add(key)
        require(comparison.get("difference_direction") == "left_minus_right" and comparison.get("formal_pairs_per_condition") == 10,
                "Pair direction/formal denominator changed")
        name = key[0]
        require(isinstance(name,str),"Missing paired comparison name")
        core_pairs = {"stage3_active_minus_stage3_midpoint":("stage3_active","stage3_midpoint"),
                      "stage1_position_minus_stage1_velocity":("stage1_position","stage1_velocity")}
        condition = name[len("extension_"):-len("_minus_clean_reference")] if name.startswith("extension_") and name.endswith("_minus_clean_reference") else None
        require(name in core_pairs or condition in CONDITIONS,"Unknown prospective comparison")
        require(isinstance(comparison.get("metrics"),dict),"Missing paired metric mapping")
        for metric,item in comparison["metrics"].items():
            pairs = item.get("pairs")
            require(isinstance(pairs,list) and len(pairs) == count(comparison.get("planned_pairs_in_matrix")),"Paired source rows lost")
            values, passed, seeds = [], [], set()
            for pair in pairs:
                seed = pair.get("seed")
                require(type(seed) is int and seed not in seeds,"Duplicate or absent paired seed")
                seeds.add(seed)
                if condition is not None:
                    reference = "stage1_position" if condition == "speed_changes_position" else "stage1_velocity"
                    ids = (f"{key[1]}_extension_{condition}_seed{seed:03d}",f"{key[1]}_{reference}_seed{seed:03d}")
                else:ids = tuple(f"{key[1]}_{group}_seed{seed:03d}" for group in core_pairs[name])
                require((pair.get("left_id"),pair.get("right_id")) == ids,"Pair IDs do not match the declared prospective contrast")
                left,right = by_id.get(pair.get("left_id")),by_id.get(pair.get("right_id"))
                for row in (left,right):
                    if row is not None:require(row["seed"] == seed and row["target_class"] == key[1],"Pairs mix seed or class")
                expected_statuses = [row["status"] if row else "NOT_SCHEDULED_IN_CORE_PLAN" for row in (left,right)]
                require([pair.get("left_status"),pair.get("right_status")] == expected_statuses,"Pair original verdict changed")
                a = left["metrics"].get(metric) if left else None
                b = right["metrics"].get(metric) if right else None
                difference = a-b if finite(a) and finite(b) else None
                require(pair.get("difference") == difference,"Paired difference disagrees with raw trial metrics")
                both = left is not None and right is not None and left["status"] == right["status"] == "PASS"
                require(pair.get("both_engineering_pass") is both,"Both-PASS subset changed")
                values.append(difference);passed.append(difference if both else None)
            for subset,raw in (("all_finite_pairs",values),("both_pass_pairs",passed)):
                stats = item.get(subset,{})
                available = [value for value in raw if finite(value)]
                require(count(stats.get("n_slots")) == len(raw) and count(stats.get("n")) == len(available)
                        and count(stats.get("n_missing")) == len(raw)-len(available),"Paired finite denominator changed")
                require(stats.get("mean") == (statistics.mean(available) if available else None),"Paired mean differs from source trial blocks")
                interval = stats.get("ci95")
                require(interval is None or isinstance(interval,list) and len(interval) == 2 and all(finite(value) for value in interval)
                        and interval[0] <= interval[1] and len(available) >= 2,"Invalid paired confidence interval")


def verified_file(directory, item):
    require(isinstance(item,dict) and isinstance(item.get("path"),str),"Missing hash-bound JSON artifact")
    relative = Path(item["path"])
    require(not relative.is_absolute() and ".." not in relative.parts,"Artifact path must stay relative to its summary")
    path = directory/relative
    require(not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(directory.resolve()),"Artifact escapes summary or is missing")
    require(sha(path) == item.get("sha256"),"Replay artifact SHA256 changed")
    return path


def load_replay(path):
    """No arrays/rosbags are opened; pending summaries never expose trial files."""
    summary = load(path)
    require(summary.get("evaluation_status") == VERIFIED_REPLAY_STATUS and summary.get("complete_verified_matrix") is True
            and summary.get("verified_trial_reports") == 20 and not summary.get("missing_or_invalid_inputs"),
            "Replay summary remains pending; no verified four-method figures")
    directory = Path(path).resolve().parent
    artifacts = summary.get("trial_report_artifacts")
    require(isinstance(artifacts,list) and len(artifacts) == 20,"Replay summary lacks twenty bound trial-report files")
    require({item.get("slot_id") for item in artifacts} == set(scheduled_slots()),"Replay artifact matrix changed")
    config_path = verified_file(directory,summary.get("registered_configuration_artifact"))
    config = load(config_path);validate_registered_config(config)
    require(summary.get("evaluation_source",{}).get("configuration_sha256") == configuration_digest(config),"Replay configuration source differs")
    sources = [{"path":str(config_path),"sha256":summary["registered_configuration_artifact"]["sha256"],"source_role":"replay_configuration"}]
    reports = []
    for item in artifacts:
        trial_path = verified_file(directory,item);report = load(trial_path)
        require(report.get("slot_id") == item["slot_id"],"Replay artifact is assigned to another slot")
        reports.append(report)
        sources.append({"path":str(trial_path),"sha256":item["sha256"],"source_role":"verified_replay_trial"})
    recalculated = paired_trial_summary(reports,config)
    for key in ("evaluation_status","scheduled_trials","available_trial_reports","verified_trial_reports","complete_verified_matrix","classes","bootstrap"):
        require(recalculated.get(key) == summary.get(key),"Replay summary contradicts its verified trial blocks: "+key)
    require(recalculated["complete_verified_matrix"] is True,"Replay evidence/support remains incomplete")
    return summary,reports,sources


def scope(report, fixture_only=False):
    if fixture_only or report.get("evidence_scope") == "FIXTURE_ONLY":return "FIXTURE_ONLY"
    return "FORMAL_SUMMARY" if all(item["mode"].endswith("FORMAL") for item in report["cohorts"].values()) else "DEVELOPMENT_PROBE_NOT_FORMAL_RESULTS"


def metric_rows(trials,metrics):
    return [{"cohort":row["cohort"],"slot_id":row["slot_id"],"target_class":row["target_class"],"group":row["group"],
             "condition":row["condition"],"seed":row["seed"],"status":row["status"],"label":label(row),"metric":metric,
             "value":row["metrics"].get(metric),"source_error_samples":row.get("metric_sample_counts",{}).get(metric),
             "sample_count_basis":"source summary metric_sample_counts; empty means unavailable",
             "distance_settling":row["settling"]["distance"],"height_settling":row["settling"]["height"]}
            for row in trials for metric in metrics]


def make_specs(report, *, replay=None, fixture_only=False):
    specs,pending = [],[]
    evidence_scope = scope(report,fixture_only)
    def add(identifier,kind,title,rows,**extra):
        specs.append({"figure_id":identifier,"kind":kind,"title":title,"rows":rows,"scope":evidence_scope,
            "source_role":"engineering_summary","caption":title+". Original failed/pending slots and missing values are retained. n denotes trials, never image/error samples.",**extra})
    def available_panels(identifier,definitions,rows,value_key):
        available = []
        for definition in definitions:
            if any(row["metric"] == definition[0] and finite(row[value_key]) for row in rows):available.append(definition)
            else:pending.append({"figure_id":identifier+"__"+definition[0],"reason":"NO_FINITE_SOURCE_METRIC_FOR_PANEL"})
        return available
    for cohort in report["cohorts"]:
        trials = [row for row in report["trials"] if row["cohort"] == cohort]
        groups = defaultdict(list)
        for row in trials:groups[label(row)].append(row)
        counts = [{"label":name,"category":state,"count":sum(row["status"] == state for row in rows),"planned_trials":len(rows)}
                  for name,rows in sorted(groups.items()) for state in STATUSES]
        add(cohort+"_verdicts","counts",cohort+": all planned trial verdicts",counts,categories=list(STATUSES))
        censoring = [{"label":name+" / "+dimension,"category":state,"count":sum(row["settling"][dimension] == state for row in rows),
                      "planned_trials":len(rows)} for name,rows in sorted(groups.items()) for dimension in ("distance","height") for state in SETTLING]
        add(cohort+"_settling_censoring","counts",cohort+": settling and right censoring",censoring,categories=list(SETTLING))
        for family,definitions in METRIC_FAMILIES.items():
            selected = trials
            if family.startswith("identity") or family == "gimbal":
                required = "physical_identity" if family.startswith("identity") else "gimbal"
                selected = [row for row in trials if required in row.get("required_evaluator_kinds",[])]
            rows = metric_rows(selected,[name for name,_ in definitions])
            identifier = cohort+"_"+family
            if not any(finite(row["value"]) for row in rows):
                pending.append({"figure_id":identifier,"reason":"NO_FINITE_APPLICABLE_SOURCE_METRIC","planned_applicable_trials":len(selected)})
                continue
            add(identifier,"metrics",cohort+": "+family.replace("_"," "),rows,
                metrics=available_panels(identifier,definitions,rows,"value"))
            if family == "shutter_prediction":
                specs[-1]["caption"] += " Windows follow shutter requests; they do not independently establish pixel-level occlusion."
    for cohort in report["cohorts"]:
        selected = [comparison for comparison in report["paired_comparisons"] if comparison["comparison"].startswith("extension_") == (cohort == "extension")]
        for family in ("navigation_errors","coverage","gimbal","identity","identity_counts","performance","settling_observed","control_jitter","image_center","shutter_prediction"):
            definitions = METRIC_FAMILIES[family]
            estimates,raw = [],[]
            for comparison in selected:
                for metric,_ in definitions:
                    item = comparison["metrics"].get(metric)
                    if not isinstance(item,dict):continue
                    for subset in ("all_finite_pairs","both_pass_pairs"):
                        stats = item[subset]
                        estimates.append({"label":comparison_label(comparison["target_class"],comparison["comparison"]),"target_class":comparison["target_class"],
                            "comparison":comparison["comparison"],"metric":metric,"subset":subset,"mean":stats["mean"],
                            "ci_low":stats["ci95"][0] if stats["ci95"] else None,"ci_high":stats["ci95"][1] if stats["ci95"] else None,
                            "ci_status":stats["ci_status"],"n_finite_trial_pairs":stats["n"],"n_planned_trial_pairs":comparison["planned_pairs_in_matrix"],
                            "formal_planned_pairs":10})
                    raw.extend({"comparison":comparison["comparison"],"target_class":comparison["target_class"],"metric":metric,**pair} for pair in item["pairs"])
            identifier = cohort+"_paired_"+family
            if not any(finite(row["mean"]) for row in estimates):
                pending.append({"figure_id":identifier,"reason":"NO_FINITE_PAIRED_SOURCE_METRIC"});continue
            add(identifier,"paired",cohort+": left-minus-right paired "+family.replace("_"," "),estimates,
                metrics=available_panels(identifier,definitions,estimates,"mean"),raw_rows=raw,
                caption="Paired trial/seed differences; all finite pairs and both-original-PASS subset shown separately. n/10 is the formal design, actual supplied-plan pair count is separate. Conditional CI is copied from the source summary; missing/degenerate CI stays absent.")
    if replay is not None:
        replay_summary,reports = replay
        rows = []
        for report_row in reports:
            for method in METHODS:
                for metric,samples in (("position_rmse_m","common_position_samples"),("velocity_rmse_mps","common_velocity_samples")):
                    value = report_row["metrics"]["methods"][method].get(metric)
                    require(value is None or finite(value) and value >= 0,"Invalid verified replay metric")
                    rows.append({"label":report_row["target_class"]+" / "+method,"target_class":report_row["target_class"],"method":method,
                        "slot_id":report_row["slot_id"],"seed":report_row["seed"],"status":report_row["engineering_status"],"metric":metric,"value":value,
                        "source_error_samples":count(report_row["metrics"][samples]),"sample_count_basis":"common four-method truth-supported score-grid samples"})
        add("replay_four_methods","metrics","Verified same-measurement estimator errors",rows,
            metrics=available_panels("replay_four_methods",[("position_rmse_m","Common-support position RMSE (m)"),
                ("velocity_rmse_mps","Common-support velocity RMSE (m/s)")],rows,"value"),
            source_role="verified_estimator_replay",
            caption="Four estimators share each recording's causal measurements and common scoring support. Ten independent trials per class; error sample counts are separate CSV fields. Original flight FAIL remains FAIL. These are conditional offline estimates, not four closed-loop flight controllers.")
        paired = []
        for category,data in replay_summary["classes"].items():
            for name,contrast in data["contrasts"].items():
                interval = contrast["ci95"]
                paired.append({"label":category+" / "+name,"metric":"position_rmse_m","subset":"verified_same_measurement_pairs",
                    "mean":contrast["mean_difference"],"ci_low":interval[0] if interval else None,"ci_high":interval[1] if interval else None,
                    "ci_status":contrast["ci_status"],"n_finite_trial_pairs":contrast["finite_pairs"],"n_planned_trial_pairs":10,"formal_planned_pairs":10})
        add("replay_position_paired_ci","paired","Verified adaptive-minus-baseline position differences",paired,
            metrics=[("position_rmse_m","Position RMSE difference (m)")],source_role="verified_estimator_replay",
            caption="Geometry-adaptive KF minus each registered baseline; paired trial-block conditional 95% CI and n/10 from the verified replay summary. Original engineering failures remain in the denominator.")
        pending.append({"figure_id":"replay_velocity_paired_ci","reason":"NO_REGISTERED_VELOCITY_CONTRAST_CI_IN_CURRENT_REPLAY_SUMMARY"})
    else:pending.append({"figure_id":"replay_four_methods","reason":"NO_COMPLETE_VERIFIED_REPLAY_EVIDENCE"})
    return specs,pending


def write_csv(path, rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("x",encoding="utf-8-sig",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=columns or ["no_source_rows"])
        writer.writeheader();writer.writerows(rows)


def render(spec, output):
    """Lazy, noninteractive rendering; tests exercise one tiny fixture only."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    metrics = spec.get("metrics",[])
    panels = 1 if spec["kind"] == "counts" else len(metrics)
    labels = list(dict.fromkeys(row["label"] for row in spec["rows"]))
    ncols = min(2,panels);nrows = math.ceil(panels/ncols)
    with plt.rc_context({"font.size":8,"axes.titlesize":9,"svg.fonttype":"none","pdf.fonttype":42}):
        fig,axes = plt.subplots(nrows,ncols,figsize=(6.3*ncols,max(3.,len(labels)*.29)*nrows),squeeze=False)
        legend_handles = []
        for axis in axes.flat:axis.set_axisbelow(True);axis.grid(axis="x",alpha=.18)
        if spec["kind"] == "counts":
            axis = axes[0,0];left = [0]*len(labels)
            for category in spec["categories"]:
                values = [sum(row["count"] for row in spec["rows"] if row["label"] == name and row["category"] == category) for name in labels]
                bars = axis.barh(range(len(labels)),values,left=left,label=category,color=COLORS[category],edgecolor="white",linewidth=.35)
                for bar,value,offset in zip(bars,values,left):
                    if value:axis.text(offset+value/2,bar.get_y()+bar.get_height()/2,str(value),ha="center",va="center",fontsize=7,
                                       color="white" if category in {"PASS","FAIL","INTERRUPTED","RUNNING"} else "#172938")
                left = [a+b for a,b in zip(left,values)]
            axis.set_yticks(range(len(labels)),labels);axis.invert_yaxis();axis.set_xlabel("All planned trials (count)")
            legend_handles = axis.get_legend_handles_labels()[0]
        else:
            for axis,(metric,title) in zip(axes.flat,metrics):
                rows = [row for row in spec["rows"] if row["metric"] == metric]
                current_labels = list(dict.fromkeys(row["label"] for row in rows))
                ticks = []
                for index,name in enumerate(current_labels):
                    group = [row for row in rows if row["label"] == name]
                    if spec["kind"] == "metrics":
                        available = [row for row in group if finite(row["value"])]
                        for offset,row in enumerate(available):
                            y = index+(offset-(len(available)-1)/2)*min(.055,.34/max(1,len(available)))
                            axis.scatter(row["value"],y,color=COLORS.get(row["status"],"#74828c"),marker="o" if row["status"] == "PASS" else "x",s=19,alpha=.85)
                        if available:axis.scatter(statistics.mean(row["value"] for row in available),index,marker="D",s=25,color="#172938",zorder=4)
                        ticks.append(name+f"  n trials={len(available)}/{len(group)}")
                    else:
                        notes = []
                        for number,row in enumerate(group):
                            notes.append(f"{row['subset']}: n={row['n_finite_trial_pairs']}/10, plan={row['n_planned_trial_pairs']}"+("; CI absent" if row["ci_low"] is None else ""))
                            if not finite(row["mean"]):continue
                            y = index+(number-(len(group)-1)/2)*.18
                            color = "#236da0" if row["subset"] != "both_pass_pairs" else "#c57316"
                            if row["ci_low"] is not None:
                                axis.plot([row["ci_low"],row["ci_high"]],[y,y],color=color,linewidth=1.4)
                            axis.scatter(row["mean"],y,color=color,s=22,marker="o" if row["subset"] != "both_pass_pairs" else "s")
                        ticks.append(name+"\n"+" | ".join(notes));axis.axvline(0,color="#74828c",linewidth=.6)
                axis.set_yticks(range(len(current_labels)),ticks,fontsize=7);axis.invert_yaxis();axis.set_xlabel(title)
                axis.set_title(title)
            for axis in list(axes.flat)[panels:]:axis.set_visible(False)
            if spec["kind"] == "metrics":
                states = [state for state in STATUSES if any(row.get("status") == state for row in spec["rows"])]
                legend_handles = [Line2D([],[],color=COLORS[state],marker="o" if state == "PASS" else "x",linestyle="",label=state) for state in states]
        fig.suptitle(spec["title"]+"\n"+spec["scope"],fontsize=11)
        height = fig.get_figheight()
        if legend_handles:
            fig.legend(handles=legend_handles,loc="upper center",bbox_to_anchor=(.5,1.-.48/height),
                       ncol=min(4,len(legend_handles)),fontsize=7,frameon=False)
        fig.text(.01,.008,"Trial n and error-sample n are separate; missing/censored values are never zero. CSV retains raw verdicts and values.",fontsize=7)
        fig.tight_layout(rect=(0,.20/height,1,1.-(1.02 if legend_handles else .60)/height))
        paths = []
        for extension in ("png","pdf","svg"):
            path = Path(output)/(spec["figure_id"]+"."+extension)
            require(not path.exists(),"Refusing to overwrite a figure")
            fig.savefig(path,dpi=180,bbox_inches="tight",metadata={"Title":spec["title"]});paths.append(path)
        plt.close(fig)
    return paths


def artifact(path, output, **metadata):
    return {"path":Path(path).relative_to(output).as_posix(),"sha256":sha(path),"bytes":Path(path).stat().st_size,**metadata}


def build(summary_path, output, *, replay_summary_path=None, only=None, fixture_only=False):
    summary_path = Path(summary_path).resolve(strict=True);output = Path(output)
    implementation_hashes = {name:sha(ROOT/name) for name in SOURCE_FILES}
    summary_hash = sha(summary_path)
    report = validate_summary(load(summary_path))
    sources = [{"path":str(summary_path),"sha256":summary_hash,"source_role":"engineering_summary"}]
    replay,pending_replay = None,[]
    replay_hash = None
    if replay_summary_path is not None:
        replay_path = Path(replay_summary_path).resolve(strict=True);replay_hash = sha(replay_path)
        sources.append({"path":str(replay_path),"sha256":replay_hash,"source_role":"replay_summary"})
        try:
            replay_data,replay_reports,replay_sources = load_replay(replay_path)
            replay = (replay_data,replay_reports);sources.extend(replay_sources)
        except (OSError,ValueError,KeyError,TypeError) as error:
            pending_replay.append({"figure_id":"replay_four_methods","reason":"PENDING_OR_INVALID_REPLAY_EVIDENCE: "+str(error)})
    specs,pending = make_specs(report,replay=replay,fixture_only=fixture_only)
    pending.extend(pending_replay)
    identifiers = {spec["figure_id"] for spec in specs}
    if only is not None:require(isinstance(only,list) and bool(only) and len(set(only)) == len(only) and not set(only)-identifiers,"Unknown/duplicate requested figure ID")
    selected = specs if only is None else [spec for spec in specs if spec["figure_id"] in only]
    output.mkdir(parents=True,exist_ok=False)
    figures,csv_artifacts = [],[]
    rows = report["trials"]
    trial_csv = output/"all_planned_trials.csv"
    write_csv(trial_csv,[{key:row.get(key) for key in ("cohort","slot_id","target_class","group","condition","seed","status","engineering_result","infrastructure_stop")} for row in rows])
    csv_artifacts.append(artifact(trial_csv,output,source_role="engineering_summary",figure_id="all_planned_trials"))
    metrics = sorted({name for row in rows for name in row["metrics"]})
    metric_csv = output/"all_trial_metrics.csv";write_csv(metric_csv,metric_rows(rows,metrics))
    csv_artifacts.append(artifact(metric_csv,output,source_role="engineering_summary",figure_id="all_trial_metrics"))
    pair_csv = output/"all_paired_trial_differences.csv"
    write_csv(pair_csv,[{"comparison":comparison["comparison"],"target_class":comparison["target_class"],"metric":metric,**pair}
                        for comparison in report["paired_comparisons"] for metric,item in comparison["metrics"].items() for pair in item["pairs"]])
    csv_artifacts.append(artifact(pair_csv,output,source_role="engineering_summary",figure_id="all_paired_trial_differences"))
    for spec in selected:
        require(re.fullmatch(r"[a-z0-9_]+",spec["figure_id"]) is not None,"Invalid output figure ID")
        data_path = output/(spec["figure_id"]+".csv");write_csv(data_path,spec["rows"])
        csv_artifacts.append(artifact(data_path,output,figure_id=spec["figure_id"],source_role=spec["source_role"]))
        if spec.get("raw_rows"):
            raw_path = output/(spec["figure_id"]+"_pairs.csv");write_csv(raw_path,spec["raw_rows"])
            csv_artifacts.append(artifact(raw_path,output,figure_id=spec["figure_id"],source_role=spec["source_role"]))
        for path in render(spec,output):
            figures.append(artifact(path,output,figure_id=spec["figure_id"],format=path.suffix[1:],caption=spec["caption"],scope=spec["scope"],source_role=spec["source_role"]))
    for source in sources:require(sha(source["path"]) == source["sha256"],"Source JSON changed while building figures")
    require(all(sha(ROOT/name) == value for name,value in implementation_hashes.items()),"Figure implementation/helper changed during generation")
    manifest = {"schema_version":1,"kind":"RELIABILITY_V4_FIGURES","generated_utc":datetime.now(timezone.utc).isoformat(),
        "summary_path":str(summary_path),"summary_sha256":sources[0]["sha256"],"scope":scope(report,fixture_only),
        "replay_summary_path":str(Path(replay_summary_path).resolve()) if replay_summary_path is not None else None,"replay_summary_sha256":replay_hash,
        "figures":figures,"csv":csv_artifacts,"pending":pending,"omitted_figure_ids":sorted(identifiers-{spec["figure_id"] for spec in selected}),
        "cohorts":report["cohorts"],"input_sources":sources,"source_hashes":implementation_hashes,
        "rendering":{"backend":"Agg","png_dpi":180,"formats":["png","pdf","svg"],"matplotlib_version":version("matplotlib"),"python_version":sys.version.split()[0]},
        "input_implementation_sources":report.get("implementation_sources",{}),
        "claim_boundary":"Figures summarize supplied immutable JSON; they do not certify flight acceptance. All trial verdicts and missing/censored values remain. Replay plots require verified same-measurement evidence and do not imply four-controller closed-loop comparisons."}
    with (output/"manifest.json").open("x",encoding="utf-8") as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write("\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary",type=Path,required=True)
    parser.add_argument("--replay-summary",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--only",nargs="+",help="Explicit small selection; omitted figure IDs remain in manifest")
    parser.add_argument("--fixture-only",action="store_true",help="Watermark test artifacts as FIXTURE_ONLY")
    args = parser.parse_args(argv)
    try:manifest = build(args.summary,args.output,replay_summary_path=args.replay_summary,only=args.only,fixture_only=args.fixture_only)
    except (OSError,ValueError,KeyError,TypeError) as error:parser.error(str(error))
    print(json.dumps({"scope":manifest["scope"],"figure_files":len(manifest["figures"]),"pending":manifest["pending"],"output":str(args.output)},ensure_ascii=False))
    return 0


if __name__ == "__main__":raise SystemExit(main())
