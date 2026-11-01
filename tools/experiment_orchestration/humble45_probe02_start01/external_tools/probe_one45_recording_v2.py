"""Thin45 far-distance diagnostic adapter over the existing one-probe APIs.

Default describe is inert. Plan writes PENDING only. Run requires actual new45
source/build and independently reviewed one-slot contract; no formal admission.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ORIGINAL_SHA = '98813305af743965804a9c605392ef9cbff2e3eade589f6c8ec594df2314b369'
if hashlib.sha256((HERE/'probe_one43.py').read_bytes()).hexdigest() != ORIGINAL_SHA:
    raise ValueError('Reviewed original one-probe implementation changed')
import probe_one43 as original

require, read, pin, checked = original.require, original.read, original.pin, original.checked
write_new, utc, canonical = original.write_new, original.utc, original.canonical
ROOT = '/root/uav_tracking_fullplan_v4_humble45'
PREFIX = 'reliability_v4_humble45_recording_probe02'
SLOT = 'car_extension_far_distance_seed004'
NAME = PREFIX+'_'+SLOT
SCOPE = 'ONE45_CAR_FAR_DISTANCE_RECORDING_DIAGNOSTIC_NORMAL_RUNNER_ONLY'
PENDING = 'PENDING_PROBE_ONE_INDEPENDENT_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_PROBE_ONE_INDEPENDENTLY_REVIEWED'
KINDS = ['source_clock', 'native_startup', 'surface_flight', 'navigation']
FALSE = original.FALSE
OWN = ('probe_one45_recording_v2.py', 'probe_one45_recording_v2.sh', 'test_probe_one45_recording_v2.py')
ORIGINAL_TOOLS = '05673fc4988c78d5bdc54e6d99a96121dee939621b83f91f1a30c46f5fbbf282'
REFERENCE_PLAN_SHA = '954baf82accd5a227faaa6b57776736c93fb6a23c937025afa112616f71e5ada'
REFERENCE_PLAN_DIGEST = '9b4dad69a18e9b6ba60162841205bd7fa9333624fb8b79ae9066d9ec2c03fbbd'


def tool_manifest():
    borrowed = original.tool_manifest()
    require(canonical(borrowed) == ORIGINAL_TOOLS, 'Reviewed original one-probe tools changed')
    return {'scope': SCOPE, 'files': {n: pin(HERE/n)['sha256'] for n in OWN},
            'original_one_probe_tools': borrowed, 'default': 'describe',
            'maximum_new_trials': 1, 'automatic_next_action': False,
            'native_lock_owned_by': 'unchanged run_reliability_v4.run_plan',
            'flight_or_evaluator_parameters_modified': False}


def experiment():
    return {'slot': SLOT, 'name': NAME, 'seed': 4, 'duration_s': 75.,
            'desired_distance_m': 12., 'real_time_factor': .125, 'flight_count': 1,
            'counted_as_core_or_formal': False}


def locations(args):
    output = args.output.resolve()
    return {'output': output, 'plan': output/'plan.json', 'run_driver': output/'observed_driver01',
            'plan_driver': Path(ROOT)/'results/freeze_validation'/(PREFIX+'_single_plan_driver01'),
            'pending_contract': HERE/('probe_one_contract_'+PREFIX+'_pending01.json')}


def validate_args(args):
    require(args.frozen_root == ROOT and args.prefix == PREFIX, 'Only fresh45 recording diagnostic is supported')
    require(args.output is not None and args.output.is_absolute()
            and args.output.resolve() == (Path(ROOT)/'results'/(PREFIX+'_seed004_matrix')).resolve(),
            'Dedicated new45 one-slot output required')
    require(args.manifest is not None and args.manifest_sha256
            and canonical(tool_manifest()) == args.reviewed_tools_sha256,
            'Actual45 candidate and reviewed recording-probe tools required')
    if args.action == 'run':
        require(args.contract is not None and args.contract_sha256, 'Separately reviewed actual one-slot contract required')


def reference(review):
    path = Path(review['source_root'])/'results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/plan.json'
    bound = pin(path)
    require(bound['sha256'] == REFERENCE_PLAN_SHA, 'Original43 extension plan changed')
    plan = read(path)
    require(plan['plan_sha256'] == REFERENCE_PLAN_DIGEST
            and canonical({k: v for k, v in plan.items() if k != 'plan_sha256'}) == REFERENCE_PLAN_DIGEST,
            'Original43 extension plan digest changed')
    matches = [t for t in plan['trials'] if t['id'] == SLOT]
    require(len(matches) == 1, 'Unique original43 far-distance trial required')
    return matches[0], {'plan': bound, 'plan_sha256': REFERENCE_PLAN_DIGEST, 'slot': SLOT,
                       'trial_canonical_sha256': canonical(matches[0]),
                       'original_failure_retained': True, 'runtime45_acceptance': False}


def remap_trial(trial):
    old_name = trial['name']
    def mapped(value):
        if isinstance(value, str):
            return value.replace(old_name, NAME).replace('/root/uav_tracking_fullplan_v4_humble43', ROOT)
        if isinstance(value, list):
            return [mapped(item) for item in value]
        if isinstance(value, dict):
            return {key: mapped(item) for key, item in value.items()}
        return value
    return mapped(deepcopy(trial))


def require_original_trial(trial, previous):
    require(trial == remap_trial(previous), 'Only43->45 root and fresh trial name may change')
    require(trial['name'] == NAME and trial['id'] == SLOT
            and trial['stage'] == 1 and trial['multi_target'] is False
            and trial['seed'] == 4 and trial['duration_s'] == 75.
            and trial['desired_distance_m'] == 12.
            and [e['kind'] for e in trial['evaluations']] == KINDS,
            'Exact original one-car75s/12m/four-evaluator scope required')


def validate_one(plan, backend, args, path=None):
    runner = backend.runner
    runner.validate_plan(plan, path)
    require(plan['mode'] == 'EXTENSION_PROBE' and plan['frozen_root'] == ROOT and plan['prefix'] == PREFIX
            and plan['selected_classes'] == ['car'] and plan['selected_seeds'] == [4]
            and plan['selected_groups'] == ['stage1_velocity', 'stage1_position']
            and plan['selected_extension_conditions'] == ['far_distance']
            and len(plan['trials']) == 1 and 4 not in plan['protocol']['seeds'],
            'Only one nonformal far-distance development trial is admitted')
    previous, bound = reference(backend.review)
    trial = plan['trials'][0]
    require_original_trial(trial, previous)
    require(plan['trial_timeout_s'] == 2800. and plan['postprocessing_timeout_s'] == 1800.
            and plan['evaluation_timeout_s'] == 1800., 'Original execution budgets required')
    require(runner.simulation_pacing_trial_binding(plan, trial)['real_time_factor'] == .125
            and runner.car_surface_recovery_trial_binding(plan, trial) == (True, True),
            'Original pacing/surface configuration required')
    protocol = read(checked(backend.candidate['protocol']))
    require(plan['protocol'] == protocol,
            'Plan protocol differs from actual immutable frozen45 candidate protocol')
    backend.core.policy.validate_class_policy(plan['protocol'], runner)
    return bound


def fresh(plan, runner):
    rows = runner.read_slots(plan)
    require(set(rows) == {SLOT} and rows[SLOT]['status'] == 'PENDING'
            and not Path(plan['trials'][0]['directory']).exists()
            and not runner.simulation_processes(), 'Untouched PENDING1 and idle runtime required; no retry')


def pending_identity(plan):
    return {'plan': pin(Path(plan['output'])/'plan.json'), 'plan_sha256': plan['plan_sha256'],
            'slot_ids': [SLOT], 'initial_status_counts': {'PENDING': 1}}


class Backend(original.Backend):
    def load(self, args):
        self.candidate, self.review = self.core.load_candidate(args.manifest, args.manifest_sha256)
        require(self.candidate['frozen_root'] == ROOT, 'Actual healthy source/build candidate must be45')

    def prepare(self):
        self.modules = self.stable.dependencies()
        self.checks = self.modules['humble33_diagnostic_checks01']
        self.built = self.stable.checked_build(self.candidate, self.review, self.checks)
        self.runtime = self.core.require_runtime(self.candidate, self.review, self.checks)
        self.built['_resource_runtime_binding'] = self.runtime['runtime_contracts']['resource']
        self.runner = self.generic.runner_at(ROOT)

    def original_audit(self, plan, trial, record):
        return self.core.original41.audit_record(self.runner, plan, trial, record, self.review, self.checks, extension=True)

    def revalidate_plan_owner(self, terminal, directory):
        observed = self.core.owner.validate_observer_root(terminal.get('observer_owner_terminal'),
                    Path(directory)/'observer_driver', ROOT)
        require(terminal.get('observer') == observed, 'Original plan owner outcome changed')


def plan_action(args, backend):
    paths, runner = locations(args), backend.runner
    require(all(not paths[k].exists() and not paths[k].is_symlink()
                for k in ('output', 'plan_driver', 'pending_contract'))
            and not runner.simulation_processes(), 'Fresh single planning paths and idle runtime required')
    before = backend.binding()
    directory = paths['plan_driver']; directory.mkdir(exist_ok=False)
    observer = backend.observer(directory)
    identity, original43, error = None, None, None
    try:
        with observer:
            plan = runner.make_extension_plan(Path(ROOT), paths['output'], PREFIX, formal=False,
                        seeds=[4], conditions=['far_distance'], classes=['car'])
            original43 = validate_one(plan, backend, args)
            runner.persist_plan(plan)
            fresh(plan, runner)
            identity = pending_identity(plan)
            observer.check()
    except BaseException as caught:
        error = type(caught).__name__+': '+str(caught)
    cleanup = backend.finish(observer, directory)
    code = 0 if error is None and identity and cleanup.get('entry_binding_after') == before and not cleanup.get('final_errors') else 2
    terminal = directory/'execution_terminal.json'
    write_new(terminal, {'schema_version': 1, 'scope': SCOPE, 'action': 'plan', 'returncode': code,
        'finished_utc': utc(), 'error': error, 'entry_binding_before': before, 'plan_pending': identity,
        'original43_reference': original43, 'tools_sha256': args.reviewed_tools_sha256,
        'runtime_preflight': backend.runtime, 'flights_started': 0, **cleanup, **{k: False for k in FALSE}})
    if code == 0:
        write_new(paths['pending_contract'], {'schema_version': 1, 'scope': SCOPE, 'status': PENDING,
            'created_utc': utc(), 'frozen_root': ROOT, 'prefix': PREFIX, 'plan_pending': identity,
            'entry_binding': before, 'plan_terminal': pin(terminal), 'tools_sha256': args.reviewed_tools_sha256,
            'original43_reference': original43, 'experiment': experiment(), **{k: False for k in FALSE}})
    return code


def load_one_contract(args, backend):
    path = args.contract.resolve(strict=True)
    require(path.parent == HERE and re.fullmatch(r'probe_one_contract_[A-Za-z0-9_-]+\.json', path.name), 'Named external one-slot contract required')
    bound = {'path': str(path), 'sha256': args.contract_sha256}
    contract = read(checked(bound))
    require(type(contract.get('schema_version')) is int and contract['schema_version'] == 1
            and contract.get('scope') == SCOPE and contract.get('status') == FINAL
            and contract.get('frozen_root') == ROOT and contract.get('prefix') == PREFIX
            and contract.get('tools_sha256') == args.reviewed_tools_sha256
            and contract.get('entry_binding') == backend.binding() and contract.get('experiment') == experiment()
            and all(contract.get(k) is False for k in FALSE), 'Actual separately reviewed recording diagnostic contract differs')
    paths = locations(args)
    plan = read(paths['plan'])
    original43 = validate_one(plan, backend, args, paths['plan'])
    backend.runner.verify_sources(plan)
    fresh(plan, backend.runner)
    require(contract.get('plan_pending') == pending_identity(plan) and contract.get('original43_reference') == original43,
            'Prospectively bound original plan/reference changed')
    terminal = read(checked(contract['plan_terminal']))
    require(pin(paths['plan_driver']/'execution_terminal.json') == contract['plan_terminal']
            and terminal.get('scope') == SCOPE and terminal.get('action') == 'plan'
            and type(terminal.get('returncode')) is int and terminal['returncode'] == 0
            and terminal.get('error') is None and type(terminal.get('flights_started')) is int
            and terminal['flights_started'] == 0 and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == contract['entry_binding']
            and terminal.get('plan_pending') == contract['plan_pending'] and terminal.get('original43_reference') == original43
            and terminal.get('final_errors') == [] and terminal.get('cleanup', {}).get('residual_processes') == [], 'Actual plan closure differs')
    backend.revalidate_plan_owner(terminal, paths['plan_driver'])
    return contract, bound, plan


def run_action(args, backend):
    contract, bound, plan = load_one_contract(args, backend)
    directory = locations(args)['run_driver']
    require(not directory.exists() and not directory.is_symlink(), 'Fresh run driver required; no retry')
    before = backend.binding(); directory.mkdir(exist_ok=False)
    observer = backend.observer(directory)
    attempt = {'slot': SLOT, 'number': 1, 'started_utc': utc(), 'error': None}
    error, stop, record, audited = None, None, None, None
    try:
        with observer:
            marker = directory/'attempt.started.json'
            write_new(marker, {'slot': SLOT, 'number': 1, 'entry_binding': before,
                'contract': bound, 'plan_sha256': plan['plan_sha256'], 'started_utc': attempt['started_utc']})
            attempt['started_marker'] = pin(marker)
            attempt['runner_result'] = backend.run(plan, observer)  # Existing normal runner owns its SITL lock.
            require(type(attempt['runner_result'].get('started_this_invocation')) is int
                    and attempt['runner_result']['started_this_invocation'] == 1, 'Exactly one original trial must be consumed')
            record = backend.runner.read_slots(plan)[SLOT]
            attempt['record'] = {'status': record.get('status'), 'engineering_result': record.get('engineering_result'),
                'record_binding': backend.checks.terminal_binding(backend.runner, plan, plan['trials'][0], record)}
            audit_error = None
            try:
                audited = backend.original_audit(plan, plan['trials'][0], record)
            except BaseException as caught:
                audit_error = type(caught).__name__+': '+str(caught)
                audited = {'status': 'ORIGINAL_AUDIT_INCOMPLETE', 'error': audit_error}
            try:
                roles = backend.checks.process_evidence(plan['trials'][0]['directory'], stage=1, multi_target=False, condition='clean')
            except BaseException as caught:
                roles = {'status': 'INCOMPLETE', 'error': type(caught).__name__+': '+str(caught)}
            stop = original.stop_audit(plan['trials'][0]['directory'], record, roles)
            observer.check()
            require(backend.binding() == before, 'Actual source/build/resource binding changed during trial')
            checked(bound)
            require(audit_error is None, 'Original record audit failed: '+str(audit_error))
    except BaseException as caught:
        error = type(caught).__name__+': '+str(caught)
        attempt['error'] = error
    finally:
        attempt['finished_utc'] = utc()
        write_new(directory/('01_'+SLOT+'.attempt_terminal.json'), attempt)
    cleanup = backend.finish(observer, directory)
    code = 0 if error is None and stop and stop['status'] == 'PASS' and cleanup.get('entry_binding_after') == before and not cleanup.get('final_errors') else 2
    write_new(directory/'execution_terminal.json', {'schema_version': 1, 'scope': SCOPE, 'action': 'run',
        'status': 'ONE_ORIGINAL_ATTEMPT_RETAINED' if code == 0 else 'STOPPED_ORIGINAL_ATTEMPT_RETAINED',
        'finished_utc': utc(), 'returncode': code, 'error': error, 'entry_binding_before': before,
        'contract': bound, 'plan': contract['plan_pending'], 'tools_sha256': args.reviewed_tools_sha256,
        'original43_reference': contract['original43_reference'], 'attempts': [attempt],
        'original_slot_status': record.get('status') if record else None,
        'original_engineering_result': record.get('engineering_result') if record else None,
        'original_audit': audited, 'additional_stop_observation': stop, 'runtime_preflight': backend.runtime,
        **cleanup, **{k: False for k in FALSE},
        'claim_boundary': 'One recording diagnostic only. Original FAIL remains FAIL. No core/formal count or automatic next action.'})
    return code


def main(argv=None, *, backend_factory=Backend):
    args = original.parser().parse_args(argv)
    try:
        if args.action == 'describe':
            value = tool_manifest()
            print(json.dumps({'manifest': value, 'canonical_sha256': canonical(value), 'experimental_inputs_opened': False}))
            return 0
        validate_args(args)
        backend = backend_factory(); backend.load(args)
        with backend.window():
            backend.prepare()
            return plan_action(args, backend) if args.action == 'plan' else run_action(args, backend)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, ImportError) as error:
        print(json.dumps({'status': 'REFUSED_OR_ORIGINAL_ATTEMPT_RETAINED', 'error': type(error).__name__+': '+str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
