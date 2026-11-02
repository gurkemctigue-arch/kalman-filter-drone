"""Small metadata precheck before exec of the unchanged formal adapter.

No protocol/plan/admission is created. No flight is chosen or started by default.
The explicit run-one action inherits the original adapter's streams, signals,
arguments and exit status via exec, after a separate append-only audit entry.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
OWN = ('formal_supplementary_preflight.py', 'formal_supplementary_preflight.sh',
       'test_formal_supplementary_preflight.py', 'test_formal_supplementary_preflight_independent01.py',
       'test_formal54_adapter_binding.py')
KIND = 'FORMAL54_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION'
AUDIT_KIND = 'FORMAL54_SUPPLEMENTARY_PREFLIGHT_CHECK_ONLY_NOT_GUARD_ADMISSION'
MAX_SMALL = 8 * 1024**2
DETECTION_REVIEW_SHA = '0583f950a1557ece5988633d9c812f46b326f26c3bb15b4c5176303becd21a9e'
ADAPTER_KIND = 'FORMAL54_EXPLICIT_REVIEWED_ADAPTER_BINDING_NOT_ADMISSION'
ADAPTER_SCOPE = 'FORMAL48_DDS_PREFLIGHT_ORIGINAL_GUARD_NATIVE_OWNER_NO_NEW_ADMISSION'
ADAPTER_NAMES = {'shell': 'formal48_guard_adapter01.sh', 'python': 'formal48_guard_adapter01.py'}
FIELDS = {'schema_version', 'kind', 'created_utc', 'admission', 'plans', 'detection_protocol',
          'selection', 'selection_basis', 'detection_review', 'adapter', 'adapter_binding', 'preflight_tools_sha256', 'audit_log'}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def raw(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL,
            'Only bounded ordinary metadata/code files may be read: ' + str(path))
    require(path.suffix in ('.json', '.jsonl', '.py', '.sh'), 'Not an allowed small metadata/code file')
    with path.open('rb') as stream:
        data = stream.read(MAX_SMALL + 1)
    require(len(data) <= MAX_SMALL, 'Metadata grew beyond its bounded read limit')
    return data


def pin(path):
    path = Path(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(raw(path)).hexdigest()}


def checked(binding):
    require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
            and isinstance(binding['path'], str) and Path(binding['path']).is_absolute()
            and valid_sha(binding['sha256']) and pin(binding['path']) == binding,
            'Exact unchanged physical original-file pin required')
    return Path(binding['path'])


def decode(data):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    def number(token):
        value = float(token)
        require(math.isfinite(value), 'Nonfinite JSON number')
        return value
    return json.loads(data, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite JSON token')))


def read(binding):
    value = decode(raw(checked(binding)).decode('utf-8-sig'))
    require(isinstance(value, dict), 'One original JSON object required')
    return value


def stamp(value):
    require(isinstance(value, str), 'Explicit aware UTC timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'Naive time cannot prove prospective ordering')
    return result.astimezone(timezone.utc)


def tool_manifest():
    return {'schema_version': 1, 'kind': KIND, 'files': {name: pin(HERE / name)['sha256'] for name in OWN},
            'adapter_binding_kind': ADAPTER_KIND, 'adapter_scope': ADAPTER_SCOPE,
            'adapter_paths_and_bytes': 'explicit independently pinned adapter binding; no historical41 fallback',
            'detection_independent_review_sha256': DETECTION_REVIEW_SHA,
            'default_action': 'describe', 'actual_contract_or_admission_created': False,
            'whole_tree_or_bag_or_weights_read': False, 'original_guard_schema_changed': False,
            'delegation': 'exec exactly the pinned original adapter prefix plus original run-one/manifest argv'}


def source_module(binding):
    path = checked(binding)
    code = raw(path)
    module_name = '_supplementary_preflight_original_protocol_' + binding['sha256']
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(code, str(path), 'exec'), module.__dict__)
    require(pin(path) == binding and Path(module.__file__).resolve() == path, 'Original verifier changed during import')
    return module


def exact_schema(value, fields, label):
    require(isinstance(value, dict) and set(value) == set(fields), 'Exact ' + label + ' fields required')


def integer(value, expected):
    return type(value) is int and value == expected


def external_path(value, root, results, plans, state, *, suffix):
    require(isinstance(value, str) and Path(value).is_absolute(), 'Explicit external physical path required')
    path = Path(value)
    require(not path.is_symlink() and str(path.resolve()) == value and path.suffix == suffix,
            'External path must be canonical and have its exact metadata suffix')
    protected = [root, results, state, *(Path(plan['output']).resolve() for plan in plans.values()),
                 *(Path(trial['directory']).resolve() for plan in plans.values() for trial in plan['trials'])]
    require(not any(path.is_relative_to(item) for item in protected), 'Output/binding is inside immutable flight evidence')
    require(path.parent.is_dir() and not path.parent.is_symlink(), 'Explicit ordinary existing external parent required')
    return path


def adapter_identity(binding, reviewed_sha, contract_time):
    """Read actual describe bytes; never import, execute or recreate the adapter."""
    require(valid_sha(reviewed_sha), 'Explicit independently reviewed adapter canonical SHA required')
    identity = read(binding)
    exact_schema(identity, {'schema_version', 'kind', 'created_utc', 'shell', 'python',
                           'describe', 'manifest_canonical_sha256', 'reviewed_tools_sha256'}, 'explicit adapter identity')
    require(integer(identity['schema_version'], 1) and identity['kind'] == ADAPTER_KIND
            and stamp(identity['created_utc']) <= contract_time,
            'Actual adapter binding must precede the new prospective supplementary contract')
    description = read(identity['describe'])
    exact_schema(description, {'manifest', 'tools_canonical_sha256', 'actual_action_executed'}, 'actual adapter describe result')
    manifest = description['manifest']
    require(isinstance(manifest, dict) and integer(manifest.get('schema_version'), 1)
            and manifest.get('scope') == ADAPTER_SCOPE and description['actual_action_executed'] is False
            and canonical(manifest) == description['tools_canonical_sha256']
            == identity['manifest_canonical_sha256'] == identity['reviewed_tools_sha256'] == reviewed_sha,
            'Actual describe bytes/internal canonical and independent reviewed canonical must agree')
    files = manifest.get('files')
    require(isinstance(files, dict)
            and set(files) == {*ADAPTER_NAMES.values(), 'test_formal48_guard_adapter01.py'}
            and all(valid_sha(digest) for digest in files.values()), 'Complete actual formal48 tool manifest required')
    pins = [binding, identity['describe']]
    parents = set()
    for key, name in ADAPTER_NAMES.items():
        path = checked(identity[key])
        require(path.name == name and identity[key]['sha256'] == files[name],
                'Actual adapter absolute path/bytes differ from the independently reviewed manifest')
        parents.add(path.parent)
        pins.append(identity[key])
    require(len(parents) == 1, 'Actual adapter shell and Python must remain original siblings')
    test_pin = pin(next(iter(parents)) / 'test_formal48_guard_adapter01.py')
    require(test_pin['sha256'] == files['test_formal48_guard_adapter01.py'], 'Reviewed actual adapter test bytes changed')
    pins.append(test_pin)
    return identity, pins


def adapter_prefix(value, admission_pin, identity):
    exact_schema(value, {'shell', 'python', 'reviewed_tools_sha256', 'argv_prefix', 'resolutions'}, 'adapter binding')
    for key in ADAPTER_NAMES:
        checked(value[key])
        require(value[key] == identity[key], 'Delegation differs from the separately pinned actual adapter')
    require(value['reviewed_tools_sha256'] == identity['reviewed_tools_sha256'], 'Actual adapter tool approval differs')
    prefix = value['argv_prefix']
    require(isinstance(prefix, list) and len(prefix) >= 6 and all(isinstance(token, str) and token for token in prefix)
            and prefix[:2] == ['bash', value['shell']['path']], 'Exact original adapter argv prefix required')
    require(len(prefix[2:]) % 2 == 0, 'Original adapter named arguments must be pairs')
    options = {}
    for flag, argument in zip(prefix[2::2], prefix[3::2]):
        require(flag not in options, 'Duplicate original adapter argument')
        options[flag] = argument
    expected = {'--manifest-sha256': admission_pin['sha256'], '--reviewed-tools-sha256': identity['reviewed_tools_sha256']}
    resolutions = value['resolutions']
    require(isinstance(resolutions, dict) and set(resolutions) <= {'core', 'extension'}, 'Only original explicit resolution pins allowed')
    pins = [value['shell'], value['python']]
    for label, binding in resolutions.items():
        checked(binding)
        expected['--' + label + '-resolution'] = binding['path']
        expected['--' + label + '-resolution-sha256'] = binding['sha256']
        pins.append(binding)
    require(options == expected, 'Adapter argv/options cannot change manifest, action, slot or resolutions')
    return list(prefix), pins


def selection_semantics(selection, basis, basis_pin, review, plans, dataset):
    require(selection.get('schema_version') == 1 and type(selection['schema_version']) is int
            and selection.get('kind') == 'PROSPECTIVE_SUPPLEMENTARY_DETECTION_SOURCE_SELECTIONS', 'Original selection object required')
    require(selection.get('selection_basis') == {'repository_path': 'planning/reliability-v4-delivery-selections.json',
            'sha256': basis_pin['sha256'], 'field': 'video_selection'}, 'Selection basis SHA/field differs')
    video = basis.get('video_selection', {})
    require(basis.get('selected_before_formal_execution') is True
            and video.get('classes') == list(dataset.CLASSES) and video.get('groups') == list(dataset.GROUPS)
            and integer(video.get('seed'), 1000) and integer(video.get('scheduled_clips'), 12), 'Original twelve-source video basis differs')
    expected = [f'{category}_{group}_seed1000' for category in dataset.CLASSES for group in dataset.GROUPS]
    require(selection.get('selected_slot_ids') == expected and len(set(expected)) == 12
            and selection.get('classes') == list(dataset.CLASSES) and selection.get('groups') == list(dataset.GROUPS)
            and integer(selection.get('seed'), 1000) and integer(selection.get('scheduled_recordings'), 12)
            and integer(selection.get('complete_formal_ledger_denominator'), 280)
            and integer(selection.get('new_formal_flight_slots'), 0)
            and selection.get('actual_protocol_must_be_created_after_both_formal_plans_and_before_any_formal_start') is True
            and selection.get('formal_seed_use_authorized') is False, 'Original ordered twelve-source/280 denominator policy differs')
    selected = {trial['id']: trial for trial in plans['core']['trials']}
    require(all(name in selected and integer(selected[name]['seed'], 1000)
                and selected[name]['target_class'] == category and selected[name]['group'] == group
                for name, (category, group) in zip(expected, ((category, group) for category in dataset.CLASSES for group in dataset.GROUPS))),
            'Selected source is absent from or relabelled in the actual core plan')
    rule = selection.get('sampling_rule')
    require(rule == {'first_follow_offset_s': 1., 'period_s': 2., 'end': 'FINAL_RECORDED_CLOCK',
                    'maximum_source_rgb_distance_s': .1, 'exact_tie': 'EARLIER_ACQUISITION',
                    'duplicate_acquisition': 'UNKNOWN_NO_SELECTION', 'image_cap': None}, 'Selection sampling rule changed')
    require(all(type(rule[key]) in (int, float) and math.isfinite(rule[key])
                for key in ('first_follow_offset_s', 'period_s', 'maximum_source_rgb_distance_s')), 'Sampling numbers cannot be booleans')
    approved = review.get('accepted_tool_and_author_test_files')
    require(isinstance(approved, dict) and set(approved) == {'prospective_detection_dataset.py', 'evaluate_prospective_detection.py', 'test_prospective_detection.py'}
            and all(valid_sha(value) for value in approved.values())
            and canonical(approved) == review.get('accepted_canonical_sha256') == selection.get('producer_tools_canonical_sha256'),
            'Selection producer approval does not match the independently accepted three-file map')


def audit_rows(path, context, current_time):
    if not path.exists():
        require(context['initial'] is None, 'No new prestart audit may be manufactured after original admission/attempts')
        return [], None
    original_pin = pin(path)
    lines = raw(path).decode('utf-8').splitlines()
    require(bool(lines) and all(line.strip() for line in lines), 'Existing audit is empty or malformed')
    rows, previous = [], None
    for sequence, line in enumerate(lines, 1):
        row = decode(line)
        exact_schema(row, {'schema_version', 'kind', 'sequence', 'created_utc', 'contract', 'admission',
                         'protocol', 'selection', 'preflight_tools_sha256', 'initial_admission',
                         'first_preflight_all280_untouched', 'previous_event_sha256', 'event_sha256'}, 'audit event')
        require(integer(row['schema_version'], 1) and row['kind'] == AUDIT_KIND and integer(row['sequence'], sequence)
                and row['contract'] == context['contract_pin'] and row['admission'] == context['contract']['admission']
                and row['protocol'] == context['contract']['detection_protocol'] and row['selection'] == context['contract']['selection']
                and row['preflight_tools_sha256'] == context['tools_sha'] and row['previous_event_sha256'] == previous
                and row['event_sha256'] == canonical({key: value for key, value in row.items() if key != 'event_sha256'}),
                'Original separate preflight audit chain/bindings changed')
        when = stamp(row['created_utc'])
        require(context['contract_time'] <= when <= current_time
                and (not rows or stamp(rows[-1]['created_utc']) <= when), 'Preflight audit clock/order is invalid')
        require(row['first_preflight_all280_untouched'] is (sequence == 1), 'Only first audit establishes untouched prestart facts')
        if sequence == 1:
            require(row['initial_admission'] is None, 'First audit must precede original initial admission')
        elif row['initial_admission'] is not None:
            require(row['initial_admission'] == context['initial_pin'], 'Original initial-admission evidence drifted')
        rows.append(row)
        previous = row['event_sha256']
    return rows, original_pin


def validate_contract(contract_pin, manifest_path, tools_sha, *, adapter_binding, adapter_reviewed_sha, now=None):
    current_time = datetime.now(timezone.utc) if now is None else now
    require(current_time.tzinfo is not None and valid_sha(tools_sha) and canonical(tool_manifest()) == tools_sha,
            'Exact independently reviewed new tools and aware current time required')
    contract = read(contract_pin)
    exact_schema(contract, FIELDS, 'external supplementary binding contract')
    require(integer(contract['schema_version'], 1) and contract['kind'] == KIND
            and contract['preflight_tools_sha256'] == tools_sha, 'Wrong external binding contract/new tool identity')
    contract_time = stamp(contract['created_utc'])
    require(contract_time <= current_time, 'Contract cannot be created in the future')
    require(contract['adapter_binding'] == adapter_binding,
            'Contract must bind the independently supplied actual adapter binding path/SHA')
    identity, identity_pins = adapter_identity(adapter_binding, adapter_reviewed_sha, contract_time)
    admission = read(contract['admission'])
    require(str(Path(manifest_path).resolve(strict=True)) == str(manifest_path)
            and pin(manifest_path) == contract['admission'], 'Serial admission argument differs from actual bound original manifest')
    require(integer(admission.get('schema_version'), 1) and admission.get('kind') == 'RELIABILITY_V4_FORMAL_ADMISSION'
            and admission.get('manifest_sha256') == canonical({key: value for key, value in admission.items() if key != 'manifest_sha256'})
            and stamp(admission['created_utc']) <= contract_time, 'Actual original sealed admission bytes/time required')
    require(contract['plans'] == admission.get('plans') and set(contract['plans']) == {'core', 'extension'}, 'Actual original formal plan pins differ')
    plans = {label: read(binding) for label, binding in contract['plans'].items()}
    root = Path(admission['final_root']).resolve(strict=True)
    require(root.is_dir() and str(root) == admission['final_root'] and all(plan['frozen_root'] == str(root) for plan in plans.values()), 'Actual physical final-root identity differs')
    results = (root / 'results').resolve(strict=True)
    for label, plan in plans.items():
        output = Path(plan['output']).resolve()
        require(integer(plan.get('schema_version'), 1) and output != results and output.is_relative_to(results)
                and Path(plan['results_root']).resolve() == results
                and pin(output / 'plan.json') == contract['plans'][label], 'Use the named original formal plan.json under its actual output')
    reference = plans['extension'].get('core_reference_binding', {})
    require(reference.get('path') == contract['plans']['core']['path']
            and reference.get('sha256') == contract['plans']['core']['sha256']
            and reference.get('plan_sha256') == plans['core']['plan_sha256'], 'Original extension file/digest reference differs')
    state = Path(admission['state_directory']).resolve()
    require(str(state) == admission['state_directory'] and state != results and state.is_relative_to(results)
            and not Path(admission['state_directory']).is_symlink(), 'Original guard state must remain in actual final results')
    checked(admission['tool'])
    require(Path(admission['tool']['path']) == root / 'tools/reliability_v4_guard.py', 'Actual sealed original guard source path differs')
    protocol = read(contract['detection_protocol'])
    require(protocol.get('plans') == contract['plans'] and protocol.get('frozen_root') == str(root), 'Protocol binds different original formal plans/root')
    review = read(contract['detection_review'])
    require(contract['detection_review']['sha256'] == DETECTION_REVIEW_SHA, 'Use the actual accepted independent detection-source review')
    require(review.get('status') == 'PASS_SOURCE_AND_SYNTHETIC_FIXTURES_ONLY', 'Detection source review scope differs')
    producers = protocol.get('producer_tools')
    require(isinstance(producers, dict) and set(producers) == {'prospective_detection_dataset.py', 'evaluate_prospective_detection.py'}, 'Complete original two-producer pins required')
    for name, binding in producers.items():
        checked(binding)
        require(Path(binding['path']).name == name and binding['sha256'] == review['accepted_tool_and_author_test_files'][name], 'Original producer bytes are not independently approved')
    # The unchanged verifier reads these named small start markers. Bound them
    # before calling it; an oversized/linked marker must never become a bag read.
    attempt_pins = []
    for plan in plans.values():
        for trial in plan['trials']:
            require(type(trial.get('seed')) is int and type(trial.get('stage')) is int,
                    'Original slot seed/stage must retain integer types')
            directory = Path(trial['directory'])
            require(directory.resolve() != results and directory.resolve().is_relative_to(results),
                    'Original trial directory escaped actual formal results')
            for path in (directory, Path(plan['output']) / 'slots' / (trial['id'] + '.started.json'),
                         Path(plan['output']) / 'slots' / (trial['id'] + '.json')):
                require(not path.is_symlink(), 'Linked original attempt metadata is not supported')
                if path != directory and path.exists():
                    attempt_pins.append(pin(path))
    dataset = source_module(producers['prospective_detection_dataset.py'])
    verified = dataset.validate_protocol(protocol, check_tools=True)
    require(verified == plans, 'Original protocol semantic verifier returned different plans')
    require(integer(protocol.get('schema_version'), 1), 'Strict protocol schema version required')
    protocol_time = stamp(protocol['created_utc'])
    require(max(stamp(plan['created_utc']) for plan in plans.values()) <= protocol_time <= contract_time <= current_time,
            'Protocol must follow both actual plans and precede actual preflight/current time')
    sources = plans['core']['source_hashes']
    require(sources == plans['extension']['source_hashes'] and all(valid_sha(value) for value in sources.values())
            and plans['core']['model_hashes'] == plans['extension']['model_hashes']
            == {name: digest for name, digest in sources.items() if name.endswith('.pt')}, 'Original formal source/model maps disagree')
    helper_pins = []
    for relative, digest in protocol['helper_source_hashes'].items():
        binding = pin(root / relative)
        require(binding['sha256'] == digest == sources[relative], 'Actual small original protocol helper bytes changed')
        helper_pins.append(binding)
    selection, basis = read(contract['selection']), read(contract['selection_basis'])
    selection_semantics(selection, basis, contract['selection_basis'], review, plans, dataset)
    require(stamp(selection['created_utc']) <= contract_time, 'Selection is later than its explicit prestart binding')
    prefix, adapter_pins = adapter_prefix(contract['adapter'], contract['admission'], identity)
    contract_path = external_path(contract_pin['path'], root, results, plans, state, suffix='.json')
    external_path(contract['detection_protocol']['path'], root, results, plans, state, suffix='.json')
    external_path(adapter_binding['path'], root, results, plans, state, suffix='.json')
    external_path(identity['describe']['path'], root, results, plans, state, suffix='.json')
    audit_path = external_path(contract['audit_log'], root, results, plans, state, suffix='.jsonl')
    input_pins = [contract_pin, contract['admission'], *contract['plans'].values(), contract['detection_protocol'],
                  contract['selection'], contract['selection_basis'], contract['detection_review'], admission['tool'],
                  *producers.values(), *helper_pins, *adapter_pins, *identity_pins, *attempt_pins]
    require(audit_path not in {Path(value['path']) for value in input_pins}, 'Audit cannot overwrite any bound input')
    require(not state.exists() or state.is_dir(), 'Original guard state is not a directory')
    initial_path = state / 'initial_admission.json'
    require(not initial_path.is_symlink(), 'Original initial-admission marker cannot be linked')
    initial = read(pin(initial_path)) if initial_path.exists() else None
    initial_pin = pin(initial_path) if initial is not None else None
    if initial is not None:
        require(integer(initial.get('schema_version'), 1) and initial.get('kind') == 'RELIABILITY_V4_INITIAL_FULL280_ADMISSION'
                and initial.get('receipt_sha256') == canonical({key: value for key, value in initial.items() if key != 'receipt_sha256'})
                and initial.get('manifest_sha256') == admission['manifest_sha256'] and initial.get('tool') == admission['tool']
                and integer(initial.get('initial_pending_slots'), 280) and contract_time <= stamp(initial['created_utc']) <= current_time,
                'Actual original full280 initial-admission evidence/time differs')
        input_pins.append(initial_pin)
    starts, products = [], []
    for plan in plans.values():
        for trial in plan['trials']:
            directory = Path(trial['directory'])
            started = Path(plan['output']) / 'slots' / (trial['id'] + '.started.json')
            terminal = Path(plan['output']) / 'slots' / (trial['id'] + '.json')
            require(not any(path.is_symlink() for path in (directory, started, terminal)), 'Linked original attempt metadata is not supported')
            products.extend(path.exists() for path in (directory, started, terminal))
            if started.is_file():
                binding = pin(started)
                marker = read(binding)
                began = stamp(marker['started_utc'])
                require(contract_time <= began <= current_time and stamp(admission['created_utc']) <= began
                        and initial is not None and stamp(initial['created_utc']) <= began,
                        'Original start preceded the supplementary binding/admission or is in the future')
                starts.append(began)
                input_pins.append(binding)
    if initial is None:
        require(not any(products), 'First supplementary preflight requires every original280 attempt untouched')
    context = {'contract': contract, 'contract_pin': pin(contract_path), 'contract_time': contract_time,
               'tools_sha': tools_sha, 'admission': admission, 'plans': plans, 'protocol': protocol,
               'prefix': prefix, 'audit_path': audit_path, 'initial': initial, 'initial_pin': initial_pin,
               'starts': starts, 'input_pins': input_pins, 'now': current_time}
    rows, audit_pin = audit_rows(audit_path, context, current_time)
    if initial is not None:
        require(rows and stamp(rows[0]['created_utc']) <= stamp(initial['created_utc'])
                and all(stamp(rows[0]['created_utc']) <= began for began in starts), 'Historical prestart audit must precede original admission and starts')
    context.update(audit_rows=rows, audit_pin=audit_pin)
    for binding in input_pins:
        checked(binding)
    require(canonical(tool_manifest()) == tools_sha, 'New preflight source changed during validation')
    return context


def append_audit(context):
    rows = context['audit_rows']
    if context['audit_pin'] is None:
        require(not context['audit_path'].exists() and not context['audit_path'].is_symlink(), 'Fresh prestart audit appeared concurrently')
    else:
        checked(context['audit_pin'])
    event = {'schema_version': 1, 'kind': AUDIT_KIND, 'sequence': len(rows) + 1,
             'created_utc': context['now'].isoformat(), 'contract': context['contract_pin'],
             'admission': context['contract']['admission'], 'protocol': context['contract']['detection_protocol'],
             'selection': context['contract']['selection'], 'preflight_tools_sha256': context['tools_sha'],
             'initial_admission': context['initial_pin'], 'first_preflight_all280_untouched': not rows,
             'previous_event_sha256': rows[-1]['event_sha256'] if rows else None}
    event['event_sha256'] = canonical(event)
    flags = os.O_WRONLY | (os.O_APPEND if rows else os.O_CREAT | os.O_EXCL)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(context['audit_path'], flags, 0o600)
    with os.fdopen(descriptor, 'ab') as stream:
        stream.write((json.dumps(event, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def run_one(contract_pin, manifest_path, tools_sha, *, adapter_binding, adapter_reviewed_sha, now=None, exec_function=None):
    context = validate_contract(contract_pin, manifest_path, tools_sha, adapter_binding=adapter_binding,
                                adapter_reviewed_sha=adapter_reviewed_sha, now=now)
    append_audit(context)
    for binding in context['input_pins']:
        checked(binding)
    require(canonical(tool_manifest()) == tools_sha, 'Preflight changed before original exec')
    argv = context['prefix'] + ['run-one', '--manifest', str(manifest_path)]
    (os.execvpe if exec_function is None else exec_function)(argv[0], argv, os.environ.copy())
    raise RuntimeError('Original adapter exec unexpectedly returned')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'verify', 'run-one'), nargs='?', default='describe')
    parser.add_argument('--contract', type=Path)
    parser.add_argument('--contract-sha256')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--reviewed-tools-sha256')
    parser.add_argument('--adapter-binding', type=Path)
    parser.add_argument('--adapter-binding-sha256')
    parser.add_argument('--adapter-reviewed-tools-sha256')
    args = parser.parse_args(argv)
    try:
        if args.action == 'describe':
            value = tool_manifest()
            print(json.dumps({'manifest': value, 'canonical_sha256': canonical(value), 'actual_action_executed': False}))
            return 0
        require(args.contract is not None and valid_sha(args.contract_sha256) and args.manifest is not None
                and args.adapter_binding is not None and valid_sha(args.adapter_binding_sha256)
                and valid_sha(args.adapter_reviewed_tools_sha256),
                'Explicit original contract/SHA, actual manifest, reviewed new tools and adapter identity required')
        binding = {'path': str(args.contract), 'sha256': args.contract_sha256}
        adapter_args = {'adapter_binding': {'path': str(args.adapter_binding), 'sha256': args.adapter_binding_sha256},
                        'adapter_reviewed_sha': args.adapter_reviewed_tools_sha256}
        if args.action == 'run-one':
            run_one(binding, args.manifest, args.reviewed_tools_sha256, **adapter_args)
        else:
            context = validate_contract(binding, args.manifest, args.reviewed_tools_sha256, **adapter_args)
            print(json.dumps({'kind': KIND, 'status': 'METADATA_BINDINGS_VERIFIED_NOT_GUARD_ADMISSION',
                              'contract': context['contract_pin'], 'prior_preflight_events': len(context['audit_rows']),
                              'original_attempts_started': len(context['starts']), 'guard_or_flight_started': False}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError, OverflowError, RuntimeError) as error:
        print(json.dumps({'kind': KIND, 'status': 'REFUSED_BEFORE_ORIGINAL_ADAPTER_EXEC',
                          'error': type(error).__name__ + ': ' + str(error), 'formal_admission_granted': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
