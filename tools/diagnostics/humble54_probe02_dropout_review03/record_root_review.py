"""Bind the actual owner05 stop and reviewed original frontier without changing it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'results/diagnostics/humble54_probe02_dropout_review03'

def binding(path, reference=None):
    return {'path': reference or str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    prior = ROOT / 'tools/experiment_orchestration/humble54_pending_collector05_registered/registered_profile05.json'
    profile = json.loads(prior.read_bytes())
    audit = json.loads((OUTPUT / 'native_prefix_audit.json').read_bytes())
    row = audit['closed'][-1]
    assert len(audit['closed']) == 3 and len(audit['pending_ids']) == 13
    assert row['original_status'] == 'INCOMPLETE_EVIDENCE' and row['original_navigation_verdict'] == 'PASS'
    assert row['known_algorithm_failures'] == []
    outer = ROOT / 'results/diagnostics/humble54_probe02_windows_owner05/terminal.json'
    native_dir = Path(r'\\wsl.localhost\UAVHumble22\root\uav_tracking_collection54_probe02_owner05')
    native = json.loads((native_dir / 'terminal.json').read_bytes())
    assert native['error'] == 'ValueError: New unknown behavior evidence; root must inspect: short:detector_interruption_observed'
    assert native['current_child']['returncode'] == 0
    assert json.loads(outer.read_bytes())['closure_verified'] is True
    stable = {'id': row['slot_id'], 'original_status': row['original_status'],
              'marker': row['original_marker'], 'terminal': row['original_terminal'],
              'record_sha256': row['record_sha256'], 'started_utc': row['original_started_utc'],
              'finished_utc': row['original_finished_utc']}
    review = {'schema_version': 1, 'status': 'ROOT_REVIEWED_CLOSED_METADATA_FRONTIER_PRESERVED',
              'kind': 'SHORT_DETECTOR_UNKNOWN_COLLECTOR_STOP', 'segment_id': 'owner05',
              'reviewed_utc': datetime.now(timezone.utc).isoformat(),
              'plan': {**profile['plan'], 'plan_sha256': profile['plan_digest']},
              'outer_terminal': binding(outer),
              'native_terminal': binding(native_dir / 'terminal.json', '/root/uav_tracking_collection54_probe02_owner05/terminal.json'),
              'events': binding(native_dir / 'events.jsonl', '/root/uav_tracking_collection54_probe02_owner05/events.jsonl'),
              'original_error': native['error'], 'frontier_record': row, 'frontier': stable,
              'original_engineering_verdict_preserved': True,
              'historical_unknown': {'slot_id': row['slot_id'], 'terminal': row['original_terminal'],
                                     'field': 'surface:short:detector_interruption_observed', 'value': None,
                                     'unobserved_checks': row['unobserved_checks'], 'original_status': row['original_status']},
              'short_input_review': binding(ROOT / 'results/diagnostics/humble54_probe02_person_dropout_input_extract03/input_evidence_evaluation03.json'),
              'prefix_audit': binding(OUTPUT / 'native_prefix_audit.json'),
              'finding': 'Both obscured source frames at 29.8 and 29.9 seconds were dropped by the registered seed4/200ms dropout. The detector received no input opportunity inside the short window. Preserve null and original INCOMPLETE; collection may continue after actual closure, without rerunning this slot or treating this input audit as detector performance.',
              'scope': 'Read-only preserved execution frontier review, not engineering or formal readiness.'}
    path = OUTPUT / 'root_review.json'
    with path.open('x', encoding='utf8') as handle:
        json.dump(review, handle, indent=2)
        handle.write('\n')
    print(json.dumps(binding(path)))

if __name__ == '__main__':
    main()
