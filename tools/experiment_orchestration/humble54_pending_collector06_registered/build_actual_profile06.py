"""Bind the real closed owner05 segment to the unchanged owner04 profile."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def binding(path, reference=None):
    return {'path': reference or str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    original = ROOT / 'tools/experiment_orchestration/humble54_pending_collector05_registered/registered_profile05.json'
    assert binding(original)['sha256'] == '5ac96b104ac1e7ad24500657f38b329c968f9440e61f23e79d7bc27fc1df0bd0'
    profile = deepcopy(json.loads(original.read_bytes()))
    folder = ROOT / 'results/diagnostics/humble54_probe02_windows_owner05'
    started = json.loads((folder / 'started.json').read_bytes())
    outer = json.loads((folder / 'terminal.json').read_bytes())
    assert outer['closure_verified'] is True and outer['status'] == 'STOPPED_FAULT' and outer['errors'] == []
    fields = set(profile['segments'][0]['description']) | {'registered_admission_unc'}
    native = started['native_owner']
    unc = Path(started['owner_unc'])
    monitor = Path(started['monitor_output'])
    segment = {'segment_id': 'owner05', 'disposition': 'ROOT_REVIEWED_METADATA_STOP',
               'after_slot': 'person_extension_depth_holes_seed004',
               'source_files': {**started['pins'], 'launcher': started['launcher_source']},
               'description': {name: started[name] for name in fields},
               'launch_files': {'started': binding(folder / 'started.json'),
                                'first_monitor': binding(folder / 'first_monitor_state.json'),
                                'first_native': binding(folder / 'first_native_state.json'),
                                'registered_admission': binding(Path(started['registered_admission_unc']), native + '.admission.json')},
               'closure_files': {'outer_terminal': binding(folder / 'terminal.json'),
                                 'native_terminal': binding(unc / 'terminal.json', native + '/terminal.json'),
                                 'monitor_final': binding(monitor / 'monitor_state.json'),
                                 'monitor_end': binding(monitor / 'end_summary.json'),
                                 'events': binding(unc / 'events.jsonl', native + '/events.jsonl'),
                                 'registered_entry_terminal': binding(unc / 'registered_entry_terminal.json', native + '/registered_entry_terminal.json')},
               'stop_evidence': {'root_review': binding(ROOT / 'results/diagnostics/humble54_probe02_dropout_review03/root_review.json')}}
    profile['segments'].append(segment)
    target = Path(__file__).with_name('registered_profile06.json')
    with target.open('x', encoding='utf8') as handle:
        json.dump(profile, handle, indent=2)
        handle.write('\n')
    print(json.dumps(binding(target)))

if __name__ == '__main__':
    main()
