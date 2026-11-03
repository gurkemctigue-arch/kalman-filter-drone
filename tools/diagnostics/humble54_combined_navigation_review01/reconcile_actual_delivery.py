"""Reconcile the already exported early-loss messages; never open a bag."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
EXPORT = ROOT / "results/diagnostics/humble54_combined_early_loss_input_extract01"
ARCHIVE = Path(__file__).resolve().parent / "early_loss_input_evidence01"
MANIFEST_SHA = "5344dbada5c9c5d12faaca3bdd98822972e2e1ea940e186069c1e6aeb2e61af2"
FAULT_SOURCE_SHA = "c07b1b5e7a7addbe2b7b4ad63cb798503646a8f92cf14aa66a1fd35582a486f0"
TOPICS = (
    "/camera/color/image_raw", "/camera/aligned_depth_to_color/image_raw",
    "/research/camera/color/image_raw", "/research/camera/aligned_depth_to_color/image_raw",
    "/tracking/detection_diagnostics",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reconcile(manifest):
    assert manifest["all_selected_topics_scanned"] is True
    assert manifest["absent_topics"] == [] and manifest["clock_regression_count"] == 0
    assert manifest["slot_id"] == "person_extension_combined_seed004"
    assert manifest["extraction_kind"] == "POST_HOC_EARLY_LOSS_INPUT_DELIVERY_DIAGNOSIS_NOT_SHORT_SHUTTER_EVIDENCE"
    assert manifest["original_sensor_faults"] == {
        "seed": 4, "noise_std_m": 0.05, "hole_fraction": 0.2,
        "drop_fraction": 0.1, "delay_s": 0.08,
    }
    counts = Counter((row["acquisition_ns"], row["topic"]) for row in manifest["opportunities"])
    rows = []
    for acquisition in range(33800000000, 35200000001, 100000000):
        window = acquisition // 200000000
        digest = hashlib.sha256(f"4:{window}".encode()).digest()
        uniform = int.from_bytes(digest[:8], "big") / 2**64
        drop = uniform < 0.1
        observed = {topic: counts[(acquisition, topic)] for topic in TOPICS}
        expected = {topic: (1 if index < 2 or not drop else 0) for index, topic in enumerate(TOPICS)}
        assert observed == expected, (acquisition, observed, expected)
        rows.append({"acquisition_ns": acquisition, "stamp_s": acquisition / 1e9,
                     "fault_window": window, "digest_sha256": digest.hex(),
                     "uniform_u64_over_2p64": uniform, "expected_action": "DROP" if drop else "KEEP",
                     "recorded_message_counts": observed, "matches_rule": True})
    assert sum(counts.values()) == 57
    assert [row["acquisition_ns"] for row in rows if row["expected_action"] == "DROP"] == list(range(34200000000, 34700000001, 100000000))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="store_true", help="Create a new archive of the existing export and derived comparison")
    args = parser.parse_args()
    raw = (EXPORT / "manifest.json").read_bytes()
    assert sha(raw) == MANIFEST_SHA
    manifest = json.loads(raw)
    assert sha((ROOT / "scripts/sensor_fault_bridge.py").read_bytes()) == FAULT_SOURCE_SHA
    rows = reconcile(manifest)
    files = {"manifest.json": MANIFEST_SHA,
             manifest["contact_sheet"]["file"]: manifest["contact_sheet"]["sha256"]}
    for row in manifest["opportunities"]:
        if "original_png" in row:
            files[row["original_png"]] = row["png_sha256"]
    assert len(files) == 17
    for name, digest in files.items():
        assert Path(name).name == name
        assert sha((EXPORT / name).read_bytes()) == digest
    report = {
        "schema_version": 1, "status": "ACTUAL_RECORDED_DELIVERY_MATCHES_DETERMINISTIC_INJECTION",
        "scope": "Post-hoc descriptive 33.8–35.2 second source acquisition window; existing exporter messages only",
        "manifest_sha256": MANIFEST_SHA, "source_sha256": FAULT_SOURCE_SHA,
        "rows": rows, "opportunity_count": 15, "raw_rgb_count": 15, "raw_depth_count": 15,
        "research_rgb_count": 9, "research_depth_count": 9, "diagnostic_count": 9,
        "consecutive_drop_count": 6,
        "interpretation": "The raw streams contain all six opportunities at 34.2–34.7s. Both recorded research streams and diagnostics omit those keys, matching the configured injector; every other selected key appears in both research streams and diagnostics.",
        "claim_boundary": "Recorded-message presence/absence, not proof of exact callback arrival or complete ROS delivery. latest_read_clock_ns is reader context, not callback receipt. Visual target presence is recorded separately by the reviewer. This window cannot replace the fixed short-shutter four-slot attachment. No original FAIL or timeout is changed.",
        "original_export_status_retained": manifest["status"],
        "tool_sha256": sha(Path(__file__).read_bytes()),
    }
    if args.archive:
        assert not ARCHIVE.exists(), "Archive already exists; do not overwrite evidence"
        ARCHIVE.mkdir()
        for name, digest in files.items():
            shutil.copyfile(EXPORT / name, ARCHIVE / name)
            assert sha((ARCHIVE / name).read_bytes()) == digest
        report["archived_utc"] = datetime.now(timezone.utc).isoformat()
        report["original_artifacts"] = {
            name: {"sha256": digest, "bytes": (ARCHIVE / name).stat().st_size}
            for name, digest in files.items()
        }
        (ARCHIVE / "actual_delivery_reconciliation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": len(rows), "archived": args.archive}))


if __name__ == "__main__":
    main()
