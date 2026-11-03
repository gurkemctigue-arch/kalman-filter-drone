
from pathlib import Path
import importlib.util,json,sys,hashlib
root=Path('/mnt/d')/Path.cwd().name if False else Path('/root/uav_tracking_fullplan_v4_humble54')
plan=root/'results/reliability_v4_humble54_extension16_probe02_matrix/plan.json'
parsed=json.loads(plan.read_bytes()); repo=Path(parsed['results_root']).parents[1]
collector_path=repo/'tools/experiment_orchestration/humble54_pending_collector05_source/collect_humble54_pending05.py'
assert hashlib.sha256(collector_path.read_bytes()).hexdigest()=='f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1'
sys.path.insert(0,str(root))
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
collector=module('actual_closed_prefix_collector05',collector_path)
original=module('actual_frozen_original_runner',root/'scripts/run_reliability_v4.py')
pins={'plan':'1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54','entry':'d9cc1f1876a5ed9a358697b29644e7aa7a3c192e0bdd2a2a7d37c208e74f06a6','capture_profiles':collector.CAPTURE_PROFILES,'history':{},'minimum_prefix':2}
_,closed,pending=collector.initial_check(plan,Path('/mnt/d/WSL/UAVHumble22-validation/run_humble54_pending_probe02_one03.sh'),'person_extension_depth_holes_seed004',pins,original)
assert len(closed)==2 and len(pending)==14
print(json.dumps({'status':'ACTUAL_CLOSED_PREFIX_CHECK_ONLY_NOT_LAUNCH','closed':closed,'pending_ids':[r['id'] for r in pending],'history':{},'collector_sha256':hashlib.sha256(collector_path.read_bytes()).hexdigest()}))
