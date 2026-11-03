"""Real CDR/schema compatibility only; no ROS init, publishers, bags or flight."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import schema_probe07
import typed_message as codec
from observer import load_probe


def c7_typed_case(probe, before_fields, after_fields):
    """Synthetic DDS timestamps isolate the unchanged c7 typed-field predicate."""
    phase="real_cdr_schema_compatibility";writer="schema_probe"
    anchor=lambda n:{"monotonic_before_ns":n,"monotonic_after_ns":n,"realtime_ns":n+1_000_000}
    events=[]
    def emit(kind,when,**fields):
        events.append({"kind":kind,"phase":phase,"recorded_monotonic_ns":when,"event_index":len(events),**fields})
    emit("controlled_writers",900,writers=[writer])
    emit("graph",1000,publishers=[{"node_name":writer,"gid_hex":"synthetic_schema_case"}])
    emit("publish",2003,writer_token=writer,before=anchor(2000),after=anchor(2002),success=True,message_fields=before_fields)
    emit("take",2007,entered_ns=2005,exited_ns=2006,capture_status="CAPTURED",
         metadata={"source_timestamp":1_002_001},message_fields=after_fields)
    emit("graph",3000,publishers=[{"node_name":writer,"gid_hex":"synthetic_schema_case"}])
    emit("controlled_writers",3100,writers=[writer])
    return probe.assess(events,phase)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);args=parser.parse_args()
    from rclpy.serialization import serialize_message,deserialize_message
    from uav_tracking_interfaces.msg import TargetObservationArray,TargetObservation,TargetState,TrackingCommand
    probe_path=Path(__file__).resolve().parent.parent/"humble54_timing_capability_probe01/probe.py"
    probe=load_probe(probe_path)
    original_pose_validator=probe.valid_pose_stamped_fields
    # This is the exact private compatibility binding already used by reducer.
    probe.valid_pose_stamped_fields=codec.valid_snapshot
    array=TargetObservationArray();observation=TargetObservation();observation.depth_valid=True
    array.observations=[observation]
    state=TargetState();state.target_visible=True
    command=TrackingCommand();command.valid=True;command.mode=1
    report={"scope":"REAL_CDR_AND_TYPED_SCHEMA_COMPATIBILITY_NOT_ACTUAL_DDS_OR_PIPELINE_TIMING",
            "python":sys.version,"codec_sha256":hashlib.sha256(Path(codec.__file__).read_bytes()).hexdigest(),
            "probe_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "c7_source_sha256":hashlib.sha256(probe_path.read_bytes()).hexdigest(),
            "ros_init_called":False,"publishers_created":False,"bags_opened":False,"weights_opened":False,
            "actual_dds_edges":"NOT_OBSERVED_BY_THIS_PROBE","actual_pipeline_latency":"NOT_OBSERVED_BY_THIS_PROBE",
            "historical_short03_reclassified":False,"historical_strict_changed":False,"physical_e2e":"NOT_OBSERVED","types":[]}
    passed=True
    for message in (array,state,command):
        wire=serialize_message(message);received=deserialize_message(wire,type(message))
        original=schema_probe07.describe(message);roundtrip=schema_probe07.describe(received)
        encoded,decoded=original["snapshot"],roundtrip["snapshot"]
        success=encoded["status"]==decoded["status"]=="PASS"
        row={"root":type(message).__name__,"original":original,"cdr_roundtrip":roundtrip,
             "cdr_bytes":len(wire),"cdr_sha256":hashlib.sha256(wire).hexdigest(),
             "cdr_typed_fields_equal":success and encoded["value"]==decoded["value"]}
        if success:
            row.update(new_validator_accepts_original=codec.valid_snapshot(encoded["value"]),
                       new_validator_accepts_cdr=codec.valid_snapshot(decoded["value"]),
                       original_pose_validator_accepts_tracking_type=original_pose_validator(encoded["value"]),
                       c7_private_typed_compatibility_case=c7_typed_case(probe,encoded["value"],decoded["value"]))
        passed=passed and row["cdr_typed_fields_equal"] and row.get("new_validator_accepts_original") is True \
               and row.get("new_validator_accepts_cdr") is True \
               and row.get("c7_private_typed_compatibility_case",{}).get("candidate_count")==1
        report["types"].append(row)
    report["status"]="PASS_REAL_CDR_SCHEMA_AND_SYNTHETIC_C7_TYPED_CASES_ONLY" if passed else "FAILED_SCHEMA_COMPATIBILITY"
    with Path(args.output).open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write("\n")
    print(json.dumps({"status":report["status"],"output":args.output,"types":[
        {"root":r["root"],"cdr_typed_fields_equal":r["cdr_typed_fields_equal"],
         "c7_synthetic_candidate_count":r.get("c7_private_typed_compatibility_case",{}).get("candidate_count")}
        for r in report["types"]]}))
    return 0 if passed else 2


if __name__=="__main__":raise SystemExit(main())
