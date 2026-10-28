"""Pure acceptance contract for the paused SITL recording graph.

Endpoint discovery alone is insufficient: a real callback on the adapter also
reports discovery on its own node and output publisher matched counts. This is startup evidence, not a
replacement for independent full-recording source-clock evaluation.
"""
from __future__ import annotations

import hashlib
import json
import math


ADAPTER_NODE = "/uav_tracking_px4_adapter"
RECORDER_NODE = "/rosbag2_recorder"
READINESS_SERVICE = ADAPTER_NODE + "/startup_readiness"
RAW_TOPIC = "/fmu/out/vehicle_odometry"
ODOM_TOPIC = "/vehicle/odometry"
TIMING_TOPIC = "/vehicle/odometry_timing"
REQUIRED_TOPICS = {
    "/clock": "rosgraph_msgs/msg/Clock",
    "/camera/color/image_raw": "sensor_msgs/msg/Image",
    "/camera/aligned_depth_to_color/image_raw": "sensor_msgs/msg/Image",
    "/camera/color/camera_info": "sensor_msgs/msg/CameraInfo",
    "/ground_truth/poses": "tf2_msgs/msg/TFMessage",
    "/ground_truth/vehicle_poses": "tf2_msgs/msg/TFMessage",
    RAW_TOPIC: "px4_msgs/msg/VehicleOdometry",
    ODOM_TOPIC: "nav_msgs/msg/Odometry",
    TIMING_TOPIC: "std_msgs/msg/String",
}


def assess_graph(snapshot: dict, *, require_recorder: bool) -> dict:
    """Require typed endpoints, QoS, a live adapter and output DDS matches."""
    failures = []
    identities = []

    def select(items, *, role, topic, node=None):
        selected = [item for item in items if node is None or item.get("node") == node]
        if len(selected) != 1:
            failures.append(f"{topic}: expected one {role}, found {len(selected)}")
            return None
        item = selected[0]
        if item.get("type") != REQUIRED_TOPICS[topic]:
            failures.append(f"{topic}: {role} type mismatch")
        gid = item.get("gid", "")
        try:
            valid_gid = len(bytes.fromhex(gid)) >= 16 and any(bytes.fromhex(gid))
        except (TypeError, ValueError):
            valid_gid = False
        if not valid_gid:
            failures.append(f"{topic}: {role} lacks a valid endpoint GID")
        identities.append((topic, role, item.get("node"), gid))
        return item

    topics = snapshot.get("topics", {})
    for topic in REQUIRED_TOPICS:
        entry = topics.get(topic, {})
        publishers = entry.get("publishers", [])
        expected_node = ADAPTER_NODE if topic in {ODOM_TOPIC, TIMING_TOPIC} else None
        publisher = select(publishers, role="publisher", topic=topic, node=expected_node)
        if expected_node and len(publishers) != 1:
            failures.append(f"{topic}: unexpected additional publisher")
        subscriptions = entry.get("subscriptions", [])
        required_nodes = []
        if topic in {RAW_TOPIC, "/clock"}:
            required_nodes.append(ADAPTER_NODE)
        if require_recorder:
            required_nodes.append(RECORDER_NODE)
        for name in required_nodes:
            subscription = select(subscriptions, role=f"subscriber {name}", topic=topic, node=name)
            if publisher and subscription and publisher.get("gid") not in subscription.get("compatible_publisher_gids", []):
                failures.append(f"{topic}: {name} has no verified compatible publisher")

    service = snapshot.get("adapter_service", {})
    if service.get("schema_version") != 1 or service.get("node") != ADAPTER_NODE:
        failures.append("adapter readiness callback absent or wrong identity/schema")
    if service.get("raw_topic") != RAW_TOPIC or service.get("odom_topic") != ODOM_TOPIC or service.get("timing_topic") != TIMING_TOPIC:
        failures.append("adapter callback topic contract mismatch")
    if service.get("raw_count_scope") != "NODE_GRAPH_DISCOVERY_NOT_RMW_MATCH":
        failures.append("adapter raw discovery count scope missing or misrepresented")
    for key, minimum in (("raw_discovered_publishers", 1), ("odom_matched_subscriptions", int(require_recorder)),
                         ("timing_matched_subscriptions", int(require_recorder))):
        count = service.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < minimum:
            failures.append(f"adapter callback {key} below {minimum}")
    # Require enough actual matches for every compatible subscriber currently
    # visible on each adapter publisher, including the recorder. A controller
    # subscription alone must not satisfy the publisher-side count.
    for topic, key in ((ODOM_TOPIC, "odom_matched_subscriptions"),
                       (TIMING_TOPIC, "timing_matched_subscriptions")):
        entry = topics.get(topic, {})
        own_gids = {p.get("gid") for p in entry.get("publishers", []) if p.get("node") == ADAPTER_NODE}
        compatible_subscribers = sum(bool(own_gids.intersection(s.get("compatible_publisher_gids", [])))
            for s in entry.get("subscriptions", []))
        count = service.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count < compatible_subscribers:
            failures.append(f"adapter callback {key} below discovered compatible subscriber count {compatible_subscribers}")
    return {"ready": not failures, "failures": failures,
            "endpoint_signature": hashlib.sha256(json.dumps(sorted(identities)).encode()).hexdigest()}


class StableGraphGate:
    """Require unchanged accepted endpoints through discovery and a final guard."""
    def __init__(self, *, stable_wall_s: float = 1.0, guard_wall_s: float = .5):
        if not all(math.isfinite(v) and v > 0 for v in (stable_wall_s, guard_wall_s)):
            raise ValueError("startup stable and guard wall budgets must be positive")
        self.stable_wall_s = stable_wall_s
        self.guard_wall_s = guard_wall_s
        self._signature = None
        self._since = None
        self._last_wall = None

    def observe(self, wall_s: float, assessment: dict) -> dict:
        if not math.isfinite(wall_s) or (self._last_wall is not None and wall_s < self._last_wall):
            raise ValueError("startup observation wall clock must be finite and monotonic")
        self._last_wall = wall_s
        if not assessment["ready"]:
            self._signature = self._since = None
        elif assessment["endpoint_signature"] != self._signature:
            self._signature = assessment["endpoint_signature"]
            self._since = wall_s
        elapsed = 0. if self._since is None else wall_s - self._since
        return {"accepted": self._since is not None and elapsed >= self.stable_wall_s + self.guard_wall_s,
                "continuous_ready_wall_s": elapsed,
                "phase": "guard" if elapsed >= self.stable_wall_s else "discovery_stability"}
