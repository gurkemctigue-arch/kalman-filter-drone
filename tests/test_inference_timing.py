"""Timing attribution and real detector lifecycle without ROS/model loading."""

from contextlib import ExitStack
import json
from threading import Lock
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

from tests import test_detector_worker as worker_tests
from uav_tracking_nodes.inference_timing import InferenceTiming

detector, image = worker_tests.detector, worker_tests.image


class Clocks:
    def __init__(self):
        self.wall_s = self.cpu_s = 0.

    def wall(self):
        return self.wall_s

    def cpu(self):
        return self.cpu_s

    def advance(self, seconds, cpu=None):
        self.wall_s += seconds
        self.cpu_s += seconds / 2 if cpu is None else cpu


class TimingAccountingTests(unittest.TestCase):
    def test_lock_wait_is_exclusive_and_hold_is_inclusive_without_double_counting(self):
        clock = Clocks()
        timing = InferenceTiming(wall_clock=clock.wall, cpu_clock=clock.cpu)
        held = []

        class DelayedLock:
            def acquire(self):
                clock.advance(.4, 0.)
                held.append(True)

            def release(self):
                held.pop()

        with timing.stage("decode"):
            clock.advance(.2)
        with timing.input_lock(DelayedLock(), "publication"):
            with timing.stage("frame_publish"):
                clock.advance(.3)
        report = timing.snapshot(final=True)
        self.assertFalse(held)
        self.assertAlmostEqual(report['stages']['publication_lock_wait']['wall_s'], .4)
        self.assertAlmostEqual(report['input_lock_holds']['publication']['wall_s'], .3)
        self.assertAlmostEqual(report['production_work_before_timing_log_wall_s'], .9)
        self.assertAlmostEqual(sum(v['wall_s'] for v in report['stages'].values()), .9)
        self.assertEqual(report['stages']['publication_lock_wait']['thread_cpu_s'], 0.)

    def test_exception_releases_lock_and_finishes_active_stage_without_mutating_partial(self):
        clock = Clocks()
        timing = InferenceTiming(wall_clock=clock.wall, cpu_clock=clock.cpu)
        lock = Lock()
        timing.begin('depth_navigation_geometry')
        clock.advance(.2)
        prefix = timing.snapshot()
        timing.end()
        with self.assertRaisesRegex(ValueError, 'publisher'):
            with timing.input_lock(lock, 'publication'):
                with timing.stage('frame_publish'):
                    clock.advance(.3)
                    raise ValueError('publisher')
        report = timing.snapshot(final=True)
        self.assertFalse(lock.locked())
        self.assertEqual(prefix['scope'], 'partial_before_diagnostics_encode_and_publish')
        self.assertNotIn('frame_publish', prefix['stages'])
        self.assertAlmostEqual(report['stages']['frame_publish']['wall_s'], .3)
        self.assertAlmostEqual(report['production_work_before_timing_log_wall_s'], .5)


class DetectorTimingTests(unittest.TestCase):
    make_node = worker_tests.DetectorSchedulingTests.make_node

    def prepare(self, *, fail_predict=False):
        node, warnings = self.make_node()
        clock = Clocks()
        outputs = {'frames': [], 'observations': [], 'diagnostics': [], 'predict_calls': 0}
        expected_error = RuntimeError('predict fixture')

        def decode(message, desired_encoding):
            clock.advance(.1)
            return (np.zeros((4, 4, 3), dtype=np.uint8) if desired_encoding == 'bgr8'
                    else np.full((4, 4), 5., dtype=np.float32))

        def predict(*args, **kwargs):
            outputs['predict_calls'] += 1
            clock.advance(.3)
            if fail_predict:
                raise expected_error
            return [NS(boxes=[NS(conf=[.9], cls=[0], xyxy=[np.array([0., 0., 4., 4.])])])]

        def publish_frame(message):
            clock.advance(.4)
            outputs['frames'].append(message)

        def publish_observation(message):
            clock.advance(.25)
            outputs['observations'].append(message)

        def publish_diagnostics(message):
            clock.advance(.5)
            outputs['diagnostics'].append(json.loads(message.data))

        node._bridge = NS(imgmsg_to_cv2=decode)
        node._model = NS(predict=predict)
        node._frame_publisher = NS(publish=publish_frame)
        node._publisher = NS(publish=publish_observation)
        node._diagnostics_pub = NS(publish=publish_diagnostics)
        node._activation_stamp_s = 0.
        parameters = {name:node.get_parameter(name).value for name in (
            'inference_image_size','inference_device','class_id','class_name','confidence_threshold',
            'depth_scale','min_depth_m','max_depth_m','min_depth_valid_ratio')}
        snapshot = detector.InferenceSnapshot(image(1),image(1),node._intrinsics,(4,4),0.,parameters,0,10**9,
            submitted_wall_s=0.,timer_input_lock_wait_wall_s=.02,timer_input_lock_snapshot_hold_wall_s=.003)
        original_stats = detector.depth_roi_stats

        def stats(*args, **kwargs):
            clock.advance(.2)
            return original_stats(*args, **kwargs)

        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(detector, 'InferenceTiming', lambda: InferenceTiming(
            wall_clock=clock.wall,cpu_clock=clock.cpu)))
        patches.enter_context(patch.object(detector.time,'perf_counter',clock.wall))
        patches.enter_context(patch.object(detector,'depth_roi_stats',stats))
        patches.enter_context(patch.object(detector,'String',lambda:NS(data=''),create=True))
        patches.enter_context(patch.object(detector,'TargetObservation',lambda:NS(position_camera_m=NS()),create=True))
        patches.enter_context(patch.object(detector,'TargetObservationArray',NS,create=True))
        return node,snapshot,clock,outputs,expected_error

    def report(self, node):
        self.assertEqual(len(node._test_timing_logs),1)
        prefix = 'INFERENCE_JOB_TIMING '
        self.assertTrue(node._test_timing_logs[0].startswith(prefix))
        return json.loads(node._test_timing_logs[0][len(prefix):])

    def test_success_preserves_publications_and_old_metric_while_final_includes_diagnostics_tail(self):
        node,snapshot,clock,outputs,_ = self.prepare()
        node._infer_snapshot(snapshot)
        report = self.report(node)
        self.assertEqual(outputs['predict_calls'],1)
        self.assertEqual([len(outputs[k]) for k in ('frames','observations','diagnostics')],[1,1,1])
        self.assertEqual(report['status'],'completed')
        self.assertEqual(report['job_key'],[0,10**9])
        self.assertEqual(report['timer_input_lock_wait_wall_s'],.02)
        data = outputs['diagnostics'][0]
        self.assertAlmostEqual(data['inference_wall_s'],1.35)
        self.assertAlmostEqual(report['production_work_before_timing_log_wall_s'],1.85)
        self.assertAlmostEqual(sum(v['wall_s'] for v in report['stages'].values()),1.85)
        self.assertIsNone(data['timing_before_diagnostics']['production_work_before_timing_log_wall_s'])
        self.assertNotIn('diagnostics_publish',data['timing_before_diagnostics']['stages'])
        self.assertAlmostEqual(report['stages']['diagnostics_publish']['wall_s'],.5)
        self.assertFalse(node._input_lock.locked())

    def test_model_exception_logs_once_and_preserves_original_exception(self):
        node,snapshot,clock,outputs,expected = self.prepare(fail_predict=True)
        with self.assertRaises(RuntimeError) as raised:
            node._infer_snapshot(snapshot)
        self.assertIs(raised.exception,expected)
        report = self.report(node)
        self.assertEqual(report['status'],'exception')
        self.assertEqual(report['reason'],'RuntimeError')
        self.assertAlmostEqual(report['stages']['yolo_predict']['wall_s'],.3)
        self.assertEqual(outputs['diagnostics'],[])
        self.assertFalse(node._input_lock.locked())

    def test_early_shutdown_return_is_logged_once_without_publishing(self):
        node,snapshot,clock,outputs,_ = self.prepare()
        node._stopping = True
        node._infer_snapshot(snapshot)
        report = self.report(node)
        self.assertEqual((report['status'],report['reason']),('early_return','stopping_at_entry'))
        self.assertEqual(outputs['predict_calls'],0)
        self.assertEqual(outputs['diagnostics'],[])
        self.assertFalse(node._input_lock.locked())

    def test_timing_logger_error_cannot_replace_original_model_error(self):
        node,snapshot,clock,outputs,expected = self.prepare(fail_predict=True)
        def broken_log(message):
            raise ValueError('logger unavailable')
        node.get_logger = lambda:NS(info=broken_log)
        with self.assertRaises(RuntimeError) as raised:
            node._infer_snapshot(snapshot)
        self.assertIs(raised.exception,expected)


if __name__ == '__main__':
    unittest.main()
