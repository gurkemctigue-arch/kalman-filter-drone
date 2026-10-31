"""Small synthetic extension16 gates/error injection; no ROS, inference or flight.

Mocks are scoped to dependency calls and use temporary metadata only. No original
source, policy global, historical result or executable contract is modified.
"""
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import development_extension as m


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,allow_nan=False)+'\n',encoding='utf-8')
    return {'path':str(path),'sha256':m.sha(path)}


class Observer:
    _finished={'original_post_wait':True}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def check(self):return {'fresh':True}


class Fixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='development_extension_pure_')
        self.addCleanup(temp.cleanup);self.temp=Path(temp.name).resolve()
        root=str(self.temp/'candidate')
        self.candidate={'frozen_root':root,'prefix':'reliability_v4_fixture_core',
            'core_classes':['car','person'],'core_groups':list(m.core.GROUPS),
            'tools_canonical_sha256':'c'*64}
        self.extension={'duration_s':75.,'conditions':list(m.CONDITIONS),'seeds':list(range(1000,1010)),
            'far_distance_m_by_class':{'person':7.,'car':12.},
            'reference_groups':{condition:('stage1_position' if condition=='speed_changes_position' else 'stage1_velocity')
                                for condition in m.CONDITIONS}}
        extension_binding=dump(Path(root)/m.EXTENSION_PROTOCOL,self.extension)
        extension_binding['path']=root+'/'+m.EXTENSION_PROTOCOL
        self.admission={'schema_version':1,'scope':m.SCOPE,'status':m.ADMISSION,
            'authorized_actions':['plan','run'],'candidate_manifest':{'path':'/candidate.json','sha256':'a'*64},
            'core_contract':{'path':'/core_contract.json','sha256':'b'*64},
            'safety_registry':{'path':str(Path(root)/'results'/(self.candidate['prefix']+'_safety_seed004_audit')/'registry.json'),
                               'sha256':'d'*64},
            'extension_protocol':extension_binding,'dependency_tools':{'core':'c'*64,'safety':'e'*64},
            'tools_canonical_sha256':'f'*64,'prefix':'reliability_v4_fixture_extensions',
            'experiment':m.experiment(self.candidate),**{key:False for key in m.core.FALSE_FIELDS}}
        self.review={'files':{m.EXTENSION_PROTOCOL:extension_binding['sha256']}}
        self.before={'candidate_source_build':{'source':'actual_same_candidate'},'extension':'actual_admission'}
        self.core_result={'result':'PASS','completed_count':12,'all_original_core_cells_pass':True,
                          'original_terminals':['actual_original']*12}
        self.safety_result={'all_four_original_pass':True,'formal_seed_use_authorized':False,
                            'registry':deepcopy(self.admission['safety_registry'])}
        self.prerequisites={'core':self.core_result,'safety':self.safety_result,
            'core_contract':self.admission['core_contract'],'safety_registry':self.admission['safety_registry'],
            'dependency_tools':self.admission['dependency_tools']}
        self.runner=SimpleNamespace(validate_plan=Mock(),simulation_pacing_declared=Mock(return_value=True),
            exclusive_navigation_declared=Mock(return_value=True),
            exclusive_navigation_summary=Mock(return_value={'car':True,'person':False}),
            simulation_pacing_trial_binding=lambda p,t:p['protocol'][m.core.policy.PACING_FIELD],
            correlated_two_face_trial_binding=lambda p,t:(t['target_class']=='car',)*2,
            car_surface_recovery_trial_binding=lambda p,t:(t['target_class']=='car',)*2,
            exclusive_navigation_trial_binding=lambda p,t:(t['target_class']=='car',)*2,
            simulation_processes=Mock(return_value=[]),verify_sources=Mock())
        self.checks=SimpleNamespace(terminal_binding=lambda r,p,t,row:{'slot':t['id'],'status':row['status']})
        self.ctx=m.Context(self.admission,self.candidate,self.review,{},self.runner,
            {'humble33_diagnostic_checks01':self.checks},{'runtime_contracts':{'resource':{'actual':'512'}}})
        self.protocol={'flight_wall_timeout_s':1000.,m.core.policy.PACING_FIELD:deepcopy(m.core.policy.EXPECTED_PACING_V2),
            'resources':{'person':{'model':'person.pt','inference_threads':2,'inference_image_size':320,'desired_distance_m':5.},
                'car':{'model':'car.pt','inference_threads':4,'inference_image_size':512,'desired_distance_m':9.,
                        m.core.policy.EXCLUSIVE_FIELD:True}}}
        self.reference={'frozen_root':root,'results_root':root+'/results','protocol':self.protocol,
            'protocol_sha256':'a'*64,'source_hashes':{'actual_source':'b'*64},'model_hashes':{'car.pt':'c'*64},
            'config_hashes':{'actual_config':'d'*64},'magnetic_runtime_binding':{'actual':'runtime'},
            'magnetic_library_binding':{'actual':'library'},'postprocessing_timeout_s':1800.,
            'evaluation_timeout_s':1800.,'trial_timeout_s':2800.}
        self.plan=deepcopy(self.reference)
        self.plan.update(mode='EXTENSION_PROBE',prefix=self.admission['prefix'],output=str(m.locations(self.ctx)['output']),
            selected_classes=['car','person'],selected_seeds=[4],selected_extension_conditions=list(m.CONDITIONS),
            selected_groups=['stage1_velocity','stage1_position'],plan_sha256='synthetic_plan_identity',
            extension_protocol_binding={**extension_binding,'protocol':self.extension},trials=[])
        for cls in ['car','person']:
            for condition in m.CONDITIONS:
                identifier=f'{cls}_extension_{condition}_seed004'
                resource=self.protocol['resources'][cls]
                command=['original_flight',identifier,m.core.policy.ADAPTER_FLAG,'50.0']
                if cls=='car':command.append(m.core.policy.EXCLUSIVE_FLAG)
                self.plan['trials'].append({'id':identifier,'target_class':cls,'extension_condition':condition,
                    'group':self.extension['reference_groups'][condition],'seed':4,'duration_s':75.,'wall_timeout_s':1000.,
                    **resource,'desired_distance_m':self.extension['far_distance_m_by_class'][cls]
                        if condition=='far_distance' else resource['desired_distance_m'],
                    m.core.policy.PACING_FIELD:deepcopy(m.core.policy.EXPECTED_PACING_V2),m.core.policy.ADAPTER_FIELD:50.,
                    'flight_command':command,'directory':str(self.temp/'uncreated'/identifier)})

    def admission_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(m,'EXTERNAL',self.temp))
        stack.enter_context(patch.object(m,'tool_manifest',return_value={'fixture':True}))
        stack.enter_context(patch.object(m.core,'load_candidate',return_value=(self.candidate,self.review)))
        stack.enter_context(patch.object(m,'verify_dependencies'))
        stack.enter_context(patch.object(m.core,'checked_metadata'))
        return stack

    def actual_admission(self):
        value=deepcopy(self.admission);value['tools_canonical_sha256']=m.canonical({'fixture':True})
        return value

    def cleanup(self,owner_error=False):
        return {'entry_binding_after':self.before,'cleanup':{'residual_processes':[]},
            'observer_owner_terminal':{'original_post_wait':True},'observer':{'healthy':not owner_error},
            'final_errors':['original owner unhealthy'] if owner_error else []}


class AdmissionTests(Fixture):
    def test_describe_missing_admission_and_contract_are_inert(self):
        before=(m.core.ORIGINAL_ROOT,m.safety.original_safety.ROOT,m.core.policy.ROOT)
        with patch.object(m.safety,'tool_manifest',side_effect=AssertionError('No safety runtime for describe')), \
                patch.object(m.stable,'dependencies') as deps,patch.object(m,'write_new') as writes, \
                patch.object(m.subprocess,'Popen') as spawn,redirect_stdout(io.StringIO()) as output,redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['describe']),0)
            self.assertEqual(m.main(['plan']),2);self.assertEqual(m.main(['run']),2)
        value=json.loads(output.getvalue());self.assertFalse(value['actual_action_executed'])
        self.assertFalse(value['tool_manifest']['driver_acquires_machine_sitl_lock'])
        deps.assert_not_called();writes.assert_not_called();spawn.assert_not_called()
        self.assertEqual(before,(m.core.ORIGINAL_ROOT,m.safety.original_safety.ROOT,m.core.policy.ROOT))

    def test_full_explicit_admission_and_candidate_order_are_retained(self):
        binding=dump(self.temp/'development_extension_admission_fixture.json',self.actual_admission())
        with self.admission_mocks():
            admitted,candidate,review=m.load_admission(binding['path'],binding['sha256'])
        self.assertEqual(admitted['experiment']['classes'],['car','person'])
        self.assertEqual(admitted['_admission_binding'],binding)
        self.assertIs(candidate,self.candidate);self.assertIs(review,self.review)

    def test_pending_partial_recovery_old_registry_foreign_protocol_and_noninteger_refuse(self):
        base=self.actual_admission();variants=[]
        for key,value in [('status',m.PENDING),('automatic_retry',True),('zero_attempt_recovery',False),
                          ('prefix',self.candidate['prefix']),('prefix','reliability_v4_humble41_extensions_probe')]:
            changed=deepcopy(base);changed[key]=value;variants.append(changed)
        for key,value in [('seed',True),('seed',1000),('flight_count',True),('flight_count',1),
                          ('conditions',list(m.CONDITIONS)[:-1]),('classes',['car'])]:
            changed=deepcopy(base);changed['experiment'][key]=value;variants.append(changed)
        changed=deepcopy(base);changed['safety_registry']['path']='/historic/registry.json';variants.append(changed)
        changed=deepcopy(base);changed['extension_protocol']['path']='/foreign/protocol.json';variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed):
                binding=dump(self.temp/'development_extension_admission_fixture.json',changed)
                with self.admission_mocks():self.assertRaises(ValueError,m.load_admission,binding['path'],binding['sha256'])

    def test_actual_final_core_and_safety_tool_identities_required(self):
        core_manifest={'core':'actual'};safety_manifest={'safety':'actual'}
        admission=deepcopy(self.admission);candidate=deepcopy(self.candidate)
        admission['dependency_tools']={'core':m.canonical(core_manifest),'safety':m.canonical(safety_manifest)}
        candidate['tools_canonical_sha256']=admission['dependency_tools']['core']
        with patch.object(m.core,'tool_manifest',return_value=core_manifest),patch.object(m.safety,'tool_manifest',return_value=safety_manifest):
            m.verify_dependencies(admission,candidate)
            admission['dependency_tools']['safety']='0'*64
            self.assertRaises(ValueError,m.verify_dependencies,admission,candidate)
            admission['dependency_tools']['safety']=m.canonical(safety_manifest);candidate['tools_canonical_sha256']='0'*64
            self.assertRaises(ValueError,m.verify_dependencies,admission,candidate)

    def test_main_runs_actual_resource_preflight_and_caches_before_actions(self):
        resource={'actual_resource':'512'};runtime={'runtime_contracts':{'resource':resource}}
        def action(ctx,*args):
            self.assertIs(ctx.built['_resource_runtime_binding'],resource)
            self.assertIs(ctx.runtime,runtime);return 0
        with patch.object(m,'reviewed_admission',return_value=(self.admission,self.candidate,self.review)), \
                patch.object(m.generic,'require_linux'),patch.object(m.stable,'dependencies',return_value=self.ctx.modules), \
                patch.object(m.generic,'exclusive_window',return_value=nullcontext()), \
                patch.object(m.stable,'stop_signals',return_value=nullcontext()), \
                patch.object(m.stable,'checked_build',side_effect=lambda *args:{}), \
                patch.object(m.core,'require_runtime',return_value=runtime) as preflight, \
                patch.object(m.generic,'runner_at',return_value=self.runner), \
                patch.object(m,'plan_extension',side_effect=action) as plan,patch.object(m,'run_extension',side_effect=action) as run, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['plan']),0);self.assertEqual(m.main(['run']),0)
            self.assertEqual(plan.call_count,1);self.assertEqual(run.call_count,1)
            preflight.return_value={'runtime_contracts':{}}
            self.assertEqual(m.main(['plan']),2);self.assertEqual(plan.call_count,1)

    def test_actual_same_candidate_core12_and_safety4_apis_are_both_called(self):
        with patch.object(m.safety,'actual_core',return_value=(Path('/actual/core'),self.reference,self.core_result)) as core, \
                patch.object(m.safety,'require_completed_safety',return_value=self.safety_result) as safety:
            prerequisites,reference=m.require_prerequisites(self.ctx)
        self.assertEqual(prerequisites,self.prerequisites);self.assertIs(reference,self.reference)
        self.assertEqual(core.call_count,1)
        self.assertEqual(safety.call_args.kwargs,{'core_plan':self.reference,'core_plan_path':Path('/actual/core')})
        self.assertEqual(core.call_args.args[0].registry_sha256,self.admission['safety_registry']['sha256'])

    def test_partial_manual_historical_or_failed_prerequisites_refuse(self):
        core_variants=[{'result':'PASS'},dict(self.core_result,completed_count=11),
            dict(self.core_result,all_original_core_cells_pass=False),dict(self.core_result,completed_count=True)]
        for value in core_variants:
            with patch.object(m.safety,'actual_core',return_value=(Path('/actual/core'),self.reference,value)), \
                    patch.object(m.safety,'require_completed_safety') as safety:
                self.assertRaises(ValueError,m.require_prerequisites,self.ctx);safety.assert_not_called()
        for value in [{'all_four_original_pass':True},dict(self.safety_result,all_four_original_pass=False),
                       dict(self.safety_result,formal_seed_use_authorized=True),dict(self.safety_result,registry={'path':'/old','sha256':'a'*64})]:
            with patch.object(m.safety,'actual_core',return_value=(Path('/actual/core'),self.reference,self.core_result)), \
                    patch.object(m.safety,'require_completed_safety',return_value=value):
                self.assertRaises(ValueError,m.require_prerequisites,self.ctx)


class MatrixAndPlanningTests(Fixture):
    def test_complete16_keeps_registered512_resources_budgets_pacing_and_original_argv(self):
        before=deepcopy(self.plan)
        self.assertIs(m.validate_matrix(self.ctx,self.plan,self.reference),self.plan)
        self.assertEqual(self.plan,before);self.runner.validate_plan.assert_called_once_with(self.plan,None)
        self.assertEqual(len(self.plan['trials']),16)
        self.assertEqual(self.plan['trials'][0]['inference_image_size'],512)
        self.assertEqual(self.plan['trials'][8]['inference_threads'],2)

    def test_partial_reordered_formal_boolean_budget_resource_geometry_or_source_mutation_refuses(self):
        variants=[]
        for key,value in [('mode','FORMAL'),('selected_seeds',[1000]),('selected_seeds',[True]),
                          ('postprocessing_timeout_s',60.),('evaluation_timeout_s',60.),('protocol_sha256','f'*64),
                          ('selected_extension_conditions',list(m.CONDITIONS)[:-1])]:
            changed=deepcopy(self.plan);changed[key]=value;variants.append(changed)
        changed=deepcopy(self.plan);changed['trials'].pop();variants.append(changed)
        changed=deepcopy(self.plan);changed['trials'].reverse();variants.append(changed)
        for key,value in [('seed',True),('inference_image_size',640),('inference_threads',3),('desired_distance_m',1.),
                          (m.core.policy.PACING_FIELD,{'changed':True}),('wall_timeout_s',1200.)]:
            changed=deepcopy(self.plan);changed['trials'][0][key]=value;variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed):self.assertRaises(ValueError,m.validate_matrix,self.ctx,changed,self.reference)

    def test_plan_uses_normal_complete_make_extension_plan_and_emits_only_pending(self):
        selected=m.locations(self.ctx);selected['plan_driver'].parent.mkdir(parents=True)
        self.runner.make_extension_plan=Mock(return_value=self.plan);self.runner.persist_plan=Mock()
        self.runner.read_slots=lambda p:{t['id']:{'status':'PENDING'} for t in p['trials']}
        self.runner.run_plan=Mock()
        self.admission['_admission_binding']={'path':'/admission.json','sha256':'a'*64}
        initial={'plan':{'path':'/actual/plan.json','sha256':'b'*64}}
        with patch.object(m,'require_prerequisites',return_value=(self.prerequisites,self.reference)), \
                patch.object(m,'entry_binding',return_value=self.before),patch.object(m.core,'make_observer',return_value=Observer()), \
                patch.object(m,'finish_action',return_value=self.cleanup()), \
                patch.object(m.core,'pending_identity',return_value=initial), \
                patch.object(m.stable,'metadata_binding',return_value={'path':'/actual/terminal.json','sha256':'c'*64}), \
                patch.object(m,'EXTERNAL',self.temp),redirect_stdout(io.StringIO()):
            # Keep real locations and write_new entirely within the temporary root.
            self.assertEqual(m.plan_extension(self.ctx),0)
        self.runner.make_extension_plan.assert_called_once_with(Path(self.ctx.root),selected['output'],self.admission['prefix'],
            formal=False,seeds=[4],conditions=list(m.CONDITIONS),classes=['car','person'])
        self.runner.persist_plan.assert_called_once_with(self.plan);self.runner.run_plan.assert_not_called()
        pending=m.read_small(self.temp/f'development_extension_contract_{self.admission["prefix"]}_pending01.json')
        self.assertEqual(pending['status'],m.PENDING);self.assertFalse(pending['formal_seed_use_authorized'])

    def test_old_products_and_driver_refuse_before_owner_or_normal_plan(self):
        selected=m.locations(self.ctx);selected['output'].mkdir(parents=True)
        with patch.object(m.core,'make_observer') as observer,patch.object(m,'require_prerequisites') as prerequisites:
            self.assertRaises(ValueError,m.plan_extension,self.ctx)
        observer.assert_not_called();prerequisites.assert_not_called()

    def test_pending_contract_refuses_before_any_plan_or_prerequisite_read(self):
        binding=dump(self.temp/'development_extension_contract_fixture.json',{'schema_version':1,'scope':m.SCOPE,'status':m.PENDING})
        with patch.object(m,'EXTERNAL',self.temp),patch.object(m,'checked_plan') as plan,patch.object(m,'entry_binding') as entry:
            self.assertRaisesRegex(ValueError,'PENDING cannot execute',m.load_contract,self.ctx,binding['path'],binding['sha256'])
        plan.assert_not_called();entry.assert_not_called()

    def final_contract(self,terminal_mutation=None):
        self.admission['_admission_binding']={'path':'/actual/admission.json','sha256':'a'*64}
        selected=m.locations(self.ctx)
        dump(selected['plan'],self.plan)
        initial=m.core.pending_identity(self.plan)
        terminal={'schema_version':1,'scope':m.SCOPE,'action':'plan','returncode':0,'error':None,
            'initial_pending':initial,'prerequisites':self.prerequisites,'flights_started':0,
            'entry_binding_before':self.before,'entry_binding_after':self.before,
            'final_errors':[],'cleanup':{'residual_processes':[]},
            'observer_owner_terminal':Observer._finished,'observer':{'healthy':True},
            **{key:False for key in m.core.FALSE_FIELDS}}
        if terminal_mutation:terminal.update(terminal_mutation)
        terminal_binding=dump(selected['plan_driver']/'execution_terminal.json',terminal)
        value={'schema_version':1,'scope':m.SCOPE,'status':m.FINAL,
            'extension_admission':self.admission['_admission_binding'],'entry_binding':self.before,
            'experiment':m.experiment(self.candidate),'prerequisites':self.prerequisites,
            'plan_pending':initial,'plan_terminal':terminal_binding,**{key:False for key in m.core.FALSE_FIELDS}}
        return dump(self.temp/'development_extension_contract_fixture_final.json',value)

    def contract_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(m,'EXTERNAL',self.temp))
        stack.enter_context(patch.object(m,'entry_binding',return_value=self.before))
        stack.enter_context(patch.object(m,'require_prerequisites',return_value=(self.prerequisites,self.reference)))
        def owner(actual,directory,root):
            m.require(actual==Observer._finished and directory==m.locations(self.ctx)['plan_driver']/'observer_driver'
                and root==self.ctx.root,'Actual healthy original owner required')
            return {'healthy':True}
        stack.enter_context(patch.object(m.owner,'validate_observer_root',side_effect=owner))
        return stack

    def test_final_contract_rechecks_actual_plan_original_terminal_and_post_wait_owner(self):
        binding=self.final_contract()
        with self.contract_mocks():
            contract,plan=m.load_contract(self.ctx,binding['path'],binding['sha256'])
        self.assertEqual(contract['status'],m.FINAL);self.assertEqual(plan,self.plan)
        self.runner.verify_sources.assert_called_once_with(plan)

    def test_final_contract_cannot_admit_unhealthy_owner_source_drift_or_recovery(self):
        for mutation in [{'observer_owner_terminal':None},{'returncode':False},{'flights_started':True},
                {'entry_binding_after':{'changed':True}},{'cleanup':{'residual_processes':[{'pid':1}]}},
                {'automatic_retry':True}]:
            with self.subTest(mutation=mutation):
                binding=self.final_contract(mutation)
                with self.contract_mocks():self.assertRaises(ValueError,m.load_contract,self.ctx,binding['path'],binding['sha256'])

    def test_finish_uses_original_owner_and_cannot_promote_unhealthy_or_source_drift(self):
        for actual in (None,{'status':'COPY_PENDING_OWNER_CLOSURE'}):
            observer=SimpleNamespace(_finished=actual)
            with patch.object(m.core,'entry_binding',return_value=self.before['candidate_source_build']), \
                    patch.object(m,'entry_binding',return_value=self.before), \
                    patch.object(m.owner,'validate_observer_root',side_effect=ValueError('original owner unhealthy')) as owner:
                result=m.finish_action(self.ctx,observer,self.temp/'driver')
            owner.assert_called_once_with(actual,self.temp/'driver/observer_driver',self.ctx.root)
            self.assertTrue(result['final_errors']);self.assertIs(result['observer_owner_terminal'],actual)


class BatchTests(Fixture):
    def exercise(self,failure_at=None,algorithm_fail_at=None,owner_error=False):
        selected=m.locations(self.ctx);selected['output'].mkdir(parents=True)
        rows={t['id']:{'status':'PENDING'} for t in self.plan['trials']};calls=[];writes={}
        contract={'prerequisites':self.prerequisites,'plan_pending':{'plan':{'path':'/original/plan','sha256':'a'*64}}}
        def run(plan,*,max_new_trials,command_runner):
            self.assertEqual(max_new_trials,1);self.assertTrue(callable(command_runner))
            i=len(calls);calls.append(i)
            if failure_at==i:raise RuntimeError('infrastructure failure')
            result='FAIL' if algorithm_fail_at==i else 'PASS'
            rows[plan['trials'][i]['id']].update(status=result,engineering_result=result)
            return {'started_this_invocation':1}
        self.runner.read_slots=lambda p:deepcopy(rows);self.runner.run_plan=run
        self.runner.run_lock=Mock(side_effect=AssertionError('No outer SITL lock'))
        def written(path,value):
            self.assertNotIn(str(path),writes);writes[str(path)]=deepcopy(value)
        def audit(r,p,t,row,review,checks,*,extension=False):
            self.assertTrue(extension);return {'record_binding':self.checks.terminal_binding(r,p,t,row),'original_evaluations':True}
        with patch.object(m,'load_contract',return_value=(contract,self.plan)), \
                patch.object(m,'require_prerequisites',return_value=(self.prerequisites,self.reference)), \
                patch.object(m,'entry_binding',return_value=self.before),patch.object(m.core,'make_observer',return_value=Observer()), \
                patch.object(m,'finish_action',return_value=self.cleanup(owner_error)),patch.object(m,'sha',return_value='a'*64), \
                patch.object(m.stable,'metadata_binding',return_value={'path':'/original/plan','sha256':'a'*64}), \
                patch.object(m.core.original41,'require_same_metadata_file'),patch.object(m.core.original41,'audit_record',side_effect=audit), \
                patch.object(m,'write_new',side_effect=written),redirect_stdout(io.StringIO()):
            code=m.run_extension(self.ctx,Path('/contract'),'a'*64)
        self.runner.run_lock.assert_not_called()
        return code,calls,writes,writes[str(selected['run_driver']/'execution_terminal.json')]

    def test_algorithm_fail_retained_and_all16_original_slots_continue(self):
        code,calls,writes,terminal=self.exercise(algorithm_fail_at=6)
        self.assertEqual(code,0);self.assertEqual(len(calls),16)
        self.assertEqual(terminal['status_counts'],{'PASS':15,'FAIL':1})
        self.assertEqual(terminal['attempt_count'],16);self.assertEqual(terminal['slots'][6]['status'],'FAIL')
        self.assertFalse(terminal['readiness_claimed']);self.assertFalse(terminal['formal_seed_use_authorized'])
        self.assertEqual(sum(p.endswith('.started.json') for p in writes),16)
        self.assertEqual(sum(p.endswith('.attempt_terminal.json') for p in writes),16)

    def test_infrastructure_failure_stops_once_retaining_original_marker_and_attempt(self):
        code,calls,writes,terminal=self.exercise(failure_at=2)
        self.assertEqual(code,2);self.assertEqual(calls,[0,1,2])
        self.assertEqual(terminal['attempt_count'],3);self.assertEqual(terminal['terminal_count'],2)
        self.assertEqual(terminal['status_counts']['PENDING'],14)
        self.assertIn('infrastructure failure',terminal['attempts'][2]['error'])
        self.assertEqual(sum(p.endswith('.started.json') for p in writes),3)
        self.assertEqual(sum(p.endswith('.attempt_terminal.json') for p in writes),3)

    def test_unhealthy_original_owner_cannot_upgrade_completed16(self):
        code,calls,writes,terminal=self.exercise(owner_error=True)
        self.assertEqual(code,2);self.assertEqual(len(calls),16)
        self.assertEqual(terminal['status'],'STOPPED_ORIGINAL_ATTEMPTS_RETAINED')
        self.assertEqual(terminal['final_errors'],['original owner unhealthy'])

    def test_original_normal_runner_command_forwarded_unchanged_and_only_one_slot(self):
        command=['original_flight','--unchanged'];observer=Observer();log=Path('/log');root=Path('/root')
        def run(plan,*,max_new_trials,command_runner):
            self.assertEqual(max_new_trials,1);return command_runner(command,log,root,1800.)
        runner=SimpleNamespace(run_plan=run,run_lock=Mock(side_effect=AssertionError('No nested lock')))
        with patch.object(m.stable,'execute_owned',return_value={'returncode':0}) as execute:
            self.assertEqual(m.core.observed_run_plan(runner,{'original':True},observer),{'returncode':0})
        execute.assert_called_once_with(command,log,observer,1800.,root)
        self.assertEqual(command,['original_flight','--unchanged']);runner.run_lock.assert_not_called()


if __name__=='__main__':unittest.main()
