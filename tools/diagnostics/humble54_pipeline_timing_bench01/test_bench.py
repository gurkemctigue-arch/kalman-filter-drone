"""Stdlib fake objects only: no ROS, bag payloads, weights, WSL or launches."""
from array import array
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import ctypes
import gc
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import bench
from observer import Hooks,Observer,Tokens,Trace,actual_local
from reducer import reduce_events
from typed_message import snapshot,valid_snapshot
PROBE=HERE.parent/'humble54_timing_capability_probe01/probe.py'


def message(name,fields,values,package='uav_tracking_interfaces'):
    def init(self):
        for key,value in values.items():setattr(self,'_'+key,value)
    namespace={'__module__':package+'.msg._fake','__slots__':tuple('_'+key for key in fields),
               '__init__':init,'get_fields_and_field_types':classmethod(lambda cls:dict(fields))}
    for name_,kind in fields.items():
        namespace[name_]=property(lambda self,key=name_:getattr(self,'_'+key),lambda self,value,key=name_:setattr(self,'_'+key,value))
    return type(name,(),namespace)()


def small_fields():
    return snapshot(message('TrackingCommand',{'mode':'uint8','valid':'bool','rate':'float32','age':'double'},
                            {'mode':1,'valid':True,'rate':-0.,'age':.0}))


def fixture():
    events=[];serial={}
    def emit(process,kind,when,**fields):
        serial[process]=serial.get(process,0)+1
        e={'process':process,'kind':kind,'event_id':f'{process}:{serial[process]}','local_index':serial[process],
           'recorded_monotonic_ns':when,**fields};events.append(e);return e
    for index,role in enumerate((*bench.ROLES,'replay','monitor')):
        emit(role,'process_start',10+index,boot_id='same-linux-boot',runtime_gate_passed=True,
             monotonic_clock={'monotonic':True,'adjustable':False})
    for n in (900,9100):emit('monitor','fmu_scan',n,publishers=[])
    for phase,role in [('detection','detector'),('state','estimator'),('command','controller')]:
        for n in (850,9150):emit('monitor','controlled_writers',n,phase=phase,writers=[role])
        for n in (900,9100):emit('monitor','graph',n,phase=phase,publishers=[{'gid_hex':role+'gid','node_name':role}])
    emit('replay','replay_input',1400,input_kind='rgb')
    emit('detector','sensor_callback',1500,sensor='rgb',image_token='rgbA',entered_ns=1500)
    emit('detector','sensor_callback',1550,sensor='depth',image_token='depthA',entered_ns=1550)
    emit('detector','snapshot',1600,snapshot_token='jobA',rgb_token='rgbA',depth_token='depthA')
    emit('detector','submit',1610,snapshot_token='jobA',accepted=True)
    emit('detector','worker_start',1700,snapshot_token='jobA')
    def edge(phase,publisher,subscriber,when,token,**lineage):
        anchor=lambda n:{'monotonic_before_ns':n,'monotonic_after_ns':n,'realtime_ns':n+1_000_000}
        pub=emit(publisher,'publish',when+3,phase=phase,writer_token=publisher,before=anchor(when),after=anchor(when+2),
                 success=True,message_fields=small_fields(),**lineage)
        take=emit(subscriber,'take',when+7,phase=phase,entered_ns=when+5,exited_ns=when+6,metadata={'source_timestamp':when+1_000_001},
                  capture_status='CAPTURED',message_fields=small_fields(),object_token=token)
        callback=emit(subscriber,'callback',when+9,phase=phase,entered_ns=when+8,take_event_id=take['event_id'],object_token=token,
                      same_object_as_original_take=True,complete_typed_fields_match_take=True,message_fields=small_fields())
        return pub,take,callback
    edge('detection','detector','estimator',2000,'estimator:received_frame',snapshot_token='jobA')
    accepted=emit('estimator','navigation_update',2100,accepted=True,source_frame_token='estimator:received_frame')
    emit('estimator','navigation_project',2300,project_token='projectA',source_frame_token='estimator:received_frame',
         accepted_update_event_id=accepted['event_id'],project_valid=True)
    edge('state','estimator','controller',2400,'controller:received_state',source_frame_token='estimator:received_frame',
         accepted_update_event_id=accepted['event_id'],project_token='projectA',project_valid=True)
    edge('command','controller','adapter',2600,'adapter:received_command',target_token='controller:received_state',command_valid=True,command_mode=1)
    for role in bench.ROLES:
        emit(role,'executor_shutdown',9500,returned=True,exception=None)
        emit(role,'observer_final',9510,trace_dropped=0,trace_errors=[],instrumentation_errors=[])
    for role in ('replay','monitor'):emit(role,'process_final',9520,trace_dropped=0,trace_errors=[])
    return events,emit,edge


def reduced(events,**kwargs):
    return reduce_events(events,probe_path=PROBE,begin_ns=1000,end_ns=9000,**kwargs)


class TypedTests(unittest.TestCase):
    def test_exact_width_scalar_buffers_preserve_numpy_style_fields_and_nan_bits(self):
        double=ctypes.c_double.from_buffer_copy(bytes.fromhex('010000000000f87f') if sys.byteorder=='little' else bytes.fromhex('7ff8000000000001'))
        single=ctypes.c_float.from_buffer_copy(bytes.fromhex('0100807f') if sys.byteorder=='little' else bytes.fromhex('7f800001'))
        result=snapshot(message('TargetState',{'x':'double','single':'float','z':'double'},
                                {'x':double,'single':single,'z':ctypes.c_double(-0.)}))
        self.assertEqual(result['fields'][0]['value']['bits_be'],'7ff8000000000001')
        self.assertEqual(result['fields'][1]['value']['bits_be'],'7f800001')
        self.assertEqual(result['fields'][2]['value']['bits_be'],'8000000000000000')
        self.assertTrue(valid_snapshot(result))

    def test_nested_complete_fields_arrays_and_signed_zero_are_preserved(self):
        point=message('Point',{'x':'double','y':'double'},{'x':-0.,'y':float('inf')},'geometry_msgs')
        msg=message('TargetState',{'point':'geometry_msgs/Point','cov':'float[2]','names':'sequence<string>'},
                    {'point':point,'cov':array('f',[1.,-0.]),'names':['a','e\u0301']})
        result=snapshot(msg)
        self.assertTrue(valid_snapshot(result))
        self.assertEqual(result['fields'][0]['value']['fields'][0]['value']['bits_be'],'8000000000000000')
        self.assertEqual(result['fields'][1]['value']['items'][1]['bits_be'],'80000000')
        changed=deepcopy(result);changed['fields'][2]['value']['items'].pop()
        self.assertFalse(valid_snapshot(changed))
        msg.point.y=2.;self.assertNotEqual(snapshot(msg),result)

    def test_float32_raw_signaling_nan_payloads_and_float64_bits(self):
        values=array('f');values.frombytes(bytes.fromhex('0100807f') if sys.byteorder=='little' else bytes.fromhex('7f800001'))
        msg=message('TargetState',{'a':'sequence<float>','b':'double'},{'a':values,'b':struct.unpack('>d',bytes.fromhex('fff8000000000001'))[0]})
        result=snapshot(msg)
        self.assertEqual(result['fields'][0]['value']['items'][0]['bits_be'],'7f800001')
        self.assertEqual(result['fields'][1]['value']['bits_be'],'fff8000000000001')
        self.assertTrue(valid_snapshot(result))
        bad=message('TargetState',{'scalar':'float'},{'scalar':float('nan')})
        with self.assertRaises(ValueError):snapshot(bad)

    def test_unknown_structure_incomplete_schema_and_bounds_reject(self):
        for kind,value in [('octet',3),('sequence<mystery>',[1]),('float[2]',[1.]),('sequence<uint8, 1>',[1,2]),('string<=1','ab'),('uint8',True)]:
            with self.subTest(kind=kind),self.assertRaises((TypeError,ValueError)):
                snapshot(message('TrackingCommand',{'field':kind},{'field':value}))
        msg=message('TrackingCommand',{'field':'uint8'},{'field':1})
        type(msg).get_fields_and_field_types=classmethod(lambda cls:{'other':'uint8'})
        with self.assertRaises(TypeError):snapshot(msg)
        result=small_fields();result['fields'][0]['value']={'type':'unknown[]','length':0,'items':[]}
        self.assertFalse(valid_snapshot(result))


class HookTests(unittest.TestCase):
    def test_original_once_same_objects_return_exception_and_thread(self):
        trace=Trace();hooks=Hooks(trace);calls=[];arg=object();returned=object();error=RuntimeError('original')
        class Algorithm:
            def run(self,value,fail=False):
                calls.append((value,threading.get_ident()))
                if fail:raise error
                return returned
        def broken(*args):raise ValueError('observer')
        hooks.method(Algorithm,'run',before=broken,after=broken)
        algorithm=Algorithm();self.assertIs(algorithm.run(arg),returned)
        with self.assertRaises(RuntimeError) as caught:algorithm.run(arg,fail=True)
        self.assertIs(caught.exception,error)
        worker=threading.Thread(target=lambda:self.assertIs(algorithm.run(arg),returned));worker.start();worker.join()
        self.assertEqual(len(calls),3);self.assertTrue(all(x[0] is arg for x in calls))
        self.assertNotEqual(calls[-1][1],threading.get_ident());hooks.close()

    def test_object_tokens_are_bounded_and_do_not_retain_all_images(self):
        class Image:pass
        tokens=Tokens('image',capacity=2);image=Image();reference=weakref.ref(image);first=tokens.token(image)
        self.assertEqual(tokens.token(image),first)
        del image
        tokens.token(Image());tokens.token(Image());gc.collect()
        self.assertIsNone(reference());self.assertEqual(len(tokens.items),2)
        self.assertEqual(tokens.evictions,1)
        observer=Observer('detector',Trace(),{},None)
        old_image=None
        for index in range(10):
            job=SimpleNamespace(rgb=Image(),depth=Image())
            if index==0:old_image=weakref.ref(job.rgb)
            observer.submit_before((None,job),{})
        del job
        gc.collect()
        self.assertIsNone(old_image());self.assertEqual(len(observer.jobs.items),8)

    def test_busy_submit_not_started_and_rejected_update_cannot_refresh_prediction(self):
        trace=Trace();observer=Observer('fake',trace,{},None)
        rgb,depth=object(),object();observer.images.token(rgb);observer.images.token(depth)
        job=SimpleNamespace(rgb=rgb,depth=depth)
        token=observer.submit_before((None,job),{})
        observer.submit_after((None,job),{},token,False,None)
        self.assertFalse(next(e for e in trace.events if e['kind']=='submit')['accepted'])
        self.assertFalse(any(e['kind']=='worker_start' for e in trace.events))
        source_a,source_b=object(),object();a=observer.objects.token(source_a);observer.objects.token(source_b)
        def update_scope(source,accepted,timestamp):
            observer.nav_update_after((None,),{'target_uuid':'task','track_id':4,'timestamp':timestamp},None,SimpleNamespace(accepted=accepted),None)
        observer.nav_code=update_scope.__code__
        update_scope(source_a,True,1.);prior=deepcopy(observer.last_accepted)
        update_scope(source_b,False,2.);self.assertEqual(observer.last_accepted,prior)
        projection=SimpleNamespace(valid=True,measured_timestamp_s=1.)
        observer.project_after((None,),{'target_uuid':'task','track_id':4},None,projection,None)
        event=next(e for e in trace.events if e['kind']=='navigation_project')
        self.assertEqual(event['source_frame_token'],a)
        observer.clear_after(None,None,None,None,None)
        observer.project_after((None,),{'target_uuid':'new','track_id':5},None,projection,None)
        self.assertIsNone(trace.events[-1]['source_frame_token'])

    def test_controller_lineage_reads_actual_local_target_after_latest_field_changes(self):
        observer=Observer('controller',Trace(),{},None);old,new=object(),object()
        token=observer.objects.token(old);observer.objects.token(new)
        class Controller:
            def step(self):
                target=old
                self._target=new
                return observer.lineage('command')
        observer.step_code=Controller.step.__code__
        self.assertEqual(Controller().step()['target_token'],token)

    def test_trace_overflow_is_disclosed_without_throwing_into_original(self):
        trace=Trace(max_event_bytes=10)
        trace.emit('oversized',data='x'*100)
        self.assertEqual(trace.dropped,1);self.assertEqual(trace.events,[])


class ReducerTests(unittest.TestCase):
    def test_full_three_edge_candidate_has_actual_max_callback_t0_and_all_coverage(self):
        result=reduced(fixture()[0])
        self.assertEqual(result['candidate_command_count'],1,result['commands'])
        self.assertEqual(result['commands'][0]['t0_monotonic_ns'],1550)
        self.assertEqual(result['commands'][0]['latency_ns'],2608-1550)
        self.assertEqual(result['received_rgb_count'],1)
        self.assertEqual(result['command_categories'],{'FOLLOW':1})
        self.assertEqual([result['edges'][p]['candidate_count'] for p in ('detection','state','command')],[1,1,1])
        self.assertEqual(result['physical_e2e'],'NOT_OBSERVED');self.assertFalse(result['historical_strict_changed'])

    def test_missing_edge_field_mismatch_competition_and_false_acceptance_are_unknown(self):
        mutations=[
            lambda es:next(e for e in es if e['kind']=='take' and e['phase']=='state')['metadata'].update(source_timestamp=0),
            lambda es:next(e for e in es if e['kind']=='take' and e['phase']=='detection').update(message_fields=None),
            lambda es:next(e for e in es if e['kind']=='graph')['publishers'].append({'node_name':'external','gid_hex':'external'}),
            lambda es:next(e for e in es if e['kind']=='navigation_update').update(accepted=False),
            lambda es:next(e for e in es if e['kind']=='publish' and e['phase']=='command').update(target_token=None),
            lambda es:next(e for e in es if e['kind']=='callback' and e['phase']=='command').update(same_object_as_original_take=False),
        ]
        for index,mutate in enumerate(mutations):
            events,_,_=fixture();mutate(events);result=reduced(events)
            with self.subTest(case=index):self.assertEqual(result['candidate_command_count'],0,result)

    def test_predicting_from_old_acceptance_retains_source_rejection_does_not_refresh(self):
        events,emit,_=fixture()
        emit('estimator','navigation_update',2200,accepted=False,source_frame_token='unaccepted-new-frame')
        self.assertEqual(reduced(events)['candidate_command_count'],1)
        emit('estimator','navigation_clear',2250)
        result=reduced(events);self.assertEqual(result['candidate_command_count'],0)
        self.assertIn('navigation_source_replaced_or_cleared_before_project',result['unknown_reasons'])

    def test_busy_dropped_rgb_and_nonfollow_are_not_removed_from_denominators(self):
        events,emit,_=fixture()
        emit('detector','sensor_callback',1800,sensor='rgb',image_token='busyRgb',entered_ns=1800)
        emit('detector','snapshot',1850,snapshot_token='busyJob',rgb_token='busyRgb',depth_token='depthA')
        emit('detector','submit',1860,snapshot_token='busyJob',accepted=False)
        result=reduced(events)
        self.assertEqual(result['received_rgb_count'],2);self.assertEqual(result['rgb_with_candidate_count'],1)
        next(e for e in events if e['kind']=='publish' and e['phase']=='command').update(command_valid=False,command_mode=4)
        result=reduced(events);self.assertEqual(result['candidate_command_count'],0)
        self.assertEqual(result['unknown_command_count'],1);self.assertEqual(result['command_categories'],{'FAILSAFE':1})

    def test_repeated_ticks_keep_first_input_latency_separate_from_later_information_age(self):
        events,emit,edge=fixture()
        edge('command','controller','adapter',3000,'adapter:another_command',target_token='controller:received_state',command_valid=True,command_mode=1)
        result=reduced(events)
        self.assertEqual(result['candidate_command_count'],2)
        self.assertEqual(result['rgb_opportunities'][0]['candidate_command_count'],2)
        self.assertEqual(result['rgb_opportunities'][0]['first_candidate_latency_ns'],1058)
        self.assertEqual(result['candidate_subset_statistics_ns']['max'],1458)

    def test_trace_loss_shutdown_failure_or_clock_domain_mismatch_invalidates_complete_chain(self):
        for mutation in [lambda es:next(e for e in es if e['kind']=='observer_final').update(trace_dropped=1),
                         lambda es:next(e for e in es if e['kind']=='executor_shutdown').update(returned=False),
                         lambda es:next(e for e in es if e['kind']=='process_start').update(boot_id='other-boot')]:
            events,_,_=fixture();mutation(events);self.assertEqual(reduced(events)['candidate_command_count'],0)


class CliTests(unittest.TestCase):
    def test_role_hook_install_failure_closes_observer_and_trace(self):
        cleanup=[]
        class RecordingTrace(Trace):
            def __init__(self,*args):super().__init__()
            def close(self):cleanup.append('trace_closed')
        class BrokenObserver:
            def __init__(self,*args):pass
            def install_ros(self,*args):raise ValueError('injected hook install failure')
            def close(self):cleanup.append('observer_closed')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();module_file=root/'original.py';module_file.write_text('# original placeholder\n')
            module=SimpleNamespace(__file__=str(module_file))
            probe=SimpleNamespace(runtime_binding=lambda:{'gate_passed':True})
            config={'source_root':str(root),'probe':{'path':'unused'},'edges':{}}
            with patch('observer.Observer',BrokenObserver),patch('observer.Trace',RecordingTrace), \
                 patch('observer.load_probe',return_value=probe),patch.object(bench.importlib,'import_module',return_value=module), \
                 patch.object(bench.os,'chdir'),patch.object(bench,'start_event'):
                with self.assertRaisesRegex(ValueError,'hook install'):bench.role_worker(config,'controller',root)
        self.assertEqual(cleanup,['observer_closed','trace_closed'])

    def test_master_monitor_constructor_failure_closes_context_and_trace(self):
        cleanup=[]
        def broken_node(*args):raise ValueError('injected monitor construction failure')
        class RecordingTrace(Trace):
            def __init__(self,*args):super().__init__()
            def close(self):cleanup.append('trace_closed')
        rclpy=SimpleNamespace(init=lambda **kw:None,ok=lambda:True,shutdown=lambda:cleanup.append('context_shutdown'))
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,{'rclpy':rclpy,'rclpy.node':SimpleNamespace(Node=broken_node)}), \
             patch('observer.Trace',RecordingTrace),patch.object(bench,'start_event'),patch.dict(bench.os.environ,{}),redirect_stdout(io.StringIO()):
            root=Path(directory)
            config={'source_root':str(root/'frozen'),'original_plan':{'path':str(root/'plan')},
                    'recording_terminal':{'path':str(root/'terminal')},'parameters':{},'bag_files':[],'_checked':[]}
            args=SimpleNamespace(manifest='unused',domain_id=211,output=str(root/'bench'),timeout_s=30.,drain_s=0.,cleanup_s=1.)
            with patch.object(bench,'preflight',return_value=config):self.assertEqual(bench.native(args),2)
            report=json.loads((root/'bench/summary.json').read_bytes())
            self.assertFalse(report['native_complete']);self.assertIn('injected monitor',report['error'])
        self.assertEqual(cleanup,['context_shutdown','trace_closed'])

    def test_replay_early_storage_failure_closes_reader_scratch_node_and_context(self):
        cleanup=[]
        destroy_raises=False
        @contextmanager
        def reader_context(*args):
            try:yield object(),{'storage_identifier':'unexpected'}
            finally:cleanup.append('reader_closed')
        class Loader:
            def exec_module(self,module):module.open_bag_reader=reader_context
        class Node:
            def __init__(self,*args):pass
            def destroy_node(self):
                cleanup.append('node_destroyed')
                if destroy_raises:raise ValueError('injected node destroy failure')
        qos=SimpleNamespace(QoSProfile=object,ReliabilityPolicy=object,DurabilityPolicy=object)
        rclpy=SimpleNamespace(init=lambda **kw:None,ok=lambda:True,shutdown=lambda:cleanup.append('context_shutdown'))
        modules={'rclpy':rclpy,'rclpy.node':SimpleNamespace(Node=Node),'rclpy.qos':qos,'rosbag2_py':SimpleNamespace(),
                 'rosidl_runtime_py':SimpleNamespace(),'rosidl_runtime_py.utilities':SimpleNamespace(get_message=lambda x:None)}
        spec=SimpleNamespace(loader=Loader())
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,modules),patch.object(bench,'start_event'), \
             patch('observer.Trace',side_effect=lambda *args:Trace()), \
             patch.object(bench.importlib.util,'spec_from_file_location',return_value=spec), \
             patch.object(bench.importlib.util,'module_from_spec',return_value=SimpleNamespace()):
            prior=tempfile.tempdir
            config={'source_root':directory,'scratch_root':directory,'bag_uri':directory,'storage_id':'sqlite3'}
            with self.assertRaisesRegex(ValueError,'storage identifier'):bench.replay_worker(config,Path(directory))
            self.assertEqual(list(Path(directory).iterdir()),[])
            self.assertIs(tempfile.tempdir,prior)
            self.assertEqual(cleanup,['reader_closed','node_destroyed','context_shutdown'])
            cleanup.clear();destroy_raises=True
            with self.assertRaisesRegex(ValueError,'node destroy'):bench.replay_worker(config,Path(directory))
            self.assertEqual(list(Path(directory).iterdir()),[])
            self.assertIs(tempfile.tempdir,prior)
        self.assertEqual(cleanup,['reader_closed','node_destroyed','context_shutdown'])

    def test_default_describe_opens_no_manifest_bag_or_model(self):
        with patch.object(bench,'read_json',side_effect=AssertionError('input opened')),patch.object(bench,'hash_file',side_effect=AssertionError('file read')):
            output=io.StringIO()
            with redirect_stdout(output):self.assertEqual(bench.main([]),0)
        self.assertEqual(json.loads(output.getvalue())['status'],'DESCRIBE_ONLY_NO_INPUTS_OPENED')

    def test_native_is_refused_on_windows_before_reading_inputs(self):
        if sys.platform!='win32':self.skipTest('Windows guard fixture')
        with patch.object(bench,'read_json',side_effect=AssertionError('input opened')):
            with self.assertRaisesRegex(ValueError,'original Linux'):bench.main(['native','--manifest','NO_FILE','--output','NO_OUTPUT','--domain-id','211'])


if __name__=='__main__':unittest.main()
