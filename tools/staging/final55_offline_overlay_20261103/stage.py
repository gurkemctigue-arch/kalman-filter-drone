"""Prepare one new final55 source staging tree; never build, fly or register.

The default action only reads. --execute creates a new staging tree and a new
external receipt directory. Production pins are fixed here, not CLI overrides.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


PROJECT = Path(__file__).resolve().parents[3]
RUNNER = "scripts/run_reliability_v4.py"
MAIN = "planning/reliability-v4-preregistration.json"
PLANNING = (MAIN, "planning/reliability-v4-extension-preregistration.json", "planning/reliability-v4-estimator-replay-preregistration.json")
FIELD = "development_input_interruption_evidence"
SCOPE = "DEVELOPMENT_EVIDENCE_ONLY_NOT_FORMAL_ADMISSION"
BASIS = "POST_HOC_DEVELOPMENT_SOURCE_BINDING_NOT_FORMAL_PREREGISTRATION"
FILTERS = ("__pycache__", ".pytest_cache", "results/", ".git/", "node_modules/", ".test_temp/", "*.egg-info/", "ros2_ws/build/", "ros2_ws/install/", "ros2_ws/log/")
NESTED = ("ros2_ws/src/uav_tracking_nodes/build/", "ros2_ws/src/uav_tracking_px4_adapter/build/")
EXCLUDED17 = tuple("ros2_ws/src/uav_tracking_nodes/build/lib/" + name for name in (
    "uav_tracking/__init__.py", "uav_tracking/control/__init__.py", "uav_tracking/control/follow_controller.py",
    "uav_tracking/control/gimbal_controller.py", "uav_tracking/core/__init__.py", "uav_tracking/core/geometry.py",
    "uav_tracking/core/kalman.py", "uav_tracking/core/models.py", "uav_tracking/core/target_manager.py",
    "uav_tracking/experiments.py", "uav_tracking/simulation.py", "uav_tracking_nodes/__init__.py",
    "uav_tracking_nodes/controller_node.py", "uav_tracking_nodes/detector_node.py", "uav_tracking_nodes/state_estimator_node.py")) + (
    "ros2_ws/src/uav_tracking_px4_adapter/build/lib/uav_tracking_px4_adapter/__init__.py",
    "ros2_ws/src/uav_tracking_px4_adapter/build/lib/uav_tracking_px4_adapter/adapter_node.py")
OVERLAYS = (
    ("scripts/evaluate_navigation_reference.py", 38019, "bbff6c746ed76d0139c194cdfc1409f38dc422d64ddbc73da2995a0838df4422", 38185, "b49984d495ec7b12e623e961f3d606958aaef682ddfbc636f9c21ed2d52abcb4"),
    ("scripts/build_reliability_v4_probe_gate.py", 24430, "cf28d5455ceaa1eb52c498ba1048782c2fea35b65a0c8b2af4bddffae633d36f", 41607, "fa7d150a0e68b4678d0727139e206e20a629971d7bfeae0882d0f804381185ae"),
    (RUNNER, 168418, "069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11", 182356, "eab5c1b9ed8a5d3c304f6986aaf959a49a4349356aedb6335c36683895a217ba"),
    ("tests/test_navigation_evaluation.py", 30212, "7d93c359bc0827d33f2f615dc5033ee98ee9d286c90a280213c7dec216f9bfb0", 34500, "634b8f5fe8f7e94de8747f68bba754196e865a2896f63c5f07bb36c5bca79510"),
    ("tests/test_reliability_v4_probe_gate.py", 19222, "628b74d562ce6f8e9255a2c3e990e95983e1e7f63081b77ce5ce1bae73ab1ded", 53086, "38c88e55f5d8b75c3c4f8c7e90ba4920a29fbd02fda21979dfe44886bb64a5ea"),
    ("tests/test_reliability_v4_runner.py", 121066, "07157bb4ea05abab0fb8ebd46b411f302ce4fa437d9e4858449d0a7920d796c3", 121218, "c0852dea246bcde137461e9fbf3af74b0c01246127433da6b90e8af682b20f44"),
    ("tools/diagnostics/reliability54_build01/record_native_validation.py", 7622, "9cfd2d181b943df7551c912813e674635a66cef06ec409141d4a6cba33f3b0e8", 10873, "a3f177546432f698b8d7acabf0c4e2229fe42db524e7ff9da7cf0791bd5b33a6"),
    ("tests/test_frozen_fastcdr_selection.py", 3466, "bee6e644f1e47554e31932afb2302c80c9a05d0d114011e19d4c9d0843f745c2", 3817, "ef36ab0e9055fb2eb74880756ab83a89b6bd4f023467aa0819b02a3217deb0c6"),
    ("tools/offline_evaluation/sensor_input_interruption_v1/evidence.py", None, None, 33761, "f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba"),
    ("tools/offline_evaluation/sensor_input_interruption_v1/test_evidence.py", None, None, 28796, "c577a1010381d2cd3afb698a18fb25c1849aea5b454c503aa7d16310688b8154"))
PROFILE = {
    "scope":"REAL_FINAL55_PRE_COLD_SOURCE_PREPARATION_ONLY", "overlays":OVERLAYS, "excluded":EXCLUDED17,
    "core_sha":"ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b",
    "core_digest":"3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31",
    "extension_sha":"f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055",
    "extension_digest":"ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761",
    "full_sha":"cdb4111738f2f51c9911e3e7cebaf9f69aafd92d5cef39d8839a1e5dbb27c82f",
    "full_count":1585, "source_count":308, "scanner_count":185, "flight_count":277, "model_count":6,
    "source_digest":"8a11b73428d6d4adacc042a41072a2e4da1dd7ed17756760073958f44ed21cb9",
    "overlay_source_digest":"e1d22d7a858aa37eb382b6b365f3fdaeff09803be3669831dc92efbb2a8150b3",
    "overlay_scanner_digest":"bdd24da4b8378ffb5502940913096fbd7b3499335de037536bee50e20f1fbde4",
    "module_sha":"f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba",
    "contract_sha":"f4f5d040b9701dcd6a2fcafbcb672699ba2c16940c1f712756d5d83193e93ea0",
    "contract_digest":"35f61541d5eab4fddd856a9c4b9ed76f2d6e0c66a8d172cf94256129e2315c17",
    "research_sha":"65713c9395bf101aa5937039311b4f3b4fed29e6a649f09ec0433004f7a09171"}


class Refused(ValueError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value, excluded=()):
    return hashlib.sha256(canonical({k:v for k,v in value.items() if k not in excluded})).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
        parse_constant=lambda value:(_ for _ in ()).throw(Refused("Nonfinite JSON")))


def binding(path):
    path = Path(path).resolve(strict=True)
    return {"path":str(path), "sha256":sha(path)}


def relative(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name == path.as_posix() and not path.is_absolute()
        and ".." not in path.parts and "\\" not in name, "Unsafe registered relative path")
    return name


def excluded(name, directory):
    for pattern in FILTERS:
        if pattern.endswith("/") and not directory:
            continue
        value = pattern.rstrip("/")
        candidate = name if "/" in value else name.rsplit("/", 1)[-1]
        if fnmatch.fnmatchcase(candidate, value):
            return True
    return False


def file_map(root):
    """Match the unchanged public rsync-filtered complete-map semantics."""
    root = Path(root).resolve(strict=True)
    result = {}
    def walk(folder, prefix=""):
        with os.scandir(folder) as stream:
            entries = sorted(stream, key=lambda item:item.name)
        for entry in entries:
            name = relative(prefix + entry.name)
            directory = entry.is_dir(follow_symlinks=False)
            if excluded(name, directory):
                continue
            path = Path(entry.path)
            if entry.is_symlink():
                result[name] = {"kind":"symlink", "target":os.readlink(path)}
            elif directory:
                walk(path, name + "/")
            elif entry.is_file(follow_symlinks=False):
                before = path.stat(follow_symlinks=False)
                value = sha(path)
                after = path.stat(follow_symlinks=False)
                require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                    == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns), "Source changed while hashing: " + name)
                result[name] = {"kind":"file", "bytes":after.st_size, "sha256":value}
            else:
                raise Refused("Unsupported source entry: " + name)
    walk(root)
    return result


def runner_rules(path):
    """Parse literal classifier constants from already hash-verified source."""
    values, helpers = {}, set()
    for node in ast.parse(Path(path).read_text(encoding="utf-8-sig")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"HASH_FOLDERS", "HASH_SUFFIXES", "OFFLINE_HELPERS"}:
                    values[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "OFFLINE_HELPERS":
                require(call.func.attr in {"add", "update"} and len(call.args) == 1, "Unexpected classifier mutation")
                value = ast.literal_eval(call.args[0])
                helpers.update([value] if call.func.attr == "add" else value)
    require(set(values) == {"HASH_FOLDERS", "HASH_SUFFIXES", "OFFLINE_HELPERS"}, "Missing literal source classifier")
    return tuple(values["HASH_FOLDERS"]), set(values["HASH_SUFFIXES"]), set(values["OFFLINE_HELPERS"]) | helpers


def source_map(entries, rules):
    folders, suffixes, _ = rules
    result = {}
    for name, item in entries.items():
        path = PurePosixPath(relative(name))
        scanned = any(name.startswith(folder + "/") for folder in folders)
        skipped = any(part in {"build", "install", "log", "__pycache__", ".git"} or part.endswith(".egg-info") for part in path.parts)
        selected = (scanned and path.suffix.lower() in suffixes and not skipped) or (
            len(path.parts) == 1 and path.suffix in {".py", ".toml", ".cfg", ".xml", ".txt"})
        if selected:
            require(item.get("kind") == "file", "Scanned source cannot be a symlink: " + name)
            result[name] = item["sha256"]
    return result


def scanner_map(entries):
    return {name:item["sha256"] for name,item in entries.items() if item.get("kind") == "file"
        and name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/")) and PurePosixPath(name).suffix in {".py", ".sh", ".msg"}}


def flight_map(entries, rules):
    return {name:value for name,value in entries.items() if name != RUNNER
        and not name.startswith("scripts/evaluate_") and name not in rules[2]}


def compare(expected, actual, label):
    delta = {"missing":sorted(expected.keys()-actual.keys()), "added":sorted(actual.keys()-expected.keys()),
             "changed":sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])}
    require(not any(delta.values()), label + " differs: " + json.dumps(delta))


def ordinary(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path, "Canonical ordinary file required: " + str(path))
    return path


def source_snapshot(source, expected_store):
    """Strict Linux results-link boundary, isolated for portable fixture tests."""
    source = Path(source)
    actual = file_map(source)
    link = actual.pop("results", None)
    require((source / "results").is_symlink() and link == {"kind":"symlink", "target":os.readlink(source / "results")}
        and (source / "results").resolve(strict=True) == expected_store, "Original generated results link/store differs")
    return actual, link


def closed_records(plan):
    result = []
    for trial in plan["trials"]:
        path = (Path(plan["output"]) / "slots" / (trial["id"] + ".json")).resolve(strict=True)
        row = load(ordinary(path))
        require(row.get("record_sha256") == digest(row, ("record_sha256",)) and row.get("id") == trial["id"]
            and row.get("plan_sha256") == plan["plan_sha256"], "Original terminal digest/source differs")
        require(row.get("status") in {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING"}
            and row.get("execution_status") == "COMPLETED" and row.get("infrastructure_stop") is False
            and type(row.get("flight_exit_code")) is int and row["flight_exit_code"] == 0
            and row.get("cleanup", {}).get("residual_processes") == [], "All 28 original flights must be completed and closed")
        flights = [item for item in row.get("commands", []) if item.get("kind") == "flight"]
        require(len(flights) == 1 and flights[0].get("command") == trial["flight_command"]
            and type(flights[0].get("returncode")) is int and flights[0]["returncode"] == 0 and flights[0].get("error") is None,
            "Original successful flight execution differs")
        finished = datetime.fromisoformat(row["finished_utc"].replace("Z", "+00:00"))
        require(finished.tzinfo is not None and finished.utcoffset().total_seconds() == 0
            and finished <= datetime.now(timezone.utc), "Original finish must be actual UTC in the past")
        result.append(binding(path))
    return result


@contextmanager
def linux_idle_guard():
    require(os.name == "posix" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22", "Production preflight requires native UAVHumble22; no WSL is launched automatically")
    import fcntl
    lock = Path("/tmp/uav_tracking_reliability_v4_sitl.lock")
    require(lock.is_file() and not lock.is_symlink(), "Existing original-flight machine lock required to prove idle")
    with lock.open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refused("An original flight/collector still owns the machine lock") from error
        try:
            blockers = []
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit() or int(proc.name) == os.getpid():
                    continue
                try:
                    argv = [value.decode(errors="replace") for value in (proc / "cmdline").read_bytes().split(b"\0") if value]
                    comm = (proc / "comm").read_text().strip()
                    fields = (proc / "stat").read_text().rpartition(")")[2].split()
                except (FileNotFoundError, ProcessLookupError):
                    continue
                require(comm != "" and fields, "Unreadable process identity")
                if native_blocker(argv, fields[0], comm):
                    blockers.append({"pid":int(proc.name), "comm":comm})
            require(not blockers, "Native workload remains: " + json.dumps(blockers))
            yield {"machine_lock":str(lock), "blockers":[]}
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def native_blocker(argv, state, comm=""):
    """Conservative process evidence, not an owner-terminal closure receipt."""
    if state == "Z":
        return False
    names = [PurePosixPath(value).name for value in argv[:3]]
    identities = [*names, comm]
    if any(name in {"px4","MicroXRCEAgent","gzserver","gz-sim-server"} or name.startswith("gz-sim-") for name in identities):
        return True
    if not argv:
        return False
    return (any(name in {"run_stage1_trial.py","stage1_flight_monitor.py","run_reliability_v4.py","run_reliability_v4_batch.py"}
                or name.startswith(("collect_","collector","evaluate_","extract_","export_estimator_"))
                or "collector" in name or "owner" in name for name in names)
        or ("gz" in names and "sim" in argv)
        or ("colcon" in names and "build" in argv)
        or ("ros2" in names and ("launch" in argv or "bag" in argv))
        or any("/install/lib/uav_tracking_" in value for value in argv[:3]))


def prepare(paths, profile):
    """Only read source/metadata. Tests inject a complete synthetic profile."""
    paths = {key:Path(value) for key,value in paths.items()}
    for key in ("source", "overlay", "core", "extension", "full", "module", "contract"):
        raw = paths[key]
        require(raw.is_absolute(), "Absolute input path required: " + key)
        paths[key] = raw.resolve(strict=True)
    for key in ("stage", "final", "receipt"):
        raw = paths[key]
        require(raw.is_absolute() and not raw.exists() and not raw.is_symlink() and raw.parent.is_dir(), "Fresh path with existing parent required: " + key)
        paths[key] = raw.parent.resolve(strict=True) / raw.name
    roots = [paths[key] for key in ("source", "overlay", "stage", "final", "receipt")]
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a) for i,a in enumerate(roots) for b in roots[i+1:]), "Source/overlay/output roots must be separate siblings or independent trees")
    for key,label,count in (("core","core",12), ("extension","extension",16)):
        require(sha(ordinary(paths[key])) == profile[label + "_sha"], "Pinned original plan file differs: " + key)
    core, extension = load(paths["core"]), load(paths["extension"])
    original_store = paths["core"].parent.parent
    require(all(not paths[key].is_relative_to(original_store) and not original_store.is_relative_to(paths[key])
        for key in ("stage", "final", "receipt")), "Outputs must stay outside original results evidence")
    if profile["scope"] == "REAL_FINAL55_PRE_COLD_SOURCE_PREPARATION_ONLY":
        require(paths["stage"].parent == Path("/root") and re.fullmatch(r"/root/uav_tracking_fullplan_[a-zA-Z0-9_]+", str(paths["final"])),
            "Production source/build staging and future cold root must use dedicated /root paths")
    for key,plan,mode,count in (("core",core,"PROBE",12), ("extension",extension,"EXTENSION_PROBE",16)):
        require(plan.get("plan_sha256") == profile[key + "_digest"] == digest(plan, ("plan_sha256",))
            and plan.get("mode") == mode and plan.get("selected_seeds") == [4] and len(plan["trials"]) == count
            and Path(plan["frozen_root"]).resolve(strict=True) == paths["source"], "Pinned original plan content differs")
    compare(core["source_hashes"], extension["source_hashes"], "Original core/extension source map")
    require(len(core["source_hashes"]) == profile["source_count"] and digest(core["source_hashes"]) == profile["source_digest"], "Original source-map registration differs")
    terminals = closed_records(core) + closed_records(extension)
    require(sha(ordinary(paths["full"])) == profile["full_sha"], "Pinned original full-map metadata differs")
    original = load(paths["full"])
    require(tuple(original.get("rsync_exclusions", [])) == FILTERS and len(original["entries"]) == profile["full_count"], "Original complete-map schema/filter/count differs")
    expected = original["entries"]
    require(all(relative(name) and item.get("kind") == "file" for name,item in expected.items()), "Unexpected original entry kind")
    nested = {name for name in expected if name.startswith(NESTED)}
    require(nested == set(profile["excluded"]), "Named nested build exclusion is not exactly the approved 17 paths")
    require(paths["core"].parent.parent == paths["extension"].parent.parent, "Original plans use different results stores")
    source_full, link = source_snapshot(paths["source"], paths["core"].parent.parent)
    compare(expected, source_full, "Immutable54 complete source")
    rules = runner_rules(ordinary(paths["source"] / RUNNER))
    original_source = source_map(source_full, rules)
    compare(core["source_hashes"], original_source, "Immutable54 registered source map")
    require(len(scanner_map({k:v for k,v in source_full.items() if k not in nested})) == profile["scanner_count"], "Original approved scanner denominator differs")
    compare({name:value for name,value in original_source.items() if name.startswith(("scripts/","uav_tracking/","ros2_ws/src/"))
        and PurePosixPath(name).suffix in {".py",".sh",".msg"}}, scanner_map({k:v for k,v in source_full.items() if k not in nested}),
        "Actual copied54 baseline scanner map")
    models = {name:value for name,value in original_source.items() if name.endswith(".pt")}
    require(len(models) == profile["model_count"] and models == core["model_hashes"] == extension["model_hashes"], "All six original model pins must agree")
    payloads = {}
    for name,old_bytes,old_sha,new_bytes,new_sha in profile["overlays"]:
        relative(name)
        if old_sha is None:
            require(old_bytes is None and name not in expected and not (paths["source"] / name).exists(), "New overlay already exists in original source")
        else:
            require(expected.get(name) == {"kind":"file", "bytes":old_bytes, "sha256":old_sha}, "Original overlay before-pin differs: " + name)
        payload = ordinary(paths["overlay"] / name).read_bytes()
        require(len(payload) == new_bytes and hashlib.sha256(payload).hexdigest() == new_sha, "Reviewed overlay source differs: " + name)
        payloads[name] = payload
    new_rules = runner_rules(paths["overlay"] / RUNNER)
    require(rules == new_rules, "Source classification/scanner rules must remain exactly unchanged")
    public = (paths["source"] / "scripts/freeze_full_plan_workspace.sh").read_text(encoding="utf-8")
    require(tuple(re.findall(r"--exclude='([^']+)'", public)) == FILTERS, "Public freeze exclusions differ")
    documents = {name:load(ordinary(paths["source"] / name)) for name in PLANNING}
    require(all(row.get("status") == "DRAFT_NOT_FROZEN_NOT_EXECUTED" for row in documents.values())
        and FIELD not in documents[MAIN] and documents[MAIN].get("registration_utc") is None
        and documents[MAIN].get("navigation_acceptance", {}).get("status") == "REGISTERED"
        and documents[MAIN]["navigation_acceptance"] == core["protocol"]["navigation_acceptance"], "Original DRAFT/numeric registration boundary differs")
    for key,pin in (("module","module_sha"), ("contract","contract_sha")):
        require(str(paths[key]) == str(Path(paths[key]).resolve(strict=True)) and sha(ordinary(paths[key])) == profile[pin], "External evidence file/SHA differs: " + key)
        require(not any(paths[key].is_relative_to(root) for root in (paths["source"], paths["stage"], paths["final"], paths["core"].parent.parent)), "Evidence module/contract must stay outside frozen and original results roots")
    contract = load(paths["contract"])
    cells = [{"slot_id":trial["id"], "target_class":trial["target_class"], "condition":trial["extension_condition"]}
        for trial in extension["trials"] if trial.get("extension_condition") in {"dropout", "combined"}]
    require(digest(contract) == profile["contract_digest"] and contract.get("revision") == "sensor_input_interruption_v1"
        and contract.get("scope") == SCOPE and contract.get("source_plan") == binding(paths["extension"])
        and contract.get("dev_slots") == cells and len(cells) == 4
        and {(row["target_class"],row["condition"]) for row in cells} == {(cls,cond) for cls in ("person","car") for cond in ("dropout","combined")}, "External post-hoc contract/fixed four cells differ")
    descriptor = {"schema_version":1, "revision":"sensor_input_interruption_v1", "scope":SCOPE, "evidence_basis":BASIS,
        "module":binding(paths["module"]), "contract":{**binding(paths["contract"]), "canonical_sha256":digest(contract)},
        "source_plan":binding(paths["extension"]), "dev_slots":cells}
    protocol = deepcopy(documents[MAIN]); protocol[FIELD] = descriptor
    protocol_bytes = (json.dumps(protocol, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()
    baseline = {name:item for name,item in expected.items() if name not in nested}
    overlaid = deepcopy(baseline)
    for name,payload in {**payloads, MAIN:protocol_bytes}.items():
        overlaid[name] = {"kind":"file", "bytes":len(payload), "sha256":hashlib.sha256(payload).hexdigest()}
    expected_source = source_map(overlaid, new_rules)
    require(set(expected_source) == set(original_source) and digest(expected_source) == profile["overlay_source_digest"], "Expected new308 source map differs")
    expected_scanner = scanner_map(overlaid)
    require(len(expected_scanner) == profile["scanner_count"] and digest(expected_scanner) == profile["overlay_scanner_digest"], "Expected new185 scanner map differs")
    compare(flight_map(original_source, rules), flight_map(expected_source, new_rules), "Exact original/new flight source")
    require(len(flight_map(expected_source, new_rules)) == profile["flight_count"], "Flight source denominator differs")
    research = paths["source"] / "results/recorded_estimator_research/research_report.json"
    require(sha(research) == profile["research_sha"], "Original real research report differs")
    return {"paths":paths, "profile":profile, "original":expected, "baseline":baseline, "overlaid":overlaid,
        "source":expected_source, "scanner":expected_scanner, "flight":flight_map(expected_source,new_rules),
        "payloads":payloads, "protocol":protocol_bytes, "descriptor":descriptor, "rules":new_rules,
        "terminals":terminals, "research":research, "source_results_link":link,
        "inputs":{key:binding(paths[key]) for key in ("core","extension","full","module","contract")}}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def summary(prepared):
    return {"scope":prepared["profile"]["scope"], "source_root":str(prepared["paths"]["source"]),
        "staging_root":str(prepared["paths"]["stage"]), "inputs":prepared["inputs"],
        "original_full_entries":len(prepared["original"]), "baseline_full_entries":len(prepared["baseline"]),
        "overlay_full_entries":len(prepared["overlaid"]), "source_entries":len(prepared["source"]),
        "scanner_entries":len(prepared["scanner"]), "flight_entries":len(prepared["flight"]),
        "expected_source_sha256":digest(prepared["source"]), "expected_scanner_sha256":digest(prepared["scanner"]),
        "descriptor":prepared["descriptor"], "claim_boundary":"Staging only; no cold build, bag read, evaluator, flight, gate, preregistration publication or formal admission."}


def execute(prepared):
    paths = prepared["paths"]
    receipt, stage = paths["receipt"], paths["stage"]
    receipt.mkdir(exist_ok=False)
    write_new(receipt / "started.json", {"created_utc":stamp(), "driver":binding(__file__), **summary(prepared)})
    try:
        stage.mkdir(exist_ok=False)
        for name in sorted(prepared["baseline"]):
            source, destination = ordinary(paths["source"] / name), stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            require(not destination.exists() and not destination.is_symlink(), "Destination already exists")
            shutil.copy2(source, destination, follow_symlinks=False)
        destination = stage / "results/recorded_estimator_research/research_report.json"
        destination.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(prepared["research"], destination)
        require(sha(destination) == prepared["profile"]["research_sha"], "Copied real research report differs")
        baseline_actual = file_map(stage)
        compare(prepared["baseline"], baseline_actual, "Actual copied54 baseline complete map")
        for name,payload in {**prepared["payloads"], MAIN:prepared["protocol"]}.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb" if name in prepared["baseline"] else "xb") as stream:
                stream.write(payload)
        actual = file_map(stage)
        compare(prepared["overlaid"], actual, "Actual final55 pre-cold complete map")
        compare(prepared["source"], source_map(actual,prepared["rules"]), "Actual final55 source308 map")
        compare(prepared["scanner"], scanner_map(actual), "Actual final55 scanner185 map")
        require(not any(name.startswith(NESTED) for name in actual), "Nested build copies reached staging")
        original_after, original_link = source_snapshot(paths["source"], paths["core"].parent.parent)
        require(original_link == prepared["source_results_link"], "Original results link changed during staging")
        compare(prepared["original"], original_after, "Original54 source after staging")
        for item in (*prepared["inputs"].values(), *prepared["terminals"]):
            require(sha(item["path"]) == item["sha256"], "Original input changed during staging")
        for name,value in (("original54_complete_map",prepared["original"]), ("copied54_baseline_map",baseline_actual),
                ("expected_overlay_complete_map",prepared["overlaid"]), ("actual_overlay_complete_map",actual),
                ("actual_source_hashes",prepared["source"]), ("actual_scanner_hashes",prepared["scanner"]), ("actual_flight_hashes",prepared["flight"])):
            write_new(receipt / (name + ".json"), {"entries":value, "entries_sha256":digest(value)})
        outcome = {"status":"PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION", "finished_utc":stamp(), **summary(prepared)}
        write_new(receipt / "outcome.json", outcome)
        return outcome
    except BaseException as error:
        write_new(receipt / "outcome.json", {"status":"FAIL_STAGING_ATTEMPT_RETAINED", "finished_utc":stamp(),
            "error":f"{type(error).__name__}: {error}", "staging_root":str(stage), "claim_boundary":"Retained failed preparation; no cleanup, cold build or original rewrite."})
        raise


def run(paths, *, execute_requested=False, profile=None, idle_guard=None):
    profile = PROFILE if profile is None else profile
    with (linux_idle_guard if idle_guard is None else idle_guard)():
        prepared = prepare(paths, profile)
        if execute_requested:
            return execute(prepared)
        return {"status":"PREFLIGHT_ONLY_NO_WRITES", **summary(prepared)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("/root/uav_tracking_fullplan_v4_humble54"))
    parser.add_argument("--overlay-root", type=Path, default=PROJECT)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--final-root", type=Path, required=True, help="Reserved future cold root; this driver never creates it")
    parser.add_argument("--receipt-directory", type=Path, required=True, help="Fresh external directory; only --execute creates it")
    parser.add_argument("--sensor-module", type=Path)
    parser.add_argument("--sensor-contract", type=Path)
    parser.add_argument("--execute", action="store_true", help="After read-only checks, create one new staging tree and retained receipts; never cold-build")
    args = parser.parse_args(argv)
    original_results = args.source_root / "results"
    paths = {"source":args.source_root, "overlay":args.overlay_root, "stage":args.stage_root, "final":args.final_root,
        "receipt":args.receipt_directory,
        "core":original_results / "reliability_v4_humble54_core12_probe01_matrix/plan.json",
        "extension":original_results / "reliability_v4_humble54_extension16_probe01_matrix/plan.json",
        "full":original_results / "freeze_validation/source_integrity/source_before.json",
        "module":args.sensor_module or args.overlay_root / "tools/offline_evaluation/sensor_input_interruption_v1/evidence.py",
        "contract":args.sensor_contract or args.overlay_root / "tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical02.json"}
    try:
        result = run(paths, execute_requested=args.execute)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, Refused, KeyError, TypeError, SyntaxError, ValueError) as error:
        print(json.dumps({"status":"REFUSED", "error":f"{type(error).__name__}: {error}", "claim_boundary":"No cold build or native task started; failed execute attempts remain."}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
