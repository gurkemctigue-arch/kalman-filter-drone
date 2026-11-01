"""Add a packed copy of Git objects; retain all original Git files byte for byte."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

root = Path.cwd().resolve()
external = Path('D:/WSL/UAVHumble22-validation')
before_path = external / 'humble46_git_repack_before_root01.json'
outcome_path = external / 'humble46_git_repack_outcome_root01.json'
assert not before_path.exists() and not outcome_path.exists()
gitdir = root / '.git'
assert gitdir.is_dir() and not gitdir.is_symlink()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args], capture_output=True)
    assert result.returncode == 0, (args, result.returncode, result.stderr.decode(errors='replace'))
    return result.stdout

def inventory():
    files = {}
    for path in sorted(gitdir.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            files[path.relative_to(gitdir).as_posix()] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    return files

head = run(['rev-parse', 'HEAD']).decode().strip()
assert head == 'de89a6696d60a113929c97bab775dc2258ef4d01'
assert not run(['-c', 'core.autocrlf=true', 'status', '--porcelain'])
original = inventory()
assert not any(name.startswith('objects/pack/') for name in original)
before = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': head,
          'files': original, 'count_objects': run(['count-objects', '-v']).decode()}
with before_path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(before, stream, indent=2); stream.write('\n')
start = time.monotonic()
command = ['git', '-C', str(root), '-c', 'pack.threads=2', 'repack', '-a', '-n', '-q']
result = subprocess.run(command, capture_output=True)
after = inventory()
unchanged = all(after.get(name) == facts for name, facts in original.items())
added = sorted(after.keys() - original.keys())
assert result.returncode == 0 and unchanged
assert added and all(name.startswith('objects/pack/pack-') and name.endswith(('.pack', '.idx', '.rev', '.bitmap')) for name in added)
assert run(['rev-parse', 'HEAD']).decode().strip() == head
assert not run(['-c', 'core.autocrlf=true', 'status', '--porcelain'])
fsck = run(['fsck', '--full'])
value = {'scope': 'ADDITIVE_GIT_OBJECT_STORAGE_MAINTENANCE_NOT_SOURCE_OR_PROTOCOL_CHANGE',
         'status': 'PASS_ORIGINAL_GIT_BYTES_RETAINED', 'finished_utc': datetime.now(timezone.utc).isoformat(),
         'elapsed_wall_s': time.monotonic() - start, 'command': command, 'returncode': result.returncode,
         'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace'),
         'before_inventory_sha256': sha(before_path), 'original_git_file_count': len(original),
         'all_original_git_file_bytes_unchanged': unchanged, 'source_commit': head,
         'new_files': {name: after[name] for name in added}, 'count_objects_after': run(['count-objects', '-v']).decode(),
         'git_fsck_full_exit0': True, 'git_fsck_full_stdout': fsck.decode(errors='replace'),
         'original_objects_pruned': False, 'refs_index_head_unchanged': True,
         'GIT_environment_override_used': False, 'performance_gain_measured': False}
with outcome_path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(value, stream, indent=2); stream.write('\n')
print(json.dumps(value, indent=2))
