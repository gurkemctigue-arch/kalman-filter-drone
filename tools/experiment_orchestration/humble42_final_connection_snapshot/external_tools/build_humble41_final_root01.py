"""Build/verify an actually prepared final root; never register, plan or fly.

This external helper is inert on import. The shell wrapper creates a fresh
Humble build environment, then a separate sourced final-root Python process
verifies generated modules and real CDR type support. All outputs are exclusive.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import prepare_humble41_final_root01 as preparation

EXTERNAL = Path(__file__).resolve().parent
WRAPPER = EXTERNAL / 'build_humble41_final_root01.sh'
PREPARATION_SHA = '4e97c4a0bd621069630d2afaa2664c11f139dfbc623c4efa9f59938fd240c0d7'
VENV_PYTHON = Path('/root/uav_humble22/venv/bin/python')
PX4_ROOT = Path('/root/uav_humble22/PX4-Autopilot-v4mag')
PX4_MSGS = Path('/root/uav_humble22/px4_msgs_ws')
BRIDGE = Path('/root/uav_humble22/ros_gz_shutdown_A01_ws')
FASTCDR = Path('/opt/ros/humble/lib/cmake/fastcdr')
AGENT = '/root/uav_humble22/agent_install'
PACKAGES = ('uav_tracking_interfaces', 'uav_tracking_nodes', 'uav_tracking_bringup', 'uav_tracking_px4_adapter')
MODULES = ('uav_tracking.core', 'uav_tracking.core.target_manager', 'uav_tracking_nodes.stage2_telemetry',
    'uav_tracking_nodes', 'uav_tracking_nodes.detector_node', 'uav_tracking_nodes.inference_timing',
    'uav_tracking_nodes.inference_worker', 'uav_tracking_interfaces.msg',
    'uav_tracking_interfaces.msg._target_observation_array', 'uav_tracking_interfaces.msg._target_state',
    'uav_tracking_interfaces.msg._target_observation', 'uav_tracking_interfaces.msg._navigation_overlap')
ENVIRONMENT = ('PATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'CMAKE_MODULE_PATH',
    'CMAKE_FRAMEWORK_PATH', 'CMAKE_APPBUNDLE_PATH', 'CMAKE_INCLUDE_PATH', 'CMAKE_LIBRARY_PATH',
    'CMAKE_PROGRAM_PATH', 'CPATH', 'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH',
    'PKG_CONFIG_PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME',
    'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CC', 'CXX', 'CMAKE_TOOLCHAIN_FILE',
    'CMAKE_SYSROOT', 'CMAKE_FIND_ROOT_PATH', 'CMAKE_GENERATOR', 'CMAKE_GENERATOR_PLATFORM', 'CMAKE_GENERATOR_TOOLSET',
    'COLCON_DEFAULTS_FILE', 'COLCON_HOME',
    'fastcdr_DIR', 'FastCDR_DIR', 'FASTCDR_ROOT', 'FASTDDS_ROOT',
    'HUMBLE22_PROJECT_ROOT', 'STAGE1_PROJECT_ROOT', 'HUMBLE22_ROS_GZ_WS', 'STAGE1_ROS_GZ_WS',
    'HUMBLE22_PX4_ROOT', 'STAGE1_PX4_ROOT', 'STAGE1_PX4_MSGS_WS', 'STAGE1_PYTHON_EXECUTABLE',
    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MAKEFLAGS', 'CMAKE_BUILD_PARALLEL_LEVEL')
require, sha, read, binding, write_new = (preparation.require, preparation.sha, preparation.read,
    preparation.file_binding, preparation.write_new)
KIND = 'HUMBLE41_FINAL_ROOT01_COLD_BUILD_AND_SOURCE_ISOLATION'
SKIP_CONTRACT_SHA = '9a4f9d8584077d5c6ebbc099cb35b0c56746bbd725b0893882814bdc87b92406'
BRIDGE_LIFECYCLE = EXTERNAL / 'humble23_bridge_shutdown_diagnostic01/A01_final_validation01.json'
BRIDGE_LIFECYCLE_SHA = 'a5c8d2a593d4c8ea17a809723f12dafca28cca016b1e5aa4ae3934878ac1ed1b'
OWN_FILES = ('prepare_humble41_final_root01.py', 'build_humble41_final_root01.py',
    'build_humble41_final_root01.sh', 'humble41_final_root_empty_overlay01.json',
    'test_prepare_build_humble41_final_root01.py')


def now():
    return datetime.now(timezone.utc).isoformat()


def tools():
    return {str(path): sha(path) for path in (Path(__file__).resolve(), WRAPPER,
        EXTERNAL / 'prepare_humble41_final_root01.py', EXTERNAL / 'humble33_skip_contract.py')}


def tool_manifest():
    """Portable release identity only; no source scan or runtime operation."""
    require(sha(EXTERNAL / 'humble33_skip_contract.py') == SKIP_CONTRACT_SHA,
        'Reviewed frozen platform skip contract changed')
    return {'schema_version': 1, 'scope': 'HUMBLE41_FINAL_ROOT_PREPARATION_AND_COLD_BUILD_ONLY',
        'files': {name: sha(EXTERNAL / name) for name in OWN_FILES},
        'dependencies': {'humble33_skip_contract.py': SKIP_CONTRACT_SHA},
        'actual_source_root': preparation.SOURCE_ROOT.as_posix(),
        'actual_source_review_sha256': preparation.BASE_REVIEW_SHA256,
        'actual_source_manifest_sha256': preparation.BASE_MANIFEST_SHA256,
        'actual_source_canonical_sha256': preparation.BASE_CANONICAL_SHA256,
        'runtime': preparation.RUNTIME, 'overlay_policy': 'EXPLICIT_EMPTY_ONLY',
        'requires_three_planning_drafts': True, 'core_import_modules': list(MODULES),
        'package_names': list(PACKAGES), 'cdr_check_count': 11,
        'capacity_or_closure_admission_claimed': False,
        'final_root_selected': False, 'actual_copy_or_build_claimed': False,
        'formal_admission_or_seed_use_authorized': False}


def validate_final_paths(root, results, path):
    require(root.parent == Path('/root')
        and re.fullmatch(r'uav_tracking_fullplan_[A-Za-z0-9_]+', root.name)
        and root != preparation.SOURCE_ROOT, 'Use an independent actual final root')
    require(re.fullmatch(r'/mnt/d/.+/results/frozen_fullplan_[A-Za-z0-9_]+', str(results))
        and root.is_dir() and not root.is_symlink() and root.resolve(strict=True) == root
        and results.is_dir() and not results.is_symlink() and results.resolve(strict=True) == results,
        'Final source/results paths must be explicit and unaliased')
    require((root / 'results').is_symlink() and (root / 'results').resolve(strict=True) == results
        and path.resolve(strict=True) == results / 'freeze_validation/source_preparation_outcome.json',
        'Successful outcome must belong to the bound final results store')


def validate_receipt(path, digest):
    """Metadata-only actual41 authorization; inspect is never a copy receipt."""
    path = Path(path)
    require(re.fullmatch(r'[0-9a-f]{64}', digest or '') and sha(path) == digest,
        'Bind the actual successful preparation outcome SHA256')
    outcome = read(path)
    require(outcome.get('schema_version') == 1 and outcome.get('kind') == preparation.KIND
        and outcome.get('status') == 'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED'
        and outcome.get('source_unchanged') is True, 'An actual successful copy outcome is required')
    require(outcome.get('build_executed') is False and outcome.get('plans_created') is False
        and outcome.get('protocols_registered') is False and outcome.get('flights_executed') == 0
        and outcome.get('formal_seed_use') is False, 'Preparation scope differs')
    proposal = outcome['proposal']
    review, manifest = preparation.validate_proposal_authority(proposal)
    require(proposal['tool']['sha256'] == PREPARATION_SHA, 'Reviewed actual41 preparer bytes differ')
    root, results = Path(proposal['destination_root']), Path(proposal['results_root'])
    validate_final_paths(root, results, path)
    require(read(results / 'freeze_validation/source_preparation_started.json') == proposal,
        'Original preparation started receipt differs')
    preparation_manifest = results / 'freeze_validation/source_sha256.txt'
    require(outcome.get('preparation_source_manifest') == binding(preparation_manifest)
        and preparation_manifest.read_text(encoding='utf-8') == ''.join(
            digest + '  ' + name + '\n' for name, digest in sorted(review['files'].items())),
        'Original preparation source manifest changed; retain it across future registrations')
    require(sha(EXTERNAL / 'humble33_skip_contract.py') == SKIP_CONTRACT_SHA,
        'Reviewed frozen platform skip contract changed')
    return {'outcome': outcome, 'proposal': proposal, 'review': review, 'root': root, 'results': results,
        'attempt': results / 'freeze_validation/final_root_build41_01', 'preparation': binding(path)}


def source_check(context):
    proposal = context['proposal']
    preparation.validate_proposal_authority(proposal)
    require(context['outcome'].get('preparation_source_manifest') == binding(
        context['results'] / 'freeze_validation/source_sha256.txt'), 'Preparation source manifest changed')
    for name in preparation.BOUND_INPUTS:
        require(binding(Path(proposal[name]['path'])) == proposal[name], 'Bound preparation input changed: ' + name)
    require(preparation.inventory(preparation.SOURCE_ROOT) == proposal['original_whole_tree_inventory'],
        'Original development source changed since actual copy')
    result = preparation.verify_prepared(proposal)
    require(result == context['outcome'].get('source_verification'), 'Successful copy verification differs')
    classifier = preparation.frozen_classifier(context['root'])
    require(proposal['flight_source_hashes'] == classifier.flight_source_hashes(proposal['original_classified_source_hashes']),
        'Final flight source differs from the actual development source')
    require(binding(Path(context['preparation']['path'])) == context['preparation'],
        'Actual successful preparation outcome changed during source verification')
    return result


def require_environment(context, *, build):
    root, review = context['root'], context['review']
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22',
        'Use the actual isolated UAVHumble22 Linux distribution')
    require(Path(sys.executable) == VENV_PYTHON and os.environ.get('ROS_DISTRO') == 'humble',
        'Use the actual Humble virtual-environment Python')
    for key, expected in {'STAGE1_PROJECT_ROOT': root, 'HUMBLE22_PROJECT_ROOT': root,
            'HUMBLE22_ROS_GZ_WS': BRIDGE, 'STAGE1_ROS_GZ_WS': BRIDGE,
            'STAGE1_PX4_ROOT': PX4_ROOT, 'HUMBLE22_PX4_ROOT': PX4_ROOT,
            'STAGE1_PX4_MSGS_WS': PX4_MSGS, 'STAGE1_PYTHON_EXECUTABLE': VENV_PYTHON}.items():
        require(os.environ.get(key) == str(expected), 'Incorrect selected runtime path: ' + key)
    require(review.get('runtime') == preparation.RUNTIME, 'Actual41 review selected another runtime')
    values = {name: os.environ.get(name) for name in ENVIRONMENT}
    if build:
        require(all(AGENT not in (value or '') for value in values.values()), 'Agent runtime prefix polluted build')
        for name in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CC', 'CXX', 'CMAKE_TOOLCHAIN_FILE',
                'CMAKE_SYSROOT', 'CMAKE_FIND_ROOT_PATH', 'CMAKE_GENERATOR', 'CMAKE_GENERATOR_PLATFORM', 'CMAKE_GENERATOR_TOOLSET',
                'COLCON_DEFAULTS_FILE', 'COLCON_HOME'):
            require(not values[name], 'Inherited compiler/toolchain override is not allowed: ' + name)
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'CMAKE_BUILD_PARALLEL_LEVEL'):
            require(values[name] == ('2' if name == 'CMAKE_BUILD_PARALLEL_LEVEL' else '1'),
                'Explicit bounded build concurrency required: ' + name)
        for key in ('AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH'):
            for entry in (values[key] or '').split(':'):
                require(not entry or not re.match(r'/root/uav_tracking_fullplan_', entry)
                    or key == 'PYTHONPATH' and entry == str(root), 'Old/final install prefix in cold build: ' + key)
    return values


def reject_old_build_paths(text, root):
    for match in re.findall(r'/root/uav_tracking_fullplan_[A-Za-z0-9_]+', text):
        require(match == str(root), 'Actual compiler/cache/link input points at an old project root: ' + match)


def audit_fastcdr(root):
    package = root / 'ros2_ws/build/uav_tracking_interfaces'
    cache = package / 'CMakeCache.txt'
    text = cache.read_text()
    reject_old_build_paths(text, root)
    selected = re.findall(r'(?m)^fastcdr_DIR:[^=]+=(.+)$', text)
    require(len(selected) == 1 and Path(selected[0]).resolve(strict=True) == FASTCDR.resolve(strict=True)
        and AGENT not in text, 'Actual CMake FastCDR provenance differs')
    flags, links = sorted(package.glob('CMakeFiles/*/flags.make')), sorted(package.glob('CMakeFiles/*/link.txt'))
    require(flags and links and all(AGENT not in path.read_text() for path in [*flags, *links]),
        'Actual compiler/linker flags missing or Agent-contaminated')
    for path in [*flags, *links]:
        reject_old_build_paths(path.read_text(), root)
    fastrtps = [path for path in flags if 'fastrtps' in str(path)]
    require(len(fastrtps) >= 2 and all('/opt/ros/humble/include' in path.read_text() for path in fastrtps),
        'Actual FastRTPS compiler include provenance missing')
    return {'status': 'MATCHES_HUMBLE_SYSTEM_FASTCDR', 'root': str(root), 'fastcdr_directory': str(FASTCDR),
        'agent_compile_prefix_absent': True, 'compiler_flag_files': len(flags), 'fastrtps_flag_files': len(fastrtps),
        'inputs_sha256': {str(path): sha(path) for path in [cache, FASTCDR / 'fastcdr-config.cmake', *flags, *links]}}


def bridge_provenance(context):
    root, review = context['root'], context['review']
    name = 'uav_tracking.ros_gz_runtime'
    module = importlib.import_module(name)
    require(Path(module.__file__).resolve(strict=True) == root / 'uav_tracking/ros_gz_runtime.py',
        'Bridge verifier imported from another source root')
    registration_path = root / 'config/ros_gz_runtime_humble22.json'
    registration = read(registration_path)
    require(registration.get('overlay_root') == str(BRIDGE), 'Registered bridge overlay differs')
    result = module.verify_registration(registration, patch_path=root / 'patches/ros_gz_bridge_ownership_shutdown_A01.patch')
    require(result.get('status') == 'PASS', 'Actual selected bridge source/ELF closure differs')
    require(binding(BRIDGE_LIFECYCLE) == {'path': str(BRIDGE_LIFECYCLE), 'sha256': BRIDGE_LIFECYCLE_SHA},
        'Original reviewed shutdown_A01 lifecycle evidence changed')
    evidence = read(BRIDGE_LIFECYCLE)
    require(evidence.get('status') == 'PASS'
        and evidence.get('verification', {}).get('all_owned_processes_clean') is True,
        'Actual shutdown_A01 lifecycle was not verified')
    return {**result, 'original_reviewed_lifecycle_summary': binding(BRIDGE_LIFECYCLE),
        'lifecycle_diagnostic_reexecuted': False}


def audit_origins(context):
    root = context['root']
    modules, prefixes = {}, {}
    for name in (*MODULES, *context['review'].get('additional_import_modules', [])):
        location = Path(importlib.import_module(name).__file__).resolve(strict=True)
        require(location.is_relative_to(root), 'Final module escaped its source/build root: ' + name)
        modules[name] = str(location)
    for name in PACKAGES:
        prefix = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', name], text=True).strip()).resolve(strict=True)
        require(prefix.is_relative_to(root), 'Final ament prefix escaped its root: ' + name)
        prefixes[name] = str(prefix)
    bridge = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', 'ros_gz_bridge'], text=True).strip()).resolve(strict=True)
    require(bridge == (BRIDGE / 'install').resolve(strict=True), 'Bridge ament prefix fell back to another overlay')
    return {'root': str(root), 'module_files': modules, 'ros_package_prefixes': prefixes, 'isolated': True,
        'module_count': len(modules), 'ament_package_count': len(prefixes), 'bridge_package_prefix': str(bridge),
        'selected_bridge_overlay': str(BRIDGE), 'bridge_runtime_validation': bridge_provenance(context)}


def cdr_roundtrip():
    # The eleven real generated-message cases are identical to the actual
    # reviewed predecessor check; no mocks, ROS node, transport or simulator are involved.
    from rclpy.serialization import serialize_message, deserialize_message
    from uav_tracking_interfaces.msg import NavigationOverlap, TargetObservation, TargetObservationArray
    normal = NavigationOverlap()
    normal.candidate_a_id, normal.candidate_b_id = 7, 8
    normal.class_a_id, normal.class_b_id = 2, 0
    normal.bbox_a_px, normal.bbox_b_px = [10., 10., 20., 20.], [12., 13., 14., 14.]
    normal.u0, normal.v0, normal.width, normal.height = 12, 13, 2, 1
    normal.expected_pixel_count, normal.valid_pixel_count = 2, 2
    normal.rectangle_representable, normal.depth_complete = True, True
    normal.points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
    incomplete = NavigationOverlap()
    incomplete.candidate_a_id, incomplete.candidate_b_id = 7, 9
    incomplete.class_a_id, incomplete.class_b_id = 2, 3
    incomplete.bbox_a_px, incomplete.bbox_b_px = [-3e9, 5., 5., 12.], [-3e9, 7., 10., 14.]
    incomplete.u0, incomplete.v0 = -3, 7
    incomplete.width = incomplete.height = 0
    incomplete.expected_pixel_count = incomplete.valid_pixel_count = 0
    incomplete.rectangle_representable, incomplete.depth_complete = False, False
    incomplete.points_camera_m = []
    observation = TargetObservation()
    observation.candidate_id, observation.class_id = 7, 2
    observation.class_name, observation.camera_frame = 'car', 'camera_link'
    observation.depth_valid, observation.depth_m = True, 5.
    observation.navigation_bbox_inside_image = True
    observation.navigation_bbox_complete = False
    observation.navigation_overlap_count = 2
    observation.navigation_points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
    observation.navigation_visibility_support_camera_m = [.5, -.25, 5.]
    frame = TargetObservationArray()
    frame.header.stamp.sec, frame.header.stamp.nanosec = 12, 345678901
    frame.header.frame_id = 'camera_link'
    observation.header = frame.header
    frame.observations = [observation]
    frame.navigation_overlaps = [normal, incomplete]
    frame.navigation_ground_points_camera_m = [1., 2., 3.]
    wire = serialize_message(frame)
    decoded = deserialize_message(wire, TargetObservationArray)
    selected, = decoded.observations
    complete, unknown = decoded.navigation_overlaps
    checks = {
        'same_acquisition_header': decoded.header == frame.header and selected.header == decoded.header,
        'new_observation_flags_and_count': selected.navigation_bbox_inside_image is True
            and selected.navigation_bbox_complete is False and selected.navigation_overlap_count == 2,
        'original_full_cloud_preserved': list(selected.navigation_points_camera_m) == list(observation.navigation_points_camera_m),
        'exclusive_cloud_preserved_separately': list(selected.navigation_visibility_support_camera_m)
            == list(observation.navigation_visibility_support_camera_m)
            and len(selected.navigation_points_camera_m) != len(selected.navigation_visibility_support_camera_m),
        'pair_candidate_and_class_ids': (complete.candidate_a_id, complete.candidate_b_id,
            complete.class_a_id, complete.class_b_id) == (7, 8, 2, 0)
            and (unknown.candidate_a_id, unknown.candidate_b_id, unknown.class_a_id, unknown.class_b_id) == (7, 9, 2, 3),
        'complete_rectangle_and_counts': (complete.u0, complete.v0, complete.width, complete.height,
            complete.expected_pixel_count, complete.valid_pixel_count) == (12, 13, 2, 1, 2, 2)
            and complete.rectangle_representable is True and complete.depth_complete is True,
        'complete_float32_points': list(complete.points_camera_m) == list(normal.points_camera_m)
            and len(complete.points_camera_m) == complete.expected_pixel_count * 3,
        'signed_origin_and_incomplete_wire_fields': unknown.u0 == -3 and unknown.v0 == 7
            and unknown.rectangle_representable is False and unknown.depth_complete is False
            and unknown.width == unknown.height == unknown.expected_pixel_count == unknown.valid_pixel_count == 0
            and not unknown.points_camera_m,
        'raw_bbox_fields': list(complete.bbox_a_px) == list(normal.bbox_a_px)
            and list(complete.bbox_b_px) == list(normal.bbox_b_px)
            and list(unknown.bbox_a_px) == list(incomplete.bbox_a_px)
            and list(unknown.bbox_b_px) == list(incomplete.bbox_b_px),
        'ground_support_preserved': list(decoded.navigation_ground_points_camera_m) == [1., 2., 3.],
        'pair_count_matches_observation': len(decoded.navigation_overlaps) == selected.navigation_overlap_count,
    }
    return {'scope': 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION',
        'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
        'serialized_bytes': len(wire), 'serialized_sha256': hashlib.sha256(wire).hexdigest(), 'execution_count': 1}


def run_suite(context):
    from humble33_skip_contract import SKIP_SOURCE_PATHS, validate_skip_sources, validate_observed_skips
    root, attempt = context['root'], context['attempt']
    log = attempt / 'unittest.log'
    started = now()
    with log.open('x') as stream:
        process = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
            cwd=root, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    text = log.read_text()
    observed = re.search(r'Ran (\d+) tests in ([0-9.]+)s', text)
    result = {'status': 'FAIL', 'started_utc': started, 'finished_utc': now(), 'returncode': process.returncode,
        'tests': int(observed[1]) if observed else None, 'log': binding(log)}
    try:
        result['skip_source_contract'] = validate_skip_sources({name: (root / name).read_text() for name in SKIP_SOURCE_PATHS})
        result['actual_skipped_tests'] = validate_observed_skips(text)
        node = shutil.which('node')
        node_docx = subprocess.run([node, '-e', 'require.resolve("docx")'], cwd=root,
            capture_output=True, text=True).returncode if node else None
        require(shutil.which('bash') is not None and shutil.which('zstd') is not None
            and shutil.which('powershell') is None and not (node and node_docx == 0),
            'Actual tools no longer justify exactly the five Linux platform skips')
        require(process.returncode == 0 and observed is not None and int(observed[1]) > 0
            and re.search(r'(?m)^OK \(skipped=5\)$', text) and 'FAILED' not in text,
            'Actual full suite did not pass with exactly its documented platform skips')
        result['status'] = 'PASS'
    except (ValueError, SyntaxError) as error:
        result['validation_error'] = type(error).__name__ + ':' + str(error)
    write_new(attempt / 'full_suite.json', result)
    require(result['status'] == 'PASS', 'Actual final-root suite failed; retain logs and do not retry this root')
    return result


def verify(context, run_full_suite):
    require_environment(context, build=False)
    attempt = context['attempt']
    started = read(attempt / 'started.json')
    require(started['preparation'] == context['preparation'] and started['tools_sha256'] == tools(),
        'Bound preparation/build helpers changed after build started')
    require(binding(Path(started['colcon_defaults']['path'])) == started['colcon_defaults']
        and read(Path(started['colcon_defaults']['path'])) == {}, 'Exclusive empty colcon defaults changed')
    fastcdr = read(attempt / 'fastcdr_provenance.json')
    require(fastcdr == audit_fastcdr(context['root']), 'Actual FastCDR evidence changed before imports')
    origins = audit_origins(context)
    write_new(attempt / 'import_isolation.json', origins)
    cdr = cdr_roundtrip()
    write_new(attempt / 'generated_message_roundtrip.json', cdr)
    require(cdr['status'] == 'PASS' and len(cdr['checks']) == 11, 'Actual generated-message CDR round trip failed')
    suite = run_suite(context) if run_full_suite else {'status': 'NOT_RUN', 'executed': False}
    source_after = source_check(context)
    require(started['source_verification_before'] == source_after, 'Final source changed during actual build/checks')
    require(tools() == started['tools_sha256'], 'Build/verification helper changed during final checks')
    result = {'schema_version': 1, 'kind': KIND, 'status': 'PASS_BUILD_AND_STATIC_CHECKS_ONLY',
        'root': str(context['root']), 'finished_utc': now(), 'preparation': context['preparation'],
        'source_verification_after': source_after, 'modules': len(origins['module_files']),
        'ament_packages': len(origins['ros_package_prefixes']), 'actual_cdr_checks': len(cdr['checks']),
        'full_suite': suite, 'source_unchanged': True, 'tools_sha256': tools(),
        'flight_acceptance': 'NOT_EVALUATED', 'protocols_registered': False, 'formal_admitted': False,
        'formal_seed_use': False}
    write_new(attempt / 'verification_outcome.json', result)
    return result


def colcon_command(root, colcon):
    return [sys.executable, colcon, '--log-base', str(root / 'ros2_ws/log'), 'build',
        '--build-base', str(root / 'ros2_ws/build'), '--install-base', str(root / 'ros2_ws/install'),
        '--merge-install', '--symlink-install', '--packages-select', *PACKAGES,
        '--cmake-args', '-DPython3_EXECUTABLE=' + sys.executable, '-DPYTHON_EXECUTABLE=' + sys.executable,
        '-Dfastcdr_DIR=' + str(FASTCDR)]


def build(context, run_full_suite):
    environment = require_environment(context, build=True)
    root, attempt = context['root'], context['attempt']
    for name in ('build', 'install', 'log'):
        path = root / 'ros2_ws' / name
        require(not path.exists() and not path.is_symlink(), 'Cold build refuses existing tree: ' + name)
    require(not attempt.exists() and not attempt.is_symlink(), 'Exclusive build attempt already exists')
    source_before = source_check(context)
    colcon = shutil.which('colcon')
    require(colcon is not None and (FASTCDR / 'fastcdr-config.cmake').is_file(), 'Actual colcon/Humble FastCDR unavailable')
    command = colcon_command(root, colcon)
    attempt.mkdir(exist_ok=False)
    defaults = attempt / 'colcon_defaults.yaml'
    write_new(defaults, {})  # JSON empty object is valid YAML; avoids ~/.colcon/defaults.yaml.
    build_environment = dict(os.environ, COLCON_DEFAULTS_FILE=str(defaults))
    environment['COLCON_DEFAULTS_FILE'] = str(defaults)
    start, timer = now(), time.monotonic()
    write_new(attempt / 'started.json', {'schema_version': 1, 'kind': KIND, 'started_utc': start,
        'root': str(root), 'results': str(context['results']), 'preparation': context['preparation'],
        'source_verification_before': source_before, 'command': command, 'environment': environment,
        'colcon_defaults': binding(defaults),
        'tools_sha256': tools(), 'run_full_suite': run_full_suite, 'formal_seed_use': False})
    try:
        log = attempt / 'colcon_build.log'
        with log.open('x') as stream:
            process = subprocess.run(command, cwd=root / 'ros2_ws', stdout=stream,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=build_environment)
        write_new(attempt / 'colcon_exit.json', {'returncode': process.returncode, 'finished_utc': now(), 'log': binding(log)})
        require(process.returncode == 0, 'Actual colcon failed; preserve this root and log without retry')
        text = re.sub(r'\x1b\[[0-9;]*m', '', log.read_text())
        require(re.search(r'Summary:\s+4 packages finished', text), 'Actual four-package build summary missing')
        write_new(attempt / 'fastcdr_provenance.json', audit_fastcdr(root))
        args = ['bash', str(WRAPPER), '--verify-internal', '--preparation-outcome', context['preparation']['path'],
            '--preparation-sha256', context['preparation']['sha256']]
        if run_full_suite:
            args.append('--run-suite')
        with (attempt / 'verification.log').open('x') as stream:
            verification = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT)
        require(verification.returncode == 0, 'Final-root module/CDR/source validation failed; retain verification.log')
        result = read(attempt / 'verification_outcome.json')
        require(result.get('status') == 'PASS_BUILD_AND_STATIC_CHECKS_ONLY'
            and result.get('tools_sha256') == tools(), 'Actual final verification outcome missing/changed')
        outcome = {'schema_version': 1, 'kind': KIND,
            'status': 'FINAL_ROOT_BUILT_AND_STATIC_CHECKS_VERIFIED_NOT_REGISTERED_OR_FLOWN',
            'started_utc': start, 'finished_utc': now(), 'elapsed_wall_s': time.monotonic() - timer,
            'root': str(root), 'results': str(context['results']), 'preparation': context['preparation'],
            'verification': binding(attempt / 'verification_outcome.json'), 'four_packages_built': True,
            'full_suite_status': result['full_suite']['status'], 'source_unchanged': True,
            'protocols_registered': False, 'plans_created': False, 'flights_executed': 0,
            'formal_seed_use': False, 'formal_admitted': False,
            'claim_boundary': 'Actual cold build, module/ament/FastCDR/bridge closure and CDR checks only. Optional suite is explicit. Final registration, source seal, capacity admission and formal280 remain separate.'}
        write_new(attempt / 'outcome.json', outcome)
        print(json.dumps({'status': outcome['status'], 'outcome': str(attempt / 'outcome.json'),
            'full_suite_status': outcome['full_suite_status']}), flush=True)
        return outcome
    except BaseException as error:
        write_new(attempt / 'failed.json', {'schema_version': 1, 'kind': KIND, 'status': 'FAILED_RETAIN_ROOT_AND_ALL_LOGS',
            'started_utc': start, 'finished_utc': now(), 'error': type(error).__name__ + ':' + str(error),
            'automatic_retry': False, 'formal_seed_use': False, 'root': str(root)})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('root', 'build', 'verify'))
    parser.add_argument('--preparation-outcome', type=Path, required=True)
    parser.add_argument('--preparation-sha256', required=True)
    parser.add_argument('--run-suite', action='store_true')
    args = parser.parse_args(argv)
    require(sys.platform == 'linux', 'This actual final-root helper requires isolated Linux')
    context = validate_receipt(args.preparation_outcome, args.preparation_sha256)
    if args.action == 'root':
        print(context['root'])
    elif args.action == 'build':
        build(context, args.run_suite)
    else:
        verify(context, args.run_suite)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
