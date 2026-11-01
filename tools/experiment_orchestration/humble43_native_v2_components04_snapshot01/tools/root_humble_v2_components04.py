"""One-shot native Humble component verification only after the complete core driver is idle."""
import json
import os
import re
import stat as stat_types
from pathlib import Path
import subprocess
import sys
import tempfile

import root_install_validate_v2_01 as shared

ROOT = Path(__file__).resolve().parent
EXTERNAL = ROOT.parent
FROZEN = Path('/root/uav_tracking_fullplan_v4_humble43')
OUTPUT = ROOT / 'root_humble_validation04'
EXPECTED = '83eebf67bfaafc02e1ae0f2a555b2d8408be40b5bc381be1063133dcf86c8afd'


class _ReadOnlyProcIO:
    """Bounded native reads only; this never opens the machine lock itself."""
    def lstat(self, path):
        return os.lstat(path)

    def identity(self, metadata):
        return os.major(metadata.st_dev), os.minor(metadata.st_dev), metadata.st_ino

    def read_proc_locks(self, proc_root, byte_limit):
        with (Path(proc_root) / 'locks').open('rb') as stream:
            raw = stream.read(byte_limit + 1)
        if len(raw) > byte_limit:
            raise RuntimeError('Original proc locks exceeds bounded read')
        return raw.decode('utf-8')

    def proc_fd_links(self, proc_root, limits):
        process_entries = process_count = total = 0
        with os.scandir(proc_root) as processes:
            for process in processes:
                process_entries += 1
                if process_entries > limits['proc_entries']:
                    raise RuntimeError('Proc directory enumeration exceeds bound')
                if not process.name.isdigit():
                    continue
                process_count += 1
                if process_count > limits['processes']:
                    raise RuntimeError('Proc process enumeration exceeds bound')
                # Keep scandir open while reading its entries, including self FD.
                with os.scandir(Path(proc_root) / process.name / 'fd') as descriptors:
                    per_process = 0
                    for descriptor in descriptors:
                        per_process += 1
                        total += 1
                        if per_process > limits['fds_per_process'] or total > limits['total_fds']:
                            raise RuntimeError('Proc FD enumeration exceeds bound')
                        if not descriptor.name.isdigit():
                            raise RuntimeError('Unexpected nonnumeric proc FD entry')
                        target = os.readlink(descriptor.path)
                        if len(target) > limits['link_chars']:
                            raise RuntimeError('Proc FD target exceeds bound')
                        yield {'pid': int(process.name), 'fd': descriptor.name, 'target': target}


def original_machine_lock_snapshot(lock_path='/tmp/uav_tracking_reliability_v4_sitl.lock',
                                   proc_root='/proc', io=None):
    """Observe ABSENT separately from FREE; any uncertainty defers, never locks."""
    io = _ReadOnlyProcIO() if io is None else io
    lock_path = os.fspath(lock_path)
    limits = {'proc_entries': 8192, 'processes': 4096, 'fds_per_process': 4096,
              'total_fds': 65536, 'link_chars': 4096, 'locks_bytes': 1024 * 1024}
    result = {'ready': False, 'state': 'UNVERIFIABLE', 'path': lock_path,
              'opened_or_modified': False, 'opened_fd_references': [], 'held_entries': [],
              'limits': limits, 'reasons': []}
    try:
        try:
            before = io.lstat(lock_path)
        except FileNotFoundError:
            before = None
            result['state'] = 'ABSENT'
        if before is not None and not stat_types.S_ISREG(before.st_mode):
            result['state'] = 'INVALID'
            result['reasons'].append('Original machine lock path is linked or not a regular file')
            return result
        lock_text = io.read_proc_locks(proc_root, limits['locks_bytes'])
        if not isinstance(lock_text, str) or len(lock_text.encode('utf-8')) > limits['locks_bytes']:
            raise RuntimeError('Invalid or oversized original proc locks text')
        rows = []
        for line in lock_text.splitlines():
            if not line.strip():
                continue
            identities = [re.fullmatch(r'([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9]+)', token)
                          for token in line.split()]
            identities = [item for item in identities if item is not None]
            if len(identities) != 1:
                raise RuntimeError('Original proc lock row cannot be verified')
            item = identities[0]
            rows.append(((int(item[1], 16), int(item[2], 16), int(item[3])), line))
        result['proc_locks_rows'] = len(rows)
        if before is None:
            count = 0
            for reference in io.proc_fd_links(proc_root, limits):
                count += 1
                if count > limits['total_fds']:
                    raise RuntimeError('Proc FD enumeration exceeds bound')
                if (not isinstance(reference, dict) or type(reference.get('pid')) is not int
                        or reference['pid'] <= 0 or not isinstance(reference.get('fd'), str)
                        or not reference['fd'].isdigit() or not isinstance(reference.get('target'), str)
                        or len(reference['target']) > limits['link_chars']):
                    raise RuntimeError('Original proc FD reference cannot be verified')
                if reference['target'] in (lock_path, lock_path + ' (deleted)'):
                    result['opened_fd_references'].append(dict(reference))
                    result['reasons'].append('Absent original machine lock still has an open FD reference')
                    return result
            result['proc_fd_links_checked'] = count
            try:
                io.lstat(lock_path)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('Original machine lock appeared during absent-path inspection')
            result['absence_cause'] = 'UNKNOWN_NOT_ATTRIBUTED_TO_ORIGINAL_RUNNER_UNLINK'
        else:
            identity = tuple(io.identity(before))
            if len(identity) != 3 or any(type(value) is not int or value < 0 for value in identity):
                raise RuntimeError('Original machine lock identity cannot be verified')
            result.update(major=identity[0], minor=identity[1], inode=identity[2])
            result['held_entries'] = [line for item, line in rows if item == identity]
            after = io.lstat(lock_path)
            if not stat_types.S_ISREG(after.st_mode) or tuple(io.identity(after)) != identity:
                raise RuntimeError('Original machine lock identity changed during inspection')
            result['state'] = 'HELD' if result['held_entries'] else 'FREE'
            if result['held_entries']:
                result['reasons'].append('Original machine SITL lock is still held')
                return result
        result['ready'] = True
    except (OSError, RuntimeError, ValueError, TypeError, UnicodeError) as error:
        result['state'] = 'UNVERIFIABLE'
        result['reasons'].append(type(error).__name__ + ': ' + str(error))
    return result


def core_idle_snapshot():
    """Bounded original metadata and live OS reads only; never acquire any lock."""
    matrix = FROZEN / 'results/reliability_v4_humble43_probe01_seed004_matrix'
    path = matrix / 'observed_driver01/execution_terminal.json'
    result = {'ready': False, 'core_terminal_path': str(path), 'reasons': []}
    if not path.is_file() or path.is_symlink():
        result['reasons'].append('Complete original core run terminal is absent or linked')
        return result
    if path.stat().st_size > 8 * 1024**2:
        raise RuntimeError('Core run terminal exceeds bounded metadata scope')
    raw = path.read_bytes(); value = json.loads(raw)
    result['core_terminal'] = {'path': str(path), 'sha256': shared.sha(path)}
    expected_ids = [cls+'_'+group+'_seed004' for cls in ('person', 'car') for group in
        ('stage1_velocity', 'stage1_position', 'stage2_crossing', 'stage3_midpoint', 'stage3_active', 'stage3_multi_active')]
    closed = (type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('scope') == 'PARAMETERIZED_CORE12_NORMAL_RUNNER_DEVELOPMENT_ONLY'
        and value.get('action') == 'run-core' and type(value.get('returncode')) is int and value['returncode'] == 0
        and value.get('status') == 'ORIGINAL_CORE_TERMINALS_COMPLETE'
        and value.get('error') is None and value.get('slot_read_error') is None
        and value.get('final_errors') == [] and value.get('cleanup') == {'residual_processes': []}
        and all(type(value.get(key)) is int and value[key] == 12 for key in ('planned_count', 'attempt_count', 'terminal_count'))
        and [item.get('slot') for item in value.get('slots', [])] == expected_ids
        and [item.get('slot') for item in value.get('attempts', [])] == expected_ids
        and value.get('entry_binding_before') == value.get('entry_binding_after')
        and isinstance(value.get('entry_binding_before'), dict) and bool(value['entry_binding_before'])
        and 'zero_attempt_recovery' not in value
        and all(value.get(key) is False for key in ('formal_seed_use_authorized', 'readiness_claimed',
            'automatic_retry', 'automatic_next_action', 'resume_or_recovery_authorized')))
    if not closed:
        result['reasons'].append('Original core12 run has not closed completely and healthily')
        return result
    drivers = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            state = (proc/'stat').read_text().rpartition(')')[2].split()[0]
            argv = [token.decode(errors='replace') for token in (proc/'cmdline').read_bytes().split(b'\0') if token]
            names = {Path(token).name for token in argv[:5]}
            if state != 'Z' and int(proc.name) != os.getpid() and 'run-core' in argv and names & {'development_runner.py', 'development_runner.sh'}:
                drivers.append({'pid': int(proc.name), 'argv': argv})
        except (FileNotFoundError, ProcessLookupError):
            continue
    result['actual_normal_core_drivers'] = drivers
    if drivers:
        result['reasons'].append('Normal run-core process has not exited')
        return result
    # Reuse the exact original process detector. No source/runtime validator,
    # plan, bag, model, flight, observer or nested lock is invoked.
    sys.path.insert(0, str(EXTERNAL))
    try:
        import reviewed_freeze_build as generic
        runner = generic.runner_at(FROZEN)
    finally:
        sys.path.pop(0)
    residual = runner.simulation_processes()
    result['actual_simulation_processes'] = residual
    if residual:
        result['reasons'].append('Actual simulation processes remain')
        return result
    observed_lock = original_machine_lock_snapshot()
    result['original_machine_lock'] = observed_lock
    if observed_lock['ready'] is not True:
        result['reasons'].extend(observed_lock['reasons'])
        return result
    if path.read_bytes() != raw:
        raise RuntimeError('Original core terminal changed during idle inspection')
    result['ready'] = True
    return result


def require_core_idle():
    result = core_idle_snapshot()
    if result['ready'] is not True:
        raise RuntimeError('Core is not closed/idle: ' + json.dumps(result, sort_keys=True))
    return result


def main():
    if sys.platform != 'linux' or os.environ.get('WSL_DISTRO_NAME') != 'UAVHumble22':
        raise RuntimeError('Actual UAVHumble22 Linux required')
    initial_idle = core_idle_snapshot()
    if initial_idle['ready'] is not True:
        print(json.dumps({'status': 'DEFERRED_CORE_NOT_CLOSED_OR_IDLE', 'tests_run': False, 'idle': initial_idle}))
        return 3
    manifest_path = ROOT / 'revision02/v2_ten_file_closed_manifest_revision02.json'
    if shared.sha(manifest_path) != EXPECTED:
        raise RuntimeError('Reviewed component source manifest changed')
    manifest = json.loads(manifest_path.read_bytes())
    if any(shared.sha(EXTERNAL / name) != digest for name, digest in manifest['files'].items()):
        raise RuntimeError('Deployed v2 source changed')
    baseline = json.loads((ROOT / 'v1_external_top_level_before_sha256.json').read_bytes())['files']
    shared.validate_original_files(baseline)
    os.nice(15)
    OUTPUT.mkdir(exist_ok=False)
    temporary = tempfile.mkdtemp(prefix='uav_humble43_v2_components04_')
    environment = os.environ.copy()
    environment.update(TMPDIR=temporary, TMP=temporary, TEMP=temporary, PYTHONDONTWRITEBYTECODE='1',
                       PYTHONIOENCODING='utf-8', PYTHONPATH=str(EXTERNAL),
                       UAV_REVIEW_FROZEN_SOURCE_ROOT=str(FROZEN), OMP_NUM_THREADS='1',
                       OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    terminal = {'scope': 'NATIVE_HUMBLE_V2_COMPONENTS_ONLY_NOT_ADMISSION_OR_FLIGHT', 'suites': [],
                'describes': [], 'python': sys.version, 'python_executable': sys.executable,
                'frozen_source_root': str(FROZEN), 'manifest_sha256': EXPECTED,
                'nice': os.nice(0), 'temporary_directory': temporary, 'plan_or_flight_started': False,
                'formal_seed_use_authorized': False, 'core_idle_before': initial_idle, 'idle_checks': []}
    try:
        for module in ('test_development_calibration_v2', 'test_development_final_root_v2', 'test_seal_development_final_source_v2'):
            terminal['idle_checks'].append({'before_suite': module, 'evidence': require_core_idle()})
            with (OUTPUT / (module + '.stdout.log')).open('xb') as stdout, (OUTPUT / (module + '.stderr.log')).open('xb') as stderr:
                child = subprocess.run([sys.executable, '-B', str(ROOT / 'root_install_validate_v2_01.py'), '_suite', module,
                                        str(OUTPUT / (module + '.result.json'))], cwd=EXTERNAL, env=environment,
                                       stdout=stdout, stderr=stderr, timeout=180, check=False)
            result = json.loads((OUTPUT / (module + '.result.json')).read_bytes())
            result['returncode'] = child.returncode
            terminal['suites'].append(result)
        critical = [i for s in terminal['suites'] for i in s['test_ids'] if '.FrozenExtensionAuthorityIntegrationTests.' in i]
        passed = (sum(s['tests_run'] for s in terminal['suites']) == 85
                  and all(s['returncode'] == 0 and s['successful'] and s['skipped'] == [] for s in terminal['suites'])
                  and len(critical) == 9)
        terminal['real_frozen_authority_tests'] = critical
        if passed:
            for name, family in (('prepare_development_final_root_v2.py', 'connection_v2'),
                                 ('development_calibration_v2.py', 'calibration_v2'), ('seal_development_final_source_v2.py', 'seal_v2')):
                terminal['idle_checks'].append({'before_describe': name, 'evidence': require_core_idle()})
                output = OUTPUT / (name + '.describe.json')
                with output.open('xb') as stdout, (OUTPUT / (name + '.describe.stderr.log')).open('xb') as stderr:
                    child = subprocess.run([sys.executable, '-B', str(EXTERNAL / name), 'describe'], cwd=EXTERNAL,
                                           env=environment, stdout=stdout, stderr=stderr, timeout=60, check=False)
                value = json.loads(output.read_bytes())
                digest = value.get('sha256', value.get('tools_canonical_sha256'))
                valid = child.returncode == 0 and value.get('actual_action_executed') is False and digest == manifest[family]['canonical_sha256']
                terminal['describes'].append({'name': name, 'returncode': child.returncode, 'sha256': digest, 'matches': valid})
                if not valid:
                    raise RuntimeError('Native tool identity differs from reviewed manifest')
        terminal['core_idle_after'] = require_core_idle()
        terminal['all_ten_new_bytes_match'] = all(shared.sha(EXTERNAL / n) == h for n, h in manifest['files'].items())
        terminal['status'] = 'PASS_NATIVE_85_COMPONENT_TESTS_ONLY_NOT_ADMISSION' if passed and len(terminal['describes']) == 3 and terminal['all_ten_new_bytes_match'] else 'COMPONENT_FAILURE_RETAINED'
    except BaseException as error:
        terminal['status'] = 'ERROR_RETAINED'
        terminal['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        try:
            terminal['original_files_verified_finally'] = shared.validate_original_files(baseline)
        except BaseException as error:
            terminal['status'] = 'ERROR_RETAINED'
            terminal['original_file_recheck_error'] = type(error).__name__ + ': ' + str(error)
        shared.write_new(OUTPUT / 'root_terminal.json', terminal)
        print(json.dumps({'status': terminal['status'], 'suite_returncodes': [s['returncode'] for s in terminal['suites']],
                          'output': str(OUTPUT)}, ensure_ascii=True))
    return 0 if terminal['status'] == 'PASS_NATIVE_85_COMPONENT_TESTS_ONLY_NOT_ADMISSION' else 2


if __name__ == '__main__':
    raise SystemExit(main())
