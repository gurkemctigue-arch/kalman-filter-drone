"""Register reviewed actual prefix bindings using only literal constant edits."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CHAIN_SHA = 'b5aae1e007b009848555bbe3a9d9dfc4e6974f8afe4452c8b94e0aa31c547705'
COLLECTOR_SHA = 'cd325e39a0d49a2c890813217af8e97d8ee8efb290f645ffa3ff9b1a7d1293cf'
PROFILE_SHA = 'cf176db9ef9fd0ee70cd2e7631dc1d518c0c9289940c83eabd89497d10161678'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def replace(raw, before, after):
    assert raw.count(before.encode()) == 1, before
    return raw.replace(before.encode(), after.encode())

def main():
    chain = ROOT / 'tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_chain.py'
    collector = ROOT / 'tools/experiment_orchestration/humble54_pending_collector06_source/collect_humble54_pending06.py'
    profile = HERE / 'registered_profile06.json'
    for path, pin in ((chain, CHAIN_SHA), (collector, COLLECTOR_SHA), (profile, PROFILE_SHA)):
        assert sha(path.read_bytes()) == pin, str(path)
    audit_path = ROOT / 'results/diagnostics/humble54_probe02_owner06_registration01/windows_chain_audit.json'
    audit = json.loads(audit_path.read_bytes())
    assert audit['status'] == 'BOUND_PRESERVED_PREFIX_CHAIN' and len(audit['closed_ids']) == 3 and len(audit['pending_ids']) == 13
    archive = HERE / 'actual_registration01'
    archive.mkdir()
    gate = HERE / 'run_registered06.py'
    outer = ROOT / 'tools/experiment_orchestration/humble54_probe02_windows_owner06/start_owner06.py'
    gate_raw, outer_raw = gate.read_bytes(), outer.read_bytes()
    assert sha(gate_raw) == '63933270ab2b4a3865ec86b97bfec88ad5824229bc55869f249123072fbfd29b'
    assert sha(outer_raw) == 'bc1f4062415bb3088167ff8df1dc93186494fae4766c2449153e035e09c818ea'
    (archive / 'prepared_gate.py').write_bytes(gate_raw)
    (archive / 'prepared_outer.py').write_bytes(outer_raw)
    gate_new = replace(gate_raw, 'PROFILE_STATUS = "PREPARED_NOT_REGISTERED"', 'PROFILE_STATUS = "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN"')
    gate_new = replace(gate_new, 'REGISTERED_PROFILE_SHA256 = None', f'REGISTERED_PROFILE_SHA256 = "{PROFILE_SHA}"')
    gate_new = replace(gate_new, 'CHAIN_VALIDATOR_SHA256 = None', f'CHAIN_VALIDATOR_SHA256 = "{CHAIN_SHA}"')
    gate_new = replace(gate_new, '"collector": None', f'"collector": "{COLLECTOR_SHA}"')
    gate.write_bytes(gate_new)
    outer_new = replace(outer_raw, 'PROFILE_STATUS = "PREPARED_NOT_REGISTERED"', 'PROFILE_STATUS = "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN"')
    for name, pin in (('collector', COLLECTOR_SHA), ('gate', sha(gate_new)), ('chain_validator', CHAIN_SHA), ('registered_profile', PROFILE_SHA)):
        outer_new = replace(outer_new, f'"{name}": None', f'"{name}": "{pin}"')
    outer.write_bytes(outer_new)
    receipt = {'kind': 'ACTUAL_OWNER06_LITERAL_REGISTRATION_ONLY', 'registered_utc': datetime.now(timezone.utc).isoformat(),
               'gate_sha256': sha(gate_new), 'outer_sha256': sha(outer_new),
               'chain_sha256': CHAIN_SHA, 'collector_sha256': COLLECTOR_SHA, 'profile_sha256': PROFILE_SHA,
               'windows_chain_audit': {'path': str(audit_path), 'sha256': sha(audit_path.read_bytes())},
               'original_owners_unchanged': True, 'execution_started': False}
    with (archive / 'registration.json').open('x', encoding='utf8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
