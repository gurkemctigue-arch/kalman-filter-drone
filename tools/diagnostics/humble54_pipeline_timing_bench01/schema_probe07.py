"""Small real generated-message/CDR probe; never initializes ROS or reads bags."""
from __future__ import annotations
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import struct
import sys
import traceback

import typed_message as codec


def captured(call):
    try:
        return {"status":"PASS","value":call()}
    except Exception as error:
        return {"status":"ERROR","exception_type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()}


def raw_value(value):
    if hasattr(value,"get_fields_and_field_types"):
        return raw_message(value)
    if isinstance(value,(list,tuple)) or type(value).__module__=="array" or hasattr(value,"dtype") and hasattr(value,"__len__"):
        return {"kind":"sequence","items":[raw_value(item) for item in value]}
    if type(value) is bool:
        return {"kind":"bool","value":value}
    if type(value) is int:
        return {"kind":"int","value":value}
    if type(value) is float:
        return {"kind":"float","bits_be":struct.pack(">d",value).hex()}
    if type(value) is str:
        return {"kind":"str","value":value}
    return {"kind":"UNSUPPORTED","python_type":type(value).__module__+"."+type(value).__name__}


def raw_message(message):
    cls=type(message)
    return {"kind":"message","python_module":cls.__module__,"class_name":cls.__name__,
            "slots":list(cls.__slots__),"schema":message.get_fields_and_field_types(),
            "values":{name:raw_value(getattr(message,name)) for name in message.get_fields_and_field_types()}}


def describe(message):
    cls=type(message);source=Path(inspect.getfile(cls));fields=message.get_fields_and_field_types()
    return {"python_module":cls.__module__,"class_name":cls.__name__,"source_path":str(source),
            "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"slots":list(cls.__slots__),
            "schema":fields,"type_name":captured(lambda:codec.type_name(message)),
            "snapshot":captured(lambda:codec.snapshot(message)),"raw_default_message":raw_message(message),
            "fields":[{"name":name,"declared_type":kind,
                       "value_python_type":type(getattr(message,name)).__module__+"."+type(getattr(message,name)).__name__,
                       "typed_value":captured(lambda kind=kind,name=name:codec._value(kind,getattr(message,name),0))}
                      for name,kind in fields.items()]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);args=parser.parse_args()
    from rclpy.serialization import serialize_message,deserialize_message
    from uav_tracking_interfaces.msg import TargetObservationArray,TargetState,TrackingCommand
    report={"scope":"REAL_GENERATED_TYPES_AND_ORIGINAL_CDR_ONLY_NOT_PIPELINE_OR_DDS_TIMING",
            "python":sys.version,"codec_path":codec.__file__,"codec_sha256":hashlib.sha256(Path(codec.__file__).read_bytes()).hexdigest(),
            "ros_init_called":False,"publishers_created":False,"bags_opened":False,"weights_opened":False,"types":[]}
    for cls in (TargetObservationArray,TargetState,TrackingCommand):
        message=cls();row={"declared_root":cls.__name__,"original":describe(message)}
        wire=serialize_message(message);roundtrip=deserialize_message(wire,cls)
        row.update(cdr_bytes=len(wire),cdr_sha256=hashlib.sha256(wire).hexdigest(),cdr_hex=wire.hex(),
                   cdr_roundtrip=describe(roundtrip),same_class_after_cdr=type(roundtrip) is cls)
        report["types"].append(row)
    with Path(args.output).open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write("\n")
    print(json.dumps({"output":args.output,"codec_sha256":report["codec_sha256"],"roots":[
        {"name":row["declared_root"],"python_module":row["original"]["python_module"],
         "type_name":row["original"]["type_name"],"slots":row["original"]["slots"],"schema":row["original"]["schema"],
         "snapshot":row["original"]["snapshot"],"cdr_roundtrip_snapshot":row["cdr_roundtrip"]["snapshot"]}
        for row in report["types"]]},ensure_ascii=False))


if __name__=="__main__":main()
