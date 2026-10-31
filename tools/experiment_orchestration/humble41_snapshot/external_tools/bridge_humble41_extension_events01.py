"""Read original Humble41 EXTENSION_PROBE16 into existing monitor events.

Only plan binding/CLI are new. The reviewed scanner and PID/final-scan loop are
reused unchanged. No safety-registry support, scheduler, admission or verdict.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import bridge_humble41_events01 as core
import bridge_formal280_events01 as reader

EXTERNAL = Path(__file__).resolve().parent
ROOT = '/root/uav_tracking_fullplan_v4_humble41'
PREFIX = 'reliability_v4_humble41_extensions_probe'
SCOPE = 'HUMBLE41_EXTENSION16_READONLY_PROGRESS_NOT_ADMISSION_OR_ACCEPTANCE'
CORE_SHA = '94568d694a4379cd744343b13643d442abe67749bf3a7e34bf08cbef25d064aa'
READER_SHA = '0229bf564ec3609ee226b388e9024276516f76d05f8f9bdc110235c8ed18e270'
MONITOR_SHA = '759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98'
CLASSES = ('person', 'car')
CONDITIONS = ('depth_noise', 'depth_holes', 'dropout', 'latency', 'combined',
              'speed_changes_velocity', 'speed_changes_position', 'far_distance')
OWN = ('bridge_humble41_extension_events01.py', 'test_bridge_humble41_extension_events01.py')
require, sha, run_bridge = reader.require, core.sha, core.run_bridge

def tool_manifest():
    for module, name, digest in ((core, 'bridge_humble41_events01.py', CORE_SHA),
            (reader, 'bridge_formal280_events01.py', READER_SHA)):
        require(Path(module.__file__).resolve(strict=True) == EXTERNAL/name
                and sha(module.__file__) == digest, 'Reviewed read-only dependency changed')
    return {'schema_version': 1, 'scope': SCOPE,
        'files': {name: sha(EXTERNAL/name) for name in OWN},
        'reused_core_loop_sha256': CORE_SHA, 'reused_reader_sha256': READER_SHA,
        'monitor_helper_sha256': MONITOR_SHA, 'kind_counts': {'extension': 16},
        'terminal_scope': core.SCOPE, 'default_plan': None, 'default_pid': None,
        'scanner_and_loop_modified': False, 'engineering_verdict_computed': False,
        'consumes_prerequisite_results': False, 'runtime_or_formal_action': False}

class ExtensionEvents(reader.PlanEvents):
    def __init__(self, path, expected_sha):
        require(re.fullmatch('[0-9a-f]{64}', expected_sha or ''), 'Actual original plan file SHA required')
        path = Path(path).resolve(strict=True); source = reader.small_json(path)
        require(source is not None, 'Original extension plan is absent or unfinished')
        plan, binding = source
        dimensions = [(cls, condition) for cls in CLASSES for condition in CONDITIONS]
        ids = [f'{cls}_extension_{condition}_seed004' for cls, condition in dimensions]
        require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1
            and plan.get('mode') == 'EXTENSION_PROBE' and plan.get('frozen_root') == ROOT
            and plan.get('prefix') == PREFIX and binding['sha256'] == expected_sha
            and plan.get('plan_sha256') == reader.canonical(plan, 'plan_sha256')
            and plan.get('selected_classes') == list(CLASSES)
            and plan.get('selected_seeds') == [4] and type(plan['selected_seeds'][0]) is int
            and plan.get('selected_groups') == ['stage1_velocity', 'stage1_position']
            and plan.get('selected_extension_conditions') == list(CONDITIONS)
            and isinstance(plan.get('trials'), list) and all(isinstance(t, dict) for t in plan['trials'])
            and [t.get('id') for t in plan['trials']] == ids,
            'Original root41 extension16 mode/prefix/order/denominator or digest differs')
        require(all(t.get('target_class') == cls and t.get('extension_condition') == condition
            and type(t.get('seed')) is int and t['seed'] == 4
            and isinstance(t.get('flight_command'), list) and bool(t['flight_command'])
            and all(isinstance(token, str) for token in t['flight_command'])
            for t, (cls, condition) in zip(plan['trials'], dimensions)), 'Original trial class/extension condition/seed differs')
        self.total, self.kind = 16, 'extension'
        self.plans = [{'label': self.kind, 'path': path, 'plan': plan, 'binding': binding}]
        self.entries = [{'slot': t['id'], 'number': n, 'matrix_number': n, 'matrix': self.kind,
            'plan': plan, 'binding': binding, 'slots': path.parent/'slots', 'trial': t}
            for n, t in enumerate(plan['trials'], 1)]
        self.seen, self.unclosed = set(), {}

    def header(self):
        return {'event': 'BRIDGE_BOUND_PLANS', 'utc': reader.now(), 'total': self.total,
            'plans': [p['binding'] for p in self.plans], 'scope': SCOPE, 'kind': self.kind}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'watch'))
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--plan', type=Path); parser.add_argument('--plan-sha256')
    parser.add_argument('--pid', type=int); parser.add_argument('--expected-start-token')
    parser.add_argument('--output', type=Path); parser.add_argument('--interval', type=float, default=5.)
    args = parser.parse_args(argv); manifest = tool_manifest()
    if args.action == 'describe':
        print(json.dumps({'tool_manifest': manifest, 'tools_canonical_sha256': reader.canonical(manifest, None),
                          'actual_action_executed': False}, indent=2)); return 0
    require(all(v is not None for v in (args.project_root, args.plan, args.plan_sha256,
        args.pid, args.expected_start_token, args.output)), 'Explicit watch inputs required')
    path = args.project_root.resolve(strict=True)/'scripts/monitor_project_progress.py'
    require(path.is_file() and not path.is_symlink() and sha(path) == MONITOR_SHA, 'Existing monitor helper differs')
    spec = importlib.util.spec_from_file_location('humble41_extension_existing_monitor', path)
    monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)
    bridge = ExtensionEvents(args.plan, args.plan_sha256)
    result = run_bridge(bridge, args.output, pid=args.pid, expected_token=args.expected_start_token,
        identity_provider=monitor.process_identity, identity_checker=monitor.verify_process, interval=args.interval)
    print(json.dumps(result, indent=2)); return 0 if result['error'] is None else 2

if __name__ == '__main__':
    raise SystemExit(main())
