"""Pure-Python accounting checks; no ROS, /proc host scan or simulator."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def write_process(self, root, pid, cpu_ticks, start_ticks=10, *, comm="python3",
                      argv=b"/usr/bin/python3\0/private/secret-job.py\0--token=private\0", maps=None):
        directory = root / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / "comm").write_text(comm + "\n", encoding="utf-8")
        (directory / "cmdline").write_bytes(argv)
        (directory / "stat").write_text(self.stat(pid, cpu_ticks, start_ticks, 20), encoding="ascii")
        if maps is not None:
            (directory / "maps").write_bytes(maps)
        return directory

    @staticmethod
    def mapping(library=b"libgz-sim8-gz.so.8.10.0"):
        return b"7f000000-7f001000 r-xp 00000000 08:01 123 /private/runtime/lib/" + library + b"\n"

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

    def test_rewritten_gazebo_title_has_rss_and_cpu_without_logging_private_maps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = self.write_process(root, 635, 100, comm="ruby",
                                         argv=b"/private/runtime_world.sdf\0",
                                         maps=self.mapping(b"libgz-sim8.so.8.10.0 (deleted)"))
            sampler = observer.ProcessSampler(root, clock_ticks=100, page_size=4096)
            first = sampler.sample(1.)
            self.assertEqual(first["groups"]["gazebo"]["process_count"], 1)
            self.assertEqual(first["groups"]["gazebo"]["rss_bytes"], 20 * 4096)
            self.assertIsNone(first["groups"]["gazebo"]["cpu_percent_one_core"])
            (process / "stat").write_text(self.stat(635, 150, 10, 20), encoding="ascii")
            (process / "maps").unlink()  # A valid identity cache needs no maps read this second.
            second = sampler.sample(2.)
            self.assertAlmostEqual(second["groups"]["gazebo"]["cpu_percent_one_core"], 50.)
            self.assertEqual(second["maps_fallback"]["checks"], 0)
            self.assertEqual(second["maps_fallback"]["cache_hits"], 1)
            self.assertNotIn("runtime_world", str(second))
            self.assertNotIn("private", str(second))
            self.assertNotIn("libgz", str(second))

    def test_negative_cache_is_rechecked_for_later_library_load_and_pid_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = self.write_process(root, 635, 100, comm="ruby", argv=b"runtime_world.sdf\0",
                                         maps=self.mapping(b"libother.so.8"))
            sampler = observer.ProcessSampler(root, clock_ticks=100, page_size=4096)
            self.assertEqual(sampler.sample(1.)["groups"]["gazebo"]["process_count"], 0)
            (process / "maps").write_bytes(self.mapping())
            self.assertEqual(sampler.sample(2.)["groups"]["gazebo"]["process_count"], 0)
            discovered = sampler.sample(31.)
            self.assertEqual(discovered["groups"]["gazebo"]["process_count"], 1)
            self.assertIsNone(discovered["groups"]["gazebo"]["cpu_percent_one_core"])
            self.write_process(root, 635, 2000, start_ticks=99, comm="ruby", argv=b"runtime_world.sdf\0",
                               maps=self.mapping(b"libother.so.8"))
            reused = sampler.sample(32.)
            self.assertEqual(reused["maps_fallback"]["checks"], 1)
            self.assertEqual(reused["groups"]["gazebo"]["process_count"], 0)

    def test_similar_paths_and_sdf_are_not_gazebo_and_recorder_keeps_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid, library in enumerate((b"notlibgz-sim8.so", b"libgz-sim8.so.fake",
                                            b"libgz-sim8-system.so", b"runtime_world.sdf"), 10):
                self.write_process(root, pid, 100, comm="ruby", argv=b"runtime_world.sdf\0",
                                   maps=self.mapping(library))
            self.write_process(root, 20, 100, comm="python3", argv=b"ros2\0bag\0record\0",
                               maps=self.mapping())
            result = observer.ProcessSampler(root, clock_ticks=100, page_size=4096).sample(1.)
            self.assertEqual(result["groups"]["gazebo"]["process_count"], 0)
            self.assertEqual(result["groups"]["recorder"]["process_count"], 1)
            self.assertEqual(result["maps_fallback"]["checks"], 4)

    def test_maps_work_is_bounded_and_deferred_processes_are_checked_later(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid in (10, 11):
                self.write_process(root, pid, 100, comm="ruby", argv=b"runtime_world.sdf\0",
                                   maps=self.mapping())
            sampler = observer.ProcessSampler(root, clock_ticks=100, page_size=4096,
                                              maps_checks_per_sample=1)
            first = sampler.sample(1.)
            self.assertEqual(first["groups"]["gazebo"]["process_count"], 1)
            self.assertEqual(first["maps_fallback"]["checks"], 1)
            self.assertEqual(first["maps_fallback"]["deferred_checks"], 1)
            second = sampler.sample(2.)
            self.assertEqual(second["groups"]["gazebo"]["process_count"], 2)
            self.assertEqual(second["maps_fallback"]["checks"], 1)
            self.write_process(root, 12, 100, comm="ruby", argv=b"runtime_world.sdf\0",
                               maps=b"x" * 256 + b"\n" + self.mapping())
            bounded = observer.ProcessSampler(root, clock_ticks=100, page_size=4096, maps_max_bytes=128).sample(1.)
            self.assertEqual(bounded["groups"]["gazebo"]["process_count"], 2)
            self.assertEqual(bounded["maps_fallback"]["truncated_checks"], 1)
            self.assertLessEqual(bounded["maps_fallback"]["bytes_inspected"], 3 * 128)

    def test_exit_or_identity_change_during_maps_read_cannot_attribute_old_process(self):
        for change in ("exit", "reuse"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                process = self.write_process(root, 635, 100, comm="ruby", argv=b"runtime_world.sdf\0",
                                             maps=self.mapping())
                sampler = observer.ProcessSampler(root, clock_ticks=100, page_size=4096)
                original = sampler._gazebo_from_maps

                def read_then_change(directory):
                    result = original(directory)
                    if change == "exit":
                        (process / "stat").unlink()
                    else:
                        self.write_process(root, 635, 2000, start_ticks=99, comm="ruby",
                                           argv=b"runtime_world.sdf\0", maps=self.mapping(b"libother.so"))
                    return result

                with patch.object(sampler, "_gazebo_from_maps", side_effect=read_then_change):
                    result = sampler.sample(1.)
                self.assertEqual(result["groups"]["gazebo"]["process_count"], 0)
                self.assertGreater(result["read_error_count"], 0)
                after = sampler.sample(2.)
                self.assertEqual(after["groups"]["gazebo"]["process_count"], 0)

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
