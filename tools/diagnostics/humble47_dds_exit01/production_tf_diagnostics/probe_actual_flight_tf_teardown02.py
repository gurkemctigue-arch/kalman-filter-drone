"""Narrow production-TF/DDS teardown diagnostic; never flight/core acceptance.

Run only after sourcing the reviewed Humble environment. The production child
is the installed flight_tf executable, without replacing its node or main.
All repetitions are fresh diagnostic attempts; original flight evidence is
neither read nor rewritten. This file is an external diagnostic draft.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


SCOPE = "NARROW_PRODUCTION_FLIGHT_TF_DDS_TEARDOWN_DIAGNOSTIC_NOT_FLIGHT_ACCEPTANCE"
EXECUTION_SOURCE_BYTES = Path(__file__).read_bytes()
EXECUTION_SOURCE_SHA256 = hashlib.sha256(EXECUTION_SOURCE_BYTES).hexdigest()


def event(name, **fields):
    print(json.dumps({"event": name, "monotonic_s": time.monotonic(), **fields}), flush=True)


def source_metadata(project_root, environment_script):
    module = importlib.import_module("uav_tracking_bringup.flight_tf_node")
    from rclpy.utilities import get_rmw_implementation_identifier
    entrypoint = project_root / "ros2_ws/install/lib/uav_tracking_bringup/flight_tf"
    if not entrypoint.is_file():
        raise FileNotFoundError(entrypoint)
    source = Path(module.__file__).resolve()
    if not source.is_relative_to(project_root.resolve()):
        raise RuntimeError(f"Imported production source is outside requested root: {source}")
    bound_root = os.environ.get("STAGE1_PROJECT_ROOT")
    if not bound_root or Path(bound_root).resolve() != project_root:
        raise RuntimeError("STAGE1_PROJECT_ROOT does not identify the requested immutable project")
    if not environment_script.is_file():
        raise FileNotFoundError(environment_script)
    return {
        "harness_source": str(Path(__file__).resolve()),
        "harness_sha256": EXECUTION_SOURCE_SHA256,
        "environment_script": str(environment_script),
        "environment_script_sha256": hashlib.sha256(environment_script.read_bytes()).hexdigest(),
        "environment_script_claim": "Recorded script content; root execution command must bind actual sourcing.",
        "production_entrypoint": str(entrypoint),
        "entrypoint_sha256": hashlib.sha256(entrypoint.read_bytes()).hexdigest(),
        "entrypoint_shebang": entrypoint.read_text(encoding="utf-8").splitlines()[0],
        "imported_production_source": str(source),
        "production_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "resolved_rmw": get_rmw_implementation_identifier(),
        "rmw_environment": os.environ.get("RMW_IMPLEMENTATION"),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
        "python_executable": sys.executable,
        "environment": {name: os.environ.get(name) for name in (
            "ROS_DISTRO", "STAGE1_PROJECT_ROOT", "AMENT_PREFIX_PATH", "LD_LIBRARY_PATH", "PYTHONPATH")},
    }


def run_peer(args):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from uav_tracking.ros_lifecycle import shutdown_requests

    event("peer_source_binding", script=str(Path(__file__).resolve()), sha256=EXECUTION_SOURCE_SHA256)
    with shutdown_requests() as requested:
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        node = rclpy.create_node(f"tf_exit_probe_{args.action.replace('-', '_')}_{args.peer_index}")
        executor = SingleThreadedExecutor(context=node.context)
        executor.add_node(node)
        try:
            if args.action == "graph-peer":
                # A separate process/context supplies a real graph-discovery
                # writer. No competing /clock or sensor input is produced.
                from std_msgs.msg import String
                from tf2_msgs.msg import TFMessage
                pub = node.create_publisher(String, "/tf_exit_probe/peer_load", 10)
                node.create_subscription(String, "/tf_exit_probe/peer_load", lambda _msg: None, 10)
                node.create_timer(0.2, lambda: pub.publish(String(data=str(args.peer_index))))
                peer_counts = {"base_link": 0, "camera_link": 0}
                peer_ready = [False]

                def on_peer_tf(message):
                    for transform in message.transforms:
                        if transform.child_frame_id in peer_counts:
                            peer_counts[transform.child_frame_id] += 1
                    if not peer_ready[0] and min(peer_counts.values()) >= args.min_tf_count:
                        peer_ready[0] = True
                        event("ready", kind="independent_graph_peer_consumed_production_tf",
                              peer_index=args.peer_index, counts=dict(peer_counts))

                node.create_subscription(TFMessage, "/tf", on_peer_tf, QoSProfile(depth=100))
                event("graph_peer_created", peer_index=args.peer_index)
            else:
                from nav_msgs.msg import Odometry
                from rosgraph_msgs.msg import Clock
                from sensor_msgs.msg import JointState
                from tf2_msgs.msg import TFMessage
                from rclpy.qos import qos_profile_sensor_data

                clock_pub = node.create_publisher(
                    Clock, "/clock", QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
                odom_pub = node.create_publisher(Odometry, "/vehicle/odometry", qos_profile_sensor_data)
                joint_pub = node.create_publisher(JointState, "/gimbal/joint_states", qos_profile_sensor_data)
                counts = {"base_link": 0, "camera_link": 0, "other": 0, "static": 0}
                published = {"clock": 0, "odometry": 0, "joint": 0}
                state = {"ready": False, "next_odom": 0, "next_joint": 0, "last_stamp_ns": None}

                def on_tf(message):
                    for transform in message.transforms:
                        key = transform.child_frame_id
                        counts[key if key in ("base_link", "camera_link") else "other"] += 1
                    if not state["ready"] and min(counts["base_link"], counts["camera_link"]) >= args.min_tf_count:
                        state["ready"] = True
                        event("ready", kind="accepted_both_production_tf_routes", counts=dict(counts),
                              published=dict(published), last_source_stamp_ns=state["last_stamp_ns"])

                def on_static(message):
                    counts["static"] += len(message.transforms)

                node.create_subscription(TFMessage, "/tf", on_tf, QoSProfile(depth=100))
                node.create_subscription(TFMessage, "/tf_static", on_static,
                                         QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
                start = time.monotonic()

                def set_stamp(stamp, value):
                    stamp.sec, stamp.nanosec = divmod(int(value), 1_000_000_000)

                def tick():
                    now_ns = 2_000_000_000 + int((time.monotonic() - start) * args.clock_factor * 1e9)
                    clock = Clock()
                    set_stamp(clock.clock, now_ns)
                    clock_pub.publish(clock)
                    published["clock"] += 1
                    # Source stamps lag clock by20ms, within production age
                    # gates. No equality/arrival-order assumption is needed.
                    data_ns = now_ns - 20_000_000
                    state["last_stamp_ns"] = data_ns
                    if now_ns >= state["next_odom"]:
                        message = Odometry()
                        set_stamp(message.header.stamp, data_ns)
                        message.header.frame_id = "map"
                        message.child_frame_id = "base_link"
                        message.pose.pose.position.z = 3.0
                        message.pose.pose.orientation.w = 1.0
                        odom_pub.publish(message)
                        published["odometry"] += 1
                        state["next_odom"] = now_ns + round(1e9 / args.data_source_hz)
                    if now_ns >= state["next_joint"]:
                        message = JointState()
                        set_stamp(message.header.stamp, data_ns)
                        message.name = ["tracking_gimbal_yaw", "tracking_gimbal_pitch", "tracking_gimbal_roll"]
                        message.position = [0.1, -0.1, 0.05]
                        joint_pub.publish(message)
                        published["joint"] += 1
                        state["next_joint"] = now_ns + round(1e9 / args.data_source_hz)

                node.create_timer(1.0 / (args.clock_source_hz * args.clock_factor), tick)
                event("feeder_started", clock_factor=args.clock_factor,
                      clock_source_hz=args.clock_source_hz, data_source_hz=args.data_source_hz,
                      rate_claim="synthetic_rates_not_exact_observed_original_traffic")
            try:
                while node.context.ok() and not requested.is_set():
                    executor.spin_once(timeout_sec=0.05)
            finally:
                if args.action == "feeder":
                    event("feeder_terminal_counts", counts=counts, published=published,
                          accepted_both_routes=state["ready"])
                else:
                    event("graph_peer_terminal_counts", counts=peer_counts, accepted_both_routes=peer_ready[0])
        finally:
            event("peer_cleanup_begin", kind=args.action)
            try:
                executor.shutdown()
            finally:
                try:
                    node.destroy_node()
                finally:
                    rclpy.try_shutdown()
            event("peer_cleanup_end", kind=args.action)


def read_events(path):
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict) and "event" in row:
                events.append(row)
        except ValueError:
            continue
    return events


def run_driver(args):
    project_root = Path(args.project_root).resolve()
    output = Path(args.output).resolve()
    if output == project_root or project_root in output.parents:
        raise ValueError("Diagnostic output must be outside the immutable project root")
    metadata = source_metadata(project_root, Path(args.environment_script).resolve())
    output.mkdir(parents=True, exist_ok=False)
    # All helper processes execute a snapshot of the driver's original bytes.
    # Original02 is frozen before handoff; this also retains an exact reviewable
    # source artifact if a later candidate03 is created elsewhere.
    script_snapshot = output / "diagnostic_source_snapshot.py"
    script_snapshot.write_bytes(EXECUTION_SOURCE_BYTES)
    metadata["harness_snapshot"] = str(script_snapshot)
    report = {"scope": SCOPE, "created_utc": datetime.now(timezone.utc).isoformat(),
              "metadata": metadata, "configuration": vars(args), "cases": [],
              "claim_limit": "Raw production-node diagnostic exits; no flight/core/formal PASS claim.",
              "status": "INCOMPLETE"}
    env = {**os.environ, "PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1"}
    script = str(script_snapshot)
    try:
        for index in range(args.repetitions):
            case_dir = output / f"attempt_{index:03d}"
            case_dir.mkdir()
            procs, streams, paths = {}, {}, {}
            signals = []
            case = {"index": index, "stop_order": args.stop_order, "signals": signals,
                    "readiness_observed": False, "cleanup_additional_sigint": [],
                    "forced_kills": [], "errors": []}

            def start(name, command):
                paths[name] = case_dir / f"{name}.log"
                streams[name] = paths[name].open("x", encoding="utf-8")
                procs[name] = subprocess.Popen(command, cwd=project_root, env=env,
                                               stdout=streams[name], stderr=subprocess.STDOUT,
                                               start_new_session=True)

            def send(names, number):
                for name in names:
                    proc = procs[name]
                    if proc.poll() is None:
                        signals.append({"name": name, "pid": proc.pid, "signal": number,
                                        "monotonic_s": time.monotonic(), "scope": "owned_process_group"})
                        try:
                            os.killpg(proc.pid, number)
                        except ProcessLookupError:
                            pass

            def wait_for(names, timeout):
                deadline = time.monotonic() + timeout
                while any(procs[name].poll() is None for name in names) and time.monotonic() < deadline:
                    time.sleep(0.02)
                return all(procs[name].poll() is not None for name in names)

            def middleware_maps(name):
                proc = procs[name]
                raw = Path(f"/proc/{proc.pid}/maps").read_text(encoding="utf-8")
                markers = ("libfastrtps", "libfastcdr", "librmw_", "librcl", "_rclpy_pybind11")
                rows = [line for line in raw.splitlines() if any(marker in line for marker in markers)]
                if not rows:
                    raise RuntimeError(f"No loaded middleware mappings found for {name}")
                content = "\n".join(rows) + "\n"
                path = case_dir / f"{name}.middleware_maps.txt"
                path.write_text(content, encoding="utf-8")
                return {"pid": proc.pid, "captured_monotonic_s": time.monotonic(), "path": str(path),
                        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        "loaded_paths": sorted({line.split(maxsplit=5)[-1] for line in rows})}

            try:
                common = ["--clock-factor", str(args.clock_factor), "--clock-source-hz", str(args.clock_source_hz),
                          "--data-source-hz", str(args.data_source_hz), "--min-tf-count", str(args.min_tf_count)]
                start("feeder", [sys.executable, "-B", script, "feeder", *common])
                for peer in range(args.peer_count):
                    start(f"graph_peer_{peer}", [sys.executable, "-B", script, "graph-peer",
                          "--peer-index", str(peer), "--min-tf-count", str(args.min_tf_count)])
                command = [metadata["production_entrypoint"], "--ros-args", "-p", "use_sim_time:=true",
                           "-p", "camera_mount_mode:=gimbal"]
                case["production_command"] = command
                start("flight_tf", command)
                deadline = time.monotonic() + args.ready_timeout_s
                while time.monotonic() < deadline:
                    if any(proc.poll() is not None for proc in procs.values()):
                        raise RuntimeError("Child exited before readiness")
                    feeder_ready = any(row["event"] == "ready" for row in read_events(paths["feeder"]))
                    peers_ready = all(any(row["event"] == "ready" for row in read_events(paths[name]))
                                      for name in procs if name.startswith("graph_peer_"))
                    if feeder_ready and peers_ready:
                        case["readiness_observed"] = True
                        break
                    time.sleep(0.05)
                if not case["readiness_observed"]:
                    raise TimeoutError("Production map/base and base/camera routes not both observed")
                case["middleware_mappings"] = {name: middleware_maps(name) for name in ("flight_tf", "feeder")}
                peer_bindings = {name: [row for row in read_events(path) if row["event"] == "peer_source_binding"]
                                 for name, path in paths.items() if name != "flight_tf"}
                case["peer_source_bindings"] = peer_bindings
                if not all(len(rows) == 1 and rows[0]["sha256"] == EXECUTION_SOURCE_SHA256
                           for rows in peer_bindings.values()):
                    raise RuntimeError("A diagnostic peer source differs from the retained snapshot")
                deadline = time.monotonic() + args.active_wall_s
                while time.monotonic() < deadline:
                    if any(proc.poll() is not None for proc in procs.values()):
                        raise RuntimeError("Child exited during active diagnostic interval")
                    time.sleep(0.02)
                peers = [name for name in procs if name != "flight_tf"]
                if args.stop_order == "child-first":
                    send(["flight_tf"], signal.SIGINT)
                    if not wait_for(["flight_tf"], args.stop_timeout_s):
                        raise TimeoutError("Production child did not stop while peers remained live")
                    send(peers, signal.SIGINT)
                elif args.stop_order == "peers-first":
                    send(peers, signal.SIGINT)
                    if not wait_for(peers, args.stop_timeout_s):
                        raise TimeoutError("Peers did not stop before production child")
                    send(["flight_tf"], signal.SIGINT)
                else:
                    send([*peers, "flight_tf"], signal.SIGINT)
                if not wait_for(["flight_tf"], args.stop_timeout_s):
                    raise TimeoutError("Production child stop deadline exceeded")
            except Exception as exc:
                case["errors"].append(f"{type(exc).__name__}:{exc}")
            finally:
                # Normal schedules send one SIGINT per process. A second SIGINT
                # after a helper restores its original handler can terminate it
                # during Python finalization and fabricate a -2 diagnostic exit.
                wait_for(list(procs), args.stop_timeout_s)
                slow = [name for name, proc in procs.items() if proc.poll() is None]
                if slow:
                    case["cleanup_additional_sigint"] = slow
                    case["errors"].append(f"CleanupDeadlineExceeded:{slow}")
                    send(slow, signal.SIGINT)
                    wait_for(slow, args.stop_timeout_s)
                remaining = [name for name, proc in procs.items() if proc.poll() is None]
                case["forced_kills"] = remaining
                send(remaining, signal.SIGKILL)
                for name, proc in procs.items():
                    proc.wait(timeout=5)
                for stream in streams.values():
                    stream.close()
                case["raw_exit_codes"] = {name: proc.returncode for name, proc in procs.items()}
                case["feeder_events"] = read_events(paths["feeder"]) if "feeder" in paths else []
                case["graph_peer_events"] = {name: read_events(path) for name, path in paths.items()
                                            if name.startswith("graph_peer_")}
                case["logs"] = {name: str(path) for name, path in paths.items()}
                case["diagnostic_clean_exit"] = (case["readiness_observed"] and not case["errors"]
                    and not slow and not remaining and all(proc.returncode == 0 for proc in procs.values()))
                report["cases"].append(case)
                (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            event("diagnostic_attempt", index=index, clean=case["diagnostic_clean_exit"],
                  raw_exit_codes=case["raw_exit_codes"], errors=case["errors"])
            if not case["diagnostic_clean_exit"]:
                break  # Preserve the first fault; do not generate unbounded cores.
        complete = len(report["cases"]) == args.repetitions and all(c["diagnostic_clean_exit"] for c in report["cases"])
        report["status"] = "NO_CRASH_OBSERVED_IN_FINITE_DIAGNOSTIC" if complete else "FAULT_OBSERVED_OR_INCOMPLETE"
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    event("diagnostic_terminal", status=report["status"], cases=len(report["cases"]), output=str(output))
    return 0 if complete else 2


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "feeder", "graph-peer"])
    parser.add_argument("--project-root")
    parser.add_argument("--environment-script")
    parser.add_argument("--output")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--peer-count", type=int, default=4)
    parser.add_argument("--peer-index", type=int, default=0)
    parser.add_argument("--stop-order", choices=["simultaneous", "child-first", "peers-first"], default="simultaneous")
    parser.add_argument("--clock-factor", type=float, default=0.125)
    parser.add_argument("--clock-source-hz", type=float, default=250.0)
    parser.add_argument("--data-source-hz", type=float, default=50.0)
    parser.add_argument("--min-tf-count", type=int, default=5)
    parser.add_argument("--active-wall-s", type=float, default=1.0)
    parser.add_argument("--ready-timeout-s", type=float, default=20.0)
    parser.add_argument("--stop-timeout-s", type=float, default=5.0)
    args = parser.parse_args()
    if args.action == "run" and (not args.project_root or not args.output or not args.environment_script):
        parser.error("run requires --project-root, --environment-script and a new external --output directory")
    if not 1 <= args.repetitions <= 200 or not 0 <= args.peer_count <= 16 or args.min_tf_count < 1:
        parser.error("invalid finite repetition/peer/count bounds")
    if min(args.clock_factor, args.clock_source_hz, args.data_source_hz) <= 0:
        parser.error("rates must be positive")
    if not all(0 < value <= 60 for value in (args.active_wall_s, args.ready_timeout_s, args.stop_timeout_s)):
        parser.error("individual diagnostic intervals must be between0 and60 seconds")
    return args


if __name__ == "__main__":
    parsed = arguments()
    if parsed.action == "run":
        raise SystemExit(run_driver(parsed))
    run_peer(parsed)
