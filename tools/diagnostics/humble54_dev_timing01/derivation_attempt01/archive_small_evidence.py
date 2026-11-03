"""One-use Windows archive/extraction of saved DEV outputs; no native execution.

Does not read events.jsonl, any bag, model, or production process. The full
lineage JSON is read once with a seven MiB bound, pinned, and summarized; the
full lineage report is intentionally not copied into this public archive.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast
from collections import Counter
import hashlib
import json


BASE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/WSL/UAVHumble22-validation')
DEV = EXTERNAL / 'humble54_dev_timing01'


def bounded_read(path, maximum=1024**2):
    before = path.stat()
    assert path.is_file() and before.st_size <= maximum
    data = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(data) == before.st_size
    return data


def pin(path, data):
    return {'path': str(path), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def write_json(name, value):
    with (BASE/name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write('\n')


def main():
    inputs = [(DEV/name, 'originals/'+name) for name in (
        'execution_receipt.json', 'export/context.json', 'export.log',
        'timing_analysis.log', 'lineage_analysis.log', 'timing_report.json')]
    inputs += [(EXTERNAL/name, 'scripts/'+name) for name in (
        'run_humble54_dev_timing01.py', 'run_humble54_dev_timing01.sh')]
    originals, data_by_name = [], {}
    for source, relative in inputs:
        data = bounded_read(source)
        destination = BASE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
        assert destination.read_bytes() == data
        originals.append(dict(pin(source, data), archive_path=relative))
        data_by_name[relative] = data
    execution = json.loads(data_by_name['originals/execution_receipt.json'])
    assert execution['status'] == 'COMPLETED_DEV_OBSERVATIONS_ONLY'
    assert execution['formal_seed_use_authorized'] is False
    assert execution['input_pins_unchanged'] is True
    assert len(execution['executions']) == 3
    assert [item['name'] for item in execution['executions']] == [
        'export', 'timing_analysis', 'lineage_analysis']
    assert all(item['returncode'] == 0 for item in execution['executions'])
    for item in execution['executions']:
        name = item['log']['path'].rsplit('/', 1)[-1]
        data = data_by_name['originals/'+name]
        assert len(data) == item['log']['bytes']
        assert hashlib.sha256(data).hexdigest() == item['log']['sha256']
    for item in execution['output_pins'][:2]:
        name = ('export/context.json' if item['path'].endswith('/export/context.json')
                else 'timing_report.json')
        data = data_by_name['originals/'+name]
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
    script_pin = execution['input_pins_before'][0]
    assert hashlib.sha256(data_by_name['scripts/run_humble54_dev_timing01.py']).hexdigest() == script_pin['sha256']
    ast.parse(data_by_name['scripts/run_humble54_dev_timing01.py'].decode('utf-8'), feature_version=(3, 10))
    context = json.loads(data_by_name['originals/export/context.json'])
    timing = json.loads(data_by_name['originals/timing_report.json'])

    # Exactly one bounded read of the existing full lineage report.
    lineage_path = DEV/'lineage_report.json'
    lineage_data = bounded_read(lineage_path, 7*1024**2)
    lineage_pin = pin(lineage_path, lineage_data)
    expected = execution['output_pins'][2]
    assert lineage_pin['bytes'] == expected['bytes']
    assert lineage_pin['sha256'] == expected['sha256']
    lineage = json.loads(lineage_data)
    commands = lineage['commands']
    assert lineage['original_command_denominator'] == len(commands) == 1857
    assert lineage['known_commands'] == 0
    assert lineage['unknown_commands'] == 1857
    multiple = [row for row in commands if row['formula_native_candidate_count'] > 1]
    assert len(multiple) == 1377
    choices = multiple[:3]
    assert all(row['status'] == 'UNKNOWN' for row in choices)
    derived = {
        'kind': 'DERIVED_SUMMARY_AND_EXACT_COMMAND_ROWS_FROM_PINNED_FULL_DEV_LINEAGE_REPORT',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_full_report_pin': lineage_pin,
        'full_report_copied_into_archive': False,
        'derivation': 'All top-level original fields except commands are copied under original_top_level_fields_except_commands. Three original command objects are copied exactly, selected as the first three report commands with formula_native_candidate_count > 1. Counts below are derived from the unchanged report, not a rerun or replacement method.',
        'original_top_level_fields_except_commands': {key: value for key, value in lineage.items() if key != 'commands'},
        'derived_command_status_counts': dict(Counter(row['status'] for row in commands)),
        'derived_formula_candidate_count_distribution': dict(sorted(Counter(
            row['formula_native_candidate_count'] for row in commands).items())),
        'derived_multiple_formula_candidate_commands': len(multiple),
        'original_command_examples': choices,
        'strict_original_method_and_unknowns_preserved': True,
        'does_not_establish_controller_consumption_or_physical_e2e': True,
    }
    write_json('lineage_derived_summary.json', derived)
    write_json('source_manifest.json', {
        'kind': 'UNCHANGED_SMALL_DEV_ORIGINALS_AND_PINNED_UNCOPIED_FULL_REPORT',
        'original_count': len(originals),
        'total_original_bytes': sum(item['bytes'] for item in originals),
        'originals': originals,
        'uncopied_full_lineage_report': lineage_pin,
        'events_jsonl_read_or_copied': False,
        'bags_or_models_read': False,
        'native_execution_performed': False,
    })
    print(json.dumps({
        'original_files': len(originals), 'original_bytes': sum(item['bytes'] for item in originals),
        'timing_keys': list(timing), 'context_keys': list(context),
        'timing_selected': {key: ({name: value for name, value in timing[key].items()
                                  if name != 'samples'} if isinstance(timing[key], dict)
                                 else timing[key]) for key in (
            'event_count', 'event_counts', 'detector_processed_source_fps',
            'detector_acquisition_to_prepublication_source_s',
            'detector_processing_prefix_wall_s', 'completed_job_before_timing_log_wall_s',
            'actual_worker_processed_wall_fps')},
        'lineage_summary': {key: value for key, value in lineage.items()
                            if key not in ('commands',)},
        'example_command_indices': [row['command_event_index'] for row in choices],
    }, ensure_ascii=True))


if __name__ == '__main__':
    main()
