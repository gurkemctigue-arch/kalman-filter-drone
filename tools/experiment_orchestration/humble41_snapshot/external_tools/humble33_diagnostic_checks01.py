"""Local33 original gates only; import starts no action or simulator."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import humble33_review_guard as guard
from humble33_review_guard import ROOT, read_small, sha
RUNTIME_ENVIRONMENT = {'ROS_DOMAIN_ID': '73', 'GZ_PARTITION': 'uav_humble22_validation',
    'GZ_IP': '127.0.0.1', 'GZ_VERSION': 'harmonic', 'IGNITION_VERSION': ''}


AGENT = '/root/uav_humble22/agent_install/bin/MicroXRCEAgent'


AGENT_SHA256 = 'fc5afa7524e499cb82ccdbec69bda56f116d20b3ddecea404745340f7357959c'


PROJECT_PACKAGES = ('uav_tracking_interfaces', 'uav_tracking_nodes',
                    'uav_tracking_px4_adapter', 'uav_tracking_bringup')


def require_environment_contract(environment=None):
    """Require every missing canonical runtime field, without starting anything."""
    environment = os.environ if environment is None else environment
    if any(key not in environment or environment[key] != value
           for key, value in RUNTIME_ENVIRONMENT.items()):
        raise ValueError('Canonical Humble22 ROS/Gazebo runtime environment differs')
    for name, prefix in (('PATH', '/root/uav_humble22/agent_install/bin'),
                         ('LD_LIBRARY_PATH', '/root/uav_humble22/agent_install/lib')):
        if environment.get(name, '').split(':')[0] != prefix:
            raise ValueError('Canonical MicroXRCEAgent path prefix is missing: ' + name)
    return {'values': dict(RUNTIME_ENVIRONMENT), 'path_prefix': str(Path(AGENT).parent),
            'library_path_prefix': '/root/uav_humble22/agent_install/lib'}


def preflight_runtime():
    """Read-only executable/linker/assets checks; no nodes, bags or simulation."""
    environment = require_environment_contract()
    commands = [(['bash', '-c', 'command -v MicroXRCEAgent'], 'agent_command'),
                (['ldd', AGENT], 'agent_ldd')]
    commands.extend((['bash', str(ROOT / 'scripts/run_stage1_flight.sh'), 'check', cls],
                     cls + '_flight_check') for cls in ('person', 'car'))
    commands.extend((['ros2', 'pkg', 'prefix', package], 'package_prefix:' + package)
                    for package in PROJECT_PACKAGES)
    results = {}
    for command, name in commands:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            check=False, timeout=60, cwd=ROOT)
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError('Read-only runtime preflight failed: ' + name + ':' + result.stdout)
        if name == 'agent_command' and result.stdout.strip() != AGENT:
            raise ValueError('MicroXRCEAgent command resolved outside its registered installation')
        if name == 'agent_ldd' and 'not found' in result.stdout.lower():
            raise ValueError('MicroXRCEAgent has unresolved shared-library dependencies')
        if name.startswith('package_prefix:'):
            package = name.split(':', 1)[1]
            # The actual four-package32 build uses --merge-install, as recorded
            # by freeze_validation/import_isolation.json for every package.
            if Path(result.stdout.strip()) != ROOT / 'ros2_ws/install':
                raise ValueError('ROS package resolves outside the same frozen33 build: ' + package)
        # ASLR addresses and command listing order are not source identities.
        # Normalize those fields so read-only replay binds the same evidence.
        lines = sorted(re.sub(r'\(0x[0-9a-fA-F]+\)', '(address omitted)',
                              result.stdout).splitlines())
        results[name] = {'command': command, 'returncode': result.returncode,
                         'output_lines': lines}
    if sha(Path(AGENT)) != AGENT_SHA256:
        raise ValueError('MicroXRCEAgent executable bytes differ from the inspected installation')
    return {'status': 'PASS', 'scope': 'READ_ONLY_RUNTIME_PREFLIGHT_NO_NODES_NO_SIMULATION',
            'environment': environment, 'agent': {'path': AGENT, 'sha256': AGENT_SHA256},
            'checks': results}


def checked_build(review, binding):
    path = ROOT / 'results/freeze_validation/build_validation_summary.json'
    built = read_small(path)
    if (built.get('status') != 'PASS' or type(built.get('returncode')) is not int
            or built['returncode'] != 0 or built.get('source_unchanged') is not True
            or built.get('four_packages_built') is not True or built.get('module_ament_isolation') is not True
            or built.get('original28_unchanged') is not True or built.get('original29_unchanged') is not True
            or built.get('original30_unchanged') is not True or built.get('original31_unchanged') is not True or built.get('original32_unchanged') is not True
            or built.get('execution_count') != 1
            or built.get('source_binding_before') != binding or built.get('source_binding_after') != binding
            or built.get('freeze_source_sha256') != binding['freeze_source_sha256']
            or built.get('formal_seeds_consumed') is not False):
        raise ValueError('No actual same-source31 four-package build/test PASS receipt')
    roundtrip = ROOT / 'results/freeze_validation/generated_message_roundtrip.json'
    log = ROOT / 'results/freeze_validation/unittest.log'
    if sha(log) != built.get('suite_log_sha256'):
        raise ValueError('Actual built/tested suite log bytes changed')
    if built.get('generated_message_roundtrip_path') != str(roundtrip) or sha(roundtrip) != built.get('generated_message_roundtrip_sha256'):
        raise ValueError('Built generated-message roundtrip evidence changed')
    import importlib
    isolation=ROOT/'results/freeze_validation/import_isolation.json'
    report=read_small(isolation)
    origins={}
    for name in ('uav_tracking_nodes.detector_node','uav_tracking_nodes.inference_timing','uav_tracking_nodes.inference_worker'):
        actual=Path(importlib.import_module(name).__file__).resolve(strict=True)
        if not actual.is_relative_to(ROOT) or report.get('module_files',{}).get(name)!=str(actual):
            raise ValueError('Actual33 timing module import escaped/differs: '+name)
        relative=actual.relative_to(ROOT).as_posix()
        if sha(actual)!=review['files'].get(relative):
            raise ValueError('Actual33 imported timing module bytes differ: '+name)
        origins[name]={'path':str(actual),'sha256':sha(actual)}
    return {'path': str(path), 'sha256': sha(path), 'freeze_source_sha256': binding['freeze_source_sha256'],
            'actual_diagnostic_module_origins':origins,'import_isolation_sha256':sha(isolation)}


def resource_protocol():
    return read_small(ROOT / 'planning/reliability-v4-preregistration.json')


def require_plan_resources(plan):
    protocol = plan['protocol']
    expected = {'real_time_factor': .25, 'flight_wall_timeout_s': 600., 'duration_s': 75.,
                'max_inference_rate_hz': 10., 'supervisor_status_timing': {
                    'status_timestamp_mode': 'source_sim', 'status_source_max_age_s': 1.,
                    'status_source_max_future_s': .05, 'status_timeout_wall_s': 10.,
                    'wall_check_clock': 'ROS-time control tick; no independent status steady timer'}}
    if any(protocol.get(key) != value for key, value in expected.items()):
        raise ValueError('Inherited resource/T4 timing envelope changed')
    if (protocol.get('resources', {}).get('car', {}).get('model') != 'models/yolo11m_car_sim_train20_04.pt'
            or protocol['resources']['car'].get('inference_image_size') != 640
            or protocol['resources']['car'].get('inference_threads') != 4
            or protocol['resources']['car'].get('navigation_correlated_two_face_bound') is not True
            or protocol['resources']['person'].get('navigation_correlated_two_face_bound', False) is not False
            or protocol.get('safety_gates') != {'max_observation_age_s': .6,
                'max_prediction_duration_s': .75, 'mahalanobis_gate': 9.21,
                'lost_requires_explicit_reselection': True, 'runtime_ground_truth_forbidden': True}):
        raise ValueError('Exact04, independent car geometry and original freshness gates required')


def load_runner():
    if (os.environ.get('STAGE1_ROS_DISTRO') != 'humble'
            or os.environ.get('STAGE1_PROJECT_ROOT') != str(ROOT)):
        raise ValueError('Source the isolated Humble33 environment first')
    spec = importlib.util.spec_from_file_location('humble33_frozen_runner', ROOT / 'scripts/run_reliability_v4.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def terminal_binding(runner, plan, trial, record):
    if (record.get('status') not in runner.TERMINAL
            or record.get('record_sha256') != runner.digest(record, ('record_sha256',))
            or record.get('plan_sha256') != plan['plan_sha256'] or record.get('id') != trial['id']):
        raise ValueError('Changed, foreign or nonterminal record: ' + trial['id'])
    marker_path = runner.record_path(plan, trial, 'started.json')
    marker = read_small(marker_path)
    started_utc = record.get('started_utc', (record.get('started') or {}).get('started_utc'))
    if (marker.get('id') != trial['id'] or marker.get('plan_sha256') != plan['plan_sha256']
            or marker.get('flight_command') != trial['flight_command']
            or not isinstance(started_utc, str) or started_utc != marker.get('started_utc')):
        raise ValueError('Original started marker binding differs: ' + trial['id'])
    path = runner.record_path(plan, trial)
    return {'path': str(path), 'sha256': sha(path), 'record_sha256': record['record_sha256'],
            'started_marker': {'path': str(marker_path), 'sha256': sha(marker_path)},
            'plan_sha256': plan['plan_sha256'], 'started_utc': started_utc}


def require_completed_record(runner, plan, trial, record):
    binding = terminal_binding(runner, plan, trial, record)
    if (record.get('execution_status') != 'COMPLETED'
            or type(record.get('flight_exit_code')) is not int or record['flight_exit_code'] != 0
            or record.get('infrastructure_stop') is not False
            or record['status'] in {'INFRASTRUCTURE_ERROR', 'INTERRUPTED'}
            or record.get('cleanup', {}).get('residual_processes') != []
            or record.get('runtime_configuration', {}).get('errors') != []
            or record.get('infrastructure', {}).get('stop') is not False):
        raise ValueError('Incomplete/infrastructure attempt requires diagnosis: ' + trial['id'])
    native_handoff_runtime(trial['directory'])
    return binding


def native_handoff_runtime(directory):
    import yaml
    path = Path(directory) / 'configuration/runtime_parameters.yaml'
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Unsafe/oversized native handoff runtime YAML')
    values = yaml.safe_load(path.read_text()).get('uav_tracking_flight_supervisor', {}).get('ros__parameters', {})
    expected = {'takeoff_mode': 'px4_native', 'native_handoff_guard_s': .25,
        'native_settle_s': 1., 'native_settle_speed_mps': .20, 'takeoff_position_tolerance_m': .18,
        'native_takeoff_timeout_sim_s': 40., 'native_wall_timeout_s': 180.}
    if any(type(values.get(name)) not in {str, int, float} or values.get(name) != expected_value
           for name, expected_value in expected.items()):
        raise ValueError('Original native limits or explicit .25 guard runtime changed')
    return {'runtime_parameters_sha256': sha(path), 'values': expected}


def bridge_evidence(directory, review):
    configuration = Path(directory) / 'configuration'
    names = ('ros_gz_runtime_registration.json', 'ros_gz_runtime_preflight.json',
             'ros_gz_runtime_actual.json', 'ros_gz_runtime_after.json')
    registration, pre, actual, after = [read_small(configuration / name) for name in names]
    expected_sha = review['files']['config/ros_gz_runtime_humble22.json']
    if sha(configuration / names[0]) != expected_sha or registration.get('fixture_only') is not False:
        raise ValueError('Actual flight bridge registration differs or is a fixture')
    for report in (pre, actual, after):
        if (report.get('status') != 'PASS' or report.get('fixture_only') is not False
                or report.get('registration_digest') != registration.get('registration_digest')
                or report.get('registration_file_sha256') != expected_sha):
            raise ValueError('Bridge runtime report is unbound or failed')
    if (pre.get('scope') != 'CURRENT_SOURCE_AND_ELF_MATCH_REGISTERED_CANDIDATE'
            or after.get('scope') != pre['scope'] or after.get('ros_exit_code') != 0
            or actual.get('scope') != 'LIVE_PID_EXE_AND_MAPS_MATCH_REGISTERED_ROS_GZ_RUNTIME'):
        raise ValueError('Bridge pre/live/after verification scope differs')
    if any((configuration / name).exists() for name in ('ros_gz_runtime_actual_error.json', 'ros_gz_runtime_after_error.json')):
        raise ValueError('Actual bridge startup/shutdown error evidence exists')
    owned, process = actual.get('owned_launch', {}), actual.get('process', {})
    chain, leader = owned.get('ancestor_chain', []), owned.get('leader', {})
    if (owned.get('process') != process or not chain or chain[0] != leader or chain[-1] != process
            or type(process.get('pid')) is not int or process['pid'] <= 0
            or type(process.get('start_ticks')) is not int or process['start_ticks'] <= 0):
        raise ValueError('Bridge actual PID creation/owned launch identity missing')
    for parent, child in zip(chain, chain[1:]):
        if child.get('parent_pid') != parent.get('pid'):
            raise ValueError('Bridge actual owned ancestor chain is contradictory')
    mapped = actual.get('mapped_elfs')
    if (not isinstance(mapped, list) or not mapped or actual.get('mapped_elf_count') != len(mapped)
            or any(type(item.get('inode')) is not int or item['inode'] <= 0 or not item.get('sha256')
                   or not item.get('path') or type(item.get('bytes')) is not int or item['bytes'] <= 0
                   or type(item.get('device_major')) is not int or type(item.get('device_minor')) is not int
                   for item in mapped)):
        raise ValueError('Bridge actual process mappings are incomplete')
    expected_elfs = {}
    for item in [registration['executable'], *registration['dependencies'], *registration.get('plugins', [])]:
        identity = (item['sha256'], item['bytes'])
        key = str(Path(item['real_path']).resolve())
        if key in expected_elfs and expected_elfs[key] != identity:
            raise ValueError('Bridge registration has conflicting ELF aliases')
        expected_elfs[key] = identity
    actual_elfs = {str(Path(item['path']).resolve()): (item['sha256'], item['bytes']) for item in mapped}
    if (len(actual_elfs) != len(mapped) or actual_elfs != expected_elfs
            or actual.get('checked_plugin_count') != len(registration.get('plugins', []))):
        raise ValueError('Bridge actual mapped executable/dependencies/plugins differ from registration')
    return {'status': 'PASS', 'actual_process': process, 'owned_launch': owned,
            'files_sha256': {name: sha(configuration / name) for name in names}}


def closed75_archive(trial,record):
    import math
    directory=Path(trial['directory'])
    names=('summary.json','recording_closure.json','bag_integrity.json','process_exit_codes.json')
    reports={}
    for name in names:
        path=directory/name
        require(not path.is_symlink() and sha(path)==record.get('artifact_hashes',{}).get(name),
            'Original diagnostic closed report differs:'+name)
        reports[name]=read_small(path)
    summary,closure,archive=(reports[name] for name in names[:3])
    start=summary.get('follow_start_s');last=(closure.get('observations') or [{}])[-1].get('last_clock_ns')
    require(trial.get('duration_s')==75 and type(start) in (int,float) and math.isfinite(start) and start>=0
        and type(last) is int and last>=math.ceil((start+75.)*1e9)
        and summary.get('termination_reason')=='follow_duration_reached' and closure.get('status')=='PASS'
        and archive.get('status')=='PASS' and archive.get('policy')=='ext4_sqlite_close_standard_zstd_verified_native_read'
        and type(archive.get('recorder_exit_code')) is int and archive['recorder_exit_code']==0
        and archive.get('spool_retained') is False and archive.get('raw_validation',{}).get('status')=='PASS'
        and archive.get('native_reader_validation',{}).get('status')=='PASS'
        and archive['native_reader_validation'].get('full_stream_read') is True,
        'Original diagnostic needs genuine full75s source-clock/native-read closed archive')
    return {'scope':'ORIGINAL75S_CLOSED_ARCHIVE_METADATA_ONLY_NO_PAYLOAD_READ',
        'reports':{name:{'path':str(directory/name),'sha256':sha(directory/name)} for name in names},
        'full75s_source_clock':True,'native_archive_closed':True}

CONDITIONS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")

from collections import Counter

def require(condition,message):
    if not condition: raise ValueError(message)

def process_verdict(text, codes, *, stage, multi_target=False, condition='clean'):
    require(type(stage) is int and stage in (1, 2, 3) and type(multi_target) is bool, 'Invalid ROS scenario')
    motion = 'stage2_motion' if stage == 2 or stage == 3 and multi_target else 'scenario_motion'
    expected = {'parameter_bridge', 'px4_adapter', 'flight_tf', motion, 'detector',
                'state_estimator', 'controller', 'flight_supervisor'}
    if stage == 3:
        expected.add('gimbal_adapter')
    starts, ends, errors = Counter(), Counter(), []
    for line in text.splitlines():
        if 'process has died' in line:
            errors.append('Explicit child death: ' + line[:500])
        match = re.search(r'\[([A-Za-z0-9_]+)-([0-9]+)\]:\s+process (started with pid \[|has finished cleanly \[pid )([0-9]+)\]', line)
        if match:
            name, number, event, pid = match.groups()
            (starts if event.startswith('started') else ends)[(name, number, pid)] += 1
    if ({key[0] for key in starts} != expected or len(starts) != len(expected)
            or starts != ends or any(value != 1 for value in starts.values())):
        errors.append('Missing/duplicated/foreign/inconsistent clean ROS child/PID endings')
    expected_codes = dict(gazebo=0, px4=0, ros=0, bag=0, monitor=0)
    if condition in CONDITIONS[:5]:
        expected_codes['sensor_faults'] = 0
    else:
        require(condition in ('clean', *CONDITIONS[5:]), 'Unknown sensor condition')
    if set(codes) != set(expected_codes) | {'agent'}:
        errors.append('Missing/unexpected owned process roster')
    for name, value in expected_codes.items():
        if type(codes.get(name)) is not int or codes[name] != value:
            errors.append('Unclean owned process: ' + name)
    if type(codes.get('agent')) is not int or codes['agent'] not in (0, -2):
        errors.append('Unclean Agent exit')
    return {'status': 'PASS' if not errors else 'FAIL', 'errors': errors,
        'expected_ros_children': sorted(expected), 'process_exit_codes': codes,
        'starts': [list(key) + [count] for key, count in sorted(starts.items())],
        'clean_ends': [list(key) + [count] for key, count in sorted(ends.items())]}


def process_evidence(directory, *, stage, multi_target=False, condition='clean'):
    directory = Path(directory)
    log, codes = directory / 'ros.log', directory / 'process_exit_codes.json'
    require(not log.is_symlink() and log.stat().st_size <= 16 * 1024 * 1024, 'Unsafe/oversized original ROS log')
    actual = process_verdict(log.read_text(encoding='utf-8', errors='replace'), guard.read_small(codes),
                            stage=stage, multi_target=multi_target, condition=condition)
    require(actual['status'] == 'PASS', 'Owned process cleanup failed: ' + str(actual['errors']))
    return {**actual, 'ros_log_sha256': guard.sha(log), 'process_exit_codes_sha256': guard.sha(codes)}
