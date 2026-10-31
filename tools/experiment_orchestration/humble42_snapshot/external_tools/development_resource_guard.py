"""Named512/CPU4 development resources with original runtime safety checks.

The historical640 guard stays unchanged. This explicit adapter composes its
bridge/safety checks with the generic source/magnetic checks and validates the
new512 receipt against real image-regression and offline worker measurements.
Import is inert; no candidate registration, model import or flight is performed.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

import reviewed_freeze_build as generic

REVISION = 'car_train20_04_m512_cpu4_v1'
SCOPE = 'DEVELOPMENT_IMAGE_REGRESSION_AND_OFFLINE_WORKER_TIMING_ONLY_NOT_FLIGHT_ACCEPTANCE'
TIMING_SCOPE = 'ISOLATED_PRELOADED_PNG_CPU_PREDICT_ONLY_NO_ROS_NO_GT_NO_FLIGHT_ACCEPTANCE'
RECEIPT_PATH = 'config/car_sim_train20_04_m512_resource_receipt.json'
RECEIPT_SHA = '9abeaca3a892e61761564bc7116bb8aed34d9864f4f7406bd9f3a4bc59f3c26c'
MODEL = 'models/yolo11m_car_sim_train20_04.pt'
MODEL_SHA = 'bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c'
QUALITY_SHA = '570775127105dab3138ecc001b1815b05994763306546504fee1cfe6e9cca0e4'
SCRIPT_SHA = '127756a06e5fe7370c645d79ba41edd095094bdee6a951e63edadce7a3ad5508'
PROTOCOL_PATH = 'planning/reliability-v4-preregistration.json'
EVIDENCE_NAMES = {'started.json', 'inputs.json', 'environment.json', 'samples.jsonl', 'summary.json'}
require, sha = generic.require, generic.sha


def tool_manifest():
    external = Path(__file__).resolve().parent
    files = {}
    for name in ('development_resource_guard.py','test_development_resource_guard.py'):
        path = external/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
                'Missing bounded named resource adapter source/test')
        files[name] = sha(path)
    return {'schema_version':1,'scope':SCOPE,'files':files,'revision':REVISION,
            'receipt':{'path':RECEIPT_PATH,'sha256':RECEIPT_SHA},
            'generic_tools_canonical_sha256':generic.canonical(generic.tools_manifest()),
            'legacy_guard_modified':False,'dependency_globals_modified':False,
            'closed_loop_or_formal_acceptance_awarded':False}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def exact_int(value, expected):
    return type(value) is int and value == expected


class FileEvidence:
    """Bounded ordinary evidence files; tests can supply an in-memory reader."""
    def __init__(self):
        self.bindings = {}

    def file(self, binding, *, limit=generic.MAX_SMALL):
        require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
                and generic.valid_sha(binding.get('sha256')), 'Named evidence path/SHA required')
        path = Path(binding['path'])
        require(path.is_absolute() and path.is_file() and not path.is_symlink()
                and path.stat().st_size <= limit and sha(path) == binding['sha256'],
                'Resource evidence bytes changed: '+str(path))
        self.bindings[str(path)] = {'path': str(path), 'sha256': binding['sha256'], 'limit': limit}
        return path

    def json(self, binding):
        path = self.file(binding)
        require(path.suffix == '.json', 'JSON resource evidence required')
        value = json.loads(path.read_text(encoding='utf-8'))
        self.file(binding)
        return value

    def rows(self, binding):
        path = self.file(binding)
        require(path.suffix == '.jsonl', 'Raw JSONL measurement evidence required')
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.file(binding)
        return rows


def wall_stats(values):
    require(values and all(finite(v) and v >= 0 for v in values), 'Unknown/invalid wall measurements remain inadmissible')
    values = sorted(values)
    def percentile(fraction):
        position = fraction*(len(values)-1)
        left = int(position)
        right = min(left+1, len(values)-1)
        return values[left]+(values[right]-values[left])*(position-left)
    return {'denominator': len(values), 'known': len(values), 'unknown': 0,
            'minimum': values[0], 'median': percentile(.5), 'p95': percentile(.95),
            'p99': percentile(.99), 'maximum': values[-1]}


def require_equal_stats(actual, expected):
    require(isinstance(actual, dict) and set(actual) == set(expected), 'Complete wall-time statistic fields required')
    for key, value in expected.items():
        require(exact_int(actual.get(key), value) if type(value) is int else
                finite(actual.get(key)) and math.isclose(actual[key], value, rel_tol=1e-12, abs_tol=1e-12),
                'Original raw measurement statistics changed: '+key)


def quality_evidence(receipt, reader):
    quality = receipt.get('quality', {})
    require(quality.get('candidate_id') == 'train20_04_best_m512'
            and exact_int(quality.get('candidate_opportunities'), 260)
            and exact_int(quality.get('unknown_predictions'), 0)
            and quality.get('gate') == 'PASS_PAIRED_DEVELOPMENT_REGRESSION_ONLY'
            and quality.get('summary_sha256') == QUALITY_SHA, 'Actual consumed260 paired512 regression required')
    summary = reader.json({'path': quality['summary_path'], 'sha256': quality['summary_sha256']})
    spec = summary.get('specification', {})
    require(summary.get('status') == 'COMPLETE_DEVELOPMENT_COMPARISON'
            and summary.get('formal_seeds_used') == [] and summary.get('no_runtime_admission_awarded') is True
            and spec.get('model_sha256') == MODEL_SHA and exact_int(spec.get('torch_threads'), 4)
            and spec.get('precision') == 'CPU native PT FP32'
            and 'train20_04_best_m512' in summary.get('passed_development_regression_candidates', []),
            'Bound quality summary does not support this prospective512 resource')
    registration = next((x for x in spec.get('candidates', []) if x.get('id') == quality['candidate_id']), None)
    require(isinstance(registration, dict) and exact_int(registration.get('imgsz'), 512)
            and registration.get('actual_input_shape') == [1, 3, 384, 512], 'Quality measurement actual512 tensor binding differs')
    results = summary.get('candidates', {}).get(quality['candidate_id'], {})
    require(set(results) == {'consumed236', 'consumed_fresh24'}, 'Both original quality populations are required')
    for population, count in (('consumed236',236), ('consumed_fresh24',24)):
        result = results[population]
        require(all(exact_int(result.get(name), count) for name in ('total_pairs', 'complete_pairs'))
                and exact_int(result.get('unknown_pairs'), 0)
                and result.get('gate', {}).get('status') == quality['gate']
                and result['gate'].get('failures') == []
                and exact_int(result['gate'].get('total_pairs'), count)
                and exact_int(result.get('aggregate_metrics', {}).get(quality['candidate_id'], {}).get('unknown_prediction_opportunities'), 0),
                'Original per-population quality FAIL/unknown/incomplete cannot be removed')
    return {'candidate_id': quality['candidate_id'], 'opportunities':260, 'unknown':0,
            'summary': {'path':quality['summary_path'], 'sha256':quality['summary_sha256']},
            'scope':'CONSUMED_IMAGE_REGRESSION_ONLY_NOT_RUNTIME_ACCEPTANCE'}


def raw_export_evidence(timing, reader):
    exported = reader.json(timing['raw_input_export'])
    require(exported.get('scope') == 'raw_rgb_offline_timing_inputs_only'
            and exported.get('source_unchanged') is True and exported.get('truth_read') is False
            and exported.get('flight_acceptance_claimed') is False and exported.get('missing_stamp_ns') == [],
            'Actual raw RGB export without truth/acceptance is required')
    images = exported.get('images')
    require(isinstance(images,list) and len(images) == 12
            and len({x.get('file') for x in images}) == 12
            and exported.get('requested_stamp_ns') == [x.get('source_stamp_ns') for x in images],
            'Exact exported12-image denominator/order required')
    base = PurePosixPath(timing['raw_input_export']['path']).parent
    for image in images:
        require(re.fullmatch(r'rgb_[0-9]+\.png', image.get('file','')) is not None
                and image.get('shape') == [480,640,3] and image.get('topic') == '/camera/color/image_raw',
                'Expected raw source RGB image geometry required')
        reader.file({'path':str(base/image['file']), 'sha256':image['sha256']})
    return images


def configuration_evidence(config, timing, images, reader):
    size = config.get('inference_image_size')
    require(type(size) is int and size in (640,512), 'Only original640 and prospective512 worker evidence is supported')
    evidence = config.get('evidence')
    require(isinstance(evidence,dict) and set(evidence) == EVIDENCE_NAMES, 'Complete original worker evidence required')
    parent = PurePosixPath(evidence['started.json']['path']).parent
    require(all(PurePosixPath(b['path']).parent == parent and PurePosixPath(b['path']).name == name
                for name,b in evidence.items()), 'Worker artifact names/process provenance differ')
    started, inputs, environment, summary = (reader.json(evidence[name]) for name in
        ('started.json','inputs.json','environment.json','summary.json'))
    condition = {'id':f'pt_cpu_t4_img{size}', 'threads':4, 'imgsz':size}
    require(started.get('script_sha256') == SCRIPT_SHA and started.get('model',{}).get('sha256') == MODEL_SHA
            and started.get('conditions') == [condition] and started.get('worker_mode') == 'production'
            and started.get('fixed_condition') is True and started.get('scope') == TIMING_SCOPE
            and exact_int(started.get('cycles'),84) and exact_int(started.get('repeats'),84)
            and exact_int(started.get('warmup'),3), 'Actual original fixed production worker/84 cycles required')
    require(environment.get('executable') == generic.PYTHON
            and environment.get('method',{}).get('worker') == 'production'
            and environment.get('environment',{}).get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and inputs.get('preloaded') is True and isinstance(inputs.get('frames'),list) and len(inputs['frames']) == 12,
            'Actual Humble production worker/preloaded12 environment required')
    for frame, image in zip(inputs['frames'],images):
        require(all(frame.get(key) == image.get(key) for key in ('file','sha256','shape'))
                and PurePosixPath(frame.get('path','')).parent == PurePosixPath(started.get('input_dir','')),
                'Worker PNGs differ from bound raw export')
    require(summary.get('status') == 'OFFLINE_PAIRED_TIMING_COMPLETE_NOT_FLIGHT_ACCEPTANCE'
            and summary.get('error') is None and summary.get('failure_context') is None
            and summary.get('started_utc') == started.get('started_utc')
            and exact_int(summary.get('samples'),1008) and exact_int(summary.get('warmup_records'),3)
            and summary.get('raw_samples') == evidence['samples.jsonl']['path']
            and summary.get('accuracy_or_identity_or_live_freshness_claimed') is False
            and set(summary.get('conditions',{})) == {condition['id']}, 'Complete original1008 worker outcome required')
    rows = reader.rows(evidence['samples.jsonl'])
    require(len(rows) == 1008, 'Raw worker denominator is not1008; no unknown/missing opportunities may disappear')
    shape, durations = [1,3,480 if size == 640 else 384,size], []
    for number,row in enumerate(rows):
        repeat,index = divmod(number,12)
        frame = inputs['frames'][index]
        require(exact_int(row.get('repeat'),repeat) and exact_int(row.get('image_index'),index)
                and row.get('pair_id') == f'repeat{repeat:03d}_image{index:06d}'
                and row.get('file') == frame['file'] and row.get('png_sha256') == frame['sha256']
                and row.get('condition_id') == condition['id'] and exact_int(row.get('imgsz'),size)
                and all(exact_int(row.get(key),4) for key in ('threads','effective_threads','torch_threads_after'))
                and row.get('actual_model_input_shape') == shape and row.get('decoded_input_shape') == frame['shape']
                and row.get('actual_backend_format') == 'pt' and row.get('actual_backend_device') == 'cpu'
                and row.get('actual_backend_fp16') is False and row.get('error') is None
                and type(row.get('initialized_thread_ident')) is int
                and row['initialized_thread_ident'] == started.get('main_thread_ident')
                and type(row.get('predict_thread_ident')) is int
                and row['predict_thread_ident'] != row['initialized_thread_ident']
                and row.get('outside_timer_pool_selection_wall_s') is None
                and finite(row.get('predict_wall_s')) and row['predict_wall_s'] >= 0,
                'Actual worker row identity/shape/threads/background execution/measurement differs')
        durations.append(row['predict_wall_s'])
    actual = wall_stats(durations)
    reported = summary['conditions'][condition['id']]
    require(reported.get('condition') == condition
            and all(exact_int(reported.get(name),1008) for name in ('expected','recorded'))
            and exact_int(reported.get('unattempted_or_missing'),0), 'Original condition denominator differs')
    require_equal_stats(reported.get('predict_wall_s'),actual)
    require_equal_stats(config.get('predict_wall_s'),actual)
    return {'inference_image_size':size, 'source_process':evidence['started.json'],
            'actual_input_shape':shape, 'predict_wall_s':actual,
            'started_utc':started['started_utc'], 'finished_utc':summary['finished_utc']}


def verify_512_resource(root, review, runner, protocol, *, reader=None):
    """Require the exact new receipt; never reinterpret a historical640 receipt."""
    reader = FileEvidence() if reader is None else reader
    registration = getattr(runner,'CAR_INPUT_SCALE_REGISTRATION_TRAIN04_512',None)
    expected_registration = {'revision':REVISION, 'receipt':{'path':RECEIPT_PATH,'sha256':RECEIPT_SHA}, 'scope':SCOPE}
    require(registration == expected_registration and protocol.get('car_input_scale_registration') == registration,
            'Named independently reviewed512 registration missing; historical640 cannot substitute')
    car = protocol.get('resources',{}).get('car',{})
    require(car.get('model') == MODEL and exact_int(car.get('inference_image_size'),512)
            and exact_int(car.get('inference_threads'),4)
            and car.get(runner.CORRELATED_BOUND_FIELD) is True
            and protocol.get('model_adaptation') == runner.CAR_MODEL_ADAPTATION_TRAIN04,
            'Exact04/512/CPU4 class adaptation required')
    require(review.get('files',{}).get(RECEIPT_PATH) == RECEIPT_SHA
            and review.get('files',{}).get(MODEL) == MODEL_SHA
            and review.get('files',{}).get(PROTOCOL_PATH) == sha(Path(root)/PROTOCOL_PATH),
            'Actual final source review must bind protocol/512 receipt/original04 model SHA')
    reader.file({'path':str(Path(root)/MODEL),'sha256':MODEL_SHA}, limit=512*1024**2)
    binding = {'path':str(Path(root)/RECEIPT_PATH),'sha256':RECEIPT_SHA}
    receipt = reader.json(binding)
    require(exact_int(receipt.get('schema_version'),1) and receipt.get('revision') == REVISION and receipt.get('scope') == SCOPE
            and receipt.get('resource') == {'model':MODEL,'model_sha256':MODEL_SHA,'inference_image_size':512,
                'actual_input_shape':[1,3,384,512],'inference_threads':4,'device':'cpu','precision':'CPU native PT FP32'}
            and type(receipt['resource']['inference_image_size']) is int and type(receipt['resource']['inference_threads']) is int
            and receipt.get('formal_seeds_used') == [] and receipt.get('complete_development_readiness') is False
            and receipt.get('closed_loop_validated') is False, 'New512 receipt resource/claim boundary changed')
    quality = quality_evidence(receipt,reader)
    timing = receipt.get('timing',{})
    require(timing.get('scope') == TIMING_SCOPE and timing.get('order') == [640,512]
            and all(type(x) is int for x in timing['order']) and timing.get('worker_mode') == 'production'
            and exact_int(timing.get('threads'),4) and exact_int(timing.get('cycles_per_configuration'),84)
            and exact_int(timing.get('images_per_cycle'),12)
            and timing.get('script',{}).get('sha256') == SCRIPT_SHA
            and timing.get('maximum_latency_improved') is False,
            'Actual independent640-then512 screening and retained maximum-latency boundary required')
    reader.file(timing['script'])
    images = raw_export_evidence(timing,reader)
    configurations = timing.get('configurations')
    require(isinstance(configurations,list) and [x.get('inference_image_size') for x in configurations] == [640,512],
            'Both original independent worker configurations required')
    measured = [configuration_evidence(config,timing,images,reader) for config in configurations]
    require(PurePosixPath(measured[0]['source_process']['path']).parent != PurePosixPath(measured[1]['source_process']['path']).parent
            and datetime.fromisoformat(measured[0]['finished_utc']) <= datetime.fromisoformat(measured[1]['started_utc'])
            and measured[1]['predict_wall_s']['maximum'] >= measured[0]['predict_wall_s']['maximum'],
            'Separate sequential original worker runs and retained adverse tail required')
    return {'model':MODEL,'model_sha256':MODEL_SHA,'inference_image_size':512,'inference_threads':4,
            'registration':registration,'receipt':binding,'quality':quality,'timing':measured,
            'scope':SCOPE,'closed_loop_validated':False,'formal_seed_use_authorized':False,
            'evidence_bindings':list(reader.bindings.values())}


def runtime_contracts(review, root):
    """Same generic checks with an explicit named resource validation branch."""
    deps = generic.dependencies()
    guard, runner = deps['humble33_review_guard'], generic.runner_at(root)
    protocol = generic.read_small(Path(root)/PROTOCOL_PATH)
    runner.validate_protocol(protocol)
    classified = runner.source_hashes(root)
    classified['config/px4_magnetic_runtime.json'] = generic.MAGNETIC_SHA
    require(classified == review['classified_source_hashes'], 'Actual classified source completeness differs')
    runner.validate_model_adaptation_binding(protocol,classified)
    magnetic = generic.MAGNETIC_PATH if str(root) == review['source_root'] else str(Path(root)/'config/px4_magnetic_runtime.json')
    actual = runner.verify_external_runtime(root,Path(magnetic))
    require(actual.get('source_root') == generic.PX4_ROOT, 'Actual PX4 registration differs')
    require(not runner.simulation_processes(), 'Another simulator/recorder/flight graph is active')
    bridge, safety = guard.require_bridge_runtime(review,root), guard.require_safety_ast(root)
    if protocol.get('car_input_scale_registration',{}).get('revision') == REVISION:
        resource = verify_512_resource(root,review,runner,protocol)
    else:
        resource = guard.require_resource_choice(root)
    return {'safety':safety,'resource':resource,'bridge':bridge,'px4_root':actual['source_root']}


def require_runtime(candidate, review, checks):
    """Original environment/Agent/linker/two-class read-only flight checks."""
    generic.require_linux()
    root = candidate['frozen_root']
    require(os.environ.get('ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PROJECT_ROOT') == root
            and os.environ.get('STAGE1_ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PX4_ROOT') == generic.PX4_ROOT
            and os.environ.get('STAGE1_ROS_GZ_WS') == generic.BRIDGE and os.environ.get('HUMBLE22_ROS_GZ_WS') == generic.BRIDGE,
            'Use explicit isolated Humble development runtime wrapper')
    environment = checks.require_environment_contract()
    runtime = runtime_contracts(review,root)
    require(sha(checks.AGENT) == checks.AGENT_SHA256,'Actual MicroXRCEAgent bytes changed')
    results = {}
    commands = {'agent_command':['/bin/bash','-c','command -v MicroXRCEAgent'], 'agent_ldd':['ldd',checks.AGENT],
        **{cls+'_flight_check':['/bin/bash',root+'/scripts/run_stage1_flight.sh','check',cls] for cls in ('person','car')}}
    for name,command in commands.items():
        actual = subprocess.run(command,cwd=Path(root),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
        require(actual.returncode == 0 and actual.stdout.strip(),'Read-only runtime preflight failed: '+name)
        require(name != 'agent_command' or actual.stdout.strip() == checks.AGENT,'Agent command escaped installation')
        require(name != 'agent_ldd' or 'not found' not in actual.stdout.lower(),'Agent linker dependency unavailable')
        results[name] = {'command':command,'returncode':actual.returncode,
            'output_lines':sorted(re.sub(r'\(0x[0-9a-fA-F]+\)','(address omitted)',actual.stdout).splitlines())}
    return {'environment':environment,'runtime_contracts':runtime,'checks':results}


def revalidate_resource_binding(resource):
    """Recheck every bound file without reparsing the1008-row measurement set."""
    if resource.get('registration',{}).get('revision') != REVISION:
        return resource
    require(resource.get('scope') == SCOPE and resource.get('closed_loop_validated') is False
            and resource.get('formal_seed_use_authorized') is False and resource.get('evidence_bindings'),
            'Actual named512 measurement binding required')
    reader = FileEvidence()
    for expected in resource['evidence_bindings']:
        require(set(expected) == {'path','sha256','limit'} and type(expected['limit']) is int
                and 0 < expected['limit'] <= 512*1024**2,'Invalid bound resource evidence limit')
        reader.file({'path':expected['path'],'sha256':expected['sha256']},limit=expected['limit'])
    return resource


def verify_runtime_evidence(binding):
    """Public build-driver API; accepts complete runtime or its resource field."""
    require(isinstance(binding,dict),'Actual resource/runtime evidence binding required')
    revalidate_resource_binding(binding['resource'] if 'resource' in binding else binding)
    return binding
