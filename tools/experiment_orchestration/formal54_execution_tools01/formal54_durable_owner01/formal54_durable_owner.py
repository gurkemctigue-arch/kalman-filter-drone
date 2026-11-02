"""Detached lifetime ownership for the unchanged formal54 serial; no admission.

describe is inert. launch/worker/stop are Linux-only; watch never spawns or sends
signals. No process group is signaled and no forced-kill deadline is present.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
SCOPE = 'FORMAL54_DURABLE_SERIAL_LIFETIME_ONLY_NOT_ADMISSION'
REQUEST_KIND = 'FORMAL54_DURABLE_SERIAL_LAUNCH_REQUEST_NOT_ADMISSION'
REGISTRY_KIND = 'FORMAL54_DURABLE_PROSPECTIVE_OWNER_REGISTRY'
SERIAL_SCOPE = 'FORMAL54_OWNED_SERIAL_SIGNAL_FORWARDING_NOT_GUARD_ADMISSION'
MAX_SMALL = 8 * 1024**2
FILES = ('formal54_durable_owner.py', 'test_formal54_durable_owner.py', 'test_native_durable_dummy.py')


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def raw(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL,
            'Only bounded ordinary named metadata/code is allowed: '+str(path))
    require(path.suffix in {'.json', '.jsonl', '.py', '.sh'}, 'Named metadata/code suffix required')
    with path.open('rb') as stream:
        value = stream.read(MAX_SMALL+1)
    require(len(value) <= MAX_SMALL, 'Named metadata grew beyond its bound')
    return value


def pin(path):
    path = Path(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(raw(path)).hexdigest()}


def checked(binding):
    require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
            and isinstance(binding['path'], str) and Path(binding['path']).is_absolute()
            and valid_sha(binding['sha256']) and pin(binding['path']) == binding,
            'Exact physical absolute metadata/code path and unchanged byte SHA required')
    return Path(binding['path'])


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: '+key)
            result[key] = value
        return result
    value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda item: (_ for _ in ()).throw(ValueError('Nonfinite JSON: '+item)))
    require(isinstance(value, dict), 'One metadata object required')
    return value


def load(path):
    return decode(raw(path))


def bound(binding):
    return load(checked(binding))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def heartbeat(path, value):
    temporary = Path(path).with_name(Path(path).name+'.new')
    write_new(temporary, value)
    temporary.replace(path)


def timestamp(value):
    require(isinstance(value, str), 'Aware UTC timestamp required')
    when = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(when.tzinfo is not None, 'Naive time is not prospective evidence')
    return when.astimezone(timezone.utc)


def physical(value, *, exists=True):
    require(isinstance(value, str) and Path(value).is_absolute(), 'Explicit absolute physical path required')
    path = Path(value)
    require(not path.is_symlink() and str(path.resolve(strict=exists)) == value, 'Aliases are not physical paths')
    return path


def description():
    return {'schema_version': 1, 'scope': SCOPE, 'files': {name: pin(HERE/name)['sha256'] for name in FILES},
        'default_action': 'describe', 'launches': 'existing serial only, after independent source pins and launch ACK',
        'watch_spawns_or_signals': False, 'signal_target': 'verified positive worker PID then verified serial PID',
        'forced_kill_or_process_group_signal': False, 'flight_or_cleanup_timeout_s': None,
        'guard_or_slot_or_full280_policy_changed': False, 'native_runtime_validated': False}


class LinuxBackend:
    def require_runtime(self):
        require(sys.platform.startswith('linux') and Path('/proc/self/stat').is_file(), 'Linux /proc runtime required')

    def identity(self, pid):
        require(type(pid) is int and pid > 1, 'Positive non-system PID required')
        try:
            directory = Path('/proc')/str(pid)
            before = (directory/'stat').read_text(encoding='ascii')
            fields = before[before.rfind(')')+2:].split()
            argv = [part.decode('utf-8', errors='surrogateescape') for part in (directory/'cmdline').read_bytes().split(b'\0') if part]
            executable = str((directory/'exe').resolve(strict=True)) if fields[0] not in {'Z', 'X'} else None
            after = (directory/'stat').read_text(encoding='ascii')
            final = after[after.rfind(')')+2:].split()
            require(fields[19] == final[19], 'PID changed during identity read')
            boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
            return {'pid': pid, 'start_ticks': int(final[19]), 'start_token': 'linux:'+boot+':'+final[19],
                'pgid': int(final[2]), 'session': int(final[3]), 'state': final[0], 'argv': argv, 'exe': executable}
        except (FileNotFoundError, ProcessLookupError):
            return None

    def spawn(self, argv, **kwargs):
        return subprocess.Popen(argv, start_new_session=True, close_fds=True, **kwargs)

    def send(self, pid, number):
        require(type(pid) is int and pid > 1 and number in (signal.SIGINT, signal.SIGTERM), 'Only positive PID graceful stop allowed')
        os.kill(pid, number)

    def sleep(self, seconds):
        time.sleep(seconds)

    def monotonic(self):
        return time.monotonic()


def same_creation(actual, expected):
    return isinstance(actual, dict) and isinstance(expected, dict) and all(actual.get(key) == expected.get(key)
        for key in ('pid', 'start_token', 'start_ticks', 'pgid', 'session'))


def verify(backend, expected, command, *, isolated=True):
    require(isinstance(expected, dict) and type(expected.get('pid')) is int and expected['pid'] > 1,
            'Recorded actual process creation identity required')
    actual = backend.identity(expected['pid'])
    require(same_creation(actual, expected) and actual.get('state') not in {'Z', 'X'},
            'PID missing/reused or process creation/session differs; refusing signal/start')
    require(actual.get('argv') == list(command)
            and actual.get('exe') == str(Path(command[0]).resolve(strict=True)),
            'Actual process executable or exact expected command differs')
    if isolated:
        require(actual['pgid'] == actual['pid'] == actual['session'], 'Owned process must lead its detached session')
    return actual


def request_context(binding, owner_directory, reviewed_owner_sha, reviewed_serial_sha):
    require(valid_sha(reviewed_owner_sha) and canonical(description()) == reviewed_owner_sha,
            'Exact independently reviewed durable owner source canonical required')
    request = bound(binding)
    fields = {'schema_version', 'kind', 'created_utc', 'python_executable', 'serial_entry', 'serial_description',
        'reviewed_serial_tools_sha256', 'manifest', 'serial_output', 'working_directory', 'guard_command', 'input_files'}
    require(set(request) == fields and type(request['schema_version']) is int and request['schema_version'] == 1
            and request['kind'] == REQUEST_KIND and timestamp(request['created_utc']) <= datetime.now(timezone.utc),
            'Exact prospective serial launch request required')
    interpreter = physical(request['python_executable'])
    require(interpreter.is_file(), 'Actual Python executable must already exist')
    serial_path = checked(request['serial_entry'])
    require(serial_path.name == 'formal280_serial_guard54.py', 'Only the existing reviewed formal54 serial is delegated')
    serial_description = bound(request['serial_description'])
    require(serial_description.get('scope') == SERIAL_SCOPE and valid_sha(reviewed_serial_sha)
            and canonical(serial_description) == request['reviewed_serial_tools_sha256'] == reviewed_serial_sha,
            'Actual serial describe and separate independently reviewed canonical differ')
    files = serial_description.get('files')
    require(isinstance(files, dict) and set(files) == {'formal280_serial_guard54.py', 'owned_guard_process54.py',
        'formal280_serial_guard01.original.py', 'test_formal280_serial_guard01.original.py',
        'test_formal280_serial_guard54.py', 'test_native_owned_signal54.py'}, 'Complete actual serial manifest required')
    inputs = [binding, request['serial_entry'], request['serial_description'], request['manifest']]
    for name, digest in files.items():
        item = pin(serial_path.parent/name)
        require(item['sha256'] == digest, 'Actual serial source/test bytes changed: '+name)
        inputs.append(item)
    admission = bound(request['manifest'])
    require(admission.get('kind') == 'RELIABILITY_V4_FORMAL_ADMISSION', 'Use an actual sealed admission; this tool grants none')
    # This is output confinement, not a substitute for the actual guard checks.
    root, state = physical(admission['final_root']), physical(admission['state_directory'], exists=False)
    output = physical(request['serial_output'], exists=False)
    owner = physical(str(owner_directory), exists=False)
    require(owner != output and not owner.is_relative_to(output) and not output.is_relative_to(owner), 'Separate fresh owner and serial outputs required')
    for directory in (owner, output):
        require(not directory.exists() and directory.parent.is_dir() and not directory.parent.is_symlink()
                and not directory.is_relative_to(root) and not directory.is_relative_to(state)
                and not state.is_relative_to(directory), 'Fresh external output outside frozen source/guard state required')
    working = physical(request['working_directory'])
    require(working.is_dir(), 'Explicit existing working directory required')
    prefix = request['guard_command']
    require(isinstance(prefix, list) and prefix and all(isinstance(token, str) and token for token in prefix), 'Exact original guard argv prefix required')
    require('run-one' not in prefix and '--manifest' not in prefix, 'The existing serial alone appends action/manifest')
    require(isinstance(request['input_files'], list) and request['input_files'], 'Explicit supplementary/adapter small input pins required')
    for item in request['input_files']:
        checked(item)
    inputs += request['input_files']
    serial_command = [str(interpreter), '-B', str(serial_path), '--manifest', request['manifest']['path'],
                      '--output', str(output), '--guard-command', *prefix]
    return {'request': request, 'request_pin': binding, 'owner_directory': str(owner), 'serial_output': str(output),
        'working_directory': str(working), 'serial_command': serial_command, 'input_pins': inputs,
        'reviewed_owner_sha256': reviewed_owner_sha, 'reviewed_serial_sha256': reviewed_serial_sha}


def read_registry(directory, digest):
    directory = physical(str(directory))
    registry_pin = {'path': str(directory/'registry.json'), 'sha256': digest}
    registry = bound(registry_pin)
    require(registry.get('kind') == REGISTRY_KIND and registry.get('owner_directory') == str(directory)
            and registry.get('owner_tool_manifest') == description()
            and canonical(description()) == registry.get('reviewed_owner_sha256'), 'Original durable registry/source changed')
    request = bound(registry['request_pin'])
    require(request == registry['request'], 'Registry does not retain the exact original prospective request')
    serial_description = bound(request['serial_description'])
    require(canonical(serial_description) == request['reviewed_serial_tools_sha256'] == registry['reviewed_serial_sha256'],
            'Original independently reviewed serial canonical changed')
    expected = [request['python_executable'], '-B', request['serial_entry']['path'], '--manifest', request['manifest']['path'],
                '--output', request['serial_output'], '--guard-command', *request['guard_command']]
    require(registry['serial_command'] == expected and registry['serial_output'] == request['serial_output']
            and registry['working_directory'] == request['working_directory']
            and registry['worker_command_prefix'] == [request['python_executable'], '-I', '-B',
                str(HERE/'formal54_durable_owner.py'), 'worker', '--owner-directory', str(directory)],
            'Registered serial/worker command differs from the exact prospective command')
    expected_pins = [registry['request_pin'], request['serial_entry'], request['serial_description'], request['manifest']]
    serial_parent = checked(request['serial_entry']).parent
    expected_pins += [{'path': str((serial_parent/name).resolve(strict=True)), 'sha256': sha}
                      for name, sha in serial_description['files'].items()]
    expected_pins += request['input_files']
    require(registry['input_pins'] == expected_pins, 'Complete original request/source/input pin denominator changed')
    for item in registry['input_pins']:
        checked(item)
    return registry_pin, registry


@contextmanager
def stop_requests(install=True):
    class Ledger(list):
        closed = False
        def __init__(self):
            self.post_terminal = []
        def close(self):
            self.closed = True
    requests, previous = Ledger(), {}
    def receive(number, frame=None):
        request = {'signal': int(number), 'created_utc': utc()}
        (requests.post_terminal if requests.closed else requests).append(request)
    try:
        if install:
            for number in (signal.SIGINT, signal.SIGTERM):
                previous[number] = signal.signal(number, receive)
        yield requests
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def launch(binding, directory, reviewed_owner_sha, reviewed_serial_sha, *, backend=None):
    backend = backend or LinuxBackend()
    backend.require_runtime()
    context = request_context(binding, directory, reviewed_owner_sha, reviewed_serial_sha)
    owner = Path(context['owner_directory'])
    owner.mkdir(exist_ok=False)
    command = [context['request']['python_executable'], '-I', '-B', str(HERE/'formal54_durable_owner.py'),
               'worker', '--owner-directory', str(owner)]
    registry = {'schema_version': 1, 'kind': REGISTRY_KIND, 'created_utc': utc(), **context,
        'worker_command_prefix': command, 'owner_tool_manifest': description(), 'automatic_retry': False,
        'flight_or_cleanup_timeout_s': None, 'formal_admission_claimed': False}
    write_new(owner/'registry.json', registry)
    registry_pin = pin(owner/'registry.json')
    command += ['--registry-sha256', registry_pin['sha256']]
    process, actual = None, None
    try:
        with (owner/'worker_stdout.log').open('xb') as stdout, (owner/'worker_stderr.log').open('xb') as stderr:
            process = backend.spawn(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    cwd=context['working_directory'])
        actual = backend.identity(process.pid)
        actual = verify(backend, actual, command)
        write_new(owner/'worker_spawned.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
            'registry': registry_pin, 'worker_process': actual, 'command': command,
            'detached_session': True, 'launcher_waits_for_flight': False})
        # A detached worker cannot start any serial until this verified ACK exists.
        write_new(owner/'launch_ack.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
            'registry': registry_pin, 'worker_process': actual, 'worker_spawn': pin(owner/'worker_spawned.json')})
        return {'status': 'DETACHED_WORKER_VERIFIED_AND_ACKNOWLEDGED_NOT_FLIGHT_ACCEPTANCE',
                'registry': registry_pin, 'worker_process': actual, 'terminal_required': str(owner/'terminal.json')}
    except BaseException as error:
        code = None if process is None else process.poll()
        if process is not None and code is not None:
            code = process.wait()  # Actual handle, never disappearance-derived.
        failure = {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(), 'registry': registry_pin,
            'error': type(error).__name__+': '+str(error), 'worker_process': actual,
            'spawned_pid': None if process is None else process.pid, 'observed_handle_exit': code,
            'worker_may_still_be_alive': process is not None and code is None,
            'forced_signal_sent': False, 'no_ack_no_serial_start': not (owner/'launch_ack.json').exists()}
        write_new(owner/'launch_failure.json', failure)
        if process is None or code is not None:
            if not (owner/'terminal.json').exists():
                write_new(owner/'terminal.json', {**failure, 'state': 'LAUNCH_FAILED_BEFORE_ACK',
                    'serial_wait_completed': False, 'serial_started': False})
        raise


def adapter_observation(registry, backend):
    """Read one original current-child identity; stale/closed samples stay unknown."""
    output = Path(registry['serial_output'])
    path = output/'lifecycle_heartbeat.json'
    if not path.is_file():
        return {'status': 'NO_ORIGINAL_SERIAL_HEARTBEAT_YET'}
    data = raw(path)
    record = decode(data)
    snapshot_pin = {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(data).hexdigest()}
    child = record.get('child_process')
    if not isinstance(child, dict):
        return {'status': 'NO_CURRENT_ORIGINAL_CHILD', 'serial_heartbeat': snapshot_pin}
    actual = backend.identity(child['pid'])
    verified = same_creation(actual, child) and actual.get('state') not in {'Z', 'X'}
    return {'status': 'KERNEL_CREATION_VERIFIED' if verified else 'NOT_CURRENTLY_VERIFIED',
        'serial_heartbeat': snapshot_pin, 'recorded_child': child, 'observed_kernel_process': actual,
        'initial_guard_command': registry['request']['guard_command']+['run-one', '--manifest', registry['request']['manifest']['path']],
        'exec_transition_may_change_argv': True, 'adapter_cleanup_claimed': False,
        'authority': 'original owned_process_started/terminal and formal48 cleanup receipts only'}


def supervise(registry_pin, registry, *, backend=None, install_handlers=True, ack_budget_s=30.):
    """Own the actual serial handle until wait; CLI supplies only a checked registry."""
    backend = backend or LinuxBackend()
    backend.require_runtime()
    owner = Path(registry['owner_directory'])
    worker_command = registry['worker_command_prefix']+['--registry-sha256', registry_pin['sha256']]
    worker = verify(backend, backend.identity(os.getpid()), worker_command)
    write_new(owner/'worker_started.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
        'registry': registry_pin, 'worker_process': worker, 'command': worker_command})
    process, serial, code, waited, error = None, None, None, False, None
    forwarded, latest_adapter = [], None
    state = 'WAITING_VERIFIED_LAUNCH_ACK'
    terminal = None
    with stop_requests(install_handlers) as requests:
        write_new(owner/'worker_control_ready.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
            'registry': registry_pin, 'worker_process': worker, 'command': worker_command,
            'stop_handlers_installed': install_handlers})
        try:
            start = backend.monotonic()
            while not (owner/'launch_ack.json').exists():
                require(not requests, 'Stop before launch ACK; no serial may start')
                require(backend.monotonic()-start < ack_budget_s, 'No verified launcher ACK; abort without starting serial')
                backend.sleep(.1)
            ack = load(owner/'launch_ack.json')
            require(ack.get('registry') == registry_pin and same_creation(ack.get('worker_process'), worker),
                    'Launcher ACK belongs to a different worker creation/registry')
            spawned = bound(ack['worker_spawn'])
            require(spawned.get('registry') == registry_pin and spawned.get('command') == worker_command
                    and spawned.get('worker_process') == ack['worker_process'], 'Original verified launch receipt differs')
            verify(backend, worker, worker_command)
            for item in registry['input_pins']:
                checked(item)
            checked(registry_pin)
            require(not requests, 'Stop before serial start')
            with (owner/'serial_stdout.log').open('xb') as stdout, (owner/'serial_stderr.log').open('xb') as stderr:
                process = backend.spawn(registry['serial_command'], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        cwd=registry['working_directory'])
            serial = backend.identity(process.pid)
            serial = verify(backend, serial, registry['serial_command'])
            write_new(owner/'serial_started.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
                'registry': registry_pin, 'worker_process': worker, 'serial_process': serial,
                'command': registry['serial_command'], 'actual_popen_pid': process.pid})
            state = 'RUNNING_EXISTING_SERIAL'
            observation_error = None
            while True:
                if requests and not forwarded and process.poll() is None:
                    actual = verify(backend, serial, registry['serial_command'])
                    backend.send(actual['pid'], requests[0]['signal'])
                    forwarded.append({'created_utc': utc(), 'signal': requests[0]['signal'], 'verified_serial_process': actual})
                    write_new(owner/'serial_stop_forwarded.json', {'schema_version': 1, 'registry': registry_pin, **forwarded[0]})
                    state = 'WAITING_ORIGINAL_SERIAL_AND_ADAPTER_CLEANUP'
                try:
                    observation = adapter_observation(registry, backend)
                    if observation != latest_adapter:
                        latest_adapter = observation
                        heartbeat(owner/'adapter_observation.json', {'schema_version': 1, 'scope': SCOPE,
                            'observed_utc': utc(), 'registry': registry_pin, **observation})
                    heartbeat(owner/'heartbeat.json', {'schema_version': 1, 'scope': SCOPE, 'heartbeat_utc': utc(),
                        'registry': registry_pin, 'state': state, 'worker_process': worker, 'serial_process': serial,
                        'stop_requests': list(requests), 'forwarded_signals': list(forwarded),
                        'flight_or_cleanup_timeout_s': None, 'adapter_cleanup_claimed': False})
                except (OSError, ValueError) as caught:
                    # Observability I/O must not abandon/kill a healthy serial.
                    observation_error = type(caught).__name__+': '+str(caught)
                try:
                    code = process.wait(timeout=1.)
                    waited = True
                    break
                except subprocess.TimeoutExpired:
                    pass
            if observation_error:
                error = 'observation:'+observation_error
            state = 'SERIAL_EXITED_WAITED'
        except BaseException as caught:
            error = type(caught).__name__+': '+str(caught)
            state = 'STARTUP_OR_IDENTITY_FAILED'
        finally:
            # Never lose the actual handle on exception. Only a creation+argv
            # verified process can receive one graceful cleanup request.
            if process is not None and not waited:
                if process.poll() is None and serial is not None and not forwarded:
                    try:
                        actual = verify(backend, serial, registry['serial_command'])
                        backend.send(actual['pid'], signal.SIGTERM)
                        forwarded.append({'created_utc': utc(), 'signal': int(signal.SIGTERM),
                            'verified_serial_process': actual, 'source': 'cleanup_after_error'})
                    except (OSError, ValueError) as cleanup_error:
                        error = (error or '')+';unverified_no_signal:'+str(cleanup_error)
                # Identity trouble does not license a kill or fabricated exit.
                while True:
                    try:
                        code = process.wait(timeout=1.)
                        waited = True
                        break
                    except subprocess.TimeoutExpired:
                        continue
            # No serial remains after the actual wait. Late stop signals cannot
            # mutate the committed terminal decision or its return code.
            requests.close()
            original = Path(registry['serial_output'])/'lifecycle_terminal.json'
            original_binding, original_value = None, None
            try:
                original_binding = pin(original) if original.is_file() else None
                original_value = bound(original_binding) if original_binding else None
            except (OSError, ValueError, TypeError, KeyError) as original_error:
                error = (error or '')+';original_terminal:'+type(original_error).__name__+': '+str(original_error)
            original_valid = (isinstance(original_value, dict) and original_value.get('scope') == SERIAL_SCOPE
                and same_creation(original_value.get('owner_process'), serial or {})
                and original_value.get('serial_exit_code') == code)
            terminal = {'schema_version': 1, 'scope': SCOPE, 'finished_utc': utc(), 'registry': registry_pin,
                'state': state, 'worker_process': worker, 'serial_process': serial,
                'serial_started': process is not None, 'actual_popen_pid': None if process is None else process.pid,
                'serial_returncode': code, 'serial_wait_completed': waited,
                'stop_requests': list(requests), 'forwarded_signals': forwarded, 'error': error,
                'stop_window_closed_with_no_owned_serial': process is None or waited,
                'original_serial_terminal': original_binding, 'original_terminal_identity_and_exit_match': original_valid,
                'serial_exit_evidence_complete': waited and original_valid,
                'descendant_cleanup_claimed': False, 'formal_acceptance_claimed': False,
                'automatic_retry': False, 'flight_or_cleanup_timeout_s': None}
            write_new(owner/'terminal.json', terminal)
    return terminal


def worker_action(directory, digest, *, backend=None):
    """Retain an early source/registry/startup refusal without inventing a wait."""
    directory = physical(str(directory))
    registry_pin = {'path': str(directory/'registry.json'), 'sha256': digest}
    checked(registry_pin)
    try:
        original_pin, registry = read_registry(directory, digest)
        return supervise(original_pin, registry, backend=backend)
    except BaseException as error:
        if not (directory/'terminal.json').exists():
            write_new(directory/'terminal.json', {'schema_version': 1, 'scope': SCOPE, 'finished_utc': utc(),
                'registry': registry_pin, 'state': 'WORKER_FAILED_EVIDENCE_INCOMPLETE',
                'error': type(error).__name__+': '+str(error), 'serial_started': None,
                'serial_wait_completed': False, 'serial_exit_evidence_complete': False,
                'descendant_cleanup_claimed': False, 'formal_acceptance_claimed': False,
                'automatic_retry': False})
        raise


def original_worker_start(owner, registry_pin, registry):
    """Bind observations/control to this owner's original acknowledged receipt."""
    started_pin = pin(owner/'worker_spawned.json')
    started = bound(started_pin)
    command = registry['worker_command_prefix']+['--registry-sha256', registry_pin['sha256']]
    require(started.get('registry') == registry_pin and started.get('command') == command,
            'Original worker start registry/command belongs to another owner')
    ack = load(owner/'launch_ack.json')
    require(ack.get('registry') == registry_pin and ack.get('worker_spawn') == started_pin
            and ack.get('worker_process') == started.get('worker_process'),
            'Original acknowledged worker receipt bytes/creation changed')
    return started


def observe(directory, digest, *, backend=None):
    backend = backend or LinuxBackend()
    registry_pin, registry = read_registry(directory, digest)
    owner = Path(directory)
    terminal_path = owner/'terminal.json'
    terminal_error = None
    if terminal_path.is_file():
        try:
            terminal = load(terminal_path)
            require(terminal.get('registry') == registry_pin, 'Original owner terminal binds another registry')
            return {'scope': SCOPE, 'status': 'TERMINAL_RECORDED', 'terminal': terminal,
                    'watch_controls_execution': False}
        except (OSError, ValueError, TypeError, KeyError) as error:
            # An exclusive writer can still be between open and fsync. Only a
            # complete bound terminal is completion; retain publication error.
            terminal_error = type(error).__name__+': '+str(error)
    started_path = owner/'worker_spawned.json'
    if not started_path.is_file():
        return {'scope': SCOPE, 'status': 'LAUNCH_NOT_ACKNOWLEDGED', 'watch_controls_execution': False}
    try:
        started = original_worker_start(owner, registry_pin, registry)
        actual = verify(backend, started['worker_process'], started['command'])
        status = 'VERIFIED_WORKER_ALIVE'
    except (OSError, ValueError, KeyError, TypeError) as error:
        actual, status = None, 'OWNER_IDENTITY_MISSING_OR_CHANGED_EVIDENCE_INCOMPLETE'
    return {'scope': SCOPE, 'status': status, 'worker_process': actual,
        'terminal_publication_error': terminal_error,
        'heartbeat': load(owner/'heartbeat.json') if (owner/'heartbeat.json').is_file() else None,
        'serial_started': load(owner/'serial_started.json') if (owner/'serial_started.json').is_file() else None,
        'watch_controls_execution': False, 'automatic_retry': False}


def watch(directory, digest, *, backend=None, once=False, interval_s=5., output=print):
    backend = backend or LinuxBackend()
    require(math.isfinite(interval_s) and interval_s > 0, 'Positive finite watch interval required')
    try:
        while True:
            report = observe(directory, digest, backend=backend)
            output(json.dumps(report, ensure_ascii=False, allow_nan=False))
            if once or report['status'] == 'TERMINAL_RECORDED':
                return 0
            backend.sleep(interval_s)
    except KeyboardInterrupt:
        return 130  # No child/owner/signal operation exists in this function.


def stop(directory, digest, *, number=signal.SIGTERM, backend=None, wait=True):
    backend = backend or LinuxBackend()
    backend.require_runtime()
    require(number in (signal.SIGINT, signal.SIGTERM), 'Only graceful stop signals are exposed')
    registry_pin, registry = read_registry(directory, digest)
    owner = Path(directory)
    if (owner/'terminal.json').is_file():
        report = observe(directory, digest, backend=backend)
        if report['status'] == 'TERMINAL_RECORDED':
            return report
    started = original_worker_start(owner, registry_pin, registry)
    actual = verify(backend, started['worker_process'], started['command'])
    # launch can return before the worker installs its signal handlers. A
    # deliberate stop must never land in the worker's default-handler window.
    ready_path = owner/'worker_control_ready.json'
    while not ready_path.is_file():
        if (owner/'terminal.json').is_file():
            report = observe(directory, digest, backend=backend)
            if report['status'] == 'TERMINAL_RECORDED':
                return report
        verify(backend, started['worker_process'], started['command'])
        backend.sleep(.1)
    ready = load(ready_path)
    require(ready.get('registry') == registry_pin and ready.get('command') == started['command']
            and same_creation(ready.get('worker_process'), started['worker_process'])
            and ready.get('stop_handlers_installed') is True, 'Actual worker stop-handler readiness not verified')
    request_path = owner/('stop_request_'+uuid.uuid4().hex+'.json')
    write_new(request_path, {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
        'registry': registry_pin, 'signal': int(number), 'verified_worker_process': actual,
        'signal_target': 'positive worker PID only', 'cleanup_timeout_s': None})
    verify(backend, started['worker_process'], started['command'])
    backend.send(actual['pid'], number)
    if not wait:
        return {'status': 'GRACEFUL_STOP_REQUESTED_NOT_COMPLETION', 'stop_request': pin(request_path)}
    while True:
        report = observe(directory, digest, backend=backend)
        if report['status'] == 'TERMINAL_RECORDED':
            return report
        require(report['status'] == 'VERIFIED_WORKER_ALIVE',
                'Owner disappeared/changed without terminal; preserve evidence, do not claim cleanup or signal another PID')
        backend.sleep(1.)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'launch', 'worker', 'watch', 'stop'), nargs='?', default='describe')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--request-sha256')
    parser.add_argument('--owner-directory', type=Path)
    parser.add_argument('--reviewed-tools-sha256')
    parser.add_argument('--reviewed-serial-tools-sha256')
    parser.add_argument('--registry-sha256')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=float, default=5.)
    parser.add_argument('--signal', choices=('INT', 'TERM'), default='TERM')
    args = parser.parse_args(argv)
    try:
        if args.action == 'describe':
            value = description()
            print(json.dumps({'manifest': value, 'canonical_sha256': canonical(value), 'actual_action_executed': False}))
            return 0
        require(args.owner_directory is not None, 'Explicit owner directory required')
        if args.action == 'launch':
            require(args.request is not None and valid_sha(args.request_sha256), 'Exact prospective request path/SHA required')
            result = launch({'path': str(args.request), 'sha256': args.request_sha256}, args.owner_directory,
                            args.reviewed_tools_sha256, args.reviewed_serial_tools_sha256)
        else:
            require(valid_sha(args.registry_sha256), 'Explicit original registry byte SHA required')
            if args.action == 'watch':
                return watch(args.owner_directory, args.registry_sha256, once=args.once, interval_s=args.interval)
            if args.action == 'worker':
                LinuxBackend().require_runtime()
                result = worker_action(args.owner_directory, args.registry_sha256)
                return 0 if result['serial_exit_evidence_complete'] and result['serial_returncode'] == 0 and result['error'] is None else 2
            result = stop(args.owner_directory, args.registry_sha256,
                          number=signal.SIGINT if args.signal == 'INT' else signal.SIGTERM)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({'scope': SCOPE, 'status': 'REFUSED_OR_INCOMPLETE', 'error': type(error).__name__+': '+str(error),
            'formal_admission_claimed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
