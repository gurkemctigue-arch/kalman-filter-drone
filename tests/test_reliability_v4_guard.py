"""Outer admission regressions using temporary JSON/files; no ROS or flights.

The inert runtime doubles below cannot certify research evidence. Production
uses the already frozen official validators, separately tested by their suite.
"""
from copy import deepcopy
from contextlib import nullcontext
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
from types import SimpleNamespace
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("guard_fixture", ROOT/"tools/reliability_v4_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
T = "2026-10-20T00:00:00+00:00"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return guard.file_binding(path)


def seal_plan(plan):
    plan["plan_sha256"] = guard.sealed(plan, "plan_sha256")
    return plan


def plans(root):
    root = root.resolve()
    results = root/"results"; results.mkdir(exist_ok=True)
    common = {"frozen_root":str(root), "results_root":str(results), "created_utc":T,
              "source_hashes":{"fixture.py":"1"*64}, "model_hashes":{"fixture.pt":"2"*64}}
    values = {}
    for label, groups in (("core",guard.GROUPS),("extension",guard.CONDITIONS)):
        plan = {**deepcopy(common), "mode":"FORMAL" if label == "core" else "EXTENSION_FORMAL",
                "output":str(results/label), "trials":[]}
        for cls in guard.CLASSES:
            for group in groups:
                for seed in range(1000,1010):
                    plan["trials"].append({"id":f"{cls}_{group}_seed{seed}","target_class":cls,"group":group,
                        "extension_condition":group,"seed":seed,"directory":str(results/f'{label}_{cls}_{group}_{seed}')})
        if label == "extension":
            plan["core_reference_binding"] = {**values["core"][0], "plan_sha256":values["core"][1]["plan_sha256"]}
        seal_plan(plan)
        values[label] = (write(results/label/"plan.json",plan),plan)
    manifest = {"final_root":str(root),"plans":{label:pair[0] for label,pair in values.items()}}
    context = guard.read_plans(manifest)
    return manifest,context


def pending(context):
    return {label:{trial["id"]:{"id":trial["id"],"status":"PENDING"} for trial in getattr(context,label)["trials"]}
            for label in ("core","extension")}


class FakeStorage:
    def __init__(self, vhd_path, *, free=10**15, identities=None):
        self.vhd = vhd_path
        self.free = free
        self.identities = identities or {}
        self.reads = []

    def volume(self, specification):
        self.reads.append(specification["mount"])
        return {"mount":specification["mount"],"windows_volume_id":self.identities.get(specification["id"],specification["windows_volume_id"]),
                "free_bytes":self.free if isinstance(self.free,int) else self.free[specification["id"]]}

    def vhd_path(self, distribution):
        return self.vhd.resolve()

    def logical_free(self, root):
        return 10**16


def storage_fixture(root, *, split=False):
    root = root.resolve()
    manifest,context = plans(root)
    mounts = {name:root/name for name in (("D","E") if split else ("D",))}
    for mount in mounts.values(): mount.mkdir()
    # Windows temp directories cannot be assumed to have symlink privileges;
    # the independent symlink regression below exercises that path explicitly.
    results = root/"results"
    manifests = []
    for label in ("core","extension"):
        plan = getattr(context,label)
        plan["results_root"] = str(mounts["D"])
        manifests.append(plan)
    # Storage validates root/results resolution. Use an injectable path resolver
    # only in these arithmetic fixtures; the symlink regression uses real links.
    context.storage_results = mounts["D"]
    vhd = mounts["E" if split else "D"]/"ext4.vhdx"; vhd.write_bytes(b"fixture, not a virtual disk")
    volumes = set(mounts)
    values = lambda d=0,e=0:{name:(d if name == "D" else e) for name in volumes}
    cells,gate_slots = [],{"core":[],"extension":[]}
    dev_plans = {}
    for label,groups in (("core",guard.GROUPS),("extension",guard.CONDITIONS)):
        dev = {"trials":[]}
        for cls in guard.CLASSES:
            for group in groups:
                name=f'{label}_{cls}_{group}'
                trial=root/"development"/name; (trial/"rosbag").mkdir(parents=True)
                compressed=trial/"rosbag/data.db3.zstd"; compressed.write_bytes(b"12345")
                archive={"status":"PASS","policy":"ext4_sqlite_close_standard_zstd_verified_native_read",
                    "raw_validation":{"status":"PASS","files":[{"path":"data.db3","bytes":10}]},
                    "native_reader_validation":{"full_stream_read":True},
                    "compressed_files":[{"path":"data.db3.zstd","bytes":5,"raw_bytes":10}]}
                archive_binding=write(trial/"bag_integrity.json",archive)
                files={"rosbag/data.db3.zstd":5,"bag_integrity.json":(trial/"bag_integrity.json").stat().st_size}
                size={"scope":"FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE","trial":str(trial),"files":files,"total_trial_bytes":sum(files.values())}
                size_binding=write(root/"sizes"/(name+".json"),size)
                dev["trials"].append({"id":name,"target_class":cls,"group":group,"extension_condition":group,"directory":str(trial)})
                cells.append({"matrix":label,"target_class":cls,"condition":group,"persistent_bytes_by_volume":values(1000,10),
                    "development_size_evidence":size_binding,"archive_evidence":archive_binding,"basis":"Pure temporary fixture accounting, not real capacity"})
        path=root/(label+"_development.json"); write(path,dev); dev_plans[str(path)] = dev
        gate_slots[label]=[{"plan_path":str(path),"slot_id":trial["id"]} for trial in dev["trials"]]
    context.core["development_probe_gate"]={"evidence":{"probe_slots":gate_slots["core"]}}
    context.core["extension_protocol_binding"]={"protocol":{"development_readiness":{"evidence":{"probe_slots":gate_slots["extension"]}}}}
    storage={"volumes":[{"id":name,"mount":str(mount),"windows_volume_id":"fixture-volume-"+name} for name,mount in mounts.items()],
        "results_volume":"D","vhd_host":{"distribution":"FIXTURE","path":str(vhd),"volume":"E" if split else "D"},
        "temporary_peak_bytes":values(100,100),"temporary_bound_rule":{"revision":"three_raw_two_compressed_plus_margin_v1",
            "raw_growth_factor":1.,"compressed_growth_factor":1.,"extra_bytes_by_volume":values(),"basis":"Declared bound, never a measurement"},
        "delivery_reservations":{purpose:{"bytes_by_volume":values(100),"basis":"Explicit fixture remaining task"} for purpose in guard.DELIVERIES},
        "additional_remaining_bytes":values(),"cells":cells}
    manifest["storage"]=storage
    runtime=SimpleNamespace(v4=SimpleNamespace(load=guard.load))
    return manifest,context,runtime,FakeStorage(vhd),pending(context)


def safety_fixture(root, *, linked=False):
    root=root.resolve();dev=root/'dev';dev.mkdir()
    physical=root/'data'/'development_results';physical.mkdir(parents=True)
    if linked:
        try:
            (dev/'results').symlink_to(physical,target_is_directory=True)
        except OSError:
            if os.name != 'nt':raise
            quote=lambda text:"'"+str(text).replace("'","''")+"'"
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                'New-Item -ItemType Junction -Path '+quote(dev/'results')+' -Target '+quote(physical)+' | Out-Null'],capture_output=True,check=False)
            if result.returncode:raise OSError('Cannot create local fixture junction')
    else:
        (dev/'results').mkdir()
    for name in ('scripts/run_stage1_trial.py','uav_tracking/research_failures.py'):
        path=dev/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# inert fixture\n')
    protocol=guard.load(ROOT/'planning/reliability-v4-preregistration.json')
    # Historical safety fixtures stay legacy/off as the real candidate evolves.
    protocol.pop('simulation_pacing_registration', None)
    protocol.update(real_time_factor=.25, flight_wall_timeout_s=600.)
    resources=protocol['resources']
    for resource in resources.values():
        resource.pop(guard.CORRELATED_BOUND_FIELD, None)
        resource.pop('car_surface_recovery', None)
    source_hashes={name:guard.sha(dev/name) for name in ('scripts/run_stage1_trial.py','uav_tracking/research_failures.py')}
    for cls in guard.CLASSES:
        model=dev/resources[cls]['model'];model.parent.mkdir(exist_ok=True);model.write_bytes(b'fixture model')
        source_hashes[resources[cls]['model']]=guard.sha(model)
    development={'frozen_root':str(dev),'results_root':str((dev/'results').resolve()),'source_hashes':source_hashes,'trials':[]}
    development['plan_sha256']=guard.sealed(development,'plan_sha256')
    dev_binding=write(dev/'results/core_plan.json',development)
    card=dev/'planning/reliability-v4-ambiguity-execution.md';card.parent.mkdir()
    card.write_text((ROOT/'planning/reliability-v4-ambiguity-execution.md').read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
    code=card.read_text(encoding='utf-8').split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]+'\n'
    tail=root/'audit_tail.py';tail.write_text(code,encoding='utf-8',newline='\n')
    driver=root/'driver.py';driver.write_text('# inert fixture ledger, never executes\n')
    bindings={'flight_source_hashes':source_hashes,'evaluation_source_hashes':{},'model_hashes':{},
              'magnetic_runtime_manifest_sha256':'a'*64,'magnetic_library_registration_sha256':'b'*64,'navigation_acceptance_sha256':'c'*64}
    slots=[];registered=[]
    prefix=['bash',str(dev/'scripts/run_research_session.sh')]
    for cls in guard.CLASSES:
        for case in guard.SAFETY_CASES:
            identifier=f'{cls}_{case}_seed004';trial=dev/'results'/identifier;trial.mkdir()
            auto=case=='auto_unique_multi';resource=resources[cls]
            config={'target_class':cls,'stage':2,'seed':4,'command_mode':'velocity','gimbal_mode':'midpoint',
                'target_mode':'auto_unique' if auto else 'locked_target','association_mode':'legacy' if auto else 'hybrid_3d',
                'initial_select':'none' if auto else 'middle','initial_min_candidates':2 if auto else 3,
                'scenario_kind':'parallel' if auto else 'ambiguity','duration':35. if auto else 50.,
                'condition':'clean','motion_profile_kind':'standard','takeoff_mode':'px4_native','takeoff_height_m':3.,
                'control_reference':'ground_footprint','real_time_factor':protocol['real_time_factor'],'max_inference_rate_hz':10.,'monitor_tick_s':.02,
                'wall_timeout':protocol['flight_wall_timeout_s'],
                'gazebo_render_driver':'llvmpipe','px4_time_mode':'source_sim','magnetic_environment':'gazebo_enu',
                'propagate_vehicle_uncertainty':True,'occlusions':False,'reselect_after_loss':False,
                'no_follow_duration_s':35. if auto else None,'supervisor_status_timestamp_mode':'source_sim',
                'supervisor_status_source_max_age_s':1.,'supervisor_status_source_max_future_s':.05,'supervisor_status_timeout_wall_s':10.,
                'vehicle_control_point_offset_flu_m':[0.,0.,.24],'model_path':str(dev/resource['model']),
                'inference_image_size':resource['inference_image_size'],'inference_threads':resource['inference_threads'],
                'desired_distance_m':resource['desired_distance_m']}
            params={'uav_tracking_detection':{'navigation_enabled':True,'depth_max_age_s':.02},
                'uav_tracking_state_estimator':{'target_mode':config['target_mode'],'association_mode':config['association_mode'],
                    'max_observation_age_s':.6,'max_prediction_duration_s':.75,'mahalanobis_gate':9.21,'navigation_enabled':True,'propagate_vehicle_uncertainty':True},
                'uav_tracking_controller':{'state_topic':'/tracking/navigation_state','desired_height_m':2.,'prediction_timeout_s':.75},
                'uav_tracking_px4_adapter':{'use_sim_time':True,'odometry_timestamp_mode':'source_sim','odometry_source_max_age_s':.5,
                    'odometry_source_max_future_s':.05,'vehicle_odometry_topic':'/fmu/out/vehicle_odometry','vehicle_odom_topic':'/vehicle/odometry'},
                'uav_tracking_flight_supervisor':{'takeoff_mode':'px4_native','status_timestamp_mode':'source_sim','status_source_max_age_s':1.,'status_source_max_future_s':.05,'status_timeout_s':10.,'requested_simulation_real_time_factor':protocol['real_time_factor']}}
            values={'run_config':('run_config.json',config),
                'source_snapshot':('configuration/source_sha256.json',{key:value for key,value in source_hashes.items() if key.endswith(('.py','.sh','.msg')) or key==resource['model']}),
                'bag_integrity':('bag_integrity.json',{'status':'PASS'}),
                'recording_closure':('recording_closure.json',{'observations':[{'last_clock_ns':20000000000}]}),
                'process_exit_codes':('process_exit_codes.json',{'gazebo':0,'agent':-2,'px4':0,'bag':0,'monitor':0,'ros':0}),
                'source_clock':('px4_source_clock_report.json',{'result':'PASS'}),
                'native_startup':('native_startup_report.json',{'result':'PASS'}),
                'rendering':('configuration/gazebo_rendering_libraries.json',{'status':'PASS'}),
                'magnetic':('configuration/magnetic_environment.json',{'status':'PASS'})}
            specialty={'schema_version':2 if auto else 1,'result':'PASS','target_class':cls,
                'source':'OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY' if auto else 'OFFLINE_STAGE2_SAFETY_EVALUATION',
                'inputs':{'bag':str(trial/'rosbag')},'checks':{name:True for name in (guard.AUTO_CHECKS if auto else guard.LOCKED_CHECKS)},
                'geometric_ambiguity_observed':True,'configuration':{'target_class':cls,'require_ambiguity':True,'terminal_expectation':'hover'}}
            values['specialized']=('auto_unique_evaluation_v2.json' if auto else 'stage2_evaluation.json',specialty)
            values['terminal_speed']=('terminal_hover_speed_evaluation.json',{'schema_version':1,'result':'PASS','trial':str(trial),
                'checks':{name:True for name in guard.SPEED_CHECKS},'interval':{'start_s':14.8,'end_s':20.}})
            evidence={name:write(trial/relative,value) for name,(relative,value) in values.items()}
            parameter_path=trial/'configuration/runtime_parameters.yaml'
            parameter_path.write_text(yaml.safe_dump({name:{'ros__parameters':value} for name,value in params.items()}),encoding='utf-8')
            evidence['runtime_parameters']=guard.file_binding(parameter_path)
            flight=prefix+[str(dev/'scripts/run_stage1_trial.py'),'--name',identifier,'--class',cls,'--seed','4',
                '--target-mode',config['target_mode'],'--scenario-kind',config['scenario_kind'],
                '--real-time-factor',str(protocol['real_time_factor']),
                '--wall-timeout',str(protocol['flight_wall_timeout_s'])]
            commands={'flight':flight,
                'source_clock':prefix+['scripts/evaluate_px4_source_clock.py',str(trial),'--output',evidence['source_clock']['path']],
                'native_startup':prefix+['scripts/evaluate_native_startup.py',str(trial),'--output',evidence['native_startup']['path']],
                'terminal_speed':prefix+[str(tail),str(trial),str(card)]}
            commands['specialized']=prefix+(['scripts/run_stage23_matrix.py','--evaluate-auto-unique',str(trial/'rosbag')]
                if auto else ['scripts/evaluate_stage2_flight.py',str(trial/'rosbag'),'--telemetry-jsonl',str(trial/'telemetry.jsonl'),
                    '--monitor-summary',str(trial/'summary.json'),'--no-require-occlusions','--require-ambiguity','--terminal-expectation','hover'])
            commands['specialized']+=['--target-class',cls,'--output',evidence['specialized']['path']]
            executions={}
            for kind,argv in commands.items():
                log=root/'logs'/f'{identifier}_{kind}.log';log.parent.mkdir(exist_ok=True);log.write_text('Inert fixture, no command executed\n')
                executions[kind]={'argv':argv,'started_utc':'2026-10-20T00:00:01+00:00' if kind=='flight' else '2026-10-20T00:00:03+00:00',
                    'finished_utc':'2026-10-20T00:00:02+00:00' if kind=='flight' else '2026-10-20T00:00:04+00:00',
                    'returncode':0,'error':None,'log':guard.file_binding(log)}
            executions['terminal_speed']['code_script']=guard.file_binding(tail)
            slots.append({'id':identifier,'target_class':cls,'case':case,'seed':4,'result':'PASS','trial_directory':str(trial),
                          'executions':executions,'evidence':evidence})
            registered.append({'id':identifier,'target_class':cls,'case':case,'seed':4,'directory':str(trial),'flight_argv':flight})
    registry={'schema_version':1,'kind':'RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY','created_utc':T,
        'source_core_plan':{**dev_binding,'plan_sha256':development['plan_sha256']},'flight_source_hashes':source_hashes,
        'execution_card':guard.file_binding(card),'tail_script':guard.file_binding(tail),'driver':guard.file_binding(driver),'trials':registered}
    registry_binding=write(root/'registry.json',registry)
    facts={'schema_version':1,'kind':'RELIABILITY_V4_SAFETY_EXECUTION_FACTS','evidence_scope':'REAL_RECORDED_DEVELOPMENT_EVIDENCE',
        'result':'PASS','planned_count':4,'attempted_count':4,'pending_count':0,'created_utc':'2026-10-20T00:00:05+00:00',
        'registry':registry_binding,'slots':slots}
    facts_binding=write(root/'facts.json',facts)
    summary={'schema_version':1,'kind':'RELIABILITY_V4_FINAL_SAFETY_SUMMARY','result':'PASS','evidence_scope':'REAL_RECORDED_DEVELOPMENT_EVIDENCE',
        'created_utc':'2026-10-20T00:00:06+00:00','bindings':bindings,'source_facts':facts_binding,'slots':slots}
    manifest={'safety':write(root/'safety.json',summary)}
    context=SimpleNamespace(core={'protocol':{'resources':resources,'real_time_factor':protocol['real_time_factor'],
        'flight_wall_timeout_s':protocol['flight_wall_timeout_s']}},development=development,development_path=Path(dev_binding['path']),
        gate_bindings=bindings,registration_times=[guard.utc('2026-10-20T00:00:07+00:00')]*3)
    calls=[]
    def infrastructure(directory,attempts):
        # Reproduces the real helper's lexical root-location dependency.
        calls.append(directory)
        if not (Path(directory).parent.parent/'uav_tracking/research_failures.py').is_file():raise FileNotFoundError('Lost frozen source root')
        return {'stop':False}
    runtime=SimpleNamespace(v4=SimpleNamespace(read_evaluation=lambda *a,**k:{'result':'PASS'},
        gazebo_rendering_evidence=lambda *a,**k:{'errors':[]},magnetic_environment_evidence=lambda *a,**k:{'errors':[]},
        infrastructure_evidence=infrastructure))
    return manifest,context,runtime,summary,facts,calls


def bind_geometry_safety_fixture(context, facts, *, car=True):
    """Bind inert, newly declared per-class geometry fixtures, never flights."""
    registry = guard.load(facts['registry']['path'])
    for cls, resource in context.core['protocol']['resources'].items():
        resource[guard.CORRELATED_BOUND_FIELD] = car if cls == 'car' else False
    for slot in facts['slots']:
        enabled = context.core['protocol']['resources'][slot['target_class']][guard.CORRELATED_BOUND_FIELD]
        binding = slot['evidence']['run_config']; config = guard.load(binding['path'])
        config['correlated_two_face_bound'] = enabled
        slot['evidence']['run_config'] = write(Path(binding['path']), config)
        binding = slot['evidence']['runtime_parameters']; path = Path(binding['path'])
        parameters = yaml.safe_load(path.read_text(encoding='utf-8'))
        parameters['uav_tracking_state_estimator']['ros__parameters'][guard.CORRELATED_BOUND_FIELD] = enabled
        path.write_text(yaml.safe_dump(parameters), encoding='utf-8')
        slot['evidence']['runtime_parameters'] = guard.file_binding(path)
        argv = slot['executions']['flight']['argv']
        if enabled:argv.append(guard.CORRELATED_BOUND_FLAG)
        next(row for row in registry['trials'] if row['id'] == slot['id'])['flight_argv'] = list(argv)
    facts['registry'] = write(Path(facts['registry']['path']), registry)


class GeometryBoundEvidenceTests(unittest.TestCase):
    def test_old_archives_allow_missing_or_false_and_refuse_hidden_enablement(self):
        for absent in (True, False):
            config = {} if absent else {'correlated_two_face_bound': False}
            estimator = {} if absent else {guard.CORRELATED_BOUND_FIELD: False}
            self.assertFalse(guard.geometry_bound_evidence({}, 'car', config,
                {'uav_tracking_state_estimator': {'ros__parameters': estimator}}, []))
        for location in ('arguments', 'yaml'):
            for bad in (True, 0, 1, 'false', None):
                config, estimator = {}, {}
                if location == 'arguments':config['correlated_two_face_bound'] = bad
                else:estimator[guard.CORRELATED_BOUND_FIELD] = bad
                with self.subTest(location=location, bad=bad), self.assertRaises(guard.Refusal):
                    guard.geometry_bound_evidence({}, 'car', config,
                        {'uav_tracking_state_estimator': {'ros__parameters': estimator}}, [])
        with self.assertRaises(guard.Refusal):
            guard.geometry_bound_evidence({}, 'car', {}, {}, [guard.CORRELATED_BOUND_FLAG])

    def test_new_class_bool_requires_matching_cli_and_both_archives(self):
        for enabled in (False, True):
            resource = {guard.CORRELATED_BOUND_FIELD: enabled}
            config = {'correlated_two_face_bound': enabled}
            parameters = {'uav_tracking_state_estimator': {'ros__parameters': {guard.CORRELATED_BOUND_FIELD: enabled}}}
            argv = [guard.CORRELATED_BOUND_FLAG] if enabled else []
            self.assertIs(guard.geometry_bound_evidence(resource, 'car', config, parameters, argv), enabled)
            for location in ('arguments', 'yaml', 'cli'):
                a, p, command = deepcopy(config), deepcopy(parameters), list(argv)
                if location == 'arguments':a.clear()
                elif location == 'yaml':p['uav_tracking_state_estimator']['ros__parameters'].clear()
                else:command = [] if enabled else [guard.CORRELATED_BOUND_FLAG]
                with self.subTest(enabled=enabled, location=location), self.assertRaises(guard.Refusal):
                    guard.geometry_bound_evidence(resource, 'car', a, p, command)
        for cls, bad in (('person', True), ('car', 0), ('car', 'true'), ('car', None)):
            with self.subTest(cls=cls, bad=bad), self.assertRaises(guard.Refusal):
                guard.geometry_bound_evidence({guard.CORRELATED_BOUND_FIELD: bad}, cls, {}, {}, [])
        for argv in ([guard.CORRELATED_BOUND_FLAG]*2, [guard.CORRELATED_BOUND_FLAG+'=true']):
            with self.assertRaises(guard.Refusal):
                guard.geometry_bound_evidence({guard.CORRELATED_BOUND_FIELD: True}, 'car',
                    {'correlated_two_face_bound': True},
                    {'uav_tracking_state_estimator': {'ros__parameters': {guard.CORRELATED_BOUND_FIELD: True}}}, argv)

    def test_full_guard_accepts_matching_candidate_and_refuses_off_safety_for_on(self):
        for complete in (True, False):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as temporary:
                m, c, r, s, f, _ = safety_fixture(Path(temporary))
                if complete:
                    bind_geometry_safety_fixture(c, f)
                    SafetyTests.refresh(m, s, f)
                    guard.validate_safety(m, c, r)
                else:
                    c.core['protocol']['resources']['car'][guard.CORRELATED_BOUND_FIELD] = True
                    with self.assertRaisesRegex(guard.Refusal, 'Safety geometry'):
                        guard.validate_safety(m, c, r)


class EvidenceTests(unittest.TestCase):
    def test_binding_checks_actual_bytes_and_refuses_bags_without_hashing_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); binding=write(root/"evidence.json",{"result":"PASS"})
            self.assertEqual(guard.bound(binding)[1]["result"],"PASS")
            (root/"evidence.json").write_text('{}')
            with self.assertRaisesRegex(guard.Refusal,"changed"):guard.bound(binding)
            (root/"bag.db3.zstd").write_bytes(b"not opened")
            with self.assertRaisesRegex(guard.Refusal,"forbidden"):guard.sha(root/"bag.db3.zstd")

    def test_duplicate_json_and_nonfinite_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"x.json"
            for text in ('{"x":1,"x":2}','{"x":NaN}'):
                path.write_text(text)
                with self.assertRaises(guard.Refusal):guard.load(path)

    def test_full280_exact_reference_and_seed_partition(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest,context=plans(Path(temporary))
            self.assertEqual(len(context.core['trials'])+len(context.extension['trials']),280)
            original=deepcopy(context.extension)
            for defect in ("subset","seed","reference"):
                changed=deepcopy(original)
                if defect=='subset':changed['trials'].pop()
                elif defect=='seed':changed['trials'][0]['seed']=4
                else:changed['core_reference_binding']['sha256']='0'*64
                seal_plan(changed); manifest['plans']['extension']=write(context.extension_path,changed)
                with self.subTest(defect=defect),self.assertRaises(guard.Refusal):guard.read_plans(manifest)

    def test_windows_registry_path_conversion(self):
        self.assertEqual(guard.windows_mount(r'\\?\D:\WSL\UAVHumble22'),'/mnt/d/WSL/UAVHumble22')
        with self.assertRaises(guard.Refusal):guard.windows_mount(r'\\server\data')


class StorageTests(unittest.TestCase):
    def run_storage(self,manifest,context,runtime,rows,backend):
        # Model only the actual results symlink for arithmetic tests. Native
        # mount/vhd queries are separately tested and never mocked in production.
        original=Path.resolve
        def resolution(path,*args,**kwargs):
            if path == context.root/'results':return context.storage_results
            return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',resolution):
            return guard.validate_storage(manifest,context,runtime,rows,backend)

    def test_same_volume_aggregates280_once_and_reserves_at_least8gib(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            report=self.run_storage(m,c,r,rows,b)
            self.assertEqual(report['pending_slots'],280)
            d=report['volumes']['D']
            self.assertEqual(d['full_280_persistent_bytes'],280000)
            self.assertEqual(d['required_bytes'],280000+500+guard.MIN_RESERVE)
            self.assertEqual(len(b.reads),1)

    def test_split_volume_requires_both_physical_volumes_and_vhd_host_margin(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary),split=True)
            b.free={'D':10**15,'E':guard.MIN_RESERVE-1}
            with self.assertRaisesRegex(guard.Refusal,'physical volume E'):self.run_storage(m,c,r,rows,b)
            b.free['E']=10**15
            report=self.run_storage(m,c,r,rows,b)
            self.assertEqual(report['volumes']['E']['unattempted_persistent_bytes'],2800)
            self.assertEqual(report['volumes']['E']['temporary_reserve_bytes'],guard.MIN_RESERVE)

    def test_all28_cells_required_even_after_some_slots_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            first=next(iter(rows['core']));rows['core'][first]['status']='FAIL'
            m['storage']['cells'].pop()
            with self.assertRaisesRegex(guard.Refusal,'28-cell'):self.run_storage(m,c,r,rows,b)

    def test_remaining_budget_counts_unattempted_and_retains_original_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            first=next(iter(rows['core']));rows['core'][first]['status']='FAIL'
            report=self.run_storage(m,c,r,rows,b)
            self.assertEqual(report['pending_slots'],279)
            self.assertEqual(report['volumes']['D']['unattempted_persistent_bytes'],279000)
            self.assertEqual(rows['core'][first]['status'],'FAIL')

    def test_insufficient_by_one_byte_refuses_before_any_started_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);m,c,r,b,rows=storage_fixture(root)
            b.free=280000+500+guard.MIN_RESERVE-1
            with self.assertRaisesRegex(guard.Refusal,'no slot started'):self.run_storage(m,c,r,rows,b)
            self.assertEqual(list(root.rglob('*.started.json')),[])

    def test_declared_temporary_peak_above8gib_is_required_in_full(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            m['storage']['temporary_peak_bytes']['D']=12*1024**3
            report=self.run_storage(m,c,r,rows,b)
            self.assertEqual(report['volumes']['D']['temporary_reserve_bytes'],12*1024**3)

    def test_archive_derived_bound_cannot_be_called_a_measurement_or_underdeclared(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            m['storage']['temporary_bound_rule']['extra_bytes_by_volume']['D']=1000
            with self.assertRaisesRegex(guard.Refusal,'archive-derived bound'):self.run_storage(m,c,r,rows,b)

    def test_alias_volume_duplicate_identity_is_refused_instead_of_double_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary),split=True)
            b.identities={'D':'same','E':'same'}
            with self.assertRaisesRegex(guard.Refusal,'declared twice'):self.run_storage(m,c,r,rows,b)

    def test_wrong_vhd_host_registry_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            wrong=Path(temporary)/'other.vhdx';wrong.write_bytes(b'x');b.vhd=wrong
            with self.assertRaisesRegex(guard.Refusal,'registry-backed'):self.run_storage(m,c,r,rows,b)

    def test_budget_cannot_be_below_actual_bound_size_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            m['storage']['cells'][0]['persistent_bytes_by_volume']['D']=1
            with self.assertRaisesRegex(guard.Refusal,'actual complete'):self.run_storage(m,c,r,rows,b)

    def test_compressed_bytes_are_only_statted_and_changes_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,b,rows=storage_fixture(Path(temporary))
            sample=guard.load(m['storage']['cells'][0]['development_size_evidence']['path'])
            (Path(sample['trial'])/'rosbag/data.db3.zstd').write_bytes(b'changed')
            with self.assertRaisesRegex(guard.Refusal,'accounting size changed'):self.run_storage(m,c,r,rows,b)


class InitialAndResolutionTests(unittest.TestCase):
    def test_existing_attempt_prevents_retrofit_of_initial_full280_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manifest,context=plans(root);rows=pending(context)
            context.registration_times=[guard.utc(T)]
            manifest.update(created_utc=T,manifest_sha256='a'*64,tool={'fixture':'only'})
            starts=[guard.utc(T)+timedelta(seconds=2)]
            with self.assertRaisesRegex(guard.Refusal,'retrofit'):guard.validate_initial(manifest,context,rows,starts,root/'state')

    def test_draft_or_postflight_registration_cannot_be_admitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manifest,context=plans(root);rows=pending(context)
            context.registration_times=[guard.utc(T)+timedelta(seconds=5)]
            manifest.update(created_utc=T,manifest_sha256='a'*64,tool={'fixture':'only'})
            with self.assertRaisesRegex(guard.Refusal,'preceded'):guard.validate_initial(manifest,context,rows,[guard.utc(T)+timedelta(seconds=2)],root/'state')

    def test_original_infrastructure_failure_needs_actual_exact_bound_diagnosis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);rows={'x':{'record_sha256':'a'*64,'infrastructure_stop':True,'finished_utc':T}}
            plan={'plan_sha256':'b'*64}
            with self.assertRaisesRegex(guard.Refusal,'separately bound'):guard.validate_resolution(None,plan,rows)
            evidence=root/'diagnosis.log';evidence.write_text('fixture original diagnosis')
            data={'result':'PASS','plan_sha256':'b'*64,'resolved_record_sha256':['a'*64],
                  'created_utc':'2026-10-20T00:00:01+00:00','evidence':[guard.file_binding(evidence)]}
            binding=write(root/'resolution.json',data)
            self.assertEqual(guard.validate_resolution(binding,plan,rows),(root/'resolution.json').resolve())
            data['resolved_record_sha256']=[];binding=write(root/'resolution.json',data)
            with self.assertRaisesRegex(guard.Refusal,'every original'):guard.validate_resolution(binding,plan,rows)

    def test_running_attempt_is_never_made_pending_for_retry(self):
        context=SimpleNamespace(core={},extension={})
        runtime=SimpleNamespace(v4=SimpleNamespace(read_slots=lambda *a,**k:{'x':{'status':'RUNNING'}}))
        with self.assertRaisesRegex(guard.Refusal,'without retry'):guard.slot_rows(context,runtime)


class SafetyTests(unittest.TestCase):
    def test_safety_card_bash_constructs_both_classes_from_the_actual_plan(self):
        if os.name == 'nt':
            git=shutil.which('git')
            bash=Path(git).resolve().parent.parent/'bin/bash.exe' if git else Path('missing-host-git-bash')
        else:
            bash=Path(shutil.which('bash') or 'missing-host-bash')
        if not bash.is_file():self.skipTest('Native host bash is unavailable; never use a WSL launcher')
        card=(ROOT/'planning/reliability-v4-ambiguity-execution.md').read_text(encoding='utf-8')
        block=card.split('```bash\n',1)[1].split('\n```',1)[0]
        protocol=guard.load(ROOT/'planning/reliability-v4-preregistration.json')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();plan=root/'plan.json';log=root/'argv.jsonl'
            capture=root/'capture.py';script=root/'card.sh'
            capture.write_text('import json,sys\nwith open(sys.argv[1],"a",encoding="utf-8") as f: f.write(json.dumps(sys.argv[2:])+"\\n")\n',encoding='utf-8')
            prelude='set -euo pipefail\n'
            prelude+='tracking_fixture_python='+shlex.quote(Path(sys.executable).as_posix())+'\n'
            prelude+='tracking_fixture_capture='+shlex.quote(capture.as_posix())+'\n'
            prelude+='tracking_fixture_log='+shlex.quote(log.as_posix())+'\n'
            prelude+='python3() { "$tracking_fixture_python" -X utf8 "$@"; }\n'
            # Every apparent command is intercepted before it could launch ROS.
            prelude+='bash() { "$tracking_fixture_python" -X utf8 "$tracking_fixture_capture" "$tracking_fixture_log" "$@"; }\n'
            body=block.replace('tracking_plan=/absolute/path/to/the/final_source_probe/plan.json',
                               'tracking_plan='+shlex.quote(plan.as_posix()),1)
            script.write_text(prelude+body+'\ntracking_common_checks() { :; }\ntracking_run_class person\ntracking_run_class car\n',encoding='utf-8',newline='\n')
            sentinel=deepcopy(protocol)
            # An inert data-flow fixture proves that constants in the card
            # cannot accidentally pass merely by matching today's protocol.
            sentinel.update(real_time_factor=.125,flight_wall_timeout_s=777.)
            for cls in guard.CLASSES:
                sentinel['resources'][cls].update(model='models/fixture_'+cls+'.pt',
                    inference_image_size=288 if cls=='person' else 864,inference_threads=1,
                    desired_distance_m=6. if cls=='person' else 10.,
                    navigation_correlated_two_face_bound=cls=='car')
            for selected in (protocol,sentinel):
                write(plan,{'frozen_root':root.as_posix(),'protocol':selected})
                log.write_text('',encoding='utf-8')
                environment={**os.environ,'PYTHONUTF8':'1','MSYS2_ARG_CONV_EXCL':'*'}
                completed=subprocess.run([str(bash),'--noprofile','--norc',str(script)],
                    cwd=root,env=environment,capture_output=True,text=True,timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.assertEqual(completed.returncode,0,completed.stderr)
                calls=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
                flights=[row for row in calls if Path(row[1]).name=='run_stage1_trial.py']
                self.assertEqual(len(calls),8)
                self.assertEqual(len(flights),4)
                self.assertEqual({(row[row.index('--class')+1],row[row.index('--target-mode')+1]) for row in flights},
                    {(cls,mode) for cls in guard.CLASSES for mode in ('auto_unique','locked_target')})
                for argv in flights:
                    option=lambda key:argv[argv.index('--'+key)+1]
                    resource=selected['resources'][option('class')]
                    self.assertEqual(float(option('real-time-factor')),selected['real_time_factor'])
                    self.assertEqual(float(option('wall-timeout')),selected['flight_wall_timeout_s'])
                    self.assertEqual(Path(option('model-path')).resolve(),(root/resource['model']).resolve())
                    self.assertEqual(int(option('inference-image-size')),resource['inference_image_size'])
                    self.assertEqual(int(option('inference-threads')),resource['inference_threads'])
                    self.assertEqual(float(option('desired-distance-m')),resource['desired_distance_m'])
                    self.assertEqual(argv.count(guard.CORRELATED_BOUND_FLAG),
                                     int(resource.get(guard.CORRELATED_BOUND_FIELD, False)))
                    self.assertEqual(option('takeoff-mode'),'px4_native')
                    self.assertEqual(float(option('takeoff-height-m')),3.)
                    self.assertNotIn('--occlusions',argv)
                    self.assertNotIn('--reselect-after-loss',argv)
            invalid = deepcopy(sentinel)
            invalid['resources']['person'][guard.CORRELATED_BOUND_FIELD] = True
            write(plan, {'frozen_root': root.as_posix(), 'protocol': invalid})
            log.write_text('', encoding='utf-8')
            completed = subprocess.run([str(bash), '--noprofile', '--norc', str(script)],
                cwd=root, env=environment, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(log.read_text(encoding='utf-8'), '')

    @staticmethod
    def refresh(manifest,summary,facts):
        summary['source_facts']=write(Path(summary['source_facts']['path']),facts)
        manifest['safety']=write(Path(manifest['safety']['path']),summary)

    def test_actual_yaml_syntax_owned_agent_sigint_and_relative_evaluator_argv_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,calls=safety_fixture(Path(temporary))
            self.assertIn('ros__parameters:',Path(s['slots'][0]['evidence']['runtime_parameters']['path']).read_text())
            guard.validate_safety(m,c,r)
            self.assertEqual(len(calls),4)

    def external_card(self, root, manifest, context, summary, facts):
        canonical=Path(context.development['frozen_root'])/'planning/reliability-v4-ambiguity-execution.md'
        card=root/'external-followon.md'
        card.write_text('Reviewed orchestration revision; original audit code follows.\n\n'+
                        canonical.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
        registry=guard.load(facts['registry']['path'])
        registry['execution_card']=guard.file_binding(card)
        facts['registry']=write(Path(facts['registry']['path']),registry)
        for slot in summary['slots']:
            slot['executions']['terminal_speed']['argv'][-1]=str(card)
        self.refresh(manifest,summary,facts)
        return card,registry

    def test_bound_external_prospective_card_preserves_the_original_tail_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);m,c,r,s,f,calls=safety_fixture(root)
            card,_=self.external_card(root,m,c,s,f)
            self.assertNotEqual(card.parent,Path(c.development['frozen_root'])/'planning')
            guard.validate_safety(m,c,r)
            self.assertEqual(len(calls),4)

    def test_external_safety_card_does_not_allow_code_hash_or_command_substitution(self):
        for defect in ('stale_hash','changed_code','duplicate_code','changed_tail','different_argument'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);m,c,r,s,f,_=safety_fixture(root)
                card,registry=self.external_card(root,m,c,s,f)
                if defect in ('stale_hash','changed_code','duplicate_code'):
                    text=card.read_text(encoding='utf-8')
                    if defect=='changed_code':
                        text=text.replace("<<'PY'\n","<<'PY'\n# substituted audit\n",1)
                    elif defect=='duplicate_code':
                        text+="\n<<'PY'\npass\nPY\n"
                    else:
                        text+='\nUnregistered edit.\n'
                    card.write_text(text,encoding='utf-8',newline='\n')
                    if defect!='stale_hash':registry['execution_card']=guard.file_binding(card)
                elif defect=='changed_tail':
                    tail=Path(registry['tail_script']['path'])
                    tail.write_text('# substituted audit\n',encoding='utf-8')
                    registry['tail_script']=guard.file_binding(tail)
                    for slot in s['slots']:
                        slot['executions']['terminal_speed']['code_script']=registry['tail_script']
                else:
                    other=root/'unregistered-card.md';other.write_bytes(card.read_bytes())
                    s['slots'][0]['executions']['terminal_speed']['argv'][-1]=str(other)
                f['registry']=write(Path(f['registry']['path']),registry)
                self.refresh(m,s,f)
                with self.assertRaises(guard.Refusal):guard.validate_safety(m,c,r)

    def test_safety_simulation_resources_cannot_drift_after_legitimate_rebinding(self):
        for defect in ('config_rtf','config_wall','supervisor_rtf','flight_rtf','flight_wall'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as temporary:
                m,c,r,s,f,_=safety_fixture(Path(temporary))
                slot=s['slots'][0]
                if defect.startswith('config_'):
                    key='real_time_factor' if defect=='config_rtf' else 'wall_timeout'
                    binding=slot['evidence']['run_config'];data=guard.load(binding['path'])
                    data[key]=.5 if key=='real_time_factor' else 300.
                    slot['evidence']['run_config']=write(Path(binding['path']),data)
                elif defect=='supervisor_rtf':
                    binding=slot['evidence']['runtime_parameters'];path=Path(binding['path'])
                    data=yaml.safe_load(path.read_text())
                    data['uav_tracking_flight_supervisor']['ros__parameters']['requested_simulation_real_time_factor']=.5
                    path.write_text(yaml.safe_dump(data),encoding='utf-8')
                    slot['evidence']['runtime_parameters']=guard.file_binding(path)
                else:
                    argv=slot['executions']['flight']['argv']
                    flag='--real-time-factor' if defect=='flight_rtf' else '--wall-timeout'
                    argv[argv.index(flag)+1]='0.5' if defect=='flight_rtf' else '300.0'
                    registry=guard.load(f['registry']['path'])
                    next(row for row in registry['trials'] if row['id']==slot['id'])['flight_argv']=argv
                    f['registry']=write(Path(f['registry']['path']),registry)
                self.refresh(m,s,f)
                with self.assertRaises(guard.Refusal):guard.validate_safety(m,c,r)

    def test_real_results_link_preserves_lexical_classifier_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,calls=safety_fixture(Path(temporary),linked=True)
            guard.validate_safety(m,c,r)
            self.assertEqual(len(calls),4)
            self.assertNotEqual(calls[0],calls[0].resolve())
            self.assertTrue(str(calls[0]).startswith(c.development['frozen_root']))
            with self.assertRaisesRegex(FileNotFoundError,'Lost frozen'):r.v4.infrastructure_evidence(calls[0].resolve(),[])

    def test_agent_crash_and_other_process_sigint_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary))
            binding=s['slots'][0]['evidence']['process_exit_codes'];original=guard.load(binding['path'])
            for process,code in (('agent',-9),('ros',-2),('bag',None),('px4',139)):
                value={**original,process:code};s['slots'][0]['evidence']['process_exit_codes']=write(Path(binding['path']),value)
                self.refresh(m,s,f)
                with self.subTest(process=process),self.assertRaisesRegex(guard.Refusal,'owned child'):guard.validate_safety(m,c,r)

    def test_true_yaml_weakened_safety_age_is_rejected_after_legitimate_hash_rebinding(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary))
            path=Path(s['slots'][0]['evidence']['runtime_parameters']['path']);data=yaml.safe_load(path.read_text())
            data['uav_tracking_state_estimator']['ros__parameters']['max_prediction_duration_s']=2.
            path.write_text(yaml.safe_dump(data),encoding='utf-8');s['slots'][0]['evidence']['runtime_parameters']=guard.file_binding(path)
            self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'runtime YAML safety'):guard.validate_safety(m,c,r)

    def test_summary_cannot_upgrade_pending_original_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary));f['pending_count']=1;self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'original execution facts'):guard.validate_safety(m,c,r)

    def test_missing_ambiguity_observation_cannot_hide_behind_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary))
            slot=next(slot for slot in s['slots'] if slot['case']=='locked_ambiguity')
            path=Path(slot['evidence']['specialized']['path']);report=guard.load(path);report['geometric_ambiguity_observed']=False
            slot['evidence']['specialized']=write(path,report);self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'Actual selected geometric'):guard.validate_safety(m,c,r)

    def test_wrong_specialist_command_or_wrong_class_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary))
            command=s['slots'][0]['executions']['specialized']['argv'];command[2]='scripts/other_evaluator.py';self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'specialist command'):guard.validate_safety(m,c,r)

    def test_original_clock_tail_and_tail_schema_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary));slot=s['slots'][0];path=Path(slot['evidence']['terminal_speed']['path'])
            report=guard.load(path);report['interval']={'start_s':13.8,'end_s':19.}
            slot['evidence']['terminal_speed']=write(path,report);self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'original exact recorded Clock'):guard.validate_safety(m,c,r)
            report['schema_version']=9;slot['evidence']['terminal_speed']=write(path,report);self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'speed supplement'):guard.validate_safety(m,c,r)

    def test_prospective_registry_cannot_be_created_after_flight(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,s,f,_=safety_fixture(Path(temporary));path=Path(f['registry']['path']);registry=guard.load(path)
            registry['created_utc']='2026-10-20T00:00:02+00:00';f['registry']=write(path,registry);self.refresh(m,s,f)
            with self.assertRaisesRegex(guard.Refusal,'prospective registry'):guard.validate_safety(m,c,r)


def registration_fixture(root):
    # Real replay configuration/file validators operate on inert temp helper
    # files; official flight/runtime validation remains an explicit test double.
    from tests import test_replay_comparison as fixtures
    root=root.resolve();manifest,context=plans(root)
    configuration=fixtures.registered_fixture();configuration.pop('evidence_scope')
    for relative in fixtures.replay.SOURCE_FILES:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# inert registered helper fixture\n')
        context.core['source_hashes'][relative]=guard.sha(path)
    core_protocol={'status':'REGISTERED','registration_utc':T}
    extension_protocol={'status':'REGISTERED','registration_utc':T}
    for plan in (context.core,context.extension):
        plan['source_hashes']=deepcopy(context.core['source_hashes'])
        plan['created_utc']='2026-10-20T00:00:01+00:00'
        plan['protocol']=core_protocol
        plan['extension_protocol_binding']={'protocol':extension_protocol}
        plan['magnetic_runtime_binding']={'manifest_sha256':'e'*64,'manifest':{}}
        plan['magnetic_library_binding']={'registration_sha256':'f'*64,'registration':{}}
    seal_plan(context.core);manifest['plans']['core']=write(context.core_path,context.core)
    context.extension['core_reference_binding']={**manifest['plans']['core'],'plan_sha256':context.core['plan_sha256']}
    seal_plan(context.extension);manifest['plans']['extension']=write(context.extension_path,context.extension)
    freeze=configuration['freeze_requirements']
    freeze.update(final_engineering_plan_path=str(context.core_path),final_engineering_plan_file_sha256=manifest['plans']['core']['sha256'],
        final_engineering_plan_digest=context.core['plan_sha256'],flight_source_hashes=context.core['source_hashes'],model_hashes=context.core['model_hashes'],
        runtime_and_magnetic_bindings={'px4_runtime_manifest_sha256':'e'*64,'magnetic_library_registration_sha256':'f'*64},
        offline_replay_source_hashes={name:guard.sha(root/name) for name in fixtures.replay.SOURCE_FILES})
    configuration['registration']['registered_utc']='2026-10-20T00:00:02+00:00';fixtures.seal(configuration)
    core_path=root/'planning/reliability-v4-preregistration.json';extension_path=root/'planning/reliability-v4-extension-preregistration.json'
    replay_path=root/'planning/reliability-v4-estimator-replay-preregistration.json'
    manifest.update(created_utc='2026-10-20T00:00:03+00:00',registrations={'core':write(core_path,core_protocol),
        'extension':write(extension_path,extension_protocol),'replay':write(replay_path,configuration)})
    runtime=SimpleNamespace(v4=SimpleNamespace(PROTOCOL_PATH='planning/reliability-v4-preregistration.json',
        EXTENSION_PROTOCOL_PATH='planning/reliability-v4-extension-preregistration.json',validate_plan=Mock(),verify_sources=Mock()),replay=fixtures.cli)
    return manifest,context,runtime,configuration


class RegistrationTests(unittest.TestCase):
    def test_all_three_registrations_and_real_replay_plan_file_binding_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,_=registration_fixture(Path(temporary));guard.validate_registrations(m,c,r)
            self.assertEqual(r.v4.validate_plan.call_count,1);self.assertEqual(r.v4.verify_sources.call_count,1)
            self.assertEqual(r.v4.validate_plan.call_args.args,(c.extension,c.extension_path))
            self.assertEqual(len(c.registration_times),3)

    def test_draft_core_and_draft_replay_are_each_refused(self):
        for label in ('core','replay'):
            with self.subTest(label=label),tempfile.TemporaryDirectory() as temporary:
                m,c,r,_=registration_fixture(Path(temporary));path=Path(m['registrations'][label]['path']);data=guard.load(path)
                data['status']='DRAFT';m['registrations'][label]=write(path,data)
                with self.assertRaises(ValueError):guard.validate_registrations(m,c,r)

    def test_manifest_cannot_precede_last_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,_=registration_fixture(Path(temporary));m['created_utc']=T
            with self.assertRaisesRegex(guard.Refusal,'follow all registrations'):guard.validate_registrations(m,c,r)

    def test_replay_parameter_digest_and_actual_helper_bytes_cannot_drift(self):
        for defect in ('configuration','helper'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as temporary:
                m,c,r,configuration=registration_fixture(Path(temporary))
                if defect=='configuration':
                    configuration['calibration']['ema_alpha']=.9
                    m['registrations']['replay']=write(Path(m['registrations']['replay']['path']),configuration)
                else:
                    (c.root/r.replay.SOURCE_FILES[0]).write_text('# changed helper bytes\n')
                with self.assertRaises(ValueError):guard.validate_registrations(m,c,r)

    def test_fixture_scope_cannot_authorize_formal_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,configuration=registration_fixture(Path(temporary));configuration['evidence_scope']='PURE_REPLAY_FIXTURE_ONLY'
            m['registrations']['replay']=write(Path(m['registrations']['replay']['path']),configuration)
            with self.assertRaisesRegex(guard.Refusal,'Fixture cannot admit'):guard.validate_registrations(m,c,r)


def calibration_fixture(root):
    from tests import test_replay_calibration as fixtures
    root=root.resolve();final=root/'final';final.mkdir();dev=root/'development';dev.mkdir()
    helper=final/'fixture_helper.py';helper.write_text('# inert export helper\n')
    policy=dev/'planning/policy.md';policy.parent.mkdir();policy.write_text('# immutable fixture policy\n')
    development={'mode':'PROBE','selected_seeds':[4],'selected_classes':list(guard.CLASSES),'selected_groups':list(guard.GROUPS),
        'frozen_root':str(dev),'source_hashes':{'fixture_helper.py':guard.sha(helper)},'trials':[]}
    records={};provenance={};statistics={};expected_receipt={'fixture_audit_boundary_only':True}
    for cls in guard.CLASSES:
        for group in guard.GROUPS:
            identifier=f'{cls}_{group}_seed004';directory=dev/'results'/identifier;directory.mkdir(parents=True)
            development['trials'].append({'id':identifier,'name':identifier,'directory':str(directory),'target_class':cls})
            if group!='stage1_velocity':continue
            config_binding=write(directory/'run_config.json',{'seed':4,'target_class':cls,'command_mode':'velocity'})
            archive_binding=write(directory/'bag_integrity.json',{'status':'PASS'})
            record={'status':'EVALUATION_PENDING','execution_status':'COMPLETED','infrastructure_stop':False,'flight_exit_code':0,
                'artifact_hashes':{'run_config.json':config_binding['sha256'],'bag_integrity.json':archive_binding['sha256']}}
            record_binding=write(dev/'slots'/(identifier+'.json'),record);records[identifier]=record
            arrays=fixtures.trial([fixtures.measurement(1.,1.),fixtures.measurement(2.,3.,accepted=False)])
            arrays.update(seed=4,target_class=cls,group='stage1_velocity',slot_id='DEVELOPMENT_ONLY_'+identifier,
                export_audit={'bag_reader':{'bag':str(directory/'rosbag')},'native_archive_integrity_sha256':archive_binding['sha256']})
            arrays_binding=write(root/'arrays'/(cls+'.json'),arrays)
            statistics[cls]=fixtures.calibration.geometry_statistics(arrays)
            provenance[cls]={'slot_id':identifier,'terminal_record':record_binding,'arrays':arrays_binding,
                'recording_evidence':{name:{'path':str(directory/name),'sha256':binding['sha256']} for name,binding in
                    (('run_config.json',config_binding),('bag_integrity.json',archive_binding))},
                'verified_export_evidence':expected_receipt}
    development['plan_sha256']=guard.sealed(development,'plan_sha256');dev_binding=write(dev/'plan.json',development)
    core_gate={'result':'PASS','schema_version':2,'probe_slots':[{'plan_path':dev_binding['path'],'slot_id':trial['id']} for trial in development['trials']],
               'bindings':{'pure_fixture_binding_only':'does not authorize real execution'}}
    extension_gate={'result':'PASS','schema_version':2,'probe_slots':[{'fixture_extension':i} for i in range(16)]}
    def gate_binding(path,value):return {**write(path,value),'evidence':value}
    core_binding=gate_binding(root/'core_gate.json',core_gate);extension_binding=gate_binding(root/'extension_gate.json',extension_gate)
    parameters={'R0_sensor_world_m2_by_class':{cls:value['R0_sensor_world_m2'] for cls,value in statistics.items()},'ema_alpha':.35}
    candidate={'kind':'RELIABILITY_V4_DEVELOPMENT_CALIBRATION','status':'CANDIDATE_NOT_REGISTERED','scope':'DEVELOPMENT_ONLY',
        'created_utc':T,'development_plan':{**dev_binding,'plan_sha256':development['plan_sha256']},'provenance':provenance,
        'classes':statistics,'candidate_parameters':parameters,'policy':{'path':'planning/policy.md','sha256':guard.sha(policy)},
        'source_hashes':{'scripts/calibrate_estimator_replay_v4.py':'c'*64}}
    candidate_binding=write(root/'candidate.json',candidate)
    context=SimpleNamespace(root=final,core={'development_probe_gate':core_binding,
        'extension_protocol_binding':{'protocol':{'development_readiness':extension_binding}},
        'source_hashes':{'scripts/calibrate_estimator_replay_v4.py':'c'*64}},
        replay_configuration={'freeze_requirements':{'development_calibration_evidence':{'artifact_hashes':{candidate_binding['path']:candidate_binding['sha256']}}},
                              'calibration':deepcopy(parameters)},registration_times=[guard.utc(T)+timedelta(seconds=1)])
    v4=SimpleNamespace(sha=guard.sha,validate_plan=Mock(),read_slots=lambda *a,**k:records,
                      record_path=lambda plan,trial:dev/'slots'/(trial['id']+'.json'))
    replay=SimpleNamespace(EXPORT_SOURCE_FILES=('fixture_helper.py',),SOURCE_FILES=('fixture_helper.py',),
                           verify_export_evidence=Mock(return_value=expected_receipt))
    runtime=SimpleNamespace(v4=v4,replay=replay,calibration=fixtures.calibration)
    return {'calibration':candidate_binding},context,runtime,candidate,records


class CalibrationSourceTests(unittest.TestCase):
    @staticmethod
    def refresh(manifest,context,candidate):
        manifest['calibration']=write(Path(manifest['calibration']['path']),candidate)
        binding=manifest['calibration']
        context.replay_configuration['freeze_requirements']['development_calibration_evidence']['artifact_hashes']={binding['path']:binding['sha256']}

    def test_predeclared_two_slots_and_actual_arrays_are_bound_without_bag_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,_,_=calibration_fixture(Path(temporary));guard.validate_development(m,c,r)
            self.assertEqual(r.replay.verify_export_evidence.call_count,2)
            self.assertTrue(all(call.kwargs['development_only'] is True for call in r.replay.verify_export_evidence.call_args_list))

    def test_wrong_seed_calibration_plan_is_refused_before_export_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,candidate,_=calibration_fixture(Path(temporary));binding=candidate['development_plan'];path=Path(binding['path']);plan=guard.load(path)
            plan['selected_seeds']=[3];binding.update(write(path,plan));self.refresh(m,c,candidate)
            with self.assertRaisesRegex(guard.Refusal,'canonical complete seed004'):guard.validate_development(m,c,r)
            r.replay.verify_export_evidence.assert_not_called()

    def test_failed_canonical_flight_cannot_be_replaced_by_candidate_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,candidate,records=calibration_fixture(Path(temporary));record=records['person_stage1_velocity_seed004'];record['flight_exit_code']=1
            candidate['provenance']['person']['terminal_record']=write(Path(candidate['provenance']['person']['terminal_record']['path']),record)
            self.refresh(m,c,candidate)
            with self.assertRaisesRegex(guard.Refusal,'incomplete or substituted'):guard.validate_development(m,c,r)

    def test_actual_geometry_statistics_cannot_be_changed_by_rebinding_array_hash_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,candidate,_=calibration_fixture(Path(temporary));path=Path(candidate['provenance']['person']['arrays']['path']);data=guard.load(path)
            data['measurements'][0]['R_geometry_world_m2'][0][0]=9.
            candidate['provenance']['person']['arrays']=write(path,data);self.refresh(m,c,candidate)
            with self.assertRaisesRegex(guard.Refusal,'R0 statistics'):guard.validate_development(m,c,r)

    def test_registered_estimator_parameters_must_equal_real_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            m,c,r,_,_=calibration_fixture(Path(temporary));c.replay_configuration['calibration']['ema_alpha']=.95
            with self.assertRaisesRegex(guard.Refusal,'Registered estimator parameters differ'):guard.validate_development(m,c,r)


class InvocationTests(unittest.TestCase):
    def test_refused_check_invokes_no_runner_and_creates_no_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runner=Mock()
            def refused(*args,**kwargs):raise guard.Refusal('Insufficient physical volume')
            with patch.object(guard,'guard_lock',return_value=nullcontext()),self.assertRaises(guard.Refusal):
                guard.execute_one(root/'manifest.json',checker=refused,command_runner=runner)
            runner.assert_not_called();self.assertEqual(list(root.iterdir()),[])

    def test_only_one_frozen_runner_call_and_original_fail_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();state=root/'state';before={'x':{'status':'PENDING'},'y':{'status':'PENDING'}}
            after={'x':{'status':'FAIL','infrastructure_stop':False},'y':{'status':'PENDING'}}
            command=['bash','/frozen/scripts/run_research_session.sh','/frozen/scripts/run_reliability_v4.py','run','--plan','/frozen/results/core/plan.json','--max-new-trials','1']
            report={'command':command,'capacity':{'pending_slots':280},'next_matrix':'core','next_slot_id':'x'}
            admission=SimpleNamespace(report=report,state=state,manifest={'manifest_sha256':'a'*64,'tool':{'fixture':'separately bound'}},
                context=SimpleNamespace(root=root,core={}),rows={'core':before,'extension':{}},
                runtime=SimpleNamespace(v4=SimpleNamespace(read_slots=lambda *a,**k:after)))
            runner=Mock(return_value=SimpleNamespace(returncode=0))
            with patch.object(guard,'guard_lock',return_value=nullcontext()),patch.object(guard,'validate_storage',return_value={'pending_slots':279}):
                result=guard.execute_one(root/'manifest.json',checker=lambda *a,**k:admission,command_runner=runner)
            self.assertEqual(runner.call_count,1);self.assertEqual(runner.call_args.args[0],command)
            self.assertEqual(result['preserved_status'],'FAIL');self.assertEqual(result['started_this_invocation'],1)
            self.assertEqual(result['capacity_after']['pending_slots'],279)
            self.assertEqual(after['y']['status'],'PENDING')
            self.assertEqual(guard.load(state/'initial_admission.json')['initial_pending_slots'],280)

    def test_frozen_runner_stopping_before_a_new_attempt_is_never_reported_as_completed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();rows={'x':{'status':'PENDING'}}
            admission=SimpleNamespace(report={'command':['inert-fixture'],'capacity':{'pending_slots':280},'next_matrix':'core','next_slot_id':'x'},
                state=root/'state',manifest={'manifest_sha256':'a'*64,'tool':{}},context=SimpleNamespace(root=root,core={}),
                rows={'core':rows,'extension':{}},runtime=SimpleNamespace(v4=SimpleNamespace(read_slots=lambda *a,**k:rows)))
            with patch.object(guard,'guard_lock',return_value=nullcontext()),patch.object(guard,'validate_storage',return_value={}):
                result=guard.execute_one(root/'manifest.json',checker=lambda *a,**k:admission,command_runner=lambda *a,**k:SimpleNamespace(returncode=0))
            self.assertEqual(result['result'],'STOP');self.assertEqual(result['started_this_invocation'],0)


if __name__ == '__main__':unittest.main()
