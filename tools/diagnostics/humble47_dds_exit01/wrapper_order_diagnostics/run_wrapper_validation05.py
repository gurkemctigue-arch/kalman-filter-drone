from pathlib import Path
import subprocess,json,hashlib,sys
source = Path('/mnt/d/基于yolo和卡尔曼滤波')
out=Path('/mnt/d/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/wrapper_validation05')
out.mkdir(exist_ok=False)
names=['scripts/ros_python.sh','scripts/run_stage1_flight.sh','scripts/run_stage1_trial.sh','scripts/research_env.sh','scripts/verify_stage1.sh','scripts/evaluate_stage1_flight.sh','scripts/humble22_env.sh','scripts/apply_humble22_dds_runtime.sh']
commands=[['/usr/bin/python3','-B','-m','unittest','discover','-s',str(source/'tests'),'-p','test_dds_environment_wrappers.py','-v']]+[['bash','-n',str(source/name)] for name in names]
cases=[]
for i,argv in enumerate(commands):
    proc=subprocess.run(argv,cwd=source,capture_output=True,timeout=50)
    for stream in ('stdout','stderr'):
        (out/(str(i)+'.'+stream+'.log')).write_bytes(getattr(proc,stream))
    cases.append({'argv':argv,'returncode':proc.returncode})
report={'scope':'NATIVE_BASH_FIXTURE_TESTS_AND_SHELL_SYNTAX_NOT_FLIGHT','status':'PASS' if all(c['returncode']==0 for c in cases) else 'FAIL','cases':cases,'inputs':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names+['tests/test_dds_environment_wrappers.py']}}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(0 if report['status']=='PASS' else 2)
