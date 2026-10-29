"""Pure-Python accounting checks; no ROS, /proc host scan or simulator."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runtime_health_fixture", ROOT / "scripts/observe_runtime_health.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


class RuntimeHealthTests(unittest.TestCase):
    @staticmethod
    def stat(pid, cpu_ticks, start_ticks, rss_pages):
        fields = ["S"] + ["0"] * 21
        fields[11], fields[12], fields[19], fields[21] = str(cpu_ticks), "0", str(start_ticks), str(rss_pages)
        return f"{pid} (python worker (private)) " + " ".join(fields)

    def write_process(self, root, pid, cpu_ticks, start_ticks=10):
        directory = root / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / "comm").write_text("python3\n", encoding="utf-8")
        (directory / "cmdline").write_bytes(b"/usr/bin/python3\0/private/secret-job.py\0--token=private\0")
        (directory / "stat").write_text(self.stat(pid, cpu_ticks, start_ticks, 20), encoding="ascii")

    def test_cpu_delta_and_pid_reuse_do_not_leak_commands_or_invent_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_process(root, 123, 100)
            sampler = observer.ProcessSampler(root, clock_ticks=100, page_size=4096)
            first = sampler.sample(1.)
            self.assertIsNone(first["groups"]["python"]["cpu_percent_one_core"])
            self.write_process(root, 123, 150)
            second = sampler.sample(2.)
            self.assertAlmostEqual(second["groups"]["python"]["cpu_percent_one_core"], 50.)
            self.assertEqual(second["groups"]["python"]["rss_bytes"], 20 * 4096)
            self.write_process(root, 123, 2000, start_ticks=99)
            reused = sampler.sample(3.)
            self.assertIsNone(reused["groups"]["python"]["cpu_percent_one_core"])
            self.assertEqual(reused["groups"]["python"]["new_or_reused_processes"], 1)
            self.assertNotIn("secret-job", str(second))
            self.assertNotIn("private", str(second))

    def test_process_groups_are_disjoint_with_recorder_precedence(self):
        self.assertEqual(observer.process_group("python3", ["/usr/bin/python3", "/opt/ros/humble/bin/ros2", "bag", "record", "--all"]), "recorder")
        self.assertEqual(observer.process_group("ruby", ["/usr/bin/ruby", "/usr/bin/gz", "sim", "-r"]), "gazebo")
        self.assertEqual(observer.process_group("px4", ["/root/px4"]), "px4")
        self.assertEqual(observer.process_group("python3", ["/usr/bin/python3", "node.py"]), "python")
        self.assertIsNone(observer.process_group("bash", ["/bin/bash"]))

    def test_paused_clock_and_receipt_ages_remain_distinct(self):
        state = observer.RosTimingState()
        state.receive_clock(10_000_000_000, 1_000_000_000)
        state.receive_status(9_999_000, 2, 14, False, 1_100_000_000)
        first = state.snapshot(2_000_000_000)
        self.assertIsNone(first["sim_seconds_per_monotonic_second_observed"])
        state.receive_clock(10_000_000_000, 2_500_000_000)
        paused = state.snapshot(3_000_000_000)
        self.assertEqual(paused["sim_seconds_per_monotonic_second_observed"], 0.)
        self.assertAlmostEqual(paused["topics"]["vehicle_status"]["receipt_age_wall_s"], 1.9)
        self.assertAlmostEqual(paused["topics"]["clock"]["receipt_age_wall_s"], .5)
        self.assertEqual(paused["topics"]["vehicle_status"]["last_source_fields"]["px4_timestamp_us"], 9_999_000)
        state.receive_clock(9_000_000_000, 3_100_000_000)
        regressed = state.snapshot(4_000_000_000)
        self.assertEqual(regressed["clock_source_regressions"], 1)
        self.assertIsNone(regressed["sim_seconds_per_monotonic_second_observed"])


if __name__ == "__main__":
    unittest.main()
