"""Narrow observer accounting/output bounds; no ROS, simulator or bag."""
import importlib.util
import json
from pathlib import Path
import queue
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("link_observer_fixture", ROOT / "scripts/observe_ros_link.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


class LinkObserverTests(unittest.TestCase):
    def test_receipt_gaps_source_clock_and_missing_samples_stay_distinct(self):
        counter = observer.TopicCounters()
        empty = counter.snapshot(1_000_000_000)
        self.assertIsNone(empty["receipt_age_wall_s"])
        self.assertIsNone(empty["max_completed_receipt_gap_wall_s"])
        counter.receive(1_000_000_000, {"px4_timestamp_us": 77}, 9_000_000_000)
        counter.receive(1_250_000_000, {"px4_timestamp_us": 88}, 9_000_000_000)
        first = counter.snapshot(2_000_000_000)
        self.assertEqual(first["received_total"], 2)
        self.assertEqual(first["received_this_window"], 2)
        self.assertAlmostEqual(first["receipt_age_wall_s"], .75)
        self.assertAlmostEqual(first["max_completed_receipt_gap_wall_s"], .25)
        self.assertEqual(first["last_source_fields"], {"px4_timestamp_us": 88})
        self.assertEqual(first["latest_clock_at_receipt_ns"], 9_000_000_000)
        second = counter.snapshot(3_000_000_000)
        self.assertEqual(second["received_this_window"], 0)
        self.assertIsNone(second["window_max_completed_receipt_gap_wall_s"])
        self.assertAlmostEqual(second["receipt_age_wall_s"], 1.75)

    def test_longest_mount_match_distinguishes_ext4_from_drvfs(self):
        mountinfo = "80 65 8:48 / / rw - ext4 /dev/sdd rw\n81 80 0:1 / /mnt/d rw - 9p D:\\ rw\n"
        self.assertEqual(observer.mount_information("/tmp/probe-new", mountinfo)["filesystem"], "ext4")
        self.assertEqual(observer.mount_information("/mnt/d/probe-new", mountinfo)["filesystem"], "9p")

    def test_bounded_writer_flushes_valid_records_and_marks_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "aggregates.jsonl"
            writer = observer.BoundedWriter(path, max_bytes=100)
            self.assertTrue(writer.submit({"event": "SMALL", "count": 1}))
            self.assertTrue(writer.submit({"event": "EXCEEDS_LIMIT", "payload": "x" * 200}))
            status = writer.finish()
            self.assertFalse(status["writer_alive"])
            self.assertIsNone(status["error"])
            self.assertTrue(status["limit_reached"])
            self.assertLessEqual(path.stat().st_size, 100)
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records, [{"event": "SMALL", "count": 1}])

    def test_full_queue_drops_without_waiting_for_io(self):
        writer = observer.BoundedWriter.__new__(observer.BoundedWriter)
        writer.queue, writer.dropped = queue.Queue(maxsize=1), 0
        writer.queue.put_nowait({"event": "occupied"})
        self.assertFalse(writer.submit({"event": "would_block"}))
        self.assertEqual(writer.dropped, 1)
        self.assertEqual(writer.queue.get_nowait(), {"event": "occupied"})


if __name__ == "__main__":
    unittest.main()
