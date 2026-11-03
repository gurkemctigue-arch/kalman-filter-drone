"""Independent original-pipeline bench. Default describe does not open inputs."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
ROLES = ("detector", "estimator", "controller", "adapter")
MODULES = {"detector":"uav_tracking_nodes.detector_node", "estimator":"uav_tracking_nodes.state_estimator_node",
           "controller":"uav_tracking_nodes.controller_node", "adapter":"uav_tracking_px4_adapter.adapter_node"}
ALLOWED_INPUTS = {"rgb":"sensor_msgs/msg/Image", "depth":"sensor_msgs/msg/Image",
                  "camera_info":"sensor_msgs/msg/CameraInfo", "tf":"tf2_msgs/msg/TFMessage",
                  "tf_static":"tf2_msgs/msg/TFMessage", "clock":"rosgraph_msgs/msg/Clock",
                  "vehicle_odometry":"px4_msgs/msg/VehicleOdometry", "phase":"std_msgs/msg/String",
                  "selection":"uav_tracking_interfaces/msg/TargetSelection"}


def require(ok, text):
    if not ok:
        raise ValueError(text)


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def validate_shape(config):
    require(config.get("schema_version") == 1, "manifest schema_version must be 1")
    require(set(config["parameters"]) == set(ROLES) and set(config["remaps"]) == set(ROLES), "all four original roles are required")
    require(set(config["edges"]) == {"detection", "state", "command"}, "all three actual edges required")
    prefix = config["namespace"]
    require(type(prefix) is str and prefix.startswith("/bench/") and prefix.rstrip("/") == prefix, "unique /bench/... namespace required")
    destinations = set()
    kinds = []
    for item in config["inputs"]:
        kind = item["kind"]
        require(kind in ALLOWED_INPUTS and item["type"] == ALLOWED_INPUTS[kind], "unknown or incorrectly typed environment input")
        require(item["source"].startswith("/") and item["destination"].startswith(prefix+"/input/"), "explicit isolated input destination required")
        require(item["destination"] not in destinations, "duplicate input destination")
        destinations.add(item["destination"])
        kinds.append(kind)
        if item["source"].startswith("/fmu/"):
            require(kind == "vehicle_odometry", "only recorded PX4 VehicleOdometry environment input is allowed")
        require(not item["source"].startswith(("/tracking/", "/gimbal/")) or kind in {"phase", "selection"}, "old algorithm outputs cannot be replayed")
        require(item["qos"]["reliability"] in {"reliable", "best_effort"}
                and item["qos"]["durability"] in {"volatile", "transient_local"}
                and type(item["qos"]["depth"]) is int and item["qos"]["depth"] > 0, "explicit input replay QoS required")
    require(len(kinds) == len(set(kinds)) and set(kinds) >= set(ALLOWED_INPUTS)-{"selection"}, "exact declared sensor/task roles required")
    require(len({x["source"] for x in config["inputs"]}) == len(kinds), "duplicate recorded input source")
    require(all(type(v) is str and v.startswith(prefix+"/") for v in config["edges"].values())
            and len(set(config["edges"].values())) == 3, "distinct isolated pipeline edges required")
    for role in ROLES:
        require(type(config["remaps"][role]) is dict, "explicit original role remaps required")
        for source, dest in config["remaps"][role].items():
            require(source.startswith("/") and dest.startswith(prefix+"/"), "every remap destination must stay in bench namespace")
    require(type(config["replay_rate"]) in {int, float} and 0 < config["replay_rate"] <= 4, "declared finite replay rate required")
    require(config.get("record_limit") is None or type(config["record_limit"]) is int and config["record_limit"] > 0,
            "short clip record_limit must be explicit positive count or null for all selected records")


def preflight(manifest, *, native=False):
    config = read_json(manifest)
    validate_shape(config)
    if not native:
        return config
    require(os.name == "posix" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22", "explicit native requires original UAVHumble22")
    source = Path(config["source_root"]).resolve(strict=True)
    checked = []
    def bound(item):
        path = Path(item["path"]).resolve(strict=True)
        require(path.is_file() and hash_file(path) == item["sha256"], "input SHA differs: "+str(path))
        checked.append({"path":str(path), "sha256":item["sha256"]})
        return path
    plan = read_json(bound(config["original_plan"]))
    require(Path(plan["frozen_root"]).resolve(strict=True) == source, "original frozen root differs")
    canonical = json.dumps({k:v for k,v in plan.items() if k!="plan_sha256"}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(hashlib.sha256(canonical).hexdigest() == plan["plan_sha256"], "original plan content differs")
    for name, pin in plan["source_hashes"].items():
        if not name.endswith(".pt"):
            bound({"path":str(source/name), "sha256":pin})
    model = bound(config["model"])
    require(model.is_relative_to(source) and plan["model_hashes"].get(model.relative_to(source).as_posix()) == config["model"]["sha256"], "selected original weight differs")
    terminal_path = bound(config["recording_terminal"])
    terminal = read_json(terminal_path)
    require(terminal.get("execution_status") == "COMPLETED" and terminal.get("infrastructure_stop") is False
            and terminal.get("cleanup", {}).get("residual_processes") == [], "recording must be from a closed original trial")
    original_trial = next((t for t in plan["trials"] if t["id"] == terminal.get("id")), None)
    require(original_trial is not None and terminal.get("plan_sha256") == plan["plan_sha256"], "recording trial is not in bound original plan")
    require(original_trial.get("model")==model.relative_to(source).as_posix(), "selected model must be the original recorded trial model")
    directory = Path(original_trial["directory"]).resolve(strict=True)
    bag = Path(config["bag_uri"]).resolve(strict=True)
    require(bag.is_relative_to(directory), "bag must belong to the closed original trial")
    integrity_path=directory/"bag_integrity.json"
    require(hash_file(integrity_path)==terminal["artifact_hashes"].get("bag_integrity.json"), "original integrity report binding differs")
    integrity=read_json(integrity_path)
    require(integrity.get("status")=="PASS" and integrity.get("native_reader_validation",{}).get("status")=="PASS", "original full compressed archive validation missing")
    config["_expected_full_input_counts"] = {item["kind"]:integrity["raw_validation"]["topic_counts"][item["source"]]
                                             for item in config["inputs"]}
    archive_pins={row["path"]:row["sha256"] for row in integrity.get("compressed_files",[])}
    if not archive_pins:
        archive_pins={row["path"]:row["sha256"] for row in integrity["raw_validation"]["files"]}
    archive_pins["metadata.yaml"]=integrity.get("published_metadata_sha256",integrity["raw_validation"]["metadata_sha256"])
    bag_files = {str(Path(x["path"]).resolve(strict=True)) for x in config["bag_files"]}
    actual_bag_files = {str(p.resolve()) for p in bag.iterdir() if p.is_file()}
    require(actual_bag_files == bag_files and any(p.endswith("metadata.yaml") for p in bag_files), "all closed bag files, including metadata, must be pinned")
    for item in config["bag_files"]:
        path = bound(item)
        require(archive_pins.get(path.relative_to(bag).as_posix()) == item["sha256"], "bag file is not bound by original SHA-bound integrity report")
    for item in config["parameters"].values():
        path = bound(item)
        require(path.is_relative_to(directory) and terminal["artifact_hashes"].get(path.relative_to(directory).as_posix()) == item["sha256"],
                "use the original captured parameter file, not new behavior parameters")
    for name in ("recording_closure.json", "bag_integrity.json"):
        path = directory/name
        require(hash_file(path) == terminal["artifact_hashes"].get(name) and read_json(path).get("status") == "PASS", "original bag closure/integrity missing")
        checked.append({"path":str(path),"sha256":hash_file(path)})
    bound(config["probe"])
    scratch=Path(config["scratch_root"]).resolve(strict=True)
    require(scratch.is_dir() and not scratch.is_relative_to(source) and not scratch.is_relative_to(directory), "separate existing ext4 reader scratch root required")
    mounts=[]
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields=line.split();separator=fields.index("-");mount=Path(fields[4].replace("\\040"," "))
        if scratch==mount or mount in scratch.parents:mounts.append((len(str(mount)),fields[separator+1]))
    require(mounts and max(mounts)[1]=="ext4", "reader scratch must be native ext4")
    import shutil
    required=sum(row["bytes"] for row in integrity["raw_validation"]["files"])+sum(row.get("bytes",0) for row in integrity.get("compressed_files",[]))
    require(shutil.disk_usage(scratch).free > required+512*1024*1024, "insufficient local temporary reader space")
    config["_checked"] = checked
    return config


def start_event(trace, **fields):
    trace.emit("process_start", boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
               monotonic_clock=vars(time.get_clock_info("monotonic")), **fields)


def role_worker(config, role, output):
    from observer import Observer, Trace, load_probe
    source = Path(config["source_root"])
    sys.path[:0] = [str(source), str(source/"ros2_ws/src/uav_tracking_nodes"), str(source/"ros2_ws/src/uav_tracking_px4_adapter")]
    os.chdir(source)
    module = importlib.import_module(MODULES[role])
    require(Path(module.__file__).resolve().is_relative_to(source), "original algorithm module resolved outside frozen source")
    probe = load_probe(config["probe"]["path"])
    runtime = probe.runtime_binding()
    require(runtime["gate_passed"], "c7 native runtime gate did not pass")
    trace = Trace(output/(role+".jsonl"), role)
    observer = None
    try:
        observer = Observer(role, trace, {topic:edge for edge,topic in config["edges"].items()}, probe)
        ready = {"ready_path":str(output/(role+".ready.json"))}
        start_event(trace, runtime_gate_passed=True, runtime_binding=runtime, module_path=module.__file__, module_sha256=hash_file(module.__file__))
        # Guard the actual original YOLO constructor argument before it can load.
        # The original constructor is still called exactly once with unchanged args.
        if role == "detector":
            import ultralytics
            original_yolo = ultralytics.YOLO
            def original_weight_only(model, *args, **kwargs):
                require(Path(model).resolve(strict=True) == Path(config["model"]["path"]).resolve(strict=True), "original detector resolved another model")
                return original_yolo(model, *args, **kwargs)
            observer.hooks.patch(ultralytics, "YOLO", original_weight_only)
        observer.install_ros(module, ready)
        cls = getattr(module, {"detector":"DetectorNode", "estimator":"StateEstimatorNode", "controller":"ControllerNode", "adapter":"Px4AdapterNode"}[role])
        def verify_node(args, kwargs, state, result, raised):
            if raised is not None:
                return
            node = args[0]
            require(node.get_parameter("use_sim_time").value is True, "captured node must already use simulation clock")
            if role == "detector":
                require(getattr(node, "_model", None) is not None and node._frame_publisher.topic_name == config["edges"]["detection"], "original detector/model/frame path unavailable")
            elif role == "estimator":
                require(node._navigation_enabled and node._navigation_publisher.topic_name == config["edges"]["state"], "only actual navigation output is hooked")
                require(node.resolve_topic_name(str(node.get_parameter("observation_frame_topic").value)) == config["edges"]["detection"], "original atomic frame subscription is required")
            elif role == "controller":
                require(node.resolve_topic_name(str(node.get_parameter("state_topic").value)) == config["edges"]["state"]
                        and node._command_pub.topic_name == config["edges"]["command"], "controller must consume hooked actual navigation output")
            elif role == "adapter":
                require(node.resolve_topic_name(str(node.get_parameter("command_topic").value)) == config["edges"]["command"], "adapter must receive controller directly")
                odom = next(x["destination"] for x in config["inputs"] if x["kind"] == "vehicle_odometry")
                require(node._raw_odometry_sub.topic_name == odom, "recorded raw VehicleOdometry must feed original adapter conversion")
            trace.emit("node_configuration_verified", role=role)
            trace.emit("node_ready", **ready)
            write_new(ready["ready_path"], ready)
        # Run assertions inside the original construction call boundary; unlike an
        # ordinary telemetry hook, a failed startup check must abort the worker.
        original_init = cls.__init__
        def verified_init(*args, **kwargs):
            result = original_init(*args, **kwargs)
            verify_node(args, kwargs, None, result, None)
            return result
        observer.hooks.patch(cls, "__init__", verified_init)
        args = ["--ros-args", "--params-file", config["parameters"][role]["path"]]
        for old,new in config["remaps"][role].items():
            args += ["-r", old+":="+new]
        module.main(args=args)  # original main and original SingleThreadedExecutor
    finally:
        try:
            if observer is not None:
                observer.close()
        finally:
            trace.close()


def replay_worker(config, output):
    from observer import Trace
    import rclpy
    import rosbag2_py
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from rosidl_runtime_py.utilities import get_message
    trace = Trace(output/"replay.jsonl", "replay")
    resources=ExitStack()
    node, initialized = None, False
    try:
        start_event(trace)
        rclpy.init(args=[])
        initialized = True
        node = Node("pipeline_bench_input_replay")
        source=Path(config["source_root"])
        sys.path[:0]=[str(source),str(source/"scripts")]
        spec=importlib.util.spec_from_file_location("bench_original_bag_reader",source/"scripts/evaluate_stage1_flight.py")
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        owned=resources.enter_context(tempfile.TemporaryDirectory(prefix="pipeline_timing_read_",dir=config["scratch_root"]))
        prior_tempdir=tempfile.tempdir
        tempfile.tempdir=owned
        resources.callback(setattr,tempfile,"tempdir",prior_tempdir)
        reader,storage=resources.enter_context(helper.open_bag_reader(Path(config["bag_uri"]),rosbag2_py))
        require(storage["storage_identifier"]==config["storage_id"], "declared original storage identifier differs")
        trace.emit("reader_opened",original_helper_sha256=hash_file(source/"scripts/evaluate_stage1_flight.py"),storage=storage,
                   source_bag_read_only=True,owned_ext4_scratch=owned)
        available = {x.name:x.type for x in reader.get_all_topics_and_types()}
        inputs = {x["source"]:x for x in config["inputs"]}
        require(all(available.get(k)==v["type"] for k,v in inputs.items()), "selected original input types/topics missing")
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(inputs)))
        pubs = {}
        for source,item in inputs.items():
            qos = item["qos"]
            profile = QoSProfile(depth=qos["depth"], reliability=ReliabilityPolicy.RELIABLE if qos["reliability"]=="reliable" else ReliabilityPolicy.BEST_EFFORT,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL if qos["durability"]=="transient_local" else DurabilityPolicy.VOLATILE)
            pubs[source] = node.create_publisher(get_message(item["type"]), item["destination"], profile)
        write_new(output/"replay.ready.json", {"pid":os.getpid(),"node_name":node.get_name()})
        count, first, last, baseline = 0, None, None, time.monotonic_ns()
        counts = Counter()
        while reader.has_next():
            topic, payload, recorded_ns = reader.read_next()
            require(topic in inputs and type(recorded_ns) is int and (last is None or recorded_ns>=last), "input replay record order invalid")
            if first is None:
                first, baseline = recorded_ns, time.monotonic_ns()
            last = recorded_ns
            due = baseline + int((recorded_ns-first)/config["replay_rate"])
            while time.monotonic_ns() < due:
                time.sleep(max(0.,min(.01, (due-time.monotonic_ns())*1e-9)))
            entered = time.monotonic_ns()
            pubs[topic].publish(bytes(payload))  # original serialized input bytes
            count += 1
            counts[inputs[topic]["kind"]] += 1
            trace.emit("replay_input", input_kind=inputs[topic]["kind"], original_topic=topic,
                       destination=inputs[topic]["destination"], original_record_timestamp_ns=recorded_ns,
                       sequence=count, publish_enter_ns=entered, payload_bytes=len(payload))
            if config.get("record_limit") is not None and count >= config["record_limit"]:
                break
        trace.emit("replay_finished", input_records=count, first_original_record_ns=first, last_original_record_ns=last,
                   published_input_counts=dict(counts), full_original_input_counts=config["_expected_full_input_counts"],
                   declared_record_limit=config.get("record_limit"),
                   extent="DECLARED_SHORT_PREFIX" if config.get("record_limit") else "ALL_SELECTED_RECORDS")
    finally:
        try:
            resources.close()
        finally:
            try:
                try:
                    if node is not None:
                        node.destroy_node()
                finally:
                    if initialized and rclpy.ok():
                        rclpy.shutdown()
            finally:
                trace.emit("process_final", trace_dropped=trace.dropped, trace_errors=trace.errors)
                trace.close()


def native(args):
    config = preflight(args.manifest, native=True)
    require(type(args.domain_id) is int and 1 <= args.domain_id <= 232, "explicit independent domain id required")
    require(0 < args.timeout_s <= 900 and 0 <= args.drain_s <= 30 and 0 < args.cleanup_s <= 30,
            "bounded timeout, drain and shutdown budgets required")
    output = Path(args.output).absolute()
    require(not output.exists() and output.parent.is_dir() and not output.is_relative_to(Path(config["source_root"]).resolve()), "fresh external output root required")
    for item in [config["original_plan"],config["recording_terminal"],*config["parameters"].values(),*config["bag_files"]]:
        require(not Path(item["path"]).resolve().is_relative_to(output), "output cannot contain input evidence")
    output.mkdir()
    manifest_copy = output/"manifest.json"
    write_new(manifest_copy, {k:v for k,v in config.items() if not k.startswith("_")})
    write_new(output/"started.json", {"scope":"INDEPENDENT_CANDIDATE_SOFTWARE_BENCH", "created_utc":datetime.now(timezone.utc).isoformat(),
              "manifest_sha256":hash_file(manifest_copy), "domain_id":args.domain_id, "checked_input_bindings":config["_checked"]})
    from observer import Trace
    from reducer import reduce_files
    import rclpy
    from rclpy.node import Node
    (output/"ros_logs").mkdir()
    os.environ.update(ROS_DOMAIN_ID=str(args.domain_id), ROS_LOCALHOST_ONLY="1", PYTHONDONTWRITEBYTECODE="1",
                      ROS_LOG_DIR=str(output/"ros_logs"))
    trace, node, initialized = None, None, False
    processes, files = {}, []
    begin, end, complete, error = None, None, False, None
    cleanup_errors, group_status = [], {}
    deadline = time.monotonic()+args.timeout_s
    def graph():
        all_rows = {}
        fmu_publishers=[]
        for topic,_ in node.get_topic_names_and_types():
            if topic.startswith("/fmu/"):
                fmu_publishers.extend({"topic":topic,"node_name":i.node_name} for i in node.get_publishers_info_by_topic(topic))
        trace.emit("fmu_scan",publishers=fmu_publishers)
        require(not fmu_publishers,"real fmu publishers present in independent domain")
        for phase,topic in config["edges"].items():
            rows = [{"node_name":i.node_name,"node_namespace":i.node_namespace,"gid_hex":bytes(i.endpoint_gid).hex(),
                     "topic_type":i.topic_type,"qos_repr":repr(i.qos_profile)} for i in node.get_publishers_info_by_topic(topic)]
            trace.emit("graph",phase=phase,publishers=rows)
            all_rows[phase]=rows
        return all_rows
    def tick():
        require(time.monotonic()<deadline, "declared native bench timeout")
        rclpy.spin_once(node,timeout_sec=.005)
        return graph()
    def spawn(role):
        log=(output/(role+".log")).open("xb");files.append(log)
        processes[role]=subprocess.Popen([sys.executable,"-B",str(HERE/"bench.py"),"native-worker","--manifest",str(manifest_copy),"--role",role,"--output",str(output)],
                                         cwd=config["source_root"],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=dict(os.environ))
    def group_alive(pid):
        try:
            os.killpg(pid,0)
            return True
        except ProcessLookupError:
            return False
    try:
        trace = Trace(output/"monitor.jsonl", "monitor")
        start_event(trace)
        rclpy.init(args=[])
        initialized = True
        node = Node("pipeline_bench_graph_monitor")
        for role in ROLES:
            spawn(role)
        stable = None
        while True:
            rows=tick()
            require(all(p.poll() is None for p in processes.values()), "an original node worker exited before replay")
            ready = {role:read_json(output/(role+".ready.json")) for role in ROLES if (output/(role+".ready.json")).is_file()}
            expected={"detection":ready.get("detector",{}).get("node_name"),"state":ready.get("estimator",{}).get("node_name"),"command":ready.get("controller",{}).get("node_name")}
            good=len(ready)==4 and all(len(v)==1 and v[0]["node_name"]==expected[k] for k,v in rows.items())
            stable = (stable or time.monotonic()) if good else None
            if stable is not None and time.monotonic()-stable>=.3:
                break
        for phase,writer in expected.items():trace.emit("controlled_writers",phase=phase,writers=[writer])
        begin=time.monotonic_ns()
        trace.emit("scope_begin",entered_ns=begin)
        spawn("replay")
        while processes["replay"].poll() is None:
            require(all(processes[r].poll() is None for r in ROLES), "original node exited during replay")
            tick()
        require(processes["replay"].returncode==0, "recorded input replay failed")
        drain_until=time.monotonic()+args.drain_s
        while time.monotonic()<drain_until:tick()
        end=time.monotonic_ns()
        trace.emit("scope_end",entered_ns=end)
        graph()
        for phase,writer in expected.items():trace.emit("controlled_writers",phase=phase,writers=[writer])
        complete=True
    except BaseException as exception:
        error=f"{type(exception).__name__}: {exception}"
    finally:
        for p in processes.values():
            try:os.killpg(p.pid,signal.SIGINT)
            except ProcessLookupError:pass
            except Exception as exception:cleanup_errors.append(f"SIGINT:{p.pid}:{type(exception).__name__}")
        cleanup_deadline=time.monotonic()+min(30.,args.cleanup_s)
        try:
            while any(group_alive(p.pid) for p in processes.values()) and time.monotonic()<cleanup_deadline:
                for p in processes.values():p.poll()  # reap leaders while checking their whole owned groups
                time.sleep(.02)
        except Exception as exception:cleanup_errors.append("group_wait:"+type(exception).__name__)
        for p in processes.values():
            try:
                if group_alive(p.pid):
                    complete=False
                    os.killpg(p.pid,signal.SIGKILL)
                p.wait(timeout=5.)
                group_status[str(p.pid)]={"leader_returncode":p.returncode,"group_still_present":group_alive(p.pid)}
                if group_status[str(p.pid)]["group_still_present"]:complete=False
            except ProcessLookupError:
                p.poll()
                group_status[str(p.pid)]={"leader_returncode":p.returncode,"group_still_present":False}
            except Exception as exception:cleanup_errors.append(f"group_cleanup:{p.pid}:{type(exception).__name__}")
        for handle in files:
            try:handle.close()
            except Exception as exception:cleanup_errors.append("log_close:"+type(exception).__name__)
        try:
            if node is not None:node.destroy_node()
        except Exception as exception:cleanup_errors.append("node_destroy:"+type(exception).__name__)
        try:
            if initialized and rclpy.ok():rclpy.shutdown()
        except Exception as exception:cleanup_errors.append("context_shutdown:"+type(exception).__name__)
        finally:
            if trace is not None:
                trace.emit("process_final",trace_dropped=trace.dropped,trace_errors=trace.errors,cleanup_errors=cleanup_errors,owned_group_status=group_status)
                try:trace.close()
                except Exception as exception:cleanup_errors.append("trace_close:"+type(exception).__name__)
        complete=complete and not cleanup_errors
    codes={role:p.returncode for role,p in processes.items()}
    complete = complete and set(codes)==set(ROLES)|{"replay"} and all(v==0 for v in codes.values())
    for item in config["_checked"]:
        if hash_file(item["path"])!=item["sha256"]:
            complete=False;error="original input changed during bench"
    paths=[output/(role+".jsonl") for role in (*ROLES,"replay","monitor")]
    summary={"scope":"CONTROLLED_CANDIDATE_SOFTWARE_PIPELINE_ONLY_NOT_PHYSICAL_E2E", "native_complete":complete,"process_exit_codes":codes,"error":error,
             "cleanup_errors":cleanup_errors,"owned_group_status":group_status,
             "physical_e2e":"NOT_OBSERVED","historical_strict_changed":False}
    if begin is not None and end is not None and all(p.is_file() for p in paths):
        try:summary.update(reduce_files(paths,probe_path=config["probe"]["path"],begin_ns=begin,end_ns=end,native_complete=complete))
        except Exception as exception:summary.update(reducer_error=f"{type(exception).__name__}: {exception}",status="NOT_OBSERVED_INVALID_TRACE")
    else:summary["status"]="NOT_OBSERVED_INCOMPLETE_EXECUTION"
    write_new(output/"summary.json",summary)
    print(json.dumps({"output":str(output),"native_complete":complete,"candidate_command_count":summary.get("candidate_command_count",0),"error":error}))
    return 0 if complete else 2


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action")
    sub.add_parser("describe")
    run=sub.add_parser("native")
    run.add_argument("--manifest",required=True);run.add_argument("--output",required=True);run.add_argument("--domain-id",type=int,required=True)
    run.add_argument("--timeout-s",type=float,default=120.);run.add_argument("--drain-s",type=float,default=2.);run.add_argument("--cleanup-s",type=float,default=30.)
    worker=sub.add_parser("native-worker")
    worker.add_argument("--manifest",required=True);worker.add_argument("--output",required=True);worker.add_argument("--role",choices=(*ROLES,"replay"),required=True)
    args=parser.parse_args(argv)
    if args.action in (None,"describe"):
        print(json.dumps({"status":"DESCRIBE_ONLY_NO_INPUTS_OPENED","execution_triggered":False,"roles":ROLES,
                          "scope":"Candidate software timing of actual original detector/navigation/controller/adapter only",
                          "required_manifest_fields":["schema_version","namespace","source_root","original_plan","recording_terminal","model","parameters","bag_uri","storage_id","bag_files","scratch_root","inputs","edges","remaps","replay_rate","record_limit","probe"],
                          "allowed_input_types":ALLOWED_INPUTS,"default_reads_bag_or_model":False,"physical_e2e":"NOT_OBSERVED"},indent=2))
        return 0
    if args.action=="native":
        require(os.name=="posix" and os.environ.get("WSL_DISTRO_NAME")=="UAVHumble22", "native requires original Linux session")
        import fcntl
        lock=Path("/tmp/uav_tracking_reliability_v4_sitl.lock")
        require(lock.is_file() and not lock.is_symlink(), "existing project machine lock required")
        with lock.open("rb") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            return native(args)
    require(os.name=="posix" and os.environ.get("WSL_DISTRO_NAME")=="UAVHumble22" and os.environ.get("ROS_LOCALHOST_ONLY")=="1",
            "native worker requires the explicit original isolated Linux session")
    config=preflight(args.manifest,native=True)
    return replay_worker(config,Path(args.output)) if args.role=="replay" else role_worker(config,args.role,Path(args.output))


if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as error:
        print(json.dumps({"status":"REFUSED_OR_INCOMPLETE","error":f"{type(error).__name__}: {error}","historical_strict_changed":False,"physical_e2e":"NOT_OBSERVED"}))
        raise SystemExit(2)
