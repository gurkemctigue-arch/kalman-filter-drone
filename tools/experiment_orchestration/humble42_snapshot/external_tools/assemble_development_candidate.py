"""Bind an actual new cold build into a PENDING development candidate only."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
from pathlib import Path

import development_runner as core
import development_freeze_build as build
import reviewed_freeze_build as generic


def require_closed_build(review, frozen, facts, actions):
    """PENDING still records only genuine completed, healthy build evidence."""
    require = generic.require
    original = generic.verify_closed_capsule(review)
    directory = generic.validation_dir(review)
    require(facts.get('status') == 'PASS' and type(facts.get('returncode')) is int
            and facts['returncode'] == 0 and type(facts.get('execution_count')) is int
            and facts['execution_count'] == 1 and facts.get('four_packages_built') is True
            and facts.get('module_ament_isolation') is True and type(facts.get('skipped')) is int
            and facts['skipped'] == 5 and type(facts.get('tests')) is int and facts['tests'] > 0
            and facts.get('source_binding_before') == facts.get('source_binding_after') == frozen
            and facts.get('source_unchanged') is True
            and facts.get('freeze_source_sha256') == frozen['freeze_source_sha256']
            and facts.get('toolchain_canonical_sha256') == build.GENERIC_CANONICAL
            and facts.get('final_review') == review['_review_binding']
            and facts.get('closed_original_evidence_before') == facts.get('closed_original_evidence_after') == original
            and facts.get('closed_original_evidence_unchanged') is True
            and facts.get('formal_seeds_consumed') is False
            and facts.get('bounded_action_terminal_must_be_PASS') is True
            and facts.get('suite_log_sha256') == generic.sha(directory/'unittest.log')
            and facts.get('generated_message_roundtrip_sha256') == generic.sha(directory/'generated_message_roundtrip.json'),
            'Actual complete cold-build/full-suite evidence required')
    for action in ('build', 'validate'):
        value = generic.read_small(actions/action/'action.terminal.json')
        before = value.get('binding_before')
        require(value.get('scope') == 'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE'
                and value.get('action') == action and value.get('status') == 'PASS'
                and type(value.get('direct_child_returncode')) is int and value['direct_child_returncode'] == 0
                and type(value.get('execution_count')) is int and value['execution_count'] == 1
                and value.get('cleanup', {}).get('actual_proc_group_empty') is True
                and value['cleanup'].get('direct_child_reaped') is True
                and value['cleanup'].get('residual_processes') == []
                and isinstance(before, dict) and before == value.get('binding_after')
                and before.get('source') == frozen and before.get('review') == review['_review_binding']
                and before.get('closed_original_evidence') == original,
                'Actual same-source healthy bounded build/validate action required: '+action)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--core-tools-sha256', required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    generic.require_linux()
    require = generic.require
    require(args.core_tools_sha256 == generic.canonical(core.tool_manifest()),
            'Actual independently reviewed core tools required')
    require(args.output.parent.resolve(strict=True) == generic.EXTERNAL.resolve(strict=True)
            and args.output.name.startswith('development_candidate_') and args.output.suffix == '.json'
            and not args.output.exists(), 'Exclusive named external PENDING candidate required')
    review = build.load_review(args.review, args.review_sha256, 'validate')
    root = Path(review['frozen_root'])
    frozen = generic.frozen_binding(review)
    summary = root/'results/freeze_validation/build_validation_summary.json'
    facts = generic.read_small(summary)
    def bound(path):
        return core.stable.metadata_binding(path, json_only=True)
    label = root.name.removeprefix('uav_tracking_fullplan_')
    actions = generic.EXTERNAL/('reviewed_freeze_actions_'+label)
    require_closed_build(review, frozen, facts, actions)
    candidate = {'schema_version': 1, 'scope': core.SCOPE,
        'status': 'PENDING_INDEPENDENT_DEVELOPMENT_CANDIDATE_REVIEW_NOT_EXECUTABLE',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'frozen_root': str(root),
        'prefix': args.prefix, 'source_review': review['_review_binding'],
        'protocol': bound(root/core.policy.PROTOCOL_PATH),
        'tools_canonical_sha256': args.core_tools_sha256,
        'development_build_driver_tools_canonical_sha256': generic.canonical(build.tool_manifest()),
        'build_evidence': {'summary': bound(summary),
            **{action+'_terminal': bound(actions/action/'action.terminal.json') for action in ('build', 'validate')}},
        'original41_closure': {'path': generic.LINUX_EXTERNAL+'/'+core.ORIGINAL_CLOSURE,
                               'sha256': core.ORIGINAL_CLOSURE_SHA},
        'pressure_reuse': {'scope': core.INFRA_SCOPE,
            'implementation_hashes': {name: review['files'][name] for name in core.INFRA_FILES},
            'original_execution_terminal': {'path': core.ORIGINAL_ROOT+
                '/results/freeze_validation/observer_archive_pressure01/execution_terminal.json',
                'sha256': 'a60e271660923c76814b92773a1d7e57d121ff8013820b3c83fdcadeaf23e03f'}},
        'core_classes': list(core.CLASSES),
        'core_groups': list(core.GROUPS),
        'authorized_actions': ['plan-core', 'run-core'],
        **{name: False for name in core.FALSE_FIELDS}}
    candidate['experiment'] = core.experiment(candidate)
    temporary = deepcopy(candidate)
    temporary['status'] = core.CANDIDATE
    core.validate_candidate(temporary)
    core.require_supplement_build(temporary, review)
    generic.write_new(args.output, candidate)
    print({'status': 'PENDING_ONLY_NOT_EXECUTABLE', 'path': str(args.output),
           'sha256': generic.sha(args.output), 'flight_or_plan_started': False})


if __name__ == '__main__':
    main()
