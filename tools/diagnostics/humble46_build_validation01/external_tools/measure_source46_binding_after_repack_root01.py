"""Time the unchanged source validator after additive Git object packing."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

external = Path('/mnt/d/WSL/UAVHumble22-validation')
sys.path.insert(0, str(external))
import reviewed_freeze_build as generic
import development_freeze_build as development

output = external / 'humble46_source_binding_after_git_repack_root01.json'
assert not output.exists()
review = development.load_review(external/'reviewed_freeze_review_v4_humble46_01.json',
    '68e3d2891e08001e86b4162def9c33ad2f2536257df9726c866ffdb4e7ad98a4', 'prepare')
prepare = generic.read_small(external/'reviewed_freeze_actions_v4_humble46/prepare/action.terminal.json')
assert prepare['status'] == 'PASS'
with generic.exclusive_window():
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    actual = generic.candidate_binding(review)
    elapsed = time.monotonic() - started
    assert actual == prepare['binding_before']['source'] == prepare['binding_after']['source']
    value = {'scope': 'UNCHANGED_NATIVE_SOURCE_BINDING_TIMING_NOT_COPY_OR_BUILD_ACCEPTANCE',
             'status': 'PASS_SAME_SOURCE_BINDING', 'started_utc': started_utc,
             'finished_utc': datetime.now(timezone.utc).isoformat(), 'elapsed_wall_s': elapsed,
             'actual_source_binding_canonical_sha256': generic.canonical(actual),
             'changed_added_git_blob_comparisons': len(actual['changed_or_added_blob_pairs']),
             'actual_source_binding_equals_original_prepare_before_after': True,
             'original_generic_sha256': generic.sha(external/'reviewed_freeze_build.py'),
             'original_timeouts_or_gates_modified': False, 'GIT_environment_override_used': False,
             'copy_or_build_executed': False}
    generic.write_new(output, value)
print(json.dumps(value, indent=2))
