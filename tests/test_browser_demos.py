"""FFmpeg capability and delivery verification fixtures; no real video encoding."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("browser_demos", ROOT / "scripts/build_browser_demos.py")
demos = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demos)

MODERN_HELP = "  -vsync parameter  video sync method\n  -fps_mode mode  set framerate mode\n"
LEGACY_HELP = "  -vsync parameter  video sync method\n"
VIDEO = {
    "codec_name": "mpeg4", "width": 640, "height": 480,
    "nb_read_frames": "3", "avg_frame_rate": "10/1", "duration_s": .3,
    "relative_frame_timestamps_s": [0., .1, .2],
}


class BrowserDemoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.trial = self.root / "explicit_trial"
        self.trial.mkdir()
        self.original = b"SYNTHETIC_FIXTURE_ONLY_NOT_A_REAL_VIDEO"
        (self.trial / "onboard.mp4").write_bytes(self.original)
        for name in ("run_config.json", "summary.json"):
            (self.trial / name).write_text("{}\n", encoding="utf-8")

    def test_modern_capability_wins_when_both_options_are_advertised(self):
        result = SimpleNamespace(stdout=MODERN_HELP, stderr="")
        with patch.object(demos.subprocess, "run", return_value=result) as run:
            self.assertEqual(demos.passthrough_arguments("ffmpeg"), ["-fps_mode", "passthrough"])
        self.assertEqual(run.call_args.args[0], ["ffmpeg", "-hide_banner", "-h", "full"])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_ffmpeg44_legacy_capability_can_be_printed_on_either_stream(self):
        for stdout, stderr in ((LEGACY_HELP, ""), ("", LEGACY_HELP)):
            with self.subTest(stdout=bool(stdout)):
                # Mentioning an unavailable option in prose does not advertise it.
                result = SimpleNamespace(stdout=stdout + "See -fps_mode in newer versions.\n", stderr=stderr)
                with patch.object(demos.subprocess, "run", return_value=result):
                    self.assertEqual(demos.passthrough_arguments("ffmpeg"), ["-vsync", "0"])

    def test_no_advertised_passthrough_fails_instead_of_guessing(self):
        with patch.object(demos.subprocess, "run", return_value=SimpleNamespace(stdout="-version\n", stderr="")):
            with self.assertRaisesRegex(RuntimeError, "does not advertise"):
                demos.passthrough_arguments("ffmpeg")

    def test_failed_capability_command_is_not_treated_as_supported(self):
        error = subprocess.CalledProcessError(1, ["ffmpeg", "-h", "full"])
        with patch.object(demos.subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                demos.passthrough_arguments("ffmpeg")

    def run_fixture(self, output, help_text, after, *, failure=None):
        commands = []

        def fake_run(command, **_):
            if "-version" in command:
                return SimpleNamespace(stdout="ffmpeg fixture capability build\n", stderr="")
            if "-h" in command:
                return SimpleNamespace(stdout=help_text, stderr="")
            commands.append(command)
            Path(command[-1]).write_bytes(b"SYNTHETIC_ENCODED_FIXTURE_ONLY")
            return SimpleNamespace(returncode=0)

        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["build_browser_demos.py", "--trial", str(self.trial), "--output", str(output)]))
            stack.enter_context(patch.object(demos.shutil, "which", side_effect=lambda name: name))
            stack.enter_context(patch.object(demos.subprocess, "run", side_effect=fake_run))
            probe = stack.enter_context(patch.object(demos, "probe", side_effect=[deepcopy(VIDEO), after]))
            stack.enter_context(patch("builtins.print"))
            if failure:
                with self.assertRaises(failure):
                    demos.main()
            else:
                demos.main()
                self.assertEqual(probe.call_count, 2)
        self.assertEqual((self.trial / "onboard.mp4").read_bytes(), self.original)
        return commands

    def test_modern_and_legacy_commands_preserve_full_recording_and_verify_it(self):
        for number, (help_text, expected) in enumerate(((MODERN_HELP, ["-fps_mode", "passthrough"]), (LEGACY_HELP, ["-vsync", "0"]))):
            with self.subTest(timing=expected):
                output = self.root / f"delivery_{number}"
                commands = self.run_fixture(output, help_text, {**deepcopy(VIDEO), "codec_name": "h264"})
                self.assertEqual(len(commands), 1)
                command = commands[0]
                index = command.index(expected[0])
                self.assertEqual(command[index:index + 2], expected)
                self.assertNotIn("-vsync" if expected[0] == "-fps_mode" else "-fps_mode", command)
                self.assertIn("-n", command)
                for forbidden in ("-y", "-ss", "-t", "-to", "-frames:v", "-r", "-vf"):
                    self.assertNotIn(forbidden, command)
                self.assertEqual(command[command.index("-i") + 1], str(self.trial / "onboard.mp4"))
                self.assertEqual(command[-1], str(output / "demo_01.mp4"))
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["frame_sync_arguments"], expected)
                self.assertEqual(manifest["trials"][0]["argv"], command)
                self.assertEqual(manifest["trials"][0]["status"], "VERIFIED")
                self.assertTrue((output / "index.html").is_file())

    def test_legacy_conversion_still_rejects_trimmed_frames_duration_or_timing(self):
        alterations = (
            {"nb_read_frames": "2", "relative_frame_timestamps_s": [0., .1]},
            {"duration_s": .1},
            {"relative_frame_timestamps_s": [0., .1, .22]},
        )
        for number, alteration in enumerate(alterations):
            with self.subTest(alteration=alteration):
                output = self.root / f"failed_delivery_{number}"
                after = {**deepcopy(VIDEO), "codec_name": "h264", **alteration}
                self.run_fixture(output, LEGACY_HELP, after, failure=RuntimeError)
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["trials"][0]["status"], "FAILED")
                self.assertIn("frame/timing verification failed", manifest["trials"][0]["error"])
                self.assertTrue((output / "demo_01.mp4").is_file())
                self.assertFalse((output / "index.html").exists())

    def test_unsupported_capability_does_not_create_delivery_directory(self):
        output = self.root / "unsupported_delivery"
        self.assertEqual(self.run_fixture(output, "No timing option here\n", {}, failure=RuntimeError), [])
        self.assertFalse(output.exists())

    def test_existing_delivery_is_rejected_before_any_ffmpeg_process(self):
        output = self.root / "existing_delivery"
        output.mkdir()
        saved = output / "demo_01.mp4"
        saved.write_bytes(b"KEEP_EXISTING")
        with patch.object(sys, "argv", ["build_browser_demos.py", "--trial", str(self.trial), "--output", str(output)]), patch.object(demos.shutil, "which", side_effect=lambda name: name), patch.object(demos.subprocess, "run") as run, patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                demos.main()
        run.assert_not_called()
        self.assertEqual(saved.read_bytes(), b"KEEP_EXISTING")


if __name__ == "__main__":
    unittest.main()
