"""Copy bounded source/receipt evidence only; never run reports or evaluators."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXTERNAL = Path("D:/WSL/UAVHumble22-validation")
CAP = 1024 ** 2


def raw(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > CAP:
        raise ValueError("Ordinary small source/receipt required: " + str(path))
    data = path.read_bytes()
    if len(data) > CAP:
        raise ValueError("Source grew beyond cap")
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(wording_review, wording_diff):
    author = EXTERNAL / "report_attachment_integration54_01"
    independent = EXTERNAL / "research_delivery_attachments_review54_01"
    earlier = json.loads(raw(author / "author_receipt01.json"))
    final = json.loads(raw(author / "author_receipt02_identity_wording.json"))
    files = []
    for name, binding in final["sources_after"].items():
        source = ROOT / name
        data = raw(source)
        if digest(data) != binding["sha256"] or len(data) != binding["bytes"]:
            raise ValueError("Current source differs from final wording receipt")
        files.append((source, Path("source") / name, binding["sha256"]))
    for name in ("author_receipt01.json", "author_tests01.log", "author_source_diff01.patch",
                 "author_receipt02_identity_wording.json", "author_tests02_identity_wording.log", "author_source_diff02.patch"):
        files.append((author / name, Path("evidence/author") / name, None))
    for name in ("independent_review01.json", "independent_source_decision01.json",
                 "independent_unittest01.log", "review_attachment_wiring.py"):
        files.append((independent / name, Path("evidence/independent") / name, None))
    files.extend(((Path(wording_review), Path("evidence/independent") / Path(wording_review).name, None),
                  (Path(wording_diff), Path("evidence/independent") / Path(wording_diff).name, None)))
    rows = []
    for original, relative, expected in files:
        data = raw(original)
        observed = digest(data)
        if expected is not None and expected != observed:
            raise ValueError("Changed copied source")
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        if raw(target) != data:
            raise ValueError("Copy changed bytes")
        rows.append({"snapshot_path": relative.as_posix(), "source_path": str(original.resolve()),
                     "bytes": len(data), "sha256": observed, "copied_byte_for_byte": True})
    manifest = {"schema_version": 1, "kind": "SAVED_SMALL_REPORT_ATTACHMENT_WIRING_EVIDENCE_NOT_RESEARCH_RESULTS",
        "created_utc": datetime.now(timezone.utc).isoformat(), "files": rows,
        "copied_file_count": len(rows), "copied_bytes": sum(row["bytes"] for row in rows),
        "prior_38_test_source_pins": earlier["sources_after"], "final_source_pins": final["sources_after"],
        "test_boundary": "Both author and independent 38-test runs precede one final identity-boundary paragraph. Current report pin has AST plus two targeted tests and independent wording diff acceptance; do not retroactively attribute 38 tests to it.",
        "external_tooling_only": True, "frozen54_or_flight_registration_modified": False,
        "actual_report_or_docx_generated": False, "raw_data_read": False, "native_execution": False,
        "collector": {"sha256": digest(raw(__file__)), "bytes": len(raw(__file__))}}
    with (OUT / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"copied_file_count": len(rows), "copied_bytes": manifest["copied_bytes"],
                      "manifest_sha256": digest(raw(OUT / "manifest.json"))}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wording-review", type=Path, required=True)
    parser.add_argument("--wording-diff", type=Path, required=True)
    args = parser.parse_args()
    collect(args.wording_review, args.wording_diff)
