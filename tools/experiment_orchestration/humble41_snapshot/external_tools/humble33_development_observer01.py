"""A fresh, independent Humble33 observer; never imports a Humble23 driver."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from humble33_review_guard import ROOT, read_small, sha

MAX_SAMPLE_AGE_WALL_S = 10.
MAX_SAMPLE_TAIL_BYTES = 64 * 1024


def latest_complete_sample(path):
    """Read only a bounded health tail; incomplete last writes are ignored."""
    with Path(path).open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        start = max(0, size - MAX_SAMPLE_TAIL_BYTES)
        stream.seek(start)
        data = stream.read(MAX_SAMPLE_TAIL_BYTES)
    if start:
        boundary = data.find(b'\n')
        data = data[boundary + 1:] if boundary >= 0 else b''
    end = data.rfind(b'\n')
    if end < 0:
        raise RuntimeError('Observer has no complete health JSON line')
    for line in reversed(data[:end].splitlines()):
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(row, dict) and row.get('event') == 'RUNTIME_HEALTH_SAMPLE':
            return row
    raise RuntimeError('No complete runtime health sample in the bounded tail')


def validate_sample(sample, now):
    stamp = sample.get('monotonic_s')
    if type(stamp) not in {int, float} or not math.isfinite(stamp):
        raise RuntimeError('Observer sample has no finite monotonic time')
    age = now - stamp
    if not -1e-6 <= age <= MAX_SAMPLE_AGE_WALL_S:
        raise RuntimeError('Latest complete observer sample is stale or future: ' + str(age))
    receiver, writer = sample.get('ros_receiver'), sample.get('writer')
    if (not isinstance(receiver, dict) or receiver.get('thread_alive') is not True
            or receiver.get('error') is not None):
        raise RuntimeError('Observer ROS receiver stopped or reports an error')
    if (not isinstance(writer, dict) or writer.get('error') is not None
            or writer.get('limit_reached') is not False):
        raise RuntimeError('Observer writer error, limit, or incomplete status')
    return {'latest_sample_monotonic_s': stamp, 'sample_age_wall_s': age,
            'max_sample_age_wall_s': MAX_SAMPLE_AGE_WALL_S}


class IndependentObserver:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.process = None
        self.console = None
        self._finished = None
        self.last_check = None
        self.command = [sys.executable, '-B', str(ROOT / 'scripts/observe_runtime_health.py'),
                        '--output-dir', str(self.directory / 'runtime_health'),
                        '--duration-wall-s', '7200', '--max-log-mib', '64', '--ros']

    def __enter__(self):
        self.directory.mkdir(exist_ok=False)
        self.console = (self.directory / 'observer_console.log').open('x')
        try:
            self.process = subprocess.Popen(self.command, cwd=ROOT, stdout=self.console,
                                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            last_error = None
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    self.check()
                    return self
                except (OSError, RuntimeError) as error:
                    last_error = str(error)
                time.sleep(.1)
            raise RuntimeError('No healthy fresh first observer sample: ' + str(last_error))
        except BaseException:
            self.finish(exception=True)
            raise

    def check(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('Independent observer stopped; no next attempt is allowed')
        self.last_check = validate_sample(
            latest_complete_sample(self.directory / 'runtime_health/health.jsonl'), time.monotonic())
        return self.last_check

    def finish(self, exception=False):
        if self._finished is not None:
            return self._finished
        forced = False
        unexpected = self.process is not None and self.process.poll() is not None
        final_sample_error = None
        try:
            self.check()
        except (OSError, RuntimeError) as error:
            final_sample_error = type(error).__name__ + ':' + str(error)
        if self.process is not None:
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGTERM)
            try:
                code = self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forced = True
                self.process.kill()
                code = self.process.wait(timeout=5)
        else:
            code = None
        if self.console is not None:
            self.console.close()
        self._finished = {
            'finished_utc': datetime.now(timezone.utc).isoformat(), 'command': self.command,
            'observer_exit_code': code, 'observer_forced_stop': forced,
            'ended_before_requested_stop': unexpected, 'driver_exception': exception,
            'final_fresh_sample': self.last_check, 'final_sample_error': final_sample_error,
            'healthy_cleanup': code == 0 and not forced and not unexpected
                               and not exception and final_sample_error is None}
        with (self.directory / 'execution_terminal.json').open('x') as stream:
            json.dump(self._finished, stream, indent=2)
            stream.write('\n')
        return self._finished

    def __exit__(self, kind, value, traceback):
        result = self.finish(exception=kind is not None)
        if kind is None and not result['healthy_cleanup']:
            raise RuntimeError('Observer freshness/cleanup failed; no automatic retry')
        return False


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())

SCOPE = 'HUMBLE33_ROLLING_INDEPENDENT_OBSERVER_ENTRY01'
ROTATE_WALL_S = 5400.


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('Expected timezone-aware UTC observer time')
    return parsed.timestamp()


def finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def fresh(value):
    if (not isinstance(value, dict) or not finite(value.get('latest_sample_monotonic_s'))
            or value['latest_sample_monotonic_s'] < 0
            or not finite(value.get('sample_age_wall_s'))
            or not -1e-6 <= value['sample_age_wall_s'] <= 10.
            or value.get('max_sample_age_wall_s') != 10.):
        raise ValueError('No original fresh ten-second observer sample')
    return value


def command(directory):
    return [sys.executable, '-B', str(ROOT / 'scripts/observe_runtime_health.py'),
        '--output-dir', str(directory / 'runtime_health'), '--duration-wall-s', '7200',
        '--max-log-mib', '64', '--ros']


class RollingIndependentObserver:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.current = None
        self.sessions = []
        self.rotations = []
        self._finished = None

    def start_session(self):
        index = len(self.sessions) + 1
        directory = self.directory / f'session_{index:03d}'
        item = {'index': index, 'directory': str(directory), 'started_utc': utc(),
                'started_monotonic_s': time.monotonic()}
        observer = IndependentObserver(directory)
        # The unchanged observer refuses missing/future/stale samples and waits
        # at most10s for a healthy receiver; the previous session remains live.
        try:
            observer.__enter__()
            item['first_fresh_sample'] = observer.check()
            item['first_fresh_utc'] = utc()
            item['first_fresh_monotonic_s'] = time.monotonic()
        except BaseException:
            if observer._finished is None:
                observer.finish(exception=True)
            raise
        self.sessions.append((observer, item))
        return observer, item

    def close_session(self, observer, item, *, exception=False):
        result = observer.finish(exception=exception)
        path = observer.directory / 'execution_terminal.json'
        item.update(finished_utc=result['finished_utc'], finished_monotonic_s=time.monotonic(), terminal=result,
            terminal_binding={'path': str(path), 'sha256': sha(path)},
            artifacts={name: {'path': str(observer.directory / name),
                'sha256': sha(observer.directory / name)}
                for name in ('observer_console.log', 'runtime_health/health.jsonl')})
        return result

    def __enter__(self):
        self.directory.mkdir(exist_ok=False)
        self.started_utc = utc()
        self.current, self.current_item = self.start_session()
        return self

    def check(self):
        if self.current is None or self._finished is not None:
            raise RuntimeError('Rolling independent observer is not live')
        before = self.current.check()
        if time.monotonic() - self.current_item['started_monotonic_s'] >= ROTATE_WALL_S:
            old, old_item = self.current, self.current_item
            new, new_item = self.start_session()
            try:
                old_last = old.check()
                new_first = new.check()
                result = self.close_session(old, old_item)
                if result.get('healthy_cleanup') is not True:
                    raise RuntimeError('Previous independent observer failed its original cleanup')
                new_after = new.check()
            except BaseException:
                self.close_session(new, new_item, exception=True)
                raise
            self.current, self.current_item = new, new_item
            self.rotations.append({'old_index': old_item['index'], 'new_index': new_item['index'],
                'new_first_fresh_utc': new_item['first_fresh_utc'],
                'old_last_fresh_sample': old_last, 'new_first_fresh_sample': new_first,
                'old_finished_utc': result['finished_utc'],
                'new_fresh_after_old_finish': new_after, 'completed_utc': utc(),
                'completed_monotonic_s': time.monotonic()})
            return new_after
        return before

    def finish(self, exception=False):
        if self._finished is not None:
            return self._finished
        if self.current is not None and 'terminal' not in self.current_item:
            self.close_session(self.current, self.current_item, exception=exception)
        items = [item for _, item in self.sessions]
        healthy = bool(items) and not exception and all(
            item.get('terminal', {}).get('healthy_cleanup') is True for item in items)
        self._finished = {'schema_version': 1, 'scope': SCOPE,
            'started_utc': self.started_utc, 'finished_utc': utc(),
            'rotation_wall_s': ROTATE_WALL_S, 'session_duration_wall_s': 7200,
            'max_sample_age_wall_s': 10., 'sessions': items, 'rotations': self.rotations,
            'driver_exception': bool(exception), 'healthy_cleanup': healthy,
            'claim_boundary': 'All original7200s observers retain original logs and ten-second freshness. A new healthy session starts before the previous session closes; no flight, archive, evaluation or safety deadline is changed.'}
        write_new(self.directory / 'execution_terminal.json', self._finished)
        return self._finished

    def __exit__(self, kind, value, traceback):
        result = self.finish(exception=kind is not None)
        if kind is None and result['healthy_cleanup'] is not True:
            raise RuntimeError('Rolling observer failed; no further original attempts')
        return False


def validate_rolling_observer(terminal_or_none, directory):
    directory = Path(directory)
    path = directory / 'execution_terminal.json'
    actual = read_small(path)
    if terminal_or_none is not None and terminal_or_none != actual:
        raise ValueError('Parent rolling observer differs from the original terminal')
    sessions, rotations = actual.get('sessions'), actual.get('rotations')
    if (actual.get('schema_version') != 1 or actual.get('scope') != SCOPE
            or actual.get('rotation_wall_s') != ROTATE_WALL_S
            or actual.get('session_duration_wall_s') != 7200
            or actual.get('max_sample_age_wall_s') != 10.
            or actual.get('driver_exception') is not False or actual.get('healthy_cleanup') is not True
            or not isinstance(sessions, list) or not sessions
            or not isinstance(rotations, list) or len(rotations) != len(sessions) - 1):
        raise ValueError('Rolling observer aggregate is incomplete or unhealthy')
    for index, item in enumerate(sessions, 1):
        folder = directory / f'session_{index:03d}'
        original_path = folder / 'execution_terminal.json'
        original = read_small(original_path)
        if (item.get('index') != index or item.get('directory') != str(folder)
                or item.get('terminal_binding') != {'path': str(original_path), 'sha256': sha(original_path)}
                or item.get('terminal') != original or original.get('command') != command(folder)
                or original.get('observer_exit_code') != 0 or type(original['observer_exit_code']) is not int
                or original.get('observer_forced_stop') is not False
                or original.get('ended_before_requested_stop') is not False
                or original.get('driver_exception') is not False
                or original.get('final_sample_error') is not None
                or original.get('healthy_cleanup') is not True
                or item.get('finished_utc') != original.get('finished_utc')):
            raise ValueError('Original bounded observer session/command/cleanup changed')
        fresh(item.get('first_fresh_sample'))
        fresh(original.get('final_fresh_sample'))
        if (any(not finite(item.get(key)) for key in
                    ('started_monotonic_s', 'first_fresh_monotonic_s', 'finished_monotonic_s'))
                or not 0 <= item['started_monotonic_s'] <= item['first_fresh_monotonic_s']
                    <= item['finished_monotonic_s']
                or item['finished_monotonic_s'] - item['started_monotonic_s'] >= 7200
                or not -1e-6 <= item['first_fresh_monotonic_s']
                    - item['first_fresh_sample']['latest_sample_monotonic_s'] <= 10.
                or not -1e-6 <= item['finished_monotonic_s']
                    - original['final_fresh_sample']['latest_sample_monotonic_s'] <= 20.):
            raise ValueError('Original observer monotonic session time/freshness is invalid')
        if (not stamp(actual['started_utc']) <= stamp(item['started_utc'])
                <= stamp(item['first_fresh_utc']) <= stamp(item['finished_utc'])
                <= stamp(actual['finished_utc'])
                or stamp(item['finished_utc']) - stamp(item['started_utc']) >= 7200):
            raise ValueError('Original observer session exceeds its unchanged deadline or time ordering')
        for name in ('observer_console.log', 'runtime_health/health.jsonl'):
            artifact = folder / name
            if (artifact.is_symlink() or not artifact.is_file()
                    or item.get('artifacts', {}).get(name) != {'path': str(artifact), 'sha256': sha(artifact)}):
                raise ValueError('Original observer log changed or is missing')
        if index > 1:
            previous, rotation = sessions[index - 2], rotations[index - 2]
            if (rotation.get('old_index') != index - 1 or rotation.get('new_index') != index
                    or rotation.get('new_first_fresh_utc') != item['first_fresh_utc']
                    or rotation.get('old_finished_utc') != previous['finished_utc']
                    or not stamp(item['first_fresh_utc']) <= stamp(previous['finished_utc'])
                        <= stamp(rotation['completed_utc']) <= stamp(item['finished_utc'])
                    or not finite(rotation.get('completed_monotonic_s'))
                    or not previous['started_monotonic_s'] + ROTATE_WALL_S
                        <= item['started_monotonic_s'] <= item['first_fresh_monotonic_s']
                        <= previous['finished_monotonic_s'] <= rotation['completed_monotonic_s']
                        <= item['finished_monotonic_s']
                    or item['first_fresh_sample']['latest_sample_monotonic_s']
                        > previous['terminal']['final_fresh_sample']['latest_sample_monotonic_s'] + 10.):
                raise ValueError('No original overlap between successive fresh observers')
            for key in ('old_last_fresh_sample', 'new_first_fresh_sample', 'new_fresh_after_old_finish'):
                fresh(rotation.get(key))
    return {'path': str(path), 'sha256': sha(path), 'scope': SCOPE,
            'session_count': len(sessions), 'finished_utc': actual['finished_utc']}
