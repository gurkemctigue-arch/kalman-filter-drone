"""Reproduce the observed slowed-simulation guard failure without ROS or GT."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

from scripts.run_stage1_trial import supervisor_stream_timing
from tests import test_flight_supervisor as fixtures
from tests import test_reliability_v4_runner as runner_fixtures
from tests import test_reliability_v4_probe_gate as gate_fixtures

flight = fixtures.flight
v4 = runner_fixtures.v4
ROOT = Path(__file__).resolve().parents[1]


class SupervisorStreamTests(unittest.TestCase):
    def node(self, source_s=60.252):
        case = fixtures.FlightHandoffTests("test_fresh_command_forwarded_only_after_takeoff_phase")
        node = case.source_supervisor(source_s)
        node._test_params.update(supervisor_stream_timing("source_sim", .125),
                                 simulation_only=True, use_sim_time=True)
        node._configure_stream_timing()
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(node._test_source_s*1e9), to_msg=lambda: self.stamp(node._test_source_s)))
        node._odom.header = SimpleNamespace(stamp=self.stamp(source_s-.08))
        with patch.object(flight.time, "monotonic", return_value=1977.649831669):
            node._on_odom(node._odom)
        command = fixtures.FakeCommand()
        command.header.stamp = self.stamp(source_s-.052)
        with patch.object(flight.time, "monotonic", return_value=1977.762868270):
            node._on_command(command)
        case.receive_source_status(node, round((source_s-.3)*1e6), 1975.378186173)
        return node

    @staticmethod
    def stamp(source_s):
        ns = round(source_s*1e9)
        return SimpleNamespace(sec=ns//10**9, nanosec=ns % 10**9)

    def command(self, node, stamp_s, wall_s, valid=True):
        message = fixtures.FakeCommand()
        message.header.stamp = self.stamp(stamp_s)
        message.valid = valid
        with patch.object(flight.time, "monotonic", return_value=wall_s):
            node._on_command(message)
        return message

    def tick(self, node, wall=1978.382348639):
        with patch.object(flight, "TrackingCommand", fixtures.FakeCommand, create=True), \
             patch.object(flight, "VehicleStatus", SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14), create=True), \
             patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
             patch.object(flight.time, "monotonic", return_value=wall):
            node._tick()

    def watchdog(self, node, wall):
        with patch.object(flight, "TrackingCommand", fixtures.FakeCommand, create=True), \
             patch.object(flight, "VehicleStatus", SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14), create=True), \
             patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
             patch.object(flight.time, "monotonic", return_value=wall):
            node._stream_wall_watchdog()

    def test_observed_733ms_wall_80ms_source_case_keeps_follow(self):
        node = self.node()
        self.tick(node)
        self.assertEqual(node._phase, "FOLLOW")
        self.assertTrue(node.last_output.valid)
        self.assertAlmostEqual(1978.382348639-node._odom_received, .732516970)
        self.assertIn("odom_age_source_s=0.080", node._state_snapshot(1978.382348639))
        self.assertIn("odom_limit_s=4.000", node._state_snapshot(1978.382348639))

    def test_recorded_source_cadence_with_synthetic_slow_receipt_does_not_create_hold(self):
        node = self.node(60.152)
        # This callback receipt is a synthetic counterexample. The original
        # bag records command source cadence, not supervisor command receipt.
        node._command_received = 1976.562642054
        self.tick(node, 1977.131642987)
        self.assertEqual(node._phase, "FOLLOW")
        node._stream_timestamp_mode = "receipt_wall"
        node._test_params["command_timeout_s"] = .5
        self.tick(node, 1977.131642987)
        self.assertEqual(node._phase, "HOLD")

    def test_actual_source_expiration_and_future_limits_still_reject(self):
        for stream in ("odometry", "command"):
            for stamp_s, expected in ((59.752, []), (59.751999999, [stream+"_source_stale"]),
                                      (60.302, []), (60.302000001, [stream+"_source_future"])):
                with self.subTest(stream=stream, stamp=stamp_s):
                    node = self.node()
                    message = SimpleNamespace(header=SimpleNamespace(stamp=self.stamp(stamp_s)))
                    self.assertEqual(node._source_stream_issues(stream, message), expected)

    def test_source_old_odometry_aborts_even_when_receipt_is_fresh(self):
        node = self.node()
        node._odom.header.stamp = self.stamp(59.751999999)
        node._odom_received = 1978.3823
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("odometry_source_stale", node._reason)

    def test_source_old_command_holds_without_aborting(self):
        node = self.node()
        node._controller_command.header.stamp = self.stamp(59.751999999)
        node._command_received = 1978.3823
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertTrue(node.last_output.valid)
        self.assertEqual(node._command_last_issues, ["command_source_stale"])

    def test_wall_watchdog_detects_paused_clock_and_publishes_only_once(self):
        node = self.node()
        outputs = []
        node._flight_pub = SimpleNamespace(publish=outputs.append)
        self.watchdog(node, node._odom_received+4.)
        self.assertEqual(outputs, [])
        self.watchdog(node, node._odom_received+4.000001)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("odometry_receipt_wall_stale", node._reason)
        self.assertEqual(len(outputs), 1)
        self.assertFalse(outputs[0].valid)
        self.watchdog(node, node._odom_received+8.)
        self.assertEqual(len(outputs), 1)

    def test_command_stopped_stream_keeps_original_hold_and_is_not_watchdog_abort(self):
        node = self.node()
        node._command_received = 1970.
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertEqual(node._command_last_issues, ["command_receipt_wall_stale"])
        self.watchdog(node, 1978.4)
        self.assertEqual(node._phase, "HOLD")

    def test_steady_reuses_original_status_and_vehicle_guards_only_during_follow_hold(self):
        for defect,expected in (("source_age","status_source_stale"),
                                ("wall_age","status_receipt_wall_stale"),
                                ("future","status_source_future"), ("failsafe","failsafe"),
                                ("disarmed","disarmed"), ("offboard","offboard_exited")):
            with self.subTest(defect=defect):
                node=self.node()
                if defect=="source_age":node._status.timestamp=59_251_000
                elif defect=="wall_age":node._status_received=1968.
                elif defect=="future":node._status.timestamp=60_303_000
                elif defect=="failsafe":node._status.failsafe=True
                elif defect=="disarmed":node._status.arming_state=1
                else:node._status.nav_state=4
                self.watchdog(node,1978.382348639)
                self.assertEqual(node._phase,"ABORTED")
                self.assertIn(expected,node._reason)
        node=self.node()
        node._phase="NATIVE_TAKEOFF"
        node._status.nav_state=17
        self.watchdog(node,1990.)
        self.assertEqual(node._phase,"NATIVE_TAKEOFF")
        self.assertFalse(hasattr(node,"last_output"))

    def test_duplicate_invalid_future_and_regression_do_not_refresh_receipt(self):
        for kind in ("duplicate", "invalid", "future", "regression"):
            with self.subTest(kind=kind):
                node = self.node()
                previous = node._controller_command
                received = node._command_received
                message = fixtures.FakeCommand()
                source = {"duplicate":60.2, "future":60.302000001, "regression":60.199999999}.get(kind, 60.2)
                message.header.stamp = self.stamp(source)
                if kind == "invalid": message.header.stamp.nanosec = -1
                with patch.object(flight.time, "monotonic", return_value=1978.3):
                    node._on_command(message)
                self.assertIs(node._controller_command, previous)
                self.assertEqual(node._command_received, received)
                self.assertNotEqual(node._stream_last_rejection["command"], "none")
                if kind == "regression":
                    self.command(node, 60.252, 1978.35)
                    self.assertEqual(node._command_received, received)
                    self.watchdog(node, 1978.4)
                    self.assertIn("command_source_clock_regression_restart_required", node._reason)

    def test_odom_rejected_header_cannot_refresh_receipt_or_recover_regression(self):
        for delta in (0., -.001, .131000001):
            node = self.node()
            previous, receipt = node._odom, node._odom_received
            message = deepcopy(previous)
            message.header.stamp = self.stamp(60.172+delta)
            with patch.object(flight.time, "monotonic", return_value=1978.3):
                node._on_odom(message)
            self.assertIs(node._odom, previous)
            self.assertEqual(node._odom_received, receipt)

    def test_ros_clock_regression_latches_without_new_message(self):
        node = self.node()
        node._test_source_s = 60.251
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("source_clock_regression_restart_required", node._reason)
        node._test_source_s = 60.253
        self.assertIn("odometry_source_clock_regression_restart_required", node._odometry_timing_issues(1978.4))

    def test_invalid_stop_intent_immediately_cancels_old_valid_even_if_header_rejected(self):
        node = self.node()
        receipt = node._command_received
        self.command(node, 60.4, 1978.3, valid=False)
        self.assertEqual(node._command_received, receipt)
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.command(node, 60.4, 1978.35, valid=True)
        self.assertFalse(node._controller_is_fresh(1978.4))
        self.command(node, 60.252, 1978.36)
        self.tick(node)
        self.assertEqual(node._phase, "FOLLOW")

    def test_fresh_invalid_control_intent_holds_and_remains_channel_activity(self):
        node = self.node()
        self.command(node, 60.252, 1978.3, valid=False)
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertEqual(node._command_received, 1978.3)
        self.assertFalse(node._controller_command.valid)

    def test_source_mode_is_explicit_simulation_only_and_limits_are_finite_bounded(self):
        for key, value in (("simulation_only",False), ("use_sim_time",False),
                           ("odometry_source_max_age_s", .500001), ("command_source_max_future_s", .050001),
                           ("command_timeout_s", 10.001), ("odometry_timeout_s", float("nan")),
                           ("odometry_timeout_s", True)):
            with self.subTest(key=key, value=value):
                node = self.node()
                node._test_params[key] = value
                with self.assertRaises((RuntimeError,ValueError)):
                    node._configure_stream_timing()

    def test_diagnostics_record_actual_source_age_and_callback_receipt_separately(self):
        node=self.node()
        self.tick(node)
        node._diagnostics_pub=SimpleNamespace(publish=lambda message:setattr(node,"report",message.data))
        with patch.object(flight,"String",lambda:SimpleNamespace(data=""),create=True), \
             patch.object(flight.time,"monotonic",return_value=1978.382348639):
            node._publish_supervisor_diagnostics()
        report=json.loads(node.report)
        self.assertEqual(report["stream_timestamp_mode"],"source_sim")
        self.assertAlmostEqual(report["odometry"]["age_source_s"],.08)
        self.assertAlmostEqual(report["odometry"]["age_wall_s"],.732516970)
        self.assertAlmostEqual(report["command"]["age_source_s"],.052)
        self.assertEqual(report["command"]["received_wall_monotonic_s"],1977.762868270)
        self.assertEqual(report["guard_limits"]["command_source_age_s"],.5)
        self.assertEqual(report["guard_limits"]["command_wall_s"],4.)
        self.assertEqual(report["stream_watchdog_contract"]["executor"],
                         "SAME_SINGLE_THREADED_EXECUTOR_AS_CONTROL")

    def test_legacy_custom_command_timeout_preserves_both_old_gates(self):
        case = fixtures.FlightHandoffTests("test_fresh_command_forwarded_only_after_takeoff_phase")
        node = case.supervisor()
        node._test_params["command_timeout_s"] = 2.
        node._command_received = 98.5
        node._controller_command.header.stamp = self.stamp(40.5)
        with patch.object(flight, "TrackingCommand", fixtures.FakeCommand, create=True):
            self.assertTrue(node._controller_is_fresh(100.))
            node._controller_command.header.stamp = self.stamp(39.999999999)
            self.assertFalse(node._controller_is_fresh(100.))
            node._controller_command.header.stamp = self.stamp(42.)
            node._command_received = 97.999999999
            self.assertFalse(node._controller_is_fresh(100.))

    def test_steady_watchdog_wiring_is_same_executor_without_normal_tick(self):
        node = self.node()
        calls = []
        node.create_timer = lambda period, callback, *, clock: calls.append((period,callback,clock))
        with patch.object(flight, "ClockType", SimpleNamespace(STEADY_TIME="STEADY"), create=True), \
             patch.object(flight, "Clock", lambda *, clock_type: clock_type, create=True):
            node._create_stream_watchdog_timer()
        self.assertEqual(calls, [(.1,node._stream_wall_watchdog,"STEADY")])
        self.watchdog(node, 1978.)
        self.assertFalse(hasattr(node,"last_output"))


class StreamRegistrationTests(unittest.TestCase):
    def test_requested_rtf_only_plans_bounded_wall_budget_and_source_limits_do_not_scale(self):
        for rtf, wall in ((1.,.5),(.125,4.),(.05,10.)):
            values = supervisor_stream_timing("source_sim",rtf)
            self.assertEqual(values["command_timeout_s"],wall)
            self.assertEqual(values["odometry_timeout_s"],wall)
            self.assertEqual(values["command_source_max_age_s"],.5)
            self.assertEqual(values["odometry_source_max_future_s"],.05)
        for rtf in (.049,0.,1.01,float("nan"),float("inf"),True):
            with self.subTest(rtf=rtf), self.assertRaises(ValueError):
                supervisor_stream_timing("source_sim",rtf)
        with self.assertRaises(ValueError): supervisor_stream_timing("source_sim",.125,"receipt")
        self.assertEqual(supervisor_stream_timing("receipt_wall",.125),{"stream_timestamp_mode":"receipt_wall"})
        self.assertEqual(supervisor_stream_timing(None,.125,"source_sim"),
                         supervisor_stream_timing("source_sim",.125))
        self.assertEqual(supervisor_stream_timing(None,.125,"receipt"),
                         {"stream_timestamp_mode":"receipt_wall"})

    def test_real_registration_binds_every_parameter_and_cannot_relax_either_source_gate(self):
        protocol = v4.load(ROOT/v4.PROTOCOL_PATH)
        registration = v4.supervisor_stream_summary(protocol)
        self.assertEqual(v4.supervisor_stream_parameters(protocol),supervisor_stream_timing("source_sim",.125))
        trial = v4.trial_spec(ROOT,protocol,"candidate", "person","stage1_position",4,1000.)
        v4.supervisor_stream_trial_binding(protocol,trial)
        self.assertEqual(trial[v4.SUPERVISOR_STREAM_FIELD],registration)
        for key,value in (("command_source_max_age_s",.6),("odometry_source_max_future_s",.051),
                          ("command_timeout_wall_s",4.01),("receipt_wall_max_s",11.),("revision","other")):
            changed = deepcopy(protocol)
            changed[v4.SUPERVISOR_STREAM_FIELD][key] = value
            with self.subTest(key=key),self.assertRaises(ValueError): v4.validate_protocol(changed)
        changed=deepcopy(trial); changed["flight_command"].remove(v4.SUPERVISOR_STREAM_FLAG)
        with self.assertRaises(ValueError): v4.supervisor_stream_trial_binding(protocol,changed)

    def test_historical_protocol_never_implicitly_enables_new_source_mode(self):
        protocol=v4.load(ROOT/v4.PROTOCOL_PATH)
        protocol.pop(v4.SUPERVISOR_STREAM_FIELD)
        trial=v4.trial_spec(ROOT,protocol,"legacy", "person","stage1_position",4,1000.)
        self.assertIsNone(v4.supervisor_stream_summary(protocol))
        command=trial["flight_command"]
        self.assertEqual(command[command.index(v4.SUPERVISOR_STREAM_FLAG)+1],"receipt_wall")
        v4.supervisor_stream_trial_binding(protocol,trial)
        self.assertEqual(v4.supervisor_stream_parameters(protocol),{"stream_timestamp_mode":"receipt_wall"})
        trial["flight_command"][trial["flight_command"].index(v4.SUPERVISOR_STREAM_FLAG)+1]="source_sim"
        with self.assertRaises(ValueError):v4.supervisor_stream_trial_binding(protocol,trial)

    def test_readiness_binds_clock_policy_and_rejects_historical_clock_evidence(self):
        protocol=v4.load(ROOT/v4.PROTOCOL_PATH)
        candidate={"protocol":protocol,"source_hashes":{},"model_hashes":{},
                   "magnetic_runtime_binding":{"manifest_sha256":"a"*64},
                   "magnetic_library_binding":{"registration_sha256":"b"*64}}
        bindings=gate_fixtures.builder.bindings(candidate)
        self.assertEqual(bindings["supervisor_stream_timing_sha256"],
                         v4.digest(v4.supervisor_stream_summary(protocol)))
        legacy=deepcopy(candidate); legacy["protocol"].pop(v4.SUPERVISOR_STREAM_FIELD)
        self.assertNotIn("supervisor_stream_timing_sha256",gate_fixtures.builder.bindings(legacy))
        with self.assertRaisesRegex(ValueError,"supervisor stream timing"):
            gate_fixtures.builder.matching_pacing_policy(candidate,legacy)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"gate.json"
            bindings.pop("supervisor_stream_timing_sha256")
            evidence={"schema_version":2,"result":"PASS","ready_for_formal_reliability_v4":True,
                      "checks":{name:True for name in v4.PROBE_CHECKS},"bindings":bindings}
            runner_fixtures.write(path,evidence)
            candidate["development_probe_gate"]={"path":str(path),"sha256":v4.sha(path),"evidence":evidence}
            with self.assertRaisesRegex(ValueError,"binding differs"):
                v4.validate_probe_gate(candidate)

    def test_actual_archived_config_and_yaml_cannot_omit_or_reinterpret_any_new_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner_fixtures.fixture(root)
            protocol = v4.load(root/v4.PROTOCOL_PATH)
            registration = deepcopy(v4.load(ROOT/v4.PROTOCOL_PATH)[v4.SUPERVISOR_STREAM_FIELD])
            registration.update(odometry_timeout_wall_s=2.,command_timeout_wall_s=2.)
            protocol[v4.SUPERVISOR_STREAM_FIELD] = registration
            runner_fixtures.write(root/v4.PROTOCOL_PATH,protocol)
            frozen = runner_fixtures.plan(root,classes=["person"],groups=["stage1_position"],seeds=[4],persist=False)
            trial = frozen["trials"][0]
            runner_fixtures.FakeCommands()(trial["flight_command"],root/"synthetic.log",root,1.)
            directory = Path(trial["directory"])
            config_path = directory/"run_config.json"
            yaml_path = directory/"configuration/runtime_parameters.yaml"
            config = v4.load(config_path)
            parameters = v4.load(yaml_path)
            values = supervisor_stream_timing("source_sim",.25)
            config.update(supervisor_stream_timestamp_mode="source_sim",supervisor_stream_timing=values)
            parameters["uav_tracking_flight_supervisor"]["ros__parameters"].update(values,use_sim_time=True)
            def save(arguments,runtime):
                runner_fixtures.write(config_path,arguments)
                runner_fixtures.write(yaml_path,runtime)
            save(config,parameters)
            self.assertEqual(v4.runtime_configuration(frozen,trial)["errors"],[])
            for key in values:
                for mutation in ("missing","wrong"):
                    with self.subTest(key=key,mutation=mutation):
                        runtime=deepcopy(parameters)
                        node=runtime["uav_tracking_flight_supervisor"]["ros__parameters"]
                        if mutation=="missing": node.pop(key)
                        else: node[key]="receipt_wall" if isinstance(values[key],str) else values[key]+.001
                        save(config,runtime)
                        self.assertIn("runtime_parameters:uav_tracking_flight_supervisor:"+key,
                                      v4.runtime_configuration(frozen,trial)["errors"])
            for key in ("supervisor_stream_timestamp_mode","supervisor_stream_timing"):
                arguments=deepcopy(config); arguments.pop(key); save(arguments,parameters)
                self.assertIn("run_config:"+key,v4.runtime_configuration(frozen,trial)["errors"])
            runtime=deepcopy(parameters)
            runtime["uav_tracking_flight_supervisor"]["ros__parameters"]["use_sim_time"]=False
            save(config,runtime)
            self.assertIn("runtime_parameters:uav_tracking_flight_supervisor:use_sim_time",
                          v4.runtime_configuration(frozen,trial)["errors"])
            runtime=deepcopy(parameters)
            runtime["uav_tracking_flight_supervisor"]["ros__parameters"]["simulation_only"]=False
            save(config,runtime)
            self.assertIn("runtime_parameters:uav_tracking_flight_supervisor:simulation_only",
                          v4.runtime_configuration(frozen,trial)["errors"])


if __name__ == "__main__":
    unittest.main()
