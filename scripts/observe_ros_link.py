"""Independent, read-only ROS transport observer for an engineering probe.

No flight commands, target data, parameter clients, Gazebo truth or frozen
algorithm imports. Receive callbacks update counters only. A steady-clock
timer queues one aggregate per wall second; a bounded writer thread uses a
new local ext4 /tmp directory. Copy it to D: only after the probe has ended.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import queue
import re
import threading
import time


TOPICS = {
    "raw_px4_odometry": "/fmu/out/vehicle_odometry",
    "raw_px4_status": "/fmu/out/vehicle_status_v1",
    "clock": "/clock",
    "converted_odometry": "/vehicle/odometry",
    "flight_phase": "/tracking/flight_phase",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def mount_information(path, mountinfo=None):
    """Find the deepest Linux mount, rejecting DrvFS/9p for live output."""
    path = PurePosixPath(str(Path(path).resolve() if mountinfo is None else path))
    raw = Path("/proc/self/mountinfo").read_text(encoding="utf-8") if mountinfo is None else mountinfo
    matches = []
    for line in raw.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields, filesystem = left.split(), right.split()
        if len(fields) < 5 or len(filesystem) < 2:
            continue
        mountpoint = PurePosixPath(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), fields[4]))
        if path == mountpoint or path.is_relative_to(mountpoint):
            matches.append((len(mountpoint.parts), {"mountpoint": str(mountpoint),
                            "filesystem": filesystem[0], "device": filesystem[1]}))
    if not matches:
        raise ValueError("Could not identify the output filesystem from mountinfo")
    return max(matches, key=lambda entry: entry[0])[1]


def new_local_directory(path):
    if os.name != "posix":
        raise ValueError("Observe inside Linux after loading the ROS environment")
    path = Path(path).resolve()
    temporary = Path("/tmp").resolve()
    if path == temporary or not path.is_relative_to(temporary) or path.exists():
        raise ValueError("Use a new, nonexistent directory below /tmp; existing evidence is never overwritten")
    mount = mount_information(path)
    if mount["filesystem"] != "ext4":
        raise ValueError("Live observer output requires local ext4, got: " + mount["filesystem"])
    path.mkdir(parents=True)
    return path, mount


class TopicCounters:
    def __init__(self):
        self.total = self.window_count = 0
        self.first_ns = self.last_ns = None
        self.maximum_gap_ns = self.window_gap_ns = self.window_gaps = 0
        self.source = None
        self.clock_at_receipt_ns = None

    def receive(self, receipt_ns, source, clock_ns):
        if self.last_ns is not None:
            gap = max(0, receipt_ns - self.last_ns)
            self.maximum_gap_ns = max(self.maximum_gap_ns, gap)
            self.window_gap_ns = max(self.window_gap_ns, gap)
            self.window_gaps += 1
        else:
            self.first_ns = receipt_ns
        self.last_ns = receipt_ns
        self.total += 1
        self.window_count += 1
        self.source, self.clock_at_receipt_ns = source, clock_ns

    def snapshot(self, now_ns):
        row = {"received_total": self.total, "received_this_window": self.window_count,
               "first_receipt_monotonic_ns": self.first_ns, "last_receipt_monotonic_ns": self.last_ns,
               "receipt_age_wall_s": (now_ns - self.last_ns) * 1e-9 if self.last_ns is not None else None,
               "max_completed_receipt_gap_wall_s": self.maximum_gap_ns * 1e-9 if self.total >= 2 else None,
               "window_max_completed_receipt_gap_wall_s": self.window_gap_ns * 1e-9 if self.window_gaps else None,
               "last_source_fields": self.source, "latest_clock_at_receipt_ns": self.clock_at_receipt_ns}
        self.window_count, self.window_gap_ns, self.window_gaps = 0, 0, 0
        return row


class BoundedWriter:
    """All live filesystem I/O stays off the ROS callback/executor thread."""
    def __init__(self, path, max_bytes):
        self.path, self.max_bytes = Path(path), max_bytes
        self.queue = queue.Queue(maxsize=16)
        self.stopping = threading.Event()
        self.dropped = 0
        self.bytes_written = self.records_written = 0
        self.limit_reached = False
        self.error = None
        self.io_started_ns = None
        self.max_io_wall_s = 0.
        self.max_encode_wall_s = 0.
        self.thread = threading.Thread(target=self._run, name="observer_local_writer", daemon=True)
        self.thread.start()

    def submit(self, value):
        try:
            self.queue.put_nowait(value)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def status(self):
        # Fields are assigned atomically by one writer; this status does not
        # acquire a lock that could be held over slow filesystem operations.
        return {"queue_depth": self.queue.qsize(), "queue_capacity": 16,
                "dropped_aggregates": self.dropped, "bytes_written": self.bytes_written,
                "records_written": self.records_written, "byte_limit": self.max_bytes,
                "limit_reached": self.limit_reached, "error": self.error,
                "io_started_monotonic_ns": self.io_started_ns, "max_io_wall_s": self.max_io_wall_s,
                "max_json_encode_wall_s": self.max_encode_wall_s, "writer_alive": self.thread.is_alive()}

    def _run(self):
        try:
            with self.path.open("xb") as handle:
                while not self.stopping.is_set() or not self.queue.empty():
                    try:
                        row = self.queue.get(timeout=.1)
                    except queue.Empty:
                        continue
                    began = time.monotonic_ns()
                    encoded = (json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
                    self.max_encode_wall_s = max(self.max_encode_wall_s, (time.monotonic_ns() - began) * 1e-9)
                    if self.bytes_written + len(encoded) > self.max_bytes:
                        self.limit_reached = True
                        continue
                    self.io_started_ns = time.monotonic_ns()
                    handle.write(encoded)
                    handle.flush()
                    self.max_io_wall_s = max(self.max_io_wall_s, (time.monotonic_ns() - self.io_started_ns) * 1e-9)
                    self.io_started_ns = None
                    self.bytes_written += len(encoded)
                    self.records_written += 1
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            self.error = f"{type(error).__name__}: {error}"

    def finish(self):
        self.stopping.set()
        self.thread.join(timeout=5.)
        return self.status()


def make_observer_class():
    import rclpy
    from rclpy.clock import Clock
    from rclpy.clock_type import ClockType
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import VehicleOdometry, VehicleStatus
    from rosgraph_msgs.msg import Clock as ClockMessage
    from std_msgs.msg import String

    class LinkObserver(Node):
        def __init__(self, writer, duration_s):
            super().__init__("independent_link_observer", enable_rosout=False,
                             start_parameter_services=False, use_global_arguments=False)
            self.writer, self.duration_s = writer, duration_s
            self.started_ns = self.last_sample_ns = time.monotonic_ns()
            self.latest_clock_ns = None
            self.counters = {name: TopicCounters() for name in TOPICS}
            self.samples_submitted = 0
            qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=5,
                             reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
            self.create_subscription(VehicleOdometry, TOPICS["raw_px4_odometry"], self.on_px4_odometry, qos)
            self.create_subscription(VehicleStatus, TOPICS["raw_px4_status"], self.on_px4_status, qos)
            self.create_subscription(ClockMessage, TOPICS["clock"], self.on_clock, qos)
            self.create_subscription(Odometry, TOPICS["converted_odometry"], self.on_converted_odometry, qos)
            self.create_subscription(String, TOPICS["flight_phase"], self.on_phase, qos)
            self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
            self.create_timer(1., self.sample, clock=self.steady_clock)

        def receive(self, name, fields):
            self.counters[name].receive(time.monotonic_ns(), fields, self.latest_clock_ns)

        def on_px4_odometry(self, message):
            self.receive("raw_px4_odometry", {"px4_timestamp_us": int(message.timestamp),
                "px4_timestamp_sample_us": int(message.timestamp_sample)})

        def on_px4_status(self, message):
            self.receive("raw_px4_status", {"px4_timestamp_us": int(message.timestamp),
                "arming_state": int(message.arming_state), "nav_state": int(message.nav_state),
                "failsafe": bool(message.failsafe)})

        def on_clock(self, message):
            self.latest_clock_ns = int(message.clock.sec) * 1_000_000_000 + int(message.clock.nanosec)
            self.receive("clock", {"clock_sim_ns": self.latest_clock_ns})

        def on_converted_odometry(self, message):
            self.receive("converted_odometry", {"ros_header_stamp_ns": int(message.header.stamp.sec) * 1_000_000_000
                                                + int(message.header.stamp.nanosec)})

        def on_phase(self, message):
            self.receive("flight_phase", {"phase_text": str(message.data)[:4096]})

        def snapshot(self, event="WALL_SECOND_AGGREGATE"):
            now_ns = time.monotonic_ns()
            row = {"schema_version": 1, "event": event, "utc": utc_now(), "monotonic_ns": now_ns,
                   "elapsed_wall_s": (now_ns - self.started_ns) * 1e-9,
                   "sample_gap_wall_s": (now_ns - self.last_sample_ns) * 1e-9,
                   "latest_clock_sim_ns": self.latest_clock_ns,
                   "topics": {name: counter.snapshot(now_ns) for name, counter in self.counters.items()},
                   "writer": self.writer.status()}
            self.last_sample_ns = now_ns
            return row

        def sample(self):
            if self.writer.submit(self.snapshot()):
                self.samples_submitted += 1

        def finished(self):
            return (time.monotonic_ns() - self.started_ns) * 1e-9 >= self.duration_s

    return rclpy, LinkObserver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--duration-wall-s", type=float, default=600.)
    parser.add_argument("--max-log-mib", type=int, default=16)
    args = parser.parse_args()
    if not math.isfinite(args.duration_wall_s) or not 1 <= args.duration_wall_s <= 7200:
        parser.error("--duration-wall-s must be finite and in [1,7200]")
    if not 1 <= args.max_log_mib <= 16:
        parser.error("--max-log-mib must be in [1,16]")
    # Load message interfaces before creating any evidence directory.
    rclpy, observer_class = make_observer_class()
    from rclpy.executors import ExternalShutdownException
    try:
        directory, mount = new_local_directory(args.output_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    session = {"schema_version": 1, "created_utc": utc_now(), "topics": TOPICS, "output": str(directory),
               "output_mount": mount, "duration_wall_s": args.duration_wall_s,
               "aggregate_period_wall_s": 1., "max_log_bytes": args.max_log_mib * 1024**2,
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
               "rmw_implementation_env": os.environ.get("RMW_IMPLEMENTATION"),
               "qos": "BEST_EFFORT VOLATILE KEEP_LAST depth5; observer receives only",
               "policy": "No application/control publishers, parameter clients, GT or frozen algorithm imports; ROS infrastructure discovery/parameter-event traffic may exist; no per-message writes; no D-drive live output",
               "limits": ["Receipt time is callback execution, not kernel/DDS packet arrival",
                          "Best-effort observations can drop messages; missing receipt is not proof of missing publication",
                          "Converted odometry header uses adapter cached ROS clock; compare raw PX4 and independent native Gazebo stats",
                          "Observer steady timer and subscribers share an executor; sample gaps may reflect observer scheduling",
                          "No direct inference of watchdog cause, full-VM pause, algorithm success or safety pass"]}
    with (directory / "session.json").open("x", encoding="utf-8") as handle:
        json.dump(session, handle, ensure_ascii=False, indent=2, allow_nan=False)
    writer = BoundedWriter(directory / "aggregates.jsonl", args.max_log_mib * 1024**2)
    node, failure, initialized = None, None, False
    try:
        rclpy.init(args=[])
        initialized = True
        node = observer_class(writer, args.duration_wall_s)
        while rclpy.ok() and not node.finished():
            rclpy.spin_once(node, timeout_sec=.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if node is not None:
            writer.submit(node.snapshot("FINAL_AGGREGATE"))
            node.destroy_node()
        if initialized:
            rclpy.try_shutdown()
        writer_status = writer.finish()
        summary = {"schema_version": 1, "finished_utc": utc_now(), "failure": failure,
                   "writer": writer_status, "live_output": str(directory),
                   "status": "OBSERVER_ONLY_NO_FLIGHT_VERDICT",
                   "copy_policy": "Copy this directory to final evidence only after all independent-probe simulation processes exit"}
        with (directory / "summary.json").open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return 2 if (writer_status["error"] or writer_status["writer_alive"] or writer_status["limit_reached"]
                 or writer_status["dropped_aggregates"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
