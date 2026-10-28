#!/usr/bin/env python3
"""Owned, isolated real RGB-D Gazebo shutdown probe; no ROS/PX4/YOLO.

The /server_control request and stop field are verified against gz-sim 8.15
ServerPrivate.cc (446a44335a45b704b4d36dabcc5508ee34eeb3d8) and msgs10.
An ACK is never a clean-exit verdict. Any crash or cleanup escalation fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid


def server_stop_command():
    """Exact upstream API; caller must supply an owned unique partition."""
    return ["gz", "service", "-s", "/server_control", "--reqtype", "gz.msgs.ServerControl",
            "--reptype", "gz.msgs.Boolean", "--timeout", "5000", "--req", "stop: true"]


def response_acknowledged(returncode, output):
    return returncode == 0 and re.search(r"\bdata\s*:\s*true\b", output) is not None


def owned_environment(partition, resource_paths, plugin_paths, lp_threads):
    if not re.fullmatch(r"uav_shutdown_smoke_[a-f0-9]{32}", partition):
        raise ValueError("Only a new privately owned smoke partition is allowed")
    env = dict(os.environ, GZ_PARTITION=partition, GZ_IP="127.0.0.1",
               LP_NUM_THREADS=str(lp_threads), OMP_NUM_THREADS="2")
    for key, additions in (("GZ_SIM_RESOURCE_PATH", resource_paths), ("GZ_SIM_SYSTEM_PLUGIN_PATH", plugin_paths)):
        env[key] = os.pathsep.join([*(str(Path(p).resolve()) for p in additions), env.get(key, "")]).rstrip(os.pathsep)
    return env


def rendering_mappings(pid):
    """Capture paths/ranges, never process memory or the full environment."""
    selected = []
    mappings = Path(f"/proc/{pid}/maps").read_text().splitlines()
    for line in mappings:
        if any(token in line.lower() for token in ("/dri/", "mesa", "ogre", "libegl", "libglx", "libgz-rendering",
                                                    "d3d12", "dxcore", "libllvm", "libglapi")):
            selected.append(line)
    files = sorted({line.split(maxsplit=5)[-1] for line in selected if len(line.split(maxsplit=5)) == 6})
    hashes = {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in files if Path(name).is_file()}
    return {"mappings":selected, "library_sha256":hashes,
            "all_file_backed_mappings":[line for line in mappings if len(line.split(maxsplit=5)) == 6
                                         and line.split(maxsplit=5)[-1].startswith("/")]}


def run(args):
    if os.name != "posix":
        raise RuntimeError("Run this probe in the isolated Ubuntu environment")
    world = args.world.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    partition = "uav_shutdown_smoke_" + uuid.uuid4().hex
    env = owned_environment(partition, args.resource_path, args.plugin_path, args.lp_threads)
    gazebo_env = dict(env)
    if args.software_rendering:
        gazebo_env.update(GALLIUM_DRIVER="llvmpipe", MESA_LOADER_DRIVER_OVERRIDE="swrast", LIBGL_ALWAYS_SOFTWARE="1")
    driver_registration = None
    if args.pin_driver is not None:
        driver = args.pin_driver.resolve(strict=True)
        dependencies = subprocess.run(["ldd", str(driver)], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=10.)
        (output / "driver_dependencies.log").write_text(dependencies.stdout)
        if dependencies.returncode != 0 or "not found" in dependencies.stdout:
            raise RuntimeError("Pinned rendering driver dependencies do not resolve")
        driver_registration = {"path":str(driver), "sha256":hashlib.sha256(driver.read_bytes()).hexdigest()}
        # Keep the actual DRI library resident through render-thread TLS cleanup.
        # Only Gazebo receives this variable; the probe and service CLI do not.
        gazebo_env["LD_PRELOAD"] = os.pathsep.join([str(driver), env.get("LD_PRELOAD", "")]).rstrip(os.pathsep)
    # Transport's process singleton must see the private partition at import.
    os.environ.update({key:env[key] for key in ("GZ_PARTITION", "GZ_IP")})
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.server_control_pb2 import ServerControl
    if ServerControl.DESCRIPTOR.fields_by_name["stop"].number != 6:
        raise RuntimeError("Installed ServerControl schema does not match verified stop API")
    node = Node()
    lock = threading.Lock()
    streams = {topic:{"frames":0, "first_source_s":None, "last_source_s":None,
                      "width":None, "height":None, "data_size":None} for topic in args.image_topic}

    def callback_for(topic):
        def receive(message):
            if message.width <= 0 or message.height <= 0 or not message.data:
                return
            stamp = message.header.stamp.sec + message.header.stamp.nsec * 1e-9
            with lock:
                item = streams[topic]
                if item["last_source_s"] is None or stamp > item["last_source_s"]:
                    item["frames"] += 1
                    if item["first_source_s"] is None:
                        item["first_source_s"] = stamp
                    item.update(last_source_s=stamp, width=message.width, height=message.height,
                                data_size=len(message.data))
        return receive
    callbacks = {topic:callback_for(topic) for topic in streams}
    for topic, callback in callbacks.items():
        node.subscribe(Image, topic, callback)
    command = ["gz", "sim", "--seed", "1", "-r", "-s", "-v", "4", "--headless-rendering", str(world)]
    report = {"schema_version":1, "probe":"REAL_RGBD_GAZEBO_SHUTDOWN", "status":"FAIL",
        "partition":partition, "world":str(world), "world_sha256":hashlib.sha256(world.read_bytes()).hexdigest(),
        "stop_mode":args.stop_mode, "command":command, "rgbd_streams":streams,
        "render_environment":{key:gazebo_env.get(key) for key in ("LP_NUM_THREADS", "OMP_NUM_THREADS", "LIBGL_ALWAYS_SOFTWARE",
            "MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER", "EGL_PLATFORM", "DISPLAY")},
        "server_control_source_commit":"446a44335a45b704b4d36dabcc5508ee34eeb3d8",
        "service_acknowledged":None, "exit_code":None, "cleanup_escalations":[], "error":None}
    report["pinned_driver"] = driver_registration
    process = None
    started = time.monotonic()
    with (output / "gazebo.log").open("w") as log:
        try:
            process = subprocess.Popen(command, env=gazebo_env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            report["owned_pid"] = process.pid
            deadline = started + args.startup_timeout
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Gazebo exited before the actual RGB-D stream gate")
                with lock:
                    ready = all(item["frames"] >= args.min_frames for item in streams.values())
                if ready and time.monotonic() - started >= args.warmup_s:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Actual RGB and depth frame gate timed out")
                time.sleep(.05)
            report["actual_rgbd_gate_passed"] = True
            report["rendering_modules_before_stop"] = rendering_mappings(process.pid)
            report["stop_requested_wall_monotonic_s"] = time.monotonic()
            if args.stop_mode == "server-control":
                service_deadline = time.monotonic() + 5.
                while "/server_control" not in node.service_list():
                    if process.poll() is not None:
                        raise RuntimeError("Owned Gazebo exited before service discovery")
                    if time.monotonic() >= service_deadline:
                        raise TimeoutError("Owned partition did not advertise verified /server_control")
                    time.sleep(.05)
                result = subprocess.run(server_stop_command(), env=env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8.)
                (output / "server_control.log").write_text(result.stdout)
                report["service_acknowledged"] = response_acknowledged(result.returncode, result.stdout)
                if not report["service_acknowledged"]:
                    raise RuntimeError("Server stop request was not acknowledged")
            else:
                os.killpg(process.pid, signal.SIGINT)
            report["exit_code"] = process.wait(timeout=args.stop_timeout)
            report["stop_completed_wall_monotonic_s"] = time.monotonic()
            # A process-group existence check catches children left by a parent.
            try:
                os.killpg(process.pid, 0)
                report["owned_process_group_remaining"] = True
            except ProcessLookupError:
                report["owned_process_group_remaining"] = False
            if report["exit_code"] != 0:
                raise RuntimeError("Gazebo shutdown returned nonzero exit code " + str(report["exit_code"]))
            if report["owned_process_group_remaining"]:
                raise RuntimeError("Owned process-group descendants remain after Gazebo exit")
            report["status"] = "PASS"
        except Exception as error:
            report["error"] = type(error).__name__ + ":" + str(error)
        finally:
            if process is not None:
                for signum, seconds in ((signal.SIGINT, 5.), (signal.SIGTERM, 3.), (signal.SIGKILL, 3.)):
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        break
                    report["cleanup_escalations"].append(signum.name)
                    os.killpg(process.pid, signum)
                    try:
                        process.wait(timeout=seconds)
                    except subprocess.TimeoutExpired:
                        pass
                report["exit_code"] = process.poll()
                try:
                    os.killpg(process.pid, 0)
                    report["owned_process_group_remaining"] = True
                except ProcessLookupError:
                    report["owned_process_group_remaining"] = False
            for topic in streams:
                node.unsubscribe(topic)
    report["wall_duration_s"] = time.monotonic() - started
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({key:report.get(key) for key in ("status", "stop_mode", "exit_code", "service_acknowledged",
        "actual_rgbd_gate_passed", "owned_process_group_remaining", "error", "wall_duration_s")}, indent=2), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resource-path", action="append", default=[])
    parser.add_argument("--plugin-path", action="append", default=[])
    parser.add_argument("--stop-mode", choices=("sigint", "server-control"), required=True)
    parser.add_argument("--lp-threads", type=int, default=4)
    parser.add_argument("--pin-driver", type=Path, default=None,
                        help="Isolated compatibility experiment: preload only the owned Gazebo process")
    parser.add_argument("--software-rendering", action="store_true",
                        help="Isolated CPU llvmpipe rendering contrast; affects only owned Gazebo")
    parser.add_argument("--warmup-s", type=float, default=5.)
    parser.add_argument("--startup-timeout", type=float, default=45.)
    parser.add_argument("--stop-timeout", type=float, default=15.)
    parser.add_argument("--min-frames", type=int, default=5)
    parser.add_argument("--image-topic", action="append", default=None)
    args = parser.parse_args(argv)
    if args.lp_threads < 1 or args.min_frames < 1 or min(args.warmup_s, args.startup_timeout, args.stop_timeout) <= 0:
        parser.error("Thread, frame and timeout limits must be positive")
    args.image_topic = args.image_topic or ["/camera/rgbd/image", "/camera/rgbd/depth_image"]
    return 0 if run(args)["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
