"""Prepare a fresh source/results tree; never build, register, plan or fly.

Dev41 binding of the reviewed existing preparation implementation. Copy is
byte-identical with an explicitly empty overlay. Three planning files remain
DRAFT. Capacity, runtime acceptance and formal admission remain external gates.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

EXTERNAL = Path(__file__).resolve().parent
BASE_REVIEW_NAME = 'reviewed_freeze_review_humble41_01.json'
BASE_REVIEW_SHA256 = 'c112dca912301f7d2f79a6bc113dd21592c285f1c1cacb4a21511f22b34d50b9'
BASE_MANIFEST_SHA256 = 'b5fe12a9c7941af79dd8027f8d69850f8603468b6fd2c7fa80986e7bcba247b0'
BASE_CANONICAL_SHA256 = 'fcf0a653d4f225babc574ef395c50b5b6699efcbf8e684f64ff5b65bb1b5586a'
BASE_FILE_COUNT = 634
SOURCE_COMMIT = '8d542aff7827fded5b371971795796ce751a17aa'
SOURCE_ROOT = Path('/root/uav_tracking_fullplan_v4_humble41')
SOURCE_RESULTS = '/mnt/d/\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2/results/frozen_fullplan_v4_humble41'
LINUX_EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
REVIEW_RECEIPT_NAME = 'humble41_actual_pending_source_root_independent01.json'
REVIEW_RECEIPT_SHA256 = '141c035a608404bb4f0052ed0dead728de2e6540eab71f4cc5c2c9a264ecbb46'
RUNNER = 'scripts/run_reliability_v4.py'
FREEZER = 'scripts/freeze_full_plan_workspace.sh'
EXCLUDES = ('__pycache__', '.pytest_cache', 'results/', '.git/', 'node_modules/',
            '.test_temp/', '*.egg-info/', 'ros2_ws/build/', 'ros2_ws/install/', 'ros2_ws/log/')
OVERLAYS = {}
KIND = 'HUMBLE41_FINAL_ROOT_SOURCE_PREPARATION01_ONLY'
OVERLAY_KIND = 'HUMBLE41_FINAL_ROOT_EXPLICIT_EMPTY_OVERLAY'
PLANNING = ('planning/reliability-v4-preregistration.json',
    'planning/reliability-v4-extension-preregistration.json',
    'planning/reliability-v4-estimator-replay-preregistration.json')
DRAFT = 'DRAFT_NOT_FROZEN_NOT_EXECUTED'
RUNTIME_NAMES = ('config/px4_magnetic_runtime.json', 'config/gazebo_magnetic_runtime_humble22.json',
    'config/ros_gz_runtime_humble22.json', 'scripts/build_metric_supplement.py')
RUNTIME = {'distro': 'UAVHumble22', 'ros': 'humble',
    'px4_root': '/root/uav_humble22/PX4-Autopilot-v4mag',
    'bridge_overlay': '/root/uav_humble22/ros_gz_shutdown_A01_ws',
    'python': '/root/uav_humble22/venv/bin/python',
    'invariant_policy': 'HUMBLE33_SAFETY_AND_RESOURCE_CONTRACTS_UNCHANGED'}
BOUND_INPUTS = ('base_review', 'original_source_manifest', 'independent_review', 'overlay_manifest', 'tool')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 128 * 1024**2,
            'Expected a bounded ordinary JSON file: ' + str(path))
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + token)))


def file_binding(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Expected an ordinary source/evidence file: ' + str(path))
    return {'path': str(path), 'sha256': sha(path)}


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def relative(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name and ':' not in name and not any(ord(c) < 32 for c in name) and not path.is_absolute()
            and '..' not in path.parts and '\\' not in name and str(path) == name,
            'Unsafe project-relative source path')
    return path


def excluded(name):
    parts = relative(name).parts
    if any(part in {'__pycache__', '.pytest_cache', 'results', '.git', 'node_modules', '.test_temp'}
           or part.endswith('.egg-info') for part in parts):
        return True
    return len(parts) >= 2 and parts[0] == 'ros2_ws' and parts[1] in {'build', 'install', 'log'}


def entry(path, root):
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if path.is_symlink():
        link = os.readlink(path)
        require(not Path(link).is_absolute(), 'Absolute source symlink would retain an old-root dependency: ' + str(path))
        target = path.resolve(strict=True)
        require(target.is_relative_to(root) and not excluded(target.relative_to(root).as_posix()),
                'Source symlink escapes the copied tree or points into an excluded tree: ' + str(path))
        return {'kind': 'symlink', 'target': link}
    if path.is_dir():
        return {'kind': 'directory', 'mode': mode}
    require(path.is_file(), 'Unsupported source-tree object: ' + str(path))
    return {'kind': 'file', 'mode': mode, 'bytes': info.st_size, 'sha256': sha(path)}


def inventory(root):
    """Inventory source/build inputs, pruning results and every freezer exclusion."""
    root = Path(root).resolve(strict=True)
    result = {}
    for parent, folders, names in os.walk(root, followlinks=False):
        parent = Path(parent)
        kept = []
        for name in sorted(folders):
            path = parent / name
            key = path.relative_to(root).as_posix()
            if excluded(key):
                continue
            result[key] = entry(path, root)
            if not path.is_symlink():
                kept.append(name)
        folders[:] = kept
        for name in sorted(names):
            path = parent / name
            key = path.relative_to(root).as_posix()
            if not excluded(key):
                result[key] = entry(path, root)
    return dict(sorted(result.items()))


def frozen_classifier(root):
    spec = importlib.util.spec_from_file_location('humble41_final_preparation_classifier', root / RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_paths(source, destination, results):
    require(source == SOURCE_ROOT and source.resolve(strict=True) == source and not source.is_symlink(),
            'Use the actual immutable Humble41 development root')
    require(destination.parent == Path('/root')
            and re.fullmatch(r'uav_tracking_fullplan_[A-Za-z0-9_]+', destination.name),
            'Use a dedicated new /root/uav_tracking_fullplan_NAME source/build tree')
    require(re.fullmatch(r'/mnt/d/.+/results/frozen_fullplan_[A-Za-z0-9_]+', str(results)),
            'Final results must use a dedicated new D-drive results/frozen_fullplan_NAME directory')
    for path in (destination, results):
        require(not path.exists() and not path.is_symlink() and path.parent.is_dir()
                and path.parent.resolve(strict=True) == path.parent,
                'New non-aliased destination with an existing explicit parent required: ' + str(path))
    require(results != (source / 'results').resolve(strict=True), 'Never reuse development results')


def load_baseline():
    """Read only the actual41 source authority; never regrade old experiments."""
    review_path = EXTERNAL / BASE_REVIEW_NAME
    manifest_path = SOURCE_ROOT / 'results/freeze_validation/source_freeze_manifest.json'
    independent_path = EXTERNAL / REVIEW_RECEIPT_NAME
    require(sha(review_path) == BASE_REVIEW_SHA256 and sha(manifest_path) == BASE_MANIFEST_SHA256
            and sha(independent_path) == REVIEW_RECEIPT_SHA256, 'Actual41 baseline authority bytes changed')
    review, manifest, independent = read(review_path), read(manifest_path), read(independent_path)
    protected = review.get('files')
    require(review.get('schema_version') == 1
            and review.get('status') == 'FINAL_SOURCE_AND_TOOLS_INDEPENDENTLY_REVIEWED'
            and review.get('scope') == 'REVIEWED_SOURCE_FREEZE_BUILD_ONLY_NOT_RUNTIME_ACCEPTANCE'
            and review.get('frozen_root') == str(SOURCE_ROOT)
            and review.get('results_root') == SOURCE_RESULTS and review.get('source_commit') == SOURCE_COMMIT
            and review.get('runtime') == RUNTIME and review.get('expected_full_suite_skips') == 5
            and isinstance(protected, dict) and len(protected) == BASE_FILE_COUNT
            and canonical(protected) == BASE_CANONICAL_SHA256,
            'Actual41 reviewed source/runtime map differs')
    for name, digest in protected.items():
        relative(name)
        require(not excluded(name) and re.fullmatch('[0-9a-f]{64}', digest), 'Invalid reviewed source entry')
    require(manifest.get('schema_version') == 1 and manifest.get('source_root') == str(SOURCE_ROOT)
            and manifest.get('results_root') == SOURCE_RESULTS and manifest.get('source_commit') == SOURCE_COMMIT
            and manifest.get('files') == protected and manifest.get('freeze_source_sha256') == BASE_CANONICAL_SHA256
            and manifest.get('source_file_count') == BASE_FILE_COUNT
            and manifest.get('classified_source_hashes') == review.get('classified_source_hashes')
            and manifest.get('final_review') == {'path': str(LINUX_EXTERNAL / BASE_REVIEW_NAME), 'sha256': BASE_REVIEW_SHA256},
            'Actual41 original manifest/review binding differs')
    require(review.get('independent_review_receipt') == {
            'path': str(LINUX_EXTERNAL / REVIEW_RECEIPT_NAME), 'sha256': REVIEW_RECEIPT_SHA256,
            'scope': 'SOURCE_FREEZE_BUILD_ONLY_NOT_RUNTIME_ACCEPTANCE'}
            and independent.get('status') == 'INDEPENDENT_ROOT_SOURCE_BUILD_REVIEW_ONLY_PASS'
            and independent.get('candidate_source', {}).get('files_canonical_sha256') == BASE_CANONICAL_SHA256,
            'Actual41 independent source review differs')
    return review, manifest, {'base_review': file_binding(review_path),
        'original_source_manifest': file_binding(manifest_path), 'independent_review': file_binding(independent_path)}


def validate_empty_overlay(overlay, bindings):
    require(overlay == {'schema_version': 1, 'kind': OVERLAY_KIND,
            'base_review': bindings['base_review'], 'base_source_canonical_sha256': BASE_CANONICAL_SHA256,
            'source_root': str(SOURCE_ROOT), 'files': {}}, 'Explicit source-bound empty overlay required')


def checked_inventory_map(items, protected):
    require(isinstance(items, dict) and items, 'Missing whole-tree inventory')
    regular = {}
    for name, record in items.items():
        relative(name)
        require(not excluded(name) and isinstance(record, dict), 'Invalid whole-tree source entry')
        require(record.get('kind') in {'file', 'directory'}, 'Unreviewed source alias or special object')
        require(type(record.get('mode')) is int and 0 <= record['mode'] <= 0o7777, 'Invalid source mode')
        if record['kind'] == 'file':
            require(type(record.get('bytes')) is int and record['bytes'] >= 0, 'Invalid source file size')
            regular[name] = record.get('sha256')
    require(regular == protected, 'Whole-tree regular source files must equal the actual41 reviewed map')


def validate_proposal_authority(proposal):
    """Metadata-only receipt authorization, before loading any project modules."""
    review, manifest, bindings = load_baseline()
    require(proposal.get('schema_version') == 1 and proposal.get('kind') == KIND
            and proposal.get('source_root') == str(SOURCE_ROOT)
            and all(proposal.get(name) == value for name, value in bindings.items())
            and proposal.get('tool') == file_binding(Path(__file__).resolve()), 'Actual41 proposal authority differs')
    overlay_path = Path(proposal['overlay_manifest']['path'])
    require(proposal['overlay_manifest'] == file_binding(overlay_path)
            and read(overlay_path) == proposal.get('overlay'), 'Bound empty overlay changed')
    validate_empty_overlay(proposal['overlay'], bindings)
    require(proposal.get('original_protected_file_hashes') == review['files']
            and proposal.get('expected_protected_file_hashes') == review['files']
            and proposal.get('original_classified_source_hashes') == manifest['classified_source_hashes']
            and proposal.get('expected_classified_source_hashes') == manifest['classified_source_hashes']
            and proposal.get('expected_whole_tree_inventory') == proposal.get('original_whole_tree_inventory'),
            'An undeclared source/classified delta is forbidden')
    checked_inventory_map(proposal['original_whole_tree_inventory'], review['files'])
    require(proposal.get('preserved_runtime_library_hashes') == {name: review['files'][name] for name in RUNTIME_NAMES}
            and proposal.get('draft_planning_hashes') == {name: review['files'][name] for name in PLANNING}
            and proposal.get('freezer_exclusions') == list(EXCLUDES)
            and proposal.get('additional_exclusions') == ['/results'], 'Runtime/planning/copy exclusions differ')
    require(proposal.get('build_executed') is False and proposal.get('plans_created') is False
            and proposal.get('protocols_registered') is False and proposal.get('flights_executed') == 0
            and proposal.get('formal_seed_use') is False, 'Preparation scope differs')
    return review, manifest


def check_drafts_runtime(root, protected):
    for name in PLANNING:
        require(sha(root / name) == protected[name] and read(root / name).get('status') == DRAFT,
                'All three canonical planning files must retain their original DRAFT bytes: ' + name)
    protocol = read(root / PLANNING[0])
    require(protocol.get('magnetic_library_registration') == RUNTIME_NAMES[1], 'Actual Humble library registration differs')
    require(read(root / RUNTIME_NAMES[0]).get('source_root') == RUNTIME['px4_root']
            and read(root / RUNTIME_NAMES[2]).get('overlay_root') == RUNTIME['bridge_overlay'],
            'Do not rebase external PX4/bridge runtime paths to the new project root')


def build_proposal(source, destination, results, overlay_path):
    source, destination, results = map(Path, (source, destination, results))
    validate_paths(source, destination, results)
    review, original_manifest, bindings = load_baseline()
    protected = review['files']
    source_inventory = inventory(source)
    checked_inventory_map(source_inventory, protected)
    check_drafts_runtime(source, protected)
    exclusions = tuple(re.findall(r"--exclude='([^']+)'", (source / FREEZER).read_text(encoding='utf-8')))
    require(exclusions == EXCLUDES, 'Existing freezer exclusions changed; review the copy contract explicitly')
    classifier = frozen_classifier(source)
    classified = classifier.source_hashes(source)
    require(classified == original_manifest.get('classified_source_hashes')
            and all(protected.get(name) == value for name, value in classified.items()),
            'Development classified source map differs or includes unreviewed flight inputs')
    overlay_path = Path(overlay_path).resolve(strict=True)
    overlay = read(overlay_path)
    validate_empty_overlay(overlay, bindings)
    proposal = {'schema_version': 1, 'kind': KIND, 'scope': 'SOURCE_PREPARATION_ONLY_NOT_FINAL_FREEZE_OR_RUNTIME_ACCEPTANCE',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'source_root': str(source),
        'destination_root': str(destination), 'results_root': str(results), **bindings,
        'overlay_manifest': file_binding(overlay_path), 'overlay': overlay, 'freezer_exclusions': list(EXCLUDES),
        'additional_exclusions': ['/results'],
        'rsync_command': ['rsync', '-a', *('--exclude=' + value for value in EXCLUDES), '--exclude=/results',
                          '--', str(source) + '/', str(destination) + '/'],
        'original_whole_tree_inventory': source_inventory, 'expected_whole_tree_inventory': deepcopy(source_inventory),
        'original_protected_file_hashes': protected, 'expected_protected_file_hashes': dict(protected),
        'original_classified_source_hashes': classified, 'expected_classified_source_hashes': dict(classified),
        'flight_source_hashes': classifier.flight_source_hashes(classified),
        'preserved_runtime_library_hashes': {name: protected[name] for name in RUNTIME_NAMES},
        'draft_planning_hashes': {name: protected[name] for name in PLANNING},
        'tool': file_binding(Path(__file__).resolve()), 'build_executed': False, 'plans_created': False,
        'protocols_registered': False, 'flights_executed': 0, 'formal_seed_use': False,
        'claim_boundary': 'Source-copy proposal only; no capacity/closure/runtime/build/registration/flight/admission claim.'}
    validate_proposal_authority(proposal)
    return proposal


def verify_prepared(proposal):
    validate_proposal_authority(proposal)
    root, results = Path(proposal['destination_root']), Path(proposal['results_root'])
    require(root.is_dir() and not root.is_symlink() and results.is_dir() and not results.is_symlink()
            and (root / 'results').is_symlink() and (root / 'results').resolve(strict=True) == results,
            'New results binding changed')
    check_drafts_runtime(root, proposal['expected_protected_file_hashes'])
    actual = inventory(root)
    require(actual == proposal['expected_whole_tree_inventory'], 'Prepared whole-tree source inventory differs')
    require(all(actual.get(name, {}).get('sha256') == value
                for name, value in proposal['expected_protected_file_hashes'].items()),
            'Prepared protected source map differs')
    classifier = frozen_classifier(root)
    hashes = classifier.source_hashes(root)
    require(hashes == proposal['expected_classified_source_hashes']
            and classifier.flight_source_hashes(hashes) == proposal['flight_source_hashes'],
            'Prepared classified/flight source map differs')
    require(all(actual[name]['sha256'] == value for name, value in proposal['preserved_runtime_library_hashes'].items()),
            'Actual development runtime/library bytes changed')
    return {'whole_tree_entry_count': len(actual), 'protected_file_count': len(proposal['expected_protected_file_hashes']),
        'whole_tree_inventory_sha256': canonical(actual), 'classified_source_sha256': canonical(hashes),
        'flight_source_sha256': canonical(proposal['flight_source_hashes']), 'results_root': str(results)}


def apply_copy(proposal):
    """The sole mutation path; its only subprocess is the recorded rsync copy."""
    source, destination, results = map(Path, (proposal['source_root'], proposal['destination_root'], proposal['results_root']))
    validate_paths(source, destination, results)
    validate_proposal_authority(proposal)
    require(proposal['rsync_command'] == ['rsync', '-a', *('--exclude=' + value for value in EXCLUDES),
        '--exclude=/results', '--', str(source) + '/', str(destination) + '/'], 'Bound copy argv changed')
    for name in BOUND_INPUTS:
        require(file_binding(proposal[name]['path']) == proposal[name], 'Bound preparation input changed: ' + name)
    require(inventory(source) == proposal['original_whole_tree_inventory'], 'Original source changed before copy')
    for name, record in proposal['overlay']['files'].items():
        require(sha(Path(proposal['overlay']['source_root']) / name) == record['overlay_sha256'], 'Overlay changed before copy')
    destination.mkdir(exist_ok=False)
    results.mkdir(exist_ok=False)
    (destination / 'results').symlink_to(results, target_is_directory=True)
    validation = results / 'freeze_validation'
    validation.mkdir(exist_ok=False)
    write_new(validation / 'source_preparation_started.json', proposal)
    try:
        subprocess.run(proposal['rsync_command'], check=True, stdin=subprocess.DEVNULL)
        require((destination / 'results').is_symlink() and (destination / 'results').resolve(strict=True) == results,
                'Whole-tree copy replaced the explicitly bound new results link')
        for name, record in proposal['overlay']['files'].items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(proposal['overlay']['source_root']) / name, target)
            os.chmod(target, proposal['expected_whole_tree_inventory'][name]['mode'])
        verification = verify_prepared(proposal)
        require(inventory(source) == proposal['original_whole_tree_inventory'], 'Original source changed during copy')
        for name in BOUND_INPUTS:
            require(file_binding(proposal[name]['path']) == proposal[name], 'Bound preparation input changed during copy: ' + name)
        preparation_manifest = validation / 'source_sha256.txt'
        with preparation_manifest.open('x', encoding='utf-8', newline='\n') as stream:
            for name, digest in sorted(proposal['expected_protected_file_hashes'].items()):
                stream.write(digest + '  ' + name + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        outcome = {'schema_version': 1, 'kind': KIND, 'status': 'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED',
            'preparation_source_manifest': file_binding(preparation_manifest),
            'finished_utc': datetime.now(timezone.utc).isoformat(), 'proposal': proposal, 'source_verification': verification,
            'source_unchanged': True, 'build_executed': False, 'plans_created': False,
            'protocols_registered': False, 'flights_executed': 0, 'formal_seed_use': False,
            'claim_boundary': 'This is a preparation snapshot before future canonical registration. Keep it unchanged and seal a separate final source/planning manifest after all three registrations and formal definitions exist.'}
        write_new(validation / 'source_preparation_outcome.json', outcome)
        return outcome
    except BaseException as error:
        write_new(validation / 'source_preparation_failed.json', {'schema_version': 1, 'kind': KIND,
            'status': 'PREPARATION_FAILED_NO_RUNTIME_CLAIM', 'finished_utc': datetime.now(timezone.utc).isoformat(),
            'error': type(error).__name__ + ':' + str(error), 'existing_destinations_must_not_be_reused': True,
            'build_executed': False, 'protocols_registered': False, 'flights_executed': 0})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('inspect', 'copy'):
        command = sub.add_parser(action)
        command.add_argument('--source-root', type=Path, default=SOURCE_ROOT)
        command.add_argument('--destination-root', type=Path, required=True)
        command.add_argument('--results-store', type=Path, required=True)
        command.add_argument('--overlay-manifest', type=Path, required=True)
        if action == 'inspect':
            command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('verify')
    command.add_argument('--preparation-outcome', type=Path, required=True)
    args = parser.parse_args(argv)
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and EXTERNAL == LINUX_EXTERNAL, 'Use the isolated UAVHumble22 Linux distribution and canonical external tools')
    if args.action == 'verify':
        outcome = read(args.preparation_outcome)
        require(outcome.get('kind') == KIND and outcome.get('status') == 'SOURCE_COPY_VERIFIED_NOT_BUILT_OR_REGISTERED',
                'An actual successful preparation outcome is required')
        result = verify_prepared(outcome['proposal'])
        print(json.dumps({'kind': KIND, 'scope': 'PRE_REGISTRATION_SOURCE_RECHECK_ONLY', **result}), flush=True)
        return 0
    proposal = build_proposal(args.source_root, args.destination_root, args.results_store, args.overlay_manifest)
    if args.action == 'inspect':
        require(args.output.parent == EXTERNAL and args.output.suffix == '.json'
                and not args.output.exists() and not args.output.is_symlink(), 'Use an exclusive new external inspection JSON')
        write_new(args.output, proposal)
        print(json.dumps({'kind': KIND, 'action': 'INSPECT_ONLY_NO_ROOT_CREATED', 'output': str(args.output)}), flush=True)
    else:
        outcome = apply_copy(proposal)
        print(json.dumps({'kind': KIND, 'status': outcome['status'], 'root': proposal['destination_root'],
            'results': proposal['results_root'], 'build_executed': False, 'protocols_registered': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
