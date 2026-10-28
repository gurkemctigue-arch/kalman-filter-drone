#!/usr/bin/env python3
"""Create compact visual summaries from the archived stage-one telemetry."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TRIALS = (
    "stage1_final_v2_person_velocity",
    "stage1_final_v2_car_velocity",
    "stage1_final_v2_person_position",
    "stage1_final_v2_car_position",
)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def event_lines(rows: list[dict]) -> list[tuple[float, str, str]]:
    events = []
    for row in rows:
        if row.get("kind") == "shutter":
            label = "occlusion start" if row.get("active") else "occlusion end"
            events.append((float(row["time_s"]), label, "#c0392b"))
        elif row.get("kind") == "explicit_reselection_confirmed":
            events.append((float(row["time_s"]), "reselection confirmed", "#8e44ad"))
    return events


def plot_trial(trial_dir: Path, output_dir: Path) -> Path:
    rows = read_jsonl(trial_dir / "telemetry.jsonl")
    telemetry = [r for r in rows if r.get("kind") == "telemetry" and r.get("position")]
    observations = [r for r in rows if r.get("kind") == "observation"]
    phases = [r for r in rows if r.get("kind") == "phase"]
    if not telemetry:
        raise RuntimeError(f"no telemetry rows in {trial_dir}")

    t = [float(r["time_s"]) for r in telemetry]
    x = [float(r["position"][0]) for r in telemetry]
    y = [float(r["position"][1]) for r in telemetry]
    speed = [math.sqrt(sum(float(v) ** 2 for v in r.get("velocity", []))) for r in telemetry]
    ot = [float(r["time_s"]) for r in observations]
    depth = [float(r["depth_m"]) if r.get("depth_m") is not None else math.nan for r in observations]
    detector_frames = [r for r in rows if r.get("kind") == "detection"]
    frame_t = [float(r.get("stamp_s", r["time_s"])) for r in detector_frames]
    frame_valid = [float(any(d.get("depth_valid", False) for d in r.get("detections", [])))
                   for r in detector_frames]
    events = event_lines(rows)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    title = trial_dir.name.replace("stage1_final_v2_", "").replace("_", " / ")
    fig.suptitle(f"Stage 1 visual acceptance summary: {title}", fontsize=14)

    ax = axes[0, 0]
    ax.plot(x, y, color="#2471a3", linewidth=1.5)
    ax.scatter([x[0]], [y[0]], color="#27ae60", label="start", zorder=3)
    ax.scatter([x[-1]], [y[-1]], color="#c0392b", label="end", zorder=3)
    ax.set_title("Vehicle horizontal path")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")

    ax = axes[0, 1]
    ax.plot(t, speed, color="#2471a3", linewidth=1.2)
    ax.set_title("Vehicle speed")
    ax.set_xlabel("simulation time (s)")
    ax.set_ylabel("speed (m/s)")
    ax.grid(alpha=0.25)

    ax = axes[1, 0]
    # Missing observations are gaps, not interpolated depth measurements.
    ax.scatter(ot, depth, color="#148f77", s=5, label="received candidate depth")
    ax2 = ax.twinx()
    if detector_frames:
        ax2.scatter(frame_t, frame_valid, color="#7d3c98", alpha=0.4, s=6,
                    label="completed frame has valid depth candidate")
    ax.set_title("RGB-D samples (gaps are not interpolated)")
    ax.set_xlabel("simulation time (s)")
    ax.set_ylabel("depth (m)")
    ax2.set_ylabel("frame has valid candidate (0/1)")
    ax2.set_ylim(-0.05, 1.05)
    ax.grid(alpha=0.25)

    ax = axes[1, 1]
    ax.set_title("Phase and shutter timeline")
    ax.set_xlabel("simulation time (s)")
    ax.set_yticks([])
    ax.set_ylim(0, 1)
    for index, phase in enumerate(phases):
        when = float(phase["time_s"])
        ax.axvline(when, color="#7f8c8d", alpha=0.55, linewidth=0.8)
        ax.text(when, 0.92 - (index % 3) * 0.17, phase.get("phase", "phase"), rotation=90,
                va="top", ha="right", fontsize=8, color="#34495e")
    for when, label, color in events:
        ax.axvline(when, color=color, alpha=0.8, linewidth=1.2)
        ax.text(when, 0.08, label, rotation=90, va="bottom", ha="right", fontsize=8, color=color)
    ax.grid(axis="x", alpha=0.25)

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{trial_dir.name}.png"
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--output", type=Path, default=Path("results/stage1_visual_report"))
    args = parser.parse_args()
    outputs = []
    for name in TRIALS:
        outputs.append(plot_trial(args.results / name, args.output))
    print("\n".join(str(path) for path in outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
