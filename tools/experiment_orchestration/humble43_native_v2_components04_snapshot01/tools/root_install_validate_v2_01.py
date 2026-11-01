"""Install ten new names only and verify inert tools/components; never fly."""
from __future__ import annotations
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

STAGING = Path(__file__).resolve().parent
EXTERNAL = STAGING.parent
MANIFEST_SHA = '1cb301ccd6dd344b03ca83ad986a96c5d8962ebb44c5bb8479696baf7020dc0a'
OUTPUT = STAGING / 'root_windows_validation01'
TEMPORARY = EXTERNAL.parent / 'UAVHumble22-v2-test-temp01'
FROZEN = Path(r'\\wsl.localhost\UAVHumble22\root\uav_tracking_fullplan_v4_humble43')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item.id()


def child_suite(module_name, result_path):
    sys.path.insert(0, str(EXTERNAL))
    module = importlib.import_module(module_name)
    if Path(module.__file__).resolve() != (EXTERNAL / (module_name + '.py')).resolve():
        raise RuntimeError('Unexpected test-module origin')
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    ids = list(flatten(suite))
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    value = {
        'module': module_name, 'native_component_tests': True,
        'test_ids': ids, 'tests_run': result.testsRun,
        'skipped': [{'id': case.id(), 'reason': reason} for case, reason in result.skipped],
        'failures': [case.id() for case, _ in result.failures],
        'errors': [case.id() for case, _ in result.errors],
        'successful': result.wasSuccessful(), 'wall_s': time.monotonic() - started,
        'frozen_source_root': os.environ.get('UAV_REVIEW_FROZEN_SOURCE_ROOT'),
    }
    write_new(result_path, value)
    return 0 if result.wasSuccessful() else 1


def validate_original_files(baseline):
    changed = [name for name, digest in baseline.items()
               if not (EXTERNAL / name).is_file() or sha(EXTERNAL / name) != digest]
    if changed:
        raise RuntimeError('Existing external bytes changed: ' + repr(changed))
    return len(baseline)


def main():
    manifest_path = STAGING / 'v2_ten_file_closed_manifest.json'
    if sha(manifest_path) != MANIFEST_SHA:
        raise RuntimeError('Closed candidate manifest changed')
    manifest = json.loads(manifest_path.read_bytes())
    files = manifest['files']
    if len(files) != 10 or any('/' in n or '\\' in n or '_v2.' not in n for n in files):
        raise RuntimeError('Exactly ten new versioned basenames required')
    baseline_path = STAGING / 'v1_external_top_level_before_sha256.json'
    if sha(baseline_path) != manifest['receipts'][baseline_path.name]:
        raise RuntimeError('Original baseline receipt changed')
    baseline = json.loads(baseline_path.read_bytes())['files']
    validate_original_files(baseline)
    for name, digest in files.items():
        if (EXTERNAL / name).exists() or (EXTERNAL / name).is_symlink():
            raise RuntimeError('Refusing to overwrite ' + name)
        if sha(STAGING / 'implementation_v2' / name) != digest:
            raise RuntimeError('Staged source changed: ' + name)
    if not (FROZEN / 'scripts' / 'run_reliability_v4.py').is_file():
        raise RuntimeError('Actual reviewed frozen43 source is unavailable')
    OUTPUT.mkdir(exist_ok=False)
    TEMPORARY.mkdir(exist_ok=False)
    terminal = {'scope': 'NEW_ONLY_V2_INSTALL_COMPONENT_TESTS_AND_INERT_DESCRIBE_NOT_ADMISSION',
                'manifest_sha256': MANIFEST_SHA, 'installed': [], 'suites': [],
                'describes': [], 'wsl_invoked': False, 'plan_or_flight_started': False,
                'original_results_modified': False}
    try:
        for name, digest in files.items():
            with (EXTERNAL / name).open('xb') as stream:
                stream.write((STAGING / 'implementation_v2' / name).read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            if sha(EXTERNAL / name) != digest:
                raise RuntimeError('Installed byte verification failed')
            terminal['installed'].append({'name': name, 'sha256': digest})
        terminal['original_files_verified_before_tests'] = validate_original_files(baseline)
        environment = os.environ.copy()
        environment.update(TEMP=str(TEMPORARY), TMP=str(TEMPORARY), PYTHONDONTWRITEBYTECODE='1',
                           PYTHONIOENCODING='utf-8', PYTHONPATH=str(EXTERNAL),
                           UAV_REVIEW_FROZEN_SOURCE_ROOT=str(FROZEN))
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0
        modules = ('test_development_calibration_v2', 'test_development_final_root_v2',
                   'test_seal_development_final_source_v2')
        for module in modules:
            with (OUTPUT / (module + '.stdout.log')).open('xb') as stdout, (OUTPUT / (module + '.stderr.log')).open('xb') as stderr:
                process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '_suite', module,
                                          str(OUTPUT / (module + '.result.json'))],
                                         cwd=EXTERNAL, env=environment, stdout=stdout, stderr=stderr,
                                         timeout=180, creationflags=flags, check=False)
            result = json.loads((OUTPUT / (module + '.result.json')).read_bytes())
            result['returncode'] = process.returncode
            terminal['suites'].append(result)
        all_ids = [i for suite in terminal['suites'] for i in suite['test_ids']]
        critical = [i for i in all_ids if '.FrozenExtensionAuthorityIntegrationTests.' in i]
        skipped = {i['id'] for suite in terminal['suites'] for i in suite['skipped']}
        terminal['real_frozen_authority_tests'] = critical
        terminal['all_9_real_authority_tests_executed'] = len(critical) == 9 and not (set(critical) & skipped)
        terminal['tests_valid'] = (sum(s['tests_run'] for s in terminal['suites']) == 85
                                  and all(s['returncode'] == 0 and s['successful'] for s in terminal['suites'])
                                  and terminal['all_9_real_authority_tests_executed'])
        if terminal['tests_valid']:
            for script, key in (('prepare_development_final_root_v2.py', 'connection_v2_canonical_sha256'),
                                ('development_calibration_v2.py', 'calibration_v2_canonical_sha256'),
                                ('seal_development_final_source_v2.py', 'seal_v2_canonical_sha256')):
                output = OUTPUT / (script + '.describe.json')
                with output.open('xb') as stdout, (OUTPUT / (script + '.describe.stderr.log')).open('xb') as stderr:
                    process = subprocess.run([sys.executable, '-B', str(EXTERNAL / script), 'describe'],
                                             cwd=EXTERNAL, env=environment, stdout=stdout, stderr=stderr,
                                             timeout=60, creationflags=flags, check=False)
                described = json.loads(output.read_bytes())
                digest = described.get('sha256', described.get('tools_canonical_sha256'))
                valid = process.returncode == 0 and described.get('actual_action_executed') is False and digest == manifest[key]
                terminal['describes'].append({'script': script, 'returncode': process.returncode,
                                               'canonical_sha256': digest, 'matches_reviewed_manifest': valid})
                if not valid:
                    raise RuntimeError('Inert describe disagrees with independently reconstructed identity')
        terminal['original_files_verified_after_tests'] = validate_original_files(baseline)
        terminal['all_new_bytes_unchanged'] = all(sha(EXTERNAL / n) == digest for n, digest in files.items())
        terminal['status'] = 'PASS_COMPONENTS_ONLY_NOT_ADMISSION' if terminal['tests_valid'] and terminal['all_new_bytes_unchanged'] else 'COMPONENT_FAILURE_RETAINED'
    except BaseException as error:
        terminal['status'] = 'ERROR_RETAINED'
        terminal['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        try:
            terminal['original_files_verified_finally'] = validate_original_files(baseline)
        except BaseException as error:
            terminal['status'] = 'ERROR_RETAINED'
            terminal['original_file_recheck_error'] = type(error).__name__ + ': ' + str(error)
        write_new(OUTPUT / 'root_terminal.json', terminal)
        print(json.dumps({'status': terminal.get('status'), 'output': str(OUTPUT),
                          'installed_count': len(terminal['installed']),
                          'suite_returncodes': [r['returncode'] for r in terminal['suites']]}, ensure_ascii=True))
    return 0 if terminal['status'] == 'PASS_COMPONENTS_ONLY_NOT_ADMISSION' else 2


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_suite':
        raise SystemExit(child_suite(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
