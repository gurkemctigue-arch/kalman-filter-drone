"""Export standalone scientific figures from archived JSON summaries only.

No bags, inference or simulation are opened. Missing/pending values stay
missing; failed measurements and every planned slot remain visible.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

import summarize_stage23_matrix as statistics

ROOT = Path(__file__).resolve().parents[1]
MODE_COLORS = {"midpoint": "#4477AA", "active": "#228833"}
OUTCOME_COLORS = {"PASS": "#228833", "FAIL": "#CC3311", "INTERRUPTED": "#EE7733",
                  "PENDING": "#CCCCCC", "RUNNING_FLIGHT": "#66CCEE", "RUNNING_EVALUATION": "#66CCEE",
                  "UNVERIFIED_PASS": "#AA4499"}
IDENTITY_KEYS = ("CORRECT", "WRONG_PHYSICAL_ACTOR", "NOT_OBSERVED", "UNKNOWN_GEOMETRY", "UNKNOWN_TASK_INITIAL_ID")


def read_input(path: Path, kind: str, provenance: list[dict]) -> dict | None:
    record = {"kind": kind, "path": str(path.resolve()), "sha256": None, "error": None}
    provenance.append(record)
    try:
        raw = path.read_bytes()
        record["sha256"] = hashlib.sha256(raw).hexdigest()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value
    except (OSError, UnicodeError, ValueError) as error:
        record["error"] = str(error)
        return None


def identity_bar_data(report: dict | None, label: str) -> dict[str, Any]:
    """Partition all task opportunities, never just known/visible frames."""
    result = {"label": label, "available": False, "denominator": None, "counts": None,
              "fractions": None, "evaluation_status": report.get("evaluation_status") if report else "MISSING_REPORT",
              "safety_result": None, "reason": None}
    if report is None:
        result["reason"] = "Missing or unreadable physical-identity report"
        return result
    summary = report.get("selected_physical_identity_all")
    if not isinstance(summary, dict):
        result["reason"] = report.get("reason", "INCOMPLETE_EVIDENCE: full-task identity summary unavailable")
        return result
    total, counts = summary.get("frames"), summary.get("counts")
    if (type(total) is not int or total <= 0 or not isinstance(counts, dict)
            or any(type(counts.get(key)) is not int or counts[key] < 0 for key in IDENTITY_KEYS)):
        result["reason"] = "No positive complete task-opportunity denominator"
        return result
    if sum(counts[key] for key in IDENTITY_KEYS) != total:
        result["reason"] = "Identity categories do not partition the full task-opportunity denominator"
        return result
    grouped = {"correct": counts["CORRECT"], "wrong": counts["WRONG_PHYSICAL_ACTOR"],
               "unknown": counts["UNKNOWN_GEOMETRY"] + counts["UNKNOWN_TASK_INITIAL_ID"],
               "no_fresh": counts["NOT_OBSERVED"]}
    result.update(available=True, denominator=total, counts=grouped,
                  fractions={key: value/total for key, value in grouped.items()},
                  safety_result=summary.get("safety_result"))
    return result


def pair_plot_data(report: dict) -> list[dict[str, Any]]:
    trials = {row["trial"]["id"]: row for row in report.get("trial_measurements", [])}
    rows = []
    for pair in report.get("seed_pairs", []):
        modes = {trials[name]["trial"]["gimbal_mode"]: trials[name] for name in pair.get("slot_ids", []) if name in trials}
        for metric in ("image_center_rmse", "horizon_rmse_rad"):
            values = pair.get("differences", {}).get(metric, {})
            for mode in ("midpoint", "active"):
                trial = modes.get(mode)
                value = statistics.finite_value(values.get(mode))
                rows.append({"pair_id": pair.get("pair_id"), "target_class": pair["target_class"],
                             "seed": pair["seed"], "metric": metric, "mode": mode, "value": value,
                             "compatible": pair.get("compatible", False),
                             "verified_pass": bool(trial and trial.get("verified_pass")),
                             "slot_status": trial["slot_status"] if trial else "MISSING_SLOT",
                             "issues": pair.get("issues", [])})
    return rows


def _save(fig, output: Path, stem: str) -> list[str]:
    paths = []
    for extension in ("png", "pdf"):
        path = output / f"{stem}.{extension}"
        fig.savefig(path, dpi=220, bbox_inches="tight")
        paths.append(str(path))
    plt.close(fig)
    return paths


def plot_pairs(rows: list[dict], output: Path, *, stem="paired_seed_rmse",
               title="Stage 3: paired per-seed recorded RMSE") -> list[str]:
    fig, axes = plt.subplots(2, 2, figsize=(12., 7.7), squeeze=False)
    for class_index, category in enumerate(("person", "car")):
        for metric_index, (metric, label) in enumerate((("image_center_rmse", "Image-centre RMSE (normalized)"),
                                                       ("horizon_rmse_rad", "True horizon RMSE (rad)"))):
            ax = axes[class_index, metric_index]
            selected = [row for row in rows if row["target_class"] == category and row["metric"] == metric]
            seeds = sorted({row["seed"] for row in selected})
            for seed in seeds:
                pair = {row["mode"]: row for row in selected if row["seed"] == seed}
                if (len(pair) == 2 and all(row["value"] is not None and row["compatible"] for row in pair.values())):
                    ax.plot([seed-.13, seed+.13], [pair["midpoint"]["value"], pair["active"]["value"]],
                            color="#999999", linewidth=.8, zorder=1)
            for row in selected:
                position = row["seed"] + (-.13 if row["mode"] == "midpoint" else .13)
                if row["value"] is None:
                    status = row["slot_status"]
                    text = "P" if status == "PENDING" else ("R" if status.startswith("RUNNING") else "!")
                    ax.text(position, -.14 if row["mode"] == "midpoint" else -.23, text,
                            color="#888888" if status == "PENDING" else "#CC3311",
                            ha="center", va="top", transform=ax.get_xaxis_transform(), fontsize=7)
                    continue
                ax.scatter([position], [row["value"]], s=35, color=MODE_COLORS[row["mode"]], zorder=3)
                if not row["verified_pass"]:
                    ax.scatter([position], [row["value"]], s=55, marker="x", color="#CC3311", linewidths=1.2, zorder=4)
                if not row["compatible"]:
                    ax.scatter([position], [row["value"]], s=90, marker="D", facecolors="none", edgecolors="#EEAA33", linewidths=1., zorder=5)
            measured_pairs = sum(all(row["value"] is not None for row in selected if row["seed"] == seed)
                                 and len([row for row in selected if row["seed"] == seed]) == 2 for seed in seeds)
            ax.set_title(f"{category}: {measured_pairs}/{len(seeds)} observed pairs", fontsize=10)
            ax.set_ylabel(label)
            ax.set_xlabel("Pre-registered seed", labelpad=38)
            ax.set_xticks(seeds)
            ax.set_xlim(min(seeds)-.7 if seeds else -.7, max(seeds)+.7 if seeds else 1.)
            ax.grid(axis="y", alpha=.22)
            if not any(row["value"] is not None for row in selected):
                ax.text(.5, .55, "PENDING: no recorded paired measurements", transform=ax.transAxes,
                        ha="center", va="center", fontsize=9, color="#666666")
                ax.set_yticks([])
    fig.suptitle(title, fontsize=13, y=.995)
    handles = [Line2D([], [], marker="o", linestyle="", color=color, label=mode) for mode, color in MODE_COLORS.items()]
    handles.extend([Line2D([], [], marker="x", linestyle="", color="#CC3311", label="failed / unverified full-flight evidence"),
                    Line2D([], [], marker="D", linestyle="", markerfacecolor="none", color="#EEAA33", label="protocol mismatch; no paired link")])
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .965), ncol=2, frameon=False, fontsize=8)
    fig.text(.5, .01, "Missing measurements are status letters below the axis, never zero errors. P: pending; R: running; !: unavailable/failed.",
             ha="center", fontsize=8)
    fig.subplots_adjust(top=.84, bottom=.19, hspace=1.1, wspace=.25)
    return _save(fig, output, stem)


def plot_identity(rows: list[dict], output: Path) -> list[str]:
    count = max(len(rows), 1)
    fig, ax = plt.subplots(figsize=(12., max(3.5, .55*count+2.)))
    colors = {"correct": "#228833", "wrong": "#CC6677", "unknown": "#EEAA33", "no_fresh": "#66CCEE"}
    for index, row in enumerate(rows):
        if not row["available"]:
            ax.barh(index, 1., color="#F1F1F1", hatch="///", edgecolor="#BBBBBB", height=.65)
            ax.text(.02, index, row["evaluation_status"] or "INCOMPLETE_EVIDENCE", va="center", fontsize=8)
            continue
        left = 0.
        for key, color in colors.items():
            fraction = row["fractions"][key]
            ax.barh(index, fraction, left=left, color=color, edgecolor="white", height=.65)
            if fraction >= .06:
                ax.text(left+fraction/2, index, f"{fraction:.0%}", ha="center", va="center", fontsize=8)
            left += fraction
        ax.text(1.01, index, f"n={row['denominator']}", va="center", fontsize=8)
    labels = [row["label"] if len(row["label"]) <= 52 else row["label"][:49]+"..." for row in rows]
    ax.set_yticks(list(range(len(rows))), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.13)
    ax.set_xticks([0, .25, .5, .75, 1.], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Fraction of ALL explicit-task opportunities (unknown and no-fresh frames retained)")
    ax.set_title("Physical identity evidence: all supplied trials, including incomplete histories", pad=38)
    ax.legend(handles=[Patch(facecolor=color, label=label) for (key, color), label in zip(colors.items(),
              ("correct", "wrong physical actor", "unknown geometry / initial actor", "no fresh selected detection"))],
              loc="upper center", bbox_to_anchor=(.45, 1.12), ncol=2, frameon=False, fontsize=8)
    if not rows:
        ax.text(.5, .5, "PENDING: no physical-identity summaries supplied", transform=ax.transAxes, ha="center", color="#666666")
        ax.set_yticks([])
    fig.text(.5, .015, "Unknown is not certified correct. Hatched rows have no valid denominator; they are not 0% error or 100% unknown.",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=.37, right=.93, top=.78, bottom=.2)
    return _save(fig, output, "physical_identity_opportunities")


def plot_outcomes(report: dict, output: Path) -> list[str]:
    rows = report.get("trial_measurements", [])
    groups = sorted({f"S{row['trial']['stage']} {row['trial']['target_class']} "
                     + (row["trial"]["gimbal_mode"] if row["trial"]["stage"] == 3 else row["trial"]["scenario"]) for row in rows})
    fig, ax = plt.subplots(figsize=(11., max(4., .4*len(groups)+2.)))
    for row in rows:
        trial = row["trial"]
        group = f"S{trial['stage']} {trial['target_class']} " + (trial["gimbal_mode"] if trial["stage"] == 3 else trial["scenario"])
        status = "UNVERIFIED_PASS" if row["slot_status"] == "PASS" and not row["verified_pass"] else row["slot_status"]
        ax.scatter(trial["seed"], groups.index(group), color=OUTCOME_COLORS.get(status, "#777777"), marker="s", s=160,
                   edgecolors="white", linewidths=.8)
        if status in {"FAIL", "INTERRUPTED", "UNVERIFIED_PASS"}:
            ax.text(trial["seed"], groups.index(group), "!", ha="center", va="center", color="white", fontsize=9, weight="bold")
    ax.set_yticks(list(range(len(groups))), groups)
    ax.invert_yaxis()
    ax.set_xticks(sorted({row["trial"]["seed"] for row in rows}))
    ax.set_xlabel("Pre-registered seed")
    ax.set_title(f"Planned-slot outcome ledger: all {len(rows)} slots retained", pad=35)
    ax.grid(axis="x", alpha=.15)
    keys = ("PASS", "FAIL", "INTERRUPTED", "PENDING", "RUNNING_FLIGHT", "UNVERIFIED_PASS")
    ax.legend(handles=[Line2D([], [], linestyle="", marker="s", color=OUTCOME_COLORS[key],
                             label="RUNNING" if key == "RUNNING_FLIGHT" else key) for key in keys],
              loc="upper center", bbox_to_anchor=(.45, 1.13), ncol=3, frameon=False, fontsize=8)
    if not rows:
        ax.text(.5, .5, "PENDING: no planned matrix supplied", transform=ax.transAxes, ha="center", color="#666666")
    fig.text(.5, .015, "This is a ledger by planned seed, not a fabricated chronological flight timeline. Failed/interrupted slots are never removed.",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=.26, right=.95, top=.79, bottom=.17)
    return _save(fig, output, "planned_outcome_ledger")


def save_data(data: dict, output: Path) -> None:
    (output / "plot_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    rows = data["paired_seed_points"]
    with (output / "paired_seed_points.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["pair_id", "target_class", "seed", "metric", "mode", "value", "compatible", "verified_pass", "slot_status"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--manifest", type=Path)
    sources.add_argument("--statistics", type=Path)
    parser.add_argument("--physical-json", type=Path, nargs="*", default=[])
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False})
    provenance = []
    report = {"seed_pairs": [], "trial_measurements": [], "outcomes": {}}
    if args.manifest:
        manifest = read_input(args.manifest, "matrix_manifest", provenance)
        if manifest:
            report = statistics.build_report(manifest, args.project_root)
    elif args.statistics:
        loaded = read_input(args.statistics, "paired_statistics", provenance)
        if loaded:
            if loaded.get("source") != "OFFLINE_STAGE23_PLANNED_SEED_PAIR_SUMMARY":
                parser.error("statistics JSON is not a supported stage23 summary")
            report = loaded
    identity = []
    for path in args.physical_json:
        document = read_input(path, "physical_identity", provenance)
        label = path.parent.name
        if document and document.get("source_trial"):
            label = str(document["source_trial"]).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        identity.append(identity_bar_data(document, label))
    paired = pair_plot_data(report)
    outputs = plot_pairs(paired, args.output) + plot_identity(identity, args.output) + plot_outcomes(report, args.output)
    source = Path(__file__)
    data = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_script": {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            "software": {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "numpy": np.__version__},
            "input_provenance": provenance, "source_report_provenance": [
                {"trial_id": row["trial"]["id"], "reports": row.get("report_provenance", {}), "errors": row.get("report_errors", [])}
                for row in report.get("trial_measurements", [])],
            "plan_sha256": report.get("plan_sha256"), "paired_seed_points": paired,
            "physical_identity": identity, "all_planned_outcomes": report.get("outcomes", {}),
            "failure_history": [{"trial": row["trial"], "status": row["slot_status"], "report_errors": row.get("report_errors", [])}
                                for row in report.get("trial_measurements", []) if row["slot_status"] in {"FAIL", "INTERRUPTED"}
                                or row["slot_status"] == "PASS" and not row["verified_pass"]],
            "figures": outputs,
            "protocol": "Registered pair points only; absent measurements stay null. Identity percentages use every explicit-task opportunity. Unknown/no-fresh are separate from correct. Pending/failed histories remain visible."}
    save_data(data, args.output)
    print(json.dumps({"figures": outputs, "physical_reports": len(identity), "planned_pairs": len(report.get("seed_pairs", []))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
