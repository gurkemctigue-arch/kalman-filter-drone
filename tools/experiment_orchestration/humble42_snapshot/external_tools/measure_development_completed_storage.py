"""Stat actual candidate core12 + extension16, without payload reads/admission.

Import and describe are inert. The explicit measure action needs the reviewed
new candidate's real source/build, core contract, safety4 and extension contract.
Every original full75s terminal is retained. Existing budget/guard implementations
alone decide whole280 physical capacity; this collector never admits formal work.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys

EXTERNAL = Path(__file__).resolve().parent
KIND = 'PARAMETERIZED_COMPLETE28_STAT_ONLY_NOT_CAPACITY_ADMISSION'
ARCHIVE_POLICY = 'ext4_sqlite_close_standard_zstd_verified_native_read'
OWN = ('measure_development_completed_storage.py', 'measure_development_completed_storage.sh',
       'test_measure_development_completed_storage.py')
METADATA_SUFFIXES = {'.py', '.sh', '.json', '.jsonl', '.yaml', '.yml', '.log', '.sdf', '.bson', '.md'}
MAX_METADATA_BYTES = 16 * 1024 ** 2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    path = Path(path)
    require(path.suffix.lower() in METADATA_SUFFIXES and path.is_file()
            and not path.is_symlink() and path.stat().st_size <= MAX_METADATA_BYTES,
            'Bounded ordinary metadata/code required; payload reads are forbidden: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def read_small(path):
    sha(path)
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))
    require(isinstance(value, dict), 'JSON object required')
    return value


def binding(path):
    return {'path': str(path), 'sha256': sha(path)}


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def dependencies():
    """Only import the named reviewed external implementations, never ROS/model."""
    extension = importlib.import_module('development_extension')
    for module in (extension, extension.core, extension.safety, extension.generic,
                   extension.stable, extension.owner):
        require(Path(module.__file__).resolve(strict=True) ==
                (EXTERNAL / Path(module.__file__).name).resolve(strict=True),
                'Dependency import escaped the named external tools')
    return extension


def helper_manifest():
    extension = dependencies()
    return {'schema_version': 1, 'scope': KIND,
        'files': {name: sha(EXTERNAL / name) for name in OWN},
        'extension_tools_canonical_sha256': canonical(extension.tool_manifest()),
        'core_tools_canonical_sha256': canonical(extension.core.tool_manifest()),
        'safety_tools_canonical_sha256': canonical(extension.safety.tool_manifest()),
        'source_review_and_build_binding': 'actual extension admission -> reviewed candidate/source and actual strict512 cold build',
        'runtime_prerequisites': ['same-candidate original core12 all PASS',
                                  'same-candidate original safety4 all PASS with actual frozen guard',
                                  'all16 original extension attempts completed healthily'],
        'matrix_order': 'existing canonical person/car and original groups/conditions',
        'development_cells': {'core': 12, 'extension': 16},
        'formal_mapping': {'core': 120, 'extension': 160, 'repeats_per_cell': 10},
        'capacity_admission_performed': False, 'formal_seed_use_authorized': False,
        'bag_payload_reads': False, 'archive_operations': False, 'automatic_next_action': False,
        'observed_temporary_peak_claimed': False,
        'observer_original_post_wait_terminal_required': True}


def canonical_order(candidate, plan, *, extension=False):
    classes = ['person', 'car']
    groups = ['stage1_velocity', 'stage1_position', 'stage2_crossing',
              'stage3_midpoint', 'stage3_active', 'stage3_multi_active']
    conditions = ['depth_noise', 'depth_holes', 'dropout', 'latency', 'combined',
                  'speed_changes_velocity', 'speed_changes_position', 'far_distance']
    require(candidate.get('core_classes', classes) == classes
            and candidate.get('core_groups', groups) == groups,
            'Prospectively canonical candidate order is required; do not rewrite an existing plan')
    selected = 'selected_extension_conditions' if extension else 'selected_groups'
    require(plan.get('selected_classes') == classes and plan.get('selected_seeds') == [4]
            and type(plan['selected_seeds'][0]) is int
            and plan.get(selected) == (conditions if extension else groups),
            'Actual canonical complete seed004 plan is required')


def readonly_context(args):
    require(args.reviewed_helpers_sha256 == canonical(helper_manifest()),
            'Explicit independently reviewed storage helper bytes required')
    require(os.name == 'posix' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and os.environ.get('DEVELOPMENT_STORAGE_ACTION') == 'measure',
            'Use the explicit isolated parameterized metadata wrapper')
    extension = dependencies()
    admission, candidate, review = extension.load_admission(args.admission, args.admission_sha256)
    extension.generic.require_linux()
    modules = extension.stable.dependencies()
    checks = modules['humble33_diagnostic_checks01']
    built = extension.stable.checked_build(candidate, review, checks)
    runtime = extension.core.require_runtime(candidate, review, checks)
    built['_resource_runtime_binding'] = runtime['runtime_contracts']['resource']
    protocol = read_small(candidate['protocol']['path'])
    require(protocol.get('car_input_scale_registration', {}).get('revision') == extension.core.resources.REVISION,
            'This reviewed collector requires the actual named512/CPU4 candidate registration')
    supplement = extension.core.require_supplement_build(candidate, review)
    runner = extension.generic.runner_at(candidate['frozen_root'])
    require(not runner.simulation_processes(), 'Metadata collection requires idle runtime')
    ctx = extension.Context(admission, candidate, review, built, runner, modules, runtime)
    source = extension.entry_binding(ctx)
    contract, plan = extension.load_contract(ctx, args.contract, args.contract_sha256)
    canonical_order(candidate, plan, extension=True)
    core_plan = extension.core.checked_plan(candidate, runner)
    canonical_order(candidate, core_plan)
    extension.same_core(plan, core_plan)
    require(source == extension.entry_binding(ctx), 'Source/build/admission changed during metadata preflight')
    return extension, ctx, contract, plan, core_plan, source, supplement


def extension_completed(extension, ctx, contract, plan, expected_contract):
    """Recheck original16 attempts and real post-wait owner; never upgrade FAIL."""
    selected, runner = extension.locations(ctx), ctx.runner
    source = extension.entry_binding(ctx)
    path = selected['run_driver'] / 'execution_terminal.json'
    terminal = read_small(path)
    require(terminal.get('schema_version') == 1 and terminal.get('scope') == extension.SCOPE
        and terminal.get('action') == 'run' and type(terminal.get('returncode')) is int
        and terminal['returncode'] == 0 and terminal.get('status') == 'ORIGINAL_EXTENSION16_TERMINALS_COMPLETE'
        and terminal.get('error') is None and terminal.get('slot_read_error') is None
        and all(type(terminal.get(key)) is int and terminal[key] == 16
                for key in ('planned_count', 'attempt_count', 'terminal_count'))
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == source
        and terminal.get('final_errors') == [] and terminal.get('cleanup') == {'residual_processes': []}
        and terminal.get('contract') == expected_contract and terminal.get('plan') == contract['plan_pending']
        and terminal.get('prerequisites') == contract['prerequisites']
        and all(terminal.get(field) is False for field in extension.core.FALSE_FIELDS)
        and 'zero_attempt_recovery' not in terminal,
        'Actual same-candidate original extension16 did not close completely and healthily')
    ids = [trial['id'] for trial in plan['trials']]
    require(len(ids) == 16 and len(set(ids)) == 16
        and [item.get('slot') for item in terminal.get('slots', [])] == ids
        and [item.get('slot') for item in terminal.get('attempts', [])] == ids,
        'All16 original extension slots/attempts must be retained in order')
    rows, bound = runner.read_slots(plan), []
    require(set(rows) == set(ids), 'Original extension terminal denominator differs')
    checks = ctx.modules['humble33_diagnostic_checks01']
    for number, (trial, item, attempt) in enumerate(zip(plan['trials'], terminal['slots'], terminal['attempts']), 1):
        record = rows[trial['id']]
        audit = extension.core.original41.audit_record(runner, plan, trial, record, ctx.review, checks, extension=True)
        require(item == {'slot': trial['id'], 'status': record['status'],
                'engineering_result': record['engineering_result'], 'audit': audit}
            and type(attempt.get('number')) is int and attempt['number'] == number
            and attempt.get('error') is None and attempt.get('audit') == audit
            and type(attempt.get('runner_result', {}).get('started_this_invocation')) is int
            and attempt['runner_result']['started_this_invocation'] == 1
            and attempt.get('record') == {'status': record['status'],
                'engineering_result': record['engineering_result'], 'record_binding': audit['record_binding']},
            'Original extension row/runtime/report/failure binding changed')
        marker = selected['run_driver'] / f'{number:02d}_{trial["id"]}.started.json'
        require(extension.stable.metadata_binding(marker, json_only=True) == attempt.get('started_marker')
            and read_small(marker) == {'slot': trial['id'], 'number': number, 'entry_binding': source,
                'contract': expected_contract, 'plan_sha256': plan['plan_sha256'],
                'started_utc': attempt['started_utc'], 'original_attempt_number': 1},
            'Original extension started marker changed')
        attempt_path = selected['run_driver'] / f'{number:02d}_{trial["id"]}.attempt_terminal.json'
        require(read_small(attempt_path) == attempt, 'Original extension per-attempt terminal changed')
        bound.append({'id': trial['id'], 'status': record['status'],
            'record_binding': audit['record_binding'], 'attempt_terminal': binding(attempt_path),
            'known_algorithm_failures': audit['known_algorithm_failures']})
    observed = extension.owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['run_driver'] / 'observer_driver', ctx.root)
    actual = {key: {'status': record.get('status'), 'record_sha256': record.get('record_sha256')}
              for key, record in rows.items()}
    require(terminal.get('observer') == observed and terminal.get('actual_slot_statuses') == actual
        and terminal.get('status_counts') == dict(Counter(row['status'] for row in actual.values())),
        'Original extension aggregate status or real post-wait observer differs')
    runner.verify_sources(plan)
    require(not runner.simulation_processes(), 'Runtime residual after original extension validation')
    return {'plan': extension.core.pending_identity(plan), 'execution_terminal': binding(path),
        'completed_count': 16, 'original_terminals': bound, 'observer': observed,
        'all_original_extension_cells_pass': all(row.get('status') == row.get('engineering_result') == 'PASS'
                                                 for row in rows.values()),
        'formal_seed_use_authorized': False}


def inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Missing or linked original trial')
    root, files = directory.resolve(strict=True), {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                'Linked/escaping trial inventory entry')
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path.stat().st_size
    require(bool(files), 'Original trial inventory is empty')
    return files


def archive_path(value, suffix):
    require(isinstance(value, str), 'Archive path must be a string')
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and '\\' not in value and ':' not in value
            and '..' not in path.parts and path.as_posix() == value and value.endswith(suffix),
            'Unsafe or noncanonical original archive path')
    return value


def build_receipt(runner, checks, plan, trial, record, *, root, prefix):
    """Reuse historical accounting schema with explicit actual root/prefix."""
    terminal = checks.require_completed_record(runner, plan, trial, record)
    root, directory = Path(root), Path(trial['directory'])
    require(plan.get('frozen_root') == str(root) and directory.parent == root / 'results'
        and directory.name == trial['name'] and directory.name.startswith(prefix + '_')
        and type(trial.get('seed')) is int and trial['seed'] == 4
        and type(trial.get('duration_s')) in (int, float) and trial['duration_s'] == 75.,
        'Only original same-source full75s candidate seed004 cells may be measured')
    reports, bindings = {}, {}
    for name in ('bag_integrity.json', 'recording_closure.json', 'summary.json',
                 'process_exit_codes.json', 'run_config.json'):
        path = directory / name
        require(sha(path) == record.get('artifact_hashes', {}).get(name), 'Original bound report changed: ' + name)
        reports[name], bindings[name] = read_small(path), binding(path)
    archive, closure, summary, config = (reports[name] for name in
        ('bag_integrity.json', 'recording_closure.json', 'summary.json', 'run_config.json'))
    require(type(config.get('duration')) in (int, float) and config['duration'] == 75.
        and type(config.get('seed')) is int and config['seed'] == 4
        and config.get('target_class') == trial.get('target_class') and config.get('no_bag') is False,
        'Original recorded configuration does not match full75s candidate exposure')
    start = summary.get('follow_start_s')
    end = (closure.get('observations') or [{}])[-1].get('last_clock_ns')
    require(type(start) in (int, float) and math.isfinite(start) and start >= 0
        and type(end) is int and end >= math.ceil((start + 75.) * 1e9)
        and summary.get('termination_reason') == 'follow_duration_reached'
        and closure.get('status') == 'PASS' and archive.get('status') == 'PASS'
        and archive.get('policy') == ARCHIVE_POLICY and type(archive.get('recorder_exit_code')) is int
        and archive['recorder_exit_code'] == 0 and archive.get('spool_retained') is False,
        'Closed full75s source-clock/native archive and successful recorder exit required')
    raw_validation, native = archive.get('raw_validation', {}), archive.get('native_reader_validation', {})
    require(raw_validation.get('status') == native.get('status') == 'PASS'
        and native.get('full_stream_read') is True and type(raw_validation.get('message_count')) is int
        and type(native.get('message_count')) is int and raw_validation['message_count'] > 0
        and raw_validation['message_count'] == native.get('message_count')
        and isinstance(raw_validation.get('topic_counts'), dict) and bool(raw_validation['topic_counts'])
        and raw_validation['topic_counts'] == native.get('topic_counts'),
        'Original archive lacks complete native stream/count correspondence')
    compressed, raw = archive.get('compressed_files'), raw_validation.get('files')
    require(isinstance(compressed, list) and bool(compressed) and isinstance(raw, list) and bool(raw)
        and len({row['path'] for row in compressed}) == len(compressed)
        and len({row['path'] for row in raw}) == len(raw), 'Empty/duplicate original archive sizes')
    raw_by_path = {}
    for row in raw:
        name = archive_path(row.get('path'), '.db3')
        require(type(row.get('bytes')) is int and row['bytes'] > 0
            and isinstance(row.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', row['sha256']),
            'Invalid original raw SQLite size/digest')
        raw_by_path[name] = row
    for row in compressed:
        name = archive_path(row.get('path'), '.db3.zstd')
        raw_row = raw_by_path.get(name.removesuffix('.zstd'))
        require(type(row.get('bytes')) is int and row['bytes'] > 0
            and type(row.get('raw_bytes')) is int and row['raw_bytes'] > 0 and row.get('zstd_test') == 'PASS'
            and isinstance(raw_row, dict) and row['raw_bytes'] == raw_row['bytes']
            and row.get('raw_sha256') == raw_row.get('sha256'),
            'Invalid original compressed/raw byte correspondence')
    require(len(raw) == len(compressed), 'Original raw/compressed file denominator differs')
    files = inventory(directory)
    require(all(files.get('rosbag/' + row['path']) == row['bytes'] for row in compressed),
            'Compressed archive stat differs')
    raw_bytes, compressed_bytes = sum(row['bytes'] for row in raw), sum(row['bytes'] for row in compressed)
    require(sum(row['raw_bytes'] for row in compressed) == raw_bytes, 'Raw/compressed totals differ')
    metadata = directory / 'rosbag/metadata.yaml'
    require(sha(metadata) == archive.get('published_metadata_sha256')
            == record.get('artifact_hashes', {}).get('rosbag/metadata.yaml'),
            'Original native-validated published metadata changed')
    bag_bytes = sum(size for name, size in files.items() if name.startswith('rosbag/'))
    total_bytes = sum(files.values())
    require(files == inventory(directory)
            and all(sha(item['path']) == item['sha256'] for item in bindings.values()),
            'Original closed artifacts changed during inventory')
    return {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE', 'trial': str(directory),
        'total_trial_bytes': total_bytes, 'bag_bytes': bag_bytes,
        'auxiliary_bytes': total_bytes - bag_bytes,
        'raw_sqlite_bytes': raw_bytes, 'compressed_sqlite_bytes': compressed_bytes, 'files': files,
        'original_status': record['status'], 'original_terminal': terminal,
        'plan_sha256': plan['plan_sha256'], 'duration_s': 75,
        'original_report_bindings': bindings, 'published_metadata': binding(metadata),
        'inventory_payload_content_reads': False,
        'temporary_archive_evidence': {'scope': 'ACTUAL_ARCHIVE_COMPONENT_BYTES_NOT_OBSERVED_PEAK',
            'raw_sqlite_bytes': raw_bytes, 'compressed_sqlite_bytes': compressed_bytes,
            'archive_processing_receipt': archive.get('archive_processing'),
            'archive_report': bindings['bag_integrity.json'],
            'process_exit_receipt': bindings['process_exit_codes.json'],
            'observed_peak_bytes': None,
            'observed_peak_reason': 'No independent temporary-disk peak sampler exists in the archive receipt',
            'existing_budget_rule': 'three_raw_two_compressed_plus_margin_v1',
            'archive_component_bound_without_growth_or_margin_bytes': 3 * raw_bytes + 2 * compressed_bytes,
            'bound_is_measurement': False}, 'capacity_admission_performed': False}


def checked_output(root, output):
    root, output = Path(root), Path(output)
    expected_parent = root / 'results/freeze_validation'
    require(output.is_absolute() and output.parent == expected_parent
        and output.parent.is_dir() and not output.parent.is_symlink()
        and re.fullmatch(r'artifact_storage_[A-Za-z0-9_]+', output.name)
        and not output.exists() and not output.is_symlink(),
        'Exclusive named output under actual candidate results/freeze_validation required')
    return output


def collect(args):
    extension, ctx, contract, extension_plan, core_plan, source, supplement = readonly_context(args)
    output = checked_output(ctx.root, args.output)
    expected_contract = {'path': str(args.contract), 'sha256': args.contract_sha256}
    extension_result = extension_completed(extension, ctx, contract, extension_plan, expected_contract)
    prerequisites = contract['prerequisites']
    require(prerequisites['core'].get('all_original_core_cells_pass') is True
            and prerequisites['safety'].get('all_four_original_pass') is True,
            'Actual same-candidate original core12/safety4 acceptance required')
    checks = ctx.modules['humble33_diagnostic_checks01']
    receipts = []
    for plan, count, prefix in ((core_plan, 12, ctx.candidate['prefix']),
                                (extension_plan, 16, ctx.admission['prefix'])):
        rows = ctx.runner.read_slots(plan)
        require(len(plan['trials']) == count and set(rows) == {trial['id'] for trial in plan['trials']},
                'All original12+16 cells required; failed/unknown cells cannot be omitted')
        for trial in plan['trials']:
            receipts.append(build_receipt(ctx.runner, checks, plan, trial, rows[trial['id']],
                                          root=ctx.root, prefix=prefix))
    require(len(receipts) == 28 and len({row['trial'] for row in receipts}) == 28,
            'Exactly28 distinct original same-source cells required')
    require(extension.entry_binding(ctx) == source
        and canonical(helper_manifest()) == args.reviewed_helpers_sha256
        and not ctx.runner.simulation_processes(),
        'Source/build/dependencies/runtime changed during metadata collection')
    checked_output(ctx.root, output)
    output.mkdir(exist_ok=False)
    for row in receipts:
        write_new(output / (Path(row['trial']).name + '.json'), row)
    counts = dict(Counter(row['original_status'] for row in receipts))
    write_new(output / 'complete28.json', {'schema_version': 1, 'kind': KIND,
        'status': 'COMPLETE28_ORIGINAL_STAT_RECEIPTS', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_binding': source, 'strict512_build_evidence': supplement,
        'helpers_canonical_sha256': args.reviewed_helpers_sha256,
        'extension_admission': ctx.admission['_admission_binding'], 'extension_contract': expected_contract,
        'core_plan': binding(extension.core.locations(ctx.candidate)['plan']),
        'extension_plan': binding(extension.locations(ctx)['plan']),
        'core_completed_prerequisite': prerequisites['core'],
        'safety_completed_prerequisite': prerequisites['safety'],
        'extension_completed_prerequisite': extension_result,
        'original_status_counts': counts,
        'all28_original_cells_pass': counts == {'PASS': 28},
        'eligible_for_budget_input': counts == {'PASS': 28}
            and extension_result['all_original_extension_cells_pass'] is True,
        'receipts': [binding(output / (Path(row['trial']).name + '.json')) for row in receipts],
        'formal_mapping': {'core': 120, 'extension': 160, 'repeats_per_cell': 10},
        'physical_storage_policy': 'Existing budget/guard aggregate actual results and registry-backed WSL VHD by physical Windows volume',
        'temporary_peak_observed': False,
        'budget_tool': str(Path(ctx.root) / 'tools/reliability_v4_storage_budget.py'),
        'capacity_admission_performed': False, 'formal_seed_use_authorized': False,
        'claim_boundary': 'Actual full75s original stat evidence only. Original FAIL retained; incomplete/failed28 cannot establish readiness. No bag read, extraction, archive operation, capacity verdict or observed-peak claim.'})
    return output


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'measure'), nargs='?', default='describe')
    result.add_argument('--admission', type=Path)
    result.add_argument('--admission-sha256')
    result.add_argument('--contract', type=Path)
    result.add_argument('--contract-sha256')
    result.add_argument('--reviewed-helpers-sha256')
    result.add_argument('--output', type=Path)
    return result


def shell_root(argv):
    args = parser().parse_args(argv)
    require(args.action == 'measure' and args.contract is not None
        and isinstance(args.contract_sha256, str) and re.fullmatch('[a-f0-9]{64}', args.contract_sha256)
        and args.output is not None and args.reviewed_helpers_sha256 == canonical(helper_manifest()),
        'Explicit reviewed metadata action and original extension contract required')
    _, candidate, _ = dependencies().load_admission(args.admission, args.admission_sha256)
    return candidate['frozen_root']


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'describe':
            manifest = helper_manifest()
            print(json.dumps({'manifest': manifest, 'sha256': canonical(manifest),
                              'actual_measurement_executed': False}, indent=2))
            return 0
        extension = dependencies()
        with extension.generic.exclusive_window(), extension.stable.stop_signals():
            output = collect(args)
        print(json.dumps({'kind': KIND, 'output': str(output), 'trial_count': 28,
                          'capacity_admission_performed': False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, RuntimeError) as error:
        print(json.dumps({'kind': KIND, 'status': 'REFUSED_NO_CAPACITY_ADMISSION',
            'reason': type(error).__name__ + ':' + str(error), 'formal_seed_use_authorized': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
