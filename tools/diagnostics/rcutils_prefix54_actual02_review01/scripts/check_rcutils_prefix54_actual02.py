from pathlib import Path
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

output = Path('/mnt/d/WSL/UAVHumble22-validation/rcutils_prefix54_actual02')
rows = [json.loads(line) for line in (output/'probe.jsonl').read_text().splitlines()]
provenance, recheck = rows[0], rows[-1]
brackets = {row['event_id']: row for row in rows[1:-1]}
console = (output/'console.log').read_text()
matches = re.findall(r'\[([0-9]+\.[0-9]+)\] \[ns=([0-9]+)\].*RCUTILS_PREFIX_CLOCK_PROBE (\{.*\})',console)
assert len(matches) == 4 and len(brackets) == 4
observations = []
for decimal, integer, payload in matches:
    data, stamp = json.loads(payload), int(integer)
    bracket = brackets[data['event_id']]
    assert bracket['system_before_ns'] <= stamp <= bracket['system_after_ns']
    assert data['controlled_ros_clock_ns'] == bracket['controlled_ros_clock_ns']
    assert stamp > bracket['steady_after_ns'] and stamp != data['controlled_ros_clock_ns']
    sec, fraction = decimal.split('.')
    assert int(sec)*10**9+int(fraction.ljust(9,'0')) == stamp
    observations.append({'event_id':data['event_id'],'stamp_ns':stamp,'system_bracket_match':True,
                         'controlled_ros_clock_ns':data['controlled_ros_clock_ns']})
assert recheck['source_and_binary_pins_unchanged']
mapped = provenance['mapped_logger_libraries']
rcutils = next(Path(name) for name in mapped if Path(name).name == 'librcutils.so')
rclpy = next(Path(name) for name in mapped if Path(name).name.startswith('_rclpy_pybind11'))
pins, commands = [], []
def pin(path):
    data = path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
for name, old in provenance['source_and_binary_pins'].items():
    current = pin(Path(name))
    assert current['sha256'] == old['sha256'] and current['bytes'] == old['bytes']
    pins.append(current)
requests = [('rclpy_dynamic.txt',['readelf','--wide','--dynamic',str(rclpy)]),
            ('rcutils_symbols.txt',['readelf','--wide','--dyn-syms',str(rcutils)])]
for symbol in ('rcutils_log','rcutils_system_time_now','rcutils_logging_console_output_handler','rcutils_logging_format_message'):
    requests.append((symbol+'.txt',['objdump','-drwC','--disassemble='+symbol,str(rcutils)]))
for name, argv in requests:
    with (output/name).open('xb') as stream:
        result = subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT)
    commands.append({'argv':argv,'returncode':result.returncode,'output':pin(output/name)})
    assert result.returncode == 0
receipt = {'kind':'CURRENT_PROCESS_LOGGER_PREFIX_SYSTEM_BRACKETS_AND_ACTUAL_ELF_OBSERVATION',
           'created_utc':datetime.now(timezone.utc).isoformat(),'probe_exit_code':int((output/'probe.exit_code.txt').read_text()),
           'events':observations,'current_sources_unchanged':True,'actual_provenance_pins':pins,
           'elf_executions':commands,'elf_call_chain_conclusion':'PENDING_HUMAN_OR_AGENT_DISASSEMBLY_REVIEW',
           'historical_process_provenance_established':False,'worker_wall_fps_established':False}
with (output/'brackets_and_elf_receipt.json').open('x') as stream:
    json.dump(receipt,stream,ensure_ascii=True,indent=2)
print(json.dumps({'probe_exit':receipt['probe_exit_code'],'four_current_system_brackets_match':True,
                  'elf_outputs_saved':len(commands),'historical_or_worker_fps_proved':False}))
