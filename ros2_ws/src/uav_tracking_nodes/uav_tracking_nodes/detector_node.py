"""YOLO11 + RGB-D detector node.

The node publishes a complete ``TargetObservationArray`` per inference and
individual candidates for diagnostic compatibility. A missing
Ultralytics installation is reported clearly and keeps the node alive so the
rest of the graph can be tested with a replay or a replacement detector.
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
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
    from sensor_msgs.msg import CameraInfo, Image
    from std_msgs.msg import String
    from uav_tracking_interfaces.msg import TargetObservation, TargetObservationArray
except ImportError:  # pragma: no cover - exercised only without ROS 2.
    rclpy = None
    Node = object  # type: ignore[misc,assignment]
    get_package_share_directory = None  # type: ignore[assignment]

from uav_tracking.core import CameraIntrinsics, bbox_iou, depth_roi_stats, pinhole_backproject
from uav_tracking.core.navigation import sample_depth_points
from uav_tracking_nodes.inference_worker import NonQueuingWorker


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


@contextmanager
def shutdown_requests():
    """Keep repeated shutdown signals from interrupting native worker joins.

    ROS's default SIGINT handling can raise a second KeyboardInterrupt while
    ThreadPoolExecutor is joining torch inference. A join interrupted there
    can leave native work alive at interpreter teardown and cause SIGABRT.
    These handlers only request shutdown and remain installed until worker,
    publishers and ROS context have all closed, in that order.
    """
    # A Python signal handler only needs an atomic boolean store. Avoid
    # acquiring an Event's non-reentrant lock from a repeated signal.
    @dataclass
    class Request:
        value: bool = False

        def is_set(self):
            return self.value

    requested = Request()
    previous = {}

    def request_stop(_signal_number, _frame):
        requested.value = True

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, request_stop)
        yield requested
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


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

        self._bridge = CvBridge()
        self._input_lock = Lock()
        self._stopping = False
        self._depth_messages: deque = deque(maxlen=15)
        self._rgb_message: Any = None
        self._rgb_received_ros_ns: int | None = None
        self._depth_received_ros_ns: dict[int, int] = {}
        self._intrinsics: CameraIntrinsics | None = None
        self._camera_size: tuple[int, int] | None = None
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
        with self._input_lock:
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
            snapshot = InferenceSnapshot(
                message, depth_message, intrinsics, camera_size, sync_error, parameters,
                self._clock_epoch, now_ns,
                getattr(self, "_rgb_received_ros_ns", None),
                getattr(self, "_depth_received_ros_ns", {}).get(self._stamp_nanoseconds(depth_message.header.stamp)),
                time.perf_counter(), self._last_inference_stamp,
            )
            if self._worker.submit(snapshot):
                self._last_inference_stamp = stamp_seconds
                self._last_submit_ros_ns = now_ns

    def _on_inference_error(self, error: Exception) -> None:
        if not getattr(self, "_stopping", False):
            self.get_logger().warning(f"YOLO inference failed: {error}")

    def _infer_snapshot(self, snapshot: InferenceSnapshot) -> None:
        with self._input_lock:
            if getattr(self, "_stopping", False):
                return
            worker_started_ros_ns = self._clock_now_locked()
            if not self._snapshot_current_locked(snapshot, worker_started_ros_ns):
                return
        message, depth_message = snapshot.rgb, snapshot.depth
        stamp_seconds = self._stamp_seconds(message.header.stamp)
        parameters = snapshot.parameters
        started = time.perf_counter()
        image = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        depth = np.asarray(self._bridge.imgmsg_to_cv2(depth_message, desired_encoding="passthrough"))
        if image.shape[:2] != depth.shape[:2] or snapshot.camera_size != (message.width, message.height):
            raise ValueError("RGB, aligned depth and CameraInfo dimensions must match")
        result = self._model.predict(
            image, imgsz=int(parameters["inference_image_size"]),
            device=str(parameters["inference_device"]), verbose=False,
        )[0]
        class_id = int(parameters["class_id"])
        class_name = str(parameters["class_name"])
        threshold = float(parameters["confidence_threshold"])
        with self._input_lock:
            if getattr(self, "_stopping", False):
                return
            if not self._snapshot_current_locked(snapshot, self._clock_now_locked()):
                return
            tracking_active, activation_stamp_s = self._tracking_active, self._activation_stamp_s
        # Other classes can occlude this target or contaminate ground samples.
        # Keep their image boxes without creating tracking candidates for them.
        visible_boxes = []
        for candidate_id, box in enumerate(result.boxes):
            score = float(box.conf[0])
            detected_class = int(box.cls[0])
            if score < threshold:
                continue
            bounds = tuple(float(value) for value in box.xyxy[0].tolist())
            if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds) or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                continue
            visible_boxes.append((candidate_id, score, detected_class, bounds))
        detections, observations = [], []
        for candidate_id, score, detected_class, (x1, y1, x2, y2) in visible_boxes:
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
            if getattr(self, "_navigation_enabled", False):
                overlap = any(other_id != candidate_id and bbox_iou((x1, y1, x2, y2), other_box) > 0
                              for other_id, _, _, other_box in visible_boxes)
                observation.navigation_bbox_complete = bool(
                    x1 > 2 and y1 > 2 and x2 < message.width - 2 and y2 < message.height - 2 and not overlap)
                # A partial long side can resemble a complete end face.
                # Known overlap cannot be repaired by removing its pixels or
                # choosing the nearer depth cluster of an unknown individual.
                points = sample_depth_points(
                    depth, snapshot.intrinsics, (x1, y1, x2, y2), stride=2,
                    depth_scale=float(parameters["depth_scale"]), max_points=500,
                    min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]),
                ) if observation.navigation_bbox_complete else np.empty((0, 3))
                observation.navigation_points_camera_m = points.reshape(-1).astype(float).tolist()
                ray = pinhole_backproject(((x1 + x2) / 2, y2), 1.0, snapshot.intrinsics)
                observation.navigation_bottom_ray_camera.x = float(ray[0])
                observation.navigation_bottom_ray_camera.y = float(ray[1])
                observation.navigation_bottom_ray_camera.z = float(ray[2])
            observations.append(observation)
            detections.append({
                "confidence": score,
                "bbox": [x1, y1, x2, y2],
                "depth_valid": bool(observation.depth_valid),
                "depth_m": float(observation.depth_m),
                "depth_valid_ratio": float(stats.valid_fraction),
                "navigation_bbox_complete": bool(getattr(observation, "navigation_bbox_complete", False)),
            })
        ground_points = np.empty((0, 3))
        if getattr(self, "_navigation_enabled", False):
            ground_points = sample_depth_points(
                depth, snapshot.intrinsics, exclude_bboxes=[item[3] for item in visible_boxes],
                stride=8, depth_scale=float(parameters["depth_scale"]), max_points=1200,
                min_depth_m=float(parameters["min_depth_m"]), max_depth_m=float(parameters["max_depth_m"]),
            )
        with self._input_lock:
            if getattr(self, "_stopping", False):
                return
            now_ns = self._clock_now_locked()
            if not self._snapshot_current_locked(snapshot, now_ns):
                return
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
                    frame_publisher.publish(frame)
                for observation in observations:
                    self._publisher.publish(observation)
            diagnostics = String()
            diagnostics.data = json.dumps({
                "stamp_s": stamp_seconds,
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
                "detections": detections,
            })
            self._diagnostics_pub.publish(diagnostics)

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
