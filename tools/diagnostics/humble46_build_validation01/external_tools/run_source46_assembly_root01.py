"""Root execution receipt for the reviewed source-only Humble46 assembly."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

external = Path('/mnt/d/WSL/UAVHumble22-validation')
adapter = external / 'source_from_closed43_to46_01/assemble_closed43_to46_source.py'
receipt = external / 'humble46_source_assembly_execution_root01.json'
expected = sys.argv[1] if len(sys.argv) == 2 else ''
assert len(expected) == 64 and hashlib.sha256(adapter.read_bytes()).hexdigest() == expected
assert not receipt.exists()
command = ['/root/uav_humble22/venv/bin/python', '-B', str(adapter), '--source-root',
           '/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2',
           '--name', 'v4_humble46', '--commit', 'de89a6696d60a113929c97bab775dc2258ef4d01',
           '--core-tools-sha256', '4e5614388567b60ff5ab925390a37e254c8b8940f3092aa892579cf5cbd6359f']
started = datetime.now(timezone.utc).isoformat()
start = time.monotonic()
result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
value = {'scope': 'ROOT_ACTUAL_SOURCE46_ASSEMBLY_NOT_BUILD_OR_FLIGHT_ACCEPTANCE',
         'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
         'elapsed_wall_s': time.monotonic() - start, 'command': command,
         'adapter_sha256': expected, 'returncode': result.returncode,
         'stdout': result.stdout.decode('utf-8', errors='replace'),
         'stderr': result.stderr.decode('utf-8', errors='replace'),
         'source_commit': 'de89a6696d60a113929c97bab775dc2258ef4d01'}
with receipt.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(value, stream, indent=2, ensure_ascii=True)
    stream.write('\n')
print(json.dumps(value, indent=2, ensure_ascii=True))
raise SystemExit(result.returncode)
