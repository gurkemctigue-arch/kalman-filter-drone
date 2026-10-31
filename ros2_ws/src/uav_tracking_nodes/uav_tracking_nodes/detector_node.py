"""YOLO11 + RGB-D detector node.

The node publishes a complete ``TargetObservationArray`` per inference and
individual candidates for diagnostic compatibility. A missing
Ultralytics installation is reported clearly and keeps the node alive so the
rest of the graph can be tested with a replay or a replacement detector.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
from threading import Lock
import time
from typing import Any

import numpy as np

try:  # ROS imports are intentionally kept inside the adapter package.
    from ament_index_python.packages import get_package_share_directory
    import rclpy
    from cv_bridge import CvBridge
    from rclpy.node import Node
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.duration import Duration
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image
    from std_msgs.msg import String
    from uav_tracking_interfaces.msg import NavigationOverlap, TargetObservation, TargetObservationArray
except ImportError:  # pragma: no cover - exercised only without ROS 2.
    rclpy = None
    Node = object  # type: ignore[misc,assignment]
    get_package_share_directory = None  # type: ignore[assignment]

from uav_tracking.ros_lifecycle import shutdown_requests
from uav_tracking.core import CameraIntrinsics, depth_roi_stats, pinhole_backproject
from uav_tracking.core.navigation import sample_depth_points
from uav_tracking.core.exclusive_navigation import (
    METHOD as EXCLUSIVE_NAVIGATION_METHOD, MAX_EXCLUSIVE_PIXELS, extract_native_exclusive,
)
from uav_tracking.control.gimbal_geometry import quaternion_rotation
from uav_tracking_nodes.inference_worker import NonQueuingWorker
from uav_tracking_nodes.inference_timing import InferenceTiming


def predict_timing_details(result=None, *, image_shape=None, requested_imgsz=None, effective_threads=None):
    """Read bounded predict metadata only; absent/invalid stages stay unknown."""
    speed = getattr(result, "speed", None)
    speed_ms = {}
    for name in ("preprocess", "inference", "postprocess"):
        raw = speed.get(name) if isinstance(speed, dict) else None
        try:
            value = float(raw) if raw is not None and not isinstance(raw, (bool, str)) else None
        except (TypeError, ValueError, OverflowError):
            value = None
        speed_ms[name] = value if value is not None and math.isfinite(value) and value >= 0 else None
    boxes = getattr(result, "boxes", None)
    try:
        count = len(boxes) if boxes is not None else None
    except (TypeError, ValueError):
        count = None
    return {"ultralytics_speed_ms": speed_ms,
            "decoded_input_shape": list(image_shape) if image_shape is not None else None,
            "requested_imgsz": requested_imgsz,
            "actual_model_input_shape": None,
            "actual_model_input_shape_status": "NOT_OBSERVED",
            "post_nms_count_all_classes": count,
            "effective_inference_threads": effective_threads,
            "scope": "PREDICT_METADATA_ONLY_NOT_DEPTH_NAVIGATION_OR_END_TO_END_DELIVERY"}


def navigation_overlap_evidence(visible_boxes, depth, intrinsics, *, depth_scale,
                                min_depth_m, max_depth_m):
    """Collect every touched intersection pixel; do not decide visibility.

    The 4096-cell cap bounds per-pair transport/work. Out-of-image, over-budget
    or partially invalid evidence stays incomplete, never a smaller valid ROI.
    Pure dictionaries also allow the exact acquisition rule in recorded checks.
    """

    height, width = depth.shape
    pairs = []
    for index, (candidate_a, _, class_a, box_a) in enumerate(visible_boxes):
        for candidate_b, _, class_b, box_b in visible_boxes[index + 1:]:
            low_u, low_v = max(box_a[0], box_b[0]), max(box_a[1], box_b[1])
            high_u, high_v = min(box_a[2], box_b[2]), min(box_a[3], box_b[3])
            if low_u >= high_u or low_v >= high_v:
                continue
            left, top = math.floor(low_u), math.floor(low_v)
            right, bottom = math.ceil(high_u), math.ceil(high_v)
            expected = (right - left) * (bottom - top)
            representable = (-2**31 <= left < 2**31 and -2**31 <= top < 2**31
                             and 0 < right-left < 2**32 and 0 < bottom-top < 2**32
                             and 0 < expected < 2**32)
            pair = dict(candidate_a_id=candidate_a, candidate_b_id=candidate_b,
                        class_a_id=class_a, class_b_id=class_b,
                        bbox_a_px=list(box_a), bbox_b_px=list(box_b),
                        u0=left if representable else 0, v0=top if representable else 0,
                        width=right-left if representable else 0, height=bottom-top if representable else 0,
                        expected_pixel_count=expected if representable else 0, valid_pixel_count=0,
                        rectangle_representable=representable,
                        depth_complete=False, points_camera_m=[])
            if (representable and 0 <= left < right <= width and 0 <= top < bottom <= height
                    and 0 < expected <= 4096):
                u, v = np.meshgrid(np.arange(left, right), np.arange(top, bottom))
                z = depth[top:bottom, left:right].astype(float) * float(depth_scale)
                valid = np.isfinite(z) & (z > 0) & (z >= min_depth_m) & (z <= max_depth_m)
                pair["valid_pixel_count"] = int(valid.sum())
                valid_z = z[valid]
                points = np.column_stack(((u[valid]-intrinsics.cx)*valid_z/intrinsics.fx,
                                          (v[valid]-intrinsics.cy)*valid_z/intrinsics.fy,
                                          valid_z))
                pair["points_camera_m"] = points.reshape(-1).astype(float).tolist()
                pair["depth_complete"] = pair["valid_pixel_count"] == expected
            pairs.append(pair)
    return pairs


def navigation_exclusive_evidence(depth, intrinsics, bbox, visible_boxes, candidate_id, *,
                                 enabled, class_name, inside, overlap_count, depth_scale,
                                 min_depth_m, max_depth_m):
    """Transport complete native E, independently of legacy sampled support."""
    evidence = dict(valid=False, reason="exclusive_navigation_disabled", expected_pixels=0,
                    valid_pixels=0, points_camera_m=[], method=EXCLUSIVE_NAVIGATION_METHOD)
    if not enabled:
        return evidence
    if class_name != "car" or not inside or overlap_count <= 0:
        return {**evidence, "reason": "exclusive_navigation_not_eligible"}
    try:
        result = extract_native_exclusive(
            depth, intrinsics, bbox,
            [box for other_id, _, _, box in visible_boxes if other_id != candidate_id],
            depth_scale=depth_scale, min_depth_m=min_depth_m, max_depth_m=max_depth_m)
        expected, valid = result["expected_pixels"], result["valid_pixels"]
        if (type(expected) is not int or type(valid) is not int
                or not 0 <= valid <= expected < 2**32):
            raise ValueError("unrepresentable_exclusive_counts")
        evidence.update(reason=str(result["reason"]), expected_pixels=expected, valid_pixels=valid)
        if result["valid"]:
            points = np.asarray(result.get("points_camera_m", []), dtype=float)
            if (not 0 < expected <= MAX_EXCLUSIVE_PIXELS or valid != expected
                    or points.shape != (expected, 3) or not np.isfinite(points).all()
                    or np.any(points[:, 2] <= 0)):
                raise ValueError("exclusive_native_count_or_points_mismatch")
            evidence.update(valid=True, points_camera_m=points.reshape(-1).tolist())
    except (TypeError, ValueError, OverflowError, KeyError) as error:
        evidence.update(valid=False, reason="exclusive_extraction_invalid:" + str(error), points_camera_m=[])
    return evidence


@dataclass(frozen=True)
class InferenceSnapshot:
    rgb: Any
    depth: Any
    intrinsics: CameraIntrinsics
    camera_size: tuple[int, int]
    sync_error_s: float
    parameters: dict[str, Any]
    clock_epoch: int
    submitted_ros_ns: int
    rgb_received_ros_ns: int | None = None
    depth_received_ros_ns: int | None = None
    submitted_wall_s: float | None = None
    previous_acquisition_s: float | None = None
    timer_input_lock_wait_wall_s: float | None = None
    timer_input_lock_snapshot_hold_wall_s: float | None = None
    camera_info_source: dict[str, Any] | None = None




class DetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_detection")
        self.declare_parameter("model_path", "models/yolo11n.pt")
        self.declare_parameter("class_name", "person")
        self.declare_parameter("class_id", 0)
        self.declare_parameter("confidence_threshold", 0.45)
        self.declare_parameter("depth_scale", 0.001)
        self.declare_parameter("min_depth_m", 0.2)
        self.declare_parameter("max_depth_m", 30.0)
        self.declare_parameter("min_depth_valid_ratio", 0.35)
        self.declare_parameter("depth_max_age_s", 0.15)
        self.declare_parameter("depth_topic", "/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/color/camera_info")
        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("observation_topic", "/tracking/observations")
        self.declare_parameter("observation_frame_topic", "/tracking/observation_frames")
        self.declare_parameter("inference_image_size", 320)
        self.declare_parameter("max_inference_rate_hz", 5.0)
        self.declare_parameter("inference_device", "cpu")
        self.declare_parameter("inference_threads", 2)
        self.declare_parameter("diagnostics_topic", "/tracking/detection_diagnostics")
        self.declare_parameter("activation_phase_topic", "")
        self.declare_parameter("image_reliability", "best_effort")
        self.declare_parameter("navigation_enabled", False)
        self._navigation_enabled = bool(self.get_parameter("navigation_enabled").value)
        self.declare_parameter("navigation_exclusive_enabled", False)
        self._navigation_exclusive_enabled = bool(self.get_parameter("navigation_exclusive_enabled").value)
        if self._navigation_exclusive_enabled and (
                not self._navigation_enabled or str(self.get_parameter("class_name").value) != "car"):
            raise ValueError("exclusive navigation requires navigation_enabled and car")
        # This optional correction preserves the baseline ROI statistics,
        # association gates, identity rules and navigation geometry.
        surface_defaults = {
            "car_surface_recovery_enabled": False,
            "car_surface_recovery_method": "component_centroid_v1",
            "surface_geometry_frame": "map",
            "surface_tf_timeout_s": 0.02,
            "surface_max_image_pixels": 307200,
            "surface_max_roi_pixels": 307200,
            "surface_max_visible_boxes": 64,
        }
        for name, default in surface_defaults.items():
            self.declare_parameter(name, default)
        self._surface_settings = {name: self.get_parameter(name).value for name in surface_defaults}
        self._surface_settings.update({name: self.get_parameter(name).value for name in (
            "image_topic", "depth_topic", "camera_info_topic")})
        self._surface_tf_buffer = None
        self._surface_tf_listener = None
        if self._surface_settings["car_surface_recovery_enabled"]:
            if str(self.get_parameter("class_name").value) != "car" or int(self.get_parameter("class_id").value) != 2:
                raise ValueError("car surface recovery requires the COCO car class (2)")
            if self._surface_settings["car_surface_recovery_method"] != "component_centroid_v1":
                raise ValueError("unsupported car surface recovery method")
            timeout = float(self._surface_settings["surface_tf_timeout_s"])
            if not math.isfinite(timeout) or not 0 <= timeout <= 0.02:
                raise ValueError("surface TF timeout must be between 0 and 0.02 seconds")
            if not str(self._surface_settings["surface_geometry_frame"]).strip():
                raise ValueError("surface geometry frame is required")
            from tf2_ros import Buffer, TransformListener
            # Bind jump handling to this node's ROS clock, so simulation
            # rollback cannot leave a previous epoch's geometry in the cache.
            self._surface_tf_buffer = Buffer(node=self)
            self._surface_tf_listener = TransformListener(self._surface_tf_buffer, self, spin_thread=False)

        self._bridge = CvBridge()
        self._input_lock = Lock()
        self._stopping = False
        self._depth_messages: deque = deque(maxlen=15)
        self._rgb_message: Any = None
        self._rgb_received_ros_ns: int | None = None
        self._depth_received_ros_ns: dict[int, int] = {}
        self._intrinsics: CameraIntrinsics | None = None
        self._camera_size: tuple[int, int] | None = None
        self._camera_info_source: dict[str, Any] | None = None
        self._model: Any = None
        self._effective_inference_threads: int | None = None
        self._last_inference_stamp: float | None = None
        self._last_submit_ros_ns: int | None = None
        self._last_clock_ros_ns: int | None = None
        self._clock_epoch = 0
        phase_topic = str(self.get_parameter("activation_phase_topic").value)
        self._tracking_active = not bool(phase_topic)
        self._activation_stamp_s: float | None = None
        model_path = self._resolve_model_path(str(self.get_parameter("model_path").value))
        try:
            from ultralytics import YOLO
            import torch

            inference_threads = max(1, int(self.get_parameter("inference_threads").value))
            torch.set_num_threads(inference_threads)
            self._model = YOLO(model_path)
            # Ultralytics' lazy select_device("cpu") resets this to its own
            # NUM_THREADS during the first predict. The start callback runs
            # after backend setup and before warmup/inference, so Gazebo and
            # PX4 keep their CPU share even on the first real sensor frame.
            def enforce_cpu_threads(predictor):
                torch.set_num_threads(inference_threads)
                self._effective_inference_threads = torch.get_num_threads()

            self._model.add_callback("on_predict_start", enforce_cpu_threads)
            self.get_logger().info(f"Loaded YOLO model: {model_path}")
        except Exception as exc:  # dependency/model is optional at graph bringup.
            self.get_logger().warning(
                f"YOLO unavailable ({exc}); observations will be empty until a detector is supplied"
            )

        self._publisher = self.create_publisher(TargetObservation, str(self.get_parameter("observation_topic").value), 20)
        self._frame_publisher = self.create_publisher(
            TargetObservationArray, str(self.get_parameter("observation_frame_topic").value), 20
        )
        self._diagnostics_pub = self.create_publisher(
            String, str(self.get_parameter("diagnostics_topic").value), 20
        )
        if phase_topic:
            self.create_subscription(String, phase_topic, self._on_phase, 10)
        reliability = str(self.get_parameter("image_reliability").value)
        if reliability not in ("best_effort", "reliable"):
            raise ValueError("image_reliability must be reliable or best_effort")
        # Gazebo's bridge offers RELIABLE. On this host BEST_EFFORT large-image
        # readers dropped fragmented samples even though a reliable bag reader
        # received the full camera stream. Depth 1 also avoids FIFO latency.
        sensor_qos = QoSProfile(depth=1, reliability=(
            ReliabilityPolicy.RELIABLE if reliability == "reliable" else ReliabilityPolicy.BEST_EFFORT
        ))
        self.create_subscription(
            Image, str(self.get_parameter("depth_topic").value), self._on_depth, sensor_qos
        )
        self.create_subscription(
            CameraInfo, str(self.get_parameter("camera_info_topic").value), self._on_camera_info, sensor_qos
        )
        self.create_subscription(
            Image, str(self.get_parameter("image_topic").value), self._on_rgb, sensor_qos
        )
        rate = float(self.get_parameter("max_inference_rate_hz").value)
        self._inference_period_ns = math.ceil(1_000_000_000 / (rate if rate > 0 else 30.0))
        self._worker = NonQueuingWorker(self._infer_snapshot, self._on_inference_error)
        # A coarse inference-period timer quantizes a 0.21 s inference to
        # 0.4 s between submissions at 5 Hz. Poll cheaply and apply the exact
        # ROS-time start-to-start limit below instead.
        self._inference_timer = self.create_timer(0.02, self._process_latest)

    @staticmethod
    def _resolve_model_path(model_path: str) -> str:
        """Resolve relative checkpoints in source and installed layouts."""

        requested = Path(model_path).expanduser()
        if requested.is_absolute() or requested.exists():
            return str(requested)
        candidates = [Path.cwd() / requested]
        # ``--symlink-install`` keeps this source-relative path available.
        candidates.append(Path(__file__).resolve().parents[3] / requested)
        if get_package_share_directory is not None:
            try:
                candidates.append(Path(get_package_share_directory("uav_tracking_bringup")) / requested)
            except Exception:
                pass
        configured_root = os.environ.get("UAV_TRACKING_MODEL_DIR", "")
        if configured_root:
            candidates.append(Path(configured_root) / requested.name)
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return model_path

    def _on_phase(self, message: Any) -> None:
        # A flight task starts after takeoff has settled. Acquisition during
        # takeoff can anchor a clipped half-body box to a different surface
        # point and invalidate the track before the follow task even begins.
        # Once started, keep processing through visual loss/hover.
        with self._input_lock:
            if not self._tracking_active and message.data.split(":", 1)[0].strip() in ("HOLD", "FOLLOW"):
                self._activation_stamp_s = self.get_clock().now().nanoseconds * 1e-9
                self._tracking_active = True

    def _on_camera_info(self, message: CameraInfo) -> None:
        with self._input_lock:
            self._intrinsics = CameraIntrinsics(message.k[0], message.k[4], message.k[2], message.k[5])
            self._camera_size = (int(message.width), int(message.height))
            self._camera_info_source = {
                "stamp_ns": self._stamp_nanoseconds(message.header.stamp),
                "frame_id": str(message.header.frame_id),
                "calibration_scope": "STATIC_CALIBRATION_CACHED_CAMERA_INFO",
            }

    def _on_depth(self, message: Image) -> None:
        with self._input_lock:
            self._depth_messages.append(message)
            received = getattr(self, "_depth_received_ros_ns", {})
            received[self._stamp_nanoseconds(message.header.stamp)] = int(self.get_clock().now().nanoseconds)
            retained = {self._stamp_nanoseconds(item.header.stamp) for item in self._depth_messages}
            self._depth_received_ros_ns = {key: value for key, value in received.items() if key in retained}

    @staticmethod
    def _stamp_seconds(stamp: Any) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    @staticmethod
    def _stamp_nanoseconds(stamp: Any) -> int:
        return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)

    def _clock_now_locked(self) -> int:
        """Observe ROS time under the input lock and invalidate old epochs."""

        now_ns = int(self.get_clock().now().nanoseconds)
        if self._last_clock_ros_ns is not None and now_ns < self._last_clock_ros_ns:
            self._clock_epoch += 1
            self._last_submit_ros_ns = None
            self._last_inference_stamp = None
            self._rgb_message = None
            self._rgb_received_ros_ns = None
            self._depth_messages.clear()
            self._depth_received_ros_ns = {}
            if self._tracking_active:
                self._activation_stamp_s = now_ns * 1e-9
        self._last_clock_ros_ns = now_ns
        return now_ns

    def _snapshot_current_locked(self, snapshot: InferenceSnapshot, now_ns: int) -> bool:
        return (
            snapshot.clock_epoch == self._clock_epoch
            and snapshot.submitted_ros_ns <= now_ns
            and self._stamp_nanoseconds(snapshot.rgb.header.stamp) <= now_ns
            and self._stamp_nanoseconds(snapshot.depth.header.stamp) <= now_ns
        )

    def _on_rgb(self, message: Image) -> None:
        # Fast callbacks keep the newest sensor data even when CPU inference
        # is slower than the camera. Infer on a snapshot, never a FIFO backlog.
        with self._input_lock:
            self._rgb_message = message
            self._rgb_received_ros_ns = int(self.get_clock().now().nanoseconds)

    def _process_latest(self) -> None:
        # This timer only snapshots/submits work. Inference must not occupy
        # the ROS executor that receives sensor messages and /clock updates.
        timer_requested_wall = time.perf_counter()
        with self._input_lock:
            timer_acquired_wall = time.perf_counter()
            if getattr(self, "_stopping", False):
                return
            # Check rollback even while busy: an in-flight result from the
            # previous simulation epoch must never reach the estimator.
            now_ns = self._clock_now_locked()
            if self._model is None or self._worker.busy:
                return
            if self._last_submit_ros_ns is not None and (
                now_ns - self._last_submit_ros_ns < self._inference_period_ns
            ):
                return
            message = self._rgb_message
            depths = tuple(
                item for item in self._depth_messages
                if self._stamp_nanoseconds(item.header.stamp) <= now_ns
            )
            intrinsics, camera_size = self._intrinsics, self._camera_size
            if message is None or not depths or intrinsics is None or camera_size is None:
                return
            if self._stamp_nanoseconds(message.header.stamp) > now_ns:
                return
            stamp_seconds = self._stamp_seconds(message.header.stamp)
            if self._last_inference_stamp is not None and stamp_seconds <= self._last_inference_stamp:
                return
            depth_message = min(
                depths,
                key=lambda item: abs(stamp_seconds - self._stamp_seconds(item.header.stamp)),
            )
            sync_error = abs(stamp_seconds - self._stamp_seconds(depth_message.header.stamp))
            if sync_error > float(self.get_parameter("depth_max_age_s").value):
                return
            # Ground geometry is transformed using this RGB acquisition TF.
            # It must therefore use exactly the aligned depth acquisition,
            # including while the camera gimbal is moving.
            if getattr(self, "_navigation_enabled", False) and sync_error > 1e-6:
                return
            parameters = {name: self.get_parameter(name).value for name in (
                "inference_image_size", "inference_device", "class_id", "class_name", "confidence_threshold",
                "depth_scale", "min_depth_m", "max_depth_m", "min_depth_valid_ratio",
            )}
            parameters.update(getattr(self, "_surface_settings", {}))
            snapshot = InferenceSnapshot(
                message, depth_message, intrinsics, camera_size, sync_error, parameters,
                self._clock_epoch, now_ns,
                getattr(self, "_rgb_received_ros_ns", None),
                getattr(self, "_depth_received_ros_ns", {}).get(self._stamp_nanoseconds(depth_message.header.stamp)),
                time.perf_counter(), self._last_inference_stamp,
                timer_acquired_wall - timer_requested_wall,
                time.perf_counter() - timer_acquired_wall,
                None if getattr(self, "_camera_info_source", None) is None else dict(self._camera_info_source),
            )
            if self._worker.submit(snapshot):
                self._last_inference_stamp = stamp_seconds
                self._last_submit_ros_ns = now_ns

    def _on_inference_error(self, error: Exception) -> None:
        if not getattr(self, "_stopping", False):
            self.get_logger().warning(f"YOLO inference failed: {error}")

    def _lookup_surface_up(self, snapshot: InferenceSnapshot) -> tuple[np.ndarray, dict[str, Any]]:
        """World up in the optical frame at this acquisition, never latest TF."""
        from tf2_ros import TransformException

        camera_frame = str(snapshot.rgb.header.frame_id)
        geometry_frame = str(snapshot.parameters.get("surface_geometry_frame", "map"))
        try:
            transform = self._surface_tf_buffer.lookup_transform(
                camera_frame, geometry_frame, Time.from_msg(snapshot.rgb.header.stamp),
                timeout=Duration(seconds=float(snapshot.parameters.get("surface_tf_timeout_s", 0.02))),
            )
        except TransformException as error:
            raise ValueError("same-acquisition TF unavailable: " + str(error)) from error
        q = transform.transform.rotation
        rotation = quaternion_rotation((q.x, q.y, q.z, q.w))
        up = rotation @ np.array([0., 0., 1.])
        return up, {
            "query_stamp_ns": self._stamp_nanoseconds(snapshot.rgb.header.stamp),
            "target_frame": camera_frame, "source_frame": geometry_frame,
            "returned_stamp_ns": self._stamp_nanoseconds(transform.header.stamp),
            "rotation_camera_from_geometry": rotation.tolist(), "up_camera": up.tolist(),
            "lookup_policy": "EXACT_ACQUISITION_NO_LATEST_FALLBACK",
        }

    def _prepare_surface_recovery(self, snapshot: InferenceSnapshot, depth: np.ndarray,
                                  visible_boxes: list) -> tuple[Any, dict[str, Any]]:
        """Prepare one shared geometry context; failure preserves all raw inputs."""
        parameters = snapshot.parameters
        enabled = bool(parameters.get("car_surface_recovery_enabled", False))
        info = {
            "enabled": enabled,
            "method": str(parameters.get("car_surface_recovery_method", "component_centroid_v1")),
            "status": "RAW_BASELINE", "reason": "DISABLED",
            "source_key": [snapshot.clock_epoch, self._stamp_nanoseconds(snapshot.rgb.header.stamp)],
            "rgb_topic": parameters.get("image_topic", "/camera/color/image_raw"),
            "depth_topic": parameters.get("depth_topic", "/camera/aligned_depth_to_color/image_raw"),
            "camera_info_topic": parameters.get("camera_info_topic", "/camera/color/camera_info"),
            "rgb_stamp_ns": self._stamp_nanoseconds(snapshot.rgb.header.stamp),
            "depth_stamp_ns": self._stamp_nanoseconds(snapshot.depth.header.stamp),
            "camera_frame": str(snapshot.rgb.header.frame_id),
            "depth_frame": str(snapshot.depth.header.frame_id),
            "camera_info_source": snapshot.camera_info_source,
            "intrinsics": {name: float(getattr(snapshot.intrinsics, name)) for name in ("fx", "fy", "cx", "cy")},
            "camera_size": list(snapshot.camera_size), "depth_dtype": str(depth.dtype),
            "depth_options": {name: parameters[name] for name in (
                "depth_scale", "min_depth_m", "max_depth_m", "min_depth_valid_ratio")},
            "roi_margin": 0.15, "covariance_status": "EXISTING_RAW_ROI_HEURISTIC_NOT_CENTROID_CALIBRATED",
            "identity_assessed": False, "pending_implemented": False,
        }
        if not enabled:
            return None, info
        info["status"] = "RAW_FALLBACK"
        if str(parameters["class_name"]) != "car" or int(parameters["class_id"]) != 2:
            info["reason"] = "NOT_CAR_CLASS"
            return None, info
        if info["method"] != "component_centroid_v1":
            info["reason"] = "UNSUPPORTED_METHOD"
            return None, info
        if info["rgb_stamp_ns"] != info["depth_stamp_ns"]:
            info["reason"] = "RGB_DEPTH_INTEGER_STAMP_MISMATCH"
            return None, info
        if info["rgb_stamp_ns"] == 0:
            # tf2 reserves zero for "latest", so exact acquisition recovery
            # cannot be requested at simulation epoch zero.
            info["reason"] = "ZERO_STAMP_WOULD_QUERY_LATEST_TF"
            return None, info
        if not info["camera_frame"] or info["depth_frame"] != info["camera_frame"]:
            info["reason"] = "ALIGNED_DEPTH_FRAME_MISMATCH"
            return None, info
        if snapshot.camera_info_source is None:
            info["reason"] = "CAMERA_INFO_SOURCE_UNAVAILABLE"
            return None, info
        if snapshot.camera_info_source["frame_id"] != info["camera_frame"]:
            info["reason"] = "CAMERA_INFO_FRAME_MISMATCH"
            return None, info
        if not any(item[2] == 2 for item in visible_boxes):
            info["reason"] = "NO_CAR_CANDIDATES"
            return None, info
        try:
            from uav_tracking.core.car_surface_measurement import (
                DepthOptions, WorkBudget, prepare_car_surface_frame,
            )
            from uav_tracking.core.navigation import NavigationPrior

            up_camera, info["tf"] = self._lookup_surface_up(snapshot)
            prior = NavigationPrior("car", 4.5, 1.8, 1.5,
                                    dimension_std_m=(0.45, 0.18, 0.15),
                                    prior_id="declared_family_dimensions_v4")
            info["family_prior"] = {"class_name": "car", "dimensions_m": [4.5, 1.8, 1.5],
                                    "dimension_std_m": [0.45, 0.18, 0.15]}
            budget = WorkBudget(
                max_image_pixels=int(parameters.get("surface_max_image_pixels", 307200)),
                max_roi_pixels=int(parameters.get("surface_max_roi_pixels", 307200)),
                max_visible_boxes=int(parameters.get("surface_max_visible_boxes", 64)),
            )
            info["resource_budget"] = dict(vars(budget))
            context = prepare_car_surface_frame(
                depth, snapshot.intrinsics, [item[3] for item in visible_boxes],
                depth_options=DepthOptions(
                    float(parameters["min_depth_m"]), float(parameters["max_depth_m"]),
                    depth_scale=float(parameters["depth_scale"]),
                    min_valid_fraction=float(parameters["min_depth_valid_ratio"])),
                prior=prior, up_camera=up_camera, budget=budget,
            )
            info.update(status="GEOMETRY_PREPARED", reason="PER_CANDIDATE_ASSESSMENT",
                        geometry=context.diagnostics)
            return context, info
        except (ValueError, RuntimeError, TypeError) as error:
            info.update(reason="GEOMETRY_OR_TF_UNAVAILABLE", error=str(error))
            return None, info

    def _infer_snapshot(self, snapshot: InferenceSnapshot) -> None:
        timing = InferenceTiming()
        outcome = {"status": "early_return", "reason": "not_completed",
                   "predict_details": predict_timing_details()}
        try:
            self._infer_timed_snapshot(snapshot, timing, outcome)
        except BaseException as error:
            outcome.update(status="exception", reason=type(error).__name__)
            raise
        finally:
            report = timing.snapshot(final=True)
            try:
                self.get_logger().info("INFERENCE_JOB_TIMING " + json.dumps({
                    "job_key": [snapshot.clock_epoch, self._stamp_nanoseconds(snapshot.rgb.header.stamp)],
                    "acquisition_s": self._stamp_seconds(snapshot.rgb.header.stamp),
                    "submitted_source_s": snapshot.submitted_ros_ns * 1e-9,
                    "timer_input_lock_wait_wall_s": snapshot.timer_input_lock_wait_wall_s,
                    "timer_input_lock_snapshot_hold_wall_s": snapshot.timer_input_lock_snapshot_hold_wall_s,
                    **outcome, **report,
                }, allow_nan=False, separators=(",", ":")))
            except Exception:
                # An unavailable logger must not replace the original model,
                # conversion or publisher exception delivered to the worker.
                if outcome["status"] != "exception":
                    raise

    def _infer_timed_snapshot(self, snapshot: InferenceSnapshot, timing: InferenceTiming,
                              outcome: dict[str, Any]) -> None:
        with timing.input_lock(self._input_lock, "entry"):
            if getattr(self, "_stopping", False):
                outcome["reason"] = "stopping_at_entry"
                return
            worker_started_ros_ns = self._clock_now_locked()
            if not self._snapshot_current_locked(snapshot, worker_started_ros_ns):
                outcome["reason"] = "invalid_snapshot_at_entry"
                return
        message, depth_message = snapshot.rgb, snapshot.depth
        stamp_seconds = self._stamp_seconds(message.header.stamp)
        parameters = snapshot.parameters
        started = time.perf_counter()
        with timing.stage("decode"):
            image = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            depth = np.asarray(self._bridge.imgmsg_to_cv2(depth_message, desired_encoding="passthrough"))
        if image.shape[:2] != depth.shape[:2] or snapshot.camera_size != (message.width, message.height):
            raise ValueError("RGB, aligned depth and CameraInfo dimensions must match")
        outcome["predict_details"] = predict_timing_details(image_shape=image.shape,
            requested_imgsz=int(parameters["inference_image_size"]),
            effective_threads=getattr(self, "_effective_inference_threads", None))
        with timing.stage("yolo_predict"):
            result = self._model.predict(
                image, imgsz=int(parameters["inference_image_size"]),
                device=str(parameters["inference_device"]), verbose=False,
            )[0]
        outcome["predict_details"] = predict_timing_details(result, image_shape=image.shape,
            requested_imgsz=int(parameters["inference_image_size"]),
            effective_threads=getattr(self, "_effective_inference_threads", None))
        class_id = int(parameters["class_id"])
        class_name = str(parameters["class_name"])
        threshold = float(parameters["confidence_threshold"])
        with timing.input_lock(self._input_lock, "post_predict"):
            if getattr(self, "_stopping", False):
                outcome["reason"] = "stopping_after_predict"
                return
            if not self._snapshot_current_locked(snapshot, self._clock_now_locked()):
                outcome["reason"] = "invalid_snapshot_after_predict"
                return
            tracking_active, activation_stamp_s = self._tracking_active, self._activation_stamp_s
        timing.begin("depth_navigation_geometry")
        # Other classes can occlude this target or contaminate ground samples.
        # Keep their image boxes without creating tracking candidates for them.
        visible_boxes = []
        for candidate_id, box in enumerate(result.boxes):
            score = float(box.conf[0])
            detected_class = int(box.cls[0])
            if score < threshold:
                continue
            bounds = tuple(float(value) for value in box.xyxy[0].tolist())
            if (len(bounds) != 4 or not all(math.isfinite(value) and abs(value) <= np.finfo(np.float32).max for value in bounds)
                    or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]):
                continue
            visible_boxes.append((candidate_id, score, detected_class, bounds))
        surface_context, surface_diagnostics = self._prepare_surface_recovery(snapshot, depth, visible_boxes)
        surface_diagnostics["visible_boxes"] = [
            {"candidate_id": item[0], "confidence": item[1], "class_id": item[2], "bbox": list(item[3])}
            for item in visible_boxes
        ]
        overlaps = []
        if getattr(self, "_navigation_enabled", False):
            overlaps = navigation_overlap_evidence(
                visible_boxes, depth, snapshot.intrinsics,
                depth_scale=float(parameters["depth_scale"]),
                min_depth_m=float(parameters["min_depth_m"]),
                max_depth_m=float(parameters["max_depth_m"]))
        detections, observations = [], []
        for box_index, (candidate_id, score, detected_class, (x1, y1, x2, y2)) in enumerate(visible_boxes):
            if detected_class != class_id:
                continue
            stats = depth_roi_stats(
                depth,
                (x1, y1, x2, y2),
                depth_scale=float(parameters["depth_scale"]),
                min_depth=float(parameters["min_depth_m"]),
                max_depth=float(parameters["max_depth_m"]),
                margin=0.15,
            )
            observation = TargetObservation()
            observation.header = message.header
            observation.acquisition_epoch = snapshot.clock_epoch
            observation.candidate_id = candidate_id
            observation.class_name = class_name
            observation.class_id = detected_class
            observation.confidence = score
            observation.bbox_x_min_px = x1
            observation.bbox_y_min_px = y1
            observation.bbox_x_max_px = x2
            observation.bbox_y_max_px = y2
            observation.center_u_px = (x1 + x2) / 2.0
            observation.center_v_px = (y1 + y2) / 2.0
            observation.depth_valid = stats.is_valid and stats.valid_fraction >= float(parameters["min_depth_valid_ratio"])
            observation.depth_m = float(stats.median or 0.0)
            observation.depth_valid_ratio = float(stats.valid_fraction)
            observation.depth_std_m = float(stats.std or 0.0)
            observation.depth_min_m = float(stats.minimum or 0.0)
            observation.depth_max_m = float(stats.maximum or 0.0)
            observation.camera_frame = message.header.frame_id
            if observation.depth_valid:
                point = pinhole_backproject(
                    (observation.center_u_px, observation.center_v_px), observation.depth_m, snapshot.intrinsics
                )
                observation.position_camera_m.x = float(point[0])
                observation.position_camera_m.y = float(point[1])
                observation.position_camera_m.z = float(point[2])
            raw_position = ([float(observation.position_camera_m.x), float(observation.position_camera_m.y),
                             float(observation.position_camera_m.z)] if observation.depth_valid else None)
            surface_candidate = {
                "box_index": box_index, "raw_position_camera_m": raw_position,
                "output_position_camera_m": raw_position,
                "action": "RAW_FALLBACK" if surface_diagnostics["enabled"] else "RAW_BASELINE",
                "status": "UNKNOWN" if surface_diagnostics["enabled"] else "DISABLED",
                "reason": surface_diagnostics["reason"],
                "reference_kind": "bbox_center_ray_raw_roi_median_depth",
            }
            if surface_context is not None:
                try:
                    assessment = surface_context.assess(box_index, class_name=class_name)
                except (ValueError, RuntimeError, np.linalg.LinAlgError) as error:
                    assessment = {"status": "UNKNOWN", "reason": "GEOMETRY_ASSESSMENT_FAILED",
                                  "evidence": {"error": str(error)}, "measurement": None}
                surface_candidate.update(status=assessment["status"], reason=assessment["reason"],
                                         evidence=assessment["evidence"])
                replacement = assessment["measurement"]
                # Keep raw depth validity/quality and its R heuristic; the
                # estimator transforms this point and recomputes pose lever R.
                if replacement is not None and observation.depth_valid:
                    corrected = np.asarray(replacement["position_camera_m"], dtype=float)
                    if corrected.shape != (3,) or not np.isfinite(corrected).all():
                        raise ValueError("surface recovery returned an invalid component centroid")
                    observation.position_camera_m.x = float(corrected[0])
                    observation.position_camera_m.y = float(corrected[1])
                    observation.position_camera_m.z = float(corrected[2])
                    surface_candidate.update(action="USE_COMPONENT_CENTROID", measurement=replacement,
                                             output_position_camera_m=corrected.tolist(),
                                             reference_kind=replacement["reference_kind"])
                elif replacement is not None:
                    surface_candidate.update(status="UNKNOWN", reason="RAW_DEPTH_INVALID")
            # Publish only this acquisition's final assessment. A valid raw
            # ROI fallback never inherits an earlier supported surface point.
            observation.surface_recovery_enabled = bool(surface_diagnostics["enabled"])
            observation.surface_measurement_supported = bool(
                observation.surface_recovery_enabled and observation.depth_valid
                and surface_candidate["status"] == "SUPPORTED_SURFACE_MEASUREMENT"
                and surface_candidate["action"] == "USE_COMPONENT_CENTROID"
            )
            if getattr(self, "_navigation_enabled", False):
                touching = [pair for pair in overlaps
                            if candidate_id in (pair["candidate_a_id"], pair["candidate_b_id"])]
                inside = x1 > 2 and y1 > 2 and x2 < message.width - 2 and y2 < message.height - 2
                observation.navigation_bbox_inside_image = bool(inside)
                observation.navigation_overlap_count = len(touching)
                observation.navigation_bbox_complete = bool(inside and not touching)
                # Keep the original full support even for overlapping boxes.
                # Extra exclusive points only support a downstream depth-order
                # model; that model never substitutes this for the full cloud.
                points = sample_depth_points(
                    depth, snapshot.intrinsics, (x1, y1, x2, y2), stride=2,
                    depth_scale=float(parameters["depth_scale"]), max_points=500,
                    min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]),
                ) if inside else np.empty((0, 3))
                observation.navigation_points_camera_m = points.reshape(-1).astype(float).tolist()
                exclusive = sample_depth_points(
                    depth, snapshot.intrinsics, (x1, y1, x2, y2),
                    exclude_bboxes=[other_box for other_id, _, _, other_box in visible_boxes if other_id != candidate_id],
                    stride=2, depth_scale=float(parameters["depth_scale"]), max_points=500,
                    min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]),
                ) if inside and touching else np.empty((0, 3))
                observation.navigation_visibility_support_camera_m = exclusive.reshape(-1).astype(float).tolist()
                native_exclusive = navigation_exclusive_evidence(
                    depth, snapshot.intrinsics, (x1, y1, x2, y2), visible_boxes, candidate_id,
                    enabled=getattr(self, "_navigation_exclusive_enabled", False),
                    class_name=class_name, inside=inside, overlap_count=len(touching),
                    depth_scale=float(parameters["depth_scale"]),
                    min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]))
                observation.navigation_exclusive_depth_complete = native_exclusive["valid"]
                observation.navigation_exclusive_expected_pixel_count = native_exclusive["expected_pixels"]
                observation.navigation_exclusive_valid_pixel_count = native_exclusive["valid_pixels"]
                observation.navigation_exclusive_reason = native_exclusive["reason"]
                observation.navigation_exclusive_points_camera_m = native_exclusive["points_camera_m"]
                ray = pinhole_backproject(((x1 + x2) / 2, y2), 1.0, snapshot.intrinsics)
                observation.navigation_bottom_ray_camera.x = float(ray[0])
                observation.navigation_bottom_ray_camera.y = float(ray[1])
                observation.navigation_bottom_ray_camera.z = float(ray[2])
            observations.append(observation)
            detections.append({
                "candidate_id": int(candidate_id),
                "class_id": detected_class,
                "confidence": score,
                "bbox": [x1, y1, x2, y2],
                "depth_valid": bool(observation.depth_valid),
                "depth_m": float(observation.depth_m),
                "depth_valid_ratio": float(stats.valid_fraction),
                "depth_std_m": float(observation.depth_std_m),
                "depth_min_m": float(observation.depth_min_m),
                "depth_max_m": float(observation.depth_max_m),
                "surface_recovery": surface_candidate,
                "navigation_bbox_complete": bool(getattr(observation, "navigation_bbox_complete", False)),
                "navigation_bbox_inside_image": bool(getattr(observation, "navigation_bbox_inside_image", False)),
                "navigation_overlap_count": int(getattr(observation, "navigation_overlap_count", 0)),
                "navigation_exclusive": {
                    "enabled": bool(getattr(self, "_navigation_exclusive_enabled", False)),
                    "method": EXCLUSIVE_NAVIGATION_METHOD,
                    "depth_complete": bool(getattr(observation, "navigation_exclusive_depth_complete", False)),
                    "expected_pixels": int(getattr(observation, "navigation_exclusive_expected_pixel_count", 0)),
                    "valid_pixels": int(getattr(observation, "navigation_exclusive_valid_pixel_count", 0)),
                    "reason": str(getattr(observation, "navigation_exclusive_reason", "not_generated")),
                },
            })
        if surface_context is not None:
            surface_diagnostics["geometry"] = surface_context.diagnostics
        surface_diagnostics["candidate_count"] = len(detections)
        surface_diagnostics["corrected_count"] = sum(
            item["surface_recovery"]["action"] == "USE_COMPONENT_CENTROID" for item in detections)
        surface_diagnostics["raw_fallback_count"] = sum(
            item["surface_recovery"]["action"] == "RAW_FALLBACK" for item in detections)
        ground_points = np.empty((0, 3))
        if getattr(self, "_navigation_enabled", False):
            ground_points = sample_depth_points(
                depth, snapshot.intrinsics, exclude_bboxes=[item[3] for item in visible_boxes],
                stride=8, depth_scale=float(parameters["depth_scale"]), max_points=1200,
                min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]),
            )
        timing.end()
        with timing.input_lock(self._input_lock, "publication"):
            if getattr(self, "_stopping", False):
                outcome["reason"] = "stopping_before_publish"
                return
            now_ns = self._clock_now_locked()
            if not self._snapshot_current_locked(snapshot, now_ns):
                outcome["reason"] = "invalid_snapshot_before_publish"
                return
            timing.mark("bookkeeping")
            if tracking_active and (
                activation_stamp_s is None or stamp_seconds >= activation_stamp_s
            ):
                # Commit all candidates atomically. The estimator must never
                # guess when a frame is complete using an arbitrary timeout.
                frame_publisher = getattr(self, "_frame_publisher", None)
                if frame_publisher is not None:
                    frame = TargetObservationArray()
                    frame.header = message.header
                    frame.observations = observations
                    if getattr(self, "_navigation_enabled", False):
                        frame.navigation_ground_points_camera_m = ground_points.reshape(-1).astype(float).tolist()
                        frame.navigation_overlaps = []
                        for payload in overlaps:
                            pair_message = NavigationOverlap()
                            for name, value in payload.items():
                                setattr(pair_message, name, value)
                            frame.navigation_overlaps.append(pair_message)
                    timing.mark("frame_build")
                    with timing.stage("frame_publish"):
                        frame_publisher.publish(frame)
                timing.mark("bookkeeping")
                with timing.stage("observation_publish"):
                    for observation in observations:
                        self._publisher.publish(observation)
            timing.mark("bookkeeping")
            diagnostics = String()
            diagnostics.data = json.dumps({
                "stamp_s": stamp_seconds,
                "clock_epoch": snapshot.clock_epoch,
                "acquisition_ns": self._stamp_nanoseconds(message.header.stamp),
                "completed_s": now_ns * 1e-9,
                "rgb_received_s": None if snapshot.rgb_received_ros_ns is None else snapshot.rgb_received_ros_ns * 1e-9,
                "depth_stamp_s": self._stamp_seconds(depth_message.header.stamp),
                "depth_received_s": None if snapshot.depth_received_ros_ns is None else snapshot.depth_received_ros_ns * 1e-9,
                "submitted_s": snapshot.submitted_ros_ns * 1e-9,
                "worker_started_s": worker_started_ros_ns * 1e-9,
                "worker_wait_wall_s": None if snapshot.submitted_wall_s is None else started - snapshot.submitted_wall_s,
                "input_age_at_submit_s": snapshot.submitted_ros_ns * 1e-9 - stamp_seconds,
                "acquisition_gap_s": None if snapshot.previous_acquisition_s is None else stamp_seconds - snapshot.previous_acquisition_s,
                "inference_wall_s": time.perf_counter() - started,
                "rgb_depth_sync_error_s": snapshot.sync_error_s,
                "class_name": class_name,
                "tracking_active": tracking_active,
                "inference_backend": type(self._model).__name__,
                "inference_threads": getattr(self, "_effective_inference_threads", None),
                "image_size": [int(message.width), int(message.height)],
                "navigation_enabled": bool(getattr(self, "_navigation_enabled", False)),
                "navigation_ground_sample_count": len(ground_points),
                "navigation_overlap_pair_count": len(overlaps),
                "navigation_incomplete_overlap_pair_count": sum(not pair["depth_complete"] for pair in overlaps),
                "surface_recovery": surface_diagnostics,
                "detections": detections,
                "timing_before_diagnostics": timing.snapshot(),
            })
            timing.mark("diagnostics_encode")
            with timing.stage("diagnostics_publish"):
                self._diagnostics_pub.publish(diagnostics)
            outcome.update(status="completed", reason="diagnostics_published")

    def destroy_node(self) -> Any:
        # Do not publish the final inference during teardown. Native work
        # still completes before its model, publishers or context are freed.
        with self._input_lock:
            self._stopping = True
        timer = getattr(self, "_inference_timer", None)
        if timer is not None:
            timer.cancel()
        worker = getattr(self, "_worker", None)
        if worker is not None:
            worker.shutdown()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required to run detector_node")
    with shutdown_requests() as requested:
        # Keep the context/publishers alive while accepted native inference
        # finishes; a repeated launch SIGINT only sets the same request flag.
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = None
        executor = None
        try:
            node = DetectorNode()
            executor = SingleThreadedExecutor(context=node.context)
            executor.add_node(node)
            while rclpy.ok() and not requested.is_set():
                executor.spin_once(timeout_sec=0.2)
        except (KeyboardInterrupt, ExternalShutdownException):
            # Also support an externally stopped context or embedded caller.
            pass
        finally:
            try:
                try:
                    if executor is not None:
                        executor.shutdown()
                finally:
                    if node is not None:
                        node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()


if __name__ == "__main__":
    main()
