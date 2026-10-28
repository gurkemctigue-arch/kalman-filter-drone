"""Fixture checks for idle-window postprocessing; no evaluator is executed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("full_plan_supplement", ROOT / "scripts/run_full_plan_supplement.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def inputs():
    main = {"schema_version": 1, "planned_flights": 166, "all_offline_slots_attempted": True,
            "offline_status_counts": {"RECORDED": 166},
            "trials": [{"name": f"main_{i}", "result": "PASS"} for i in range(166)]}
    trials = [{"name": f"extra_{i}", "stage": 1, "target_class": "car", "command_mode": "velocity",
               "desired_distance_m": 12., "desired_height_m": 2.} for i in range(16)]
    plan = {"expected_trials": 16, "primary_166_included": False, "trials": trials}
    extension = {"schema_version": 1, "source": "EXTENDED_ENGINEERING_16_FLIGHTS", "plan": plan,
                 "plan_sha256": post.digest(plan), "slots": [{"trial": trial, "status": "PASS"} for trial in trials]}
    return main, extension


class FullPlanSupplementTests(unittest.TestCase):
    def test_all_flights_and_offline_bookkeeping_must_be_terminal(self):
        main, extension = inputs()
        self.assertEqual(len(post.validate_inputs(main, extension)), 16)
        for status in ("PENDING", "RUNNING_FLIGHT", "UNKNOWN"):
            main["trials"][0]["result"] = status
            with self.assertRaises(ValueError):
                post.validate_inputs(main, extension)
        main["trials"][0]["result"] = "FAIL"
        extension["slots"][0]["status"] = "INTERRUPTED"
        self.assertEqual(len(post.validate_inputs(main, extension)), 16)
        main["offline_status_counts"] = {"RECORDED": 165, "RUNNING_ANALYSIS": 1}
        with self.assertRaises(ValueError):
            post.validate_inputs(main, extension)

    def test_engineering_plan_digest_and_binding_checked(self):
        main, extension = inputs()
        extension["slots"][0]["trial"] = extension["slots"][1]["trial"]
        with self.assertRaises(ValueError):
            post.validate_inputs(main, extension)
        main, extension = inputs()
        extension["plan_sha256"] = "incorrect"
        with self.assertRaises(ValueError):
            post.validate_inputs(main, extension)

    def test_commands_use_frozen_evaluators_class_and_stage1_model(self):
        _, extension = inputs()
        tasks = post.evaluation_tasks(Path("/frozen"), extension["plan"]["trials"][0], python="python")
        self.assertEqual([task[0] for task in tasks], ["online_state_accuracy", "follow_dynamics"])
        command = tasks[0][2]
        self.assertEqual(command[command.index("--target-class") + 1], "car")
        self.assertEqual(command[command.index("--vehicle-model") + 1], "x500_stage1")
        self.assertEqual(Path(command[1]), Path("/frozen") / "scripts/evaluate_online_state_accuracy.py")

    def test_process_scan_recognizes_simulator_and_formal_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid, comm, command in ((123456789, "ruby", b"/usr/bin/gz\0sim\0-r\0world.sdf\0"),
                                       (123456790, "python", b"python\0/frozen/scripts/run_full_plan_research.py\0--phase\0flights\0"),
                                       (123456791, "bash", b"ros2\0bag\0record\0- o\0flight\0"),
                                       (123456792, "MicroXRCEAgent", b"MicroXRCEAgent\0udp4\0--port\08888\0"),
                                       (123456793, "python", b"python\0/install/lib/uav_tracking_controller/controller_node\0")):
                directory = root / str(pid)
                directory.mkdir()
                (directory / "comm").write_text(comm)
                (directory / "cmdline").write_bytes(command)
            self.assertEqual(len(post.active_simulation_processes(root)), 5)

    def test_existing_reports_are_validated_without_runner_or_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, extension = inputs()
            trial = extension["plan"]["trials"][0]
            directory = root / "results" / trial["name"]
            write(directory / "run_config.json", {**trial})
            (directory / "rosbag").mkdir()
            (directory / "rosbag/metadata.yaml").touch()
            online = directory / "online_state_accuracy_v2.json"
            dynamics = directory / "follow_dynamics.json"
            bag_path = str((directory / "rosbag").resolve())
            write(online, {"schema_version": 2, "target_class": "car", "trial": str(directory.resolve()), "bag": {"bag": bag_path},
                           "frame_sidecar": str(online.with_suffix(".frames.jsonl").resolve()),
                           "online_state_accuracy": {"metrics": {}}})
            write(dynamics, {"schema_version": 1, "evaluation_status": "RECORDED_WITH_CENSORED_FAILURES", "trial": str(directory.resolve()), "bag": {"bag": bag_path},
                             "frame_sidecar": str(dynamics.with_suffix(".frames.jsonl").resolve()), "visual_control_metrics": {},
                             "reference": {"desired_horizontal_distance_m": 12., "desired_height_above_model_origin_m": 2.}})
            for path in (online, dynamics):
                path.with_suffix(".frames.jsonl").touch()
            before = online.read_bytes(), dynamics.read_bytes()
            output = root / "supplement"
            (output / "logs").mkdir(parents=True)
            manifest = {"slots": [{"trial": trial, "status": "PENDING"}]}
            def forbidden(*args, **kwargs):
                self.fail("Evaluator must not run for existing outputs")
            post.execute(root, output, manifest, runner=forbidden, idle_check=lambda: [])
            self.assertEqual(manifest["slots"][0]["status"], "RECORDED")
            self.assertTrue(all(task["status"] == "PREEXISTING_RECORDED_REPORT" for task in manifest["slots"][0]["tasks"]))
            self.assertEqual(before, (online.read_bytes(), dynamics.read_bytes()))

    def test_missing_bag_and_interrupted_slot_are_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, extension = inputs()
            output = root / "supplement"
            output.mkdir()
            manifest = {"slots": [{"trial": extension["plan"]["trials"][0], "status": "PENDING"},
                                   {"trial": extension["plan"]["trials"][1], "status": "RUNNING_ANALYSIS"}]}
            def forbidden(*args, **kwargs):
                self.fail("Missing/interrupted evidence must not execute an evaluator")
            post.execute(root, output, manifest, runner=forbidden, idle_check=lambda: [])
            self.assertEqual([slot["status"] for slot in manifest["slots"]], ["INCOMPLETE_EVIDENCE", "INTERRUPTED"])


if __name__ == "__main__":
    unittest.main()
