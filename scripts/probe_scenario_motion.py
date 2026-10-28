#!/usr/bin/env python3
"""Independent Gazebo-only target-motion probe; truth is used for testing only."""

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def json_messages(text):
    decoder = json.JSONDecoder()
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset >= len(text):
            return
        message, offset = decoder.raw_decode(text, offset)
        yield message


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--class-name", choices=("person", "car"), default="person")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    models = project / "ros2_ws/src/uav_tracking_bringup/models"
    model_name = "target_" + args.class_name
    env = dict(os.environ)
    env["GZ_PARTITION"] = f"stage1_motion_probe_{os.getpid()}"
    env["GZ_IP"] = "127.0.0.1"
    env["GZ_SIM_RESOURCE_PATH"] = str(models) + ":" + env.get("GZ_SIM_RESOURCE_PATH", "")
    world = f'''<?xml version="1.0"?><sdf version="1.10"><world name="motion_probe">
      <physics type="ode"><max_step_size>0.004</max_step_size><real_time_factor>1</real_time_factor></physics>
      <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
      <model name="ground"><static>true</static><link name="link"><collision name="collision"><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry></collision></link></model>
      <include><uri>model://{model_name}</uri><pose>5 0 0 0 0 0</pose></include>
      </world></sdf>'''
    with tempfile.TemporaryDirectory(prefix="stage1_motion_probe_") as temporary:
        path = Path(temporary) / "probe.sdf"
        path.write_text(world)
        with (Path(temporary) / "gazebo.log").open("w") as logfile:
            gazebo = subprocess.Popen(["gz", "sim", "-r", "-s", str(path)], env=env, stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                time.sleep(2.0)
                subprocess.run(["gz", "topic", "-t", "/scenario/target/cmd_vel", "-m", "gz.msgs.Twist", "-p", "linear: {x: 0.5} angular: {z: 0.07}"], env=env, check=True, timeout=10)
                recording = subprocess.run(["gz", "topic", "-e", "-t", "/ground_truth/poses", "--json-output", "-d", "4"], env=env, text=True, capture_output=True, check=True, timeout=12)
                positions = []
                for message in json_messages(recording.stdout):
                    for pose in message.get("pose", []):
                        if pose.get("name") == model_name:
                            p = pose.get("position", {})
                            positions.append(tuple(p.get(axis, 0.0) for axis in ("x", "y", "z")))
                if len(positions) < 10:
                    raise RuntimeError("missing model poses: " + recording.stdout[:1500])
                displacement = math.dist(positions[0][:2], positions[-1][:2])
                vertical_span = max(p[2] for p in positions) - min(p[2] for p in positions)
                result = {"class": args.class_name, "samples": len(positions), "first": positions[0], "last": positions[-1], "horizontal_displacement_m": displacement, "vertical_span_m": vertical_span, "passed": displacement > 1.5 and vertical_span < 0.15}
                print(json.dumps(result, indent=2))
                if not result["passed"]:
                    raise SystemExit(1)
            finally:
                os.killpg(gazebo.pid, signal.SIGINT)
                try:
                    gazebo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(gazebo.pid, signal.SIGTERM)
                    gazebo.wait(timeout=5)


if __name__ == "__main__":
    main()
