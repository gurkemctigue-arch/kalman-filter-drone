"""Independent Linux resource and optional ROS receipt observer, sampled at 1 Hz.

Run as its own process, never inside a flight supervisor executor. Host samples
use monotonic time even when ROS simulation time pauses. Output must be a new
directory under /mnt/d; bounded asynchronous writes expose slow disk I/O and
dropped aggregates. This observer publishes no ROS messages and changes no
process, simulator setting, control parameter or guard threshold.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import threading
import time


def _sibling(name):
    spec = importlib.util.spec_from_file_location("runtime_health_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse the existing reviewed proc sampler, receipt accounting and bounded I/O.
host_observer = _sibling("watch_sim_resources")
link_observer = _sibling("observe_ros_link")
GROUPS = ("gazebo", "px4", "python", "recorder")
GAZEBO_SIM_LIBRARY = re.compile(rb"libgz-sim[0-9]+(?:-gz)?\.so(?:\.[0-9]+)*")


def process_group(comm, argv):
    """Classify privately; never return or log a process command line."""
    names = [Path(part).name.lower() for part in argv[:8]]
    executable = names[0] if names else comm.lower()
    if ("rosbag2_recorder" in comm.lower() or "rosbag2_recorder" in names
            or any(names[index:index + 2] == ["bag", "record"] for index in range(len(names) - 1))):
        return "recorder"
    if (executable in {"gz", "gzserver", "gzclient", "gz-sim-server", "gz-sim-gui"}
            or comm.lower().startswith(("gz sim", "gz-sim"))
            or any(names[index:index + 2] == ["gz", "sim"] for index in range(len(names) - 1))):
        return "gazebo"
    if executable == "px4" or comm.lower() == "px4":
        return "px4"
    if executable.startswith("python") or comm.lower().startswith("python"):
        return "python"
    return None


def parse_process_stat(raw):
    # comm can contain spaces and parentheses. Fields after its final ')' begin
    # at proc stat field 3; avoid splitting the entire line into shifted fields.
    _, separator, rest = raw.rpartition(")")
    fields = rest.split()
    if not separator or len(fields) < 22:
        raise ValueError("incomplete proc stat")
    return {"cpu_ticks": int(fields[11]) + int(fields[12]),
            "start_ticks": int(fields[19]), "rss_pages": int(fields[21])}


class ProcessSampler:
    """Disjoint group aggregates; CPU 100 percent means one logical CPU."""
    def __init__(self, proc_root=Path("/proc"), clock_ticks=None, page_size=None, *,
                 maps_rescan_s=30., maps_checks_per_sample=8, maps_max_bytes=1024 * 1024):
        self.proc_root = Path(proc_root)
        self.clock_ticks = clock_ticks if clock_ticks is not None else os.sysconf("SC_CLK_TCK")
        self.page_size = page_size if page_size is not None else os.sysconf("SC_PAGE_SIZE")
        if (not math.isfinite(maps_rescan_s) or maps_rescan_s <= 0
                or maps_checks_per_sample < 1 or maps_max_bytes < 1):
            raise ValueError("maps scan interval, count and byte budget must be positive")
        self.maps_rescan_s = maps_rescan_s
        self.maps_checks_per_sample = maps_checks_per_sample
        self.maps_max_bytes = maps_max_bytes
        self._maps_cache = {}  # (PID, kernel start ticks), never paths or maps text.
        self.previous = {}
        self.previous_s = None

    def _gazebo_from_maps(self, directory):
        """Inspect bounded mapping bytes privately; only exact library basenames count."""
        consumed = 0
        with (directory / "maps").open("rb") as handle:
            while consumed <= self.maps_max_bytes:
                line = handle.readline(self.maps_max_bytes - consumed + 1)
                if not line:
                    return None, consumed, False
                consumed += len(line)
                if consumed > self.maps_max_bytes:
                    return None, self.maps_max_bytes, True
                fields = line.rstrip(b"\n").split(None, 5)
                if len(fields) != 6 or not fields[4].isdigit() or int(fields[4]) == 0:
                    continue
                path = fields[5]
                if path.endswith(b" (deleted)"):
                    path = path[:-10]
                if path.startswith(b"/") and GAZEBO_SIM_LIBRARY.fullmatch(path.rsplit(b"/", 1)[-1]):
                    return "gazebo", consumed, False
        return None, consumed, True

    def sample(self, monotonic_s):
        groups = {name: {"process_count": 0, "rss_bytes": 0, "cpu_percent_one_core": None,
                         "cpu_observed_processes": 0, "new_or_reused_processes": 0} for name in GROUPS}
        current, cpu_delta = {}, {name: 0 for name in GROUPS}
        errors, classified, pending = 0, [], []
        seen = set()
        maps_audit = {"checks": 0, "cache_hits": 0, "bytes_inspected": 0,
                      "truncated_checks": 0, "deferred_checks": 0,
                      "rescan_interval_wall_s": self.maps_rescan_s,
                      "max_checks_per_sample": self.maps_checks_per_sample,
                      "max_bytes_per_check": self.maps_max_bytes}
        elapsed = None if self.previous_s is None else monotonic_s - self.previous_s
        for directory in self.proc_root.iterdir():
            if not directory.name.isdecimal():
                continue
            try:
                stat = parse_process_stat((directory / "stat").read_text(encoding="ascii"))
                comm = (directory / "comm").read_text(encoding="utf-8", errors="replace").strip()
                with (directory / "cmdline").open("rb") as handle:
                    argv = [part.decode("utf-8", errors="replace") for part in handle.read(8192).split(b"\0") if part]
                group = process_group(comm, argv)
            except (OSError, ValueError, IndexError):
                errors += 1  # Exiting processes/permissions are observations, not zero usage.
                continue
            pid = int(directory.name)
            if group is not None:
                classified.append((pid, stat, group))
                continue
            identity = (pid, stat["start_ticks"])
            seen.add(identity)
            cached = self._maps_cache.get(identity)
            age = None if cached is None else monotonic_s - cached["checked_s"]
            if age is not None and 0 <= age < self.maps_rescan_s:
                maps_audit["cache_hits"] += 1
                if cached["group"] is not None:
                    pending.append((directory, stat, identity, cached, False))
                continue
            pending.append((directory, stat, identity, cached, True))

        # Recheck known Gazebo identities first, then unseen/oldest candidates.
        # A large host process table cannot trigger a full maps scan each second.
        pending.sort(key=lambda item: (item[3] is None or item[3]["group"] != "gazebo",
                                       float("-inf") if item[3] is None else item[3]["checked_s"]))
        for directory, stat, identity, cached, needs_scan in pending:
            if needs_scan and maps_audit["checks"] >= self.maps_checks_per_sample:
                maps_audit["deferred_checks"] += 1
                continue
            try:
                if needs_scan:
                    maps_audit["checks"] += 1
                    try:
                        group, consumed, truncated = self._gazebo_from_maps(directory)
                        maps_audit["bytes_inspected"] += consumed
                        maps_audit["truncated_checks"] += int(truncated)
                    except OSError:
                        errors += 1
                        group = None
                else:
                    group = cached["group"]
                after = parse_process_stat((directory / "stat").read_text(encoding="ascii"))
                if after["start_ticks"] != identity[1]:
                    raise ValueError("process identity changed during private classification")
            except (OSError, ValueError, IndexError):
                errors += 1
                self._maps_cache.pop(identity, None)
                continue
            if needs_scan:
                self._maps_cache[identity] = {"checked_s": monotonic_s, "group": group}
            if group is not None:
                classified.append((identity[0], after, group))
        self._maps_cache = {identity: value for identity, value in self._maps_cache.items() if identity in seen}

        for pid, stat, group in classified:
            current[pid] = {**stat, "group": group}
            groups[group]["process_count"] += 1
            groups[group]["rss_bytes"] += max(0, stat["rss_pages"]) * self.page_size
            previous = self.previous.get(pid)
            if (elapsed is not None and elapsed > 0 and previous is not None
                    and previous["start_ticks"] == stat["start_ticks"] and previous["group"] == group
                    and stat["cpu_ticks"] >= previous["cpu_ticks"]):
                cpu_delta[group] += stat["cpu_ticks"] - previous["cpu_ticks"]
                groups[group]["cpu_observed_processes"] += 1
            else:
                groups[group]["new_or_reused_processes"] += 1
        for group, aggregate in groups.items():
            if elapsed is not None and elapsed > 0 and aggregate["cpu_observed_processes"]:
                aggregate["cpu_percent_one_core"] = cpu_delta[group] / self.clock_ticks / elapsed * 100.
        self.previous, self.previous_s = current, monotonic_s
        return {"interval_monotonic_s": elapsed, "groups": groups, "read_error_count": errors,
                "logical_cpu_count": os.cpu_count(), "process_commands_recorded": False,
                "maps_fallback": maps_audit,
                "semantics": "Groups are disjoint; RSS sums shared pages per process. CPU excludes unobserved lifetimes and new/reused PIDs; 100% is one core, not whole-host percentage. Unclassified processes use bounded, identity-cached Gazebo library checks; deferred, unreadable or truncated checks may undercount Gazebo."}


class RosTimingState:
    def __init__(self):
        self.lock = threading.Lock()
        self.counters = {name: link_observer.TopicCounters() for name in ("clock", "vehicle_status")}
        self.latest_clock_ns = None
        self.previous_snapshot_ns = self.previous_clock_ns = None
        self.clock_regressions = 0

    def receive_clock(self, source_ns, receipt_ns):
        with self.lock:
            if self.latest_clock_ns is not None and source_ns < self.latest_clock_ns:
                self.clock_regressions += 1
            self.latest_clock_ns = source_ns
            self.counters["clock"].receive(receipt_ns, {"clock_source_ns": source_ns}, source_ns)

    def receive_status(self, source_us, arming_state, nav_state, failsafe, receipt_ns):
        with self.lock:
            self.counters["vehicle_status"].receive(receipt_ns, {"px4_timestamp_us": source_us,
                "source_domain": "RAW_PX4_US_NOT_INDEPENDENTLY_VALIDATED", "arming_state": arming_state,
                "nav_state": nav_state, "failsafe": failsafe}, self.latest_clock_ns)

    def snapshot(self, now_ns=None):
        with self.lock:
            now_ns = time.monotonic_ns() if now_ns is None else now_ns
            elapsed = None if self.previous_snapshot_ns is None else (now_ns - self.previous_snapshot_ns) * 1e-9
            advance = None if self.previous_clock_ns is None or self.latest_clock_ns is None else (self.latest_clock_ns - self.previous_clock_ns) * 1e-9
            ratio = advance / elapsed if elapsed is not None and elapsed > 0 and advance is not None and advance >= 0 else None
            row = {"snapshot_monotonic_ns": now_ns, "latest_clock_source_ns": self.latest_clock_ns,
                   "clock_source_regressions": self.clock_regressions, "clock_advance_s": advance,
                   "observation_interval_monotonic_s": elapsed, "sim_seconds_per_monotonic_second_observed": ratio,
                   "topics": {name: counter.snapshot(now_ns) for name, counter in self.counters.items()}}
            self.previous_snapshot_ns, self.previous_clock_ns = now_ns, self.latest_clock_ns
            return row


class RosReceiver:
    """Own context and executor thread, independent of all control executors."""
    def __init__(self, state, status_topic):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from rosgraph_msgs.msg import Clock
        from px4_msgs.msg import VehicleStatus

        self.rclpy, self.context = rclpy, Context()
        self.stopping = threading.Event()
        self.error = None
        rclpy.init(args=[], context=self.context)
        self.node = Node("independent_runtime_health_observer", context=self.context,
                         enable_rosout=False, start_parameter_services=False, use_global_arguments=False)
        self.node.create_subscription(Clock, "/clock", lambda msg: state.receive_clock(
            int(msg.clock.sec) * 1_000_000_000 + int(msg.clock.nanosec), time.monotonic_ns()), qos_profile_sensor_data)
        self.node.create_subscription(VehicleStatus, status_topic, lambda msg: state.receive_status(
            int(msg.timestamp), int(msg.arming_state), int(msg.nav_state), bool(msg.failsafe), time.monotonic_ns()), qos_profile_sensor_data)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self._spin, name="runtime_health_ros_receiver", daemon=True)

    def _spin(self):
        try:
            while not self.stopping.is_set() and self.context.ok():
                self.executor.spin_once(timeout_sec=.1)
        except Exception as error:
            self.error = type(error).__name__  # Never serialize arbitrary callback/command text.

    def start(self):
        self.thread.start()

    def finish(self):
        self.stopping.set()
        self.thread.join(timeout=2.)
        if self.thread.is_alive():
            return {"thread_alive": True, "error": self.error}
        self.executor.shutdown(timeout_sec=1.)
        self.node.destroy_node()
        if self.context.ok():
            self.rclpy.shutdown(context=self.context)
        return {"thread_alive": False, "error": self.error}


def new_output_directory(path):
    path = Path(path).resolve()
    d_mount = Path("/mnt/d").resolve()
    if path == d_mount or not path.is_relative_to(d_mount) or path.exists():
        raise ValueError("Use a new nonexistent directory below /mnt/d; evidence is never overwritten")
    mount = link_observer.mount_information(path)
    path.mkdir(parents=True)
    return path, mount


def disk_snapshot(paths):
    output = {}
    for name, path in paths.items():
        try:
            usage = shutil.disk_usage(path)
            output[name] = {"path": str(path), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
        except OSError as error:
            output[name] = {"path": str(path), "error": type(error).__name__}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-wall-s", type=float, default=600.)
    parser.add_argument("--max-log-mib", type=int, default=16)
    parser.add_argument("--ros", action="store_true", help="Subscribe read-only to /clock and VehicleStatus in this observer's own executor thread")
    parser.add_argument("--status-topic", default="/fmu/out/vehicle_status_v1", help="Use /fmu/out/vehicle_status if the installed firmware exports the unversioned name")
    args = parser.parse_args()
    if sys.platform != "linux" or not Path("/proc/meminfo").is_file():
        parser.error("Run this observer as a separate Linux process")
    if not math.isfinite(args.duration_wall_s) or not 1 <= args.duration_wall_s <= 7200:
        parser.error("--duration-wall-s must be in [1,7200]")
    if not 1 <= args.max_log_mib <= 64:
        parser.error("--max-log-mib must be in [1,64]")
    if not args.status_topic.startswith("/") or any(char.isspace() for char in args.status_topic):
        parser.error("--status-topic must be an absolute ROS topic name")
    state = RosTimingState() if args.ros else None
    receiver = None
    try:
        # Resolve optional message imports before creating output evidence.
        receiver = RosReceiver(state, args.status_topic) if args.ros else None
        directory, mount = new_output_directory(args.output_dir)
    except (OSError, ValueError, ImportError) as error:
        if receiver is not None:
            receiver.node.destroy_node()
            receiver.rclpy.shutdown(context=receiver.context)
        parser.error(f"Observer setup failed: {type(error).__name__}: {error}")
    writer = link_observer.BoundedWriter(directory / "health.jsonl", args.max_log_mib * 1024**2)
    stopped = threading.Event()
    signal_names = []
    previous_handlers = {}

    def request_stop(signum, _frame):
        signal_names.append(signal.Signals(signum).name)
        stopped.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_stop)
    started = time.monotonic()
    reason, receiver_end = "duration_reached", None
    samples, collected, previous, next_sample = 0, 0, None, started
    sampler = ProcessSampler()
    started_row = {"schema_version": 1, "event": "RUNTIME_HEALTH_OBSERVER_STARTED", "utc": link_observer.utc_now(),
        "wall_time_ns": time.time_ns(), "monotonic_s": started, "duration_wall_s": args.duration_wall_s, "period_wall_s": 1.,
        "own_pid": os.getpid(), "output_mount": mount, "ros_enabled": args.ros,
        "ros_topics": ["/clock", args.status_topic] if args.ros else [], "ros_qos": "sensor_data: best_effort, volatile, keep_last depth 5" if args.ros else None,
        "source_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                          for name in (Path(__file__).name, "watch_sim_resources.py", "observe_ros_link.py")},
        "privacy": "No process command lines, environment variables or command arguments are serialized.",
        "claim_boundary": "Independent observer callback timing is not flight-supervisor callback timing. No simulator/control/guard change or flight-acceptance claim."}
    writer.submit(started_row)
    if receiver is not None:
        receiver.start()
    try:
        while not stopped.is_set() and time.monotonic() - started < args.duration_wall_s:
            now = time.monotonic()
            if now < next_sample:
                stopped.wait(min(next_sample - now, max(0., args.duration_wall_s - (now - started))))
                continue
            raw_host, previous = host_observer.sample(previous)
            row = {"schema_version": 1, "event": "RUNTIME_HEALTH_SAMPLE", "wall_time_ns": time.time_ns(),
                   "monotonic_s": previous, "elapsed_wall_s": previous - started,
                   "utc": raw_host.pop("utc"), "sample_gap_wall_s": raw_host.pop("sample_gap_wall_s"),
                   "host_proc": raw_host, "processes": sampler.sample(previous),
                   "disk": disk_snapshot({"linux_root": Path("/"), "output_d_mount": directory}),
                   "ros": state.snapshot() if state is not None else {"enabled": False},
                   "ros_receiver": {"thread_alive": receiver.thread.is_alive(), "error": receiver.error} if receiver is not None else None,
                   "writer": writer.status()}
            row["collection_duration_wall_s"] = time.monotonic() - previous
            collected += 1
            if writer.submit(row):
                samples += 1
            status = writer.status()
            if status["error"] or status["limit_reached"]:
                reason = "writer_error" if status["error"] else "output_byte_limit"
                break
            if receiver is not None and (receiver.error or not receiver.thread.is_alive()):
                reason = "ros_receiver_stopped"
                break
            # Never burst catch-up samples after scheduling or filesystem stalls.
            next_sample += 1.
            if next_sample <= time.monotonic():
                next_sample = time.monotonic() + 1.
        if stopped.is_set():
            reason = "signal"
    except Exception:
        reason = "observer_exception"
        raise
    finally:
        if receiver is not None:
            try:
                receiver_end = receiver.finish()
            except Exception as error:
                receiver_end = {"thread_alive": receiver.thread.is_alive(), "error": type(error).__name__}
        writer.submit({"schema_version": 1, "event": "RUNTIME_HEALTH_OBSERVER_STOPPED", "utc": link_observer.utc_now(),
                       "wall_time_ns": time.time_ns(), "monotonic_s": time.monotonic(), "reason": reason,
                       "elapsed_wall_s": time.monotonic() - started, "signals": signal_names,
                       "samples_collected": collected, "samples_submitted": samples,
                       "ros_receiver_final": receiver_end, "writer_before_flush": writer.status()})
        writer_end = writer.finish()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        result = {"output": str(directory), "reason": reason, "samples_collected": collected, "samples_submitted": samples,
                  "ros_receiver_final": receiver_end, "writer_final": writer_end}
        # If D: I/O cannot drain within the bound, report this explicitly instead
        # of claiming a complete flushed log. The writer flushes every record.
        result["flushed_cleanly"] = not (writer_end["writer_alive"] or writer_end["error"] or writer_end["limit_reached"]
                                         or writer_end["dropped_aggregates"] or receiver_end and (receiver_end["thread_alive"] or receiver_end["error"]))
        print(json.dumps(result, allow_nan=False), flush=True)
    return 0 if result["flushed_cleanly"] and reason in {"duration_reached", "signal"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
