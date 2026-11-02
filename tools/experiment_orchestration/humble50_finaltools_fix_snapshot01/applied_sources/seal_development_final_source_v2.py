"""Seal final whole-source/planning bytes, then optionally call the real registrar.

No default root, inferred readiness, invented budget or formal flight. The old
guard does not consume this whole-tree manifest; root rechecks it before serial
execution while the unchanged guard retains its own per-slot authority.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import datetime
import json
import os
from pathlib import Path
import sys

import prepare_development_final_root_v2 as preparation
import build_development_final_root_v2 as builder
import publish_development_final_protocols_v2 as publisher
import bounded_humble33_action as bounded

require,sha,read,binding,checked,write_new,canonical=(preparation.require,preparation.sha,preparation.read,
    preparation.binding,preparation.checked,preparation.write_new,preparation.canonical)
EXTERNAL=preparation.EXTERNAL
CONNECTION_SHA='e8585f14ece45335f24614a1794bedf1c205503a90cf587060ed25851c0bd0c9'
OWN=('seal_development_final_source_v2.py','test_seal_development_final_source_v2.py')
KIND='INDEPENDENT_FINAL_WHOLE_SOURCE_AND_PLANNING_MANIFEST_V2'
NAME='final_source_planning_manifest_development_v2_01.json'
SEAL_KIND='WHOLE_SOURCE_BOUND_REAL_REGISTRAR_SEAL_OUTCOME_V2'
SEAL_ATTEMPT='final_source_admission_seal_development_v2_01'
ASSEMBLY='final_admission_assembly_development_v2_01'
STORAGE_FIELDS={'volumes','results_volume','vhd_host','temporary_peak_bytes','temporary_bound_rule',
    'delivery_reservations','additional_remaining_bytes','cells'}


def tools():
    for module,name in ((preparation,'prepare_development_final_root_v2.py'),(builder,'build_development_final_root_v2.py'),
            (publisher,'publish_development_final_protocols_v2.py'),(bounded,'bounded_humble33_action.py')):
        require(Path(module.__file__).resolve(strict=True)==EXTERNAL/name,'Actual imported final-seal helper origin differs')
    require(preparation.generic.valid_sha(CONNECTION_SHA) and canonical(preparation.tool_manifest())==CONNECTION_SHA,'Independently reviewed source/build/publication connection changed')
    return {'schema_version':1,'kind':KIND,'files':{name:binding(EXTERNAL/name)['sha256'] for name in OWN},
        'reviewed_connection_canonical_sha256':CONNECTION_SHA,'original_guard_consumes_whole_tree_manifest':False,
        'default_root_or_request':None,'automatic_next_action':False,'formal_seed_use_authorized':False}


def require_tools(digest):
    require(preparation.generic.valid_sha(digest) and digest==canonical(tools()),'Explicit independently reviewed final-source tools required')


def fixed_publication(inputs,pin,action,context,copy_build):
    value=inputs.bound(pin);root,results=context['root'],context['results']
    directory=results/'freeze_validation'/('canonical_'+action+'_publication_development_v2_01')
    names=('core','extension') if action=='protocols' else ('replay',)
    require(pin==binding(directory/'outcome.json') and type(value.get('schema_version')) is int and value['schema_version']==1
            and value.get('kind')==publisher.OUTCOME
            and value.get('action')==action and value.get('status')=='PUBLISHED_NOT_ADMITTED'
            and value.get('copy_build')==copy_build and set(value.get('published',{}))==set(names)
            and value.get('preparation_manifest_retained')==context['outcome']['preparation_source_manifest']
            and type(value.get('formal_attempts_started')) is int and value['formal_attempts_started']==0
            and all(value.get(key) is False for key in ('plans_created','final_source_seal_created',
                'capacity_admission_performed','formal_seed_use_authorized')),'Actual fixed canonical publication outcome required')
    request=inputs.bound(value['request']);started=inputs.bound(binding(directory/'started.json'))
    common={'schema_version','kind','action','copy_build','expected_canonical_sha256','reviewed_tools_sha256'}
    extra={'target_plans','gates','safety_assembly'} if action=='protocols' else {'protocol_publication','formal_plans','replay_assembly'}
    require(set(request)==common|extra and type(request.get('schema_version')) is int and request['schema_version']==1
            and request.get('kind')==publisher.KIND and request.get('action')==action
            and request.get('copy_build')==copy_build and request.get('reviewed_tools_sha256')==CONNECTION_SHA
            and set(request.get('expected_canonical_sha256',{}))==set(names)
            and started.get('kind')==publisher.OUTCOME and started.get('action')==action
            and started.get('request')==value['request'] and started.get('copy_build')==copy_build
            and started.get('publisher')==binding(publisher.__file__),'Original publication request/start binding differs')
    for name in names:
        target=root/publisher.PATHS[name];published=inputs.bound(value['published'][name])
        backup=binding(directory/(name+'.original.json'))
        require(value['published'][name]==binding(target) and published.get('status')=='REGISTERED'
                and request['expected_canonical_sha256'][name]==context['proposal']['draft_planning_hashes'][publisher.PATHS[name]]
                ==backup['sha256'],'Canonical publication or original DRAFT backup differs')
        require(inputs.bound(binding(directory/(name+'_published.json')))==value['published'][name]
                and inputs.bound(binding(directory/(name+'_publish_intent.json'))).get('canonical')==str(target),
                'Actual canonical publication intent/receipt differs')
    return value,request,directory


def require_untouched_formal(formal):
    """This sidecar is deliberately a prestart seal, never a post-hoc freeze."""
    for plan,count in ((formal.core,120),(formal.extension,160)):
        require(len(plan.get('trials',[]))==count,'Both complete original formal matrices required')
        for trial in plan['trials']:
            products=(Path(trial['directory']),Path(plan['output'])/'slots'/(trial['id']+'.json'),
                Path(plan['output'])/'slots'/(trial['id']+'.started.json'))
            require(not any(path.exists() or path.is_symlink() for path in products),
                    'Final whole-source sidecar requires all280 untouched PENDING; original formal products exist')


def publication_context(inputs,pins):
    require(set(pins)=={'copy_build','protocol_publication','replay_publication'},'Three exact original evidence pins required')
    context,tool=publisher.build_context(inputs,{'copy_build':pins['copy_build'],'reviewed_tools_sha256':CONNECTION_SHA})
    protocols,protocol_request,protocol_directory=fixed_publication(inputs,pins['protocol_publication'],'protocols',context,pins['copy_build'])
    replay,replay_request,_=fixed_publication(inputs,pins['replay_publication'],'replay',context,pins['copy_build'])
    require(replay_request.get('protocol_publication')==pins['protocol_publication'],'Replay publication binds another first publication')
    root=context['root'];allowed={publisher.PATHS[name]:protocols['published'][name] for name in ('core','extension')}
    allowed[publisher.PATHS['replay']]=replay['published']['replay']
    # Derive permitted mutations from the real receipts, never an input allowlist.
    core,extension=(read(root/publisher.PATHS[name]) for name in ('core','extension'))
    stamp=core.get('registration_utc')
    require(isinstance(stamp,str) and extension.get('registration_utc')==stamp,'Actual core/extension registration times differ')
    require(extension.get('development_readiness')=={**protocol_request['gates']['extension'],
        'evidence':inputs.bound(protocol_request['gates']['extension'])},'Registered extension differs from its original gate input')
    for name,fields in [('core',{'status':'REGISTERED','registration_utc':stamp}),
            ('extension',{'status':'REGISTERED','registration_utc':stamp,'development_readiness':extension['development_readiness']})]:
        original=(protocol_directory/(name+'.original.json')).read_bytes()
        require(publisher.primitives.patch_fields(original,fields)==(root/publisher.PATHS[name]).read_bytes(),
                'Canonical protocol changed beyond the original published registration fields: '+name)
    safety_pin,_,safety_used=publisher.primitives.assembly(inputs,protocol_request['safety_assembly'],'safety-summary',tool)
    require(safety_used.get('target_plan')==protocol_request['target_plans']['core']
            and safety_used.get('core_gate')==protocol_request['gates']['core'],'Original safety assembly target/gate binding differs')
    replay_pin,replay_value,replay_used=publisher.primitives.assembly(inputs,replay_request['replay_assembly'],'replay-config',tool)
    require(Path(replay_pin['path']).read_bytes()==(root/publisher.PATHS['replay']).read_bytes()
            and replay_used.get('core_plan')==replay_request['formal_plans']['core'],
            'Canonical replay is not the actual validated registrar candidate bytes')
    formal=tool.guard.read_plans({'plans':replay_request['formal_plans'],'final_root':str(root)})
    require_untouched_formal(formal)
    expected=context['proposal']['expected_classified_source_hashes']
    require(formal.core['source_hashes']==formal.extension['source_hashes']==expected
            and formal.core['model_hashes']==formal.extension['model_hashes']=={name:digest for name,digest in expected.items() if name.endswith('.pt')},
            'Formal source/model maps differ from the actual independent final root')
    require(replay_value['freeze_requirements']['final_engineering_plan_path']==replay_request['formal_plans']['core']['path']
            and replay_value['freeze_requirements']['final_engineering_plan_file_sha256']==replay_request['formal_plans']['core']['sha256']
            and replay_value['freeze_requirements']['final_engineering_plan_digest']==formal.core['plan_sha256'],
            'Canonical replay binds another formal core file/digest')
    for name,pin in replay_request['formal_plans'].items():inputs.bound(pin)
    for name,pin in protocol_request['target_plans'].items():inputs.bound(pin)
    inputs.bound(protocol_request['gates']['core']);inputs.bound(replay_used['candidate'])
    return context,tool,allowed,{'protocols':protocols,'replay':replay,'formal_plans':replay_request['formal_plans'],
        'formal':formal,'safety':safety_pin,'calibration':replay_used['candidate']}


def source_facts(pins):
    inputs=publisher.Inputs();context,tool,allowed,evidence=publication_context(inputs,pins)
    verified=builder.source_check(context,allowed)
    final_inventory=deepcopy(context['proposal']['expected_whole_tree_inventory'])
    protected=dict(context['proposal']['expected_protected_file_hashes'])
    for name,pin in allowed.items():
        final_inventory[name]['sha256']=pin['sha256'];final_inventory[name]['bytes']=(context['root']/name).stat().st_size
        protected[name]=pin['sha256']
    require(canonical(final_inventory)==verified['whole_tree_inventory_sha256'],'Actual final whole inventory differs')
    inputs.recheck()
    core,extension=evidence['formal'].core,evidence['formal'].extension
    runtime_fields=('magnetic_runtime_binding','magnetic_library_binding')
    require(all(core.get(name)==extension.get(name) for name in runtime_fields),'Actual formal runtime/model declarations differ')
    facts={'schema_version':1,'kind':KIND,'final_root':str(context['root']),'results_root':str(context['results']),
        'inputs':pins,'producer_tools':tools(),'reviewed_connection_canonical_sha256':CONNECTION_SHA,
        'original_preparation_manifest':context['outcome']['preparation_source_manifest'],
        'candidate_manifest':context['proposal']['candidate_manifest'],'candidate_source_review':context['proposal']['source_review'],
        'original_candidate_source_manifest':context['proposal']['original_source_manifest'],
        'strict512_source_build':context['proposal']['strict512_source_build'],
        'cold_build_runtime_preflight':binding(context['attempt']/'runtime_preflight.json'),
        'original_whole_tree_inventory_sha256':canonical(context['proposal']['original_whole_tree_inventory']),
        'final_whole_tree_inventory':final_inventory,'final_protected_file_hashes':protected,
        'canonical_planning':{name:allowed[publisher.PATHS[name]] for name in publisher.PATHS},
        'classified_source_hashes':context['proposal']['expected_classified_source_hashes'],
        'flight_source_hashes':context['proposal']['flight_source_hashes'],'source_verification':verified,
        'model_hashes':core['model_hashes'],'source_runtime':context['review']['runtime'],
        'formal_runtime_bindings':{name:core[name] for name in runtime_fields},
        'formal_plans':evidence['formal_plans'],'actual_safety_summary':evidence['safety'],'actual_development_calibration':evidence['calibration'],
        'original_guard_consumes_whole_tree_manifest':False,'formal_attempts_started':0,
        'initial_admission_performed':False,'capacity_admission_performed':False,'formal_seed_use_authorized':False}
    return facts,context,tool,evidence


def verify_manifest(pin,tools_sha):
    require_tools(tools_sha);value=checked(pin)
    require(type(value.get('schema_version')) is int and value['schema_version']==1
            and value.get('kind')==KIND and isinstance(value.get('inputs'),dict),'Actual final source/planning manifest required')
    facts,context,tool,evidence=source_facts(value['inputs'])
    require(pin==binding(context['results']/'freeze_validation'/NAME),'Actual manifest must remain at its original final results path')
    stamp=value.get('created_utc')
    require(isinstance(stamp,str),'Original source/planning manifest timestamp required')
    parsed=datetime.datetime.fromisoformat(stamp)
    require(parsed.tzinfo is not None and parsed<=datetime.datetime.now(datetime.timezone.utc),'Invalid/future final-source manifest timestamp')
    require(value==dict(facts,created_utc=stamp),'Final source/planning manifest changed or actual source/evidence differs')
    return value,context,tool,evidence


def create_manifest(pins,tools_sha):
    require_tools(tools_sha)
    with preparation.generic.exclusive_window():
        facts,context,_,_=source_facts(pins);path=context['results']/'freeze_validation'/NAME
        require(not path.exists() and not path.is_symlink(),'One immutable new final source/planning manifest; no overwrite or retry')
        write_new(path,dict(facts,created_utc=preparation.generic.utc()))
        pin=binding(path);verify_manifest(pin,tools_sha)
    return pin


def admission_request(inputs,pin,value,context,tool,evidence):
    request=inputs.bound(pin)
    require(set(request)==tool.REQUEST_FIELDS and type(request.get('schema_version')) is int and request['schema_version']==1
            and request.get('kind')=='RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST'
            and request.get('final_root')==str(context['root']) and request.get('plans')==value['formal_plans']
            and request.get('registrations')==value['canonical_planning']
            and request.get('calibration')==evidence['calibration'] and request.get('safety')==evidence['safety'],
            'Exact original admission request must bind this final source, plans and registrations')
    storage=request.get('storage')
    require(isinstance(storage,dict) and set(storage)==STORAGE_FIELDS and isinstance(storage['volumes'],list)
            and storage['volumes'] and isinstance(storage['cells'],list) and len(storage['cells'])==28
            and isinstance(storage['delivery_reservations'],dict) and set(storage['delivery_reservations'])==set(tool.guard.DELIVERIES),
            'Actual explicit complete physical storage/budget fields required; no generated defaults')
    state=Path(request.get('state_directory',''))
    require(state.is_absolute() and not state.is_symlink() and state.resolve()==state
            and state.is_relative_to(context['results']) and state!=context['results']
            and not state.exists(),'Actual first admission requires an untouched independent state path')
    return request


def seal_admission(manifest_pin,request_pin,tools_sha):
    require_tools(tools_sha)
    require(os.environ.get('WSL_DISTRO_NAME')=='UAVHumble22' and Path(sys.executable)==builder.primitives.VENV_PYTHON,
            'Use the actual isolated Humble virtual-environment Python')
    with preparation.generic.exclusive_window():
        value,context,tool,evidence=verify_manifest(manifest_pin,tools_sha)
        inputs=publisher.Inputs();inputs.bound(manifest_pin)
        request=admission_request(inputs,request_pin,value,context,tool,evidence)
        runtime=tool.guard.load_runtime(context['root'],evidence['formal'].core)
        require(not runtime.v4.simulation_processes(),'Actual source/admission seal requires an idle runtime')
        directory=context['results']/'freeze_validation'/SEAL_ATTEMPT;owner=directory.with_name(SEAL_ATTEMPT+'_owner')
        assembly=directory.with_name(ASSEMBLY)
        require(not any(path.exists() or path.is_symlink() for path in (directory,owner,assembly)),
                'Exclusive new outer/owner/registrar directories required; no retry')
        command=[str(builder.primitives.VENV_PYTHON),'-B',str(context['root']/'tools/reliability_v4_register.py'),
            'seal','--request',request_pin['path'],'--output-directory',str(assembly)]
        directory.mkdir()
        write_new(directory/'started.json',{'kind':SEAL_KIND,'created_utc':preparation.generic.utc(),'manifest':manifest_pin,
            'request':request_pin,'tools':tools(),'command':command,'formal_seed_use_authorized':False})
        def closure(_phase):
            checked(request_pin);current,_,_,_=verify_manifest(manifest_pin,tools_sha)
            return {'whole_manifest':manifest_pin,'whole_inventory_sha256':current['source_verification']['whole_tree_inventory_sha256'],
                'request':request_pin,'tools':tools(),'formal_seed_use_authorized':False}
        try:
            terminal=bounded.run_bounded(command,owner,action='final-source-admission-seal',
                timeout_s=preparation.generic.ACTIONS['validate'],grace_s=30.,kill_confirm_s=5.,binding=closure)
            require(terminal.get('status')=='PASS','Actual registrar seal failed; retain all original evidence without retry')
            artifact,admission,used=publisher.primitives.assembly(inputs,binding(assembly/'outcome.json'),'seal',tool)
            outcome=read(assembly/'outcome.json')
            guard_check=outcome.get('detail',{}).get('guard_check',{})
            require(artifact==binding(assembly/'final_admission.json') and used=={'request':request_pin}
                    and admission.get('kind')=='RELIABILITY_V4_FORMAL_ADMISSION'
                    and admission.get('schema_version')==1 and admission.get('manifest_sha256')==tool.guard.sealed(admission,'manifest_sha256')
                    and admission.get('tool')==binding(tool.guard.__file__)
                    and all(admission.get(key)==data for key,data in request.items() if key not in {'schema_version','kind'})
                    and guard_check.get('result')=='PASS' and guard_check.get('capacity',{}).get('pending_slots')==280
                    and guard_check.get('manifest',{}).get('sha256')==artifact['sha256']
                    and guard_check.get('manifest_sha256')==admission['manifest_sha256'] and guard_check.get('tool')==admission['tool']
                    and outcome['detail'].get('claim')=='ADMISSION_CHECK_ONLY_NO_INITIAL_ADMISSION_OR_FLIGHT'
                    and outcome['detail'].get('guard_state_created') is False
                    and not Path(request['state_directory']).exists(),'Actual complete original registrar/guard seal evidence differs')
            inputs.recheck()
            result={'schema_version':1,'kind':SEAL_KIND,'status':'ACTUAL_REGISTRAR_SEAL_BOUND_TO_WHOLE_SOURCE_NO_FLIGHT',
                'created_utc':preparation.generic.utc(),'whole_source_manifest':manifest_pin,'original_request':request_pin,
                'registrar_outcome':binding(assembly/'outcome.json'),'actual_admission_manifest':artifact,
                'bounded_terminal':binding(owner/'action.terminal.json'),'binding_before':terminal['binding_before'],
                'binding_after':terminal['binding_after'],'tools':tools(),'formal_attempts_started':0,
                'initial_admission_performed':False,'formal_seed_use_authorized':False,
                'whole_manifest_recheck_required_before_formal_serial_start':True,
                'original_guard_consumes_whole_tree_manifest':False}
            write_new(directory/'outcome.json',result);return result
        except BaseException as error:
            write_new(directory/'failed.json',{'kind':SEAL_KIND,'status':'FAILED_RETAIN_ALL_ORIGINAL_EVIDENCE_NO_RETRY',
                'error':type(error).__name__+':'+str(error),'formal_seed_use_authorized':False})
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('describe','create','verify','seal-admission'),nargs='?',default='describe')
    for name in ('copy-build','protocol-publication','replay-publication','manifest','request'):
        parser.add_argument('--'+name,type=Path);parser.add_argument('--'+name+'-sha256')
    parser.add_argument('--reviewed-tools-sha256');args=parser.parse_args(argv)
    if args.action=='describe':
        manifest=tools();print(json.dumps({'manifest':manifest,'sha256':canonical(manifest),'actual_action_executed':False}));return 0
    preparation.development_build.resource.require_linux();require_tools(args.reviewed_tools_sha256)
    def pin(name):
        path=getattr(args,name);digest=getattr(args,name+'_sha256')
        require(path is not None and preparation.generic.valid_sha(digest),'Explicit original '+name+' path/SHA required')
        return {'path':str(path),'sha256':digest}
    if args.action=='create':
        result=create_manifest({name:pin(name) for name in ('copy_build','protocol_publication','replay_publication')},args.reviewed_tools_sha256)
    elif args.action=='verify':
        original=pin('manifest');verify_manifest(original,args.reviewed_tools_sha256)
        result={'manifest':original,'source_verified':True,'admission_performed':False}
    else:result=seal_admission(pin('manifest'),pin('request'),args.reviewed_tools_sha256)
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
