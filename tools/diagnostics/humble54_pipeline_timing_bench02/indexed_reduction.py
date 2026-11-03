"""Offline reduction indexes; no gates, ROS imports, or native entry point."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


def _indexable(value):
    # JSON tokens are strings. Preserve legacy equality scans for other types.
    return value is None or type(value) is str


def _ordered_numeric(value):
    return type(value) is int or type(value) is float and math.isfinite(value)


class EventIndex:
    SPECS = (("navigation_update", "event_id"),
             ("navigation_project", "project_token"),
             ("snapshot", "snapshot_token"), ("snapshot", "rgb_token"),
             ("submit", "snapshot_token"), ("worker_start", "snapshot_token"),
             ("sensor_callback", "image_token"))

    def __init__(self, events):
        self.events = events
        self.lookups = {spec: defaultdict(list) for spec in self.SPECS}
        self.navigation = defaultdict(list)
        self.navigation_fallback = set()
        for event in events:
            kind = event["kind"]
            for spec, values in self.lookups.items():
                if spec[0] == kind:
                    value = event.get(spec[1])
                    if _indexable(value):
                        values[value].append(event)
            if kind == "navigation_clear" or kind == "navigation_update" and event.get("accepted") is True:
                process, stamp = event.get("process"), event["recorded_monotonic_ns"]
                if _indexable(process):
                    if _ordered_numeric(stamp):
                        self.navigation[process].append(stamp)
                    else:
                        self.navigation_fallback.add(process)

    def find(self, kind, key, value):
        if _indexable(value):
            return self.lookups[(kind, key)].get(value, [])
        return [event for event in self.events if event["kind"] == kind and event.get(key) == value]

    def navigation_replaced(self, accepted, project):
        process = accepted["process"]
        begin, end = accepted["recorded_monotonic_ns"], project["recorded_monotonic_ns"]
        if (_indexable(process) and process not in self.navigation_fallback
                and all(_ordered_numeric(stamp) for stamp in (begin, end))):
            stamps = self.navigation.get(process, [])
            # Both boundaries are strict in the original predicate.
            return bisect_right(stamps, begin) < bisect_left(stamps, end)
        return any(event.get("process") == process
                   and begin < event["recorded_monotonic_ns"] < end
                   and (event["kind"] == "navigation_clear"
                        or event["kind"] == "navigation_update" and event.get("accepted") is True)
                   for event in self.events)


class OutcomeIndex:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.by_rgb = defaultdict(list)
        for outcome in outcomes:
            value = outcome.get("rgb_token")
            if outcome["status"] == "CANDIDATE_SOFTWARE_LATENCY" and _indexable(value):
                self.by_rgb[value].append(outcome)

    def find(self, value):
        if _indexable(value):
            return self.by_rgb.get(value, [])
        return [row for row in self.outcomes if row.get("rgb_token") == value
                and row["status"] == "CANDIDATE_SOFTWARE_LATENCY"]


def read_events(paths, bindings, *, chunk_bytes=1024 * 1024):
    """Hash original chunks, parsing the exact bytes.splitlines() records.

    A trailing CR is held across chunks, so CRLF, LF, CR-only, blank lines and
    missing final newline retain the original reducer's record boundaries.
    The complete parsed event list is still retained by the caller.
    """
    for path in paths:
        digest, size, pending = hashlib.sha256(), 0, b""
        with Path(path).open("rb") as stream:
            while True:
                block = stream.read(chunk_bytes)
                if not block:
                    break
                digest.update(block)
                size += len(block)
                lines = (pending + block).splitlines(keepends=True)
                pending = b""
                if lines and not lines[-1].endswith(b"\n"):
                    pending = lines.pop()
                for line in lines:
                    content = line.rstrip(b"\r\n")
                    if content:
                        yield json.loads(content)
            for line in pending.splitlines():
                if line:
                    yield json.loads(line)
        bindings.append({"path": str(path), "bytes": size, "sha256": digest.hexdigest()})
