"""Plot archived small input messages and original lifecycle events, no bags."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "early_loss_input_evidence01"


def main():
    paths = [EVIDENCE / "manifest.json", EVIDENCE / "actual_delivery_reconciliation.json",
             HERE / "early_loss_evidence.json"]
    raw = [p.read_bytes() for p in paths]
    assert hashlib.sha256(raw[0]).hexdigest() == "5344dbada5c9c5d12faaca3bdd98822972e2e1ea940e186069c1e6aeb2e61af2"
    manifest, reconciliation, original = [json.loads(data) for data in raw]
    assert reconciliation["status"] == "ACTUAL_RECORDED_DELIVERY_MATCHES_DETERMINISTIC_INJECTION"
    assert original["original_parameters_protection"]["max_prediction_duration_s"] == .75
    topics = ["/camera/color/image_raw", "/camera/aligned_depth_to_color/image_raw",
              "/research/camera/color/image_raw", "/research/camera/aligned_depth_to_color/image_raw",
              "/tracking/detection_diagnostics"]
    labels = ["Raw RGB · source key", "Raw depth · source key", "Research RGB · source key",
              "Research depth · source key", "Diagnostic · source key", "Detector output · recorded completion"]
    figure, axis = plt.subplots(figsize=(11.5, 5.8), layout="constrained")
    for index, topic in enumerate(topics):
        times = [row["acquisition_ns"] / 1e9 for row in manifest["opportunities"] if row["topic"] == topic]
        axis.scatter(times, [5-index] * len(times), s=46, color="#2166ac", zorder=3)
        if index >= 2:
            missing = [row["stamp_s"] for row in reconciliation["rows"] if row["expected_action"] == "DROP"]
            axis.scatter(missing, [5-index] * len(missing), s=43, marker="x", color="#b2182b", zorder=3)
    completed = [json.loads(row["original_diagnostic_json"])["completed_s"]
                 for row in manifest["opportunities"] if row["topic"] == topics[-1]]
    axis.scatter(completed, [0] * len(completed), marker="D", s=30, color="#1b7837", zorder=3)
    axis.axvspan(34.15, 34.75, color="#fddbc7", alpha=.45, zorder=0)
    axis.text(34.45, 5.6, "6 raw opportunities retained;\nresearch streams + diagnostics absent", ha="center", fontsize=10)
    last = original["observed_detection_boundary"]["last_before_gap"]
    returned = original["observed_detection_boundary"]["first_after_gap"]
    assert last["stamp_s"] == 34.1 and returned["stamp_s"] == 34.8
    expiry = last["stamp_s"] + .75
    axis.axvline(expiry, color="#b2182b", linestyle="--", linewidth=1.3)
    axis.annotate("0.75 s source-age deadline\n34.85 s (HOVER observed 34.852)",
                  xy=(expiry, 2.3), xytext=(35.02, 3.1), ha="left", fontsize=9,
                  arrowprops={"arrowstyle": "->", "color": "#b2182b"})
    axis.annotate("last output\n34.204 s", xy=(last["completed_s"], 0), xytext=(34.1, -.72),
                  ha="center", fontsize=9, arrowprops={"arrowstyle": "->"})
    axis.annotate("next output 34.904 s\nprevious source age = 0.804 s", xy=(returned["completed_s"], 0),
                  xytext=(35.05, -.72), ha="left", fontsize=9, arrowprops={"arrowstyle": "->"})
    axis.set_yticks([5, 4, 3, 2, 1, 0], labels)
    axis.set_xlim(33.74, 35.58)
    axis.set_ylim(-1.0, 6.4)
    axis.set_xticks([33.8, 34.0, 34.2, 34.4, 34.6, 34.8, 35.0, 35.2, 35.4])
    axis.grid(axis="x", alpha=.2)
    axis.set_xlabel("Original source clock (s); source-key markers do not represent callback receipt times")
    axis.set_title("Original combined-fault run: recorded input gap before first loss", loc="left", fontsize=13, weight="bold")
    figure.suptitle("15 raw RGB + 15 raw depth; 9 research pairs + 9 diagnostics · original FAIL retained", fontsize=10, y=1.02)
    output_paths = [HERE / "actual_input_gap.png", HERE / "actual_input_gap.pdf"]
    for path in output_paths:
        figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)
    receipt = {"scope": "DESCRIPTIVE_RECORDED_STREAM_PLOT_NOT_REEVALUATION_OR_SHORT_SHUTTER_ATTACHMENT",
               "created_utc": datetime.now(timezone.utc).isoformat(),
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "inputs": {str(p.relative_to(HERE)): hashlib.sha256(data).hexdigest() for p, data in zip(paths, raw)},
               "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output_paths},
               "limits": "Dots show source acquisition keys, diamonds recorded diagnostic completed_s. Missing research messages are only absence from the complete selected recorded stream. No reader clock is used as callback arrival. Events and original FAIL are unchanged."}
    (HERE / "actual_input_gap_plot_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PLOT_CREATED", "outputs": [p.name for p in output_paths]}))


if __name__ == "__main__":
    main()
