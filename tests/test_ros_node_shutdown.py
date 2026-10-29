"""Exercise production entrypoint cleanup with an already stopped ROS context.

Only the real main() AST is loaded: no ROS, native inference, simulator or
flight code is started. The final integrated signal behavior remains a
separate end-to-end check after the frozen research run.
"""
import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1] / "ros2_ws/src"
ENTRYPOINTS = (
    ("uav_tracking_nodes/uav_tracking_nodes/controller_node.py", "ControllerNode", False),
    ("uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py", "StateEstimatorNode", False),
    ("uav_tracking_px4_adapter/uav_tracking_px4_adapter/adapter_node.py", "Px4AdapterNode", False),
    ("uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py", "FlightSupervisor", False),
    ("uav_tracking_bringup/uav_tracking_bringup/flight_tf_node.py", "FlightTfNode", False),
    ("uav_tracking_bringup/uav_tracking_bringup/gimbal_adapter_node.py", "GimbalAdapterNode", False),
    ("uav_tracking_bringup/uav_tracking_bringup/scenario_motion.py", "ScenarioMotion", True),
    ("uav_tracking_bringup/uav_tracking_bringup/stage2_motion.py", "Stage2Motion", True),
)


class ExternalShutdown(Exception):
    pass


class RosNodeShutdownTests(unittest.TestCase):
    def invoke(self, source, constructor_name, *, spin_error=None, already_closed=False,
               constructor_error=None, destroy_error=None):
        events=[];context={"ok":True}
        requested=SimpleNamespace(value=False)
        requested.is_set=lambda:requested.value
        node_context=SimpleNamespace(ok=lambda:context["ok"])

        @contextmanager
        def requests():
            yield requested

        class Node:
            def __init__(self):
                events.append("construct")
                self.context=node_context
                if constructor_error is not None:
                    raise constructor_error

            def stop(self):
                if not context["ok"]:
                    raise AssertionError("must not publish stop after context shutdown")
                events.append("stop")

            def destroy_node(self):
                events.append("destroy")
                if destroy_error is not None:
                    raise destroy_error

        class Executor:
            def __init__(self, *, context):
                self_context=context
                if self_context is not node_context:
                    raise AssertionError("executor must own the node's context")
                events.append("executor")

            def add_node(self, node):
                events.append("add")

            def spin_once(self, timeout_sec):
                events.append("spin")
                requested.value=True
                if already_closed:
                    context["ok"]=False
                if spin_error is not None:
                    raise spin_error

            def shutdown(self):
                events.append("executor_shutdown")

        def shutdown():
            events.append("try_shutdown")
            context["ok"]=False

        def init(**kwargs):
            if kwargs.get("signal_handler_options") != "NO":
                raise AssertionError("rclpy must not asynchronously close this context")
            events.append("init")

        fake_ros=SimpleNamespace(init=init,
                                 ok=lambda:context["ok"], try_shutdown=shutdown)
        tree=ast.parse((ROOT/source).read_text(encoding="utf-8"))
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="main")
        namespace={"rclpy":fake_ros,"ExternalShutdownException":ExternalShutdown,constructor_name:Node,
                   "shutdown_requests":requests,"SignalHandlerOptions":SimpleNamespace(NO="NO"),
                   "SingleThreadedExecutor":Executor}
        exec(compile(ast.Module(body=[main],type_ignores=[]),str(ROOT/source),"exec"),namespace)
        return namespace["main"],events,context

    def test_sigint_after_context_already_closed_is_clean_and_does_not_publish(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,context=self.invoke(source,constructor,spin_error=KeyboardInterrupt(),already_closed=True)
                main([])
                self.assertEqual(events,["init","construct","executor","add","spin",
                                         "executor_shutdown","destroy","try_shutdown"])
                self.assertFalse(context["ok"])

    def test_external_context_shutdown_is_a_normal_exit(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,_=self.invoke(source,constructor,spin_error=ExternalShutdown(),already_closed=True)
                main([])
                self.assertEqual(events[-2:],["destroy","try_shutdown"])

    def test_normal_return_preserves_motion_stop_before_destroy_and_context_shutdown(self):
        for source,constructor,motion in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,context=self.invoke(source,constructor)
                main([])
                self.assertEqual(events,["init","construct","executor","add","spin","executor_shutdown"]
                                 +(["stop"] if motion else [])+["destroy","try_shutdown"])
                self.assertFalse(context["ok"])

    def test_real_callback_errors_remain_failures_after_cleanup(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,_=self.invoke(source,constructor,spin_error=ValueError("callback failed"))
                with self.assertRaisesRegex(ValueError,"callback failed"):
                    main([])
                self.assertEqual(events[-2:],["destroy","try_shutdown"])

    def test_runtime_errors_are_not_suppressed_even_if_context_has_stopped(self):
        for source,constructor,_ in ENTRYPOINTS:
            for closed in (False,True):
                with self.subTest(source=source,closed=closed):
                    error=RuntimeError("Unable to convert call argument to Python object (compile in debug mode for details)")
                    main,events,_=self.invoke(source,constructor,spin_error=error,already_closed=closed)
                    with self.assertRaises(RuntimeError) as caught:
                        main([])
                    self.assertIs(caught.exception,error)
                    self.assertIn("executor_shutdown",events)
                    self.assertEqual(events[-2:],["destroy","try_shutdown"])

    def test_failed_node_construction_closes_context_without_destroying_missing_node(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,_=self.invoke(source,constructor,constructor_error=ValueError("startup failed"))
                with self.assertRaisesRegex(ValueError,"startup failed"):
                    main([])
                self.assertEqual(events,["init","construct","try_shutdown"])

    def test_destroy_error_is_not_hidden_but_context_still_closes(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,_=self.invoke(source,constructor,destroy_error=ValueError("destroy failed"))
                with self.assertRaisesRegex(ValueError,"destroy failed"):
                    main([])
                self.assertEqual(events[-2:],["destroy","try_shutdown"])


if __name__=="__main__":
    unittest.main()
