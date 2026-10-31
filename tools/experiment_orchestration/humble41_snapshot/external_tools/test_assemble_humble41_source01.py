"""Synthetic source41 assembly controls; no actual source, WSL or payloads."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import assemble_humble41_source01 as m


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix='source41_fake_') as temporary:
        top = Path(temporary).resolve(); root = top/'source'; external = top/'external'
        root.mkdir(); external.mkdir()
        def lin(path): return '/mnt/d/FIXTURE/'+Path(path).resolve().relative_to(top).as_posix()
        def win(path):
            assert path.startswith('/mnt/d/FIXTURE/')
            return top/path.removeprefix('/mnt/d/FIXTURE/')
        def save(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
            return {'path':lin(path), 'sha256':m.sha(path)}
        with patch.object(m, 'EXTERNAL', external), patch.object(m, 'lin', side_effect=lin), patch.object(m, 'win', side_effect=win):
            ignored = [m.MAGNETIC]+[f'models/resource{i}.bin' for i in range(8)]
            tracked = ['planning/reliability-v4-preregistration.json', 'scripts/observe_runtime_health.py', 'tests/test_runtime_health_live_output.py']
            for name in tracked+ignored:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{}' if name.endswith('.json') else name)
            files = {name:m.sha(root/name) for name in tracked+ignored}
            previous = {name:digest for name,digest in files.items() if name != tracked[2]}
            previous[tracked[1]] = '1'*64
            old_files = {}
            for index in range(13):
                path = root/f'results/frozen_fullplan_v4_humble32/slots/original{index}.json'
                save(path, {'status':'FAIL' if index == 0 else 'PASS', 'record_sha256':str(index)})
                old_files[lin(path)] = {'sha256':m.sha(path), 'bytes':path.stat().st_size}
            inherited_path = external/'old_capsule.json'
            inherited = {'all_inputs_closed':True, 'payload_reread':False, 'readiness_claimed':False,
                'predecessor38_core12':{'status_counts':{'PASS':11,'FAIL':1}},
                'predecessor39_singleprobe':{'status':'FAIL','fixed10hz_identity':{'unknown':210}},
                'files':old_files, 'boundaries':{'original32_core':{'closed':True,'receipt':next(iter(old_files))}}}
            inherited_binding = save(inherited_path, inherited)
            prior_path = external/'reviewed_freeze_review_humble40_01.json'
            prior = {'frozen_root':m.BASE_ROOT, 'source_root':lin(root), 'source_commit':m.BASE_COMMIT,
                'files':previous, 'classified_source_hashes':{name:previous[name] for name in tracked[:2]},
                'closed_evidence':inherited_binding, 'toolchain_canonical_sha256':m.canonical({}),
                'source_overrides':{m.MAGNETIC:{'sha256':files[m.MAGNETIC]}},
                'assembly_provenance':{'inherited_ignored_resources':ignored}, 'additional_import_modules':[]}
            save(prior_path, prior)
            results = root/'results/frozen_fullplan_v4_humble40'
            manifest_path = results/'freeze_validation/source_freeze_manifest.json'
            save(manifest_path, {'files':previous,'source_commit':m.BASE_COMMIT,'freeze_source_sha256':m.canonical(previous)})
            source = {'manifest_sha256':m.sha(manifest_path),'freeze_source_sha256':m.canonical(previous)}
            build = {}
            summary_path = results/'freeze_validation/build_validation_summary.json'
            save(summary_path, {'status':'PASS','returncode':0,'source_unchanged':True,'four_packages_built':True,
                'module_ament_isolation':True,'source_binding_before':source,'source_binding_after':source})
            build['summary'] = {'path':m.BASE_ROOT+'/results/freeze_validation/build_validation_summary.json','sha256':m.sha(summary_path)}
            for action in ('build','validate'):
                path = external/f'reviewed_freeze_actions_v4_humble40/{action}/action.terminal.json'
                build[action+'_terminal'] = save(path, {'scope':'BOUNDED_SINGLE_ACTION_PROCESS_GROUP_ONLY_NOT_FLIGHT_ACCEPTANCE',
                    'status':'PASS','finished_utc':'synthetic','direct_child_returncode':0,
                    'binding_before':{'source':source},'binding_after':{'source':source},
                    'cleanup':{'actual_proc_group_empty':True,'direct_child_reaped':True,'residual_processes':[]}})
            entry = {'common_probe40_binding':{'source':source,'source_review':{'path':lin(prior_path),'sha256':m.sha(prior_path)},'build_metadata':build}}
            matrix = results/m.CORE_RELATIVE
            ids = [f'{cls}_{group}_seed004' for cls in ('person','car') for group in
                ('stage1_velocity','stage1_position','stage2_crossing','stage3_midpoint','stage3_active','stage3_multi_active')]
            plan = {'mode':'PROBE','source_hashes':prior['classified_source_hashes'],'protocol_sha256':previous[tracked[0]],
                    'trials':[{'id':slot,'flight_command':['original',slot]} for slot in ids]}
            plan['plan_sha256'] = m.canonical(plan); save(matrix/'plan.json', plan)
            statuses, attempts, audited = {}, [], []
            records = []
            for index, slot in enumerate(ids):
                if index >= 4:
                    statuses[slot] = {'status':'PENDING','record_sha256':None}; continue
                expected = 'PASS' if index < 3 else 'INFRASTRUCTURE_ERROR'
                command = {'command':['original',slot],'returncode':0 if index < 3 else -2}
                if index == 3: command['error'] = 'RuntimeError:Latest complete observer sample is stale or future: 25.23778100799973'
                record = {'id':slot,'status':expected,'engineering_result':'PASS' if index < 3 else 'FAIL',
                    'execution_status':'COMPLETED','infrastructure_stop':index == 3,'flight_exit_code':command['returncode'],
                    'commands':[command],'evaluations':[],'plan_sha256':plan['plan_sha256'],'started_utc':'synthetic'}
                record['record_sha256'] = m.canonical(record)
                path = matrix/'slots'/(slot+'.json'); bound = save(path, record)
                save(matrix/'slots'/(slot+'.started.json'), {'id':slot,'plan_sha256':plan['plan_sha256'],
                    'flight_command':['original',slot],'started_utc':'synthetic'})
                save(matrix/'observed_driver01'/f'{index+1:02d}_{slot}.started.json', {'slot':slot})
                attempt = {'slot':slot,'record':{'record_binding':{**bound,'record_sha256':record['record_sha256']}},'audit':{} if index < 3 else None}
                if index == 3: attempt['runner_result'] = {'status_counts':m.EXPECTED_COUNTS,'terminal_count':4,'pending_ids':ids[4:]}
                save(matrix/'observed_driver01'/f'{index+1:02d}_{slot}.attempt_terminal.json', attempt)
                attempts.append(attempt)
                if index < 3: audited.append({'slot':slot})
                statuses[slot] = {'status':expected,'record_sha256':record['record_sha256']}
                records.append(record)
            terminal = {'scope':'HUMBLE40_CORE12_NORMAL_RUNNER_DEVELOPMENT_ONLY','returncode':2,
                'status':'STOPPED_ORIGINAL_ATTEMPTS_RETAINED','error':'ValueError:Incomplete/infrastructure attempt requires diagnosis: person_stage3_midpoint_seed004',
                'finished_utc':'synthetic','final_errors':['observer:ValueError:Rolling observer aggregate is incomplete or unhealthy'],
                'cleanup':{'residual_processes':[]},'entry_binding_before':entry,'entry_binding_after':deepcopy(entry),
                'observer':None,'planned_count':12,'attempt_count':4,'terminal_count':3,'status_counts':m.EXPECTED_COUNTS,
                'slot_read_error':None,'attempts':attempts,'slots':audited,'actual_slot_statuses':statuses,
                **{key:False for key in ('formal_seed_use_authorized','readiness_claimed','automatic_retry','automatic_next_action')}}
            terminal_path = matrix/'observed_driver01/execution_terminal.json'; save(terminal_path,terminal)
            observer_root = matrix/'observed_driver01/observer_driver'
            session_path = observer_root/'session_001/execution_terminal.json'
            session = {'observer_exit_code':0,'healthy_cleanup':False,'driver_exception':True}; session_bound = save(session_path,session)
            aggregate = {'healthy_cleanup':False,'driver_exception':True,'max_sample_age_wall_s':10.,'sessions':[{'terminal':session,'terminal_binding':session_bound}]}
            save(observer_root/'execution_terminal.json',aggregate)
            fault_path = external/m.STOPPED_REVIEW_NAME
            fault = {'status':'INDEPENDENT_SOURCE40_CORE_STOPPED_FAULT_RECORD_CLOSURE_RETAINED','driver':{'sha256':m.sha(terminal_path)},
                'counts':{'status_counts':m.EXPECTED_COUNTS,'planned':12,'original_driver_attempt_count':4,'original_driver_terminal_count':3,'normal_runner_terminal_count':4},
                'unattempted8':ids[4:],**{key:False for key in ('original04_regraded','payload_read','formal_seed_use_authorized','readiness_claimed')}}
            save(fault_path,fault)
            generic = SimpleNamespace(validate_review=Mock(),tools_manifest=lambda:{},FINAL_STATUS='SYNTHETIC_FINAL',
                delta=lambda old,new:{'changed':sorted(k for k in old.keys()&new.keys() if old[k]!=new[k]),'added':sorted(new.keys()-old.keys()),'removed':sorted(old.keys()-new.keys())})
            runner = SimpleNamespace(source_hashes=lambda _:{name:files[name] for name in tracked[:2]},PROTOCOL_PATH=tracked[0],
                validate_protocol=Mock(),SIMULATION_PACING_V2={'revision':'synthetic'},simulation_pacing_summary=lambda _: {'revision':'synthetic'},exclusive_navigation_summary=lambda _: {'person':False,'car':True})
            args = SimpleNamespace(source_root=root,baseline_review=prior_path,baseline_review_sha256=m.sha(prior_path),
                commit='a'*40,core_terminal_sha256=m.sha(terminal_path),stopped_core_review_sha256=m.sha(fault_path),
                reviewed_tools_sha256=m.canonical({}),additional_import_module=[])
            def git(command):
                if 'status' in command:return b''
                if 'rev-parse' in command:return (args.commit+'\n').encode()
                if 'ls-files' in command:return b'\0'.join(n.encode() for n in tracked)+b'\0'
                if 'diff' in command:return ('M\t'+tracked[1]+'\nA\t'+tracked[2]+'\n').encode()
                if 'show' in command:return (root/command[-1].split(':',1)[1]).read_bytes()
                raise AssertionError(command)
            yield SimpleNamespace(**locals())


def capsule(f):
    return m.closed40_capsule(f.root,f.prior,f.prior_path,f.manifest_path,m.sha(f.terminal_path),m.sha(f.fault_path))


@contextmanager
def mocks(f):
    with patch.object(m,'tool_manifest',return_value={}), \
            patch.object(m.importlib,'import_module',side_effect=lambda name: f.generic if name == 'reviewed_freeze_build' else f.runner), \
            patch.object(m.subprocess,'check_output',side_effect=f.git), patch.object(m.subprocess,'run'):
        yield


class Assembly41Tests(unittest.TestCase):
    def test_stopped_runtime_keeps_four_persisted_three_audited_and_eight_pending(self):
        with fixture() as f:
            result = capsule(f)
            self.assertEqual(result['predecessor40_core_stopped']['status_counts'],m.EXPECTED_COUNTS)
            self.assertEqual(result['predecessor40_core_stopped']['driver_audited_terminal_count'],3)
            self.assertEqual(result['predecessor40_core_stopped']['persisted_terminal_count'],4)
            self.assertFalse(result['predecessor40_core_stopped']['runtime_acceptance'])
            self.assertTrue(result['boundaries']['predecessor']['receipt'].endswith('/validate/action.terminal.json'))
            self.assertFalse(result['readiness_claimed'])
            self.assertEqual(len([n for n in result['files'] if 'frozen_fullplan_v4_humble32/' in n]),13)

    def test_stopped_driver_or_independent_review_wrong_sha_cannot_be_accepted(self):
        with fixture() as f:
            self.assertRaisesRegex(ValueError,'driver bytes changed',m.closed40_capsule,f.root,f.prior,f.prior_path,f.manifest_path,'0'*64,m.sha(f.fault_path))
            self.assertRaisesRegex(ValueError,'fault review changed',m.closed40_capsule,f.root,f.prior,f.prior_path,f.manifest_path,m.sha(f.terminal_path),'0'*64)

    def test_rebound_driver_cannot_claim_full_completion_pass_or_healthy_observer(self):
        for field,value in [('returncode',0),('status_counts',{'PASS':12}),('attempt_count',12),('terminal_count',4),('observer',{'healthy':True}),('final_errors',[])]:
            with self.subTest(field=field),fixture() as f:
                f.terminal[field] = value; f.save(f.terminal_path,f.terminal)
                self.assertRaises(ValueError,capsule,f)

    def test_retained_fourth_slot_cannot_be_regraded_or_modified(self):
        with fixture() as f:
            path=f.matrix/'slots/person_stage3_midpoint_seed004.json'; value=m.small(path)
            value['status']='PASS'; f.save(path,value)
            self.assertRaises(ValueError,capsule,f)

    def test_eight_pending_cells_cannot_acquire_attempt_artifacts(self):
        with fixture() as f:
            f.save(f.matrix/'slots/person_stage3_active_seed004.started.json',{'attempted':True})
            self.assertRaisesRegex(ValueError,'pending cell was attempted',capsule,f)

    def test_unhealthy_observer_cannot_be_changed_to_healthy(self):
        with fixture() as f:
            path=f.matrix/'observed_driver01/observer_driver/execution_terminal.json'; value=m.small(path)
            value['healthy_cleanup']=True; f.save(path,value)
            self.assertRaisesRegex(ValueError,'unhealthy observer',capsule,f)

    def test_healthy_build_is_separate_and_missing_build_closure_stops_assembly(self):
        with fixture() as f:
            path=f.external/'reviewed_freeze_actions_v4_humble40/validate/action.terminal.json'; value=m.small(path)
            value['direct_child_returncode']=2; f.save(path,value)
            self.assertRaisesRegex(ValueError,'build action',capsule,f)

    def test_original32_and_inherited_capsule_bytes_are_not_rewritten(self):
        with fixture() as f:
            before={p:p.read_bytes() for p in f.top.rglob('*.json')}
            capsule(f)
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            path=f.win(next(iter(f.inherited['files']))); f.save(path,{'changed':True})
            self.assertRaisesRegex(ValueError,'Original32',capsule,f)

    def test_actual_exact_observer_delta_produces_pending_only_without_freeze_or_flight(self):
        with fixture() as f,mocks(f):
            result=m.assemble_pending(f.args)
            review=m.small(Path(result['review'])); closed=m.small(Path(result['closed_capsule']))
            self.assertEqual(review['allowed_delta'],m.EXPECTED_DELTA)
            self.assertEqual(review['source_commit'],f.args.commit)
            self.assertEqual(review['baseline']['source_commit'],m.BASE_COMMIT)
            self.assertEqual(review['frozen_root'],m.NEW_ROOT)
            self.assertEqual(closed['predecessor40_core_stopped']['status_counts'],m.EXPECTED_COUNTS)
            self.assertFalse(review['flight_actions_authorized'])
            self.assertFalse(result['final_review_created'])
            self.assertFalse((f.root/'results/frozen_fullplan_v4_humble41').exists())
            self.assertRaises(ValueError,m.assemble_pending,f.args)

    def test_other_source_changes_cannot_enter_the_two_file_candidate(self):
        with fixture() as f,mocks(f):
            (f.root/'models/resource0.bin').write_text('changed algorithm/model')
            self.assertRaisesRegex(ValueError,'Only the observer',m.assemble_pending,f.args)

    def test_nonbaseline40_commit_and_dirty_tree_are_rejected(self):
        with fixture() as f,mocks(f):
            f.prior['source_commit']='b'*40;f.save(f.prior_path,f.prior);f.args.baseline_review_sha256=m.sha(f.prior_path)
            self.assertRaisesRegex(ValueError,'Actual40 source/root',m.assemble_pending,f.args)
        with fixture() as f,mocks(f),patch.object(m.subprocess,'check_output',side_effect=lambda cmd:b' M dirty' if 'status' in cmd else f.git(cmd)):
            self.assertRaisesRegex(ValueError,'clean committed',m.assemble_pending,f.args)

    def test_describe_and_missing_arguments_do_not_touch_source_or_publish(self):
        with patch.object(m,'tool_manifest',return_value={}),patch.object(m,'assemble_pending') as assemble,redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(['describe']),0)
        assemble.assert_not_called()
        with patch.object(m,'small') as read,patch.object(m,'write_pending') as write,redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(['assemble-pending']),2)
        read.assert_not_called();write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
