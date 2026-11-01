"""Pure fake-IO boundary tests; never import the component helper or shared code."""
import ast
import hashlib
import io as memory_io
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace
import unittest


SUBJECT = Path(__file__).with_name('root_humble_v2_components04.py')
SUBJECT_SHA = 'ac75708b91a9b336e5b6dadbbe9239143c6a4558df51c775f9aceb028dfb8492'
LOCK = '/tmp/uav_tracking_reliability_v4_sitl.lock'
PROC = '/fake/proc'
MISSING = FileNotFoundError('fake absent')


def extracted_namespace():
    raw = SUBJECT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SUBJECT_SHA:
        raise RuntimeError('Reviewed new helper changed; review the new bytes first')
    source = ast.parse(raw.decode('utf-8'), filename=str(SUBJECT))
    names = {'_ReadOnlyProcIO', 'original_machine_lock_snapshot'}
    nodes = [node for node in source.body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    if {node.name for node in nodes} != names or len(nodes) != 2:
        raise RuntimeError('Exactly the two reviewed definitions must be extracted')
    # The sole file read above is the new helper text. No helper import, main,
    # shared module, real proc, lock file, WSL, subprocess or flight is invoked.
    namespace = {'os': SimpleNamespace(fspath=os.fspath), 'Path': Path,
                 're': re, 'stat_types': stat}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SUBJECT), 'exec'), namespace)
    return namespace


def metadata(inode=30, mode=stat.S_IFREG | 0o600, major=10, minor=31):
    return SimpleNamespace(st_mode=mode, st_dev=0, st_ino=inode,
                           fake_identity=(major, minor, inode))


class FakeIO:
    def __init__(self, states=None, locks='', references=()):
        self.states = list([MISSING, MISSING] if states is None else states)
        self.locks, self.references, self.calls = locks, references, []

    def lstat(self, path):
        self.calls.append(('lstat', path))
        value = self.states.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def identity(self, value):
        return value.fake_identity

    def read_proc_locks(self, root, limit):
        self.calls.append(('locks', root, limit))
        if isinstance(self.locks, BaseException):
            raise self.locks
        return self.locks

    def proc_fd_links(self, root, limits):
        self.calls.append(('fds', root, dict(limits)))
        if isinstance(self.references, BaseException):
            raise self.references
        yield from self.references


def reference(target=LOCK, pid=12, fd='3'):
    return {'pid': pid, 'fd': fd, 'target': target}


class SnapshotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.namespace = extracted_namespace()
        self.snapshot = self.namespace['original_machine_lock_snapshot']

    def observe(self, fake):
        result = self.snapshot(LOCK, PROC, fake)
        self.assertIs(result['opened_or_modified'], False)
        return result

    def unverifiable(self, fake):
        value = self.observe(fake)
        self.assertFalse(value['ready'])
        self.assertEqual(value['state'], 'UNVERIFIABLE')
        self.assertTrue(value['reasons'])
        return value

    def test_clean_absence_keeps_unknown_cause(self):
        fake = FakeIO()
        value = self.observe(fake)
        self.assertTrue(value['ready'])
        self.assertEqual(value['state'], 'ABSENT')
        self.assertEqual(value['absence_cause'], 'UNKNOWN_NOT_ATTRIBUTED_TO_ORIGINAL_RUNNER_UNLINK')
        self.assertEqual([call[0] for call in fake.calls], ['lstat', 'locks', 'fds', 'lstat'])

    def test_absence_with_exact_plain_or_deleted_open_reference_defers(self):
        for target in [LOCK, LOCK + ' (deleted)']:
            with self.subTest(target=target):
                value = self.observe(FakeIO(references=[reference(target)]))
                self.assertFalse(value['ready'])
                self.assertEqual(value['state'], 'ABSENT')
                self.assertEqual(value['opened_fd_references'], [reference(target)])

    def test_similar_paths_do_not_match_exact_lock_reference(self):
        fake = FakeIO(references=[reference(target) for target in
                      [LOCK + '.old', LOCK + ' (deleted).old', LOCK + 'x', '/other/' + LOCK.rsplit('/', 1)[1]]])
        value = self.observe(fake)
        self.assertTrue(value['ready'])
        self.assertEqual(value['opened_fd_references'], [])
        self.assertEqual(value['proc_fd_links_checked'], 4)

    def test_existing_free_lock_matches_device_and_inode(self):
        fake = FakeIO(states=[metadata(), metadata()], locks='1: FLOCK ADVISORY WRITE 9 0a:1f:31 0 EOF\n')
        value = self.observe(fake)
        self.assertTrue(value['ready'])
        self.assertEqual(value['state'], 'FREE')
        self.assertEqual((value['major'], value['minor'], value['inode']), (10, 31, 30))
        self.assertNotIn('fds', [call[0] for call in fake.calls])

    def test_existing_held_lock_defers(self):
        line = '1: FLOCK ADVISORY WRITE 9 0A:1F:30 0 EOF'
        value = self.observe(FakeIO(states=[metadata(), metadata()], locks=line))
        self.assertFalse(value['ready'])
        self.assertEqual(value['state'], 'HELD')
        self.assertEqual(value['held_entries'], [line])

    def test_link_directory_and_fifo_are_invalid(self):
        for kind in [stat.S_IFLNK, stat.S_IFDIR, stat.S_IFIFO]:
            with self.subTest(kind=kind):
                fake = FakeIO(states=[metadata(mode=kind)])
                value = self.observe(fake)
                self.assertFalse(value['ready'])
                self.assertEqual(value['state'], 'INVALID')
                self.assertEqual([call[0] for call in fake.calls], ['lstat'])

    def test_initial_lstat_permission_failure_defers(self):
        self.unverifiable(FakeIO(states=[PermissionError('fake lstat denied')]))

    def test_proc_locks_read_failures_defer(self):
        for failure in [PermissionError('fake locks denied'), FileNotFoundError('fake proc unavailable'),
                        UnicodeError('fake decoding failure')]:
            with self.subTest(failure=type(failure).__name__):
                self.unverifiable(FakeIO(locks=failure))

    def test_nontext_oversized_and_malformed_lock_rows_defer(self):
        for text in [b'', 'x' * (1024 * 1024 + 1), 'not a proc lock row',
                     '1: FLOCK 0a:1f:30 0a:1f:31']:
            with self.subTest(kind=type(text).__name__, length=len(text)):
                self.unverifiable(FakeIO(locks=text))

    def test_fd_walk_permission_and_disappearance_defer(self):
        for failure in [PermissionError('fake fd denied'), FileNotFoundError('fake fd vanished')]:
            with self.subTest(failure=type(failure).__name__):
                self.unverifiable(FakeIO(references=failure))

    def test_invalid_fd_payloads_defer(self):
        for item in [None, {}, reference(pid=True), reference(pid=0), reference(fd='x'),
                     reference(fd=3), reference(target=None), reference(target='x' * 4097)]:
            with self.subTest(item_type=type(item).__name__):
                self.unverifiable(FakeIO(references=[item]))

    def test_injected_fd_enumeration_total_bound_is_still_enforced(self):
        self.unverifiable(FakeIO(references=(reference('/other') for _ in range(65537))))

    def test_inode_change_disappearance_and_type_change_defer(self):
        for after in [metadata(inode=31), MISSING, metadata(mode=stat.S_IFLNK)]:
            with self.subTest(after=type(after).__name__):
                self.unverifiable(FakeIO(states=[metadata(), after]))

    def test_absent_path_appearance_or_second_stat_denied_defers(self):
        for after in [metadata(), PermissionError('fake final stat denied')]:
            with self.subTest(after=type(after).__name__):
                self.unverifiable(FakeIO(states=[MISSING, after]))

    def test_bad_device_identity_is_not_free(self):
        for identity in [(), (1, 2), (1, 2, -1), (1, 2, True), (1, '2', 3)]:
            with self.subTest(identity=identity):
                value = metadata()
                value.fake_identity = identity
                self.unverifiable(FakeIO(states=[value]))


class FakeScan:
    def __init__(self, entries):
        self.entries = entries
        self.closed = False

    def __enter__(self):
        return iter(self.entries)

    def __exit__(self, *_):
        self.closed = True


class NativeReadAdapterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.namespace = extracted_namespace()
        self.adapter = self.namespace['_ReadOnlyProcIO']()
        self.limits = {'proc_entries': 4, 'processes': 2, 'fds_per_process': 2,
                       'total_fds': 3, 'link_chars': 8, 'locks_bytes': 8}
        self.scans = []

    def scan(self, processes, descriptors, targets, failures=None):
        mapping = {PROC: processes, **descriptors}
        failures = {} if failures is None else failures

        def scandir(path):
            key = os.fspath(path).replace('\\', '/')
            if key in failures:
                raise failures[key]
            if key not in mapping:
                raise AssertionError('Unexpected filesystem access: ' + key)
            result = FakeScan(mapping[key])
            self.scans.append(result)
            return result

        def readlink(path):
            value = targets[os.fspath(path).replace('\\', '/')]
            if isinstance(value, BaseException):
                raise value
            return value

        self.namespace['os'].scandir = scandir
        self.namespace['os'].readlink = readlink
        return list(self.adapter.proc_fd_links(PROC, self.limits))

    def process(self, name):
        return SimpleNamespace(name=str(name))

    def fd(self, process, descriptor):
        return SimpleNamespace(name=str(descriptor), path=f'{PROC}/{process}/fd/{descriptor}')

    def test_numeric_processes_and_exact_bounds_complete_and_close(self):
        result = self.scan([self.process('locks'), self.process(1), self.process(2)],
                           {f'{PROC}/1/fd': [self.fd(1, 3), self.fd(1, 4)],
                            f'{PROC}/2/fd': [self.fd(2, 5)]},
                           {f'{PROC}/1/fd/3': 'a', f'{PROC}/1/fd/4': 'b', f'{PROC}/2/fd/5': '12345678'})
        self.assertEqual(len(result), 3)
        self.assertEqual(result[-1], reference('12345678', pid=2, fd='5'))
        self.assertTrue(all(scan.closed for scan in self.scans))

    def test_proc_directory_entry_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'directory enumeration'):
            self.scan([self.process('locks')] * 5, {}, {})

    def test_process_count_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'process enumeration'):
            self.scan([self.process(i) for i in [1, 2, 3]],
                      {f'{PROC}/1/fd': [], f'{PROC}/2/fd': []}, {})

    def test_per_process_fd_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'FD enumeration'):
            self.scan([self.process(1)], {f'{PROC}/1/fd': [self.fd(1, n) for n in [3, 4, 5]]},
                      {f'{PROC}/1/fd/3': 'a', f'{PROC}/1/fd/4': 'b'})

    def test_total_fd_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'FD enumeration'):
            self.scan([self.process(1), self.process(2)],
                      {f'{PROC}/1/fd': [self.fd(1, 3), self.fd(1, 4)],
                       f'{PROC}/2/fd': [self.fd(2, 5), self.fd(2, 6)]},
                      {f'{PROC}/1/fd/3': 'a', f'{PROC}/1/fd/4': 'b', f'{PROC}/2/fd/5': 'c'})

    def test_target_length_bound(self):
        with self.assertRaisesRegex(RuntimeError, 'target exceeds'):
            self.scan([self.process(1)], {f'{PROC}/1/fd': [self.fd(1, 3)]},
                      {f'{PROC}/1/fd/3': '123456789'})

    def test_nonnumeric_fd_is_unverifiable(self):
        with self.assertRaisesRegex(RuntimeError, 'nonnumeric'):
            self.scan([self.process(1)], {f'{PROC}/1/fd': [self.fd(1, 'bad')]}, {})

    def test_scandir_root_or_process_permission_failure_propagates(self):
        for path in [PROC, f'{PROC}/1/fd']:
            with self.subTest(path=path), self.assertRaises(PermissionError):
                self.scan([self.process(1)], {}, {}, failures={path: PermissionError('fake denied')})

    def test_readlink_permission_or_disappearance_propagates(self):
        for error in [PermissionError('fake denied'), FileNotFoundError('fake vanished')]:
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                self.scan([self.process(1)], {f'{PROC}/1/fd': [self.fd(1, 3)]},
                          {f'{PROC}/1/fd/3': error})

    def locks_bytes(self, data=None, error=None):
        class FakePath:
            def __init__(self, *_):
                pass

            def __truediv__(self, name):
                if name != 'locks':
                    raise AssertionError('Unexpected file name')
                return self

            def open(self, mode):
                if mode != 'rb':
                    raise AssertionError('Unexpected writable file mode')
                if error is not None:
                    raise error
                return memory_io.BytesIO(data)

        self.namespace['Path'] = FakePath
        return self.adapter.read_proc_locks(PROC, 8)

    def test_proc_locks_exact_byte_limit(self):
        self.assertEqual(self.locks_bytes(b'12345678'), '12345678')

    def test_proc_locks_byte_overflow(self):
        with self.assertRaisesRegex(RuntimeError, 'bounded read'):
            self.locks_bytes(b'123456789')

    def test_proc_locks_utf8_decode_failure(self):
        with self.assertRaises(UnicodeError):
            self.locks_bytes(b'\xff')

    def test_proc_locks_open_permission_failure(self):
        with self.assertRaises(PermissionError):
            self.locks_bytes(error=PermissionError('fake denied'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
