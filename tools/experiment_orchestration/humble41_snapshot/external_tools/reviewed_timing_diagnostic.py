"""One explicitly admitted75s timing PROBE on a reviewed frozen workspace.

Import/describe are inert. Source/build review alone does not authorize this
diagnostic: a separate final admission and explicitly reviewed tool SHA are
required. No search, retry, core/formal matrix, or next action is available.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import json

import reviewed_freeze_build as generic

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'REVIEWED_ONE75S_TIMING_DIAGNOSTIC_NOT_READINESS'
FINAL_STATUS = 'FINAL_SINGLE_TIMING_DIAGNOSTIC_INDEPENDENTLY_REVIEWED'
PREFIX = 'reliability_v4_timing_person01'
SLOT = 'person_stage1_velocity_seed004'
GENERIC_CANONICAL = 'e57017201f1033847e49bb7843b1ef61bad28c21ac9f16e876736498980219cf'
BORROWED = {
    'humble33_diagnostic_checks01.py': '15f89375b5cbdd986fddf317dff95e9f8737023d8af2dd1e5c0869d3d310e431',
    'humble33_development_observer01.py': 'ac9bf14ef870d23eea86ec0ffad426fc71265ca812e1b22c0ae2068ad60dbf09',
    'analyze_humble33_inference_timing01.py': '2df9ea330245b6306ad56f59136c43ffa25832e3b93329cfbe9df3218e75205c',
}
OWN_FILES = ('reviewed_timing_diagnostic.py', 'reviewed_timing_diagnostic.sh', 'test_reviewed_timing_diagnostic.py')
require = generic.require
sha = generic.sha
canonical = generic.canonical
read_small = generic.read_small
write_new = generic.write_new


def utc():
    return datetime.now(timezone.utc).isoformat()


def metadata_binding(path, *, json_only=False):
    path = Path(path)
    require(path.suffix in (('.json',) if json_only else ('.json', '.log')) and path.is_file()
        and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL, 'Bounded named metadata only; never bag input')
    if json_only:
        read_small(path)
    return {'path': str(path), 'sha256': sha(path)}


def tool_manifest():
    require(Path(generic.__file__).resolve(strict=True) == (EXTERNAL / 'reviewed_freeze_build.py').resolve(strict=True)
        and canonical(generic.tools_manifest()) == GENERIC_CANONICAL, 'Reviewed generic build toolchain changed')
    files = {}
    for name, expected in BORROWED.items():
        path = EXTERNAL / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL
            and sha(path) == expected, 'Pinned parameterized diagnostic dependency changed: ' + name)
        files[name] = expected
    for name in OWN_FILES:
        path = EXTERNAL / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL, 'Missing reviewed diagnostic entry')
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': files, 'generic_build_tools': generic.tools_manifest(),
        'borrowed_external_import_graph': dependency_graph(),
        'original_slot': SLOT, 'prefix': PREFIX, 'class': 'person', 'group': 'stage1_velocity', 'seed': 4,
        'duration_s': 75, 'inference_image_size': 320, 'inference_threads': 2,
        'observer_session_wall_s': 7200, 'observer_rotation_wall_s': 5400, 'observer_max_sample_age_wall_s': 10,
        'outer_cleanup_graces_s': [240, 30, 10], 'original_child_cleanup_graces_s': [240, 30, 10],
        'original_child_cleanup_allowance_s': 280, 'outer_cleanup_margin_s': 120,
        'legacy_global_ROOT_modified': False, 'full_suite_rerun': False,
        'formal_seed_use_authorized': False, 'readiness_claimed': False, 'automatic_next_action': False}


def dependency_graph():
    """Every transitive borrowed local import is also fixed by the generic SHA."""
    allowed = set(BORROWED) | set(generic.DEPENDENCIES)
    graph = {}
    for filename in BORROWED:
        tree = ast.parse((EXTERNAL / filename).read_text(encoding='utf-8'), filename=filename)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.extend(item.name.split('.')[0] for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module: imports.append(node.module.split('.')[0])
        local = {name + '.py' for name in imports if (EXTERNAL / (name + '.py')).is_file()}
        require(local <= allowed, 'Unregistered diagnostic transitive local import')
        graph[filename] = sorted(local)
    return graph


def dependencies():
    tool_manifest()
    generic.dependencies()
    modules = {}
    for filename in BORROWED:
        name = filename.removesuffix('.py')
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve(strict=True) == (EXTERNAL / filename).resolve(strict=True)
            and sha(module.__file__) == BORROWED[filename], 'Diagnostic dependency import escaped')
        modules[name] = module
    return modules


def paths(admission):
    root = Path(admission['frozen_root'])
    plan = Path(admission['plan_path'])
    return {'root': root, 'plan': plan, 'plan_driver': root / 'results/freeze_validation/timing_plan_driver01',
        'run_driver': plan.parent / 'timing_driver01'}


def validate_admission(value):
    require(isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('status') == FINAL_STATUS and value.get('scope') == SCOPE, 'Separate final diagnostic admission required')
    root = generic.absolute(value.get('frozen_root'))
    require(value.get('plan_path') == root + '/results/' + PREFIX + '_seed004_matrix/plan.json'
        and value.get('authorized_actions') == ['plan', 'run'] and generic.valid_sha(value.get('source_commit'), 40)
        and generic.valid_sha(value.get('diagnostic_tools_canonical_sha256')), 'Explicit root/one-slot/tool identity required')
    require(value.get('experiment') == {'class': 'person', 'group': 'stage1_velocity', 'seed': 4, 'duration_s': 75,
        'inference_image_size': 320, 'inference_threads': 2, 'prefix': PREFIX, 'slot': SLOT}, 'Only the original person75s/seed004 diagnostic is supported')
    require(all(type(value['experiment'][field]) is int for field in
        ('seed', 'duration_s', 'inference_image_size', 'inference_threads'))
        and value.get('formal_seed_use_authorized') is False and value.get('readiness_claimed') is False
        and value.get('automatic_retry') is False and value.get('automatic_next_action') is False, 'No formal/readiness/retry authorization')
    source = value.get('source_review', {})
    require(isinstance(source, dict) and generic.valid_sha(source.get('sha256')), 'Exact final source review SHA required')
    generic.absolute(source.get('path'))
    expected = {'summary': root + '/results/freeze_validation/build_validation_summary.json'}
    label = Path(root).name.removeprefix('uav_tracking_fullplan_')
    for action in ('build', 'validate'):
        expected[action + '_terminal'] = generic.LINUX_EXTERNAL + '/reviewed_freeze_actions_' + label + '/' + action + '/action.terminal.json'
    evidence = value.get('build_evidence', {})
    require(isinstance(evidence, dict) and set(evidence) == set(expected), 'Actual generic build+validate receipts required')
    for name, path in expected.items():
        require(isinstance(evidence[name], dict) and evidence[name].get('path') == path
            and generic.valid_sha(evidence[name].get('sha256')), 'Build evidence path/SHA differs: ' + name)
    return value


def load_admission(path, expected_sha, reviewed_tools, action, frozen_root, plan_path):
    require(action in ('plan', 'run') and path is not None and generic.valid_sha(expected_sha)
        and generic.valid_sha(reviewed_tools), 'Existing separate diagnostic admission and reviewed tool SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
        and re.fullmatch(r'reviewed_timing_review_[A-Za-z0-9_]+\.json', path.name), 'Explicit external diagnostic registry required')
    value = validate_admission(read_small(path))
    require(sha(path) == expected_sha and value['diagnostic_tools_canonical_sha256'] == reviewed_tools
        == canonical(tool_manifest()), 'Diagnostic admission/tool bytes changed')
    require(frozen_root == value['frozen_root'] and plan_path == value['plan_path'], 'Explicit command root/plan differs from admission')
    source = generic.load_review(value['source_review']['path'], value['source_review']['sha256'], 'validate')
    require(source['frozen_root'] == value['frozen_root'] and source['source_commit'] == value['source_commit'], 'Diagnostic source differs from final build review')
    value['_admission_binding'] = {'path': str(path), 'sha256': expected_sha}
    return value, source


def checked_build(admission, review, checks):
    # Verify the wrapper contract before imports, which may alter process env.
    environment_before = checks.require_environment_contract()
    library_before = os.environ['LD_LIBRARY_PATH']
    frozen = generic.frozen_binding(review)
    original = generic.verify_closed_capsule(review)
    bound = {}
    for name, expected in admission['build_evidence'].items():
        actual = metadata_binding(expected['path'], json_only=True)
        require(actual == expected, 'Actual admitted build receipt changed: ' + name)
        bound[name] = actual
    for action in ('build', 'validate'):
        value = read_small(bound[action + '_terminal']['path'])
        binding = value.get('binding_before')
        require(value.get('scope') == 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE'
            and value.get('action') == action and value.get('status') == 'PASS' and type(value.get('direct_child_returncode')) is int
            and value['direct_child_returncode'] == 0 and value.get('execution_count') == 1
            and value.get('cleanup', {}).get('actual_proc_group_empty') is True
            and value['cleanup'].get('direct_child_reaped') is True and value['cleanup'].get('residual_processes') == []
            and isinstance(binding, dict) and binding == value.get('binding_after')
            and binding.get('source') == frozen and binding.get('review') == review['_review_binding']
            and binding.get('closed_original_evidence') == original, 'Actual same-source generic ' + action + ' action did not PASS')
    summary = read_small(bound['summary']['path'])
    require(summary.get('status') == 'PASS' and type(summary.get('returncode')) is int and summary['returncode'] == 0
        and type(summary.get('tests')) is int and summary['tests'] > 0 and summary.get('skipped') == 5
        and summary.get('execution_count') == 1 and summary.get('source_unchanged') is True
        and summary.get('source_binding_before') == summary.get('source_binding_after') == frozen
        and summary.get('final_review') == review['_review_binding']
        and summary.get('toolchain_canonical_sha256') == GENERIC_CANONICAL
        and summary.get('freeze_source_sha256') == frozen['freeze_source_sha256']
        and summary.get('four_packages_built') is True and summary.get('module_ament_isolation') is True
        and summary.get('closed_original_evidence_before') == summary.get('closed_original_evidence_after') == original
        and summary.get('closed_original_evidence_unchanged') is True and summary.get('formal_seeds_consumed') is False
        and summary.get('bounded_action_terminal_must_be_PASS') is True, 'Actual complete same-source build/suite receipt missing')
    directory = generic.validation_dir(review)
    for name in ('unittest.log', 'import_isolation.json', 'fastcdr_provenance.json', 'generated_message_roundtrip.json'):
        bound[name] = metadata_binding(directory / name, json_only=name.endswith('.json'))
    require(bound['unittest.log']['sha256'] == summary.get('suite_log_sha256')
        and bound['generated_message_roundtrip.json']['sha256'] == summary.get('generated_message_roundtrip_sha256'), 'Actual original suite/CDR log changed')
    cdr = read_small(directory / 'generated_message_roundtrip.json')
    require(cdr.get('status') == 'PASS' and cdr.get('source_binding_after_roundtrip') == frozen
        and cdr.get('scope') == 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION'
        and set(cdr.get('checks', {})) == generic.CDR_CHECK_NAMES and all(v is True for v in cdr['checks'].values())
        and cdr.get('execution_count') == 1, 'Actual built-message CDR result differs')
    isolation = read_small(directory / 'import_isolation.json')
    require(isolation.get('root') == review['frozen_root'] and isolation.get('isolated') is True
        and set(isolation.get('module_files', {})) == set(generic.MODULES) | set(review.get('additional_import_modules', []))
        and set(isolation.get('ros_package_prefixes', {})) == set(generic.PACKAGES)
        and isolation.get('selected_bridge_overlay') == generic.BRIDGE
        and isolation.get('bridge_runtime_validation', {}).get('status') == 'PASS', 'Complete actual import/ament isolation missing')
    root = Path(review['frozen_root']).resolve(strict=True)
    import_environment = {'event': 'BUILD_MODULE_IMPORT_LIBRARY_ENVIRONMENT', 'contract_before': environment_before,
        'before_import_ld_library_path': library_before, 'effects': [], 'only_ld_library_path_restored': True}
    try:
        for name, reported in isolation['module_files'].items():
            before = os.environ.get('LD_LIBRARY_PATH')
            try:
                actual = Path(importlib.import_module(name).__file__).resolve(strict=True)
            finally:
                after = os.environ.get('LD_LIBRARY_PATH')
                if after != before:
                    import_environment['effects'].append({'module': name, 'before': before, 'after': after})
            require(actual == Path(reported).resolve(strict=True) and actual.is_relative_to(root), 'Actual imported module escaped: ' + name)
            if name in ('uav_tracking_nodes.detector_node', 'uav_tracking_nodes.inference_timing', 'uav_tracking_nodes.inference_worker'):
                require(sha(actual) == review['files'].get(actual.relative_to(root).as_posix()), 'Actual timing module bytes differ: ' + name)
    finally:
        import_environment['after_import_ld_library_path'] = os.environ.get('LD_LIBRARY_PATH')
        os.environ['LD_LIBRARY_PATH'] = library_before
        import_environment['restored_ld_library_path'] = os.environ['LD_LIBRARY_PATH']
        # PATH and all ROS/Gazebo fields are checked unchanged; only LD restored.
        try:
            import_environment['contract_after_restore'] = checks.require_environment_contract()
        except BaseException as caught:
            import_environment['contract_after_restore_error'] = type(caught).__name__ + ':' + str(caught)
            raise
        finally:
            print(json.dumps(import_environment, sort_keys=True), flush=True)
    for name in generic.PACKAGES:
        actual = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', name], text=True).strip()).resolve(strict=True)
        require(actual == Path(isolation['ros_package_prefixes'][name]).resolve(strict=True) == root / 'ros2_ws/install', 'Actual package prefix escaped')
    cached = read_small(directory / 'fastcdr_provenance.json')
    actual = generic.verify_fastcdr(review, write=False)
    require(cached.get('status') == actual['status'] and cached.get('inputs_sha256') == actual['inputs_sha256'], 'Actual cached FastCDR provenance differs')
    return {'source': frozen, 'closed_original_evidence': original, 'bound_build_metadata': bound,
        'module_import_environment': import_environment}


def require_runtime(admission, review, checks):
    generic.require_linux()
    require(os.environ.get('ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PROJECT_ROOT') == admission['frozen_root']
        and os.environ.get('STAGE1_ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PX4_ROOT') == generic.PX4_ROOT
        and os.environ.get('STAGE1_ROS_GZ_WS') == generic.BRIDGE and os.environ.get('HUMBLE22_ROS_GZ_WS') == generic.BRIDGE,
        'Use the explicit reviewed diagnostic runtime wrapper')
    environment = checks.require_environment_contract()
    runtime = generic.runtime_contracts(review, admission['frozen_root'])
    require(sha(checks.AGENT) == checks.AGENT_SHA256, 'Actual MicroXRCEAgent bytes changed')
    results = {}
    commands = {'agent_command': ['/bin/bash', '-c', 'command -v MicroXRCEAgent'], 'agent_ldd': ['ldd', checks.AGENT],
        'person_flight_check': ['/bin/bash', str(paths(admission)['root'] / 'scripts/run_stage1_flight.sh'), 'check', 'person']}
    for name, command in commands.items():
        result = subprocess.run(command, cwd=paths(admission)['root'], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60)
        require(result.returncode == 0 and result.stdout.strip(), 'Read-only diagnostic preflight failed: ' + name)
        require(name != 'agent_command' or result.stdout.strip() == checks.AGENT, 'Agent command escaped installation')
        require(name != 'agent_ldd' or 'not found' not in result.stdout.lower(), 'Agent linker dependency unavailable')
        results[name] = {'command': command, 'returncode': result.returncode,
            'output_lines': sorted(re.sub(r'\(0x[0-9a-fA-F]+\)', '(address omitted)', result.stdout).splitlines())}
    return {'environment': environment, 'runtime_contracts': runtime, 'checks': results}


def entry_binding(admission, review, built):
    require(metadata_binding(admission['_admission_binding']['path'], json_only=True) == admission['_admission_binding']
        and canonical(tool_manifest()) == admission['diagnostic_tools_canonical_sha256'], 'Diagnostic admission/tool changed')
    actual = generic.action_binding(review, 'validate')
    require(actual['source'] == built['source'] and actual['closed_original_evidence'] == built['closed_original_evidence'],
        'Actual frozen source or closed original evidence changed')
    for expected in built['bound_build_metadata'].values():
        require(metadata_binding(expected['path'], json_only=Path(expected['path']).suffix == '.json') == expected, 'Original build evidence changed')
    return {'admission': admission['_admission_binding'], 'source_review': review['_review_binding'],
        'source': built['source'], 'build': built, 'diagnostic_tools_canonical_sha256': admission['diagnostic_tools_canonical_sha256']}


def observer_command(root, directory):
    return [sys.executable, '-B', str(Path(root) / 'scripts/observe_runtime_health.py'), '--output-dir',
        str(Path(directory) / 'runtime_health'), '--duration-wall-s', '7200', '--max-log-mib', '64', '--ros']


def observer_types(legacy):
    """Normal subclass parameters only; no legacy globals/commands are patched."""
    class ExplicitRootObserver(legacy.IndependentObserver):
        def __init__(self, directory, root):
            self.directory = Path(directory)
            self.root = Path(root)
            self.process = None
            self.console = None
            self._finished = None
            self.last_check = None
            self.command = observer_command(root, directory)

        def __enter__(self):
            # The original handshake also used ROOT as cwd; bind both locations.
            self.directory.mkdir(exist_ok=False)
            self.console = (self.directory / 'observer_console.log').open('x')
            try:
                self.process = subprocess.Popen(self.command, cwd=self.root, stdout=self.console,
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

    class ExplicitRootRollingObserver(legacy.RollingIndependentObserver):
        def __init__(self, directory, root):
            super().__init__(directory)
            self.root = Path(root)

        def start_session(self):
            index = len(self.sessions) + 1
            directory = self.directory / f'session_{index:03d}'
            item = {'index': index, 'directory': str(directory), 'started_utc': utc(), 'started_monotonic_s': time.monotonic()}
            observer = ExplicitRootObserver(directory, self.root)
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
    return ExplicitRootObserver, ExplicitRootRollingObserver


def validate_observer_root(terminal_or_none, directory, root, legacy):
    """Original validator, with only explicit command-root and local API aliases.

    This implementation-time port preserves unchanged observer protocol metadata;
    it neither edits legacy globals nor rewrites/normalizes original receipts.
    """
    fresh, finite, stamp = legacy.fresh, legacy.finite, legacy.stamp
    observer_scope, rotation_wall_s = legacy.SCOPE, legacy.ROTATE_WALL_S
    directory = Path(directory)
    path = directory / 'execution_terminal.json'
    actual = read_small(path)
    if terminal_or_none is not None and terminal_or_none != actual:
        raise ValueError('Parent rolling observer differs from the original terminal')
    sessions, rotations = actual.get('sessions'), actual.get('rotations')
    if (actual.get('schema_version') != 1 or actual.get('scope') != observer_scope
            or actual.get('rotation_wall_s') != rotation_wall_s
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
                or item.get('terminal') != original or original.get('command') != observer_command(root, folder)
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
                    or not previous['started_monotonic_s'] + rotation_wall_s
                        <= item['started_monotonic_s'] <= item['first_fresh_monotonic_s']
                        <= previous['finished_monotonic_s'] <= rotation['completed_monotonic_s']
                        <= item['finished_monotonic_s']
                    or item['first_fresh_sample']['latest_sample_monotonic_s']
                        > previous['terminal']['final_fresh_sample']['latest_sample_monotonic_s'] + 10.):
                raise ValueError('No original overlap between successive fresh observers')
            for key in ('old_last_fresh_sample', 'new_first_fresh_sample', 'new_fresh_after_old_finish'):
                fresh(rotation.get(key))
    return {'path': str(path), 'sha256': sha(path), 'scope': observer_scope,
            'session_count': len(sessions), 'finished_utc': actual['finished_utc']}


def outer_allowance(plan, trial):
    flight, evaluation = plan.get('trial_timeout_s'), plan.get('evaluation_timeout_s')
    require(type(flight) in (int, float) and math.isfinite(flight) and flight > 0
        and type(evaluation) in (int, float) and math.isfinite(evaluation) and evaluation > 0
        and isinstance(trial.get('evaluations'), list), 'Actual original child/evaluator budgets required')
    return {'trial_timeout_s': float(flight), 'evaluation_timeout_s': float(evaluation), 'evaluation_count': len(trial['evaluations']),
        'original_child_cleanup_graces_s': [240, 30, 10], 'original_child_cleanup_allowance_s': 280.,
        'cleanup_margin_s': 120., 'outer_allowance_s': float(flight + len(trial['evaluations']) * evaluation + 280. + 120.)}


def require_timing_evidence(timing):
    require(isinstance(timing, dict) and timing.get('status') == 'LOG_TIMING_ANALYZED_E2E_UNAVAILABLE'
        and timing.get('counts', {}).get('outcomes', {}).get('completed', 0) > 0
        and timing.get('limits', {}).get('source_e2e_to_estimator_or_state_status')
            == 'UNKNOWN_REQUIRES_SEPARATE_DELIVERY_STATE_EVIDENCE'
        and timing['limits'].get('runtime_success_claimed') is False
        and timing['limits'].get('readiness_claimed') is False,
        'No complete identifiable final log timing evidence; E2E remains unknown')


def save_timing_report(path, timing):
    # Bound before writing so an oversized report cannot break final receipt creation.
    require(len(json.dumps(timing, indent=2, allow_nan=False).encode('utf-8')) + 1 <= generic.MAX_SMALL,
        'Timing report exceeds bounded metadata policy')
    write_new(path, timing)
    return metadata_binding(path, json_only=True)


def plan_checked(admission, checks):
    plan_path = paths(admission)['plan']; plan = read_small(plan_path)
    runner = generic.runner_at(admission['frozen_root'])
    require(isinstance(plan, dict) and plan.get('mode') == 'PROBE' and plan.get('prefix') == PREFIX and plan.get('frozen_root') == admission['frozen_root']
        and plan.get('selected_seeds') == [4] and type(plan['selected_seeds'][0]) is int
        and plan.get('selected_classes') == ['person'] and plan.get('selected_groups') == ['stage1_velocity']
        and isinstance(plan.get('trials'), list) and len(plan['trials']) == 1
        and isinstance(plan['trials'][0], dict), 'Exactly the admitted one-slot PROBE required')
    runner.validate_plan(plan, plan_path); runner.verify_sources(plan); checks.require_plan_resources(plan)
    trial = plan['trials'][0]
    require(trial.get('id') == SLOT and all(type(trial.get(field)) is int for field in
        ('seed', 'inference_image_size', 'inference_threads')) and trial['seed'] == 4
        and trial.get('duration_s') == 75 and trial.get('model') == 'models/yolo11n.pt'
        and trial.get('inference_image_size') == 320 and trial.get('inference_threads') == 2,
        'Original person75s/n320/CPU2 parameters changed')
    return runner, plan, trial, runner.read_slots(plan)[SLOT]


def execute_owned(command, log, observer, timeout, root):
    """Preserve original outer grace; original runner owns its child budgets."""
    started, timer = utc(), time.monotonic(); process = None; error = None; cleanup = []
    with Path(log).open('x', encoding='utf-8') as stream:
        try:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                observer.check()
                if time.monotonic() - timer >= timeout:
                    raise TimeoutError('Original prospective outer allowance exceeded')
                try: process.wait(timeout=1.)
                except subprocess.TimeoutExpired: pass
            observer.check()
        except BaseException as caught:
            error = type(caught).__name__ + ':' + str(caught)
            if process is not None:
                for sent, grace in ((signal.SIGINT, 240), (signal.SIGTERM, 30), (signal.SIGKILL, 10)):
                    if process.poll() is not None: break
                    process.send_signal(sent); cleanup.append({'signal': int(sent), 'grace_s': grace})
                    try: process.wait(timeout=grace)
                    except subprocess.TimeoutExpired: continue
    return {'command': command, 'started_utc': started, 'finished_utc': utc(), 'elapsed_wall_s': time.monotonic() - timer,
        'returncode': process.poll() if process else None, 'error': error, 'outer_cleanup_actions': cleanup,
        'log': str(log), 'timeout_wall_s': float(timeout)}


def clean_execution(receipt, command):
    require(receipt.get('command') == command and type(receipt.get('returncode')) is int and receipt['returncode'] == 0
        and receipt.get('error') is None and receipt.get('outer_cleanup_actions') == [], 'Original outer command/observer did not close cleanly')


def final_cleanup(admission, review, built, runner, observer, directory, legacy):
    errors = []; source = None; residual = None
    try: source = entry_binding(admission, review, built)['source']
    except BaseException as caught: errors.append('source:' + type(caught).__name__ + ':' + str(caught))
    try:
        residual = runner.simulation_processes(); require(residual == [], 'Residual runtime after original diagnostic action')
    except BaseException as caught: errors.append('residual:' + type(caught).__name__ + ':' + str(caught))
    try: validate_observer_root(observer._finished, Path(directory) / 'observer_driver', admission['frozen_root'], legacy)
    except BaseException as caught: errors.append('observer:' + type(caught).__name__ + ':' + str(caught))
    return {'source_binding_after': source, 'cleanup': {'residual_processes': residual},
        'observer': observer._finished, 'final_errors': errors}


def plan_main(admission, review, built, modules, runtime):
    selected = paths(admission); runner = generic.runner_at(admission['frozen_root'])
    require(not any(p.exists() or p.is_symlink() for p in (selected['plan'].parent, selected['plan_driver']))
        and not runner.simulation_processes(), 'Diagnostic plan already exists or another runtime is active')
    selected['plan_driver'].mkdir(exist_ok=False)
    command = [sys.executable, '-B', 'scripts/run_reliability_v4.py', 'plan', '--frozen-root', admission['frozen_root'],
        '--output', str(selected['plan'].parent), '--prefix', PREFIX, '--probe', '--seeds', '4', '--classes', 'person',
        '--groups', 'stage1_velocity', '--wall-timeout', '600.0']
    legacy = modules['humble33_development_observer01']; _, rolling = observer_types(legacy)
    observer = rolling(selected['plan_driver'] / 'observer_driver', selected['root'])
    initial = None; execution = None; error = None; binding = entry_binding(admission, review, built)
    try:
        with observer:
            execution = execute_owned(command, selected['plan_driver'] / 'plan.log', observer, 1800., selected['root'])
            write_new(selected['plan_driver'] / 'plan.outer_execution.json', execution); clean_execution(execution, command)
            _, plan, trial, record = plan_checked(admission, modules['humble33_diagnostic_checks01'])
            require(record.get('status') == 'PENDING', 'Original new plan must remain untouched PENDING')
            initial = {'plan': metadata_binding(selected['plan'], json_only=True), 'plan_sha256': plan['plan_sha256'], 'slot': trial['id'], 'status': 'PENDING'}
    except BaseException as caught: error = type(caught).__name__ + ':' + str(caught)
    cleanup = final_cleanup(admission, review, built, runner, observer, selected['plan_driver'], legacy)
    code = 0 if error is None and initial and not cleanup['final_errors'] else 2
    terminal = {'schema_version': 1, 'scope': SCOPE, 'action': 'plan', 'finished_utc': utc(), 'returncode': code,
        'error': error, 'execution': execution, 'initial_pending': initial, 'diagnostic_entry_binding': binding,
        'runtime_preflight': runtime, **cleanup, 'flights_started': 0, 'formal_seed_use_authorized': False,
        'readiness_claimed': False, 'automatic_next_action': False}
    write_new(selected['plan_driver'] / 'execution_terminal.json', terminal)
    if code == 0: write_new(selected['plan'].parent / 'diagnostic_plan_receipt01.json', terminal)
    return code


def run_main(admission, review, built, modules, runtime):
    selected = paths(admission); checks = modules['humble33_diagnostic_checks01']; legacy = modules['humble33_development_observer01']
    runner, plan, trial, record = plan_checked(admission, checks)
    binding = entry_binding(admission, review, built)
    receipt = read_small(selected['plan'].parent / 'diagnostic_plan_receipt01.json')
    require(receipt == read_small(selected['plan_driver'] / 'execution_terminal.json') and receipt.get('returncode') == 0
        and receipt.get('action') == 'plan' and receipt.get('flights_started') == 0 and receipt.get('diagnostic_entry_binding') == binding
        and receipt.get('initial_pending') == {'plan': metadata_binding(selected['plan'], json_only=True), 'plan_sha256': plan['plan_sha256'], 'slot': SLOT, 'status': 'PENDING'},
        'Original independently closed same-source diagnostic plan required')
    validate_observer_root(receipt.get('observer'), selected['plan_driver'] / 'observer_driver', admission['frozen_root'], legacy)
    require(record.get('status') == 'PENDING' and not selected['run_driver'].exists() and not selected['run_driver'].is_symlink()
        and not runner.simulation_processes(), 'Diagnostic was attempted or another runtime is active; no retry')
    selected['run_driver'].mkdir(exist_ok=False); allowance = outer_allowance(plan, trial)
    write_new(selected['run_driver'] / 'setup.json', {'scope': SCOPE, 'created_utc': utc(), 'slot': SLOT, 'plan': metadata_binding(selected['plan'], json_only=True),
        'initial_status': 'PENDING', 'outer_allowance': allowance, 'diagnostic_entry_binding': binding, 'readiness_claimed': False})
    command = [sys.executable, '-B', 'scripts/run_reliability_v4.py', 'run', '--plan', str(selected['plan']), '--max-new-trials', '1']
    _, rolling = observer_types(legacy); observer = rolling(selected['run_driver'] / 'observer_driver', selected['root'])
    error = None; execution = None; completed = None; timing_binding = None
    try:
        # The original runner owns the machine SITL lock. Acquiring it here would
        # make its independently opened child lock fail LOCK_EX|LOCK_NB. The
        # entry-point generic.exclusive_window serializes these external actions.
        with observer:
            entry_binding(admission, review, built); runner.verify_sources(plan)
            execution = execute_owned(command, selected['run_driver'] / 'person.outer.log', observer, allowance['outer_allowance_s'], selected['root'])
            execution['outer_allowance'] = allowance; write_new(selected['run_driver'] / 'person.outer_execution.json', execution)
            record = runner.read_slots(plan)[SLOT]
            require(record.get('status') in runner.TERMINAL, 'Original runner has no terminal; retain attempt without retry')
            completed = {'slot': SLOT, 'status': record['status'], 'record_binding': checks.terminal_binding(runner, plan, trial, record)}
            clean_execution(execution, command); checks.require_completed_record(runner, plan, trial, record)
            actual = runner.runtime_configuration(plan, trial); require(actual.get('errors') == [], 'Actual diagnostic runtime/source/model/gates differ')
            completed.update(runtime=actual, bridge=checks.bridge_evidence(trial['directory'], review),
                processes=checks.process_evidence(trial['directory'], stage=1, condition='clean'), closed75_archive=checks.closed75_archive(trial, record))
            log = Path(trial['directory']) / 'ros.log'
            require(metadata_binding(log)['sha256'] == record.get('artifact_hashes', {}).get('ros.log'), 'Original timing log differs from closed record')
            timing = modules['analyze_humble33_inference_timing01'].analyze(log)
            timing_binding = save_timing_report(selected['run_driver'] / 'timing_log_analysis.json', timing)
            require_timing_evidence(timing)
            entry_binding(admission, review, built); runner.verify_sources(plan); observer.check()
    except BaseException as caught: error = type(caught).__name__ + ':' + str(caught)
    cleanup = final_cleanup(admission, review, built, runner, observer, selected['run_driver'], legacy)
    code = 0 if error is None and completed and not cleanup['final_errors'] else 2
    write_new(selected['run_driver'] / 'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE, 'action': 'run', 'finished_utc': utc(),
        'returncode': code, 'status': 'ONE_ORIGINAL_DIAGNOSTIC_TERMINAL_RETAINED' if code == 0 else 'STOPPED_NO_AUTOMATIC_RETRY',
        'error': error, 'slot': completed, 'execution': execution, 'diagnostic_entry_binding': binding,
        'source_binding_before': built['source'], 'runtime_preflight': runtime, **cleanup,
        'timing_log_analysis': timing_binding,
        'formal_seed_use_authorized': False, 'readiness_claimed': False, 'automatic_next_action': False,
        'claim_boundary': 'One75s original timing diagnostic; original PASS/FAIL/unknown retained. No repair success, full-core/extension readiness, causal conclusion, E2E latency or formal admission.'})
    return code


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'plan', 'run'))
    result.add_argument('--admission', type=Path)
    result.add_argument('--admission-sha256')
    result.add_argument('--reviewed-tools-sha256')
    result.add_argument('--frozen-root')
    result.add_argument('--plan')
    return result


def shell_root(argv):
    args = parser().parse_args(argv)
    admission, _ = load_admission(args.admission, args.admission_sha256, args.reviewed_tools_sha256,
        args.action, args.frozen_root, args.plan)
    return admission['frozen_root']


@contextmanager
def stop_signals():
    old = {}
    def interrupted(number, frame):
        raise KeyboardInterrupt('Requested stop signal ' + str(number))
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            old[number] = signal.signal(number, interrupted)
        yield
    finally:
        for number, handler in old.items(): signal.signal(number, handler)


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == 'describe':
        print(json.dumps({'manifest': tool_manifest(), 'diagnostic_tools_canonical_sha256': canonical(tool_manifest()),
            'default_real_admission': None, 'actual_project_action_executed': False}, indent=2)); return 0
    try:
        admission, review = load_admission(args.admission, args.admission_sha256, args.reviewed_tools_sha256,
            args.action, args.frozen_root, args.plan)
        generic.require_linux()
        modules = dependencies()
        with generic.exclusive_window(), stop_signals():
            built = checked_build(admission, review, modules['humble33_diagnostic_checks01'])
            runtime = require_runtime(admission, review, modules['humble33_diagnostic_checks01'])
            entry_binding(admission, review, built)
            return {'plan': plan_main, 'run': run_main}[args.action](admission, review, built, modules, runtime)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as caught:
        print(json.dumps({'status': 'DIAGNOSTIC_REFUSED_OR_FAILED', 'reason': type(caught).__name__ + ':' + str(caught),
            'automatic_retry': False, 'readiness_claimed': False}), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
