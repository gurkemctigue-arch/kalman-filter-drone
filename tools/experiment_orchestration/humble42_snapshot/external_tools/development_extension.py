"""Parameterized extension16, after actual same-source core12 and safety4.

Import/describe are inert. Planning emits a PENDING contract. Execution needs
its separately reviewed final contract and the original complete new core and
safety evidence. The frozen normal runner retains its argv and sole SITL lock.
Dependency canonical identities are explicit admission inputs, never draft pins.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys

import development_runner as core
import development_safety as safety
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
import local_runtime_observer41 as owner

EXTERNAL = Path(__file__).resolve().parent
SCOPE = 'PARAMETERIZED_EXTENSION16_NORMAL_RUNNER_DEVELOPMENT_ONLY'
ADMISSION = 'FINAL_PARAMETERIZED_EXTENSION16_INDEPENDENTLY_REVIEWED'
PENDING = 'PENDING_EXTENSION16_RUNTIME_REVIEW_NOT_EXECUTABLE'
FINAL = 'FINAL_PARAMETERIZED_EXTENSION16_NORMAL_RUNNER_INDEPENDENTLY_REVIEWED'
CONDITIONS = ('depth_noise','depth_holes','dropout','latency','combined',
              'speed_changes_velocity','speed_changes_position','far_distance')
EXTENSION_PROTOCOL = 'planning/reliability-v4-extension-preregistration.json'
OWN_FILES = ('development_extension.py','development_extension.sh','test_development_extension.py')
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small, write_new, utc = generic.read_small, generic.write_new, core.utc


@dataclass(frozen=True)
class Context:
    admission: dict
    candidate: dict
    review: dict
    built: dict
    runner: object
    modules: dict
    runtime: dict

    @property
    def root(self):
        return self.candidate['frozen_root']

    def safety_context(self):
        return safety.Context(self.candidate,self.review,self.built,self.runner,self.modules,self.runtime,
            Path(self.admission['core_contract']['path']),self.admission['core_contract']['sha256'],
            self.admission['dependency_tools']['safety'],self.admission['safety_registry']['sha256'])


def files_manifest(names):
    result = {}
    for name in names:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
                'Bounded extension/dependency source missing: '+name)
        result[name] = sha(path)
    return result


def tool_manifest():
    """Read source identities; no safety runtime validator or result reads."""
    for module in (core,safety,generic,stable,owner):
        require(Path(module.__file__).resolve(strict=True) ==
                (EXTERNAL/Path(module.__file__).name).resolve(strict=True),'Dependency import escaped external tools')
    return {'schema_version':1,'scope':SCOPE,'files':files_manifest(OWN_FILES),
        'core_tools_canonical_sha256':canonical(core.tool_manifest()),
        'safety_dependency_files':files_manifest(safety.OWN),
        'safety_canonical_policy':'explicit final admission; checked against actual safety.tool_manifest for every action',
        'normal_runner_apis':['make_extension_plan','persist_plan','run_plan'],
        'classes':list(core.CLASSES),'conditions':list(CONDITIONS),'flight_count':16,'seed':4,
        'fresh_actual_core12_all_PASS_required':True,'fresh_actual_safety4_all_PASS_required':True,
        'same_candidate_source_build_protocol_required':True,
        'maximum_new_trials_per_call':1,'driver_acquires_machine_sitl_lock':False,
        'normal_runner_owns_sitl_lock':True,'flight_or_evaluator_argv_modified':False,
        'algorithm_FAIL_preserved':True,'infrastructure_failure_stops':True,
        'observer_original_post_wait_outcome_required':True,'observer_archive_wall_budget_s':1800.,
        'default_admission':None,'default_runtime_contract':None,
        **{field:False for field in core.FALSE_FIELDS}}


def experiment(candidate):
    classes,_ = core.matrix_order(candidate)
    return {'classes':classes,'conditions':list(CONDITIONS),'seed':4,'duration_s':75.,'flight_count':16}


def locations(ctx):
    root,prefix = Path(ctx.root),ctx.admission['prefix']
    output = root/'results'/f'{prefix}_seed004_matrix'
    return {'output':output,'plan':output/'plan.json','run_driver':output/'observed_driver01',
        'plan_driver':root/'results/freeze_validation'/f'{prefix}_extension_plan_driver01',
        'pending_contract':EXTERNAL/f'development_extension_contract_{prefix}_pending01.json'}


def verify_dependencies(admission,candidate):
    actual_core = canonical(core.tool_manifest())
    require(admission.get('dependency_tools',{}).get('core') == actual_core == candidate['tools_canonical_sha256'],
            'Extension/core candidate final tool identities differ')
    require(admission['dependency_tools'].get('safety') == canonical(safety.tool_manifest()),
            'Explicit final independently reviewed safety tool identity required')


def load_admission(path,expected_sha):
    require(path is not None and generic.valid_sha(expected_sha),'Explicit extension admission path/SHA required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
            and re.fullmatch(r'development_extension_admission_[A-Za-z0-9_]+\.json',path.name),
            'Named external extension16 admission required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
            and value.get('scope') == SCOPE and value.get('status') == ADMISSION,
            'Final independently reviewed extension16 admission required')
    require(value.get('authorized_actions') == ['plan','run']
            and all(value.get(name) is False for name in core.FALSE_FIELDS)
            and 'zero_attempt_recovery' not in value,
            'Extension admission cannot authorize retries, recovery, readiness or formal seeds')
    for name in ('candidate_manifest','core_contract','safety_registry','extension_protocol'):
        binding = value.get(name)
        require(isinstance(binding,dict) and set(binding) == {'path','sha256'}
                and generic.valid_sha(binding.get('sha256')),'Explicit actual '+name+' binding required')
    require(isinstance(value.get('dependency_tools'),dict) and set(value['dependency_tools']) == {'core','safety'}
            and all(generic.valid_sha(digest) for digest in value['dependency_tools'].values())
            and value.get('tools_canonical_sha256') == canonical(tool_manifest()),
            'Explicit extension/core/safety tool identities required')
    candidate,review = core.load_candidate(value['candidate_manifest']['path'],value['candidate_manifest']['sha256'])
    verify_dependencies(value,candidate)
    prefix = value.get('prefix')
    require(isinstance(prefix,str) and re.fullmatch(r'reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,70}',prefix)
            and prefix != candidate['prefix'] and prefix != 'reliability_v4_humble41_extensions_probe',
            'Fresh independently bound extension prefix required')
    actual_experiment = value.get('experiment')
    require(actual_experiment == experiment(candidate) and type(actual_experiment.get('seed')) is int
            and type(actual_experiment.get('flight_count')) is int,'Complete2-class/eight-condition/int seed4 matrix required')
    root = candidate['frozen_root']
    require(value['extension_protocol']['path'] == root+'/'+EXTENSION_PROTOCOL
            and review.get('files',{}).get(EXTENSION_PROTOCOL) == value['extension_protocol']['sha256'],
            'Extension protocol must belong to the same reviewed frozen source')
    core.checked_metadata(value['extension_protocol'],json_only=True)
    extension = read_small(value['extension_protocol']['path'])
    require(extension.get('duration_s') == 75. and extension.get('conditions') == list(CONDITIONS)
            and 4 not in extension.get('seeds',[]),'Actual full75s/eight-condition development registration required')
    expected_registry = str(Path(root)/'results'/(candidate['prefix']+'_safety_seed004_audit')/'registry.json')
    require(Path(value['safety_registry']['path']) == Path(expected_registry),
            'Only actual same-candidate new safety4 registry is admitted')
    core.checked_metadata(value['core_contract'],json_only=True)
    core.checked_metadata(value['safety_registry'],json_only=True)
    value['_admission_binding'] = {'path':str(path),'sha256':expected_sha}
    return value,candidate,review


def entry_binding(ctx):
    core.checked_metadata(ctx.admission['_admission_binding'],json_only=True)
    require(ctx.admission['tools_canonical_sha256'] == canonical(tool_manifest()),'Reviewed extension tools changed')
    verify_dependencies(ctx.admission,ctx.candidate)
    for name in ('core_contract','safety_registry','extension_protocol'):
        core.checked_metadata(ctx.admission[name],json_only=True)
    return {'extension_admission':ctx.admission['_admission_binding'],
        'extension_tools_canonical_sha256':ctx.admission['tools_canonical_sha256'],
        'dependency_tools':ctx.admission['dependency_tools'],
        'extension_protocol':ctx.admission['extension_protocol'],
        'candidate_source_build':core.entry_binding(ctx.candidate,ctx.review,ctx.built)}


def require_prerequisites(ctx):
    """Use actual new execution APIs; no historic PASS or manual summary input."""
    safety_ctx = ctx.safety_context()
    path,plan,core_result = safety.actual_core(safety_ctx,ctx.review,ctx.built,ctx.runner)
    require(core_result.get('result') == 'PASS' and core_result.get('all_original_core_cells_pass') is True
            and type(core_result.get('completed_count')) is int and core_result['completed_count'] == 12,
            'All12 original same-candidate core attempts must pass healthily before extension')
    result = safety.require_completed_safety(safety_ctx,ctx.review,ctx.built,ctx.runner,
                                           core_plan=plan,core_plan_path=path)
    require(result.get('all_four_original_pass') is True
            and result.get('formal_seed_use_authorized') is False
            and {key:result.get('registry',{}).get(key) for key in ('path','sha256')} == ctx.admission['safety_registry'],
            'Actual same-candidate original safety4 acceptance/registry required')
    return {'core':core_result,'safety':result,'core_contract':ctx.admission['core_contract'],
            'safety_registry':ctx.admission['safety_registry'],'dependency_tools':ctx.admission['dependency_tools']},plan


def same_core(plan,reference):
    require(all(plan.get(field) == reference.get(field) for field in
        ('frozen_root','results_root','protocol','protocol_sha256','source_hashes','model_hashes','config_hashes',
         'magnetic_runtime_binding','magnetic_library_binding')),
        'Extension source/model/build/runtime/protocol differs from actual completed candidate core')


def validate_matrix(ctx,plan,reference,path=None):
    runner = ctx.runner
    runner.validate_plan(plan,path)
    same_core(plan,reference)
    classes = experiment(ctx.candidate)['classes']
    expected = [f'{cls}_extension_{condition}_seed004' for cls in classes for condition in CONDITIONS]
    selected = locations(ctx)
    require(plan.get('mode') == 'EXTENSION_PROBE' and plan.get('frozen_root') == ctx.root
            and plan.get('prefix') == ctx.admission['prefix'] and Path(plan['output']).resolve() == selected['output'].resolve()
            and plan.get('selected_classes') == classes and plan.get('selected_seeds') == [4]
            and type(plan['selected_seeds'][0]) is int
            and plan.get('selected_extension_conditions') == list(CONDITIONS)
            and plan.get('selected_groups') == ['stage1_velocity','stage1_position']
            and [trial.get('id') for trial in plan.get('trials',[])] == expected,
            'Exact original complete2-class/eight-condition/seed004 extension16 required')
    protocol = reference['protocol']
    extension = read_small(ctx.admission['extension_protocol']['path'])
    require(plan.get('extension_protocol_binding') == {'path':ctx.admission['extension_protocol']['path'],
            'sha256':ctx.admission['extension_protocol']['sha256'],'protocol':extension},
            'Actual immutable extension protocol binding differs')
    require(plan.get('postprocessing_timeout_s') == reference['postprocessing_timeout_s'] == 1800.
            and plan.get('evaluation_timeout_s') == reference['evaluation_timeout_s'] == 1800.
            and plan.get('trial_timeout_s') == reference['trial_timeout_s'],
            'Original core flight/postprocessing/evaluation budgets must be retained')
    core.policy.validate_class_policy(protocol,runner)
    pacing = protocol[core.policy.PACING_FIELD]
    for trial,(cls,condition) in zip(plan['trials'],((cls,condition) for cls in classes for condition in CONDITIONS)):
        resource = protocol['resources'][cls]
        group = extension['reference_groups'][condition]
        distance = extension['far_distance_m_by_class'][cls] if condition == 'far_distance' else resource['desired_distance_m']
        car = cls == 'car'
        require(trial.get('target_class') == cls and trial.get('extension_condition') == condition
                and trial.get('group') == group and type(trial.get('seed')) is int and trial['seed'] == 4
                and trial.get('duration_s') == 75. and trial.get('wall_timeout_s') == protocol['flight_wall_timeout_s']
                and all(trial.get(key) == resource[key] for key in ('model','inference_image_size','inference_threads'))
                and type(trial.get('inference_image_size')) is int and type(trial.get('inference_threads')) is int
                and trial.get('desired_distance_m') == distance
                and runner.correlated_two_face_trial_binding(plan,trial) == (car,car)
                and runner.car_surface_recovery_trial_binding(plan,trial) == (car,car),
                'Registered extension class resource/geometry/condition/reference differs')
        require(trial.get(core.policy.PACING_FIELD) == pacing
                and runner.simulation_pacing_trial_binding(plan,trial) == pacing,
                'Every extension slot must retain actual core registered pacing')
        core.original41.validate_exclusive_trial(plan,trial,runner)
    return plan


def checked_plan(ctx,reference):
    path = locations(ctx)['plan']
    plan = read_small(path)
    validate_matrix(ctx,plan,reference,path)
    ctx.runner.verify_sources(plan)
    return plan


def finish_action(ctx,observer,directory):
    finished = core.finish_action(ctx.candidate,ctx.review,ctx.built,ctx.runner,observer,directory)
    finished['candidate_source_binding_after'] = finished.pop('entry_binding_after')
    try:
        finished['entry_binding_after'] = entry_binding(ctx)
        require(finished['entry_binding_after']['candidate_source_build'] == finished['candidate_source_binding_after'],
                'Actual source changed between owner and extension closure')
    except BaseException as error:
        finished['entry_binding_after'] = None
        finished['final_errors'].append('extension_binding:'+type(error).__name__+':'+str(error))
    return finished


def plan_extension(ctx):
    selected,runner = locations(ctx),ctx.runner
    require(not any(selected[name].exists() or selected[name].is_symlink() for name in
                    ('output','plan_driver','pending_contract')) and not runner.simulation_processes(),
            'Fresh extension plan/driver/contract and idle runtime required')
    prerequisites,reference = require_prerequisites(ctx)
    before = entry_binding(ctx)
    directory = selected['plan_driver'];directory.mkdir(exist_ok=False)
    observer = core.make_observer(ctx.candidate,directory)
    error,initial = None,None
    try:
        with observer:
            plan = runner.make_extension_plan(Path(ctx.root),selected['output'],ctx.admission['prefix'],
                formal=False,seeds=[4],conditions=list(CONDITIONS),classes=experiment(ctx.candidate)['classes'])
            validate_matrix(ctx,plan,reference)
            runner.persist_plan(plan)
            core.require_fresh_rows(plan,runner.read_slots(plan))
            initial = core.pending_identity(plan)
            require(require_prerequisites(ctx)[0] == prerequisites,'Actual core/safety prerequisite changed during planning')
            observer.check()
    except BaseException as caught:
        error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(ctx,observer,directory)
    code = 0 if error is None and initial and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    terminal_path = directory/'execution_terminal.json'
    write_new(terminal_path,{'schema_version':1,'scope':SCOPE,'action':'plan','finished_utc':utc(),'returncode':code,
        'error':error,'entry_binding_before':before,'initial_pending':initial,'prerequisites':prerequisites,
        'runtime_preflight':ctx.runtime,**cleanup,'flights_started':0,**{name:False for name in core.FALSE_FIELDS}})
    if code == 0:
        value = {'schema_version':1,'scope':SCOPE,'status':PENDING,'created_utc':utc(),
            'extension_admission':ctx.admission['_admission_binding'],'entry_binding':before,'plan_pending':initial,
            'plan_terminal':stable.metadata_binding(terminal_path,json_only=True),'prerequisites':prerequisites,
            'experiment':experiment(ctx.candidate),**{name:False for name in core.FALSE_FIELDS}}
        write_new(selected['pending_contract'],value)
        print(json.dumps({'status':PENDING,'pending_contract':str(selected['pending_contract']),
                          'sha256':sha(selected['pending_contract']),'flights_started':0}),flush=True)
    return code


def load_contract(ctx,path,expected_sha):
    require(path is not None and generic.valid_sha(expected_sha),'Explicit separately reviewed actual extension contract required')
    path = Path(path)
    require(path.parent.resolve(strict=True) == EXTERNAL.resolve(strict=True)
            and re.fullmatch(r'development_extension_contract_[A-Za-z0-9_-]+\.json',path.name),
            'Named external extension runtime contract required')
    value = read_small(path)
    require(sha(path) == expected_sha and type(value.get('schema_version')) is int and value['schema_version'] == 1
            and value.get('scope') == SCOPE and value.get('status') == FINAL,
            'Actual independently reviewed final extension contract required; PENDING cannot execute')
    require(value.get('extension_admission') == ctx.admission['_admission_binding']
            and value.get('entry_binding') == entry_binding(ctx)
            and value.get('experiment') == experiment(ctx.candidate)
            and type(value['experiment'].get('seed')) is int and type(value['experiment'].get('flight_count')) is int
            and all(value.get(name) is False for name in core.FALSE_FIELDS) and 'zero_attempt_recovery' not in value,
            'Complete original extension16 source/tools/admission required; no recovery/formal permission')
    prerequisites,reference = require_prerequisites(ctx)
    require(value.get('prerequisites') == prerequisites,'Actual complete new core12/safety4 prerequisite changed')
    plan = checked_plan(ctx,reference)
    initial,selected = core.pending_identity(plan),locations(ctx)
    require(value.get('plan_pending') == initial,'Actual extension pending plan identity changed')
    core.original41.require_same_metadata_file(stable.metadata_binding(selected['plan'],json_only=True),initial['plan'])
    terminal_path = selected['plan_driver']/'execution_terminal.json'
    require(stable.metadata_binding(terminal_path,json_only=True) == value.get('plan_terminal'),'Original extension planning terminal changed')
    terminal = read_small(terminal_path)
    require(terminal.get('scope') == SCOPE and terminal.get('action') == 'plan'
            and type(terminal.get('returncode')) is int and terminal['returncode'] == 0 and terminal.get('error') is None
            and terminal.get('initial_pending') == initial and terminal.get('prerequisites') == prerequisites
            and type(terminal.get('flights_started')) is int and terminal['flights_started'] == 0
            and terminal.get('entry_binding_before') == terminal.get('entry_binding_after') == value['entry_binding']
            and terminal.get('final_errors') == [] and terminal.get('cleanup',{}).get('residual_processes') == []
            and all(terminal.get(name) is False for name in core.FALSE_FIELDS),
            'Original extension planning source/cleanup did not close cleanly')
    actual_owner = owner.validate_observer_root(terminal.get('observer_owner_terminal'),
        selected['plan_driver']/'observer_driver',ctx.root)
    require(actual_owner == terminal.get('observer'),'Original extension plan owner post-wait result changed')
    return value,plan


def run_extension(ctx,contract_path,contract_sha):
    contract,plan = load_contract(ctx,contract_path,contract_sha)
    selected,runner = locations(ctx),ctx.runner
    directory = selected['run_driver']
    core.require_fresh_rows(plan,runner.read_slots(plan))
    require(not directory.exists() and not directory.is_symlink() and not runner.simulation_processes(),
            'Fresh extension16 driver required; no retry/resume')
    before = entry_binding(ctx)
    directory.mkdir(exist_ok=False)
    observer = core.make_observer(ctx.candidate,directory)
    attempts,completed,error = [],[],None
    checks = ctx.modules['humble33_diagnostic_checks01']
    try:
        with observer:
            for number,trial in enumerate(plan['trials'],1):
                require(entry_binding(ctx) == before and sha(contract_path) == contract_sha,
                        'Source/build/admission/tools/contract changed before next extension slot')
                prerequisites,_ = require_prerequisites(ctx)
                require(prerequisites == contract['prerequisites'],'Actual original core/safety evidence changed')
                runner.verify_sources(plan)
                core.original41.require_same_metadata_file(stable.metadata_binding(selected['plan'],json_only=True),
                    contract['plan_pending']['plan'])
                rows = runner.read_slots(plan)
                require(rows[trial['id']]['status'] == 'PENDING' and not runner.simulation_processes()
                        and not Path(trial['directory']).exists() and not Path(trial['directory']).is_symlink(),
                        'Original extension slot already attempted/products present or runtime active')
                for previous in completed:
                    previous_trial = next(t for t in plan['trials'] if t['id'] == previous['slot'])
                    require(checks.terminal_binding(runner,plan,previous_trial,rows[previous['slot']]) ==
                            previous['audit']['record_binding'],'Prior immutable extension terminal changed')
                observer.check()
                attempt = {'slot':trial['id'],'number':number,'started_utc':utc(),'runner_result':None,
                           'record':None,'audit':None,'error':None}
                attempts.append(attempt)
                marker = directory/f'{number:02d}_{trial["id"]}.started.json'
                write_new(marker,{'slot':trial['id'],'number':number,'entry_binding':before,
                    'contract':{'path':str(contract_path),'sha256':contract_sha},'plan_sha256':plan['plan_sha256'],
                    'started_utc':attempt['started_utc'],'original_attempt_number':1})
                attempt['started_marker'] = stable.metadata_binding(marker,json_only=True)
                print(json.dumps({'event':'START_ORIGINAL_EXTENSION_SLOT','slot':trial['id'],'number':number,'total':16}),flush=True)
                try:
                    attempt['runner_result'] = core.observed_run_plan(runner,plan,observer)
                    record = runner.read_slots(plan)[trial['id']]
                    attempt['record'] = {'status':record.get('status'),'engineering_result':record.get('engineering_result'),
                                        'record_binding':checks.terminal_binding(runner,plan,trial,record)}
                    attempt['audit'] = core.original41.audit_record(runner,plan,trial,record,ctx.review,checks,extension=True)
                    require(type(attempt['runner_result'].get('started_this_invocation')) is int
                            and attempt['runner_result']['started_this_invocation'] == 1,
                            'Normal runner must consume exactly one original extension slot')
                    observer.check()
                    require(entry_binding(ctx) == before and sha(contract_path) == contract_sha,
                            'Original extension source/build/tools/contract changed during slot')
                    completed.append({'slot':trial['id'],'status':record['status'],
                                      'engineering_result':record['engineering_result'],'audit':attempt['audit']})
                except BaseException as caught:
                    attempt['error'] = type(caught).__name__+':'+str(caught)
                    raise
                finally:
                    attempt['finished_utc'] = utc()
                    write_new(directory/f'{number:02d}_{trial["id"]}.attempt_terminal.json',attempt)
    except BaseException as caught:
        error = type(caught).__name__+':'+str(caught)
    cleanup = finish_action(ctx,observer,directory)
    code = 0 if error is None and len(completed) == 16 and cleanup['entry_binding_after'] == before and not cleanup['final_errors'] else 2
    actual_rows,row_error = None,None
    try:
        actual_rows = {key:{'status':row.get('status'),'record_sha256':row.get('record_sha256')}
                       for key,row in runner.read_slots(plan).items()}
    except BaseException as caught:
        row_error,code = type(caught).__name__+':'+str(caught),2
    write_new(directory/'execution_terminal.json',{'schema_version':1,'scope':SCOPE,'action':'run','finished_utc':utc(),
        'returncode':code,'status':'ORIGINAL_EXTENSION16_TERMINALS_COMPLETE' if code == 0 else 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED',
        'error':error,'entry_binding_before':before,'runtime_preflight':ctx.runtime,
        'contract':{'path':str(contract_path),'sha256':contract_sha},'plan':contract['plan_pending'],
        'prerequisites':contract['prerequisites'],'planned_count':16,'attempt_count':len(attempts),'terminal_count':len(completed),
        'attempts':attempts,'slots':completed,'actual_slot_statuses':actual_rows,'slot_read_error':row_error,
        'status_counts':dict(Counter(row['status'] for row in (actual_rows or {}).values())),**cleanup,
        **{name:False for name in core.FALSE_FIELDS},
        'claim_boundary':'Complete original development extension attempts retain algorithm FAIL; no formal/project acceptance is granted.'})
    return code


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action',choices=('describe','plan','run'))
    result.add_argument('--admission',type=Path);result.add_argument('--admission-sha256')
    result.add_argument('--contract',type=Path);result.add_argument('--contract-sha256')
    return result


def reviewed_admission(args):
    require(args.action in ('plan','run'),'Explicit extension action required')
    if args.action == 'run':
        require(args.contract is not None and generic.valid_sha(args.contract_sha256),'Run requires separate final actual extension contract')
    return load_admission(args.admission,args.admission_sha256)


def shell_root(argv):
    _,candidate,_ = reviewed_admission(parser().parse_args(argv))
    return candidate['frozen_root']


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'describe':
            manifest = tool_manifest()
            print(json.dumps({'status':'PENDING_INDEPENDENT_TOOL_REVIEW','tool_manifest':manifest,
                'tools_canonical_sha256':canonical(manifest),'actual_action_executed':False},indent=2))
            return 0
        admission,candidate,review = reviewed_admission(args)
        generic.require_linux()
        modules = stable.dependencies()
        with generic.exclusive_window(),stable.stop_signals():
            built = stable.checked_build(candidate,review,modules['humble33_diagnostic_checks01'])
            runtime = core.require_runtime(candidate,review,modules['humble33_diagnostic_checks01'])
            built['_resource_runtime_binding'] = runtime['runtime_contracts']['resource']
            runner = generic.runner_at(candidate['frozen_root'])
            ctx = Context(admission,candidate,review,built,runner,modules,runtime)
            if args.action == 'plan':
                return plan_extension(ctx)
            return run_extension(ctx,args.contract,args.contract_sha256)
    except (OSError,ValueError,RuntimeError,KeyError,IndexError,StopIteration,subprocess.SubprocessError) as caught:
        print(json.dumps({'status':'DEVELOPMENT_EXTENSION_REFUSED_OR_FAILED','reason':type(caught).__name__+':'+str(caught),
                          **{name:False for name in core.FALSE_FIELDS}}),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
