"""Verify registered seeds reach the real shell argv without launching Gazebo."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("seed_trial_runner",ROOT/"scripts/run_stage1_trial.py")
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SeedRunnerTests(unittest.TestCase):
    def test_car_surface_recovery_is_explicitly_archived_and_reaches_launched_graph(self):
        self.run_registered_seed(0, 1, target_class="car", recovery=True)

    def test_copied_yaml_cannot_enable_recovery_without_the_cli_opt_in(self):
        self.run_registered_seed(0, 1, target_class="car", configured_recovery=True)

    def test_full_runner_records_seed_and_passes_it_to_the_gazebo_process_environment(self):
        self.run_registered_seed(73,74)
        self.run_registered_seed(0,1)

    def test_recording_closure_precedes_recorder_stop_and_archive(self):
        self.run_registered_seed(0,1,with_bag=True)

    def test_closure_failure_still_closes_and_archives_failed_trial(self):
        self.run_registered_seed(0,1,with_bag=True,closure_fails=True)

    def test_observer_cleanup_reporting_fault_still_preserves_and_archives_failed_trial(self):
        self.run_registered_seed(0,1,with_bag=True,observer_close_fails=True)

    def run_registered_seed(self,registered,actual,*,with_bag=False,closure_fails=False,observer_close_fails=False,
                            target_class="person",recovery=False,configured_recovery=None):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            bringup=root/"ros2_ws/src/uav_tracking_bringup"
            for relative in (f"config/stage1_tracking_{target_class}.yaml","config/stage1_flight_bridge.yaml",
                             f"worlds/stage1_flight_{target_class}.sdf",f"models/target_{target_class}/model.sdf",
                             "models/x500_stage1/model.sdf"):
                destination=bringup/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/"ros2_ws/src/uav_tracking_bringup"/relative,destination)
            if configured_recovery is not None:
                config_path=bringup/f"config/stage1_tracking_{target_class}.yaml"
                configured=yaml.safe_load(config_path.read_text(encoding="utf-8"))
                configured["uav_tracking_detection"]["ros__parameters"]["car_surface_recovery_enabled"]=configured_recovery
                configured["uav_tracking_state_estimator"]["ros__parameters"]["supported_birth_confirmation_required"]=configured_recovery
                config_path.write_text(yaml.safe_dump(configured),encoding="utf-8")
            # Only the existence/hash is needed: every process is mocked.
            model=root/"models/yolo11n.pt"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"test model, never loaded")
            px4=root/"px4_fixture"
            persisted=px4/"build/px4_sitl_default/rootfs/parameters.bson"
            persisted.parent.mkdir(parents=True)
            persisted.write_bytes(b"before flight persisted parameters")
            environments={}
            lifecycle=[]
            class Process:
                def __init__(self,command,**kwargs):
                    self.name=Path(kwargs["stdout"].name).stem
                    self.pid=731
                    self.returncode=None
                    self.monitor_polls=0
                    environments[self.name]=dict(kwargs["env"])
                def poll(self):
                    if self.name=="monitor":
                        self.monitor_polls+=1
                        if self.monitor_polls>1:self.returncode=0
                    return self.returncode
                def send_signal(self,signum):pass
                def wait(self,**kwargs):
                    lifecycle.append("stop_"+self.name)
                    if self.name=="px4":persisted.write_bytes(b"after normal firmware save")
                    self.returncode=0
                    return 0
            def probe(command,**kwargs):
                if command[:3]==["gz","service","-l"]:output="/world/stage1_flight/control\n"
                elif command[:3]==["ros2","topic","list"]:
                    output="/clock\n/camera/color/image_raw\n/camera/aligned_depth_to_color/image_raw\n"
                else:
                    if "pause: false" in command:lifecycle.append("unpause")
                    output="data: true\n"
                return SimpleNamespace(returncode=0,stdout=output)
            # This seed/argv fixture launches no process. The production
            # capture must remain strict; fake PID731 has no /proc mapping.
            rendering_capture = SimpleNamespace(capture_ready=Mock(return_value={
                "status":"PASS", "expected_driver":"auto", "owned_pid":731,
                "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY_NO_PROCESS_LAUNCHED"}))
            graph_wait = SimpleNamespace(wait_ready=Mock(return_value={
                "status":"PASS", "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY_NO_ROS_GRAPH"}))
            def closure(output,**kwargs):
                kwargs["check_alive"]()
                lifecycle.append("pause_and_drain")
                output.write_text(json.dumps({"status":"FAIL" if closure_fails else "PASS",
                    "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY_NO_PROCESS_LAUNCHED"}))
                if closure_fails:raise RuntimeError("injected drain failure")
            class ClosureObserver:
                def __init__(self, **kwargs):
                    self.expected_truth_frames=kwargs['expected_truth_frames']
                    lifecycle.append("observer_construct")
                def start(self):lifecycle.append("observer_start")
                def check_alive(self):pass
                def close(self):
                    lifecycle.append("observer_close")
                    if observer_close_fails:raise OSError("injected lifecycle report write failure")
                    return {"healthy_cleanup":True}
                def pause_and_drain(self, output, **kwargs):
                    kwargs['expected_truth_frames']=self.expected_truth_frames
                    return closure(output, **kwargs)
            closing=SimpleNamespace(RecordingClosureObserver=Mock(side_effect=ClosureObserver))
            def spool(_output):
                destination=root/"spool"
                destination.mkdir()
                return destination
            def archive(*args):
                lifecycle.append("archive")
                return {"status":"PASS","evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"}
            argv=["trial","--name","seed_trial","--seed",str(registered),
                  "--model-path","models/yolo11n.pt","--class",target_class]
            if recovery:argv.append("--car-surface-recovery")
            if not with_bag:argv.append("--no-bag")
            with patch.object(runner,"__file__",str(root/"scripts/run_stage1_trial.py")), \
                    patch("sys.argv",argv), \
                    patch.object(runner.subprocess,"Popen",Process),patch.object(runner.subprocess,"run",probe), \
                    patch.object(runner.time,"sleep"),patch.object(runner.os,"killpg",create=True), \
                    patch.object(runner,"create_recording_spool",side_effect=spool), \
                    patch.object(runner,"finalize_recording",side_effect=archive), \
                    patch.dict(sys.modules,{"capture_gazebo_rendering":rendering_capture,
                                            "wait_stage1_graph":graph_wait,
                                            "close_stage1_recording":closing}), \
                    patch.dict(os.environ,{"STAGE1_PX4_ROOT":str(px4)}):
                if closure_fails or observer_close_fails:
                    with self.assertRaisesRegex(RuntimeError,"without proved source-stream drain"):
                        runner.main()
                else:runner.main()
            if with_bag:
                closing.RecordingClosureObserver.assert_called_once()
                self.assertEqual(closing.RecordingClosureObserver.call_args.kwargs['expected_truth_frames'],
                                 {'target':[f'target_{target_class}'],'vehicle':['stage1_uav']})
                self.assertEqual(lifecycle.count("pause_and_drain"),1)
                self.assertLess(lifecycle.index("observer_start"),lifecycle.index("unpause"))
                self.assertLess(lifecycle.index("pause_and_drain"),lifecycle.index("stop_bag"))
                self.assertLess(lifecycle.index("stop_bag"),lifecycle.index("stop_ros"))
                self.assertLess(lifecycle.index("stop_gazebo"),lifecycle.index("observer_close"))
                self.assertLess(lifecycle.index("observer_close"),lifecycle.index("archive"))
                self.assertLess(lifecycle.index("stop_ros"),lifecycle.index("archive"))
            else:closing.RecordingClosureObserver.assert_not_called()
            rendering_capture.capture_ready.assert_called_once_with(731,"auto")
            graph_wait.wait_ready.assert_called_once()
            self.assertEqual(graph_wait.wait_ready.call_args.args,
                             (root.resolve()/"results/seed_trial/graph_startup_readiness.json",))
            self.assertEqual(graph_wait.wait_ready.call_args.kwargs["require_recorder"],with_bag)
            config=json.loads((root/"results/seed_trial/run_config.json").read_text())
            self.assertEqual(config["seed"],registered)
            self.assertEqual(config["gazebo_seed"],actual)
            self.assertEqual(config["gazebo_seed_mapping"],"registered_seed_plus_one_zero_is_ignored_by_gazebo_cli")
            self.assertEqual(config["car_surface_recovery"],recovery)
            self.assertEqual(config["car_surface_recovery_method"],"component_centroid_v1")
            self.assertEqual(environments["gazebo"]["STAGE_SIM_SEED"],str(actual))
            snapshot=root/"results/seed_trial/configuration"
            runtime_path=snapshot/"runtime_parameters.yaml"
            self.assertEqual(Path(environments["ros"]["STAGE_PARAMS_FILE"]),runtime_path.resolve())
            runtime=yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
            detector=runtime["uav_tracking_detection"]["ros__parameters"]
            self.assertEqual(detector["car_surface_recovery_enabled"],recovery)
            self.assertIs(runtime["uav_tracking_state_estimator"]["ros__parameters"]["supported_birth_confirmation_required"],recovery)
            expected_recovery={"car_surface_recovery_method":"component_centroid_v1",
                "surface_geometry_frame":"map","surface_tf_timeout_s":.02,
                "surface_max_image_pixels":307200,"surface_max_roi_pixels":307200,"surface_max_visible_boxes":64}
            self.assertEqual({key:detector[key] for key in expected_recovery},expected_recovery)
            rendering=json.loads((snapshot/"gazebo_rendering_libraries.json").read_text())
            self.assertEqual(rendering["evidence_scope"],"ORCHESTRATION_FIXTURE_ONLY_NO_PROCESS_LAUNCHED")
            manifest=json.loads((snapshot/"px4_parameters.json").read_text())
            for phase,data in (("before",b"before flight persisted parameters"),("after",b"after normal firmware save")):
                self.assertEqual((snapshot/manifest[phase]["artifact"]).read_bytes(),data)
                self.assertEqual(manifest[phase]["sha256"],hashlib.sha256(data).hexdigest())
            self.assertEqual(persisted.read_bytes(),b"after normal firmware save")


@unittest.skipUnless(os.name=="posix" and shutil.which("bash"),"POSIX shell integration; run this test in WSL")
class SeedShellTests(unittest.TestCase):
    def invoke(self,seed,backend="egl",paused="1"):
        with tempfile.TemporaryDirectory(prefix="gz_seed_test_") as temporary:
            root=Path(temporary)
            fake_gz=root/"gz"
            # exec resolves this executable from PATH. No Gazebo binary,
            # ROS graph, world, sensor, or physics process is ever started.
            fake_gz.write_text("#!"+sys.executable+"\nimport json,os,sys\nprint(json.dumps({'argv':sys.argv[1:],'seed_env':os.environ.get('STAGE_SIM_SEED')}))\n")
            fake_gz.chmod(0o755)
            env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ["PATH"],
                     STAGE_SIM_SEED=seed,STAGE1_RENDER_BACKEND=backend,STAGE_START_PAUSED=paused,
                     STAGE1_PROJECT_ROOT=str(ROOT),STAGE_WORLD_FILE="/fake world/test.sdf")
            wrapper="source() { return 0; }; ros2() { printf '%s\\n' /fake/share; }; export -f source ros2; exec bash \"$1\" gazebo car"
            return subprocess.run(["bash","-c",wrapper,"seed-test",str(ROOT/"scripts/run_stage1_flight.sh")],
                                  env=env,capture_output=True,text=True,timeout=10)

    def test_both_render_branches_pass_the_exact_registered_seed_as_one_argument(self):
        for backend in ("egl","wslg"):
            with self.subTest(backend=backend):
                result=self.invoke("73",backend)
                self.assertEqual(result.returncode,0,result.stderr)
                payload=json.loads(result.stdout.splitlines()[-1])
                self.assertEqual(payload["seed_env"],"73")
                self.assertEqual(payload["argv"][0:3],["sim","--seed","73"])
                self.assertEqual(payload["argv"][-1],"/fake world/test.sdf")
                self.assertNotIn("-r",payload["argv"])

    def test_unpaused_start_preserves_seed_and_adds_run_flag(self):
        result=self.invoke("4294967295",paused="0")
        self.assertEqual(result.returncode,0,result.stderr)
        argv=json.loads(result.stdout.splitlines()[-1])["argv"]
        self.assertEqual(argv[1:3],["--seed","4294967295"])
        self.assertIn("-r",argv)

    def test_invalid_seeds_fail_before_fake_simulator_can_execute(self):
        for seed in ("0","-1","4294967296","1 2","; touch /unexpected","100000000000000"):
            with self.subTest(seed=seed):
                result=self.invoke(seed)
                self.assertEqual(result.returncode,2)
                self.assertIn("unsigned 32-bit",result.stderr)
                self.assertNotIn("seed_env",result.stdout)


if __name__=="__main__":unittest.main()
