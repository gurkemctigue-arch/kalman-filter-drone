"""Adapter50 pacing registration and archived evidence; no ROS or simulation."""
from copy import deepcopy
import io
from contextlib import redirect_stderr
from itertools import permutations
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from scripts import run_stage1_trial as trial_runner
from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_guard as safety
from tests import test_reliability_v4_recovery_gates as gates

v4, builder, guard = fixtures.v4, gates.builder, safety.guard
VERSIONS = ('legacy', 'v1', 'v2')


def with_version(protocol, version):
    value = deepcopy(protocol)
    value.pop(v4.SIMULATION_PACING_FIELD, None)
    value.update(real_time_factor=.25, flight_wall_timeout_s=600.)
    if version != 'legacy':
        value[v4.SIMULATION_PACING_FIELD] = deepcopy(v4.SIMULATION_PACING_V1 if version == 'v1' else v4.SIMULATION_PACING_V2)
        value.update(real_time_factor=.125, flight_wall_timeout_s=1000.)
    return value


def policy_plan(version):
    result = gates.policy_plan()
    result['protocol'] = with_version(result['protocol'], version)
    return result


def archives(rate=50.):
    return ({v4.PX4_ADAPTER_PUBLISH_RATE_FIELD: rate}, {
        'uav_tracking_px4_adapter': {'ros__parameters': {'publish_rate_hz': rate}},
        'uav_tracking_controller': {'ros__parameters': {'control_rate_hz': 20.}},
        'uav_tracking_flight_supervisor': {'ros__parameters': {'publish_rate_hz': 20., 'heartbeat_prestream_s': 1.2,
            'native_takeoff_timeout_sim_s': 40., 'native_wall_timeout_s': 180.}}})


class AdapterPacingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.legacy = fixtures.fixture(self.root)

    def declare(self, version='v2'):
        value = with_version(self.legacy, version)
        fixtures.write(self.root/v4.PROTOCOL_PATH, value)
        return value

    def make(self, version='v2', **options):
        self.declare(version)
        return fixtures.make_fixture_plan(self.root, 'results/adapter_'+version, 'reliability_v4_adapter_'+version,
            classes=list(v4.CLASSES), seeds=[4], **options)

    def test_versions_keep_distinct_exact_contracts_and_historical20_defaults(self):
        for version in VERSIONS:
            protocol = self.declare(version); v4.validate_protocol(protocol)
            self.assertEqual(v4.simulation_pacing_adapter_publish_rate_hz(protocol), 50. if version == 'v2' else 20.)
        self.assertNotIn(v4.PX4_ADAPTER_PUBLISH_RATE_FIELD, v4.SIMULATION_PACING_V1)
        self.assertEqual(v4.SIMULATION_PACING_V1['revision'], 'simulation_rtf0125_wall1000_v1')
        original = self.declare()
        for value in (20., True, 0., float('nan'), float('inf')):
            changed = deepcopy(original); changed[v4.SIMULATION_PACING_FIELD][v4.PX4_ADAPTER_PUBLISH_RATE_FIELD] = value
            with self.subTest(value=value), self.assertRaises(ValueError): v4.validate_protocol(changed)
        for key in ('revision', v4.PX4_ADAPTER_PUBLISH_RATE_FIELD, 'scope'):
            changed = deepcopy(original); del changed[v4.SIMULATION_PACING_FIELD][key]
            with self.subTest(missing=key), self.assertRaises(ValueError): v4.validate_protocol(changed)
        changed = self.declare('v1'); changed[v4.SIMULATION_PACING_FIELD][v4.PX4_ADAPTER_PUBLISH_RATE_FIELD] = 50.
        with self.assertRaises(ValueError): v4.validate_protocol(changed)

    def test_core_and_extension_specs_explicitly_bind_only_v2_adapter50(self):
        core = self.make(groups=list(v4.GROUPS))
        fixtures.write(self.root/v4.EXTENSION_PROTOCOL_PATH, v4.load(fixtures.ROOT/v4.EXTENSION_PROTOCOL_PATH))
        with patch.object(v4, 'verify_external_runtime', side_effect=fixtures.fixture_runtime_verifier):
            extension = v4.make_extension_plan(self.root, 'results/adapter_extensions', 'reliability_v4_adapter_extensions', seeds=[4])
        self.assertEqual((len(core['trials']), len(extension['trials'])), (12, 16))
        for plan in (core, extension):
            v4.validate_plan(plan)
            for trial in plan['trials']:
                command = trial['flight_command']
                self.assertEqual(trial[v4.PX4_ADAPTER_PUBLISH_RATE_FIELD], 50.)
                self.assertEqual(trial[v4.SIMULATION_PACING_FIELD], v4.SIMULATION_PACING_V2)
                self.assertEqual(command.count(v4.PX4_ADAPTER_PUBLISH_RATE_FLAG), 1)
                self.assertEqual(float(command[command.index(v4.PX4_ADAPTER_PUBLISH_RATE_FLAG)+1]), 50.)
        for version in ('legacy', 'v1'):
            plan = self.make(version, groups=['stage1_velocity'])
            for trial in plan['trials']:
                self.assertNotIn(v4.PX4_ADAPTER_PUBLISH_RATE_FIELD, trial)
                self.assertNotIn(v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, trial['flight_command'])
            v4.validate_plan(plan)

    def test_resealed_v2_spec_or_argv_drift_and_hidden_legacy_flag_are_rejected(self):
        original = self.make(groups=['stage1_velocity'])
        for defect in ('spec_missing', 'spec20', 'flag_missing', 'flag20', 'duplicate', 'assignment', 'nan'):
            plan = deepcopy(original); trial = plan['trials'][0]; argv = trial['flight_command']
            index = argv.index(v4.PX4_ADAPTER_PUBLISH_RATE_FLAG)
            if defect == 'spec_missing': trial.pop(v4.PX4_ADAPTER_PUBLISH_RATE_FIELD)
            elif defect == 'spec20': trial[v4.PX4_ADAPTER_PUBLISH_RATE_FIELD] = 20.
            elif defect == 'flag_missing': del argv[index:index+2]
            elif defect == 'flag20': argv[index+1] = '20.0'
            elif defect == 'duplicate': argv.extend([v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, '50.0'])
            elif defect == 'assignment': argv.extend([v4.PX4_ADAPTER_PUBLISH_RATE_FLAG+'=50.0'])
            else: argv[index+1] = 'nan'
            plan['plan_sha256'] = v4.digest(plan, ('plan_sha256',))
            with self.subTest(defect=defect), self.assertRaises(ValueError): v4.validate_plan(plan)
            self.assertTrue(v4.runtime_configuration(plan, trial)['errors'])
        for version in ('legacy', 'v1'):
            plan = self.make(version, groups=['stage1_velocity'])
            plan['trials'][0]['flight_command'].extend([v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, '50.0'])
            plan['plan_sha256'] = v4.digest(plan, ('plan_sha256',))
            with self.subTest(version=version), self.assertRaises(ValueError): v4.validate_plan(plan)

    def test_actual_archived_configuration_and_yaml_drift_are_rejected(self):
        plan = self.make(groups=['stage1_velocity']); trial = plan['trials'][0]
        fixtures.FakeCommands()(trial['flight_command'], self.root/'runtime.log', self.root, 1.)
        directory = Path(trial['directory']); config_path = directory/'run_config.json'; yaml_path = directory/'configuration/runtime_parameters.yaml'
        original_config, original_parameters = v4.load(config_path), v4.load(yaml_path)
        self.assertEqual(v4.runtime_configuration(plan, trial)['errors'], [])
        changes = [('config', None, 20.), ('config', None, True), ('config', None, 'missing'),
            ('uav_tracking_px4_adapter', 'publish_rate_hz', 20.), ('uav_tracking_px4_adapter', 'publish_rate_hz', 'missing'),
            ('uav_tracking_controller', 'control_rate_hz', 50.), ('uav_tracking_flight_supervisor', 'publish_rate_hz', 50.),
            ('uav_tracking_flight_supervisor', 'heartbeat_prestream_s', 0.),
            ('uav_tracking_flight_supervisor', 'heartbeat_prestream_s', 'missing'),
            ('uav_tracking_flight_supervisor', 'native_takeoff_timeout_sim_s', 1000.),
            ('uav_tracking_flight_supervisor', 'native_takeoff_timeout_sim_s', 'missing'),
            ('uav_tracking_flight_supervisor', 'native_wall_timeout_s', 1000.)]
        for node, key, value in changes:
            config, parameters = deepcopy(original_config), deepcopy(original_parameters)
            container = config if node == 'config' else parameters[node]['ros__parameters']
            key = v4.PX4_ADAPTER_PUBLISH_RATE_FIELD if node == 'config' else key
            if value == 'missing': container.pop(key)
            else: container[key] = value
            fixtures.write(config_path, config); fixtures.write(yaml_path, parameters)
            with self.subTest(node=node, key=key, value=value):
                self.assertTrue(any(key in error for error in v4.runtime_configuration(plan, trial)['errors']))

    def test_historical20_archives_can_omit_defaults_but_cannot_smuggle50(self):
        for version in ('legacy', 'v1'):
            protocol = self.declare(version)
            self.assertEqual(v4.simulation_pacing_runtime_evidence(protocol, {}, {}, [])['errors'], [])
            config, parameters = archives(20.)
            self.assertEqual(v4.simulation_pacing_runtime_evidence(protocol, config, parameters, [])['errors'], [])
            config[v4.PX4_ADAPTER_PUBLISH_RATE_FIELD] = 50.
            self.assertTrue(v4.simulation_pacing_runtime_evidence(protocol, config, parameters, [])['errors'])
            config, parameters = archives(20.); parameters['uav_tracking_px4_adapter']['ros__parameters']['publish_rate_hz'] = 50.
            self.assertTrue(v4.simulation_pacing_runtime_evidence(protocol, config, parameters, [])['errors'])
            config, parameters = archives(20.)
            self.assertTrue(v4.simulation_pacing_runtime_evidence(protocol, config, parameters,
                [v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, '50.0'])['errors'])
            for key, value in (('heartbeat_prestream_s', 0.), ('native_takeoff_timeout_sim_s', 1000.)):
                config, parameters = archives(20.)
                parameters['uav_tracking_flight_supervisor']['ros__parameters'][key] = value
                with self.subTest(version=version, key=key):
                    self.assertTrue(v4.simulation_pacing_runtime_evidence(protocol, config, parameters, [])['errors'])

    def test_trial_parameter_hook_only_changes_adapter_rate_and_archives_existing_loop_defaults(self):
        for rate in (20., 50.):
            parameters = {node: {'ros__parameters': {}} for node in
                ('uav_tracking_px4_adapter', 'uav_tracking_controller', 'uav_tracking_flight_supervisor')}
            parameters['uav_tracking_flight_supervisor']['ros__parameters']['native_wall_timeout_s'] = 180.
            trial_runner.apply_px4_adapter_publish_rate(parameters, rate)
            self.assertEqual(parameters['uav_tracking_px4_adapter']['ros__parameters']['publish_rate_hz'], rate)
            self.assertEqual(parameters['uav_tracking_controller']['ros__parameters']['control_rate_hz'], 20.)
            self.assertEqual(parameters['uav_tracking_flight_supervisor']['ros__parameters']['publish_rate_hz'], 20.)
            self.assertEqual(parameters['uav_tracking_flight_supervisor']['ros__parameters']['heartbeat_prestream_s'], 1.2)
            self.assertEqual(parameters['uav_tracking_flight_supervisor']['ros__parameters']['native_wall_timeout_s'], 180.)
        for value in (True, None, '50', 0., 49., float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError): trial_runner.apply_px4_adapter_publish_rate({}, value)
        with patch('sys.argv', ['run_stage1_trial.py', '--name', 'must_not_exist', '--px4-adapter-publish-rate-hz', '49']), \
                patch.object(trial_runner.subprocess, 'Popen') as spawned, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            trial_runner.main()
        spawned.assert_not_called()

    def test_core_extension_and_gimbal_gates_refuse_every_cross_version_direction(self):
        for target_version, previous_version in permutations(VERSIONS, 2):
            target, previous = policy_plan(target_version), policy_plan(previous_version)
            with tempfile.TemporaryDirectory() as temporary:
                path, output = Path(temporary)/'probe.json', Path(temporary)/'must_not_write.json'
                path.write_text('{}', encoding='utf-8')
                for extension in (False, True):
                    with self.subTest(target=target_version, previous=previous_version, extension=extension), \
                            patch.object(builder, 'read_plan', return_value=(path, previous)), \
                            patch.object(v4, 'read_slots', side_effect=AssertionError('Reject before slot reads')), \
                            self.assertRaisesRegex(ValueError, 'simulation pacing policy'):
                        builder.assemble(target, [path], extension=extension,
                            registration_utc=v4.utc_now() if extension else None)
                with patch.object(builder, 'target_snapshot', return_value=(path, target, {})), \
                        patch.object(builder, 'read_plan', return_value=(path, previous)), \
                        self.assertRaisesRegex(ValueError, 'simulation pacing policy'):
                    builder.register_gimbal_reevaluations(path, path, output)
                self.assertFalse(output.exists())
        self.assertNotEqual(builder.bindings(policy_plan('v1'))['simulation_pacing_sha256'],
                            builder.bindings(policy_plan('v2'))['simulation_pacing_sha256'])

    def test_safety_shared_validator_and_old_runner_fallback_never_admit_v2_as_v1(self):
        current = SimpleNamespace(v4=SimpleNamespace(simulation_pacing_runtime_evidence=v4.simulation_pacing_runtime_evidence))
        old = SimpleNamespace(v4=SimpleNamespace(simulation_pacing_summary=v4.simulation_pacing_summary))
        for version in VERSIONS:
            protocol = self.declare(version); config, parameters = archives(50. if version == 'v2' else 20.)
            argv = [v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, '50.0'] if version == 'v2' else []
            self.assertEqual(guard.simulation_pacing_evidence(current, protocol, config, parameters, argv),
                             50. if version == 'v2' else 20.)
            if version == 'v2':
                with self.assertRaises(guard.Refusal): guard.simulation_pacing_evidence(old, protocol, config, parameters, argv)
            else:
                self.assertEqual(guard.simulation_pacing_evidence(old, protocol, {}, {}, []), 20.)
                for key, value in (('heartbeat_prestream_s', 0.), ('native_takeoff_timeout_sim_s', 1000.)):
                    invalid = deepcopy(parameters)
                    invalid['uav_tracking_flight_supervisor']['ros__parameters'][key] = value
                    with self.subTest(version=version, key=key), self.assertRaises(guard.Refusal):
                        guard.simulation_pacing_evidence(old, protocol, config, invalid, [])
            parameters['uav_tracking_px4_adapter']['ros__parameters']['publish_rate_hz'] = 20. if version == 'v2' else 50.
            with self.assertRaises(guard.Refusal): guard.simulation_pacing_evidence(current, protocol, config, parameters, argv)

    def test_runner_admission_refuses_all_cross_version_sources_before_terminal_records(self):
        for index, (target_version, previous_version) in enumerate(permutations(VERSIONS, 2)):
            target, previous = policy_plan(target_version), policy_plan(previous_version)
            previous['mode'] = 'PROBE'
            source = self.root/('previous_'+str(index)+'.json'); fixtures.write(source, previous)
            gate = {'schema_version': 2, 'result': 'PASS', 'ready_for_formal_reliability_v4': True,
                'checks': {name: True for name in v4.PROBE_CHECKS}, 'bindings': builder.bindings(target),
                'probe_slots': [{'plan_path': str(source), 'plan_file_sha256': v4.sha(source), 'slot_id': 'inert'}]}
            path = self.root/('gate_'+str(index)+'.json'); fixtures.write(path, gate)
            target['development_probe_gate'] = {'path': str(path), 'sha256': v4.sha(path), 'evidence': gate}
            with self.subTest(target=target_version, previous=previous_version), patch.object(v4, 'validate_plan'), \
                    patch.object(v4, 'read_slots', side_effect=AssertionError('Mismatch must precede record reads')), \
                    self.assertRaisesRegex(ValueError, 'simulation pacing differs'):
                v4.validate_probe_gate(target)

    def test_four_safety_slots_require_actual_explicit_v2_archives_and_registry_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest, context, runtime, summary, facts, calls = safety.safety_fixture(Path(temporary))
            context.core['protocol'] = with_version(context.core['protocol'], 'v2')
            runtime.v4.simulation_pacing_runtime_evidence = v4.simulation_pacing_runtime_evidence
            context.gate_bindings['simulation_pacing_sha256'] = v4.digest(v4.simulation_pacing_summary(context.core['protocol']))
            registry = guard.load(facts['registry']['path'])
            for slot in facts['slots']:
                binding = slot['evidence']['run_config']; config = guard.load(binding['path'])
                config.update(real_time_factor=.125, wall_timeout=1000., px4_adapter_publish_rate_hz=50.)
                slot['evidence']['run_config'] = safety.write(Path(binding['path']), config)
                path = Path(slot['evidence']['runtime_parameters']['path']); parameters = yaml.safe_load(path.read_text(encoding='utf-8'))
                _, rates = archives()
                for node, values in rates.items(): parameters[node]['ros__parameters'].update(values['ros__parameters'])
                parameters['uav_tracking_flight_supervisor']['ros__parameters']['requested_simulation_real_time_factor'] = .125
                path.write_text(yaml.safe_dump(parameters), encoding='utf-8'); slot['evidence']['runtime_parameters'] = guard.file_binding(path)
                argv = slot['executions']['flight']['argv']
                argv[argv.index('--real-time-factor')+1] = '.125'; argv[argv.index('--wall-timeout')+1] = '1000.0'
                argv.extend([v4.PX4_ADAPTER_PUBLISH_RATE_FLAG, '50.0'])
                next(row for row in registry['trials'] if row['id'] == slot['id'])['flight_argv'] = list(argv)
            facts['registry'] = safety.write(Path(facts['registry']['path']), registry)
            safety.SafetyTests.refresh(manifest, summary, facts)
            guard.validate_safety(manifest, context, runtime)
            self.assertEqual(len(calls), 4)


if __name__ == '__main__': unittest.main()
