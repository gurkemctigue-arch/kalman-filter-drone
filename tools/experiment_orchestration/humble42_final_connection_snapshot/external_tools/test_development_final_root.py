"""Synthetic final-root connections only; no actual source scan/build/prereq."""
from contextlib import ExitStack,nullcontext,redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import prepare_development_final_root as p
import build_development_final_root as b
import publish_development_final_protocols as u


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value)+'\n',encoding='utf-8')
    return p.binding(path)


class SourceFixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='final_connection_source_only_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.source=self.base/'candidate';self.source.mkdir()
        self.root=self.base/'final';self.results=self.base/'final_results'
        protocol={'status':p.DRAFT,'navigation_acceptance':{'coast_s':.60,'lost_s':.75},
            'magnetic_library_registration':p.primitives.RUNTIME_NAMES[1],
            'resources':{'car':{'model':p.core.resources.MODEL,'inference_image_size':512,'inference_threads':4}},
            'car_input_scale_registration':{'revision':p.core.resources.REVISION}}
        for name,value in [(p.PLANNING[0],protocol),(p.PLANNING[1],{'status':p.DRAFT}),
                (p.PLANNING[2],{'status':p.DRAFT}),
                ('config/px4_magnetic_runtime.json',{'source_root':p.primitives.RUNTIME['px4_root']}),
                ('config/gazebo_magnetic_runtime_humble22.json',{'fixture':'same runtime bytes'}),
                ('config/ros_gz_runtime_humble22.json',{'overlay_root':p.primitives.RUNTIME['bridge_overlay']})]:
            dump(self.source/name,value)
        for name,content in [('a.py',b'# frozen source\n'),(p.core.resources.MODEL,b'fixture weights only'),
                (p.primitives.FREEZER,(' '.join("--exclude='"+x+"'" for x in p.primitives.EXCLUDES)+'\n').encode()),
                ('scripts/build_metric_supplement.py',b'# fixture\n')]:
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        protected={path.relative_to(self.source).as_posix():p.sha(path) for path in self.source.rglob('*') if path.is_file()}
        self.classified={name:protected[name] for name in ('a.py','config/px4_magnetic_runtime.json')}
        self.review={'files':protected,'runtime':deepcopy(p.primitives.RUNTIME)}
        self.candidate={'frozen_root':str(self.source)};self.manifest={'classified_source_hashes':self.classified}
        self.pin=dump(self.base/'candidate.json',{'fixture':'source authority placeholder only'})
        self.bindings={'candidate_manifest':self.pin,'source_review':{'path':'/fixture/review.json','sha256':'a'*64},
            'original_source_manifest':{'path':'/fixture/manifest.json','sha256':'b'*64},
            'source_binding':{'fixture':'reviewed'},'strict512_source_build':{'fixture':'actual API mocked'}}
        self.classifier=SimpleNamespace(source_hashes=lambda root:{name:p.sha(Path(root)/name) for name in self.classified},
            flight_source_hashes=lambda values:dict(values))
        self.digest=p.canonical(p.tool_manifest())

    def source_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(p,'authority',return_value=(self.candidate,self.review,self.manifest,self.bindings)))
        stack.enter_context(patch.object(p,'validate_paths'))
        stack.enter_context(patch.object(p.primitives,'frozen_classifier',return_value=self.classifier))
        return stack

    def proposal(self):
        with self.source_mocks():return p.proposal(self.pin,self.root,self.results,self.digest)

    def copy(self):
        value=self.proposal()
        def rsync(command,**kwargs):
            self.assertEqual(command,value['rsync_command'])
            def ignore(directory,names):
                return [name for name in names if p.primitives.excluded((Path(directory)/name).relative_to(self.source).as_posix())]
            shutil.copytree(self.source,self.root,dirs_exist_ok=True,copy_function=shutil.copy2,ignore=ignore)
            return SimpleNamespace(returncode=0)
        with self.source_mocks(),patch.object(p.subprocess,'run',side_effect=rsync):
            try:outcome=p.apply_copy(value)
            except OSError as error:
                if getattr(error,'winerror',None)==1314:self.skipTest('Host denies directory symlink creation; actual Linux fixture covers this')
                raise
        return value,outcome


class PreparationTests(SourceFixture):
    def test_explicit_inspect_keeps_whole_tree_and_classified_denominators_separate(self):
        value=self.proposal()
        self.assertGreater(len(value['expected_protected_file_hashes']),len(value['expected_classified_source_hashes']))
        self.assertEqual(value['expected_protected_file_hashes'],self.review['files'])
        self.assertEqual(value['expected_classified_source_hashes'],self.classified)
        self.assertFalse(self.root.exists());self.assertFalse(self.results.exists())
        self.assertEqual(value['overlay_files'],{});self.assertFalse(value['formal_seed_use_authorized'])
        protocol=json.loads((self.source/p.PLANNING[0]).read_text())
        self.assertEqual(protocol['navigation_acceptance'],{'coast_s':.6,'lost_s':.75})

    def test_copy_preserves_every_source_draft_and_original_preparation_manifest(self):
        value,outcome=self.copy()
        self.assertEqual(outcome['status'],'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED')
        self.assertTrue((self.root/'results').is_symlink())
        self.assertEqual((self.root/'results').resolve(),self.results)
        for name,digest in self.review['files'].items():self.assertEqual(p.sha(self.root/name),digest)
        self.assertEqual((self.results/'freeze_validation/source_sha256.txt').read_text(),
            ''.join(digest+'  '+name+'\n' for name,digest in sorted(self.review['files'].items())))
        with self.source_mocks():self.assertRaises(FileExistsError,p.apply_copy,value)

    def test_missing_authority_or_modified_whole_map_classified_map_overlay_and_claim_refuse(self):
        original=self.proposal()
        for mutate in [lambda v:v['expected_protected_file_hashes'].pop('a.py'),
                lambda v:v['expected_classified_source_hashes'].pop('a.py'),
                lambda v:v.update(overlay_files={'a.py':'tuned'}),lambda v:v.update(formal_seed_use_authorized=True),
                lambda v:v.update(flights_executed=False),lambda v:v.update(source_root='/old/41')]:
            value=deepcopy(original);mutate(value)
            with self.source_mocks():self.assertRaises(ValueError,p.validate_proposal,value)
        with patch.object(p,'authority',side_effect=ValueError('Missing actual candidate build evidence')):
            self.assertRaisesRegex(ValueError,'Missing actual',p.proposal,self.pin,self.root,self.results,self.digest)
        self.assertFalse(self.root.exists())

    def test_no_registered_or_changed_resource_is_accepted_as_original_draft(self):
        protected=deepcopy(self.review['files'])
        core=json.loads((self.source/p.PLANNING[0]).read_text())
        for key,value in [('inference_image_size',640),('inference_threads',3)]:
            changed=deepcopy(core);changed['resources']['car'][key]=value
            dump(self.source/p.PLANNING[0],changed);protected[p.PLANNING[0]]=p.sha(self.source/p.PLANNING[0])
            self.assertRaises(ValueError,p.check_drafts,self.source,protected)
        changed=deepcopy(core);changed['status']='REGISTERED';dump(self.source/p.PLANNING[0],changed)
        protected[p.PLANNING[0]]=p.sha(self.source/p.PLANNING[0])
        self.assertRaises(ValueError,p.check_drafts,self.source,protected)

    def test_only_bound_published_canonical_deltas_allowed_after_build(self):
        value,outcome=self.copy();original_manifest=(self.results/'freeze_validation/source_sha256.txt').read_bytes()
        core=json.loads((self.root/p.PLANNING[0]).read_text());core['status']='REGISTERED'
        published=dump(self.root/p.PLANNING[0],core)
        with self.source_mocks():
            self.assertRaises(ValueError,p.verify_prepared,value)
            p.verify_prepared(value,{p.PLANNING[0]:published})
            (self.root/'a.py').write_bytes(b'# unrelated tuning forbidden\n')
            self.assertRaises(ValueError,p.verify_prepared,value,{p.PLANNING[0]:published})
        self.assertEqual((self.results/'freeze_validation/source_sha256.txt').read_bytes(),original_manifest)

    def test_outcome_binding_uses_real_results_path_for_root_results_alias(self):
        value,outcome=self.copy();actual=self.results/'freeze_validation/source_preparation_outcome.json'
        aliased=self.root/'results/freeze_validation/source_preparation_outcome.json'
        self.assertEqual(p.binding(actual),p.binding(aliased))
        with self.source_mocks():context=b.validate_receipt(p.binding(aliased)['path'],p.sha(aliased))
        self.assertEqual(context['root'],self.root)
        self.assertEqual(context['preparation']['path'],str(actual))
        self.assertEqual(context['proposal'],value)


class PathAndInertTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','POSIX path policy is exercised by the Humble fixture')
    def test_path_policy_requires_independent_root_d_results_new_products_and_bound_link(self):
        source=Path('/root/uav_tracking_fullplan_fixture');root=Path('/root/uav_tracking_fullplan_fixture_final')
        results=Path('/mnt/d/fixture/results/frozen_fullplan_fixture_final')
        with patch.object(Path,'is_dir',return_value=True),patch.object(Path,'is_symlink',return_value=False), \
                patch.object(Path,'exists',return_value=False),patch.object(Path,'resolve',lambda self,**kw:self):
            p.validate_paths(source,root,results)
            for final,store in [(source,results),(Path('/tmp/final'),results),(root,source/'results'),
                    (root,Path('/mnt/c/fixture/results/frozen_fullplan_bad'))]:
                self.assertRaises(ValueError,p.validate_paths,source,final,store)
        with patch.object(Path,'is_dir',return_value=True),patch.object(Path,'is_symlink',return_value=False), \
                patch.object(Path,'exists',return_value=True),patch.object(Path,'resolve',lambda self,**kw:self):
            self.assertRaises(ValueError,p.validate_paths,source,root,results)

    def test_all_describe_entries_are_inert_and_dependency_globals_unchanged(self):
        original=(p.primitives.SOURCE_ROOT,b.primitives.preparation.SOURCE_ROOT,u.primitives.ROOT,u.primitives.RESULTS)
        with patch.object(p,'authority',side_effect=AssertionError('No actual source reads')), \
                patch.object(b,'validate_receipt',side_effect=AssertionError('No actual copy/build')), \
                patch.object(u,'publish',side_effect=AssertionError('No actual publication')), \
                patch.object(p.subprocess,'Popen',side_effect=AssertionError('No process launch')), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(p.main([]),0);self.assertEqual(b.main([]),0);self.assertEqual(u.main([]),0)
        self.assertEqual(original,(p.primitives.SOURCE_ROOT,b.primitives.preparation.SOURCE_ROOT,u.primitives.ROOT,u.primitives.RESULTS))

    def test_missing_action_inputs_refuse_before_any_source_copy_build_or_publish(self):
        with patch.object(p.generic,'require_linux'),patch.object(p,'authority') as authority, \
                patch.object(p,'apply_copy') as copy,patch.object(b,'launch') as build,patch.object(u,'publish') as publish:
            self.assertRaises(ValueError,p.main,['copy'])
            self.assertRaises(ValueError,u.main,['protocols'])
            self.assertRaises(ValueError,u.main,['replay'])
        authority.assert_not_called();copy.assert_not_called();build.assert_not_called();publish.assert_not_called()

    def test_bound_json_aliases_and_source_hash_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json';pin=dump(path,{'actual':'fixture'})
            self.assertEqual(p.checked(pin),{'actual':'fixture'})
            dump(path,{'changed':True});self.assertRaises(ValueError,p.checked,pin)
            self.assertRaises(ValueError,p.checked,{'path':'relative.json','sha256':'a'*64})


class BuildOwnershipTests(unittest.TestCase):
    def test_internal_build_requires_actual_bounded_parent_before_environment_or_colcon(self):
        context={'owner':Path('/fixture/owner')}
        with patch.dict(os.environ,{},clear=True),patch.object(b.primitives,'require_environment') as environment, \
                patch.object(b.development_build,'runtime_contracts') as runtime:
            self.assertRaises(ValueError,b.build,context)
        environment.assert_not_called();runtime.assert_not_called()

    def test_bounded_child_parent_group_session_and_original_leader_are_all_required(self):
        context={'owner':Path('/fixture/owner')}
        owned={'pid':42,'pgid':42,'session':42,'observed_leader_stat':{'start_ticks':10}}
        environment={'DEVELOPMENT_FINAL_BUILD_RECEIPT_DIR':str(context['owner']),'DEVELOPMENT_FINAL_BUILD_PARENT_PID':'7'}
        with patch.dict(os.environ,environment,clear=True),patch.object(b,'read',return_value=owned), \
                patch.object(b.bounded,'process_stat',side_effect=lambda pid:{'pid':42,'ppid':7,'start_ticks':10} if pid==42 else {'pid':7}), \
                patch.object(b.os,'getpgrp',return_value=42,create=True),patch.object(b.os,'getsid',return_value=42,create=True):
            b.require_owned_child(context)
            with patch.object(b.os,'getsid',return_value=99):self.assertRaises(ValueError,b.require_owned_child,context)
            owned['observed_leader_stat']['start_ticks']=11
            self.assertRaises(ValueError,b.require_owned_child,context)

    def test_colcon_reuses_actual_four_packages_and_humble_fastcdr_without_old_root(self):
        root=Path('/root/uav_tracking_fullplan_fixture_final')
        command=b.primitives.colcon_command(root,'/fixture/colcon')
        self.assertIn('-Dfastcdr_DIR='+str(b.primitives.FASTCDR),command)
        self.assertEqual(command[command.index('--packages-select')+1:command.index('--cmake-args')],list(b.primitives.PACKAGES))
        self.assertIn(str(root/'ros2_ws/build'),command)
        self.assertNotIn(str(b.primitives.preparation.SOURCE_ROOT),command)


class CompletedBuildFixture(unittest.TestCase):
    """Rebound synthetic PASS labels still need the original underlying evidence."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='final_build_closure_fixture_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.root=self.base/'final';self.root.mkdir()
        self.results=self.base/'results';self.attempt=self.results/'freeze_validation'/b.ATTEMPT
        self.attempt.mkdir(parents=True);self.owner=self.results/'freeze_validation'/(b.ATTEMPT+'_owner');self.owner.mkdir()
        self.tools={'fixture':'bounded tiny evidence only'};self.source={'original_source':'fixed'}
        self.preparation=dump(self.base/'preparation.json',{'fixture':'original copy'})
        self.context={'root':self.root,'results':self.results,'attempt':self.attempt,'owner':self.owner,
            'preparation':self.preparation,'outcome':{'source_verification':self.source},'review':{}}
        module=self.root/'a.py';module.write_text('# tiny module origin\n')
        prefix=self.root/'install';prefix.mkdir()
        grouped={}
        for test_id,(path,predicate,reason) in b.skips.EXPECTED_SKIPS.items():
            _,cls,method=test_id.rsplit('.',2)
            grouped.setdefault(path,{}).setdefault(cls,[]).append((method,predicate,reason))
        for path,classes in grouped.items():
            content='import unittest\n'
            for cls,methods in classes.items():
                content+='class '+cls+':\n'
                for method,predicate,reason in methods:
                    content+='    @unittest.skipUnless('+predicate+','+repr(reason)+')\n    def '+method+'(self):pass\n'
            target=self.root/path;target.parent.mkdir(exist_ok=True);target.write_text(content)
        dump(self.attempt/'colcon_defaults.yaml',{})
        runtime=dump(self.attempt/'runtime_preflight.json',{'fixture':'strict512 checked boundary'})
        self.started={'kind':b.KIND,'preparation':self.preparation,'tools':self.tools,'source_before':self.source,
            'colcon_defaults':p.binding(self.attempt/'colcon_defaults.yaml'),'runtime_preflight':runtime,
            'command':b.primitives.colcon_command(self.root,'/fixture/colcon')}
        dump(self.attempt/'started.json',self.started)
        (self.attempt/'colcon_build.log').write_text('Summary: 4 packages finished [0.1s]\n')
        dump(self.attempt/'colcon_exit.json',{'returncode':0,'log':p.binding(self.attempt/'colcon_build.log')})
        modules={name:str(module) for name in b.primitives.MODULES}
        prefixes={name:str(prefix) for name in b.primitives.PACKAGES}
        self.origins={'root':str(self.root),'isolated':True,'module_files':modules,'ros_package_prefixes':prefixes,
            'module_count':len(modules),'ament_package_count':len(prefixes),'selected_bridge_overlay':str(b.primitives.BRIDGE),
            'bridge_runtime_validation':{'status':'PASS'}}
        dump(self.attempt/'import_isolation.json',self.origins)
        self.cdr={'scope':'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION','status':'PASS',
            'checks':{str(n):True for n in range(11)},'execution_count':1,'serialized_bytes':5,'serialized_sha256':'a'*64}
        dump(self.attempt/'generated_message_roundtrip.json',self.cdr)
        dump(self.attempt/'fastcdr_provenance.json',{'status':'MATCHES_HUMBLE_SYSTEM_FASTCDR','root':str(self.root),
            'fastcdr_directory':str(b.primitives.FASTCDR),'agent_compile_prefix_absent':True,'inputs_sha256':{str(module):p.sha(module)}})
        log=''.join(test_id.rsplit('.',1)[1]+' ('+test_id.rsplit('.',1)[0]+') ... skipped '+repr(row[2])+'\n'
            for test_id,row in b.skips.EXPECTED_SKIPS.items())+'\nRan 12 tests in 0.1s\n\nOK (skipped=5)\n'
        (self.attempt/'unittest.log').write_text(log)
        self.suite={'status':'PASS','returncode':0,'tests':12,'log':p.binding(self.attempt/'unittest.log'),
            'actual_skipped_tests':b.skips.validate_observed_skips(log),'skip_source_contract':b.skips.validate_skip_sources({
                name:(self.root/name).read_text() for name in b.skips.SKIP_SOURCE_PATHS})}
        dump(self.attempt/'full_suite.json',self.suite)
        dump(self.attempt/'runtime_preflight_closure.json',{'before':runtime,'after':runtime,'strict512_verified':True})
        self.verification={'kind':b.KIND,'status':'PASS_BUILD_AND_STATIC_CHECKS_ONLY','root':str(self.root),
            'preparation':self.preparation,'tools':self.tools,'source_after':self.source,'full_suite':self.suite,
            'module_count':len(modules),'ament_package_count':len(prefixes),'actual_cdr_checks':11,
            'source_unchanged':True,'protocols_registered':False,'formal_seed_use_authorized':False}
        dump(self.attempt/'verification_outcome.json',self.verification)
        self.outcome={'kind':b.KIND,'status':'FINAL_ROOT_BUILT_NOT_REGISTERED_OR_FLOWN','root':str(self.root),'results':str(self.results),
            'preparation':self.preparation,'verification':p.binding(self.attempt/'verification_outcome.json'),
            'four_packages_built':True,'full_suite_status':'PASS','source_unchanged':True,'protocols_registered':False,
            'plans_created':False,'flights_executed':0,'formal_seed_use_authorized':False}
        dump(self.attempt/'outcome.json',self.outcome)
        self.action={'preparation':self.preparation,'tools':self.tools,'source':self.source,'formal_seed_use_authorized':False}
        self.owner_start={'action':'final-root-build','command':b.build_command(self.context),'binding_before':self.action,
            'execution_count':1,'automatic_retry':False,'automatic_next_step':False,'formal_seeds_consumed':False,
            'timeout_s':p.generic.ACTIONS['build']+p.generic.ACTIONS['validate'],'term_grace_s':30.,'kill_confirm_s':5.}
        dump(self.owner/'action.started.json',self.owner_start)
        dump(self.owner/'action.process.json',{'pid':42,'pgid':42,'session':42,'observed_leader_stat':{'pid':42,'start_ticks':10}})
        (self.owner/'action.log').write_text('tiny original wrapper log\n')
        self.terminal={**self.owner_start,'scope':'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE',
            'status':'PASS','direct_child_returncode':0,'pid':42,'requested_signals':[],'launcher_error':None,'binding_error':None,
            'cleanup':{'actual_proc_group_empty':True,'direct_child_reaped':True,'residual_processes':[]},
            'binding_after':self.action,'runtime_acceptance':'NOT_EVALUATED','action_log_sha256':p.sha(self.owner/'action.log')}
        dump(self.owner/'action.terminal.json',self.terminal)
        self.refresh()

    def refresh(self):
        self.outcome['verification']=p.binding(self.attempt/'verification_outcome.json');dump(self.attempt/'outcome.json',self.outcome)
        self.chain={'kind':b.KIND,'status':'ACTUAL_FINAL_COPY_BUILD_SUITE_COMPLETE_NOT_ADMITTED','preparation':self.preparation,
            'build_outcome':p.binding(self.attempt/'outcome.json'),'bounded_terminal':p.binding(self.owner/'action.terminal.json'),
            'action_binding':self.action,'build_artifacts':{name:p.binding(self.attempt/name) for name in b.BUILD_ARTIFACTS},
            'owner_artifacts':{name:p.binding(self.owner/name) for name in b.OWNER_ARTIFACTS},'tools':self.tools,
            'formal_seed_use_authorized':False,'capacity_admission_performed':False}
        self.pin=dump(self.attempt/'chain.json',self.chain)

    def mocks(self):
        stack=ExitStack();stack.enter_context(patch.object(b,'validate_receipt',return_value=self.context))
        stack.enter_context(patch.object(b,'tools',return_value=self.tools))
        stack.enter_context(patch.object(b.development_build,'verify_512_runtime'))
        return stack

    def test_actual_terminal_build_suite_evidence_accepts_without_requiring_current_draft_source(self):
        with self.mocks(),patch.object(b,'source_check',side_effect=AssertionError('Published canonical delta belongs to publication validation')):
            self.assertEqual(b.validate_completed_build(self.pin),self.context)

    def test_rebound_positive_labels_cannot_hide_cdr_failure_or_runtime_mismatch(self):
        self.cdr['checks']['0']=False;dump(self.attempt/'generated_message_roundtrip.json',self.cdr);self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'eleven',b.validate_completed_build,self.pin)
        self.cdr['checks']['0']=True;dump(self.attempt/'generated_message_roundtrip.json',self.cdr)
        dump(self.attempt/'runtime_preflight_closure.json',{'before':{'wrong':True},'after':self.started['runtime_preflight'],'strict512_verified':True})
        self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'runtime preflight closure',b.validate_completed_build,self.pin)

    def test_rebound_failed_colcon_or_incomplete_full_suite_is_rejected(self):
        dump(self.attempt/'colcon_exit.json',{'returncode':2,'log':p.binding(self.attempt/'colcon_build.log')});self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'four-package cold-build log',b.validate_completed_build,self.pin)
        dump(self.attempt/'colcon_exit.json',{'returncode':0,'log':p.binding(self.attempt/'colcon_build.log')})
        self.suite['tests']=999;dump(self.attempt/'full_suite.json',self.suite)
        self.verification['full_suite']=self.suite;dump(self.attempt/'verification_outcome.json',self.verification);self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'full-suite',b.validate_completed_build,self.pin)

    def test_rebound_owner_action_retry_or_non_original_source_binding_is_rejected(self):
        self.terminal['action']='different-action';dump(self.owner/'action.terminal.json',self.terminal);self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'owner',b.validate_completed_build,self.pin)
        self.terminal['action']='final-root-build';dump(self.owner/'action.terminal.json',self.terminal)
        self.owner_start['automatic_retry']=True;dump(self.owner/'action.started.json',self.owner_start);self.refresh()
        with self.mocks():self.assertRaisesRegex(ValueError,'owner command',b.validate_completed_build,self.pin)


class OriginalGateFixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='original28_terminal_fixture_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.source=self.base/'original_source';self.source.mkdir()
        self.context={'proposal':{'source_root':str(self.source),'expected_classified_source_hashes':{'a.py':'a'*64}}}
        self.runner=SimpleNamespace(CLASSES=('person','car'),GROUPS=tuple('g'+str(n) for n in range(6)),
            EXTENSION_CONDITIONS=tuple('condition'+str(n) for n in range(8)),validate_plan=Mock(),
            record_path=lambda plan,trial:self.base/(trial['id']+'.record.json'))
        self.runtime=SimpleNamespace(v4=self.runner)

    def evidence(self,extensions):
        trials=[{'id':cls+'_'+cell} for cls in self.runner.CLASSES for cell in
            (self.runner.EXTENSION_CONDITIONS if extensions else self.runner.GROUPS)]
        plan={'mode':'EXTENSION_PROBE' if extensions else 'PROBE','frozen_root':str(self.source),
            'source_hashes':self.context['proposal']['expected_classified_source_hashes'],'selected_seeds':[4],
            'selected_classes':list(self.runner.CLASSES),
            'selected_groups':['stage1_velocity','stage1_position'] if extensions else list(self.runner.GROUPS),'trials':trials}
        if extensions:plan['selected_extension_conditions']=list(self.runner.EXTENSION_CONDITIONS)
        pin=dump(self.base/'original_plan.json',plan);rows={};slots=[]
        for trial in trials:
            record={'status':'PASS','engineering_result':'PASS','execution_status':'COMPLETED','infrastructure_stop':False,'flight_exit_code':0}
            rows[trial['id']]=record;record_pin=dump(self.runner.record_path(plan,trial),record)
            slots.append({'plan_path':pin['path'],'plan_file_sha256':pin['sha256'],'slot_id':trial['id'],
                'record_file_sha256':record_pin['sha256']})
        self.runner.read_slots=Mock(return_value=rows)
        return plan,rows,{'result':'PASS','probe_slots':slots,**({'known_algorithm_failures':[]} if extensions else {})}

    def test_each_complete_original_matrix_requires_actual_terminal_pass_record_bindings(self):
        for extensions in (False,True):
            plan,rows,gate=self.evidence(extensions)
            u.require_all_original_pass(u.Inputs(),self.runtime,gate,self.context,extensions=extensions)
            self.runner.read_slots.assert_called_with(plan,verify_artifacts=False)
            item=gate['probe_slots'][0];rows[item['slot_id']]['engineering_result']='FAIL'
            pin=dump(self.runner.record_path(plan,plan['trials'][0]),rows[item['slot_id']]);item['record_file_sha256']=pin['sha256']
            self.assertRaisesRegex(ValueError,'record must itself be PASS',u.require_all_original_pass,
                u.Inputs(),self.runtime,gate,self.context,extensions=extensions)

    def test_normal_extension_pass_gate_with_disclosed_algorithm_failures_is_not_28_pass(self):
        _,_,gate=self.evidence(True);gate['known_algorithm_failures']=[{'slot_id':gate['probe_slots'][0]['slot_id'],'failures':['navigation:FAIL']}]
        self.assertRaisesRegex(ValueError,'no disclosed algorithm failures',u.require_all_original_pass,
            u.Inputs(),self.runtime,gate,self.context,extensions=True)

    def test_duplicate_subset_or_rebound_original_fail_cannot_be_promoted_by_gate_title(self):
        plan,rows,gate=self.evidence(False);gate['probe_slots'][-1]=dict(gate['probe_slots'][0])
        self.assertRaisesRegex(ValueError,'exactly once',u.require_all_original_pass,u.Inputs(),self.runtime,gate,self.context,extensions=False)
        plan,rows,gate=self.evidence(False);item=gate['probe_slots'][0];row=rows[item['slot_id']];row['status']='FAIL'
        pin=dump(self.runner.record_path(plan,plan['trials'][0]),row);item['record_file_sha256']=pin['sha256']
        self.assertRaisesRegex(ValueError,'record must itself be PASS',u.require_all_original_pass,
            u.Inputs(),self.runtime,gate,self.context,extensions=False)


class RegistrarConnectionFixture(unittest.TestCase):
    """Exercise parameterized glue through original assembly binding and validators."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='normal_registrar_connection_fixture_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.root=self.base/'final';self.root.mkdir()
        self.protected={'a.py':'a'*64};self.flight={'a.py':'a'*64}
        self.context={'root':self.root,'proposal':{'expected_classified_source_hashes':self.protected,'flight_source_hashes':self.flight}}
        self.core={'status':p.DRAFT,'navigation_acceptance':{'coast_s':.60,'lost_s':.75},'resources':{'input':512,'threads':4}}
        self.extension={'status':p.DRAFT,'keep':'original condition design'};self.replay={'status':p.DRAFT,'keep':'original replay design'}
        for name,value in [('core',self.core),('extension',self.extension),('replay',self.replay)]:dump(self.root/u.PATHS[name],value)
        registrar=self.base/'registrar.py';registrar.write_text('# small registrar source identity fixture\n')
        guard=self.base/'guard.py';guard.write_text('# small guard source identity fixture\n')
        self.guard=SimpleNamespace(__file__=str(guard),no_fixture=Mock(),utc=lambda value:value,validate_safety=Mock(),
            validate_development=Mock(),read_plans=Mock())
        self.tool=SimpleNamespace(__file__=str(registrar),guard=self.guard,gate_context=Mock())
        self.runner=SimpleNamespace(flight_source_hashes=Mock(return_value=self.flight),validate_protocol=Mock(),
            validate_navigation_gates=Mock(),validate_extension_protocol=Mock(),validate_probe_gate=Mock())
        self.runtime=SimpleNamespace(v4=self.runner,replay=SimpleNamespace(validate_registered_config=Mock(),verify_registration_artifacts=Mock()))

    def assembly(self,action,artifact,used):
        directory=self.base/('assembly_'+action);directory.mkdir()
        pin=dump(directory/'artifact.json',artifact)
        dump(directory/'started.json',{'kind':'RELIABILITY_V4_REGISTRATION_ASSEMBLY_START','action':action,
            'registrar':p.binding(self.tool.__file__),'guard':p.binding(self.guard.__file__),'inputs':used})
        outcome={'kind':'RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME','status':'ASSEMBLED_AND_VALIDATED_NOT_EXECUTED',
            'action':action,'registrar':p.binding(self.tool.__file__),'canonical_files_modified':False,'formal_attempts_started':0,
            'artifact':pin,'validated_bytes_sha256':pin['sha256']}
        return dump(directory/'outcome.json',outcome),pin

    def protocol_request(self):
        core=dump(self.base/'target_core.json',{'frozen_root':str(self.root),'source_hashes':self.protected,'protocol':self.core})
        extension=dump(self.base/'target_extension.json',{'frozen_root':str(self.root),'source_hashes':self.protected,
            'extension_protocol_binding':{'protocol':self.extension}})
        gates={name:dump(self.base/(name+'_gate.json'),{'result':'PASS','original':name}) for name in ('core','extension')}
        safety,_=self.assembly('safety-summary',{'created_utc':'2000-01-01T00:00:00+00:00'},
            {'target_plan':core,'core_gate':gates['core']})
        self.safety_context=SimpleNamespace(core={'protocol':self.core},registration_times=[])
        self.tool.gate_context.return_value=(self.runtime,self.safety_context)
        return {'target_plans':{'core':core,'extension':extension},'gates':gates,'safety_assembly':safety}

    def test_protocol_glue_calls_original_gate_safety_and_exact_28_pass_checks_before_staging(self):
        request=self.protocol_request()
        with patch.object(u.builder,'source_check') as source,patch.object(u,'pending') as pending, \
                patch.object(u,'require_all_original_pass') as all_pass:
            runtime,originals,candidates=u.prepare_protocols(u.Inputs(),request,self.context,self.tool)
        self.assertIs(runtime,self.runtime);source.assert_called_once_with(self.context)
        self.tool.gate_context.assert_called_once_with(request['target_plans']['core']['path'],request['gates']['core']['path'])
        self.assertEqual(pending.call_count,2);self.runner.validate_protocol.assert_called_once()
        self.runner.validate_navigation_gates.assert_called_once_with(self.core['navigation_acceptance'])
        self.runner.validate_extension_protocol.assert_called_once();self.runner.validate_probe_gate.assert_called_once()
        self.assertEqual(all_pass.call_count,2);self.assertEqual([call.kwargs['extensions'] for call in all_pass.call_args_list],[False,True])
        self.guard.validate_safety.assert_called_once()
        for name in ('core','extension'):
            self.assertEqual((self.root/u.PATHS[name]).read_bytes(),originals[name])
            self.assertEqual(json.loads(candidates[name])['status'],'REGISTERED')
        self.assertEqual(json.loads(candidates['core'])['navigation_acceptance'],{'coast_s':.6,'lost_s':.75})

    def test_original_safety_validation_refusal_leaves_all_canonicals_as_original_drafts(self):
        request=self.protocol_request();self.guard.validate_safety.side_effect=ValueError('actual safety not complete')
        originals={name:(self.root/u.PATHS[name]).read_bytes() for name in u.PATHS}
        with patch.object(u.builder,'source_check'),patch.object(u,'pending'),patch.object(u,'require_all_original_pass'):
            self.assertRaisesRegex(ValueError,'actual safety',u.prepare_protocols,u.Inputs(),request,self.context,self.tool)
        for name,raw in originals.items():self.assertEqual((self.root/u.PATHS[name]).read_bytes(),raw)

    def replay_request(self):
        published={}
        for name in ('core','extension'):
            value=p.read(self.root/u.PATHS[name]);value.update(status='REGISTERED',registration_utc='2000-01-01T00:00:00+00:00')
            published[name]=dump(self.root/u.PATHS[name],value)
        copy_build=dump(self.base/'copy_build.json',{'fixture':'actual build validated by separate closure fixture'})
        publication=dump(self.base/'protocol_publication.json',{'kind':u.OUTCOME,'action':'protocols','status':'PUBLISHED_NOT_ADMITTED',
            'copy_build':copy_build,'published':published})
        core={'source_hashes':self.protected,'plan_sha256':'b'*64,'protocol':p.read(self.root/u.PATHS['core'])}
        extension={'source_hashes':self.protected,'extension_protocol_binding':{'protocol':p.read(self.root/u.PATHS['extension'])}}
        core_pin=dump(self.base/'formal_core.json',core);extension_pin=dump(self.base/'formal_extension.json',extension)
        candidate={'freeze_requirements':{'final_engineering_plan_path':core_pin['path'],
            'final_engineering_plan_file_sha256':core_pin['sha256'],'final_engineering_plan_digest':core['plan_sha256']},
            'registration':{'registered_utc':'2001-01-01T00:00:00+00:00'},'status':'REGISTERED'}
        calibration=dump(self.base/'calibration.json',{'fixture':'real validator is called below'})
        assembly,artifact=self.assembly('replay-config',candidate,{'core_plan':core_pin,'candidate':calibration})
        self.formal=SimpleNamespace();self.guard.read_plans.return_value=self.formal
        self.guard.load_runtime=Mock(return_value=self.runtime)
        return {'copy_build':copy_build,'protocol_publication':publication,'formal_plans':{'core':core_pin,'extension':extension_pin},
            'replay_assembly':assembly},candidate,artifact,calibration

    def test_replay_glue_rechecks_allowed_source_delta_real_registration_artifacts_and_development_calibration(self):
        request,candidate,artifact,calibration=self.replay_request();original=(self.root/u.PATHS['replay']).read_bytes()
        with patch.object(u.builder,'source_check') as source,patch.object(u,'pending') as pending:
            runtime,originals,candidates=u.prepare_replay(u.Inputs(),request,self.context,self.tool)
        source.assert_called_once_with(self.context,{u.PATHS[name]:p.binding(self.root/u.PATHS[name]) for name in ('core','extension')})
        self.assertEqual(pending.call_count,2);self.runtime.replay.validate_registered_config.assert_called_once_with(candidate)
        self.runtime.replay.verify_registration_artifacts.assert_called_once_with(candidate,source_root=self.root)
        self.guard.validate_development.assert_called_once_with({'calibration':calibration},self.formal,self.runtime)
        self.assertEqual(candidates['replay'],Path(artifact['path']).read_bytes());self.assertEqual(originals['replay'],original)
        self.assertEqual((self.root/u.PATHS['replay']).read_bytes(),original)

    def test_development_calibration_refusal_cannot_publish_replay(self):
        request,_,_,_=self.replay_request();self.guard.validate_development.side_effect=ValueError('actual calibration invalid')
        original=(self.root/u.PATHS['replay']).read_bytes()
        with patch.object(u.builder,'source_check'),patch.object(u,'pending'):
            self.assertRaisesRegex(ValueError,'calibration invalid',u.prepare_replay,u.Inputs(),request,self.context,self.tool)
        self.assertEqual((self.root/u.PATHS['replay']).read_bytes(),original)


class PublicationFixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='final_canonical_fixture_only_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.root=self.base/'final';self.results=self.base/'results';self.root.mkdir();self.results.mkdir()
        (self.results/'freeze_validation').mkdir()
        self.originals={};self.candidates={}
        for name in ('core','extension','replay'):
            raw=(json.dumps({'status':p.DRAFT,'keep':{'thresholds':[.6,.75],'input':512,'threads':4}},indent=2)+'\n').encode()
            path=self.root/u.PATHS[name];path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
            self.originals[name]=raw;self.candidates[name]=u.primitives.patch_fields(raw,{'status':'REGISTERED','registration_utc':'2026-11-01T00:00:00+00:00'})
        self.context={'root':self.root,'results':self.results,'proposal':{'draft_planning_hashes':{
            u.PATHS[name]:p.sha(self.root/u.PATHS[name]) for name in self.originals}},
            'outcome':{'preparation_source_manifest':{'path':'/fixture/source_sha256.txt','sha256':'a'*64}}}
        self.runner=SimpleNamespace(simulation_processes=Mock(return_value=[]),run_lock=Mock(return_value=nullcontext()))
        self.runtime=SimpleNamespace(v4=self.runner)
        self.request={'schema_version':1,'kind':u.KIND,'action':'protocols',
            'copy_build':{'path':'/actual/chain.json','sha256':'a'*64},
            'expected_canonical_sha256':{name:p.sha(self.root/u.PATHS[name]) for name in ('core','extension')},
            'reviewed_tools_sha256':'fixture-independent-tools','target_plans':{},'gates':{},'safety_assembly':{}}
        self.pin=dump(self.base/'request.json',self.request)

    def mocks(self):
        stack=ExitStack();stack.enter_context(patch.object(p.generic,'require_linux'))
        stack.enter_context(patch.dict(os.environ,{'WSL_DISTRO_NAME':'UAVHumble22'}))
        stack.enter_context(patch.object(u,'build_context',return_value=(self.context,object())))
        stack.enter_context(patch.object(u,'prepare_protocols',return_value=(self.runtime,
            {name:self.originals[name] for name in ('core','extension')},{name:self.candidates[name] for name in ('core','extension')})))
        return stack

    def test_protocols_back_up_drafts_publish_only_named_fields_and_keep_seal_separate(self):
        with self.mocks():outcome=u.publish('protocols',self.pin)
        directory=self.results/'freeze_validation/canonical_protocols_publication_development01'
        self.assertEqual(outcome['status'],'PUBLISHED_NOT_ADMITTED')
        self.assertFalse(outcome['final_source_seal_created']);self.assertFalse(outcome['formal_seed_use_authorized'])
        for name in ('core','extension'):
            self.assertEqual((directory/(name+'.original.json')).read_bytes(),self.originals[name])
            self.assertEqual((self.root/u.PATHS[name]).read_bytes(),self.candidates[name])
            value=json.loads((self.root/u.PATHS[name]).read_text())
            self.assertEqual(value['keep'],{'thresholds':[.6,.75],'input':512,'threads':4})
        self.assertEqual((self.root/u.PATHS['replay']).read_bytes(),self.originals['replay'])
        with self.mocks():self.assertRaises(ValueError,u.publish,'protocols',self.pin)

    def test_partial_atomic_publication_is_retained_with_original_backups_no_rollback_or_retry(self):
        replace=os.replace;calls=[]
        def fail_second(source,destination):
            calls.append(str(destination))
            if len(calls)==2:raise OSError('injected second canonical publication failure')
            return replace(source,destination)
        with self.mocks(),patch.object(u.os,'replace',side_effect=fail_second):
            self.assertRaises(OSError,u.publish,'protocols',self.pin)
        directory=self.results/'freeze_validation/canonical_protocols_publication_development01'
        failure=p.read(directory/'failed.json')
        self.assertFalse(failure['rollback_attempted']);self.assertTrue(failure['preserve_all_original_backups'])
        self.assertEqual((self.root/u.PATHS['core']).read_bytes(),self.candidates['core'])
        self.assertEqual((self.root/u.PATHS['extension']).read_bytes(),self.originals['extension'])
        for name in ('core','extension'):self.assertEqual((directory/(name+'.original.json')).read_bytes(),self.originals[name])

    def test_missing_real_build_or_guard_evidence_stops_before_any_canonical_mutation(self):
        with patch.object(p.generic,'require_linux'),patch.dict(os.environ,{'WSL_DISTRO_NAME':'UAVHumble22'}), \
                patch.object(u,'build_context',side_effect=ValueError('actual mandatory suite missing')):
            self.assertRaises(ValueError,u.publish,'protocols',self.pin)
        for name,raw in self.originals.items():self.assertEqual((self.root/u.PATHS[name]).read_bytes(),raw)

    def test_input_tamper_wrong_canonical_sha_or_runtime_activity_refuses(self):
        for mutation in ('wrongsha','active'):
            if mutation=='wrongsha':
                self.request['expected_canonical_sha256']['core']='f'*64;self.pin=dump(self.base/'request.json',self.request)
            else:self.runner.simulation_processes.return_value=[{'pid':1}]
            with self.mocks():self.assertRaises(ValueError,u.publish,'protocols',self.pin)
        self.assertFalse((self.results/'freeze_validation/canonical_protocols_publication_development01').exists())

    def test_normal_runner_pending_checks_exact_denominator_and_no_prior_products(self):
        trials=[{'id':f'slot{n}','directory':str(self.base/f'uncreated{n}')} for n in range(12)]
        plan={'mode':'PROBE','frozen_root':str(self.root),'trials':trials,'selected_seeds':[4],
            'selected_classes':['person','car'],'selected_groups':['original_group']}
        runner=SimpleNamespace(CLASSES=('person','car'),GROUPS=('original_group',),validate_plan=Mock(),verify_sources=Mock(),
            read_slots=Mock(return_value={trial['id']:{'status':'PENDING'} for trial in trials}))
        runtime=SimpleNamespace(v4=runner)
        u.pending(runtime,plan,'/fixture/plan.json',self.root,'PROBE',12)
        runner.read_slots.return_value.pop('slot11')
        self.assertRaises(ValueError,u.pending,runtime,plan,'/fixture/plan.json',self.root,'PROBE',12)
        runner.read_slots.return_value={trial['id']:{'status':'PENDING'} for trial in trials}
        (self.base/'uncreated0').mkdir()
        self.assertRaises(ValueError,u.pending,runtime,plan,'/fixture/plan.json',self.root,'PROBE',12)


if __name__=='__main__':unittest.main()
