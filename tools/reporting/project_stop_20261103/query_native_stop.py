"""Read Linux process metadata only; never launches or stops an experiment."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

NEEDLES = (
    "px4", "gz sim", "gz-sim", "MicroXRCEAgent", "ros2 launch",
    "run_reliability_v4.py", "formal54_durable_owner.py",
    "humble54_pipeline_bench", "benchmark_lossless",
    "humble54_pending_collector", "run_closed_measurement.py",
)

rows = []
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit() or int(entry.name) == os.getpid():
        continue
    try:
        argv = (entry / 'cmdline').read_bytes().decode(errors='replace').replace('\x00', ' ').strip()
        if any(needle in argv for needle in NEEDLES):
            rows.append({'pid': int(entry.name), 'argv': argv[:500]})
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
print(json.dumps({'kind': 'READ_ONLY_STOP_STATE_QUERY',
                  'utc': datetime.now(timezone.utc).isoformat(),
                  'matching_processes': rows}, ensure_ascii=False))
