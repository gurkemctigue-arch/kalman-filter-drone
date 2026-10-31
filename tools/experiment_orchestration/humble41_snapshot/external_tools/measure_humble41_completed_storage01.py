"""Stat actual Humble41 core12 + extension16; no extraction or admission.

Import and describe are inert. Measure requires idle isolated Humble, reviewed
actual source/build/matrix/safety evidence and all original full75s terminals.
The existing generic budget/guard remain authoritative for physical capacity.
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
import sys

ROOT = Path('/root/uav_tracking_fullplan_v4_humble41')
EXTERNAL = Path(__file__).resolve().parent
OUTPUT_RELATIVE = 'results/freeze_validation/artifact_storage41_01'
KIND = 'HUMBLE41_COMPLETE28_STAT_ONLY_NOT_CAPACITY_ADMISSION'
ARCHIVE_POLICY = 'ext4_sqlite_close_standard_zstd_verified_native_read'
OWN = ('measure_humble41_completed_storage01.py', 'run_humble41_storage_measure01.sh',
       'test_humble41_completed_storage01.py')
DEPENDENCIES = ('extension_runner41.py', 'extension_runner41.sh', 'test_extension_runner41.py',
    'matrix_runner41.py', 'matrix_runner41.sh', 'test_matrix_runner41.py',
    'safety_runner41.py', 'safety_runner41.sh', 'test_safety_runner41.py',
    'humble41_safety_execution01.md', 'evaluate_humble41_safety_tail01.py',
    'source_runtime41.py', 'test_source_runtime41.py',
    'local_runtime_observer41.py', 'test_local_runtime_observer41.py',
    'root_archive_observer41_pressure01.py', 'root_archive_observer41_pressure01.sh')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    path = Path(path)
    require(path.suffix in {'.py', '.sh', '.json', '.md'} and path.is_file()
        and not path.is_symlink() and path.stat().st_size <= 16*1024*1024,
        'Bounded named code/JSON required; no payload hashing')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def read_small(path):
    sha(path)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def binding(path):
    return {'path': str(path), 'sha256': sha(path)}


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def helper_manifest():
    return {'schema_version': 1, 'scope': KIND, 'frozen_root': ROOT.as_posix(),
        'files': {name: sha(EXTERNAL/name) for name in OWN},
        'dependency_files': {name: sha(EXTERNAL/name) for name in DEPENDENCIES},
        'source_review_binding': 'EXPLICIT_ACTUAL_PATH_AND_SHA_PER_MEASURE',
        'output_relative': OUTPUT_RELATIVE,
        'development_cells': {'core': 12, 'extension': 16},
        'formal_mapping': {'core': 120, 'extension': 160, 'repeats_per_cell': 10},
        'expected_class_policy': {'car': {'enabled': True, 'explicit': True},
                                  'person': {'enabled': False, 'explicit': False}},
        'matrix_locations': 'extension_runner41.locations; delegates immutable actual core driver01 to matrix_runner41',
        'capacity_admission_performed': False, 'formal_seed_use_authorized': False,
        'bag_payload_reads': False, 'automatic_next_action': False,
        'observer_original_post_wait_terminal_required': True}


def readonly_context(args):
    manifest = helper_manifest()
    require(args.reviewed_helpers_sha256 == canonical(manifest),
            'Explicit reviewed storage helper SHA differs')
    require(getattr(args, 'review', None) is not None
            and isinstance(getattr(args, 'review_sha256', None), str)
            and len(args.review_sha256) == 64
            and all(c in '0123456789abcdef' for c in args.review_sha256),
            'Explicit actual final41 source review path and SHA required before runtime import')
    require(os.name == 'posix' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
        and os.environ.get('HUMBLE41_STORAGE_ACTION') == 'measure',
        'Use the explicit isolated41 metadata wrapper')
    matrix = importlib.import_module('extension_runner41')
    generic, stable = matrix.generic, matrix.stable
    require(Path(matrix.__file__).resolve() == (EXTERNAL/'extension_runner41.py').resolve()
        and matrix.ROOT == str(ROOT)
        and generic.valid_sha(args.matrix_tools_sha256)
        and canonical(matrix.tool_manifest()) == args.matrix_tools_sha256,
        'Actual independently reviewed extension41 tools required')
    # Checks exact Python bytes before import; no cached or unbound safety API.
    safety = matrix.load_safety_api(args.safety_tools_sha256, args.safety_python_sha256)
    require(args.review is not None and generic.valid_sha(args.review_sha256),
            'Explicit actual final41 source review path and SHA required')
    review = generic.load_review(args.review, args.review_sha256, 'validate')
    require(review['frozen_root'] == str(ROOT), 'Wrong actual41 frozen root')
    modules = stable.dependencies()
    checks = modules['humble33_diagnostic_checks01']
    evidence = matrix.source.build_evidence(review)
    built = stable.checked_build({'build_evidence': evidence}, review, checks)
    checks.require_environment_contract()
    generic.runtime_contracts(review, str(ROOT))
    runner = generic.runner_at(str(ROOT))
    require(not runner.simulation_processes(), 'Metadata collection requires idle runtime')
    source = matrix.entry_binding(review, built)
    require(canonical(helper_manifest()) == args.reviewed_helpers_sha256,
            'Reviewed storage dependencies changed during context verification')
    return matrix, safety, runner, modules, checks, review, built, source


def extension_completed(matrix, runner, modules, review, built, args):
    """Read actual16 producer ledgers without turning algorithm FAIL into PASS."""
    plan = matrix.checked_plan('extension', runner)
    matrix.verify_same_core(plan, runner)
    selected = matrix.locations('extension')
    path = selected['run_driver']/'execution_terminal.json'
    terminal = read_small(path)
    source = matrix.entry_binding(review, built)
    require(terminal.get('schema_version') == 1 and terminal.get('scope') == matrix.SCOPE
        and terminal.get('action') == 'run' and terminal.get('matrix_kind') == 'extension'
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('status') == 'ORIGINAL_MATRIX_TERMINALS_COMPLETE'
        and terminal.get('error') is None and terminal.get('slot_read_error') is None
        and terminal.get('planned_count') == terminal.get('attempt_count') == terminal.get('terminal_count') == 16
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == source
        and terminal.get('final_errors') == [] and terminal.get('cleanup', {}).get('residual_processes') == []
        and all(terminal.get(name) is False for name in ('formal_seed_use_authorized', 'readiness_claimed',
            'automatic_retry', 'automatic_next_action')), 'Actual41 extension16 did not close completely and healthily')
    contract = terminal.get('contract', {})
    actual_contract, _ = matrix.load_contract('extension', contract.get('path'), contract.get('sha256'),
        args, review, built, runner, modules)
    require(terminal.get('plan') == actual_contract['plan_pending']
        and terminal.get('prerequisites') == actual_contract['prerequisites'],
        'Original extension plan/core/safety prerequisites changed')
    ids = [trial['id'] for trial in plan['trials']]
    require(len(ids) == 16 and len(set(ids)) == 16
        and [row.get('slot') for row in terminal.get('slots', [])] == ids
        and [row.get('slot') for row in terminal.get('attempts', [])] == ids,
        'All16 original extension slots and attempts must be retained in order')
    rows = runner.read_slots(plan)
    require(set(rows) == set(ids), 'Extension original terminal denominator differs')
    bound = []
    checks = modules['humble33_diagnostic_checks01']
    for number, (trial, item, attempt) in enumerate(zip(plan['trials'], terminal['slots'], terminal['attempts']), 1):
        record = rows[trial['id']]
        audit = matrix.audit_record(runner, plan, trial, record, review, checks, extension=True)
        require(item == {'slot': trial['id'], 'status': record['status'],
                'engineering_result': record['engineering_result'], 'audit': audit}
            and attempt.get('slot') == trial['id'] and attempt.get('number') == number
            and attempt.get('error') is None and attempt.get('audit') == audit
            and attempt.get('runner_result', {}).get('started_this_invocation') == 1
            and attempt.get('record') == {'status': record['status'],
                'engineering_result': record['engineering_result'], 'record_binding': audit['record_binding']},
            'Original extension per-slot runtime/report/failure binding changed')
        marker = selected['run_driver']/f'{number:02d}_{trial["id"]}.started.json'
        require(matrix.stable.metadata_binding(marker, json_only=True) == attempt.get('started_marker')
            and read_small(marker) == {'slot': trial['id'], 'number': number, 'entry_binding': source,
                'contract': contract, 'plan_sha256': plan['plan_sha256'], 'started_utc': attempt['started_utc'],
                'original_attempt_number': 1}, 'Original extension started marker changed')
        attempt_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.attempt_terminal.json'
        require(read_small(attempt_path) == attempt, 'Original extension attempt terminal changed')
        bound.append({'id': trial['id'], 'status': record['status'],
            'record_binding': audit['record_binding'], 'attempt_terminal': binding(attempt_path),
            'known_algorithm_failures': audit['known_algorithm_failures']})
    observed = matrix.owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['run_driver']/'observer_driver', str(ROOT))
    actual = {key: {'status': row.get('status'), 'record_sha256': row.get('record_sha256')} for key, row in rows.items()}
    require(terminal.get('observer') == observed and terminal.get('actual_slot_statuses') == actual
        and terminal.get('status_counts') == dict(Counter(row['status'] for row in actual.values())),
        'Original extension aggregate status/observer differs')
    require(not runner.simulation_processes(), 'Runtime residual after extension validation')
    return {'plan': matrix.pending_identity(plan), 'execution_terminal': binding(path),
        'completed_count': 16, 'original_terminals': bound, 'observer': observed,
        'engineering_pass_claimed': False, 'formal_seed_use_authorized': False}


# inventory, same_source and build_receipt below retain the reviewed32
# accounting schema and archive rules, adapted only to actual41 names.

def inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(),'Missing or linked original trial')
    root = directory.resolve(strict=True); files = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                'Linked/escaping trial inventory entry')
        if path.is_file(): files[path.relative_to(directory).as_posix()] = path.stat().st_size
    require(bool(files),'Original trial inventory is empty')
    return files


def same_source(core, extension):
    for key in ('frozen_root','results_root','source_hashes','model_hashes','protocol'):
        require(core.get(key) and core.get(key) == extension.get(key), 'Core/extension identity differs:'+key)


def build_receipt(runner, checks, plan, trial, record):
    terminal = checks.require_completed_record(runner,plan,trial,record)
    directory = Path(trial['directory'])
    require(directory.parent == ROOT/'results' and directory.name == trial['name']
        and directory.name.startswith('reliability_v4_humble41_') and type(trial.get('seed')) is int
        and trial['seed']==4 and trial.get('duration_s')==75,
        'Only original same-source41 full75s development cells may be measured')
    reports, bindings = {},{}
    for name in ('bag_integrity.json','recording_closure.json','summary.json','process_exit_codes.json','run_config.json'):
        path = directory/name
        require(sha(path)==record.get('artifact_hashes',{}).get(name),'Original bound report changed:'+name)
        reports[name],bindings[name] = read_small(path),binding(path)
    archive,closure,summary = (reports[n] for n in ('bag_integrity.json','recording_closure.json','summary.json'))
    start = summary.get('follow_start_s'); end = (closure.get('observations') or [{}])[-1].get('last_clock_ns')
    require(type(start) in (int,float) and math.isfinite(start) and start>=0 and type(end) is int
        and end>=math.ceil((start+75.)*1e9) and summary.get('termination_reason')=='follow_duration_reached'
        and closure.get('status')=='PASS' and archive.get('status')=='PASS' and archive.get('policy')==ARCHIVE_POLICY
        and type(archive.get('recorder_exit_code')) is int and archive['recorder_exit_code']==0
        and archive.get('spool_retained') is False and archive.get('raw_validation',{}).get('status')=='PASS'
        and archive.get('native_reader_validation',{}).get('status')=='PASS'
        and archive['native_reader_validation'].get('full_stream_read') is True,
        'Closed full75s source-clock/native archive and successful recorder exit required')
    compressed,raw = archive.get('compressed_files'),archive['raw_validation'].get('files')
    require(isinstance(compressed,list) and bool(compressed) and isinstance(raw,list) and bool(raw)
        and len({row['path'] for row in compressed})==len(compressed)
        and len({row['path'] for row in raw})==len(raw),'Empty/duplicate original archive sizes')
    for row in compressed:
        rel=PurePosixPath(row['path'])
        require(not rel.is_absolute() and '\\' not in row['path'] and ':' not in row['path'] and '..' not in rel.parts
            and type(row.get('bytes')) is int and row['bytes']>0
            and type(row.get('raw_bytes')) is int and row['raw_bytes']>0 and row.get('zstd_test')=='PASS',
            'Invalid original compressed archive size/path evidence')
    require(all(type(row.get('bytes')) is int and row['bytes']>0 for row in raw),'Invalid raw SQLite sizes')
    files = inventory(directory)
    require(all(files.get('rosbag/'+row['path'])==row['bytes'] for row in compressed),'Compressed archive stat differs')
    raw_bytes=sum(row['bytes'] for row in raw); compressed_bytes=sum(row['bytes'] for row in compressed)
    require(sum(row['raw_bytes'] for row in compressed)==raw_bytes,'Raw/compressed correspondence differs')
    require(files==inventory(directory) and all(sha(item['path'])==item['sha256'] for item in bindings.values()),
            'Original closed artifacts changed during inventory')
    return {'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE','trial':str(directory),
        'total_trial_bytes':sum(files.values()),'bag_bytes':sum(n for name,n in files.items() if name.startswith('rosbag/')),
        'raw_sqlite_bytes':raw_bytes,'compressed_sqlite_bytes':compressed_bytes,'files':files,
        'original_status':record['status'],'original_terminal':terminal,'plan_sha256':plan['plan_sha256'],'duration_s':75,
        'original_report_bindings':bindings,'inventory_payload_content_reads':False,
        'temporary_archive_evidence':{'scope':'ACTUAL_ARCHIVE_COMPONENT_BYTES_NOT_OBSERVED_PEAK',
            'raw_sqlite_bytes':raw_bytes,'compressed_sqlite_bytes':compressed_bytes,
            'archive_processing_receipt':archive.get('archive_processing'),
            'archive_report':bindings['bag_integrity.json'],'process_exit_receipt':bindings['process_exit_codes.json'],
            'observed_peak_bytes':None,'observed_peak_reason':'No independent temporary-disk peak sampler exists in the archive receipt',
            'existing_budget_rule':'three_raw_two_compressed_plus_margin_v1',
            'archive_component_bound_without_growth_or_margin_bytes':3*raw_bytes+2*compressed_bytes,
            'bound_is_measurement':False},'capacity_admission_performed':False}


def collect(args):
    matrix, safety, runner, modules, checks, review, built, source = readonly_context(args)
    output = ROOT/OUTPUT_RELATIVE
    require(not output.exists() and not output.is_symlink(),
            'Exclusive41 storage output exists; no retry/overwrite')
    core = matrix.require_completed_core(review, built, runner, all_pass=True)
    safety_evidence = safety.require_completed_safety(review, built, runner)
    extension = extension_completed(matrix, runner, modules, review, built, args)
    core_plan, ext_plan = (matrix.checked_plan(kind, runner) for kind in ('core', 'extension'))
    same_source(core_plan, ext_plan)
    receipts = []
    for plan, count in ((core_plan, 12), (ext_plan, 16)):
        rows = runner.read_slots(plan)
        require(len(plan['trials']) == count and set(rows) == {t['id'] for t in plan['trials']},
                'All original12+16 cells required; failed/unknown cells cannot be dropped')
        for trial in plan['trials']:
            receipts.append(build_receipt(runner, checks, plan, trial, rows[trial['id']]))
    require(len(receipts) == 28 and len({r['trial'] for r in receipts}) == 28,
            'Exactly28 distinct original cells required')
    require(matrix.entry_binding(review, built) == source
        and canonical(matrix.tool_manifest()) == args.matrix_tools_sha256
        and canonical(safety.tool_manifest()) == args.safety_tools_sha256
        and canonical(helper_manifest()) == args.reviewed_helpers_sha256,
        'Actual41 source/build/dependencies changed during stat collection')
    require(not runner.simulation_processes(), 'Runtime appeared during metadata collection')
    require(not output.exists() and not output.is_symlink(), 'Exclusive41 output already exists')
    output.mkdir(exist_ok=False)
    for row in receipts:
        write_new(output/(Path(row['trial']).name+'.json'), row)
    write_new(output/'complete28.json', {'schema_version': 1, 'kind': KIND,
        'status': 'COMPLETE28_ORIGINAL_STAT_RECEIPTS', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_binding': source, 'base_review_sha256': args.review_sha256,
        'helpers_canonical_sha256': args.reviewed_helpers_sha256,
        'matrix_tools_canonical_sha256': args.matrix_tools_sha256,
        'safety_tools_canonical_sha256': args.safety_tools_sha256,
        'core_completed_prerequisite': core, 'safety_completed_prerequisite': safety_evidence,
        'extension_completed_prerequisite': extension,
        'original_status_counts': dict(Counter(row['original_status'] for row in receipts)),
        'receipts': [binding(output/(Path(row['trial']).name+'.json')) for row in receipts],
        'formal_mapping': {'core': 120, 'extension': 160, 'repeats_per_cell': 10},
        'physical_storage_policy': 'Aggregate actual results and registry-backed WSL VHD by physical volume using the existing inventory/budget/guard tools',
        'temporary_peak_observed': False, 'budget_tool': str(ROOT/'tools/reliability_v4_storage_budget.py'),
        'capacity_admission_performed': False, 'formal_seed_use_authorized': False,
        'claim_boundary': 'Full75s original size evidence only. No old-source/clean substitution, failed-cell omission, extraction, capacity verdict or observed-peak claim.'})
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'measure'), nargs='?', default='describe')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    for name in ('reviewed-helpers-sha256', 'matrix-tools-sha256', 'safety-tools-sha256', 'safety-python-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    if args.action == 'describe':
        manifest = helper_manifest()
        print(json.dumps({'manifest': manifest, 'sha256': canonical(manifest),
                          'actual_measurement_executed': False}, indent=2))
        return 0
    try:
        output = collect(args)
        print(json.dumps({'kind': KIND, 'output': str(output), 'trial_count': 28,
                          'capacity_admission_performed': False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, RuntimeError) as error:
        print(json.dumps({'kind': KIND, 'status': 'REFUSED_NO_CAPACITY_ADMISSION',
            'reason': str(error), 'formal_seed_use_authorized': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())


