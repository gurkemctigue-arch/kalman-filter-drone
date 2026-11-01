"""Publish actual46 source after root peer review; never build or fly.

Unfilled actual pending SHA refuses before imports/IO. Exactly two status fields
may change. Original44 failed validation and45 stopped core/owner stay retained.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
EXPECTED_PENDING_SHA = '8e659a64d01b493dc3f0173148623ef9dac8b85298b133788eedfa3c67fb743e'
MAPS_SHA = '427be692d9706aa901b3843d92f5422ebff5cc076bbfd5f0942290af066ec4d8'
ADAPTER_SHA = 'a62535e473ee79d26bfee2704630ce20b3df6e0a01abd020c92da3a4d44af617'
COMMIT = 'de89a6696d60a113929c97bab775dc2258ef4d01'


def main():
    if not isinstance(EXPECTED_PENDING_SHA, str) or not re.fullmatch('[0-9a-f]{64}', EXPECTED_PENDING_SHA):
        raise ValueError('Actual independently reviewed46 pending SHA not yet fixed; publication refused')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(EXTERNAL))
    import reviewed_freeze_build as generic
    import development_freeze_build as development
    generic.require_linux()
    require = generic.require
    pending_path = EXTERNAL/'reviewed_freeze_review_v4_humble46_pending01.json'
    final_path = EXTERNAL/'reviewed_freeze_review_v4_humble46_01.json'
    receipt_path = EXTERNAL/'reviewed_freeze_source_humble46_root_peer01.json'
    maps_path = EXTERNAL/'source_from_closed43_to46_01/reviewed_commit46_maps01.json'
    adapter_path = EXTERNAL/'source_from_closed43_to46_01/assemble_closed43_to46_source.py'
    require(generic.sha(pending_path) == EXPECTED_PENDING_SHA and generic.sha(maps_path) == MAPS_SHA
            and generic.sha(adapter_path) == ADAPTER_SHA, 'Actual46 source/maps/adapter bytes changed')
    require(not any(path.exists() or path.is_symlink() for path in (final_path, receipt_path)), 'Fresh source46 publication required')
    pending, maps = generic.read_small(pending_path), generic.read_small(maps_path)
    require(pending['status'] == 'PENDING_ROOT_INDEPENDENT_REVIEW_NOT_EXECUTABLE'
            and pending['source_commit'] == maps['source_commit'] == COMMIT
            and pending['frozen_root'] == '/root/uav_tracking_fullplan_v4_humble46'
            and pending['baseline']['root'] == '/root/uav_tracking_fullplan_v4_humble43'
            and pending['files'] == maps['files']
            and pending['classified_source_hashes'] == maps['classified_source_hashes']
            and pending['allowed_delta'] == maps['allowed_delta']
            and pending['assembly_provenance']['runtime_delta_from43'] == maps['classified_delta']
            and 'runtime_identical_to44' not in pending['assembly_provenance'], 'Unexpected46 source/map/runtime delta')
    history_binding = pending['assembly_provenance']['original43_44_45_outcomes']
    require(generic.sha(history_binding['path']) == history_binding['sha256'], 'Actual historical metadata changed')
    history = generic.read_small(history_binding['path'])
    old44, old45 = history['historical44'], history['historical45']
    require(old44['actions']['validate']['status'] == 'FAILED'
            and old44['actions']['validate']['direct_child_returncode'] == 2
            and old44['suite']['status'] == 'FAIL' and old44['suite']['errors'] == 3
            and old44['healthy_validate_acceptance'] is False, 'Original44 failed validation must remain')
    require(old45['suite'] == {'status': 'PASS', 'tests': 1767, 'skipped': 5, 'execution_count': 1}
            and old45['core']['status'] == 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED'
            and old45['core']['returncode'] == 2 and old45['core']['planned_count'] == 12
            and old45['core']['attempt_count'] == 2 and old45['core']['terminal_count'] == 1
            and old45['core']['status_counts'] == {'PASS': 1, 'INFRASTRUCTURE_ERROR': 1, 'PENDING': 10}
            and old45['core']['final_errors'] == ['observer:ValueError:Owner outcome differs from original immutable D copy candidate']
            and old45['failed_owner']['healthy_cleanup'] is False
            and old45['runtime46_acceptance'] is False, 'Original45 healthy build/stopped core/failed owner must remain')
    spec = importlib.util.spec_from_file_location('_source46_publisher_reviewed_adapter', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    source = Path(pending['source_root'])
    runner = generic.runner_at(source)
    stream = adapter.stream_contract(source, generic.read_small(source/runner.PROTOCOL_PATH),
        pending['files'], pending['classified_source_hashes'], runner, generic, maps)
    require(stream == pending['candidate_protocol']['supervisor_stream_timing'], 'Actual46 stream/new gate source binding changed')
    review = deepcopy(pending)
    review['status'] = generic.FINAL_STATUS
    review['development_resource_override']['status'] = development.STATUS
    generic.validate_review(review)
    closed = generic.verify_closed_capsule(review)
    actual_source = generic.candidate_binding(review)
    supplement = development.supplement_binding(review)
    reverted = deepcopy(review)
    reverted['status'] = pending['status']
    reverted['development_resource_override']['status'] = pending['development_resource_override']['status']
    require(reverted == pending, 'Source publication changed more than two status fields')
    require(generic.sha(pending_path) == EXPECTED_PENDING_SHA and generic.sha(maps_path) == MAPS_SHA
            and generic.sha(adapter_path) == ADAPTER_SHA, 'Actual46 reviewed inputs changed during publication')
    generic.write_new(final_path, review)
    generic.write_new(receipt_path, {'schema_version': 1,
        'scope': 'ROOT_PEER_ACTUAL_SOURCE46_REVIEW_NOT_BUILD_OR_RUNTIME_ACCEPTANCE',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'result': 'PASS_SOURCE_PUBLICATION_ONLY',
        'pending': {'path': str(pending_path), 'sha256': EXPECTED_PENDING_SHA},
        'final': {'path': str(final_path), 'sha256': generic.sha(final_path)},
        'actual_candidate_binding': actual_source, 'closed_original_evidence': closed,
        'resource_supplement': supplement, 'actual_stream_newgate_source_binding': stream,
        'source_maps': {'path': str(maps_path), 'sha256': MAPS_SHA},
        'original45_stopped_core': old45['core'], 'original45_failed_owner': old45['failed_owner'],
        'only_two_status_fields_changed': True, 'build_or_flight_started': False,
        'original_failures_changed': False, 'automatic_next_action': False,
        'code': {'path': str(Path(__file__).resolve()), 'sha256': generic.sha(__file__)}})
    print({'status': 'PASS_SOURCE_PUBLICATION_ONLY', 'final': str(final_path),
           'sha256': generic.sha(final_path), 'receipt': str(receipt_path)})


if __name__ == '__main__':
    main()
