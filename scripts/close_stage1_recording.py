"""Pause the owned world and observe drained source streams before bag close."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from uav_tracking.recording_closure import StreamDrainState


def pause_and_drain(output: Path, *, world: str, env: dict, expected_truth_frames=None, check_alive=None,
                    timeout_wall_s: float = 10.) -> dict:
    """Keep all producers/recorder live until actual pause and stream drain.

    Raw matching is observational. It does not certify that every recording
    row exists: the unchanged full-recording source audit remains mandatory.
    """
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import VehicleOdometry
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage

    if output.exists():
        raise FileExistsError(output)
    beginning=time.monotonic()
    report={"schema_version":1,"status":"FAIL",
        "scope":"WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE",
        "created_utc":datetime.now(timezone.utc).isoformat(),"world":world,
        "timeout_wall_s":timeout_wall_s,"quiet_wall_s":.5,"observations":[],
        "expected_truth_frames":expected_truth_frames or {},
        "truth_scope":"Offline logging headers only; no pose, identity or association is returned to online tracking/control",
        "policy":"Recorder and producers remain alive during closure; complete recorded Clock tail and all rows remain in independent evaluation"}
    context=rclpy.context.Context()
    node=executor=None
    state=StreamDrainState(quiet_wall_s=.5,expected_truth_frames=expected_truth_frames)
    try:
        rclpy.init(context=context)
        node=rclpy.create_node("uav_trial_recording_closure",context=context)
        executor=SingleThreadedExecutor(context=context)
        executor.add_node(node)

        def clock(message):
            state.clock(message.clock.sec*1_000_000_000+message.clock.nanosec,time.monotonic())

        def raw(message):
            state.raw(int(message.timestamp_sample),int(message.timestamp),time.monotonic())

        def timing(message):
            try:
                diagnostic=json.loads(message.data)
                if not isinstance(diagnostic,dict):raise ValueError("diagnostic must be an object")
                state.timing(diagnostic,time.monotonic())
            except (ValueError,TypeError) as error:
                state.errors.append(f"diagnostic_decode: {error}")

        def adapted(message):
            state.adapted(message.header.stamp.sec*1_000_000_000+message.header.stamp.nanosec,time.monotonic())

        node.create_subscription(Clock,"/clock",clock,20)
        node.create_subscription(VehicleOdometry,"/fmu/out/vehicle_odometry",raw,qos_profile_sensor_data)
        node.create_subscription(String,"/vehicle/odometry_timing",timing,100)
        node.create_subscription(Odometry,"/vehicle/odometry",adapted,100)
        def truth(kind,message):
            state.truth(kind,[(transform.child_frame_id,
                transform.header.stamp.sec*1_000_000_000+transform.header.stamp.nanosec)
                for transform in message.transforms],time.monotonic())
        if expected_truth_frames:
            node.create_subscription(TFMessage,"/ground_truth/poses",lambda message:truth('target',message),100)
            node.create_subscription(TFMessage,"/ground_truth/vehicle_poses",lambda message:truth('vehicle',message),100)
        # A new volatile subscriber can discover different publishers at
        # different times. Pausing before every required callback has arrived
        # can permanently hide GT/timing even while the recorder has them.
        # Discovery and post-pause drain share the original total wall budget.
        warm_deadline=beginning+timeout_wall_s
        readiness=state.ready_to_pause(time.monotonic())
        while not readiness['ready'] and time.monotonic()<warm_deadline:
            if check_alive:check_alive()
            executor.spin_once(timeout_sec=min(.05,max(0.,warm_deadline-time.monotonic())))
            readiness=state.ready_to_pause(time.monotonic())
        report["before_pause"]={"clock_observed":state.clock_ns is not None,
            "raw_observed":state.last_raw is not None,"counts":dict(state.counts),
            "elapsed_wall_s":time.monotonic()-beginning,"readiness":readiness}
        if not readiness['ready']:
            raise RuntimeError("Required source callbacks not ready within recording closure wall budget; world was not paused")
        if check_alive:check_alive()
        remaining=beginning+timeout_wall_s-time.monotonic()
        if remaining<=0:raise RuntimeError("Recording closure wall budget expired before pause request")
        paused=subprocess.run(["gz","service","-s",f"/world/{world}/control",
            "--reqtype","gz.msgs.WorldControl","--reptype","gz.msgs.Boolean",
            "--timeout",str(min(5000,max(1,int(remaining*1000)))),"--req","pause: true"],env=env,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=min(5.5,remaining))
        report["pause_request"]={"command_pause":True,"returncode":paused.returncode,"response":paused.stdout}
        if paused.returncode!=0 or "true" not in paused.stdout:
            raise RuntimeError("Gazebo did not acknowledge recording-closure pause")
        state.pause_ack(time.monotonic())
        report["pause_ack_elapsed_wall_s"]=time.monotonic()-beginning
        while time.monotonic()-beginning<timeout_wall_s:
            if check_alive:check_alive()
            deadline=min(beginning+timeout_wall_s,time.monotonic()+.05)
            while time.monotonic()<deadline:
                executor.spin_once(timeout_sec=min(.01,max(0.,deadline-time.monotonic())))
            assessment=state.assess(time.monotonic())
            report["observations"].append({"elapsed_wall_s":time.monotonic()-beginning,**assessment})
            if assessment["ready"]:
                report.update(status="PASS",closed_streams_elapsed_wall_s=time.monotonic()-beginning)
                return report
        raise RuntimeError("Recording source streams did not become quiet and fully drain within wall budget")
    except Exception as error:
        report["error"]=f"{type(error).__name__}: {error}"
        raise
    finally:
        if executor is not None:executor.shutdown()
        if node is not None:node.destroy_node()
        if context.ok():rclpy.shutdown(context=context)
        report["finished_utc"]=datetime.now(timezone.utc).isoformat()
        report["elapsed_wall_s"]=time.monotonic()-beginning
        report["observer_cleanup_completed"]=True
        with output.open("x",encoding="utf-8") as stream:
            json.dump(report,stream,indent=2)
            stream.write("\n")
