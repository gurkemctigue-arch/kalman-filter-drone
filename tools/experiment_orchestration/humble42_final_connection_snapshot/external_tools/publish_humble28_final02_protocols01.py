"""Explicit final02 canonical publication only; no planning, seal or flight.

Default describe is inert. Runtime calls the existing final-root validators;
the two actions reserve independent one-shot audit directories before mutation.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import SimpleNamespace

EXTERNAL = Path(__file__).resolve().parent
ROOT = Path('/root/uav_tracking_fullplan_v4_humble28_final02')
RESULTS = Path('/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble28_final02')
BUILD = EXTERNAL / 'humble28_final02_copy_build01/outcome.json'
PATHS = {name: 'planning/reliability-v4-' + suffix + '.json' for name, suffix in
         (('core', 'preregistration'), ('extension', 'extension-preregistration'),
          ('replay', 'estimator-replay-preregistration'))}
KIND = 'HUMBLE28_FINAL02_EXPLICIT_CANONICAL_PUBLICATION_REQUEST'
OUTCOME = 'HUMBLE28_FINAL02_CANONICAL_PUBLICATION_OUTCOME'
DRAFT = 'DRAFT_NOT_FROZEN_NOT_EXECUTED'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Expected ordinary file: ' + str(path))
    require(path.stat().st_size <= 128 * 1024**2, 'Only bounded metadata/code inputs are allowed')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    require(isinstance(value, dict), 'JSON object required')
    return value


def binding(path):
    return {'path': str(Path(path).resolve(strict=True)), 'sha256': sha(path)}


class Inputs:
    def __init__(self):
        self.pins = {}

    def bound(self, value):
        require(isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and Path(value['path']).is_absolute() and re.fullmatch('[a-f0-9]{64}', value['sha256']),
            'Exact absolute path/SHA256 binding required')
        path = Path(value['path'])
        require(binding(path) == value, 'Changed or aliased input: ' + str(path))
        self.pins[str(path)] = value['sha256']
        return read(path)

    def recheck(self):
        require(all(sha(path) == digest for path, digest in self.pins.items()), 'Publication input changed')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_context(inputs, request):
    require(request['copy_build']['path'] == str(BUILD), 'Actual fixed final02 copy/build outcome required')
    chain = inputs.bound(request['copy_build'])
    require(chain.get('schema_version') == 1
        and chain.get('status') == 'FINAL02_SOURCE_COPY_BUILD_AND_SUITE_COMPLETE_NO_FORMAL_ADMISSION'
        and chain.get('destination_root') == str(ROOT) and chain.get('results_root') == str(RESULTS)
        and chain.get('formal_admitted') is False and chain.get('formal_seed_use') is False
        and chain.get('protocols_registered') is False and chain.get('plans_created') is False
        and chain.get('flights_executed') == 0, 'No actual successful final02 copy/build chain')
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve(strict=True) == ROOT
        and RESULTS.is_dir() and not RESULTS.is_symlink() and RESULTS.resolve(strict=True) == RESULTS
        and (ROOT / 'results').is_symlink() and (ROOT / 'results').resolve(strict=True) == RESULTS,
        'Only the fixed new final02 source/results roots are accepted')
    source = inputs.bound(chain['source_copy_outcome'])
    built = inputs.bound(chain['build_outcome'])
    require(chain['source_copy_outcome']['path'] == str(RESULTS / 'freeze_validation/source_preparation_outcome.json')
        and chain['build_outcome']['path'] == str(RESULTS / 'freeze_validation/final_root_build02/outcome.json')
        and source.get('schema_version') == 1 and source.get('kind') == 'HUMBLE28_FINAL_ROOT_SOURCE_PREPARATION02_ONLY'
        and source.get('status') == 'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED'
        and source.get('source_unchanged') is True, 'Original final02 copy evidence differs')
    require(built.get('schema_version') == 1 and built.get('kind') == 'HUMBLE28_FINAL_ROOT02_COLD_BUILD_AND_SOURCE_ISOLATION'
        and built.get('status') == 'FINAL_ROOT_BUILT_AND_STATIC_CHECKS_VERIFIED_NOT_REGISTERED_OR_FLOWN'
        and built.get('root') == str(ROOT) and built.get('results') == str(RESULTS)
        and built.get('preparation') == chain['source_copy_outcome']
        and built.get('four_packages_built') is True and built.get('full_suite_status') == 'PASS'
        and built.get('source_unchanged') is True and built.get('formal_admitted') is False
        and built.get('formal_seed_use') is False, 'Cold build and full suite must actually pass')
    for key in ('source_copy_exit', 'cold_build_and_suite_exit'):
        require(inputs.bound(chain[key]).get('returncode') == 0, 'Original copy/build process failed')
    verification = inputs.bound(built['verification'])
    require(verification.get('status') == 'PASS_BUILD_AND_STATIC_CHECKS_ONLY'
        and verification.get('full_suite', {}).get('status') == 'PASS', 'Bound source/type/suite verification required')
    prepared = inputs.bound(chain['inputs'])
    require(prepared.get('kind') == 'HUMBLE28_FINAL02_COPY_BUILD_INPUTS_PREPARATION_ONLY'
        and prepared.get('destination_root') == str(ROOT) and prepared.get('results_root') == str(RESULTS)
        and prepared.get('run_full_suite') is True and prepared.get('formal_seed_use_authorized') is False,
        'Original fixed final02 source/build inputs required')
    require(prepared['helpers'].get('build_humble28_final_root02.py') == binding(EXTERNAL / 'build_humble28_final_root02.py')
        and prepared['helpers'].get('prepare_humble28_final_root02.py') == binding(EXTERNAL / 'prepare_humble28_final_root02.py'),
        'Actual bound final02 build and copy validators required')
    for value in prepared['helpers'].values():
        # Helpers are code, not JSON; bind before importing the actual validator.
        require(binding(value['path']) == value, 'Copy/build helper changed')
        inputs.pins[value['path']] = value['sha256']
    builder = load_module('publisher_final02_build', EXTERNAL / 'build_humble28_final_root02.py')
    context = builder.validate_receipt(Path(chain['source_copy_outcome']['path']), chain['source_copy_outcome']['sha256'])
    require(context['proposal'] == source['proposal']
        and verification.get('tools_sha256') == builder.tools(), 'Actual build provenance differs')
    return context, builder


def registrar(context):
    expected = context['proposal']['expected_protected_file_hashes']
    for name in ('tools/reliability_v4_register.py', 'tools/reliability_v4_guard.py'):
        require(sha(ROOT / name) == expected[name], 'Final02 registration helper changed')
    return load_module('publisher_final02_registrar', ROOT / 'tools/reliability_v4_register.py')


def patch_fields(raw, values):
    """Change only named top-level value spans; preserve every other byte."""
    prefix = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    text, decoder, spans = raw[len(prefix):].decode('utf-8'), json.JSONDecoder(), {}
    skip = lambda n: n + len(text[n:]) - len(text[n:].lstrip())
    pos = skip(0)
    require(text[pos] == '{', 'Canonical object required')
    pos = skip(pos + 1)
    while text[pos] != '}':
        key, pos = decoder.raw_decode(text, pos)
        pos = skip(pos)
        require(text[pos] == ':', 'Invalid canonical field')
        start = skip(pos + 1)
        _, pos = decoder.raw_decode(text, start)
        require(key not in spans, 'Duplicate canonical field')
        spans[key] = (start, pos)
        pos = skip(pos)
        if text[pos] == ',':
            pos = skip(pos + 1)
        else:
            require(text[pos] == '}', 'Invalid canonical separator')
    changes = []
    additions = []
    for key, value in values.items():
        encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        if key in spans:
            changes.append((*spans[key], encoded))
        else:
            additions.append(json.dumps(key) + ': ' + encoded)
    if additions:
        changes.append((pos, pos, ',\n  ' + ',\n  '.join(additions) + '\n'))
    for start, end, encoded in sorted(changes, reverse=True):
        text = text[:start] + encoded + text[end:]
    return prefix + text.encode('utf-8')


def pending(runtime, plan, path, mode, count):
    require(plan.get('mode') == mode and len(plan.get('trials', [])) == count
        and plan.get('frozen_root') == str(ROOT), 'Wrong final02 target/formal definition')
    if mode in {'PROBE', 'EXTENSION_PROBE'}:
        require(plan.get('selected_seeds') == [4]
            and plan.get('selected_classes') == list(runtime.v4.CLASSES)
            and plan.get('selected_groups') == (list(runtime.v4.GROUPS) if mode == 'PROBE' else ['stage1_velocity', 'stage1_position'])
            and (mode == 'PROBE' or plan.get('selected_extension_conditions') == list(runtime.v4.EXTENSION_CONDITIONS)),
            'Only the complete unexecuted canonical12/16 target snapshots qualify')
    runtime.v4.validate_plan(plan, path)
    runtime.v4.verify_sources(plan)
    require(all(row['status'] == 'PENDING' for row in runtime.v4.read_slots(plan).values()),
        'Every target/formal slot must remain unattempted')


def assembly(inputs, value, action, tool):
    outcome = inputs.bound(value)
    require(outcome.get('kind') == 'RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME'
        and outcome.get('status') == 'ASSEMBLED_AND_VALIDATED_NOT_EXECUTED'
        and outcome.get('action') == action and outcome.get('registrar') == binding(tool.__file__)
        and outcome.get('canonical_files_modified') is False and outcome.get('formal_attempts_started') == 0,
        'Actual validated registrar assembly outcome required')
    artifact = inputs.bound(outcome['artifact'])
    require(outcome['artifact']['sha256'] == outcome.get('validated_bytes_sha256'), 'Validated candidate byte binding differs')
    started = inputs.bound(binding(Path(value['path']).parent / 'started.json'))
    require(started.get('kind') == 'RELIABILITY_V4_REGISTRATION_ASSEMBLY_START'
        and started.get('action') == action and started.get('registrar') == outcome['registrar']
        and started.get('guard') == binding(tool.guard.__file__),
        'Original registrar inputs/started evidence differs')
    for key, pin in started['inputs'].items():
        inputs.bound(pin)
    return outcome['artifact'], artifact, started['inputs']


def prepare_protocols(inputs, request, context, builder):
    builder.source_check(context)
    tool = registrar(context)
    core = inputs.bound(request['target_plans']['core'])
    extension = inputs.bound(request['target_plans']['extension'])
    core_gate = inputs.bound(request['gates']['core'])
    extension_gate = inputs.bound(request['gates']['extension'])
    require(core.get('frozen_root') == extension.get('frozen_root') == str(ROOT)
        and core.get('source_hashes') == extension.get('source_hashes') == context['proposal']['expected_classified_source_hashes'],
        'Targets must bind the actual fixed final02 source before runtime import')
    runtime, safety_context = tool.gate_context(request['target_plans']['core']['path'], request['gates']['core']['path'])
    pending(runtime, core, request['target_plans']['core']['path'], 'PROBE', 12)
    pending(runtime, extension, request['target_plans']['extension']['path'], 'EXTENSION_PROBE', 16)
    require(core['source_hashes'] == extension['source_hashes'] == context['proposal']['expected_classified_source_hashes']
        and runtime.v4.flight_source_hashes(core['source_hashes']) == context['proposal']['flight_source_hashes'],
        'Targets differ from the actual same-flight-source final02 build')
    for gate in (core_gate, extension_gate):
        tool.guard.no_fixture(gate, 'Actual development gate')
    originals = {name: (ROOT / PATHS[name]).read_bytes() for name in ('core', 'extension')}
    old_core, old_extension = (read(ROOT / PATHS[name]) for name in ('core', 'extension'))
    require(old_core['status'] == old_extension['status'] == DRAFT
        and old_core == core['protocol'] and old_extension == extension['extension_protocol_binding']['protocol'],
        'Actual unchanged draft target protocols required')
    stamp = now()
    changed_core = {**old_core, 'status': 'REGISTERED', 'registration_utc': stamp}
    changed_extension = {**old_extension, 'status': 'REGISTERED', 'registration_utc': stamp,
        'development_readiness': {**request['gates']['extension'], 'evidence': extension_gate}}
    runtime.v4.validate_protocol(changed_core)
    runtime.v4.validate_navigation_gates(changed_core['navigation_acceptance'])
    runtime.v4.validate_extension_protocol(changed_extension, changed_core, formal=True)
    test_plan = deepcopy(extension)
    test_plan['protocol'] = changed_core
    test_plan['extension_protocol_binding']['protocol'] = changed_extension
    runtime.v4.validate_probe_gate(test_plan, extensions=True)
    summary_pin, summary, used = assembly(inputs, request['safety_assembly'], 'safety-summary', tool)
    require(used['target_plan'] == request['target_plans']['core'] and used['core_gate'] == request['gates']['core'],
        'Safety assembly must bind these exact pre-registration targets/gate')
    safety_context.core['protocol'] = changed_core
    safety_context.registration_times = [tool.guard.utc(stamp), tool.guard.utc(stamp)]
    tool.guard.validate_safety({'safety': summary_pin}, safety_context, runtime)
    require(tool.guard.utc(summary['created_utc']) <= tool.guard.utc(stamp), 'Safety summary must precede protocol registration')
    candidates = {'core': patch_fields(originals['core'], {'status': 'REGISTERED', 'registration_utc': stamp}),
        'extension': patch_fields(originals['extension'], {key: changed_extension[key] for key in
            ('status', 'registration_utc', 'development_readiness')})}
    require(json.loads(candidates['core']) == changed_core and json.loads(candidates['extension']) == changed_extension,
        'Staged protocol bytes differ from validated candidates')
    return runtime, originals, candidates


def prepare_replay(inputs, request, context, builder):
    publication = inputs.bound(request['protocol_publication'])
    require(publication.get('kind') == OUTCOME and publication.get('action') == 'protocols'
        and publication.get('status') == 'PUBLISHED_NOT_ADMITTED' and publication.get('copy_build') == request['copy_build'],
        'Actual successful first protocol publication required')
    for name in ('core', 'extension'):
        require(binding(ROOT / PATHS[name]) == publication['published'][name], 'Published core/extension changed')
    tool = registrar(context)
    core, extension = (inputs.bound(request['formal_plans'][name]) for name in ('core', 'extension'))
    formal = tool.guard.read_plans({'plans': request['formal_plans'], 'final_root': str(ROOT)})
    runtime = tool.guard.load_runtime(ROOT, core)
    pending(runtime, core, request['formal_plans']['core']['path'], 'FORMAL', 120)
    pending(runtime, extension, request['formal_plans']['extension']['path'], 'EXTENSION_FORMAL', 160)
    require(core['source_hashes'] == context['proposal']['expected_classified_source_hashes']
        and runtime.v4.flight_source_hashes(core['source_hashes']) == context['proposal']['flight_source_hashes'],
        'Formal source differs from the actual canonical28 flight map')
    pin, candidate, used = assembly(inputs, request['replay_assembly'], 'replay-config', tool)
    require(used['core_plan'] == request['formal_plans']['core'], 'Replay registrar bound another formal core')
    runtime.replay.validate_registered_config(candidate)
    runtime.replay.verify_registration_artifacts(candidate, source_root=ROOT)
    require(candidate['freeze_requirements']['final_engineering_plan_path'] == request['formal_plans']['core']['path']
        and candidate['freeze_requirements']['final_engineering_plan_file_sha256'] == request['formal_plans']['core']['sha256']
        and candidate['freeze_requirements']['final_engineering_plan_digest'] == core['plan_sha256'],
        'Replay candidate does not bind the actual formal core')
    formal.replay_configuration = candidate
    formal.registration_times = [tool.guard.utc(core['protocol']['registration_utc']),
        tool.guard.utc(core['extension_protocol_binding']['protocol']['registration_utc']),
        tool.guard.utc(candidate['registration']['registered_utc'])]
    tool.guard.validate_development({'calibration': used['candidate']}, formal, runtime)
    original = (ROOT / PATHS['replay']).read_bytes()
    require(read(ROOT / PATHS['replay']).get('status') == DRAFT, 'Cannot replace registered replay configuration')
    return runtime, {'replay': original}, {'replay': Path(pin['path']).read_bytes()}


def write_bytes_new(path, raw):
    with Path(path).open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def write_new(path, value):
    write_bytes_new(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def publish(action, request_pin):
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22',
        'Only the actual isolated UAVHumble22 environment may publish')
    inputs = Inputs()
    request = inputs.bound(request_pin)
    common = {'schema_version', 'kind', 'action', 'copy_build', 'expected_canonical_sha256'}
    extras = {'target_plans', 'gates', 'safety_assembly'} if action == 'protocols' else {
        'protocol_publication', 'formal_plans', 'replay_assembly'}
    require(set(request) == common | extras and request.get('schema_version') == 1
        and request.get('kind') == KIND and request.get('action') == action, 'Explicit exact action request required')
    names = ('core', 'extension') if action == 'protocols' else ('replay',)
    require(set(request['expected_canonical_sha256']) == set(names), 'Bind every original canonical SHA')
    output = RESULTS / ('freeze_validation/canonical_' + action + '_publication01')
    require(not output.exists() and not output.is_symlink(), 'Existing one-shot publication reservation; no retry')
    context, builder = build_context(inputs, request)
    prepare = prepare_protocols if action == 'protocols' else prepare_replay
    runtime, originals, candidates = prepare(inputs, request, context, builder)
    require(runtime.v4.simulation_processes() == [], 'Simulation must be fully idle')
    for name in names:
        require(hashlib.sha256(originals[name]).hexdigest() == request['expected_canonical_sha256'][name]
            == context['proposal']['expected_protected_file_hashes'][PATHS[name]],
            'Original canonical bytes differ from explicit SHA or actual copy')
    inputs.recheck()
    output.mkdir(exist_ok=False)
    write_new(output / 'started.json', {'schema_version': 1, 'kind': OUTCOME, 'action': action,
        'started_utc': now(), 'request': request_pin, 'publisher': binding(__file__),
        'expected_canonical_sha256': request['expected_canonical_sha256'], 'copy_build': request['copy_build']})
    published = {}
    try:
        with runtime.v4.run_lock(output):
            require(runtime.v4.simulation_processes() == [], 'Runtime appeared before publication lock')
            for name in names:
                require(sha(ROOT / PATHS[name]) == request['expected_canonical_sha256'][name], 'Canonical changed before backup')
                write_bytes_new(output / (name + '.original.json'), originals[name])
                require(sha(output / (name + '.original.json')) == request['expected_canonical_sha256'][name], 'Backup byte check failed')
            for name in names:
                staged = ROOT / 'planning' / ('.publisher01-' + action + '-' + name + '.json')
                write_bytes_new(staged, candidates[name])
                os.chmod(staged, stat.S_IMODE((ROOT / PATHS[name]).stat().st_mode))
                require(staged.read_bytes() == candidates[name], 'Staged bytes differ from validated candidate')
            write_new(output / 'validated.json', {'inputs_sha256': inputs.pins,
                'original_backups': {name: binding(output / (name + '.original.json')) for name in names},
                'validated_candidate_sha256': {name: hashlib.sha256(candidates[name]).hexdigest() for name in names}})
            inputs.recheck()
            for name in names:
                canonical = ROOT / PATHS[name]
                require(sha(canonical) == request['expected_canonical_sha256'][name], 'Canonical changed before atomic replace')
                write_new(output / (name + '_publish_intent.json'), {'canonical': str(canonical), 'created_utc': now()})
                os.replace(ROOT / 'planning' / ('.publisher01-' + action + '-' + name + '.json'), canonical)
                require(canonical.read_bytes() == candidates[name], 'Published bytes differ')
                published[name] = binding(canonical)
                write_new(output / (name + '_published.json'), published[name])
        outcome = {'schema_version': 1, 'kind': OUTCOME, 'action': action, 'status': 'PUBLISHED_NOT_ADMITTED',
            'finished_utc': now(), 'copy_build': request['copy_build'], 'request': request_pin,
            'published': published, 'formal_attempts_started': 0, 'plans_created': False,
            'claim_boundary': 'Explicit canonical publication only. No final source seal, capacity admission or flight.'}
        write_new(output / 'outcome.json', outcome)
        return outcome
    except BaseException as error:
        observed = {}
        for name in names:
            try:
                observed[name] = binding(ROOT / PATHS[name])
            except Exception as probe:
                observed[name] = {'error': type(probe).__name__ + ':' + str(probe)}
        write_new(output / 'failed.json', {'kind': OUTCOME, 'status': 'STOPPED_RETAIN_PARTIAL_PUBLICATION_NO_RETRY',
            'finished_utc': now(), 'error': type(error).__name__ + ':' + str(error),
            'published_receipts': published, 'observed_canonical': observed,
            'rollback_attempted': False, 'preserve_all_original_backups': True})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('protocols', 'replay'), nargs='?', default='protocols')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--request-sha256')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'status': 'DESCRIBE_ONLY_NO_PUBLICATION', 'action': args.action,
            'fixed_final_root': str(ROOT), 'fixed_results': str(RESULTS), 'request_kind': KIND,
            'required_actual_copy_build_outcome': str(BUILD), 'request_required_for_execute': True,
            'formal_attempts_started': 0}, ensure_ascii=False), flush=True)
        return 0
    require(args.request is not None and args.request_sha256 is not None, 'Actual request path and SHA required')
    outcome = publish(args.action, {'path': str(args.request), 'sha256': args.request_sha256})
    print(json.dumps(outcome, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
