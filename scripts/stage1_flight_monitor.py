"""Record a real visual PX4 trial; never publish target observations/commands.

The optional collisionless shutter is a test stimulus in front of the vehicle
camera, positioned and refreshed using measured optical TF in every stage.
Target ground truth is not
subscribed to here. Offline evaluation may consume the recorded truth later.
With --reselect-after-loss, a separately logged, explicit selection message
uses one recent detector box to start a new task after the long-loss test.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time
import uuid

import numpy as np
try:
    import cv2
    import rclpy
    from cv_bridge import CvBridge
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import VehicleStatus, TrajectorySetpoint
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.duration import Duration
    from rclpy.time import Time
    from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from ros_gz_interfaces.srv import SetEntityPose
    from sensor_msgs.msg import Image
    from std_msgs.msg import String
    from uav_tracking_interfaces.msg import TargetObservation, TargetSelection, TargetState, TrackingCommand, TrackingStatus
    from tf2_ros import Buffer, TransformException, TransformListener
except ImportError:  # Keep the evidence checks testable without a ROS install.
    rclpy = None
    Node = object

from uav_tracking.control.gimbal_geometry import quaternion_rotation
from uav_tracking.ros_lifecycle import shutdown_requests


SETPOINT_COUNTER_KEYS = (
    "px4_setpoints", "classified_px4_setpoints", "position_only_setpoints", "velocity_only_setpoints",
    "invalid_setpoints", "simultaneous_position_velocity_setpoints", "partial_position_setpoints",
    "partial_velocity_setpoints", "malformed_partial_setpoints", "malformed_dimension_setpoints",
    "infinite_setpoint_fields", "inactive_position_velocity_setpoints", "follow_setpoints",
    "follow_position_setpoints", "follow_velocity_setpoints", "follow_invalid_setpoints",
)

# The pose-service ACK is not a rendered-image timestamp. Use the same fixed
# rendering allowance for both classes, then require independent detector
# evidence in the offline evaluator. This never changes a tracking timeout.
SHUTTER_RENDER_MARGIN_S = 0.05


def flight_monitor_outcome(summary: dict, termination_reason: str) -> dict:
    """Report process completion separately from the offline safety verdict.

    Explicit auto-unique/no-follow tests must hover and therefore cannot
    satisfy the normal visual-command and horizontal-travel requirements.
    They still need an actual armed Offboard flight and valid PX4 stream.
    """
    counts = summary.get("counts", {})
    no_follow = termination_reason == "no_follow_duration_reached"
    if no_follow:
        altitude = summary.get("max_vehicle_altitude_m")
        passed = bool(
            summary.get("armed_seen") and summary.get("offboard_seen")
            and altitude is not None and altitude >= 2.0
            and counts.get("px4_setpoints", 0) >= 100
            and counts.get("classified_px4_setpoints", 0) == counts.get("px4_setpoints")
            and counts.get("invalid_setpoints") == 0
            and counts.get("simultaneous_position_velocity_setpoints") == 0
        )
    else:
        passed = termination_reason == "follow_duration_reached" and summary.get("basic_flight_passed") is True
    return {"termination_reason": termination_reason,
            "completion_criteria": "hover_flight_stream" if no_follow else "basic_visual_follow_flight",
            "monitor_success": bool(passed), "monitor_exit_code": 0 if passed else 1,
            "offline_evaluation_required": True}


def stamp_s(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def select_visual_box(detections, rule):
    """Test/user selection by image geometry only, never simulator identity."""
    valid = [d for d in detections if d.get("depth_valid") and len(d.get("bbox", [])) == 4]
    valid.sort(key=lambda item: (item["bbox"][0] + item["bbox"][2]) / 2)
    if not valid:
        return None
    if rule == "none":
        return valid[0] if len(valid) == 1 else None
    index = {"leftmost": 0, "middle": len(valid) // 2, "rightmost": len(valid) - 1}[rule]
    return valid[index]


def shutter_pose_from_camera_transform(transform, now_s: float, distance_m: float = 0.60):
    """Test-only shutter from measured optical TF, never commanded angles.

    The shutter model's thin axis is local +X. Its local +Y/+Z span the
    image plane, so optical right/down/forward must first become FLU.
    """

    source_s = stamp_s(transform.header.stamp)
    if (not math.isfinite(now_s) or not math.isfinite(source_s) or source_s <= 0
            or source_s - now_s > 0.05 or now_s - source_s > 0.20):
        raise ValueError("stale or invalid measured optical TF")
    if transform.header.frame_id != "map" or transform.child_frame_id != "camera_link":
        raise ValueError("unexpected measured optical TF frames")
    p, q = transform.transform.translation, transform.transform.rotation
    rotation = quaternion_rotation([q.x, q.y, q.z, q.w])
    position = np.array([p.x, p.y, p.z], dtype=float) + float(distance_m) * rotation[:, 2]
    if not np.all(np.isfinite(position)) or not math.isfinite(distance_m) or distance_m <= 0:
        raise ValueError("invalid shutter geometry")
    # q(world<-optical) * q(optical<-FLU), normalized xyzw. The inverse of
    # optical->FLU [-.5,.5,-.5,.5] is [.5,-.5,.5,.5].
    source_q = np.array([q.x, q.y, q.z, q.w], dtype=float)
    x, y, z, w = source_q / np.linalg.norm(source_q)
    orientation = np.array([(w + x + y + z) / 2, (-w - x + y + z) / 2,
                            (w - x - y + z) / 2, (w - x + y - z) / 2])
    return position, orientation, source_s


class FlightMonitor(Node):
    def __init__(self, args) -> None:
        super().__init__("stage1_flight_monitor", parameter_overrides=[rclpy.parameter.Parameter("use_sim_time", value=True)])
        self.args = args
        args.output.mkdir(parents=True, exist_ok=True)
        self.log = (args.output / "telemetry.jsonl").open("w", encoding="utf-8")
        self.started_wall = time.monotonic()
        self.follow_start = None
        self.start_sim = None
        self.end_sim = None
        self.phase = "WAITING"
        self.aborted_wall = None
        self.odom = None
        self.target = None
        self.diagnostics = None
        self.status = None
        self.track_snapshot = None
        self.gimbal_diagnostics = None
        self.bridge = CvBridge()
        self.video = None
        self.last_video_s = -math.inf
        # Include explicit zeros: an absent field in a historical summary is
        # missing evidence, not proof that a check observed zero violations.
        self.counts = Counter({name: 0 for name in SETPOINT_COUNTER_KEYS})
        self.state_counts = Counter()
        self.status_counts = Counter()
        self.errors = []
        self.positions = []
        self.detection_latency = []
        self.inference_times = []
        self.depth_ratios = []
        self.shutter_future = None
        self.shutter_request_seq = 0
        self.shutter_pending = None
        self.shutter_client = self.create_client(SetEntityPose, f"/world/{args.world}/set_pose")
        self.shutter_requested = False
        self.shutter_events = []
        self.shutter_results = {}
        self.occlusion_schedule = [
            {"name": "short", "start_offset_s": 12.0, "duration_s": args.short_occlusion_s,
             "render_margin_s": SHUTTER_RENDER_MARGIN_S, "state": "waiting"},
            {"name": "long", "start_offset_s": 25.0, "duration_s": 3.0,
             "render_margin_s": SHUTTER_RENDER_MARGIN_S, "state": "waiting"},
        ]
        self.shutter_last_pose_update_s = -math.inf
        self.shutter_tf_buffer = Buffer(cache_time=Duration(seconds=5.0))
        self.shutter_tf_listener = TransformListener(self.shutter_tf_buffer, self)
        self.armed_seen = False
        self.offboard_seen = False
        self.reselection_uuid = None
        self.reselection_confirmed = False
        self.initial_selection_uuid = None
        self.initial_selection_confirmed = False
        self.selection_pub = self.create_publisher(TargetSelection, "/tracking/selection", 10)
        self.last_telemetry = -math.inf
        self.create_subscription(Odometry, "/vehicle/odometry", self.on_odom, 10)
        self.create_subscription(TargetObservation, "/tracking/observations", self.on_observation, 20)
        self.create_subscription(TargetState, "/tracking/state", self.on_state, 20)
        self.create_subscription(TargetState, "/tracking/navigation_state", self.on_navigation_state, 20)
        self.create_subscription(String, "/tracking/navigation_diagnostics", self.on_navigation_diagnostics, 20)
        self.create_subscription(TrackingStatus, "/tracking/status", self.on_status, 20)
        self.create_subscription(TrackingCommand, "/tracking/command", self.on_command, 20)
        self.create_subscription(String, "/tracking/detection_diagnostics", self.on_diagnostics, 20)
        self.create_subscription(String, "/tracking/flight_phase", self.on_phase, 20)
        self.create_subscription(String, "/gimbal/diagnostics", self.on_gimbal_diagnostics, 20)
        self.create_subscription(String, "/tracking/tracks", self.on_tracks, 20)
        self.create_subscription(VehicleStatus, "/fmu/out/vehicle_status_v1", self.on_vehicle_status, qos_profile_sensor_data)
        self.create_subscription(TrajectorySetpoint, "/fmu/in/trajectory_setpoint", self.on_setpoint, 20)
        self.create_subscription(Image, "/camera/color/image_raw", self.on_image,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE))
        self.create_timer(float(getattr(args, "monitor_tick_s", .10)), self.tick)

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def on_navigation_state(self, msg) -> None:
        self.event("navigation_state", stamp_s=float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9,
                   state=int(msg.state), track_id=int(msg.track_id), target_uuid=msg.target_uuid,
                   prediction_age_s=float(msg.prediction_age_s),
                   position_m=[msg.position_m.x, msg.position_m.y, msg.position_m.z],
                   velocity_mps=[msg.velocity_mps.x, msg.velocity_mps.y, msg.velocity_mps.z])

    def on_navigation_diagnostics(self, msg) -> None:
        try:
            payload = json.loads(msg.data)
        except (TypeError, ValueError):
            self.event("invalid_navigation_diagnostics")
            return
        self.event("navigation_diagnostics", **payload)

    def event(self, kind: str, **data) -> None:
        self.log.write(json.dumps({"time_s": self.now_s(), "kind": kind, **data}, allow_nan=False) + "\n")

    def on_odom(self, msg) -> None:
        self.odom = msg

    def on_phase(self, msg) -> None:
        phase = msg.data.split(":", 1)[0].strip()
        if self.phase != phase:
            self.phase = phase
            self.event("phase", phase=self.phase, detail=msg.data)
            self.get_logger().info(f"flight phase: {msg.data}")
        if self.phase.upper() == "FOLLOW" and self.follow_start is None:
            self.follow_start = self.now_s()
        if self.phase.upper() == "ABORTED" and self.aborted_wall is None:
            self.aborted_wall = time.monotonic()

    def on_observation(self, msg) -> None:
        self.counts["observations"] += 1
        if msg.depth_valid:
            self.counts["valid_depth_observations"] += 1
        self.event("observation", stamp_s=stamp_s(msg.header.stamp), confidence=float(msg.confidence),
                   depth_m=float(msg.depth_m), valid=bool(msg.depth_valid))

    def on_state(self, msg) -> None:
        self.target = msg
        self.state_counts[int(msg.state)] += 1
        self.event("target_state", stamp_s=stamp_s(msg.header.stamp), state=int(msg.state),
                   track_id=int(msg.track_id), target_uuid=str(msg.target_uuid),
                   prediction_age_s=float(msg.prediction_age_s),
                   position_m=[msg.position_m.x, msg.position_m.y, msg.position_m.z],
                   velocity_mps=[msg.velocity_mps.x, msg.velocity_mps.y, msg.velocity_mps.z])
        if (self.initial_selection_uuid and not self.initial_selection_confirmed
                and msg.target_uuid == self.initial_selection_uuid and msg.state == TargetState.STATE_MEASURED):
            self.initial_selection_confirmed = True
            self.event("initial_selection_confirmed", target_uuid=msg.target_uuid, track_id=int(msg.track_id))
        if (self.reselection_uuid and not self.reselection_confirmed
                and msg.target_uuid == self.reselection_uuid and msg.state == TargetState.STATE_MEASURED):
            self.reselection_confirmed = True
            self.event("explicit_reselection_confirmed", target_uuid=msg.target_uuid, track_id=int(msg.track_id))

    def on_status(self, msg) -> None:
        self.status = msg
        self.status_counts[int(msg.lifecycle)] += 1
        self.event("control_status", lifecycle=int(msg.lifecycle), reason=str(msg.reason),
                   track_id=int(msg.track_id), measurement_age_s=float(msg.time_since_measurement_s))
        if msg.lifecycle in (TrackingStatus.LIFECYCLE_FOLLOW, TrackingStatus.LIFECYCLE_PREDICT):
            self.errors.append([self.now_s(), float(msg.distance_error_m), float(msg.height_error_m)])

    def on_command(self, msg) -> None:
        self.counts["commands"] += 1
        self.counts["valid_commands"] += int(msg.valid)

    def on_setpoint(self, msg) -> None:
        self.counts["px4_setpoints"] += 1
        position, velocity = list(msg.position), list(msg.velocity)
        position_finite = sum(math.isfinite(v) for v in position)
        velocity_finite = sum(math.isfinite(v) for v in velocity)
        dimension_valid = len(position) == len(velocity) == 3
        position_partial = 0 < position_finite < 3
        velocity_partial = 0 < velocity_finite < 3
        mixed = position_finite > 0 and velocity_finite > 0
        infinite = any(math.isinf(v) for v in position + velocity)
        inactive = position_finite == velocity_finite == 0
        position_only = dimension_valid and position_finite == 3 and all(math.isnan(v) for v in velocity)
        velocity_only = dimension_valid and velocity_finite == 3 and all(math.isnan(v) for v in position)
        invalid = not (position_only or velocity_only)
        self.counts["classified_px4_setpoints"] += 1
        self.counts["position_only_setpoints"] += int(position_only)
        self.counts["velocity_only_setpoints"] += int(velocity_only)
        self.counts["invalid_setpoints"] += int(invalid)
        self.counts["simultaneous_position_velocity_setpoints"] += int(mixed)
        self.counts["partial_position_setpoints"] += int(position_partial)
        self.counts["partial_velocity_setpoints"] += int(velocity_partial)
        self.counts["malformed_partial_setpoints"] += int(position_partial or velocity_partial)
        self.counts["malformed_dimension_setpoints"] += int(not dimension_valid)
        self.counts["infinite_setpoint_fields"] += int(infinite)
        self.counts["inactive_position_velocity_setpoints"] += int(inactive)
        if self.phase == "FOLLOW":
            self.counts["follow_setpoints"] += 1
            self.counts["follow_position_setpoints"] += int(position_only)
            self.counts["follow_velocity_setpoints"] += int(velocity_only)
            self.counts["follow_invalid_setpoints"] += int(invalid)
        if invalid:
            # Represent nonfinite values explicitly so telemetry remains
            # strict JSON. Partial mixed fields must not escape inspection.
            display = lambda values: [float(v) if math.isfinite(v) else str(float(v)) for v in values]
            self.event("invalid_px4_setpoint", phase=self.phase, position=display(position), velocity=display(velocity),
                       mixed=mixed, partial_position=position_partial, partial_velocity=velocity_partial,
                       dimension_valid=dimension_valid, infinite=infinite, inactive=inactive)

    def on_vehicle_status(self, msg) -> None:
        self.armed_seen |= msg.arming_state == VehicleStatus.ARMING_STATE_ARMED
        self.offboard_seen |= msg.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD

    def on_diagnostics(self, msg) -> None:
        data = json.loads(msg.data)
        self.diagnostics = data
        self.counts["detector_frames"] += 1
        self.counts["detector_frames_with_target"] += int(bool(data["detections"]))
        self.detection_latency.append(data["completed_s"] - data["stamp_s"])
        self.inference_times.append(data["inference_wall_s"])
        for det in data["detections"]:
            self.depth_ratios.append(det["depth_valid_ratio"])
        self.event("detection", **data)

    def on_gimbal_diagnostics(self, msg) -> None:
        data = json.loads(msg.data)
        self.gimbal_diagnostics = data
        self.event("gimbal", **data)

    def on_tracks(self, msg) -> None:
        self.track_snapshot = json.loads(msg.data)
        self.event("tracks", **self.track_snapshot)

    def on_image(self, msg) -> None:
        t = stamp_s(msg.header.stamp)
        if t - self.last_video_s < 0.19:
            return
        self.last_video_s = t
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        if self.video is None:
            self.video = cv2.VideoWriter(str(self.args.output / "onboard.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (msg.width, msg.height))
        if self.diagnostics and abs(t - self.diagnostics["stamp_s"]) < 0.7:
            for det in self.diagnostics["detections"]:
                x1, y1, x2, y2 = (int(v) for v in det["bbox"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"YOLO {det['confidence']:.2f} D={det['depth_m']:.2f}m", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        snapshot = getattr(self, "track_snapshot", None)
        if snapshot:
            for track in snapshot.get("tracks", []):
                if (track.get("selected") and track.get("bbox_xyxy")
                        and 0 <= t - track.get("last_detection_s", -math.inf) < 0.7):
                    x1, y1, x2, y2 = (int(value) for value in track["bbox_xyxy"])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 235, 255), 3)
                    cv2.putText(frame, f"SELECTED #{track['track_id']}", (x1, min(msg.height - 8, y2 + 18)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 235, 255), 1)
        cv2.rectangle(frame, (0, 0), (msg.width, 91 if self.gimbal_diagnostics else 70), (30, 30, 30), -1)
        label = f"t={t:.1f}s {self.phase} state={getattr(self.target, 'state', '-')}"
        cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        if self.target is not None and self.target.target_uuid:
            text = f"selected track={self.target.track_id} task={self.target.target_uuid[:8]}"
            cv2.putText(frame, text, (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 235, 255), 1)
        if self.gimbal_diagnostics and self.gimbal_diagnostics.get("feedback_angles_rad"):
            angles = np.rad2deg(self.gimbal_diagnostics["feedback_angles_rad"])
            text = f"gimbal measured Y/P/R={angles[0]:.1f}/{angles[1]:.1f}/{angles[2]:.1f} deg"
            cv2.putText(frame, text, (10, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 235, 255), 1)
        if self.diagnostics:
            text = f"box age={t - self.diagnostics['stamp_s']:.2f}s (preview overlay)"
            cv2.putText(frame, text, (10, 86 if self.gimbal_diagnostics else 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (210, 210, 210), 1)
        self.video.write(frame)
        self.counts["video_frames"] += 1
        if self.counts["video_frames"] % 50 == 1:
            cv2.imwrite(str(self.args.output / f"frame_{self.counts['video_frames']:05d}.jpg"), frame)

    def record_shutter_result(self, metadata: dict, success: bool, error: str | None = None) -> None:
        result = {"time_s": self.now_s(), **metadata, "success": success}
        if error is not None:
            result["error"] = error
        # Keep each response attached to its own request. Refresh ACKs cannot
        # start or restart the close dwell interval.
        if not hasattr(self, "shutter_results"):
            self.shutter_results = {}
        self.shutter_results[metadata["request_id"]] = result
        kind = "shutter_pose_update_result" if metadata.get("refresh", False) else "shutter_service_result"
        self.event(kind, **result)

    def collect_shutter_response(self) -> None:
        if self.shutter_future is not None:
            if not self.shutter_future.done():
                return
            try:
                response = self.shutter_future.result()
                self.record_shutter_result(self.shutter_pending, bool(response.success) if response else False)
            except Exception as exc:
                self.record_shutter_result(self.shutter_pending, False, str(exc))
            self.shutter_future = None
            self.shutter_pending = None

    def set_shutter(self, active: bool, *, cleanup: bool = False) -> int | None:
        self.collect_shutter_response()
        if self.shutter_future is not None:
            return None
        # Even a fixed mount moves with the aircraft. A world-fixed plane can
        # be left behind during the dwell despite a successful close ACK.
        refresh = bool(active and self.shutter_requested)
        if refresh and self.now_s() - self.shutter_last_pose_update_s < 0.20:
            return
        if active == self.shutter_requested and not refresh and not cleanup:
            return
        if not self.shutter_client.service_is_ready():
            return
        if active:
            try:
                transform = self.shutter_tf_buffer.lookup_transform("map", "camera_link", Time(), timeout=Duration(seconds=0.0))
                position, orientation, tf_source_s = shutter_pose_from_camera_transform(transform, self.now_s())
                x, y, z = position
                pose_source = "measured_camera_tf"
            except (TransformException, ValueError, TypeError) as exc:
                self.event("shutter_pose_unavailable", active=active, refresh=refresh, reason=str(exc))
                return
        else:
            x, y, z = 0.0, 0.0, -50.0
            orientation = [0.0, 0.0, 0.0, 1.0]
            pose_source, tf_source_s = "parked_below_world", None
        request = SetEntityPose.Request()
        request.entity.name = "vision_shutter"
        request.entity.type = request.entity.MODEL
        request.pose.position.x, request.pose.position.y, request.pose.position.z = float(x), float(y), float(z)
        (request.pose.orientation.x, request.pose.orientation.y,
         request.pose.orientation.z, request.pose.orientation.w) = orientation
        # A persistent ROS/Gazebo service bridge avoids spawning a CLI whose
        # startup delay can extend a 0.2 s test stimulus by several frames.
        self.shutter_request_seq += 1
        metadata = {"request_id": self.shutter_request_seq, "active": active, "request_time_s": self.now_s(),
                    "refresh": refresh, "cleanup": cleanup, "pose_source": pose_source, "camera_tf_stamp_s": tf_source_s,
                    "position_m": [float(x), float(y), float(z)], "orientation_xyzw": [float(value) for value in orientation]}
        if not refresh:
            self.shutter_events.append({"time_s": metadata["request_time_s"], **metadata})
        self.event("shutter_pose_update" if refresh else "shutter", time_s=metadata["request_time_s"], **metadata)
        try:
            self.shutter_future = self.shutter_client.call_async(request)
        except Exception as exc:
            self.record_shutter_result(metadata, False, str(exc))
            return metadata["request_id"]
        self.shutter_pending = metadata
        self.shutter_requested = active
        self.shutter_last_pose_update_s = self.now_s()
        return metadata["request_id"]

    def run_shutter_schedule(self, now_s: float) -> None:
        """Close, await its ACK, dwell, then open; never consume dwell in transit.

        Request/ACK events retain their original meanings. The additional
        schedule records describe service-confirmed dwell, not independently
        measured visibility. Failed actions remain failed experimental evidence.
        """
        self.collect_shutter_response()
        for episode in self.occlusion_schedule:
            state = episode["state"]
            if state in ("complete", "failed"):
                continue
            if state == "waiting":
                if now_s - self.follow_start < episode["start_offset_s"]:
                    return
                request_id = self.set_shutter(True)
                if request_id is not None:
                    episode.update(state="closing", close_request_id=request_id)
                return
            if state == "closing":
                result = self.shutter_results.get(episode["close_request_id"])
                if result is None:
                    return
                if not result["success"]:
                    episode.update(state="failed", failure="close_service_failed")
                    self.event("shutter_schedule_failure", **episode)
                    # Best-effort parking after a failed/uncertain close. This
                    # is cleanup, never an assertion of successful occlusion.
                    self.set_shutter(False, cleanup=True)
                    return
                episode.update(state="holding", close_ack_s=result["time_s"],
                               open_not_before_s=result["time_s"] + episode["duration_s"] + episode["render_margin_s"])
                self.event("shutter_hold_started", **episode,
                           semantics="minimum dwell from successful close ACK; rendered visibility is evaluated separately")
                state = "holding"
            if state == "holding":
                if now_s + 1e-9 < episode["open_not_before_s"]:
                    self.set_shutter(True)  # retain measured-TF refresh as the camera moves
                    return
                request_id = self.set_shutter(False)
                if request_id is not None:
                    episode.update(state="opening", open_request_id=request_id,
                                   open_request_s=now_s)
                return
            if state == "opening":
                result = self.shutter_results.get(episode["open_request_id"])
                if result is None:
                    return
                episode.update(state="complete" if result["success"] else "failed",
                               open_ack_s=result["time_s"])
                if not result["success"]:
                    episode["failure"] = "open_service_failed"
                    self.event("shutter_schedule_failure", **episode)
                    # One explicitly labelled cleanup request; a successful
                    # retry cannot rewrite the failed experimental action.
                    self.set_shutter(False, cleanup=True)
                else:
                    self.event("shutter_hold_finished", **episode,
                               ack_to_open_request_s=episode["open_request_s"] - episode["close_ack_s"])
                return

    def tick(self) -> None:
        t = self.now_s()
        if t <= 0:
            return
        if self.start_sim is None:
            self.start_sim = t
        self.end_sim = t
        initial_rule = getattr(self.args, "initial_select", "none")
        if (initial_rule != "none" and self.initial_selection_uuid is None and self.phase == "HOLD"
                and self.diagnostics and self.diagnostics.get("tracking_active")
                and 0 <= t - self.diagnostics["stamp_s"] <= 0.4
                and len(self.diagnostics["detections"]) >= getattr(self.args, "initial_min_candidates", 2)):
            chosen = select_visual_box(self.diagnostics["detections"], initial_rule)
            if chosen is not None:
                self.initial_selection_uuid = self.publish_visual_selection(chosen, "TEST_SCRIPT_INITIAL_SELECTION")
                self.event("initial_selection_requested", target_uuid=self.initial_selection_uuid,
                           source="TEST_SCRIPT_INITIAL_SELECTION", rule=initial_rule,
                           image_stamp_s=self.diagnostics["stamp_s"], bbox=chosen["bbox"])
        if self.args.occlusions and self.follow_start is not None:
            elapsed = t - self.follow_start
            self.run_shutter_schedule(t)
            # An explicitly enabled test operation, after the evaluator's long
            # occlusion/recovery window. It selects a *new task* from a recent
            # real detector box, without simulator identity or truth inputs.
            if (self.args.reselect_after_loss and elapsed >= 32.0 and self.reselection_uuid is None
                    and self.target is not None and self.target.state == TargetState.STATE_LOST
                    and self.status is not None and self.status.lifecycle == TrackingStatus.LIFECYCLE_HOVER
                    and self.diagnostics and 0 <= t - self.diagnostics["stamp_s"] <= 0.4):
                detections = self.diagnostics["detections"]
                chosen = select_visual_box(detections, initial_rule)
                if chosen is not None:
                    self.reselection_uuid = self.publish_visual_selection(chosen, "TEST_SCRIPT_EXPLICIT_RESELECTION")
                    self.event("explicit_reselection_requested", target_uuid=self.reselection_uuid,
                               source="TEST_SCRIPT_EXPLICIT_RESELECTION", image_stamp_s=self.diagnostics["stamp_s"],
                               bbox=chosen["bbox"])
        if self.odom is not None and t - self.last_telemetry >= 0.19:
            self.last_telemetry = t
            p, v = self.odom.pose.pose.position, self.odom.twist.twist.linear
            state = int(self.target.state) if self.target else 0
            row = [t, p.x, p.y, p.z, v.x, v.y, v.z, state]
            self.positions.append(row)
            self.event("telemetry", phase=self.phase, position=[p.x, p.y, p.z], velocity=[v.x, v.y, v.z],
                       velocity_frame=self.odom.child_frame_id, state=state,
                       age_s=float(self.target.prediction_age_s) if self.target else None)
        if self.counts["detector_frames"] and self.counts["detector_frames"] % 50 == 0:
            self.log.flush()

    def publish_visual_selection(self, chosen, source):
        x1, y1, x2, y2 = chosen["bbox"]
        selection = TargetSelection()
        selection.header.stamp = self.get_clock().now().to_msg()
        selection.header.frame_id = "camera_link"
        selection.action = TargetSelection.ACTION_SELECT
        selection.class_name = self.args.target_class
        selection.target_uuid = str(uuid.uuid4())
        selection.center_u_px, selection.center_v_px = (x1 + x2) / 2, (y1 + y2) / 2
        selection.width_px, selection.height_px = x2 - x1, y2 - y1
        selection.source = source
        self.selection_pub.publish(selection)
        return selection.target_uuid

    def termination_reason(self) -> str | None:
        # An abort cannot be hidden by a duration endpoint on the same tick.
        if self.aborted_wall is not None or self.phase.upper() == "ABORTED":
            return "flight_aborted"
        if time.monotonic() - self.started_wall > self.args.wall_timeout:
            return "wall_timeout"
        if self.follow_start is not None and self.now_s() - self.follow_start >= self.args.duration:
            return "follow_duration_reached"
        if (self.follow_start is None and self.start_sim is not None
                and getattr(self.args, "no_follow_duration_s", None) is not None
                and self.now_s() - self.start_sim >= self.args.no_follow_duration_s):
            return "no_follow_duration_reached"
        return None

    def finished(self) -> bool:
        reason = self.termination_reason()
        if reason == "flight_aborted":
            return self.aborted_wall is not None and time.monotonic() - self.aborted_wall > 2.0
        return reason is not None

    def finish(self, interrupted: bool = False) -> dict:
        self.set_shutter(False)
        if self.video:
            self.video.release()
        self.log.close()
        positions = np.asarray(self.positions)
        errors = np.asarray(self.errors)
        # These are estimates, not ground-truth accuracy measurements.
        summary = {
            "source": "ONBOARD_RGBD_YOLO_PX4_FLIGHT",
            "class_name": self.args.target_class,
            "start_sim_s": self.start_sim, "end_sim_s": self.end_sim,
            "follow_start_s": self.follow_start,
            "wall_duration_s": time.monotonic() - self.started_wall,
            "counts": dict(self.counts), "states": dict(self.state_counts), "lifecycles": dict(self.status_counts),
            "setpoint_evidence": {"counter_schema_version": 1,
                                  "topic": "/fmu/in/trajectory_setpoint",
                                  "classified_samples": self.counts["classified_px4_setpoints"],
                                  "required_counters_present": all(name in self.counts for name in SETPOINT_COUNTER_KEYS)},
            "armed_seen": self.armed_seen, "offboard_seen": self.offboard_seen,
            "max_vehicle_altitude_m": float(np.max(positions[:, 3])) if positions.size else None,
            "horizontal_vehicle_span_m": float(np.linalg.norm(np.ptp(positions[:, 1:3], axis=0))) if positions.size else None,
            "estimated_distance_error_rmse_m": float(np.sqrt(np.mean(errors[:, 1] ** 2))) if errors.size else None,
            "estimated_height_error_rmse_m": float(np.sqrt(np.mean(errors[:, 2] ** 2))) if errors.size else None,
            "median_detection_latency_s": float(np.median(self.detection_latency)) if self.detection_latency else None,
            "p95_detection_latency_s": float(np.quantile(self.detection_latency, .95)) if self.detection_latency else None,
            "median_inference_wall_s": float(np.median(self.inference_times)) if self.inference_times else None,
            "median_depth_valid_ratio": float(np.median(self.depth_ratios)) if self.depth_ratios else None,
            "shutter_events": self.shutter_events,
            "occlusion_schedule": getattr(self, "occlusion_schedule", []),
            "explicit_reselection": {"enabled": self.args.reselect_after_loss,
                                     "requested_target_uuid": self.reselection_uuid,
                                     "measured_confirmation": self.reselection_confirmed},
            "initial_selection": {"rule": getattr(self.args, "initial_select", "none"),
                                  "requested_target_uuid": self.initial_selection_uuid,
                                  "measured_confirmation": self.initial_selection_confirmed},
        }
        summary["basic_flight_passed"] = bool(
            self.armed_seen and self.offboard_seen and self.counts["valid_depth_observations"] >= 20
            and self.counts["valid_commands"] >= 100 and self.counts["px4_setpoints"] >= 100
            and summary["max_vehicle_altitude_m"] is not None and summary["max_vehicle_altitude_m"] >= 2.0
            and summary["horizontal_vehicle_span_m"] >= 1.0
            and self.counts["simultaneous_position_velocity_setpoints"] == 0
            and self.counts["invalid_setpoints"] == 0
            and self.counts["classified_px4_setpoints"] == self.counts["px4_setpoints"]
        )
        reason = "interrupted" if interrupted else self.termination_reason() or "ros_context_stopped"
        summary.update(flight_monitor_outcome(summary, reason))
        (self.args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary


def main() -> int:
    if rclpy is None:
        raise RuntimeError("ROS 2 and its flight-monitor dependencies are required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-class", choices=["person", "car"], default="person")
    parser.add_argument("--world", default="stage1_flight")
    parser.add_argument("--duration", type=float, default=45.0, help="Sim seconds after FOLLOW handoff")
    parser.add_argument("--wall-timeout", type=float, default=300.0)
    parser.add_argument("--no-follow-duration-s", type=float, default=None,
                        help="Explicit simulation-time endpoint for tests that must remain in HOVER")
    parser.add_argument("--occlusions", action="store_true")
    parser.add_argument("--short-occlusion-s", type=float, default=0.2)
    parser.add_argument("--monitor-tick-s", type=float, default=.10)
    parser.add_argument("--reselect-after-loss", action="store_true")
    parser.add_argument("--initial-select", choices=["none", "leftmost", "middle", "rightmost"], default="none")
    parser.add_argument("--initial-min-candidates", type=int, default=2)
    args = parser.parse_args()
    if not math.isfinite(args.monitor_tick_s) or not .01 <= args.monitor_tick_s <= .10:
        parser.error("monitor tick must be finite and in [0.01,0.10] seconds")
    with shutdown_requests() as requested:
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = None
        executor = None
        interrupted = False
        try:
            node = FlightMonitor(args)
            executor = SingleThreadedExecutor(context=node.context)
            executor.add_node(node)
            while node.context.ok() and not requested.is_set() and not node.finished():
                executor.spin_once(timeout_sec=0.1)
            interrupted = requested.is_set()
        except (KeyboardInterrupt, ExternalShutdownException):
            interrupted = True
        finally:
            try:
                try:
                    if executor is not None:
                        executor.shutdown()
                finally:
                    if node is not None:
                        try:
                            summary = node.finish(interrupted=interrupted)
                        finally:
                            node.destroy_node()
            finally:
                rclpy.try_shutdown()
    return int(summary["monitor_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
