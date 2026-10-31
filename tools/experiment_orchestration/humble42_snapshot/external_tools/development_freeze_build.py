"""Explicit512 source/build supplement; legacy tools and history stay intact.

The old generic manifest identifies the unchanged implementations reused for
copy primitives, colcon, isolation, CDR and suite validation. This driver and
its resource guard have a separate mandatory identity in the final review.
No old resource preflight is claimed for512. No flight action is provided.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import reviewed_freeze_build as generic
import development_resource_guard as resource

require, sha, canonical = generic.require, generic.sha, generic.canonical
EXTERNAL = Path(__file__).resolve().parent
OWN_FILES = ('development_freeze_build.py', 'development_freeze_build.sh',
             'test_development_freeze_build.py')
GENERIC_CANONICAL = 'e57017201f1033847e49bb7843b1ef61bad28c21ac9f16e876736498980219cf'
SCOPE = 'EXPLICIT512_RESOURCE_SUPPLEMENT_WITH_UNCHANGED_GENERIC_BUILD_IMPLEMENTATIONS'
STATUS = 'FINAL_DEVELOPMENT_BUILD_RESOURCE_OVERRIDE_INDEPENDENTLY_REVIEWED'
RECEIPT = {'path': 'config/car_sim_train20_04_m512_resource_receipt.json',
           'sha256': '9abeaca3a892e61761564bc7116bb8aed34d9864f4f7406bd9f3a4bc59f3c26c'}


def tool_manifest():
    require(canonical(generic.tools_manifest()) == GENERIC_CANONICAL,
            'Unchanged reused generic tool identity required')
    for module in (generic, resource):
        require(Path(module.__file__).resolve(strict=True) ==
                (EXTERNAL/Path(module.__file__).name).resolve(strict=True),
                'Build dependency escaped explicit external tool location')
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
                'Missing bounded build supplement source/test')
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': files,
            'reused_generic_canonical_sha256': GENERIC_CANONICAL,
            'resource_guard': resource.tool_manifest(),
            'actual_build_and_suite_functions': ['reviewed_freeze_build.build',
                'reviewed_freeze_build.installed_checks', 'reviewed_freeze_build.validate_build'],
            'legacy_runtime_contracts_called': False, 'dependency_globals_modified': False,
            'flight_actions_authorized': False, 'formal_seed_use_authorized': False}


def expected_override():
    """Template only: the assembler never publishes a final source review."""
    return {'schema_version': 1, 'status': STATUS, 'scope': SCOPE,
            'tools_canonical_sha256': canonical(tool_manifest()),
            'resource_revision': 'car_train20_04_m512_cpu4_v1', 'receipt': dict(RECEIPT),
            'supersedes_legacy_resource_choice_only': True,
            'legacy_runtime_invariant_field_is_schema_compatibility_only': True,
            'unchanged_contracts': ['safety', 'bridge', 'magnetic', 'environment',
                                    'source_binding', 'bounded_owner', 'build', 'suite'],
            'legacy640_runtime_acceptance_claimed': False,
            'runtime_acceptance_claimed': False, 'formal_seed_use_authorized': False}


def supplement_binding(review):
    override = review.get('development_resource_override')
    require(type(override) is dict and canonical(override) == canonical(expected_override()),
            'Explicit independently reviewed512 build/resource supplement required')
    require(review.get('toolchain_canonical_sha256') == GENERIC_CANONICAL
            and review.get('files', {}).get(RECEIPT['path']) == RECEIPT['sha256'],
            'Supplement must bind actual512 receipt and unchanged reused generic tools')
    protocol_name = 'planning/reliability-v4-preregistration.json'
    require(generic.valid_sha(review.get('files', {}).get(protocol_name)),
            'Supplement needs the reviewed protocol binding')
    return {'override': override, 'tools_manifest': tool_manifest(),
            'reviewed_protocol_sha256': review['files'][protocol_name]}


def load_review(path, digest, action):
    review = generic.load_review(path, digest, action)
    supplement_binding(review)
    return review


def action_binding(review, action):
    return {**generic.action_binding(review, action),
            'development_resource_override': supplement_binding(review)}


def runtime_contracts(review, root):
    supplement_binding(review)
    runtime = resource.runtime_contracts(review, root)
    verify_512_runtime(runtime, root)
    return runtime


def verify_512_runtime(runtime, root):
    """No legacy fallback is permitted for this explicitly512 supplement."""
    actual = runtime.get('resource') if isinstance(runtime, dict) else None
    require(isinstance(actual, dict)
            and actual.get('registration') == {'revision': resource.REVISION,
                'receipt': RECEIPT, 'scope': resource.SCOPE}
            and actual.get('receipt') == {'path': str(Path(root)/RECEIPT['path']),
                                          'sha256': RECEIPT['sha256']}
            and type(actual.get('inference_image_size')) is int and actual['inference_image_size'] == 512
            and type(actual.get('inference_threads')) is int and actual['inference_threads'] == 4
            and actual.get('model_sha256') == resource.MODEL_SHA
            and actual.get('scope') == resource.SCOPE
            and actual.get('closed_loop_validated') is False
            and actual.get('formal_seed_use_authorized') is False
            and isinstance(actual.get('evidence_bindings'), list) and actual['evidence_bindings'],
            'Actual complete512 resource verification required; legacy or empty evidence is refused')
    resource.verify_runtime_evidence(runtime)
    return runtime


def prepare(review):
    require(not any(p.exists() or p.is_symlink() for p in
            (Path(review['frozen_root']), Path(review['results_root']))),
            'New source/results must be unreserved')
    runtime = runtime_contracts(review, review['source_root'])
    resource.verify_runtime_evidence(runtime)
    return {'scope': SCOPE, 'action': 'prepare',
            'runtime_contracts': runtime,
            'root_created': False, 'build_executed': False}


def copy_source(review):
    roots = (Path(review['frozen_root']), Path(review['results_root']))
    require(not any(p.exists() or p.is_symlink() for p in roots), 'No overwrite/retry of frozen paths')
    require(all(p.parent.is_dir() and not p.parent.is_symlink() for p in roots),
            'Dedicated source/results parents must exist')
    before, original = generic.candidate_binding(review), generic.verify_closed_capsule(review)
    roots[0].mkdir()
    roots[1].mkdir()
    (roots[0]/'results').symlink_to(roots[1], target_is_directory=True)
    directory = generic.validation_dir(review)
    directory.mkdir()
    for name, digest in review['files'].items():
        override = review['source_overrides'].get(name)
        source = Path(override['path']) if override else Path(review['source_root'])/name
        generic.copy_registered_file(source, roots[0]/generic.relative(name), digest)
    runtime = runtime_contracts(review, roots[0])
    resource.verify_runtime_evidence(runtime)
    require(generic.candidate_binding(review) == before and generic.verify_closed_capsule(review) == original,
            'Source/original evidence changed during explicit copy')
    generic.write_new(directory/'source_freeze_manifest.json', {
        'schema_version': 1, 'created_utc': generic.utc(), 'scope': generic.SCOPE,
        'source_root': str(roots[0]), 'results_root': str(roots[1]),
        'source_commit': review['source_commit'], 'files': review['files'],
        'classified_source_hashes': review['classified_source_hashes'],
        'freeze_source_sha256': canonical(review['files']), 'source_file_count': len(review['files']),
        'source_bytes_policy': before, 'final_review': review['_review_binding'],
        'toolchain_canonical_sha256': GENERIC_CANONICAL,
        'development_resource_override': supplement_binding(review),
        'closed_original_evidence': original, 'runtime_contracts': runtime,
        'build_executed': False, 'tests_executed': False,
        'formal_seeds_consumed': False, 'runtime_acceptance': 'NOT_EVALUATED'})
    archived = directory/'external_wrappers'
    archived.mkdir()
    names = set(generic.tools_manifest()['files']) | set(OWN_FILES) | set(resource.tool_manifest()['files'])
    for name in sorted(names):
        shutil.copy2(EXTERNAL/name, archived/name)
    generic.write_new(archived/'development_build_tools_manifest.json', tool_manifest())
    shutil.copy2(review['_review_binding']['path'], directory/'final_source_review.json')
    return generic.frozen_binding(review)


def receipts(review, action):
    label = Path(review['frozen_root']).name.removeprefix('uav_tracking_fullplan_')
    return EXTERNAL/('reviewed_freeze_actions_'+label)/action


def child_action(review, action, phase):
    generic.require_linux()
    deps = generic.dependencies()
    directory = receipts(review, action)
    require(os.environ.get('DEVELOPMENT_FREEZE_RECEIPT_DIR') == str(directory),
            'Actual supplement receipt path differs')
    owned = generic.read_small(directory/'action.process.json')
    parent = os.environ.get('DEVELOPMENT_FREEZE_PARENT_PID', '')
    require(parent.isdigit() and int(parent) > 1, 'No bounded supplement launcher PID')
    stat = deps['bounded_humble33_action'].process_stat
    leader, launcher = stat(owned.get('pid', -1)), stat(int(parent))
    require(leader is not None and launcher is not None
            and leader.get('ppid') == launcher['pid']
            and leader.get('start_ticks') == owned.get('observed_leader_stat', {}).get('start_ticks')
            and os.getpgrp() == os.getsid(0) == owned.get('pid') == owned.get('pgid') == owned.get('session'),
            'Supplement child escaped its actual bounded process group')
    require(os.environ.get('DEVELOPMENT_FREEZE_ACTION') == action
            and os.environ.get('STAGE1_PROJECT_ROOT') == review['frozen_root']
            and os.environ.get('ROS_DISTRO') == 'humble'
            and os.environ.get('STAGE1_ROS_GZ_WS') == generic.BRIDGE
            and os.environ.get('STAGE1_PX4_ROOT') == generic.PX4_ROOT,
            'Use the explicit clean-environment supplement entry')
    before = action_binding(review, action)
    runtime_path = directory/'runtime_preflight.json'
    runtime_root = review['source_root'] if action in ('prepare', 'copy') else review['frozen_root']
    if phase == 'post-build':
        require(action == 'build', 'Post-build belongs only to build')
        preflight = generic.read_small(runtime_path)
        require(preflight.get('action_binding') == before,
                'Post-build resource evidence must bind the actual initial action')
        runtime = preflight['runtime']
        closure = generic.read_small(directory/'runtime_preflight_action_closure.json')
        require(closure.get('action_binding') == before
                and closure.get('before_sha256') == closure.get('after_sha256') == sha(runtime_path),
                'Initial actual resource preflight was changed or not closed')
        verify_512_runtime(runtime, runtime_root)
        result = generic.installed_checks(review)
    else:
        require(phase == 'action', 'Unknown supplement child phase')
        runtime = runtime_contracts(review, runtime_root)
        generic.write_new(runtime_path, {'schema_version': 1, 'created_utc': generic.utc(),
            'action_binding': before, 'runtime': runtime})
        preflight_before = sha(runtime_path)
        result = {'prepare': prepare, 'copy': copy_source,
                  'build': generic.build, 'validate': generic.validate_build}[action](review)
    if phase == 'post-build':
        preflight_before = closure['after_sha256']
    verify_512_runtime(runtime, runtime_root)
    require(sha(runtime_path) == preflight_before, 'Actual runtime preflight changed during action')
    require(action_binding(review, action) == before,
            'Source, reviewed supplement, tools or history changed during actual action')
    generic.write_new(directory/('runtime_preflight_'+phase.replace('-', '_')+'_closure.json'), {
        'schema_version': 1, 'finished_utc': generic.utc(), 'action_binding': before,
        'before_sha256': preflight_before, 'after_sha256': sha(runtime_path),
        'strict512_resource_verified': True, 'evidence_files_unchanged': True})
    if action == 'prepare':
        generic.write_new(directory/'preparation.json', result)
    return result


def launch(review, action, review_path, review_sha):
    generic.require_linux()
    bound = lambda phase: action_binding(review, action)
    bound('before')
    directory = receipts(review, action)
    require(not directory.parent.is_symlink(), 'Supplement receipt root cannot be a symlink')
    with generic.exclusive_window():
        bound('locked')
        directory.parent.mkdir(exist_ok=True)
        environment = dict(os.environ, DEVELOPMENT_FREEZE_ACTION=action,
            DEVELOPMENT_FREEZE_PARENT_PID=str(os.getpid()), DEVELOPMENT_FREEZE_RECEIPT_DIR=str(directory))
        command = ['/bin/bash', str(EXTERNAL/'development_freeze_build.sh'),
                   action, str(review_path), review_sha]
        return generic.dependencies()['bounded_humble33_action'].run_bounded(
            command, directory, action=action, timeout_s=generic.ACTIONS[action],
            grace_s=30., kill_confirm_s=5., binding=bound, environment=environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', *generic.ACTIONS))
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    parser.add_argument('--internal-phase', choices=('action', 'post-build'), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.action == 'describe':
            require(args.review is None and args.review_sha256 is None and args.internal_phase is None,
                    'Describe cannot admit an action')
            manifest = tool_manifest()
            print(json.dumps({'status': 'PENDING_INDEPENDENT_REVIEW', 'tool_manifest': manifest,
                'tools_canonical_sha256': canonical(manifest), 'actual_action_executed': False}, indent=2))
            return 0
        review = load_review(args.review, args.review_sha256, args.action)
        if args.internal_phase:
            print(json.dumps(child_action(review, args.action, args.internal_phase)))
            return 0
        result = launch(review, args.action, args.review, args.review_sha256)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else (124 if result['status'] == 'TIMED_OUT' else 2)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'DEVELOPMENT_BUILD_REFUSED_OR_FAILED', 'action': args.action,
            'reason': type(error).__name__+':'+str(error), 'runtime_acceptance': 'NOT_EVALUATED',
            'automatic_retry': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
