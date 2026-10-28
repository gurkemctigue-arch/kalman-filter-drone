"""Exercise production entrypoint cleanup with an already stopped ROS context.

Only the real main() AST is loaded: no ROS, native inference, simulator or
flight code is started. The final integrated signal behavior remains a
separate end-to-end check after the frozen research run.
"""
import ast
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

        class Node:
            def __init__(self):
                events.append("construct")
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

        def spin(node):
            events.append("spin")
            if already_closed:
                context["ok"]=False
            if spin_error is not None:
                raise spin_error

        def shutdown():
            events.append("try_shutdown")
            context["ok"]=False

        fake_ros=SimpleNamespace(init=lambda **kwargs: events.append("init"), spin=spin,
                                 ok=lambda:context["ok"], try_shutdown=shutdown)
        tree=ast.parse((ROOT/source).read_text(encoding="utf-8"))
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="main")
        namespace={"rclpy":fake_ros,"ExternalShutdownException":ExternalShutdown,constructor_name:Node}
        exec(compile(ast.Module(body=[main],type_ignores=[]),str(ROOT/source),"exec"),namespace)
        return namespace["main"],events,context

    def test_sigint_after_context_already_closed_is_clean_and_does_not_publish(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,context=self.invoke(source,constructor,spin_error=KeyboardInterrupt(),already_closed=True)
                main([])
                self.assertEqual(events,["init","construct","spin","destroy","try_shutdown"])
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
                self.assertEqual(events,["init","construct","spin"]+(["stop"] if motion else [])+["destroy","try_shutdown"])
                self.assertFalse(context["ok"])

    def test_real_callback_errors_remain_failures_after_cleanup(self):
        for source,constructor,_ in ENTRYPOINTS:
            with self.subTest(source=source):
                main,events,_=self.invoke(source,constructor,spin_error=ValueError("callback failed"))
                with self.assertRaisesRegex(ValueError,"callback failed"):
                    main([])
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
