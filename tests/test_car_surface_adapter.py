"""Exercise optional car-surface recovery through the real detector adapters.

Geometry is stubbed here; its independent point-set tests live separately.
These regressions cover acquisition provenance, atomic raw fallbacks and the
corrected point's measured vehicle-pose covariance without ROS or YOLO.
"""
from __future__ import annotations

from collections import deque
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import ast
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))

from tests import test_detector_worker as worker_fixture
from tests import test_estimator_timing as estimator_fixture
from uav_tracking.core import ConstantVelocityKalman3D, TargetManager
from uav_tracking.core import car_surface_measurement as surface
from uav_tracking_nodes import detector_node as detector
from uav_tracking_nodes import state_estimator_node as estimator


class FakeTransformException(Exception):
    pass


class FakeTime:
    @staticmethod
    def from_msg(stamp):
        return NS(nanoseconds=stamp.sec * 1_000_000_000 + stamp.nanosec)


class FakeDuration:
    def __init__(self, *, seconds):
        self.seconds = seconds


def image_ns(nanoseconds):
    message = worker_fixture.image(0.)
    message.header.stamp = NS(sec=nanoseconds // 1_000_000_000,
                              nanosec=nanoseconds % 1_000_000_000)
    return message


def box(class_id=2, score=.9, bounds=(0., 0., 4., 4.)):
    return NS(conf=[score], cls=[class_id], xyxy=[np.asarray(bounds)])


def supported(position=(.5, -.25, 7.5)):
    return {
        "status": "SUPPORTED_SURFACE_MEASUREMENT", "reason": "supported_test_component",
        "evidence": {"component_counts": [1577], "scope": "SURFACE_ONLY_NOT_IDENTITY"},
        "measurement": {
            "position_camera_m": list(position),
            "reference_kind": "visible_surface_proxy_component_centroid",
            "measurement_kind": "DERIVED_POINT_SET_CENTROID", "component_support_count": 1577,
            "covariance_camera_m2": None, "covariance_status": "not_calibrated",
        },
    }


def unknown():
    return {"status": "UNKNOWN", "reason": "multiple_supported_components",
            "evidence": {"component_counts": [100, 200]}, "measurement": None}


class FakeSurfaceFrame:
    def __init__(self, assessments):
        self.assessments, self.calls = assessments, []

    @property
    def diagnostics(self):
        return {"ground_fit_calls": 1, "cached_assessments": len(self.calls)}

    def assess(self, index, *, class_name):
        self.calls.append((index, class_name))
        return deepcopy(self.assessments[index])


class CarSurfaceAdapterTests(unittest.TestCase):
    # Reuse the same nonqueuing worker, clock and fake model as the existing
    # scheduling regressions without inheriting/re-running their test methods.
    make_node = worker_fixture.DetectorSchedulingTests.make_node
    set_time = staticmethod(worker_fixture.DetectorSchedulingTests.set_time)
    configure_fake_inference = staticmethod(worker_fixture.DetectorSchedulingTests.configure_fake_inference)

    def car_node(self, boxes, *, enabled=True):
        node, warnings = self.make_node()
        original_parameter = node.get_parameter
        overrides = {"class_id": 2, "class_name": "car"}
        node.get_parameter = lambda name: NS(value=overrides[name]) if name in overrides else original_parameter(name)
        node._navigation_enabled = False
        node._surface_settings = {
            "car_surface_recovery_enabled": enabled,
            "car_surface_recovery_method": "component_centroid_v1",
            "surface_geometry_frame": "map", "surface_tf_timeout_s": .02,
            "surface_max_image_pixels": 307200, "surface_max_roi_pixels": 307200,
            "surface_max_visible_boxes": 64,
            "image_topic": "/test/rgb", "depth_topic": "/test/depth",
            "camera_info_topic": "/test/camera_info",
        }
        node._on_camera_info(NS(k=[100., 0., 2., 0., 100., 2., 0., 0., 1.],
                                width=4, height=4, header=image_ns(0).header))
        diagnostics, observations = self.configure_fake_inference(
            node, lambda *_args, **_kwargs: [NS(boxes=boxes)])
        frames = []
        node._frame_publisher = NS(publish=frames.append)
        return node, warnings, diagnostics, observations, frames

    @contextmanager
    def ros_stubs(self):
        tf_module = ModuleType("tf2_ros")
        tf_module.TransformException = FakeTransformException
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"tf2_ros": tf_module}))
            stack.enter_context(patch.object(detector, "Time", FakeTime, create=True))
            stack.enter_context(patch.object(detector, "Duration", FakeDuration, create=True))
            stack.enter_context(patch.object(detector, "String", lambda: NS(data=""), create=True))
            stack.enter_context(patch.object(detector, "TargetObservation", lambda: NS(
                position_camera_m=NS(x=0., y=0., z=0.), navigation_bottom_ray_camera=NS()), create=True))
            stack.enter_context(patch.object(detector, "TargetObservationArray", NS, create=True))
            yield

    @staticmethod
    def historical_tf(node, *, angle=.3, fail=False):
        calls = []

        def lookup(target, source, query, *, timeout):
            calls.append((target, source, query.nanoseconds, timeout.seconds))
            if fail:
                raise FakeTransformException("historical transform unavailable")
            # An accidental latest/zero-time lookup gives a different roll.
            roll = angle if query.nanoseconds else -1.1
            return NS(header=NS(stamp=image_ns(query.nanoseconds).header.stamp, frame_id=target),
                      child_frame_id=source, transform=NS(rotation=NS(
                          x=math.sin(roll / 2), y=0., z=0., w=math.cos(roll / 2))))

        node._surface_tf_buffer = NS(lookup_transform=lookup)
        return calls

    def infer(self, node, *, rgb_ns=1_000_000_000, depth_ns=None):
        depth_ns = rgb_ns if depth_ns is None else depth_ns
        self.set_time(node, max(rgb_ns, depth_ns) / 1e9 + .02)
        node._on_rgb(image_ns(rgb_ns))
        node._on_depth(image_ns(depth_ns))
        node._process_latest()
        self.assertTrue(node._worker.wait_idle(2), "inference worker did not finish")

    def test_historical_tf_query_uses_exact_integer_rgb_stamp_and_inverse_frame_direction(self):
        node, warnings, diagnostics, observations, frames = self.car_node([box()])
        calls = self.historical_tf(node, angle=.3)
        context = FakeSurfaceFrame({0: supported()})
        stamp = 1_000_000_123
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame", return_value=context) as prepare:
            self.infer(node, rgb_ns=stamp)
        self.assertEqual(warnings, [])
        self.assertEqual(calls, [("camera_link", "map", stamp, .02)])
        np.testing.assert_allclose(prepare.call_args.kwargs["up_camera"],
                                   [0., -math.sin(.3), math.cos(.3)], atol=1e-15)
        tf = diagnostics[0]["surface_recovery"]["tf"]
        self.assertEqual((tf["query_stamp_ns"], tf["returned_stamp_ns"]), (stamp, stamp))
        self.assertEqual(tf["lookup_policy"], "EXACT_ACQUISITION_NO_LATEST_FALLBACK")
        self.assertEqual(frames[0].header.stamp.nanosec, 123)
        self.assertEqual(observations[0].header, frames[0].header)

    def test_navigation_off_one_nanosecond_depth_mismatch_keeps_atomic_raw_frame(self):
        node, warnings, diagnostics, observations, frames = self.car_node([box()])
        calls = self.historical_tf(node)
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame") as prepare:
            self.infer(node, depth_ns=1_000_000_001)
        self.assertEqual(warnings, [])
        self.assertEqual(calls, [])
        prepare.assert_not_called()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].observations, observations)
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].depth_valid)
        self.assertEqual(vars(observations[0].position_camera_m), {"x": 0., "y": 0., "z": 5.})
        report = diagnostics[0]["surface_recovery"]
        self.assertEqual(report["reason"], "RGB_DEPTH_INTEGER_STAMP_MISMATCH")
        self.assertEqual(report["depth_stamp_ns"] - report["rgb_stamp_ns"], 1)
        self.assertEqual(diagnostics[0]["detections"][0]["surface_recovery"]["action"], "RAW_FALLBACK")
        self.assertTrue(observations[0].surface_recovery_enabled)
        self.assertFalse(observations[0].surface_measurement_supported)

    def test_mixed_candidates_keep_raw_fields_ids_order_and_all_class_geometry_inputs(self):
        boxes = [box(score=.1), box(bounds=(0., 0., 3., 4.)),
                 box(class_id=0, bounds=(1., 0., 3., 4.)), box(score=.1),
                 box(bounds=(1., 0., 4., 4.))]
        node, warnings, diagnostics, observations, frames = self.car_node(boxes)
        self.historical_tf(node)
        context = FakeSurfaceFrame({0: supported(), 2: unknown()})
        baseline, raw_warnings, _, raw_observations, _ = self.car_node(boxes, enabled=False)
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame", return_value=context) as prepare:
            self.infer(node)
            self.infer(baseline)
        self.assertEqual(warnings + raw_warnings, [])
        self.assertEqual(context.calls, [(0, "car"), (2, "car")])
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(prepare.call_args.args[2], [tuple(b.xyxy[0]) for b in (boxes[1], boxes[2], boxes[4])])
        self.assertEqual([o.candidate_id for o in observations], [1, 4])
        self.assertEqual(frames[0].observations, observations)
        for actual, raw in zip(observations, raw_observations):
            actual_fields, raw_fields = deepcopy(vars(actual)), deepcopy(vars(raw))
            actual_fields.pop("position_camera_m")
            raw_fields.pop("position_camera_m")
            for name in ("surface_recovery_enabled", "surface_measurement_supported"):
                actual_fields.pop(name)
                raw_fields.pop(name)
            self.assertEqual(actual_fields, raw_fields)
        self.assertEqual([(o.surface_recovery_enabled, o.surface_measurement_supported) for o in observations],
                         [(True, True), (True, False)])
        self.assertEqual([(o.surface_recovery_enabled, o.surface_measurement_supported) for o in raw_observations],
                         [(False, False), (False, False)])
        self.assertEqual(vars(observations[0].position_camera_m), {"x": .5, "y": -.25, "z": 7.5})
        self.assertEqual(vars(observations[1].position_camera_m), vars(raw_observations[1].position_camera_m))
        self.assertEqual(observations[0].depth_m, 5., "raw scalar depth is not the centroid's optical Z")
        self.assertEqual(observations[0].depth_std_m, 0.)
        report = diagnostics[0]
        provenance = report["surface_recovery"]
        self.assertEqual([b["candidate_id"] for b in provenance["visible_boxes"]], [1, 2, 4])
        self.assertEqual(provenance["geometry"]["cached_assessments"], 2)
        self.assertEqual(provenance["source_key"], [0, 1_000_000_000])
        self.assertEqual(provenance["camera_info_source"]["calibration_scope"], "STATIC_CALIBRATION_CACHED_CAMERA_INFO")
        self.assertEqual(provenance["covariance_status"], "EXISTING_RAW_ROI_HEURISTIC_NOT_CENTROID_CALIBRATED")
        self.assertFalse(provenance["identity_assessed"])
        self.assertFalse(provenance["pending_implemented"])
        details = [d["surface_recovery"] for d in report["detections"]]
        self.assertEqual([d["action"] for d in details], ["USE_COMPONENT_CENTROID", "RAW_FALLBACK"])
        self.assertEqual(details[0]["measurement"]["component_support_count"], 1577)
        self.assertEqual(details[1]["status"], "UNKNOWN")
        self.assertEqual(details[1]["reason"], "multiple_supported_components")
        encoded = json.dumps(report, allow_nan=False)
        self.assertLess(len(encoded), 16_000)
        self.assertNotIn("component_point_set", encoded)

    def test_missing_historical_tf_preserves_all_raw_candidates_and_reports_failure(self):
        node, warnings, diagnostics, observations, frames = self.car_node([
            box(bounds=(0., 0., 3., 4.)), box(bounds=(1., 0., 4., 4.))])
        calls = self.historical_tf(node, fail=True)
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame") as prepare:
            self.infer(node)
        self.assertEqual(warnings, [])
        self.assertEqual(len(calls), 1)
        prepare.assert_not_called()
        self.assertEqual(len(frames), 1)
        self.assertEqual([o.candidate_id for o in observations], [0, 1])
        np.testing.assert_allclose([[o.position_camera_m.x, o.position_camera_m.y, o.position_camera_m.z]
                                    for o in observations], [[-.025, 0., 5.], [.025, 0., 5.]])
        report = diagnostics[0]["surface_recovery"]
        self.assertEqual(report["status"], "RAW_FALLBACK")
        self.assertEqual(report["reason"], "GEOMETRY_OR_TF_UNAVAILABLE")
        self.assertIn("same-acquisition TF unavailable", report["error"])
        self.assertTrue(all(d["surface_recovery"]["action"] == "RAW_FALLBACK"
                            for d in diagnostics[0]["detections"]))

    def test_supported_geometry_cannot_turn_invalid_raw_depth_into_a_valid_observation(self):
        node, warnings, diagnostics, observations, frames = self.car_node([box()])
        self.historical_tf(node)
        node._bridge = NS(imgmsg_to_cv2=lambda _message, desired_encoding:
                          np.zeros((4, 4, 3), dtype=np.uint8) if desired_encoding == "bgr8"
                          else np.zeros((4, 4), dtype=np.float32))
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame",
                                           return_value=FakeSurfaceFrame({0: supported()})):
            self.infer(node)
        self.assertEqual(warnings, [])
        self.assertEqual(len(frames), 1)
        self.assertFalse(observations[0].depth_valid)
        self.assertEqual(vars(observations[0].position_camera_m), {"x": 0., "y": 0., "z": 0.})
        detail = diagnostics[0]["detections"][0]["surface_recovery"]
        self.assertEqual((detail["status"], detail["reason"], detail["action"]),
                         ("UNKNOWN", "RAW_DEPTH_INVALID", "RAW_FALLBACK"))
        self.assertTrue(observations[0].surface_recovery_enabled)
        self.assertFalse(observations[0].surface_measurement_supported)

    def test_surface_support_crosses_ros_boundary_per_acquisition_without_cached_success(self):
        node, warnings, _, observations, frames = self.car_node([box()])
        self.historical_tf(node)
        node._clock_epoch = 4
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame", side_effect=[
                FakeSurfaceFrame({0: supported(position=(0., 0., 5.))}),
                FakeSurfaceFrame({0: unknown()}),
        ]):
            self.infer(node)
            node._clock_epoch = 9
            self.infer(node, rgb_ns=1_300_000_000)
        self.assertEqual(warnings, [])
        self.assertEqual(len(frames), 2)
        self.assertEqual([(o.surface_recovery_enabled, o.surface_measurement_supported) for o in observations],
                         [(True, True), (True, False)])
        self.assertEqual([f.header.stamp.sec + f.header.stamp.nanosec * 1e-9 for f in frames], [1., 1.3])
        self.assertEqual([o.acquisition_epoch for o in observations], [4, 9])

        estimator_fixture.EstimatorAdapterTimingTests.setUp(self)
        measured = self.node
        measured._manager = TargetManager(target_class="car", min_hits=1)
        measured._navigation_enabled = False
        for frame, received, expected, epoch in zip(frames, (1.05, 1.35), (True, False), (4, 9)):
            self.time = received
            measured._on_observation_frame(frame)
            current = measured._manager.target.last_detection
            self.assertEqual(current.timestamp, received - .05)
            self.assertIs(current.metadata["surface_recovery_enabled"], True)
            self.assertIs(current.metadata["surface_measurement_supported"], expected)
            self.assertEqual(current.metadata["acquisition_epoch"], epoch)
            np.testing.assert_array_equal(current.position_3d, [0., 0., 5.])

        # An old/default message cannot reuse the previous frame's opt-in.
        legacy = deepcopy(frames[-1])
        legacy.header = image_ns(1_600_000_000).header
        for observation in legacy.observations:
            observation.header = legacy.header
            del observation.surface_recovery_enabled
            del observation.surface_measurement_supported
            del observation.acquisition_epoch
        self.time = 1.65
        measured._on_observation_frame(legacy)
        current = measured._manager.target.last_detection
        self.assertEqual(current.timestamp, 1.6)
        self.assertIs(current.metadata["surface_recovery_enabled"], False)
        self.assertIs(current.metadata["surface_measurement_supported"], False)
        self.assertEqual(current.metadata["acquisition_epoch"], 0)
        self.assertEqual(self.warnings, [])

    def test_estimator_default_or_inconsistent_support_never_becomes_positive_evidence(self):
        estimator_fixture.EstimatorAdapterTimingTests.setUp(self)
        self.node._navigation_enabled = False
        for index, (enabled, supported_flag, depth_valid) in enumerate([
                (False, True, True), (True, True, False), (True, False, True),
                ("true", True, True), (True, "true", True),
        ], 1):
            with self.subTest(enabled=enabled, support=supported_flag, depth=depth_valid):
                item = estimator_fixture.observation(index * .1)
                item.surface_recovery_enabled = enabled
                item.surface_measurement_supported = supported_flag
                item.depth_valid = depth_valid
                # Capture the real adapter conversion without asking a
                # tracker to retain a depth-invalid candidate as its target.
                converted = []
                self.node._manager.update_with_result = lambda detections, **_: converted.extend(detections)
                self.node._publish = lambda *_args, **_kwargs: None
                self.node._expire_elapsed_target = lambda: None
                self.node._process_observations([item], index * .1)
                self.assertEqual(len(converted), 1)
                self.assertIs(converted[0].metadata["surface_measurement_supported"], False)
                self.assertIs(converted[0].metadata["surface_recovery_enabled"], enabled is True)

    def test_invalid_acquisition_epoch_cannot_reach_transform_selection_or_manager(self):
        estimator_fixture.EstimatorAdapterTimingTests.setUp(self)
        for epoch in (False, True, -1, 2**64, 1.0, "1", None):
            with self.subTest(epoch=epoch):
                item = estimator_fixture.observation(.1)
                item.acquisition_epoch = epoch
                self.node._pending_selection = NS()
                with patch.object(self.node, "_transform") as transform, \
                        patch.object(self.node._manager, "lock_detection") as select, \
                        patch.object(self.node._manager, "update_with_result") as update:
                    with self.assertRaisesRegex(ValueError, "acquisition_epoch"):
                        self.node._process_observations([item], .1)
                transform.assert_not_called()
                select.assert_not_called()
                update.assert_not_called()

    def test_mixed_acquisition_epochs_drop_atomic_frame_before_advancing_state(self):
        estimator_fixture.EstimatorAdapterTimingTests.setUp(self)
        first = estimator_fixture.observation(.1)
        second = estimator_fixture.observation(.1, x=20.)
        first.acquisition_epoch, second.acquisition_epoch = 4, 9
        message = NS(header=first.header, observations=[first, second])
        self.time = .15
        with patch.object(self.node, "_transform") as transform, \
                patch.object(self.node._manager, "update_with_result") as update:
            self.node._on_observation_frame(message)
            with self.assertRaisesRegex(ValueError, "mixed acquisition epochs"):
                self.node._process_observations(message.observations, .1)
        transform.assert_not_called()
        update.assert_not_called()
        self.assertIsNone(self.node._last_source)
        self.assertIsNone(self.node._last_observation_timestamp)
        self.assertEqual(len(self.warnings), 1)
        self.assertIn("mixed acquisition epochs", self.warnings[0])

    def test_declared_birth_policy_default_and_override_reach_manager_constructor(self):
        # Execute the production ROS class unchanged against a small parameter
        # transport so the declaration and constructor wiring are both tested.
        tree = ast.parse(Path(estimator.__file__).read_text(encoding="utf-8"))
        production_class = next(item for item in tree.body
                                if isinstance(item, ast.ClassDef) and item.name == "StateEstimatorNode")
        for override in (None, True):
            with self.subTest(override=override):
                class ParameterNode:
                    def __init__(self, _name):
                        self.parameters = {} if override is None else {
                            "supported_birth_confirmation_required": override}

                    def declare_parameter(self, name, default):
                        self.parameters.setdefault(name, default)

                    def get_parameter(self, name):
                        return NS(value=self.parameters[name])

                    def create_publisher(self, *_args):
                        return NS()

                    def create_subscription(self, *_args):
                        return NS()

                    def create_timer(self, *_args):
                        return NS()

                manager = Mock(return_value=NS())
                namespace = {**vars(estimator), "Node": ParameterNode, "TargetManager": manager,
                             "Buffer": lambda: NS(), "TransformListener": lambda *_args: NS()}
                namespace.update({name: NS for name in
                                  ("TargetObservation", "TargetObservationArray", "TargetSelection", "TargetState", "String")})
                exec(compile(ast.Module(body=[production_class], type_ignores=[]), estimator.__file__, "exec"), namespace)
                node = namespace["StateEstimatorNode"]()
                expected = False if override is None else override
                self.assertIs(node.parameters["supported_birth_confirmation_required"], expected)
                self.assertIs(manager.call_args.kwargs["supported_birth_confirmation_required"], expected)

    def test_detector_centroid_reaches_estimator_with_one_full_cross_term_pose_contribution(self):
        node, warnings, _, observations, frames = self.car_node([box()])
        self.historical_tf(node)
        with self.ros_stubs(), patch.object(surface, "prepare_car_surface_frame",
                                           return_value=FakeSurfaceFrame({0: supported()})):
            self.infer(node)
        self.assertEqual(warnings, [])
        camera_point = np.array([.5, -.25, 7.5])
        np.testing.assert_array_equal(camera_point, list(vars(observations[0].position_camera_m).values()))

        # Reuse real estimator acquisition, publication and manager wiring;
        # stub only the ROS transform transport. Its pose helper is not mocked.
        estimator_fixture.EstimatorAdapterTimingTests.setUp(self)
        measured = self.node
        measured._manager = TargetManager(target_class="car", min_hits=1,
            estimator_method="adaptive_kf", kf_kwargs={"measurement_noise_std": [.05, .08, .1]})
        measured._propagate_vehicle_uncertainty = True
        measured._navigation_enabled = False
        angle = .4
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0.],
                             [math.sin(angle), math.cos(angle), 0.], [0., 0., 1.]])
        translation, body = np.array([3., 2., 4.]), np.array([.3, -.4, 2.])
        factor = np.array([[1., .1, .2, .3, .1, -.1], [0., 1.2, .2, -.2, .4, .1],
                           [.2, -.1, 1.3, .1, .2, .3], [.3, .2, -.1, 1., .1, .2],
                           [.1, .4, .2, .2, 1.1, -.1], [-.2, .1, .3, -.1, .2, 1.4]])
        pose_covariance = factor @ factor.T * .001
        self.assertGreater(np.linalg.norm(pose_covariance[:3, 3:]), 0.)
        measured._pose_samples = deque([(1., body, pose_covariance)], maxlen=400)
        transform_calls = []

        def lookup(target, source, query, *, timeout):
            transform_calls.append((target, source, query.nanoseconds))
            return NS(header=NS(stamp=image_ns(query.nanoseconds).header.stamp, frame_id=target),
                      child_frame_id=source, transform=NS(rotation=NS(
                          x=0., y=0., z=math.sin(angle / 2), w=math.cos(angle / 2))))

        def transform_point(point, _transform):
            incoming = np.array([point.point.x, point.point.y, point.point.z])
            np.testing.assert_array_equal(incoming, camera_point)
            result = rotation @ incoming + translation
            return NS(point=NS(x=result[0], y=result[1], z=result[2]))

        measured._tf_buffer = NS(lookup_transform=lookup)
        measured._transform = estimator.StateEstimatorNode._transform.__get__(measured)
        expected_world = rotation @ camera_point + translation
        lever = expected_world - body
        cross = np.array([[0., -lever[2], lever[1]], [lever[2], 0., -lever[0]],
                          [-lever[1], lever[0], 0.]])
        jacobian = np.concatenate((np.eye(3), -cross), axis=1)
        expected_pose_R = jacobian @ pose_covariance @ jacobian.T
        expected_pose_R = (expected_pose_R + expected_pose_R.T) / 2
        # Compare with the inherited raw-quality heuristic, which receives
        # unchanged confidence/std/fraction, independently of the pose helper.
        reference_filter = ConstantVelocityKalman3D(measurement_noise_std=[.05, .08, .1])
        base_R = reference_filter.measurement_covariance(confidence=.9,
                    depth_stats={"valid_fraction": 1., "std": 0.})
        expected_total_R = base_R + expected_pose_R
        raw_world = rotation @ np.array([0., 0., 5.]) + translation
        raw_lever = raw_world - body
        raw_cross = np.array([[0., -raw_lever[2], raw_lever[1]], [raw_lever[2], 0., -raw_lever[0]],
                              [-raw_lever[1], raw_lever[0], 0.]])
        raw_J = np.concatenate((np.eye(3), -raw_cross), axis=1)
        self.assertFalse(np.allclose(expected_pose_R, raw_J @ pose_covariance @ raw_J.T))
        with ExitStack() as stack:
            for name, value in {"PointStamped": lambda: NS(header=NS(), point=NS()),
                                "Time": FakeTime, "Duration": FakeDuration,
                                "TransformException": FakeTransformException,
                                "do_transform_point": transform_point}.items():
                stack.enter_context(patch.object(estimator, name, value, create=True))
            self.time = 1.05
            measured._on_observation_frame(frames[0])
            track = measured._manager.target
            np.testing.assert_allclose(track.last_detection.position_3d, expected_world)
            np.testing.assert_allclose(track.last_detection.metadata["additional_measurement_covariance"],
                                       expected_pose_R, rtol=1e-12, atol=1e-14)
            np.testing.assert_allclose(track.covariance_3d, expected_total_R, rtol=1e-12, atol=1e-14)
            # A second actual fusion also receives exactly this R, not a
            # second pose term or the raw point's outdated attitude lever.
            frame = deepcopy(frames[0])
            frame.header.stamp = image_ns(1_100_000_000).header.stamp
            for observation in frame.observations:
                observation.header.stamp = frame.header.stamp
            measured._pose_samples.append((1.1, body, pose_covariance))
            self.time = 1.15
            measured._on_observation_frame(frame)
            self.assertEqual(len(measured._manager.tracks), 1)
            np.testing.assert_allclose(track._filter.last_measurement_covariance,
                                       expected_total_R, rtol=1e-12, atol=1e-14)
            self.assertEqual(track.last_measurement_timestamp, 1.1)
        self.assertEqual(transform_calls, [("map", "camera_link", 1_000_000_000),
                                           ("map", "camera_link", 1_100_000_000)])
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
