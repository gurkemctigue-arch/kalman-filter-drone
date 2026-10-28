"""Frozen v4 orchestration fixtures; no simulator, ROS, or bag database reads."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reliability_v4_fixture", ROOT / "scripts/run_reliability_v4.py")
v4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v4)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def registered_gates():
    return {"status": "REGISTERED", "maximum_base_link_distance_rmse_m": 1.,
            "maximum_base_link_height_rmse_m": .3, "minimum_valid_state_coverage": .7,
            "minimum_truth_coverage": .95, "require_final_window_settled": True,
            "minimum_physical_identity_coverage": .4}


def navigation_report(directory="fixture"):
    transients = {}
    for dimension, band in (("distance", .5), ("height", .25)):
        transients[dimension] = {"scheduled_samples":100, "valid_truth_samples":100, "truth_coverage":1.,
            "band_m":band, "minimum_in_band_duration_s":3., "observed_interval_s":9.9,
            "settled_through_interval_end":True, "settling_right_censored":False,
            "settling_time_s":.2, "duplicate_source_times":False}
    return {"schema_version":1, "evaluation_status":"RECORDED_WITH_CENSORED_FAILURES", "trial":str(directory),
        "reference":{"controlled_vehicle_point":"base_link", "desired_horizontal_distance_m":5., "desired_height_m":2.},
        "interval":{"start_s":0., "end_s":9.9, "navigation_evaluation_start_s":0., "sample_period_s":.1},
        "whole_interval":{"scheduled_samples":100, "matched_truth_samples":100, "inactive_control_samples":0,
            "metrics":{"base_link_distance_error_m":{"rmse":.4, "count":100},
                       "base_link_height_error_m":{"rmse":.1, "count":100},
                       "model_origin_distance_error_m":{"rmse":.3, "count":100}},
            "transients":{"base_link":transients}},
        "kf_navigation":{"counts":{"scheduled_samples":100,"valid_navigation_samples":85}, "valid_state_coverage":.85}}


def physical_identity_report(directory="fixture"):
    return {"schema_version":1, "evaluation_status":"RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS", "source_trial":str(directory),
        "conservative_selected_identity":{"frames":100, "correct":60, "wrong":0, "unknown":40,
            "known_coverage":.6, "retention_lower_bound":.6},
        "conservative_task_time_identity":{"schema_version":1, "evaluation_status":"RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS",
            "coverage_basis":"fixed_10hz_request_to_recorded_clock_end", "sample_period_s":.1,
            "interval":{"start_s":0., "end_s":10.}, "scheduled_samples":100, "correct":60, "wrong":0, "unknown":40,
            "recorded_clock":{"start_s":0.,"end_s":10.,"messages":101},
            "known_coverage":.6, "retention_lower_bound":.6, "requested_task_count":1, "unconfirmed_requested_tasks":[],
            "tasks":{"fixture-task":{"request_time_s":0., "confirmation_time_s":0., "confirmed":True,
                "expected_physical_id":"fixture-physical-actor", "initial_mapping_known":True, "duplicate_request_uuid":False,
                "scheduled_samples":100,"correct":60,"wrong":0,"unknown":40,"known_coverage":.6,"retention_lower_bound":.6}}}}


def provenance(root, kind, script):
    return {"script":str(root/script), "script_sha256":v4.sha(root/script),
            "dependencies":{str(root/helper):v4.sha(root/helper) for helper in v4.REPORT_PROVENANCE_HELPERS[kind]}}


def fixture(root, *, navigation=True, gates=False, ros_distro="jazzy"):
    protocol = v4.load(ROOT / v4.PROTOCOL_PATH)
    # Test repositories have an explicit synthetic environment independent of
    # the production protocol selected by the workspace running this suite.
    # In particular a Humble freeze must not make this Jazzy fixture claim to
    # be an audited Humble registration merely by changing its file name.
    if ros_distro not in {"jazzy", "humble"}:
        raise ValueError("Unknown synthetic ROS environment")
    protocol["magnetic_library_registration"] = ("config/gazebo_magnetic_runtime_humble22.json"
                                                if ros_distro == "humble"
                                                else "config/gazebo_magnetic_runtime.json")
    if gates:
        protocol["navigation_acceptance"] = registered_gates()
    write(root / v4.PROTOCOL_PATH, protocol)
    for name in ("run_reliability_v4.py", "run_stage1_trial.py", "run_research_session.sh", "ros_python.sh",
                 "evaluate_stage1_flight.py", "evaluate_stage2_flight.py", "evaluate_stage3_gimbal.py", "evaluate_physical_identity.py",
                 "configure_gazebo_magnetic_contract.py", "prepare_px4_magnetic_compatibility.py", "evaluate_px4_source_clock.py",
                 "capture_gazebo_magnetic_libraries.py", "evaluate_online_state_accuracy.py", "extract_research_recording.py",
                 "px4_stage1_startup.sh", "run_stage1_flight.sh", "evaluate_native_startup.py", "capture_gazebo_rendering.py"):
        path = root / "scripts" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("# frozen fixture, never executed\n", encoding="utf-8")
    if navigation:
        (root / "scripts/evaluate_navigation_reference.py").write_text("# nav fixture\n", encoding="utf-8")
    path = root / "uav_tracking/research_failures.py"
    path.parent.mkdir()
    path.write_text("# classifier injected by fixture\n", encoding="utf-8")
    for relative in v4.OFFLINE_HELPERS:
        path = root/relative
        if not path.exists():
            path.write_text("# ORCHESTRATION_FIXTURE_ONLY: offline helper, never executed\n", encoding="utf-8")
    (root / "models").mkdir()
    (root / "models/yolo11n.pt").write_bytes(b"person-model-fixture")
    (root / "models/yolo11s.pt").write_bytes(b"car-model-fixture")
    (root / "config").mkdir()
    (root / "config/safety.yaml").write_text("prediction: 0.75\n", encoding="utf-8")
    (root / "config/gazebo_magnetic_reference.json").write_bytes((ROOT / "config/gazebo_magnetic_reference.json").read_bytes())
    lookup = v4.load(root/"config/gazebo_magnetic_reference.json")
    write(root/protocol["magnetic_library_registration"], {"schema_version":1, "status":"AUDITED_INSTALLED_PACKAGES",
        "environment_id":f"fixture_{ros_distro}_not_real_flight",
        "environment":{"os_id":"ubuntu", "os_version":"22.04" if ros_distro == "humble" else "24.04", "ros_distro":ros_distro},
        "source_registration":{key:lookup[key] for key in ("gazebo_sim_version", "gazebo_sim_commit", "gazebo_sim_source_sha256",
            "gazebo_sensors_version", "gazebo_sensors_commit", "gazebo_sensors_source_sha256")},
        "libraries":{kind:{"path":f"/fixture/{kind}.so", "sha256":str(i)*64, "package":"fixture-package-not-installed",
            "package_version":"fixture-version", "package_file_md5_matches":True} for i,kind in enumerate(("gazebo_sim", "gazebo_sensors"),1)},
        "package_repository_provenance":{"repository":"fixture repository", "authentication":"fixture authentication", "evidence":"fixture not real apt evidence"},
        "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
    write(root / v4.MAGNETIC_RUNTIME_PATH, {"schema_version":1, "contract":v4.MAGNETIC_CONTRACT,
        "operation":"RUNTIME_ARTIFACT_VERIFIED", "source_root":str(root/"isolated_px4_fixture"),
        "px4_commit":"fixture_commit_not_real_flight", "bridge_source_sha256":"fixture_source_not_real_flight",
        "patch_sha256":"fixture_patch_not_real_flight", "dependencies":{"fixture":{"commit":"fixture", "initialized":True}},
        "tracked_dirty_paths":["fixture_bridge.cpp"], "binary_path":str(root/"isolated_px4_fixture/bin/px4"),
        "binary_sha256":"fixture_binary_not_real_flight", "binary_bytes":42,
        "expected_startup_log_marker":"magnetic frame contract: "+v4.MAGNETIC_CONTRACT,
        "actual_startup_log_verified":False, "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
    patch_path = root/"patches/px4/gazebo_enu_flu_to_frd.patch"
    patch_path.parent.mkdir(parents=True)
    patch_path.write_text("fixture patch, never applied\n", encoding="utf-8")
    for relative in v4.SOURCE_CLOCK_HELPERS:
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("# frozen helper fixture, never executed\n", encoding="utf-8")
    for name in ("flight_supervisor.py", "startup_readiness.py"):
        (root/"ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter"/name).write_text(
            "# native takeoff fixture, never executed\n", encoding="utf-8")
    for model in ("x500_stage1", "x500_stage3"):
        path = root/f"ros2_ws/src/uav_tracking_bringup/models/{model}/model.sdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<sdf><model name="fixture"/></sdf>', encoding="utf-8")
    worlds = root / "ros2_ws/src/uav_tracking_bringup/worlds"
    worlds.mkdir(parents=True)
    for cls in v4.CLASSES:
        for name in [f"stage{stage}_flight_{cls}.sdf" for stage in (1, 2, 3)] + [f"stage3_multi_{cls}.sdf"]:
            (worlds / name).write_text('<sdf><world name="fixture"><magnetic_field>5.56e-6 2.13e-5 -4.15e-5</magnetic_field>'
                '<physics><real_time_factor>1.0</real_time_factor></physics><spherical_coordinates>'
                '<world_frame_orientation>ENU</world_frame_orientation><heading_deg>0</heading_deg>'
                '<latitude_deg>47.397971</latitude_deg><longitude_deg>8.546164</longitude_deg>'
                '</spherical_coordinates><plugin filename="gz-sim-magnetometer-system" name="gz::sim::systems::Magnetometer"/></world></sdf>', encoding="utf-8")
    return protocol


def plan(root, *, groups=None, classes=None, seeds=None, suffix="fixture", persist=True):
    result = make_fixture_plan(root, "results/" + suffix, "reliability_v4_" + suffix,
                          groups=groups or ["stage1_velocity"], classes=classes or ["person"],
                          seeds=[0, 1] if seeds is None else seeds)
    if persist:
        v4.persist_plan(result)
    return result


def fixture_runtime_verifier(root, manifest_path):
    manifest = v4.load(manifest_path)
    if manifest.get("evidence_scope") != "ORCHESTRATION_FIXTURE_ONLY":
        raise AssertionError("Test double must never stand in for real runtime evidence")
    return manifest


def make_fixture_plan(*args, **kwargs):
    with patch.object(v4, "verify_external_runtime", side_effect=fixture_runtime_verifier):
        return v4.make_plan(*args, **kwargs)


class FakeCommands:
    def __init__(self, *, surface="PASS", code=0, wrong_binding=False, clock="PASS", native="PASS"):
        self.calls = []
        self.surface = surface
        self.code = code
        self.wrong_binding = wrong_binding
        self.clock = clock
        self.native = native

    def __call__(self, command, log, root, timeout):
        self.calls.append(list(command))
        log.write_text("fixture command completed\n", encoding="utf-8")
        script = Path(command[2]).name
        code = 0
        if script == "run_stage1_trial.py":
            directory = root / "results" / command[command.index("--name") + 1]
            directory.mkdir(parents=True, exist_ok=False)
            option = lambda key: command[command.index("--" + key.replace("_", "-")) + 1]
            config = {key: option(key) for key in ["name", "command_mode", "gimbal_mode", "target_mode", "association_mode",
                "initial_select", "scenario_kind", "control_reference", "condition", "estimator_method", "model_path", "magnetic_environment",
                "magnetic_runtime_manifest", "magnetic_library_registration", "px4_time_mode", "takeoff_mode"]}
            config["gazebo_render_driver"] = option("gazebo_render_driver")
            config.update(target_class=option("class"))
            for key in ["stage", "seed", "initial_min_candidates", "inference_image_size", "inference_threads"]:
                config[key] = int(option(key))
            for key in ["speed_mps", "desired_distance_m", "duration", "real_time_factor", "max_inference_rate_hz", "monitor_tick_s", "short_occlusion_s"]:
                config[key] = float(option(key))
            config.update(multi_target="--multi-target" in command, occlusions=True, reselect_after_loss=True,
                          propagate_vehicle_uncertainty="--propagate-vehicle-uncertainty" in command,
                          supervisor_status_timestamp_mode="source_sim", supervisor_status_source_max_age_s=1.,
                          supervisor_status_source_max_future_s=.05, supervisor_status_timeout_wall_s=10.,
                          vehicle_control_point_offset_flu_m=[0., 0., .24])
            write(directory / "run_config.json", config)
            parameters = {
                "uav_tracking_detection": {"navigation_enabled": True, "depth_max_age_s": .02,
                    **{key: config[key] for key in ["model_path", "inference_image_size", "inference_threads", "max_inference_rate_hz"]}},
                "uav_tracking_state_estimator": {"navigation_enabled": True, "max_observation_age_s": .60,
                    "propagate_vehicle_uncertainty": True,
                    "max_prediction_duration_s": .75, "mahalanobis_gate": 9.21,
                    **{key: config[key] for key in ["target_mode", "association_mode", "estimator_method"]}},
                "uav_tracking_controller": {"state_topic": "/tracking/navigation_state", "desired_height_m": 2.,
                    "prediction_timeout_s": .75, **{key: config[key] for key in ["command_mode", "desired_distance_m"]}},
                "uav_tracking_px4_adapter": {"use_sim_time":True, "odometry_timestamp_mode":"source_sim",
                    "odometry_source_max_age_s":.50, "odometry_source_max_future_s":.05,
                    "vehicle_odometry_topic":"/fmu/out/vehicle_odometry", "vehicle_odom_topic":"/vehicle/odometry",
                    "odometry_timing_topic":"/vehicle/odometry_timing"},
                "uav_tracking_flight_supervisor":{"takeoff_mode":"px4_native","takeoff_height_m":3.,
                    "native_takeoff_timeout_sim_s":40., "native_wall_timeout_s":180.,
                    "status_timestamp_mode":"source_sim", "status_source_max_age_s":1.,
                    "status_source_max_future_s":.05, "status_timeout_s":10.,
                    "requested_simulation_real_time_factor":.5,
                    "auto_start":True,"simulation_only":True},
            }
            write(directory / "configuration/runtime_parameters.yaml", {key: {"ros__parameters": value} for key, value in parameters.items()})
            renderer_libraries = {"/usr/lib/x86_64-linux-gnu/dri/swrast_dri.so":{
                "sha256":"1"*64, "inode":123, "device_major":8, "device_minor":1},
                "/usr/lib/x86_64-linux-gnu/libLLVM-15.so.1":{
                "sha256":"2"*64, "inode":124, "device_major":8, "device_minor":1}}
            write(directory/"configuration/gazebo_rendering_libraries.json", {
                "schema_version":1, "status":"PASS", "owned_pid":8123,
                "expected_driver":config["gazebo_render_driver"], "actual_process_environment":{
                    "LIBGL_ALWAYS_SOFTWARE":"1", "MESA_LOADER_DRIVER_OVERRIDE":"swrast", "GALLIUM_DRIVER":"llvmpipe"},
                "actual_mappings":[f"7f001000-7f002000 r--p 00000000 08:01 {evidence['inode']} {library}"
                                   for library, evidence in renderer_libraries.items()],
                "actual_libraries":renderer_libraries,
                "contract_issues":[], "attempts":1, "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
            world_name = ("stage3_multi_" if config["multi_target"] else f"stage{config['stage']}_flight_") + config["target_class"] + ".sdf"
            source_world = root / "ros2_ws/src/uav_tracking_bringup/worlds" / world_name
            world_tree = ET.parse(source_world)
            shutil.copy2(source_world, directory/"configuration"/source_world.name)
            lookup_path = directory / "configuration/gazebo_magnetic_reference.json"
            lookup_path.write_bytes((root / "config/gazebo_magnetic_reference.json").read_bytes())
            lookup = v4.load(lookup_path)
            plugin = world_tree.find("world/plugin")
            ET.SubElement(plugin, "use_earth_frame_ned").text = "false"
            ET.SubElement(plugin, "use_units_gauss").text = "true"
            world_tree.find("world/physics/real_time_factor").text = ".5"
            runtime_world = directory / "configuration/runtime_world.sdf"
            world_tree.write(runtime_world, encoding="utf-8", xml_declaration=True)
            runtime_manifest = directory / "configuration/px4_magnetic_runtime.json"
            runtime_manifest.write_bytes((root/v4.MAGNETIC_RUNTIME_PATH).read_bytes())
            runtime = v4.load(runtime_manifest)
            write(directory / "configuration/magnetic_environment.json", {"magnetic_environment": v4.MAGNETIC_CONTRACT,
                "source_world": str(source_world), "source_world_sha256": v4.sha(source_world),
                "runtime_world": str(runtime_world), "runtime_world_sha256": v4.sha(runtime_world),
                "lookup_sha256": v4.sha(lookup_path), "gazebo_lookup_reference": lookup,
                "preserved_world_magnetic_field_initialization":world_tree.findtext("world/magnetic_field"),
                "world_field_is_actual_runtime_input":False, "px4_runtime":runtime,
                "px4_runtime_manifest_path":str(runtime_manifest), "px4_runtime_manifest_sha256":v4.sha(runtime_manifest),
                "sensor_mount":{"sensor_orientation_in_body_flu":"identity", "model_sha256":{
                    model:v4.sha(root/f"ros2_ws/src/uav_tracking_bringup/models/{model}/model.sdf")
                    for model in ("x500_stage1", "x500_stage3")}}, "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
            px4_log = directory/"px4.log"
            px4_log.write_text(runtime["expected_startup_log_marker"]+"\nfixture only; no real flight\n", encoding="utf-8")
            write(directory/"configuration/px4_magnetic_runtime_actual.json", {**runtime,
                "actual_startup_log_verified":True, "actual_startup_log_path":str(px4_log), "actual_startup_log_sha256":v4.sha(px4_log)})
            write(directory/"configuration/px4_parameters.json", {"explicit_environment_overrides":{
                "UXRCE_DDS_SYNCT":0, "SENS_EN_MAGSIM":0, "SENS_IMU_MODE":1, "MIS_TAKEOFF_ALT":3., "COM_TAKEOFF_ACT":0}})
            registration_path = directory/"configuration/gazebo_magnetic_runtime_registration.json"
            shutil.copy2(config["magnetic_library_registration"], registration_path)
            registration = v4.load(registration_path)
            write(directory/"configuration/gazebo_loaded_magnetic_libraries.json", {"schema_version":1, "verified":True,
                "registration_path":str(registration_path), "registration_sha256":v4.sha(registration_path),
                "environment_id":registration["environment_id"], "owned_leader_pid":42, "owned_session":42, "owned_process_group":42,
                "expected_source_registration":registration["source_registration"],
                "observed_processes":[{"pid":42, "session":42, "process_group":42}],
                "actual_loaded_libraries":[{"kind":kind, "mapped_path":item["path"], "sha256":item["sha256"],
                    "bytes":1000, "inode":i+100, "observed_pids":[42]} for i,(kind,item) in enumerate(registration["libraries"].items())],
                "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
            write(directory / "process_exit_codes.json", {"monitor": 0, "bag": 0, "ros": 0, "px4": 0, "gazebo": 0, "agent": 0})
            write(directory / "summary.json", {"termination_reason": "completed"})
            (directory / "rosbag").mkdir()
            (directory / "rosbag/metadata.yaml").write_text("fixture metadata only\n", encoding="utf-8")
            code = self.code
        else:
            output = Path(command[command.index("--output") + 1])
            directory = output.parent
            bag = directory / "rosbag"
            if self.wrong_binding:
                bag = root / "results/old_trial/rosbag"
            if script == "evaluate_px4_source_clock.py":
                report = {"schema_version":1, "evaluation_status":self.clock, "source_clock_pass":self.clock=="PASS",
                    "clock_domain_valid":self.clock=="PASS", "vehicle_frame_continuity_valid":True,
                    "trial":str(directory if not self.wrong_binding else root/"results/old_trial"),
                    "counts":{"raw_px4":10,"timing_diagnostics":10,"adapted_odometry":10,"claimed_accepted":10,
                        "claimed_rejected":0,"independently_matched_triplets":10}, "failures":{} if self.clock=="PASS" else {"fixture_rejection":1},
                    "incomplete_evidence":{}, "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY",
                    "evaluation_source":{"script_sha256":v4.sha(root/"scripts/evaluate_px4_source_clock.py"),
                        "dependencies":{str(root/helper):v4.sha(root/helper) for helper in v4.SOURCE_CLOCK_HELPERS}}}
                code = 0 if self.clock=="PASS" else 2
            elif script == "evaluate_native_startup.py":
                report = {"schema_version":1,"evaluation_status":self.native,"native_startup_pass":self.native=="PASS",
                    "trial":str(directory if not self.wrong_binding else root/"results/old_trial"),
                    "checks":{key:True if self.native=="PASS" else False if self.native=="FAIL" else None
                              for key in v4.NATIVE_STARTUP_CHECKS},
                    "failures":{} if self.native!="FAIL" else {"fixture_native_rejection":1},
                    "incomplete_evidence":{} if self.native!="INCOMPLETE_EVIDENCE" else {"fixture_missing_evidence":1},
                    "evaluation_source":provenance(root,"native_startup","scripts/"+script),
                    "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"}
                code = 0 if self.native=="PASS" else 2
            elif script == "evaluate_stage1_flight.py":
                report = {"schema_version": 3, "acceptance": {"result": self.surface}, "inputs": {"bag": str(bag)}}
            elif script == "evaluate_stage2_flight.py":
                report = {"schema_version": 1, "result": "PASS", "inputs": {"bag": str(bag)}}
            elif script == "evaluate_stage3_gimbal.py":
                report = {"schema_version": 3, "result": "PASS", "metadata": {"bag": str(bag)}}
            elif script == "evaluate_physical_identity.py":
                report = physical_identity_report(directory)
                report["evaluation_source"] = provenance(root, "physical_identity", "scripts/"+script)
            else:
                report = navigation_report(directory)
                report["evaluation_source"] = provenance(root, "navigation", "scripts/"+script)
            write(output, report)
        return {"command": list(command), "returncode": code, "log": str(log), "error": None}


def healthy_infrastructure(directory, attempts):
    return {"stop": False, "reasons": [], "evidence": {"bag": {"metadata_exists": True}, "attempts": len(attempts)}}


def run(plan_, fake=None, **options):
    with patch.object(v4, "verify_external_runtime", side_effect=fixture_runtime_verifier):
        return v4.run_plan(plan_, command_runner=fake or FakeCommands(), process_probe=lambda: [],
                           infrastructure=healthy_infrastructure, **options)


def fixture_probe_gate(root):
    """Exercise 12 orchestration fixtures; this never creates real flight evidence."""
    development = plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[0], suffix="gate_fixtures")
    result = run(development)
    if result["status_counts"] != {"PASS":12}:
        raise AssertionError(result)
    gate = {"schema_version":2, "result":"PASS", "ready_for_formal_reliability_v4":True,
        "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY", "checks":{key:True for key in v4.PROBE_CHECKS},
        "bindings":{"flight_source_hashes":v4.flight_source_hashes(development["source_hashes"]),
            "evaluation_source_hashes":v4.offline_source_hashes(development["source_hashes"]),
            "model_hashes":development["model_hashes"],
            "magnetic_runtime_manifest_sha256":development["magnetic_runtime_binding"]["manifest_sha256"],
            "magnetic_library_registration_sha256":development["magnetic_library_binding"]["registration_sha256"],
            "navigation_acceptance_sha256":v4.digest(development["protocol"]["navigation_acceptance"])},
        "probe_slots":[{"plan_path":str(Path(development["output"])/"plan.json"),
            "plan_file_sha256":v4.sha(Path(development["output"])/"plan.json"), "slot_id":trial["id"],
            "record_file_sha256":v4.sha(v4.record_path(development,trial))} for trial in development["trials"]]}
    path = root/"probe_gate.json"
    write(path, gate)
    return path


class ReliabilityV4Tests(unittest.TestCase):
    def test_actual_renderer_archive_is_required_and_driver_environment_is_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0])
            trial = frozen["trials"][0]
            FakeCommands()(trial["flight_command"], root/"fixture_log.txt", root, 1.)
            directory = Path(trial["directory"])
            path = directory/"configuration/gazebo_rendering_libraries.json"
            original = v4.load(path)
            self.assertFalse(v4.gazebo_rendering_evidence(directory, "llvmpipe")["errors"])
            for defect in ("status", "driver", "env", "llvm", "d3d12", "hash", "mapping", "inode", "mapsyntax"):
                with self.subTest(defect=defect):
                    report = deepcopy(original)
                    if defect == "status":report["status"] = "FAIL"
                    elif defect == "driver":report["expected_driver"] = "auto"
                    elif defect == "env":report["actual_process_environment"]["GALLIUM_DRIVER"] = "d3d12"
                    elif defect == "llvm":report["actual_libraries"].pop("/usr/lib/x86_64-linux-gnu/libLLVM-15.so.1")
                    elif defect == "d3d12":report["actual_mappings"].append(
                        "7f001000-7f002000 r--p 00000000 00:00 234 /usr/lib/wsl/drivers/nv-fake/libd3d12core.so")
                    elif defect == "hash":next(iter(report["actual_libraries"].values()))["sha256"] = "unbound"
                    elif defect == "inode":next(iter(report["actual_libraries"].values()))["inode"] = 999
                    elif defect == "mapsyntax":report["actual_mappings"] = ["not a proc maps line"]
                    else:report["actual_mappings"] = []
                    write(path, report)
                    self.assertTrue(v4.gazebo_rendering_evidence(directory, "llvmpipe")["errors"])
                    self.assertTrue(any(error.startswith("gazebo_rendering:")
                                        for error in v4.runtime_configuration(frozen, trial)["errors"]))
            path.unlink()
            self.assertTrue(v4.gazebo_rendering_evidence(directory, "llvmpipe")["errors"])

    def test_new_renderer_protocol_is_explicit_and_rejects_legacy_auto(self):
        original = v4.load(ROOT/v4.PROTOCOL_PATH)
        self.assertEqual(original["gazebo_render_driver"], "llvmpipe")
        for driver in (None, "auto", "d3d12"):
            with self.subTest(driver=driver):
                protocol = deepcopy(original)
                if driver is None:protocol.pop("gazebo_render_driver")
                else:protocol["gazebo_render_driver"] = driver
                with self.assertRaisesRegex(ValueError, "gazebo_render_driver"):
                    v4.validate_protocol(protocol)

    def test_replay_tools_bind_full_manifest_but_do_not_force_flight_source_changes(self):
        offline = {"scripts/export_estimator_replay_v4.py", "scripts/run_estimator_replay_v4.py",
                   "uav_tracking/replay_comparison.py", "uav_tracking/replay_export.py",
                   "uav_tracking/navigation_reproduction.py"}
        online = {"uav_tracking/recording_archive.py", "uav_tracking/core/kalman.py"}
        hashes = {relative:v4.sha(ROOT/relative) for relative in offline | online}
        self.assertEqual(set(v4.offline_source_hashes(hashes)), offline)
        self.assertEqual(set(v4.flight_source_hashes(hashes)), online)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            frozen = plan(root, seeds=[0])
            self.assertTrue(offline <= set(frozen["source_hashes"]))
            self.assertTrue(offline.isdisjoint(v4.flight_source_hashes(frozen["source_hashes"])))

    def test_formal_requires_registered_numeric_gates_and_real_named_probe_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            gate = root/"probe_gate.json"
            write(gate, {"result":"PASS", "ready_for_formal_reliability_v4":True, "checks":{"development_probe":True}})
            with self.assertRaisesRegex(ValueError, "REGISTERED"):
                make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=gate)
            protocol = v4.load(root/v4.PROTOCOL_PATH)
            protocol["navigation_acceptance"] = registered_gates()
            write(root/v4.PROTOCOL_PATH, protocol)
            with self.assertRaisesRegex(ValueError, "probe gate has not passed"):
                make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=gate)
        for key, invalid in (("maximum_base_link_distance_rmse_m", -1.), ("maximum_base_link_height_rmse_m", True),
                             ("minimum_valid_state_coverage", 1.1), ("minimum_truth_coverage", float("nan")),
                             ("minimum_physical_identity_coverage", None), ("require_final_window_settled", 1)):
            with self.subTest(key=key):
                gates = registered_gates(); gates[key] = invalid
                with self.assertRaises(ValueError):
                    v4.validate_navigation_gates(gates)

    def test_probe_gate_requires_complete_matrix_and_preserved_artifact_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); path = fixture_probe_gate(root)
            original = v4.load(path)
            for defect in ("subset", "source_binding", "record_binding", "missing_named_check", "missing_plan"):
                with self.subTest(defect=defect):
                    gate = deepcopy(original)
                    if defect == "subset":gate["probe_slots"].pop()
                    elif defect == "source_binding":gate["bindings"]["model_hashes"] = {}
                    elif defect == "record_binding":gate["probe_slots"][0]["record_file_sha256"] = "0"*64
                    elif defect == "missing_named_check":gate["checks"].pop(v4.PROBE_CHECKS[0])
                    else:gate["probe_slots"][0]["plan_path"] = str(root/"missing_plan.json")
                    write(path, gate)
                    with self.assertRaises(ValueError):
                        make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=path)
                    self.assertFalse((root/"results/formal").exists())

    def test_probe_offline_revision_requires_new_named_report_with_actual_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); path = fixture_probe_gate(root)
            gate = v4.load(path)
            (root/"scripts/evaluate_navigation_reference.py").write_text("# second offline fixture revision\n", encoding="utf-8")
            gate["bindings"]["evaluation_source_hashes"] = v4.offline_source_hashes(v4.source_hashes(root))
            write(path, gate)
            with self.assertRaisesRegex(ValueError, "Changed offline evaluator"):
                make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=path)
            original_reports = {}
            for item in gate["probe_slots"]:
                previous = v4.load(item["plan_path"])
                trial = next(trial for trial in previous["trials"] if trial["id"] == item["slot_id"])
                spec = next(entry for entry in trial["evaluations"] if entry["kind"] == "navigation")
                original_reports[spec["report"]] = v4.sha(spec["report"])
                replacement = Path(trial["directory"])/"navigation_second_offline_fixture.json"
                report = v4.load(spec["report"])
                report["evaluation_source"] = provenance(root, "navigation", spec["script"])
                write(replacement, report)
                item["evaluation_overrides"] = [{"kind":"navigation", "report":str(replacement),
                    "report_sha256":v4.sha(replacement), "evaluation_root":str(root),
                    "execution":{"returncode":0,"error":None,"evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"}}]
            write(path, gate)
            formal = make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=path)
            v4.validate_plan(formal)
            self.assertEqual(len(formal["trials"]), 120)
            self.assertEqual({name:v4.sha(name) for name in original_reports}, original_reports)

    def test_formal_matrix_is_exactly_120_and_commands_freeze_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root, gates=True)
            gate = fixture_probe_gate(root)
            actual = make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, probe_gate=gate)
            self.assertEqual(len(actual["trials"]), 120)
            self.assertEqual(len({t["name"] for t in actual["trials"]}), 120)
            for cls in v4.CLASSES:
                for group in v4.GROUPS:
                    rows = [t for t in actual["trials"] if t["target_class"] == cls and t["group"] == group]
                    self.assertEqual([t["seed"] for t in rows], list(range(1000, 1010)))
                    for trial in rows:
                        command = trial["flight_command"]
                        for flag, expected in [("--duration", "45.0"), ("--real-time-factor", "0.5"),
                                               ("--max-inference-rate-hz", "10.0"), ("--monitor-tick-s", "0.02"),
                                               ("--control-reference", "ground_footprint")]:
                            self.assertEqual(command[command.index(flag) + 1], expected)
                        self.assertIn("--occlusions", command)
                        self.assertIn("--propagate-vehicle-uncertainty", command)
                        self.assertEqual(command[command.index("--magnetic-environment") + 1], "gazebo_enu")
                        self.assertEqual(Path(command[command.index("--magnetic-runtime-manifest") + 1]).resolve(), (root/v4.MAGNETIC_RUNTIME_PATH).resolve())
                        self.assertEqual(command[command.index("--px4-time-mode") + 1], "source_sim")
                        self.assertEqual(command[command.index("--takeoff-mode") + 1], "px4_native")
                        self.assertEqual(command[command.index("--gazebo-render-driver") + 1], "llvmpipe")
                        self.assertEqual(trial["gazebo_render_driver"], "llvmpipe")
                        self.assertEqual(Path(command[command.index("--magnetic-library-registration") + 1]).resolve(),
                                         (root/actual["protocol"]["magnetic_library_registration"]).resolve())
                        self.assertIn("--reselect-after-loss", command)
                        self.assertEqual(trial["inference_image_size"], 640 if cls == "car" else 320)
                        self.assertEqual(trial["inference_threads"], 4 if cls == "car" else 2)
            multi = next(t for t in actual["trials"] if t["group"] == "stage3_multi_active")
            self.assertIn("--multi-target", multi["flight_command"])
            self.assertEqual(multi["target_mode"], "locked_target")
            self.assertEqual(multi["association_mode"], "hybrid_3d")
            self.assertEqual(multi["initial_select"], "middle")
            self.assertFalse((root / "results/formal").exists())

    def test_development_seeds_stay_separate_from_held_out_formal_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            development = make_fixture_plan(root, "results/dev", "reliability_v4_dev", groups=["stage1_velocity"], classes=["person"])
            self.assertEqual(development["selected_seeds"], [0])
            self.assertEqual(plan(root, seeds=[0, 1, 3], persist=False)["selected_seeds"], [0, 1, 3])
            with self.assertRaisesRegex(ValueError, "Held-out formal seeds"):
                plan(root, seeds=[1000], persist=False)
            with self.assertRaisesRegex(ValueError, "Held-out formal seeds"):
                plan(root, seeds=[0, 1009], persist=False)

    def test_formal_rejects_subset_and_unpassed_probe_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            for options in ({}, {"seeds": [0]}, {"groups": ["stage1_velocity"]}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    make_fixture_plan(root, "results/formal", "reliability_v4_formal", formal=True, **options)

    def test_draft_preregistration_has_no_false_formal_completion(self):
        protocol = v4.load(ROOT / v4.PROTOCOL_PATH)
        self.assertEqual(protocol["status"], "DRAFT_NOT_FROZEN_NOT_EXECUTED")
        self.assertNotEqual(protocol["navigation_acceptance"]["status"], "REGISTERED")

    def test_model_source_config_and_new_files_are_checked_before_any_command(self):
        for relative in ["models/yolo11n.pt", "config/safety.yaml", "scripts/new_algorithm.py", v4.PROTOCOL_PATH]:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); frozen = plan(root)
                path = root / relative
                path.write_text("changed frozen input\n", encoding="utf-8")
                fake = FakeCommands()
                with self.assertRaisesRegex(ValueError, "Frozen source"):
                    run(frozen, fake)
                self.assertEqual(fake.calls, [])

    def test_pending_old_result_or_existing_plan_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root)
            with self.assertRaises(FileExistsError):
                v4.persist_plan(frozen)
            Path(frozen["trials"][0]["directory"]).mkdir()
            with self.assertRaisesRegex(ValueError, "Pending trial already"):
                run(frozen)

    def test_resume_consumes_only_pending_and_never_overwrites_terminal_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); frozen = plan(root)
            first = FakeCommands(surface="FAIL")
            state = run(frozen, first, max_new_trials=1)
            self.assertEqual(state["status_counts"], {"FAIL": 1, "PENDING": 1})
            path = v4.record_path(frozen, frozen["trials"][0]); before = path.read_bytes()
            second = FakeCommands()
            state = run(frozen, second)
            self.assertEqual(state["status_counts"], {"FAIL": 1, "PASS": 1})
            self.assertEqual(before, path.read_bytes())
            flights = [c for c in second.calls if Path(c[2]).name == "run_stage1_trial.py"]
            self.assertEqual(len(flights), 1)
            self.assertIn(frozen["trials"][1]["name"], flights[0])
            self.assertEqual(run(frozen)["started_this_invocation"], 0)

    def test_complete_reports_and_zero_exit_do_not_pass_unregistered_navigation_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root, seeds=[0])
            self.assertEqual(run(frozen)["status_counts"], {"EVALUATION_PENDING": 1})
            row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
            self.assertEqual(row["flight_exit_code"], 0)
            self.assertEqual(row["evaluations"][-1]["result"], "RECORDED_WITH_CENSORED_FAILURES")

    def test_missing_navigation_at_freeze_stays_pending_and_never_runs_foreign_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, navigation=False, gates=True); frozen = plan(root, seeds=[0])
            fake = FakeCommands()
            self.assertEqual(run(frozen, fake)["status_counts"], {"EVALUATION_PENDING": 1})
            self.assertFalse(any(Path(c[2]).name == "evaluate_navigation_reference.py" for c in fake.calls))

    def test_infrastructure_stop_is_retained_without_retry_and_requires_bound_diagnosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root)
            fake = FakeCommands()
            bad = lambda directory, attempts: {"stop": True, "reasons": [{"code": "MISSING_BAG"}], "evidence": {}}
            with patch.object(v4, "verify_external_runtime", side_effect=fixture_runtime_verifier):
                result = v4.run_plan(frozen, command_runner=fake, process_probe=lambda: [], infrastructure=bad)
            self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR": 1, "PENDING": 1})
            self.assertEqual(len(fake.calls), 1)
            with self.assertRaisesRegex(RuntimeError, "requires diagnosis"):
                run(frozen)
            row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
            resolution = {"result": "PASS", "resolved_record_sha256": [row["record_sha256"]],
                          "diagnosis": "Independent fixture storage restored"}
            result = run(frozen, resolution=resolution)
            self.assertEqual(result["started_this_invocation"], 1)
            self.assertEqual(v4.read_slots(frozen)[row["id"]]["record_sha256"], row["record_sha256"])

    def test_crash_marker_becomes_terminal_interrupted_and_is_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root)
            trial = frozen["trials"][0]
            v4.write_new(v4.record_path(frozen, trial, "started.json"), {"id": trial["id"], "plan_sha256": frozen["plan_sha256"]})
            fake = FakeCommands(); state = run(frozen, fake)
            self.assertEqual(state["status_counts"], {"INTERRUPTED": 1, "PENDING": 1})
            self.assertEqual(fake.calls, [])
            self.assertTrue(v4.record_path(frozen, trial, "started.json").is_file())

    def test_terminal_ledger_and_artifact_tampering_are_detected(self):
        for target in ["record", "artifact"]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); frozen = plan(root, seeds=[0]); run(frozen)
                trial = frozen["trials"][0]
                if target == "record":
                    path = v4.record_path(frozen, trial); row = v4.load(path); row["status"] = "PASS"; write(path, row)
                else:
                    (Path(trial["directory"]) / "summary.json").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "changed"):
                    v4.status(frozen)

    def test_wrong_input_bag_binding_stops_and_preserves_the_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); frozen = plan(root)
            fake = FakeCommands(wrong_binding=True)
            result = run(frozen, fake)
            self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR": 1, "PENDING": 1})
            row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
            self.assertEqual(row["evaluations"][0]["result"], "INVALID")
            self.assertIn("bound", row["evaluations"][0]["error"])

    def test_existing_simulator_blocks_before_starting_or_creating_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root); fake = FakeCommands()
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                with patch.object(v4, "verify_external_runtime", side_effect=fixture_runtime_verifier):
                    v4.run_plan(frozen, command_runner=fake, process_probe=lambda: [{"pid": 123, "argv": ["px4"]}],
                                infrastructure=healthy_infrastructure)
            self.assertEqual(fake.calls, [])
            self.assertEqual(v4.status(frozen)["status_counts"], {"PENDING": 2})

    def test_navigation_scores_base_link_and_keeps_censored_failures(self):
        report = navigation_report()
        report["whole_interval"]["metrics"]["base_link_distance_error_m"]["rmse"] = 2.
        report["whole_interval"]["metrics"]["model_origin_distance_error_m"]["rmse"] = .01
        report["whole_interval"]["transients"]["base_link"]["distance"].update(
            settled_through_interval_end=False, settling_right_censored=True, settling_time_s=None)
        verdict, evidence = v4.navigation_verdict(report, registered_gates())
        self.assertEqual(verdict, "FAIL")
        self.assertFalse(evidence["checks"]["base_link_distance"])
        self.assertFalse(evidence["checks"]["final_distance_settled"])

    def test_navigation_rejects_malformed_counts_coverage_rmse_and_settling(self):
        mutations = ((('whole_interval','scheduled_samples'), 0),
                     (('whole_interval','matched_truth_samples'), 101),
                     (('whole_interval','metrics','base_link_distance_error_m','rmse'), -.1),
                     (('whole_interval','metrics','base_link_height_error_m','count'), 0),
                     (('kf_navigation','valid_state_coverage'), 1.5),
                     (('kf_navigation','valid_state_coverage'), True),
                     (('kf_navigation','counts','valid_navigation_samples'), 90),
                     (('kf_navigation','counts','scheduled_samples'), 99),
                     (('interval','navigation_evaluation_start_s'), 5.),
                     (('interval','sample_period_s'), .2),
                     (('whole_interval','transients','base_link','distance','settling_right_censored'), True),
                     (('whole_interval','transients','base_link','distance','settling_time_s'), None),
                     (('whole_interval','transients','base_link','distance','settling_time_s'), 8.),
                     (('whole_interval','transients','base_link','distance','minimum_in_band_duration_s'), .1),
                     (('whole_interval','transients','base_link','height','band_m'), 3.),
                     (('whole_interval','transients','base_link','distance','duplicate_source_times'), True))
        for keys, value in mutations:
            with self.subTest(keys=keys):
                report = navigation_report(); node = report
                for key in keys[:-1]:node = node[key]
                node[keys[-1]] = value
                self.assertEqual(v4.navigation_verdict(report, registered_gates())[0], "INCOMPLETE_EVIDENCE")

    def test_actual_navigation_and_identity_evaluator_schemas_match_acceptance(self):
        from tests import test_navigation_evaluation as navigation
        from tests import test_physical_identity_evaluator as identity
        rows, config, _ = navigation.fixture()
        report = navigation.evaluation.evaluate(rows, config)
        self.assertEqual(v4.navigation_verdict(report, registered_gates())[0], "PASS")
        frames = [identity.identity_row(1.01 + i * .1) for i in range(10)]
        timed = identity.evaluation.task_time_identity(frames, [identity.requested()],
            [{"target_uuid":"task", "time_s":1.}], [0.,1.,2.],
            lambda timestamp:{"gt":[identity.object_("A",0,10),identity.object_("B",20,30)],"truth_complete":True})
        report = {"schema_version":1,"evaluation_status":"RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS",
            "conservative_selected_identity":identity.evaluation.selected_identity_summary(frames),
            "conservative_task_time_identity":timed}
        self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "PASS")

    def test_native_takeoff_runtime_and_startup_sources_are_required(self):
        for defect in ("supervisor_mode", "takeoff_height", "takeoff_action", "recorded_mode", "multiple_ekf_instances",
                       "status_mode", "status_source_age", "status_future", "status_wall", "recorded_status_mode",
                       "recorded_gazebo_driver"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0]); fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    execution = fake(command, log, current_root, timeout)
                    if Path(command[2]).name != "run_stage1_trial.py":return execution
                    directory = Path(frozen["trials"][0]["directory"])
                    if defect == "supervisor_mode":
                        path = directory/"configuration/runtime_parameters.yaml"; report = v4.load(path)
                        report["uav_tracking_flight_supervisor"]["ros__parameters"]["takeoff_mode"] = "offboard_velocity"
                    elif defect in {"status_mode", "status_source_age", "status_future", "status_wall"}:
                        path = directory/"configuration/runtime_parameters.yaml"; report = v4.load(path)
                        key, value = {"status_mode":("status_timestamp_mode", "receipt_wall"),
                                      "status_source_age":("status_source_max_age_s", 2.),
                                      "status_future":("status_source_max_future_s", .5),
                                      "status_wall":("status_timeout_s", 20.)}[defect]
                        report["uav_tracking_flight_supervisor"]["ros__parameters"][key] = value
                    elif defect == "recorded_status_mode":
                        path = directory/"run_config.json"; report = v4.load(path)
                        report["supervisor_status_timestamp_mode"] = "receipt_wall"
                    elif defect == "recorded_gazebo_driver":
                        path = directory/"run_config.json"; report = v4.load(path)
                        report["gazebo_render_driver"] = "auto"
                    elif defect == "recorded_mode":
                        path = directory/"run_config.json"; report = v4.load(path); report["takeoff_mode"] = "offboard_velocity"
                    else:
                        path = directory/"configuration/px4_parameters.json"; report = v4.load(path)
                        key = "MIS_TAKEOFF_ALT" if defect == "takeoff_height" else "SENS_IMU_MODE" if defect == "multiple_ekf_instances" else "COM_TAKEOFF_ACT"
                        report["explicit_environment_overrides"][key] = 0 if defect == "multiple_ekf_instances" else 1
                    write(path, report)
                    return execution

                self.assertEqual(run(frozen, corrupt)["status_counts"], {"INFRASTRUCTURE_ERROR":1})
                self.assertEqual(len(fake.calls), 1)
        for relative in ("scripts/px4_stage1_startup.sh", "scripts/run_stage1_flight.sh",
                         "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py",
                         "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/startup_readiness.py"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); (root/relative).unlink()
                with self.assertRaisesRegex(ValueError, "Missing required frozen source"):
                    plan(root, seeds=[0], persist=False)

    def test_full_task_time_identity_cannot_hide_silent_tail_or_unconfirmed_task(self):
        report = physical_identity_report()
        self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "PASS")
        report["conservative_selected_identity"].update(correct=100,unknown=0,known_coverage=1.,retention_lower_bound=1.)
        timed = report["conservative_task_time_identity"]
        timed.update(correct=10,unknown=90,known_coverage=.1,retention_lower_bound=.1)
        timed["tasks"]["fixture-task"].update(correct=10,unknown=90,known_coverage=.1,retention_lower_bound=.1)
        self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "FAIL")
        report = physical_identity_report(); timed = report["conservative_task_time_identity"]
        timed["unconfirmed_requested_tasks"] = ["fixture-task"]
        timed.update(correct=0,unknown=100,known_coverage=0.,retention_lower_bound=0.)
        timed["tasks"]["fixture-task"].update(confirmed=False,confirmation_time_s=None,
            correct=0,unknown=100,known_coverage=0.,retention_lower_bound=0.)
        self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "FAIL")
        report = physical_identity_report()
        report["conservative_selected_identity"].update(wrong=1,correct=59)
        self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "FAIL")

    def test_identity_rejects_impossible_numerators_ratios_grid_and_uuid_schema(self):
        for defect in ("coverage", "counts", "grid", "period", "task_count", "duplicate_uuid", "confirmation", "wrong_time_type",
                       "truncated_clock", "delayed_first_request", "unmapped_known_identity"):
            with self.subTest(defect=defect):
                report = physical_identity_report(); timed = report["conservative_task_time_identity"]
                if defect == "coverage":timed["known_coverage"] = 2.
                elif defect == "counts":timed["wrong"] = -1
                elif defect == "grid":timed["interval"]["end_s"] = 15.
                elif defect == "period":timed["sample_period_s"] = True
                elif defect == "task_count":timed["requested_task_count"] = 2
                elif defect == "duplicate_uuid":timed["tasks"]["fixture-task"]["duplicate_request_uuid"] = True
                elif defect == "confirmation":timed["tasks"]["fixture-task"]["confirmation_time_s"] = -1.
                elif defect == "wrong_time_type":timed["tasks"]["fixture-task"]["request_time_s"] = "0"
                elif defect == "truncated_clock":timed["recorded_clock"]["end_s"] = 20.
                elif defect == "delayed_first_request":
                    timed["tasks"]["fixture-task"].update(request_time_s=1.,confirmation_time_s=1.)
                else:timed["tasks"]["fixture-task"].update(initial_mapping_known=False,expected_physical_id=None)
                self.assertEqual(v4.physical_identity_verdict(report, registered_gates())[0], "INCOMPLETE_EVIDENCE")

    def test_engineering_requires_every_independent_evaluator_once_including_source_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True)
            frozen = plan(root, groups=["stage3_multi_active"], seeds=[0]); run(frozen)
            trial = frozen["trials"][0]
            record = v4.load(v4.record_path(frozen,trial))
            flight = next(entry for entry in record["commands"] if entry["kind"] == "flight")
            entries = record["evaluations"]
            for kind in v4.required_evaluators(trial):
                with self.subTest(kind=kind):
                    subset = [entry for entry in entries if entry["kind"] != kind]
                    self.assertEqual(v4.engineering_verdict(frozen, trial, flight, subset)[0], "INCOMPLETE_EVIDENCE")
            self.assertEqual(v4.engineering_verdict(frozen, trial, flight, entries+[entries[0]])[0], "INCOMPLETE_EVIDENCE")
            clock_entry = next(entry for entry in entries if entry["kind"] == "source_clock")
            clock_report = v4.load(clock_entry["report"]); clock_report["clock_domain_valid"] = False
            write(Path(clock_entry["report"]), clock_report)
            clock_entry["report_sha256"] = v4.sha(clock_entry["report"])
            self.assertEqual(v4.engineering_verdict(frozen, trial, flight, entries)[0], "INCOMPLETE_EVIDENCE")

    def test_multi_target_identity_unknown_remains_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True)
            frozen = plan(root, groups=["stage3_multi_active"], classes=["car"], seeds=[0])
            self.assertEqual(run(frozen)["status_counts"], {"PASS": 1})
            row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
            identity = row["engineering_evidence"]["physical_identity"]
            self.assertEqual(identity["unknown"], 40)
            self.assertEqual(identity["retention_lower_bound"], .6)
            self.assertEqual(identity["wrong"], 0)

    def test_altered_plan_digest_or_weakened_safety_never_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root)
            altered = deepcopy(frozen); altered["trials"][0]["seed"] = 99
            with self.assertRaisesRegex(ValueError, "digest"):
                run(altered)
            altered = deepcopy(frozen); altered["protocol"]["safety_gates"]["max_prediction_duration_s"] = 2.
            altered["plan_sha256"] = v4.digest(altered, ("plan_sha256",))
            with self.assertRaisesRegex(ValueError, "safety"):
                run(altered)

    def test_actual_world_hash_field_and_vehicle_covariance_switch_are_qualified(self):
        for defect in ("stale_world_hash", "wrong_actual_field", "pose_propagation_disabled"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); frozen = plan(root)
                fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    result = fake(command, log, current_root, timeout)
                    if Path(command[2]).name == "run_stage1_trial.py":
                        directory = Path(frozen["trials"][0]["directory"]) / "configuration"
                        if defect == "stale_world_hash":
                            path = directory / "magnetic_environment.json"
                            evidence = v4.load(path); evidence["runtime_world_sha256"] = "0" * 64; write(path, evidence)
                        elif defect == "wrong_actual_field":
                            path = directory / "runtime_world.sdf"
                            tree = ET.parse(path); tree.find("world/magnetic_field").text = "1e-5 1e-5 -1e-5"
                            tree.write(path)
                            evidence_path = directory / "magnetic_environment.json"
                            evidence = v4.load(evidence_path); evidence["runtime_world_sha256"] = v4.sha(path); write(evidence_path, evidence)
                        else:
                            path = directory / "runtime_parameters.yaml"
                            parameters = v4.load(path)
                            parameters["uav_tracking_state_estimator"]["ros__parameters"]["propagate_vehicle_uncertainty"] = False
                            write(path, parameters)
                    return result

                result = run(frozen, corrupt)
                self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR": 1, "PENDING": 1})
                self.assertEqual(len(fake.calls), 1)
                row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
                self.assertTrue(row["runtime_configuration"]["errors"])

    def test_missing_real_runtime_manifest_cannot_be_fabricated_by_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            (root/v4.MAGNETIC_RUNTIME_PATH).unlink()
            with self.assertRaisesRegex(ValueError, "not yet available"):
                make_fixture_plan(root, "results/new", "reliability_v4_new", seeds=[0], groups=["stage1_velocity"], classes=["person"])
            self.assertFalse((root/v4.MAGNETIC_RUNTIME_PATH).exists())
            self.assertFalse((root/"results").exists())

    def test_fixture_runtime_is_explicitly_rejected_by_the_real_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            with self.assertRaisesRegex(ValueError, "Fixture magnetic runtime"):
                v4.make_plan(root, "results/not_real", "reliability_v4_not_real", seeds=[0], groups=["stage1_velocity"], classes=["person"])

    def test_changed_external_binary_binding_blocks_before_any_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root); fake = FakeCommands()
            changed = deepcopy(frozen["magnetic_runtime_binding"]["manifest"])
            changed["binary_sha256"] = "changed external binary"
            with patch.object(v4, "verify_external_runtime", return_value=changed), self.assertRaisesRegex(ValueError, "runtime changed"):
                v4.run_plan(frozen, command_runner=fake, process_probe=lambda: [], infrastructure=healthy_infrastructure)
            self.assertEqual(fake.calls, [])

    def test_runtime_patch_binary_path_log_plugin_and_source_clock_are_bound(self):
        for defect in ("binary_hash", "binary_path", "bridge_source", "startup_log", "plugin_frame", "plugin_units", "source_mode", "clock_future_limit"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); frozen = plan(root, seeds=[0]); fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    result = fake(command, log, current_root, timeout)
                    if Path(command[2]).name != "run_stage1_trial.py":
                        return result
                    directory = Path(frozen["trials"][0]["directory"])
                    if defect in {"binary_hash", "binary_path", "bridge_source"}:
                        path = directory/"configuration/px4_magnetic_runtime_actual.json"
                        document = v4.load(path)
                        key = {"binary_hash":"binary_sha256", "binary_path":"binary_path", "bridge_source":"bridge_source_sha256"}[defect]
                        document[key] = "wrong historical artifact"
                        write(path, document)
                    elif defect == "startup_log":
                        (directory/"px4.log").write_text("marker absent\n", encoding="utf-8")
                    elif defect in {"plugin_frame", "plugin_units"}:
                        path = directory/"configuration/runtime_world.sdf"
                        tree = ET.parse(path)
                        tree.find("world/plugin/"+("use_earth_frame_ned" if defect=="plugin_frame" else "use_units_gauss")).text = "true" if defect=="plugin_frame" else "false"
                        tree.write(path)
                        evidence_path = directory/"configuration/magnetic_environment.json"
                        document = v4.load(evidence_path); document["runtime_world_sha256"] = v4.sha(path); write(evidence_path, document)
                    else:
                        path = directory/"configuration/runtime_parameters.yaml"
                        document = v4.load(path)
                        params = document["uav_tracking_px4_adapter"]["ros__parameters"]
                        params["odometry_timestamp_mode" if defect=="source_mode" else "odometry_source_max_future_s"] = "receipt" if defect=="source_mode" else .2
                        write(path, document)
                    return result

                result = run(frozen, corrupt)
                self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR":1})
                self.assertEqual(len(fake.calls), 1)

    def test_retrospective_magnetic_audit_uses_only_frozen_saved_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); frozen = plan(root, seeds=[0]); run(frozen)
            trial = frozen["trials"][0]
            # The historical audit must not execute a live PX4 verifier or
            # import a later-mutated helper, nor read the original world.
            (root/"scripts/prepare_px4_magnetic_compatibility.py").write_text("raise RuntimeError('future source')", encoding="utf-8")
            (root/trial["world_source"]).unlink()
            (root/v4.MAGNETIC_RUNTIME_PATH).unlink()
            with patch.object(v4, "verify_external_runtime", side_effect=AssertionError("unexpected live verifier")):
                report = v4.magnetic_environment_evidence(frozen, trial)
            self.assertEqual(report["errors"], [], report)
            self.assertEqual(report["binary_sha256"], frozen["magnetic_runtime_binding"]["manifest"]["binary_sha256"])

    def test_source_clock_failure_and_incomplete_are_not_engineering_pass(self):
        for verdict, expected in (("FAIL", "FAIL"), ("INCOMPLETE", "INCOMPLETE_EVIDENCE")):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0])
                state = run(frozen, FakeCommands(clock=verdict))
                self.assertEqual(state["status_counts"], {expected:1})
                row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
                self.assertEqual(row["evaluations"][0]["kind"], "source_clock")
                self.assertEqual(row["evaluations"][0]["result"], expected)

    def test_native_startup_failure_incomplete_and_misclaimed_checks_cannot_pass(self):
        for verdict, expected in (("FAIL", "FAIL"), ("INCOMPLETE_EVIDENCE", "INCOMPLETE_EVIDENCE")):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0])
                self.assertEqual(run(frozen, FakeCommands(native=verdict))["status_counts"], {expected:1})
        for defect in ("missing_check", "false_check", "script_hash", "helper_hash", "claimed_pass"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0]); fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    execution = fake(command, log, current_root, timeout)
                    if Path(command[2]).name != "evaluate_native_startup.py":return execution
                    path = Path(command[command.index("--output")+1]); report = v4.load(path)
                    if defect == "missing_check":report["checks"].pop(v4.NATIVE_STARTUP_CHECKS[0])
                    elif defect == "false_check":report["checks"][v4.NATIVE_STARTUP_CHECKS[0]] = False
                    elif defect == "script_hash":report["evaluation_source"]["script_sha256"] = "later source"
                    elif defect == "helper_hash":report["evaluation_source"]["dependencies"] = {}
                    else:report["native_startup_pass"] = False
                    write(path, report)
                    return execution

                self.assertEqual(run(frozen, corrupt)["status_counts"], {"INFRASTRUCTURE_ERROR":1})

    def test_clock_evaluator_hash_helpers_and_boolean_verdict_are_qualified(self):
        for defect in ("script_hash", "helper_hash", "claimed_pass"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True); frozen = plan(root, seeds=[0]); fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    result = fake(command, log, current_root, timeout)
                    if Path(command[2]).name == "evaluate_px4_source_clock.py":
                        path = Path(command[command.index("--output")+1]); report = v4.load(path)
                        if defect == "script_hash":
                            report["evaluation_source"]["script_sha256"] = "later evaluator"
                        elif defect == "helper_hash":
                            report["evaluation_source"]["dependencies"] = {}
                        else:
                            report["source_clock_pass"] = False
                        write(path, report)
                    return result

                result = run(frozen, corrupt)
                self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR":1})
                row = v4.read_slots(frozen)[frozen["trials"][0]["id"]]
                self.assertEqual(row["evaluations"][0]["result"], "INVALID")

    def test_loaded_magnetic_elf_cannot_self_approve_a_different_environment(self):
        for defect in ("elf_hash", "elf_path", "registration_hash", "environment_id", "outside_owned_process", "duplicate_kind"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root); frozen = plan(root, seeds=[0]); fake = FakeCommands()

                def corrupt(command, log, current_root, timeout):
                    result = fake(command, log, current_root, timeout)
                    if Path(command[2]).name == "run_stage1_trial.py":
                        path = Path(frozen["trials"][0]["directory"])/"configuration/gazebo_loaded_magnetic_libraries.json"
                        report = v4.load(path)
                        if defect == "elf_hash":
                            report["actual_loaded_libraries"][0]["sha256"] = "a"*64
                        elif defect == "elf_path":
                            report["actual_loaded_libraries"][0]["mapped_path"] = "/other/environment/library.so"
                        elif defect == "registration_hash":
                            report["registration_sha256"] = "0"*64
                        elif defect == "environment_id":
                            report["environment_id"] = "different_distribution"
                        elif defect == "outside_owned_process":
                            report["observed_processes"][0]["session"] = 123
                        else:
                            report["actual_loaded_libraries"].append(deepcopy(report["actual_loaded_libraries"][0]))
                        write(path, report)
                    return result

                result = run(frozen, corrupt)
                self.assertEqual(result["status_counts"], {"INFRASTRUCTURE_ERROR":1})
                self.assertEqual(len(fake.calls), 1)

    def test_humble_uses_its_own_explicit_frozen_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True, ros_distro="humble")
            protocol = v4.load(root/v4.PROTOCOL_PATH)
            registration = v4.load(root/protocol["magnetic_library_registration"])
            protocol["magnetic_library_registration"] = "config/gazebo_magnetic_runtime_humble22.json"
            registration.update(environment_id="fixture_humble_not_real_flight",
                                environment={"os_id":"ubuntu", "os_version":"22.04", "ros_distro":"humble"})
            for item in registration["libraries"].values():
                item["path"] = item["path"].replace("/fixture/", "/fixture_humble/")
                item["sha256"] = "e"*64
            write(root/protocol["magnetic_library_registration"], registration)
            write(root/v4.PROTOCOL_PATH, protocol)
            frozen = plan(root, seeds=[0])
            self.assertEqual(frozen["magnetic_library_binding"]["registration"]["environment"]["ros_distro"], "humble")
            self.assertEqual(run(frozen)["status_counts"], {"PASS":1})

    def test_fixture_environment_is_explicit_even_when_workspace_protocol_is_humble(self):
        source_protocol = v4.load(ROOT/v4.PROTOCOL_PATH)
        source_protocol["magnetic_library_registration"] = "config/gazebo_magnetic_runtime_humble22.json"
        original_load = v4.load
        def load_with_humble_workspace(path):
            if Path(path) == ROOT/v4.PROTOCOL_PATH:
                return deepcopy(source_protocol)
            return original_load(path)
        for ros, version in (("jazzy", "24.04"), ("humble", "22.04")):
            with self.subTest(ros_distro=ros), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with patch.object(v4, "load", side_effect=load_with_humble_workspace):
                    protocol = fixture(root, gates=True, ros_distro=ros)
                registration = v4.load(root/protocol["magnetic_library_registration"])
                self.assertEqual(registration["environment"],
                                 {"os_id":"ubuntu", "os_version":version, "ros_distro":ros})
                frozen = plan(root, seeds=[0])
                self.assertEqual(run(frozen)["status_counts"], {"PASS":1})

    def test_library_registration_cannot_mislabel_the_ros_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            path = root/"config/gazebo_magnetic_runtime.json"
            registration = v4.load(path)
            registration["environment"].update(os_version="22.04", ros_distro="humble")
            write(path, registration)
            with self.assertRaisesRegex(ValueError, "different named ROS/Ubuntu environment"):
                plan(root, seeds=[0])

    def test_an_audited_full_source_variant_is_allowed_but_an_unpinned_commit_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            protocol = v4.load(root/v4.PROTOCOL_PATH)
            registration = v4.load(root/protocol["magnetic_library_registration"])
            lookup_path = root/"config/gazebo_magnetic_reference.json"
            lookup = v4.load(lookup_path)
            original = registration["source_registration"]
            # An explicit mock variant demonstrates allowlist semantics; it
            # does not assert that this package/commit was installed anywhere.
            variant = {**original, "gazebo_sensors_version":"8.3.0", "gazebo_sensors_commit":"f"*40}
            lookup["audited_source_variants"] = [original, variant]
            write(lookup_path, lookup)
            registration["source_registration"] = variant
            write(root/protocol["magnetic_library_registration"], registration)
            accepted = plan(root, seeds=[0], persist=False)
            self.assertEqual(accepted["magnetic_library_binding"]["registration"]["source_registration"], variant)
            registration["source_registration"]["gazebo_sensors_commit"] = "a"*40
            write(root/protocol["magnetic_library_registration"], registration)
            with self.assertRaisesRegex(ValueError, "does not match frozen source versions"):
                plan(root, seeds=[0], persist=False)

    def test_position_mode_preserves_real_launch_override_of_yaml_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True)
            frozen = plan(root, groups=["stage1_position"], seeds=[0])
            fake = FakeCommands()

            def yaml_default(command, log, current_root, timeout):
                result = fake(command, log, current_root, timeout)
                if Path(command[2]).name == "run_stage1_trial.py":
                    path = Path(frozen["trials"][0]["directory"]) / "configuration/runtime_parameters.yaml"
                    parameters = v4.load(path)
                    parameters["uav_tracking_controller"]["ros__parameters"]["command_mode"] = "velocity"
                    write(path, parameters)
                return result

            self.assertEqual(run(frozen, yaml_default)["status_counts"], {"PASS": 1})

    def test_omitted_sdf_heading_defaults_to_zero_but_nonzero_heading_is_rejected(self):
        for heading, expected in [(None, "PASS"), (5., "INFRASTRUCTURE_ERROR")]:
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root, gates=True)
                source = root / "ros2_ws/src/uav_tracking_bringup/worlds/stage1_flight_person.sdf"
                tree = ET.parse(source)
                spherical = tree.find("world/spherical_coordinates")
                if heading is None:
                    spherical.remove(spherical.find("heading_deg"))
                else:
                    spherical.find("heading_deg").text = str(heading)
                tree.write(source)
                frozen = plan(root, seeds=[0])
                self.assertEqual(run(frozen)["status_counts"], {expected: 1})

    def test_evaluator_zero_and_report_agreement_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root, gates=True); frozen = plan(root)
            fake = FakeCommands()

            def contradictory(command, log, current_root, timeout):
                result = fake(command, log, current_root, timeout)
                if Path(command[2]).name == "evaluate_stage1_flight.py":
                    result["returncode"] = 2  # PASS output with abnormal exit is not successful evidence.
                return result

            self.assertEqual(run(frozen, contradictory)["status_counts"], {"INFRASTRUCTURE_ERROR": 1, "PENDING": 1})

    def test_outer_timeout_first_signals_trial_to_run_its_own_finally_cleanup(self):
        class FakeProcess:
            returncode = None

            def __init__(self):
                self.waits = 0
                self.signals = []

            def wait(self, timeout):
                self.waits += 1
                if self.waits == 1:
                    raise v4.subprocess.TimeoutExpired("fixture", timeout)
                self.returncode = -2
                return self.returncode

            def poll(self):
                return self.returncode

            def send_signal(self, sent):
                self.signals.append(sent)

        with tempfile.TemporaryDirectory() as tmp:
            process = FakeProcess()
            with patch.object(v4.subprocess, "Popen", return_value=process):
                result = v4.execute_command(["fixture"], Path(tmp) / "outer.log", Path(tmp), 1)
            self.assertEqual(process.signals, [v4.signal.SIGINT])
            self.assertEqual(result["error"], "TimeoutExpired")
            self.assertEqual(result["returncode"], -2)


if __name__ == "__main__":
    unittest.main()
