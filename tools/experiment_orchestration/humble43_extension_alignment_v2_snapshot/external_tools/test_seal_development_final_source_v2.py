"""Tiny synthetic whole-source sidecar tests; no actual freeze or admission."""
from contextlib import ExitStack,nullcontext,redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import seal_development_final_source_v2 as m


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');return m.binding(path)


class WholeSourceFixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='whole_source_sidecar_synthetic_only_');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.root=self.base/'final';self.root.mkdir()
        self.results=self.base/'results';self.results.mkdir();self.validation=self.results/'freeze_validation';self.validation.mkdir()
        self.attempt=self.validation/m.builder.ATTEMPT;self.attempt.mkdir()
        self.originals={}
        for name in ('core','extension','replay'):
            value={'status':m.preparation.DRAFT,'keep':{'coast_s':.6,'lost_s':.75,'input':512,'threads':4}}
            dump(self.root/m.publisher.PATHS[name],value)
            self.originals[name]=(self.root/m.publisher.PATHS[name]).read_bytes()
        for name in ('a.py','model.pt','tools/reliability_v4_register.py','tools/reliability_v4_guard.py'):
            path=self.root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'# tiny fixture source or model bytes\n')
        self.original_inventory=m.preparation.primitives.inventory(self.root)
        protected={name:entry['sha256'] for name,entry in self.original_inventory.items() if entry.get('kind')=='file'}
        self.classified={name:m.sha(self.root/name) for name in ('a.py','model.pt')};self.flight={'a.py':self.classified['a.py']}
        self.preparation_manifest=dump(self.validation/'original_preparation_manifest.json',{'original_DRAFT_map':protected})
        self.preparation_bytes=Path(self.preparation_manifest['path']).read_bytes()
        self.context={'root':self.root,'results':self.results,'attempt':self.attempt,'review':{'runtime':{'fixture':'selected runtime'}},
            'outcome':{'preparation_source_manifest':self.preparation_manifest},'proposal':{
                'expected_whole_tree_inventory':self.original_inventory,'original_whole_tree_inventory':self.original_inventory,
                'expected_protected_file_hashes':protected,'expected_classified_source_hashes':self.classified,'flight_source_hashes':self.flight,
                'draft_planning_hashes':{m.publisher.PATHS[name]:m.sha(self.root/m.publisher.PATHS[name]) for name in self.originals},
                'candidate_manifest':{'path':'/synthetic/candidate.json','sha256':'a'*64},
                'source_review':{'path':'/synthetic/source_review.json','sha256':'b'*64},
                'original_source_manifest':{'path':'/synthetic/source_manifest.json','sha256':'c'*64},'strict512_source_build':{'fixture':'bound supplement'}}}
        dump(self.attempt/'runtime_preflight.json',{'fixture':'actual build boundary is mocked explicitly'})
        self.tool=SimpleNamespace(__file__=str(self.root/'tools/reliability_v4_register.py'),REQUEST_FIELDS={
            'schema_version','kind','final_root','plans','registrations','calibration','safety','state_directory','storage'})
        self.tool.guard=SimpleNamespace(__file__=str(self.root/'tools/reliability_v4_guard.py'),
            DELIVERIES=('offline_replay20','videos12','detection_audit','figures_documents','runtime_logs'),
            sealed=lambda value,key:m.canonical({name:data for name,data in value.items() if name!=key}))
        self.runtime=SimpleNamespace(v4=SimpleNamespace(simulation_processes=Mock(return_value=[])))
        self.tool.guard.load_runtime=Mock(return_value=self.runtime)
        self.target_core=dump(self.base/'target_core.json',{'fixture':'pre-registration target core'})
        self.target_extension=dump(self.base/'target_extension.json',{'fixture':'pre-registration target extension'})
        self.gates={name:dump(self.base/(name+'_gate.json'),{'fixture':'original gate '+name}) for name in ('core','extension')}
        self.copy_build=dump(self.attempt/'chain.json',{'fixture':'real build validator is explicitly mocked'})
        safety_assembly,self.safety=self.assembly('safety-summary',{'fixture':'real safety validator is outside this tiny fixture'},
            {'target_plan':self.target_core,'core_gate':self.gates['core']})
        stamp='2026-01-01T00:00:00+00:00'
        for name in ('core','extension'):
            fields={'status':'REGISTERED','registration_utc':stamp}
            if name=='extension':fields['development_readiness']={**self.gates[name],'evidence':m.read(self.gates[name]['path'])}
            (self.root/m.publisher.PATHS[name]).write_bytes(m.publisher.primitives.patch_fields(self.originals[name],fields))
        self.protocol_request={'schema_version':1,'kind':m.publisher.KIND,'action':'protocols','copy_build':self.copy_build,
            'expected_canonical_sha256':{name:self.context['proposal']['draft_planning_hashes'][m.publisher.PATHS[name]] for name in ('core','extension')},
            'reviewed_tools_sha256':m.CONNECTION_SHA,'target_plans':{'core':self.target_core,'extension':self.target_extension},
            'gates':self.gates,'safety_assembly':safety_assembly}
        self.protocol_publication=self.publication('protocols',self.protocol_request,('core','extension'))
        self.core=self.formal('core',120);self.extension=self.formal('extension',160)
        self.formal_plans={name:dump(self.base/(name+'_formal.json'),getattr(self,name)) for name in ('core','extension')}
        self.tool.guard.read_plans=Mock(return_value=SimpleNamespace(core=self.core,extension=self.extension))
        self.calibration=dump(self.base/'calibration.json',{'fixture':'real calibration validation is outside this tiny fixture'})
        configuration={'status':'REGISTERED','freeze_requirements':{
            'final_engineering_plan_path':self.formal_plans['core']['path'],
            'final_engineering_plan_file_sha256':self.formal_plans['core']['sha256'],
            'final_engineering_plan_digest':self.core['plan_sha256']}}
        replay_assembly,self.replay_candidate=self.assembly('replay-config',configuration,
            {'core_plan':self.formal_plans['core'],'candidate':self.calibration})
        (self.root/m.publisher.PATHS['replay']).write_bytes(Path(self.replay_candidate['path']).read_bytes())
        self.replay_request={'schema_version':1,'kind':m.publisher.KIND,'action':'replay','copy_build':self.copy_build,
            'expected_canonical_sha256':{'replay':self.context['proposal']['draft_planning_hashes'][m.publisher.PATHS['replay']]},
            'reviewed_tools_sha256':m.CONNECTION_SHA,'protocol_publication':self.protocol_publication,
            'formal_plans':self.formal_plans,'replay_assembly':replay_assembly}
        self.replay_publication=self.publication('replay',self.replay_request,('replay',))
        self.pins={'copy_build':self.copy_build,'protocol_publication':self.protocol_publication,'replay_publication':self.replay_publication}
        # Tiny lifecycle fixtures do not claim production module-origin review.
        # The real tools/origin/connection checks have a dedicated fixture below.
        self.producer_tools={'fixture':'synthetic lifecycle only',
            'reviewed_connection_canonical_sha256':m.CONNECTION_SHA}
        tools_patch=patch.object(m,'tools',return_value=self.producer_tools)
        tools_patch.start();self.addCleanup(tools_patch.stop)
        self.digest=m.canonical(m.tools())

    def formal(self,name,count):
        return {'source_hashes':self.classified,'model_hashes':{'model.pt':self.classified['model.pt']},'plan_sha256':'d'*64,
            'output':str(self.results/(name+'_formal')),'trials':[{'id':name+str(n),'directory':str(self.results/(name+str(n)))} for n in range(count)],
            'magnetic_runtime_binding':{'fixture':'same runtime'},'magnetic_library_binding':{'fixture':'same library'}}

    def assembly(self,action,artifact,used,*,directory=None,detail=None):
        directory=directory or self.base/('registrar_'+action);directory.mkdir()
        pin=dump(directory/('final_admission.json' if action=='seal' else 'artifact.json'),artifact)
        dump(directory/'started.json',{'kind':'RELIABILITY_V4_REGISTRATION_ASSEMBLY_START','action':action,
            'registrar':m.binding(self.tool.__file__),'guard':m.binding(self.tool.guard.__file__),'inputs':used})
        outcome={'kind':'RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME','status':'ASSEMBLED_AND_VALIDATED_NOT_EXECUTED',
            'action':action,'registrar':m.binding(self.tool.__file__),'canonical_files_modified':False,'formal_attempts_started':0,
            'artifact':pin,'validated_bytes_sha256':pin['sha256']}
        if detail is not None:outcome['detail']=detail
        return dump(directory/'outcome.json',outcome),pin

    def publication(self,action,request,names):
        directory=self.validation/('canonical_'+action+'_publication_development_v2_01');directory.mkdir()
        request_pin=dump(self.base/(action+'_request.json'),request)
        published={name:m.binding(self.root/m.publisher.PATHS[name]) for name in names}
        dump(directory/'started.json',{'kind':m.publisher.OUTCOME,'action':action,'request':request_pin,
            'copy_build':self.copy_build,'publisher':m.binding(m.publisher.__file__)})
        for name in names:
            (directory/(name+'.original.json')).write_bytes(self.originals[name])
            dump(directory/(name+'_published.json'),published[name])
            dump(directory/(name+'_publish_intent.json'),{'canonical':str(self.root/m.publisher.PATHS[name])})
        return dump(directory/'outcome.json',{'schema_version':1,'kind':m.publisher.OUTCOME,'action':action,'status':'PUBLISHED_NOT_ADMITTED',
            'copy_build':self.copy_build,'request':request_pin,'published':published,'preparation_manifest_retained':self.preparation_manifest,
            'formal_attempts_started':0,'plans_created':False,'final_source_seal_created':False,'capacity_admission_performed':False,
            'formal_seed_use_authorized':False})

    def check_source(self,context,allowed):
        self.assertIs(context,self.context);expected=deepcopy(self.original_inventory)
        self.assertEqual(set(allowed),set(m.publisher.PATHS.values()))
        for name,pin in allowed.items():
            m.require(m.binding(self.root/name)==pin,'Actual canonical bytes changed')
            expected[name]['sha256']=pin['sha256'];expected[name]['bytes']=(self.root/name).stat().st_size
        actual=m.preparation.primitives.inventory(self.root)
        m.require(actual==expected,'Actual source changed beyond three published deltas')
        m.require({name:m.sha(self.root/name) for name in self.classified}==self.classified,'Classified source changed')
        m.require(Path(self.preparation_manifest['path']).read_bytes()==self.preparation_bytes,'Original preparation manifest changed')
        return {'whole_tree_entry_count':len(actual),'protected_file_count':len(self.context['proposal']['expected_protected_file_hashes']),
            'whole_tree_inventory_sha256':m.canonical(actual),'classified_source_sha256':m.canonical(self.classified),
            'flight_source_sha256':m.canonical(self.flight),'results_root':str(self.results)}

    def mocks(self):
        stack=ExitStack()
        stack.enter_context(patch.object(m.publisher,'build_context',return_value=(self.context,self.tool)))
        stack.enter_context(patch.object(m.builder,'source_check',side_effect=self.check_source))
        stack.enter_context(patch.object(m.preparation.generic,'exclusive_window',return_value=nullcontext()))
        return stack

    def create(self):
        with self.mocks():return m.create_manifest(self.pins,self.digest)

    def rebind_canonical(self,name):
        action='protocols' if name in ('core','extension') else 'replay'
        directory=self.validation/('canonical_'+action+'_publication_development_v2_01')
        outcome=m.read(directory/'outcome.json');outcome['published'][name]=m.binding(self.root/m.publisher.PATHS[name])
        dump(directory/(name+'_published.json'),outcome['published'][name]);pin=dump(directory/'outcome.json',outcome)
        if action=='protocols':
            self.pins['protocol_publication']=pin
            self.replay_request['protocol_publication']=pin
            replay_request_pin=dump(self.base/'replay_request.json',self.replay_request)
            replay_directory=self.validation/'canonical_replay_publication_development_v2_01'
            started=m.read(replay_directory/'started.json');started['request']=replay_request_pin;dump(replay_directory/'started.json',started)
            replay_outcome=m.read(replay_directory/'outcome.json');replay_outcome['request']=replay_request_pin
            self.pins['replay_publication']=dump(replay_directory/'outcome.json',replay_outcome)
        else:self.pins['replay_publication']=pin

    def test_manifest_binds_exact_final_maps_and_three_publications_keeps_original_preparation(self):
        original=deepcopy(self.context['proposal']['expected_protected_file_hashes']);pin=self.create()
        with self.mocks():value,context,_,_=m.verify_manifest(pin,self.digest)
        self.assertIs(context,self.context);self.assertEqual(value['classified_source_hashes'],self.classified)
        self.assertEqual(value['flight_source_hashes'],self.flight);self.assertEqual(value['model_hashes'],{'model.pt':self.classified['model.pt']})
        self.assertEqual(value['original_preparation_manifest'],self.preparation_manifest)
        self.assertEqual(Path(self.preparation_manifest['path']).read_bytes(),self.preparation_bytes)
        self.assertEqual(self.context['proposal']['expected_protected_file_hashes'],original)
        self.assertEqual({key for key in original if original[key]!=value['final_protected_file_hashes'][key]},set(m.publisher.PATHS.values()))
        self.assertFalse(value['original_guard_consumes_whole_tree_manifest']);self.assertFalse(value['formal_seed_use_authorized'])
        with self.mocks():self.assertRaisesRegex(ValueError,'immutable',m.create_manifest,self.pins,self.digest)

    def test_rebound_arbitrary_protocol_delta_cannot_become_allowed_by_rewriting_pass_receipts(self):
        target=self.root/m.publisher.PATHS['core'];value=m.read(target);value['keep']['lost_s']=99;dump(target,value)
        self.rebind_canonical('core')
        with self.mocks():self.assertRaisesRegex(ValueError,'beyond.*registration fields',m.source_facts,self.pins)

    def test_rebound_replay_bytes_must_equal_actual_registrar_candidate(self):
        target=self.root/m.publisher.PATHS['replay'];value=m.read(target);value['new_unregistered_setting']=True;dump(target,value)
        self.rebind_canonical('replay')
        with self.mocks():self.assertRaisesRegex(ValueError,'validated registrar candidate bytes',m.source_facts,self.pins)

    def test_arbitrary_outcome_path_or_changed_original_backup_refuses_before_manifest(self):
        rogue=dump(self.base/'retitled_publication.json',m.read(self.protocol_publication['path']));pins=dict(self.pins,protocol_publication=rogue)
        with self.mocks():self.assertRaisesRegex(ValueError,'fixed canonical publication',m.source_facts,pins)
        directory=self.validation/'canonical_protocols_publication_development_v2_01';(directory/'core.original.json').write_bytes(b'{}')
        with self.mocks():self.assertRaisesRegex(ValueError,'DRAFT backup',m.source_facts,self.pins)
        self.assertFalse((self.validation/m.NAME).exists())

    def test_actual_whole_source_or_preparation_tamper_invalidates_existing_manifest(self):
        pin=self.create();(self.root/'a.py').write_bytes(b'# unrelated tuning\n')
        with self.mocks():self.assertRaisesRegex(ValueError,'source changed',m.verify_manifest,pin,self.digest)
        (self.root/'a.py').write_bytes(b'# tiny fixture source or model bytes\n')
        Path(self.preparation_manifest['path']).write_text('{"changed_original":true}')
        with self.mocks():self.assertRaisesRegex(ValueError,'Original preparation manifest changed',m.verify_manifest,pin,self.digest)

    def test_posthoc_started_terminal_or_trial_products_refuse_prestart_sidecar(self):
        trial=self.core['trials'][0]
        paths=(Path(trial['directory']),Path(self.core['output'])/'slots'/(trial['id']+'.json'),
            Path(self.core['output'])/'slots'/(trial['id']+'.started.json'))
        for path in paths:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
            with self.mocks():self.assertRaisesRegex(ValueError,'untouched PENDING',m.create_manifest,self.pins,self.digest)
            path.unlink()
        self.assertFalse((self.validation/m.NAME).exists())

    def test_manifest_content_or_wrong_location_cannot_be_rebound_as_original(self):
        pin=self.create();value=m.read(pin['path']);value['final_protected_file_hashes']['a.py']='f'*64
        changed=dump(pin['path'],value)
        with self.mocks():self.assertRaisesRegex(ValueError,'manifest changed',m.verify_manifest,changed,self.digest)
        other=dump(self.base/'moved_manifest.json',value)
        with self.mocks():self.assertRaisesRegex(ValueError,'original final results path',m.verify_manifest,other,self.digest)

    def request(self,pin):
        value=m.read(pin['path'])
        return {'schema_version':1,'kind':'RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST','final_root':str(self.root),
            'plans':self.formal_plans,'registrations':value['canonical_planning'],'calibration':self.calibration,'safety':self.safety,
            'state_directory':str(self.results/'uncreated_guard_state'),
            'storage':{'volumes':[{'fixture':'not real capacity evidence'}],'results_volume':'fixture_volume',
                'vhd_host':{'fixture':'actual normal guard validates this'},'temporary_peak_bytes':{'fixture_volume':1},
                'temporary_bound_rule':{'fixture':'actual normal guard validates this'},
                'delivery_reservations':{key:{'fixture':'actual explicit inputs'} for key in self.tool.guard.DELIVERIES},
                'additional_remaining_bytes':{'fixture_volume':1},'cells':[{'fixture':n} for n in range(28)]}}

    def admission_mocks(self):
        stack=self.mocks();stack.enter_context(patch.dict(os.environ,{'WSL_DISTRO_NAME':'UAVHumble22'}))
        stack.enter_context(patch.object(m.sys,'executable',str(m.builder.primitives.VENV_PYTHON)))
        return stack

    def fake_registrar_execution(self,command,owner,**kwargs):
        self.executed_command=command;before=kwargs['binding']('before');owner.mkdir()
        request=m.read(command[command.index('--request')+1]);directory=Path(command[command.index('--output-directory')+1])
        admission={key:data for key,data in request.items() if key not in {'schema_version','kind'}}
        admission.update(schema_version=1,kind='RELIABILITY_V4_FORMAL_ADMISSION',created_utc='2026-01-01T00:00:00+00:00',
            tool=m.binding(self.tool.guard.__file__))
        admission['manifest_sha256']=self.tool.guard.sealed(admission,'manifest_sha256')
        outcome_pin,artifact_pin=self.assembly('seal',admission,{'request':m.binding(command[command.index('--request')+1])},directory=directory,
            detail={'claim':'ADMISSION_CHECK_ONLY_NO_INITIAL_ADMISSION_OR_FLIGHT','guard_state_created':False,
                'guard_check':{'result':'PASS','capacity':{'pending_slots':getattr(self,'fake_pending',280)},
                    'manifest':{'path':str(directory/'.validation/unpublished.json'),'sha256':'bind actual written bytes below'},
                    'manifest_sha256':admission['manifest_sha256'],'tool':admission['tool']}})
        outcome=m.read(outcome_pin['path'])
        outcome['detail']['guard_check']['manifest']['sha256']=artifact_pin['sha256']
        dump(outcome_pin['path'],outcome)
        terminal={'status':'PASS','binding_before':before,'binding_after':kwargs['binding']('after')}
        dump(owner/'action.terminal.json',terminal);return terminal

    def test_outer_seal_calls_exact_original_cli_request_with_whole_verification_before_and_after(self):
        pin=self.create();request_pin=dump(self.base/'admission_request.json',self.request(pin))
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded',side_effect=self.fake_registrar_execution) as run:
            result=m.seal_admission(pin,request_pin,self.digest)
        expected=[str(m.builder.primitives.VENV_PYTHON),'-B',str(self.root/'tools/reliability_v4_register.py'),'seal',
            '--request',request_pin['path'],'--output-directory',str(self.validation/m.ASSEMBLY)]
        self.assertEqual(self.executed_command,expected);self.assertEqual(run.call_args.kwargs['action'],'final-source-admission-seal')
        self.assertEqual(result['binding_before'],result['binding_after']);self.assertEqual(result['whole_source_manifest'],pin)
        self.assertFalse(result['initial_admission_performed']);self.assertFalse(result['formal_seed_use_authorized'])
        self.assertTrue(result['whole_manifest_recheck_required_before_formal_serial_start'])
        self.assertFalse(Path(self.request(pin)['state_directory']).exists())

    def test_missing_budget_or_wrong_request_registration_refuses_without_subprocess(self):
        pin=self.create();value=self.request(pin);value['storage'].pop('cells');request_pin=dump(self.base/'admission_request.json',value)
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded') as run:
            self.assertRaisesRegex(ValueError,'explicit complete physical storage',m.seal_admission,pin,request_pin,self.digest)
        run.assert_not_called()
        value=self.request(pin);value['registrations']['core']={'path':'/synthetic/other.json','sha256':'f'*64}
        request_pin=dump(self.base/'admission_request.json',value)
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded') as run:
            self.assertRaisesRegex(ValueError,'Exact original admission request',m.seal_admission,pin,request_pin,self.digest)
        run.assert_not_called();self.assertFalse((self.validation/m.SEAL_ATTEMPT).exists())

    def test_original_registrar_refusal_or_wrong_full_denominator_retains_failure_no_outer_pass(self):
        pin=self.create();request_pin=dump(self.base/'admission_request.json',self.request(pin));self.fake_pending=279
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded',side_effect=self.fake_registrar_execution):
            self.assertRaisesRegex(ValueError,'complete original registrar/guard seal',m.seal_admission,pin,request_pin,self.digest)
        directory=self.validation/m.SEAL_ATTEMPT
        self.assertFalse((directory/'outcome.json').exists());self.assertTrue((directory/'failed.json').is_file())
        self.assertTrue((self.validation/m.ASSEMBLY/'outcome.json').is_file())
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded') as run:
            self.assertRaisesRegex(ValueError,'Exclusive new outer',m.seal_admission,pin,request_pin,self.digest)
        run.assert_not_called()

    def test_runtime_activity_prevents_seal_without_creating_outer_attempt(self):
        pin=self.create();request_pin=dump(self.base/'admission_request.json',self.request(pin))
        self.runtime.v4.simulation_processes.return_value=[{'pid':1}]
        with self.admission_mocks(),patch.object(m.bounded,'run_bounded') as run:
            self.assertRaisesRegex(ValueError,'idle runtime',m.seal_admission,pin,request_pin,self.digest)
        run.assert_not_called();self.assertFalse((self.validation/m.SEAL_ATTEMPT).exists())


class InertCliTests(unittest.TestCase):
    def test_default_describe_and_missing_inputs_never_scan_source_or_seal(self):
        with patch.object(m,'source_facts',side_effect=AssertionError('No actual source scan')), \
                patch.object(m,'seal_admission',side_effect=AssertionError('No actual admission')) as seal, \
                patch.object(m.preparation.generic,'require_linux'), \
                patch.object(m,'tools',return_value={'fixture':'inert describe only'}),redirect_stdout(io.StringIO()):
            self.assertEqual(m.main([]),0)
            digest=m.canonical(m.tools())
            for action in ('create','verify','seal-admission'):
                self.assertRaises(ValueError,m.main,[action,'--reviewed-tools-sha256',digest])
        seal.assert_not_called()


class VersionedToolsBoundaryTests(unittest.TestCase):
    """Use real tools() on tiny named files, never a source/capacity claim."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='v2_connection_origin_fixture_')
        self.addCleanup(temp.cleanup);self.base=Path(temp.name).resolve()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(m,'EXTERNAL',self.base))
        for module,name in ((m.preparation,'prepare_development_final_root_v2.py'),
                (m.builder,'build_development_final_root_v2.py'),
                (m.publisher,'publish_development_final_protocols_v2.py'),
                (m.bounded,'bounded_humble33_action.py')):
            (self.base/name).write_text('# tiny reviewed-origin fixture\n',encoding='utf-8')
            self.stack.enter_context(patch.object(module,'__file__',str(self.base/name)))
        for name in m.OWN:(self.base/name).write_text('# tiny own fixture\n',encoding='utf-8')
        for name in m.preparation.OWN:
            path=self.base/name
            if not path.exists():path.write_text('# tiny connection fixture\n',encoding='utf-8')
        def manifest():
            return {'fixture':'all five named connection byte hashes',
                'files':{name:m.sha(self.base/name) for name in m.preparation.OWN}}
        self.stack.enter_context(patch.object(m.preparation,'tool_manifest',side_effect=manifest))
        self.pin=m.canonical(manifest())
        self.stack.enter_context(patch.object(m,'CONNECTION_SHA',self.pin))

    def test_actual_tools_bind_five_file_connection_and_both_seal_files(self):
        value=m.tools()
        self.assertEqual(value['reviewed_connection_canonical_sha256'],self.pin)
        self.assertEqual(set(value['files']),set(m.OWN))
        self.assertTrue(all(name.endswith('_v2.py') for name in value['files']))

    def test_each_connection_file_tamper_and_v1_pin_refuse(self):
        for name in m.preparation.OWN:
            path=self.base/name;original=path.read_bytes()
            try:
                path.write_bytes(original+b'# changed\n')
                self.assertRaisesRegex(ValueError,'connection changed',m.tools)
            finally:path.write_bytes(original)
        with patch.object(m,'CONNECTION_SHA','1187d22d974889ea3f9ce36b787bc882b32fb05b0c6a2dad5acc715db4b8b269'):
            self.assertRaisesRegex(ValueError,'connection changed',m.tools)
        with patch.object(m,'CONNECTION_SHA',None):
            self.assertRaisesRegex(ValueError,'connection changed',m.tools)

    def test_imported_v1_publisher_origin_cannot_satisfy_v2_tools(self):
        old=self.base/'publish_development_final_protocols.py';old.write_text('# v1 fixture\n')
        with patch.object(m.publisher,'__file__',str(old)):
            self.assertRaisesRegex(ValueError,'origin differs',m.tools)


if __name__=='__main__':unittest.main()
