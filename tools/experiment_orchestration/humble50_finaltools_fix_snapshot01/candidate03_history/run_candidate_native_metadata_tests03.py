"""One bounded unittest selection; synthetic metadata only, no subprocesses."""
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve(strict=True).parent
EXTERNAL=HERE.parent/'dds48_tools01'
sys.dont_write_bytecode=True
sys.path.insert(0,str(EXTERNAL))
TMP=HERE/'native_metadata_temp03'
TMP.mkdir(exist_ok=False)
os.environ['TMPDIR']=str(TMP)
os.environ['TMP']=str(TMP)
os.environ['TEMP']=str(TMP)
tempfile.tempdir=str(TMP)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

def forbidden(*args,**kwargs):
    raise AssertionError('Actual native process/probe/build/simulation forbidden in selected metadata tests')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')

require=(os.name=='posix' and sys.platform.startswith('linux')
    and os.environ.get('WSL_DISTRO_NAME')=='UAVHumble22'
    and str(Path(sys.executable))=='/root/uav_humble22/venv/bin/python')
if not require:raise RuntimeError('Only the explicitly authorized Humble venv execution is allowed')
builder_path=HERE/'build_development_final_root_v2.candidate01.py'
tests_path=HERE/'test_development_final_root_v2.candidate01.py'
if sha(builder_path)!='7405debd20fd1867858dba1b9a1baf507640fee3b4b2e77eb3df2e265ad60708':raise RuntimeError('Builder changed')
if sha(tests_path)!='bdf88c4cc55311faa2e46a403538e7df3d4245b2fd447b7dc14d498e1c77a7d9':raise RuntimeError('Tests changed')
buffer=io.StringIO()
with ExitStack() as stack:
    for target in ('subprocess.Popen','subprocess.run','subprocess.check_output','os.system'):
        stack.enter_context(patch(target,side_effect=forbidden))
    builder=load('build_development_final_root_v2',builder_path)
    for obj,name in ((builder.preparation,'authority'),(builder.preparation,'verify_prepared'),
            (builder.development_build,'runtime_contracts'),(builder.development_build.resource,'dds_contracts'),
            (builder.primitives,'audit_origins'),(builder.primitives,'audit_fastcdr'),
            (builder.primitives,'cdr_roundtrip'),(builder.primitives,'run_suite'),
            (builder.primitives,'require_environment')):
        stack.enter_context(patch.object(obj,name,side_effect=forbidden))
    tests=load('test_final_v2_candidate_native_metadata03',tests_path)
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(getattr(tests,name))
        for name in ('CompletedBuildFixture','BuildOwnershipTests'))
    if suite.countTestCases()!=17:raise RuntimeError('Exact 17 selected cases required')
    result=unittest.TextTestRunner(stream=buffer,verbosity=2).run(suite)
log=buffer.getvalue()
log_path=HERE/'candidate_native_metadata_tests_attempt03.log'
with log_path.open('x',encoding='utf8',newline='\n') as stream:stream.write(log)
receipt={'schema_version':1,'status':'PASS_HUMBLE_CANDIDATE_SYNTHETIC_METADATA_TESTS_ONLY'
    if result.wasSuccessful() else 'FAIL_HUMBLE_CANDIDATE_SYNTHETIC_METADATA_TESTS_ONLY',
    'created_utc':datetime.now(timezone.utc).isoformat(),'tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
    'builder':{'path':str(builder_path),'sha256':sha(builder_path)},
    'tests_source':{'path':str(tests_path),'sha256':sha(tests_path)},
    'log':{'path':str(log_path),'sha256':sha(log_path)},
    'runner':{'path':str(Path(__file__)),'sha256':sha(Path(__file__))},
    'temporary_root':str(TMP),'temporary_entries_after_cleanup':len(list(TMP.iterdir())),
    'platform':'UAVHumble22 venv Python; original Linux LD semantics with no OS adapter',
    'all_subprocesses_and_actual_dds_acquisition_original_audits_suite_forbidden':True,
    'native_cv2_or_ros_import_executed':False,'actual_native_preflight_executed':False,
    'actual_compilation_or_simulation_executed':False,'production_or_main_files_modified':False,
    'future_final_root_or_formal_evidence_bound':False}
write_new(HERE/'candidate_native_metadata_tests_attempt03.json',receipt)
print(log)
print(json.dumps(receipt,sort_keys=True))
sys.exit(0 if result.wasSuccessful() else 1)
