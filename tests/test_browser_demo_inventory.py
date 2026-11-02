"""Small delivery fixtures only: no real videos, FFmpeg, bags or simulation."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("browser_demo_inventory", ROOT / "scripts/build_browser_demos.py")
demos = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demos)


class BrowserDemoInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.matrix = self.root / "matrix"
        (self.matrix / "slots").mkdir(parents=True)
        self.plan_path = self.matrix / "plan.json"
        self.selection_path = self.root / "selection.json"
        self.selection = {"selected_before_formal_execution": True, "video_selection": {
            "seed": 1000, "classes": list(demos.VIDEO_CLASSES), "groups": list(demos.VIDEO_GROUPS),
            "scheduled_clips": 12}}
        self.write_json(self.selection_path, self.selection)
        self.plan = {"mode": "FORMAL", "output": str(self.matrix), "trials": []}
        for cls in demos.VIDEO_CLASSES:
            for group in demos.VIDEO_GROUPS:
                slot_id = f"{cls}_{group}_seed1000"
                self.plan["trials"].append({"id": slot_id, "name": "formal_" + slot_id,
                    "target_class": cls, "group": group, "seed": 1000,
                    "scenario_kind": "crossing" if group in ("stage2_crossing", "stage3_multi_active") else "parallel",
                    "directory": str(self.root / ("formal_" + slot_id))})
        self.plan["plan_sha256"] = demos.json_digest(self.plan, "plan_sha256")
        self.write_json(self.plan_path, self.plan)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def recorded(self, number, *, status="FAIL", missing_video=False, config_changes=None, summary_changes=None,
                 include_video_hash=False):
        trial = self.plan["trials"][number]
        directory = Path(trial["directory"])
        directory.mkdir()
        video = directory / "onboard.mp4"
        if not missing_video:
            video.write_bytes(b"SMALL_SYNTHETIC_FIXTURE_NOT_A_VIDEO")
        config = {key: trial[key] for key in ("name", "target_class", "seed", "scenario_kind")}
        config.update(config_changes or {})
        summary = {"class_name": trial["target_class"]}
        summary.update(summary_changes or {})
        self.write_json(directory / "run_config.json", config)
        self.write_json(directory / "summary.json", summary)
        slot = {"id": trial["id"], "name": trial["name"], "plan_sha256": self.plan["plan_sha256"],
            "status": status, "engineering_result": "FAIL", "finished_utc": "2026-11-03T00:00:00+00:00",
            "artifact_hashes": {name: demos.digest(directory / name) for name in demos.RECORDED_FILES
                                if (name != "onboard.mp4" or include_video_hash) and (directory / name).is_file()}}
        slot["record_sha256"] = demos.json_digest(slot, "record_sha256")
        self.write_json(self.matrix / "slots" / (trial["id"] + ".json"), slot)
        return directory

    def inventory(self):
        return demos.selected_inventory(self.plan_path, self.selection_path)

    def test_inventory_keeps_twelve_even_without_any_original_terminal_or_video(self):
        output = self.root / "inventory"
        with patch.object(sys, "argv", ["build_browser_demos.py", "--core-plan", str(self.plan_path),
                "--selection", str(self.selection_path), "--inventory-only", "--output", str(output)]), \
                patch.object(demos.subprocess, "run") as run, patch.object(demos.shutil, "which") as which, \
                patch("builtins.print"):
            demos.main()
        run.assert_not_called()
        which.assert_not_called()
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["trials"]), 12)
        self.assertEqual(manifest["counts"], {"scheduled": 12, "transcode_eligible": 0, "verified_copies": 0})
        self.assertTrue(all(row["original_status"] is None and row["reasons"] for row in manifest["trials"]))
        document = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("0/12", document)
        self.assertTrue(all(trial["id"] in document for trial in self.plan["trials"]))

    def test_fail_with_missing_video_and_running_source_remain_ineligible(self):
        self.recorded(0, missing_video=True)
        self.recorded(1, status="RUNNING")
        manifest = self.inventory()
        missing, running = manifest["trials"][:2]
        self.assertEqual(missing["original_engineering_result"], "FAIL")
        self.assertIn("Missing recorded evidence: onboard.mp4", missing["reasons"])
        self.assertFalse(missing["transcode_eligible"])
        self.assertFalse(running["transcode_eligible"])
        self.assertTrue(any("running/pending" in reason for reason in running["reasons"]))
        self.assertEqual(len(manifest["trials"]), 12)

    def test_actual_config_and_summary_fields_are_checked_even_with_matching_artifact_hashes(self):
        self.recorded(0, config_changes={"seed": 1001})
        self.recorded(1, summary_changes={"class_name": "car", "scenario": "foreign"})
        rows = self.inventory()["trials"]
        self.assertIn("Recorded source identity mismatch: run_config.json:seed", rows[0]["reasons"])
        self.assertIn("Recorded source identity mismatch: summary.json:class_name", rows[1]["reasons"])
        self.assertIn("Recorded source identity mismatch: summary.json:scenario", rows[1]["reasons"])
        self.assertFalse(rows[0]["transcode_eligible"])
        self.assertFalse(rows[1]["transcode_eligible"])

    def test_fixed_selection_cannot_shrink_or_change_the_seed(self):
        for field, value in (("scheduled_clips", 11), ("groups", list(demos.VIDEO_GROUPS[:-1])), ("seed", 1001)):
            with self.subTest(field=field):
                selection = json.loads(json.dumps(self.selection))
                selection["video_selection"][field] = value
                self.write_json(self.selection_path, selection)
                with self.assertRaisesRegex(ValueError, "exactly.*twelve"):
                    self.inventory()

    def test_inventory_does_not_hash_video_or_hide_absent_summary_identity_fields(self):
        self.recorded(4)
        original_digest = demos.digest

        def small_metadata_only(path):
            self.assertNotEqual(path.suffix, ".mp4")
            return original_digest(path)

        with patch.object(demos, "digest", side_effect=small_metadata_only):
            row = self.inventory()["trials"][4]
        self.assertTrue(row["transcode_eligible"])
        self.assertEqual(row["original_status"], "FAIL")
        self.assertFalse(row["files"]["onboard.mp4"]["content_hash_checked"])
        self.assertIsNone(row["expected_source_sha256"])
        self.assertIn("historical video SHA absent", row["video_provenance_scope"])
        self.assertTrue(any(item["file"] == "onboard.mp4" and item["field"] == "original_artifact_sha256"
                            for item in row["unverifiable_fields"]))
        self.assertTrue(any(item["file"] == "summary.json" and item["field"] == "seed"
                            for item in row["unverifiable_fields"]))

    def test_only_complete_terminal_source_uses_original_conversion_and_keeps_its_ordinal(self):
        self.recorded(4)
        output = self.root / "copies"
        timestamps = {"codec_name": "mpeg4", "width": 2, "height": 2, "nb_read_frames": "2",
                      "avg_frame_rate": "10/1", "duration_s": .2, "relative_frame_timestamps_s": [0., .1]}
        commands = []

        def fake_run(command, **_):
            if "-version" in command:
                return SimpleNamespace(stdout="ffmpeg fixture\n", stderr="")
            if "-h" in command:
                return SimpleNamespace(stdout="  -fps_mode mode\n", stderr="")
            commands.append(command)
            Path(command[-1]).write_bytes(b"ENCODED_FIXTURE")
            return SimpleNamespace(returncode=0)

        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["build_browser_demos.py", "--core-plan", str(self.plan_path),
                "--selection", str(self.selection_path), "--output", str(output)]))
            stack.enter_context(patch.object(demos.shutil, "which", side_effect=lambda name: name))
            stack.enter_context(patch.object(demos.subprocess, "run", side_effect=fake_run))
            probe = stack.enter_context(patch.object(demos, "probe", side_effect=[timestamps, {**timestamps, "codec_name": "h264"}]))
            stack.enter_context(patch("builtins.print"))
            demos.main()
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(len(commands), 1)
        self.assertEqual(Path(commands[0][-1]).name, "demo_05.mp4")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["trials"]), 12)
        self.assertEqual(manifest["trials"][4]["status"], "VERIFIED")
        self.assertEqual(manifest["trials"][4]["original_engineering_result"], "FAIL")
        self.assertTrue(manifest["trials"][4]["source_unchanged_during_transcode"])
        self.assertIsNone(manifest["trials"][4]["files"]["onboard.mp4"]["content_hash_matches_original"])
        self.assertEqual(manifest["counts"]["verified_copies"], 1)

    def test_changed_source_video_is_rejected_before_probe_or_conversion(self):
        directory = self.recorded(0, include_video_hash=True)
        row = self.inventory()["trials"][0]
        (directory / "onboard.mp4").write_bytes(b"CHANGED_AFTER_ORIGINAL_SLOT")
        with patch.object(demos, "probe") as probe, patch.object(demos.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "original slot artifact hash"):
                demos.transcode_record("ffmpeg", "ffprobe", ["-vsync", "0"], directory / "onboard.mp4",
                                       self.root / "unused.mp4", row)
        probe.assert_not_called()
        run.assert_not_called()

    def test_source_mutation_during_conversion_cannot_be_published_as_verified(self):
        self.recorded(0)  # The actual collector schema has no historical MP4 hash.
        output = self.root / "mutated_source_delivery"

        def changing_conversion(_ffmpeg, _ffprobe, _timing, source, destination, row):
            row.update(source_sha256=demos.digest(source), status="VERIFIED")
            destination.write_bytes(b"SYNTHETIC_COPY")
            source.write_bytes(b"SOURCE_MUTATED_DURING_CONVERSION")

        with patch.object(sys, "argv", ["build_browser_demos.py", "--core-plan", str(self.plan_path),
                "--selection", str(self.selection_path), "--output", str(output)]), \
                patch.object(demos.shutil, "which", side_effect=lambda name: name), \
                patch.object(demos.subprocess, "run", return_value=SimpleNamespace(stdout="ffmpeg fixture\n")), \
                patch.object(demos, "passthrough_arguments", return_value=["-vsync", "0"]), \
                patch.object(demos, "transcode_record", side_effect=changing_conversion):
            with self.assertRaisesRegex(RuntimeError, "Source video changed"):
                demos.main()
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["trials"]), 12)
        self.assertEqual(manifest["trials"][0]["status"], "FAILED")
        self.assertFalse(manifest["trials"][0]["source_unchanged_during_transcode"])
        self.assertEqual(manifest["trials"][0]["original_engineering_result"], "FAIL")
        self.assertFalse(manifest["video_delivery_complete"])
        self.assertEqual(manifest["counts"]["verified_copies"], 0)


if __name__ == "__main__":
    unittest.main()
