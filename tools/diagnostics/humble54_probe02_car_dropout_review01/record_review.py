"""Archive this already-performed AI image review; no ROS, bag reader or inference.

The observations below were made by actually viewing the contact sheet and each
of the nine original PNGs with view_image. Running this recorder is not a new
image review and never evaluates the sensor_input_interruption_v1 flight gate.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "results/diagnostics/humble54_probe02_car_dropout_input_extract01"
DESTINATION = Path(__file__).resolve().parent
MANIFEST_SHA256 = "2818cafb2de57f3a7559eb50b90a946acbe53f3246dd5b44c8a6f526c73006a6"
REVIEW_RECORDED_UTC = "2026-11-03T09:27:01+00:00"
REVIEWER = "Codex AI subagent /root/clock_split_external_review"
VISIBLE = "ONE_CAR_AND_SCENE_VISIBLE_IN_CONTACT_SHEET"
OBSCURED = "SCENE_OBSCURED_NEAR_BLACK_TARGET_NOT_VISIBLE"
OBSERVATIONS = {
    "raw_rgb_01_seq013482_ns30700000000.png": (VISIBLE,
        "One gray car seen from the rear in the upper central image; wheels, rear window and body are distinguishable against pale ground and blue sky."),
    "raw_rgb_02_seq013512_ns30800000000.png": (VISIBLE,
        "One gray rear-view car remains clearly distinguishable in the upper central image with ground and sky visible; no second car is visible."),
    "raw_rgb_03_seq013542_ns30900000000.png": (VISIBLE,
        "One gray rear-view car, its wheels and rear window remain visible; the surrounding ground and sky are visible."),
    "raw_rgb_04_seq013572_ns31000000000.png": (OBSCURED,
        "The image is almost entirely dark with faint broad tonal/diagonal regions. No car, ground horizon or sky can be identified from these pixels."),
    "raw_rgb_05_seq013602_ns31100000000.png": (OBSCURED,
        "The original image is near black with faint tonal regions. No car or recognizable outdoor scene is visible."),
    "raw_rgb_06_seq013632_ns31200000000.png": (OBSCURED,
        "The original image remains near black; faint dark tonal bands are visible but no car or recognizable outdoor scene can be distinguished."),
    "raw_rgb_07_seq013659_ns31300000000.png": (VISIBLE,
        "A gray rear-view car is visible again in the upper central image with ground and sky; the image alone does not establish its tracked identity."),
    "raw_rgb_08_seq013686_ns31400000000.png": (VISIBLE,
        "One gray rear-view car and the surrounding ground and sky are clearly visible; no tracker output is present in this image."),
    "raw_rgb_09_seq013713_ns31500000000.png": (VISIBLE,
        "One gray rear-view car remains visible against ground and sky; this is only a visible-image observation, not proof of tracking recovery."),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native(path):
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def write_new_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main():
    manifest_path = SOURCE / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    assert digest(manifest_bytes) == MANIFEST_SHA256
    manifest = json.loads(manifest_bytes)
    assert manifest["slot_id"] == "car_extension_dropout_seed004"
    assert manifest["exported_raw_rgb_count"] == 9
    assert len(manifest["opportunities"]) == 33
    rows = [row for row in manifest["opportunities"] if "original_png" in row]
    assert [row["original_png"] for row in rows] == list(OBSERVATIONS)
    copies = [("manifest.json", MANIFEST_SHA256)] + [
        (row["original_png"], row["png_sha256"]) for row in rows] + [
        (manifest["contact_sheet"]["file"], manifest["contact_sheet"]["sha256"])]
    verified = []
    for filename, expected in copies:
        data = (SOURCE / filename).read_bytes()
        assert digest(data) == expected, filename
        verified.append((filename, expected, data))
    archive = DESTINATION / "evidence/input"
    archive.mkdir(parents=True, exist_ok=False)
    copy_bindings = []
    for filename, expected, data in verified:
        with (archive / filename).open("xb") as handle:
            handle.write(data)
        assert digest((archive / filename).read_bytes()) == expected
        copy_bindings.append({"source_path": str(SOURCE / filename),
                              "native_source_path": native(SOURCE / filename),
                              "archived_file": "evidence/input/" + filename,
                              "bytes": len(data), "sha256": expected})
    images = []
    for row in rows:
        label, notes = OBSERVATIONS[row["original_png"]]
        images.append({"file": row["original_png"], "sha256": row["png_sha256"],
                       "acquisition_ns": row["acquisition_ns"], "observation": label,
                       "pixel_notes": notes, "reviewer": REVIEWER,
                       "review_recorded_utc": REVIEW_RECORDED_UTC,
                       "viewed_original_resolution": True, "width": row["width"],
                       "height": row["height"], "record_sequence": row["record_sequence"]})
    module = ROOT / "tools/offline_evaluation/sensor_input_interruption_v1/evidence.py"
    module_sha = digest(module.read_bytes())
    assert module_sha == "f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba"
    review = {
        "kind": "INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE",
        "review_type": "DIRECT_IMAGE_REVIEW_AI", "created_utc": REVIEW_RECORDED_UTC,
        "reviewers": [REVIEWER + "; directly viewed the contact sheet and all nine original PNGs using view_image; PNGs viewed at original 640x480 resolution."],
        "manifest": {"path": native(manifest_path), "sha256": MANIFEST_SHA256},
        "contact_sheet": manifest["contact_sheet"], "images": images,
        "scope": "Pixel facts only. Original FAIL, checks and nulls are unchanged. Visible car reappearance does not prove tracker recovery, the same physical individual, identity preservation or engineering acceptance.",
        "observed_summary": {"visible_acquisition_ns": [row["acquisition_ns"] for row in images if row["observation"] == VISIBLE],
                             "near_black_acquisition_ns": [row["acquisition_ns"] for row in images if row["observation"] == OBSCURED],
                             "source_images_reviewed": 9, "contact_sheet_reviewed": True},
        "schema_reference_only": {"module_path": native(module), "sha256": module_sha,
                                  "revision": "sensor_input_interruption_v1",
                                  "review_fields_reference": "evidence.py:_review (line 368 onward)",
                                  "full_evaluate_slot_executed": False},
        "engineering_boundary": {
            "original_terminal_status": manifest["original_terminal_status"],
            "original_acceptance_result": manifest["original_acceptance"]["result"],
            "original_detector_interruption_observed": manifest["original_short_window"]["checks"]["detector_interruption_observed"],
            "original_diagnostic_frames_inside": manifest["original_short_window"]["diagnostic_frames_inside"],
            "original_no_loss_during_short_occlusion": manifest["original_short_window"]["checks"]["no_loss_during_short_occlusion"],
            "original_identity_preserved_on_observed_recovery": manifest["original_short_window"]["checks"]["identity_preserved_on_observed_recovery"],
            "original_first_measured_after_open_s": manifest["original_short_window"]["first_measured_after_open_s"],
            "applicability_note": "This is not the zero-downstream-input detector-null case targeted by the module. The original detector check already has two diagnostic frames and is true; the separate identity-on-recovery null is not filled by pixels. The module's _original bool gate at lines 273-276 checks SHORT_ALGORITHM before its NOT_APPLICABLE branch at line 445. No formal module result is claimed.",
            "status": "PIXEL_REVIEW_ONLY_NOT_ENGINEERING_EVALUATION",
            "upstream_input_interruption_corroborated_claimed": False,
            "tracker_recovery_proven": False, "identity_preservation_proven": False,
            "original_artifacts_modified": False,
        },
    }
    review_path = DESTINATION / "visual_review_native01.json"
    write_new_json(review_path, review)
    summary = {
        "kind": "MANIFEST_OPPORTUNITY_DESCRIPTION_NOT_NEW_ENGINEERING_EVALUATION",
        "manifest_sha256": MANIFEST_SHA256, "opportunity_count": 33,
        "window_opportunity_counts": dict(Counter(row["topic"] for row in manifest["opportunities"])),
        "acquisition_ns_by_topic": {topic: [row["acquisition_ns"] for row in manifest["opportunities"] if row["topic"] == topic]
                                    for topic in manifest["topics_selected"][1:]},
        "observation_boundary": "Raw RGB/depth exist at all nine sampled times. In this extracted window research RGB/depth and diagnostics have only 30.7-31.1 s entries. Their absence at 31.2-31.5 s is recorded absence, not an empty detector result or tracker recovery proof.",
        "original_terminal_status": manifest["original_terminal_status"],
        "original_short_checks": manifest["original_short_window"]["checks"],
    }
    write_new_json(DESTINATION / "opportunity_description01.json", summary)
    write_new_json(DESTINATION / "archive_manifest01.json", {
        "schema_version": 1, "kind": "BYTE_PRESERVING_REVIEW_ARCHIVE_NOT_ACCEPTANCE",
        "created_utc": REVIEW_RECORDED_UTC, "reviewer": REVIEWER,
        "original_manifest_status_unchanged": manifest["status"],
        "copies": copy_bindings,
        "new_visual_review": {"file": review_path.name, "sha256": digest(review_path.read_bytes())},
        "authoring_script": {"file": Path(__file__).name, "sha256": digest(Path(__file__).read_bytes())},
        "bag_read": False, "telemetry_read": False, "wsl_or_ros_executed": False,
    })
    assert digest(manifest_path.read_bytes()) == MANIFEST_SHA256
    print(json.dumps({"visual_review_path": str(review_path), "sha256": digest(review_path.read_bytes()),
                      "images_actually_reviewed": len(images), "source_manifest_unchanged": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()
