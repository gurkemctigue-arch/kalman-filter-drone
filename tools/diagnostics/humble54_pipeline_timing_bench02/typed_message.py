"""Complete typed snapshots of small ROS tracking messages; no ROS import.

CDR padding is deliberately absent. Unknown structures fail closed. Scalar
float32 NaNs are rejected because Python conversion cannot certify their wire
payload; raw float32 array buffers preserve all bits, including signaling NaNs.
"""
from array import array
import math
import re
import struct
import sys

ROOT_TYPES = {"uav_tracking_interfaces/msg/TargetObservationArray",
              "uav_tracking_interfaces/msg/TargetState", "uav_tracking_interfaces/msg/TrackingCommand"}
INTEGERS = {**{f"int{n}": (-(1 << (n-1)), (1 << (n-1))-1) for n in (8, 16, 32, 64)},
            **{f"uint{n}": (0, (1 << n)-1) for n in (8, 16, 32, 64)}}


def type_name(message):
    cls = type(message)
    parts = cls.__module__.split(".")
    if len(parts) < 3 or parts[1] != "msg":
        raise TypeError("not a generated ROS message type")
    return parts[0] + "/msg/" + cls.__name__


def _qualified(name):
    match = re.fullmatch(r"([a-z][a-z0-9_]*)/(?:msg/)?([A-Za-z][A-Za-z0-9_]*)", name)
    if not match:
        raise TypeError("unknown field type: " + name)
    return match[1] + "/msg/" + match[2]


def _value(kind, value, depth):
    if depth > 24:
        raise ValueError("message nesting limit")
    sequence = re.fullmatch(r"(?:sequence|bounded_sequence)<(.+?)(?:,\s*(\d+))?>", kind)
    fixed = re.fullmatch(r"(.+)\[(\d+)\]", kind)
    if sequence or fixed:
        element = (sequence or fixed)[1].strip()
        size = int((sequence or fixed)[2]) if (sequence or fixed)[2] is not None else None
        if isinstance(value, (str, bytes, bytearray, dict)) or not hasattr(value, "__len__"):
            raise TypeError("expected complete field sequence")
        if (fixed and len(value) != size) or (sequence and size is not None and len(value) > size):
            raise ValueError("sequence bound differs")
        if len(value) > 100000:
            raise ValueError("small tracking message sequence limit")
        # ROS float arrays are array('f') or numpy arrays. Read raw buffers,
        # avoiding an intermediate Python float that could quiet a signaling NaN.
        if element in {"float", "float32", "double", "float64"}:
            width = 4 if element in {"float", "float32"} else 8
            try:
                view = memoryview(value)
            except TypeError:
                view = None
            if view is not None:
                if view.ndim != 1 or not view.c_contiguous or view.itemsize != width or view.format not in {"f", "d", "<f", ">f", "<d", ">d", "=f", "=d"}:
                    raise TypeError("unexpected float buffer format")
                if view.format[-1] != ("f" if width == 4 else "d"):
                    raise TypeError("float buffer width differs")
                raw = view.tobytes()
                little = view.format[0] == "<" or (view.format[0] not in "<>" and sys.byteorder == "little")
                return {"type": kind, "length": len(value), "items": [
                    {"type": element, "bits_be": (raw[i:i+width][::-1] if little else raw[i:i+width]).hex()}
                    for i in range(0, len(raw), width)]}
        return {"type": kind, "length": len(value), "items": [_value(element, item, depth+1) for item in value]}
    if kind in {"bool", "boolean"}:
        if type(value) is not bool:
            raise TypeError("bool field type differs")
        return {"type": kind, "value": value}
    if kind in INTEGERS:
        low, high = INTEGERS[kind]
        if type(value) is not int or not low <= value <= high:
            raise ValueError("integer field type/range differs")
        return {"type": kind, "value": value}
    if kind in {"float", "float32", "double", "float64"}:
        width = 4 if kind in {"float", "float32"} else 8
        if type(value) is not float:
            # Generated ROS setters can retain numpy.float64 instances. Their
            # zero-dimensional buffer certifies bits without Python conversion.
            try:
                view = memoryview(value)
            except TypeError:
                view = None
            if (view is None or view.ndim != 0 or not view.c_contiguous or view.itemsize != width
                    or view.format not in ({"f","<f",">f","=f"} if width == 4 else {"d","<d",">d","=d"})):
                raise TypeError("scalar float lacks a certifiable exact-width representation")
            raw=view.tobytes()
            little=view.format[0]=="<" or (view.format[0] not in "<>" and sys.byteorder=="little")
            return {"type":kind,"bits_be":(raw[::-1] if little else raw).hex()}
        if width == 4 and math.isnan(value):
            raise ValueError("scalar float32 NaN payload not certifiable")
        return {"type": kind, "bits_be": struct.pack(">f" if width == 4 else ">d", value).hex()}
    string = re.fullmatch(r"string(?:<=([0-9]+))?", kind)
    if string:
        if type(value) is not str or (string[1] is not None and len(value) > int(string[1])):
            raise ValueError("string type/bound differs")
        return {"type": kind, "utf8_hex": value.encode("utf-8", errors="strict").hex()}
    expected = _qualified(kind)
    if type_name(value) != expected:
        raise TypeError("nested message type differs")
    return _message(value, depth+1)


def _message(message, depth):
    fields = message.get_fields_and_field_types()
    if type(fields) is not dict or not fields or any(type(k) is not str or type(v) is not str for k, v in fields.items()):
        raise TypeError("invalid complete message field schema")
    slots = type(message).__slots__
    if tuple(slots) != tuple("_" + key for key in fields):
        raise TypeError("message slots and field schema differ")
    return {"type": type_name(message), "fields": [
        {"name": name, "value": _value(kind, getattr(message, name), depth)} for name, kind in fields.items()]}


def snapshot(message):
    if type_name(message) not in ROOT_TYPES:
        raise TypeError("not one of the three declared tracking message types")
    return _message(message, 0)


def valid_snapshot(value):
    """Validate the trace representation itself without trusting a marker flag."""
    def check(item, depth=0):
        if depth > 30 or type(item) is not dict or type(item.get("type")) is not str:
            return False
        kind = item["type"]
        if "fields" in item:
            fields = item["fields"]
            if re.fullmatch(r"[a-z][a-z0-9_]*/msg/[A-Za-z][A-Za-z0-9_]*",kind) is None:
                return False
            return (set(item) == {"type", "fields"} and type(fields) is list and bool(fields)
                    and len({x.get("name") for x in fields if type(x) is dict}) == len(fields)
                    and all(type(x) is dict and set(x) == {"name", "value"} and type(x["name"]) is str
                            and check(x["value"], depth+1) for x in fields))
        if "items" in item:
            parsed=re.fullmatch(r"(?:sequence|bounded_sequence)<(.+?)(?:,\s*(\d+))?>",kind)
            fixed=re.fullmatch(r"(.+)\[(\d+)\]",kind)
            if not parsed and not fixed:
                return False
            base=(parsed or fixed)[1].strip();bound=(parsed or fixed)[2]
            try:expected=base if base in INTEGERS or base in {"bool","boolean","float","float32","double","float64","string"} or re.fullmatch(r"string<=[0-9]+",base) else _qualified(base)
            except (TypeError,ValueError):return False
            return (set(item) == {"type", "length", "items"} and type(item["length"]) is int
                    and type(item["items"]) is list and item["length"] == len(item["items"])
                    and (not fixed or item["length"]==int(bound)) and (not parsed or bound is None or item["length"]<=int(bound))
                    and all(x.get("type")==expected and check(x, depth+1) for x in item["items"] if type(x) is dict)
                    and all(type(x) is dict for x in item["items"]))
        if kind in INTEGERS:
            return set(item) == {"type", "value"} and type(item["value"]) is int and INTEGERS[kind][0] <= item["value"] <= INTEGERS[kind][1]
        if kind in {"bool", "boolean"}:
            return set(item) == {"type", "value"} and type(item["value"]) is bool
        if kind in {"float", "float32", "double", "float64"}:
            width = 8 if kind in {"float", "float32"} else 16
            return set(item) == {"type", "bits_be"} and type(item["bits_be"]) is str and re.fullmatch("[0-9a-f]{"+str(width)+"}", item["bits_be"]) is not None
        if re.fullmatch(r"string(?:<=[0-9]+)?", kind):
            if set(item) != {"type", "utf8_hex"} or type(item["utf8_hex"]) is not str:
                return False
            try:
                decoded=bytes.fromhex(item["utf8_hex"]).decode("utf-8")
                match=re.fullmatch(r"string<=([0-9]+)",kind)
                return decoded.encode().hex()==item["utf8_hex"] and (match is None or len(decoded)<=int(match[1]))
            except (ValueError, UnicodeError):
                return False
        return False
    return type(value) is dict and value.get("type") in ROOT_TYPES and check(value)
