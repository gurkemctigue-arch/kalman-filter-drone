"""Reject real graph startup races without launching a simulator."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from uav_tracking.startup_readiness import (
    ADAPTER_NODE, ODOM_TOPIC, RAW_TOPIC, RECORDER_NODE, REQUIRED_TOPICS,
    TIMING_TOPIC, StableGraphGate, assess_graph,
)


def ready_graph():
    graph = {"topics": {}, "adapter_service": {
        "schema_version": 1, "node": ADAPTER_NODE,
        "raw_topic": RAW_TOPIC, "odom_topic": ODOM_TOPIC, "timing_topic": TIMING_TOPIC,
        "raw_discovered_publishers": 1, "raw_count_scope": "NODE_GRAPH_DISCOVERY_NOT_RMW_MATCH",
        "odom_matched_subscriptions": 4,
        "timing_matched_subscriptions": 1}}
    for index, (topic, message_type) in enumerate(REQUIRED_TOPICS.items(), start=1):
        gid = f"{index:048x}"
        # The native publisher has the real observed bare-DDS identity. No
        # contract should assume it is a conventional named ROS node.
        node = "/_CREATED_BY_BARE_DDS_APP_" if topic == RAW_TOPIC else "/bridge"
        if topic in {ODOM_TOPIC, TIMING_TOPIC}:
            node = ADAPTER_NODE
        publisher = {"node": node, "type": message_type, "gid": gid}
        subscriptions = [{"node": RECORDER_NODE, "type": message_type,
            "gid": f"{index+30:048x}", "compatible_publisher_gids": [gid]}]
        if topic in {RAW_TOPIC, "/clock"}:
            subscriptions.append({"node": ADAPTER_NODE, "type": message_type,
                "gid": f"{index+60:048x}", "compatible_publisher_gids": [gid]})
        graph["topics"][topic] = {"publishers": [publisher], "subscriptions": subscriptions}
    return graph


class StartupReadinessContractTests(unittest.TestCase):
    def test_topic_names_and_unrelated_subscribers_cannot_satisfy_the_gate(self):
        graph = ready_graph()
        self.assertTrue(assess_graph(graph, require_recorder=True)["ready"])
        for topic in REQUIRED_TOPICS:
            broken = copy.deepcopy(graph)
            recorder = next(s for s in broken["topics"][topic]["subscriptions"] if s["node"] == RECORDER_NODE)
            recorder["node"] = "/unrelated_subscriber"
            with self.subTest(topic=topic):
                self.assertFalse(assess_graph(broken, require_recorder=True)["ready"])
        graph["topics"][RAW_TOPIC]["subscriptions"][-1]["node"] = "/px4_adapter"
        self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])

    def test_wrong_type_missing_gid_and_incompatible_qos_are_rejected(self):
        for fault in ("type", "gid", "qos"):
            graph = ready_graph()
            if fault == "type":
                graph["topics"][ODOM_TOPIC]["publishers"][0]["type"] = "std_msgs/msg/String"
            elif fault == "gid":
                graph["topics"][RAW_TOPIC]["publishers"][0]["gid"] = "00" * 24
            else:
                graph["topics"][TIMING_TOPIC]["subscriptions"][0]["compatible_publisher_gids"] = []
            with self.subTest(fault=fault):
                self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])

    def test_adapter_callback_and_actual_dds_matches_are_mandatory(self):
        original = ready_graph()
        for field, value in (("node", "/fake_adapter"), ("raw_discovered_publishers", 0),
                ("raw_discovered_publishers", True), ("raw_count_scope", "RMW_MATCH"),
                ("odom_matched_subscriptions", 0),
                ("timing_matched_subscriptions", 0), ("raw_topic", "/wrong_raw")):
            graph = copy.deepcopy(original)
            graph["adapter_service"][field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])
        original["adapter_service"] = {}
        self.assertFalse(assess_graph(original, require_recorder=True)["ready"])

    def test_existing_controller_match_cannot_mask_an_unmatched_recorder(self):
        graph = ready_graph()
        recorder = graph["topics"][ODOM_TOPIC]["subscriptions"][0]
        graph["topics"][ODOM_TOPIC]["subscriptions"].append({**recorder, "node": "/controller", "gid": "ff" * 24})
        graph["adapter_service"]["odom_matched_subscriptions"] = 1
        self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])

    def test_no_bag_mode_is_explicit_and_still_requires_the_real_adapter(self):
        graph = ready_graph()
        for entry in graph["topics"].values():
            entry["subscriptions"] = [s for s in entry["subscriptions"] if s["node"] != RECORDER_NODE]
        graph["adapter_service"]["timing_matched_subscriptions"] = 0
        self.assertTrue(assess_graph(graph, require_recorder=False)["ready"])
        self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])
        graph["adapter_service"]["raw_discovered_publishers"] = 0
        self.assertFalse(assess_graph(graph, require_recorder=False)["ready"])

    def test_duplicate_adapter_or_recorder_endpoint_is_ambiguous(self):
        for role in ("publishers", "subscriptions"):
            graph = ready_graph()
            graph["topics"][TIMING_TOPIC][role].append(copy.deepcopy(graph["topics"][TIMING_TOPIC][role][0]))
            with self.subTest(role=role):
                self.assertFalse(assess_graph(graph, require_recorder=True)["ready"])

    def test_endpoint_replacement_or_failed_observation_restarts_both_wall_windows(self):
        assessment = assess_graph(ready_graph(), require_recorder=True)
        gate = StableGraphGate(stable_wall_s=1., guard_wall_s=.5)
        self.assertFalse(gate.observe(0., assessment)["accepted"])
        self.assertEqual(gate.observe(1., assessment)["phase"], "guard")
        self.assertFalse(gate.observe(1.49, assessment)["accepted"])
        replaced = {**assessment, "endpoint_signature": "different DDS endpoint"}
        self.assertFalse(gate.observe(1.5, replaced)["accepted"])
        self.assertFalse(gate.observe(2., {**replaced, "ready": False})["accepted"])
        self.assertFalse(gate.observe(2.1, replaced)["accepted"])
        self.assertTrue(gate.observe(3.6, replaced)["accepted"])
        with self.assertRaises(ValueError):
            gate.observe(3.5, replaced)

    def test_adapter_response_distinguishes_raw_discovery_from_output_matches(self):
        from tests.test_px4_adapter import adapter_node
        def endpoint(topic, count, method):
            return SimpleNamespace(topic_name=topic, **{method:Mock(return_value=count)})
        node = SimpleNamespace(get_fully_qualified_name=lambda:ADAPTER_NODE,
            count_publishers=Mock(return_value=0),
            _raw_odometry_sub=SimpleNamespace(topic_name=RAW_TOPIC),
            _vehicle_odom_pub=endpoint(ODOM_TOPIC, 3, "get_subscription_count"),
            _odometry_timing_pub=endpoint(TIMING_TOPIC, 1, "get_subscription_count"))
        response = adapter_node.Px4AdapterNode._on_startup_readiness(node, None, SimpleNamespace())
        data = json.loads(response.message)
        self.assertTrue(response.success)
        self.assertEqual(data["raw_discovered_publishers"], 0)
        self.assertEqual(data["raw_count_scope"],"NODE_GRAPH_DISCOVERY_NOT_RMW_MATCH")
        self.assertEqual(data["odom_matched_subscriptions"], 3)
        node.count_publishers.assert_called_once_with(RAW_TOPIC)


class StartupReadinessCollectorTests(unittest.TestCase):
    def run_collector(self, *, service_available=True, abort=None):
        path = Path(__file__).resolve().parents[1]/"scripts/wait_stage1_graph.py"
        spec = importlib.util.spec_from_file_location("startup_collector_fixture", path)
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)
        graph = ready_graph()
        clock = SimpleNamespace(value=0.)
        context = SimpleNamespace(ok=lambda:True)
        destroyed = []
        future = SimpleNamespace(done=lambda:True,
            result=lambda:SimpleNamespace(success=True,message=json.dumps(graph["adapter_service"])))
        client = SimpleNamespace(service_is_ready=lambda:service_available, call_async=lambda _:future)
        def endpoints(topic, role):
            return [SimpleNamespace(node_namespace="/", node_name=e["node"].lstrip("/"),
                topic_type=e["type"], endpoint_gid=bytes.fromhex(e["gid"]), qos_profile="fixture")
                for e in graph["topics"][topic][role]]
        node = SimpleNamespace(create_client=lambda *_:client,
            get_publishers_info_by_topic=lambda topic:endpoints(topic,"publishers"),
            get_subscriptions_info_by_topic=lambda topic:endpoints(topic,"subscriptions"),
            destroy_node=lambda:destroyed.append(True))
        def spin(timeout_sec):
            clock.value+=max(timeout_sec,.001)
        executor = SimpleNamespace(add_node=Mock(),spin_once=spin,shutdown=Mock())
        def create_executor(*, context):
            self.assertIs(context, ros.context.Context())
            return executor
        ros = SimpleNamespace(context=SimpleNamespace(Context=lambda:context), init=lambda **_:None,
            create_node=lambda *_,**__:node, shutdown=Mock())
        qos = SimpleNamespace(QoSCompatibility=SimpleNamespace(OK="OK"),
            qos_check_compatible=lambda *_:(SimpleNamespace(name="OK"), ""))
        # The real collector compares enum members; this fixture equality is
        # explicit while the contract tests reject incompatible endpoint GIDs.
        class Compatibility:
            name = "OK"
        compatibility = Compatibility()
        qos.QoSCompatibility.OK = compatibility
        qos.qos_check_compatible=lambda *_:(compatibility, "")
        modules = {"rclpy":ros, "rclpy.qos":qos,
            "rclpy.executors":SimpleNamespace(SingleThreadedExecutor=create_executor),
            "std_srvs":SimpleNamespace(), "std_srvs.srv":SimpleNamespace(Trigger=SimpleNamespace(Request=lambda:None))}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"readiness.json"
            with patch.dict(sys.modules,modules), patch.object(collector.time,"monotonic",lambda:clock.value):
                if abort is not None or not service_available:
                    with self.assertRaises(RuntimeError):
                        collector.wait_ready(output,require_recorder=True,timeout_wall_s=2.,check_alive=abort)
                else:
                    result = collector.wait_ready(output,require_recorder=True,timeout_wall_s=2.)
                    self.assertEqual(result["status"],"PASS")
                saved = json.loads(output.read_text())
            self.assertEqual(destroyed,[True])
            ros.shutdown.assert_called_once_with(context=context)
            executor.add_node.assert_called_once_with(node)
            executor.shutdown.assert_called_once_with()
            return saved

    def test_collector_preserves_each_endpoint_and_final_guard_evidence(self):
        saved = self.run_collector()
        self.assertEqual(saved["status"],"PASS")
        self.assertGreaterEqual(saved["observations"][-1]["stability"]["continuous_ready_wall_s"],1.5)
        self.assertEqual(saved["observations"][-1]["adapter_service"]["raw_discovered_publishers"],1)
        self.assertIn("qos_checks", saved["observations"][-1]["topics"][RAW_TOPIC]["subscriptions"][0])

    def test_timeout_and_owned_process_failure_are_structured_failures(self):
        timeout = self.run_collector(service_available=False)
        self.assertEqual(timeout["status"],"FAIL")
        self.assertIn("callback absent", " ".join(timeout["observations"][-1]["assessment"]["failures"]))
        def aborted():
            raise RuntimeError("owned adapter exited")
        aborted_report = self.run_collector(abort=aborted)
        self.assertEqual(aborted_report["status"],"FAIL")
        self.assertIn("owned adapter exited",aborted_report["error"])


if __name__ == "__main__":
    unittest.main()
