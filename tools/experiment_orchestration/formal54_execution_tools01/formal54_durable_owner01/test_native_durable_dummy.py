"""NOT RUN by the author. Root must schedule in an exclusive native idle window.

Linux Python dummy workers only. The synthetic request/admission/serial fixture
is explicitly fabricated and never imports a real serial, guard, ROS or model.
The public durable launcher, watch, stop and real detached Popen waits are used.
Do not interpret this fixture's self-declared tool hashes as formal approval.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import formal54_durable_owner as owner
from test_formal54_durable_owner import Fixture

HERE = Path(__file__).resolve().parent
DUMMY = r'''
import argparse, json, os, signal, sys, time
from pathlib import Path
sys.path.insert(0, OWNER_DIRECTORY)
import formal54_durable_owner as owner
p=argparse.ArgumentParser()
p.add_argument('--manifest')
p.add_argument('--output')
p.add_argument('--guard-command',nargs=argparse.REMAINDER)
a=p.parse_args()
out=Path(a.output)
out.mkdir()
requested=[]
def receive(number,frame):requested.append(int(number))
signal.signal(signal.SIGINT,receive)
signal.signal(signal.SIGTERM,receive)
identity=owner.LinuxBackend().identity(os.getpid())
owner.write_new(out/'dummy_ready.json',{'pid':os.getpid(),'synthetic_dummy_only':True})
deadline=time.monotonic()+12.
while not requested and time.monotonic()<deadline:time.sleep(.02)
time.sleep(.35)
owner.write_new(out/'dummy_cleanup.json',{'requests':requested,'synthetic_dummy_only':True,'cleanup_complete':True})
code=0 if requested else 3
owner.write_new(out/'lifecycle_terminal.json',{'schema_version':1,'scope':owner.SERIAL_SCOPE,
    'owner_process':identity,'serial_exit_code':code,'state':'DUMMY_ONLY_CLOSED','synthetic_dummy_only':True})
raise SystemExit(code)
'''.replace('OWNER_DIRECTORY', repr(str(HERE)))


@unittest.skipUnless(sys.platform.startswith('linux'), 'Root-scheduled Linux dummy-only validation')
class NativeDurableDummyTests(unittest.TestCase):
    def exercise(self, number):
        with tempfile.TemporaryDirectory(prefix='formal54_durable_native_dummy_') as directory:
            case = Fixture(directory)
            entry = Path(case.request['serial_entry']['path'])
            entry.write_text(DUMMY, encoding='utf-8')
            case.description['files'][entry.name] = owner.pin(entry)['sha256']
            case.description_path.write_text(json.dumps(case.description), encoding='utf-8')
            case.serial_sha = owner.canonical(case.description)
            case.request.update(serial_entry=owner.pin(entry), serial_description=owner.pin(case.description_path),
                                reviewed_serial_tools_sha256=case.serial_sha)
            case.request_path.write_text(json.dumps(case.request), encoding='utf-8')
            backend = owner.LinuxBackend()
            launched = owner.launch(owner.pin(case.request_path), case.owner, owner.canonical(owner.description()),
                                    case.serial_sha, backend=backend)
            registry_sha = launched['registry']['sha256']
            watch_process = None
            try:
                deadline = time.monotonic()+8
                while not (case.output/'dummy_ready.json').is_file():
                    self.assertLess(time.monotonic(), deadline, 'Dummy did not become ready; inspect owner logs')
                    self.assertFalse((case.owner/'terminal.json').exists(), 'Worker failed before dummy ready')
                    time.sleep(.03)
                started = owner.load(case.owner/'serial_started.json')
                serial = owner.verify(backend, started['serial_process'], started['command'])
                watch_command = [str(Path(sys.executable).resolve()), '-I', '-B', str(HERE/'formal54_durable_owner.py'),
                    'watch', '--owner-directory', str(case.owner), '--registry-sha256', registry_sha, '--interval', '.05']
                with (case.base/'dummy_watch.log').open('wb') as log:
                    watch_process = subprocess.Popen(watch_command, stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, start_new_session=True)
                time.sleep(.25)
                watch_identity = backend.identity(watch_process.pid)
                owner.verify(backend, watch_identity, watch_command)
                backend.send(watch_process.pid, signal.SIGINT)
                self.assertEqual(watch_process.wait(timeout=5), 130)
                owner.verify(backend, serial, started['command'])
                self.assertFalse((case.owner/'terminal.json').exists(), 'Stopping watch must not stop execution')
                report = owner.stop(case.owner, registry_sha, number=number, backend=backend)
                terminal = report['terminal']
                self.assertTrue(terminal['serial_wait_completed'])
                self.assertTrue(terminal['serial_exit_evidence_complete'])
                self.assertEqual(terminal['serial_returncode'], 0)
                self.assertEqual(len(terminal['forwarded_signals']), 1)
                self.assertEqual(terminal['forwarded_signals'][0]['signal'], int(number))
                cleanup = owner.load(case.output/'dummy_cleanup.json')
                self.assertEqual(cleanup['requests'], [int(number)])
                self.assertIsNone(backend.identity(serial['pid']))
            finally:
                if watch_process is not None and watch_process.poll() is None:
                    actual = backend.identity(watch_process.pid)
                    if actual and actual.get('argv') == watch_command:
                        backend.send(watch_process.pid, signal.SIGINT)
                        watch_process.wait(timeout=5)
                if not (case.owner/'terminal.json').exists():
                    owner.stop(case.owner, registry_sha, backend=backend)
                # No SIGKILL fallback. Dummy's 12s self-end is a test fixture,
                # never a production flight or cleanup deadline.
                until = time.monotonic()+3
                while time.monotonic()<until:
                    actual = backend.identity(launched['worker_process']['pid'])
                    if actual is None or actual.get('state') in {'Z','X'}:
                        break
                    time.sleep(.03)

    def test_detached_owner_watch_and_sigint_cleanup(self):
        self.exercise(signal.SIGINT)

    def test_detached_owner_watch_and_sigterm_cleanup(self):
        self.exercise(signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
