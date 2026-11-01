"""Review actual probe02 PENDING1 and publish only its new contract status."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
ROOT = '/root/uav_tracking_fullplan_v4_humble45'
sys.path.insert(0, ROOT)
sys.path.insert(0, str(EXTERNAL))
import probe_one45_recording_v2 as probe
import development_runner as core
import reviewed_freeze_build as generic

expected = 'e0db09b6f7f80af4db385e845cc286391180201fa9c9409daec6261768d56a2d'
pending_path = EXTERNAL/'probe_one_contract_reliability_v4_humble45_recording_probe02_pending01.json'
final_path = EXTERNAL/'probe_one_contract_reliability_v4_humble45_recording_probe02_final01.json'
receipt_path = EXTERNAL/'humble45_probe02_contract_root_peer01.json'
generic.require_linux()
generic.require(not final_path.exists() and not receipt_path.exists(), 'Fresh publication required')
generic.require(probe.pin(pending_path)['sha256'] == expected, 'Actual pending contract changed')
pending = probe.read(pending_path)
generic.require(pending['status'] == probe.PENDING and pending['prefix'] == probe.PREFIX
    and pending['frozen_root'] == ROOT and pending['tools_sha256'] == probe.canonical(probe.tool_manifest())
    == '853eba9b215e4c0298f0770c8b6e729af660076c97b633f9f8a485987eebb759'
    and pending['experiment'] == probe.experiment()
    and all(pending.get(k) is False for k in probe.FALSE), 'Actual nonformal single contract differs')
candidate_binding = pending['entry_binding']['candidate_manifest']
generic.require(candidate_binding['sha256'] == 'b20438f956f91cafe4e65e25b2f9341a0cf88a50abc6194372f0912065cdabe6', 'Candidate changed')
candidate, review = core.load_candidate(candidate_binding['path'], candidate_binding['sha256'])
runner = generic.runner_at(ROOT)
backend = SimpleNamespace(runner=runner, candidate=candidate, review=review, core=core)
plan_path = probe.checked(pending['plan_pending']['plan'])
plan = probe.read(plan_path)
reference = probe.validate_one(plan, backend, None, plan_path)
runner.verify_sources(plan)
probe.fresh(plan, runner)
generic.require(pending['plan_pending'] == probe.pending_identity(plan)
    and pending['original43_reference'] == reference, 'Actual original trial/reference changed')
terminal = probe.read(probe.checked(pending['plan_terminal']))
generic.require(terminal['scope'] == probe.SCOPE and terminal['action'] == 'plan'
    and type(terminal['returncode']) is int and terminal['returncode'] == 0
    and terminal['error'] is None and terminal['flights_started'] == 0
    and terminal['entry_binding_before'] == terminal['entry_binding_after'] == pending['entry_binding']
    and terminal['plan_pending'] == pending['plan_pending'] and terminal['original43_reference'] == reference
    and terminal['final_errors'] == [] and terminal['cleanup']['residual_processes'] == [], 'Actual planning closure failed')
observed = core.owner.validate_observer_root(terminal['observer_owner_terminal'],
    Path(probe.checked(pending['plan_terminal'])).parent/'observer_driver', ROOT)
generic.require(observed == terminal['observer'], 'Actual plan owner differs')
final = deepcopy(pending)
final['status'] = probe.FINAL
reverse = deepcopy(final)
reverse['status'] = pending['status']
generic.require(reverse == pending and probe.pin(pending_path)['sha256'] == expected, 'Publication altered original contract')
probe.write_new(final_path, final)
probe.write_new(receipt_path, {
    'scope': 'ROOT_PEER_ACTUAL_PROBE02_PENDING_PLAN_ONLY_NOT_FLIGHT_ACCEPTANCE',
    'created_utc': datetime.now(timezone.utc).isoformat(), 'reviewer': '/root',
    'result': 'PASS_SINGLE_DEVELOPMENT_PLAN_CONTRACT_REVIEW',
    'pending': {'path': str(pending_path), 'sha256': expected},
    'final': probe.pin(final_path), 'plan': pending['plan_pending'],
    'source_review': pending['entry_binding']['source_review'], 'owner': observed,
    'original43_reference': reference, 'only_status_changed': True,
    'flights_started': 0, 'formal_seeds_consumed': False,
    'old_probe01_failure_modified': False, 'code': probe.pin(Path(__file__))})
print({'status': 'PASS_PLAN_CONTRACT_PUBLICATION_ONLY', 'contract': probe.pin(final_path),
    'receipt': str(receipt_path)})
