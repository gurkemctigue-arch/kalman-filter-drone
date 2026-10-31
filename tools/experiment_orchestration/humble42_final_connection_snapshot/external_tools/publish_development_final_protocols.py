"""Publish validated canonical registrations in one prepared independent root.

Describe is inert. Actual publication needs real build/gate/registrar evidence.
It never creates plans, a final source seal, capacity admission or formal flight.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

import prepare_development_final_root as preparation
import build_development_final_root as builder
import publish_humble28_final02_protocols01 as primitives

KIND='PARAMETERIZED_EXPLICIT_CANONICAL_PUBLICATION_REQUEST'
OUTCOME='PARAMETERIZED_CANONICAL_PUBLICATION_OUTCOME_NOT_ADMISSION'
PATHS=dict(zip(('core','extension','replay'),preparation.PLANNING))
require,sha,read,binding,write_new=preparation.require,preparation.sha,preparation.read,preparation.binding,preparation.write_new


class Inputs:
    def __init__(self):self.pins={}
    def bound(self,pin):
        require(Path(pin.get('path','')).suffix=='.json','Only explicit bounded JSON publication inputs required')
        require(Path(pin['path']).stat().st_size<=preparation.generic.MAX_SMALL,'Publication JSON exceeds metadata bound')
        value=preparation.checked(pin);self.pins[pin['path']]=pin['sha256'];return value
    def recheck(self):
        require(all(sha(path)==digest for path,digest in self.pins.items()),'Actual publication input changed')


def build_context(inputs,request):
    inputs.bound(request['copy_build'])
    context=builder.validate_completed_build(request['copy_build'])
    require(request.get('reviewed_tools_sha256')==preparation.canonical(preparation.tool_manifest()),
            'Explicit independently reviewed publication tool identity required')
    root=context['root'];protected=context['proposal']['expected_protected_file_hashes']
    for name in ('tools/reliability_v4_register.py','tools/reliability_v4_guard.py'):
        require(sha(root/name)==protected[name],'Actual frozen registrar/guard changed')
    tool=primitives.load_module('parameterized_final_registrar',root/'tools/reliability_v4_register.py')
    return context,tool


def pending(runtime,plan,path,root,mode,count):
    require(plan.get('mode')==mode and len(plan.get('trials',[]))==count and plan.get('frozen_root')==str(root),
            'Actual complete independently built target/formal plan required')
    if mode in ('PROBE','EXTENSION_PROBE'):
        require(plan.get('selected_seeds')==[4] and type(plan['selected_seeds'][0]) is int
                and plan.get('selected_classes')==list(runtime.v4.CLASSES)
                and plan.get('selected_groups')==(list(runtime.v4.GROUPS) if mode=='PROBE' else ['stage1_velocity','stage1_position'])
                and (mode=='PROBE' or plan.get('selected_extension_conditions')==list(runtime.v4.EXTENSION_CONDITIONS)),
                'Only untouched canonical complete12/16 seed4 target snapshots qualify')
    runtime.v4.validate_plan(plan,path);runtime.v4.verify_sources(plan)
    rows=runtime.v4.read_slots(plan)
    require(set(rows)=={trial['id'] for trial in plan['trials']} and all(row['status']=='PENDING' for row in rows.values()),
            'Every original target/formal slot must remain untouched PENDING')
    require(not any(Path(trial['directory']).exists() or Path(trial['directory']).is_symlink() for trial in plan['trials']),
            'Target/formal trial products already exist')


def require_all_original_pass(inputs,runtime,gate,context,*,extensions):
    """Add this batch's stricter 28-PASS rule after the normal gate validator.

    The original gate legitimately permits disclosed extension algorithm failures.
    This connection cannot promote those or reevaluated original FAIL records.
    """
    slots=gate.get('probe_slots');count=16 if extensions else 12
    require(isinstance(slots,list) and len(slots)==count and all(isinstance(item,dict) for item in slots),
            'Actual complete original12/16 gate slots required')
    if extensions:
        require(gate.get('known_algorithm_failures')==[],'Original16 must have no disclosed algorithm failures')
    paths={item.get('plan_path') for item in slots}
    require(len(paths)==1 and None not in paths,'One original canonical12/16 source plan required')
    path=next(iter(paths));digests={item.get('plan_file_sha256') for item in slots}
    require(len(digests)==1,'Every original slot must bind the same actual source plan bytes')
    previous=inputs.bound({'path':path,'sha256':next(iter(digests))})
    require(previous.get('mode')==('EXTENSION_PROBE' if extensions else 'PROBE')
            and previous.get('frozen_root')==context['proposal']['source_root']
            and previous.get('source_hashes')==context['proposal']['expected_classified_source_hashes']
            and previous.get('selected_seeds')==[4] and type(previous['selected_seeds'][0]) is int
            and previous.get('selected_classes')==list(runtime.v4.CLASSES)
            and previous.get('selected_groups')==(['stage1_velocity','stage1_position'] if extensions else list(runtime.v4.GROUPS))
            and (not extensions or previous.get('selected_extension_conditions')==list(runtime.v4.EXTENSION_CONDITIONS))
            and len(previous.get('trials',[]))==count,'Actual original same-source canonical12/16 matrix required')
    runtime.v4.validate_plan(previous,path)
    trials={trial['id']:trial for trial in previous['trials']}
    require(len(trials)==count and len({item.get('slot_id') for item in slots})==count
            and {item.get('slot_id') for item in slots}==set(trials),'Every original source slot must occur exactly once')
    # Normal gate validation already checks all registered artifacts/evaluators.
    # Reread the immutable original records without a second payload hash pass.
    rows=runtime.v4.read_slots(previous,verify_artifacts=False)
    require(set(rows)==set(trials),'Original terminal record denominator differs')
    for item in slots:
        trial=trials[item['slot_id']];record=rows[item['slot_id']]
        actual=inputs.bound({'path':str(Path(runtime.v4.record_path(previous,trial)).resolve(strict=True)),
            'sha256':item.get('record_file_sha256')})
        require(actual==record and record.get('status')==record.get('engineering_result')=='PASS'
                and record.get('execution_status')=='COMPLETED' and record.get('infrastructure_stop') is False
                and type(record.get('flight_exit_code')) is int and record['flight_exit_code']==0,
                'Every original development record must itself be PASS: '+item['slot_id'])
        require(not item.get('evaluation_overrides'),'Unchanged-source gate must retain its original evaluations')


def prepare_protocols(inputs,request,context,tool):
    builder.source_check(context)
    root=context['root'];core=inputs.bound(request['target_plans']['core']);extension=inputs.bound(request['target_plans']['extension'])
    core_gate=inputs.bound(request['gates']['core']);extension_gate=inputs.bound(request['gates']['extension'])
    expected=context['proposal']['expected_classified_source_hashes']
    require(core.get('frozen_root')==extension.get('frozen_root')==str(root)
            and core.get('source_hashes')==extension.get('source_hashes')==expected,'Targets differ from actual independent final source')
    runtime,safety_context=tool.gate_context(request['target_plans']['core']['path'],request['gates']['core']['path'])
    pending(runtime,core,request['target_plans']['core']['path'],root,'PROBE',12)
    pending(runtime,extension,request['target_plans']['extension']['path'],root,'EXTENSION_PROBE',16)
    require(runtime.v4.flight_source_hashes(expected)==context['proposal']['flight_source_hashes'],'Actual flight-source map differs')
    for gate in (core_gate,extension_gate):tool.guard.no_fixture(gate,'Actual development gate')
    originals={name:(root/PATHS[name]).read_bytes() for name in ('core','extension')}
    old_core,old_extension=(read(root/PATHS[name]) for name in ('core','extension'))
    require(old_core['status']==old_extension['status']==preparation.DRAFT
            and old_core==core['protocol'] and old_extension==extension['extension_protocol_binding']['protocol'],
            'Actual unchanged DRAFT target protocols required')
    stamp=preparation.generic.utc()
    changed_core={**old_core,'status':'REGISTERED','registration_utc':stamp}
    changed_extension={**old_extension,'status':'REGISTERED','registration_utc':stamp,
        'development_readiness':{**request['gates']['extension'],'evidence':extension_gate}}
    runtime.v4.validate_protocol(changed_core);runtime.v4.validate_navigation_gates(changed_core['navigation_acceptance'])
    runtime.v4.validate_extension_protocol(changed_extension,changed_core,formal=True)
    test_plan=deepcopy(extension);test_plan['protocol']=changed_core
    test_plan['extension_protocol_binding']['protocol']=changed_extension
    runtime.v4.validate_probe_gate(test_plan,extensions=True)
    require_all_original_pass(inputs,runtime,core_gate,context,extensions=False)
    require_all_original_pass(inputs,runtime,extension_gate,context,extensions=True)
    summary_pin,summary,used=primitives.assembly(inputs,request['safety_assembly'],'safety-summary',tool)
    require(used['target_plan']==request['target_plans']['core'] and used['core_gate']==request['gates']['core'],
            'Actual safety assembly must bind these exact pre-registration target/gate inputs')
    safety_context.core['protocol']=changed_core
    safety_context.registration_times=[tool.guard.utc(stamp),tool.guard.utc(stamp)]
    tool.guard.validate_safety({'safety':summary_pin},safety_context,runtime)
    require(tool.guard.utc(summary['created_utc'])<=tool.guard.utc(stamp),'Actual safety summary must precede registration')
    candidates={'core':primitives.patch_fields(originals['core'],{'status':'REGISTERED','registration_utc':stamp}),
        'extension':primitives.patch_fields(originals['extension'],{key:changed_extension[key]
            for key in ('status','registration_utc','development_readiness')})}
    require(json.loads(candidates['core'])==changed_core and json.loads(candidates['extension'])==changed_extension,
            'Staged canonical bytes differ from normal validators')
    return runtime,originals,candidates


def prepare_replay(inputs,request,context,tool):
    publication=inputs.bound(request['protocol_publication']);root=context['root']
    require(publication.get('kind')==OUTCOME and publication.get('action')=='protocols'
            and publication.get('status')=='PUBLISHED_NOT_ADMITTED' and publication.get('copy_build')==request['copy_build'],
            'Actual successful canonical core/extension publication required')
    allowed={PATHS[name]:publication['published'][name] for name in ('core','extension')}
    builder.source_check(context,allowed)
    core,extension=(inputs.bound(request['formal_plans'][name]) for name in ('core','extension'))
    formal=tool.guard.read_plans({'plans':request['formal_plans'],'final_root':str(root)})
    runtime=tool.guard.load_runtime(root,core)
    pending(runtime,core,request['formal_plans']['core']['path'],root,'FORMAL',120)
    pending(runtime,extension,request['formal_plans']['extension']['path'],root,'EXTENSION_FORMAL',160)
    require(core['source_hashes']==extension['source_hashes']==context['proposal']['expected_classified_source_hashes']
            and runtime.v4.flight_source_hashes(core['source_hashes'])==context['proposal']['flight_source_hashes'],
            'Actual formal plans differ from the independent final-root flight map')
    pin,candidate,used=primitives.assembly(inputs,request['replay_assembly'],'replay-config',tool)
    require(used['core_plan']==request['formal_plans']['core'],'Actual replay registrar bound another formal core')
    runtime.replay.validate_registered_config(candidate);runtime.replay.verify_registration_artifacts(candidate,source_root=root)
    require(candidate['freeze_requirements']['final_engineering_plan_path']==request['formal_plans']['core']['path']
            and candidate['freeze_requirements']['final_engineering_plan_file_sha256']==request['formal_plans']['core']['sha256']
            and candidate['freeze_requirements']['final_engineering_plan_digest']==core['plan_sha256'],
            'Actual replay candidate does not bind the untouched formal core')
    formal.replay_configuration=candidate
    formal.registration_times=[tool.guard.utc(core['protocol']['registration_utc']),
        tool.guard.utc(extension['extension_protocol_binding']['protocol']['registration_utc']),
        tool.guard.utc(candidate['registration']['registered_utc'])]
    tool.guard.validate_development({'calibration':used['candidate']},formal,runtime)
    original=(root/PATHS['replay']).read_bytes()
    require(read(root/PATHS['replay'])['status']==preparation.DRAFT,'Cannot replace a registered replay configuration')
    return runtime,{'replay':original},{'replay':Path(pin['path']).read_bytes()}


def publish(action,request_pin):
    preparation.generic.require_linux()
    require(os.environ.get('WSL_DISTRO_NAME')=='UAVHumble22','Actual isolated Humble environment required')
    inputs=Inputs();request=inputs.bound(request_pin)
    common={'schema_version','kind','action','copy_build','expected_canonical_sha256','reviewed_tools_sha256'}
    extra={'target_plans','gates','safety_assembly'} if action=='protocols' else {'protocol_publication','formal_plans','replay_assembly'}
    require(type(request.get('schema_version')) is int and request['schema_version']==1 and request.get('kind')==KIND
            and request.get('action')==action and set(request)==common|extra,'Exact explicit canonical publication request required')
    context,tool=build_context(inputs,request);root,results=context['root'],context['results']
    names=('core','extension') if action=='protocols' else ('replay',)
    require(set(request['expected_canonical_sha256'])==set(names),'Every original canonical SHA must be explicit')
    output=results/'freeze_validation'/('canonical_'+action+'_publication_development01')
    require(not output.exists() and not output.is_symlink(),'One-shot canonical publication; retry/resume forbidden')
    runtime,originals,candidates=(prepare_protocols if action=='protocols' else prepare_replay)(inputs,request,context,tool)
    require(not runtime.v4.simulation_processes(),'Canonical publication requires idle runtime')
    for name in names:
        require(hashlib.sha256(originals[name]).hexdigest()==request['expected_canonical_sha256'][name]
                ==context['proposal']['draft_planning_hashes'][PATHS[name]],'Actual original DRAFT SHA differs')
    inputs.recheck();output.mkdir()
    write_new(output/'started.json',{'schema_version':1,'kind':OUTCOME,'action':action,'request':request_pin,
        'copy_build':request['copy_build'],'publisher':binding(__file__),'created_utc':preparation.generic.utc()})
    published={}
    try:
        with runtime.v4.run_lock(output):
            require(not runtime.v4.simulation_processes(),'Runtime appeared before publication lock')
            for name in names:
                require(sha(root/PATHS[name])==request['expected_canonical_sha256'][name],'Canonical changed before original backup')
                primitives.write_bytes_new(output/(name+'.original.json'),originals[name])
                staged=root/'planning'/('.publisher-development-'+action+'-'+name+'.json')
                primitives.write_bytes_new(staged,candidates[name])
                os.chmod(staged,stat.S_IMODE((root/PATHS[name]).stat().st_mode))
                require(staged.read_bytes()==candidates[name],'Actual staged bytes differ')
            inputs.recheck()
            for name in names:
                target=root/PATHS[name]
                require(sha(target)==request['expected_canonical_sha256'][name],'Canonical changed before atomic publication')
                write_new(output/(name+'_publish_intent.json'),{'canonical':str(target),'created_utc':preparation.generic.utc()})
                os.replace(root/'planning'/('.publisher-development-'+action+'-'+name+'.json'),target)
                require(target.read_bytes()==candidates[name],'Published bytes differ')
                published[name]=binding(target);write_new(output/(name+'_published.json'),published[name])
        outcome={'schema_version':1,'kind':OUTCOME,'action':action,'status':'PUBLISHED_NOT_ADMITTED',
            'finished_utc':preparation.generic.utc(),'copy_build':request['copy_build'],'request':request_pin,'published':published,
            'preparation_manifest_retained':context['outcome']['preparation_source_manifest'],
            'formal_attempts_started':0,'plans_created':False,'final_source_seal_created':False,
            'capacity_admission_performed':False,'formal_seed_use_authorized':False}
        write_new(output/'outcome.json',outcome)
        return outcome
    except BaseException as error:
        write_new(output/'failed.json',{'kind':OUTCOME,'status':'STOPPED_RETAIN_PARTIAL_PUBLICATION_NO_RETRY',
            'error':type(error).__name__+':'+str(error),'published_receipts':published,'rollback_attempted':False,
            'preserve_all_original_backups':True,'formal_seed_use_authorized':False})
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('describe','protocols','replay'),nargs='?',default='describe')
    parser.add_argument('--request',type=Path);parser.add_argument('--request-sha256');args=parser.parse_args(argv)
    if args.action=='describe':
        manifest=preparation.tool_manifest();print(json.dumps({'manifest':manifest,'sha256':preparation.canonical(manifest),
            'actual_publication_executed':False,'default_final_root':None}));return 0
    require(args.request is not None and preparation.generic.valid_sha(args.request_sha256),'Explicit actual publication request/SHA required')
    publish(args.action,{'path':str(args.request),'sha256':args.request_sha256});return 0


if __name__=='__main__':raise SystemExit(main())
