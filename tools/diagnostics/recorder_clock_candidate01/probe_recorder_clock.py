"""One prospective recorder-QoS component condition; describe is inert.

Reuse the archived 20-source-second production RGB-D split-bridge probe.
Only run imports ROS/rosbag and launches processes. No PX4, YOLO, flight,
production configuration edit, original-report rewrite, or automatic retry.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import traceback


KIND = "PROSPECTIVE_RECORDER_CLOCK_QOS_COMPONENT_V1"
CLOCK = "/clock"
RGB = "/camera/color/image_raw"
DEPTH = "/camera/aligned_depth_to_color/image_raw"
INFO = "/camera/color/camera_info"
PRODUCER = "/recorder_clock_candidate/producer_receipt"
CONTROL = "/recorder_clock_candidate/capture_control"
IMAGES = (RGB, DEPTH, INFO)
TOPICS = (CLOCK, *IMAGES, PRODUCER, CONTROL)
QOS_SHA = "d56c368ecba5e77a7343a7832be4ec234a4cd4576e367aaa9a808c356cf76824"
BASE_PROBE_SHA = "1ec86d74d846f31a151db28b0db1c1246c298c9d2975f8f08fbe1c9f1924a892"
RECORDER_NAME = "recorder_clock_candidate_record"
LIMIT_JSON = 16 * 1024 * 1024
LIMIT_BAG = 2 * 1024**3


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    require(path.is_file() and path.stat().st_size <= LIMIT_JSON, "Expected a bounded small input: " + str(path))
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def stamp_ns(stamp):
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def image_key(topic, message):
    """Compare complete pixel bytes, or complete CameraInfo calibration values."""
    common = {"stamp_ns": stamp_ns(message.header.stamp), "frame_id": message.header.frame_id,
              "width": int(message.width), "height": int(message.height)}
    if topic == INFO:
        payload = {**common, "distortion_model": message.distortion_model, "d": list(message.d),
                   "k": list(message.k), "r": list(message.r), "p": list(message.p),
                   "binning_x": int(message.binning_x), "binning_y": int(message.binning_y),
                   "roi": [int(message.roi.x_offset), int(message.roi.y_offset), int(message.roi.height),
                           int(message.roi.width), bool(message.roi.do_rectify)]}
    else:
        data = bytes(message.data)
        payload = {**common, "encoding": message.encoding, "step": int(message.step),
                   "is_bigendian": int(message.is_bigendian), "data_bytes": len(data),
                   "pixel_sha256": hashlib.sha256(data).hexdigest()}
        require(len(data) == int(message.height) * int(message.step), "Incomplete image payload")
    require(common["width"] == 640 and common["height"] == 480, "Production RGB-D shape changed")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return common["stamp_ns"], digest


def load_base(path):
    spec = importlib.util.spec_from_file_location("recorder_clock_original_rgbd_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stop_owned(row, base):
    child, identity = row["child"], row["identity"]
    signals = []
    for sig, timeout in ((signal.SIGINT, 25), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        if child.poll() is not None:
            break
        current = base.process(child.pid)
        require(current == identity, "Owned process identity changed; refuse signal")
        os.killpg(identity["process_group"], sig)
        signals.append(signal.Signals(sig).name)
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
    child.wait(timeout=1)
    return {"returncode": child.returncode, "requested_signals": signals,
            "direct_child_reaped": child.poll() is not None,
            "residual_group_members": base.group_members(identity["process_group"]),
            "forced": any(name != "SIGINT" for name in signals)}


def signal_recorder(row, base, sig):
    require(row["child"].poll() is None and base.process(row["child"].pid) == row["identity"],
            "Recorder identity changed before controlled stress signal")
    os.killpg(row["identity"]["process_group"], sig)


def resume_for_cleanup(stopped, row, base, stress):
    if stopped:
        signal_recorder(row, base, signal.SIGCONT)
        stress["resumed_during_cleanup"] = True
    return False


def diagnostic_profile(depth):
    require(type(depth) is int and depth in {10, 1024}, "Diagnostic evidence depth must be 10 or 1024")
    return {"history": "keep_last", "depth": depth, "reliability": "reliable", "durability": "volatile"}


def candidate_profiles(profile, condition, producer_evidence_depth=10):
    require(condition in {"current2048", "candidate1"}, "Unknown recorder condition")
    diagnostic = diagnostic_profile(producer_evidence_depth)
    require(profile[CLOCK] == {"history": "keep_last", "depth": 2048, "reliability": "reliable", "durability": "volatile"},
            "Unexpected current /clock QoS")
    candidate = json.loads(json.dumps(profile))
    candidate[CLOCK]["depth"] = 2048 if condition == "current2048" else 1
    if producer_evidence_depth == 1024:
        for topic in (PRODUCER, CONTROL):
            require(topic not in candidate, "Diagnostic topic overlaps an original production profile")
            candidate[topic] = dict(diagnostic)
    return candidate


def nonclock_complete(start, end, observed_end, comparisons, equality):
    return (end - start == 20_000_000_000 and observed_end and set(comparisons) == set(IMAGES)
        and all(200 <= value["observer_count"] <= 201 and value["duplicate_observer_source_stamps"] == 0
            and value["exact_stamp_payload_multiset_equal"] and value["registered_10hz_4ms_cadence_observed"]
            for value in comparisons.values())
        and set(equality) == {PRODUCER, CONTROL} and all(equality.values()))


def analyze_bag(output, sent, live_images, live_clock, base_receipt, capture_window):
    """Read only this newly closed, uncompressed bag, preserving native order."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    import yaml

    bag = output / "rosbag"
    files = list(bag.iterdir())
    require(all(path.is_file() and not path.is_symlink() for path in files), "Unexpected bag member")
    require(sum(path.stat().st_size for path in files) <= LIMIT_BAG, "Component bag exceeds 2 GiB bound")
    integrity = {}
    for path in files:
        if path.suffix == ".db3":
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                integrity[path.name] = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    require(integrity and all(value == ["ok"] for value in integrity.values()), "Native SQLite integrity failed")
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="sqlite3"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
    require(set(types) == set(TOPICS), "Recorded topic set changed")
    classes = {topic: get_message(name) for topic, name in types.items()}
    counts, image_rows, producer_rows, controls = Counter(), {topic: [] for topic in IMAGES}, [], []
    clock_rows, latest_clock, previous_clock, previous_record_ns = [], None, None, None
    original_sequence = 0
    while reader.has_next():
        topic, data, record_ns = reader.read_next()
        message = deserialize_message(data, classes[topic])
        counts[topic] += 1
        if topic == CLOCK:
            current = stamp_ns(message.clock)
            clock_rows.append({"record_sequence": original_sequence, "source_ns": current,
                "original_record_ns": int(record_ns),
                "source_step_ns": None if previous_clock is None else current - previous_clock,
                "original_record_interval_ns": None if previous_record_ns is None else int(record_ns) - previous_record_ns})
            latest_clock, previous_clock, previous_record_ns = current, current, int(record_ns)
        elif topic in IMAGES:
            source_ns, digest = image_key(topic, message)
            image_rows[topic].append({"stamp_ns": source_ns, "digest": digest, "record_sequence": original_sequence,
                                      "original_record_ns": int(record_ns), "latest_recorded_clock_ns": latest_clock})
        else:
            payload = json.loads(message.data)
            require(payload.get("schema_version") == 1 and payload.get("kind") == KIND, "Foreign producer/control payload")
            row = {"payload": payload, "record_sequence": original_sequence, "original_record_ns": int(record_ns),
                   "latest_recorded_clock_ns": latest_clock}
            if topic == PRODUCER:
                row["latest_clock_minus_producer_receipt_ns"] = None if latest_clock is None else latest_clock - payload["producer_receipt_ros_ns"]
                producer_rows.append(row)
            else:
                controls.append(row)
        original_sequence += 1
    del reader
    metadata = yaml.safe_load((bag / "metadata.yaml").read_text())["rosbag2_bagfile_information"]
    metadata_counts = {row["topic_metadata"]["name"]: row["message_count"] for row in metadata["topics_with_message_count"]}
    require(dict(counts) == metadata_counts, "Full native read disagrees with metadata")
    require(all(live_images[topic] and image_rows[topic] for topic in IMAGES), "Missing non-clock stream")
    # This future window was armed before its data arrived. Never crop it to
    # whichever native-bag intersection happens to survive discovery or loss.
    require(isinstance(capture_window, dict), "No prospective capture window was armed")
    start, end = capture_window["start_source_ns"], capture_window["end_source_ns"]
    observed_end = live_clock["last_source_ns"] >= end and all(
        max(row["stamp_ns"] for row in live_images[topic]) >= end - 104_000_001 for topic in IMAGES)
    comparisons = {}
    for topic in IMAGES:
        observed = [row for row in image_rows[topic] if start <= row["stamp_ns"] <= end]
        expected = [row for row in live_images[topic] if start <= row["stamp_ns"] <= end]
        keys = lambda rows: Counter((row["stamp_ns"], row["digest"]) for row in rows)
        source_times = sorted({row["stamp_ns"] for row in expected})
        gaps = [right - left for left, right in zip(source_times, source_times[1:])]
        comparisons[topic] = {"observer_count": len(expected), "native_bag_count": len(observed),
            "exact_stamp_payload_multiset_equal": keys(expected) == keys(observed),
            "missing": sum((keys(expected) - keys(observed)).values()),
            "unexpected_or_duplicate": sum((keys(observed) - keys(expected)).values()),
            "duplicate_observer_source_stamps": len(expected) - len(source_times),
            "max_observed_source_gap_ns": max(gaps, default=None),
            "registered_10hz_4ms_cadence_observed": bool(gaps) and max(gaps) <= 104_000_001}
    received_payloads = {PRODUCER: [row["payload"] for row in producer_rows], CONTROL: [row["payload"] for row in controls]}
    equality = {topic: Counter(json.dumps(item, sort_keys=True) for item in sent[topic]) ==
                       Counter(json.dumps(item, sort_keys=True) for item in received_payloads[topic]) for topic in sent}
    end_controls = [row for row in sent[CONTROL] if row["event"] == "END"]
    end_reference = end_controls[-1]["producer_receipt_ros_ns"] if end_controls else None
    max_image_stamp = max(row["stamp_ns"] for rows in image_rows.values() for row in rows)
    tail_closed = bool(clock_rows and end_reference is not None and latest_clock >= max(max_image_stamp, end_reference, live_clock["last_source_ns"]))
    source_steps = [row["source_step_ns"] for row in clock_rows if row["source_step_ns"] is not None]
    record_intervals = [row["original_record_interval_ns"] for row in clock_rows if row["original_record_interval_ns"] is not None]
    differences = [row["latest_clock_minus_producer_receipt_ns"] for row in producer_rows if row["latest_clock_minus_producer_receipt_ns"] is not None]
    complete = nonclock_complete(start, end, observed_end, comparisons, equality)
    result = {"full_native_read": True, "sqlite_integrity": integrity, "metadata_counts": metadata_counts,
        "native_counts": dict(counts), "source_window_ns": [start, end], "source_window_duration_s": (end-start)/1e9,
        "prospective_window": capture_window, "observer_reached_registered_end": observed_end,
        "nonclock_comparisons": comparisons, "producer_control_exact_multiset_equal": equality,
        "nonclock_evidence_complete": complete, "last_clock_closure": {
            "closed": tail_closed, "last_recorded_clock_ns": latest_clock, "last_native_image_source_ns": max_image_stamp,
            "end_marker_producer_clock_ns": end_reference, "last_observer_clock_ns": live_clock["last_source_ns"]},
        "clock_counts": {"native_bag": counts[CLOCK], "independent_observer": live_clock["count"],
                         "claim": "Fewer clock messages alone is never a successful result"},
        "clock_source_step_ns": {"minimum": min(source_steps, default=None), "maximum": max(source_steps, default=None),
            "regressions": sum(value < 0 for value in source_steps), "duplicates": sum(value == 0 for value in source_steps),
            "steps_over_4ms": sum(value > 4_000_001 for value in source_steps)},
        "original_record_timestamp_interval_ns": {"minimum": min(record_intervals, default=None),
            "maximum": max(record_intervals, default=None), "negative_intervals": sum(value < 0 for value in record_intervals),
            "domain": "RAW_NATIVE_RECORDER_TIMESTAMP_DOMAIN_NOT_INDEPENDENTLY_CERTIFIED_WALL_CLOCK"},
        "producer_clock_vs_recorder_latest_ns": {"minimum": min(differences, default=None), "maximum": max(differences, default=None),
            "missing_latest_clock": len(producer_rows)-len(differences),
            "outside_original_diagnostic_reference_bounds": sum(value < -50_000_001 or value > 500_000_001 for value in differences),
            "scope": "Independent image-callback producer ROS receipt, not PX4 adapter receipt or causal latency"},
        "base_component_receipt_status": base_receipt.get("status"),
        "single_condition_comparison": "NOT_COMPARED_NO_REPAIR_OR_FLIGHT_ACCEPTANCE_CLAIM"}
    write_new(output / "clock_record_sequence.json", {"kind": KIND, "rows": clock_rows})
    write_new(output / "producer_record_sequence.json", {"kind": KIND, "rows": producer_rows, "control_rows": controls})
    write_new(output / "image_record_sequence.json", {"kind": KIND, "topics": image_rows})
    return result


def run(args):
    require(sys.platform.startswith("linux"), "Native run is Linux-only; describe remains portable")
    root, base_path = args.source_root.resolve(strict=True), args.base_probe.resolve(strict=True)
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir(), "Fresh output with existing parent required")
    output = output.resolve()
    require(not output.is_relative_to(root), "Output must be outside frozen runtime")
    require(shutil.disk_usage(output.parent).free >= 4 * 1024**3, "At least 4 GiB free required for bounded raw RGB-D bag")
    require(Path(sys.prefix).resolve() == Path("/root/uav_humble22/venv").resolve(), "Use the original Humble venv")
    require(os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22" and os.environ.get("ROS_DISTRO") == "humble",
            "Source the original UAVHumble22 / ROS Humble environment first")
    require(sha(base_path) == BASE_PROBE_SHA, "The archived component-probe bytes differ")
    for name in ("config/ros_gz_runtime_humble22.json", "config/ros_gz_clock_runtime_humble22.json", "config/dds_runtime_humble22.json"):
        require((root / name).is_file(), "Missing original runtime registration: " + name)
    profiles_path = root / "config/recording_qos.yaml"
    require(sha(profiles_path) == QOS_SHA, "Original actual53 recorder profile differs")
    base = load_base(base_path)
    for name in ("uav_tracking.ros_gz_runtime", "uav_tracking.dds_runtime"):
        require(Path(sys.modules[name].__file__).resolve().is_relative_to(root), "Wrong original helper origin: " + name)
    execution_probe = pin(Path(__file__))
    original_inputs = [pin(path) for path in (Path(__file__), base_path, profiles_path,
        root / "config/ros_gz_clock_runtime_humble22.json", root / "config/ros_gz_runtime_humble22.json",
        root / "config/dds_runtime_humble22.json",
        Path(sys.modules["uav_tracking.ros_gz_runtime"].__file__),
        Path(sys.modules["uav_tracking.dds_runtime"].__file__))]
    output.mkdir()
    state = {"schema_version": 1, "kind": KIND, "status": "RUNNING", "condition": args.condition,
        "started_utc": datetime.now(timezone.utc).isoformat(), "source_root": str(root),
        "scope": "REAL_RECORDER_WITH_PRODUCTION_RGBD_TWO_BRIDGES_COMPONENT_ONLY_NO_PX4_NO_YOLO",
        "execution_probe": execution_probe, "original_inputs": original_inputs,
        "formal_flights_started": 0, "original_reports_modified": False,
        "repair_claimed": False, "stress": {"requested_pause_wall_s": args.stress_recorder_pause_wall_s,
            "at_elapsed_source_s": 10.0, "applied": False, "artificial_stress_not_production": bool(args.stress_recorder_pause_wall_s)},
        "runtime_environment": {key: os.environ.get(key) for key in (
            "ROS_DISTRO", "RMW_IMPLEMENTATION", "ROS_DOMAIN_ID", "AMENT_PREFIX_PATH", "LD_LIBRARY_PATH", "PYTHONPATH")}}
    owned, logs, sent = {}, [], {PRODUCER: [], CONTROL: []}
    node = rclpy = None
    live_images = {topic: [] for topic in IMAGES}
    live_clock = {"count": 0, "first_source_ns": None, "last_source_ns": 0}
    base_receipt = {}
    stress_stopped = False
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def interrupted(signum, frame):
        raise KeyboardInterrupt("Received " + signal.Signals(signum).name)

    signal.signal(signal.SIGTERM, interrupted)
    try:
        import yaml
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rosgraph_msgs.msg import Clock
        from sensor_msgs.msg import Image, CameraInfo
        from std_msgs.msg import String
        profile = yaml.safe_load(profiles_path.read_text())
        candidate = candidate_profiles(profile, args.condition, args.producer_evidence_depth)
        require({key: candidate[key] for key in profile if key != CLOCK} ==
                {key: value for key, value in profile.items() if key != CLOCK}, "Original non-clock profile changed")
        snapshot = output / "recording_qos.yaml"
        snapshot.write_text(yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8")
        state["requested_recorder_profiles"] = candidate
        state["qos_snapshot"] = pin(snapshot)
        state["diagnostic_evidence_qos"] = {
            "producer_evidence_depth": args.producer_evidence_depth,
            "requested_publisher_profiles": {topic: diagnostic_profile(args.producer_evidence_depth)
                                             for topic in (PRODUCER, CONTROL)},
            "requested_recorder_profile_overrides": {topic: candidate[topic] for topic in (PRODUCER, CONTROL)
                                                     if topic in candidate},
            "image_observer_requested_profile": diagnostic_profile(10),
            "scope": "Requested QoS, not independently certified endpoint QoS; absent recorder overrides retain auto-discovery"}
        # Base probe remains byte-for-byte unchanged. Only its three documented path globals are rebound.
        base_inputs = output / "base_inputs" / "runtime_capture01"
        base_inputs.mkdir(parents=True)
        shutil.copy2(root / "config/ros_gz_clock_runtime_humble22.json", base_inputs / "ros_gz_clock_runtime_registration.json")
        loader = output / "run_original_component.py"
        loader.write_text("import importlib.util, os\nfrom pathlib import Path\n"
            + "spec=importlib.util.spec_from_file_location('original_rgbd_component'," + repr(str(base_path)) + ")\n"
            + "probe=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(probe)\n"
            + "probe.ROOT=Path(" + repr(str(root)) + ")\nprobe.BASE=Path(" + repr(str(output / "base_inputs")) + ")\n"
            + "probe.OUT=Path(" + repr(str(output / "base_capture")) + ")\n"
            + "os.environ['SPLIT_PROBE_CANDIDATE_SOURCE']=" + repr(str(root)) + "\nraise SystemExit(probe.main())\n", encoding="utf-8")
        state["base_probe_path_rebinding"] = {"ROOT": str(root), "BASE": str(output / "base_inputs"), "OUT": str(output / "base_capture"),
            "original_scope_note": "Base receipt says no bag because its own code does not record; this enclosing tool adds the recorder separately."}
        env = dict(os.environ)
        env["ROS_DOMAIN_ID"] = str(args.ros_domain_id)
        os.environ["ROS_DOMAIN_ID"] = env["ROS_DOMAIN_ID"]
        state["runtime_environment"]["ROS_DOMAIN_ID"] = env["ROS_DOMAIN_ID"]
        state["recorder_time_configuration"] = {"cli_use_sim_time": False,
            "raw_native_timestamp_domain": "NOT_INDEPENDENTLY_CERTIFIED_WALL_CLOCK",
            "comparison": "Record timestamp intervals retained directly; never subtracted from ROS source or producer monotonic time"}
        rclpy.init()
        node = rclpy.create_node("recorder_clock_candidate_observer", enable_rosout=False,
                                parameter_overrides=[Parameter("use_sim_time", value=True)])
        require(all(node.count_publishers(topic) == 0 for topic in TOPICS), "Chosen ROS domain already contains component topics")
        image_observer_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
        diagnostic_publisher_qos = QoSProfile(depth=args.producer_evidence_depth,
            reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
        publishers = {topic: node.create_publisher(String, topic, diagnostic_publisher_qos) for topic in sent}
        subscriptions = []

        def publish(topic, payload):
            payload = {"schema_version": 1, "kind": KIND, **payload}
            message = String()
            message.data = json.dumps(payload, separators=(",", ":"), allow_nan=False)
            publishers[topic].publish(message)
            sent[topic].append(payload)

        def on_clock(message):
            live_clock["count"] += 1
            live_clock["last_source_ns"] = stamp_ns(message.clock)
            if live_clock["first_source_ns"] is None:
                live_clock["first_source_ns"] = live_clock["last_source_ns"]

        def on_image(topic, message):
            receipt_ros = node.get_clock().now().nanoseconds
            receipt_monotonic, receipt_system = time.monotonic_ns(), time.time_ns()
            source, digest = image_key(topic, message)
            live_images[topic].append({"stamp_ns": source, "digest": digest})
            if topic == RGB:
                publish(PRODUCER, {"event_id": len(sent[PRODUCER]), "image_header_ns": source,
                    "origin": "rgb_callback",
                    "image_digest": digest, "producer_receipt_ros_ns": receipt_ros,
                    "producer_monotonic_ns": receipt_monotonic, "producer_system_ns": receipt_system})

        subscriptions.append(node.create_subscription(Clock, CLOCK, on_clock, QoSProfile(
            depth=100, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)))
        for topic in IMAGES:
            subscriptions.append(node.create_subscription(CameraInfo if topic == INFO else Image, topic,
                                  lambda message, topic=topic: on_image(topic, message), image_observer_qos))

        def on_producer_timer():
            publish(PRODUCER, {"event_id": len(sent[PRODUCER]), "origin": "ros_timer_100_source_hz_proxy",
                "producer_receipt_ros_ns": node.get_clock().now().nanoseconds,
                "producer_monotonic_ns": time.monotonic_ns(), "producer_system_ns": time.time_ns()})

        producer_timer = node.create_timer(.01, on_producer_timer)
        state["producer_proxy"] = {"source_timer_period_s": .01, "also_records_rgb_callback_receipts": True,
            "scope": "Independent ROS clock producer proxy; not PX4 adapter/source validity or image-to-command latency"}

        def launch(role, command):
            log = (output / (role + ".log")).open("xb")
            logs.append(log)
            child = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            identity = base.process(child.pid)
            require(identity["parent_pid"] == os.getpid() and identity["process_group"] == identity["session"] == child.pid,
                    "Wrong child owner/session")
            owned[role] = {"child": child, "identity": identity, "command": command}
            state.setdefault("owned_processes", {})[role] = {"identity": identity, "requested_command": command,
                "actual_proc_cmdline": Path(f"/proc/{child.pid}/cmdline").read_bytes().decode().rstrip("\0").split("\0")}

        ros2 = shutil.which("ros2")
        require(ros2 is not None, "Original ros2 CLI missing")
        launch("recorder", [ros2, "bag", "record", "--storage", "sqlite3", "--node-name", RECORDER_NAME,
            "--qos-profile-overrides-path", str(snapshot), "-o", str(output / "rosbag"), *TOPICS])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            require(owned["recorder"]["child"].poll() is None, "Recorder exited before discovery")
            rclpy.spin_once(node, timeout_sec=.05)
            if all(any(item.node_name == RECORDER_NAME for item in node.get_subscriptions_info_by_topic(topic)) for topic in sent):
                break
        else:
            raise RuntimeError("Recorder did not match producer/control topics")
        publish(CONTROL, {"event": "START", "producer_receipt_ros_ns": node.get_clock().now().nanoseconds,
                          "producer_system_ns": time.time_ns(), "producer_monotonic_ns": time.monotonic_ns()})
        launch("component", [sys.executable, "-B", str(loader)])
        write_new(output / "started.json", state)
        deadline = time.monotonic() + 360
        while owned["component"]["child"].poll() is None and time.monotonic() < deadline:
            require(owned["recorder"]["child"].poll() is None, "Recorder exited during real RGB-D capture")
            rclpy.spin_once(node, timeout_sec=.02)
            if ("capture_window" not in state and all(live_images[topic] for topic in IMAGES)
                    and all(any(item.node_name == RECORDER_NAME for item in node.get_subscriptions_info_by_topic(topic))
                            for topic in IMAGES)):
                start = live_clock["last_source_ns"] + 100_000_000
                state["capture_window"] = {"start_source_ns": start, "end_source_ns": start + 20_000_000_000,
                    "armed_source_ns": live_clock["last_source_ns"],
                    "rule": "First observed RGB/Depth/Info plus matched recorder readers, then a future 100ms guard and fixed20source seconds; never native-bag availability cropping"}
                publish(CONTROL, {"event": "CAPTURE_WINDOW", "producer_receipt_ros_ns": node.get_clock().now().nanoseconds,
                                  **state["capture_window"]})
                write_new(output / "capture_window.json", state["capture_window"])
            if (args.stress_recorder_pause_wall_s and not state["stress"]["applied"]
                    and live_clock["first_source_ns"] is not None
                    and live_clock["last_source_ns"] - live_clock["first_source_ns"] >= 10_000_000_000):
                stress_stopped = True
                signal_recorder(owned["recorder"], base, signal.SIGSTOP)
                state["stress"].update(applied=True, stopped_monotonic_ns=time.monotonic_ns(),
                    stopped_source_ns=live_clock["last_source_ns"], recorder_identity=owned["recorder"]["identity"])
                write_new(output / "stress_stopped.json", state["stress"])
            if stress_stopped and (time.monotonic_ns() - state["stress"]["stopped_monotonic_ns"]
                                   >= round(args.stress_recorder_pause_wall_s * 1e9)):
                signal_recorder(owned["recorder"], base, signal.SIGCONT)
                stress_stopped = False
                state["stress"].update(resumed_monotonic_ns=time.monotonic_ns(), resumed_source_ns=live_clock["last_source_ns"])
                state["stress"]["actual_pause_wall_s"] = (state["stress"]["resumed_monotonic_ns"] - state["stress"]["stopped_monotonic_ns"]) / 1e9
                write_new(output / "stress_resumed.json", state["stress"])
        require(owned["component"]["child"].poll() is not None, "Component wall budget exhausted")
        base_receipt_path = output / "base_capture" / "receipt.json"
        require(base_receipt_path.is_file() and base_receipt_path.stat().st_size <= LIMIT_JSON, "Missing base receipt")
        base_receipt = json.loads(base_receipt_path.read_text())
        state["base_component_receipt"] = pin(base_receipt_path)
        state["base_component_status"] = base_receipt.get("status")
        nested_path = output / "base_capture" / "owned_processes.json"
        if nested_path.is_file() and nested_path.stat().st_size <= LIMIT_JSON:
            state["base_owned_processes"] = json.loads(nested_path.read_text())
            state["base_owned_processes_pin"] = pin(nested_path)
        state["base_nested_cleanup"] = base_receipt.get("cleanup")
        require(base_receipt.get("status") == "PASS", "Base production RGB-D component failed")
        state["status"] = "CAPTURE_ENDED_PENDING_BAG_ANALYSIS"
    except BaseException as error:
        state.update(status="FAILED_OR_INCOMPLETE_COMPONENT", error=type(error).__name__ + ": " + str(error), traceback=traceback.format_exc())
    finally:
        cleanup = {}
        if stress_stopped and "recorder" in owned:
            try:
                stress_stopped = resume_for_cleanup(stress_stopped, owned["recorder"], base, state["stress"])
            except BaseException as error:
                state["stress"]["cleanup_resume_error"] = str(error)
        if "component" in owned:
            try:
                cleanup["component"] = stop_owned(owned["component"], base)
            except BaseException as error:
                cleanup["component"] = {"error": str(error)}
        if node is not None:
            try:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    rclpy.spin_once(node, timeout_sec=.01)
                if "publish" in locals():
                    publish(CONTROL, {"event": "END", "producer_receipt_ros_ns": node.get_clock().now().nanoseconds,
                        "producer_system_ns": time.time_ns(), "producer_monotonic_ns": time.monotonic_ns()})
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        rclpy.spin_once(node, timeout_sec=.01)
            except BaseException as error:
                state["observer_drain_error"] = str(error)
        if "recorder" in owned:
            try:
                cleanup["recorder"] = stop_owned(owned["recorder"], base)
            except BaseException as error:
                cleanup["recorder"] = {"error": str(error)}
        for log in logs:
            log.close()
        state["cleanup"] = cleanup
        if node is not None:
            try:
                node.destroy_node()
            except BaseException as error:
                state["observer_destroy_error"] = str(error)
        if rclpy is not None and rclpy.ok():
            try:
                rclpy.shutdown()
            except BaseException as error:
                state["observer_shutdown_error"] = str(error)
        write_new(output / "observer_ledger.json", {"kind": KIND, "image_topics": live_images,
                  "clock": live_clock, "sent": sent})
    try:
        require(all(pin(item["path"]) == item for item in original_inputs), "Original component input changed")
        require(set(state["cleanup"]) == {"component", "recorder"} and all(
            row.get("returncode") == 0 and row.get("direct_child_reaped") is True and not row.get("forced")
            and not row.get("residual_group_members") for row in state["cleanup"].values()), "Owned cleanup failed")
        require(state["status"] == "CAPTURE_ENDED_PENDING_BAG_ANALYSIS", "Capture failed; retained data not promoted")
        nested_cleanup = state.get("base_nested_cleanup", {})
        require(set(nested_cleanup) == {"data", "clock", "gazebo"} and all(row.get("exit_code") == 0
                and row.get("direct_child_reaped") is True and not row.get("forced") and not row.get("residual_group_members")
                for row in nested_cleanup.values()), "Base bridge/Gazebo ownership cleanup incomplete")
        require(not args.stress_recorder_pause_wall_s or (state["stress"]["applied"]
                and "resumed_monotonic_ns" in state["stress"] and not state["stress"].get("resumed_during_cleanup")),
                "Requested controlled stress was not completed inside the observation")
        require(not any(key in state for key in ("observer_drain_error", "observer_destroy_error", "observer_shutdown_error")),
                "Observer did not drain and exit normally")
        state["bag_analysis"] = analyze_bag(output, sent, live_images, live_clock, base_receipt, state.get("capture_window"))
        state["status"] = ("COMPONENT_EVIDENCE_COMPLETE_NO_REPAIR_CLAIM" if
            state["bag_analysis"]["nonclock_evidence_complete"] and state["bag_analysis"]["last_clock_closure"]["closed"]
            else "INCOMPLETE_NONCLOCK_OR_CLOCK_TAIL_EVIDENCE")
    except BaseException as error:
        state.update(status="FAILED_OR_INCOMPLETE_COMPONENT", analysis_error=type(error).__name__ + ": " + str(error))
    state["finished_utc"] = datetime.now(timezone.utc).isoformat()
    state["clock_comparison_boundary"] = "Single condition never proves improvement. Preserve fewer-clock, missing images, producer-reference anomalies and failure cases. No full-flight clock or target-following acceptance."
    write_new(output / "result.json", state)
    signal.signal(signal.SIGTERM, previous_sigterm)
    return {"output": str(output), "status": state["status"], "repair_claimed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "run"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--base-probe", type=Path)
    parser.add_argument("--condition", choices=("current2048", "candidate1"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ros-domain-id", type=int, default=74)
    parser.add_argument("--producer-evidence-depth", type=int, choices=(10, 1024), default=10,
                        help="Diagnostic producer/control publisher depth; 1024 also explicitly overrides their recorder histories")
    parser.add_argument("--stress-recorder-pause-wall-s", type=float, choices=(0., .6, 1.), default=0.,
                        help="Explicit artificial recorder-only SIGSTOP/SIGCONT once after +10 source seconds")
    args = parser.parse_args()
    if args.action == "describe":
        print(json.dumps({"kind": KIND, "conditions": {"current2048": 2048, "candidate1": 1},
            "changed_field": "/clock.depth only; reliable/volatile and all other profiles preserved",
            "duration_source_s": 20, "camera": "640x480 RGB-D 10Hz", "rtf": .125,
            "optional_artificial_stress_pause_wall_s": [0, .6, 1.],
            "producer_evidence_depth": args.producer_evidence_depth,
            "diagnostic_evidence_depth_choices": [10, 1024],
            "diagnostic_recorder_override": args.producer_evidence_depth == 1024,
            "real_bag_recorder": True, "actual_execution": False, "repair_claimed": False}))
        return 0
    if not all((args.source_root, args.base_probe, args.condition, args.output)):
        parser.error("run requires explicit --source-root --base-probe --condition --output")
    if not 0 <= args.ros_domain_id <= 232:
        parser.error("--ros-domain-id must be 0..232")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "COMPONENT_EVIDENCE_COMPLETE_NO_REPAIR_CLAIM" else 2


if __name__ == "__main__":
    raise SystemExit(main())
