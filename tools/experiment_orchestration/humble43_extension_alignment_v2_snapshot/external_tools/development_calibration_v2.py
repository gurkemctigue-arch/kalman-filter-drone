"""Explicit two named seed004 velocity exports and candidate R0 statistics.

Import/describe are inert. Plan writes a PENDING three-command contract only.
Run requires its independently reviewed final SHA and the actual same-source
core12/safety4 PASS and extension16 original frozen-contract/healthy owner evidence.
Frozen export/calibration algorithms, measurement membership and thresholds are reused.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import development_runner as core
import development_safety as safety
import development_extension as extension
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
import local_runtime_observer41 as owner

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'PARAMETERIZED_TWO_NAMED_DEVELOPMENT_EXPORTS_AND_R0_CANDIDATE_V2_ORIGINAL_EXTENSION_CONTRACT'
ADMISSION = 'FINAL_DEVELOPMENT_CALIBRATION_V2_ADMISSION_INDEPENDENTLY_REVIEWED'
PENDING = 'PENDING_CALIBRATION_V2_COMMAND_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_DEVELOPMENT_CALIBRATION_V2_COMMANDS_INDEPENDENTLY_REVIEWED'
OWN = ('development_calibration_v2.py', 'development_calibration_v2.sh', 'test_development_calibration_v2.py')
CLASSES = ('person', 'car')
SCRIPTS = ('scripts/export_estimator_replay_v4.py', 'scripts/calibrate_estimator_replay_v4.py')
POLICY = 'planning/reliability-v4-calibration-policy-draft.md'
SIDECARS = ('online_equivalence.json', 'native_state_audit.json', 'truth_alignment.json')
INPUTS = ('run_config.json', 'bag_integrity.json', 'recording_closure.json', 'summary.json',
          'configuration/source_sha256.json', 'configuration/runtime_parameters.yaml', 'rosbag/metadata.yaml')
CAPACITY_SCOPE = 'ONE_EXPORT_TEMPORARY_HEADROOM_NOT_FORMAL280_ADMISSION'
MIN_RESERVE = 8 * 1024**3
MAX_ARRAY = 256 * 1024**2
TIMEOUT = 1800.
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new, utc = generic.read_small, generic.write_new, core.utc


@dataclass(frozen=True)
class Context:
    admission: dict
    extension_context: extension.Context

    @property
    def root(self):
        return Path(self.extension_context.root)

    @property
    def runner(self):
        return self.extension_context.runner


def file_binding(path, *, limit=generic.MAX_SMALL):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            'Missing/unsafe bounded named file: '+str(path))
    return {'path': str(path), 'sha256': sha(path)}


def read_array(path):
    path = Path(path)
    before = file_binding(path, limit=MAX_ARRAY)
    require(path.suffix == '.json', 'Named JSON array/candidate required')
    value = json.loads(path.read_text(encoding='utf-8'),
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    require(file_binding(path, limit=MAX_ARRAY) == before, 'Array changed while reading')
    return value


def tool_manifest():
    for module in (core, safety, extension, generic, stable, owner):
        require(Path(module.__file__).resolve(strict=True) ==
                (EXTERNAL/Path(module.__file__).name).resolve(strict=True), 'Dependency escaped named external tools')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {name: file_binding(EXTERNAL/name)['sha256'] for name in OWN},
        'core_tools_canonical_sha256': canonical(core.tool_manifest()),
        'extension_tools_canonical_sha256': canonical(extension.tool_manifest()),
        'safety_dependency_files': {name: file_binding(EXTERNAL/name)['sha256'] for name in safety.OWN},
        'dependency_identity_policy': 'All actual final canonicals supplied by independent admission, no intermediate pin',
        'classes': list(CLASSES), 'seed': 4, 'group': 'stage1_velocity', 'commands': 3,
        'frozen_algorithms': list(SCRIPTS), 'requires_actual_all12_all4_PASS_and_healthy_owners': True,
        'extension16_contract': 'UNCHANGED_ORIGINAL_FROZEN_VALIDATOR_WITH_EXACT_DISCLOSED_FAILURES',
        'extension16_all_engineering_PASS_required': False,
        'same_measurement_and_original_thresholds_unchanged': True,
        'R0_membership': 'All unique valid pre-fusion R_geometry over FOLLOW through final Clock, including KF rejects',
        'truth_used_to_select_R0_samples': False, 'additional_inference_or_flight': False,
        'capacity_scope': CAPACITY_SCOPE, 'minimum_reserve_bytes': MIN_RESERVE,
        'command_timeout_wall_s': TIMEOUT, 'exports_use_formal_registration_flags': False,
        'candidate_status': 'CANDIDATE_NOT_REGISTERED', **{name: False for name in core.FALSE_FIELDS}}


def locations(ctx):
    prefix = ctx.admission['prefix']
    return {'output': ctx.root/'results'/prefix,
        'plan_driver': ctx.root/'results/freeze_validation'/(prefix+'_metadata_plan_driver_v2_01'),
        'pending_contract': EXTERNAL/('development_calibration_v2_contract_'+prefix+'_pending01.json')}


def validate_storage(value):
    require(isinstance(value, dict) and set(value) == {'scope', 'temporary_directory',
        'physical_backing_root', 'output_volume_root', 'minimum_reserve_bytes', 'output_budget_bytes'},
        'Explicit temporary, physical backing and output capacity policy required')
    require(value['scope'] == CAPACITY_SCOPE and type(value['minimum_reserve_bytes']) is int
        and value['minimum_reserve_bytes'] == MIN_RESERVE and type(value['output_budget_bytes']) is int
        and value['output_budget_bytes'] > 0, 'Original8GiB reserve and explicit output budget required')
    for name in ('temporary_directory', 'physical_backing_root', 'output_volume_root'):
        generic.absolute(value[name])
    return value


def load_admission(path, expected_sha):
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit calibration admission path/SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
        and re.fullmatch(r'development_calibration_v2_admission_[A-Za-z0-9_]+\.json', path.name),
        'Named external calibration admission required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('scope') == SCOPE and value.get('status') == ADMISSION
        and value.get('authorized_actions') == ['plan', 'run']
        and all(value.get(name) is False for name in core.FALSE_FIELDS) and 'zero_attempt_recovery' not in value,
        'Independent final development-only calibration admission required')
    require(value.get('tools_canonical_sha256') == canonical(tool_manifest()), 'Reviewed calibration tool bytes changed')
    for name in ('extension_admission', 'extension_contract', 'candidate_manifest', 'core_contract', 'safety_registry'):
        binding = value.get(name)
        require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
            and generic.valid_sha(binding.get('sha256')), 'Explicit actual '+name+' binding required')
        core.checked_metadata(binding, json_only=True)
    ext, candidate, review = extension.load_admission(**{
        'path': value['extension_admission']['path'], 'expected_sha': value['extension_admission']['sha256']})
    for name in ('candidate_manifest', 'core_contract', 'safety_registry'):
        require(value[name] == ext[name], 'Calibration and actual extension context differ: '+name)
    dependencies = {'core': canonical(core.tool_manifest()), 'safety': canonical(safety.tool_manifest()),
                    'extension': canonical(extension.tool_manifest())}
    require(value.get('dependency_tools') == dependencies
        and ext['dependency_tools'] == {key: dependencies[key] for key in ('core', 'safety')},
        'Explicit actual final core/safety/extension tool identities required')
    prefix = value.get('prefix')
    require(isinstance(prefix, str) and re.fullmatch(r'reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,105}', prefix)
        and prefix not in (candidate['prefix'], ext['prefix']), 'Fresh explicit calibration output prefix required')
    require(value.get('selection') == {'classes': list(CLASSES), 'seed': 4, 'group': 'stage1_velocity',
        'slot_ids': [cls+'_stage1_velocity_seed004' for cls in CLASSES]}, 'Only the two named seed004 velocity slots are supported')
    validate_storage(value.get('storage'))
    value['_admission_binding'] = {'path': str(path), 'sha256': expected_sha}
    return value, ext, candidate, review


def entry_binding(ctx):
    core.checked_metadata(ctx.admission['_admission_binding'], json_only=True)
    require(ctx.admission['tools_canonical_sha256'] == canonical(tool_manifest()), 'Calibration tools changed')
    for name in ('extension_admission', 'extension_contract', 'candidate_manifest', 'core_contract', 'safety_registry'):
        core.checked_metadata(ctx.admission[name], json_only=True)
    return {'metadata_admission': ctx.admission['_admission_binding'],
        'tools_canonical_sha256': ctx.admission['tools_canonical_sha256'],
        'dependency_tools': ctx.admission['dependency_tools'],
        'extension_source_build': extension.entry_binding(ctx.extension_context),
        'storage_policy': validate_storage(ctx.admission['storage'])}


def require_completed_extension(ctx):
    """Read original extension16 files, reports and owner, never a manual summary."""
    ext = ctx.extension_context
    binding = ctx.admission['extension_contract']
    contract, plan = extension.load_contract(ext, binding['path'], binding['sha256'])
    prerequisites, reference = extension.require_prerequisites(ext)
    require(contract['prerequisites'] == prerequisites, 'Actual original core12/safety4 prerequisite changed')
    selected = extension.locations(ext)
    path = selected['run_driver']/'execution_terminal.json'
    terminal = read_small(path)
    before = extension.entry_binding(ext)
    require(type(terminal.get('schema_version')) is int and terminal['schema_version'] == 1
        and terminal.get('scope') == extension.SCOPE and terminal.get('action') == 'run'
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('status') == 'ORIGINAL_EXTENSION16_TERMINALS_COMPLETE'
        and terminal.get('error') is None and terminal.get('slot_read_error') is None
        and all(type(terminal.get(name)) is int and terminal[name] == 16 for name in ('planned_count', 'attempt_count', 'terminal_count'))
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == before
        and terminal.get('final_errors') == [] and terminal.get('cleanup') == {'residual_processes': []}
        and terminal.get('contract') == binding and terminal.get('plan') == contract['plan_pending']
        and terminal.get('prerequisites') == prerequisites
        and all(terminal.get(name) is False for name in core.FALSE_FIELDS) and 'zero_attempt_recovery' not in terminal,
        'Actual same-candidate extension16 did not close completely and healthily')
    ids = [trial['id'] for trial in plan['trials']]
    require(len(ids) == len(set(ids)) == 16
        and [row.get('slot') for row in terminal.get('slots', [])] == ids
        and [row.get('slot') for row in terminal.get('attempts', [])] == ids,
        'Actual original extension16 attempt/slot denominator or order differs')
    rows, records = ctx.runner.read_slots(plan), []
    require(set(rows) == set(ids), 'Actual extension row denominator differs')
    checks = ext.modules['humble33_diagnostic_checks01']
    for number, (trial, item, attempt) in enumerate(zip(plan['trials'], terminal['slots'], terminal['attempts']), 1):
        row = rows[trial['id']]
        audit = core.original41.audit_record(ctx.runner, plan, trial, row, ext.review, checks, extension=True)
        require(item == {'slot': trial['id'], 'status': row['status'],
                'engineering_result': row['engineering_result'], 'audit': audit}
            and attempt.get('audit') == audit and attempt.get('error') is None
            and type(attempt.get('number')) is int and attempt['number'] == number
            and type(attempt.get('runner_result', {}).get('started_this_invocation')) is int
            and attempt['runner_result']['started_this_invocation'] == 1
            and attempt.get('record') == {'status': row['status'],
                'engineering_result': row['engineering_result'], 'record_binding': audit['record_binding']},
            'Original extension row/attempt/audit changed')
        marker = selected['run_driver']/f'{number:02d}_{trial["id"]}.started.json'
        require(stable.metadata_binding(marker, json_only=True) == attempt.get('started_marker')
            and read_small(marker) == {'slot': trial['id'], 'number': number, 'entry_binding': before,
                'contract': binding, 'plan_sha256': plan['plan_sha256'], 'started_utc': attempt['started_utc'], 'original_attempt_number': 1},
            'Original extension started marker changed')
        attempt_path = selected['run_driver']/f'{number:02d}_{trial["id"]}.attempt_terminal.json'
        require(read_small(attempt_path) == attempt, 'Original extension per-attempt terminal changed')
        records.append({'slot': trial['id'], 'status': row['status'],
            'engineering_result': row['engineering_result'], 'record_binding': audit['record_binding'],
            'known_algorithm_failures': audit['known_algorithm_failures'],
            'attempt_terminal': stable.metadata_binding(attempt_path, json_only=True)})
    observed = owner.validate_observer_root(terminal.get('observer_owner_terminal'), selected['run_driver']/'observer_driver', ext.root)
    actual_rows = {key: {'status': row.get('status'), 'record_sha256': row.get('record_sha256')} for key, row in rows.items()}
    require(terminal.get('actual_slot_statuses') == actual_rows
        and terminal.get('status_counts') == dict(Counter(row['status'] for row in actual_rows.values()))
        and terminal.get('observer') == observed and not ctx.runner.simulation_processes(),
        'Original extension aggregate/healthy owner or runtime residual changed')
    ctx.runner.verify_sources(plan)
    return {'core': prerequisites['core'], 'safety': prerequisites['safety'],
        'extension': {'result': 'PASS',
            'result_scope': 'ORIGINAL_FROZEN_EXTENSION_CONTRACT_NOT_ALL_ENGINEERING_PASS',
            'completed_count': 16,
            'all_original_cells_pass': all(item['status'] == item['engineering_result'] == 'PASS' for item in records),
            'status_counts': dict(Counter(item['status'] for item in records)),
            'engineering_result_counts': dict(Counter(item['engineering_result'] for item in records)),
            'known_algorithm_failures_by_slot': {item['slot']: item['known_algorithm_failures'] for item in records},
            'plan': stable.metadata_binding(selected['plan'], json_only=True), 'plan_sha256': plan['plan_sha256'],
            'contract': binding, 'execution_terminal': stable.metadata_binding(path, json_only=True),
            'original_terminals': records, 'observer': observed}, 'extension_prerequisites': prerequisites}, reference


def inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Original trial directory is missing or linked')
    root, files = directory.resolve(strict=True), {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root), 'Linked or escaping recording inventory')
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path.stat().st_size
    require(bool(files), 'Empty recording inventory')
    return files


def frozen_sources(ctx, plan):
    path = ctx.root/'uav_tracking/replay_comparison.py'
    require(file_binding(path)['sha256'] == ctx.extension_context.review['files'].get('uav_tracking/replay_comparison.py'),
        'Actual frozen replay source differs')
    declarations = {}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ('SOURCE_FILES', 'EXPORT_SOURCE_FILES')):
            declarations[node.targets[0].id] = ast.literal_eval(node.value)
    require(set(declarations) == {'SOURCE_FILES', 'EXPORT_SOURCE_FILES'}
        and all(isinstance(names, tuple) and names and all(isinstance(name, str) for name in names) for names in declarations.values()),
        'Actual explicit frozen replay source manifests required')
    names = set(declarations['EXPORT_SOURCE_FILES']) | set(SCRIPTS) | {POLICY}
    hashes = {}
    for name in sorted(names):
        generic.relative(name)
        digest = file_binding(ctx.root/name)['sha256']
        require(ctx.extension_context.review['files'].get(name) == digest
            and (name == POLICY or plan['source_hashes'].get(name) == digest), 'Frozen offline/flight helper changed: '+name)
        hashes[name] = digest
    return {'source_hashes': hashes, 'SOURCE_FILES': list(declarations['SOURCE_FILES']),
            'EXPORT_SOURCE_FILES': list(declarations['EXPORT_SOURCE_FILES'])}


def selected_recordings(ctx, plan):
    require(plan.get('mode') == 'PROBE' and plan.get('selected_seeds') == [4]
        and type(plan['selected_seeds'][0]) is int and plan.get('selected_classes') == list(core.CLASSES)
        and plan.get('selected_groups') == list(core.GROUPS) and len(plan.get('trials', [])) == 12,
        'Original canonical two-class/six-group seed004 core required by frozen calibrator')
    sources, selected = frozen_sources(ctx, plan), {}
    rows = ctx.runner.read_slots(plan)
    for cls in CLASSES:
        identifier = cls+'_stage1_velocity_seed004'
        matches = [trial for trial in plan['trials'] if trial.get('id') == identifier]
        require(len(matches) == 1, 'Missing or duplicate named velocity slot: '+identifier)
        trial, row = matches[0], rows[identifier]
        directory = Path(trial['directory'])
        require(trial.get('target_class') == cls and type(trial.get('seed')) is int and trial['seed'] == 4
            and trial.get('group') == 'stage1_velocity' and trial.get('stage') == 1
            and trial.get('command_mode') == 'velocity' and trial.get('multi_target') is False
            and trial.get('duration_s') == 75. and directory == ctx.root/'results'/trial['name']
            and row.get('status') == row.get('engineering_result') == 'PASS', 'Foreign/nonvelocity or failed calibration recording')
        metadata = {name: file_binding(directory/name) for name in INPUTS}
        require(all(binding['sha256'] == row.get('artifact_hashes', {}).get(name) for name, binding in metadata.items()),
            'Original selected recording metadata differs from terminal')
        config, archive, closure, summary = (read_small(directory/name) for name in INPUTS[:4])
        expected = {'target_class': cls, 'seed': 4, 'stage': 1, 'command_mode': 'velocity',
                    'multi_target': False, 'no_bag': False, 'duration': 75.}
        require(all(config.get(name) == value and (type(value) is not bool or type(config.get(name)) is bool)
            for name, value in expected.items()), 'Original selected run_config differs')
        snapshot = read_small(directory/'configuration/source_sha256.json')
        require(snapshot and all(ctx.extension_context.review['files'].get(name) == digest for name, digest in snapshot.items()),
            'Original selected source snapshot differs from candidate')
        end, start = (closure.get('observations') or [{}])[-1].get('last_clock_ns'), summary.get('follow_start_s')
        require(type(start) in (int, float) and math.isfinite(start) and start >= 0 and type(end) is int
            and end >= math.ceil((start+75.)*1e9) and summary.get('termination_reason') == 'follow_duration_reached'
            and closure.get('status') == archive.get('status') == 'PASS'
            and archive.get('policy') == 'ext4_sqlite_close_standard_zstd_verified_native_read'
            and archive.get('raw_validation', {}).get('status') == archive.get('native_reader_validation', {}).get('status') == 'PASS'
            and archive['native_reader_validation'].get('full_stream_read') is True, 'Original full75s native archive/Clock closure required')
        raw, compressed = archive['raw_validation'].get('files'), archive.get('compressed_files')
        require(isinstance(raw, list) and raw and isinstance(compressed, list) and compressed
            and len({item.get('path') for item in raw}) == len(raw)
            and len({item.get('path') for item in compressed}) == len(compressed), 'Complete unique original archive size evidence required')
        files = inventory(directory)
        for item in raw:
            generic.relative(item['path'])
            require(type(item.get('bytes')) is int and item['bytes'] > 0, 'Invalid original raw size')
        for item in compressed:
            generic.relative(item['path'])
            require(type(item.get('bytes')) is int and item['bytes'] > 0 and type(item.get('raw_bytes')) is int
                and item['raw_bytes'] > 0 and item.get('zstd_test') == 'PASS'
                and files.get('rosbag/'+item['path']) == item['bytes'], 'Original compressed size/stat correspondence differs')
        raw_bytes, compressed_bytes = sum(item['bytes'] for item in raw), sum(item['bytes'] for item in compressed)
        require(sum(item['raw_bytes'] for item in compressed) == raw_bytes, 'Original raw/compressed correspondence differs')
        selected[cls] = {'trial': trial, 'record_binding': ext_record_binding(ctx, plan, trial, row),
            'input_metadata': metadata, 'files': files, 'raw_sqlite_bytes': raw_bytes, 'compressed_sqlite_bytes': compressed_bytes}
    return selected, sources


def ext_record_binding(ctx, plan, trial, row):
    return ctx.extension_context.modules['humble33_diagnostic_checks01'].terminal_binding(ctx.runner, plan, trial, row)


def require_inputs_unchanged(selected):
    for cls, source in selected.items():
        directory = Path(source['trial']['directory'])
        require(inventory(directory) == source['files'], 'Original selected recording sizes changed: '+cls)
        require(all(file_binding(directory/name) == binding for name, binding in source['input_metadata'].items()),
            'Original selected recording metadata changed: '+cls)


def commands(ctx, selected, plan_path):
    output = locations(ctx)['output']
    rows = [{'id': cls+'_export', 'command': [generic.PYTHON, '-B', str(ctx.root/SCRIPTS[0]),
        selected[cls]['trial']['directory'], '--output', str(output/(cls+'_export'))]} for cls in CLASSES]
    rows.append({'id': 'calibration', 'command': [generic.PYTHON, '-B', str(ctx.root/SCRIPTS[1]),
        '--plan', str(plan_path), '--person-arrays', str(output/'person_export/arrays.json'),
        '--car-arrays', str(output/'car_export/arrays.json'), '--output', str(output/'calibration_candidate.json')]})
    return [{**row, 'argv_sha256': canonical(row['command']), 'timeout_wall_s': TIMEOUT} for row in rows]


def output_bytes(output):
    if not Path(output).exists():
        return 0
    return sum(inventory(output).values())


def require_capacity(ctx, source=None):
    policy = validate_storage(ctx.admission['storage'])
    temporary, backing, volume = (Path(policy[name]).resolve(strict=True) for name in
        ('temporary_directory', 'physical_backing_root', 'output_volume_root'))
    require(temporary == Path(tempfile.gettempdir()).resolve(strict=True), 'Reviewed temporary route differs from actual exporter cache')
    output = locations(ctx)['output']
    require(output.parent.resolve(strict=True).is_relative_to(volume)
        and output.parent.stat().st_dev == volume.stat().st_dev, 'Actual output volume differs from reviewed capacity route')
    used = output_bytes(output)
    require(used <= policy['output_budget_bytes'], 'Produced metadata exceeds reviewed output budget')
    remaining = policy['output_budget_bytes']-used
    raw = source['raw_sqlite_bytes'] if source is not None else 0
    compressed = source['compressed_sqlite_bytes'] if source is not None else 0
    required = 3*raw+2*compressed+MIN_RESERVE
    actual = {'temporary_logical_free_bytes': shutil.disk_usage(temporary).free,
        'physical_backing_free_bytes': shutil.disk_usage(backing).free, 'output_volume_free_bytes': shutil.disk_usage(volume).free}
    require(actual['temporary_logical_free_bytes'] >= required
        and actual['physical_backing_free_bytes'] >= required+remaining
        and actual['output_volume_free_bytes'] >= remaining+MIN_RESERVE,
        'Insufficient actual temporary/physical backing/output headroom; no export is started')
    return {'scope': CAPACITY_SCOPE, 'raw_bytes': raw, 'compressed_bytes': compressed,
        'single_export_required_bytes': required, 'remaining_output_budget_bytes': remaining,
        'output_bytes_already_written': used, 'routes': policy, **actual, 'formal280_capacity_admission': False}


def planning_facts(ctx):
    prerequisite, plan = require_completed_extension(ctx)
    selected, sources = selected_recordings(ctx, plan)
    plan_path = core.locations(ctx.extension_context.candidate)['plan']
    return {'prerequisites': prerequisite, 'core_plan': {**file_binding(plan_path.resolve(strict=True)), 'plan_sha256': plan['plan_sha256']},
        'selected_recordings': selected, 'offline_sources': sources, 'commands': commands(ctx, selected, plan_path),
        'storage_policy': ctx.admission['storage']}


def plan_calibration(ctx):
    selected = locations(ctx)
    require(not any(selected[name].exists() or selected[name].is_symlink() for name in ('output', 'plan_driver', 'pending_contract'))
        and not ctx.runner.simulation_processes(), 'Fresh metadata plan/output/contract and idle runtime required')
    before = entry_binding(ctx)
    facts = planning_facts(ctx)
    capacity = {cls: require_capacity(ctx, facts['selected_recordings'][cls]) for cls in CLASSES}
    require(entry_binding(ctx) == before and planning_facts(ctx) == facts, 'Original source/28 prerequisites/selection changed during planning')
    directory = selected['plan_driver']; directory.mkdir(exist_ok=False)
    terminal_path = directory/'execution_terminal.json'
    write_new(terminal_path, {'schema_version': 1, 'scope': SCOPE, 'action': 'plan', 'returncode': 0,
        'finished_utc': utc(), 'entry_binding_before': before, 'entry_binding_after': before, 'facts': facts,
        'capacity_snapshot': capacity, 'actual_commands_executed': 0, **{name: False for name in core.FALSE_FIELDS}})
    value = {'schema_version': 1, 'scope': SCOPE, 'status': PENDING, 'created_utc': utc(),
        'metadata_admission': ctx.admission['_admission_binding'], 'entry_binding': before, 'facts': facts,
        'plan_terminal': file_binding(terminal_path), **{name: False for name in core.FALSE_FIELDS}}
    write_new(selected['pending_contract'], value)
    print(json.dumps({'status': PENDING, 'pending_contract': file_binding(selected['pending_contract']),
        'commands': facts['commands'], 'actual_commands_executed': 0}), flush=True)
    return 0


def load_contract(ctx, path, expected_sha):
    require(path is not None and generic.valid_sha(expected_sha), 'Explicit separately reviewed actual calibration command contract required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
        and re.fullmatch(r'development_calibration_v2_contract_[A-Za-z0-9_-]+\.json', path.name), 'Named external command contract required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
        and value.get('scope') == SCOPE and value.get('status') == FINAL,
        'Actual independently reviewed final3-command contract required; PENDING cannot execute')
    before = entry_binding(ctx)
    facts = planning_facts(ctx)
    require(value.get('metadata_admission') == ctx.admission['_admission_binding'] and value.get('entry_binding') == before
        and value.get('facts') == facts and all(value.get(name) is False for name in core.FALSE_FIELDS)
        and 'zero_attempt_recovery' not in value, 'Actual source/28 owners/selected records/commands changed')
    terminal_path = locations(ctx)['plan_driver']/'execution_terminal.json'
    require(file_binding(terminal_path) == value.get('plan_terminal'), 'Original metadata planning terminal changed')
    terminal = read_small(terminal_path)
    require(terminal.get('scope') == SCOPE and terminal.get('action') == 'plan'
        and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == before
        and terminal.get('facts') == facts and type(terminal.get('actual_commands_executed')) is int
        and terminal['actual_commands_executed'] == 0 and all(terminal.get(name) is False for name in core.FALSE_FIELDS),
        'Original prospective metadata plan did not close with immutable actual context')
    return value


def frozen_algorithms(ctx, facts):
    """Import frozen array-only validators only after actual run admission."""
    root = ctx.root.resolve(strict=True)
    for name, module in tuple(sys.modules.items()):
        if name in ('run_reliability_v4', 'run_estimator_replay_v4') or name == 'uav_tracking' or name.startswith('uav_tracking.'):
            location = getattr(module, '__file__', None)
            if location is not None:
                require(Path(location).resolve(strict=True).is_relative_to(root), 'Cached algorithm import escaped actual frozen root: '+name)
    require(frozen_sources(ctx, read_small(facts['core_plan']['path'])) == facts['offline_sources'],
        'Frozen offline source changed before import')
    def load(name, relative):
        path = (root/relative).resolve(strict=True)
        existing = sys.modules.get(name)
        if existing is not None:
            require(Path(existing.__file__).resolve(strict=True) == path, 'Frozen module name already belongs to another source')
            return existing
        spec = importlib.util.spec_from_file_location(name, path)
        require(spec is not None and spec.loader is not None, 'Cannot load actual frozen array validator')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    original_path = list(sys.path)
    try:
        sys.path[:0] = [str(root/'scripts'), str(root)]
        replay = load('run_estimator_replay_v4', 'scripts/run_estimator_replay_v4.py')
        calibration = load('_reviewed_development_calibration_v2_'+facts['core_plan']['sha256'], SCRIPTS[1])
    finally:
        sys.path[:] = original_path
    require(Path(calibration.engineering.__file__).resolve(strict=True) == root/'scripts/run_reliability_v4.py'
        and calibration.replay is replay, 'Frozen calibrator dependency root differs')
    for name, module in tuple(sys.modules.items()):
        if name == 'uav_tracking' or name.startswith('uav_tracking.'):
            require(Path(module.__file__).resolve(strict=True).is_relative_to(root), 'Imported tracking helper escaped actual frozen source')
    return replay, calibration


def audit_configuration(facts, plan):
    sources = {name: facts['offline_sources']['source_hashes'][name]
        for name in facts['offline_sources']['EXPORT_SOURCE_FILES']}
    return {'freeze_requirements': {'evaluation_source_hashes': sources,
        'offline_replay_source_hashes': {name: sources[name] for name in facts['offline_sources']['SOURCE_FILES']},
        'flight_source_hashes': plan['source_hashes']}}


def validate_export(ctx, cls, facts, algorithms):
    replay, calibration = algorithms
    source = facts['selected_recordings'][cls]
    path = locations(ctx)['output']/(cls+'_export/arrays.json')
    array_binding, value = file_binding(path, limit=MAX_ARRAY), read_array(path)
    audit = value.get('export_audit', {})
    require(value.get('target_class') == cls and type(value.get('seed')) is int and value['seed'] == 4
        and value.get('group') == 'stage1_velocity'
        and value.get('slot_id') == 'DEVELOPMENT_ONLY_'+source['trial']['name']
        and value.get('engineering_status') == 'DEVELOPMENT_ONLY_NO_FORMAL_VERDICT'
        and audit.get('status') == 'PASS' and audit.get('scope') == 'DEVELOPMENT_ONLY'
        and audit.get('online_equivalence') == audit.get('native_state_audit') == 'PASS'
        and audit.get('native_archive_integrity_sha256') == source['input_metadata']['bag_integrity.json']['sha256'],
        'Export did not close for the exact named development recording: '+cls)
    sidecars = {name: file_binding(path.parent/name, limit=MAX_ARRAY) for name in SIDECARS}
    plan = read_small(facts['core_plan']['path'])
    row = ctx.runner.read_slots(plan)[source['trial']['id']]
    recording = calibration.bind_named_recording(source['trial'], row, value)
    evidence = replay.verify_export_evidence(path, value, audit_configuration(facts, plan),
        source_root=ctx.root, development_only=True)
    statistics = calibration.geometry_statistics(value)
    require(file_binding(path, limit=MAX_ARRAY) == array_binding
        and all(file_binding(path.parent/name, limit=MAX_ARRAY) == binding for name, binding in sidecars.items()),
        'Original exported array or sidecar changed during validation')
    return {'arrays': {**array_binding, 'path': str(path.resolve(strict=True))}, 'sidecars': sidecars, 'recording_evidence': recording,
            'verified_export_evidence': evidence, 'geometry_statistics': statistics}


def validate_candidate(ctx, facts, algorithms, exports):
    path = locations(ctx)['output']/'calibration_candidate.json'
    result_binding, value = file_binding(path, limit=MAX_ARRAY), read_array(path)
    require(set(value) == {'schema_version', 'kind', 'status', 'scope', 'created_utc', 'policy', 'development_plan',
        'provenance', 'classes', 'candidate_parameters', 'source_hashes', 'claim_boundary'}
        and type(value['schema_version']) is int and value['schema_version'] == 1
        and value['kind'] == 'RELIABILITY_V4_DEVELOPMENT_CALIBRATION'
        and value['status'] == 'CANDIDATE_NOT_REGISTERED' and value['scope'] == 'DEVELOPMENT_ONLY'
        and isinstance(value['created_utc'], str) and value['created_utc']
        and value['development_plan'] == facts['core_plan']
        and value['policy'] == {'path': POLICY, 'sha256': facts['offline_sources']['source_hashes'][POLICY]}
        and value['source_hashes'] == {SCRIPTS[1]: facts['offline_sources']['source_hashes'][SCRIPTS[1]]},
        'Frozen candidate header/source/policy/plan binding differs; registration is prohibited')
    fresh = {cls: validate_export(ctx, cls, facts, algorithms) for cls in CLASSES}
    require(fresh == exports, 'Original exports changed before candidate validation')
    plan = read_small(facts['core_plan']['path'])
    provenance = {}
    for cls in CLASSES:
        trial = facts['selected_recordings'][cls]['trial']
        provenance[cls] = {'slot_id': trial['id'], 'engineering_status': 'PASS',
            'terminal_record': file_binding(ctx.runner.record_path(plan, trial)),
            'arrays': exports[cls]['arrays'], 'recording_evidence': exports[cls]['recording_evidence'],
            'verified_export_evidence': exports[cls]['verified_export_evidence']}
    classes = {cls: exports[cls]['geometry_statistics'] for cls in CLASSES}
    parameters = {'R0_sensor_world_m2_by_class': {cls: classes[cls]['R0_sensor_world_m2'] for cls in CLASSES},
        'Q_model_and_parameters': {'model': 'piecewise_constant_acceleration', 'acceleration_std_mps2': 1.},
        'P0_matrix_and_initial_velocity_policy': {'covariance_6x6': [[float((1.,1.,1.,4.,4.,4.)[i]) if i == j else 0.
            for j in range(6)] for i in range(6)], 'velocity_policy': 'registered_constant', 'initial_velocity_mps': [0.,0.,0.]},
        'ema_alpha': .35, 'common_gate_R_and_initialization_policy': {'measurement_covariance': 'geometry_plus_pose',
            'initialization': 'common_P0', 'threshold_squared': 9.21}, 'common_support_truth_coverage_requirement': .8}
    require(value['classes'] == classes and value['provenance'] == provenance and value['candidate_parameters'] == parameters
        and value['claim_boundary'] == 'Candidate development statistics only; does not register parameters, certify full engineering acceptance or read held-out outcomes.'
        and file_binding(path, limit=MAX_ARRAY) == result_binding,
        'Original geometry membership/R0/full covariance/fixed parameters/provenance changed')
    return result_binding


def finish_action(ctx, observer, output):
    finished = extension.finish_action(ctx.extension_context, observer, output)
    finished['extension_binding_after'] = finished.pop('entry_binding_after')
    try:
        finished['entry_binding_after'] = entry_binding(ctx)
        require(finished['entry_binding_after']['extension_source_build'] == finished['extension_binding_after'],
            'Source changed between original owner and calibration closure')
    except BaseException as caught:
        finished['entry_binding_after'] = None
        finished['final_errors'].append('calibration_binding:'+type(caught).__name__+':'+str(caught))
    return finished


def run_calibration(ctx, contract_path, contract_sha):
    contract = load_contract(ctx, contract_path, contract_sha)
    facts, output = contract['facts'], locations(ctx)['output']
    require(not output.exists() and not output.is_symlink() and not ctx.runner.simulation_processes(),
        'Fresh calibration output and idle runtime required; no retry, overwrite or resume')
    before = entry_binding(ctx)
    initial_capacity = {cls: require_capacity(ctx, facts['selected_recordings'][cls]) for cls in CLASSES}
    output.mkdir(exist_ok=False)
    write_new(output/'setup.json', {'schema_version': 1, 'scope': SCOPE, 'created_utc': utc(),
        'entry_binding': before, 'contract': {'path': str(contract_path), 'sha256': contract_sha},
        'facts': facts, 'capacity_snapshot': initial_capacity, **{name: False for name in core.FALSE_FIELDS}})
    observer = owner.make_observer(output/'observer_driver', ctx.root, archive_wall_budget_s=1800.)
    attempts, exports, candidate, error = [], {}, None, None
    try:
        with ctx.runner.run_lock(output):
            require(not ctx.runner.simulation_processes(), 'Runtime appeared before metadata lock acquisition')
            with observer:
                algorithms = frozen_algorithms(ctx, facts)
                for number, command in enumerate(facts['commands'], 1):
                    require(entry_binding(ctx) == before and sha(contract_path) == contract_sha
                        and planning_facts(ctx) == facts, 'Original source/prerequisites/command context changed')
                    require_inputs_unchanged(facts['selected_recordings'])
                    for cls in exports:
                        require(validate_export(ctx, cls, facts, algorithms) == exports[cls], 'Prior export changed')
                    cls = command['id'].removesuffix('_export') if command['id'].endswith('_export') else None
                    capacity = require_capacity(ctx, facts['selected_recordings'][cls] if cls else None)
                    observer.check()
                    attempt = {'id': command['id'], 'number': number, 'started_utc': utc(), 'execution': None,
                        'validation': None, 'capacity_snapshot': capacity, 'error': None}
                    attempts.append(attempt)
                    marker = output/f'{number:02d}_{command["id"]}.started.json'
                    write_new(marker, {'id': command['id'], 'number': number, 'entry_binding': before,
                        'contract': {'path': str(contract_path), 'sha256': contract_sha}, 'command': command,
                        'started_utc': attempt['started_utc'], 'original_attempt_number': 1})
                    attempt['started_marker'] = file_binding(marker)
                    print(json.dumps({'event': 'START_ORIGINAL_CALIBRATION_COMMAND', 'id': command['id'], 'number': number, 'total': 3}), flush=True)
                    try:
                        receipt = stable.execute_owned(command['command'], output/(command['id']+'.log'), observer,
                            command['timeout_wall_s'], ctx.root)
                        attempt['execution'] = receipt
                        stable.clean_execution(receipt, command['command'])
                        observer.check()
                        if cls:
                            exports[cls] = validate_export(ctx, cls, facts, algorithms)
                            attempt['validation'] = exports[cls]
                        else:
                            candidate = validate_candidate(ctx, facts, algorithms, exports)
                            attempt['validation'] = candidate
                        require(entry_binding(ctx) == before and sha(contract_path) == contract_sha
                            and planning_facts(ctx) == facts, 'Original context changed during command')
                        require_inputs_unchanged(facts['selected_recordings'])
                        require_capacity(ctx)
                    except BaseException as caught:
                        attempt['error'] = type(caught).__name__+':'+str(caught)
                        raise
                    finally:
                        attempt['finished_utc'] = utc()
                        write_new(output/f'{number:02d}_{command["id"]}.attempt_terminal.json', attempt)
    except BaseException as caught:
        error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(ctx, observer, output)
    try:
        require(sha(contract_path) == contract_sha and planning_facts(ctx) == facts, 'Actual final command/source/prerequisites changed')
        require_inputs_unchanged(facts['selected_recordings'])
        require_capacity(ctx)
        if candidate is not None:
            require(validate_candidate(ctx, facts, algorithms, exports) == candidate, 'Candidate changed after original owner post-wait')
    except BaseException as caught:
        cleanup['final_errors'].append('final_context:'+type(caught).__name__+':'+str(caught))
    code = 0 if error is None and len(attempts) == 3 and set(exports) == set(CLASSES) and candidate is not None \
        and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    write_new(output/'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE, 'action': 'run',
        'finished_utc': utc(), 'returncode': code,
        'status': 'ORIGINAL_TWO_EXPORTS_AND_CANDIDATE_COMPLETE_NOT_REGISTERED' if code == 0 else 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED',
        'error': error, 'entry_binding_before': before, 'runtime_preflight': ctx.extension_context.runtime,
        'contract': {'path': str(contract_path), 'sha256': contract_sha}, 'facts': facts,
        'planned_count': 3, 'attempt_count': len(attempts), 'attempts': attempts,
        'unattempted_commands': facts['commands'][len(attempts):], 'exports': exports, 'candidate': candidate,
        **cleanup, **{name: False for name in core.FALSE_FIELDS},
        'claim_boundary': 'Two original named development exports and candidate statistics only. No registration, formal admission or estimator superiority claim.'})
    return code


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('describe', 'plan', 'run'))
    result.add_argument('--admission', type=Path); result.add_argument('--admission-sha256')
    result.add_argument('--contract', type=Path); result.add_argument('--contract-sha256')
    return result


def reviewed_admission(args):
    require(args.action in ('plan', 'run'), 'Explicit calibration action required')
    if args.action == 'run':
        require(args.contract is not None and generic.valid_sha(args.contract_sha256),
            'Run requires separately reviewed final actual three-command contract')
    return load_admission(args.admission, args.admission_sha256)


def shell_root(argv):
    _, _, candidate, _ = reviewed_admission(parser().parse_args(argv))
    return candidate['frozen_root']


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'describe':
            manifest = tool_manifest()
            print(json.dumps({'status': 'PENDING_INDEPENDENT_TOOL_REVIEW', 'tool_manifest': manifest,
                'tools_canonical_sha256': canonical(manifest), 'actual_action_executed': False}, indent=2))
            return 0
        admission, ext_admission, candidate, review = reviewed_admission(args)
        generic.require_linux()
        modules = stable.dependencies()
        with generic.exclusive_window(), stable.stop_signals():
            checks = modules['humble33_diagnostic_checks01']
            built = stable.checked_build(candidate, review, checks)
            runtime = core.require_runtime(candidate, review, checks)
            built['_resource_runtime_binding'] = runtime['runtime_contracts']['resource']
            runner = generic.runner_at(candidate['frozen_root'])
            ctx = Context(admission, extension.Context(ext_admission, candidate, review, built, runner, modules, runtime))
            if args.action == 'plan':
                return plan_calibration(ctx)
            return run_calibration(ctx, args.contract, args.contract_sha256)
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, StopIteration, subprocess.SubprocessError) as caught:
        print(json.dumps({'status': 'DEVELOPMENT_CALIBRATION_REFUSED_OR_FAILED',
            'reason': type(caught).__name__+':'+str(caught), **{name: False for name in core.FALSE_FIELDS}}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
