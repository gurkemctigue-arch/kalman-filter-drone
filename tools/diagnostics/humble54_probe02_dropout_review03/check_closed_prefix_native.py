"""Audit the three actual closed slots, retaining the precisely reviewed null."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import types

def load(path, expected):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module

def main():
    repo = Path(__file__).resolve().parents[3]
    frozen = Path('/root/uav_tracking_fullplan_v4_humble54')
    collector = load(repo / 'tools/experiment_orchestration/humble54_pending_collector05_source/collect_humble54_pending05.py', 'f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1')
    runner = load(frozen / 'scripts/run_reliability_v4.py', collector.RUNNER_SHA)
    evidence = json.loads((repo / 'results/diagnostics/humble54_probe02_person_dropout_input_extract03/input_evidence_evaluation03.json').read_bytes())
    assert evidence['status'] == 'UPSTREAM_INPUT_INTERRUPTION_CORROBORATED' and evidence['errors'] == []
    history = {'person_extension_dropout_seed004': 'c09f95ee3c4d5f14847bcbea82e8795b11cab6f5184fe735abac4c22decaeba8'}
    pins = {'plan': collector.PLAN_SHA, 'entry': collector.ENTRY_SHA, 'capture_profiles': collector.CAPTURE_PROFILES, 'history': history, 'minimum_prefix': 3}
    started = datetime.now(timezone.utc).isoformat()
    plan, closed, pending = collector.initial_check((frozen / 'results/reliability_v4_humble54_extension16_probe02_matrix/plan.json').resolve(strict=True), Path('/mnt/d/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh'), 'person_extension_dropout_seed004', pins, runner)
    report = {'kind': 'ACTUAL_THREE_CLOSED_SLOTS_READONLY_AUDIT', 'started_utc': started,
              'finished_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS_PRESERVED_PREFIX_ONLY',
              'closed': closed, 'pending_ids': [row['id'] for row in pending],
              'scope': 'Original INCOMPLETE and unknown retained; no flight, retry or formal admission.'}
    output = repo / 'results/diagnostics/humble54_probe02_dropout_review03/native_prefix_audit.json'
    with output.open('x', encoding='utf8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'status': report['status'], 'closed': len(closed), 'pending': len(pending)}))

if __name__ == '__main__':
    main()
