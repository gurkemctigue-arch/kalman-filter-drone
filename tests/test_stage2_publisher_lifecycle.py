"""Motion stop must coexist with the ROS node's mixed publisher registry."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "ros2_ws/src/"
          "uav_tracking_bringup/uav_tracking_bringup/stage2_motion.py")


class Twist:
    def __init__(self):
        self.linear = SimpleNamespace(x=0.0)
        self.angular = SimpleNamespace(z=0.0)


class String:
    def __init__(self):
        self.data = ""


class Publisher:
    def __init__(self, message_type, topic):
        self.message_type, self.topic = message_type, topic
        self.messages = []

    def publish(self, message):
        if not isinstance(message, self.message_type):
            raise TypeError(f"{self.topic} requires {self.message_type.__name__}")
        self.messages.append(message)


class RegistryNode:
    """Match rclpy's ownership of all publishers, including events."""

    def __init__(self, name):
        self._publishers = []
        self.parameters = {"use_sim_time": True}

    def declare_parameter(self, name, value):
        self.parameters[name] = value

    def get_parameter(self, name):
        return SimpleNamespace(value=self.parameters[name])

    def create_publisher(self, message_type, topic, depth):
        publisher = Publisher(message_type, topic)
        self._publishers.append(publisher)
        return publisher

    def create_subscription(self, *args):
        return None

    def create_timer(self, *args):
        return None

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1_000_000_000))


class Stage2PublisherLifecycleTests(unittest.TestCase):
    def test_stop_sends_three_zero_twists_without_retyping_event_publisher(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        production_class = next(item for item in tree.body
                                if isinstance(item, ast.ClassDef) and item.name == "Stage2Motion")
        namespace = {
            "Node": RegistryNode, "Twist": Twist, "String": String, "json": json,
            "MotionTimeline": lambda: SimpleNamespace(started_s=0.0, aborted=False),
            "stage2_motion_profile": lambda *args, **kwargs: ((0.5, 0.1),) * 3,
        }
        exec(compile(ast.Module(body=[production_class], type_ignores=[]), str(SOURCE), "exec"), namespace)
        node = namespace["Stage2Motion"]()
        node._tick()
        node.stop()
        self.assertEqual(len(node._publishers), 4)
        commands = [publisher for publisher in node._publishers if publisher.message_type is Twist]
        events = [publisher for publisher in node._publishers if publisher.message_type is String]
        self.assertEqual(len(commands), 3)
        self.assertEqual(len(events), 1)
        for publisher in commands:
            self.assertEqual(len(publisher.messages), 2)
            self.assertEqual(publisher.messages[0].linear.x, 0.5)
            self.assertEqual(publisher.messages[-1].linear.x, 0.0)
            self.assertEqual(publisher.messages[-1].angular.z, 0.0)
        self.assertEqual(len(events[0].messages), 1)
        self.assertEqual(json.loads(events[0].messages[0].data)["elapsed_s"], 1.0)


if __name__ == "__main__":
    unittest.main()
