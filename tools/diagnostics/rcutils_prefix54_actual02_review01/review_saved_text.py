"""Independently review saved logger evidence, without executing ROS or ELF tools.

Run only this reviewer. The archived probe/checker/shell scripts are evidence,
not an instruction to execute them. All reads are bounded by one MiB per file.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import re


BASE = Path(__file__).resolve().parent
MAX_FILE = 1024 * 1024


def read(relative):
    path = BASE / relative
    before = path.stat()
    assert path.is_file() and before.st_size <= MAX_FILE, relative
    data = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(data) == before.st_size
    return data


def decode(relative):
    return read(relative).decode('utf-8')


def require_snippets(relative, snippets):
    saved = decode(relative)
    for snippet in snippets:
        assert snippet in saved, (relative, snippet)


def review():
    old = read('scripts/rcutils_prefix_clock_probe01.py')
    new = read('scripts/rcutils_prefix_clock_probe02.py')
    old_import = b'from rclpy.clock_type import ClockType'
    new_import = b'from rclpy.clock import ClockType'
    assert old.count(old_import) == 1 and new.count(new_import) == 1
    assert old.replace(old_import, new_import) == new
    for relative in ('scripts/rcutils_prefix_clock_probe01.py',
                     'scripts/rcutils_prefix_clock_probe02.py',
                     'scripts/check_rcutils_prefix54_actual02.py'):
        ast.parse(decode(relative), feature_version=(3, 10))
    assert read('actual01/probe.jsonl') == b''
    assert read('actual01/probe.exit_code.txt') == b'1\n'
    assert "ModuleNotFoundError: No module named 'rclpy.clock_type'" in decode('actual01/console.log')
    assert read('actual02/probe.exit_code.txt') == b'0\n'

    rows = [json.loads(line) for line in decode('actual02/probe.jsonl').splitlines()]
    assert len(rows) == 6
    provenance, recheck = rows[0], rows[-1]
    brackets = rows[1:-1]
    assert provenance['kind'] == 'CURRENT_LOGGER_CLOCK_AUDIT_PROVENANCE_NOT_HISTORICAL_PROOF'
    assert provenance['node_or_dds_or_simulator_started'] is False
    assert provenance['prior_environment']['LD_PRELOAD'] is None
    assert provenance['audit_environment']['LD_PRELOAD'] is None
    assert provenance['audit_environment']['RCUTILS_CONSOLE_OUTPUT_FORMAT'] == (
        '[{severity}] [{time}] [ns={time_as_nanoseconds}] [{name}]: {message}')
    assert [row['event_id'] for row in brackets] == list(range(4))
    assert [row['controlled_ros_clock_ns'] for row in brackets] == [7*10**9, 9*10**9, 3*10**9, 3*10**9]
    assert recheck['source_and_binary_pins_unchanged'] is True
    assert recheck['historical_process_provenance_established'] is False
    assert recheck['clock_source_conclusion_created'] is False
    pattern = re.compile(r'^\[INFO\] \[(\d+)\.(\d{9})\] \[ns=(\d+)\] '
                         r'\[rcutils_prefix_clock_probe01\]: RCUTILS_PREFIX_CLOCK_PROBE (\{.*\})$')
    console = decode('actual02/console.log').splitlines()
    assert len(console) == 4
    events = []
    for line, bracket in zip(console, brackets):
        match = pattern.fullmatch(line)
        assert match is not None
        sec, fraction, stamp, payload = match.groups()
        stamp = int(stamp)
        assert int(sec)*10**9 + int(fraction) == stamp
        payload = json.loads(payload)
        assert payload['event_id'] == bracket['event_id']
        assert payload['controlled_ros_clock_ns'] == bracket['controlled_ros_clock_ns']
        assert bracket['system_before_ns'] <= stamp <= bracket['system_after_ns']
        assert bracket['steady_before_ns'] <= bracket['steady_after_ns'] < stamp
        assert stamp != bracket['controlled_ros_clock_ns']
        events.append({
            'event_id': bracket['event_id'], 'stamp_ns': stamp,
            'controlled_ros_clock_ns': bracket['controlled_ros_clock_ns'],
            'system_before_ns': bracket['system_before_ns'],
            'system_after_ns': bracket['system_after_ns'],
            'steady_before_ns': bracket['steady_before_ns'],
            'steady_after_ns': bracket['steady_after_ns'],
            'system_bracket_match': True,
            'decimal_and_integer_tokens_identical': True,
            'distance_from_system_before_ns': stamp-bracket['system_before_ns'],
            'distance_to_system_after_ns': bracket['system_after_ns']-stamp,
        })
    for first, second in zip(events, events[1:]):
        assert first['stamp_ns'] < second['stamp_ns']
        assert first['system_after_ns'] < second['system_before_ns']
        assert first['steady_after_ns'] < second['steady_before_ns']

    checker = json.loads(decode('actual02/brackets_and_elf_receipt.json'))
    assert checker['probe_exit_code'] == 0
    assert checker['current_sources_unchanged'] is True
    assert checker['historical_process_provenance_established'] is False
    assert checker['worker_wall_fps_established'] is False
    assert len(checker['elf_executions']) == 6
    assert checker['elf_call_chain_conclusion'] == 'PENDING_HUMAN_OR_AGENT_DISASSEMBLY_REVIEW'
    for event, checked in zip(events, checker['events']):
        assert {name: event[name] for name in checked} == checked
    assert len(checker['events']) == len(events)
    for command in checker['elf_executions']:
        assert command['returncode'] == 0
        saved = command['output']
        name = saved['path'].rsplit('/', 1)[-1]
        data = read('actual02/' + name)
        assert len(data) == saved['bytes']
        assert hashlib.sha256(data).hexdigest() == saved['sha256']
    pins = provenance['source_and_binary_pins']
    assert len(pins) == 15 and len(provenance['mapped_logger_libraries']) == 10
    for saved in checker['actual_provenance_pins']:
        pin = pins[saved['path']]
        assert saved['bytes'] == pin['bytes'] and saved['sha256'] == pin['sha256']
    assert len(checker['actual_provenance_pins']) == len(pins)
    for name, mapped in provenance['mapped_logger_libraries'].items():
        pin = pins[name]
        major, minor = (int(v, 16) for v in mapped['device'].split(':'))
        # Linux's saved st_dev is accepted as recorded provenance; this
        # reviewer never opens those native libraries or historical processes.
        assert major == 8 and minor == 48 and pin['device'] == 2096
        assert pin['inode'] == mapped['inode']
    assert hashlib.sha256(new).hexdigest() == pins[
        '/mnt/d/WSL/UAVHumble22-validation/rcutils_prefix_clock_probe02.py']['sha256']

    require_snippets('actual02/rclpy_dynamic.txt', ['Shared library: [librcutils.so]'])
    require_snippets('actual02/rcutils_log.txt', [
        'f048:', 'lea    0x8(%rsp),%rdi',
        'f04d:', 'call   5a00 <rcutils_system_time_now@plt>',
        'g_rcutils_logging_output_handler', 'f09f:', 'mov    0x8(%rsp),%rcx',
        'f0af:', 'call   *%rax'])
    require_snippets('actual02/rcutils_system_time_now.txt', [
        'ef01:', 'mov    %rsp,%rsi', 'ef04:', 'xor    %edi,%edi',
        'ef06:', 'call   5990 <clock_gettime@plt>',
        'ef23:', 'imul   $0x3b9aca00,%rax,%rax',
        'ef2a:', 'add    %rdx,%rax', 'ef2d:', 'mov    %rax,(%rbx)'])
    require_snippets('actual02/rcutils_logging_console_output_handler.txt', [
        'b62d:', 'mov    %rcx,%r13', 'bbdd:', 'mov    %r13,%rcx',
        'bbe6:', 'call   5f20 <rcutils_logging_format_message@plt>'])
    require_snippets('actual02/rcutils_logging_format_message.txt', [
        '8f29:', 'mov    %rcx,%rbx', '8f6f:', 'mov    %rbx,0x30(%rsp)',
        '9051:', 'call   5b50 <find_token_handler@plt>',
        '8f90:', 'lea    0x10(%rsp),%rdi', '8f98:', 'call   *%rax'])
    return {
        'kind': 'INDEPENDENT_SAVED_TEXT_AND_INTEGER_BRACKET_REVIEW',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'reviewer': '/root/detector_tail_candidate',
        'failed_actual01_preserved': True,
        'probe02_change_is_exactly_one_import_replacement': True,
        'python_scripts_parse_as_python310': True,
        'original_checker_not_executed_by_reviewer': True,
        'native_libraries_not_opened_by_reviewer': True,
        'events': events,
        'all_system_and_steady_brackets_nonregressing': True,
        'current_process_prefix_system_clock_observation_supported': True,
        'elf_saved_text_call_chain_review': {
            'architecture': 'x86-64 System V argument convention',
            'rcutils_log': 'f04d calls rcutils_system_time_now; f09f loads the resulting timestamp as fourth argument; f0af dispatches output handler.',
            'rcutils_system_time_now': 'ef04 zeroes clock ID; ef06 calls clock_gettime(0, ...); Linux clock ID 0 is CLOCK_REALTIME; ef23..ef2d forms seconds*1e9+nanoseconds.',
            'console_handler': 'b62d preserves fourth argument in r13; bbdd restores rcx before bbe6 calls rcutils_logging_format_message.',
            'formatter': '8f29 preserves timestamp; 8f6f stores it at context+0x20; 8f90..8f98 passes context to the selected token handler.',
            'token_handler_bodies_reviewed': False,
            'runtime_tokens_match_same_integer_timestamp': True,
        },
        'mapped_library_provenance_scope': 'Current audit process saved maps and before/after pathname pins only; libraries were not reopened in this independent review.',
        'historical_process_provenance_established': False,
        'worker_wall_fps_established': False,
        'worker_callback_or_publish_endpoint_established': False,
        'scope_limitations': [
            'Separate audit ROSClock and TimeSource were changed locally; no production detector node was started.',
            'No historical detector process source/binary/load environment was authenticated by this observation.',
            'No worker duration, callback timestamp, inference endpoint, throughput, or FPS follows from four logger calls.',
            'Individual formatter token handler bodies are absent from the saved disassembly and were not claimed as reviewed.',
        ],
    }


if __name__ == '__main__':
    receipt = review()
    destination = BASE / 'independent_review_receipt.json'
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    print(json.dumps({'receipt': destination.name, 'events': len(receipt['events']),
                      'system_prefix_observation_supported': True,
                      'historical_process_provenance_established': False,
                      'worker_wall_fps_established': False}))
