"""One explicit external-driver repair and read-only native diagnostic.

Original safety01 stays INFRASTRUCTURE_ERROR. No flight or original result rewrite.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

RUNTIME = Path('/root/uav_tracking_fullplan_v4_humble54')
AUDIT = Path('/root/uav_tracking_snapshot_audit54_tools01')
PROJECT = Path('/mnt/d/基于yolo和卡尔曼滤波')
OUTPUT = Path('/mnt/d/WSL/UAVHumble22-validation/safety54_symlink_recovery02')
CORE = RUNTIME/'results/reliability_v4_humble54_core12_probe01_matrix/plan.json'
OLD_AUDIT = RUNTIME/'results/reliability_v4_humble54_safety01_audit'
CONTRACT = RUNTIME/'results/snapshot_audit54_contract02.json'
OLD_DRIVER_SHA = '6d6d1b56d14866355c7d423d3eaaed420860f20190d59acdfa20b853b9f3073b'
NEW_DRIVER_SHA = '82c5ee395e81db0a15339149d8775cf3a8fe1c9fdce524e9e54cf2bc3d287e73'
GUARD_SHA = 'e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e'

def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def now():
    return datetime.now(timezone.utc).isoformat()

def main():
    assert not OUTPUT.exists() and not CONTRACT.exists()
    plan_before = pin(CORE)
    old_terminal = pin(OLD_AUDIT/'execution_terminal.json')
    old_contract = pin(RUNTIME/'results/snapshot_audit54_contract01.json')
    driver = AUDIT/'tools/run_reliability_v4_safety.py'
    replacement = PROJECT/'tools/run_reliability_v4_safety.py'
    assert pin(driver)['sha256'] == OLD_DRIVER_SHA and pin(replacement)['sha256'] == NEW_DRIVER_SHA
    guard_path = AUDIT/'tools/reliability_v4_guard.py'
    assert pin(guard_path)['sha256'] == GUARD_SHA
    OUTPUT.mkdir()
    before = {name:pin(AUDIT/name) for name in ('tools/reliability_v4_guard.py',
        'tools/reliability_v4_snapshot_audit.py','tools/reliability_v4_register.py','tools/__init__.py')}
    receipt = {'schema_version':1,'kind':'ACTUAL_NATIVE_SAFETY_SYMLINK_COMMAND_CONTRACT_REPAIR',
        'started_utc':now(),'status':'RUNNING','core_plan':plan_before,'original_failed_terminal':old_terminal,
        'original_contract':old_contract,'fixed_tool_root':str(AUDIT),'unchanged_tool_pins_before':before,
        'formal_admission_created':False,'flights_started':0,'original_result_rewritten':False}
    try:
        (OUTPUT/'original_driver.py').write_bytes(driver.read_bytes())
        (OUTPUT/'original_contract01.json').write_bytes(Path(old_contract['path']).read_bytes())
        driver.write_bytes(replacement.read_bytes())
        assert pin(driver)['sha256'] == NEW_DRIVER_SHA
        receipt['driver_before'] = pin(OUTPUT/'original_driver.py')
        receipt['driver_after'] = pin(driver)
        receipt.update(scope='ACTUAL_FIXED_TOOL_NATIVE_CONTRACT_AND_SNAPSHOT_AUDIT_ONLY',
            self=pin(Path(__file__)),plan=plan_before,exit_code=1,contract_creation_attempted=True,
            mandatory_helper_hash_traversals_skipped=False,
            helper_original_source_and_model_hashing_allowed_and_preserved=True)
        for flag in ('safety_registration_created','formal_admission_or_plan_created','formal_execution_authorized',
                     'formal_dual_root_integration_validated','historical_flight_imports_proved','runtime_root_edited',
                     'original_snapshots_edited','bag_sidecar_or_telemetry_read_by_this_script'):
            receipt[flag] = False
        tool_names = tuple(before) + ('tools/run_reliability_v4_safety.py',)
        receipt['bundle_before'] = {'files':{name:pin(AUDIT/name) for name in tool_names}}
        metadata_names = ('source_integrity/source_frozen_integrity.json','source_integrity/source_before.json',
                          'source_integrity/source_after.json','source_integrity/frozen_actual.json','import_isolation.json')
        receipt['freeze_metadata_before'] = {name:pin(RUNTIME/'results/freeze_validation'/name) for name in metadata_names}
        sys.path.insert(0,str(AUDIT))
        from tools import reliability_v4_guard as guard
        from tools import reliability_v4_snapshot_audit as helper
        from tools import run_reliability_v4_safety as safety
        assert Path(guard.__file__).resolve() == guard_path
        assert Path(safety.__file__).resolve() == driver
        created = helper.create_contract(CORE,
            RUNTIME/'results/freeze_validation/source_integrity/source_frozen_integrity.json',
            RUNTIME/'results/freeze_validation/import_isolation.json',CONTRACT,api=guard)
        contract_binding = {k:created[k] for k in ('path','sha256')}
        context = safety.load_core(CORE,RUNTIME/'results/humble54_core12_owner01/owner_terminal.json',
                                   snapshot_audit_contract=contract_binding)
        receipt['snapshots'] = []
        first_bytes = None
        for slot_id in ('person_stage1_velocity_seed004','person_stage1_position_seed004','person_stage2_crossing_seed004'):
            trial = next(item for item in context.plan['trials'] if item['id'] == slot_id)
            snapshot_path = Path(trial['directory'])/'configuration/source_sha256.json'
            raw = snapshot_path.read_bytes()
            snapshot = json.loads(raw)
            item = {'id':slot_id,'original':pin(snapshot_path),'entries':len(snapshot)}
            if first_bytes is None:
                first_bytes = raw
                expected = {name:digest for name,digest in context.plan['source_hashes'].items() if helper.selected_source(name)}
                model = context.plan['protocol']['resources']['person']['model']
                for name in (model,'config/dds_runtime_humble22.json'):
                    expected[name] = context.plan['source_hashes'][name]
                item.update(helper_validate_snapshot_called=True,validation_basis='ACTUAL_UNMODIFIED_HELPER_VALIDATE_SNAPSHOT_CALL',
                    explicit_contract_validation=helper.validate_snapshot(snapshot,expected,contract_binding,context.plan,CORE.resolve(),
                        api=guard,driver_path=driver,validator_path=guard_path))
                receipt['expected_registered_snapshot_entries'] = len(expected)
            else:
                assert raw == first_bytes
                item.update(helper_validate_snapshot_called=False,
                    validation_basis='ORIGINAL_BYTES_SHA_AND_COMPLETE_MAPPING_EQUAL_TO_FIRST_ACTUAL_HELPER_VALIDATED_SNAPSHOT',
                    equivalent_to=receipt['snapshots'][0]['original'])
            receipt['snapshots'].append(item)
        registry = guard.load(OLD_AUDIT/'registry.json')
        original_row = guard.load(OLD_AUDIT/'person_auto_unique_multi_seed004.json')
        assert original_row['status'] == 'INFRASTRUCTURE_ERROR'
        fact = original_row['execution_facts']
        artifacts = {}
        for name in ('source_clock','native_startup','specialized'):
            binding = fact['evidence'][name]
            path = Path(binding['path'])
            artifacts[name] = (path,guard.load(path))
        directory = Path(original_row['trial']['directory'])
        args = (fact['executions'],artifacts,context.root)
        kwargs = {'execution_card':Path(registry['execution_card']['path'])}
        try:
            guard.safety_command_contract(*args,directory,'person','auto_unique_multi',**kwargs)
        except guard.Refusal as error:
            assert 'Safety command does not execute' in str(error)
            receipt['original_lexical_comparison_refusal_reproduced'] = str(error)
        else:
            raise AssertionError('Original linked-path refusal was not reproduced')
        guard.safety_command_contract(*args,directory.resolve(strict=True),'person','auto_unique_multi',**kwargs)
        receipt['physical_path_contract_diagnostic'] = 'PASS'
        receipt.update(read_only_old_command_contract_result='PASS',
            diagnostic_scope='Read-only command-contract diagnostic only; no full original-slot re-evaluation or result rewrite',
            contract=contract_binding,contract_metadata=guard.load(CONTRACT),exit_code=0,
            result='NATIVE_CONTRACT_AND_FIRST3_SNAPSHOT_AUDIT_COMPLETE_FORMAL_DUAL_ROOT_VALIDATION_PENDING',
            status='NATIVE_REPAIR_CONTRACT_AND_READ_ONLY_COMMAND_CONTRACT_COMPLETE_FRESH_SAFETY4_PENDING')
    except BaseException as error:
        receipt.update(status='FAILED_RETAIN_ALL_OUTPUTS',error=type(error).__name__+': '+str(error))
        raise
    finally:
        receipt['unchanged_tool_pins_after'] = {name:pin(AUDIT/name) for name in before}
        receipt['fixed_guard_helper_registrar_unchanged'] = before == receipt['unchanged_tool_pins_after']
        receipt['original_failure_and_contract_unchanged'] = old_terminal == pin(OLD_AUDIT/'execution_terminal.json') and old_contract == pin(RUNTIME/'results/snapshot_audit54_contract01.json')
        receipt['core_plan_unchanged'] = plan_before == pin(CORE)
        receipt['plan_after'] = pin(CORE)
        if 'bundle_before' in receipt:
            receipt['bundle_after'] = {'files':{name:pin(AUDIT/name) for name in tool_names}}
            receipt['freeze_metadata_after'] = {name:pin(RUNTIME/'results/freeze_validation'/name) for name in metadata_names}
            receipt['current_tool_bundle_unchanged_during_validation'] = receipt['bundle_before'] == receipt['bundle_after']
            receipt['frozen_metadata_unchanged_during_validation'] = receipt['freeze_metadata_before'] == receipt['freeze_metadata_after']
            if not all(receipt[name] for name in ('current_tool_bundle_unchanged_during_validation',
                'frozen_metadata_unchanged_during_validation','fixed_guard_helper_registrar_unchanged',
                'original_failure_and_contract_unchanged','core_plan_unchanged')):
                receipt.update(status='FAILED_RETAIN_ALL_OUTPUTS',exit_code=1,error='Source/metadata mutation observed')
        receipt['finished_utc'] = now()
        with (OUTPUT/'native_recovery02.json').open('x') as stream:
            json.dump(receipt,stream,ensure_ascii=True,indent=2)
        print(json.dumps({'status':receipt['status'],'receipt':str(OUTPUT/'native_recovery02.json')}),flush=True)
        if receipt.get('exit_code') != 0:
            raise RuntimeError('Native recovery did not complete successfully; keep all outputs')

if __name__ == '__main__':
    main()
