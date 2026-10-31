"""Small injected evidence derived from the actual512 receipt; no ML/ROS load."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import development_resource_guard as g


def local_path(name):
    return Path('D:/'+name.removeprefix('/mnt/d/')) if os.name == 'nt' and name.startswith('/mnt/d/') else Path(name)


def actual_json(name):
    return json.loads(local_path(name).read_text(encoding='utf-8'))


class MemoryEvidence:
    def __init__(self, documents, row_sets):
        self.documents, self.row_sets, self.bindings = documents, row_sets, {}
    def file(self, binding, *, limit=g.generic.MAX_SMALL):
        self.bindings[binding['path']] = dict(binding, limit=limit)
        return Path(binding['path'])
    def json(self, binding):
        self.file(binding)
        return deepcopy(self.documents[binding['path'].replace('\\','/')])
    def rows(self, binding):
        self.file(binding)
        return deepcopy(self.row_sets[binding['path'].replace('\\','/')])


def fixture():
    # All registration/resource/quality fields come from the immutable real
    # prospective receipt. Only raw timing opportunities/statistics are synthetic.
    repo = '/mnt/d/基于yolo和卡尔曼滤波'
    receipt = actual_json(repo+'/'+g.RECEIPT_PATH)
    root = '/root/uav_tracking_fullplan_fixture512'
    documents, row_sets = {}, {}
    documents[root+'/'+g.RECEIPT_PATH] = receipt
    quality = receipt['quality']
    documents[quality['summary_path']] = actual_json(quality['summary_path'])
    timing = receipt['timing']
    documents[timing['raw_input_export']['path']] = actual_json(timing['raw_input_export']['path'])
    for config in timing['configurations']:
        size, evidence = config['inference_image_size'], config['evidence']
        for name in ('started.json','inputs.json','environment.json','summary.json'):
            documents[evidence[name]['path']] = actual_json(evidence[name]['path'])
        started = documents[evidence['started.json']['path']]
        frames = documents[evidence['inputs.json']['path']]['frames']
        rows=[]
        for number in range(1008):
            repeat,index=divmod(number,12);frame=frames[index]
            rows.append({'repeat':repeat,'image_index':index,'pair_id':f'repeat{repeat:03d}_image{index:06d}',
                'file':frame['file'],'png_sha256':frame['sha256'],'condition_id':f'pt_cpu_t4_img{size}',
                'imgsz':size,'threads':4,'effective_threads':4,'torch_threads_after':4,
                'actual_model_input_shape':[1,3,480 if size == 640 else 384,size], 'decoded_input_shape':frame['shape'],
                'actual_backend_format':'pt','actual_backend_device':'cpu','actual_backend_fp16':False,
                'initialized_thread_ident':started['main_thread_ident'], 'predict_thread_ident':started['main_thread_ident']+1,
                'outside_timer_pool_selection_wall_s':None,
                'predict_wall_s':(2.2 if number == 1007 else .5+number/1008) if size == 512 else 1.+number/1008})
        row_sets[evidence['samples.jsonl']['path']]=rows
        stats=g.wall_stats([x['predict_wall_s'] for x in rows])
        config['predict_wall_s']=stats
        documents[evidence['summary.json']['path']]['conditions'][f'pt_cpu_t4_img{size}']['predict_wall_s']=stats
    registration={'revision':g.REVISION,'receipt':{'path':g.RECEIPT_PATH,'sha256':g.RECEIPT_SHA},'scope':g.SCOPE}
    adaptation={'model':g.MODEL,'model_sha256':g.MODEL_SHA,'target_class':'car'}
    protocol={'car_input_scale_registration':registration,'resources':{'car':{'model':g.MODEL,
        'inference_image_size':512,'inference_threads':4,'navigation_correlated_two_face_bound':True}},
        'model_adaptation':adaptation}
    review={'files':{g.RECEIPT_PATH:g.RECEIPT_SHA,g.MODEL:g.MODEL_SHA,g.PROTOCOL_PATH:'a'*64}}
    runner=SimpleNamespace(CAR_INPUT_SCALE_REGISTRATION_TRAIN04_512=registration,
        CORRELATED_BOUND_FIELD='navigation_correlated_two_face_bound',CAR_MODEL_ADAPTATION_TRAIN04=adaptation)
    return root,review,runner,protocol,MemoryEvidence(documents,row_sets)


def verify(items):
    root,review,runner,protocol,reader=items
    with patch.object(g,'sha',return_value='a'*64):
        return g.verify_512_resource(root,review,runner,protocol,reader=reader)


class ResourceEvidenceTests(unittest.TestCase):
    def test_default_reader_rejects_changed_or_unbounded_actual_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'measurement.json'
            path.write_text('{"measurement": 1}',encoding='utf-8')
            reader=g.FileEvidence();binding={'path':str(path),'sha256':g.sha(path)}
            self.assertEqual(reader.json(binding),{'measurement':1})
            self.assertRaisesRegex(ValueError,'bytes changed',reader.file,binding,limit=1)
            path.write_text('{"measurement": 2}',encoding='utf-8')
            self.assertRaisesRegex(ValueError,'bytes changed',reader.json,binding)

    def test_actual_receipt_fields_and_synthetic_measurement_denominator_are_bound(self):
        result=verify(fixture())
        self.assertEqual(result['inference_image_size'],512)
        self.assertFalse(result['closed_loop_validated'])
        self.assertFalse(result['formal_seed_use_authorized'])
        self.assertEqual([x['predict_wall_s']['denominator'] for x in result['timing']],[1008,1008])
        self.assertEqual(result['quality']['opportunities'],260)
        self.assertTrue(result['evidence_bindings'])

    def test_legacy640_wrong_model_receipt_or_boolean_resources_cannot_substitute(self):
        for mutate in (
            lambda p:p.update(car_input_scale_registration={'revision':'car_train20_04_m640_cpu4_v1'}),
            lambda p:p['resources']['car'].update(inference_image_size=640),
            lambda p:p['resources']['car'].update(inference_threads=True),
            lambda p:p['resources']['car'].update(model='wrong.pt'),
            lambda p:p['car_input_scale_registration']['receipt'].update(sha256='b'*64)):
            items=fixture();mutate(items[3]);self.assertRaises(ValueError,verify,items)
        items=fixture();items[1]['files'][g.MODEL]='b'*64
        self.assertRaisesRegex(ValueError,'review must bind',verify,items)
        items=fixture();items[1]['files'][g.PROTOCOL_PATH]='b'*64
        self.assertRaisesRegex(ValueError,'review must bind',verify,items)

    def test_new_receipt_cannot_claim_flight_success_or_erase_unknown_quality(self):
        for key,value in (('closed_loop_validated',True),('complete_development_readiness',True),('formal_seeds_used',[1000])):
            items=fixture();items[4].documents[items[0]+'/'+g.RECEIPT_PATH][key]=value
            self.assertRaises(ValueError,verify,items)
        items=fixture();receipt=items[4].documents[items[0]+'/'+g.RECEIPT_PATH]
        summary=items[4].documents[receipt['quality']['summary_path']]
        summary['candidates']['train20_04_best_m512']['consumed236']['unknown_pairs']=1
        self.assertRaisesRegex(ValueError,'unknown/incomplete',verify,items)

    def test_missing_duplicate_unknown_shape_threads_or_foreground_rows_are_rejected(self):
        for name in ('missing','duplicate','unknown','shape','threads','foreground','negative_wall'):
            items=fixture();reader=items[4]
            path=next(k for k in reader.row_sets if 'worker512' in k);rows=reader.row_sets[path]
            if name=='missing':rows.pop()
            if name=='duplicate':rows[1]=deepcopy(rows[0])
            if name=='unknown':rows[1]['predict_wall_s']=None
            if name=='shape':rows[1]['actual_model_input_shape']=[1,3,480,640]
            if name=='threads':rows[1]['effective_threads']=2
            if name=='foreground':rows[1]['predict_thread_ident']=rows[1]['initialized_thread_ident']
            if name=='negative_wall':rows[1]['predict_wall_s']=-1
            with self.subTest(name=name):self.assertRaises(ValueError,verify,items)

    def test_summary_percentiles_and_retained_adverse_maximum_cannot_be_rewritten(self):
        items=fixture();receipt=items[4].documents[items[0]+'/'+g.RECEIPT_PATH]
        config=receipt['timing']['configurations'][1]
        config['predict_wall_s']['p95']-=.1
        self.assertRaisesRegex(ValueError,'statistics changed',verify,items)
        items=fixture();items[4].documents[items[0]+'/'+g.RECEIPT_PATH]['timing']['maximum_latency_improved']=True
        self.assertRaisesRegex(ValueError,'maximum-latency',verify,items)

    def test_input_export_and_worker_artifact_provenance_are_not_interchangeable(self):
        items=fixture();receipt=items[4].documents[items[0]+'/'+g.RECEIPT_PATH]
        receipt['timing']['configurations'][1]['evidence']['samples.jsonl']['path']='/foreign/samples.jsonl'
        self.assertRaisesRegex(ValueError,'process provenance',verify,items)
        items=fixture();receipt=items[4].documents[items[0]+'/'+g.RECEIPT_PATH]
        export=items[4].documents[receipt['timing']['raw_input_export']['path']]
        export['truth_read']=True
        self.assertRaisesRegex(ValueError,'without truth',verify,items)

    def test_revalidation_checks_every_original_binding_without_reparsing_samples(self):
        resource=verify(fixture())
        reader=MemoryEvidence({},{});reader.json=Mock(side_effect=AssertionError('No repeated parsing'))
        reader.rows=Mock(side_effect=AssertionError('No repeated parsing'))
        with patch.object(g,'FileEvidence',return_value=reader):
            self.assertIs(g.revalidate_resource_binding(resource),resource)
        self.assertEqual(set(reader.bindings),{x['path'] for x in resource['evidence_bindings']})
        resource['formal_seed_use_authorized']=True
        self.assertRaises(ValueError,g.revalidate_resource_binding,resource)


class RuntimeCompositionTests(unittest.TestCase):
    def run_contracts(self,*,named=True,failure=None):
        review={'source_root':'/source','classified_source_hashes':{'a':'a'*64,'config/px4_magnetic_runtime.json':g.generic.MAGNETIC_SHA}}
        protocol={'car_input_scale_registration':{'revision':g.REVISION if named else 'historical640'}}
        runner=SimpleNamespace(validate_protocol=Mock(),source_hashes=lambda root:{'a':'a'*64},
            validate_model_adaptation_binding=Mock(),verify_external_runtime=Mock(return_value={'source_root':g.generic.PX4_ROOT}),
            simulation_processes=Mock(return_value=[]))
        guard=SimpleNamespace(require_bridge_runtime=Mock(return_value={'bridge':'original'}),
            require_safety_ast=Mock(return_value={'safety':'original'}),require_resource_choice=Mock(return_value={'legacy640':True}))
        if failure=='source':review['classified_source_hashes']['unexpected']='b'*64
        if failure=='idle':runner.simulation_processes.return_value=[{'active':'gazebo'}]
        if failure=='bridge':guard.require_bridge_runtime.side_effect=ValueError('bridge failed')
        if failure=='safety':guard.require_safety_ast.side_effect=ValueError('safety failed')
        with patch.object(g.generic,'dependencies',return_value={'humble33_review_guard':guard}), \
             patch.object(g.generic,'runner_at',return_value=runner),patch.object(g.generic,'read_small',return_value=protocol), \
             patch.object(g,'verify_512_resource',return_value={'named512':True}) as resource:
            if failure:
                self.assertRaises(ValueError,g.runtime_contracts,review,'/newroot')
                resource.assert_not_called()
            else:
                result=g.runtime_contracts(review,'/newroot')
                self.assertEqual(result['resource'],{'named512':True} if named else {'legacy640':True})
                guard.require_bridge_runtime.assert_called_once_with(review,'/newroot')
                guard.require_safety_ast.assert_called_once_with('/newroot')
                runner.validate_protocol.assert_called_once_with(protocol)
                runner.validate_model_adaptation_binding.assert_called_once()
                runner.verify_external_runtime.assert_called_once()
                self.assertEqual(resource.call_count,1 if named else 0)
                self.assertEqual(guard.require_resource_choice.call_count,0 if named else 1)

    def test_named512_composes_all_original_nonresource_contracts(self):self.run_contracts()
    def test_legacy640_still_calls_unchanged_legacy_guard(self):self.run_contracts(named=False)
    def test_any_source_bridge_safety_or_idle_failure_blocks_named_resource(self):
        for failure in ('source','idle','bridge','safety'):
            with self.subTest(failure=failure):self.run_contracts(failure=failure)


if __name__ == '__main__':
    unittest.main()
