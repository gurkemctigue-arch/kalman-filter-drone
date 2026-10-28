"""ROS 2 adapter for the portable target manager and 3-D Kalman filter."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
import json
from typing import Any

import numpy as np

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import PointStamped
    from nav_msgs.msg import Odometry
    from rclpy.duration import Duration
    from rclpy.node import Node
    from rclpy.time import Time
    from std_msgs.msg import String
    from tf2_geometry_msgs import do_transform_point
    from tf2_ros import Buffer, TransformException, TransformListener
    from uav_tracking_interfaces.msg import TargetObservation, TargetObservationArray, TargetSelection, TargetState
except ImportError:  # pragma: no cover
    rclpy = None
    Node = object  # type: ignore[misc,assignment]

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus
from uav_tracking.core.models import TrackState
from uav_tracking.core.uncertainty import pose_point_covariance
from uav_tracking.core.navigation import NavigationEstimate, NavigationPrior, fit_ground_plane, estimate_footprint_from_points
from uav_tracking.control.gimbal_geometry import quaternion_rotation
from .stage2_telemetry import track_snapshot


class StateEstimatorNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_state_estimator")
        self.declare_parameter("target_mode", "auto_unique")
        self.declare_parameter("target_class", "person")
        self.declare_parameter("estimator_method", "adaptive_kf")
        self.declare_parameter("ema_alpha", 0.35)
        self.declare_parameter("state_frame", "map")
        self.declare_parameter("observation_topic", "/tracking/observations")
        self.declare_parameter("observation_frame_topic", "/tracking/observation_frames")
        self.declare_parameter("selection_topic", "/tracking/selection")
        self.declare_parameter("state_topic", "/tracking/state")
        self.declare_parameter("tracks_topic", "/tracking/tracks")
        self.declare_parameter("association_mode", "legacy")
        self.declare_parameter("association_iou_threshold", 0.01)
        self.declare_parameter("association_max_distance_m", 2.0)
        self.declare_parameter("reject_ambiguous_associations", False)
        self.declare_parameter("buffer_delay_s", 0.02)
        self.declare_parameter("min_depth_valid_ratio", 0.35)
        self.declare_parameter("max_prediction_duration_s", 0.75)
        self.declare_parameter("track_retention_duration_s", 3.0)
        self.declare_parameter("max_observation_age_s", 0.60)
        self.declare_parameter("process_noise_accel_mps2", 1.0)
        self.declare_parameter("measurement_noise_position_m", [0.05, 0.05, 0.10])
        self.declare_parameter("mahalanobis_gate", 11.344866730144373)
        self.declare_parameter("default_dt", 1.0 / 30.0)
        self.declare_parameter("max_coast_frames", 8)
        self.declare_parameter("max_lost_frames", 30)
        self.declare_parameter("navigation_enabled", False)
        self.declare_parameter("navigation_state_topic", "/tracking/navigation_state")
        self.declare_parameter("navigation_diagnostics_topic", "/tracking/navigation_diagnostics")
        # Explicit family priors, in length/width/height order. They describe
        # a pedestrian / passenger car family, not a simulator mesh lookup.
        self.declare_parameter("navigation_dimensions_m", [0.5, 0.5, 1.7])
        self.declare_parameter("navigation_dimension_std_m", [0.1, 0.1, 0.2])
        self.declare_parameter("navigation_pose_std_m", 0.05)
        self.declare_parameter("propagate_vehicle_uncertainty", False)
        self.declare_parameter("vehicle_odom_topic", "/vehicle/odometry")
        self._propagate_vehicle_uncertainty = bool(self.get_parameter("propagate_vehicle_uncertainty").value)
        self._pose_samples: deque = deque(maxlen=400)
        if self._propagate_vehicle_uncertainty:
            self.create_subscription(Odometry, str(self.get_parameter("vehicle_odom_topic").value), self._on_pose_uncertainty, 20)
        self._navigation_enabled = bool(self.get_parameter("navigation_enabled").value)
        if self._navigation_enabled:
            from .navigation_estimator import NavigationEstimator
            pose_std = float(self.get_parameter("navigation_pose_std_m").value)
            if not np.isfinite(pose_std) or pose_std < 0:
                raise ValueError("navigation_pose_std_m must be finite and nonnegative")
            dimensions = self.get_parameter("navigation_dimensions_m").value
            self._navigation_prior = NavigationPrior(
                str(self.get_parameter("target_class").value), *dimensions,
                dimension_std_m=self.get_parameter("navigation_dimension_std_m").value,
                prior_id="declared_family_dimensions_v4",
            )
            self._navigation_estimator = NavigationEstimator(
                gate_threshold=float(self.get_parameter("mahalanobis_gate").value),
                process_acceleration_std=float(self.get_parameter("process_noise_accel_mps2").value),
            )
            self._navigation_publisher = self.create_publisher(
                TargetState, str(self.get_parameter("navigation_state_topic").value), 20)
            self._navigation_diagnostics_publisher = self.create_publisher(
                String, str(self.get_parameter("navigation_diagnostics_topic").value), 20)
            self._navigation_last_diagnostics: dict[str, Any] = {}
            self._navigation_transform_key = None
            self._navigation_transform = None

        self._target_mode = TargetMode(str(self.get_parameter("target_mode").value).lower())
        self._manager = TargetManager(
            mode=self._target_mode,
            target_class=str(self.get_parameter("target_class").value),
            estimator_method=str(self.get_parameter("estimator_method").value),
            ema_alpha=float(self.get_parameter("ema_alpha").value),
            min_hits=1,
            max_coast_frames=int(self.get_parameter("max_coast_frames").value),
            max_lost_frames=int(self.get_parameter("max_lost_frames").value),
            max_coast_duration_s=float(self.get_parameter("max_prediction_duration_s").value),
            track_retention_duration_s=float(self.get_parameter("track_retention_duration_s").value),
            gate_threshold=float(self.get_parameter("mahalanobis_gate").value),
            association_mode=str(self.get_parameter("association_mode").value),
            association_iou_threshold=float(self.get_parameter("association_iou_threshold").value),
            association_max_distance=float(self.get_parameter("association_max_distance_m").value),
            reject_ambiguous_associations=bool(self.get_parameter("reject_ambiguous_associations").value),
            kf_kwargs={
                "process_acceleration_std": float(self.get_parameter("process_noise_accel_mps2").value),
                "measurement_noise_std": self.get_parameter("measurement_noise_position_m").value,
                "default_dt": float(self.get_parameter("default_dt").value),
            },
        )
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._pending: dict[tuple[int, int], list[TargetObservation]] = defaultdict(list)
        self._pending_first_received: dict[tuple[int, int], float] = {}
        self._selected_track_id: int | None = None
        self._pending_selection: TargetSelection | None = None
        self._last_source: TargetObservation | None = None
        # Only committed camera frames advance this watermark. Output-rate
        # projections must not cause normally delayed images to look old.
        self._last_observation_timestamp: float | None = None
        self._publisher = self.create_publisher(TargetState, str(self.get_parameter("state_topic").value), 20)
        self._tracks_publisher = self.create_publisher(String, str(self.get_parameter("tracks_topic").value), 20)
        frame_topic = str(self.get_parameter("observation_frame_topic").value)
        if frame_topic:
            # The detector closes each acquisition as one array, including
            # empty frames. No batching timer can expire the target while a
            # complete, fresh measurement is already waiting for its siblings.
            self.create_subscription(TargetObservationArray, frame_topic, self._on_observation_frame, 20)
        else:
            # Explicit compatibility path for older controlled smoke sources.
            self.create_subscription(TargetObservation, str(self.get_parameter("observation_topic").value), self._on_observation, 50)
        self.create_subscription(TargetSelection, str(self.get_parameter("selection_topic").value), self._on_selection, 10)
        self.create_timer(float(self.get_parameter("buffer_delay_s").value), self._flush)

    @staticmethod
    def _stamp_key(stamp: Any) -> tuple[int, int]:
        return int(stamp.sec), int(stamp.nanosec)

    @staticmethod
    def _stamp_seconds(stamp: Any) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def _on_pose_uncertainty(self, message: Any) -> None:
        if (message.header.frame_id != str(self.get_parameter("state_frame").value)
                or getattr(message, "child_frame_id", None) != "base_link"):
            return
        timestamp = self._stamp_seconds(message.header.stamp)
        point = message.pose.pose.position
        if self._pose_samples and timestamp < self._pose_samples[-1][0]:
            self._pose_samples.clear()
        self._pose_samples.append((timestamp, np.array([point.x, point.y, point.z]),
                                   np.asarray(message.pose.covariance, dtype=float).reshape(6, 6)))

    def _point_pose_covariance(self, point_world: Any, timestamp: float) -> np.ndarray:
        if not self._pose_samples:
            raise ValueError("vehicle_pose_uncertainty_unavailable")
        sample = min(self._pose_samples, key=lambda value: abs(value[0] - timestamp))
        if abs(sample[0] - timestamp) > .05:
            raise ValueError("vehicle_pose_uncertainty_not_synchronized")
        return pose_point_covariance(point_world, sample[1], sample[2])

    def _on_observation(self, message: TargetObservation) -> None:
        key = self._stamp_key(message.header.stamp)
        self._pending[key].append(message)
        self._pending_first_received.setdefault(key, self.get_clock().now().nanoseconds * 1e-9)

    def _on_observation_frame(self, message: Any) -> None:
        """Commit one complete acquisition immediately, even with zero boxes."""
        if any(self._stamp_key(item.header.stamp) != self._stamp_key(message.header.stamp)
               for item in message.observations):
            self.get_logger().warning("Dropping observation array with mixed acquisition stamps")
            return
        if any(item.header.frame_id != message.header.frame_id
               or (item.camera_frame and item.camera_frame != message.header.frame_id)
               for item in message.observations):
            self.get_logger().warning("Dropping observation array with mixed camera frames")
            return
        self._commit_observations(list(message.observations), message)

    def _commit_observations(self, observations: list[TargetObservation], source: Any) -> bool:
        timestamp = self._stamp_seconds(source.header.stamp)
        now = self.get_clock().now().nanoseconds * 1e-9
        if self._last_observation_timestamp is not None and timestamp <= self._last_observation_timestamp:
            self.get_logger().warning(f"Dropping out-of-order observation frame at {timestamp:.6f}")
            return False
        max_age = float(self.get_parameter("max_observation_age_s").value)
        if now > timestamp and now - timestamp > max_age:
            self.get_logger().warning(f"Dropping stale observation frame (age {now - timestamp:.3f}s)")
            return False
        if timestamp > now:
            self.get_logger().warning(f"Dropping future observation frame at {timestamp:.6f}")
            return False
        self._last_source = source
        self._process_observations(observations, timestamp, source=source)
        self._last_observation_timestamp = timestamp
        return True

    def _on_selection(self, message: TargetSelection) -> None:
        if message.action == TargetSelection.ACTION_CLEAR or message.action == TargetSelection.ACTION_RESET:
            self._manager.unlock_target()
            self._selected_track_id = None
            self._pending_selection = None
            return
        if message.action != TargetSelection.ACTION_SELECT:
            return
        if message.track_id:
            self._manager.lock_target(int(message.track_id), target_uuid=message.target_uuid or None)
            self._selected_track_id = int(message.track_id)
            self._pending_selection = None
        else:
            # A UI/test script normally knows the initial box but not the
            # tracker's private ID.  Keep the box until a synchronized frame
            # contains a matching candidate, then lock that detection before
            # TargetManager creates/updates tracks.
            self._pending_selection = message

    @staticmethod
    def _selection_index(selection: TargetSelection, observations: list[TargetObservation]) -> int | None:
        """Return the unique observation overlapping an initial selection box."""

        if selection.width_px <= 0.0 or selection.height_px <= 0.0:
            return None
        sx1 = float(selection.center_u_px - selection.width_px / 2.0)
        sy1 = float(selection.center_v_px - selection.height_px / 2.0)
        sx2 = float(selection.center_u_px + selection.width_px / 2.0)
        sy2 = float(selection.center_v_px + selection.height_px / 2.0)
        scored: list[tuple[float, int]] = []
        for index, observation in enumerate(observations):
            if selection.class_name and observation.class_name != selection.class_name:
                continue
            ix1 = max(sx1, float(observation.bbox_x_min_px))
            iy1 = max(sy1, float(observation.bbox_y_min_px))
            ix2 = min(sx2, float(observation.bbox_x_max_px))
            iy2 = min(sy2, float(observation.bbox_y_max_px))
            intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
            union = selection.width_px * selection.height_px + max(
                0.0,
                float(observation.bbox_x_max_px - observation.bbox_x_min_px),
            ) * max(0.0, float(observation.bbox_y_max_px - observation.bbox_y_min_px)) - intersection
            iou = intersection / union if union > 1e-9 else 0.0
            scored.append((iou, index))
        if not scored:
            return None
        scored.sort(reverse=True)
        # Require actual overlap and reject a tie, so a malformed selection
        # can never silently choose one of several same-class candidates.
        if scored[0][0] <= 0.05 or (len(scored) > 1 and scored[0][0] - scored[1][0] < 1e-6):
            return None
        return scored[0][1]

    def _transform(self, observation: TargetObservation) -> np.ndarray | None:
        if (
            not observation.depth_valid
            or observation.depth_valid_ratio < float(self.get_parameter("min_depth_valid_ratio").value)
        ):
            return None
        point = PointStamped()
        point.header = observation.header
        point.header.frame_id = observation.camera_frame or observation.header.frame_id
        point.point = observation.position_camera_m
        try:
            # tf2_ros expects an rclpy.time.Time (with a nanoseconds
            # property), while the message header carries a
            # builtin_interfaces/Time.  Passing the latter directly raises
            # at runtime on ROS 2 even though both print as a timestamp.
            query_time = Time.from_msg(point.header.stamp)
            transform = self._tf_buffer.lookup_transform(
                str(self.get_parameter("state_frame").value),
                point.header.frame_id,
                query_time,
                timeout=Duration(seconds=float(self.get_parameter("buffer_delay_s").value)),
            )
            transformed = do_transform_point(point, transform)
            if getattr(self, "_navigation_enabled", False):
                rotation = transform.transform.rotation
                translation = transform.transform.translation
                matrix = np.eye(4)
                matrix[:3, :3] = quaternion_rotation((rotation.x, rotation.y, rotation.z, rotation.w))
                matrix[:3, 3] = [translation.x, translation.y, translation.z]
                self._navigation_transform_key = (self._stamp_key(point.header.stamp), point.header.frame_id)
                self._navigation_transform = matrix
        except (TransformException, TypeError, ValueError) as exc:
            self.get_logger().warning(f"TF lookup failed: {exc}", throttle_duration_sec=2.0)
            return None
        return np.array([transformed.point.x, transformed.point.y, transformed.point.z], dtype=float)

    def _flush(self) -> None:
        now = self.get_clock().now().nanoseconds * 1e-9
        processed = False
        while self._pending:
            key = sorted(self._pending)[0]
            # A detector publishes several candidates with one acquisition
            # stamp. Allow one batching interval after first receipt so a
            # timer callback cannot turn the first candidate into AUTO_UNIQUE
            # before the remaining candidates have been delivered.
            if now - self._pending_first_received[key] < float(self.get_parameter("buffer_delay_s").value):
                break
            observations = self._pending.pop(key)
            self._pending_first_received.pop(key, None)
            processed = self._commit_observations(observations, observations[0]) or processed
        if processed or self._last_source is None:
            return
        if self._last_observation_timestamp is not None and now < self._last_observation_timestamp:
            return
        result = self._manager.predict_with_result(now)
        self._publish(result, self._last_source, publish_stamp=self.get_clock().now().to_msg())

    def _process_observations(self, observations: list[TargetObservation], timestamp: float, source: Any = None) -> None:
        source = source if source is not None else observations[0]
        observations = [
            observation for observation in observations
            if self._manager.target_class is None or observation.class_name == self._manager.target_class
        ]
        if self._pending_selection is not None:
            selection_index = self._selection_index(self._pending_selection, observations)
            if selection_index is not None:
                self._manager.lock_detection(
                    selection_index,
                    target_uuid=self._pending_selection.target_uuid or None,
                )
                self._pending_selection = None
        detections: list[Detection] = []
        for observation in observations:
            position = self._transform(observation)
            metadata = {"candidate_id": int(observation.candidate_id)}
            if position is not None and getattr(self, "_propagate_vehicle_uncertainty", False):
                try:
                    metadata["additional_measurement_covariance"] = self._point_pose_covariance(position, timestamp).tolist()
                except ValueError as error:
                    self.get_logger().warning(f"Skipping uncertain world measurement: {error}", throttle_duration_sec=2.0)
                    position = None
            detections.append(
                Detection(
                    bbox=(observation.bbox_x_min_px, observation.bbox_y_min_px, observation.bbox_x_max_px, observation.bbox_y_max_px),
                    class_id=observation.class_name,
                    confidence=observation.confidence,
                    timestamp=timestamp,
                    position_3d=None if position is None else tuple(position),
                    depth_stats={
                        "valid_fraction": float(observation.depth_valid_ratio),
                        "std": float(observation.depth_std_m),
                    },
                    metadata=metadata,
                )
            )
        result = self._manager.update_with_result(detections, timestamp=timestamp)
        if getattr(self, "_navigation_enabled", False):
            self._update_navigation(result, observations, source, timestamp)
        self._publish(result, source)

    def _navigation_reference(self, result: Any, observations: list[Any], source: Any, timestamp: float) -> tuple[Any, dict[str, Any]]:
        """Use only the accepted selected candidate; preserve surface identity."""
        target = result.target
        uuid = str(self._manager.target_uuid or "")
        track_id = int(target.track_id) if target is not None else 0
        reference = NavigationEstimate(reason="no_accepted_selected_measurement")
        details: dict[str, Any] = {"acquisition_s": timestamp, "target_uuid": uuid, "track_id": track_id}
        if (target is not None and target._matched_this_frame and target.last_detection is not None
                and target.last_measurement_timestamp == timestamp
                and result.status not in {TargetStatus.LOST, TargetStatus.AMBIGUOUS}):
            candidate_id = target.last_detection.metadata.get("candidate_id")
            observation = next((item for item in observations if int(item.candidate_id) == candidate_id), None)
            if observation is not None:
                key = (self._stamp_key(source.header.stamp), observation.camera_frame or observation.header.frame_id)
                ground = np.asarray(getattr(source, "navigation_ground_points_camera_m", []), dtype=float)
                points = np.asarray(getattr(observation, "navigation_points_camera_m", []), dtype=float)
                matrix = self._navigation_transform
                if source.header.frame_id != (observation.camera_frame or observation.header.frame_id):
                    reference = NavigationEstimate(reason="mixed_navigation_camera_frames")
                elif key != self._navigation_transform_key or matrix is None:
                    reference = NavigationEstimate(reason="missing_same_stamp_camera_transform")
                elif not getattr(observation, "navigation_bbox_complete", False):
                    reference = NavigationEstimate(reason="incomplete_or_occluded_detection_box")
                elif ground.size < 120 or ground.size % 3 or points.size < 36 or points.size % 3:
                    reference = NavigationEstimate(reason="insufficient_same_stamp_depth_support")
                else:
                    rotation, camera = matrix[:3, :3], matrix[:3, 3]
                    ground_world = ground.reshape(-1, 3) @ rotation.T + camera
                    object_world = points.reshape(-1, 3) @ rotation.T + camera
                    plane = fit_ground_plane(ground_world)
                    details.update(ground_valid=plane.valid, ground_reason=plane.reason,
                                   ground_inliers=plane.inlier_count, ground_samples=plane.sample_count,
                                   ground_residual_std_m=plane.residual_std_m)
                    if plane.valid:
                        ray = observation.navigation_bottom_ray_camera
                        reference = estimate_footprint_from_points(
                            object_world, ground_plane=plane, camera_position_world=camera,
                            prior=self._navigation_prior,
                            bottom_ray_world=rotation @ np.array([ray.x, ray.y, ray.z]),
                            velocity_world=target.velocity_3d,
                        )
                        if reference.valid:
                            # Reject extrapolation from a distant ground patch.
                            inliers = ground_world[np.abs(ground_world @ plane.normal + plane.offset) <= .08]
                            nearest = float(np.min(np.linalg.norm(inliers[:, :2] - reference.position_world_m[:2], axis=1))) if len(inliers) else float("inf")
                            details["nearest_ground_support_m"] = nearest if np.isfinite(nearest) else None
                            if nearest > 3.0:
                                reference = NavigationEstimate(reason="ground_support_too_distant")
                            else:
                                pose_std = float(self.get_parameter("navigation_pose_std_m").value)
                                if not np.isfinite(pose_std) or pose_std < 0:
                                    raise ValueError("navigation_pose_std_m must be finite and nonnegative")
                                reference = NavigationEstimate(
                                    position_world_m=reference.position_world_m,
                                    covariance=reference.covariance + (
                                        self._point_pose_covariance(reference.position_world_m, timestamp)
                                        if getattr(self, "_propagate_vehicle_uncertainty", False)
                                        else np.eye(3) * pose_std**2),
                                    valid=True, reason=reference.reason, reference_kind=reference.reference_kind,
                                    support_count=reference.support_count, heading_source=reference.heading_source,
                                    diagnostics=reference.diagnostics,
                                )
                    else:
                        reference = NavigationEstimate(reason="ground_plane_" + plane.reason)
        return reference, details

    def _update_navigation(self, result: Any, observations: list[Any], source: Any, timestamp: float) -> None:
        target = result.target
        uuid = str(self._manager.target_uuid or "")
        track_id = int(target.track_id) if target is not None else 0
        try:
            reference, details = self._navigation_reference(result, observations, source, timestamp)
        except (TypeError, ValueError, OverflowError, np.linalg.LinAlgError) as error:
            # Malformed optional geometry must stop following, not terminate
            # the RGB-D identity estimator or Offboard heartbeat chain.
            reference = NavigationEstimate(reason="invalid_navigation_geometry:" + str(error))
            details = {"acquisition_s": timestamp, "target_uuid": uuid, "track_id": track_id}
        update = self._navigation_estimator.update(
            reference, timestamp=timestamp, target_uuid=uuid, track_id=track_id,
            initial_velocity=target.velocity_3d if target is not None else None,
        )
        details.update(reference_valid=reference.valid, reference_reason=reference.reason,
                       reference_kind=reference.reference_kind, support_count=reference.support_count,
                       heading_source=reference.heading_source,
                       raw_position_world_m=None if reference.position_world_m is None else reference.position_world_m.tolist(),
                       reference_covariance=None if reference.covariance is None else reference.covariance.tolist(),
                       geometry=reference.diagnostics, fusion=update.diagnostics,
                       fusion_accepted=update.accepted, fusion_reason=update.reason)
        self._navigation_last_diagnostics = details

    def _publish(self, result: Any, source: TargetObservation, publish_stamp: Any | None = None) -> None:
        message = TargetState()
        # ROS messages are mutable Python objects. Never change the cached
        # image header when stamping a current-time prediction.
        message.header = deepcopy(source.header)
        if publish_stamp is not None:
            message.header.stamp = publish_stamp
        message.header.frame_id = str(self.get_parameter("state_frame").value)
        message.track_id = int(result.target.track_id) if result.target is not None else 0
        # ``target_uuid`` is task identity, independent of the transient
        # tracker ID.  Keep publishing it through a long loss so logs and a
        # re-selection UI can correlate the lifecycle without using Gazebo IDs.
        message.target_uuid = str(self._manager.target_uuid or "")
        message.class_name = str(result.target.class_id) if result.target is not None else ""
        target = result.target
        message.rejected_measurements = int(target.rejected_measurements) if target is not None else 0
        if target is None or target.position_3d is None:
            if result.status == TargetStatus.AMBIGUOUS:
                message.state = TargetState.STATE_AMBIGUOUS
            elif result.status == TargetStatus.LOST:
                message.state = TargetState.STATE_LOST
            else:
                message.state = TargetState.STATE_UNINITIALIZED
            message.target_visible = False
            message.prediction_age_s = 0.0
        else:
            message.position_m.x, message.position_m.y, message.position_m.z = target.position_3d
            velocity = target.velocity_3d or (0.0, 0.0, 0.0)
            message.velocity_mps.x, message.velocity_mps.y, message.velocity_mps.z = velocity
            covariance_6d = np.asarray(
                target.covariance_6d if target.covariance_6d is not None else np.zeros((6, 6)),
                dtype=float,
            ).reshape(6, 6)
            message.covariance = [float(value) for value in covariance_6d.reshape(-1)]
            measurement_timestamp = target.last_measurement_timestamp
            output_stamp = publish_stamp if publish_stamp is not None else source.header.stamp
            age_s = (
                max(0.0, self._stamp_seconds(output_stamp) - float(measurement_timestamp))
                if measurement_timestamp is not None
                else float("inf")
            )
            max_prediction = float(self.get_parameter("max_prediction_duration_s").value)
            has_measurement = bool(
                target._matched_this_frame
                and target.last_detection is not None
                and target.last_detection.position_3d is not None
            )
            is_lost = (
                result.status == TargetStatus.LOST
                or target.state in {TrackState.LOST, TrackState.REMOVED}
                or age_s > max_prediction
            )
            is_ambiguous = result.status == TargetStatus.AMBIGUOUS
            message.target_visible = bool(target._matched_this_frame and not is_lost and not is_ambiguous)
            message.prediction_age_s = float(age_s)
            if is_ambiguous:
                message.state = TargetState.STATE_AMBIGUOUS
            elif is_lost:
                message.state = TargetState.STATE_LOST
            elif has_measurement:
                message.state = TargetState.STATE_MEASURED
            else:
                message.state = TargetState.STATE_PREDICTED
        self._publisher.publish(message)
        if getattr(self, "_navigation_enabled", False):
            self._publish_navigation(message, result)
        tracks_publisher = getattr(self, "_tracks_publisher", None)
        if tracks_publisher is not None:
            telemetry = String()
            telemetry.data = json.dumps(track_snapshot(
                result, target_uuid=self._manager.target_uuid,
                acquisition_s=self._stamp_seconds(source.header.stamp),
                output_s=self._stamp_seconds(message.header.stamp),
                frame_id=message.header.frame_id,
                projected=publish_stamp is not None,
            ), allow_nan=False, separators=(",", ":"))
            tracks_publisher.publish(telemetry)

    def _publish_navigation(self, surface: Any, result: Any) -> None:
        output_s = self._stamp_seconds(surface.header.stamp)
        snapshot = self._navigation_estimator.project(
            output_s, target_uuid=surface.target_uuid, track_id=surface.track_id,
            max_age=float(self.get_parameter("max_prediction_duration_s").value),
            surface_status=result.status.value,
        )
        message = deepcopy(surface)
        if snapshot.valid:
            message.position_m.x, message.position_m.y, message.position_m.z = snapshot.position_world_m
            message.velocity_mps.x, message.velocity_mps.y, message.velocity_mps.z = snapshot.velocity_world_mps
            message.covariance = np.asarray(snapshot.covariance, dtype=float).reshape(-1).tolist()
            message.prediction_age_s = float(snapshot.measurement_age_s)
            # A fresh surface box cannot turn a coasting navigation estimate
            # into a measured navigation state.
            is_measurement = snapshot.measured_timestamp_s == output_s and surface.state == TargetState.STATE_MEASURED
            message.state = TargetState.STATE_MEASURED if is_measurement else TargetState.STATE_PREDICTED
            message.target_visible = bool(is_measurement and surface.target_visible)
        else:
            message.state = (TargetState.STATE_AMBIGUOUS if surface.state == TargetState.STATE_AMBIGUOUS
                             else TargetState.STATE_LOST)
            message.target_visible = False
            message.position_m.x = message.position_m.y = message.position_m.z = 0.0
            message.velocity_mps.x = message.velocity_mps.y = message.velocity_mps.z = 0.0
            message.covariance = [0.0] * 36
            message.prediction_age_s = (float(snapshot.measurement_age_s)
                                        if snapshot.measurement_age_s is not None and np.isfinite(snapshot.measurement_age_s) else 0.0)
        self._navigation_publisher.publish(message)
        diagnostics = String()
        diagnostics.data = json.dumps(dict(
            self._navigation_last_diagnostics, output_s=output_s, valid=snapshot.valid,
            state_reason=snapshot.reason,
            measurement_age_s=(float(snapshot.measurement_age_s)
                               if snapshot.measurement_age_s is not None and np.isfinite(snapshot.measurement_age_s) else None),
        ), allow_nan=False, separators=(",", ":"))
        self._navigation_diagnostics_publisher.publish(diagnostics)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required to run state_estimator_node")
    rclpy.init(args=args)
    node = None
    try:
        node = StateEstimatorNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None:
                node.destroy_node()
        finally:
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
