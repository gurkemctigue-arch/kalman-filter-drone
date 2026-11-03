"""Evaluate the two actually reviewed development inputs, never original acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json

project = Path('/mnt/d/基于yolo和卡尔曼滤波')
module_path = project / 'tools/offline_evaluation/sensor_input_interruption_v1/evidence.py'
assert hashlib.sha256(module_path.read_bytes()).hexdigest() == 'f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba'
contract_path = project / 'results/diagnostics/humble54_input_evidence_contract01/contract.json'
contract_bytes = contract_path.read_bytes()
contract = json.loads(contract_bytes)
assert contract['source_plan']['sha256'] == 'f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055'
spec = importlib.util.spec_from_file_location('observed_input_evidence01', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
started = datetime.now(timezone.utc).isoformat()
results = []
for condition in ('dropout', 'combined'):
    folder = project / ('results/diagnostics/humble54_person_' + condition + '_input_extract02')
    output = folder / 'input_evidence_evaluation01.json'
    assert not output.exists() and not output.is_symlink()
    result = module.evaluate_slot(Path(contract['source_plan']['path']),
        'person_extension_' + condition + '_seed004', folder / 'manifest.json',
        folder / 'visual_review_native01.json', contract)
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    results.append({'slot_id':result['slot_id'], 'status':result['status'],
        'errors':result['errors'], 'known_algorithm_failures':result['known_algorithm_failures'],
        'path':str(output), 'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
receipt = {'kind':'ACTUAL_PERSON_INPUT_EVIDENCE_EVALUATIONS_NOT_ORIGINAL_ACCEPTANCE',
    'started_utc':started, 'finished_utc':datetime.now(timezone.utc).isoformat(),
    'module':{'path':str(module_path), 'sha256':hashlib.sha256(module_path.read_bytes()).hexdigest()},
    'contract':{'path':str(contract_path), 'sha256':hashlib.sha256(contract_bytes).hexdigest()},
    'results':results, 'missing_car_cells':True, 'scope':'Two original development cells only; not complete four-cell evidence, readiness or changed original results.'}
with (contract_path.parent / 'person_evaluation_receipt01.json').open('x', encoding='utf8') as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps(receipt, allow_nan=False))
