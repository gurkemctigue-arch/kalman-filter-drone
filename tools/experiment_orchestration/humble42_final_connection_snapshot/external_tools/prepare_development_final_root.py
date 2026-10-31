"""Copy an explicitly reviewed candidate to an independent DRAFT final root.

Describe is inert. Inspect/copy need explicit source and tool identities. This
connection grants no runtime, capacity, canonical registration or formal seal.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

import prepare_humble41_final_root01 as primitives
import assemble_development_candidate as assembler
import development_runner as core
import development_freeze_build as development_build
import reviewed_freeze_build as generic

EXTERNAL=Path(__file__).resolve().parent
KIND='PARAMETERIZED_FINAL_ROOT_SOURCE_PREPARATION_ONLY'
OWN=('prepare_development_final_root.py','build_development_final_root.py',
     'build_development_final_root.sh','publish_development_final_protocols.py','test_development_final_root.py')
REUSED={'prepare_humble41_final_root01.py':'4e97c4a0bd621069630d2afaa2664c11f139dfbc623c4efa9f59938fd240c0d7',
    'build_humble41_final_root01.py':'d79aa4138c1488d037bb0459bd199ba0094e83040835c45878b1838323209eff',
    'publish_humble28_final02_protocols01.py':'eaf2141f7e343dd6c74bcef80d7480f9b4282e947effed92110f428cc43d4664',
    'humble33_skip_contract.py':'9a4f9d8584077d5c6ebbc099cb35b0c56746bbd725b0893882814bdc87b92406',
    'assemble_development_candidate.py':'cb011d9bd35aae9b68d4d175dc8b1afecdc13cf089595aa93903f0c51a8561c1'}
PLANNING=primitives.PLANNING
DRAFT=primitives.DRAFT
require,sha,read,write_new,canonical=generic.require,generic.sha,primitives.read,generic.write_new,generic.canonical


def binding(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),'Expected ordinary bound source/metadata: '+str(path))
    return {'path':str(path.resolve(strict=True)),'sha256':sha(path)}


def checked(value):
    require(isinstance(value,dict) and set(value)=={'path','sha256'} and generic.valid_sha(value.get('sha256'))
            and Path(value['path']).is_absolute() and binding(value['path'])==value,'Changed or aliased explicit input')
    return read(value['path'])


def tool_manifest():
    for name,digest in REUSED.items():
        path=EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=generic.MAX_SMALL
                and sha(path)==digest,'Unchanged reused primitive required: '+name)
        module=importlib.import_module(Path(name).stem)
        require(Path(module.__file__).resolve(strict=True)==path,
                'Actually imported reused primitive escaped the reviewed external directory: '+name)
    files={}
    for name in OWN:
        path=EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=generic.MAX_SMALL,'Missing bounded final-root helper')
        files[name]=sha(path)
    return {'schema_version':1,'scope':KIND,'files':files,'unchanged_reused_primitives':REUSED,
        'core_tools_canonical_sha256':canonical(core.tool_manifest()),
        'strict512_build_tools_canonical_sha256':canonical(development_build.tool_manifest()),
        'whole_tree_and_classified_maps_separate':True,'overlay_files':{},'three_original_DRAFT_files_required':True,
        'source_preparation_manifest_preserved_after_publication':True,'default_source_or_final_root':None,
        'source_or_dependency_globals_modified':False,'capacity_admission_performed':False,
        'formal_seed_use_authorized':False,'automatic_next_action':False}


def require_tools(digest):
    require(generic.valid_sha(digest) and digest==canonical(tool_manifest()),'Explicit independently reviewed final-root tools required')


def validate_paths(source,destination,results,*,existing=False):
    source,destination,results=map(Path,(source,destination,results))
    require(source.is_absolute() and source.is_dir() and not source.is_symlink()
            and source.resolve(strict=True)==source,'Actual unaliased candidate source required')
    require(destination.parent==Path('/root') and re.fullmatch(r'uav_tracking_fullplan_[A-Za-z0-9_]+',destination.name)
            and destination!=source,'Independent new /root source/build tree required')
    require(re.fullmatch(r'/mnt/d/.+/results/frozen_fullplan_[A-Za-z0-9_]+',str(results))
            and results!=(source/'results').resolve(strict=True),'Independent D-backed results required')
    for path in (destination,results):
        require(path.parent.is_dir() and not path.parent.is_symlink()
                and path.parent.resolve(strict=True)==path.parent,'Explicit existing unaliased parent required')
        if existing:
            require(path.is_dir() and not path.is_symlink() and path.resolve(strict=True)==path,'Prepared final path changed')
        else:
            require(not path.exists() and not path.is_symlink(),'New exclusive final paths required; no recovery/reuse')
    if existing:
        require((destination/'results').is_symlink() and (destination/'results').resolve(strict=True)==results,
                'Prepared root/results must point to its bound D results store')


def authority(candidate_pin):
    candidate,review=core.load_candidate(candidate_pin['path'],candidate_pin['sha256'])
    source=Path(candidate['frozen_root'])
    frozen=generic.frozen_binding(review)
    manifest=read(source/'results/freeze_validation/source_freeze_manifest.json')
    facts=read(candidate['build_evidence']['summary']['path'])
    actions=Path(candidate['build_evidence']['build_terminal']['path']).parent.parent
    assembler.require_closed_build(review,frozen,facts,actions)
    supplement=core.require_supplement_build(candidate,review)
    require(manifest['files']==review['files'] and manifest['classified_source_hashes']==review['classified_source_hashes'],
            'Actual reviewed whole-tree/classified maps differ')
    return candidate,review,manifest,{'candidate_manifest':candidate_pin,'source_review':review['_review_binding'],
        'original_source_manifest':binding(source/'results/freeze_validation/source_freeze_manifest.json'),
        'source_binding':frozen,'strict512_source_build':supplement}


def check_drafts(root,protected):
    primitives.check_drafts_runtime(Path(root),protected)
    protocol=read(Path(root)/PLANNING[0]);car=protocol['resources']['car']
    require(car.get('inference_image_size')==512 and type(car['inference_image_size']) is int
            and car.get('inference_threads')==4 and type(car['inference_threads']) is int
            and car.get('model')==core.resources.MODEL
            and protocol.get('car_input_scale_registration',{}).get('revision')==core.resources.REVISION,
            'Actual unchanged named512/CPU4 registration required')


def proposal(candidate_pin,destination,results,tools_sha):
    require_tools(tools_sha)
    candidate,review,manifest,bindings=authority(candidate_pin)
    source=Path(candidate['frozen_root']);destination,results=Path(destination),Path(results)
    validate_paths(source,destination,results)
    items=primitives.inventory(source)
    primitives.checked_inventory_map(items,review['files'])
    check_drafts(source,review['files'])
    classifier=primitives.frozen_classifier(source)
    classified=classifier.source_hashes(source)
    require(classified==manifest['classified_source_hashes']
            and all(review['files'].get(name)==digest for name,digest in classified.items()),
            'Actual classified flight inputs differ from reviewed whole-tree source')
    exclusions=tuple(re.findall(r"--exclude='([^']+)'",(source/primitives.FREEZER).read_text()))
    require(exclusions==primitives.EXCLUDES,'Original freezer exclusions changed')
    return {'schema_version':1,'kind':KIND,'created_utc':generic.utc(),'source_root':str(source),
        'destination_root':str(destination),'results_root':str(results),**bindings,'tools_canonical_sha256':tools_sha,
        'overlay_files':{},'freezer_exclusions':list(primitives.EXCLUDES),'additional_exclusions':['/results'],
        'rsync_command':['rsync','-a',*('--exclude='+value for value in primitives.EXCLUDES),'--exclude=/results',
                         '--',str(source)+'/',str(destination)+'/'],
        'original_whole_tree_inventory':items,'expected_whole_tree_inventory':deepcopy(items),
        'original_protected_file_hashes':review['files'],'expected_protected_file_hashes':dict(review['files']),
        'original_classified_source_hashes':classified,'expected_classified_source_hashes':dict(classified),
        'flight_source_hashes':classifier.flight_source_hashes(classified),
        'draft_planning_hashes':{name:review['files'][name] for name in PLANNING},
        'runtime':review['runtime'],'build_executed':False,'protocols_registered':False,'plans_created':False,
        'flights_executed':0,'formal_seed_use_authorized':False,'capacity_admission_performed':False}


def validate_proposal(value):
    require(type(value.get('schema_version')) is int and value['schema_version']==1 and value.get('kind')==KIND,
            'Actual parameterized preparation proposal required')
    require_tools(value.get('tools_canonical_sha256'))
    candidate,review,manifest,bindings=authority(value['candidate_manifest'])
    require(value['source_root']==candidate['frozen_root'] and all(value.get(key)==val for key,val in bindings.items()),
            'Preparation source/build authority changed')
    require(value.get('overlay_files')=={} and value.get('original_protected_file_hashes')==
            value.get('expected_protected_file_hashes')==review['files']
            and value.get('original_classified_source_hashes')==value.get('expected_classified_source_hashes')==manifest['classified_source_hashes']
            and value.get('original_whole_tree_inventory')==value.get('expected_whole_tree_inventory')
            and value.get('draft_planning_hashes')=={name:review['files'][name] for name in PLANNING}
            and value.get('freezer_exclusions')==list(primitives.EXCLUDES) and value.get('additional_exclusions')==['/results']
            and all(value.get(name) is False for name in ('build_executed','protocols_registered','plans_created',
                'formal_seed_use_authorized','capacity_admission_performed'))
            and type(value.get('flights_executed')) is int and value['flights_executed']==0,
            'Preparation cannot introduce a source overlay, registration or runtime claim')
    primitives.checked_inventory_map(value['expected_whole_tree_inventory'],review['files'])
    return candidate,review


def verify_prepared(value,allowed_planning=None):
    validate_proposal(value)
    source,root,results=map(Path,(value['source_root'],value['destination_root'],value['results_root']))
    validate_paths(source,root,results,existing=True)
    require(primitives.inventory(source)==value['original_whole_tree_inventory'],'Immutable candidate source changed')
    allowed={} if allowed_planning is None else allowed_planning
    require(set(allowed)<=set(PLANNING),'Only explicitly published canonical planning files may change')
    expected=deepcopy(value['expected_whole_tree_inventory'])
    for name,pin in allowed.items():
        require(binding(root/name)==pin,'Published canonical binding changed')
        expected[name]['sha256']=pin['sha256'];expected[name]['bytes']=(root/name).stat().st_size
    actual=primitives.inventory(root)
    require(actual==expected,'Prepared source differs beyond explicitly bound canonical publications')
    for name in set(PLANNING)-set(allowed):
        require(sha(root/name)==value['draft_planning_hashes'][name] and read(root/name)['status']==DRAFT,
                'Unpublished canonical file must retain its original DRAFT bytes')
    classifier=primitives.frozen_classifier(root);classified=classifier.source_hashes(root)
    require(classified==value['expected_classified_source_hashes']
            and classifier.flight_source_hashes(classified)==value['flight_source_hashes'],
            'Final classified flight inputs differ from the immutable candidate')
    return {'whole_tree_entry_count':len(actual),'protected_file_count':len(value['expected_protected_file_hashes']),
        'whole_tree_inventory_sha256':canonical(actual),'classified_source_sha256':canonical(classified),
        'flight_source_sha256':canonical(value['flight_source_hashes']),'results_root':str(results)}


def apply_copy(value):
    validate_proposal(value)
    source,root,results=map(Path,(value['source_root'],value['destination_root'],value['results_root']))
    validate_paths(source,root,results)
    command=['rsync','-a',*('--exclude='+item for item in primitives.EXCLUDES),'--exclude=/results',
             '--',str(source)+'/',str(root)+'/']
    require(value['rsync_command']==command and primitives.inventory(source)==value['original_whole_tree_inventory'],
            'Original source inventory or copy argv changed')
    root.mkdir();results.mkdir();(root/'results').symlink_to(results,target_is_directory=True)
    directory=results/'freeze_validation';directory.mkdir()
    write_new(directory/'source_preparation_started.json',value)
    try:
        subprocess.run(command,check=True,stdin=subprocess.DEVNULL)
        verified=verify_prepared(value)
        manifest=directory/'source_sha256.txt'
        with manifest.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(''.join(digest+'  '+name+'\n' for name,digest in sorted(value['expected_protected_file_hashes'].items())))
        outcome={'schema_version':1,'kind':KIND,'status':'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED',
            'finished_utc':generic.utc(),'proposal':value,'source_verification':verified,'source_unchanged':True,
            'preparation_source_manifest':binding(manifest),'build_executed':False,'protocols_registered':False,
            'plans_created':False,'flights_executed':0,'formal_seed_use_authorized':False}
        write_new(directory/'source_preparation_outcome.json',outcome)
        return outcome
    except BaseException as error:
        write_new(directory/'source_preparation_failed.json',{'status':'FAILED_RETAIN_PARTIAL_ROOT_NO_RETRY',
            'error':type(error).__name__+':'+str(error),'finished_utc':generic.utc(),'formal_seed_use_authorized':False})
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('describe','inspect','copy'),nargs='?',default='describe')
    parser.add_argument('--candidate',type=Path);parser.add_argument('--candidate-sha256')
    parser.add_argument('--destination-root',type=Path);parser.add_argument('--results-store',type=Path)
    parser.add_argument('--reviewed-tools-sha256');parser.add_argument('--proposal',type=Path)
    parser.add_argument('--proposal-sha256');parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if args.action=='describe':
        manifest=tool_manifest();print(json.dumps({'manifest':manifest,'sha256':canonical(manifest),'actual_action_executed':False}));return 0
    generic.require_linux();require_tools(args.reviewed_tools_sha256)
    if args.action=='inspect':
        require(args.candidate is not None and generic.valid_sha(args.candidate_sha256)
                and args.destination_root is not None and args.results_store is not None and args.output is not None,
                'Explicit source/final paths and exclusive proposal output required')
        value=proposal({'path':str(args.candidate),'sha256':args.candidate_sha256},
            args.destination_root,args.results_store,args.reviewed_tools_sha256)
        require(args.output.parent.resolve(strict=True)==EXTERNAL and args.output.suffix=='.json','Named external proposal output required')
        write_new(args.output,value)
    else:
        require(args.proposal is not None and generic.valid_sha(args.proposal_sha256),'Explicit actual inspected proposal/SHA required')
        value=checked({'path':str(args.proposal),'sha256':args.proposal_sha256})
        require(value['tools_canonical_sha256']==args.reviewed_tools_sha256,'Copy must use the reviewed actual proposal')
        apply_copy(value)
    return 0


if __name__=='__main__':raise SystemExit(main())
