"""Retain closed32 base evidence only; never read bags or start project work."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
ORIGINAL_ROOT = Path('/root/uav_tracking_fullplan_v4_humble32')
ORIGINAL_RESULTS = Path('/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/frozen_fullplan_v4_humble32')
BASE = EXTERNAL/'humble33_original32_base_snapshot01.json'
CORE = 'results/reliability_v4_humble32_probe01_seed004_matrix'
CLEAN = 'results/reliability_v4_humble32_clean20_serial01'
SOURCE_COMMIT = 'b1a2e04ab9e8fdfba86c7477339cf3edda98a035'
SOURCE_SHA = '8f0e4f9b8d31fa6fe088ce28c64378c144c4a4bc903aa7a5063cfa5d1d2cbc84'
REVIEW_SHA = 'cff125384e83e89b0b37fb29e355d5f93ebda9fd201d770309488a377d735069'
SCOPE = 'ORIGINAL32_CLOSED_BASE_ONLY_NO_CORE_ADMISSION'


def require(condition,message):
    if not condition: raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sha(path):
    path=Path(path)
    require(path.suffix in {'.json','.yaml','.log','.py','.sh','.md'} and path.is_file()
        and not path.is_symlink() and path.stat().st_size<=16*1024*1024,'Bounded closed metadata/code only; no payload hashing')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    sha(path)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe(name):
    require(isinstance(name,str) and bool(name) and '\\' not in name and ':' not in name
        and not PurePosixPath(name).is_absolute() and all(p not in {'','.','..'} for p in name.split('/')),
        'Unsafe closed-evidence relative path')
    return name


def artifact(root,results,name):
    safe(name)
    return Path(results)/name[8:] if name.startswith('results/') else Path(root)/name


def base_names():
    names={'results/freeze_validation/'+name for name in (
        'source_freeze_manifest.json','humble32_final_source_review.json','build_validation_summary.json',
        'build_environment.json','fastcdr_provenance.json','generated_message_roundtrip.json',
        'import_isolation.json','unittest.started.json','unittest.log','colcon_build.log')}
    names.update(CLEAN+'/'+name for name in ('setup.json','execution_terminal.json',
        'person_started.json','person_terminal.json','car_started.json','car_terminal.json'))
    for cls in ('person','car'):
        names.update(CLEAN+'/'+cls+'_evaluation01/'+name for name in (
            'px4_source_clock_evaluation.json','native_startup_evaluation.json',
            'navigation_reference_evaluation.json','surface_flight_evaluation.json'))
        trial='results/reliability_v4_humble32_clean20_01_'+cls+'_velocity_seed004/'
        names.update(trial+name for name in ('run_config.json','summary.json','bag_integrity.json',
            'recording_closure.json','recording_closure_observer.json','process_exit_codes.json',
            'graph_startup_readiness.json','configuration/source_sha256.json',
            'configuration/runtime_parameters.yaml','configuration/ros_gz_runtime_after.json'))
    return names


def facts(root,results):
    get=lambda name:read(artifact(root,results,name))
    manifest=get('results/freeze_validation/source_freeze_manifest.json')
    review=get('results/freeze_validation/humble32_final_source_review.json')
    require(sha(artifact(root,results,'results/freeze_validation/humble32_final_source_review.json'))==REVIEW_SHA
        and manifest.get('source_commit')==review.get('source_commit')==SOURCE_COMMIT
        and len(manifest.get('files',{}))==597 and manifest['files']==review.get('files')
        and manifest.get('freeze_source_sha256')==review.get('source_canonical_sha256')==SOURCE_SHA
        and canonical(manifest['files'])==SOURCE_SHA,'Original32 reviewed source map differs')
    built=get('results/freeze_validation/build_validation_summary.json')
    require(built.get('status')=='PASS' and type(built.get('returncode')) is int and built['returncode']==0
        and built.get('tests')==1537 and built.get('skipped')==5 and built.get('source_unchanged') is True
        and all(built.get('original'+str(n)+'_unchanged') is True for n in (28,29,30,31))
        and built.get('formal_seeds_consumed') is False,'Original32 build outcome differs')
    terminal=get(CLEAN+'/execution_terminal.json')
    require(terminal.get('status')=='TWO_CLEAN20_ORIGINAL_ATTEMPTS_COMPLETE'
        and terminal.get('planned_count')==terminal.get('terminal_count')==2
        and type(terminal.get('returncode')) is int and terminal['returncode']==0
        and terminal.get('stop_reason') is None and terminal.get('source_binding_error') is None
        and terminal.get('observer_validation_error') is None
        and terminal.get('source_binding_before')==terminal.get('source_binding_after')
        and terminal.get('cleanup')=={'residual_processes':[],'residual_probe_error':None}
        and terminal.get('engineering_pass_claimed') is False
        and terminal.get('formal_seeds_consumed') is False,'Original32 closed clean denominator/outcome differs')
    retained={}
    for cls in ('person','car'):
        value=get(CLEAN+'/'+cls+'_terminal.json');audit=value.get('audit',{})
        nav=get(CLEAN+'/'+cls+'_evaluation01/navigation_reference_evaluation.json')
        surface=get(CLEAN+'/'+cls+'_evaluation01/surface_flight_evaluation.json')
        require(value.get('error') is None and audit.get('status')=='COMPLETED_CLEAN20_WITH_SURFACE_OCCLUSION_BOUNDARY'
            and audit.get('navigation',{}).get('result')=='PASS'
            and audit.get('surface',{}).get('original_acceptance_result')=='INCOMPLETE_EVIDENCE'
            and audit.get('engineering_pass_claimed') is False
            and nav.get('evaluation_status')=='RECORDED_WITH_CENSORED_FAILURES'
            and surface.get('acceptance',{}).get('result')=='INCOMPLETE_EVIDENCE',
            'Original32 clean numerical result cannot promote original censored/unknown outcome')
        retained[cls]={'audit_status':audit['status'],'navigation_numeric_result':'PASS',
            'navigation_original_evaluation_status':nav['evaluation_status'],
            'surface_original_result':'INCOMPLETE_EVIDENCE','engineering_pass_claimed':False}
    return {'source_commit':SOURCE_COMMIT,'source_canonical_sha256':SOURCE_SHA,
        'source_file_count':597,'build_status':'PASS','tests':1537,'skipped':5,
        'clean_original_count':2,'clean_outcomes':retained,'core_readiness_claimed':False}


def capture_base(root,results,external):
    """Read only the fixed closed set; no live core logs, observer or terminals."""
    external=Path(external)
    original_review=read(external/'humble32_final_source_review.json')
    require(sha(external/'humble32_final_source_review.json')==REVIEW_SHA,'Original32 external final review differs')
    names=set(original_review['helpers_sha256'])
    names.update(('humble32_final_source_review.json','humble32_development_preparation01.json',
        'run_humble32_development01.py','humble32_development_checks01.py',
        'humble32_development_observer01.py','run_humble32_development01.sh','test_humble32_development01.py'))
    small={name:sha(artifact(root,results,name)) for name in sorted(base_names())}
    inputs={name:sha(external/safe(name)) for name in sorted(names)}
    retained=facts(root,results)
    require(small=={name:sha(artifact(root,results,name)) for name in small}
        and inputs=={name:sha(external/name) for name in inputs},'Closed32 evidence changed during snapshot')
    return {'schema_version':1,'scope':SCOPE,'created_utc':datetime.now(timezone.utc).isoformat(),
        'original_root':ORIGINAL_ROOT.as_posix(),'original_results':ORIGINAL_RESULTS.as_posix(),
        'files':small,'files_canonical_sha256':canonical(small),
        'external_inputs':inputs,'external_inputs_canonical_sha256':canonical(inputs),
        'source_files':original_review['files'],'classified_source_hashes':original_review['classified_source_hashes'],
        'retained_facts':retained,
        'core_live_files_included':False,'bag_payload_reads':False,'formal_seed_use_authorized':False}


def verify_base(value,root,results,external):
    require(value.get('schema_version')==1 and value.get('scope')==SCOPE
        and value.get('original_root')==ORIGINAL_ROOT.as_posix()
        and value.get('original_results')==ORIGINAL_RESULTS.as_posix()
        and value.get('core_live_files_included') is False and value.get('formal_seed_use_authorized') is False,
        'Foreign/mutable original32 base snapshot')
    require(set(value.get('files',{}))==base_names()
        and canonical(value['files'])==value.get('files_canonical_sha256')
        and canonical(value['external_inputs'])==value.get('external_inputs_canonical_sha256')
        and canonical(value.get('source_files'))==SOURCE_SHA,'Original32 fixed retention denominator/source map differs')
    require(all(sha(artifact(root,results,name))==digest for name,digest in value['files'].items())
        and all(sha(Path(external)/safe(name))==digest for name,digest in value['external_inputs'].items()),
        'Original32 closed artifact changed')
    require(facts(root,results)==value.get('retained_facts'),'Original32 immutable semantics changed')
    return {'scope':SCOPE,'files_canonical_sha256':value['files_canonical_sha256'],
        'external_inputs_canonical_sha256':value['external_inputs_canonical_sha256'],
        'source_canonical_sha256':SOURCE_SHA,'retained_facts':value['retained_facts'],
        'historical_failures_promoted':False,'core_readiness_claimed':False}


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def capture_core(base_path,output):
    """Optional later append-only closed core snapshot; never a readiness gate."""
    base=read(base_path);verify_base(base,ORIGINAL_ROOT,ORIGINAL_RESULTS,EXTERNAL)
    path=ORIGINAL_RESULTS/CORE[8:]/'core_serial01/execution_terminal.json'
    terminal=read(path)
    require(type(terminal.get('returncode')) is int and terminal['returncode'] in (0,2)
        and isinstance(terminal.get('finished_utc'),str)
        and terminal.get('formal_seeds_consumed') is False,'Core32 has no original closed terminal yet')
    names={CORE+'/plan.json',CORE+'/core_serial01/setup.json',CORE+'/core_serial01/execution_terminal.json'}
    plan=read(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,CORE+'/plan.json'))
    closed_clean=read(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,CLEAN+'/execution_terminal.json'))
    require(sha(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,CORE+'/plan.json'))==closed_clean.get('plan_file_sha256')
        and plan.get('plan_sha256')==canonical({k:v for k,v in plan.items() if k!='plan_sha256'})
        and plan.get('source_hashes')==base.get('classified_source_hashes')
        and len(plan.get('trials',[]))==12,'Core32 plan differs from original closed clean/source binding')
    expected_ids=[trial['id'] for trial in plan['trials']]
    slots=terminal.get('slots',[])
    require(terminal.get('scope')=='HUMBLE32_CORE12_ORIGINAL_ATTEMPTS_AND_CLEANUP_NOT_FORMAL_GATE'
        and terminal.get('planned_count')==12 and terminal.get('terminal_count')==len(slots)
        and [slot.get('slot') for slot in slots]==expected_ids[:len(slots)] and len(slots)<=12
        and terminal.get('cleanup')=={'residual_processes':[],'residual_probe_error':None}
        and terminal.get('source_binding_before')==terminal.get('source_binding_after')
        and terminal.get('source_binding_before',{}).get('freeze_source_sha256')==SOURCE_SHA,
        'Original core32 denominator/source/closure differs')
    require(terminal['returncode']!=0 or len(slots)==12 and terminal.get('stop_reason') is None,
        'Successful original driver closure needs all12 terminals')
    retained=[]
    for slot in slots:
        trial=next(t for t in plan['trials'] if t['id']==slot['slot'])
        relative=CORE+'/slots/'+trial['id']+'.json'
        record=read(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,relative))
        require(record.get('id')==trial['id']
            and record.get('record_sha256')==canonical({k:v for k,v in record.items() if k!='record_sha256'})
            and record.get('plan_sha256')==plan.get('plan_sha256')
            and record.get('status')==slot.get('status') and record.get('status') in
            {'PASS','FAIL','INCOMPLETE_EVIDENCE','EVALUATION_PENDING','INFRASTRUCTURE_ERROR','INTERRUPTED'},
            'Original closed core slot digest/status differs')
        names.update((relative,CORE+'/slots/'+trial['id']+'.started.json'))
        for entry in record.get('evaluations',[]):
            report=PurePosixPath(entry['report']).relative_to(PurePosixPath(ORIGINAL_ROOT.as_posix())).as_posix()
            names.add(safe(report))
            require(sha(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,report))==entry.get('report_sha256'),
                'Closed original core report binding differs')
        retained.append({**{k:record.get(k) for k in ('id','status','infrastructure_stop','execution_status','flight_exit_code')},
            'original_record':record})
    values={name:sha(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,name)) for name in sorted(names)}
    require(values=={name:sha(artifact(ORIGINAL_ROOT,ORIGINAL_RESULTS,name)) for name in values},'Closed core changed')
    write_new(output,{'schema_version':1,'scope':'ORIGINAL32_CLOSED_CORE_APPEND_ONLY_NOT_READINESS',
        'created_utc':datetime.now(timezone.utc).isoformat(),'parent_base':{'path':str(base_path),'sha256':sha(base_path),
            'files_canonical_sha256':base['files_canonical_sha256']},'files':values,'retained_original_slots':retained,
        'original_driver_terminal_fields':{key:terminal.get(key) for key in
            ('returncode','planned_count','terminal_count','stop_reason','source_binding_error',
             'observer_validation_error','status_counts')},
        'all_pass_claimed':False,'formal_seed_use_authorized':False})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('describe','snapshot-core'),nargs='?',default='describe')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if args.action=='describe':
        print(json.dumps({'scope':SCOPE,'base':BASE.as_posix(),'fixed_closed_file_count':len(base_names()),
            'core_live_files_included':False,'actual_snapshot_executed':False}));return 0
    require(args.output is not None and args.output.parent.resolve()==EXTERNAL.resolve()
        and re.fullmatch(r'humble33_original32_core_snapshot[0-9]{2}\.json',args.output.name),
        'Explicit newly named external closed-core snapshot required')
    capture_core(BASE,args.output);return 0


if __name__=='__main__':raise SystemExit(main())
