"""Plot the closed probe02 combined diagnostic from verified small sidecars."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    evidence_path = folder / "sidecar_evidence02.json"
    evidence = json.loads(evidence_path.read_bytes())
    png = folder / "combined_failure_timeline02.png"
    pdf = folder / "combined_failure_timeline02.pdf"
    receipt = folder / "plot_receipt02.json"
    if any(p.exists() for p in (png, pdf, receipt)):
        raise FileExistsError("Preserve existing actual plots")
    data = {}
    for relative, binding in evidence["source_bindings"].items():
        path = root / relative
        if path.name in ("navigation_reference_evaluation.frames.jsonl",
                          "navigation_reference_evaluation.raw_frames.jsonl",
                          "navigation_reference_evaluation.message_frames.jsonl"):
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == binding["sha256"]
            data[path.name] = [json.loads(line) for line in raw.splitlines()]
    frames = data["navigation_reference_evaluation.frames.jsonl"]
    references = data["navigation_reference_evaluation.raw_frames.jsonl"]
    messages = data["navigation_reference_evaluation.message_frames.jsonl"]
    first_loss = evidence["first_lost_navigation_message"]["received_sim_s"]
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 8.6), constrained_layout=True)
    fig.suptitle("Probe02 person / combined faults: original engineering FAIL retained", fontsize=13)
    ax = axes[0]
    ax.plot([r["time_s"] for r in frames], [r["base_link_distance_error_m"] for r in frames],
            color="#175a91", linewidth=1.5, label="Base-link distance error (all evaluation samples)")
    ax.axhspan(-0.5, 0.5, color="#e0efe3", label="Original distance band: +/-0.5 m")
    ax.axvline(first_loss, color="#b13b36", linestyle="--", label="First navigation LOST in FOLLOW: 34.86 s")
    ax.axvspan(42.8, 45.88, color="#9e9e9e", alpha=0.25, label="Requested long shutter: 42.8-45.88 s")
    ax.set(xlabel="Evaluation simulation time (s)", ylabel="Distance error (m)")
    ax.legend(fontsize=8, loc="upper right")
    ax = axes[1]
    local = [r for r in references if 33.8 <= r["time_s"] <= 35.2]
    for accepted, color, marker, label in ((True, "#286f45", "o", "Accepted reference"),
                                           (False, "#b13b36", "x", "Invalid reference")):
        selected = [r for r in local if r["fusion_accepted"] is accepted]
        ax.scatter([r["time_s"] for r in selected],
                   [r["received_sim_s"] - r["time_s"] for r in selected],
                   color=color, marker=marker, label=label)
    ax.axvspan(34.2, 34.8, color="#dcbb61", alpha=0.25,
               label="Expected DROP windows (rule only; raw delivery not verified)")
    ax.text(34.15, 0.178, "Last accepted: source 34.10 / sidecar operational 34.224\n"
            "Next reference: source 34.80 / sidecar operational 34.904", fontsize=8, va="top")
    ax.set(xlim=(33.75, 35.25), ylim=(0.07, 0.19), xlabel="Reference source simulation time (s)",
           ylabel="Sidecar operational - source (s)")
    ax.legend(fontsize=8, loc="lower right")
    ax = axes[2]
    local_messages = [r for r in messages if 34.75 <= r["received_sim_s"] <= 34.94]
    ax.scatter([r["received_sim_s"] for r in local_messages],
               [1 if r["reason"] == "valid" else 0 for r in local_messages], color="#175a91", zorder=3)
    ax.axvline(34.85, color="#a17a16", linestyle=":", label="Last accepted source + original 0.75 s limit: 34.85")
    ax.axvline(first_loss, color="#b13b36", linestyle="--", label="First recorded LOST: 34.86")
    ax.set(xlim=(34.75, 34.94), ylim=(-0.3, 1.3), yticks=[0, 1], yticklabels=["LOST", "valid"],
           xlabel="Navigation message sidecar operational simulation time (s)", ylabel="Navigation status")
    ax.legend(fontsize=8, loc="center left")
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.supxlabel("Existing evaluator sidecars only. Simulation-time differences are not physical wall-clock end-to-end latency.", fontsize=9)
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    receipt.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "plot_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "artifacts": {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                      for p in (png, pdf)},
        "scope": "VISUALIZATION_OF_EXISTING_SMALL_SIDECARS_ONLY_ORIGINAL_FAIL_RETAINED"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ACTUAL_PLOTS_WRITTEN", "artifacts": [png.name, pdf.name]}))


if __name__ == "__main__":
    main()
