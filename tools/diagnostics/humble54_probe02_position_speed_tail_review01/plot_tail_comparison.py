"""Plot the closed probe02 distance-error sidecars without ROS or bag access.

Run from any directory, using a fresh output directory for every rerun:
    python -B plot_tail_comparison.py --output-dir artifacts_rerun01
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
EVIDENCE_SHA256 = "e9e3c2ad60ca5a4117b964921f67084aa1a8a5d9635c60167b262a43f20febe0"
SIDECAR_SHA256 = {
    "position": "33866893a65779b6bbc2105d2dcda51905ba659345926480609f5e83d4520fa5",
    "velocity": "b94152e657d20e96df4673e351e9bdc18628160a6415ee30fd76dcbf48fbd758",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, expected):
    before = path.stat()
    if not path.is_file() or path.is_symlink() or before.st_size > 2 * 1024 * 1024:
        raise ValueError("An ordinary small input file is required")
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Input changed during reading")
    if digest(raw) != expected:
        raise ValueError("Pinned input differs: " + str(path))
    return raw, {"path": str(path), "sha256": expected, "bytes": len(raw)}


def duration_bar(ax, start, stop, y, label, color):
    ax.annotate("", xy=(stop, y), xytext=(start, y),
                arrowprops={"arrowstyle": "|-|", "color": color, "lw": 1.2})
    ax.text((start + stop) / 2, y + 0.025, label, ha="center", va="bottom",
            fontsize=8.5, color=color,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": .9, "pad": 1.2})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "artifacts")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError("Use a fresh output directory; existing artifacts are preserved")
    started = datetime.now(timezone.utc).isoformat()
    evidence_raw, evidence_binding = read_pinned(HERE / "actual_sidecar_evidence.json", EVIDENCE_SHA256)
    evidence = json.loads(evidence_raw)
    inputs = [evidence_binding]
    sources = {}
    for mode, pin in SIDECAR_SHA256.items():
        path = HERE / "inputs" / (mode + ".navigation_reference_evaluation.frames.jsonl")
        raw, binding = read_pinned(path, pin)
        inputs.append(binding)
        rows = [json.loads(line) for line in raw.splitlines()]
        recorded = evidence["trials"][mode]
        if len(rows) != recorded["source_records"]:
            raise ValueError("Original sidecar record count differs")
        for item in recorded["tail_rows"]:
            if rows[item["source_line"] - 1] != item["row"]:
                raise ValueError("Publication evidence and sidecar rows differ")
        sources[mode] = rows

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.4), sharey=True)
    colors = {"position": "#2563eb", "velocity": "#b45309"}
    for ax, mode in zip(axes, ("position", "velocity")):
        recorded = evidence["trials"][mode]
        rows = [r for r in sources[mode] if r["time_s"] >= 86.]
        end = recorded["recorded_end_s"]
        color = colors[mode]
        ax.axhspan(-.5, .5, color="#16a34a", alpha=.045)
        ax.axhline(.5, color="#64748b", ls="--", lw=1., label="Distance band: +/- 0.5 m")
        ax.axhline(-.5, color="#64748b", ls="--", lw=1.)
        ax.axhline(0., color="#cbd5e1", lw=.7)
        ax.plot([r["time_s"] for r in rows], [r["base_link_distance_error_m"] for r in rows],
                color=color, marker="o", markersize=3., lw=1., label="Recorded 10 Hz evaluations")
        ax.axvline(end, color="#0f172a", ls=":", lw=1.1)
        ax.text(end - .025, .68, "Recorded end\n" + f"{end:.3f} s", ha="right", va="top",
                fontsize=8.5, color="#0f172a")
        ax.set_xlim(86., end + .1)
        ax.set_ylim(-.62, .72)
        ax.set_ylabel("Distance error (m)")
        ax.set_xticks(list(range(86, 93)))
        ax.grid(axis="x", color="#e2e8f0", lw=.6)
        ax.legend(loc="upper left", frameon=False, fontsize=8., handlelength=2.2)
        if mode == "position":
            suffix = recorded["final_inside_run"]["start_s"]
            previous = next(r for r in rows if abs(r["time_s"] - 90.052) < 1e-8)
            first = next(r for r in rows if abs(r["time_s"] - suffix) < 1e-8)
            ax.axvspan(previous["time_s"], suffix, color="#64748b", alpha=.15)
            ax.plot(suffix, first["base_link_distance_error_m"], marker="o", ms=7.,
                    mfc="white", mec="#15803d", mew=1.5, zorder=5)
            ax.annotate("First observed back in band: 90.152 s\nCrossing lies in [90.052, 90.152] s",
                        xy=(suffix, first["base_link_distance_error_m"]), xytext=(89.2, .055),
                        fontsize=8.5, ha="left", va="bottom", color="#334155",
                        arrowprops={"arrowstyle": "->", "color": "#64748b", "lw": .8},
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": .9, "pad": 2.})
            duration_bar(ax, end - 3., end, -.24, "Required final window: 3.000 s", "#475569")
            duration_bar(ax, suffix, end, -.43, "Actual final dwell: 2.320 s < 3.000 s", "#166534")
            ax.set_title("Position mode: late excursion leaves insufficient final dwell (original FAIL)",
                         loc="left", fontsize=11, fontweight="bold", color="#1e3a8a")
        else:
            duration_bar(ax, end - 3., end, -.24, "Required final 3.000 s maintained", "#475569")
            ax.text(86.12, -.43, "Continuous sampled in-band suffix starts at 58.100 s;\n"
                    "dwell through recorded end = 34.760 s.", fontsize=9., color="#166534", va="center")
            ax.set_title("Velocity mode: final distance band maintained (original PASS)",
                         loc="left", fontsize=11, fontweight="bold", color="#92400e")
    axes[-1].set_xlabel("Simulation time (s)")
    fig.suptitle("Probe02 person speed changes, seed 004: final distance behavior", fontsize=14, y=.985)
    fig.text(.085, .022,
             "10 Hz observations; lines only guide the eye. Crossing times are bounded by adjacent samples.\n"
             "Dwell uses the original evaluator's recorded-end convention (last-sample gaps: 0.020 / 0.060 s).\n"
             "Positive error means farther than the requested 5 m. Original thresholds and verdicts are unchanged.",
             fontsize=8.2, color="#475569", va="bottom")
    fig.subplots_adjust(left=.085, right=.975, top=.91, bottom=.16, hspace=.33)
    for item in inputs:
        read_pinned(Path(item["path"]), item["sha256"])
    output.mkdir(parents=True, exist_ok=False)
    png = output / "position_velocity_tail_distance.png"
    pdf = output / "position_velocity_tail_distance.pdf"
    fig.savefig(png, dpi=220, facecolor="white")
    fig.savefig(pdf, facecolor="white", metadata={"Title": "Probe02 final distance behavior", "Creator": "Closed sidecar diagnostics"})
    plt.close(fig)
    script_raw = Path(__file__).read_bytes()
    receipt = {
        "scope": "ACTUAL_WINDOWS_SMALL_SIDECAR_PLOT_ONLY_NOT_FLIGHT_OR_REEVALUATION",
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": 0, "python_executable": sys.executable, "python_version": platform.python_version(),
        "matplotlib_version": matplotlib.__version__, "argv": sys.argv,
        "script": {"path": str(Path(__file__).resolve()), "sha256": digest(script_raw)},
        "inputs": inputs,
        "outputs": [{"path": str(path), "bytes": path.stat().st_size,
                     "sha256": digest(path.read_bytes())} for path in (png, pdf)],
        "plot_window_start_s": 86., "preserved_original_verdicts": {"position": "FAIL", "velocity": "PASS"},
        "position_final_dwell_s": evidence["trials"]["position"]["final_inside_dwell_to_recorded_end_s"],
        "required_dwell_s": 3., "wsl_ros_bag_telemetry": "NOT_USED",
    }
    receipt_path = output / "plot_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "receipt": str(receipt_path), "outputs": receipt["outputs"]}))


if __name__ == "__main__":
    main()
