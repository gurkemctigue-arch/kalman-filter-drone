"""Record the root's actual eight-image review and invoke the fixed evaluator."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[3]
FOLDER = REPO / 'results/diagnostics/humble54_probe02_person_dropout_input_extract03'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def native(path):
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]

def main():
    manifest_path = FOLDER / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest['exported_raw_rgb_count'] == 8
    assert manifest['contact_sheet']['sha256'] == sha(FOLDER / 'contact_sheet.png')
    images = []
    for row in manifest['opportunities']:
        if 'original_png' not in row:
            continue
        assert sha(FOLDER / row['original_png']) == row['png_sha256']
        images.append({'file': row['original_png'], 'sha256': row['png_sha256'], 'acquisition_ns': row['acquisition_ns'],
                       'observation': 'SCENE_OBSCURED_NEAR_BLACK_TARGET_NOT_VISIBLE' if row['acquisition_ns'] in (29800000000, 29900000000) else 'ONE_PERSON_AND_SCENE_VISIBLE_IN_CONTACT_SHEET'})
    review = {'kind': 'INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE',
              'review_type': 'DIRECT_IMAGE_REVIEW_AI', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'reviewers': ['Codex root directly viewed all eight thumbnails with view_image after actual probe02 extraction.'],
              'manifest': {'path': native(manifest_path), 'sha256': sha(manifest_path)},
              'contact_sheet': manifest['contact_sheet'], 'images': images,
              'scope': 'Descriptive image review only; original terminal/check/null remain unchanged.'}
    review_path = FOLDER / 'visual_review_native03.json'
    with review_path.open('x', encoding='utf8') as handle:
        json.dump(review, handle, indent=2)
        handle.write('\n')
    script = '''from pathlib import Path
import hashlib,json,sys,types
repo=Path(sys.argv[1])
folder=repo/'results/diagnostics/humble54_probe02_person_dropout_input_extract03'
source=repo/'tools/offline_evaluation/sensor_input_interruption_v1/evidence.py'
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba'
module=types.ModuleType('fixed_input_evidence');module.__file__=str(source)
exec(compile(raw,str(source),'exec'),module.__dict__)
contract_path=repo/'tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.json'
contract=json.loads(contract_path.read_bytes())
result=module.evaluate_slot(Path(contract['source_plan']['path']), 'person_extension_dropout_seed004', folder/'manifest.json',folder/'visual_review_native03.json',contract)
with (folder/'input_evidence_evaluation03.json').open('x',encoding='utf8') as handle:
 json.dump(result,handle,indent=2);handle.write('\\n')
print(json.dumps(result))
raise SystemExit(0 if result['status']=='UPSTREAM_INPUT_INTERRUPTION_CORROBORATED' and not result['errors'] else 2)
'''
    result = subprocess.run(['wsl.exe', '--distribution', 'UAVHumble22', '--exec', 'python3', '-B', '-c', script, native(REPO)], capture_output=True)
    out = REPO / 'results/diagnostics/humble54_probe02_dropout_review03'
    (out/'evaluation_stdout.log').write_bytes(result.stdout)
    (out/'evaluation_stderr.log').write_bytes(result.stderr)
    print(result.stdout.decode('utf8', errors='replace'))
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
