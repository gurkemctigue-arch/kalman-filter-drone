"""One scheduled development recording audit; never starts a flight."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import time

validation = Path('/mnt/d/WSL/UAVHumble22-validation/humble54_dev_timing01')
root = Path('/root/uav_tracking_fullplan_v4_humble54')
project = Path('/mnt/d/基于yolo和卡尔曼滤波')
plan = root/'results/reliability_v4_humble54_core12_probe01_matrix/plan.json'
trial = root/'results/reliability_v4_humble54_core12_probe01_person_stage1_velocity_seed004'
timing = project/'tools/offline_evaluation/timing_v2/offline_pipeline_timing.py'
lineage = project/'tools/offline_evaluation/control_tick_lineage_v1/control_tick_lineage.py'

def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path':str(path), 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}

def now():
    return datetime.now(timezone.utc).isoformat()

def main():
    assert not validation.exists(), 'Never overwrite an earlier audit'
    assert json.loads(plan.read_bytes())['plan_sha256'] == '3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31'
    assert (trial/'recording_closure.json').is_file()
    inputs = (Path(__file__), plan, timing, timing.with_name('test_offline_pipeline_timing.py'),
              lineage, lineage.with_name('test_control_tick_lineage.py'))
    before = [pin(path) for path in inputs]
    validation.mkdir()
    receipt = {'kind':'ACTUAL_DEV_TIMING_SCHEMA_AND_LINEAGE_AUDIT_NOT_FORMAL_ACCEPTANCE',
               'started_utc':now(), 'input_pins_before':before, 'executions':[],
               'formal_seed_use_authorized':False, 'status':'RUNNING'}
    prefix = ['bash', str(root/'scripts/run_research_session.sh')]
    def execute(name, argv):
        start, mono = now(), time.monotonic()
        with (validation/(name+'.log')).open('xb') as stream:
            process = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=False)
        receipt['executions'].append({'name':name, 'argv':argv, 'started_utc':start,
            'finished_utc':now(), 'wall_duration_s':time.monotonic()-mono,
            'returncode':process.returncode, 'log':pin(validation/(name+'.log'))})
        if process.returncode:
            raise RuntimeError(name+' failed with exit '+str(process.returncode))
    try:
        execute('export', prefix+[str(timing), 'export', '--source-root', str(root),
            '--trial', str(trial), '--output', str(validation/'export'),
            '--protected-root', str(plan.parent), '--job-log', str(trial/'ros.log')])
        context = pin(validation/'export/context.json')
        common = ['analyze', '--events', str(validation/'export/events.jsonl'),
                  '--context',context['path'], '--context-sha256',context['sha256']]
        execute('timing_analysis', prefix+[str(timing)]+common+['--output',str(validation/'timing_report.json')])
        execute('lineage_analysis', prefix+[str(lineage)]+common+['--output',str(validation/'lineage_report.json')])
        receipt['output_pins'] = [pin(validation/name) for name in ('export/context.json','timing_report.json','lineage_report.json')]
        receipt['status'] = 'COMPLETED_DEV_OBSERVATIONS_ONLY'
    except BaseException as error:
        receipt.update(status='FAILED_RETAIN_OUTPUT_NO_RETRY', error=type(error).__name__+': '+str(error))
        raise
    finally:
        receipt['input_pins_after'] = [pin(path) for path in inputs]
        receipt['input_pins_unchanged'] = before == receipt['input_pins_after']
        receipt['finished_utc'] = now()
        with (validation/'execution_receipt.json').open('x',encoding='utf-8') as stream:
            json.dump(receipt,stream,ensure_ascii=True,indent=2)
        print(json.dumps({'status':receipt['status'],'receipt':str(validation/'execution_receipt.json')}),flush=True)

if __name__ == '__main__':
    main()
