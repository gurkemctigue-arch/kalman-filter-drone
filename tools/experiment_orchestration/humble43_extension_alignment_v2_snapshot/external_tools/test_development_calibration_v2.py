"""Small synthetic gates/command failure fixtures. No bag, inference or flight.

All runtime substitutes are scoped unittest mocks; original policy/source/tools
and historical evidence are never edited. Synthetic owners cannot authorize a
real admission. These tests create only small temporary files.
"""
from contextlib import ExitStack, nullcontext, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import os
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import development_calibration_v2 as m


def dump(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8')
    return m.file_binding(path)


class Observer:
    _finished = {'original_post_wait': True}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def check(self): return {'fresh': True}


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='calibration_small_fixture_')
        self.addCleanup(temporary.cleanup); self.temp = Path(temporary.name).resolve()
        self.root = self.temp/'candidate'; (self.root/'results').mkdir(parents=True)
        self.candidate = {'frozen_root': str(self.root), 'prefix': 'reliability_v4_fixture_core'}
        self.runner = SimpleNamespace(read_slots=Mock(side_effect=lambda p: deepcopy(self.rows)),
            simulation_processes=Mock(return_value=[]), verify_sources=Mock(),
            run_lock=Mock(side_effect=lambda output: nullcontext()),
            record_path=lambda plan, trial: self.root/'records'/(trial['id']+'.json'))
        self.checks = SimpleNamespace(terminal_binding=lambda r,p,t,row: {'slot':t['id'],'record':row['record_sha256']})
        self.ext_admission = {'prefix': 'reliability_v4_fixture_extension',
            'core_contract': {'path': str(self.temp/'core.json'), 'sha256': 'b'*64},
            'safety_registry': {'path': str(self.temp/'registry.json'), 'sha256': 'c'*64},
            'dependency_tools': {'core':'d'*64,'safety':'e'*64}}
        self.ext = m.extension.Context(self.ext_admission, self.candidate, {'files':{}}, {}, self.runner,
            {'humble33_diagnostic_checks01': self.checks}, {'runtime_contracts':{'resource':{'actual':'512'}}})
        self.admission = {'prefix': 'reliability_v4_fixture_metadata',
            '_admission_binding': {'path': str(self.temp/'admission.json'), 'sha256':'a'*64},
            'extension_contract': {'path': str(self.temp/'extension_contract.json'), 'sha256':'f'*64},
            'storage': {'scope':m.CAPACITY_SCOPE,'temporary_directory':str(Path(tempfile.gettempdir()).resolve()),
                'physical_backing_root':str(self.temp),'output_volume_root':str(self.root),
                'minimum_reserve_bytes':m.MIN_RESERVE,'output_budget_bytes':1024**3}}
        self.ctx = m.Context(self.admission, self.ext)
        self.before = {'extension_source_build':{'fixture':'same_source'},'calibration':'actual_admission'}
        self.ext_before = {'fixture':'same_source'}
        self.prerequisites = {'core':{'all_original_core_cells_pass':True,'completed_count':12},
            'safety':{'all_four_original_pass':True}}
        self.reference = {'mode':'PROBE','selected_seeds':[4],'selected_classes':list(m.core.CLASSES),
            'selected_groups':list(m.core.GROUPS),'trials':[],'source_hashes':{},'plan_sha256':'1'*64}
        self.plan = {'trials':[], 'plan_sha256':'2'*64, 'source_hashes':{}}
        self.rows, attempts, slots = {}, [], []
        self.original_owner = {'fixture_original_post_wait':True}
        selected = m.extension.locations(self.ext)
        for number in range(1,17):
            identifier = 'extension_slot_'+str(number)
            trial = {'id':identifier}; self.plan['trials'].append(trial)
            row = {'status':'PASS','engineering_result':'PASS','record_sha256':str(number)*4}
            self.rows[identifier] = row
            audit = self.audit(self.runner,self.plan,trial,row,None,None,extension=True)
            marker = {'slot':identifier,'number':number,'entry_binding':self.ext_before,
                'contract':self.admission['extension_contract'],'plan_sha256':self.plan['plan_sha256'],
                'started_utc':'2026-01-01T00:00:00+00:00','original_attempt_number':1}
            marker_binding = dump(selected['run_driver']/f'{number:02d}_{identifier}.started.json',marker)
            attempt = {'slot':identifier,'number':number,'audit':audit,'error':None,
                'runner_result':{'started_this_invocation':1},'started_utc':marker['started_utc'],
                'record':{'status':'PASS','engineering_result':'PASS','record_binding':audit['record_binding']},
                'started_marker':marker_binding}
            dump(selected['run_driver']/f'{number:02d}_{identifier}.attempt_terminal.json',attempt)
            attempts.append(attempt);slots.append({'slot':identifier,'status':'PASS','engineering_result':'PASS','audit':audit})
        dump(selected['plan'],self.plan)
        self.extension_contract = {'prerequisites':self.prerequisites,'plan_pending':{'original_pending':'identity'}}
        self.terminal = {'schema_version':1,'scope':m.extension.SCOPE,'action':'run','returncode':0,
            'status':'ORIGINAL_EXTENSION16_TERMINALS_COMPLETE','error':None,'slot_read_error':None,
            'planned_count':16,'attempt_count':16,'terminal_count':16,
            'entry_binding_before':self.ext_before,'entry_binding_after':self.ext_before,
            'final_errors':[],'cleanup':{'residual_processes':[]},'contract':self.admission['extension_contract'],
            'plan':self.extension_contract['plan_pending'],'prerequisites':self.prerequisites,
            'slots':slots,'attempts':attempts,'observer_owner_terminal':self.original_owner,'observer':{'healthy':True},
            'actual_slot_statuses':{key:{'status':row['status'],'record_sha256':row['record_sha256']} for key,row in self.rows.items()},
            'status_counts':{'PASS':16},**{name:False for name in m.core.FALSE_FIELDS}}
        self.terminal_path = selected['run_driver']/'execution_terminal.json'; dump(self.terminal_path,self.terminal)
        self.facts = {'prerequisites':self.prerequisites,'core_plan':{'path':str(self.temp/'plan.json'),'sha256':'9'*64,'plan_sha256':'1'*64},
            'selected_recordings':{cls:{'trial':{'directory':str(self.root/'results'/cls),'name':cls,'id':cls+'_stage1_velocity_seed004'},
                'raw_sqlite_bytes':30,'compressed_sqlite_bytes':10} for cls in m.CLASSES},
            'offline_sources':{},'storage_policy':self.admission['storage']}
        self.facts['commands'] = m.commands(self.ctx,self.facts['selected_recordings'],Path(self.facts['core_plan']['path']))
        self.contract = {'facts':self.facts}

    @staticmethod
    def audit(runner,plan,trial,row,*args,**kwargs):
        return {'record_binding':{'path':trial['id']+'.json','sha256':row['record_sha256']},'known_algorithm_failures':deepcopy(row.get('known_algorithm_failures', []))}

    def extension_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(m.extension,'load_contract',return_value=(self.extension_contract,self.plan)))
        stack.enter_context(patch.object(m.extension,'require_prerequisites',return_value=(self.prerequisites,self.reference)))
        stack.enter_context(patch.object(m.extension,'entry_binding',return_value=self.ext_before))
        stack.enter_context(patch.object(m.core.original41,'audit_record',side_effect=self.audit))
        def owner(actual,directory,root):
            m.require(actual==self.original_owner and directory==m.extension.locations(self.ext)['run_driver']/'observer_driver'
                and root==self.ext.root,'Original owner differs')
            return {'healthy':True}
        stack.enter_context(patch.object(m.owner,'validate_observer_root',side_effect=owner))
        return stack

    def cleanup(self,bad=False):
        return {'entry_binding_after':self.before,'cleanup':{'residual_processes':[]},
            'observer_owner_terminal':self.original_owner,'observer':{'healthy':not bad},
            'final_errors':['owner failure'] if bad else []}

    def run_mocks(self,failed=None,bad_owner=False):
        stack=ExitStack()
        stack.enter_context(patch.object(m,'load_contract',return_value=self.contract))
        stack.enter_context(patch.object(m,'entry_binding',return_value=self.before))
        stack.enter_context(patch.object(m,'planning_facts',return_value=self.facts))
        stack.enter_context(patch.object(m,'require_inputs_unchanged'))
        stack.enter_context(patch.object(m,'require_capacity',return_value={'capacity':'actual'}))
        stack.enter_context(patch.object(m,'frozen_algorithms',return_value=('replay','calibration')))
        stack.enter_context(patch.object(m.owner,'make_observer',return_value=Observer()))
        stack.enter_context(patch.object(m,'finish_action',return_value=self.cleanup(bad_owner)))
        stack.enter_context(patch.object(m,'validate_export',side_effect=lambda ctx,cls,*args:{'arrays':{'class':cls}}))
        stack.enter_context(patch.object(m,'validate_candidate',return_value={'path':'candidate.json','sha256':'a'*64}))
        def execute(command,log,observer,timeout,root):
            self.assertEqual(timeout,1800.);self.assertEqual(root,self.root)
            Path(log).write_text('fixture only\n',encoding='utf-8')
            return {'command':command,'returncode':2 if failed and failed in str(log) else 0,
                'error':None,'outer_cleanup_actions':[],'timeout_wall_s':timeout}
        self.execute=stack.enter_context(patch.object(m.stable,'execute_owned',side_effect=execute))
        return stack


class GateTests(Fixture):
    def test_describe_and_missing_admission_inert(self):
        with (patch.object(m,'tool_manifest',return_value={'scope':'PURE_SMALL_DESCRIBE_FIXTURE'}),
                patch.object(m,'load_admission',side_effect=AssertionError('not describe')),redirect_stdout(io.StringIO())):
            self.assertEqual(m.main(['describe']),0)
        with patch.object(m,'run_calibration') as run,redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['run']),2);run.assert_not_called()

    def test_exact_original_three_argv_no_formal_flags(self):
        rows=self.facts['commands'];output=m.locations(self.ctx)['output']
        self.assertEqual([row['id'] for row in rows],['person_export','car_export','calibration'])
        self.assertEqual(rows[0]['command'],[m.generic.PYTHON,'-B',str(self.root/m.SCRIPTS[0]),
            str(self.root/'results/person'),'--output',str(output/'person_export')])
        self.assertEqual(rows[2]['command'],[m.generic.PYTHON,'-B',str(self.root/m.SCRIPTS[1]),
            '--plan',str(self.temp/'plan.json'),'--person-arrays',str(output/'person_export/arrays.json'),
            '--car-arrays',str(output/'car_export/arrays.json'),'--output',str(output/'calibration_candidate.json')])
        for row in rows:
            self.assertEqual(row['timeout_wall_s'],1800.);self.assertEqual(row['argv_sha256'],m.canonical(row['command']))
            self.assertNotIn('--registration',row['command']);self.assertNotIn('--slot-id',row['command'])

    def test_original_all16_and_prerequisites_are_revalidated(self):
        with self.extension_mocks():
            result,reference=m.require_completed_extension(self.ctx)
        self.assertEqual(result['extension']['completed_count'],16);self.assertEqual(reference,self.reference)
        self.runner.verify_sources.assert_called_once_with(self.plan)

    def test_partial_failed_manual_historical_or_changed_source_extension_refuses(self):
        changes=[('terminal_count',15),('returncode',False),('scope','historical'),('observer_owner_terminal',None),
            ('prerequisites',{'manual_summary':'PASS'}),('cleanup',{'residual_processes':['px4']}),
            ('entry_binding_after',{'different':'source'}),('slots',self.terminal['slots'][:-1])]
        for key,value in changes:
            with self.subTest(key=key),self.extension_mocks():
                changed=deepcopy(self.terminal);changed[key]=value;dump(self.terminal_path,changed)
                with self.assertRaises((ValueError,RuntimeError)):m.require_completed_extension(self.ctx)
        dump(self.terminal_path,self.terminal)
        self.rows['extension_slot_1']['status']='FAIL'
        with self.extension_mocks(),self.assertRaises((ValueError,RuntimeError)):m.require_completed_extension(self.ctx)

    def test_marker_attempt_and_algorithm_audit_changes_refuse(self):
        selected=m.extension.locations(self.ext)
        marker=selected['run_driver']/'01_extension_slot_1.started.json';original=marker.read_bytes()
        marker.write_text('{}\n',encoding='utf-8')
        with self.extension_mocks(),self.assertRaises((ValueError,RuntimeError)):m.require_completed_extension(self.ctx)
        marker.write_bytes(original)
        path=selected['run_driver']/'01_extension_slot_1.attempt_terminal.json';original=path.read_bytes()
        path.write_text('{}\n',encoding='utf-8')
        with self.extension_mocks(),self.assertRaises((ValueError,RuntimeError)):m.require_completed_extension(self.ctx)
        path.write_bytes(original)
        with self.extension_mocks(),patch.object(m.core.original41,'audit_record',return_value={
            'known_algorithm_failures':['distance_error'],'record_binding':{}}),self.assertRaises((ValueError,RuntimeError)):
            m.require_completed_extension(self.ctx)

    def test_pending_contract_refuses_before_any_fact_read(self):
        binding=dump(self.temp/'development_calibration_v2_contract_fixture_pending01.json',
            {'schema_version':1,'scope':m.SCOPE,'status':m.PENDING})
        with (patch.object(m,'EXTERNAL',self.temp),patch.object(m,'planning_facts') as facts,
                self.assertRaises((ValueError,RuntimeError))):
            m.load_contract(self.ctx,binding['path'],binding['sha256'])
        facts.assert_not_called()

    def test_bounded_sources_are_not_json_metadata_and_symlinks_refuse(self):
        source=self.temp/'small.py';source.write_text('x=1\n',encoding='utf-8')
        self.assertEqual(m.file_binding(source)['sha256'],m.sha(source))
        with self.assertRaises((ValueError,RuntimeError)):m.file_binding(source,limit=2)
        link=self.temp/'link.py'
        try:link.symlink_to(source)
        except OSError:return
        with self.assertRaises((ValueError,RuntimeError)):m.file_binding(link)

    def test_array_nonfinite_and_mutation_refuse(self):
        path=self.temp/'arrays.json';path.write_text('{"value":NaN}\n',encoding='utf-8')
        with self.assertRaises(ValueError):m.read_array(path)

    @unittest.skipUnless(os.name == 'posix', 'Requires canonical POSIX storage paths; mandatory in Humble Linux validation')
    def test_single_export_three_routes_and_original_bound(self):
        source={'raw_sqlite_bytes':100,'compressed_sqlite_bytes':40}
        with patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)):
            result=m.require_capacity(self.ctx,source)
        self.assertEqual(result['single_export_required_bytes'],3*100+2*40+m.MIN_RESERVE)
        self.assertFalse(result['formal280_capacity_admission'])
        for free in (0,m.MIN_RESERVE-1):
            with patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=free)),self.assertRaises((ValueError,RuntimeError)):
                m.require_capacity(self.ctx,source)
        changed=deepcopy(self.admission['storage']);changed['minimum_reserve_bytes']=0
        with self.assertRaises((ValueError,RuntimeError)):m.validate_storage(changed)


class ExecutionTests(Fixture):
    def test_original_three_commands_once_single_outer_lock_and_owner(self):
        binding=dump(self.temp/'contract.json',{'fixture':'final'})
        with self.run_mocks(),redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_calibration(self.ctx,binding['path'],binding['sha256']),0)
        self.assertEqual(self.execute.call_count,3);self.runner.run_lock.assert_called_once_with(m.locations(self.ctx)['output'])
        terminal=m.read_small(m.locations(self.ctx)['output']/'execution_terminal.json')
        self.assertEqual(terminal['attempt_count'],3);self.assertEqual(terminal['unattempted_commands'],[])
        self.assertEqual(terminal['observer_owner_terminal'],self.original_owner)
        self.assertTrue(all(terminal[name] is False for name in m.core.FALSE_FIELDS))

    def test_failed_first_export_stops_once_retains_original_evidence_and_pending_two(self):
        binding=dump(self.temp/'contract.json',{'fixture':'final'})
        with self.run_mocks(failed='person_export'),redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_calibration(self.ctx,binding['path'],binding['sha256']),2)
        self.assertEqual(self.execute.call_count,1)
        output=m.locations(self.ctx)['output'];terminal=m.read_small(output/'execution_terminal.json')
        self.assertEqual(terminal['attempt_count'],1);self.assertEqual(len(terminal['unattempted_commands']),2)
        self.assertTrue((output/'01_person_export.started.json').is_file())
        self.assertTrue((output/'01_person_export.attempt_terminal.json').is_file())
        self.assertTrue((output/'person_export.log').is_file());self.assertIsNone(terminal['candidate'])
        with self.run_mocks(),self.assertRaises((ValueError,RuntimeError)):
            m.run_calibration(self.ctx,binding['path'],binding['sha256'])

    def test_unhealthy_original_owner_cannot_promote_complete_commands(self):
        binding=dump(self.temp/'contract.json',{'fixture':'final'})
        with self.run_mocks(bad_owner=True),redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_calibration(self.ctx,binding['path'],binding['sha256']),2)
        self.assertEqual(self.execute.call_count,3)
        terminal=m.read_small(m.locations(self.ctx)['output']/'execution_terminal.json')
        self.assertEqual(terminal['status'],'STOPPED_ORIGINAL_ATTEMPTS_RETAINED')

    def test_insufficient_capacity_stops_before_output_observer_or_subprocess(self):
        with (self.run_mocks(),patch.object(m,'require_capacity',side_effect=ValueError('insufficient')),
                self.assertRaises(ValueError)):m.run_calibration(self.ctx,'contract.json','a'*64)
        self.execute.assert_not_called();self.assertFalse(m.locations(self.ctx)['output'].exists())

    def test_source_change_after_command_stops_before_next(self):
        binding=dump(self.temp/'contract.json',{'fixture':'final'})
        calls=0
        def binding_check(ctx):
            nonlocal calls
            calls+=1
            return self.before if calls<3 else {'source':'changed'}
        with self.run_mocks(),patch.object(m,'entry_binding',side_effect=binding_check),redirect_stdout(io.StringIO()):
            self.assertEqual(m.run_calibration(self.ctx,binding['path'],binding['sha256']),2)
        self.assertEqual(self.execute.call_count,1)

    def test_main_caches_actual_resource_before_action(self):
        runtime={'runtime_contracts':{'resource':{'actual':'512'}}};built={}
        def action(ctx):
            self.assertEqual(ctx.extension_context.built['_resource_runtime_binding'],runtime['runtime_contracts']['resource'])
            return 0
        with (patch.object(m,'reviewed_admission',return_value=(self.admission,self.ext_admission,self.candidate,{})),
                patch.object(m.generic,'require_linux'),patch.object(m.stable,'dependencies',return_value={'humble33_diagnostic_checks01':object()}),
                patch.object(m.generic,'exclusive_window',return_value=nullcontext()),patch.object(m.stable,'stop_signals',return_value=nullcontext()),
                patch.object(m.stable,'checked_build',return_value=built),patch.object(m.core,'require_runtime',return_value=runtime),
                patch.object(m.generic,'runner_at',return_value=self.runner),patch.object(m,'plan_calibration',side_effect=action)):
            self.assertEqual(m.main(['plan']),0)


class MetadataAndArtifactTests(Fixture):
    def selected_fixture(self):
        plan=deepcopy(self.reference);rows={}
        self.ext.review['files']['fixture_source.py']='a'*64
        for cls in m.CLASSES:
            name='fixture_'+cls;directory=self.root/'results'/name
            trial={'id':cls+'_stage1_velocity_seed004','name':name,'directory':str(directory),
                'target_class':cls,'seed':4,'group':'stage1_velocity','stage':1,'command_mode':'velocity',
                'multi_target':False,'duration_s':75.}
            plan['trials'].append(trial)
            files={
                'run_config.json':{'target_class':cls,'seed':4,'stage':1,'command_mode':'velocity','multi_target':False,'no_bag':False,'duration':75.},
                'bag_integrity.json':{'status':'PASS','policy':'ext4_sqlite_close_standard_zstd_verified_native_read',
                    'raw_validation':{'status':'PASS','files':[{'path':'bag.db3','bytes':30}]},
                    'native_reader_validation':{'status':'PASS','full_stream_read':True},
                    'compressed_files':[{'path':'bag.db3.zstd','bytes':10,'raw_bytes':30,'zstd_test':'PASS'}]},
                'recording_closure.json':{'status':'PASS','observations':[{'last_clock_ns':80_000_000_000}]},
                'summary.json':{'follow_start_s':5.,'termination_reason':'follow_duration_reached'},
                'configuration/source_sha256.json':{'fixture_source.py':'a'*64}}
            artifacts={relative:dump(directory/relative,value)['sha256'] for relative,value in files.items()}
            for relative in ('configuration/runtime_parameters.yaml','rosbag/metadata.yaml'):
                path=directory/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture: true\n',encoding='utf-8')
                artifacts[relative]=m.sha(path)
            (directory/'rosbag/bag.db3.zstd').write_bytes(b'0123456789')
            rows[trial['id']]={'status':'PASS','engineering_result':'PASS','record_sha256':'c'*64,'artifact_hashes':artifacts}
        plan['trials'].extend({'id':'other_'+str(n)} for n in range(10))
        self.rows=rows
        return plan

    def test_only_named_two_velocity75_seed4_complete_recordings_accepted(self):
        plan=self.selected_fixture()
        with patch.object(m,'frozen_sources',return_value={'actual_frozen':'identity'}):
            selected,sources=m.selected_recordings(self.ctx,plan)
            self.assertEqual(list(selected),list(m.CLASSES));self.assertEqual(sources,{'actual_frozen':'identity'})
            self.assertEqual(selected['person']['raw_sqlite_bytes'],30)
            m.require_inputs_unchanged(selected)
            for field,value in [('seed',5),('group','stage1_position'),('multi_target',True),('duration_s',60.)]:
                changed=deepcopy(plan);changed['trials'][0][field]=value
                with self.subTest(field=field),self.assertRaises((ValueError,RuntimeError)):
                    m.selected_recordings(self.ctx,changed)
            changed=deepcopy(plan);changed['selected_classes']=['car','person']
            with self.assertRaises((ValueError,RuntimeError)):m.selected_recordings(self.ctx,changed)
        source=selected['person'];path=Path(source['trial']['directory'])/'summary.json'
        path.write_text('{}\n',encoding='utf-8')
        with self.assertRaises((ValueError,RuntimeError)):m.require_inputs_unchanged(selected)

    def test_metadata_hash_or_archive_size_substitution_refuses(self):
        plan=self.selected_fixture();trial=plan['trials'][0];directory=Path(trial['directory'])
        with patch.object(m,'frozen_sources',return_value={}):
            path=directory/'rosbag/bag.db3.zstd';path.write_bytes(b'wrong')
            with self.assertRaises((ValueError,RuntimeError)):m.selected_recordings(self.ctx,plan)
            path.write_bytes(b'0123456789');self.rows[trial['id']]['artifact_hashes']['bag_integrity.json']='f'*64
            with self.assertRaises((ValueError,RuntimeError)):m.selected_recordings(self.ctx,plan)

    def test_frozen_source_tuple_ast_and_review_hashes_without_algorithm_import(self):
        relative='uav_tracking/replay_comparison.py';path=self.root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("SOURCE_FILES = ('uav_tracking/replay_comparison.py',)\nEXPORT_SOURCE_FILES = ('uav_tracking/replay_comparison.py',)\nraise RuntimeError('must never import')\n",encoding='utf-8')
        files={relative:m.sha(path)}
        for name in (*m.SCRIPTS,m.POLICY):
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('# fixture\n',encoding='utf-8');files[name]=m.sha(target)
        self.ext.review['files'].update(files);plan={'source_hashes':{name:value for name,value in files.items() if name!=m.POLICY}}
        result=m.frozen_sources(self.ctx,plan)
        self.assertEqual(result['source_hashes'],files)
        path.write_text('changed source\n',encoding='utf-8')
        with self.assertRaises((ValueError,RuntimeError)):m.frozen_sources(self.ctx,plan)

    def test_plan_only_pending_then_final_contract_exact_context_recheck(self):
        (self.root/'results/freeze_validation').mkdir(exist_ok=True)
        with (patch.object(m,'EXTERNAL',self.temp),patch.object(m,'entry_binding',return_value=self.before),
                patch.object(m,'planning_facts',return_value=self.facts),patch.object(m,'require_capacity',return_value={'actual':'headroom'}),
                redirect_stdout(io.StringIO())):
            self.assertEqual(m.plan_calibration(self.ctx),0)
            pending=m.locations(self.ctx)['pending_contract'];value=m.read_small(pending)
            self.assertEqual(value['status'],m.PENDING);self.assertFalse(m.locations(self.ctx)['output'].exists())
            value['status']=m.FINAL;final=self.temp/'development_calibration_v2_contract_fixture_final01.json'
            binding=dump(final,value)
            self.assertEqual(m.load_contract(self.ctx,final,binding['sha256']),value)
            changed=deepcopy(value);changed['facts']['commands'][0]['command'].append('--registration')
            bad=dump(self.temp/'development_calibration_v2_contract_fixture_wrong01.json',changed)
            with self.assertRaises((ValueError,RuntimeError)):m.load_contract(self.ctx,bad['path'],bad['sha256'])

    def artifact_fixture(self):
        output=m.locations(self.ctx)['output'];output.mkdir(exist_ok=False)
        sources={name:('b'*64) for name in (*m.SCRIPTS,m.POLICY,'helper.py')}
        self.facts['offline_sources']={'source_hashes':sources,'SOURCE_FILES':['helper.py'],'EXPORT_SOURCE_FILES':['helper.py']}
        core_plan={'source_hashes':{'flight.py':'f'*64},'plan_sha256':'1'*64}
        plan_binding=dump(self.temp/'actual_plan.json',core_plan)
        self.facts['core_plan']={**plan_binding,'plan_sha256':core_plan['plan_sha256']}
        replay=SimpleNamespace(verify_export_evidence=Mock(return_value={'original_verified':'evidence'}))
        calibration=SimpleNamespace(bind_named_recording=Mock(return_value={'original':'recording'}),
            geometry_statistics=Mock(return_value={'R0_sensor_world_m2':[[1.,0.,0.],[0.,2.,0.],[0.,0.,3.]],
                'independent_valid_geometry':3,'selected_acquisitions':['pre_fusion_including_kf_reject']}))
        for cls in m.CLASSES:
            source=self.facts['selected_recordings'][cls]
            source['input_metadata']={'bag_integrity.json':{'sha256':'c'*64}}
            self.rows[source['trial']['id']]={'status':'PASS'}
            dump(self.runner.record_path(core_plan,source['trial']),{'record':'original'})
            value={'target_class':cls,'seed':4,'group':'stage1_velocity','slot_id':'DEVELOPMENT_ONLY_'+source['trial']['name'],
                'engineering_status':'DEVELOPMENT_ONLY_NO_FORMAL_VERDICT','export_audit':{'status':'PASS','scope':'DEVELOPMENT_ONLY',
                    'online_equivalence':'PASS','native_state_audit':'PASS','native_archive_integrity_sha256':'c'*64}}
            dump(output/(cls+'_export/arrays.json'),value)
            for sidecar in m.SIDECARS:dump(output/(cls+'_export')/sidecar,{'original':'sidecar'})
        return replay,calibration

    def test_export_calls_unchanged_original_evidence_named_recording_and_geometry(self):
        algorithms=self.artifact_fixture();replay,calibration=algorithms
        result=m.validate_export(self.ctx,'person',self.facts,algorithms)
        self.assertEqual(result['geometry_statistics']['independent_valid_geometry'],3)
        calibration.bind_named_recording.assert_called_once();calibration.geometry_statistics.assert_called_once()
        self.assertEqual(replay.verify_export_evidence.call_args.kwargs,{'source_root':self.root,'development_only':True})
        self.assertEqual(replay.verify_export_evidence.call_args.args[2]['freeze_requirements']['flight_source_hashes'],{'flight.py':'f'*64})
        path=m.locations(self.ctx)['output']/'person_export/arrays.json';value=m.read_array(path);value['slot_id']='another_person'
        dump(path,value)
        with self.assertRaises((ValueError,RuntimeError)):m.validate_export(self.ctx,'person',self.facts,algorithms)

    def test_candidate_full_R0_parameters_membership_provenance_and_nonregistration(self):
        algorithms=self.artifact_fixture()
        exports={cls:m.validate_export(self.ctx,cls,self.facts,algorithms) for cls in m.CLASSES}
        classes={cls:exports[cls]['geometry_statistics'] for cls in m.CLASSES}
        plan=m.read_small(self.facts['core_plan']['path']);provenance={}
        for cls in m.CLASSES:
            trial=self.facts['selected_recordings'][cls]['trial']
            provenance[cls]={'slot_id':trial['id'],'engineering_status':'PASS','terminal_record':m.file_binding(self.runner.record_path(plan,trial)),
                'arrays':exports[cls]['arrays'],'recording_evidence':exports[cls]['recording_evidence'],
                'verified_export_evidence':exports[cls]['verified_export_evidence']}
        value={'schema_version':1,'kind':'RELIABILITY_V4_DEVELOPMENT_CALIBRATION','status':'CANDIDATE_NOT_REGISTERED','scope':'DEVELOPMENT_ONLY',
            'created_utc':'2026-01-01T00:00:00+00:00','policy':{'path':m.POLICY,'sha256':'b'*64},'development_plan':self.facts['core_plan'],
            'classes':classes,'provenance':provenance,'source_hashes':{m.SCRIPTS[1]:'b'*64},
            'candidate_parameters':{'R0_sensor_world_m2_by_class':{cls:classes[cls]['R0_sensor_world_m2'] for cls in m.CLASSES},
                'Q_model_and_parameters':{'model':'piecewise_constant_acceleration','acceleration_std_mps2':1.},
                'P0_matrix_and_initial_velocity_policy':{'covariance_6x6':[[float((1,1,1,4,4,4)[i]) if i==j else 0. for j in range(6)] for i in range(6)],
                    'velocity_policy':'registered_constant','initial_velocity_mps':[0.,0.,0.]},'ema_alpha':.35,
                'common_gate_R_and_initialization_policy':{'measurement_covariance':'geometry_plus_pose','initialization':'common_P0','threshold_squared':9.21},
                'common_support_truth_coverage_requirement':.8},
            'claim_boundary':'Candidate development statistics only; does not register parameters, certify full engineering acceptance or read held-out outcomes.'}
        path=m.locations(self.ctx)['output']/'calibration_candidate.json';binding=dump(path,value)
        self.assertEqual(m.validate_candidate(self.ctx,self.facts,algorithms,exports),binding)
        for field in ('status','classes','provenance','candidate_parameters'):
            changed=deepcopy(value)
            if field=='status':changed[field]='REGISTERED'
            elif field=='classes':changed[field]['person']['selected_acquisitions']=[]
            elif field=='provenance':changed[field]['person']['arrays']['sha256']='f'*64
            else:changed[field]['common_gate_R_and_initialization_policy']['threshold_squared']=20.
            dump(path,changed)
            with self.subTest(field=field),self.assertRaises((ValueError,RuntimeError)):
                m.validate_candidate(self.ctx,self.facts,algorithms,exports)

    def test_real_results_symlink_matches_frozen_plan_and_array_resolve_without_changing_argv(self):
        lexical_results=self.root/'results';physical_results=self.temp/'physical_results'
        lexical_results.rename(physical_results)
        try:
            lexical_results.symlink_to(physical_results,target_is_directory=True)
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows account lacks symlink privilege (WinError1314); mandatory in Humble Linux validation')
            raise
        self.assertTrue(lexical_results.is_symlink())
        lexical_plan=m.core.locations(self.candidate)['plan'];dump(lexical_plan,self.reference)
        selected=deepcopy(self.facts['selected_recordings'])
        with (patch.object(m,'require_completed_extension',return_value=(self.prerequisites,self.reference)),
                patch.object(m,'selected_recordings',return_value=(selected,{'frozen':'sources'}))):
            facts=m.planning_facts(self.ctx)
        physical_plan=lexical_plan.resolve(strict=True)
        self.assertNotEqual(lexical_plan,physical_plan);self.assertTrue(lexical_plan.samefile(physical_plan))
        self.assertEqual(facts['core_plan']['path'],str(physical_plan))
        self.assertEqual(facts['core_plan']['sha256'],m.sha(lexical_plan))
        argv=facts['commands'][2]['command']
        self.assertEqual(argv[argv.index('--plan')+1],str(lexical_plan))
        original_dump=dump;observed={}
        def frozen_resolve_semantics(path,value):
            path=Path(path)
            if path.name=='actual_plan.json':
                # planning_facts above binds physical plan; simulate that actual
                # production result while reusing the small candidate fixture.
                path=lexical_plan
                original_dump(path,value)
                return m.file_binding(path.resolve(strict=True))
            if path.name=='calibration_candidate.json':
                value=deepcopy(value)
                value['development_plan']['path']=str(Path(value['development_plan']['path']).resolve(strict=True))
                for cls in m.CLASSES:
                    binding=value['provenance'][cls]['arrays'];canonical=Path(binding['path']).resolve(strict=True)
                    self.assertEqual(binding['path'],str(canonical))
                    self.assertTrue((m.locations(self.ctx)['output']/(cls+'_export/arrays.json')).samefile(canonical))
                    binding['path']=str(canonical)
                observed['original_physical_plan_and_array_provenance']=True
            return original_dump(path,value)
        with patch(__name__+'.dump',side_effect=frozen_resolve_semantics):
            self.test_candidate_full_R0_parameters_membership_provenance_and_nonregistration()
        self.assertTrue(observed['original_physical_plan_and_array_provenance'])


class AdmissionTests(Fixture):
    def admission_fixture(self):
        value={'schema_version':1,'scope':m.SCOPE,'status':m.ADMISSION,'authorized_actions':['plan','run'],
            'prefix':self.admission['prefix'],'selection':{'classes':list(m.CLASSES),'seed':4,'group':'stage1_velocity',
                'slot_ids':[cls+'_stage1_velocity_seed004' for cls in m.CLASSES]},'storage':self.admission['storage'],
            'tools_canonical_sha256':m.canonical({'calibration':'final'}),
            'dependency_tools':{'core':m.canonical({'core':'final'}),'safety':m.canonical({'safety':'final'}),
                'extension':m.canonical({'extension':'final'})},**{name:False for name in m.core.FALSE_FIELDS}}
        ext={**self.ext_admission,'dependency_tools':{key:value['dependency_tools'][key] for key in ('core','safety')}}
        for name in ('extension_admission','extension_contract','candidate_manifest','core_contract','safety_registry'):
            value[name]=dump(self.temp/(name+'.json'),{'fixture':name})
        for name in ('candidate_manifest','core_contract','safety_registry'):ext[name]=value[name]
        return value,ext

    def admission_mocks(self,ext):
        stack=ExitStack()
        stack.enter_context(patch.object(m,'EXTERNAL',self.temp))
        stack.enter_context(patch.object(m,'tool_manifest',return_value={'calibration':'final'}))
        stack.enter_context(patch.object(m.core,'tool_manifest',return_value={'core':'final'}))
        stack.enter_context(patch.object(m.safety,'tool_manifest',return_value={'safety':'final'}))
        stack.enter_context(patch.object(m.extension,'tool_manifest',return_value={'extension':'final'}))
        stack.enter_context(patch.object(m.extension,'load_admission',return_value=(ext,self.candidate,self.ext.review)))
        return stack

    @unittest.skipUnless(os.name == 'posix', 'Requires canonical POSIX storage paths; mandatory in Humble Linux validation')
    def test_explicit_final_dynamic_all_three_dependencies_and_source_context(self):
        value,ext=self.admission_fixture()
        binding=dump(self.temp/'development_calibration_v2_admission_fixture01.json',value)
        with self.admission_mocks(ext):
            actual,actual_ext,candidate,review=m.load_admission(binding['path'],binding['sha256'])
            self.assertEqual(actual['_admission_binding'],binding);self.assertEqual(actual_ext,ext)
            self.assertEqual(candidate,self.candidate);self.assertEqual(review,self.ext.review)
            for key in ('core','safety','extension'):
                changed=deepcopy(value);changed['dependency_tools'][key]='0'*64
                bad=dump(self.temp/'development_calibration_v2_admission_wrong01.json',changed)
                with self.subTest(dependency=key),self.assertRaises((ValueError,RuntimeError)):
                    m.load_admission(bad['path'],bad['sha256'])
            changed=deepcopy(value);changed['core_contract']=value['extension_contract']
            bad=dump(self.temp/'development_calibration_v2_admission_wrong_context01.json',changed)
            with self.assertRaises((ValueError,RuntimeError)):m.load_admission(bad['path'],bad['sha256'])

    def test_pending_foreign_slot_formal_and_recovery_admission_refuse(self):
        value,ext=self.admission_fixture()
        changes=[('status',m.PENDING),('selection',{'classes':['car'],'seed':4,'group':'stage1_velocity'}),
            ('authorized_actions',['plan','run','register']),('prefix',self.candidate['prefix']),('zero_attempt_recovery',True)]
        if m.core.FALSE_FIELDS:changes.append((m.core.FALSE_FIELDS[0],True))
        with self.admission_mocks(ext):
            for key,changed_value in changes:
                changed=deepcopy(value);changed[key]=changed_value
                binding=dump(self.temp/'development_calibration_v2_admission_bad01.json',changed)
                with self.subTest(field=key),self.assertRaises((ValueError,RuntimeError)):
                    m.load_admission(binding['path'],binding['sha256'])


class OriginalOutcomeBindingV2Tests(Fixture):
    """Binding-only fixtures after the original audit; no new failure authority.

    These mocks isolate preservation of the original verdict/audit/lifecycle.
    Actual admissibility belongs to the unchanged frozen functions exercised by
    the separate frozen-authority publisher integration tests, never this stub.
    """
    def bind_original_failure(self, *, known=None):
        identifier='extension_slot_1'
        failures=known if known is not None else ['navigation:REGISTERED_PERFORMANCE_GATES_FAILED']
        row=self.rows[identifier]
        row.update(status='FAIL',engineering_result='FAIL',known_algorithm_failures=deepcopy(failures))
        trial=self.plan['trials'][0]
        audit=self.audit(self.runner,self.plan,trial,row,None,None,extension=True)
        self.terminal['slots'][0]={'slot':identifier,'status':'FAIL','engineering_result':'FAIL','audit':audit}
        attempt=self.terminal['attempts'][0]
        attempt.update(audit=audit,record={'status':'FAIL','engineering_result':'FAIL','record_binding':audit['record_binding']})
        selected=m.extension.locations(self.ext)
        dump(selected['run_driver']/'01_extension_slot_1.attempt_terminal.json',attempt)
        self.terminal['actual_slot_statuses'][identifier]['status']='FAIL'
        self.terminal['status_counts']={'PASS':15,'FAIL':1}
        dump(self.terminal_path,self.terminal)
        return identifier,audit

    def test_original_contract_scope_is_distinct_from_all16_engineering_pass(self):
        with self.extension_mocks():
            result,_=m.require_completed_extension(self.ctx)
        value=result['extension']
        self.assertEqual(value['result'],'PASS')
        self.assertEqual(value['result_scope'],'ORIGINAL_FROZEN_EXTENSION_CONTRACT_NOT_ALL_ENGINEERING_PASS')
        self.assertTrue(value['all_original_cells_pass'])
        self.assertEqual(value['status_counts'],{'PASS':16})
        self.assertEqual(len(value['known_algorithm_failures_by_slot']),16)
        self.assertTrue(all(failures==[] for failures in value['known_algorithm_failures_by_slot'].values()))

    def test_audited_original_fail_status_and_exact_disclosures_are_preserved(self):
        identifier,audit=self.bind_original_failure()
        before={str(path):m.sha(path) for path in self.root.rglob('*') if path.is_file()}
        with self.extension_mocks():
            result,_=m.require_completed_extension(self.ctx)
        value=result['extension']
        self.assertEqual(value['result'],'PASS')
        self.assertFalse(value['all_original_cells_pass'])
        self.assertEqual(value['status_counts'],{'PASS':15,'FAIL':1})
        self.assertEqual(value['engineering_result_counts'],{'PASS':15,'FAIL':1})
        record=value['original_terminals'][0]
        self.assertEqual(record['slot'],identifier)
        self.assertEqual(record['status'],record['engineering_result'])
        self.assertEqual(record['status'],'FAIL')
        self.assertEqual(record['known_algorithm_failures'],audit['known_algorithm_failures'])
        self.assertEqual(value['known_algorithm_failures_by_slot'][identifier],audit['known_algorithm_failures'])
        self.assertEqual(len(value['original_terminals']),16)
        self.assertEqual({str(path):m.sha(path) for path in self.root.rglob('*') if path.is_file()},before)

    def test_hidden_failure_promoted_saved_status_or_mismatched_audit_refuses(self):
        _,_=self.bind_original_failure()
        original=deepcopy(self.terminal)
        for defect in ('hidden_failure','promote_status','record_status','count'):
            changed=deepcopy(original)
            if defect=='hidden_failure':changed['slots'][0]['audit']['known_algorithm_failures']=[]
            elif defect=='promote_status':changed['slots'][0]['status']='PASS'
            elif defect=='record_status':changed['attempts'][0]['record']['engineering_result']='PASS'
            else:changed['status_counts']={'PASS':16}
            dump(self.terminal_path,changed)
            with self.subTest(defect=defect),self.extension_mocks(),self.assertRaises((ValueError,RuntimeError)):
                m.require_completed_extension(self.ctx)

    def test_original_audit_rejection_cannot_be_bypassed_by_new_wrapper(self):
        self.bind_original_failure()
        with (self.extension_mocks(),patch.object(m.core.original41,'audit_record',side_effect=ValueError('original safety rejects')),
                self.assertRaisesRegex(ValueError,'original safety rejects')):
            m.require_completed_extension(self.ctx)
        self.assertFalse(m.locations(self.ctx)['output'].exists())

    def test_original_failed_velocity_calibration_recording_still_refuses(self):
        # Reuse this fixture's own sources, avoiding a second unmanaged TestCase.
        plan=MetadataAndArtifactTests.selected_fixture(self)
        self.rows['person_stage1_velocity_seed004'].update(status='FAIL',engineering_result='FAIL')
        with patch.object(m,'frozen_sources',return_value={}),self.assertRaisesRegex((ValueError,RuntimeError),'failed calibration recording'):
            m.selected_recordings(self.ctx,plan)

    def test_only_v2_names_and_scope_are_admissible(self):
        self.assertEqual(m.OWN,('development_calibration_v2.py','development_calibration_v2.sh','test_development_calibration_v2.py'))
        self.assertIn('_V2_',m.SCOPE)
        self.assertIn('development_calibration_v2_contract_',m.locations(self.ctx)['pending_contract'].name)
        binding=dump(self.temp/'development_calibration_admission_fixture01.json',{})
        with patch.object(m,'EXTERNAL',self.temp),self.assertRaisesRegex((ValueError,RuntimeError),'Named external calibration admission'):
            m.load_admission(binding['path'],binding['sha256'])
        binding=dump(self.temp/'development_calibration_contract_fixture01.json',{})
        with patch.object(m,'EXTERNAL',self.temp),self.assertRaisesRegex((ValueError,RuntimeError),'Named external command contract'):
            m.load_contract(self.ctx,binding['path'],binding['sha256'])


if __name__=='__main__':
    unittest.main()
