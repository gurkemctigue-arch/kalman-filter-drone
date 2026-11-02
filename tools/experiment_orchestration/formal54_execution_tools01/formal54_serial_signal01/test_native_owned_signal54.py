"""Linux dummy processes only; root must schedule this separately from builds.

Does not load a real manifest, guard, adapter, ROS, WSL command or simulator.
This file has NOT been executed as part of the Windows author validation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from owned_guard_process54 import LinuxBackend

CHILD = r'''
import json, os, signal, sys, time
from pathlib import Path
root = Path(sys.argv[1])
requested = []
def stop(number, frame):
    requested.append(int(number))
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
(root/'dummy_ready.json').write_text(json.dumps({'pid': os.getpid()}))
while not requested:
    time.sleep(.02)
time.sleep(.35)
(root/'dummy_cleanup.json').write_text(json.dumps({'pid': os.getpid(), 'signals': requested, 'cleanup_complete': True}))
'''

OWNER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from owned_guard_process54 import OwnedGuardRunner, write_new
root = Path(sys.argv[2])
output = root/'batch'
owner = OwnedGuardRunner(output)
with owner:
    output.mkdir()
    owner.attach_batch()
    invocation = output/'0001'
    invocation.mkdir()
    with (invocation/'stdout.log').open('xb') as stdout, (invocation/'stderr.log').open('xb') as stderr:
        import subprocess
        child = owner([sys.executable, '-B', str(root/'dummy_child.py'), str(root)],
                      stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, check=False)
    result = {'status': 'STOPPED_ORIGINAL_RECORDS_RETAINED', 'dummy_only': True, 'returncode': child.returncode}
    owner.annotate(result)
    owner.finish(result)
'''


@unittest.skipUnless(sys.platform.startswith('linux'), 'Native Linux dummy-process signal validation only')
class NativeOwnedSignalTests(unittest.TestCase):
    def exercise_signal(self, number):
        with tempfile.TemporaryDirectory(prefix='formal54_native_dummy_only_') as name:
            root = Path(name)
            (root/'dummy_child.py').write_text(CHILD, encoding='utf-8')
            backend = LinuxBackend()
            with (root/'owner.log').open('wb') as log:
                process = subprocess.Popen([sys.executable, '-B', '-c', OWNER, str(HERE), str(root)],
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                identity = backend.identity(process.pid)
                try:
                    deadline = time.monotonic()+10
                    while not (root/'dummy_ready.json').is_file():
                        self.assertIsNone(process.poll(), (root/'owner.log').read_text(errors='replace'))
                        self.assertLess(time.monotonic(), deadline, 'Dummy adapter did not become ready')
                        time.sleep(.02)
                    observed = backend.identity(process.pid)
                    self.assertEqual(observed['start_token'], identity['start_token'])
                    os.kill(process.pid, number)
                    self.assertEqual(process.wait(timeout=15), 0, (root/'owner.log').read_text(errors='replace'))
                    cleanup = json.loads((root/'dummy_cleanup.json').read_text())
                    self.assertTrue(cleanup['cleanup_complete'])
                    self.assertEqual(cleanup['signals'], [int(number)])
                    terminal = json.loads((root/'batch/0001/owned_process_terminal.json').read_text())
                    self.assertTrue(terminal['wait_completed'])
                    self.assertEqual(terminal['returncode'], 0)
                    self.assertEqual(terminal['child_process']['pid'], cleanup['pid'])
                    self.assertEqual(terminal['child_process']['pgid'], cleanup['pid'])
                    self.assertEqual(terminal['child_process']['session'], cleanup['pid'])
                    self.assertEqual(len(terminal['forwarded_signals']), 1)
                    self.assertFalse(terminal['forwarded_signals'][0]['group_signaled'])
                    state = json.loads((root/'batch/lifecycle_terminal.json').read_text())
                    self.assertEqual(state['state'], 'STOPPED_BY_SIGNAL')
                    self.assertEqual(state['scheduled_slots'], 280)
                    self.assertEqual(state['completed_owned_children'], 1)
                    self.assertIsNone(backend.identity(cleanup['pid']))
                finally:
                    if process.poll() is None:
                        observed = backend.identity(process.pid)
                        if identity and observed and observed['start_token'] == identity['start_token']:
                            os.kill(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            # These are this test's isolated dummy processes only.
                            # No process/group by name, WSL or flight graph is touched.
                            start = root/'batch/0001/owned_process_started.json'
                            if start.is_file():
                                expected = json.loads(start.read_text())['child_process']
                                observed = backend.identity(expected['pid'])
                                if observed and observed['start_token'] == expected['start_token']:
                                    os.kill(expected['pid'], signal.SIGKILL)
                            process.kill()
                            process.wait(timeout=5)

    def test_native_sigint_waits_for_dummy_cleanup(self):
        self.exercise_signal(signal.SIGINT)

    def test_native_sigterm_waits_for_dummy_cleanup(self):
        self.exercise_signal(signal.SIGTERM)


if __name__ == '__main__':
    unittest.main(verbosity=2)
