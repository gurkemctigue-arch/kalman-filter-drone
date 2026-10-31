"""Run the actual sealed formal guard with the reviewed native health owner.

This adapter creates no registration, seal, plan or permission. The unchanged
guard selects one PENDING slot and owns all admission, locking and capacity.
Import and describe are inert. Actual run-one requires a separately reviewed
adapter digest and the exact already sealed manifest digest.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from types import SimpleNamespace

import local_runtime_observer41 as owner

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'FORMAL41_ORIGINAL_GUARD_WITH_NATIVE_HEALTH_OWNER_NO_NEW_ADMISSION'
OWN = ('formal41_guard_adapter01.py', 'formal41_guard_adapter01.sh',
       'test_formal41_guard_adapter01.py')
OWNER_TOOLS_SHA = 'e558bf367038a2bb3530d7e5a8ea3e3fae7eb84ac19d02acedecc7c5c2be3ea3'
COLLECTOR_SHA = 'f174ec21ebf962f156d76f8d35f802eebf318163555815527a3e2227b914f180'
MAX_METADATA = 128 * 1024**2
GUARD_RELATIVE = 'tools/reliability_v4_guard.py'
COLLECTOR_RELATIVE = 'scripts/observe_runtime_health.py'
RUNNER_RELATIVE = 'scripts/run_reliability_v4.py'
OWNED_NAME = 'formal41_owned01'


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def file_bytes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_METADATA,
            'Missing, linked or oversized named metadata/source')
    data = path.read_bytes()
    require(len(data) <= MAX_METADATA, 'Named metadata/source grew beyond its limit')
    return data


def binding(path):
    path = Path(path)
    raw = file_bytes(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(raw).hexdigest()}


def parse_json(data):
    value = json.loads(data.decode('utf-8'), parse_constant=lambda item: (_ for _ in ()).throw(
        ValueError('Non-finite JSON constant: '+item)))
    require(isinstance(value, dict), 'JSON metadata must be an object')
    return value


def bound_json(item):
    require(isinstance(item, dict) and set(item) == {'path', 'sha256'}
            and valid_sha(item['sha256']) and Path(item['path']).is_absolute(),
            'Exact absolute path/SHA binding required')
    path = Path(item['path'])
    raw = file_bytes(path)
    require(binding(path) == item and hashlib.sha256(raw).hexdigest() == item['sha256'],
            'Bound original metadata/source changed')
    return path.resolve(strict=True), parse_json(raw)


def write_new(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode('utf-8')
    require(len(raw) <= MAX_METADATA, 'Owned metadata exceeds its bound')
    with Path(path).open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def tool_manifest():
    require(Path(owner.__file__).resolve(strict=True) ==
            (EXTERNAL/'local_runtime_observer41.py').resolve(strict=True)
            and canonical(owner.tool_manifest()) == OWNER_TOOLS_SHA,
            'Reviewed native owner source/test changed')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {name: binding(EXTERNAL/name)['sha256'] for name in OWN},
        'owner_tools_canonical_sha256': OWNER_TOOLS_SHA, 'collector_sha256': COLLECTOR_SHA,
        'actions': ['describe', 'run-one'], 'default_manifest': None,
        'guard_api': 'actual manifest.tool execute_one(command_runner=observed_runner)',
        'guard_argv_or_slot_or_capacity_modified': False, 'additional_sitl_lock': False,
        'owner_actual_terminal_persisted_before_command_return': True,
        'sample_max_age_wall_s': 10., 'owner_archive_wall_budget_s': 1800.,
        'native_session_wall_s': 7200., 'rotation_wall_s': 5400.,
        'owned_child_cleanup_graces_s': [240, 30, 10],
        'automatic_retry': False, 'registration_or_seal_created': False,
        'local_raw_evidence_removed': False,
        'authorization_source': 'Unchanged actual sealed guard only; adapter grants no admission'}


def load_context(path, expected_sha, reviewed_tools_sha):
    require(valid_sha(expected_sha) and valid_sha(reviewed_tools_sha)
            and canonical(tool_manifest()) == reviewed_tools_sha,
            'Exact reviewed adapter and already sealed manifest digests required')
    path = Path(path)
    require(path.is_absolute() and not path.is_symlink(), 'Original absolute manifest required')
    manifest_binding = binding(path)
    require(manifest_binding['sha256'] == expected_sha, 'Original sealed manifest digest changed')
    _, manifest = bound_json(manifest_binding)
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1
            and manifest.get('kind') == 'RELIABILITY_V4_FORMAL_ADMISSION'
            and manifest.get('manifest_sha256') == canonical({key: value for key, value in manifest.items()
                                                            if key != 'manifest_sha256'}),
            'Actual sealed formal admission is required; no candidate or invented seal')
    root = Path(manifest.get('final_root', ''))
    require(root.is_absolute() and root.is_dir() and root.resolve(strict=True) == root,
            'Sealed actual final root must already exist without an alias')
    state = Path(manifest.get('state_directory', '')).resolve()
    results = (root/'results').resolve(strict=True)
    require(state != results and state.is_relative_to(results), 'Original guard state escaped final results')
    plans = {}
    for label, mode in (('core', 'FORMAL'), ('extension', 'EXTENSION_FORMAL')):
        plan_path, plan = bound_json(manifest.get('plans', {}).get(label))
        require(plan.get('mode') == mode and plan.get('frozen_root') == str(root),
                'Both original final-root formal plan bindings are required')
        plans[label] = {'path': plan_path, 'data': plan, 'binding': manifest['plans'][label]}
    require(plans['core']['data'].get('source_hashes') == plans['extension']['data'].get('source_hashes')
            and isinstance(plans['core']['data'].get('source_hashes'), dict),
            'Actual formal plans must bind identical frozen source')
    sources = plans['core']['data']['source_hashes']
    tool = manifest.get('tool')
    require(isinstance(tool, dict) and set(tool) == {'path', 'sha256'}
            and Path(tool['path']).is_absolute()
            and valid_sha(tool['sha256']),
            'Sealed manifest must name its actual original guard path/SHA')
    guard_source = file_bytes(tool['path'])
    require(hashlib.sha256(guard_source).hexdigest() == tool['sha256'], 'Original bound guard source changed')
    collector = binding(root/COLLECTOR_RELATIVE)
    require(collector['sha256'] == sources.get(COLLECTOR_RELATIVE) == COLLECTOR_SHA,
            'Actual final-root collector is not the reviewed native tmpfs source')
    context = SimpleNamespace(path=Path(manifest_binding['path']), manifest=manifest,
        manifest_binding=manifest_binding, root=root, state=state, plans=plans,
        tool=tool, guard_source=guard_source, collector=collector,
        reviewed_tools_sha=reviewed_tools_sha)
    verify_inputs(context)
    return context


def verify_inputs(context):
    require(binding(context.path) == context.manifest_binding, 'Original sealed manifest changed')
    require(binding(context.tool['path']) == context.tool, 'Original sealed guard source changed')
    for plan in context.plans.values():
        require(binding(plan['path']) == plan['binding'], 'Original formal plan changed')
    require(binding(context.root/COLLECTOR_RELATIVE) == context.collector,
            'Actual final-root collector source changed')
    require(canonical(tool_manifest()) == context.reviewed_tools_sha, 'Reviewed adapter/owner tools changed')


def load_original_guard(context):
    """Execute the same already hashed bytes, never a second pathname read."""
    verify_inputs(context)
    name = '_formal41_original_guard_'+context.tool['sha256']
    spec = importlib.util.spec_from_file_location(name, context.tool['path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(context.guard_source, context.tool['path'], 'exec'), module.__dict__)
    require(Path(module.__file__).resolve(strict=True) == Path(context.tool['path'])
            and binding(context.tool['path']) == context.tool, 'Original guard path/bytes changed during import')
    return module


def require_runtime(context):
    require(os.name == 'posix' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and os.environ.get('ROS_DISTRO') == 'humble'
            and os.environ.get('STAGE1_PROJECT_ROOT') == str(context.root)
            and os.environ.get('STAGE1_ROS_DISTRO') == 'humble',
            'Use the explicit isolated Humble wrapper for the actual sealed final root')


def simulation_processes(context):
    module = sys.modules.get('run_reliability_v4')
    require(module is not None and Path(module.__file__).resolve(strict=True) == context.root/RUNNER_RELATIVE
            and binding(module.__file__)['sha256'] == context.plans['core']['data']['source_hashes'].get(RUNNER_RELATIVE),
            'Actual original guard did not load its bound frozen runner')
    return module.simulation_processes()


def stop_child(process, actions):
    """Signal only this owned runner; its original finally owns the flight graph."""
    if process is not None:
        for sent, grace in ((signal.SIGINT, 240), (signal.SIGTERM, 30),
                            (getattr(signal, 'SIGKILL', signal.SIGTERM), 10)):
            if process.poll() is not None:
                break
            process.send_signal(sent)
            actions.append({'signal': int(sent), 'grace_s': grace})
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                continue
        require(process.poll() is not None, 'Owned original runner survived its unchanged cleanup graces')


class ObservedRunner:
    def __init__(self, context, signals=None):
        self.context = context
        self.signals = signals or SimpleNamespace(child_live=False, requested=[])
        self.directory = None
        self.calls = 0

    def __call__(self, command, *, cwd, stdout, stderr, check):
        require(self.calls == 0, 'Original guard may invoke only one owned runner; no retry')
        self.calls += 1
        context = self.context
        verify_inputs(context)
        require(Path(cwd) == context.root and stderr == subprocess.STDOUT and check is False,
                'Original guard callback cwd/stream/check semantics changed')
        log = Path(stdout.name).resolve(strict=True)
        invocation = log.parent
        require(log.name == 'runner.log' and invocation.parent == context.state
                and re.fullmatch(r'[0-9]{8}T[0-9]{6}_[0-9a-f]{32}', invocation.name),
                'Owned output must be the original guard invocation runner.log')
        admission_path = invocation/'admission.json'
        admission = parse_json(file_bytes(admission_path))
        require(admission.get('kind') == 'RELIABILITY_V4_GUARD_ADMISSION_CHECK'
                and admission.get('result') == 'PASS' and admission.get('command') == command
                and admission.get('manifest') == context.manifest_binding
                and admission.get('manifest_sha256') == context.manifest['manifest_sha256']
                and admission.get('tool') == context.tool,
                'Original guard admission/command binding changed')
        directory = invocation/OWNED_NAME
        require(not directory.exists() and not directory.is_symlink(), 'Owned invocation already exists; no overwrite')
        directory.mkdir(exist_ok=False)
        self.directory = directory
        started = {'schema_version': 1, 'scope': SCOPE, 'started_utc': utc(),
            'manifest': context.manifest_binding, 'guard': context.tool,
            'admission': binding(admission_path), 'command': command, 'cwd': str(cwd),
            'tools_canonical_sha256': context.reviewed_tools_sha, 'automatic_retry': False}
        write_new(directory/'started.json', started)
        observer, process = None, None
        errors, cleanup = [], []
        execution = {'command': command, 'cwd': str(cwd), 'started_utc': None,
            'finished_utc': None, 'returncode': None, 'outer_cleanup_actions': cleanup,
            'forced_stop': False, 'stop_requests': self.signals.requested}
        actual, validated = None, None
        try:
            observer = owner.make_observer(directory/'observer_driver', context.root,
                                           archive_wall_budget_s=1800.)
            with observer:
                try:
                    require(not self.signals.requested, 'Stop requested before owned runner startup')
                    observer.check()
                    execution['started_utc'] = utc()
                    self.signals.child_live = True
                    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                        stdout=stdout, stderr=stderr, start_new_session=True)
                    while process.poll() is None:
                        observer.check()
                        try:
                            process.wait(timeout=1.)
                        except subprocess.TimeoutExpired:
                            continue
                    execution['returncode'] = process.poll()
                    execution['finished_utc'] = utc()
                    self.signals.child_live = False
                    observer.check()
                except BaseException:
                    # Defer repeated stop signals while the original child
                    # completes its bounded cleanup and the owner closes.
                    self.signals.child_live = False
                    stop_child(process, cleanup)
                    raise
        except BaseException as error:
            errors.append(type(error).__name__+':'+str(error))
        finally:
            self.signals.child_live = False
            if process is not None:
                try:
                    if process.poll() is None and not cleanup:
                        stop_child(process, cleanup)
                    require(process.poll() is not None, 'Owned runner remained alive after original cleanup')
                except BaseException as error:
                    errors.append('cleanup:'+type(error).__name__+':'+str(error))
                execution['returncode'] = process.poll()
                execution['finished_utc'] = execution['finished_utc'] or utc()
            execution['forced_stop'] = bool(cleanup)
            if observer is not None:
                try:
                    if observer._finished is None:
                        observer.finish(exception=bool(errors))
                except BaseException as error:
                    errors.append('owner_finish:'+type(error).__name__+':'+str(error))
                actual = observer._finished
            if self.signals.requested:
                errors.append('Stop requested; native/archive closure retained before original guard STOP')
            # Persist the actual post-wait outcome before validation or return.
            write_new(directory/'owner_result.json', {'schema_version': 1, 'scope': SCOPE,
                'manifest': context.manifest_binding, 'admission': started['admission'],
                'observer_owner_terminal': actual, 'command_execution': execution,
                'errors_observed_before_validation': list(errors)})
            try:
                validated = owner.validate_observer_root(actual, directory/'observer_driver', context.root)
            except BaseException as error:
                errors.append('observer:'+type(error).__name__+':'+str(error))
            try:
                verify_inputs(context)
                require(simulation_processes(context) == [], 'Residual flight graph after owned runner cleanup')
                require(cleanup == [], 'Owned runner required forced outer cleanup')
            except BaseException as error:
                errors.append('final:'+type(error).__name__+':'+str(error))
            write_new(directory/'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE,
                'finished_utc': utc(), 'manifest': context.manifest_binding,
                'admission': started['admission'], 'owner_result': binding(directory/'owner_result.json'),
                'observer_owner_terminal': actual, 'observer': validated,
                'command_execution': execution, 'errors': errors,
                'status': 'ORIGINAL_COMMAND_AND_OWNER_CLOSED' if not errors else 'STOP_REQUIRED',
                'automatic_retry': False, 'original_slot_modified': False})
        require(not errors and validated is not None, 'Owned health/command failed; original guard must STOP: '+';'.join(errors))
        require(not self.signals.requested, 'Stop requested before original guard callback returned')
        return subprocess.CompletedProcess(command, execution['returncode'])

    def retain_guard_outcome(self, result):
        if self.directory is None:
            return
        invocation = self.directory.parent
        outcome_path = invocation/'outcome.json'
        require(parse_json(file_bytes(outcome_path)) == result, 'Original guard returned another outcome')
        write_new(self.directory/'guard_outcome_binding.json', {'schema_version': 1, 'scope': SCOPE,
            'created_utc': utc(), 'original_outcome': binding(outcome_path),
            'original_admission': binding(invocation/'admission.json'),
            'owned_terminal': binding(self.directory/'execution_terminal.json'),
            'owner_result': binding(self.directory/'owner_result.json'),
            'result': result.get('result'), 'slot_id': result.get('slot_id'),
            'stop_requests': list(self.signals.requested),
            'original_slot_modified': False, 'automatic_retry': False})


@contextmanager
def stop_signals():
    previous = {}
    state = SimpleNamespace(child_live=False, requested=[])
    def interrupt(number, frame):
        state.requested.append(int(number))
        if state.child_live:
            raise KeyboardInterrupt('Requested stop signal '+str(number))
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, interrupt)
        yield state
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_one(context, resolutions=None):
    require_runtime(context)
    verify_inputs(context)
    guard = load_original_guard(context)
    with stop_signals() as signals:
        observed = ObservedRunner(context, signals)
        result = guard.execute_one(context.path, resolutions=resolutions or {}, command_runner=observed)
    observed.retain_guard_outcome(result)
    require(not observed.signals.requested or result.get('result') == 'STOP',
            'Stop requested after original guard closure; retain its outcome and stop the serial batch')
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'run-one'))
    result.add_argument('--manifest', type=Path)
    result.add_argument('--manifest-sha256')
    result.add_argument('--reviewed-tools-sha256')
    for label in ('core', 'extension'):
        result.add_argument('--'+label+'-resolution', type=Path)
        result.add_argument('--'+label+'-resolution-sha256')
    return result


def arguments_context(args):
    require(args.action == 'run-one' and args.manifest is not None,
            'Only actual sealed run-one is exposed')
    return load_context(args.manifest, args.manifest_sha256, args.reviewed_tools_sha256)


def shell_root(argv):
    return str(arguments_context(parser().parse_args(argv)).root)


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == 'describe':
        manifest = tool_manifest()
        print(json.dumps({'manifest': manifest, 'tools_canonical_sha256': canonical(manifest),
                          'actual_action_executed': False}, indent=2))
        return 0
    try:
        context = arguments_context(args)
        resolutions = {}
        for label in ('core', 'extension'):
            path, digest = getattr(args, label+'_resolution'), getattr(args, label+'_resolution_sha256')
            require((path is None) == (digest is None), 'Original resolution path/SHA must be supplied together')
            if path is not None:
                require(valid_sha(digest), 'Original resolution SHA required')
                resolutions[label] = {'path': str(path.resolve(strict=True)), 'sha256': digest}
        result = run_one(context, resolutions)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if result.get('result') == 'STOP' else 0
    except (OSError, ValueError, KeyError, TypeError, ImportError, StopIteration,
            RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'result': 'REFUSED', 'error': type(error).__name__+': '+str(error),
                          'new_slot_authorized': False}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
