"""Wait on real paused ROS endpoints and an actual PX4 adapter callback."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

from uav_tracking.startup_readiness import (
    READINESS_SERVICE, REQUIRED_TOPICS, StableGraphGate, assess_graph,
)


def wait_ready(output: Path, *, require_recorder: bool, check_alive=None,
               timeout_wall_s: float = 45.) -> dict:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSCompatibility, qos_check_compatible
    from std_srvs.srv import Trigger

    if output.exists():
        raise FileExistsError(output)
    beginning = time.monotonic()
    report = {"schema_version": 1, "status": "FAIL", "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "PAUSED_GRAPH_AND_ADAPTER_DDS_MATCHES_BEFORE_UNPAUSE",
        "require_recorder": require_recorder, "required_topics": REQUIRED_TOPICS,
        "timeout_wall_s": timeout_wall_s, "stable_wall_s": 1., "guard_wall_s": .5,
        "policy": "No source samples waived; independent complete-recording evaluation remains required",
        "observations": []}
    context = rclpy.context.Context()
    node = None
    executor = None
    try:
        rclpy.init(context=context)
        node = rclpy.create_node("uav_trial_startup_probe", context=context)
        # rclpy.spin_once without an executor uses the uninitialized global
        # context. This collector owns a distinct Context and executor pair.
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        client = node.create_client(Trigger, READINESS_SERVICE)
        gate = StableGraphGate()
        while time.monotonic() - beginning < timeout_wall_s:
            if check_alive:
                check_alive()
            snapshot = {"elapsed_wall_s": time.monotonic()-beginning, "topics": {}, "adapter_service": {}}
            if client.service_is_ready():
                future = client.call_async(Trigger.Request())
                service_deadline = min(beginning+timeout_wall_s, time.monotonic()+.75)
                while not future.done() and time.monotonic() < service_deadline:
                    executor.spin_once(timeout_sec=.05)
                if future.done():
                    response = future.result()
                    if response and response.success:
                        snapshot["adapter_service"] = json.loads(response.message)
                    else:
                        snapshot["service_error"] = "readiness callback returned unsuccessful response"
                else:
                    future.cancel()
                    snapshot["service_error"] = "readiness callback wall timeout"
            else:
                snapshot["service_error"] = "readiness service not discovered"

            def encode(info):
                namespace = info.node_namespace.rstrip("/")
                return {"node": namespace+"/"+info.node_name, "type": info.topic_type,
                    "gid": bytes(info.endpoint_gid).hex(), "qos": str(info.qos_profile)}

            for topic in REQUIRED_TOPICS:
                publishers = node.get_publishers_info_by_topic(topic)
                subscriptions = node.get_subscriptions_info_by_topic(topic)
                encoded_subscriptions = []
                for subscription in subscriptions:
                    encoded = encode(subscription)
                    encoded["compatible_publisher_gids"] = []
                    encoded["qos_checks"] = []
                    for publisher in publishers:
                        result, reason = qos_check_compatible(publisher.qos_profile, subscription.qos_profile)
                        encoded["qos_checks"].append({"publisher_gid": bytes(publisher.endpoint_gid).hex(),
                            "compatibility": result.name, "reason": reason})
                        if result == QoSCompatibility.OK and publisher.topic_type == subscription.topic_type:
                            encoded["compatible_publisher_gids"].append(bytes(publisher.endpoint_gid).hex())
                    encoded_subscriptions.append(encoded)
                snapshot["topics"][topic] = {"publishers": [encode(p) for p in publishers],
                    "subscriptions": encoded_subscriptions}
            assessment = assess_graph(snapshot, require_recorder=require_recorder)
            stability = gate.observe(time.monotonic()-beginning, assessment)
            snapshot.update(assessment=assessment, stability=stability)
            report["observations"].append(snapshot)
            if stability["accepted"]:
                report.update(status="PASS", ready_elapsed_wall_s=time.monotonic()-beginning)
                break
            # This spins DDS discovery and the service response on wall time;
            # no simulation-time timer or unpause is needed to establish readiness.
            deadline = min(beginning+timeout_wall_s, time.monotonic()+.2)
            while time.monotonic() < deadline:
                executor.spin_once(timeout_sec=min(.05, max(0., deadline-time.monotonic())))
        else:
            report["error"] = "Paused graph readiness wall timeout"
        if report["status"] != "PASS":
            raise RuntimeError("Paused graph endpoints/DDS matches not ready; see graph_startup_readiness.json")
        return report
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["elapsed_wall_s"] = time.monotonic()-beginning
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if context.ok():
            rclpy.shutdown(context=context)
