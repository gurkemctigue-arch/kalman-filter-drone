"""Read-only canonical development progress with explicit root/plan bindings.

Reuse the original slot scanner, PID identity and final-scan loop. This does
not start experiments, read bags, create admission, or compute a verdict.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re

import bridge_humble41_events01 as original
import bridge_formal280_events01 as reader

EXTERNAL = Path(__file__).resolve().parent
ORIGINAL_SHA = '94568d694a4379cd744343b13643d442abe67749bf3a7e34bf08cbef25d064aa'
READER_SHA = '0229bf564ec3609ee226b388e9024276516f76d05f8f9bdc110235c8ed18e270'
MONITOR_SHA = '759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98'
SCOPE = 'EXPLICIT_DEVELOPMENT_READONLY_PROGRESS_NOT_ADMISSION_OR_ACCEPTANCE'
CLASSES = ('person', 'car')
CONDITIONS = ('depth_noise', 'depth_holes', 'dropout', 'latency', 'combined',
              'speed_changes_velocity', 'speed_changes_position', 'far_distance')
require, sha = reader.require, original.sha


def tool_manifest():
    for module, name, digest in (
        (original, 'bridge_humble41_events01.py', ORIGINAL_SHA),
        (reader, 'bridge_formal280_events01.py', READER_SHA),
    ):
        require(Path(module.__file__).resolve(strict=True) == EXTERNAL/name
                and sha(module.__file__) == digest, 'Original read-only dependency changed')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {n: sha(EXTERNAL/n) for n in
                  ('bridge_development_events.py', 'test_bridge_development_events.py')},
        'original_loop_sha256': ORIGINAL_SHA, 'original_reader_sha256': READER_SHA,
        'monitor_helper_sha256': MONITOR_SHA, 'kind_counts': {'core': 12, 'extension': 16},
        'default_root': None, 'default_plan': None, 'default_pid': None,
        'runtime_or_formal_action': False, 'engineering_verdict_computed': False,
        'terminal_loop_scope': original.SCOPE}


class DevelopmentEvents(reader.PlanEvents):
    def __init__(self, path, expected_sha, *, root, prefix, kind):
        require(kind in ('core', 'extension')
                and re.fullmatch(r'/root/uav_tracking_fullplan_[A-Za-z0-9_]+', root or '')
                and re.fullmatch(r'[A-Za-z0-9_]+', prefix or '')
                and re.fullmatch(r'[0-9a-f]{64}', expected_sha or ''),
                'Explicit kind, original root, prefix and plan SHA required')
        path = Path(path).resolve(strict=True)
        source = reader.small_json(path)
        require(source is not None, 'Original plan is absent or unfinished')
        plan, binding = source
        groups = original.GROUPS if kind == 'core' else CONDITIONS
        dimensions = [(cls, group) for cls in CLASSES for group in groups]
        ids = [f'{cls}_{group}_seed004' if kind == 'core' else
               f'{cls}_extension_{group}_seed004' for cls, group in dimensions]
        require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1
                and plan.get('mode') == ('PROBE' if kind == 'core' else 'EXTENSION_PROBE')
                and plan.get('frozen_root') == root and plan.get('prefix') == prefix
                and binding['sha256'] == expected_sha
                and plan.get('plan_sha256') == reader.canonical(plan, 'plan_sha256')
                and plan.get('selected_classes') == list(CLASSES)
                and plan.get('selected_seeds') == [4] and type(plan['selected_seeds'][0]) is int
                and plan.get('selected_groups') == (list(original.GROUPS) if kind == 'core'
                                                       else ['stage1_velocity', 'stage1_position'])
                and isinstance(plan.get('trials'), list)
                and all(isinstance(t, dict) for t in plan['trials'])
                and [t.get('id') for t in plan['trials']] == ids,
                'Original plan binding, digest, dimensions or complete denominator differs')
        if kind == 'extension':
            require(plan.get('selected_extension_conditions') == list(CONDITIONS),
                    'Original extension conditions differ')
        require(all(t.get('target_class') == cls and
                t.get('group' if kind == 'core' else 'extension_condition') == group and
                type(t.get('seed')) is int and t['seed'] == 4 and
                isinstance(t.get('flight_command'), list) and t['flight_command'] and
                all(isinstance(token, str) for token in t['flight_command'])
                for t, (cls, group) in zip(plan['trials'], dimensions)),
                'Original trial identity or flight command differs')
        self.total, self.kind = len(ids), kind
        self.plans = [{'label': kind, 'path': path, 'plan': plan, 'binding': binding}]
        self.entries = [{'slot': t['id'], 'number': n, 'matrix_number': n,
            'matrix': kind, 'plan': plan, 'binding': binding,
            'slots': path.parent/'slots', 'trial': t}
            for n, t in enumerate(plan['trials'], 1)]
        self.seen, self.unclosed = set(), {}

    def header(self):
        return {'event': 'BRIDGE_BOUND_PLANS', 'utc': reader.now(), 'total': self.total,
                'plans': [p['binding'] for p in self.plans], 'scope': SCOPE, 'kind': self.kind}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'watch'))
    for name in ('project-root', 'plan', 'output'):
        parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'frozen-root', 'prefix', 'expected-start-token'):
        parser.add_argument('--'+name)
    parser.add_argument('--kind', choices=('core', 'extension'))
    parser.add_argument('--pid', type=int)
    parser.add_argument('--interval', type=float, default=5.)
    args = parser.parse_args(argv)
    manifest = tool_manifest()
    if args.action == 'describe':
        print(json.dumps({'tool_manifest': manifest,
            'tools_canonical_sha256': reader.canonical(manifest, None),
            'actual_action_executed': False}, indent=2))
        return 0
    require(all(getattr(args, name) is not None for name in
        ('project_root', 'plan', 'output', 'plan_sha256', 'frozen_root', 'prefix',
         'expected_start_token', 'kind', 'pid')), 'Explicit watch inputs required')
    path = args.project_root.resolve(strict=True)/'scripts/monitor_project_progress.py'
    require(path.is_file() and not path.is_symlink() and sha(path) == MONITOR_SHA,
            'Existing monitor helper differs')
    spec = importlib.util.spec_from_file_location('development_existing_monitor', path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    bridge = DevelopmentEvents(args.plan, args.plan_sha256, root=args.frozen_root,
                               prefix=args.prefix, kind=args.kind)
    result = original.run_bridge(bridge, args.output, pid=args.pid,
        expected_token=args.expected_start_token, identity_provider=monitor.process_identity,
        identity_checker=monitor.verify_process, interval=args.interval)
    print(json.dumps(result, indent=2))
    return 0 if result['error'] is None else 2


if __name__ == '__main__':
    raise SystemExit(main())
