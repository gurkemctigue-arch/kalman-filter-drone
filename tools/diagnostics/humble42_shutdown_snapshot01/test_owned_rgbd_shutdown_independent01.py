"""Independent bounded fake-only checks; no native imports, subprocess or /proc."""
from contextlib import ExitStack
from enum import IntEnum
import ast
import importlib.util
import itertools
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('shutdown_independent_tool', Path(__file__).with_name('owned_rgbd_shutdown.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Signals(IntEnum):
    SIGINT = 2
    SIGTERM = 15
    SIGKILL = 9


def creation(start=10):
    return dict(pid=123, ppid=1, pgid=123, session=123, boot_id='fake-boot', start_ticks=start)


class Participant:
    name, pid = 'gazebo', 123
    def __init__(self, timeouts=0):
        self.creation, self.signals = creation(), []
        self.code, self.timeouts = None, timeouts
    def poll(self):
        return self.code
    def wait(self, duration):
        if self.timeouts:
            self.timeouts -= 1
            raise m.subprocess.TimeoutExpired('fake-only', duration)
        self.code = 0
        return 0


class IndependentChecks(unittest.TestCase):
    def signaling(self, participant, replacement=None):
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        contexts.enter_context(patch.object(m, 'signal', Signals))
        contexts.enter_context(patch.object(m, 'group_members', lambda pid: [replacement or creation()] if participant.poll() is None else []))
        contexts.enter_context(patch.object(m.time, 'monotonic', side_effect=itertools.count(100., .1)))
        kill = contexts.enter_context(patch.object(m.os, 'killpg', create=True))
        contexts.enter_context(patch.object(m, 'JOURNAL', None))
        return kill

    def test_actual_signal_path_keeps_initial_eight_second_deadline(self):
        participant = Participant()
        kill = self.signaling(participant)
        events = []
        result = m.terminate_owned(participant, events, (8., 5., 3.), phase='fake')
        kill.assert_called_once_with(123, Signals.SIGINT)
        self.assertEqual(events[0]['deadline_monotonic_s'] - events[0]['monotonic_s'], 8.)
        self.assertTrue(m.clean_initial_exit(result, events))

    def test_owned_pid_reuse_is_refused_before_any_signal(self):
        participant = Participant()
        kill = self.signaling(participant, creation(999))
        with self.assertRaisesRegex(ValueError, 'creation identity changed'):
            m.terminate_owned(participant, [], (8., 5., 3.), phase='fake')
        kill.assert_not_called()

    def test_timeout_then_term_zero_remains_a_failed_initial_exit(self):
        participant = Participant(timeouts=1)
        kill = self.signaling(participant)
        events = []
        result = m.terminate_owned(participant, events, (8., 5., 3.), phase='fake')
        self.assertEqual(kill.call_count, 2)
        self.assertEqual(result['signals'], ['SIGINT', 'SIGTERM'])
        self.assertTrue(events[0]['wait_timeout'])
        self.assertFalse(m.clean_initial_exit(result, events))

    def test_optional_proc_stack_and_wchan_are_explicit_unknown(self):
        def read(path, limit):
            name = Path(path).name
            if name in ('stack', 'wchan'):
                raise PermissionError('fake kernel restriction')
            if name == 'environ':
                return 'LP_NUM_THREADS=4\0OMP_NUM_THREADS=2\0LIBGL_ALWAYS_SOFTWARE=1\0MESA_LOADER_DRIVER_OVERRIDE=swrast\0GALLIUM_DRIVER=llvmpipe\0'
            if name == 'maps':
                return '/usr/lib/swrast_dri.so\n/usr/lib/libLLVM.so\n'
            return 'synthetic stat/status'
        with patch.object(m, 'group_members', return_value=[creation()]), patch.object(m, 'read_bounded', side_effect=read), patch.object(m.Path, 'iterdir', return_value=iter([Path('/proc/123/task/124')])):
            result = m.snapshot(123)
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['optional_errors']), 4)
        self.assertEqual(result['members'][0]['stack']['status'], 'NOT_OBSERVED')
        self.assertEqual(m.rendering_issues(result), [])

    def test_missing_actual_mappings_remains_required_evidence(self):
        capture = dict(pid=123, members=[dict(identity=creation(), selected_environment=dict(
            LP_NUM_THREADS='4', OMP_NUM_THREADS='2', LIBGL_ALWAYS_SOFTWARE='1',
            MESA_LOADER_DRIVER_OVERRIDE='swrast', GALLIUM_DRIVER='llvmpipe'), mappings=[])])
        self.assertEqual(set(m.rendering_issues(capture)), {'Missing actual swrast_dri mapping', 'Missing actual LLVM mapping'})

    def test_no_native_subscribe_return_assumption_replaces_actual_callbacks(self):
        for returned in (None, False, True):
            with self.subTest(returned=returned):
                sent, calls = [], []
                commands = iter(('snapshot', 'close'))
                connection = SimpleNamespace(send=sent.append, recv=lambda: next(commands), close=lambda: calls.append('closed'))
                image = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nsec=1)), width=3, height=2, data=b'fake pixels')
                descriptor = SimpleNamespace(fields_by_name={name: SimpleNamespace(type=8) for name in ('header', 'width', 'height', 'data', 'pause')}, full_name='fake-only')
                class Image:
                    DESCRIPTOR = descriptor
                    def __new__(cls):
                        return image
                class Node:
                    def subscribe(self, cls, topic, callback):
                        calls.append(('subscribe', topic))
                        callback(image)
                        return returned
                    def unsubscribe(self, topic):
                        calls.append(('unsubscribe', topic))
                    def service_list(self):
                        return []
                modules = {}
                for name in ('gz', 'gz.transport13', 'gz.msgs10', 'gz.msgs10.image_pb2', 'gz.msgs10.world_control_pb2', 'gz.msgs10.boolean_pb2'):
                    modules[name] = ModuleType(name)
                modules['gz.transport13'].Node = Node
                modules['gz.msgs10.image_pb2'].Image = Image
                modules['gz.msgs10.world_control_pb2'].WorldControl = SimpleNamespace(DESCRIPTOR=descriptor)
                modules['gz.msgs10.boolean_pb2'].Boolean = SimpleNamespace(DESCRIPTOR=SimpleNamespace(fields_by_name={'data': SimpleNamespace(type=8)}, full_name='fake-boolean'))
                with patch.dict('sys.modules', modules), patch.object(m.os, 'getpgid', return_value=123, create=True), patch.object(m.os, 'getpid', return_value=123), patch.object(m, 'identity', return_value=creation()), patch.dict(m.os.environ, {}, clear=False):
                    m.subscriber_worker(connection, {'GZ_PARTITION': 'fake-private', 'GZ_IP': '127.0.0.1'}, ['/fake/rgb', '/fake/depth'])
                self.assertEqual(sent[0]['event'], 'ready')
                self.assertEqual(sent[1]['streams']['/fake/rgb']['increasing_frames'], 1)
                self.assertEqual(sent[2]['event'], 'unsubscribed')
                self.assertIn('closed', calls)

    def test_both_tool_and_fixtures_parse_under_python310(self):
        for name in ('owned_rgbd_shutdown.py', 'test_owned_rgbd_shutdown.py', Path(__file__).name):
            ast.parse(Path(__file__).with_name(name).read_text(encoding='utf-8'), feature_version=(3, 10))


if __name__ == '__main__':
    unittest.main(verbosity=2)
