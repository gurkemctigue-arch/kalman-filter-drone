"""Confidence tiers across real detector, selection and monitor entry points.

These use small fake images/model outputs; no ROS installation or inference
model is required. Core association/identity policies have separate tests.
"""
from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import yaml

from tests import test_car_surface_adapter as surface_fixture
from tests import test_estimator_timing as estimator_fixture
from tests import test_simulation_seed as seed_fixture
from uav_tracking_nodes import state_estimator_node as estimator


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "confidence_tier_flight_monitor", ROOT / "scripts/stage1_flight_monitor.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class DetectorConfidenceTierAdapterTests(unittest.TestCase):
    make_node = surface_fixture.CarSurfaceAdapterTests.make_node
    set_time = staticmethod(surface_fixture.CarSurfaceAdapterTests.set_time)
    configure_fake_inference = staticmethod(surface_fixture.CarSurfaceAdapterTests.configure_fake_inference)
    car_node = surface_fixture.CarSurfaceAdapterTests.car_node
    ros_stubs = surface_fixture.CarSurfaceAdapterTests.ros_stubs
    infer = surface_fixture.CarSurfaceAdapterTests.infer

    def run_candidates(self, floor):
        boxes = [surface_fixture.box(score=.24), surface_fixture.box(score=.25),
                 surface_fixture.box(score=.40), surface_fixture.box(score=.45),
                 surface_fixture.box(class_id=0, score=.40),
                 surface_fixture.box(class_id=0, score=.45)]
        node, warnings, diagnostics, observations, frames = self.car_node(boxes, enabled=False)
        if floor is not None:
            node._maintenance_confidence_threshold = floor
        calls = []
        node._model.predict = lambda *args, **kwargs: (
            calls.append(kwargs) or [NS(boxes=boxes)])
        with self.ros_stubs():
            self.infer(node)
        self.assertEqual(warnings, [])
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].observations, observations)
        return diagnostics[0], observations, calls

    def test_enabled_retains_weak_same_class_and_keeps_other_class_high_floor(self):
        diagnostic, observations, calls = self.run_candidates(.25)
        self.assertEqual(calls[0]["conf"], .25)
        self.assertEqual([o.candidate_id for o in observations], [1, 2, 3])
        self.assertEqual([o.confidence for o in observations], [.25, .40, .45])
        self.assertTrue(all(o.depth_valid for o in observations))
        self.assertEqual([d["maintenance_only"] for d in diagnostic["detections"]],
                         [True, True, False])
        self.assertEqual(diagnostic["initialization_confidence_threshold"], .45)
        self.assertEqual(diagnostic["maintenance_confidence_threshold"], .25)
        visible = diagnostic["surface_recovery"]["visible_boxes"]
        self.assertEqual([(d["candidate_id"], d["class_id"]) for d in visible],
                         [(1, 2), (2, 2), (3, 2), (5, 0)])

    def test_disabled_keeps_old_prediction_options_and_high_confidence_only(self):
        diagnostic, observations, calls = self.run_candidates(None)
        self.assertNotIn("conf", calls[0])
        self.assertEqual([o.candidate_id for o in observations], [3])
        self.assertEqual([d["maintenance_only"] for d in diagnostic["detections"]], [False])
        visible = diagnostic["surface_recovery"]["visible_boxes"]
        self.assertEqual([d["candidate_id"] for d in visible], [3, 5])

    def test_prediction_floor_below_ultralytics_default_is_explicit(self):
        _, observations, calls = self.run_candidates(.10)
        self.assertEqual(calls[0]["conf"], .10)
        self.assertEqual([o.candidate_id for o in observations], [0, 1, 2, 3])


class EstimatorConfidenceSelectionTests(unittest.TestCase):
    @staticmethod
    def selection():
        return NS(class_name="car", center_u_px=5., center_v_px=5., width_px=10., height_px=10.)

    @staticmethod
    def observation(confidence, *, bounds=(0., 0., 10., 10.), class_name="car"):
        return NS(confidence=confidence, class_name=class_name,
                  bbox_x_min_px=bounds[0], bbox_y_min_px=bounds[1],
                  bbox_x_max_px=bounds[2], bbox_y_max_px=bounds[3])

    def test_weak_only_selection_is_rejected_without_changing_default_api(self):
        observation = self.observation(.40)
        select = estimator.StateEstimatorNode._selection_index
        self.assertEqual(select(self.selection(), [observation]), 0)
        self.assertIsNone(select(self.selection(), [observation], .45))

    def test_weaker_better_overlap_cannot_steal_explicit_selection(self):
        observations = [self.observation(.40), self.observation(.45, bounds=(1., 0., 11., 10.))]
        select = estimator.StateEstimatorNode._selection_index
        self.assertEqual(select(self.selection(), observations), 0)
        self.assertEqual(select(self.selection(), observations, .45), 1)

    def test_high_confidence_ties_wrong_class_and_nonfinite_score_remain_rejected(self):
        select = estimator.StateEstimatorNode._selection_index
        self.assertIsNone(select(self.selection(), [self.observation(.8), self.observation(.9)], .45))
        for observation in [self.observation(.8, class_name="person"), self.observation(float("nan"))]:
            with self.subTest(observation=observation):
                self.assertIsNone(select(self.selection(), [observation], .45))

    def test_processing_forwards_manager_floor_and_original_filtered_index(self):
        node = estimator.StateEstimatorNode.__new__(estimator.StateEstimatorNode)
        node._manager = NS(target_class="car", initialization_confidence_threshold=.45,
                           lock_detection=Mock(), update_with_result=Mock(return_value="result"))
        selection = self.selection()
        selection.target_uuid = "explicit-task"
        node._pending_selection = selection
        node._acquisition_epochs = lambda observations: [0] * len(observations)
        node._transform = lambda observation: None
        node._expire_elapsed_target = Mock()
        node._publish = Mock()
        weak, high = [estimator_fixture.observation(1., x) for x in (0., 1.)]
        for observation, confidence in ((weak, .4), (high, .8)):
            observation.class_name, observation.confidence = "car", confidence

        node._process_observations([weak], 1.)
        node._manager.lock_detection.assert_not_called()
        self.assertIs(node._pending_selection, selection)
        node._process_observations([weak, high], 1.1)
        node._manager.lock_detection.assert_called_once_with(1, target_uuid="explicit-task")
        self.assertIsNone(node._pending_selection)
        detections = node._manager.update_with_result.call_args.args[0]
        self.assertEqual([d.confidence for d in detections], [.4, .8])
        node._publish.assert_called_with("result", weak)


class MonitorConfidenceSelectionTests(unittest.TestCase):
    @staticmethod
    def candidate(x, *, weak=False, valid=True):
        return {"bbox": [x, 0., x + 10., 10.], "confidence": .30 if weak else .8,
                "maintenance_only": weak, "depth_valid": valid}

    def test_inserting_weak_box_cannot_shift_middle_or_extreme_selection(self):
        left, middle, right = [self.candidate(x) for x in (10., 30., 50.)]
        detections = [self.candidate(0., weak=True), left, middle, right]
        self.assertEqual(monitor.visual_initialization_candidates(detections), [left, middle, right])
        for rule, expected in [("leftmost", left), ("middle", middle), ("rightmost", right)]:
            with self.subTest(rule=rule):
                self.assertIs(monitor.select_visual_box(detections, rule), expected)

    def test_unique_selection_pool_keeps_legacy_boxes_and_excludes_bad_depth(self):
        high = self.candidate(20.)
        high.pop("maintenance_only")  # Old detector logs have no flag.
        detections = [high, self.candidate(0., weak=True), self.candidate(40., valid=False),
                      {"depth_valid": True, "bbox": [1, 2, 3]}]
        self.assertIs(monitor.select_visual_box(detections, "none"), high)
        self.assertIsNone(monitor.select_visual_box([self.candidate(0., weak=True)], "middle"))

    def monitor_node(self, detections, *, reselection=False):
        node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        node.args = NS(initial_select="middle", initial_min_candidates=3,
                       occlusions=reselection, reselect_after_loss=reselection)
        node.now_s = lambda: 33.
        node.start_sim, node.end_sim = 0., None
        node.initial_selection_uuid = "old-task" if reselection else None
        node.reselection_uuid = None
        node.phase = "HOLD"
        node.follow_start = 0. if reselection else None
        node.diagnostics = {"stamp_s": 33., "tracking_active": True, "detections": detections}
        node.target = NS(state=4) if reselection else None
        node.status = NS(lifecycle=5) if reselection else None
        node.odom = None
        node.counts = Counter()
        node.run_shutter_schedule = Mock()
        node.publish_visual_selection = Mock(return_value="new-task")
        node.event = Mock()
        return node

    def test_initial_minimum_uses_high_valid_candidates_and_not_weak_count(self):
        detections = [self.candidate(10.), self.candidate(30.), self.candidate(50., weak=True)]
        node = self.monitor_node(detections)
        node.tick()
        node.publish_visual_selection.assert_not_called()
        self.assertIsNone(node.initial_selection_uuid)
        detections.append(self.candidate(70.))
        node.tick()
        node.publish_visual_selection.assert_called_once_with(detections[1], "TEST_SCRIPT_INITIAL_SELECTION")
        self.assertEqual(node.initial_selection_uuid, "new-task")

    def test_explicit_reselection_uses_same_high_pool_and_never_weak_box(self):
        weak = self.candidate(0., weak=True)
        node = self.monitor_node([weak], reselection=True)
        with patch.object(monitor, "TargetState", NS(STATE_LOST=4), create=True), \
                patch.object(monitor, "TrackingStatus", NS(LIFECYCLE_HOVER=5), create=True):
            node.tick()
            node.publish_visual_selection.assert_not_called()
            high = self.candidate(20.)
            node.diagnostics["detections"] += [high]
            node.tick()
        node.publish_visual_selection.assert_called_once_with(high, "TEST_SCRIPT_EXPLICIT_RESELECTION")
        self.assertEqual(node.reselection_uuid, "new-task")


class ConfidenceTierConfigurationTests(unittest.TestCase):
    run_registered_seed = seed_fixture.SeedRunnerTests.run_registered_seed

    def assert_car_thresholds(self, parameters):
        detector = parameters["uav_tracking_detection"]["ros__parameters"]
        state = parameters["uav_tracking_state_estimator"]["ros__parameters"]
        self.assertEqual(detector["confidence_threshold"], .45)
        self.assertEqual(detector["maintenance_confidence_threshold"], .25)
        self.assertEqual(state["initialization_confidence_threshold"], detector["confidence_threshold"])
        self.assertEqual(state["maintenance_confidence_threshold"], detector["maintenance_confidence_threshold"])
        self.assertEqual(state["max_observation_age_s"], .60)
        self.assertEqual(state["max_prediction_duration_s"], .75)

    def test_all_three_car_configs_agree_while_person_keeps_disabled_default(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                config_dir = ROOT / "ros2_ws/src/uav_tracking_bringup/config"
                car = yaml.safe_load((config_dir / f"stage{stage}_tracking_car.yaml").read_text(encoding="utf-8"))
                self.assert_car_thresholds(car)
                person = yaml.safe_load((config_dir / f"stage{stage}_tracking_person.yaml").read_text(encoding="utf-8"))
                for name in ("uav_tracking_detection", "uav_tracking_state_estimator"):
                    self.assertEqual(person[name]["ros__parameters"].get("maintenance_confidence_threshold", -1.), -1.)
                self.assertEqual(person["uav_tracking_state_estimator"]["ros__parameters"].get(
                    "initialization_confidence_threshold", -1.), -1.)

    def test_actual_runner_archive_retains_confidence_policy_in_launched_runtime_yaml(self):
        # Reuse the orchestration fixture; processes are mocked and no simulator
        # runs. Read the runtime artifact before the fixture's temporary cleanup.
        read_text = Path.read_text
        snapshots = []

        def capture(path, *args, **kwargs):
            text = read_text(path, *args, **kwargs)
            if path.name == "runtime_parameters.yaml":
                snapshots.append(yaml.safe_load(text))
            return text

        with patch.object(Path, "read_text", capture):
            self.run_registered_seed(0, 1, target_class="car", recovery=True)
        self.assertEqual(len(snapshots), 1)
        self.assert_car_thresholds(snapshots[0])


if __name__ == "__main__":
    unittest.main()
