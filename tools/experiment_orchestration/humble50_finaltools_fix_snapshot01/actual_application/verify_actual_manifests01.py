"""Read actual metadata manifests only; never build, preflight or launch ROS."""
import builtins
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation/dds48_tools01')
OUTPUT = Path(__file__).resolve().parent
PROJECTED = OUTPUT.parent / 'sealer_candidate01'
sys.dont_write_bytecode = True
sys.path.insert(0, str(EXTERNAL))


def denied_process(*args, **kwargs):
    raise RuntimeError('Metadata manifest verification must not launch a process')


original_import = builtins.__import__


def metadata_import(name, *args, **kwargs):
    if name.split('.')[0] in {'rclpy', 'cv2', 'torch', 'rosbag2_py'}:
        raise RuntimeError('Runtime import forbidden in metadata verification: ' + name)
    return original_import(name, *args, **kwargs)


subprocess.Popen = denied_process
builtins.__import__ = metadata_import

import prepare_development_final_root_v2 as preparation
import seal_development_final_source_v2 as sealer
import development_runner as core
import development_freeze_build as build

actual = preparation.tool_manifest()
expected = json.loads((PROJECTED / 'projected_final_v2_tool_manifest01.json').read_bytes())
assert actual == expected
assert preparation.canonical(actual) == 'e8585f14ece45335f24614a1794bedf1c205503a90cf587060ed25851c0bd0c9'
actual_sealer = sealer.tools()
expected_sealer = json.loads((PROJECTED / 'projected_sealer_tool_manifest01.json').read_bytes())
assert actual_sealer == expected_sealer
assert preparation.canonical(actual_sealer) == 'ffa69d35ed1581c68e1b80ef0f3f5030be99178ea1236d5547c3fb4203268a41'
assert core.canonical(core.tool_manifest()) == '2129fd88ec6f55625acaa1455919d516a364075394bd2e18efed3f108316a11a'
assert core.canonical(build.tool_manifest()) == '919a4483554c73cfbabb1efda910c2dd831e79b963443545bece5307fe51077e'
record = {
    'schema_version': 1,
    'scope': 'ACTUAL_NATIVE_METADATA_MANIFESTS_ONLY_NOT_BUILD_RUNTIME_OR_FORMAL_AUTHORITY',
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'PASS_ACTUAL_MANIFESTS_MATCH_INDEPENDENT_STATIC_PROJECTIONS',
    'interpreter': sys.executable,
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'preparation': actual,
    'preparation_canonical_sha256': preparation.canonical(actual),
    'sealer': actual_sealer,
    'sealer_canonical_sha256': preparation.canonical(actual_sealer),
    'core2129_and_strictbuild919_unchanged': True,
    'native_runtime_imports_or_subprocesses_allowed': False,
    'native_runtime_preflight_or_tests_executed': False,
    'build_or_formal_authority_granted': False,
}
with (OUTPUT / 'native_actual_manifests01.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({key: record[key] for key in ('status', 'preparation_canonical_sha256', 'sealer_canonical_sha256', 'core2129_and_strictbuild919_unchanged')}))
