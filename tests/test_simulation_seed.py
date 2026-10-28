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
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("seed_trial_runner",ROOT/"scripts/run_stage1_trial.py")
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SeedRunnerTests(unittest.TestCase):
    def test_full_runner_records_seed_and_passes_it_to_the_gazebo_process_environment(self):
        self.run_registered_seed(73,74)
        self.run_registered_seed(0,1)

    def run_registered_seed(self,registered,actual):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            bringup=root/"ros2_ws/src/uav_tracking_bringup"
            for relative in ("config/stage1_tracking_person.yaml","config/stage1_flight_bridge.yaml",
                             "worlds/stage1_flight_person.sdf","models/target_person/model.sdf",
                             "models/x500_stage1/model.sdf"):
                destination=bringup/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/"ros2_ws/src/uav_tracking_bringup"/relative,destination)
            # Only the existence/hash is needed: every process is mocked.
            model=root/"models/yolo11n.pt"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"test model, never loaded")
            px4=root/"px4_fixture"
            persisted=px4/"build/px4_sitl_default/rootfs/parameters.bson"
            persisted.parent.mkdir(parents=True)
            persisted.write_bytes(b"before flight persisted parameters")
            environments={}
            class Process:
                def __init__(self,command,**kwargs):
                    self.name=Path(kwargs["stdout"].name).stem
                    self.pid=731
                    self.returncode=0 if self.name=="monitor" else None
                    environments[self.name]=dict(kwargs["env"])
                def poll(self):return self.returncode
                def send_signal(self,signum):pass
                def wait(self,**kwargs):
                    if self.name=="px4":persisted.write_bytes(b"after normal firmware save")
                    self.returncode=0
                    return 0
            def probe(command,**kwargs):
                if command[:3]==["gz","service","-l"]:output="/world/stage1_flight/control\n"
                elif command[:3]==["ros2","topic","list"]:
                    output="/clock\n/camera/color/image_raw\n/camera/aligned_depth_to_color/image_raw\n"
                else:output="data: true\n"
                return SimpleNamespace(returncode=0,stdout=output)
            with patch.object(runner,"__file__",str(root/"scripts/run_stage1_trial.py")), \
                    patch("sys.argv",["trial","--name","seed_trial","--seed",str(registered),"--no-bag",
                                      "--model-path","models/yolo11n.pt"]), \
                    patch.object(runner.subprocess,"Popen",Process),patch.object(runner.subprocess,"run",probe), \
                    patch.object(runner.time,"sleep"),patch.object(runner.os,"killpg",create=True), \
                    patch.dict(os.environ,{"STAGE1_PX4_ROOT":str(px4)}):
                runner.main()
            config=json.loads((root/"results/seed_trial/run_config.json").read_text())
            self.assertEqual(config["seed"],registered)
            self.assertEqual(config["gazebo_seed"],actual)
            self.assertEqual(config["gazebo_seed_mapping"],"registered_seed_plus_one_zero_is_ignored_by_gazebo_cli")
            self.assertEqual(environments["gazebo"]["STAGE_SIM_SEED"],str(actual))
            snapshot=root/"results/seed_trial/configuration"
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
