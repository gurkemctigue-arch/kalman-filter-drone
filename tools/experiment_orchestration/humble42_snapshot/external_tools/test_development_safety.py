"""Small synthetic metadata/error-injection tests; no ROS, WSL, bag or flight.

Dependency functions are scoped unittest mocks. No dependency root/policy globals
are reassigned and no historical result or tool is written.
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

import development_safety as m


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8')
    return m.binding(path)


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='development_safety_pure_')
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name).resolve()
        self.source = {'source': {'freeze_source_sha256': 'c'*64}, 'candidate_manifest': {'sha256': 'd'*64}}
        self.before = {**self.source, 'safety_tools_canonical_sha256': 'e'*64}
        candidate = {'frozen_root': str(self.temp/'candidate'), 'prefix': 'reliability_v4_fixture_probe01'}
        self.rows = {}
        self.runner = SimpleNamespace(read_slots=Mock(side_effect=lambda p: deepcopy(self.rows)),
            simulation_processes=Mock(return_value=[]), verify_sources=Mock(),
            flight_source_hashes=lambda v: deepcopy(v),
            infrastructure_evidence=Mock(return_value={'stop': False}), run_plan=Mock(side_effect=AssertionError('No normal run_plan for safety')))
        self.ctx = m.Context(candidate, {}, {}, self.runner, {'humble33_diagnostic_checks01': object()}, {},
            self.temp/'development_contract_core_fixture_final01.json', 'a'*64, 'e'*64)
        self.plan = {'plan_sha256': 'b'*64, 'trials': [], 'source_hashes': {'scripts/a.py': 'f'*64},
            'protocol': {'real_time_factor': .5, 'flight_wall_timeout_s': 1000.,
                'gazebo_render_driver': 'llvmpipe', 'magnetic_library_registration': 'config/magnetic.json',
                'resources': {cls: {'model': cls+'.pt', 'inference_image_size': 640,
                    'inference_threads': 4, 'desired_distance_m': 9. if cls=='car' else 5.} for cls in ('person','car')}}}
        selected = m.development.locations(candidate)
        attempts, slots = [], []
        self.original_owner = {'scope': 'FIXTURE_ONLY_ORIGINAL_OWNER', 'post_wait': True}
        for number in range(1, 13):
            identifier = f'original_slot_{number:02d}'
            self.plan['trials'].append({'id': identifier})
            record = {'status': 'PASS', 'engineering_result': 'PASS', 'record_sha256': str(number)*8}
            self.rows[identifier] = record
            audit = self.audit(self.runner, self.plan, {'id': identifier}, record, {}, object())
            marker = {'slot': identifier, 'number': number, 'entry_binding': self.source,
                'contract': {'path': str(self.ctx.core_contract), 'sha256': self.ctx.core_contract_sha256},
                'plan_sha256': self.plan['plan_sha256'], 'started_utc': '2026-01-01T00:00:00+00:00', 'original_attempt_number': 1}
            marker_path = selected['run_driver']/f'{number:02d}_{identifier}.started.json'
            dump(marker_path, marker)
            attempt = {'slot': identifier, 'number': number, 'error': None, 'audit': audit,
                'runner_result': {'started_this_invocation': 1}, 'started_utc': marker['started_utc'],
                'record': {'status': 'PASS', 'engineering_result': 'PASS', 'record_binding': audit['record_binding']},
                'started_marker': m.stable.metadata_binding(marker_path, json_only=True)}
            dump(selected['run_driver']/f'{number:02d}_{identifier}.attempt_terminal.json', attempt)
            attempts.append(attempt)
            slots.append({'slot': identifier, 'status': 'PASS', 'engineering_result': 'PASS', 'audit': audit})
        dump(self.ctx.core, self.plan)
        self.contract = {'plan_pending': {'actual_plan_fixture': 'immutable'}}
        self.terminal = {'schema_version': 1, 'scope': m.development.SCOPE, 'action': 'run-core', 'returncode': 0,
            'status': 'ORIGINAL_CORE_TERMINALS_COMPLETE', 'error': None, 'slot_read_error': None,
            'planned_count': 12, 'attempt_count': 12, 'terminal_count': 12, 'entry_binding_before': self.source,
            'entry_binding_after': self.source, 'final_errors': [], 'cleanup': {'residual_processes': []},
            'contract': {'path': str(self.ctx.core_contract), 'sha256': self.ctx.core_contract_sha256},
            'plan': self.contract['plan_pending'], 'slots': slots, 'attempts': attempts,
            'actual_slot_statuses': {key: {'status': v['status'], 'record_sha256': v['record_sha256']} for key,v in self.rows.items()},
            'status_counts': {'PASS': 12}, 'observer_owner_terminal': self.original_owner, 'observer': {'healthy': True},
            **{key: False for key in m.development.FALSE_FIELDS}}
        self.terminal_path = selected['run_driver']/'execution_terminal.json'
        dump(self.terminal_path, self.terminal)

    @staticmethod
    def audit(runner, plan, trial, record, review, checks):
        return {'record_binding': {'path': trial['id']+'.json', 'sha256': record['record_sha256']}}

    def core_mocks(self):
        stack = ExitStack()
        stack.enter_context(patch.object(m.development, 'load_contract', return_value=(self.contract, self.plan)))
        stack.enter_context(patch.object(m.development, 'entry_binding', return_value=self.source))
        stack.enter_context(patch.object(m.development, 'pending_identity', return_value={'actual_plan': True}))
        stack.enter_context(patch.object(m.development.original41, 'audit_record', side_effect=self.audit))
        def owner(actual, directory, root):
            m.require(actual == self.original_owner and directory == m.development.locations(self.ctx.candidate)['run_driver']/'observer_driver'
                and root == self.ctx.candidate['frozen_root'], 'Original healthy post-wait owner required')
            return {'healthy': True}
        stack.enter_context(patch.object(m.owner, 'validate_observer_root', side_effect=owner))
        return stack

    def definitions(self):
        flags = lambda ctx,runner,protocol,cls: (['--px4-adapter-publish-rate-hz','50.0'], cls=='car', cls=='car', 50., cls=='car')
        with patch.object(m.development,'validate_matrix'), patch.object(m,'policy_flags',side_effect=flags):
            return m.safety_definitions(self.ctx,self.runner,self.plan)

    def registry_mocks(self, complete=None):
        stack = ExitStack()
        stack.enter_context(patch.object(m,'actual_core',return_value=(self.ctx.core,self.plan,complete or {'completed_count':12,'all_original_core_cells_pass':True})))
        stack.enter_context(patch.object(m,'entry_binding',return_value=self.before))
        stack.enter_context(patch.object(m,'safety_definitions',return_value=self.definitions()))
        stack.enter_context(patch.object(m,'verify_tail',return_value={'execution_card':m.binding(m.CARD),'tail_script':m.binding(m.TAIL)}))
        return stack


class AdmissionTests(Fixture):
    def test_describe_and_missing_admission_are_inert_and_globals_unchanged(self):
        old = (m.original_safety.ROOT,m.original_safety.AUDIT,m.original_safety.CORE,m.development.ORIGINAL_ROOT)
        with patch.object(m.stable,'dependencies') as deps, patch.object(m,'write_new') as writes, \
                patch.object(m.subprocess,'Popen') as spawned, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['describe']),0)
            for action in ('register','run'):
                self.assertEqual(m.main([action]),2)
        deps.assert_not_called(); writes.assert_not_called(); spawned.assert_not_called()
        self.assertEqual(old,(m.original_safety.ROOT,m.original_safety.AUDIT,m.original_safety.CORE,m.development.ORIGINAL_ROOT))

    def test_explicit_candidate_and_core_contract_and_separate_registry_are_required(self):
        argv=['run','--manifest','missing.json','--manifest-sha256','a'*64,
            '--reviewed-tools-sha256',m.canonical(m.tool_manifest())]
        with patch.object(m.development,'load_candidate') as load:
            self.assertRaises(ValueError,m.reviewed_candidate,m.parser().parse_args(argv))
            self.assertRaises(ValueError,m.reviewed_candidate,m.parser().parse_args(argv+['--core-contract','x.json','--core-contract-sha256','b'*64]))
        load.assert_not_called()

    def test_main_caches_actual_runtime_resource_before_either_action_and_rejects_missing_resource(self):
        resource={'registration':{'revision':'fixture-only512'},'evidence_bindings':[{'fixture':'not-admission'}]}
        runtime={'runtime_contracts':{'resource':resource}}
        def action(ctx,*args):
            self.assertIs(ctx.built['_resource_runtime_binding'],resource)
            self.assertIs(ctx.runtime,runtime)
            return 0
        with patch.object(m,'reviewed_candidate',return_value=(self.ctx.candidate,{})), \
                patch.object(m.generic,'require_linux'),patch.object(m.stable,'dependencies',return_value=self.ctx.modules), \
                patch.object(m.generic,'exclusive_window',return_value=nullcontext()), \
                patch.object(m.stable,'stop_signals',return_value=nullcontext()), \
                patch.object(m.stable,'checked_build',side_effect=lambda *args:{}), \
                patch.object(m.development,'require_runtime',return_value=runtime) as preflight, \
                patch.object(m.generic,'runner_at',return_value=self.runner), \
                patch.object(m,'register_safety',side_effect=action) as register, \
                patch.object(m,'run_safety',side_effect=action) as run,redirect_stderr(io.StringIO()):
            for mode in ('register','run'):
                self.assertEqual(m.main([mode,'--core-contract',str(self.ctx.core_contract)]),0)
            self.assertEqual(register.call_count,1); self.assertEqual(run.call_count,1)
            preflight.return_value={'runtime_contracts':{}}
            self.assertEqual(m.main(['register']),2)
            self.assertEqual(register.call_count,1)

    def test_core_rechecks_all_twelve_original_attempts_and_actual_owner(self):
        with self.core_mocks():
            path,plan,complete=m.actual_core(self.ctx,{}, {},self.runner)
        self.assertEqual(path,self.ctx.core); self.assertEqual(plan,self.plan)
        self.assertTrue(complete['all_original_core_cells_pass'])
        self.assertEqual(len(complete['original_terminals']),12)
        self.runner.verify_sources.assert_called_once_with(self.plan)

    def test_partial_manual_old_scope_source_contract_and_owner_defects_refuse(self):
        variants=[]
        for key,value in [('terminal_count',11),('scope',m.original_safety.SCOPE),
                ('entry_binding_after',{'manual':'PASS'}),('observer_owner_terminal',None),
                ('contract',{'path':'/old/contract.json','sha256':'a'*64}),('automatic_retry',True),
                ('status_counts',{'PASS':11,'FAIL':1})]:
            value2=deepcopy(self.terminal); value2[key]=value; variants.append(value2)
        variants.append({'result':'PASS','completed_count':12,'all_original_core_cells_pass':True})
        for changed in variants:
            with self.subTest(changed=changed):
                dump(self.terminal_path,changed)
                with self.core_mocks(): self.assertRaises(ValueError,m.actual_core,self.ctx,{}, {},self.runner)

    def test_old_eleven_pass_one_fail_is_never_admitted(self):
        self.rows['original_slot_12'].update(status='FAIL',engineering_result='FAIL')
        with self.core_mocks():
            self.assertRaisesRegex(ValueError,'All12 actual',m.actual_core,self.ctx,{}, {},self.runner)

    def test_mutated_attempt_or_marker_and_residual_refuse(self):
        attempt=m.development.locations(self.ctx.candidate)['run_driver']/'01_original_slot_01.attempt_terminal.json'
        original=m.read_small(attempt); dump(attempt,{'manual':'PASS'})
        with self.core_mocks(): self.assertRaisesRegex(ValueError,'per-attempt',m.actual_core,self.ctx,{}, {},self.runner)
        dump(attempt,original)
        marker=m.development.locations(self.ctx.candidate)['run_driver']/'01_original_slot_01.started.json'
        original=m.read_small(marker); changed=deepcopy(original); changed['original_attempt_number']=2; dump(marker,changed)
        with self.core_mocks(): self.assertRaisesRegex(ValueError,'started marker',m.actual_core,self.ctx,{}, {},self.runner)
        dump(marker,original); self.runner.simulation_processes.return_value=[{'pid':123}]
        with self.core_mocks(): self.assertRaisesRegex(ValueError,'residual',m.actual_core,self.ctx,{}, {},self.runner)


class RegistryAndExecutionTests(Fixture):
    def register(self):
        with self.registry_mocks(),patch.object(m,'execute') as execute,redirect_stdout(io.StringIO()):
            self.assertEqual(m.register_safety(self.ctx,{}, {},self.runner),0)
            execute.assert_not_called()
        return m.read_small(self.ctx.audit/'registry.json')

    def test_four_original_modes_and_all_five_argv_hashes_are_registered(self):
        trials=self.definitions()
        self.assertEqual([t['id'] for t in trials],['person_auto_unique_multi_seed004','person_locked_ambiguity_seed004','car_auto_unique_multi_seed004','car_locked_ambiguity_seed004'])
        for trial in trials:
            automatic=trial['case']=='auto_unique_multi'
            self.assertEqual(trial['settings']['duration'],35. if automatic else 50.)
            self.assertEqual(trial['settings']['initial_min_candidates'],2 if automatic else 3)
            self.assertEqual(trial['settings']['target_mode'],'auto_unique' if automatic else 'locked_target')
            self.assertEqual(set(trial['execution_commands']),m.EXECUTIONS)
            self.assertEqual(trial['execution_command_sha256'],{k:m.canonical(v) for k,v in trial['execution_commands'].items()})
            self.assertEqual(trial['execution_commands']['terminal_speed'][-3:],[str(m.TAIL),trial['directory'],str(m.CARD)])
            self.assertEqual(trial['flight_command'].count('--px4-adapter-publish-rate-hz'),1)
            self.assertNotIn('--occlusions',trial['flight_command']); self.assertNotIn('--reselect-after-loss',trial['flight_command'])
            self.assertTrue(trial['directory'].startswith(str(self.ctx.root)))
        registry=self.register()
        self.assertEqual(registry['trials'],trials)
        self.assertFalse(registry['formal_seeds_consumed'])

    def test_register_and_run_both_gate_actual_core_and_registry_is_independently_reviewed(self):
        with patch.object(m,'actual_core',side_effect=ValueError('actual core failed')),patch.object(m,'write_new') as writes:
            self.assertRaisesRegex(ValueError,'actual core',m.register_safety,self.ctx,{}, {},self.runner)
            self.assertRaisesRegex(ValueError,'actual core',m.checked_registry,self.ctx,{}, {},self.runner,expected_sha='b'*64)
        writes.assert_not_called()
        self.register(); path=self.ctx.audit/'registry.json'; digest=m.sha(path)
        with self.registry_mocks():
            self.assertRaises(ValueError,m.checked_registry,self.ctx,{}, {},self.runner)
            self.assertRaises(ValueError,m.checked_registry,self.ctx,{}, {},self.runner,expected_sha='0'*64)
            m.checked_registry(self.ctx,{}, {},self.runner,expected_sha=digest)
        changed=m.read_small(path); changed['trials'][0]['flight_argv'].append('--changed'); dump(path,changed)
        with self.registry_mocks():
            self.assertRaisesRegex(ValueError,'Prospective',m.checked_registry,self.ctx,{}, {},self.runner,expected_sha=m.sha(path))

    def test_original_tail_bytes_and_explicit_candidate_root_are_used(self):
        guard=SimpleNamespace(verified_safety_card=Mock())
        actual=m.verify_tail(self.ctx,guard)
        self.assertEqual(actual['tail_script']['sha256'],m.ORIGINAL_TAIL_SHA)
        self.assertEqual(actual['execution_card']['sha256'],m.ORIGINAL_CARD_SHA)
        guard.verified_safety_card.assert_called_once_with(actual,self.ctx.root)

    def receipt(self,command,name,observer,timeout,code=0):
        log=self.ctx.audit/(name+'.log'); log.write_text('synthetic only\n',encoding='utf-8')
        actual={'command':command,'started_utc':'2026-01-01T00:00:00+00:00','finished_utc':'2026-01-01T00:00:01+00:00',
            'returncode':code,'error':None,'outer_cleanup_actions':[],'log':str(log)}
        path=self.ctx.audit/(name+'.outer_execution.json')
        return {**dump(path,actual),'execution':actual}

    def test_original_algorithm_exit_two_is_allowed_only_for_algorithm_evaluation(self):
        self.ctx.audit.mkdir(parents=True)
        receipt=self.receipt(['synthetic'],'synthetic',None,1800.,2)
        self.assertRaises(ValueError,m.original_execution,receipt,['synthetic'])
        self.assertEqual(m.original_execution(receipt,['synthetic'],algorithm_exit=True)['returncode'],2)

    def run_fixture(self,flight_code,algorithm_fail):
        registry=self.register()
        observer=SimpleNamespace(_finished=self.original_owner,check=Mock(return_value={'fresh':True}))
        class Owner:
            _finished=observer._finished
            check=observer.check
            def __enter__(self): return self
            def __exit__(self,*args): return False
        cleanup={'entry_binding_after':self.before,'cleanup':{'residual_processes':[]},
            'observer_owner_terminal':self.original_owner,'observer':{'healthy':True},'final_errors':[]}
        def execute(ctx,command,name,obs,timeout):
            trial=next(t for t in registry['trials'] if name.startswith(t['id']+'_'))
            kind=name[len(trial['id'])+1:]
            directory=Path(trial['directory'])
            if kind=='flight':
                for key,relative in m.EVIDENCE.items():
                    if key not in ('source_clock','native_startup','terminal_speed'): dump(directory/relative,{})
            else:
                dump(directory/m.report_names(trial)[kind],{})
            return self.receipt(command,name,obs,timeout,flight_code if kind=='flight' else (2 if algorithm_fail and kind=='specialized' else 0))
        with patch.object(m,'entry_binding',return_value=self.before),patch.object(m.owner,'make_observer',return_value=Owner()), \
                patch.object(m,'execute',side_effect=execute),patch.object(m,'finish_action',return_value=cleanup), \
                patch.object(m,'safety_runtime',return_value={}),patch.object(m,'safety_report_audit',return_value={'status':'FAIL' if algorithm_fail else 'PASS'}), \
                redirect_stdout(io.StringIO()):
            code=m.run_safety_locked(self.ctx,{}, {},self.runner,self.ctx.modules,self.plan,registry,self.before)
        return code,m.read_small(self.ctx.audit/'execution_terminal.json'),m.read_small(self.ctx.audit/'slots_facts.json')

    def test_infrastructure_exit_stops_after_one_retaining_pending_three(self):
        code,terminal,facts=self.run_fixture(2,False)
        self.assertEqual(code,2); self.assertEqual(terminal['attempted_count'],1); self.assertEqual(terminal['pending_count'],3)
        self.assertTrue(terminal['slots'][0]['infrastructure_stop']); self.assertEqual(facts['result'],'FAIL')
        self.assertEqual(set(facts['slots'][0]['executions']),{'flight'})
        self.runner.run_plan.assert_not_called()

    def test_complete_algorithm_fail_retains_four_five_execution_twelve_evidence(self):
        code,terminal,facts=self.run_fixture(0,True)
        self.assertEqual(code,0); self.assertEqual(terminal['attempted_count'],4); self.assertEqual(terminal['pending_count'],0)
        self.assertEqual(facts['result'],'FAIL')
        for slot in facts['slots']:
            self.assertEqual(set(slot['executions']),m.EXECUTIONS)
            self.assertEqual(set(slot['evidence']),set(m.EVIDENCE)|{'specialized'})
            self.assertEqual(slot['original_status'],'FAIL'); self.assertFalse(slot['infrastructure_stop'])
        self.assertFalse((self.ctx.audit/'development_guard_validation.json').exists())
        self.runner.run_plan.assert_not_called()


if __name__=='__main__':
    unittest.main()
