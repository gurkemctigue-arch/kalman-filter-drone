"""Prepare actual Windows46 source maps for independent review, never assemble.

Reads committed source and named metadata only. The inherited ext4 magnetic
override is represented by its existing exact43 review pin, not a claim that
Windows freshly read it. Native assembler later rehashes that original path.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXTERNAL = HERE.parent
COMMIT = 'de89a6696d60a113929c97bab775dc2258ef4d01'
BASE_COMMIT = '25bd5aa92c642a98503ce586ed028daa224e4326'
BASE_REVIEW_SHA = '19fbace1a78d3149d5195338e088c3c1691901dac1616d53babe639246974b58'
OUT = HERE/'reviewed_commit46_maps01.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def delta(before, after):
    return {'changed': sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
            'added': sorted(after.keys()-before.keys()), 'removed': sorted(before.keys()-after.keys())}


def main():
    sys.dont_write_bytecode = True
    root = Path.cwd().resolve(strict=True)
    if sys.platform != 'win32' or OUT.exists():
        raise ValueError('Only fresh Windows metadata preparation from actual project cwd')
    def git(*args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=true', '-C', str(root), *args])
    if git('rev-parse', 'HEAD').decode().strip() != COMMIT or git('status', '--porcelain'):
        raise ValueError('Actual committed clean46 tree required')
    prior_path = EXTERNAL/'reviewed_freeze_review_v4_humble43_01.json'
    if sha(prior_path) != BASE_REVIEW_SHA:
        raise ValueError('Original43 review changed')
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    tracked = sorted(name.decode('utf-8') for name in git('ls-files', '-z').split(b'\0') if name)
    ignored = prior['assembly_provenance']['inherited_ignored_resources']
    if set(tracked) & set(ignored):
        raise ValueError('Inherited ignored resource became tracked')
    files = {}
    for name in sorted(tracked+ignored):
        if name in prior['source_overrides']:
            files[name] = prior['source_overrides'][name]['sha256']
        else:
            path = root/name
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Missing/unsafe actual source: '+name)
            files[name] = sha(path)
    full_delta = delta(prior['files'], files)
    git_delta = {key: sorted(name.decode('utf-8') for name in git('diff', '--no-renames', '--name-only',
        '-z', '--diff-filter='+code, BASE_COMMIT, COMMIT, '--').split(b'\0') if name)
        for code, key in (('M', 'changed'), ('A', 'added'), ('D', 'removed'))}
    if full_delta != git_delta:
        raise ValueError('Actual complete Git/physical delta differs')
    for name in full_delta['changed']+full_delta['added']:
        if (root/name).read_bytes() != git('show', COMMIT+':'+name):
            raise ValueError('Changed/added physical source differs from actual committed blob: '+name)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root/'scripts'))
    import run_reliability_v4 as runner
    if Path(runner.__file__).resolve() != root/'scripts/run_reliability_v4.py':
        raise ValueError('Another source runner imported')
    classified = runner.source_hashes(root)
    classified['config/px4_magnetic_runtime.json'] = files['config/px4_magnetic_runtime.json']
    if any(files.get(name) != digest for name,digest in classified.items()):
        raise ValueError('Classified map not completely covered by tracked/inherited source')
    protocol = json.loads((root/runner.PROTOCOL_PATH).read_text(encoding='utf-8'))
    runner.validate_protocol(protocol)
    spec = importlib.util.spec_from_file_location('_prepared46_actual_gate', root/'scripts/build_reliability_v4_probe_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    prospective = {'protocol': protocol, 'source_hashes': classified,
        'model_hashes': {key:value for key,value in classified.items() if key.endswith('.pt')},
        'magnetic_runtime_binding': {'manifest_sha256': files['config/px4_magnetic_runtime.json']},
        'magnetic_library_binding': {'registration_sha256': files['config/gazebo_magnetic_runtime_humble22.json']}}
    evidence_names = ['humble46_stream_clock_patch_independent_final01.json',
                      'humble46_stream_clock_windows_tests05_receipt.json']
    evidence = []
    for name in evidence_names:
        path = EXTERNAL/name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 16*1024*1024:
            raise ValueError('Actual final source/test evidence absent: '+name)
        evidence.append({'path': '/mnt/d/WSL/UAVHumble22-validation/'+name,
                         'sha256': sha(path), 'bytes': path.stat().st_size})
    value = {'schema_version': 1,
        'scope': 'COMMITTED46_FULL_SOURCE_AND_CLASSIFIED_MAPS_NOT_RUNTIME_ACCEPTANCE',
        'status': 'ACTUAL_COMMIT_MAPS_PREPARED_FOR_INDEPENDENT_REVIEW',
        'source_commit': COMMIT, 'source_root': prior['source_root'], 'baseline_commit': BASE_COMMIT,
        'files': files, 'files_canonical_sha256': canonical(files), 'allowed_delta': full_delta,
        'classified_source_hashes': classified, 'classified_canonical_sha256': canonical(classified),
        'classified_delta': delta(prior['classified_source_hashes'], classified),
        'supervisor_stream_timing_sha256': canonical(runner.supervisor_stream_summary(protocol)),
        'prospective_gate_bindings': gate.bindings(prospective), 'review_evidence': evidence,
        'source_overrides': prior['source_overrides'],
        'preparation_evidence': {'host': 'Windows', 'tracked_file_count': len(tracked),
            'inherited_ignored_resources': ignored, 'physical_source_count_including_inherited_override_pin': len(files),
            'git_complete_delta_equals_physical_delta': True, 'changed_added_bytes_equal_actual_git_blobs': True,
            'inherited_override_current_native_bytes_checked': False,
            'override_policy': 'Use unchanged43 exact ext4 original pin here; native assembly and unchanged generic candidate_binding rehash the original path before acceptance',
            'map_independent_review': 'PENDING_EXTERNAL_REVIEW', 'assembler_executed': False,
            'WSL_started': False, 'original_bag_or_runtime_payload_read': False,
            'committed_evidence_snapshot_bytes_hashed_as_source': True, 'build_or_flight_started': False},
        'formal_or_runtime_acceptance_claimed': False}
    if git('status', '--porcelain') or git('rev-parse', 'HEAD').decode().strip() != COMMIT:
        raise ValueError('Committed source changed during map preparation')
    with OUT.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2,ensure_ascii=True)+'\n')
    print(json.dumps({'status':'ACTUAL_MAPS_PREPARED_NOT_ASSEMBLED','map':str(OUT),'sha256':sha(OUT),
        'source_file_count':len(files),'classified_source_count':len(classified),
        'full_delta':full_delta,'classified_delta':value['classified_delta']},ensure_ascii=True))


if __name__ == '__main__':
    main()
