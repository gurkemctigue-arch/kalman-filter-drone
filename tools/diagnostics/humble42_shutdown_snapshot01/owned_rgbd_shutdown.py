#!/usr/bin/env python3
"""One owned renderer-only diagnostic. Never formal-slot repair or retry.

Native API is inherited from scripts/probe_gazebo_shutdown.py: transport13
Node.subscribe(Image, topic, callback); msgs10 Image.header.stamp.sec/nsec.
World pause uses the exact existing runner CLI WorldControl/Boolean API.
Only a normal Python subprocess imports native transport, after private env setup.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

BOUNDS = dict(proc_entries=4096, group_members=32, tasks=256,
              stat_bytes=8192, detail_bytes=16384, maps_bytes=1048576)
MACHINE_LOCK = Path('/tmp/uav_tracking_reliability_v4_sitl.lock')
WINDOW_LOCK = Path('/root/uav_tracking_humble_build_window.lock')
JOURNAL = None


def journal(event):
    if JOURNAL is not None:
        with JOURNAL.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, allow_nan=False) + '\n')
            stream.flush(); os.fsync(stream.fileno())


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def read_bounded(path, limit):
    with Path(path).open('rb') as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit, 'Bound exceeded: ' + str(path))
    return value.decode(errors='replace')


def identity(pid):
    raw = read_bounded(Path('/proc') / str(pid) / 'stat', BOUNDS['stat_bytes'])
    fields = raw[raw.rfind(')') + 2:].split()
    require(len(fields) >= 20, 'Incomplete process stat')
    return dict(pid=pid, ppid=int(fields[1]), pgid=int(fields[2]),
                session=int(fields[3]), state=fields[0], start_ticks=int(fields[19]),
                boot_id=read_bounded('/proc/sys/kernel/random/boot_id', 128).strip(),
                clock_ticks_per_s=os.sysconf('SC_CLK_TCK'), observed_utc=utc())


def group_members(pgid):
    entries = [entry for entry in Path('/proc').iterdir() if entry.name.isdigit()]
    require(len(entries) <= BOUNDS['proc_entries'], 'Process enumeration bound exceeded')
    members = []
    for entry in entries:
        try:
            item = identity(int(entry.name))
        except FileNotFoundError:
            continue
        if item['pgid'] == pgid:
            members.append(item)
    require(len(members) <= BOUNDS['group_members'], 'Owned group bound exceeded')
    return members


def snapshot(pid):
    """Read only bounded owned-process kernel metadata, never process memory."""
    report = dict(utc=utc(), monotonic_s=time.monotonic(), pid=pid, errors=[], optional_errors=[], members=[])
    try:
        roster = group_members(pid)
        require(roster, 'Owned process group absent at requested live snapshot')
        for member in roster:
            proc = Path('/proc') / str(member['pid'])
            item = dict(identity=member, tasks=[])
            try:
                environment = read_bounded(proc / 'environ', 65536).split('\0')
                keys = ('LP_NUM_THREADS','OMP_NUM_THREADS','LIBGL_ALWAYS_SOFTWARE',
                        'MESA_LOADER_DRIVER_OVERRIDE','GALLIUM_DRIVER')
                item['selected_environment'] = {name:value for field in environment
                    for name, separator, value in [field.partition('=')] if separator and name in keys}
            except (OSError, ValueError) as error:
                report['errors'].append(f'{proc}/environ: {type(error).__name__}:{error}')
            for name in ('status', 'wchan', 'stack'):
                try:
                    item[name] = read_bounded(proc / name, BOUNDS['detail_bytes'])
                except (OSError, ValueError) as error:
                    message = f'{proc / name}: {type(error).__name__}:{error}'
                    item[name] = dict(status='NOT_OBSERVED',reason=message)
                    report['optional_errors' if name in ('stack','wchan') else 'errors'].append(message)
            try:
                maps = read_bounded(proc / 'maps', BOUNDS['maps_bytes'])
                item['mappings'] = maps.splitlines()
            except (OSError, ValueError) as error:
                report['errors'].append(f'{proc}/maps: {type(error).__name__}:{error}')
            tasks = sorted((proc / 'task').iterdir(), key=lambda path:int(path.name))
            require(len(tasks) <= BOUNDS['tasks'], 'Owned task enumeration bound exceeded')
            for task in tasks:
                detail = dict(tid=int(task.name))
                for name in ('stat', 'wchan', 'stack'):
                    try:
                        detail[name] = read_bounded(task / name, BOUNDS['detail_bytes'])
                    except (OSError, ValueError) as error:
                        message = f'{task / name}: {type(error).__name__}:{error}'
                        detail[name] = dict(status='NOT_OBSERVED',reason=message)
                        report['optional_errors' if name in ('stack','wchan') else 'errors'].append(message)
                item['tasks'].append(detail)
            report['members'].append(item)
    except (OSError, ValueError) as error:
        report['errors'].append(type(error).__name__ + ':' + str(error))
    return report


def rendering_issues(capture):
    paths = '\n'.join(line.lower() for item in capture['members'] for line in item.get('mappings', []))
    issues = []
    expected = dict(LP_NUM_THREADS='4',OMP_NUM_THREADS='2',LIBGL_ALWAYS_SOFTWARE='1',
                    MESA_LOADER_DRIVER_OVERRIDE='swrast',GALLIUM_DRIVER='llvmpipe')
    for member in capture['members']:
        if member['identity']['pid'] == capture['pid'] and member.get('selected_environment') != expected:
            issues.append('Actual Gazebo selected environment mismatch')
    if 'swrast_dri.so' not in paths:
        issues.append('Missing actual swrast_dri mapping')
    if 'libllvm' not in paths:
        issues.append('Missing actual LLVM mapping')
    if 'libd3d12' in paths or '/usr/lib/wsl/drivers/' in paths:
        issues.append('Unexpected actual WSL/D3D12 driver mapping')
    return issues


def stream_update(item, message, now):
    """No pixels retained. Invalid/duplicate source stamps never satisfy gates."""
    stamp = message.header.stamp.sec * 1000000000 + message.header.stamp.nsec
    item['last_callback_monotonic_s'] = now
    if (message.width <= 0 or message.height <= 0 or not message.data
            or message.header.stamp.sec < 0 or not 0 <= message.header.stamp.nsec < 1000000000):
        item['invalid'] += 1
        return
    item['nonempty_callbacks'] += 1
    item['last_receive_monotonic_s'] = now
    if item['last_source_ns'] is None or stamp > item['last_source_ns']:
        item['increasing_frames'] += 1
        if item['first_source_ns'] is None:
            item['first_source_ns'] = stamp
        item.update(last_source_ns=stamp, width=message.width, height=message.height,
                    data_size=len(message.data))


def subscription_receipt(value):
    """The inherited signature is known; its native return contract is not."""
    return dict(type_name=type(value).__name__, kind='NONE' if value is None else 'RETURNED',
                value=value if value is None or type(value) in (bool,int,str) else repr(value)[:256])


def subscriber_worker(connection, env, topics):
    """Own native singleton and callbacks in a separately reapable process."""
    try:
        require(os.getpgid(os.getpid()) == os.getpid(), 'Subscriber requires its own process group')
        os.environ.update({key:env[key] for key in ('GZ_PARTITION', 'GZ_IP')})
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        from gz.msgs10.world_control_pb2 import WorldControl
        from gz.msgs10.boolean_pb2 import Boolean
        require(WorldControl.DESCRIPTOR.fields_by_name['pause'].type == 8,
                'Installed WorldControl.pause is not protobuf bool')
        require(Boolean.DESCRIPTOR.fields_by_name['data'].type == 8,
                'Installed Boolean.data is not protobuf bool')
        for field in ('header', 'width', 'height', 'data'):
            require(field in Image.DESCRIPTOR.fields_by_name, 'Installed Image missing ' + field)
        Image().header.stamp.sec; Image().header.stamp.nsec
        node, guard = Node(), threading.Lock()
        streams = {topic:dict(increasing_frames=0, first_source_ns=None, last_source_ns=None,
                    last_receive_monotonic_s=None, last_callback_monotonic_s=None,
                    nonempty_callbacks=0, invalid=0) for topic in topics}
        callbacks, callback_errors, subscribe_calls = {}, [], {}
        def callback(topic):
            def receive(message):
                try:
                    with guard:
                        stream_update(streams[topic], message, time.monotonic())
                except BaseException as error:
                    with guard:
                        callback_errors.append(type(error).__name__ + ':' + str(error))
            return receive
        for topic in topics:
            callbacks[topic] = callback(topic)
            subscribe_calls[topic] = subscription_receipt(node.subscribe(Image, topic, callbacks[topic]))
        connection.send(dict(event='ready', identity=identity(os.getpid()),
            schemas=dict(image=Image.DESCRIPTOR.full_name, world_control=WorldControl.DESCRIPTOR.full_name,
                         boolean=Boolean.DESCRIPTOR.full_name), subscribe_calls=subscribe_calls))
        while True:
            command = connection.recv()
            if command == 'snapshot':
                with guard:
                    result = dict(streams=deepcopy(streams), callback_errors=list(callback_errors))
                result.update(services=list(node.service_list()), utc=utc(), monotonic_s=time.monotonic())
                connection.send(result)
            elif command == 'close':
                for topic in topics:
                    node.unsubscribe(topic)
                with guard:
                    result = dict(event='unsubscribed', streams=deepcopy(streams), callback_errors=list(callback_errors))
                connection.send(result)
                break
            else:
                raise ValueError('Unknown owned subscriber request')
    except BaseException as error:
        try:
            connection.send(dict(event='error', error=type(error).__name__ + ':' + str(error)))
        except (EOFError, BrokenPipeError):
            pass
        raise
    finally:
        connection.close()


class Participant:
    def __init__(self, name, process):
        self.name, self.process = name, process
        self.pid = process.pid
        self.creation = None
        self.signals = []
    def poll(self):
        return self.process.poll()
    def wait(self, seconds):
        return self.process.wait(timeout=max(0., seconds))


def terminate_owned(participant, events, budgets, *, phase, captures=None):
    """Cleanup never returns an acceptance verdict or alters an earlier error."""
    for signum, grace in zip((signal.SIGINT, signal.SIGTERM, signal.SIGKILL), budgets):
        remaining = group_members(participant.pid)
        if participant.poll() is not None and not remaining:
            break
        leader = next((item for item in remaining if item['pid'] == participant.pid), None)
        if leader is not None and participant.creation is not None:
            require((leader['boot_id'], leader['start_ticks']) ==
                    (participant.creation['boot_id'], participant.creation['start_ticks']),
                    'Refusing signal after owned PID creation identity changed')
        # A still-unreaped owned leader can be cleaned directly if group evidence
        # is unavailable. Never signal an inherited or unrelated group.
        signal_group = bool(remaining)
        if not signal_group:
            require(participant.poll() is None, 'No owned signal recipient remains')
            remaining = [identity(participant.pid)]
        if captures is not None:
            captures.append(snapshot(participant.pid))
        beginning = time.monotonic()
        event = dict(participant=participant.name, phase=phase, signal=signum.name,
            utc=utc(), monotonic_s=beginning, deadline_monotonic_s=beginning + grace,
            grace_s=grace, pgid=participant.pid if signal_group else None,
            scope='owned_process_group' if signal_group else 'owned_leader_only', recipients=remaining)
        events.append(event); participant.signals.append(signum.name)
        journal(dict(event='signal_requested', **event))
        try:
            (os.killpg if signal_group else os.kill)(participant.pid, signum)
        except ProcessLookupError:
            participant.wait(0.1)
        try:
            participant.wait(event['deadline_monotonic_s'] - time.monotonic())
        except subprocess.TimeoutExpired:
            event['wait_timeout'] = True
        event.update(observed_exit=participant.poll(), observed_utc=utc(), observed_monotonic_s=time.monotonic())
        journal(dict(event='signal_wait_finished', **event))
    return dict(name=participant.name, creation=participant.creation, exit_code=participant.poll(),
                signals=participant.signals, residual=group_members(participant.pid))


@contextmanager
def exclusive_locks(output):
    import fcntl
    handles = []
    try:
        for path in (WINDOW_LOCK, MACHINE_LOCK, output / '.run.lock'):
            stream = path.open('a+b')
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                stream.close(); raise
            handles.append(stream)
        yield
    finally:
        for stream in reversed(handles):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN); stream.close()


def decision(report):
    errors = list(report['errors'])
    required = ('binding_verified', 'subscriber_ready', 'paused_start_observed', 'unpause_ack',
                'rgbd_gate', 'pause_ack', 'drain_gate', 'renderer_verified', 'gazebo_clean_initial_exit',
                'subscriber_clean_exit', 'all_owned_cleaned', 'kernel_evidence_captured')
    errors += ['Missing successful evidence: ' + key for key in required if report.get(key) is not True]
    errors += ['Owned process SIGTERM/SIGKILL: ' + item['participant'] for item in report['signal_events']
               if item['signal'] in ('SIGTERM', 'SIGKILL')]
    return dict(status='FAIL' if errors else 'PASS', errors=errors)


def clean_initial_exit(result, events):
    first = next((event for event in events if event['participant']=='gazebo'), None)
    return bool(first and first['signal']=='SIGINT' and not first.get('wait_timeout')
        and first['observed_exit']==0 and first['observed_monotonic_s'] <= first['deadline_monotonic_s']
        and first.get('scope')=='owned_process_group'
        and result['signals']==['SIGINT'] and not result['residual'])


def run(args):
    global JOURNAL
    require(os.name == 'posix' and sys.platform.startswith('linux') and
            os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22', 'Actual isolated WSL UAVHumble22 is required')
    require(args.execute_owned_diagnostic, 'Explicit diagnostic execution switch required')
    require((args.seed, args.lp_threads, args.omp_threads) == (5, 4, 2), 'This diagnostic requires original seed5/LP4/OMP2')
    require((args.sigint_grace, args.sigterm_grace, args.sigkill_grace) == (8., 5., 3.), 'Original 8/5/3 budgets required')
    require(args.min_frames >= 2 and len(args.image_topic) == 2 and len(set(args.image_topic)) == 2,
            'Exactly two distinct RGB/Depth Image topics and at least two increasing frames required')
    for budget in (args.startup_timeout, args.drain_timeout, args.quiet_s):
        require(budget > 0 and budget <= 120, 'Invalid bounded lifecycle allowance')
    source = args.source_root.resolve(strict=True)
    world = args.world.resolve(strict=True)
    probe = args.probe_source.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), 'Diagnostic output must be new')
    require(source not in output.parents and output != source, 'Output must be outside frozen source root')
    require(output.name.startswith('humble42_shutdown_diag_'), 'Explicit fresh diagnostic output prefix required')
    bindings = [(source / 'scripts/run_stage1_trial.py', args.runner_sha256),
                (source / 'scripts/run_stage1_flight.sh', args.launcher_sha256),
                (probe, args.probe_sha256), (world, args.world_sha256),
                (Path(__file__).resolve(), args.tool_sha256)]
    for path, expected in bindings:
        require(re.fullmatch('[a-f0-9]{64}', expected) and sha(path) == expected, 'Binding mismatch: ' + str(path))
    worlds = ET.parse(world).getroot().findall('world')
    require(len(worlds) == 1 and worlds[0].get('name') == args.world_name, 'Actual world name mismatch')
    spec = importlib.util.spec_from_file_location('frozen_shutdown_probe_primitives', probe)
    primitives = importlib.util.module_from_spec(spec); spec.loader.exec_module(primitives)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='OWNED_RENDERER_ONLY_RGBD_SHUTDOWN_DIAGNOSTIC', status='FAIL',
        started_utc=utc(), bindings=[dict(path=str(path), sha256=expected) for path, expected in bindings],
        tool_sha256=sha(__file__), errors=[], signal_events=[], process_captures=[], helpers=[],
        locks=[str(WINDOW_LOCK), str(MACHINE_LOCK), str(output / '.run.lock')],
        parameters=vars(args) | {'source_root':str(source), 'world':str(world), 'output':str(output), 'probe_source':str(probe)},
        bounds=BOUNDS, limitations=['Not a complete75s original09 reproduction, repair, or formal admission.',
        'Observed callback quiescence is not a rosbag/full-recorder source-stream closure proof.',
        'Finite dmesg error/warning ring evidence cannot exclude historical OOM or identify an unrecorded prior signal sender.'])
    report['parameters'] = {key:str(value) if isinstance(value, Path) else value for key,value in report['parameters'].items()}
    report['binding_verified'] = True
    participants, gazebo, subscriber, connection = [], None, None, None
    partition = 'uav_shutdown_smoke_' + uuid.uuid4().hex
    env = primitives.owned_environment(partition, args.resource_path, args.plugin_path, args.lp_threads)
    env['OMP_NUM_THREADS'] = str(args.omp_threads)
    require(not env.get('LD_PRELOAD'), 'A preloaded driver is outside this diagnostic contract')
    gazebo_env = dict(env, LIBGL_ALWAYS_SOFTWARE='1', MESA_LOADER_DRIVER_OVERRIDE='swrast', GALLIUM_DRIVER='llvmpipe')
    report.update(partition=partition, selected_environment={key:gazebo_env.get(key) for key in
        ('GZ_PARTITION','GZ_IP','LP_NUM_THREADS','OMP_NUM_THREADS','LIBGL_ALWAYS_SOFTWARE','MESA_LOADER_DRIVER_OVERRIDE','GALLIUM_DRIVER')})
    def alive():
        require(gazebo is not None and gazebo.poll() is None, 'Gazebo exited during lifecycle')
        require(subscriber is not None and subscriber.poll() is None, 'Native subscriber exited during lifecycle')
    def request(command):
        connection.send(command)
        require(connection.poll(2.), 'Native subscriber request timeout')
        result = connection.recv()
        require(result.get('event') != 'error' and not result.get('callback_errors'), 'Native subscriber failure: ' + str(result))
        return result
    def helper(name, command, timeout=8.):
        log_path = output / (name + '.log')
        with log_path.open('x', encoding='utf-8') as stream:
            child = Participant(name, subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True))
            participants.append(child); child.creation = identity(child.pid)
            journal(dict(event='participant_started',name=name,creation=child.creation))
            started = time.monotonic()
            try:
                code = child.wait(timeout)
            except subprocess.TimeoutExpired:
                terminate_owned(child, report['signal_events'], (2., 2., 1.), phase='helper_failure_cleanup')
                raise
        require(not group_members(child.pid), 'Owned helper descendants remain: ' + name)
        text = read_bounded(log_path, 262144)
        report['helpers'].append(dict(name=name, command=command, creation=child.creation,
            exit_code=code, elapsed_wall_s=time.monotonic()-started, log=str(log_path)))
        return code, text
    def kernel(name):
        code, text = helper(name, ['dmesg', '--level=err,warn', '--ctime'])
        require(code == 0, 'Kernel error/warning ring was inaccessible')
        matches = [line for line in text.splitlines() if re.search(r'oom|out of memory|killed process|gazebo|gz sim', line, re.I)]
        report[name] = dict(lines=len(text.splitlines()), matches=matches,
            scope='Finite currently retained error/warning ring; absence does not exclude historical OOM')
    previous = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Owned diagnostic received ' + signal.Signals(signum).name)
    with exclusive_locks(output):
        JOURNAL = output / 'events.jsonl'
        with JOURNAL.open('x', encoding='utf-8'):
            pass
        new_json(output / 'registration.json', report)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        try:
            kernel('kernel_before')
            connection, child_connection = multiprocessing.Pipe()
            with (output / 'native_subscriber.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--subscriber-worker',
                    str(child_connection.fileno()), json.dumps(args.image_topic)], env=env,
                    pass_fds=(child_connection.fileno(),), stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            child_connection.close()
            subscriber = Participant('native_rgbd_subscriber', process); participants.append(subscriber)
            subscriber.creation = identity(subscriber.pid)
            journal(dict(event='participant_started',name=subscriber.name,creation=subscriber.creation))
            require(connection.poll(10.), 'Native subscriber startup timeout')
            ready = connection.recv(); report['subscriber_start'] = ready
            require(ready.get('event') == 'ready' and ready['identity']['pgid'] == subscriber.pid,
                    'Native subscriber did not establish its owned process group')
            require((ready['identity']['boot_id'],ready['identity']['start_ticks']) ==
                (subscriber.creation['boot_id'],subscriber.creation['start_ticks']), 'Subscriber startup identity mismatch')
            report['subscriber_ready'] = True
            command = ['gz','sim','--seed',str(args.seed),'-s','--headless-rendering',str(world)]
            report['gazebo_command'] = command
            with (output / 'gazebo.log').open('x', encoding='utf-8') as log:
                gazebo = Participant('gazebo', subprocess.Popen(command, env=gazebo_env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
            participants.append(gazebo); gazebo.creation = identity(gazebo.pid)
            journal(dict(event='participant_started',name=gazebo.name,creation=gazebo.creation))
            require(gazebo.creation['pgid'] == gazebo.pid, 'Gazebo PGID ownership mismatch')
            service = '/world/' + args.world_name + '/control'
            deadline = time.monotonic() + args.startup_timeout
            while True:
                alive(); state = request('snapshot')
                if service in state['services']:
                    break
                require(time.monotonic() < deadline, 'Paused world control discovery timeout'); time.sleep(.05)
            before = state
            time.sleep(args.quiet_s); alive(); paused = request('snapshot')
            require(all(paused['streams'][topic]['increasing_frames'] <= 1 and
                paused['streams'][topic]['increasing_frames'] == before['streams'][topic]['increasing_frames']
                for topic in args.image_topic), 'Started world did not remain paused')
            report.update(paused_start_observed=True, paused_start=paused)
            def world_control(name, pause):
                code, text = helper(name, ['gz','service','-s',service,'--reqtype','gz.msgs.WorldControl',
                    '--reptype','gz.msgs.Boolean','--timeout','5000','--req','pause: ' + str(pause).lower()])
                require(primitives.response_acknowledged(code, text), 'World control request not acknowledged: ' + name)
            world_control('unpause', False); report['unpause_ack'] = True
            deadline = time.monotonic() + args.startup_timeout
            while True:
                alive(); state = request('snapshot')
                if all(state['streams'][topic]['increasing_frames'] - paused['streams'][topic]['increasing_frames'] >= args.min_frames for topic in args.image_topic):
                    break
                require(time.monotonic() < deadline, 'Actual increasing RGB-D gate timeout'); time.sleep(.05)
            report.update(rgbd_gate=True, rgbd_evidence=state)
            capture = snapshot(gazebo.pid); report['process_captures'].append(capture)
            report['errors'] += capture['errors'] + rendering_issues(capture)
            report['renderer_verified'] = not rendering_issues(capture)
            world_control('pause', True); report['pause_ack'] = True
            deadline = time.monotonic() + args.drain_timeout
            while True:
                alive(); state = request('snapshot'); now = time.monotonic()
                if all(now - state['streams'][topic]['last_callback_monotonic_s'] >= args.quiet_s for topic in args.image_topic):
                    break
                require(now < deadline, 'RGB-D callback drain timeout'); time.sleep(.05)
            report.update(drain_gate=True, drain_evidence=state, drain_utc=utc())
            result = terminate_owned(gazebo, report['signal_events'], (8.,5.,3.), phase='diagnostic_stop', captures=report['process_captures'])
            report['gazebo_stop'] = result
            report['gazebo_clean_initial_exit'] = clean_initial_exit(result, report['signal_events'])
        except BaseException as error:
            report['errors'].append(type(error).__name__ + ':' + str(error))
        finally:
            # Cleanup is separately recorded and cannot rehabilitate an earlier failure.
            for signum in previous:
                signal.signal(signum, signal.SIG_IGN)
            report['cleanup'] = []
            if gazebo is not None:
                try:
                    report['cleanup'].append(terminate_owned(gazebo, report['signal_events'], (8.,5.,3.), phase='failure_cleanup'))
                except BaseException as error:
                    report['errors'].append('Gazebo cleanup: ' + str(error))
            if subscriber is not None:
                try:
                    closed = request('close'); report['subscriber_closed'] = closed
                    subscriber.wait(2.)
                    report['subscriber_clean_exit'] = closed.get('event')=='unsubscribed' and subscriber.poll()==0 and not group_members(subscriber.pid)
                except BaseException as error:
                    report['errors'].append('Native subscriber cleanup: ' + str(error))
                try:
                    report['cleanup'].append(terminate_owned(subscriber, report['signal_events'], (2.,2.,1.), phase='subscriber_failure_cleanup'))
                except BaseException as error:
                    report['errors'].append('Native subscriber forced cleanup: ' + str(error))
            if connection is not None:
                connection.close()
            try:
                kernel('kernel_after'); report['kernel_evidence_captured'] = 'kernel_before' in report
            except BaseException as error:
                report['errors'].append('Kernel evidence: ' + str(error))
            for participant in participants:
                try:
                    result = terminate_owned(participant, report['signal_events'], (2.,2.,1.), phase='final_owned_cleanup')
                    if result['residual'] or result['exit_code'] is None:
                        report['errors'].append('Remaining owned participant: ' + participant.name)
                except BaseException as error:
                    report['errors'].append('Owned cleanup: ' + participant.name + ':' + str(error))
            report['all_owned_cleaned'] = not any(participant.poll() is None or group_members(participant.pid) for participant in participants)
            for capture in report['process_captures']:
                report['errors'] += [error for error in capture['errors'] if error not in report['errors']]
            report['optional_diagnostic_gaps'] = [error for capture in report['process_captures']
                for error in capture['optional_errors']]
            report['participants'] = [dict(name=item.name, creation=item.creation, exit_code=item.poll(), signals=item.signals) for item in participants]
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            report.update(decision(report)); report['finished_utc'] = utc()
            new_json(output / 'report.json', report)
    print(json.dumps({key:report.get(key) for key in ('status','errors','gazebo_clean_initial_exit','subscriber_clean_exit','all_owned_cleaned')}, indent=2), flush=True)
    return report


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','probe-source','world','output'):
        value.add_argument('--'+name, type=Path, required=True)
    for name in ('runner-sha256','launcher-sha256','probe-sha256','world-sha256','tool-sha256','world-name'):
        value.add_argument('--'+name, required=True)
    for name in ('seed','lp-threads','omp-threads','min-frames'):
        value.add_argument('--'+name, type=int, required=True)
    for name in ('sigint-grace','sigterm-grace','sigkill-grace'):
        value.add_argument('--'+name, type=float, required=True)
    value.add_argument('--resource-path', action='append', default=[])
    value.add_argument('--plugin-path', action='append', default=[])
    value.add_argument('--image-topic', action='append', required=True)
    value.add_argument('--startup-timeout', type=float, default=45.)
    value.add_argument('--drain-timeout', type=float, default=10.)
    value.add_argument('--quiet-s', type=float, default=.5)
    value.add_argument('--execute-owned-diagnostic', action='store_true')
    return value


if __name__ == '__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--subscriber-worker':
        from multiprocessing.connection import Connection
        require(os.name=='posix' and os.environ.get('WSL_DISTRO_NAME')=='UAVHumble22', 'Native worker requires UAVHumble22')
        require(re.fullmatch('uav_shutdown_smoke_[a-f0-9]{32}',os.environ.get('GZ_PARTITION','')), 'Native worker requires owned partition')
        subscriber_worker(Connection(int(sys.argv[2])),os.environ,json.loads(sys.argv[3]))
        raise SystemExit(0)
    raise SystemExit(0 if run(parser().parse_args())['status']=='PASS' else 2)
