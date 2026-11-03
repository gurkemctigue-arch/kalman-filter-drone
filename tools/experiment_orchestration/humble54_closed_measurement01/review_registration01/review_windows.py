"""Read-only review of literal registration; never imports the runner or starts WSL."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PINNED_AFTER = "47fcbd727debbdb418bb9fbb1cc6a5abeb9806855f6331709c8590c688232433"
MAX_ORIGINAL_BYTES = 16 * 1024 * 1024
ALLOWED = {"PRODUCTION_ENABLED", "REGISTERED_INPUTS"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def literals_and_remainder(source: str):
    tree = ast.parse(source)
    found = {}
    omitted = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in ALLOWED:
                assert target.id not in found, target.id
                found[target.id] = ast.literal_eval(node.value)
                omitted.update(range(node.lineno, node.end_lineno + 1))
    assert set(found) == ALLOWED
    remainder = "".join(
        line for number, line in enumerate(source.splitlines(keepends=True), 1)
        if number not in omitted
    )
    return found, remainder


def main():
    reg_path = BASE / "registration01/registration.json"
    reg_bytes = reg_path.read_bytes()
    registration = json.loads(reg_bytes)
    before_path = BASE / "registration01/run_closed_measurement.pre_registration.py"
    after_path = BASE / "run_closed_measurement.py"
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    assert digest(before) == registration["before_sha256"]
    assert digest(after) == registration["after_sha256"] == PINNED_AFTER
    assert before == (BASE / "prepared_snapshot01/run_closed_measurement.py").read_bytes()
    old_values, old_remainder = literals_and_remainder(before.decode("utf-8"))
    new_values, new_remainder = literals_and_remainder(after.decode("utf-8"))
    assert old_values == {"PRODUCTION_ENABLED": False, "REGISTERED_INPUTS": {}}
    assert new_values == {
        "PRODUCTION_ENABLED": True,
        "REGISTERED_INPUTS": registration["bindings"],
    }
    assert old_remainder == new_remainder
    bindings = registration["bindings"]
    expected_names = {"collector", "profile", "terminal", "events", "admission", "monitor_state", "launcher_terminal"}
    assert set(bindings) == set(registration["host_originals"]) == expected_names
    artifacts = []
    for name in sorted(expected_names):
        binding = bindings[name]
        native_path = binding["path"]
        host_path = registration["host_originals"][name]
        if native_path.startswith("/mnt/d/"):
            expected_host = "D:\\" + native_path[len("/mnt/d/"):].replace("/", "\\")
        else:
            assert native_path.startswith("/root/")
            expected_host = "\\\\wsl.localhost\\UAVHumble22" + native_path.replace("/", "\\")
        assert host_path == expected_host
        original = Path(host_path)
        size = original.stat().st_size
        assert original.is_file() and size <= MAX_ORIGINAL_BYTES, (name, size)
        content = original.read_bytes()
        actual_sha = digest(content)
        assert actual_sha == binding["sha256"], name
        artifacts.append({"name": name, "native_path": native_path,
                          "host_original": host_path, "bytes": size,
                          "sha256": actual_sha, "matches_registered": True})
    result = {
        "schema_version": 1,
        "reviewed_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": "/root/continuation06_preparation",
        "status": "LITERAL_CONFIGURATION_AND_SEVEN_ORIGINAL_BINDINGS_VERIFIED",
        "registration_sha256": digest(reg_bytes),
        "before_sha256": digest(before), "after_sha256": digest(after),
        "changes": ["PRODUCTION_ENABLED False -> True", "REGISTERED_INPUTS {} -> seven actual original path/SHA bindings"],
        "all_other_source_text_identical": True,
        "pre_source_equals_reviewed_prepared_snapshot": True,
        "steps_locks_thresholds_changed": False,
        "artifacts": artifacts,
        "total_original_bytes_read": sum(x["bytes"] for x in artifacts),
        "conclusion": "No blocking issue in this literal registration difference. Existing execution semantics remain unchanged; runner revalidates actual inputs at execution.",
        "boundaries": ["No runner import, native/WSL command, bag/model payload read or simulation launch", "Registration review does not establish measurement success, readiness or formal admission"],
    }
    output = HERE / "independent_review01.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "artifact_count": len(artifacts),
                      "total_original_bytes_read": result["total_original_bytes_read"],
                      "receipt_sha256": digest(output.read_bytes())}, indent=2))


if __name__ == "__main__":
    main()
