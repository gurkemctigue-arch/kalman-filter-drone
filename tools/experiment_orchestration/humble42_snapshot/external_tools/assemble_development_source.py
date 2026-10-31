"""Assemble a pending source/build review from a closed predecessor.

This creates metadata only. A separate review must validate the delta before
the existing freeze/build tool can consume a final review. It authorizes no
flight and does not convert predecessor failures into acceptance.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

import reviewed_freeze_build as generic
import development_runner as development
import development_freeze_build as build_driver


def assemble(args):
    require, sha, read = generic.require, generic.sha, generic.read_small
    source = args.source_root.resolve(strict=True)
    require(str(source).startswith('/mnt/d/'), 'Explicit physical D-drive source required')
    prior_path = args.baseline_review.resolve(strict=True)
    require(sha(prior_path) == args.baseline_review_sha256, 'Predecessor review changed')
    prior = generic.validate_review(read(prior_path))
    prior_root = Path(prior['frozen_root'])
    require(str(prior_root) == development.ORIGINAL_ROOT
            and sha(prior_path) == development.ORIGINAL_REVIEW_SHA,
            'This release migrates the independently closed original41 predecessor only')
    require(generic.canonical(development.tool_manifest()) == args.core_tools_sha256,
            'Explicit independently reviewed closure-verifier tool identity required')
    manifest_path = prior_root/'results/freeze_validation/source_freeze_manifest.json'
    manifest = read(manifest_path)
    require(manifest['files'] == prior['files'] and manifest['source_commit'] == prior['source_commit'],
            'Actual predecessor manifest differs')
    terminal = args.closed_core_terminal.resolve(strict=True)
    require(sha(terminal) == args.closed_core_terminal_sha256, 'Predecessor core terminal changed')
    original = read(terminal)
    require(original.get('planned_count') == original.get('attempt_count') == original.get('terminal_count') == 12
            and isinstance(original.get('finished_utc'), str)
            and original.get('cleanup', {}).get('residual_processes') == [], 'Original full core is not closed')
    require(sum(original.get('status_counts', {}).values()) == 12
            and original.get('entry_binding_before') == original.get('entry_binding_after'),
            'Original core denominator/source closure differs')
    closure_path = args.closed_core_verification.resolve(strict=True)
    require(sha(closure_path) == args.closed_core_verification_sha256, 'Original closure verification changed')
    closure = read(closure_path)
    require(closure.get('all_pass_required') is False and closure.get('safety_or_extension_admitted') is False
            and isinstance(closure.get('finished_utc'), str), 'Closure must retain the original failure boundary')
    verifier = closure.get('original_closure_verifier', {})
    require(verifier.get('result') == 'PASS' and verifier.get('completed_count') == 12
            and verifier.get('all_original_core_cells_pass') is False, 'Actual non-accepting closure verifier required')
    # Reuse the independently reviewed metadata verifier. It reopens the
    # actual12 records, starts, attempts and evaluator reports, recomputes
    # their original verdicts and validates the real archived owner result.
    # No rosbag, raw telemetry, images or new flight is consumed here.
    audited = development.original_closure_binding()
    require(Path(audited['receipt']['path']).samefile(closure_path)
            and audited['receipt']['sha256'] == args.closed_core_verification_sha256
            and Path(audited['execution_terminal']['path']).samefile(terminal)
            and audited['execution_terminal']['sha256'] == args.closed_core_terminal_sha256,
            'Closure receipt/actual terminal/predecessor must be the same independently verified files')
    source_bound = original.get('entry_binding_before', {}).get('source41_binding', {})
    require(source_bound.get('source_review', {}).get('sha256') == args.baseline_review_sha256
            and source_bound.get('source', {}).get('manifest_sha256') == sha(manifest_path)
            and source_bound.get('source', {}).get('freeze_source_sha256') == generic.canonical(prior['files']),
            'Original core closure does not bind the actual predecessor source')

    def git(*tokens):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=true', '-C', str(source), *tokens])
    require(not git('status', '--porcelain'), 'A clean committed candidate is required')
    commit = git('rev-parse', 'HEAD').decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Full commit required')
    subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor', prior['source_commit'], commit], check=True)
    tracked = sorted(name.decode() for name in git('ls-files', '-z').split(b'\0') if name)
    ignored = prior['assembly_provenance']['inherited_ignored_resources']
    require(not set(tracked) & set(ignored), 'Inherited ignored assets became tracked')
    files = {}
    for name in sorted(tracked + ignored):
        override = prior['source_overrides'].get(name)
        path = Path(override['path']) if override else source/name
        require(path.is_file() and not path.is_symlink(), 'Missing regular candidate asset: '+name)
        files[name] = sha(path)
    delta = generic.delta(prior['files'], files)
    actual_git_delta = {'changed': [], 'added': [], 'removed': []}
    for code, key in [('M', 'changed'), ('A', 'added'), ('D', 'removed')]:
        actual_git_delta[key] = sorted(name.decode() for name in git('diff', '--no-renames', '--name-only',
            '-z', '--diff-filter='+code, prior['source_commit'], commit, '--').split(b'\0') if name)
    require(actual_git_delta == delta, 'Physical/Git source delta differs')
    runner = generic.runner_at(source)
    classified = runner.source_hashes(source)
    classified['config/px4_magnetic_runtime.json'] = files['config/px4_magnetic_runtime.json']
    require(all(files.get(name) == digest for name, digest in classified.items()), 'Classified source bytes not covered')
    protocol_path = source/runner.PROTOCOL_PATH
    protocol = read(protocol_path)
    runner.validate_protocol(protocol)
    resource_override = build_driver.expected_override()
    generic.require(protocol.get('car_input_scale_registration') ==
                    getattr(runner, 'CAR_INPUT_SCALE_REGISTRATION_TRAIN04_512', None),
                    'This assembler release requires the explicit512 candidate')
    resource_override['status'] = 'PENDING_INDEPENDENT_RESOURCE_BUILD_REVIEW_NOT_EXECUTABLE'

    inherited_path = Path(prior['closed_evidence']['path'])
    require(sha(inherited_path) == prior['closed_evidence']['sha256'], 'Inherited historical capsule changed')
    inherited = read(inherited_path)
    retained, facts = {}, []
    def retain(path, fields=()):
        path = Path(path)
        value = read(path)
        retained[str(path)] = {'sha256': sha(path), 'bytes': path.stat().st_size}
        for field in fields:
            actual = value
            for part in field.split('.'):
                actual = actual[part]
            facts.append({'path': str(path), 'field': field, 'expected': actual})
        return value
    # Bind older history as its unchanged external capsule. Preserve the
    # original32 direct files required by the existing build verifier.
    for name in inherited['files']:
        if '/results/frozen_fullplan_v4_humble32/' in name:
            retain(name)
    original32 = inherited['boundaries']['original32_core']['receipt']
    retain(original32, ('status_counts', 'returncode'))
    for slot in read(original32)['slots']:
        matches = [name for name in retained if '/slots/' in name and Path(name).name == slot['slot']+'.json']
        require(len(matches) == 1, 'Original32 slot evidence missing')
        retain(matches[0], ('status',))
    retain(inherited_path, ('all_inputs_closed', 'readiness_claimed'))
    retain(prior_path, ('source_commit', 'files', 'closed_evidence'))
    retain(manifest_path)
    retain(terminal, ('status_counts', 'returncode', 'cleanup', 'finished_utc'))
    retain(closure_path, ('original_closure_verifier', 'all_pass_required', 'safety_or_extension_admitted'))
    retain(verifier['core_plan']['plan']['path'], ('plan_sha256',))
    for row in verifier['original_terminals']:
        retain(row['record_binding']['path'], ('status', 'record_sha256', 'plan_sha256'))
        retain(row['record_binding']['started_marker']['path'])
        retain(row['attempt_terminal']['path'])
    predecessor = generic.EXTERNAL/('reviewed_freeze_actions_'+prior_root.name.removeprefix('uav_tracking_fullplan_'))/'validate/action.terminal.json'
    pred = retain(predecessor, ('status', 'direct_child_returncode'))
    require(pred.get('status') == 'PASS' and pred.get('direct_child_returncode') == 0
            and pred.get('binding_before') == pred.get('binding_after'), 'Predecessor build validation is not closed')
    capsule = {'schema_version': 1, 'scope': 'CLOSED_32_CORE_AND_PREDECESSOR_METADATA_ONLY',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'all_inputs_closed': True,
        'payload_reread': False, 'readiness_claimed': False, 'files': dict(sorted(retained.items())),
        'retained_fields': facts, 'boundaries': {'original32_core': inherited['boundaries']['original32_core'],
            'predecessor': {'closed': True, 'receipt': str(predecessor)}},
        'predecessor_core_outcome': {'status_counts': original['status_counts'],
            'core_terminal': str(terminal), 'original_failure_retained': True, 'runtime_acceptance': False}}
    frozen = '/root/uav_tracking_fullplan_'+args.name
    review = deepcopy(prior)
    review.pop('independent_review_receipt', None)
    review.update(status='PENDING_ROOT_INDEPENDENT_REVIEW_NOT_EXECUTABLE',
        created_utc=datetime.now(timezone.utc).isoformat(), source_root=str(source), source_commit=commit,
        frozen_root=frozen, results_root=str(source/'results'/('frozen_fullplan_'+args.name)),
        files=files, classified_source_hashes=classified, allowed_delta=delta,
        baseline={'source_commit': prior['source_commit'], 'root': str(prior_root),
            'manifest_path': str(manifest_path), 'manifest_sha256': sha(manifest_path),
            'files_canonical_sha256': generic.canonical(prior['files'])},
        candidate_protocol={'path': str(protocol_path), 'sha256': sha(protocol_path),
            'status': 'COMMITTED_SOURCE_ONLY_NOT_FROZEN_NOT_EXECUTED',
            'exclusive_navigation': runner.exclusive_navigation_summary(protocol),
            'pacing_revision': runner.simulation_pacing_summary(protocol).get('revision')},
        development_resource_override=resource_override,
        assembly_provenance={'status': 'ACTUAL_PENDING_SOURCE_REVIEW_ONLY', 'tracked_file_count': len(tracked),
            'inherited_ignored_resources': ignored, 'source_file_count': len(files),
            'classified_source_count': len(classified), 'formal_or_runtime_acceptance_claimed': False})
    capsule_path = generic.EXTERNAL/('reviewed_freeze_closed_'+args.name+'_pending01.json')
    review_path = generic.EXTERNAL/('reviewed_freeze_review_'+args.name+'_pending01.json')
    require(not any(path.exists() for path in (Path(frozen), Path(review['results_root']), capsule_path, review_path)),
            'Candidate paths must be new')
    # No final review is written here, even after successful schema checks.
    generic.write_new(capsule_path, capsule)
    review['closed_evidence'] = {'path': str(capsule_path), 'sha256': sha(capsule_path)}
    schema_only = deepcopy(review)
    schema_only['status'] = generic.FINAL_STATUS
    generic.validate_review(schema_only)
    generic.verify_closed_capsule(schema_only)
    generic.candidate_binding(schema_only)
    generic.write_new(review_path, review)
    print(json.dumps({'status': 'PENDING_ONLY_NOT_EXECUTABLE', 'review': str(review_path),
        'review_sha256': sha(review_path), 'capsule': str(capsule_path), 'delta': delta}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--baseline-review', required=True, type=Path)
    parser.add_argument('--baseline-review-sha256', required=True)
    parser.add_argument('--closed-core-terminal', required=True, type=Path)
    parser.add_argument('--closed-core-terminal-sha256', required=True)
    parser.add_argument('--closed-core-verification', required=True, type=Path)
    parser.add_argument('--closed-core-verification-sha256', required=True)
    parser.add_argument('--core-tools-sha256', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_]+', args.name):
        parser.error('name must be a dedicated alphanumeric/underscore suffix')
    assemble(args)


if __name__ == '__main__':
    main()
