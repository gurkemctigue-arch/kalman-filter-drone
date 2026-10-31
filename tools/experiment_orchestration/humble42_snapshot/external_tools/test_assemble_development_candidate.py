"""Independent small metadata/error-injection audit of PENDING assembly only."""
from contextlib import ExitStack,redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import assemble_development_candidate as m


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value)+'\n',encoding='utf-8')


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='assemble_pending_pure_')
        self.addCleanup(temp.cleanup);self.temp=Path(temp.name).resolve()
        self.root=self.temp/'uav_tracking_fullplan_fixture'
        self.directory=self.root/'results/freeze_validation'
        self.directory.mkdir(parents=True)
        self.actions=self.temp/'reviewed_freeze_actions_fixture'
        self.review={'frozen_root':str(self.root),'_review_binding':{'path':'/actual/review.json','sha256':'a'*64},
            'files':{name:'b'*64 for name in m.core.INFRA_FILES}}
        self.frozen={'manifest_sha256':'c'*64,'freeze_source_sha256':'d'*64,'verified_file_count':123}
        self.original={'scope':'actual_original_closed_evidence','sha256':'e'*64}
        self.before={'source':self.frozen,'review':self.review['_review_binding'],
                     'closed_original_evidence':self.original,'development_resource_override':{'receipt':'actual512'}}
        for name in ('unittest.log','generated_message_roundtrip.json'):
            (self.directory/name).write_text('actual small fixture only\n',encoding='utf-8')
        self.facts={'status':'PASS','returncode':0,'execution_count':1,'four_packages_built':True,
            'module_ament_isolation':True,'skipped':5,'tests':123,'source_binding_before':self.frozen,
            'source_binding_after':self.frozen,'source_unchanged':True,'freeze_source_sha256':self.frozen['freeze_source_sha256'],
            'toolchain_canonical_sha256':m.build.GENERIC_CANONICAL,'final_review':self.review['_review_binding'],
            'closed_original_evidence_before':self.original,'closed_original_evidence_after':self.original,
            'closed_original_evidence_unchanged':True,'formal_seeds_consumed':False,'bounded_action_terminal_must_be_PASS':True,
            'suite_log_sha256':m.generic.sha(self.directory/'unittest.log'),
            'generated_message_roundtrip_sha256':m.generic.sha(self.directory/'generated_message_roundtrip.json')}
        self.terminals={action:{'scope':'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE',
            'action':action,'status':'PASS','direct_child_returncode':0,'execution_count':1,
            'cleanup':{'actual_proc_group_empty':True,'direct_child_reaped':True,'residual_processes':[]},
            'binding_before':self.before,'binding_after':self.before} for action in ('build','validate')}
        self.reset_terminals()

    def reset_terminals(self):
        for action,value in self.terminals.items():dump(self.actions/action/'action.terminal.json',value)

    def helper_mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(m.generic,'verify_closed_capsule',return_value=self.original))
        stack.enter_context(patch.object(m.generic,'validation_dir',return_value=self.directory))
        return stack

    def test_complete_actual_bounded_build_and_validate_are_admitted(self):
        with self.helper_mocks():m.require_closed_build(self.review,self.frozen,self.facts,self.actions)

    def test_boolean_partial_foreign_source_history_formal_or_wrong_hash_summary_refuses(self):
        variants=[]
        for key,value in [('status','FAIL'),('returncode',False),('returncode',2),('execution_count',True),
                ('execution_count',2),('skipped',True),('tests',True),('tests',0),('four_packages_built',False),
                ('module_ament_isolation',False),('source_unchanged',False),('freeze_source_sha256','f'*64),
                ('toolchain_canonical_sha256','f'*64),('final_review',{'foreign':True}),
                ('source_binding_after',{'foreign':True}),('closed_original_evidence_after',{'manual':'PASS'}),
                ('closed_original_evidence_unchanged',False),('formal_seeds_consumed',True),
                ('bounded_action_terminal_must_be_PASS',False),('suite_log_sha256','f'*64),
                ('generated_message_roundtrip_sha256','f'*64)]:
            facts=deepcopy(self.facts);facts[key]=value;variants.append(facts)
        for facts in variants:
            with self.subTest(facts=facts),self.helper_mocks():
                self.assertRaises(ValueError,m.require_closed_build,self.review,self.frozen,facts,self.actions)

    def test_each_actual_terminal_requires_rc_scope_single_execution_healthy_cleanup_and_source(self):
        mutations=[{'scope':'manual_summary'},{'status':'FAIL'},{'action':'prepare'},
            {'direct_child_returncode':False},{'direct_child_returncode':2},{'execution_count':True},{'execution_count':2},
            {'cleanup':{'actual_proc_group_empty':False,'direct_child_reaped':True,'residual_processes':[]}},
            {'cleanup':{'actual_proc_group_empty':True,'direct_child_reaped':False,'residual_processes':[]}},
            {'cleanup':{'actual_proc_group_empty':True,'direct_child_reaped':True,'residual_processes':[{'pid':1}]}},
            {'binding_after':{'foreign':True}}]
        for field in ('source','review','closed_original_evidence'):
            before=deepcopy(self.before);before[field]={'foreign':True}
            mutations.append({'binding_before':before,'binding_after':before})
        for action in ('build','validate'):
            for mutation in mutations:
                self.reset_terminals();value=deepcopy(self.terminals[action]);value.update(mutation)
                dump(self.actions/action/'action.terminal.json',value)
                with self.subTest(action=action,mutation=mutation),self.helper_mocks():
                    self.assertRaises(ValueError,m.require_closed_build,self.review,self.frozen,self.facts,self.actions)

    def test_missing_terminal_and_tampered_original_suite_or_cdr_refuse(self):
        for action in ('build','validate'):
            self.reset_terminals();(self.actions/action/'action.terminal.json').unlink()
            with self.helper_mocks():self.assertRaises(ValueError,m.require_closed_build,self.review,self.frozen,self.facts,self.actions)
        self.reset_terminals()
        for name in ('unittest.log','generated_message_roundtrip.json'):
            original=(self.directory/name).read_bytes();(self.directory/name).write_text('mutated\n',encoding='utf-8')
            with self.helper_mocks():self.assertRaises(ValueError,m.require_closed_build,self.review,self.frozen,self.facts,self.actions)
            (self.directory/name).write_bytes(original)

    def main_mocks(self,output):
        stack=self.helper_mocks()
        stack.enter_context(patch.object(m.generic,'EXTERNAL',self.temp))
        stack.enter_context(patch.object(m.generic,'require_linux'))
        stack.enter_context(patch.object(m.build,'load_review',return_value=self.review))
        stack.enter_context(patch.object(m.generic,'frozen_binding',return_value=self.frozen))
        stack.enter_context(patch.object(m.core,'tool_manifest',return_value={'core':'actual_reviewed'}))
        stack.enter_context(patch.object(m.build,'tool_manifest',return_value={'build':'actual_reviewed'}))
        stack.enter_context(patch('sys.argv',['assemble_development_candidate.py','--review','/actual/review.json',
            '--review-sha256','a'*64,'--core-tools-sha256',m.generic.canonical({'core':'actual_reviewed'}),
            '--prefix','reliability_v4_fixture_probe','--output',str(output)]))
        return stack

    def test_main_writes_pending_only_validates_complete_temporary_copy_and_refuses_overwrite(self):
        dump(self.directory/'build_validation_summary.json',self.facts)
        dump(self.root/m.core.policy.PROTOCOL_PATH,{'actual_protocol':'fixture'})
        output=self.temp/'development_candidate_fixture_pending.json'
        seen=[]
        with self.main_mocks(output),patch.object(m.core,'validate_candidate',side_effect=lambda v:seen.append(deepcopy(v))) as valid, \
                patch.object(m.core,'require_supplement_build') as supplement,redirect_stdout(io.StringIO()):
            m.main()
        written=m.generic.read_small(output)
        self.assertEqual(written['status'],'PENDING_INDEPENDENT_DEVELOPMENT_CANDIDATE_REVIEW_NOT_EXECUTABLE')
        self.assertEqual(seen[0]['status'],m.core.CANDIDATE)
        self.assertEqual(written['experiment']['flight_count'],12);self.assertEqual(written['experiment']['seed'],4)
        self.assertEqual(written['core_classes'],list(m.core.CLASSES))
        self.assertEqual(written['core_groups'],list(m.core.GROUPS))
        self.assertEqual(written['original41_closure'],{'path':m.generic.LINUX_EXTERNAL+'/'+m.core.ORIGINAL_CLOSURE,'sha256':m.core.ORIGINAL_CLOSURE_SHA})
        self.assertEqual(written['pressure_reuse']['scope'],m.core.INFRA_SCOPE)
        self.assertEqual(written['pressure_reuse']['original_execution_terminal'],{
            'path':m.core.ORIGINAL_ROOT+'/results/freeze_validation/observer_archive_pressure01/execution_terminal.json',
            'sha256':'a60e271660923c76814b92773a1d7e57d121ff8013820b3c83fdcadeaf23e03f'})
        self.assertTrue(all(written[key] is False for key in m.core.FALSE_FIELDS))
        self.assertEqual(valid.call_count,1);self.assertEqual(supplement.call_count,1)
        self.assertRaisesRegex(ValueError,'Final independently',m.core.validate_candidate,written)
        original=output.read_bytes()
        with self.main_mocks(output),patch.object(m.build,'load_review') as load:
            self.assertRaises(ValueError,m.main)
        load.assert_not_called();self.assertEqual(output.read_bytes(),original)


if __name__=='__main__':unittest.main()
