"""Plot recorded 166-flight summary JSON only; never starts a simulator or reader.

Figures preserve failed/missing flight units and distinguish actual online
surface-anchor error from ideal-ego replay. CSVs and a hash-addressed copy of
the source summary accompany PNG, PDF and SVG artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
METHODS = ("raw", "ema", "fixed_kf", "adaptive_kf")
METHOD_COLORS = ("#758496", "#d59b39", "#27889a", "#6751b5")
STATUS_COLORS = {
    "PASS": "#39856b", "FAIL": "#bd5148", "INCOMPLETE": "#d39a44",
    "INTERRUPTED": "#9971ab", "PENDING": "#dce1e7",
    "RUNNING_FLIGHT": "#69a8c3", "RUNNING_EVALUATION": "#4e78a0",
}
UNITS = {
    "horizontal_rmse_m": "Whole-interval model-origin follow-distance RMSE (m)",
    "height_rmse_m": "Whole-interval height RMSE (m)",
    "online_state_anchor_position_rmse_m": "Actual online surface-anchor position RMSE (m)",
    "online_state_coverage": "Active state / all recorded opportunities",
    "command_jitter_rms_mps2": "Velocity command delta / dt RMS (m/s²)",
    "detected_center_normalized_error_rmse": "Detection-conditioned image-center RMSE",
    "true_image_horizon_error_rad_rmse": "True image horizon RMSE (rad)",
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def save(fig, output, name):
    paths = []
    for extension in ("png", "pdf", "svg"):
        path = output / f"{name}.{extension}"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def footer(fig, text):
    fig.text(.5, .006, text, ha="center", va="bottom", fontsize=8, wrap=True)


def plot_progress(data, output):
    groups = defaultdict(Counter)
    for trial in data.get("trials", []):
        groups[(trial["stage"], trial["target_class"])][trial.get("result", "PENDING")] += 1
    fig, ax = plt.subplots(figsize=(11, 5.6))
    keys = sorted(groups)
    statuses = [s for s in STATUS_COLORS if any(groups[k][s] for k in keys)]
    statuses += sorted(set().union(*(set(groups[k]) for k in keys)) - set(STATUS_COLORS)) if keys else []
    left = np.zeros(len(keys))
    for status in statuses:
        values = np.array([groups[key][status] for key in keys])
        bars = ax.barh(np.arange(len(keys)), values, left=left, color=STATUS_COLORS.get(status, "#222222"), label=status)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + value / 2, bar.get_y() + bar.get_height() / 2, str(value), ha="center", va="center", fontsize=9)
        left += values
    ax.set_yticks(np.arange(len(keys)), [f"Stage {stage}: {category} (planned {sum(groups[(stage, category)].values())})" for stage, category in keys])
    ax.set_xlabel("Independent planned flight slots")
    ax.set_title(f"Recorded study progress: {data.get('recorded_or_attempted_flights', 0)} / {data.get('planned_flights', 166)} attempted")
    if statuses: ax.legend(loc="upper center", bbox_to_anchor=(.5, -.15), ncol=4, fontsize=9)
    ax.grid(axis="x", alpha=.2)
    footer(fig, "Attempted / completed evidence is distinct from PASS. Failed, incomplete and pending slots remain visible.")
    fig.tight_layout(rect=(0, .12, 1, 1))
    return save(fig, output, "flight_status")


def plot_stage1(data, output):
    rows = [row for row in data.get("trials", []) if row.get("stage") == 1 and row.get("command_mode") == "velocity"]
    fields = ("online_state_anchor_position_rmse_m", "horizontal_rmse_m", "online_state_coverage")
    fig, axes = plt.subplots(2, len(fields), figsize=(16, 8), squeeze=False)
    for category, axs in zip(("person", "car"), axes):
        for ax, field in zip(axs, fields):
            for index, (method, color) in enumerate(zip(METHODS, METHOD_COLORS)):
                group = sorted((r for r in rows if r["target_class"] == category and r["estimator_method"] == method), key=lambda r: r["seed"])
                measured = [r for r in group if finite(r.get(field))]
                values = [r[field] for r in measured]
                for row in measured:
                    offset = ((row["seed"] % 10) - 4.5) * .035
                    ax.scatter(index + offset, row[field], s=25, marker="o" if row["result"] == "PASS" else "x", color=color if row["result"] == "PASS" else "#bd5148", alpha=.8, zorder=3)
                if values:
                    ax.errorbar(index, np.mean(values), yerr=np.std(values, ddof=1) if len(values) > 1 else 0, fmt="_", markersize=18, color="#202934", capsize=5, zorder=4)
            labels = []
            for method in METHODS:
                group = [r for r in rows if r["target_class"] == category and r["estimator_method"] == method]
                labels.append(f"{method}\nmeasured {sum(finite(r.get(field)) for r in group)}/{len(group)}\nPASS {sum(r['result'] == 'PASS' for r in group)}")
            ax.set_xticks(np.arange(4), labels, fontsize=8)
            ax.set_ylabel(UNITS[field], fontsize=9)
            ax.set_title(category)
            if field.endswith("coverage"): ax.set_ylim(-.03, 1.03)
            ax.grid(axis="y", alpha=.2)
    fig.suptitle("Stage 1: real isolated velocity-control flights; dots are whole-flight/seed units, bars are mean ± sample SD", fontsize=12)
    footer(fig, "Red × retains measurable failed flights. Missing values are not zero. Surface-anchor position error uses actual online PX4/map state, not ideal-ego replay or model-center truth.")
    fig.tight_layout(rect=(0, .04, 1, .95))
    return save(fig, output, "stage1_recorded_outcomes")


def comparisons(data):
    result = []
    for comparison, group in data.get("stage1_joined_statistics", {}).get("paired_comparisons", {}).items():
        for metric, conditions in group.get("outcomes", {}).items():
            for condition, interval in conditions.items():
                result.append({"stage": 1, "comparison": comparison, "metric": metric, "condition": condition, **interval})
        interval = group.get("failure_indicator_difference", {})
        result.append({"stage": 1, "comparison": comparison, "metric": "failure_indicator", "condition": "all_recorded_pairs", **interval})
    for category, group in data.get("stage3_paired_statistics", {}).items():
        for metric, conditions in group.get("active_minus_midpoint", {}).items():
            for condition, interval in conditions.items():
                if isinstance(interval, dict):
                    result.append({"stage": 3, "comparison": f"{category}_active_minus_midpoint", "metric": metric, "condition": condition, **interval})
    return result


def interval_row(ax, row, y, color):
    mean, ci = row.get("mean_difference"), row.get("ci95")
    pairs = row.get("pairs", 0)
    excluded = row.get("excluded_pairs", row.get("excluded", None))
    annotation = f"n={pairs}" + (f", excluded={excluded}" if excluded is not None else "")
    if finite(mean) and ci and all(finite(value) for value in ci):
        ax.plot(ci, [y, y], color=color, lw=2)
        ax.scatter([mean], [y], color=color, s=30, zorder=3)
        ax.annotate(annotation, (ci[1], y), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8)
    else:
        ax.text(.03, y, f"No measurable interval ({annotation})", transform=ax.get_yaxis_transform(), fontsize=8, va="center", color="#6a737e")


def plot_stage1_pairs(data, output):
    rows = comparisons(data)
    fields = ("online_state_anchor_position_rmse_m", "horizontal_rmse_m", "online_state_coverage", "failure_indicator")
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    for ax, field in zip(axes.flat, fields):
        selected = [r for r in rows if r["stage"] == 1 and r["metric"] == field and r["condition"] in {"all_measurable_recorded_pairs", "all_recorded_pairs"}]
        for index, row in enumerate(selected):
            interval_row(ax, row, index, METHOD_COLORS[-1])
        ax.set_yticks(np.arange(len(selected)), [r["comparison"].replace("_velocity_clean_standard_adaptive_minus_", " vs ") for r in selected], fontsize=8)
        ax.axvline(0, color="#8a949f", ls="--")
        ax.set_xlabel("Adaptive minus baseline:\n" + UNITS.get(field, "failure-rate difference"), fontsize=9)
        ax.grid(axis="x", alpha=.2)
        if not selected: ax.text(.5, .5, "No recorded paired evidence", transform=ax.transAxes, ha="center")
        ax.margins(x=.4)
        ax.set_ylim(-.6, max(.6, len(selected)-.4))
    fig.suptitle("Stage 1: paired bootstrap 95% intervals, 10,000 resamples of whole seed units\nAll measurable recorded pairs include failed flights; both-PASS sensitivity is exported in CSV", fontsize=12)
    footer(fig, "Exploratory intervals; no multiplicity adjustment. Negative favors adaptive for errors/failures; positive favors adaptive for coverage. No claim of universal superiority.")
    fig.tight_layout(rect=(0, .04, 1, .94))
    return save(fig, output, "stage1_paired_intervals")


def plot_stage2(data, output):
    rows = [r for r in data.get("trials", []) if r.get("stage") == 2 and r.get("scenario") == "crossing"]
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), squeeze=False)
    statuses = (("CORRECT", "Correct", "#39856b"), ("WRONG_PHYSICAL_ACTOR", "Wrong actor", "#bd5148"),
                ("NOT_OBSERVED", "Not observed", "#d39a44"), ("UNKNOWN", "Unknown geometry/task", "#a0a8b2"))
    for category, ax in zip(("person", "car"), axes.flat):
        group = sorted((r for r in rows if r["target_class"] == category), key=lambda r: r["seed"])
        left = np.zeros(len(group))
        for key, label, color in statuses:
            fractions = []
            for row in group:
                report = row.get("selected_physical_identity_all") or {}
                counts = report.get("counts", {})
                denominator = sum(counts.values())
                value = sum(value for name, value in counts.items() if name.startswith("UNKNOWN")) if key == "UNKNOWN" else counts.get(key, 0)
                fractions.append(value / denominator if denominator else 0)
            ax.barh(np.arange(len(group)), fractions, left=left, label=label, color=color)
            left += fractions
        labels = []
        for index, row in enumerate(group):
            total = sum((row.get("selected_physical_identity_all") or {}).get("counts", {}).values())
            labels.append(f"seed {row['seed']:02d} | {row['result']} | opportunities={total}")
            if not total: ax.text(.03, index, "No physical-identity evidence", va="center", fontsize=8, color="#6a737e")
        ax.set_yticks(np.arange(len(group)), labels, fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_title(category)
        ax.set_xlabel("Fraction of ALL selected-task opportunities")
        ax.grid(axis="x", alpha=.2)
    if rows: axes.flat[0].legend(ncol=4, loc="upper center", bbox_to_anchor=(.5, 1.3), fontsize=9)
    fig.suptitle("Stage 2 crossings: independent requested physical identity; occluded/ambiguous intervals stay unknown", fontsize=12)
    footer(fig, "A stable target UUID is not identity evidence. Zero observed wrong matches does not certify unknown intervals. Geometric MOT diagnostics are separate from visible-object claims.")
    fig.tight_layout(rect=(0, .04, 1, .94))
    return save(fig, output, "stage2_physical_identity")


def plot_stage3(data, output):
    rows = comparisons(data)
    fields = ("detected_center_normalized_error_rmse", "true_image_horizon_error_rad_rmse", "online_state_anchor_position_rmse_m", "online_state_coverage")
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.5))
    for ax, field in zip(axes.flat, fields):
        selected = [r for r in rows if r["stage"] == 3 and r["metric"] == field and r["condition"] == "all_measurable_recorded_pairs"]
        for index, row in enumerate(selected): interval_row(ax, row, index, METHOD_COLORS[2])
        ax.set_yticks(np.arange(len(selected)), [r["comparison"].replace("_active_minus_midpoint", "") for r in selected])
        ax.axvline(0, color="#8a949f", ls="--")
        ax.set_xlabel("Active minus midpoint:\n" + UNITS[field], fontsize=9)
        ax.grid(axis="x", alpha=.2)
        if not selected: ax.text(.5, .5, "No recorded paired evidence", transform=ax.transAxes, ha="center")
        ax.margins(x=.5)
        ax.set_ylim(-.6, max(.6, len(selected)-.4))
    fig.suptitle("Stage 3: paired bootstrap 95% intervals of real seed pairs; 10,000 whole-seed resamples", fontsize=12)
    footer(fig, "Image-center error conditions on observed detections and must be read with sample counts/coverage. Failures remain in measurable pairs; both-PASS intervals are exported separately.")
    fig.tight_layout(rect=(0, .05, 1, .94))
    return save(fig, output, "stage3_paired_intervals")


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def plot_follow_transients(data, output):
    """Make nonsettling/missing flights visible beside observed time values."""
    groups = data.get("follow_dynamics_statistics", {})
    keys = sorted(groups)
    fig, axes = plt.subplots(1, 2, figsize=(16, max(5, .42 * len(keys) + 2)))
    categories = (("observed_settled", "Observed settled", "#39856b"),
                  ("right_censored", "Not settled in observed window", "#d39a44"),
                  ("missing_window", "Missing window", "#dce1e7"))
    for axis, ax in zip(("distance", "height"), axes):
        left = np.zeros(len(keys))
        for field, label, color in categories:
            values = np.array([groups[key].get(f"initial_{axis}_settling", {}).get(field, 0) for key in keys])
            ax.barh(np.arange(len(keys)), values, left=left, label=label, color=color)
            for index, value in enumerate(values):
                if value: ax.text(left[index] + value / 2, index, str(int(value)), ha="center", va="center", fontsize=8)
            left += values
        ax.set_yticks(np.arange(len(keys)), keys, fontsize=8)
        ax.set_xlabel("Recorded whole-flight units")
        ax.set_title(f"Initial {axis} transient: settling evidence")
        ax.grid(axis="x", alpha=.2)
        if not keys: ax.text(.5, .5, "No recorded transient windows", transform=ax.transAxes, ha="center")
    axes[0].legend(loc="upper center", bbox_to_anchor=(1, -.12), ncol=3, fontsize=9)
    footer(fig, "Missing/unsettled times are not zero. Conditional observed settling times and whole-flight status are in CSV. Moving-target task transient, not a stationary step response.")
    fig.tight_layout(rect=(0, .12, 1, .96))
    return save(fig, output, "follow_transient_evidence")


def render(summary_path, output):
    raw = summary_path.read_bytes()
    data = json.loads(raw)
    if data.get("planned_flights") != 166:
        raise ValueError("Expected the explicit 166-slot full-plan summary; do not mix an engineering probe or replay report")
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = output / f"source_summary_{digest[:16]}.json"
    snapshot.write_bytes(raw)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    figures = []
    for plotter in (plot_progress, plot_stage1, plot_stage1_pairs, plot_stage2, plot_stage3, plot_follow_transients):
        figures.extend(plotter(data, output))
    fields = ("name", "stage", "target_class", "scenario", "command_mode", "estimator_method", "gimbal_mode", "seed", "result",
              "real_time_factor", "inference_image_size", "inference_threads",
              "horizontal_rmse_m", "height_rmse_m", "online_state_anchor_position_rmse_m", "online_state_coverage", "online_state_reference_coverage",
              "command_jitter_rms_mps2", "detected_center_normalized_error_rmse", "detected_center_normalized_error_observed_samples",
              "true_image_horizon_error_rad_rmse", "true_image_horizon_error_rad_observed_samples", "physical_identity_status", "selected_physical_identity_all",
              "all_detection_opportunities", "geometric_unoccluded_opportunities", "task_count",
              "mean_task_amodal_hota", "mean_task_amodal_idf1", "mean_task_amodal_id_switches",
              "mean_task_unoccluded_geometry_hota", "mean_task_unoccluded_geometry_idf1", "mean_task_unoccluded_geometry_id_switches",
              "follow_dynamics_status", "initial_distance_opposite_side_overshoot_m", "initial_distance_settling_time_s",
              "initial_distance_settling_right_censored", "initial_distance_truth_coverage", "initial_distance_observed_interval_s",
              "initial_height_opposite_side_overshoot_m", "initial_height_settling_time_s", "initial_height_settling_right_censored",
              "initial_height_truth_coverage", "initial_height_observed_interval_s", "explicit_selection_windows",
              "explicit_selection_confirmed", "explicit_selection_confirmation_censored", "explicit_selection_mean_confirmation_latency_s",
              "follow_visual_report_available", "follow_visual_detection_opportunities", "follow_visual_center_observed_samples",
              "follow_visual_observed_center_coverage", "follow_visual_source_images_with_first_tracking_command")
    fields += tuple(f"follow_visual_{metric}_{statistic}"
                    for metric in ("detected_center_error_px", "detected_center_normalized_error", "image_to_first_tracking_command_sim_s")
                    for statistic in ("count", "mean", "rmse", "p95"))
    write_csv(output / "flight_units.csv", data.get("trials", []), fields)
    write_csv(output / "paired_intervals.csv", comparisons(data), ("stage", "comparison", "metric", "condition", "pairs", "excluded_pairs", "mean_difference", "ci95", "resamples", "seed", "method"))
    dynamics = [{"group": key, **value} for key, value in sorted(data.get("follow_dynamics_statistics", {}).items())]
    write_csv(output / "follow_transient_groups.csv", dynamics,
              ("group", "flight_units", "dynamics_recorded", "flight_failure_rate", "initial_distance_settling",
               "initial_height_settling", "initial_distance_opposite_side_overshoot_m", "initial_height_opposite_side_overshoot_m",
               "initial_distance_truth_coverage", "initial_height_truth_coverage", "explicit_selection_windows",
               "explicit_selection_confirmation_censored", "flight_mean_observed_confirmation_latency_s", "visual_control_statistics", "claim_boundary"))
    artifacts = [*figures, output / "flight_units.csv", output / "paired_intervals.csv", output / "follow_transient_groups.csv", snapshot]
    manifest = {
        "schema_version": 1, "source_summary": str(summary_path.resolve()), "source_summary_sha256": digest,
        "source_plan_sha256": data.get("plan_sha256"), "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "planned_flights": data["planned_flights"], "attempted_flights": data.get("recorded_or_attempted_flights"),
        "status_counts": data.get("status_counts"), "all_flights_pass": data.get("all_flights_pass"),
        "all_offline_slots_attempted": data.get("all_offline_slots_attempted"),
        "artifacts_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts},
        "claim_boundary": "Figures consume only recorded full-plan summary JSON. Pending, failed, missing and unknown evidence stays explicit. Online state uses the frozen visible-surface anchor, not model-center accuracy or ideal-ego replay. Paired units are real whole-flight seed pairs. No bag reads, inference, simulation, GT-assisted control, ReID or wall-time real-time claim.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "results/full_plan_research_v1/summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/full_plan_figures")
    args = parser.parse_args()
    print(json.dumps(render(args.summary, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
