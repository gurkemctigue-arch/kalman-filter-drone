"""One read-only telemetry traversal per closed trial; no ROS, bag or replay."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from collections import Counter


ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results/frozen_fullplan_v4_humble54"
CASES = (
    ("person_extension_combined_seed004", 33.8, 35.2,
     "f57d22dff4989c8bbb45b56ba2151d66e52b5689984cd0a0104f531d4749b655"),
    ("car_extension_dropout_seed004", 30.7, 31.85,
     "f80a774d1af43cbb6e8525662bb13f3c2853c9c19d68ac57ccd82435b9015f17"),
)
KINDS = {"control_status", "detection", "observation", "target_state", "navigation_state",
         "tracks", "navigation_diagnostics"}


def main():
    folder = Path(__file__).resolve().parent
    output = folder / "actual_windows01.json"
    if output.exists():
        raise FileExistsError("Preserve the existing actual extraction")
    reports = []
    for slot, start, end, terminal_sha in CASES:
        terminal_path = RESULTS / "reliability_v4_humble54_extension16_probe02_matrix/slots" / (slot + ".json")
        raw = terminal_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == terminal_sha
        terminal = json.loads(raw)
        assert terminal["execution_status"] == "COMPLETED" and terminal["infrastructure_stop"] is False
        source = RESULTS / ("reliability_v4_humble54_extension16_probe02_" + slot) / "telemetry.jsonl"
        before = source.stat()
        digest = hashlib.sha256()
        offset, count = 0, 0
        rows = []
        with source.open("rb") as stream:
            while True:
                line = stream.readline(2 * 1024**2 + 1)
                if not line:
                    break
                if len(line) > 2 * 1024**2 or not line.endswith(b"\n"):
                    raise ValueError("Oversized or incomplete telemetry row")
                digest.update(line)
                count += 1
                record = json.loads(line)
                if record.get("kind") in KINDS:
                    times = [record[k] for k in ("time_s", "stamp_s", "acquisition_s")
                             if type(record.get(k)) in (float, int)]
                    if any(start <= t <= end for t in times):
                        rows.append({"original_line": count, "original_byte_offset": offset, "record": record})
                        if len(rows) > 2000:
                            raise ValueError("Bounded window exceeded 2000 records; do not subsample")
                offset += len(line)
        after = source.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        assert digest.hexdigest() == terminal["artifact_hashes"]["telemetry.jsonl"]
        reports.append({"slot": slot, "original_engineering_result": terminal["engineering_result"],
                        "source": str(source.resolve()), "source_sha256": digest.hexdigest(),
                        "source_bytes": offset, "source_lines": count, "terminal_sha256": terminal_sha,
                        "window_inclusive_sim_s": [start, end],
                        "selection": "All selected kinds where recorded time_s, stamp_s or acquisition_s falls in window; other clocks are not substituted",
                        "selected_count": len(rows),
                        "selected_kind_counts": dict(Counter(r["record"]["kind"] for r in rows)), "rows": rows})
    result = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "ACTUAL_CLOSED_TELEMETRY_WINDOWS_ORIGINAL_JSON_FIELDS_AND_ORDER_ONLY",
              "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "cases": reports,
              "claim_boundary": "Original FAIL/nulls retained; no input mutation, inference, replay, new trial, gate/admission, physical identity assertion or exact callback/wall-clock latency measurement."}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ACTUAL_HASH_VERIFIED_WINDOWS_WRITTEN", "cases": [
        {k: r[k] for k in ("slot", "source_lines", "selected_count", "selected_kind_counts")}
        for r in reports], "output_bytes": output.stat().st_size,
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
