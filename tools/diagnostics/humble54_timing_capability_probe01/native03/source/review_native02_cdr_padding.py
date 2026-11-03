"""Describe native02 CDR structure only; never regrade its UNKNOWN result."""
import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "archive/native02_source4102a248_before_typed_message_fix/native02"


def decode_cdr_pose_stamped(payload_hex):
    data = bytes.fromhex(payload_hex)
    if len(data) < 16 or data[:4] not in (b"\x00\x00\x00\x00", b"\x00\x01\x00\x00"):
        raise ValueError("Only exact CDR1 BE/LE with zero options is reviewed")
    endian = "<" if data[1] == 1 else ">"
    sec, nanosec = struct.unpack_from(endian + "iI", data, 4)
    length = struct.unpack_from(endian + "I", data, 12)[0]
    string_end = 16 + length
    if length < 1 or string_end > len(data) or data[string_end - 1] != 0:
        raise ValueError("Invalid CDR string length or terminator")
    text = data[16:string_end - 1].decode("utf-8")
    # CDR alignment is relative to the four-byte encapsulation payload start.
    doubles_start = 4 + ((string_end - 4 + 7) // 8) * 8
    if doubles_start + 7 * 8 != len(data):
        raise ValueError("Unexpected PoseStamped payload extent")
    names = ("pose.position.x", "pose.position.y", "pose.position.z", "pose.orientation.x",
             "pose.orientation.y", "pose.orientation.z", "pose.orientation.w")
    fields = [{"path": "header.stamp.sec", "type": "int32", "value": sec},
              {"path": "header.stamp.nanosec", "type": "uint32", "value": nanosec},
              {"path": "header.frame_id", "type": "string", "value": text,
               "utf8_hex": data[16:string_end - 1].hex()}]
    for index, name in enumerate(names):
        bits = data[doubles_start + index * 8:doubles_start + (index + 1) * 8]
        fields.append({"path": name, "type": "float64",
                       "bits_be_hex": (bits[::-1] if endian == "<" else bits).hex()})
    return {"encapsulation_hex": data[:4].hex(), "payload_bytes": len(data),
            "string_with_nul_span": [16, string_end], "padding_span": [string_end, doubles_start],
            "float64_span": [doubles_start, len(data)], "fields": fields}


def main():
    summary_bytes = (ARCHIVE / "summary.json").read_bytes()
    raw_bytes = (ARCHIVE / "raw_events.json").read_bytes()
    assert hashlib.sha256(summary_bytes).hexdigest() == "cb7636b1cea32dd4d071879da1747baa384d4aab1d95754ad7402efdf9b51340"
    assert hashlib.sha256(raw_bytes).hexdigest() == "64534f05541986fc16dc4c7b9229162608005d7e56598cd6ce5504c7e320a33f"
    summary = json.loads(summary_bytes)
    events = {item["event_index"]: item for item in json.loads(raw_bytes)["events"]}
    pairs = []
    for phase in summary["phases"]:
        for pair in phase["pairs"]:
            assert len(pair["publish_event_indices"]) == 1
            pub = events[pair["publish_event_indices"][0]]
            take = events[pair["take_event_index"]]
            left = decode_cdr_pose_stamped(pub["payload_hex"])
            right = decode_cdr_pose_stamped(take["payload_hex"])
            different = [index for index, (a, b) in enumerate(zip(bytes.fromhex(pub["payload_hex"]),
                                                                       bytes.fromhex(take["payload_hex"]))) if a != b]
            padding = set(range(*left["padding_span"]))
            pairs.append({"phase": phase["phase"], "publish_event_index": pub["event_index"],
                          "take_event_index": take["event_index"], "original_status": pair["status"],
                          "original_reasons": pair["reasons"],
                          "publish_payload_hex": pub["payload_hex"], "take_payload_hex": take["payload_hex"],
                          "publish_cdr_structure": left, "take_cdr_structure": right,
                          "different_byte_offsets": different,
                          "all_typed_fields_equal": left["fields"] == right["fields"],
                          "differences_only_in_padding": (left["payload_bytes"] == right["payload_bytes"]
                              and left["padding_span"] == right["padding_span"] and set(different) <= padding)})
    result = {"kind": "NATIVE02_ORIGINAL_CDR_STRUCTURE_DESCRIPTION_NOT_REGRADED",
              "original_native_status": summary["status"], "original_raw_event_count": len(events),
              "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
              "raw_events_sha256": hashlib.sha256(raw_bytes).hexdigest(),
              "review_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "Only decode the already-declared original candidate pairs; no rematching, capability promotion, strict/E2E or native rerun.",
              "pair_count": len(pairs), "all_pairs_typed_equal_and_only_padding_different":
                  all(pair["all_typed_fields_equal"] and pair["differences_only_in_padding"] for pair in pairs),
              "pairs": pairs}
    output = ROOT / "native02_cdr_padding_review.json"
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"pair_count": result["pair_count"], "padding_only": result["all_pairs_typed_equal_and_only_padding_different"],
                      "original_status_retained": result["original_native_status"], "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
