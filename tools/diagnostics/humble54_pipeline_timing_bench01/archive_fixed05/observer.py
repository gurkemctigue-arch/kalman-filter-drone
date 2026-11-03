"""External, bounded, process-local hooks. Original call/return/exception retained."""
from collections import OrderedDict
from contextlib import contextmanager
import functools
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import queue
import sys
import threading
import time

from typed_message import snapshot

PROBE_SHA = "c7d0050cab71ce6a340c7fc5647531e92334029c8dc38b14393d2dc0058ae426"


def load_probe(path):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROBE_SHA:
        raise ValueError("c7 capability source pin differs")
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location("bench_c7_probe", path))
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


class Tokens:
    """Bounded strong references; eviction creates UNKNOWN, never ID reuse joins."""
    def __init__(self, prefix, capacity=64):
        self.prefix, self.capacity, self.serial = prefix, capacity, 0
        self.items = OrderedDict()
        self.lock = threading.RLock()
        self.evictions = 0

    def token(self, obj, create=True):
        with self.lock:
            prior = self.items.get(id(obj))
            if prior is not None and prior[0] is obj:
                self.items.move_to_end(id(obj))
                return prior[1]
            if not create:
                return None
            self.serial += 1
            token = f"{self.prefix}:{self.serial}"
            self.items[id(obj)] = (obj, token)
            while len(self.items) > self.capacity:
                self.items.popitem(last=False)
                self.evictions += 1
            return token


class Trace:
    """No blocking file writes on original threads; bounded queue and event size."""
    def __init__(self, path=None, process="fake", capacity=32, max_event_bytes=2_000_000):
        self.process, self.path, self.max_event_bytes = process, path, max_event_bytes
        self.serial, self.dropped, self.errors = 0, 0, []
        self.lock = threading.Lock()
        self.events = [] if path is None else None
        self.queue = queue.Queue(capacity)
        self.writer = None
        if path is not None:
            self.file = Path(path).open("x", encoding="utf-8", newline="\n")
            self.writer = threading.Thread(target=self._write, name="bench_trace_writer", daemon=False)
            self.writer.start()

    def _write(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                self.file.write(item + "\n")
            except Exception as error:
                self.errors.append({"where": "trace_writer", "error": type(error).__name__})
            finally:
                self.queue.task_done()

    def emit(self, kind, **fields):
        with self.lock:
            self.serial += 1
            event = {"kind": kind, "process": self.process, "event_id": f"{self.process}:{self.serial}",
                     "local_index": self.serial, "recorded_monotonic_ns": time.monotonic_ns(),
                     "thread_id": threading.get_ident(), **fields}
        try:
            line = json.dumps(event, separators=(",", ":"), allow_nan=False)
            if len(line.encode("utf-8")) > self.max_event_bytes:
                raise queue.Full
            if self.events is not None:
                self.events.append(event)
            else:
                self.queue.put_nowait(line)
        except (queue.Full, ValueError, TypeError, OverflowError):
            with self.lock:
                self.dropped += 1
        return event["event_id"]

    def close(self):
        if self.writer is not None:
            self.queue.put(None)  # teardown only, never an algorithm callback
            self.writer.join()
            self.file.close()


class Hooks:
    def __init__(self, trace):
        self.trace, self.restore = trace, []

    def patch(self, cls, name, replacement):
        original = getattr(cls, name)
        self.restore.append((cls, name, original))
        setattr(cls, name, replacement)
        return original

    def method(self, cls, name, before=None, after=None):
        original = getattr(cls, name)
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            state = None
            if before:
                try:
                    state = before(args, kwargs)
                except Exception as error:
                    self.trace.emit("hook_error", method=name, error=type(error).__name__)
            result, raised = None, None
            try:
                result = original(*args, **kwargs)
                return result
            except BaseException as error:
                raised = type(error).__name__
                raise
            finally:
                if after:
                    try:
                        after(args, kwargs, state, result, raised)
                    except Exception as error:
                        self.trace.emit("hook_error", method=name, error=type(error).__name__)
        self.patch(cls, name, wrapped)
        return original

    def close(self):
        for cls, name, original in reversed(self.restore):
            setattr(cls, name, original)


def actual_local(code, name):
    frame = inspect.currentframe()
    try:
        frame = frame.f_back
        while frame is not None:
            if frame.f_code is code:
                return frame.f_locals.get(name)
            frame = frame.f_back
        return None
    finally:
        del frame


class Observer:
    def __init__(self, role, trace, edges, probe):
        self.role, self.trace, self.edges, self.probe = role, trace, edges, probe
        self.hooks = Hooks(trace)
        self.objects, self.images = Tokens(role), Tokens(role+":image", capacity=8)
        self.jobs = Tokens(role+":job", capacity=8)
        self.pending, self.projects = OrderedDict(), OrderedDict()
        self.last_accepted = None
        self.local = threading.local()
        self.nav_code, self.project_code, self.step_code = None, None, None
        self.errors = []

    def typed(self, message):
        try:
            return snapshot(message)
        except Exception as error:
            self.trace.emit("typed_unknown", error=type(error).__name__)
            return None

    def sensor(self, kind, message):
        entered = time.monotonic_ns()
        token = self.images.token(message)
        self.trace.emit("sensor_callback", sensor=kind, image_token=token, entered_ns=entered)

    def submit_before(self, args, kwargs):
        job = args[1]
        token = self.jobs.token(job)
        self.trace.emit("snapshot", snapshot_token=token,
                        rgb_token=self.images.token(job.rgb, False), depth_token=self.images.token(job.depth, False))
        return token

    def submit_after(self, args, kwargs, token, result, raised):
        self.trace.emit("submit", snapshot_token=token, accepted=result if type(result) is bool else None, exception=raised)

    def infer_before(self, args, kwargs):
        previous = getattr(self.local, "job", None)
        self.local.job = self.jobs.token(args[1], False)
        self.trace.emit("worker_start", snapshot_token=self.local.job)
        return previous

    def infer_after(self, args, kwargs, previous, result, raised):
        self.trace.emit("worker_end", snapshot_token=getattr(self.local, "job", None), exception=raised)
        self.local.job = previous

    def nav_update_after(self, args, kwargs, state, result, raised):
        source = actual_local(self.nav_code, "source") if self.nav_code else None
        source_token = self.objects.token(source, False) if source is not None else None
        accepted = getattr(result, "accepted", None)
        identity = (kwargs.get("target_uuid"), kwargs.get("track_id"))
        event = self.trace.emit("navigation_update", source_frame_token=source_token,
                                accepted=accepted if type(accepted) is bool else None,
                                identity=list(identity), exception=raised)
        if accepted is True and raised is None:
            self.last_accepted = {"source_frame_token": source_token, "update_event_id": event,
                                  "identity": identity, "timestamp": kwargs.get("timestamp")}

    def clear_after(self, args, kwargs, state, result, raised):
        self.last_accepted = None
        self.trace.emit("navigation_clear", exception=raised)

    def project_after(self, args, kwargs, state, result, raised):
        token = self.objects.token(result) if result is not None else None
        prior = self.last_accepted
        identity = (kwargs.get("target_uuid"), kwargs.get("track_id"))
        valid = (getattr(result, "valid", None) is True and raised is None and prior is not None
                 and identity == prior["identity"] and getattr(result, "measured_timestamp_s", None) == prior["timestamp"])
        info = {"source_frame_token": prior["source_frame_token"] if valid else None,
                "accepted_update_event_id": prior["update_event_id"] if valid else None,
                "project_token": token, "project_valid": getattr(result, "valid", None) is True}
        self.projects[token] = info
        while len(self.projects) > 64:
            self.projects.popitem(last=False)
        self.trace.emit("navigation_project", **info, exception=raised)

    def lineage(self, edge):
        if edge == "detection":
            return {"snapshot_token": getattr(self.local, "job", None)}
        if edge == "state":
            project = actual_local(self.project_code, "snapshot") if self.project_code else None
            token = self.objects.token(project, False) if project is not None else None
            return self.projects.get(token, {"project_token": None, "source_frame_token": None})
        target = actual_local(self.step_code, "target") if self.step_code else None
        return {"target_token": self.objects.token(target, False) if target is not None else None}

    def on_take(self, record):
        topic = record["sub"].topic_name
        if topic not in self.edges or record["status"] == "EMPTY":
            return
        message = record.get("message")
        token = self.objects.token(message) if message is not None else None
        fields = self.typed(message) if message is not None else None
        meta = record.get("metadata", {})
        metadata = {name: meta.get(name) for name in ("source_timestamp", "received_timestamp")}
        event = self.trace.emit("take", phase=self.edges[topic], object_token=token,
                                capture_status=record["status"], entered_ns=record["entered_ns"],
                                exited_ns=record.get("exited_ns"), metadata=metadata, message_fields=fields)
        if token is not None:
            self.pending[token] = (event, fields)
            while len(self.pending) > 64:
                self.pending.popitem(last=False)

    def callback(self, edge, original, message):
        entered = time.monotonic_ns()
        token = self.objects.token(message)
        taken = self.pending.pop(token, None)
        fields = self.typed(message)
        self.trace.emit("callback", phase=edge, object_token=token, entered_ns=entered,
                        take_event_id=taken[0] if taken else None,
                        same_object_as_original_take=taken is not None,
                        complete_typed_fields_match_take=taken is not None and taken[1] is not None and taken[1] == fields,
                        message_fields=fields)
        return original(message)

    def install_ros(self, module, ready):
        """Call before constructing the original node or binding any callback."""
        from rclpy.node import Node
        from rclpy.publisher import Publisher
        from rclpy.executors import Executor
        original_pub, original_sub = Node.create_publisher, Node.create_subscription
        original_publish = Publisher.publish
        observer = self
        def checked_topic(node, topic):
            resolved = node.resolve_topic_name(topic)
            if resolved == "/fmu" or resolved.startswith("/fmu/"):
                raise ValueError("unisolated fmu endpoint refused before construction: " + resolved)
            return resolved
        def create_publisher(node, msg_type, topic, *args, **kwargs):
            resolved = checked_topic(node, topic)
            result = original_pub(node, msg_type, topic, *args, **kwargs)
            observer.trace.emit("publisher_created", topic=resolved, writer_token=node.get_name())
            return result
        def create_subscription(node, msg_type, topic, callback, *args, **kwargs):
            resolved = checked_topic(node, topic)
            if resolved in observer.edges:
                original_callback = callback
                @functools.wraps(original_callback)
                def callback(message):
                    return observer.callback(observer.edges[resolved], original_callback, message)
            return original_sub(node, msg_type, topic, callback, *args, **kwargs)
        def publish(publisher, message):
            topic = publisher.topic_name
            if topic not in observer.edges:
                return original_publish(publisher, message)
            phase = observer.edges[topic]
            fields = observer.typed(message)
            try:
                lineage = observer.lineage(phase)
            except Exception as error:
                observer.trace.emit("hook_error", method="publish_lineage", error=type(error).__name__)
                lineage = {}
            before = observer.probe.anchor()
            success, error = False, None
            try:
                result = original_publish(publisher, message)
                success = True
                return result
            except BaseException as exception:
                error = type(exception).__name__
                raise
            finally:
                after = observer.probe.anchor()
                observer.trace.emit("publish", phase=phase, object_token=observer.objects.token(message),
                                    writer_token=ready.get("node_name"), before=before, after=after,
                                    success=success, exception_type=error, message_fields=fields,
                                    command_valid=getattr(message, "valid", None), command_mode=getattr(message, "mode", None), **lineage)
        self.hooks.patch(Node, "create_publisher", create_publisher)
        self.hooks.patch(Node, "create_subscription", create_subscription)
        self.hooks.patch(Publisher, "publish", publish)
        self.hooks.patch(Executor, "_take_subscription",
                         self.probe.transparent_take_wrapper(Executor._take_subscription, self.on_take, self.errors))
        self.hooks.method(Executor, "shutdown", after=lambda a,k,s,r,e:
                          self.trace.emit("executor_shutdown", returned=r if type(r) is bool else None, exception=e))
        cls = getattr(module, {"detector": "DetectorNode", "estimator": "StateEstimatorNode",
                               "controller": "ControllerNode", "adapter": "Px4AdapterNode"}[self.role])
        def constructed(args, kwargs, state, result, raised):
            if raised is None:
                node = args[0]
                ready.update(node_name=node.get_name(), pid=__import__("os").getpid())
        self.hooks.method(cls, "__init__", after=constructed)
        if self.role == "detector":
            for method, kind in (("_on_rgb", "rgb"), ("_on_depth", "depth")):
                self.hooks.method(cls, method, before=lambda a, k, kind=kind: self.sensor(kind, a[1]))
            from uav_tracking_nodes.inference_worker import NonQueuingWorker
            self.hooks.method(NonQueuingWorker, "submit", self.submit_before, self.submit_after)
            self.hooks.method(cls, "_infer_snapshot", self.infer_before, self.infer_after)
        elif self.role == "estimator":
            if not hasattr(cls, "_update_navigation") or not hasattr(cls, "_publish_navigation"):
                raise ValueError("only independently hooked navigation path is supported")
            self.nav_code, self.project_code = cls._update_navigation.__code__, cls._publish_navigation.__code__
            from uav_tracking_nodes.navigation_estimator import NavigationEstimator
            self.hooks.method(NavigationEstimator, "update", after=self.nav_update_after)
            self.hooks.method(NavigationEstimator, "_clear_measurement", after=self.clear_after)
            self.hooks.method(NavigationEstimator, "project", after=self.project_after)
        elif self.role == "controller":
            self.step_code = cls._step.__code__

    def close(self):
        self.hooks.close()
        self.trace.emit("observer_final", instrumentation_errors=self.errors,
                        trace_dropped=self.trace.dropped, trace_errors=self.trace.errors,
                        object_evictions=self.objects.evictions, image_evictions=self.images.evictions,
                        job_evictions=self.jobs.evictions)
