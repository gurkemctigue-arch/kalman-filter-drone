"""Small standard-library fixture; no native modules, WSL, subprocess or sim."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location('owned_shutdown', Path(__file__).with_name('owned_rgbd_shutdown.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def message(sec=0, nsec=1, width=640, height=480, data=b'rgbd'):
    return SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=sec,nsec=nsec)),
                           width=width,height=height,data=data)


def fresh_stream():
    return dict(increasing_frames=0,first_source_ns=None,last_source_ns=None,
                last_receive_monotonic_s=None,last_callback_monotonic_s=None,
                nonempty_callbacks=0,invalid=0)


def passing_report():
    names = ('binding_verified','subscriber_ready','paused_start_observed','unpause_ack',
             'rgbd_gate','pause_ack','drain_gate','renderer_verified','gazebo_clean_initial_exit',
             'subscriber_clean_exit','all_owned_cleaned','kernel_evidence_captured')
    return dict({name:True for name in names}, errors=[], signal_events=[])


def clean_stop():
    result = dict(signals=['SIGINT'],residual=[])
    events = [dict(participant='gazebo',signal='SIGINT',scope='owned_process_group',
                   observed_exit=0, observed_monotonic_s=7.9,deadline_monotonic_s=8.)]
    return result,events


class EvidenceSafetyFixture(unittest.TestCase):
    def test_native_subscribe_return_never_substitutes_actual_frames(self):
        for value in (None,False,0):
            receipt=m.subscription_receipt(value)
            self.assertEqual(receipt['value'],value)
            self.assertEqual(receipt['kind'],'NONE' if value is None else 'RETURNED')
            report=passing_report();report['rgbd_gate']=False
            self.assertEqual(m.decision(report)['status'],'FAIL')

    def test_two_nonempty_strictly_increasing_source_stamps_are_required(self):
        item=fresh_stream()
        for stamp in (1,1,0,2):
            m.stream_update(item,message(nsec=stamp),1.)
        self.assertEqual(item['increasing_frames'],2)
        self.assertEqual((item['first_source_ns'],item['last_source_ns']),(1,2))

    def test_invalid_frame_does_not_meet_gate_but_keeps_drain_active(self):
        item=fresh_stream()
        m.stream_update(item,message(data=b''),4.)
        self.assertEqual(item['increasing_frames'],0)
        self.assertEqual(item['invalid'],1)
        self.assertEqual(item['last_callback_monotonic_s'],4.)

    def test_invalid_stamp_is_not_a_frame(self):
        for value in (message(sec=-1),message(nsec=1000000000),message(nsec=-1)):
            item=fresh_stream();m.stream_update(item,value,1.)
            self.assertEqual(item['increasing_frames'],0)

    def test_natural_zero_within_original_initial_window_can_pass(self):
        self.assertTrue(m.clean_initial_exit(*clean_stop()))
        self.assertEqual(m.decision(passing_report())['status'],'PASS')

    def test_late_zero_is_not_clean_initial_exit(self):
        result,events=clean_stop();events[0]['observed_monotonic_s']=8.001
        self.assertFalse(m.clean_initial_exit(result,events))

    def test_timeout_then_zero_is_not_clean_initial_exit(self):
        result,events=clean_stop();events[0]['wait_timeout']=True
        self.assertFalse(m.clean_initial_exit(result,events))

    def test_sigkill_or_nonzero_never_passes(self):
        for code in (-9,-11,1):
            result,events=clean_stop();events[0]['observed_exit']=code
            self.assertFalse(m.clean_initial_exit(result,events))

    def test_force_cleanup_cannot_rehabilitate_zero_exit(self):
        for name in ('SIGTERM','SIGKILL'):
            report=passing_report()
            report['signal_events']=[dict(participant='gazebo',signal=name)]
            self.assertEqual(m.decision(report)['status'],'FAIL')

    def test_missing_any_required_gate_fails(self):
        template=passing_report()
        for key in set(template)-{'errors','signal_events'}:
            report=passing_report();del report[key]
            self.assertEqual(m.decision(report)['status'],'FAIL',key)

    def test_missing_owned_identity_fails_even_after_successful_cleanup(self):
        report=passing_report();report['errors']=['/proc/123/stat: FileNotFoundError']
        self.assertEqual(m.decision(report)['status'],'FAIL')

    def test_optional_kernel_stack_not_observed_does_not_override_complete_exit(self):
        report=passing_report()
        report['optional_diagnostic_gaps']=['/proc/123/task/124/stack: PermissionError']
        self.assertEqual(m.decision(report)['status'],'PASS')

    def test_residual_process_or_leader_only_signal_fails(self):
        result,events=clean_stop();result['residual']=[dict(pid=123)]
        self.assertFalse(m.clean_initial_exit(result,events))
        result,events=clean_stop();events[0]['scope']='owned_leader_only'
        self.assertFalse(m.clean_initial_exit(result,events))

    def test_declared_cpu_environment_does_not_substitute_actual_mappings(self):
        capture=dict(pid=123,members=[dict(identity=dict(pid=123),selected_environment={},mappings=[])])
        issues=m.rendering_issues(capture)
        self.assertIn('Missing actual swrast_dri mapping',issues)
        self.assertIn('Missing actual LLVM mapping',issues)
        self.assertIn('Actual Gazebo selected environment mismatch',issues)


if __name__=='__main__':
    unittest.main(verbosity=2)
