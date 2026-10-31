"""Pure source/build/class/runtime bindings for the separately owned Humble41 core.

No planning, flight, observer, probe40 import, or dependency monkeypatching.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import subprocess
import reviewed_freeze_build as generic
import reviewed_timing_diagnostic as stable
EXTERNAL = Path(__file__).resolve().parent
ROOT = '/root/uav_tracking_fullplan_v4_humble41'
SCOPE = 'HUMBLE41_SOURCE_BUILD_CLASS_RUNTIME_BINDINGS_ONLY'
STABLE_CANONICAL = '89f9971915440e86184505bb9846356bb726a08489600f5911f3d4c2a12d656d'
OWN_FILES = ('source_runtime41.py', 'test_source_runtime41.py')
PACING_FIELD = 'simulation_pacing_registration'
ADAPTER_FIELD = 'px4_adapter_publish_rate_hz'
ADAPTER_FLAG = '--px4-adapter-publish-rate-hz'
EXCLUSIVE_FIELD = 'navigation_exclusive_reference'
EXCLUSIVE_FLAG = '--exclusive-navigation-reference'
PROTOCOL_PATH = 'planning/reliability-v4-preregistration.json'
EXPECTED_CLASS_POLICY = {'car': {EXCLUSIVE_FIELD: True, 'explicit': True},
                         'person': {EXCLUSIVE_FIELD: False, 'explicit': False}}
EXPECTED_PACING_V2 = {'revision': 'simulation_rtf0125_wall1000_adapter50_v2',
    'real_time_factor': .125, 'flight_wall_timeout_s': 1000., 'follow_duration_s': 75.,
    'max_inference_rate_hz': 10., 'physical_identity_sample_period_s': .1,
    'scope': 'simulation_cpu_wall_resource_and_adapter_heartbeat_only',
    'safety_source_time_gates': 'unchanged', ADAPTER_FIELD: 50.}
require, sha, canonical = generic.require, generic.sha, generic.canonical
read_small = generic.read_small


def tool_manifest():
    require(Path(stable.__file__).resolve(strict=True) == (EXTERNAL/'reviewed_timing_diagnostic.py').resolve(strict=True)
        and canonical(stable.tool_manifest()) == STABLE_CANONICAL, 'Original stable dependency changed')
    files = {}
    for name in OWN_FILES:
        path = EXTERNAL/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= generic.MAX_SMALL,
            'Missing bounded source41 binding helper/test')
        files[name] = sha(path)
    return {'schema_version': 1, 'scope': SCOPE, 'files': files,
        'stable_tools_canonical_sha256': STABLE_CANONICAL,
        'frozen_root': ROOT, 'single_probe_requirement': False,
        'dependency_globals_modified': False, 'runtime_actions_exposed': False,
        'required_simulation_pacing': EXPECTED_PACING_V2, 'expected_class_policy': EXPECTED_CLASS_POLICY}


def build_evidence(review):
    expected = {'summary': ROOT+'/results/freeze_validation/build_validation_summary.json'}
    for action in ('build', 'validate'):
        expected[action+'_terminal'] = generic.LINUX_EXTERNAL+'/reviewed_freeze_actions_v4_humble41/'+action+'/action.terminal.json'
    require(review['frozen_root'] == ROOT, 'Only the new41 root is supported')
    return {name: stable.metadata_binding(path, json_only=True) for name, path in expected.items()}

def validate_class_policy(protocol, runner=None):
    require(isinstance(protocol, dict) and isinstance(protocol.get('resources'), dict),
        'Actual41 class resources required')
    resources = protocol['resources']
    require(isinstance(resources.get('car'), dict) and resources['car'].get(EXCLUSIVE_FIELD) is True
        and isinstance(resources.get('person'), dict) and EXCLUSIVE_FIELD not in resources['person'],
        'Actual41 requires explicit car exclusive navigation and absent implicit-off person')
    if runner is not None:
        require(runner.exclusive_navigation_declared(protocol)
            and runner.exclusive_navigation_summary(protocol) == {'car': True, 'person': False},
            'Frozen normal runner must recognize the explicit car-only exclusive policy')
    return EXPECTED_CLASS_POLICY

def source_policy_binding(review):
    """Bind actual frozen registration bytes; never assume a future commit."""
    path = Path(ROOT)/PROTOCOL_PATH
    policy = validate_class_policy(read_small(path))
    binding = stable.metadata_binding(path, json_only=True)
    # checked_build/action_binding verify the complete actual frozen manifest.
    # The protocol belongs to its files map; it need not belong to the separate
    # flight-critical classified subset. Bind its actual entry explicitly here.
    manifest_path = Path(ROOT)/'results/freeze_validation/source_freeze_manifest.json'
    manifest = read_small(manifest_path)
    manifest_binding = stable.metadata_binding(manifest_path, json_only=True)
    classified_maps = (review.get('classified_source_hashes', {}),
        manifest.get('classified_source_hashes', {}) if isinstance(manifest, dict) else None)
    candidate = review.get('candidate_protocol', {})
    require(review.get('frozen_root') == ROOT
        and review.get('files', {}).get(PROTOCOL_PATH) == binding['sha256']
        and isinstance(manifest, dict) and manifest.get('files', {}).get(PROTOCOL_PATH) == binding['sha256']
        and all(isinstance(mapping, dict)
            and (PROTOCOL_PATH not in mapping or mapping[PROTOCOL_PATH] == binding['sha256'])
            for mapping in classified_maps)
        and candidate.get('path') == review.get('source_root', '')+'/'+PROTOCOL_PATH
        and candidate.get('sha256') == binding['sha256']
        and candidate.get('exclusive_navigation') == {'car': True, 'person': False},
        'Actual frozen41 protocol differs from final reviewed source/class policy')
    return {'protocol': binding, 'source_manifest': manifest_binding, 'expected_class_policy': policy}

def entry_binding(review, built):
    require(canonical(tool_manifest()) == built['_reviewed_tools_sha256'], 'Reviewed runtime tool changed')
    actual = generic.action_binding(review, 'validate')
    require(actual['source'] == built['source'] and actual['closed_original_evidence'] == built['closed_original_evidence'],
        'Frozen source or retained historical evidence changed')
    for expected in built['bound_build_metadata'].values():
        require(stable.metadata_binding(expected['path'], json_only=Path(expected['path']).suffix == '.json') == expected,
            'Actual build metadata changed')
    return {'source_review': review['_review_binding'], 'source': built['source'],
        'closed_original_evidence': built['closed_original_evidence'],
        'build_metadata': built['bound_build_metadata'], 'tools_canonical_sha256': built['_reviewed_tools_sha256'],
        'exclusive_navigation_policy': source_policy_binding(review)}

def require_runtime(review, checks):
    generic.require_linux()
    require(os.environ.get('ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PROJECT_ROOT') == ROOT
        and os.environ.get('STAGE1_ROS_DISTRO') == 'humble' and os.environ.get('STAGE1_PX4_ROOT') == generic.PX4_ROOT
        and os.environ.get('STAGE1_ROS_GZ_WS') == generic.BRIDGE and os.environ.get('HUMBLE22_ROS_GZ_WS') == generic.BRIDGE,
        'Use the explicit41 isolated runtime wrapper')
    environment = checks.require_environment_contract()
    runtime = generic.runtime_contracts(review, ROOT)
    require(sha(checks.AGENT) == checks.AGENT_SHA256, 'Actual Agent bytes changed')
    results = {}
    for name, command in {'agent_command': ['/bin/bash', '-c', 'command -v MicroXRCEAgent'],
        'agent_ldd': ['ldd', checks.AGENT], 'car_check': ['/bin/bash', ROOT+'/scripts/run_stage1_flight.sh', 'check', 'car']}.items():
        result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        require(result.returncode == 0 and result.stdout.strip(), 'Runtime preflight failed: '+name)
        require(name != 'agent_command' or result.stdout.strip() == checks.AGENT, 'Agent command escaped')
        require(name != 'agent_ldd' or 'not found' not in result.stdout.lower(), 'Agent linker dependency unavailable')
        results[name] = {'command': command, 'returncode': result.returncode,
            'output_lines': sorted(re.sub(r'\(0x[0-9a-fA-F]+\)', '(address omitted)', result.stdout).splitlines())}
    return {'environment': environment, 'runtime_contracts': runtime, 'checks': results,
        'exclusive_navigation_policy': source_policy_binding(review)}

def validate_supported_birth_runtime(target_class, configuration, parameters):
    """Bind the source41 birth policy to saved values, including implicit-off person."""
    require(target_class in ('car', 'person'), 'Known target class required')
    expected = target_class == 'car'
    require(isinstance(configuration, dict) and isinstance(parameters, dict)
        and configuration.get('car_surface_recovery') is expected,
        'Actual source41 run_config must retain strict class surface policy')
    checked = {}
    for name, field in (('uav_tracking_detection', 'car_surface_recovery_enabled'),
                        ('uav_tracking_state_estimator', 'supported_birth_confirmation_required')):
        node = parameters.get(name)
        values = node.get('ros__parameters') if isinstance(node, dict) else None
        require(isinstance(values, dict) and values.get(field) is expected,
            'Actual source41 archived class policy differs: '+name+':'+field)
        checked[name+':'+field] = expected
    return {'target_class': target_class, 'run_config_car_surface_recovery': expected,
        'runtime_parameters': checked}
