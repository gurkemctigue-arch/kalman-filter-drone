"""No-flight/error-injection controls for the parameterized development driver."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import development_runner as d


def candidate():
    root = '/root/uav_tracking_fullplan_v4_candidate_test'
    digest = 'a'*64
    label = 'v4_candidate_test'
    return {'schema_version': 1, 'scope': d.SCOPE, 'status': d.CANDIDATE,
        'frozen_root': root, 'prefix': 'reliability_v4_candidate_test_probe01',
        'experiment': d.experiment(), 'authorized_actions': ['plan-core', 'run-core'],
        'source_review': {'path': '/external/reviewed_freeze_review_test.json', 'sha256': digest},
        'protocol': {'path': root+'/'+d.policy.PROTOCOL_PATH, 'sha256': digest},
        'tools_canonical_sha256': digest,
        'original41_closure': {'path': d.generic.LINUX_EXTERNAL+'/'+d.ORIGINAL_CLOSURE,
                               'sha256': d.ORIGINAL_CLOSURE_SHA},
        'pressure_reuse': {'scope': d.INFRA_SCOPE,
            'implementation_hashes': {p: digest for p in d.INFRA_FILES},
            'original_execution_terminal': {'path': '/original/pressure.json', 'sha256': digest}},
        'build_evidence': {'summary': {'path': root+'/results/freeze_validation/build_validation_summary.json', 'sha256': digest},
            **{action+'_terminal': {'path': d.generic.LINUX_EXTERNAL+f'/reviewed_freeze_actions_{label}/{action}/action.terminal.json',
                                   'sha256': digest} for action in ('build', 'validate')}},
        '_manifest_binding': {'path': '/external/development_candidate_test.json', 'sha256': digest},
        **{name: False for name in d.FALSE_FIELDS}}


def plan_fixture(c):
    classes, groups = d.matrix_order(c)
    protocol = {'duration_s': 75., 'flight_wall_timeout_s': 1000., 'seeds': list(range(1000, 1010)),
        d.policy.PACING_FIELD: deepcopy(d.policy.EXPECTED_PACING_V2),
        'resources': {'person': {'model': 'person.pt', 'inference_threads': 2, 'inference_image_size': 320, 'desired_distance_m': 5.},
            'car': {'model': 'car.pt', 'inference_threads': 3, 'inference_image_size': 640, 'desired_distance_m': 9.,
                    d.policy.EXCLUSIVE_FIELD: True}}}
    trials = []
    for cls in classes:
        for group in groups:
            identifier = f'{cls}_{group}_seed004'
            trial = {'id': identifier, 'target_class': cls, 'group': group, 'seed': 4,
                'duration_s': 75., 'wall_timeout_s': 1000., **protocol['resources'][cls],
                d.policy.PACING_FIELD: deepcopy(d.policy.EXPECTED_PACING_V2), d.policy.ADAPTER_FIELD: 50.,
                'flight_command': ['original', identifier, d.policy.ADAPTER_FLAG, '50.0'],
                'directory': '/uncreated/synthetic/'+identifier, 'evaluations': []}
            if cls == 'car': trial['flight_command'].append(d.policy.EXCLUSIVE_FLAG)
            trials.append(trial)
    return {'mode': 'PROBE', 'prefix': c['prefix'], 'frozen_root': c['frozen_root'],
        'output': str(d.locations(c)['output']), 'selected_classes': classes,
        'selected_groups': groups, 'selected_seeds': [4], 'protocol': protocol,
        'protocol_sha256': c['protocol']['sha256'], 'trials': trials, 'trial_timeout_s': 2800.,
        'postprocessing_timeout_s': 1800., 'evaluation_timeout_s': 1800., 'plan_sha256': 'synthetic'}


def runner_fixture():
    return SimpleNamespace(validate_plan=Mock(), simulation_pacing_declared=Mock(return_value=True),
        exclusive_navigation_declared=Mock(return_value=True),
        exclusive_navigation_summary=Mock(return_value={'car': True, 'person': False}),
        simulation_pacing_trial_binding=lambda p,t: p['protocol'][d.policy.PACING_FIELD],
        correlated_two_face_trial_binding=lambda p,t: (t['target_class']=='car',)*2,
        car_surface_recovery_trial_binding=lambda p,t: (t['target_class']=='car',)*2,
        exclusive_navigation_trial_binding=lambda p,t: (t['target_class']=='car',)*2)


class AdmissionTests(unittest.TestCase):
    def test_candidate_is_explicit_complete_and_parameterized(self):
        c = candidate()
        self.assertIs(d.validate_candidate(c), c)
        self.assertEqual(d.locations(c)['plan'].name, 'plan.json')
        self.assertNotEqual(c['frozen_root'], d.ORIGINAL_ROOT)

    def test_candidate_rejects_pending_partial_boolean_formal_recovery_and_old_root(self):
        variants = []
        for key, value in (('status', d.PENDING), ('frozen_root', d.ORIGINAL_ROOT),
                           ('prefix', d.original41.PREFIXES['core']), ('automatic_retry', True),
                           ('zero_attempt_recovery', False), ('readiness_claimed', True)):
            c = candidate(); c[key] = value; variants.append(c)
        for key,value in (('seed', True), ('seed', 1000), ('flight_count', 1), ('groups', ['stage1_velocity'])):
            c = candidate(); c['experiment'][key] = value; variants.append(c)
        c=candidate(); c['pressure_reuse']['scope']='same-source'; variants.append(c)
        c=candidate(); c['original41_closure']['sha256']='b'*64; variants.append(c)
        c=candidate(); c['build_evidence']['summary']['path']='/old/summary.json'; variants.append(c)
        for c in variants:
            with self.subTest(c=c): self.assertRaises(ValueError, d.validate_candidate, c)

    def test_missing_admission_and_noncore_actions_refuse_before_writes_or_runtime(self):
        with patch.object(d, 'write_new') as written, patch.object(d.stable, 'dependencies') as deps, \
             patch.object(d.subprocess, 'Popen') as spawned, redirect_stderr(io.StringIO()):
            for action in ('plan-core', 'run-core', 'plan-extension', 'run-extension', 'plan-safety', 'run-safety'):
                self.assertEqual(d.main([action]), 2)
        written.assert_not_called(); deps.assert_not_called(); spawned.assert_not_called()

    def test_describe_is_inert_and_keeps_dependency_globals(self):
        before = (d.original41.ROOT, d.policy.ROOT, d.stable.PREFIX)
        with patch.object(d, 'write_new') as written, patch.object(d.stable, 'dependencies') as deps, \
             patch.object(d.subprocess, 'run') as executed, patch.object(d.subprocess, 'Popen') as spawned, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(d.main(['describe']), 0)
        result=json.loads(output.getvalue())
        self.assertFalse(result['actual_action_executed'])
        self.assertFalse(result['tool_manifest']['driver_acquires_machine_sitl_lock'])
        self.assertFalse(result['tool_manifest']['extension_actions_executable'])
        self.assertEqual(before, (d.original41.ROOT, d.policy.ROOT, d.stable.PREFIX))
        written.assert_not_called(); deps.assert_not_called(); executed.assert_not_called(); spawned.assert_not_called()

    def test_manifest_sha_mismatch_refuses_before_source_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'development_candidate_test.json'
            p.write_text(json.dumps(candidate()),encoding='utf-8')
            with patch.object(d,'EXTERNAL',Path(temporary)), patch.object(d.generic,'load_review') as load:
                self.assertRaisesRegex(ValueError,'SHA mismatch',d.load_candidate,p,'b'*64)
            load.assert_not_called()

    def test_pending_runtime_contract_cannot_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'development_contract_core_test.json'
            p.write_text(json.dumps({'schema_version':1,'scope':d.SCOPE,'status':d.PENDING}),encoding='utf-8')
            with patch.object(d,'EXTERNAL',Path(temporary)), patch.object(d,'checked_plan') as plan, \
                 patch.object(d,'entry_binding') as binding:
                self.assertRaisesRegex(ValueError,'PENDING cannot run',d.load_contract,
                    candidate(),{},{},None,p,d.sha(p))
            plan.assert_not_called(); binding.assert_not_called()


class MatrixTests(unittest.TestCase):
    def test_explicit_complete_candidate_order_is_passed_without_changing_specs(self):
        c=candidate()
        c['core_classes']=['car','person']
        c['core_groups']=['stage3_multi_active','stage2_crossing','stage1_velocity',
                          'stage1_position','stage3_midpoint','stage3_active']
        c['experiment']=d.experiment(c)
        d.validate_candidate(c)
        p=plan_fixture(c)
        with patch.object(d,'read_small',return_value=p['protocol']):
            self.assertIs(d.validate_matrix(c,p,runner_fixture()),p)
        self.assertEqual(p['trials'][0]['id'],'car_stage3_multi_active_seed004')
        self.assertEqual(len(p['trials']),12)
        for field in ('core_classes','core_groups'):
            changed=deepcopy(c);changed[field]=changed[field][:-1]
            self.assertRaises(ValueError,d.validate_candidate,changed)

    def test_all12_exact_argv_and_actual_protocol_resources_are_preserved(self):
        c=candidate(); p=plan_fixture(c); before=deepcopy(p)
        with patch.object(d,'read_small',return_value=p['protocol']):
            self.assertIs(d.validate_matrix(c,p,runner_fixture()),p)
        self.assertEqual(p,before)
        self.assertEqual(p['trials'][6]['inference_threads'],3)

    def test_partial_reordered_boolean_formal_foreign_or_argv_mutation_rejected(self):
        c=candidate(); base=plan_fixture(c)
        variants=[]
        for key,value in (('selected_seeds',[True]),('selected_seeds',[1000]),('mode','FORMAL'),
                           ('frozen_root',d.ORIGINAL_ROOT),('evaluation_timeout_s',60.),('protocol_sha256','b'*64)):
            p=deepcopy(base);p[key]=value;variants.append(p)
        p=deepcopy(base);p['trials'].pop();variants.append(p)
        p=deepcopy(base);p['trials'].reverse();variants.append(p)
        p=deepcopy(base);p['trials'][0]['seed']=True;variants.append(p)
        p=deepcopy(base);p['trials'][6]['inference_threads']=4;variants.append(p)
        p=deepcopy(base);p['trials'][0]['flight_command']+=['--px4-adapter-publish-rate-hz=50'];variants.append(p)
        for p in variants:
            with patch.object(d,'read_small',return_value=base['protocol']):
                self.assertRaises(ValueError,d.validate_matrix,c,p,runner_fixture())

    def test_old_products_pending_subset_and_prior_attempt_are_rejected(self):
        c=candidate();p=plan_fixture(c)
        rows={t['id']:{'status':'PENDING'} for t in p['trials']}
        d.require_fresh_rows(p,rows)
        missing=dict(rows);missing.pop(next(iter(missing)))
        self.assertRaises(ValueError,d.require_fresh_rows,p,missing)
        attempted=deepcopy(rows);attempted[next(iter(attempted))]['status']='FAIL'
        self.assertRaises(ValueError,d.require_fresh_rows,p,attempted)
        with tempfile.TemporaryDirectory() as temporary:
            p['trials'][0]['directory']=temporary
            self.assertRaisesRegex(ValueError,'Old trial products',d.require_fresh_rows,p,rows)

    def test_normal_runner_owns_lock_and_original_command_is_forwarded_unchanged(self):
        original=['flight','--original']; log=Path('/log'); root=Path('/root'); observer=object()
        def run(plan,*,max_new_trials,command_runner):
            self.assertEqual(max_new_trials,1)
            return command_runner(original,log,root,1800.)
        runner=SimpleNamespace(run_plan=run,run_lock=Mock(side_effect=AssertionError('No nested lock')))
        with patch.object(d.stable,'execute_owned',return_value={'returncode':0}) as execute:
            self.assertEqual(d.observed_run_plan(runner,{'original':True},observer),{'returncode':0})
        execute.assert_called_once_with(original,log,observer,1800.,root)
        self.assertEqual(original,['flight','--original']);runner.run_lock.assert_not_called()

    def test_owner_creation_uses_parameterized_root_and_original_limits(self):
        c=candidate()
        with patch.object(d.owner,'make_observer',return_value='actual_owner') as make:
            self.assertEqual(d.make_observer(c,Path('/driver')),'actual_owner')
        make.assert_called_once_with(Path('/driver/observer_driver'),c['frozen_root'],archive_wall_budget_s=1800.)

    def test_unhealthy_or_missing_original_owner_cannot_close(self):
        for actual in (None,{'status':'COPY_VERIFIED_PENDING_OWNER_CLOSURE','healthy_cleanup':False}):
            observer=SimpleNamespace(_finished=actual)
            with patch.object(d,'entry_binding',return_value={'original':True}), \
                 patch.object(d.owner,'validate_observer_root',side_effect=ValueError('Original owner unhealthy')) as check:
                result=d.finish_action(candidate(),{},{},SimpleNamespace(simulation_processes=lambda:[]),observer,Path('/driver'))
            check.assert_called_once_with(actual,Path('/driver/observer_driver'),candidate()['frozen_root'])
            self.assertTrue(result['final_errors']);self.assertIs(result['observer_owner_terminal'],actual)


class PlanningTests(unittest.TestCase):
    def test_actual_plan_order_passes_normal_make_plan_and_only_pending_is_emitted(self):
        with tempfile.TemporaryDirectory(prefix='development_plan_no_flight_') as temporary:
            base=Path(temporary);c=candidate()
            c['core_classes']=['car','person'];c['core_groups']=list(reversed(d.GROUPS));c['experiment']=d.experiment(c)
            selected={'output':base/'matrix','plan':base/'matrix/plan.json','run_driver':base/'matrix/driver',
                      'plan_driver':base/'plan_driver','pending_contract':base/'pending.json'}
            p=plan_fixture(c);p['output']=str(selected['output'])
            binding={'actual_source':True};initial={'plan':{'path':'actual_plan','sha256':'a'*64}}
            writes={}
            class Observer:
                _finished={'actual_post_wait':True}
                def __enter__(self): return self
                def __exit__(self,*args): return False
                def check(self): return {'fresh':True}
            runner=SimpleNamespace(simulation_processes=lambda:[],make_plan=Mock(return_value=p),persist_plan=Mock(),
                read_slots=lambda p:{t['id']:{'status':'PENDING'} for t in p['trials']},run_plan=Mock())
            cleanup={'entry_binding_after':binding,'cleanup':{'residual_processes':[]},
                     'observer_owner_terminal':{'actual_post_wait':True},'observer':{'verified':True},'final_errors':[]}
            def written(path,value): writes[str(path)]=deepcopy(value)
            with patch.object(d,'locations',return_value=selected),patch.object(d,'entry_binding',return_value=binding), \
                 patch.object(d,'make_observer',return_value=Observer()),patch.object(d,'validate_matrix'), \
                 patch.object(d,'pending_identity',return_value=initial),patch.object(d,'finish_action',return_value=cleanup), \
                 patch.object(d,'write_new',side_effect=written),patch.object(d,'sha',return_value='a'*64), \
                 patch.object(d.stable,'metadata_binding',return_value={'path':'actual_terminal','sha256':'a'*64}), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(d.plan_core(c,{},{},runner,{}),0)
            runner.make_plan.assert_called_once_with(Path(c['frozen_root']),selected['output'],c['prefix'],
                formal=False,seeds=[4],groups=c['core_groups'],classes=c['core_classes'])
            runner.run_plan.assert_not_called()
            value=writes[str(selected['pending_contract'])]
            self.assertEqual(value['status'],d.PENDING)
            self.assertNotEqual(value['status'],d.FINAL)
            self.assertEqual(writes[str(selected['plan_driver']/'execution_terminal.json')]['flights_started'],0)

    def test_old_plan_or_missing_prerequisite_refuses_before_driver_creation(self):
        with tempfile.TemporaryDirectory(prefix='development_plan_gate_') as temporary:
            base=Path(temporary);selected={'output':base/'matrix','plan':base/'matrix/plan.json',
                'run_driver':base/'matrix/driver','plan_driver':base/'plan_driver','pending_contract':base/'pending.json'}
            runner=SimpleNamespace(simulation_processes=lambda:[],make_plan=Mock())
            with patch.object(d,'locations',return_value=selected), \
                 patch.object(d,'entry_binding',side_effect=ValueError('Actual pressure missing')),patch.object(d,'write_new') as written:
                self.assertRaisesRegex(ValueError,'pressure missing',d.plan_core,candidate(),{},{},runner,{})
            self.assertFalse(selected['plan_driver'].exists());runner.make_plan.assert_not_called();written.assert_not_called()
            selected['output'].mkdir()
            with patch.object(d,'locations',return_value=selected),patch.object(d,'entry_binding') as binding:
                self.assertRaisesRegex(ValueError,'Fresh plan',d.plan_core,candidate(),{},{},runner,{})
            binding.assert_not_called()


class SupplementBuildTests(unittest.TestCase):
    def exercise(self, mutation=None):
        c=candidate();review={'_review_binding':c['source_review']}
        tools={'files':{'development_freeze_build.py':'b'*64}}
        resource_tools={'files':{'development_resource_guard.py':'c'*64}}
        supplement={'actual_independently_reviewed512_driver':True}
        c['development_build_driver_tools_canonical_sha256']=d.canonical(tools)
        terminal=lambda action:{'action':action,'status':'PASS','binding_before':{
            'review':review['_review_binding'],'development_resource_override':supplement},
            'binding_after':{'review':review['_review_binding'],'development_resource_override':supplement}}
        documents={c['build_evidence'][action+'_terminal']['path']:terminal(action) for action in ('build','validate')}
        preflights={}
        for action in ('build','validate'):
            directory=Path(c['build_evidence'][action+'_terminal']['path']).parent
            before=documents[c['build_evidence'][action+'_terminal']['path']]['binding_before']
            preflight={'schema_version':1,'action_binding':before,'runtime':{'resource':{
                'registration':{'revision':d.resources.REVISION,
                    'receipt':dict(d.development_build.RECEIPT),'scope':d.resources.SCOPE},
                'receipt':{'path':str(Path(c['frozen_root'])/d.resources.RECEIPT_PATH),'sha256':d.resources.RECEIPT_SHA},
                'inference_image_size':512,'inference_threads':4,'model_sha256':d.resources.MODEL_SHA,
                'scope':d.resources.SCOPE,'closed_loop_validated':False,'formal_seed_use_authorized':False,
                'evidence_bindings':[{'path':'/actual/measurement','sha256':'a'*64,'limit':1000}]}}}
            preflights[action]=preflight
            documents[str(directory/'runtime_preflight.json')]=preflight
            for phase in (('action','post_build') if action == 'build' else ('action',)):
                documents[str(directory/f'runtime_preflight_{phase}_closure.json')]={'schema_version':1,
                    'action_binding':before,'before_sha256':'d'*64,'after_sha256':'d'*64,
                    'strict512_resource_verified':True,'evidence_files_unchanged':True}
        manifest={'development_resource_override':supplement,'final_review':review['_review_binding']}
        if mutation == 'candidate':c.pop('development_build_driver_tools_canonical_sha256')
        if mutation == 'terminal':documents[c['build_evidence']['build_terminal']['path']]['binding_before'].pop('development_resource_override')
        if mutation == 'freeze':manifest.pop('development_resource_override')
        if mutation == 'empty_runtime':preflights['build']['runtime']={}
        if mutation == 'legacy640':preflights['build']['runtime']['resource']['inference_image_size']=640
        if mutation == 'empty_evidence':preflights['validate']['runtime']['resource']['evidence_bindings']=[]
        if mutation == 'preflight_binding':preflights['validate']['action_binding']={'foreign_action':True}
        build_directory=Path(c['build_evidence']['build_terminal']['path']).parent
        if mutation == 'missing_closure':documents.pop(str(build_directory/'runtime_preflight_action_closure.json'))
        if mutation == 'missing_post_closure':documents.pop(str(build_directory/'runtime_preflight_post_build_closure.json'))
        if mutation == 'hash_drift':documents[str(build_directory/'runtime_preflight_action_closure.json')]['after_sha256']='e'*64
        if mutation == 'post_hash_drift':documents[str(build_directory/'runtime_preflight_post_build_closure.json')]['before_sha256']='e'*64
        if mutation == 'unverified_closure':documents[str(build_directory/'runtime_preflight_action_closure.json')]['strict512_resource_verified']=False
        def read(path):return documents.get(str(path),manifest)
        with patch.object(d.development_build,'supplement_binding',return_value=supplement), \
             patch.object(d.development_build,'tool_manifest',return_value=tools), \
             patch.object(d.resources,'tool_manifest',return_value=resource_tools), \
             patch.object(d.resources,'verify_runtime_evidence',side_effect=lambda value:value) as verified, \
             patch.object(d,'checked_archived_source',side_effect=lambda value:value) as archived, \
             patch.object(d,'checked_metadata') as checked,patch.object(d,'read_small',side_effect=read), \
             patch.object(d.stable,'metadata_binding',side_effect=lambda path,**kwargs:{'path':str(path),'sha256':'d'*64}):
            if mutation:self.assertRaises(ValueError,d.require_supplement_build,c,review)
            else:
                result=d.require_supplement_build(c,review)
                self.assertEqual(result['supplement'],supplement)
                self.assertEqual(len(result['actual_action_terminals']),2)
                self.assertEqual(checked.call_count,7)
                self.assertEqual(archived.call_count,2)
                self.assertEqual(result['archived_driver_and_guard_files'],{**tools['files'],**resource_tools['files']})
                self.assertEqual(verified.call_count,2)
                self.assertEqual(set(result['actual_runtime_preflight_evidence']),{'build','validate'})
                self.assertEqual(set(result['actual_runtime_preflight_evidence']['build']['closures']),{'action','post_build'})

    def test_new_driver_actual_build_validate_freeze_and_archived_tools_are_bound(self):self.exercise()
    def test_legacy_summary_without_actual_new_driver_binding_cannot_admit512(self):
        for mutation in ('candidate','terminal','freeze'):
            with self.subTest(mutation=mutation):self.exercise(mutation)

    def test_actual_preflight_and_both_build_phases_must_be_complete512_and_immutable(self):
        for mutation in ('empty_runtime','legacy640','empty_evidence','preflight_binding','missing_closure',
                         'missing_post_closure','hash_drift','post_hash_drift','unverified_closure'):
            with self.subTest(mutation=mutation):self.exercise(mutation)


class RealArchivedSourceTests(unittest.TestCase):
    """Real JSON and .py/.sh leaves: metadata APIs are deliberately not mocked."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='development_actual_archive_')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.archived=self.root/'results/freeze_validation/external_wrappers'
        self.archived.mkdir(parents=True)
        self.review={'_review_binding':{'path':'/actual/review.json','sha256':'a'*64}}
        self.supplement={'fixture_only_reviewed512':True}
        self.tools={'files':{}}
        self.resource_tools={'files':{}}
        for name,content,manifest in (
                ('actual_driver.py',b'print("fixture source only")\n',self.tools),
                ('actual_launch.sh',b'#!/bin/sh\nexit 0\n',self.tools),
                ('actual_guard.py',b'# fixture guard source only\n',self.resource_tools)):
            path=self.archived/name;path.write_bytes(content);manifest['files'][name]=d.sha(path)
        self.candidate={'frozen_root':str(self.root),
            'development_build_driver_tools_canonical_sha256':d.canonical(self.tools),'build_evidence':{}}
        before={'review':self.review['_review_binding'],'development_resource_override':self.supplement}
        def dump(path,value):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value)+'\n',encoding='utf-8')
            return d.stable.metadata_binding(path,json_only=True)
        for action in ('build','validate'):
            directory=self.root/'actual_actions'/action
            self.candidate['build_evidence'][action+'_terminal']=dump(directory/'action.terminal.json',
                {'action':action,'status':'PASS','binding_before':before,'binding_after':before})
            preflight=dump(directory/'runtime_preflight.json',
                {'schema_version':1,'action_binding':before,'runtime':{'fixture_strict512':'separate resource branch'}})
            for phase in (('action','post_build') if action=='build' else ('action',)):
                dump(directory/f'runtime_preflight_{phase}_closure.json',
                    {'schema_version':1,'action_binding':before,'before_sha256':preflight['sha256'],
                     'after_sha256':preflight['sha256'],'strict512_resource_verified':True,'evidence_files_unchanged':True})
        dump(self.root/'results/freeze_validation/source_freeze_manifest.json',
            {'development_resource_override':self.supplement,'final_review':self.review['_review_binding']})

    def exercise(self):
        with patch.object(d.development_build,'supplement_binding',return_value=self.supplement), \
                patch.object(d.development_build,'tool_manifest',return_value=self.tools), \
                patch.object(d.resources,'tool_manifest',return_value=self.resource_tools), \
                patch.object(d.development_build,'verify_512_runtime') as verify:
            result=d.require_supplement_build(self.candidate,self.review)
        self.assertEqual(verify.call_count,2)
        return result

    def test_actual_py_sh_and_json_archives_pass_without_metadata_api_bypass(self):
        result=self.exercise()
        self.assertEqual(result['archived_driver_and_guard_files'],{**self.tools['files'],**self.resource_tools['files']})
        self.assertEqual(set(result['actual_runtime_preflight_evidence']),{'build','validate'})

    def test_missing_changed_or_nonregular_py_or_sh_leaf_refuses(self):
        for name in ('actual_driver.py','actual_launch.sh'):
            path=self.archived/name;original=path.read_bytes()
            for mutation in ('missing','changed','directory'):
                if mutation=='missing':path.unlink()
                elif mutation=='changed':path.write_bytes(original+b'# changed\n')
                else:path.unlink();path.mkdir()
                with self.subTest(name=name,mutation=mutation):self.assertRaises(ValueError,self.exercise)
                if path.is_dir():path.rmdir()
                path.write_bytes(original)

    def test_source_leaf_symlink_refuses_even_when_target_bytes_match(self):
        path=self.archived/'actual_driver.py';original=path.read_bytes();target=self.root/'same_bytes.py'
        target.write_bytes(original);path.unlink()
        try:path.symlink_to(target)
        except OSError as error:
            path.write_bytes(original)
            self.skipTest('Host cannot create a file symlink: '+str(error))
        self.assertRaises(ValueError,self.exercise)

    def test_oversized_and_non_source_leaf_refuse(self):
        path=self.archived/'actual_driver.py';original=path.read_bytes()
        with path.open('wb') as stream:stream.truncate(d.generic.MAX_SMALL+1)
        self.tools['files']['actual_driver.py']=d.sha(path)
        self.candidate['development_build_driver_tools_canonical_sha256']=d.canonical(self.tools)
        self.assertRaises(ValueError,self.exercise)
        path.write_bytes(original);self.tools['files'].pop('actual_driver.py')
        wrong=self.archived/'actual_driver.txt';wrong.write_bytes(original)
        self.tools['files'][wrong.name]=d.sha(wrong)
        self.candidate['development_build_driver_tools_canonical_sha256']=d.canonical(self.tools)
        self.assertRaises(ValueError,self.exercise)


class BatchTests(unittest.TestCase):
    def exercise(self, failure_at=None, algorithm_fail_at=None, owner_failure=False):
        with tempfile.TemporaryDirectory(prefix='development_no_flight_') as temporary:
            base=Path(temporary);c=candidate();p=plan_fixture(c)
            selected={'output':base/'matrix','plan':base/'matrix/plan.json','run_driver':base/'matrix/driver',
                      'plan_driver':base/'plan_driver','pending_contract':base/'pending.json'}
            selected['output'].mkdir()
            rows={t['id']:{'status':'PENDING'} for t in p['trials']}; calls=[]; writes={}
            contract={'plan_pending':{'plan':{'path':'/original/plan','sha256':'a'*64}}}
            binding={'actual_source_and_tools':True}
            class Observer:
                _finished={'actual_post_wait':True}
                def __enter__(self): return self
                def __exit__(self,*args): return False
                def check(self): return {'fresh':True}
            def run(plan,*,max_new_trials,command_runner):
                i=len(calls);calls.append(i)
                row=rows[p['trials'][i]['id']]
                if failure_at == i: raise RuntimeError('infrastructure failure')
                row.update(status='FAIL' if algorithm_fail_at == i else 'PASS',engineering_result='FAIL' if algorithm_fail_at == i else 'PASS')
                return {'started_this_invocation':1}
            runner=SimpleNamespace(read_slots=lambda plan:deepcopy(rows),simulation_processes=lambda:[],verify_sources=Mock(),run_plan=run,
                                   run_lock=Mock(side_effect=AssertionError('No nested SITL lock')))
            checks=SimpleNamespace(terminal_binding=lambda r,p,t,row:{'slot':t['id'],'status':row['status']})
            cleanup={'entry_binding_after':binding,'cleanup':{'residual_processes':[]},
                     'observer_owner_terminal':{'actual_post_wait':True},'observer':{'verified':not owner_failure},
                     'final_errors':['owner failed'] if owner_failure else []}
            def written(path,value):
                self.assertNotIn(str(path),writes);writes[str(path)]=deepcopy(value)
            def audit(r,plan,t,row,review,actual_checks):
                return {'record_binding':checks.terminal_binding(r,plan,t,row),'original_evaluations':True,'cleanup':True}
            with patch.object(d,'load_contract',return_value=(contract,p)),patch.object(d,'locations',return_value=selected), \
                 patch.object(d,'entry_binding',return_value=binding),patch.object(d,'make_observer',return_value=Observer()), \
                 patch.object(d,'finish_action',return_value=cleanup),patch.object(d,'sha',return_value='a'*64), \
                 patch.object(d.stable,'metadata_binding',return_value={'path':'/original/plan','sha256':'a'*64}), \
                 patch.object(d.original41,'require_same_metadata_file'),patch.object(d.original41,'audit_record',side_effect=audit), \
                 patch.object(d,'write_new',side_effect=written),redirect_stdout(io.StringIO()):
                code=d.run_core(c,{},{},runner,{'humble33_diagnostic_checks01':checks},{},Path('/contract'),'a'*64)
            runner.run_lock.assert_not_called()
            terminal=writes[str(selected['run_driver']/'execution_terminal.json')]
            return code,calls,writes,terminal

    def test_algorithm_fail_retained_and_complete12_original_slots_continue(self):
        code,calls,writes,terminal=self.exercise(algorithm_fail_at=6)
        self.assertEqual(code,0);self.assertEqual(len(calls),12)
        self.assertEqual(terminal['status_counts'],{'PASS':11,'FAIL':1})
        self.assertEqual(terminal['slots'][6]['status'],'FAIL')
        self.assertEqual(terminal['attempt_count'],12)
        self.assertFalse(terminal['readiness_claimed'])
        self.assertEqual(sum(k.endswith('.started.json') for k in writes),12)
        self.assertEqual(sum(k.endswith('.attempt_terminal.json') for k in writes),12)

    def test_infrastructure_error_stops_without_retry_and_retains_attempt(self):
        code,calls,writes,terminal=self.exercise(failure_at=2)
        self.assertEqual(code,2);self.assertEqual(calls,[0,1,2])
        self.assertEqual(terminal['attempt_count'],3);self.assertEqual(terminal['terminal_count'],2)
        self.assertIn('infrastructure failure',terminal['attempts'][2]['error'])
        self.assertEqual(terminal['status_counts']['PENDING'],10)
        self.assertEqual(sum(k.endswith('.attempt_terminal.json') for k in writes),3)

    def test_owner_failure_does_not_upgrade_completed_results(self):
        code,calls,writes,terminal=self.exercise(owner_failure=True)
        self.assertEqual(code,2);self.assertEqual(len(calls),12)
        self.assertEqual(terminal['status'],'STOPPED_ORIGINAL_ATTEMPTS_RETAINED')
        self.assertEqual(terminal['final_errors'],['owner failed'])


if __name__ == '__main__':
    unittest.main()
