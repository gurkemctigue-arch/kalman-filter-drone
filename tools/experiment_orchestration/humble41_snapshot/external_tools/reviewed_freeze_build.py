"""Reviewed, parameterized source freeze/build actions; no simulator actions.

There is deliberately no publisher or default real review. Every mutable CLI
action requires an existing independently reviewed JSON and its explicit SHA.
Import/describe do not reserve directories, source ROS, or start processes.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time

EXTERNAL = Path(__file__).resolve().parent
LINUX_EXTERNAL = '/mnt/d/WSL/UAVHumble22-validation'
SCOPE = 'REVIEWED_SOURCE_FREEZE_BUILD_ONLY_NOT_RUNTIME_ACCEPTANCE'
FINAL_STATUS = 'FINAL_SOURCE_AND_TOOLS_INDEPENDENTLY_REVIEWED'
ACTIONS = {'prepare': 300., 'copy': 300., 'build': 1800., 'validate': 600.}
PACKAGES = ('uav_tracking_interfaces', 'uav_tracking_nodes', 'uav_tracking_bringup', 'uav_tracking_px4_adapter')
DEPENDENCIES = {
    'bounded_humble33_action.py': '9375a171d23eeef7c82b541e06893cdc16cfed4eedfc988f096da7afa29dad2d',
    'humble33_review_guard.py': '4c97caea15f017f708949dac304318f8eab6570e1134bdf54cc6e184e1b4f2c2',
    'humble33_original32_retention01.py': 'b4914fe9ffc92502cc357c3e89e3a1c7c78e52dff0a20ae846114b42e54e9931',
    'humble33_skip_contract.py': '9a4f9d8584077d5c6ebbc099cb35b0c56746bbd725b0893882814bdc87b92406',
}
OWN_FILES = ('reviewed_freeze_build.py', 'reviewed_freeze_build.sh', 'test_reviewed_freeze_build.py')
PX4_ROOT = '/root/uav_humble22/PX4-Autopilot-v4mag'
BRIDGE = '/root/uav_humble22/ros_gz_shutdown_A01_ws'
PYTHON = '/root/uav_humble22/venv/bin/python'
MAGNETIC_PATH = '/root/uav_tracking_fullplan_v4_humble29/config/px4_magnetic_runtime.json'
MAGNETIC_SHA = '3c4f9693cfab51c6b2049af619bfb6e3edbd22a8328468b7e84f75053485c66b'
FORBIDDEN_COMPILE = '/root/uav_humble22/agent_install'
SYSTEM_FASTCDR = '/opt/ros/humble/lib/cmake/fastcdr'
WINDOW_LOCK = '/root/uav_tracking_humble_build_window.lock'
MAX_SMALL = 16 * 1024 * 1024
MAX_CAPSULE_FILES = 512
MAX_CAPSULE_BYTES = 256 * 1024 * 1024
MODULES = ('uav_tracking.core', 'uav_tracking.core.target_manager', 'uav_tracking_nodes.stage2_telemetry',
    'uav_tracking_nodes', 'uav_tracking_nodes.detector_node', 'uav_tracking_nodes.inference_timing',
    'uav_tracking_nodes.inference_worker', 'uav_tracking_interfaces.msg',
    'uav_tracking_interfaces.msg._target_observation_array', 'uav_tracking_interfaces.msg._target_state',
    'uav_tracking_interfaces.msg._target_observation', 'uav_tracking_interfaces.msg._navigation_overlap')
CDR_CHECK_NAMES = frozenset(('same_acquisition_header', 'new_observation_flags_and_count', 'original_full_cloud_preserved',
    'exclusive_cloud_preserved_separately', 'pair_candidate_and_class_ids', 'complete_rectangle_and_counts',
    'complete_float32_points', 'signed_origin_and_incomplete_wire_fields', 'raw_bbox_fields',
    'ground_support_preserved', 'pair_count_matches_observation'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def valid_sha(value, size=64):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{' + str(size) + '}', value) is not None


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_small(path):
    path = Path(path)
    require(path.suffix == '.json' and path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL, 'Missing/unsafe bounded JSON: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def relative(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name
        and not PurePosixPath(name).is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe relative path')
    return name


def absolute(name):
    require(isinstance(name, str) and name.startswith('/') and not name.startswith('//')
        and '\\' not in name and ':' not in name and not any(ord(c) < 32 for c in name) and '..' not in name.split('/')
        and PurePosixPath(name).as_posix() == name, 'Expected canonical absolute Linux path')
    return name


def checked_map(value):
    require(isinstance(value, dict) and value, 'Empty file map')
    for name, digest in value.items():
        relative(name)
        require(valid_sha(digest), 'Invalid file digest')
    return value


def verify_files(root, files):
    root = Path(root).resolve(strict=True)
    for name, digest in checked_map(files).items():
        path = root / name
        require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(root)
            and sha(path) == digest, 'File escaped or changed: ' + name)
    return canonical(files)


def dependency_graph():
    """Enumerate the complete borrowed external-local import closure, not history."""
    graph = {}
    for filename in DEPENDENCIES:
        tree = ast.parse((EXTERNAL / filename).read_text(encoding='utf-8'), filename=filename)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(item.name.split('.')[0] for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split('.')[0])
        local = {name + '.py' for name in modules if (EXTERNAL / (name + '.py')).is_file()}
        require(local <= set(DEPENDENCIES), 'Unregistered transitive external-local import')
        graph[filename] = sorted(local)
    return graph


def tools_manifest():
    values = {}
    for name, expected in DEPENDENCIES.items():
        path = EXTERNAL / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL and sha(path) == expected, 'Pinned reusable dependency changed: ' + name)
        values[name] = expected
    for name in OWN_FILES:
        path = EXTERNAL / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL, 'Missing reviewed entry/test: ' + name)
        values[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': values, 'borrowed_external_import_graph': dependency_graph(),
        'project_dynamic_imports_bound_by_review_files': ['scripts/run_reliability_v4.py', 'uav_tracking/ros_gz_runtime.py'],
        'borrowed_apis': ['bounded_humble33_action.run_bounded', 'humble33_skip_contract',
            'humble33_review_guard.require_safety_ast(root)', 'humble33_review_guard.require_resource_choice(root)',
            'humble33_review_guard.require_bridge_runtime(review,root)'],
        'legacy_cli_or_production_binding_called': False, 'automatic_next_action': False}


def dependencies():
    tools_manifest()  # Verify all transitive local imports before loading them.
    result = {}
    for name in ('humble33_original32_retention01', 'humble33_review_guard', 'humble33_skip_contract', 'bounded_humble33_action'):
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve(strict=True) == (EXTERNAL / (name + '.py')).resolve(strict=True), 'Imported dependency escaped: ' + name)
        require(sha(module.__file__) == DEPENDENCIES[name + '.py'], 'Imported dependency bytes changed')
        result[name] = module
    return result


def delta(previous, current):
    return {'changed': sorted(name for name in previous.keys() & current.keys() if previous[name] != current[name]),
        'added': sorted(current.keys() - previous.keys()), 'removed': sorted(previous.keys() - current.keys())}


def validate_review(value):
    require(isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('status') == FINAL_STATUS and value.get('scope') == SCOPE, 'No final independent source/tool review')
    require(value.get('formal_seed_use_authorized') is False and value.get('flight_actions_authorized') is False
        and value.get('automatic_next_action') is False, 'Build review cannot authorize flight/formal/retry')
    require(valid_sha(value.get('source_commit'), 40) and valid_sha(value.get('toolchain_canonical_sha256')), 'Exact final commit/tool SHA required')
    source = absolute(value.get('source_root'))
    frozen = absolute(value.get('frozen_root'))
    results = absolute(value.get('results_root'))
    match = re.fullmatch(r'/root/uav_tracking_fullplan_([A-Za-z0-9_]+)', frozen)
    require(match is not None and source != frozen, 'Dedicated frozen root required')
    require(results == source + '/results/frozen_fullplan_' + match[1], 'Exact dedicated results/root pair required')
    baseline = value.get('baseline', {})
    require(valid_sha(baseline.get('source_commit'), 40) and valid_sha(baseline.get('manifest_sha256'))
        and valid_sha(baseline.get('files_canonical_sha256')) and absolute(baseline.get('root')) != frozen,
        'Independent predecessor source binding required')
    absolute(baseline.get('manifest_path'))
    require(frozen not in ('/root/uav_tracking_fullplan_v4_humble32', '/root/uav_tracking_fullplan_v4_humble33'), 'Historical frozen roots are protected')
    checked_map(value.get('files'))
    require(all(not name.startswith(('results/', '.git/', 'ros2_ws/build/', 'ros2_ws/install/', 'ros2_ws/log/'))
        for name in value['files']), 'Only source files may enter the source manifest')
    classified = checked_map(value.get('classified_source_hashes'))
    require(all(value['files'].get(name) == digest for name, digest in classified.items()), 'Incomplete classified source binding')
    approved = value.get('allowed_delta')
    require(isinstance(approved, dict) and set(approved) == {'changed', 'added', 'removed'}, 'Exact allowed delta required')
    all_names = []
    for names in approved.values():
        require(isinstance(names, list) and names == sorted(set(names)), 'Delta paths must be unique and sorted')
        all_names.extend(relative(name) for name in names)
    require(len(all_names) == len(set(all_names)), 'Delta classifications overlap')
    require(value.get('source_overrides') == {'config/px4_magnetic_runtime.json': {'path': MAGNETIC_PATH, 'sha256': MAGNETIC_SHA}}
        and value['files'].get('config/px4_magnetic_runtime.json') == MAGNETIC_SHA,
        'Only the inherited explicitly bound Humble magnetic override is supported')
    require('config/px4_magnetic_runtime.json' not in all_names, 'Override cannot hide a reviewed source change')
    require(value.get('runtime') == {'distro': 'UAVHumble22', 'ros': 'humble', 'px4_root': PX4_ROOT,
        'bridge_overlay': BRIDGE, 'python': PYTHON, 'invariant_policy': 'HUMBLE33_SAFETY_AND_RESOURCE_CONTRACTS_UNCHANGED'}, 'Reviewed fixed runtime differs')
    require(value.get('action_timeouts_s') == ACTIONS and value.get('expected_full_suite_skips') == 5
        and type(value['expected_full_suite_skips']) is int and value.get('authorized_actions') == list(ACTIONS), 'Explicit inherited build budgets/skips/actions required')
    capsule = value.get('closed_evidence', {})
    require(valid_sha(capsule.get('sha256')), 'Closed predecessor/core evidence SHA required')
    absolute(capsule.get('path'))
    additions = value.get('additional_import_modules', [])
    require(isinstance(additions, list) and additions == sorted(set(additions)) and all(
        isinstance(name, str) and re.fullmatch(r'(?:uav_tracking|uav_tracking_nodes|uav_tracking_interfaces)(?:\.[A-Za-z_][A-Za-z0-9_]*)+', name)
        for name in additions), 'Additional import modules must be explicit project modules')
    return value


def baseline_manifest(review):
    bound = review['baseline']
    value = read_small(bound['manifest_path'])
    require(sha(bound['manifest_path']) == bound['manifest_sha256'], 'Predecessor manifest changed')
    checked_map(value.get('files'))
    require(value.get('source_commit') == bound['source_commit'] and value.get('source_root') == bound['root']
        and canonical(value['files']) == value.get('freeze_source_sha256') == bound['files_canonical_sha256'], 'Predecessor actual manifest/source differs')
    require(delta(value['files'], review['files']) == review['allowed_delta'], 'Candidate differs from exact independently reviewed delta')
    return value


def candidate_binding(review):
    baseline_manifest(review)
    root = Path(review['source_root'])
    command = ['git', '-C', str(root)]
    head = subprocess.check_output(command + ['rev-parse', 'HEAD'], text=True).strip()
    require(head == review['source_commit'], 'HEAD differs from final reviewed commit')
    require(not subprocess.check_output(['git', '-c', 'core.autocrlf=true', '-C', str(root), 'status', '--porcelain'], text=True).strip(), 'Final committed clean checkout required')
    subprocess.run(command + ['merge-base', '--is-ancestor', review['baseline']['source_commit'], head], check=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for category, code in (('changed', 'M'), ('added', 'A'), ('removed', 'D')):
        raw = subprocess.check_output(command + ['diff', '--no-renames', '--name-only', '-z', '--diff-filter=' + code,
            review['baseline']['source_commit'], head, '--'])
        actual = [name for name in raw.decode('utf-8').split('\0') if name]
        require(sorted(actual) == review['allowed_delta'][category], 'Git delta differs: ' + category)
    for name, digest in review['files'].items():
        override = review['source_overrides'].get(name)
        path = Path(override['path']) if override else root / relative(name)
        allowed = Path(MAGNETIC_PATH).parent.resolve(strict=True) if override else root.resolve(strict=True)
        require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(allowed)
            and sha(path) == digest, 'Actual candidate bytes differ: ' + name)
    pairs = {}
    for name in review['allowed_delta']['changed'] + review['allowed_delta']['added']:
        actual = (root / name).read_bytes()
        blob = subprocess.check_output(command + ['show', head + ':' + name])
        require(actual == blob, 'Changed text/blob physical bytes differ: ' + name)
        pairs[name] = {'bytes': len(actual), 'sha256': hashlib.sha256(actual).hexdigest(), 'actual_equals_git_blob': True}
    return {'source_root': str(root), 'source_commit': head, 'files_canonical_sha256': canonical(review['files']),
        'physical_byte_authority': True, 'copy_normalizes_line_endings': False, 'changed_or_added_blob_pairs': pairs}


def frozen_binding(review):
    root = Path(review['frozen_root'])
    results = Path(review['results_root'])
    require(root.is_dir() and not root.is_symlink() and (root / 'results').is_symlink()
        and (root / 'results').resolve(strict=True) == results.resolve(strict=True), 'Frozen results binding differs')
    path = results / 'freeze_validation/source_freeze_manifest.json'
    value = read_small(path)
    require(value.get('files') == review['files'] and value.get('classified_source_hashes') == review['classified_source_hashes']
        and value.get('source_commit') == review['source_commit'] and value.get('source_root') == str(root)
        and value.get('results_root') == str(results) and value.get('final_review') == review['_review_binding']
        and value.get('toolchain_canonical_sha256') == review['toolchain_canonical_sha256']
        and value.get('freeze_source_sha256') == canonical(review['files'])
        and value.get('source_file_count') == len(review['files']), 'Actual new frozen manifest differs')
    verify_files(root, review['files'])
    return {'manifest_sha256': sha(path), 'freeze_source_sha256': canonical(review['files']), 'verified_file_count': len(review['files'])}


def verify_closed_capsule(review):
    """Explicit bounded metadata only; no recursive history or payload reads."""
    bound = review['closed_evidence']
    value = read_small(bound['path'])
    require(sha(bound['path']) == bound['sha256'], 'Closed evidence capsule changed')
    require(value.get('schema_version') == 1 and value.get('scope') == 'CLOSED_32_CORE_AND_PREDECESSOR_METADATA_ONLY'
        and value.get('all_inputs_closed') is True and value.get('payload_reread') is False
        and value.get('readiness_claimed') is False, 'No independently closed evidence capsule')
    files = value.get('files', {})
    require(isinstance(files, dict) and 0 < len(files) <= MAX_CAPSULE_FILES, 'Closed metadata denominator missing/oversized')
    allowed = (Path('/root/uav_tracking_fullplan_v4_humble32'), Path(review['baseline']['root']),
        Path(review['source_root']) / 'results/frozen_fullplan_v4_humble32',
        Path(review['source_root']) / ('results/frozen_fullplan_' + Path(review['baseline']['root']).name.removeprefix('uav_tracking_fullplan_')),
        EXTERNAL)
    total = 0
    for name, row in files.items():
        absolute(name)
        require(isinstance(row, dict) and valid_sha(row.get('sha256')) and type(row.get('bytes')) is int
            and 0 <= row['bytes'] <= MAX_SMALL, 'Unsafe closed metadata entry')
        path = Path(name)
        require(path.suffix in ('.json', '.yaml', '.yml', '.log', '.py', '.sh', '.md') and path.is_file()
            and not path.is_symlink() and any(path.resolve(strict=True).is_relative_to(p.resolve(strict=True))
                for p in allowed if p.exists()) and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Closed original artifact changed: ' + name)
        total += row['bytes']
        require(total <= MAX_CAPSULE_BYTES, 'Closed metadata exceeds bounded review size')
    boundaries = value.get('boundaries', {})
    require(set(boundaries) == {'original32_core', 'predecessor'}, 'Both closed boundaries required')
    required_facts = set()
    for name, entry in boundaries.items():
        require(isinstance(entry, dict) and entry.get('closed') is True and entry.get('receipt') in files, 'Missing closed original receipt: ' + name)
        terminal = read_small(entry['receipt'])
        require(isinstance(terminal.get('finished_utc'), str), 'Original action has no closed terminal time')
        if name == 'original32_core':
            require(terminal.get('scope') == 'HUMBLE32_CORE12_ORIGINAL_ATTEMPTS_AND_CLEANUP_NOT_FORMAL_GATE'
                and terminal.get('planned_count') == terminal.get('terminal_count') == 12
                and len(terminal.get('slots', [])) == 12 and type(terminal.get('returncode')) is int
                and terminal['returncode'] in (0, 2)
                and terminal.get('cleanup') == {'residual_processes': [], 'residual_probe_error': None},
                'Original32 full core denominator/cleanup differs')
            slots = terminal['slots']
            require(len({slot.get('slot') for slot in slots}) == 12, 'Original32 slot denominator is not unique')
            require(terminal.get('status_counts') == dict(Counter(slot.get('status') for slot in slots)), 'Original32 status denominator contradicts original slots')
            required_facts.update(((entry['receipt'], 'status_counts'), (entry['receipt'], 'returncode')))
            for slot in slots:
                matches = [path for path in files if '/slots/' in path and Path(path).name == slot['slot'] + '.json'
                    and 'frozen_fullplan_v4_humble32/' in path]
                require(len(matches) == 1, 'Missing original32 slot record')
                record = read_small(matches[0])
                require(record.get('id') == slot['slot'] and record.get('status') == slot.get('status')
                    and record.get('record_sha256') == canonical({k: v for k, v in record.items() if k != 'record_sha256'}),
                    'Original32 slot identity/status/digest differs')
                required_facts.add((matches[0], 'status'))
            require(any(slot.get('slot') == 'person_stage1_velocity_seed004' and slot.get('status') == 'FAIL'
                for slot in slots), 'Original32 recorded velocity FAIL must remain')
        elif terminal.get('scope') == 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE':
            require(type(terminal.get('direct_child_returncode')) is int
                and terminal.get('cleanup', {}).get('actual_proc_group_empty') is True
                and terminal['cleanup'].get('direct_child_reaped') is True
                and terminal['cleanup'].get('residual_processes') == [], 'Predecessor bounded action is not cleanly closed')
            before = terminal.get('binding_before', {}).get('source')
            after = terminal.get('binding_after', {}).get('source')
            require(isinstance(before, dict) and before == after and before.get('freeze_source_sha256') == review['baseline']['files_canonical_sha256'],
                'Closed predecessor action does not bind the actual predecessor source')
            required_facts.update(((entry['receipt'], 'status'), (entry['receipt'], 'direct_child_returncode')))
        else:
            require(type(terminal.get('returncode')) is int and terminal['returncode'] in (0, 2)
                and terminal.get('cleanup', {}).get('residual_processes') == [], 'Predecessor diagnostic is not closed')
            before, after = terminal.get('source_binding_before'), terminal.get('source_binding_after')
            require(isinstance(before, dict) and before == after and before.get('freeze_source_sha256') == review['baseline']['files_canonical_sha256'],
                'Closed predecessor diagnostic/source binding differs')
            required_facts.add((entry['receipt'], 'returncode'))
    facts = value.get('retained_fields', [])
    require(isinstance(facts, list) and facts, 'Original statuses/FAIL fields must be explicit')
    declared_facts = {(fact.get('path'), fact.get('field')) for fact in facts if isinstance(fact, dict)}
    require(required_facts <= declared_facts, 'All original core statuses/counts and predecessor outcome must remain explicit')
    for fact in facts:
        require(isinstance(fact, dict) and fact.get('path') in files and isinstance(fact.get('field'), str)
            and fact['field'] and 'expected' in fact, 'Unbound original retained field')
        actual = read_small(fact['path'])
        for part in fact['field'].split('.'):
            require(isinstance(actual, dict) and part in actual, 'Missing original retained field')
            actual = actual[part]
        require(type(actual) is type(fact['expected']) and actual == fact['expected'], 'Original outcome changed')
    return {'capsule_sha256': bound['sha256'], 'files': len(files), 'metadata_bytes': total,
        'file_map_sha256': canonical(files), 'retained_fields_sha256': canonical(facts), 'payloads_reverified': False}


def load_review(path, expected_sha, action):
    require(action in ACTIONS and path is not None and valid_sha(expected_sha), 'Existing final review plus explicit SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True) and re.fullmatch(r'reviewed_freeze_review_[A-Za-z0-9_]+\.json', path.name), 'Review must be an explicitly named external registry')
    value = validate_review(read_small(path))
    require(sha(path) == expected_sha and canonical(tools_manifest()) == value['toolchain_canonical_sha256'], 'Independent review/tool SHA changed')
    value['_review_binding'] = {'path': str(path), 'sha256': expected_sha}
    return value


def action_binding(review, action):
    read_small(review['_review_binding']['path'])
    require(sha(review['_review_binding']['path']) == review['_review_binding']['sha256']
        and canonical(tools_manifest()) == review['toolchain_canonical_sha256'], 'Review/tool bytes changed')
    baseline_manifest(review)
    source = candidate_binding(review) if action in ('prepare', 'copy') else frozen_binding(review)
    return {'review': review['_review_binding'], 'source': source, 'closed_original_evidence': verify_closed_capsule(review)}


def runner_at(root):
    path = Path(root) / 'scripts/run_reliability_v4.py'
    name = 'reviewed_freeze_source_runner'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def runtime_contracts(review, root):
    deps = dependencies()
    guard = deps['humble33_review_guard']
    runner = runner_at(root)
    protocol = read_small(Path(root) / 'planning/reliability-v4-preregistration.json')
    runner.validate_protocol(protocol)
    classified = runner.source_hashes(root)
    classified['config/px4_magnetic_runtime.json'] = MAGNETIC_SHA
    require(classified == review['classified_source_hashes'], 'Actual classified source completeness differs')
    runner.validate_model_adaptation_binding(protocol, classified)
    magnetic = MAGNETIC_PATH if str(root) == review['source_root'] else str(Path(root) / 'config/px4_magnetic_runtime.json')
    actual = runner.verify_external_runtime(root, Path(magnetic))
    require(actual.get('source_root') == PX4_ROOT, 'Actual PX4 registration differs')
    require(not runner.simulation_processes(), 'Another simulator/recorder/flight graph is active')
    bridge = guard.require_bridge_runtime(review, root)
    return {'safety': guard.require_safety_ast(root), 'resource': guard.require_resource_choice(root),
        'bridge': bridge, 'px4_root': actual['source_root']}


def validation_dir(review):
    return Path(review['results_root']) / 'freeze_validation'


def copy_registered_file(source, destination, digest):
    source, destination = Path(source), Path(destination)
    require(source.is_file() and not source.is_symlink() and sha(source) == digest, 'Candidate changed during copy')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    require(sha(destination) == digest, 'Copy changed physical source bytes')


def prepare(review):
    require(not any(p.exists() or p.is_symlink() for p in (Path(review['frozen_root']), Path(review['results_root']))), 'New root/results must be unreserved')
    runtime = runtime_contracts(review, review['source_root'])
    return {'scope': SCOPE, 'action': 'prepare', 'runtime_contracts': runtime, 'root_created': False, 'build_executed': False}


def copy_source(review):
    roots = (Path(review['frozen_root']), Path(review['results_root']))
    require(not any(p.exists() or p.is_symlink() for p in roots), 'No overwrite/retry of frozen paths')
    require(all(p.parent.is_dir() and not p.parent.is_symlink() for p in roots), 'Dedicated root/results parents must exist')
    before = candidate_binding(review)
    original = verify_closed_capsule(review)
    roots[0].mkdir()
    roots[1].mkdir()
    (roots[0] / 'results').symlink_to(roots[1], target_is_directory=True)
    validation_dir(review).mkdir()
    for name, digest in review['files'].items():
        override = review['source_overrides'].get(name)
        source = Path(override['path']) if override else Path(review['source_root']) / name
        destination = roots[0] / relative(name)
        copy_registered_file(source, destination, digest)
    runtime = runtime_contracts(review, roots[0])
    require(candidate_binding(review) == before and verify_closed_capsule(review) == original, 'Source/original evidence changed during copy')
    write_new(validation_dir(review) / 'source_freeze_manifest.json', {'schema_version': 1, 'created_utc': utc(),
        'scope': SCOPE, 'source_root': str(roots[0]), 'results_root': str(roots[1]), 'source_commit': review['source_commit'],
        'files': review['files'], 'classified_source_hashes': review['classified_source_hashes'],
        'freeze_source_sha256': canonical(review['files']), 'source_file_count': len(review['files']),
        'source_bytes_policy': before, 'final_review': review['_review_binding'], 'toolchain_canonical_sha256': review['toolchain_canonical_sha256'],
        'closed_original_evidence': original, 'runtime_contracts': runtime, 'build_executed': False, 'tests_executed': False,
        'formal_seeds_consumed': False, 'runtime_acceptance': 'NOT_EVALUATED'})
    archived = validation_dir(review) / 'external_wrappers'
    archived.mkdir()
    for name in tools_manifest()['files']:
        shutil.copy2(EXTERNAL / name, archived / name)
    shutil.copy2(review['_review_binding']['path'], validation_dir(review) / 'final_source_review.json')
    return frozen_binding(review)


def build_command(python, colcon):
    return [python, colcon, 'build', '--merge-install', '--symlink-install', '--packages-select', *PACKAGES,
        '--cmake-args', '-DPython3_EXECUTABLE=' + python, '-DPYTHON_EXECUTABLE=' + python,
        '-Dfastcdr_DIR=' + SYSTEM_FASTCDR]


def build(review):
    root = Path(review['frozen_root'])
    before = frozen_binding(review)
    require(not any((root / 'ros2_ws' / name).exists() or (root / 'ros2_ws' / name).is_symlink()
        for name in ('build', 'install', 'log')), 'Cold build refuses any existing artifact tree')
    names = ('PATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'CMAKE_MODULE_PATH', 'CMAKE_INCLUDE_PATH',
        'CMAKE_LIBRARY_PATH', 'CMAKE_PROGRAM_PATH', 'CMAKE_FRAMEWORK_PATH', 'CMAKE_APPBUNDLE_PATH', 'CPATH', 'CPLUS_INCLUDE_PATH',
        'C_INCLUDE_PATH', 'LIBRARY_PATH', 'PKG_CONFIG_PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME')
    environment = {name: os.environ.get(name) for name in names}
    require(not any(FORBIDDEN_COMPILE in (value or '') for value in environment.values()), 'Agent runtime polluted compile environment')
    colcon = shutil.which('colcon')
    require(colcon is not None and (Path(SYSTEM_FASTCDR) / 'fastcdr-config.cmake').is_file(), 'System Humble FastCDR/colcon unavailable')
    command = build_command(sys.executable, colcon)
    write_new(validation_dir(review) / 'build_environment.json', {'created_utc': utc(), 'command': command, 'variables': environment,
        'source_binding_before': before, 'execution_count': 1, 'agent_compile_prefix_absent': True})
    with (validation_dir(review) / 'colcon_build.log').open('x') as stream:
        result = subprocess.run(command, cwd=root / 'ros2_ws', stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
    require(result.returncode == 0, 'Actual cold four-package build failed: ' + str(result.returncode))
    require(frozen_binding(review) == before, 'Frozen source changed during build')
    return verify_fastcdr(review)


def verify_fastcdr(review, *, write=True):
    package = Path(review['frozen_root']) / 'ros2_ws/build/uav_tracking_interfaces'
    cache = package / 'CMakeCache.txt'
    text = cache.read_text()
    expected = Path(SYSTEM_FASTCDR)
    selected = re.findall(r'(?m)^fastcdr_DIR:[^=]+=(.+)$', text)
    require(len(selected) == 1 and Path(selected[0]).resolve() == expected.resolve()
        and FORBIDDEN_COMPILE not in text, 'Actual CMake FastCDR selection differs')
    flags = sorted(package.glob('CMakeFiles/*/flags.make'))
    links = sorted(package.glob('CMakeFiles/*/link.txt'))
    fastrtps = [path for path in flags if 'fastrtps' in str(path)]
    require(flags and links and len(fastrtps) >= 2 and all('/opt/ros/humble/include' in path.read_text() for path in fastrtps)
        and all(FORBIDDEN_COMPILE not in path.read_text() for path in flags + links), 'Actual compiler/linker FastCDR provenance failed')
    inputs = [cache, expected / 'fastcdr-config.cmake', *flags, *links]
    report = {'schema_version': 1, 'created_utc': utc(), 'scope': 'ACTUAL_CMAKE_AND_COMPILER_FASTCDR_PROVENANCE_ONLY',
        'status': 'MATCHES_HUMBLE_SYSTEM_FASTCDR', 'fastcdr_directory': str(expected), 'agent_compile_prefix_absent': True,
        'inputs_sha256': {str(path): sha(path) for path in inputs}}
    if write:
        write_new(validation_dir(review) / 'fastcdr_provenance.json', report)
    return report


def installed_checks(review):
    root = Path(review['frozen_root'])
    bridge_prefix = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', 'ros_gz_bridge'], text=True).strip()).resolve(strict=True)
    require(bridge_prefix == (Path(BRIDGE) / 'install').resolve(strict=True), 'Selected bridge overlay escaped')
    bridge = dependencies()['humble33_review_guard'].require_bridge_runtime(review, root)
    modules = {}
    for name in (*MODULES, *review.get('additional_import_modules', [])):
        path = Path(importlib.import_module(name).__file__).resolve(strict=True)
        require(path.is_relative_to(root.resolve(strict=True)), 'Actual imported project module escaped: ' + name)
        modules[name] = str(path)
    prefixes = {}
    for name in PACKAGES:
        path = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', name], text=True).strip()).resolve(strict=True)
        require(path == (root / 'ros2_ws/install').resolve(strict=True), 'Actual ament prefix differs: ' + name)
        prefixes[name] = str(path)
    write_new(validation_dir(review) / 'import_isolation.json', {'root': str(root), 'module_files': modules,
        'ros_package_prefixes': prefixes, 'isolated': True, 'selected_bridge_overlay': BRIDGE,
        'bridge_package_prefix': str(bridge_prefix), 'bridge_runtime_validation': bridge})
    from rclpy.serialization import serialize_message, deserialize_message
    from uav_tracking_interfaces.msg import NavigationOverlap, TargetObservation, TargetObservationArray

    normal = NavigationOverlap()
    normal.candidate_a_id, normal.candidate_b_id = 7, 8
    normal.class_a_id, normal.class_b_id = 2, 0
    normal.bbox_a_px, normal.bbox_b_px = [10., 10., 20., 20.], [12., 13., 14., 14.]
    normal.u0, normal.v0, normal.width, normal.height = 12, 13, 2, 1
    normal.expected_pixel_count, normal.valid_pixel_count = 2, 2
    normal.rectangle_representable, normal.depth_complete = True, True
    normal.points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
    incomplete = NavigationOverlap()
    incomplete.candidate_a_id, incomplete.candidate_b_id = 7, 9
    incomplete.class_a_id, incomplete.class_b_id = 2, 3
    incomplete.bbox_a_px, incomplete.bbox_b_px = [-3e9, 5., 5., 12.], [-3e9, 7., 10., 14.]
    incomplete.u0, incomplete.v0 = -3, 7
    incomplete.width = incomplete.height = 0
    incomplete.expected_pixel_count = incomplete.valid_pixel_count = 0
    incomplete.rectangle_representable, incomplete.depth_complete = False, False
    incomplete.points_camera_m = []
    observation = TargetObservation()
    observation.candidate_id, observation.class_id = 7, 2
    observation.class_name, observation.camera_frame = 'car', 'camera_link'
    observation.depth_valid, observation.depth_m = True, 5.
    observation.navigation_bbox_inside_image = True
    observation.navigation_bbox_complete = False
    observation.navigation_overlap_count = 2
    observation.navigation_points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
    observation.navigation_visibility_support_camera_m = [.5, -.25, 5.]
    frame = TargetObservationArray()
    frame.header.stamp.sec, frame.header.stamp.nanosec = 12, 345678901
    frame.header.frame_id = 'camera_link'
    observation.header = frame.header
    frame.observations = [observation]
    frame.navigation_overlaps = [normal, incomplete]
    frame.navigation_ground_points_camera_m = [1., 2., 3.]
    wire = serialize_message(frame)
    decoded = deserialize_message(wire, TargetObservationArray)
    selected, = decoded.observations
    complete, unknown = decoded.navigation_overlaps
    checks = {
        'same_acquisition_header': decoded.header == frame.header and selected.header == decoded.header,
        'new_observation_flags_and_count': selected.navigation_bbox_inside_image is True
            and selected.navigation_bbox_complete is False and selected.navigation_overlap_count == 2,
        'original_full_cloud_preserved': list(selected.navigation_points_camera_m) == list(observation.navigation_points_camera_m),
        'exclusive_cloud_preserved_separately': list(selected.navigation_visibility_support_camera_m)
            == list(observation.navigation_visibility_support_camera_m)
            and len(selected.navigation_points_camera_m) != len(selected.navigation_visibility_support_camera_m),
        'pair_candidate_and_class_ids': (complete.candidate_a_id, complete.candidate_b_id,
            complete.class_a_id, complete.class_b_id) == (7, 8, 2, 0)
            and (unknown.candidate_a_id, unknown.candidate_b_id, unknown.class_a_id, unknown.class_b_id) == (7, 9, 2, 3),
        'complete_rectangle_and_counts': (complete.u0, complete.v0, complete.width, complete.height,
            complete.expected_pixel_count, complete.valid_pixel_count) == (12, 13, 2, 1, 2, 2)
            and complete.rectangle_representable is True and complete.depth_complete is True,
        'complete_float32_points': list(complete.points_camera_m) == list(normal.points_camera_m)
            and len(complete.points_camera_m) == complete.expected_pixel_count * 3,
        'signed_origin_and_incomplete_wire_fields': unknown.u0 == -3 and unknown.v0 == 7
            and unknown.rectangle_representable is False and unknown.depth_complete is False
            and unknown.width == unknown.height == unknown.expected_pixel_count == unknown.valid_pixel_count == 0
            and not unknown.points_camera_m,
        'raw_bbox_fields': list(complete.bbox_a_px) == list(normal.bbox_a_px)
            and list(complete.bbox_b_px) == list(normal.bbox_b_px)
            and list(unknown.bbox_a_px) == list(incomplete.bbox_a_px)
            and list(unknown.bbox_b_px) == list(incomplete.bbox_b_px),
        'ground_support_preserved': list(decoded.navigation_ground_points_camera_m) == [1., 2., 3.],
        'pair_count_matches_observation': len(decoded.navigation_overlaps) == selected.navigation_overlap_count,
    }
    receipt = {'scope': 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION',
        'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks, 'serialized_bytes': len(wire),
        'serialized_sha256': hashlib.sha256(wire).hexdigest(), 'generated_module_files': {name: value for name, value in modules.items()
            if name.startswith('uav_tracking_interfaces.')}, 'source_binding_after_roundtrip': frozen_binding(review), 'execution_count': 1}
    write_new(validation_dir(review) / 'generated_message_roundtrip.json', receipt)
    require(set(checks) == CDR_CHECK_NAMES and all(checks.values()), 'Actual generated-message CDR round trip failed')
    return receipt


def execute_suite_once(review, before):
    directory = validation_dir(review)
    write_new(directory / 'unittest.started.json', {'started_utc': utc(), 'execution_count': 1, 'source_binding_before': before,
        'automatic_retry': False, 'formal_seeds_consumed': False})
    log = directory / 'unittest.log'
    with log.open('x') as stream:
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
            cwd=Path(review['frozen_root']), stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
    return result, log.read_text(), log


def validate_build(review):
    root = Path(review['frozen_root'])
    directory = validation_dir(review)
    before = frozen_binding(review)
    original_before = verify_closed_capsule(review)
    isolation = read_small(directory / 'import_isolation.json')
    fastcdr = read_small(directory / 'fastcdr_provenance.json')
    cdr = read_small(directory / 'generated_message_roundtrip.json')
    require(isolation.get('isolated') is True and isolation.get('root') == str(root)
        and isolation.get('selected_bridge_overlay') == BRIDGE
        and isolation.get('bridge_package_prefix') == str((Path(BRIDGE) / 'install').resolve(strict=True))
        and set(isolation.get('module_files', {})) == set(MODULES) | set(review.get('additional_import_modules', []))
        and set(isolation.get('ros_package_prefixes', {})) == set(PACKAGES)
        and isolation.get('bridge_runtime_validation', {}).get('status') == 'PASS', 'Actual same-source import/bridge evidence missing')
    for name, path in isolation.get('module_files', {}).items():
        require(Path(path).resolve(strict=True).is_relative_to(root.resolve(strict=True))
            and Path(importlib.import_module(name).__file__).resolve(strict=True) == Path(path).resolve(strict=True), 'Actual module origin changed')
    for name, path in isolation['ros_package_prefixes'].items():
        actual = subprocess.check_output(['ros2', 'pkg', 'prefix', name], text=True).strip()
        require(Path(path).resolve(strict=True) == Path(actual).resolve(strict=True) == (root / 'ros2_ws/install').resolve(strict=True),
            'Actual installed ament prefix changed')
    actual_fastcdr = verify_fastcdr(review, write=False)
    require(fastcdr.get('status') == actual_fastcdr['status'] and fastcdr.get('inputs_sha256') == actual_fastcdr['inputs_sha256'], 'Actual FastCDR evidence changed')
    require(cdr.get('status') == 'PASS' and cdr.get('scope') == 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION'
        and isinstance(cdr.get('checks'), dict) and set(cdr['checks']) == CDR_CHECK_NAMES
        and all(v is True for v in cdr['checks'].values()) and cdr.get('execution_count') == 1
        and cdr.get('source_binding_after_roundtrip') == before, 'Actual CDR evidence missing/different')
    text = re.sub(r'\x1b\[[0-9;]*m', '', (directory / 'colcon_build.log').read_text())
    require(re.search(r'Summary:\s+4 packages finished', text), 'Four-package build summary missing')
    skip = dependencies()['humble33_skip_contract']
    skip_source = skip.validate_skip_sources({name: (root / name).read_text() for name in skip.SKIP_SOURCE_PATHS})
    started = utc()
    result, text, log = execute_suite_once(review, before)
    observed, error = None, None
    try:
        observed = skip.validate_observed_skips(text)
    except ValueError as caught:
        error = str(caught)
    node = shutil.which('node')
    node_docx = subprocess.run([node, '-e', 'require.resolve("docx")'], cwd=root, capture_output=True).returncode if node else None
    platform = {'os_name': os.name, 'sys_platform': sys.platform, 'bash_path': shutil.which('bash'),
        'zstd_path': shutil.which('zstd'), 'powershell_path': shutil.which('powershell'), 'node_path': node, 'node_docx_resolve_returncode': node_docx}
    platform_ok = os.name == 'posix' and sys.platform.startswith('linux') and platform['bash_path'] is not None \
        and platform['zstd_path'] is not None and platform['powershell_path'] is None and not (node and node_docx == 0)
    count = re.search(r'Ran (\d+) tests in ([0-9.]+)s', text)
    after = frozen_binding(review)
    original_after = verify_closed_capsule(review)
    passed = result.returncode == 0 and count is not None and int(count[1]) > 0 and re.search(r'(?m)^OK \(skipped=5\)$', text) \
        and 'FAILED' not in text and error is None and platform_ok and before == after and original_before == original_after
    report = {'created_utc': utc(), 'started_utc': started, 'status': 'PASS' if passed else 'FAIL', 'returncode': result.returncode,
        'tests': int(count[1]) if count else None, 'skipped': len(observed) if observed is not None else None,
        'execution_count': 1, 'source_binding_before': before, 'source_binding_after': after, 'source_unchanged': before == after,
        'freeze_source_sha256': before['freeze_source_sha256'], 'suite_log_sha256': sha(log),
        'final_review': review['_review_binding'], 'toolchain_canonical_sha256': review['toolchain_canonical_sha256'],
        'closed_original_evidence_before': original_before, 'closed_original_evidence_after': original_after,
        'closed_original_evidence_unchanged': original_before == original_after,
        'four_packages_built': True, 'module_ament_isolation': True, 'platform': platform,
        'skip_source_contract': skip_source, 'actual_skipped_tests': observed, 'skip_contract_error': error,
        'generated_message_roundtrip_sha256': sha(directory / 'generated_message_roundtrip.json'),
        'generated_message_roundtrip_path': str(directory / 'generated_message_roundtrip.json'),
        'bounded_action_terminal_must_be_PASS': True,
        'formal_seeds_consumed': False, 'runtime_acceptance': 'NOT_EVALUATED'}
    write_new(directory / 'build_validation_summary.json', report)
    require(passed, 'Actual full suite/build validation failed; original result retained, no retry')
    return report


@contextmanager
def exclusive_window():
    import fcntl
    with open(WINDOW_LOCK, 'a+', encoding='utf-8') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            stream.seek(0)
            stream.truncate()
            json.dump({'pid': os.getpid(), 'acquired_utc': utc()}, stream)
            stream.flush()
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def require_linux():
    require(os.name == 'posix' and sys.platform.startswith('linux') and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22', 'Mutable actions require actual WSL UAVHumble22')
    require(EXTERNAL.as_posix() == LINUX_EXTERNAL, 'Actual reviewed external tool location differs')


def child_action(review, action, phase):
    require_linux()
    deps = dependencies()
    receipt_dir = EXTERNAL / ('reviewed_freeze_actions_' + Path(review['frozen_root']).name.removeprefix('uav_tracking_fullplan_')) / action
    require(os.environ.get('REVIEWED_FREEZE_RECEIPT_DIR') == str(receipt_dir), 'Internal receipt path differs')
    owned = read_small(receipt_dir / 'action.process.json')
    launcher_text = os.environ.get('REVIEWED_FREEZE_PARENT_PID', '')
    require(launcher_text.isdigit() and int(launcher_text) > 1, 'No actual bounded launcher PID')
    process_stat = deps['bounded_humble33_action'].process_stat
    leader = process_stat(owned.get('pid', -1))
    launcher = process_stat(int(launcher_text))
    require(leader is not None and launcher is not None and leader.get('ppid') == launcher['pid']
        and leader.get('start_ticks') == owned.get('observed_leader_stat', {}).get('start_ticks')
        and os.getpgrp() == os.getsid(0) == owned.get('pid') == owned.get('pgid') == owned.get('session'),
        'Internal process escaped the actual newly owned bounded session')
    require(os.environ.get('REVIEWED_FREEZE_ACTION') == action
        and os.environ.get('STAGE1_PROJECT_ROOT') == review['frozen_root'] and os.environ.get('ROS_DISTRO') == 'humble'
        and os.environ.get('STAGE1_ROS_GZ_WS') == BRIDGE and os.environ.get('STAGE1_PX4_ROOT') == PX4_ROOT, 'Use the bounded reviewed clean-environment entry')
    before = action_binding(review, action)
    if phase == 'post-build':
        require(action == 'build', 'Post-build phase belongs only to build')
        result = installed_checks(review)
    else:
        require(phase == 'action', 'Unknown internal phase')
        runtime_contracts(review, review['source_root'] if action in ('prepare', 'copy') else review['frozen_root'])
        result = {'prepare': prepare, 'copy': copy_source, 'build': build, 'validate': validate_build}[action](review)
    require(action_binding(review, action) == before, 'Source/review/closed originals changed during child action')
    if action == 'prepare':
        write_new(Path(os.environ['REVIEWED_FREEZE_RECEIPT_DIR']) / 'preparation.json', result)
    return result


def launch(review, action, review_path, review_sha):
    require_linux()
    deps = dependencies()
    binding = lambda phase: action_binding(review, action)
    binding('before')  # Before reserving any directory or opening the lock.
    receipts = EXTERNAL / ('reviewed_freeze_actions_' + Path(review['frozen_root']).name.removeprefix('uav_tracking_fullplan_'))
    require(not receipts.is_symlink(), 'Receipt root cannot be a symlink')
    with exclusive_window():
        binding('locked')
        receipts.mkdir(exist_ok=True)
        environment = dict(os.environ, REVIEWED_FREEZE_ACTION=action, REVIEWED_FREEZE_PARENT_PID=str(os.getpid()),
            REVIEWED_FREEZE_RECEIPT_DIR=str(receipts / action))
        command = ['/bin/bash', str(EXTERNAL / 'reviewed_freeze_build.sh'), action, str(review_path), review_sha]
        return deps['bounded_humble33_action'].run_bounded(command, receipts / action, action=action,
            timeout_s=ACTIONS[action], grace_s=30., kill_confirm_s=5., binding=binding, environment=environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', *ACTIONS))
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    parser.add_argument('--internal-phase', choices=('action', 'post-build'), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.action == 'describe':
        require(args.review is None and args.review_sha256 is None and args.internal_phase is None, 'Describe does not admit a real action')
        print(json.dumps({'scope': SCOPE, 'actions': list(ACTIONS), 'requires_existing_final_review': True,
            'publishes_review': False, 'default_real_profile': None, 'tools_manifest': tools_manifest(),
            'toolchain_canonical_sha256': canonical(tools_manifest()), 'automatic_next_action': False,
            'runtime_acceptance': 'NOT_EVALUATED'}, indent=2))
        return 0
    try:
        review = load_review(args.review, args.review_sha256, args.action)
        if args.internal_phase:
            print(json.dumps(child_action(review, args.action, args.internal_phase)))
            return 0
        result = launch(review, args.action, args.review, args.review_sha256)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else (124 if result['status'] == 'TIMED_OUT' else 2)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'ACTION_REFUSED_OR_FAILED', 'action': args.action, 'reason': type(error).__name__ + ':' + str(error),
            'runtime_acceptance': 'NOT_EVALUATED', 'automatic_retry': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
