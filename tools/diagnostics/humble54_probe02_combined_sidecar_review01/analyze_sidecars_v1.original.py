"""Describe an already closed probe02 using small existing sidecars only.

No bag, telemetry, ROS, simulator, production imports or historical verdict edits.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results/frozen_fullplan_v4_humble54"
SLOT = "person_extension_combined_seed004"
TRIAL = RESULTS / ("reliability_v4_humble54_extension16_probe02_" + SLOT)
TERMINAL = RESULTS / "reliability_v4_humble54_extension16_probe02_matrix/slots" / (SLOT + ".json")
EXPECTED_TERMINAL = "f57d22dff4989c8bbb45b56ba2151d66e52b5689984cd0a0104f531d4749b655"
FAULT_SOURCE_SHA = "c07b1b5e7a7addbe2b7b4ad63cb798503646a8f92cf14aa66a1fd35582a486f0"


def main():
    folder = Path(__file__).resolve().parent
    output = folder / "sidecar_evidence01.json"
    if output.exists():
        raise FileExistsError("Preserve the existing actual analysis")
    bindings = {}

    def read(path):
        raw = path.read_bytes()
        if len(raw) > 2 * 1024**2:
            raise ValueError("Only bounded small sidecars are allowed")
        bindings[str(path.relative_to(ROOT))] = {
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)
        }
        return raw

    terminal_bytes = read(TERMINAL)
    assert hashlib.sha256(terminal_bytes).hexdigest() == EXPECTED_TERMINAL
    terminal = json.loads(terminal_bytes)
    assert terminal["engineering_result"] == "FAIL" and terminal["execution_status"] == "COMPLETED"
    rows = {}
    for kind in ("frames", "raw_frames", "message_frames"):
        raw = read(TRIAL / ("navigation_reference_evaluation." + kind + ".jsonl"))
        rows[kind] = [json.loads(line) for line in raw.splitlines()]
    fault = json.loads(read(TRIAL / "configuration/sensor_faults.json"))
    source_map = json.loads(read(TRIAL / "configuration/source_sha256.json"))
    source = read(ROOT / "scripts/sensor_fault_bridge.py")
    assert hashlib.sha256(source).hexdigest() == source_map["scripts/sensor_fault_bridge.py"] == FAULT_SOURCE_SHA
    assert fault == {"seed": 4, "noise_std_m": 0.05, "hole_fraction": 0.2,
                     "drop_fraction": 0.1, "delay_s": 0.08}
    parameters = read(TRIAL / "configuration/runtime_parameters.yaml").decode("utf-8")
    assert "max_prediction_duration_s: 0.75" in parameters and "prediction_timeout_s: 0.75" in parameters
    messages = rows["message_frames"]
    first_lost_index = next(i for i, row in enumerate(messages) if row["reason"] == "lost")
    first_lost = messages[first_lost_index]
    last_valid = messages[first_lost_index - 1]
    last_accepted = max((r for r in rows["raw_frames"] if r.get("fusion_accepted") is True
                         and r["received_sim_s"] < first_lost["received_sim_s"]),
                        key=lambda r: r["received_sim_s"])
    next_reference = min((r for r in rows["raw_frames"] if r["time_s"] > last_accepted["time_s"]),
                         key=lambda r: r["time_s"])
    transitions = []
    previous = None
    for row in rows["frames"]:
        if not 30 <= row["time_s"] <= 43:
            continue
        state = tuple(row.get(k) for k in ("navigation_state", "navigation_valid", "navigation_reason", "active"))
        if state != previous:
            transitions.append(row)
        previous = state
    schedule = []
    for window in range(169, 177):
        digest = hashlib.sha256(f"{fault['seed']}:{window}".encode()).digest()
        score = int.from_bytes(digest[:8], "big") / 2**64
        schedule.append({"source_window": window, "start_s": window / 5,
                         "end_exclusive_s": (window + 1) / 5, "score": score,
                         "expected_action": "DROP" if score < fault["drop_fraction"] else "KEEP"})
    report = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "EXISTING_SMALL_NAVIGATION_SIDECARS_POST_HOC_DIAGNOSIS",
        "original_status_retained": "FAIL", "original_terminal_sha256": EXPECTED_TERMINAL,
        "source_bindings": bindings,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "whole_sidecar_counts": {k: len(v) for k, v in rows.items()},
        "first_lost_navigation_message": first_lost,
        "preceding_valid_navigation_message": last_valid,
        "last_accepted_reference_before_loss": last_accepted,
        "next_recorded_reference": next_reference,
        "reference_rows_in_source_34_2_to_34_8_exclusive": sum(34.2 <= r["time_s"] < 34.8 for r in rows["raw_frames"]),
        "source_gap_s": next_reference["time_s"] - last_accepted["time_s"],
        "last_source_to_next_reference_observed_receive_s": next_reference["received_sim_s"] - last_accepted["time_s"],
        "prediction_limit_s": 0.75,
        "nominal_last_source_expiry_s": last_accepted["time_s"] + 0.75,
        "navigation_grid_transitions_30_to_43_s": transitions,
        "expected_fault_schedule_only": schedule,
        "findings": [
            "The first navigation LOST is recorded at 34.86 s, following valid at 34.84 s; this is before the requested 42.8 s long shutter.",
            "Last accepted reference has source 34.1 s and observed receive 34.224 s. Next reference source is 34.8 s, observed receive 34.904 s, already invalid because no selected measurement is accepted.",
            "The 0.804 s source-to-next-reference-observed-receive interval exceeds the unchanged 0.75 s prediction budget. Source-age expiry is consistent with the observed LOST boundary.",
            "Reproducing the recorded seed4 200 ms fault rule predicts three consecutive DROP windows 34.2–34.8 s, matching the absence in the reference sidecar. This does not independently prove actual fault-bridge delivery."
        ],
        "limitations": [
            "Existing evaluator sidecars are derivative evidence, not independent raw RGB/depth or exact ROS callback timestamps.",
            "No bag or telemetry was read. Association pairwise scores, detector receipt, actual bridge input/output and exact controller HOVER transition remain unobserved here.",
            "No claim of complete causal wall-clock latency, identity coverage, automatic recovery or repaired flight acceptance follows from this diagnosis.",
            "A native bounded export is still needed to distinguish raw-input interruption from transport, scheduling, detector discards or association rejection."
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ACTUAL_SIDECAR_ANALYSIS_WRITTEN", "first_lost_s": first_lost["received_sim_s"],
                      "last_accepted_source_s": last_accepted["time_s"], "next_reference_received_s": next_reference["received_sim_s"],
                      "original_status_retained": "FAIL", "report_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
