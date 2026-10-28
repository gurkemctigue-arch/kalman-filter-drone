"""Own all processes for one isolated, reproducible real visual SITL trial."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import yaml


def simulation_status_watchdog_s(requested_real_time_factor: float) -> float:
    """Preserve a 1 s PX4-time budget for its 2 Hz status in slowed SITL.

    Commander publishes every 500 ms of simulated time, not 5 Hz merely
    because the DDS topic has a 5 Hz rate limit. The supervisor's independent
    liveness guard uses monotonic wall time. This explicit runner setting
    leaves the portable node's real-vehicle default of 1 wall second intact.
    """
    if not math.isfinite(requested_real_time_factor) or not 0 < requested_real_time_factor <= 1:
        raise ValueError("requested simulation real-time factor must be in (0,1]")
    return 1.0 / requested_real_time_factor


def apply_multi_target_identity(parameters: dict, bringup: Path, target_class: str) -> Path:
    """Keep designated-target safety while retaining the physical gimbal graph."""
    identity_config_path = bringup / "config" / f"stage2_tracking_{target_class}.yaml"
    identity_parameters = yaml.safe_load(identity_config_path.read_text(encoding="utf-8"))
    parameters["uav_tracking_state_estimator"] = identity_parameters["uav_tracking_state_estimator"]
    return identity_config_path


def snapshot_px4_parameters(px4_root: Path, destination: Path, phase: str) -> dict:
    """Archive persistent SITL input/output without resetting any parameter."""
    source=px4_root/"build/px4_sitl_default/rootfs/parameters.bson"
    metadata={"source":str(source),"exists":source.is_file(),"phase":phase,
              "scope":"Persisted nondefault PX4 parameters; firmware/airframe defaults and startup overrides remain separate evidence"}
    if source.is_file():
        artifact=destination/f"px4_parameters_{phase}.bson"
        shutil.copy2(source,artifact)
        metadata.update(artifact=artifact.name,bytes=artifact.stat().st_size,
                        sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--class", dest="target_class", choices=["person", "car"], default="person")
    parser.add_argument("--name", required=True)
    parser.add_argument("--duration", type=float, default=45)
    parser.add_argument("--command-mode", choices=["velocity", "position"], default="velocity")
    parser.add_argument("--render-backend", choices=["egl", "wslg"], default="egl")
    parser.add_argument("--wall-timeout", type=float, default=300)
    parser.add_argument("--occlusions", action="store_true")
    parser.add_argument("--short-occlusion-s", type=float, default=0.2,
                        help="Rendered short shutter duration; total measurement gap also includes sampling/inference")
    parser.add_argument("--reselect-after-loss", action="store_true",
                        help="Explicit test-script box selection after the long shutter test")
    parser.add_argument("--no-bag", action="store_true")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--multi-target", action="store_true",
                        help="Use the stage-three three-actor world and designated-target pipeline")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--speed-mps", type=float, default=None)
    parser.add_argument("--condition", choices=["clean", "depth_noise", "depth_holes", "dropout", "latency", "combined"], default="clean")
    parser.add_argument("--initial-select", choices=["none", "leftmost", "middle", "rightmost"], default="none")
    parser.add_argument("--initial-min-candidates", type=int, default=2)
    parser.add_argument("--gimbal-mode", choices=["midpoint", "active"], default="active")
    parser.add_argument("--scenario-kind", choices=["parallel", "crossing", "ambiguity"], default="crossing")
    parser.add_argument("--target-mode", choices=["auto_unique", "locked_target"], default=None)
    parser.add_argument("--association-mode", choices=["legacy", "iou_2d", "hybrid_3d"], default=None)
    parser.add_argument("--estimator-method", choices=["raw", "ema", "fixed_kf", "adaptive_kf"], default="adaptive_kf")
    parser.add_argument("--desired-distance-m", type=float, default=None)
    parser.add_argument("--takeoff-height-m", type=float, default=3.0)
    parser.add_argument("--takeoff-mode", choices=["offboard_velocity", "px4_native"], default="offboard_velocity",
                        help="Opt-in native PX4 takeoff completes in-flight EKF alignment before Offboard handoff")
    parser.add_argument("--no-follow-duration-s", type=float, default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--inference-threads", type=int, default=None)
    parser.add_argument("--inference-image-size", type=int, default=None)
    parser.add_argument("--max-inference-rate-hz", type=float, default=None,
                        help="Acquisition submission rate cap; does not change any freshness/safety threshold")
    parser.add_argument("--monitor-tick-s", type=float, default=0.10,
                        help="Shutter scheduler resolution; acknowledgement-based minimum dwell is unchanged")
    parser.add_argument("--control-reference", choices=["visible_surface", "ground_footprint"], default="visible_surface")
    parser.add_argument("--magnetic-environment", choices=["archived_source", "coherent_wmm", "gazebo_enu"], default="archived_source")
    parser.add_argument("--magnetic-runtime-manifest", default=None,
                        help="Verified separate PX4 ELF/source manifest required for the opt-in Gazebo ENU magnetic contract")
    parser.add_argument("--magnetic-library-registration", default=None,
                        help="Pre-audited per-environment Gazebo ELF registration; gazebo_enu defaults to config/gazebo_magnetic_runtime.json (Jazzy)")
    parser.add_argument("--propagate-vehicle-uncertainty", action="store_true")
    parser.add_argument("--px4-time-mode", choices=["receipt", "source_sim"], default="receipt",
                        help="source_sim disables XRCE wall-time mapping before client startup and validates PX4 source time against /clock")
    parser.add_argument("--real-time-factor", type=float, default=1.0)
    parser.add_argument("--motion-profile-kind", choices=["standard", "speed_changes"], default="standard")
    args = parser.parse_args()
    if not math.isfinite(args.monitor_tick_s) or not .01 <= args.monitor_tick_s <= .10:
        parser.error("monitor tick must be finite and in [0.01,0.10] seconds")
    if args.multi_target and args.stage != 3:
        parser.error("--multi-target is only used for stage-three joint trials; stage two is already multi-target")
    if not 0 < args.short_occlusion_s < 0.75:
        parser.error("short occlusion must be between 0 and the 0.75 s measurement prediction limit")
    if not 0 <= args.seed < 4_294_967_295:
        parser.error("registered seed must be in [0,4294967294] for the nonzero Gazebo seed mapping")
    # The same registered seed controls the target profile/fault RNG and
    # Gazebo's process-wide random generator. It is not just a speed label.
    # Gazebo 8.15 runServer ignores seed 0, including explicit --seed 0.
    # Map registered zero-based trial seeds to nonzero uint32 process seeds.
    args.gazebo_seed = args.seed + 1
    args.gazebo_seed_mapping = "registered_seed_plus_one_zero_is_ignored_by_gazebo_cli"
    if args.speed_mps is None:
        args.speed_mps = random.Random(args.seed).uniform(0.45, 0.55)
    if not 0 < args.speed_mps <= 1:
        parser.error("speed must be in (0,1]")
    if args.desired_distance_m is not None and not 2 <= args.desired_distance_m <= 20:
        parser.error("desired distance must be in [2,20] m")
    if not 2 <= args.takeoff_height_m <= 6:
        parser.error("takeoff height must be in [2,6] m")
    if args.takeoff_mode == "px4_native" and args.px4_time_mode != "source_sim":
        parser.error("px4_native startup requires the explicit source_sim timestamp contract")
    if not 0 < args.real_time_factor <= 1:
        parser.error("simulation real-time factor must be in (0,1]")
    args.supervisor_status_timeout_wall_s = simulation_status_watchdog_s(args.real_time_factor)
    if args.control_reference == "ground_footprint":
        # Declared vehicle geometry for independent offline scoring only.
        # Runtime tracking/control never consumes Gazebo truth.
        args.vehicle_control_point_offset_flu_m = [0.0, 0.0, 0.24]
    root = Path(__file__).resolve().parents[1]
    magnetic_runtime = None
    if args.magnetic_environment == "gazebo_enu":
        if not args.magnetic_runtime_manifest:
            parser.error("gazebo_enu requires --magnetic-runtime-manifest for a separately built compatible PX4")
        from prepare_px4_magnetic_compatibility import validate_runtime_manifest
        magnetic_runtime = validate_runtime_manifest(Path(args.magnetic_runtime_manifest))
        from capture_gazebo_magnetic_libraries import load_registration
        args.magnetic_library_registration = str(Path(args.magnetic_library_registration or
            root / "config/gazebo_magnetic_runtime.json").resolve())
        load_registration(Path(args.magnetic_library_registration))
        configured_px4 = os.environ.get("STAGE1_PX4_ROOT")
        if configured_px4 and Path(configured_px4).resolve() != Path(magnetic_runtime["source_root"]).resolve():
            parser.error("STAGE1_PX4_ROOT conflicts with the verified magnetic runtime")
    elif args.magnetic_runtime_manifest or args.magnetic_library_registration:
        parser.error("magnetic runtime manifests and library registrations are only used with gazebo_enu")
    output = root / "results" / args.name
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, STAGE1_AUTO_START="true", STAGE1_PROJECT_ROOT=str(root),
               STAGE1_COMMAND_MODE=args.command_mode,
               STAGE_SIM_SEED=str(args.gazebo_seed),
               STAGE1_RENDER_BACKEND=args.render_backend,
               STAGE1_PX4_TIME_MODE=args.px4_time_mode,
               STAGE1_TAKEOFF_MODE=args.takeoff_mode,
               GZ_PARTITION=os.environ.get("GZ_PARTITION", "stage1_flight"), GZ_IP="127.0.0.1",
               ROS_DOMAIN_ID=os.environ.get("ROS_DOMAIN_ID", "0"),
               PYTHONUNBUFFERED="1", OMP_NUM_THREADS="2", LP_NUM_THREADS="4", STAGE_START_PAUSED="1")
    if magnetic_runtime is not None:
        env["STAGE1_PX4_ROOT"] = magnetic_runtime["source_root"]
        env["STAGE1_PX4_MAG_CONTRACT"] = magnetic_runtime["contract"]
    world = f"stage{args.stage}_flight"
    env.update(STAGE_WORLD=world, STAGE_LAUNCH=f"stage{args.stage}_flight.launch.py",
               STAGE_SPEED_MPS=str(args.speed_mps), STAGE_GIMBAL_MODE=args.gimbal_mode,
               STAGE_SCENARIO_KIND=args.scenario_kind, STAGE_TARGET_CLASS=args.target_class,
               STAGE_MULTI_TARGET="true" if args.multi_target else "false",
               STAGE1_TAKEOFF_HEIGHT_M=str(args.takeoff_height_m))
    env["STAGE_MOTION_PROFILE_KIND"] = args.motion_profile_kind
    (output / "run_config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    snapshot = output / "configuration"
    snapshot.mkdir()
    if magnetic_runtime is not None:
        shutil.copy2(args.magnetic_runtime_manifest, snapshot / "px4_magnetic_runtime.json")
        shutil.copy2(args.magnetic_library_registration,
                     snapshot / "gazebo_magnetic_runtime_registration.json")
    px4_root=Path(env.get("STAGE1_PX4_ROOT","/root/PX4-Autopilot"))
    parameter_evidence={"before":snapshot_px4_parameters(px4_root,snapshot,"before"),
                        "startup_wrapper":"scripts/px4_stage1_startup.sh",
                        "explicit_environment_overrides":{"COM_RC_IN_MODE":4,"NAV_DLL_ACT":0,
                            "UXRCE_DDS_SYNCT":0 if args.px4_time_mode == "source_sim" else 1},
                        "policy":"Archive only; no reset/import/overwrite of rootfs parameters"}
    parameter_manifest=snapshot/"px4_parameters.json"
    if magnetic_runtime is not None:
        parameter_evidence["explicit_environment_overrides"]["SENS_EN_MAGSIM"] = 0
    if args.takeoff_mode == "px4_native":
        parameter_evidence["explicit_environment_overrides"].update(
            MIS_TAKEOFF_ALT=args.takeoff_height_m, COM_TAKEOFF_ACT=0, SENS_IMU_MODE=1)
    parameter_manifest.write_text(json.dumps(parameter_evidence,indent=2),encoding="utf-8")
    bringup = root / "ros2_ws" / "src" / "uav_tracking_bringup"
    config_path = bringup / "config" / f"stage{args.stage}_tracking_{args.target_class}.yaml"
    bridge_name = "stage1_flight_bridge.yaml" if args.stage == 1 else f"stage{args.stage}_bridge.yaml"
    world_source = bringup / "worlds" / (
        f"stage3_multi_{args.target_class}.sdf" if args.multi_target else f"{world}_{args.target_class}.sdf")
    for item in [config_path,
                 bringup / "config" / bridge_name,
                 world_source,
                 bringup / "models" / f"target_{args.target_class}" / "model.sdf",
                 bringup / "models" / ("x500_stage3" if args.stage == 3 else "x500_stage1") / "model.sdf"]:
        target_name = (item.parent.name + "_" + item.name) if item.name == "model.sdf" else item.name
        shutil.copy2(item, snapshot / target_name)
    source_hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for folder in [root / "uav_tracking", root / "ros2_ws" / "src", root / "scripts"]
                     for path in folder.rglob("*") if path.is_file() and path.suffix in {".py", ".sh", ".msg"}}
    parameters = yaml.safe_load(config_path.read_text())
    # Only the simulation supervisor consumes these overrides. Do not change
    # odometry, command, or target measurement/prediction safety thresholds.
    parameters.setdefault("uav_tracking_flight_supervisor", {}).setdefault("ros__parameters", {}).update(
        status_timeout_s=args.supervisor_status_timeout_wall_s,
        requested_simulation_real_time_factor=args.real_time_factor,
    )
    if args.multi_target:
        # Carry stage-two identity safety into the physical-gimbal graph.
        # The single-target stage-three defaults deliberately retain legacy
        # association for compatibility; they are insufficient for this mode.
        identity_config_path = apply_multi_target_identity(parameters, bringup, args.target_class)
        shutil.copy2(identity_config_path, snapshot / identity_config_path.name)
    runtime_world = snapshot / "runtime_world.sdf"
    if args.magnetic_environment == "coherent_wmm":
        from configure_sim_magnetic_field import configure_world
        lookup = snapshot / "px4_wmm_reference.json"
        shutil.copy2(root / "config/px4_wmm_reference.json", lookup)
        configure_world(world_source, runtime_world, snapshot / "magnetic_environment.json", lookup_json=lookup)
    elif args.magnetic_environment == "gazebo_enu":
        from configure_gazebo_magnetic_contract import configure_world
        lookup = snapshot / "gazebo_magnetic_reference.json"
        shutil.copy2(root / "config/gazebo_magnetic_reference.json", lookup)
        load_registration(snapshot / "gazebo_magnetic_runtime_registration.json", lookup)
        configure_world(world_source, runtime_world, snapshot / "magnetic_environment.json",
                        runtime_manifest=snapshot / "px4_magnetic_runtime.json", lookup_json=lookup)
    world_tree = ET.parse(runtime_world if runtime_world.exists() else world_source)
    world_tree.find("world/physics/real_time_factor").text = str(args.real_time_factor)
    world_tree.write(runtime_world, encoding="utf-8", xml_declaration=True)
    if args.magnetic_environment in {"coherent_wmm", "gazebo_enu"}:
        magnetic_evidence_path = snapshot / "magnetic_environment.json"
        magnetic_evidence = json.loads(magnetic_evidence_path.read_text(encoding="utf-8"))
        magnetic_evidence["configured_world_sha256_before_runtime_overrides"] = magnetic_evidence["runtime_world_sha256"]
        magnetic_evidence["runtime_world_sha256"] = hashlib.sha256(runtime_world.read_bytes()).hexdigest()
        magnetic_evidence["runtime_real_time_factor"] = args.real_time_factor
        magnetic_evidence_path.write_text(json.dumps(magnetic_evidence, indent=2), encoding="utf-8")
    env["STAGE_WORLD_FILE"] = str(runtime_world)
    if args.model_path:
        parameters["uav_tracking_detection"]["ros__parameters"]["model_path"] = args.model_path
    if args.inference_threads is not None:
        if args.inference_threads < 1:
            parser.error("inference threads must be positive")
        parameters["uav_tracking_detection"]["ros__parameters"]["inference_threads"] = args.inference_threads
    if args.inference_image_size is not None:
        if args.inference_image_size < 128 or args.inference_image_size % 32:
            parser.error("inference size must be a multiple of 32 and at least 128")
        parameters["uav_tracking_detection"]["ros__parameters"]["inference_image_size"] = args.inference_image_size
    if args.max_inference_rate_hz is not None:
        if not math.isfinite(args.max_inference_rate_hz) or args.max_inference_rate_hz <= 0:
            parser.error("max inference rate must be finite and positive")
        parameters["uav_tracking_detection"]["ros__parameters"]["max_inference_rate_hz"] = args.max_inference_rate_hz
    if args.control_reference == "ground_footprint":
        parameters["uav_tracking_detection"]["ros__parameters"]["navigation_enabled"] = True
        # The new geometry contract requires one aligned acquisition. Waiting
        # for matching depth is preferable to moving a prior frame's cloud
        # with the current gimbal TF. Camera frames are generated at 10 Hz.
        parameters["uav_tracking_detection"]["ros__parameters"]["depth_max_age_s"] = .02
        estimator = parameters["uav_tracking_state_estimator"]["ros__parameters"]
        estimator["navigation_enabled"] = True
        estimator["navigation_dimensions_m"] = [4.5, 1.8, 1.5] if args.target_class == "car" else [.5, .5, 1.7]
        estimator["navigation_dimension_std_m"] = [.45, .18, .15] if args.target_class == "car" else [.1, .1, .2]
        parameters["uav_tracking_controller"]["ros__parameters"]["state_topic"] = "/tracking/navigation_state"
    parameters["uav_tracking_state_estimator"]["ros__parameters"]["estimator_method"] = args.estimator_method
    parameters["uav_tracking_state_estimator"]["ros__parameters"]["propagate_vehicle_uncertainty"] = args.propagate_vehicle_uncertainty
    parameters["uav_tracking_px4_adapter"]["ros__parameters"]["odometry_timestamp_mode"] = args.px4_time_mode
    parameters["uav_tracking_px4_adapter"]["ros__parameters"]["odometry_source_max_age_s"] = .50
    parameters["uav_tracking_px4_adapter"]["ros__parameters"]["odometry_source_max_future_s"] = .05
    parameters["uav_tracking_px4_adapter"]["ros__parameters"]["odometry_timing_topic"] = "/vehicle/odometry_timing"
    # Record the launch overrides too, so the saved parameter contract is
    # sufficient for an independent evaluator without consulting current code.
    parameters["uav_tracking_px4_adapter"]["ros__parameters"].update(
        use_sim_time=True, command_topic="/tracking/flight_command", require_vehicle_status=True,
        vehicle_status_topic="/fmu/out/vehicle_status_v1")
    parameters["uav_tracking_controller"]["ros__parameters"]["command_mode"] = args.command_mode
    parameters["uav_tracking_detection"]["ros__parameters"].update(
        activation_phase_topic="/tracking/flight_phase", image_reliability="reliable")
    parameters["uav_tracking_flight_supervisor"]["ros__parameters"].update(
        auto_start=True, simulation_only=True, takeoff_height_m=args.takeoff_height_m,
        takeoff_mode=args.takeoff_mode, use_sim_time=True)
    if args.takeoff_mode == "px4_native":
        parameters["uav_tracking_flight_supervisor"]["ros__parameters"].update(
            native_settle_s=1.0, native_settle_speed_mps=.20,
            takeoff_position_tolerance_m=.18,
            local_position_topic="/fmu/out/vehicle_local_position_v1",
            estimator_flags_topic="/fmu/out/estimator_status_flags")
    if args.stage == 3:
        parameters["uav_tracking_controller"]["ros__parameters"]["enable_gimbal_yaw_reference"] = True
        parameters.setdefault("uav_tracking_gimbal", {}).setdefault("ros__parameters", {})["gimbal_mode"] = args.gimbal_mode
    if args.desired_distance_m is not None:
        parameters["uav_tracking_controller"]["ros__parameters"]["desired_distance_m"] = args.desired_distance_m
    if args.target_mode:
        parameters["uav_tracking_state_estimator"]["ros__parameters"]["target_mode"] = args.target_mode
    if args.association_mode:
        parameters["uav_tracking_state_estimator"]["ros__parameters"]["association_mode"] = args.association_mode
    fault_settings = {
        "clean": {}, "depth_noise": {"noise_std_m": .05}, "depth_holes": {"hole_fraction": .25},
        "dropout": {"drop_fraction": .10}, "latency": {"delay_s": .12},
        "combined": {"noise_std_m": .05, "hole_fraction": .20, "drop_fraction": .10, "delay_s": .08},
    }[args.condition]
    if fault_settings:
        detector = parameters["uav_tracking_detection"]["ros__parameters"]
        detector.update(image_topic="/research/camera/color/image_raw",
                        depth_topic="/research/camera/aligned_depth_to_color/image_raw",
                        camera_info_topic="/research/camera/color/camera_info")
    runtime_params = snapshot / "runtime_parameters.yaml"
    runtime_params.write_text(yaml.safe_dump(parameters, sort_keys=False), encoding="utf-8")
    env["STAGE_PARAMS_FILE"] = str(runtime_params)
    (snapshot / "sensor_faults.json").write_text(json.dumps({"seed": args.seed, **fault_settings}, indent=2), encoding="utf-8")
    model_path = parameters["uav_tracking_detection"]["ros__parameters"]["model_path"]
    checkpoint = root / model_path
    model_files = [checkpoint] if checkpoint.is_file() else sorted(path for path in checkpoint.rglob("*") if path.is_file())
    if not model_files:
        raise FileNotFoundError(f"No detector model files at {checkpoint}")
    for model_file in model_files:
        source_hashes[str(model_file.relative_to(root))] = hashlib.sha256(model_file.read_bytes()).hexdigest()
    (snapshot / "source_sha256.json").write_text(json.dumps(source_hashes, indent=2), encoding="utf-8")
    runner = root / "scripts" / "run_stage1_flight.sh"
    processes = {}
    logs = []

    def start(name, command):
        log = (output / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        # ros2 launch forwards SIGINT to its children in noninteractive mode.
        # DEVNULL keeps that mode independent of the caller's terminal.
        proc = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL if name == "ros" else None,
                                start_new_session=True)
        processes[name] = proc
        print(f"started {name} pid={proc.pid}", flush=True)
        return proc

    def stop(name, timeout=10):
        proc = processes.get(name)
        if proc and proc.poll() is None:
            if name == "ros":
                # The shell wrapper execs ros2 launch. Let launch signal its
                # children once; group SIGINT would also hit them directly.
                proc.send_signal(signal.SIGINT)
            else:
                os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)

    try:
        start("gazebo", ["bash", str(runner), "gazebo", args.target_class])
        start("agent", ["bash", str(runner), "agent", args.target_class])
        ready = False
        for _ in range(30):
            if processes["gazebo"].poll() is not None:
                raise RuntimeError("Gazebo exited; see gazebo.log")
            probe = subprocess.run(["gz", "service", "-l"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if f"/world/{world}/control" in probe.stdout:
                ready = True
                break
            time.sleep(1)
        if not ready:
            raise RuntimeError("Gazebo world service did not become available")
        if magnetic_runtime is not None:
            from capture_gazebo_magnetic_libraries import capture_ready
            try:
                libraries = capture_ready(processes["gazebo"].pid,
                    registration_json=snapshot / "gazebo_magnetic_runtime_registration.json",
                    lookup_json=snapshot / "gazebo_magnetic_reference.json")
                (snapshot / "gazebo_loaded_magnetic_libraries.json").write_text(
                    json.dumps(libraries, indent=2), encoding="utf-8")
            except (OSError, ValueError) as error:
                (snapshot / "gazebo_loaded_magnetic_libraries_error.json").write_text(
                    json.dumps({"verified": False, "error": str(error)}), encoding="utf-8")
                raise RuntimeError("Gazebo magnetic library provenance failed before PX4 startup") from error
        start("px4", ["bash", str(runner), "px4", args.target_class])
        time.sleep(3)
        if not args.no_bag:
            topics = ["/clock", "/camera/color/image_raw", "/camera/aligned_depth_to_color/image_raw", "/camera/color/camera_info",
                      "/tracking/observations", "/tracking/observation_frames", "/tracking/state", "/tracking/status", "/tracking/command", "/tracking/flight_command",
                      "/tracking/flight_phase", "/tracking/detection_diagnostics", "/tracking/selection", "/vehicle/odometry", "/vehicle/odometry_timing", "/tf", "/tf_static",
                      "/fmu/out/vehicle_odometry", "/fmu/out/vehicle_status_v1", "/fmu/out/vehicle_command_ack",
                      "/fmu/out/vehicle_local_position_v1", "/fmu/out/estimator_status_flags",
                      "/fmu/in/vehicle_command", "/fmu/in/trajectory_setpoint", "/fmu/in/offboard_control_mode",
                      "/ground_truth/poses", "/ground_truth/vehicle_poses"]
            topics.extend(["/tracking/tracks", "/gimbal/joint_states", "/gimbal/diagnostics", "/gimbal/body_yaw_reference",
                           "/gimbal/yaw/cmd_pos", "/gimbal/pitch/cmd_pos", "/gimbal/roll/cmd_pos", "/scenario/stage2_profile",
                           "/research/camera/color/image_raw", "/research/camera/aligned_depth_to_color/image_raw"])
            topics.extend(["/tracking/navigation_state", "/tracking/navigation_diagnostics"])
            start("bag", ["ros2", "bag", "record", "--storage", "sqlite3", "--compression-mode", "file", "--compression-format", "zstd", "-o", str(output / "rosbag"), *topics])
        monitor_cmd = [sys.executable, str(root / "scripts" / "stage1_flight_monitor.py"), "--output", str(output), "--target-class", args.target_class,
                       "--duration", str(args.duration), "--wall-timeout", str(args.wall_timeout), "--world", world,
                       "--monitor-tick-s", str(args.monitor_tick_s),
                       "--initial-select", args.initial_select, "--initial-min-candidates", str(args.initial_min_candidates)]
        if args.occlusions:
            monitor_cmd.append("--occlusions")
            monitor_cmd.extend(["--short-occlusion-s", str(args.short_occlusion_s)])
        if args.no_follow_duration_s is not None:
            monitor_cmd.extend(["--no-follow-duration-s", str(args.no_follow_duration_s)])
        if args.reselect_after_loss:
            if not args.occlusions:
                raise ValueError("--reselect-after-loss requires --occlusions")
            monitor_cmd.append("--reselect-after-loss")
        monitor = start("monitor", monitor_cmd)
        if fault_settings:
            fault_command = [sys.executable, str(root / "scripts" / "sensor_fault_bridge.py"), "--ros-args", "-p", f"seed:={args.seed}"]
            for key, value in fault_settings.items():
                fault_command.extend(["-p", f"{key}:={value}"])
            start("sensor_faults", fault_command)
        start("ros", ["bash", str(runner), "ros", args.target_class])
        # Build the camera bridge before starting sensor publication. This
        # reduces transport discovery/startup overlap; any crash remains a
        # failed trial, never an automatic hidden retry.
        bridge_ready = False
        startup_log = []
        for _ in range(15):
            if "process has died" in (output / "ros.log").read_text(errors="replace"):
                raise RuntimeError("ROS component failed during startup; see ros.log")
            probe = subprocess.run(["ros2", "topic", "list", "--no-daemon", "--spin-time", "0.5"],
                                   env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            startup_log.append(probe.stdout)
            if {"/clock", "/camera/color/image_raw", "/camera/aligned_depth_to_color/image_raw"}.issubset(probe.stdout.splitlines()):
                bridge_ready = True
                break
            time.sleep(0.5)
        (output / "bridge_startup.log").write_text("\n".join(startup_log), encoding="utf-8")
        if not bridge_ready:
            raise RuntimeError("Camera bridge did not advertise all sensor topics while paused")
        resumed = subprocess.run(["gz", "service", "-s", f"/world/{world}/control", "--reqtype", "gz.msgs.WorldControl",
                                  "--reptype", "gz.msgs.Boolean", "--timeout", "5000", "--req", "pause: false"],
                                 env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        (output / "unpause.log").write_text(resumed.stdout, encoding="utf-8")
        if resumed.returncode != 0 or "true" not in resumed.stdout:
            raise RuntimeError("Gazebo did not acknowledge unpause")
        deadline = time.monotonic() + args.wall_timeout + 15
        while monitor.poll() is None:
            for name in ["gazebo", "agent", "px4", "ros"]:
                if processes[name].poll() is not None:
                    raise RuntimeError(f"{name} exited {processes[name].returncode}; see its log")
            if "process has died" in (output / "ros.log").read_text(errors="replace"):
                raise RuntimeError("ROS component failed during flight; see ros.log")
            if time.monotonic() > deadline:
                raise RuntimeError("trial wall deadline exceeded")
            time.sleep(1)
        print(f"monitor exited {monitor.returncode}; evidence: {output}", flush=True)
        if monitor.returncode != 0:
            raise RuntimeError(f"Flight monitor failed with exit code {monitor.returncode}; see monitor.log")
    finally:
        # rosbag2 must flush the raw image/depth cache and finish file-mode
        # zstd compression before metadata.yaml is written. 45 s was too
        # short for the car/position recordings: the process was killed after
        # a successful flight, leaving a valid-looking db3 without a complete
        # bag. This is a recording-finalization bound only; it does not alter
        # the flight, estimator, controller, or safety thresholds.
        for name in ["monitor", "bag", "ros", "sensor_faults", "px4", "gazebo", "agent"]:
            stop(name, timeout=180 if name == "bag" else 8)
        for log in logs:
            log.close()
        (output / "process_exit_codes.json").write_text(json.dumps({name: p.poll() for name, p in processes.items()}, indent=2), encoding="utf-8")
        parameter_evidence["after"]=snapshot_px4_parameters(px4_root,snapshot,"after")
        parameter_manifest.write_text(json.dumps(parameter_evidence,indent=2),encoding="utf-8")
        if magnetic_runtime is not None:
            from prepare_px4_magnetic_compatibility import verify_runtime, assert_runtime_unchanged
            try:
                verified = verify_runtime(px4_root, output / "px4.log")
                assert_runtime_unchanged(magnetic_runtime, verified)
                (snapshot / "px4_magnetic_runtime_actual.json").write_text(
                    json.dumps(verified, indent=2), encoding="utf-8")
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                (snapshot / "px4_magnetic_runtime_verification_error.json").write_text(
                    json.dumps({"verified": False, "error": str(error)}), encoding="utf-8")
                if processes.get("monitor") is not None and processes["monitor"].poll() == 0:
                    raise RuntimeError("Flight ended without verified magnetic PX4 startup provenance") from error


if __name__ == "__main__":
    main()
