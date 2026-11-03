"""Describe the two original development runs without changing their verdicts."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil


PINS = {
    "velocity": "a152e62b340e4ebbc55613cad93a938f1cfe010ed9b4cd0bb4602e19e5a0855d",
    "position": "ec7e46918d6677b9359a63df5b40f898020e4fb0759fdd1ef98e834b81a31729",
}
PLAN_SHA = "f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    base = root / "results/frozen_fullplan_v4_humble54"
    matrix = base / "reliability_v4_humble54_extension16_probe01_matrix"
    plan_path = matrix / "plan.json"
    require(sha(plan_path) == PLAN_SHA, "Original plan changed")
    plan = json.loads(plan_path.read_bytes())
    results, inputs, curves = {}, [], {}
    copies = [(plan_path, "source_plan.json")]
    for mode, expected in PINS.items():
        slot = f"person_extension_speed_changes_{mode}_seed004"
        terminal_path = matrix / "slots" / (slot + ".json")
        require(sha(terminal_path) == expected, "Original terminal changed: " + slot)
        terminal = json.loads(terminal_path.read_bytes())
        require(terminal["plan_sha256"] == plan["plan_sha256"], "Wrong plan")
        require(terminal["execution_status"] == "COMPLETED" and
                terminal["infrastructure_stop"] is False and
                type(terminal["flight_exit_code"]) is int and
                terminal["flight_exit_code"] == 0, "Incomplete flight")
        trial = base / ("reliability_v4_humble54_extension16_probe01_" + slot)
        paths = {name: trial / name for name in
                 ("navigation_reference_evaluation.json",
                  "navigation_reference_evaluation.frames.jsonl")}
        for name, path in paths.items():
            require(sha(path) == terminal["artifact_hashes"][name], "Changed artifact")
        report = json.loads(paths["navigation_reference_evaluation.json"].read_bytes())
        rows = [json.loads(line) for line in
                paths["navigation_reference_evaluation.frames.jsonl"].read_text(encoding="utf8").splitlines()]
        whole = report["whole_interval"]
        require(len(rows) == whole["scheduled_samples"] == 752, "Incomplete denominator")
        require(whole["matched_truth_samples"] == len(rows), "Missing physical truth")
        rmse = math.sqrt(sum(row["base_link_distance_error_m"] ** 2 for row in rows) / len(rows))
        require(abs(rmse - whole["metrics"]["base_link_distance_error_m"]["rmse"]) < 1e-12,
                "Original RMSE not reproduced")
        transient = whole["transients"]["base_link"]["distance"]
        band = transient["band_m"]
        require(band == .5 and transient["minimum_in_band_duration_s"] == 3., "Different acceptance")
        end = report["interval"]["end_s"]
        outside = [row for row in rows if not row["active"] or
                   abs(row["base_link_distance_error_m"]) > band]
        suffix = rows[rows.index(outside[-1]) + 1:] if outside else rows
        require(suffix and all(row["active"] and abs(row["base_link_distance_error_m"]) <= band
                               for row in suffix), "Bad suffix")
        duration = end - suffix[0]["time_s"]
        settled = (duration >= 3. - 1e-8 and end - suffix[-1]["time_s"] <= .15 and
                   all(0 < b["time_s"] - a["time_s"] <= .15 for a, b in zip(suffix, suffix[1:])))
        require(settled == transient["settled_through_interval_end"], "Suffix verdict not reproduced")
        result = {"slot_id": slot, "original_status": terminal["status"],
                  "started_utc": terminal["started_utc"], "finished_utc": terminal["finished_utc"],
                  "original_engineering_evidence": terminal["engineering_evidence"],
                  "report_status": report["evaluation_status"], "full_samples": len(rows),
                  "distance_rmse_m": rmse,
                  "height_rmse_m": whole["metrics"]["base_link_height_error_m"]["rmse"],
                  "registered_distance_transient": transient,
                  "last_outside_or_inactive": outside[-1] if outside else None,
                  "final_inside_suffix_start_s": suffix[0]["time_s"],
                  "final_inside_suffix_samples": len(suffix),
                  "final_inside_suffix_duration_to_original_end_s": duration,
                  "original_end_s": end,
                  "relative_suffix_start_s": suffix[0]["time_s"] - report["interval"]["start_s"],
                  "reproduced_settled": settled,
                  "final_sample_distance_error_m": rows[-1]["base_link_distance_error_m"]}
        results[mode] = result
        curves[mode] = (report["interval"]["start_s"], rows)
        copies.append((terminal_path, mode + "_terminal.json"))
        copies.extend((path, mode + "_" + name) for name, path in paths.items())
    output = folder / "evidence01"
    require(not output.exists(), "Output exists; preserve previous attempt")
    output.mkdir()
    for path, name in copies:
        destination = output / name
        shutil.copyfile(path, destination)
        require(sha(path) == sha(destination), "Copy changed bytes")
        inputs.append({"original_path": path.relative_to(root).as_posix(),
                       "copy": name, "bytes": path.stat().st_size, "sha256": sha(path)})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family": font.get_name(), "axes.unicode_minus": False,
                         "font.size": 10, "pdf.fonttype": 42})
    fig, axes = plt.subplots(2, 1, figsize=(10, 6))
    for ax in axes:
        ax.axhspan(-.5, .5, color="#508d77", alpha=.10, label="原稳定带 ±0.5 m")
        ax.axhline(.5, color="#8b9991", linewidth=.8, linestyle="--")
        ax.axhline(-.5, color="#8b9991", linewidth=.8, linestyle="--")
        for mode, (start, rows) in curves.items():
            ax.plot([row["time_s"] - start for row in rows],
                    [row["base_link_distance_error_m"] for row in rows],
                    label="速度模式" if mode == "velocity" else "位置模式", linewidth=1.5)
        ax.grid(axis="y", alpha=.2)
        ax.set_ylabel("跟随距离误差 / m")
    axes[0].set_title("行人加减速：原始完整窗口与末端稳定性", loc="left")
    axes[0].legend(loc="upper right", frameon=False)
    axes[0].set_xlim(0, 75.2)
    axes[1].set_xlim(65, 75.2)
    axes[1].set_ylim(-.65, .85)
    axes[1].axvspan(72.136, 75.136, color="#cfb084", alpha=.14)
    axes[1].axvline(results["position"]["relative_suffix_start_s"], color="#a56b27", linestyle=":")
    axes[1].set_xlabel("自各自 FOLLOW 起点的时间 / s")
    fig.text(.02, .015, "同一开发种子下的两次独立飞行；末端要求连续 3 s。保留原 PASS/FAIL，不延长窗口或改变门限。", fontsize=9)
    fig.tight_layout(rect=(0, .045, 1, 1))
    outputs = []
    for suffix in ("png", "pdf"):
        path = output / ("distance_comparison." + suffix)
        fig.savefig(path, dpi=160)
        outputs.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha(path)})
    plt.close(fig)
    evidence = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "kind": "DESCRIPTIVE_ORIGINAL_SUFFIX_REPRODUCTION_NOT_NEW_EVALUATION",
                "inputs": inputs, "results": results, "plots": outputs,
                "claim_boundary": "Two original development flights, not a repeated causal comparison. "
                "All original samples, thresholds, windows and verdicts retained. "
                "This diagnoses failure; it does not certify a controller repair."}
    with (output / "review.json").open("x", encoding="utf8") as stream:
        json.dump(evidence, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({mode: {key: value for key, value in result.items() if key in
          ("original_status", "distance_rmse_m", "final_inside_suffix_duration_to_original_end_s", "reproduced_settled")}
          for mode, result in results.items()}))


if __name__ == "__main__":
    main()
