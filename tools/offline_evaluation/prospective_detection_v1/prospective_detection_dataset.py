"""Prospective all-actor detection dataset, outside every flight freeze.

Default describe is inert. Protocol creation reads two explicit formal plans.
Extraction is an OFFLINE, potentially large bag/hash job and must be scheduled
only when flight/recording/inference is idle. It never starts a simulator.
Generated mesh boxes are AMODAL proposals, never visible-label approval.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

KIND = "PROSPECTIVE_ALL_ACTOR_DYNAMIC_CAMERA_DETECTION_V1"
GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing", "stage3_midpoint", "stage3_active", "stage3_multi_active")
CONDITIONS = ("depth_noise", "depth_holes", "dropout", "latency", "combined", "speed_changes_velocity", "speed_changes_position", "far_distance")
CLASSES = ("person", "car")
SEEDS = list(range(1000, 1010))
TERMINAL = {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING", "INFRASTRUCTURE_ERROR", "INTERRUPTED"}
RULE = {"first_follow_offset_ns": 1000000000, "sample_period_ns": 2000000000,
        "maximum_rgb_offset_ns": 100000000, "maximum_camera_info_offset_ns": 100000000,
        "nearest_tie_rule": "earlier acquisition timestamp", "duplicate_source_rule": "retain opportunity; no ambiguous image is selected",
        "tail_rule": "all grid points <= final recorded clock, with no frame cap", "shutter_guard_s": 1.0,
        "selection_inputs": ["recorded first FOLLOW phase", "recorded clock", "original RGB acquisition timestamps"],
        "forbidden_selection_inputs": ["detector output", "tracking success", "PASS/FAIL", "visibility", "selected actor"]}
HELPERS = ("scripts/evaluate_physical_identity.py", "scripts/evaluate_stage1_flight.py", "scripts/extract_research_recording.py",
           "scripts/evaluate_detection_recordings.py", "scripts/run_reliability_v4.py", "uav_tracking/research_labels.py",
           "uav_tracking/research_metrics.py", "uav_tracking/stage2_identity.py")
INPUT_FILES = ("run_config.json", "configuration/runtime_world.sdf", "configuration/runtime_parameters.yaml", "configuration/source_sha256.json",
               "configuration/magnetic_environment.json", "telemetry.jsonl", "summary.json")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while data := stream.read(4 * 1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def read(path):
    def invalid(value):
        raise ValueError("Non-finite JSON: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def pin(path):
    return {"path": str(Path(path).resolve(strict=True)), "sha256": sha(path)}


def checked(binding):
    require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, "Exact path/SHA pin required")
    require(sha(binding["path"]) == binding["sha256"], "Pinned bytes changed: " + binding["path"])
    return read(binding["path"])


def tool_pins():
    folder = Path(__file__).resolve().parent
    return {name: pin(folder / name) for name in ("prospective_detection_dataset.py", "evaluate_prospective_detection.py")}


def load_helpers(root, expected):
    """One explicitly pinned frozen checkout per process; reject foreign imports."""
    root = Path(root).resolve(strict=True)
    require(set(expected) == set(HELPERS), "Complete explicit helper-source map required")
    for relative, digest in expected.items():
        require(sha(root / relative) == digest, "Frozen helper source changed: " + relative)
    for name, module in list(sys.modules.items()):
        if name.startswith("uav_tracking") or name in {"evaluate_stage1_flight", "extract_research_recording", "evaluate_physical_identity", "evaluate_detection_recordings", "run_reliability_v4"}:
            origin = getattr(module, "__file__", None)
            require(origin is not None and Path(origin).resolve().is_relative_to(root), "Foreign helper already imported: " + name)
    sys.path[:0] = [str(root / "scripts"), str(root)]
    modules = {name: importlib.import_module(name) for name in
               ("evaluate_physical_identity", "evaluate_detection_recordings", "run_reliability_v4", "uav_tracking.research_labels", "uav_tracking.research_metrics")}
    for module in modules.values():
        require(Path(module.__file__).resolve().is_relative_to(root), "Helper origin escaped explicit frozen root")
    return modules


def validate_matrix(core, extension):
    """Pure denominator/identity checks; production also calls frozen validators."""
    require(core.get("mode") == "FORMAL" and extension.get("mode") == "EXTENSION_FORMAL", "Actual original formal120+160 plans required")
    for plan, count in ((core, 120), (extension, 160)):
        require(plan.get("plan_sha256") == canonical({k: v for k, v in plan.items() if k != "plan_sha256"}), "Internal formal plan digest changed")
        require(plan.get("selected_classes") == list(CLASSES) and plan.get("selected_seeds") == SEEDS
                and all(type(seed) is int for seed in plan["selected_seeds"]), "Complete original classes and held-out1000..1009 required")
        require(len(plan.get("trials", [])) == count, "Original formal denominator differs")
        require(len({t["id"] for t in plan["trials"]}) == count and len({t["directory"] for t in plan["trials"]}) == count, "Duplicate formal trial identity/path")
        cells = [(t["target_class"], t.get("extension_condition") if count == 160 else t["group"], t["seed"]) for t in plan["trials"]]
        axis = CONDITIONS if count == 160 else GROUPS
        require(set(cells) == {(cls, group, seed) for cls in CLASSES for group in axis for seed in SEEDS}, "Missing/foreign original formal cell")
    require(core.get("selected_groups") == list(GROUPS) and extension.get("selected_extension_conditions") == list(CONDITIONS), "Original matrix order differs")
    require(core.get("frozen_root") == extension.get("frozen_root")
            and core.get("source_hashes") == extension.get("source_hashes")
            and core.get("model_hashes") == extension.get("model_hashes")
            and isinstance(core.get("source_hashes"), dict) and bool(core["source_hashes"]), "Formal source/model identities disagree")
    require(not ({t["id"] for t in core["trials"]} & {t["id"] for t in extension["trials"]}), "Core/extension slot IDs alias")
    require(extension.get("core_reference_binding", {}).get("plan_sha256") == core["plan_sha256"], "Extension must reference this original core plan")


def make_protocol(core_pin, extension_pin):
    core, extension = checked(core_pin), checked(extension_pin)
    validate_matrix(core, extension)
    root = Path(core["frozen_root"])
    hashes = {relative: sha(root / relative) for relative in HELPERS}
    for relative, digest in hashes.items():
        require(core["source_hashes"].get(relative) == digest, "Helper absent/different in original classified source map: " + relative)
    modules = load_helpers(root, hashes)
    runner = modules["run_reliability_v4"]
    runner.validate_plan(core, core_pin["path"])
    runner.validate_plan(extension, extension_pin["path"])
    for plan in (core, extension):
        for trial in plan["trials"]:
            require(not Path(trial["directory"]).exists() and not Path(trial["directory"]).is_symlink()
                    and not (Path(plan["output"])/"slots"/(trial["id"]+".json")).exists()
                    and not (Path(plan["output"])/"slots"/(trial["id"]+".started.json")).exists(),
                    "Prospective detection protocol must precede every original280 attempt")
    require(extension["core_reference_binding"]["path"] == core_pin["path"]
            and extension["core_reference_binding"]["sha256"] == core_pin["sha256"], "Actual extension file reference differs")
    slots = [{"plan": name, "slot_id": trial["id"], "source_trial": trial["directory"], "target_class": trial["target_class"],
              "stage": trial["stage"], "group": trial["group"], "condition": trial.get("extension_condition"), "seed": trial["seed"],
              "camera_mode": "DYNAMIC_PHYSICAL_NO_FIXED_FALLBACK" if trial["stage"] == 3 else "PINNED_FIXED_MOUNT"}
             for name, plan in (("core", core), ("extension", extension)) for trial in plan["trials"]]
    return {"schema_version": 1, "kind": KIND, "sampling_rule": RULE, "original_planned_slots": 280,
            "created_utc":datetime.now(timezone.utc).isoformat(),"all280_unattempted_at_protocol_creation":True,
            "frozen_root": str(root), "plans": {"core": core_pin, "extension": extension_pin}, "helper_source_hashes": hashes,
            "producer_tools": tool_pins(), "slots": slots, "formal_attempts_started_by_this_tool": 0,
            "review_policy": "All-actor amodal proposals are not independent visible-label approval. Agent/manual label review can occur later without viewing predictions."}


def validate_protocol(protocol, *, check_tools=True):
    require(protocol.get("schema_version") == 1 and protocol.get("kind") == KIND and protocol.get("sampling_rule") == RULE
            and protocol.get("original_planned_slots") == 280, "Wrong prospective protocol/rule/denominator")
    require(protocol.get("all280_unattempted_at_protocol_creation") is True,"Prospective unattempted admission required")
    created = datetime.fromisoformat(protocol["created_utc"].replace("Z","+00:00"))
    require(created.tzinfo is not None,"Prospective UTC timestamp required")
    core, extension = (checked(protocol["plans"][name]) for name in ("core", "extension"))
    validate_matrix(core, extension)
    require(protocol["frozen_root"] == core["frozen_root"], "Protocol frozen root differs")
    expected = [(name, t["id"], t["directory"], t["target_class"], t["stage"], t["group"], t.get("extension_condition"), t["seed"])
                for name, plan in (("core", core), ("extension", extension)) for t in plan["trials"]]
    actual = [(t["plan"], t["slot_id"], t["source_trial"], t["target_class"], t["stage"], t["group"], t["condition"], t["seed"]) for t in protocol["slots"]]
    require(actual == expected and len(actual) == 280, "Protocol omitted/reordered/relabelled original slots")
    for slot in protocol["slots"]:
        require(slot["camera_mode"] == ("DYNAMIC_PHYSICAL_NO_FIXED_FALLBACK" if slot["stage"] == 3 else "PINNED_FIXED_MOUNT"), "Camera rule changed")
    require(set(protocol["helper_source_hashes"]) == set(HELPERS), "Incomplete frozen helper map")
    require(all(core["source_hashes"].get(k) == v for k, v in protocol["helper_source_hashes"].items()), "Helpers differ from original plan")
    # Only small original attempt metadata is read here; never bag payloads.
    # A late-created protocol cannot relabel already consumed formal seeds.
    for plan in (core,extension):
        for trial in plan["trials"]:
            started = Path(plan["output"])/"slots"/(trial["id"]+".started.json")
            terminal = Path(plan["output"])/"slots"/(trial["id"]+".json")
            if started.is_file():
                marker = read(started)
                began = datetime.fromisoformat(marker["started_utc"].replace("Z","+00:00"))
                require(marker.get("id") == trial["id"] and marker.get("plan_sha256") == plan["plan_sha256"]
                        and began.tzinfo is not None and created <= began,"Detection protocol was created after an original formal attempt")
            else:
                require(not terminal.exists() and not Path(trial["directory"]).exists(),
                        "Original formal products without a preserved start marker cannot prove prospective admission")
    if check_tools:
        require(protocol["producer_tools"] == tool_pins(), "Prospective producer tools changed")
    return {"core": core, "extension": extension}


def assert_external_output(protocol, path):
    """Resolve results symlinks before protecting every original evidence tree."""
    target = Path(path).resolve()
    plans = [checked(protocol["plans"][name]) for name in ("core","extension")]
    protected = [Path(protocol["frozen_root"]).resolve(),(Path(protocol["frozen_root"])/"results").resolve()]
    protected += [Path(plan["output"]).resolve() for plan in plans]
    protected += [Path(trial["directory"]).resolve() for plan in plans for trial in plan["trials"]]
    require(not any(target == item or target.is_relative_to(item) for item in protected),
            "New output resolves inside original frozen/trial/plan evidence")
    return target


def shutter_history(events):
    """Conservative source requests/ACKs; no claim of rendered mask timing."""
    requests = [e for e in events if e.get("kind") == "shutter"]
    responses = [e for e in events if e.get("kind") == "shutter_service_result"]
    complete = bool(requests)
    windows, active = [],None
    for row in sorted(requests,key=lambda e:float(e.get("time_s",-1))):
        timestamp = row.get("time_s")
        valid = (type(timestamp) in (int,float) and math.isfinite(timestamp) and type(row.get("active")) is bool
                 and type(row.get("request_id")) is int and row["request_id"] > 0)
        matching = [r for r in responses if valid and r.get("request_id") == row["request_id"]]
        ack = (len(matching) == 1 and matching[0].get("active") is row.get("active") and matching[0].get("success") is True
               and matching[0].get("request_time_s") == timestamp and type(matching[0].get("time_s")) in (int,float)
               and math.isfinite(matching[0]["time_s"]) and matching[0]["time_s"] >= timestamp)
        complete = complete and valid and ack
        if not valid:
            continue
        if row["active"] and active is None:
            active = row
        elif not row["active"] and active is not None:
            windows.append({"start_s":float(active["time_s"]),"end_s":float(timestamp),"complete":True,
                            "close_request_id":active["request_id"],"open_request_id":row["request_id"]}); active = None
    if active is not None:
        windows.append({"start_s":float(active["time_s"]),"end_s":None,"complete":False,"close_request_id":active["request_id"],"open_request_id":None})
    return windows,{"complete_recorded_actions":bool(complete),"request_count":len(requests),"response_count":len(responses),
                    "semantics":"Request-window +/-1s guards with per-request ACKs; independent visible-label review remains required"}


def source_shutter_history(trial, input_artifacts):
    path = Path(trial)/"telemetry.jsonl"
    if not path.is_file():
        return [],shutter_history([])[1]
    require(input_artifacts.get("telemetry.jsonl",{}).get("sha256") == sha(path),"Original shutter telemetry absent/different in bound inputs")
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("kind") in {"shutter","shutter_service_result"}:
                events.append(row)
    return shutter_history(events)


def geometry_source_binding(root, trial, plan, inputs, asset, fixed=None):
    """Bind actual visual/camera resources to original frozen/archived hashes."""
    root,trial = Path(root).resolve(),Path(trial).resolve()
    original = plan["source_hashes"]
    archived_external = {}
    magnetic = trial/"configuration/magnetic_environment.json"
    if magnetic.is_file() and inputs.get("configuration/magnetic_environment.json",{}).get("sha256") == sha(magnetic):
        evidence = read(magnetic).get("sensor_mount",{})
        archived_external = {str(Path(path).resolve()):evidence.get("model_sha256",{}).get(name)
                             for name,path in evidence.get("model_paths",{}).items()}
    sources = dict(asset.get("source_sha256",{}))
    if fixed:
        sources.update(fixed.get("resolved_model_sdf_sha256",{}))
    missing = []
    for path,digest in sources.items():
        resolved = Path(path).resolve()
        if resolved.is_relative_to(trial):
            expected = inputs.get(resolved.relative_to(trial).as_posix(),{}).get("sha256")
        elif resolved.is_relative_to(root):
            expected = original.get(resolved.relative_to(root).as_posix())
        else:
            expected = archived_external.get(str(resolved))
        if expected != digest or not resolved.is_file() or sha(resolved) != digest:
            missing.append(path)
    if not sources:
        missing.append("missing_bound_geometry_sources")
    if fixed is not None and not fixed.get("resolved_model_sdf_sha256"):
        missing.append("missing_recursive_fixed_mount_sources")
    return {"supported":not missing,"mismatched_or_unbound_geometry_sources":missing,"actual_source_sha256":sources,
            "external_mount_binding":"Original terminal-pinned magnetic_environment.sensor_mount model paths/SHA; no historical-default substitution"}


def sampling_schedule(clock_ns, follow_events, image_rows):
    """Every fixed opportunity survives missing/duplicate RGB and tracking loss."""
    require(all(type(t) is int and t >= 0 for t in clock_ns), "Invalid recorded clock")
    if not clock_ns:
        return [], {"status": "UNKNOWN", "reason": "missing_recorded_clock"}
    if any(a > b for a, b in zip(clock_ns, clock_ns[1:])):
        return [], {"status": "UNKNOWN", "reason": "recorded_clock_regression"}
    follows = [e for e in follow_events if e.get("phase") == "FOLLOW"]
    if not follows or type(follows[0].get("received_clock_ns")) is not int:
        return [], {"status": "UNKNOWN", "reason": "missing_first_follow_with_recorded_clock"}
    follow = follows[0]["received_clock_ns"]
    if not clock_ns[0] <= follow <= clock_ns[-1]:
        return [], {"status": "UNKNOWN", "reason": "follow_outside_recorded_clock"}
    by_time = defaultdict(list)
    for row in image_rows:
        require(type(row.get("source_acquisition_ns")) is int and row["source_acquisition_ns"] >= 0, "Invalid original image acquisition stamp")
        by_time[row["source_acquisition_ns"]].append(row)
    times = sorted(by_time)
    frames, used = [], set()
    for index, tick in enumerate(range(follow + RULE["first_follow_offset_ns"], clock_ns[-1] + 1, RULE["sample_period_ns"])):
        i = bisect_left(times, tick)
        candidates = times[max(0, i-1):min(len(times), i+1)]
        nearest = min(candidates, key=lambda t: (abs(t-tick), t)) if candidates else None
        row = {"opportunity_index": index, "time_s": tick / 1e9, "scheduled_ns": tick, "source_acquisition_ns": None,
               "source_time_s": None, "source_offset_ns": None, "image_status": "MISSING", "image_file": None,
               "sampling_reason": "no_original_rgb_within_tolerance", "duplicate_source_count": 0}
        if nearest is not None and abs(nearest-tick) <= RULE["maximum_rgb_offset_ns"]:
            row.update(source_acquisition_ns=nearest, source_time_s=nearest/1e9, source_offset_ns=nearest-tick,
                       duplicate_source_count=len(by_time[nearest]))
            if len(by_time[nearest]) != 1:
                row["sampling_reason"] = "ambiguous_duplicate_source_timestamp"
            elif nearest in used:
                row["sampling_reason"] = "source_image_reused_by_another_opportunity"
            else:
                used.add(nearest)
                row.update(image_status="SELECTED", sampling_reason=None, source_rgb=by_time[nearest][0])
        frames.append(row)
    return frames, {"status": "KNOWN", "first_follow_clock_ns": follow, "first_recorded_clock_ns": clock_ns[0],
                    "final_recorded_clock_ns": clock_ns[-1], "opportunities": len(frames),
                    "source_timestamp_rule": "time_s is ONLY the fixed opportunity/cache key; all projection/calibration/shutter decisions use source_acquisition_ns"}


def choose_camera_info(rows, source_ns, source_rgb):
    """Calibration must belong to the selected source sensor and image shape."""
    if source_ns is None or not source_rgb:
        return None, "missing_source_rgb"
    candidates = [r for r in rows if abs(r["source_acquisition_ns"]-source_ns) <= RULE["maximum_camera_info_offset_ns"]]
    if not candidates:
        return None, "missing_source_time_camera_info"
    nearest = min(candidates, key=lambda r: (abs(r["source_acquisition_ns"]-source_ns), r["source_acquisition_ns"]))
    same = [r for r in candidates if r["source_acquisition_ns"] == nearest["source_acquisition_ns"]]
    if len({canonical(r) for r in same}) != 1:
        return None, "conflicting_source_time_camera_info"
    if (not nearest.get("frame_id") or nearest["frame_id"] != source_rgb.get("frame_id")
            or (nearest["width"], nearest["height"]) != (source_rgb.get("width"), source_rgb.get("height"))):
        return None, "camera_info_source_sensor_or_shape_mismatch"
    values = nearest.get("intrinsics", [])
    if len(values) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values) or min(values[:2]) <= 0:
        return None, "invalid_source_time_camera_info"
    if nearest.get("distortion_model") not in {"plumb_bob", "", None} or any(abs(v) > 1e-12 for v in nearest.get("distortion", [])):
        return None, "unsupported_distorted_rgb_calibration"
    return nearest, None


def expected_actor_ids(slot):
    category = slot["target_class"]
    return [f"stage2_{category}_{i}" for i in range(3)] if slot["group"] in {"stage2_crossing", "stage3_multi_active"} else [f"target_{category}"]


def singleton_scene_audit(root, trial, category, helpers):
    """Certify only the original rigid singleton world; never fake a 3-actor world."""
    import numpy as np
    audit = {"supported": False, "closed_scene_occluders_complete": False, "reason": None, "source_sha256": {},
             "expected_actor_ids": ["target_" + category], "scope": "Original singleton rigid mesh; ground/sensor-host self-visibility remains an explicit scene assumption"}
    def bind(path):
        audit["source_sha256"][str(path.resolve())] = sha(path)
    def numbers(text, n):
        values = np.fromstring(text or "", sep=" ")
        require(values.shape == (n,) and np.isfinite(values).all(), "invalid_scene_transform")
        return values
    try:
        world_path = Path(trial)/"configuration/runtime_world.sdf"
        template_path = Path(root)/f"ros2_ws/src/uav_tracking_bringup/models/target_{category}/model.sdf"
        bind(world_path); bind(template_path)
        world = ET.parse(world_path).getroot().find("world")
        template = ET.parse(template_path).getroot().find("model")
        require(world is not None and template is not None, "missing_world_or_target_template")
        require(not world.findall(".//actor") and len(world.findall(".//model")) == len(world.findall("model"))
                and len(world.findall(".//include")) == len(world.findall("include")), "unsupported_nested_rendered_scene")
        actors = {item.get("name"): item for item in world.findall("model")}
        require(set(actors) == {"ground", "vision_shutter"} and len(world.findall("model")) == 2, "unexpected_singleton_scene_model")
        includes = {item.findtext("name"): item for item in world.findall("include")}
        require(set(includes) == {"stage1_uav", "target_"+category} and len(world.findall("include")) == 2, "unexpected_singleton_scene_include")
        for item in includes.values():
            require(all(child.tag in {"name", "uri", "pose"} for child in item) and not any(pose.get("relative_to") for pose in item.findall("pose")), "unsupported_include_override")
        require(includes["stage1_uav"].findtext("uri") in {"model://x500_stage1", "model://x500_stage3"}
                and np.array_equal(numbers(includes["stage1_uav"].findtext("pose"), 6), [0,0,.25,0,0,0]), "unsupported_sensor_host")
        require(includes["target_"+category].findtext("uri") == "model://target_"+category, "singleton_target_template_differs")
        numbers(includes["target_"+category].findtext("pose"), 6)
        require(len(template.findall("link")) == 1 and not any(template.findall(".//"+tag) for tag in ("joint", "frame", "include", "actor", "model")), "unsupported_target_frame_graph")
        require(all(not pose.get("relative_to") for pose in template.findall(".//pose")), "relative_target_frame")
        require(np.all(numbers(template.findtext("pose", "0 0 0 0 0 0"), 6) == 0)
                and np.all(numbers(template.findtext("link/pose", "0 0 0 0 0 0"), 6) == 0), "nonzero_target_template_link_pose")
        models = Path(root)/"ros2_ws/src/uav_tracking_bringup/models"
        visuals = template.findall("link/visual")
        require(bool(visuals), "missing_target_visuals")
        for plugin in template.findall(".//plugin"):
            require(plugin.get("filename") in {"gz-sim-velocity-control-system", "gz-sim-pose-publisher-system"}, "unsupported_target_plugin")
        for visual in visuals:
            mesh = visual.find("geometry/mesh")
            require(mesh is not None and mesh.find("submesh") is None and visual.find("material/script") is None and visual.find("material/shader") is None, "unsupported_target_visual")
            uri = mesh.findtext("uri", "")
            require(uri.startswith("model://") and ".." not in Path(uri[8:]).parts, "unsupported_target_uri")
            require(np.all(numbers(mesh.findtext("scale", "1 1 1"), 3) > 0), "invalid_mesh_scale")
            numbers(visual.findtext("pose", "0 0 0 0 0 0"), 6)
            path = models/uri[8:]
            require(path.resolve().is_relative_to(models.resolve()), "mesh_outside_resources")
            bind(path)
            if path.suffix.lower() == ".dae":
                forbidden = {"instance_controller", "library_animations", "library_animation_clips", "profile_GLSL", "profile_CG"}
                require(not any(node.tag.rsplit("}", 1)[-1] in forbidden for node in ET.parse(path).getroot().iter()), "animated_or_shader_mesh")
            elif path.suffix.lower() == ".obj":
                for row in path.read_text(encoding="utf-8").splitlines():
                    if row.startswith("mtllib "):
                        material = path.parent/row.split(maxsplit=1)[1]
                        require(material.resolve().is_relative_to(models.resolve()), "material_outside_resources"); bind(material)
                        require(not any(line.strip().split(maxsplit=1)[0].lower() in {"disp", "map_disp"} for line in material.read_text(encoding="utf-8").splitlines() if line.strip()), "unsupported_displacement_material")
            else:
                raise ValueError("unsupported_mesh_format")
        ground, shutter = actors["ground"], actors["vision_shutter"]
        for item in (ground, shutter):
            require(item.findtext("static") == "true" and len(item.findall("link")) == 1 and len(item.findall(".//visual")) == 1
                    and not any(item.findall(".//"+tag) for tag in ("plugin", "frame", "joint")), "unsupported_ground_or_shutter")
            require(all(not pose.get("relative_to") and np.all(numbers(pose.text, 6) == 0) for link in item.findall("link") for pose in link.findall(".//pose")), "unsupported_occluder_local_pose")
        require(np.all(numbers(ground.findtext("pose", "0 0 0 0 0 0"), 6) == 0)
                and np.array_equal(numbers(ground.findtext(".//visual/geometry/plane/normal"), 3), [0,0,1]), "unsupported_ground_geometry")
        require(np.array_equal(numbers(shutter.findtext("pose"), 6), [0,0,-50,0,0,0])
                and np.array_equal(numbers(shutter.findtext(".//visual/geometry/box/size"), 3), [.05,3,3]), "unsupported_shutter_geometry")
        lights = world.findall("light")
        require(len(lights) == 1 and lights[0].get("name") == "sun" and lights[0].get("type") == "directional", "unsupported_scene_lighting")
        helpers["uav_tracking.research_labels"].target_mesh_points(models, category)
        audit.update(supported=True, closed_scene_occluders_complete=True)
    except (OSError, ValueError, TypeError, AttributeError, ET.ParseError) as error:
        audit["reason"] = str(error)
    return audit


def actor_projection(points, target_pose, camera_pose, camera, labels):
    """Distinguish a known out-of-view actor from unknown near-plane geometry."""
    import numpy as np
    try:
        values = np.asarray(points, dtype=float)
        if values.ndim != 2 or values.shape[1] != 3 or not len(values) or not np.isfinite(values).all():
            return None, "UNKNOWN_INVALID_MESH"
        world = values @ target_pose[1].T + target_pose[0]
        optical = (world-camera_pose[0]) @ camera_pose[1]
        if not np.isfinite(optical).all():
            return None, "UNKNOWN_INVALID_PROJECTED_GEOMETRY"
        if np.all(optical[:,2] <= 0):
            return None, "KNOWN_BEHIND_NEAR_PLANE"
        if np.any(optical[:,2] <= .10):
            return None, "UNKNOWN_CROSSES_NEAR_PLANE"
        box = labels.project_mesh(values, target_pose, camera_pose, camera["intrinsics"], camera["width"], camera["height"])
        return (box, "KNOWN_IN_VIEW") if box else (None, "KNOWN_OUT_OF_VIEW")
    except (TypeError, ValueError, KeyError, IndexError):
        return None, "UNKNOWN_INVALID_PROJECTED_GEOMETRY"


def build_geometry(frame, slot, metadata, helpers, points, asset_audit, fixed_mount=None):
    """Pure fixtureable projection, independent of all detector outputs."""
    import numpy as np
    labels, identity = helpers["uav_tracking.research_labels"], helpers["evaluate_physical_identity"]
    result = dict(frame, gt=[], actor_geometry=[], truth_complete=False, eligible_geometric_subset=False,
                  visible_label_eligible=False, review_status="PENDING_INDEPENDENT_LABEL_REVIEW", exclusion_reasons=[])
    reasons = result["exclusion_reasons"]
    if frame.get("source_acquisition_ns") is None or frame.get("image_status") != "SELECTED":
        reasons.append(frame.get("sampling_reason") or "missing_source_rgb"); result["exclusion_reason"] = reasons[0]; return result
    timestamp = frame["source_acquisition_ns"]/1e9
    camera, camera_reason = choose_camera_info(metadata.get("camera_info", []), frame["source_acquisition_ns"], frame.get("source_rgb"))
    result["camera_info"] = camera
    if camera_reason:
        reasons.append(camera_reason)
    vehicle = metadata.get("vehicle", [])
    targets = {name: metadata.get("targets", {}).get(name, []) for name in expected_actor_ids(slot)}
    links = metadata.get("physical_links", {})
    try:
        if slot["stage"] == 3:
            camera_pose, camera_audit = identity.dynamic_camera_pose(timestamp, vehicle, links.get("base_link", []), links.get("tracking_camera_mount", []), metadata.get("camera_tf", []))
            result["camera_geometry"] = camera_audit
            if camera_pose is None:
                reasons.append(camera_audit.get("reason", "missing_dynamic_camera_geometry"))
        else:
            vehicle_pose = identity.exact_source_pose(vehicle, timestamp) or labels.interpolate_pose(vehicle, timestamp)
            camera_pose = None if vehicle_pose is None or fixed_mount is None else (vehicle_pose[0]+vehicle_pose[1]@fixed_mount[0], vehicle_pose[1]@fixed_mount[1])
            result["camera_geometry"] = {"status": "KNOWN" if camera_pose is not None else "UNKNOWN", "mode": "PINNED_FIXED_MOUNT"}
            if camera_pose is None:
                reasons.append("missing_fixed_camera_or_vehicle_truth")
        exact_audit = identity.projection_exact_time_audit(timestamp, vehicle, targets, physical_links=links if slot["stage"] == 3 else None)
        result["source_time_audit"] = exact_audit
    except (TypeError, ValueError, KeyError) as error:
        camera_pose = None; exact_audit = {"complete": False, "reason": str(error)}; result["source_time_audit"] = exact_audit
        reasons.append("invalid_source_time_pose")
    if points is None:
        reasons.append("missing_or_unsupported_complete_mesh")
    geometry_inputs_known = camera is not None and camera_pose is not None and points is not None
    known = geometry_inputs_known
    for actor, rows in targets.items():
        status, projection = "UNKNOWN_CAMERA_OR_MESH", None
        if geometry_inputs_known:
            try:
                pose = identity.exact_source_pose(rows, timestamp) or labels.interpolate_pose(rows, timestamp)
            except (TypeError, ValueError, KeyError):
                pose = None
            if pose is None:
                status = "UNKNOWN_MISSING_ACTOR_POSE"
            else:
                projection, status = actor_projection(points, pose, camera_pose, camera, labels)
        result["actor_geometry"].append({"id": actor, "status": status})
        if status.startswith("UNKNOWN"):
            known = False
            reasons.append(actor+":"+status)
        if projection is not None:
            result["gt"].append({"id": actor, "class_name": slot["target_class"], **projection})
    result["truth_complete"] = known and len(result["actor_geometry"]) == len(targets)
    if not exact_audit.get("complete"):
        reasons.append("no_exact_independent_source_time_geometry")
    if not asset_audit.get("supported") or not asset_audit.get("closed_scene_occluders_complete"):
        reasons.append("unsupported_or_incomplete_scene_assets")
    result["shutter_guard"] = any(window["start_s"]-RULE["shutter_guard_s"] <= timestamp <= (float("inf") if window["end_s"] is None else window["end_s"])+RULE["shutter_guard_s"] for window in metadata.get("shutters", []))
    if metadata.get("shutter_evidence_complete") is not True:
        reasons.append("incomplete_recorded_shutter_evidence")
    if result["shutter_guard"]:
        reasons.append("shutter_guard_interval_at_source_image")
    if any(not obj["fully_in_frame"] for obj in result["gt"]):
        reasons.append("amodal_actor_partially_out_of_frame")
    boxes = [obj["bbox"] for obj in result["gt"]]
    overlap = any(min(a[2],b[2]) > max(a[0],b[0]) and min(a[3],b[3]) > max(a[1],b[1]) for i,a in enumerate(boxes) for b in boxes[i+1:])
    result["overlap"] = overlap
    if overlap:
        reasons.append("same_class_amodal_boxes_overlap")
    if camera_pose is not None:
        result["camera_world_pose"] = {"position_m": np.asarray(camera_pose[0]).tolist(), "rotation": np.asarray(camera_pose[1]).tolist()}
    result["exclusion_reasons"] = list(dict.fromkeys(reasons))
    result["eligible_geometric_subset"] = result["visible_label_eligible"] = not result["exclusion_reasons"] and result["truth_complete"]
    result["exclusion_reason"] = ";".join(result["exclusion_reasons"]) or None
    result["label_semantics"] = "gt contains ALL in-view same-class actors as AMODAL boxes; empty gt is usable only when truth_complete and visible_label_eligible; independent visible review still required"
    return result


def stamp_ns(stamp):
    return int(stamp.sec)*1000000000 + int(stamp.nanosec)


def read_bag_metadata(bag, helpers):
    """Two-pass extraction: first pass retains source-time metadata, not images."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    identity = helpers["evaluate_physical_identity"]
    metadata = {"clock_ns": [], "follow_events": [], "image_rows": [], "camera_info": [], "camera_tf": [], "physical_links": defaultdict(list), "trajectories": defaultdict(list)}
    topics = ["/clock", "/tracking/flight_phase", "/camera/color/image_raw", "/camera/color/camera_info", "/ground_truth/poses", "/ground_truth/vehicle_poses", "/tf"]
    latest_clock = None
    with identity.open_bag_reader(bag, rosbag2_py) as (reader, _storage):
        types = {t.name: t.type for t in reader.get_all_topics_and_types()}
        reader.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
        classes = {t: get_message(types[t]) for t in topics if t in types}
        count = Counter()
        while reader.has_next():
            topic, data, record_ns = reader.read_next(); message = deserialize_message(data, classes[topic]); count[topic] += 1
            if topic == "/clock":
                latest_clock = stamp_ns(message.clock); metadata["clock_ns"].append(latest_clock)
            elif topic == "/tracking/flight_phase":
                metadata["follow_events"].append({"phase": message.data.split(":",1)[0].strip(), "received_clock_ns": latest_clock})
            elif topic == "/camera/color/image_raw":
                metadata["image_rows"].append({"source_acquisition_ns": stamp_ns(message.header.stamp), "record_ns": record_ns,
                    "width": message.width, "height": message.height, "step": message.step, "encoding": message.encoding,
                    "frame_id": message.header.frame_id, "topic_sequence": count[topic]})
            elif topic == "/camera/color/camera_info":
                metadata["camera_info"].append({"source_acquisition_ns": stamp_ns(message.header.stamp), "frame_id": message.header.frame_id,
                    "width": message.width, "height": message.height, "intrinsics": [message.k[0],message.k[4],message.k[2],message.k[5]],
                    "distortion": list(message.d), "distortion_model": message.distortion_model})
            elif topic.startswith("/ground_truth/"):
                for transform in message.transforms:
                    metadata["trajectories"][transform.child_frame_id.strip("/")].append(identity.pose_dict(transform))
                    child = transform.child_frame_id.replace("::", "/").strip("/").rsplit("/",1)[-1]
                    if child in {"base_link", "tracking_camera_mount"}:
                        parent = transform.header.frame_id.replace("::", "/").strip("/").rsplit("/",1)[-1]
                        if parent == "stage1_uav":
                            metadata["physical_links"][child].append(identity.pose_dict(transform))
            elif topic == "/tf":
                for transform in message.transforms:
                    if (transform.header.frame_id.strip("/"),transform.child_frame_id.strip("/")) == ("base_link", "camera_link"):
                        metadata["camera_tf"].append(identity.pose_dict(transform))
    metadata["topic_counts"] = dict(count)
    return metadata


def choose_trajectory(trajectories, name):
    matches = [rows for key, rows in trajectories.items() if key == name or key.endswith("::"+name) or key.rsplit("/",1)[-1] == name]
    return sorted(matches[0], key=lambda row: row["time_s"]) if len(matches) == 1 else []


def save_images(bag, frames, output, helpers):
    import cv2
    import numpy as np
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    selected = {frame["source_acquisition_ns"]: frame for frame in frames if frame["image_status"] == "SELECTED"}
    with helpers["evaluate_physical_identity"].open_bag_reader(bag, rosbag2_py) as (reader, _storage):
        reader.set_filter(rosbag2_py.StorageFilter(topics=["/camera/color/image_raw"]))
        message_type = get_message("sensor_msgs/msg/Image")
        while reader.has_next():
            _topic, data, record_ns = reader.read_next(); message = deserialize_message(data, message_type)
            frame = selected.get(stamp_ns(message.header.stamp))
            if frame is None:
                continue
            expected = frame["source_rgb"]
            actual = {"source_acquisition_ns": stamp_ns(message.header.stamp), "record_ns": record_ns, "width": message.width,
                      "height": message.height, "step": message.step, "encoding": message.encoding, "frame_id": message.header.frame_id}
            if any(actual[key] != expected[key] for key in actual):
                frame.update(image_status="MISSING", sampling_reason="source_image_changed_between_passes"); continue
            try:
                require(message.encoding.lower() in {"rgb8", "bgr8"} and message.width > 0 and message.height > 0
                        and message.step >= message.width*3 and len(message.data) == message.height*message.step, "unsupported_or_malformed_original_rgb")
                image = np.frombuffer(message.data,dtype=np.uint8).reshape(message.height,message.step)[:,:message.width*3].reshape(message.height,message.width,3).copy()
                if message.encoding.lower() == "rgb8":
                    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                success, encoded = cv2.imencode(".png", image); require(success, "source_image_encode_failed")
                path = output/f"source_{frame['opportunity_index']:05d}_{frame['source_acquisition_ns']}.png"
                with path.open("xb") as stream:
                    stream.write(encoded.tobytes())
                frame.update(image_file=path.name, image_status="PRESENT", image_sha256=sha(path), image_bytes=path.stat().st_size,
                             original_rgb_payload_sha256=hashlib.sha256(bytes(message.data)).hexdigest())
            except (ValueError, TypeError) as error:
                frame.update(image_status="MISSING", sampling_reason=str(error))
    for frame in frames:
        if frame["image_status"] == "SELECTED":
            frame.update(image_status="MISSING", sampling_reason="selected_original_rgb_not_found_on_image_pass")


def original_slot(protocol, slot_id):
    plans = validate_protocol(protocol)
    slots = [s for s in protocol["slots"] if s["slot_id"] == slot_id]
    require(len(slots) == 1, "One original formal slot ID required")
    slot = slots[0]; plan = plans[slot["plan"]]
    trial = next(t for t in plan["trials"] if t["id"] == slot_id)
    record_path = Path(plan["output"])/"slots"/(slot_id+".json")
    if not record_path.is_file():
        return slot, trial, None, {"status": "UNAVAILABLE_OR_NOT_TERMINAL", "terminal_record": None}
    record = read(record_path)
    require(record.get("record_sha256") == canonical({k:v for k,v in record.items() if k != "record_sha256"})
            and record.get("plan_sha256") == plan["plan_sha256"] and record.get("id") == slot_id
            and record.get("status") in TERMINAL, "Original terminal record changed/foreign")
    return slot, trial, record, {"status": record["status"], "terminal_record": pin(record_path)}


def verify_original_inputs(trial, record):
    """Heavy whole-bag verification occurs only in explicitly scheduled extract."""
    directory = Path(trial["directory"])
    actual = {}
    required = list(INPUT_FILES)
    bag = directory/"rosbag"
    if bag.is_dir():
        required += [str(path.relative_to(directory)).replace("\\", "/") for path in sorted(bag.rglob("*")) if path.is_file()]
    manifest = record.get("artifact_hashes", {})
    for relative in required:
        path = directory/relative
        if not path.is_file():
            continue
        require(relative in manifest and sha(path) == manifest[relative], "Actual original extraction input absent/different in terminal hashes: "+relative)
        actual[relative] = {"sha256": manifest[relative], "bytes": path.stat().st_size}
    return actual


def frame_coverage(frames):
    return {"original_plan_slots":280,"this_original_slot":1,"scheduled_opportunities":len(frames),
            "present_images":sum(f["image_status"] == "PRESENT" for f in frames),
            "visible_geometry_eligible":sum(f["visible_label_eligible"] for f in frames),
            "reason_counts":dict(Counter(reason for f in frames for reason in f["exclusion_reasons"]))}


def extract(protocol_pin, slot_id, output):
    protocol = checked(protocol_pin); slot, trial, record, terminal = original_slot(protocol, slot_id)
    output = assert_external_output(protocol, output)
    require(not output.exists(), "Fresh external output required; all prior evidence retained")
    root = Path(protocol["frozen_root"]).resolve()
    output.mkdir(parents=True)
    source = {"schema_version": 1, "kind": KIND, "protocol": protocol_pin, "slot_id": slot_id, "source_trial": slot["source_trial"],
              "target_class": slot["target_class"], "stage": slot["stage"], "camera_mode": slot["camera_mode"], "terminal": terminal,
              "expected_actor_ids": expected_actor_ids(slot), "sampling_rule": RULE, "frames": [], "producer_tools": tool_pins(),
              "label_approval": "PENDING_INDEPENDENT_VISIBLE_LABEL_REVIEW", "extraction_status": "UNKNOWN", "input_artifacts": {}}
    source["sampling_audit"] = {"status":"UNKNOWN","reason":"extraction_metadata_not_available"}
    if record is None:
        source.update(extraction_status="UNAVAILABLE_OR_NOT_TERMINAL", sampling_audit={"status":"UNKNOWN","reason":"original_slot_not_terminal"})
    else:
        source["input_artifacts"] = verify_original_inputs(trial, record)
        bag = Path(trial["directory"])/"rosbag"
        if not bag.is_dir() or not (bag/"metadata.yaml").is_file():
            source.update(extraction_status="UNOBSERVABLE_MISSING_ORIGINAL_BAG", sampling_audit={"status":"UNKNOWN","reason":"missing_original_bag"})
        else:
            helpers = load_helpers(root, protocol["helper_source_hashes"])
            try:
                metadata = read_bag_metadata(bag, helpers)
                source["sampling_metadata"] = {key:metadata[key] for key in ("clock_ns","follow_events","image_rows")}
                frames, audit = sampling_schedule(metadata["clock_ns"], metadata["follow_events"], metadata["image_rows"])
                source["sampling_audit"] = audit; source["topic_counts"] = metadata["topic_counts"]
                source["frames"] = [dict(frame,gt=[],actor_geometry=[],truth_complete=False,
                    eligible_geometric_subset=False,visible_label_eligible=False,
                    exclusion_reasons=["extraction_not_completed"],exclusion_reason="extraction_not_completed") for frame in frames]
                metadata["vehicle"] = choose_trajectory(metadata["trajectories"], "stage1_uav")
                metadata["targets"] = {name: choose_trajectory(metadata["trajectories"], name) for name in source["expected_actor_ids"]}
                for rows in [metadata["camera_tf"], *metadata["physical_links"].values()]:
                    rows.sort(key=lambda row: row["time_s"])
                identity = helpers["evaluate_physical_identity"]
                telemetry = Path(trial["directory"])/"telemetry.jsonl"
                metadata["shutters"],source["shutter_evidence"] = source_shutter_history(trial["directory"],source["input_artifacts"])
                metadata["shutter_evidence_complete"] = source["shutter_evidence"]["complete_recorded_actions"]
                source["shutter_windows"] = metadata["shutters"]
                if len(source["expected_actor_ids"]) == 3:
                    asset = identity.static_projection_asset_audit(root, Path(trial["directory"]), slot["target_class"])
                else:
                    asset = singleton_scene_audit(root, Path(trial["directory"]), slot["target_class"], helpers)
                source["scene_asset_audit"] = asset
                try:
                    points, mesh = helpers["uav_tracking.research_labels"].target_mesh_points(root/"ros2_ws/src/uav_tracking_bringup/models", slot["target_class"])
                    source["mesh"] = mesh
                except (OSError, ValueError, TypeError, ET.ParseError) as error:
                    points = None; source["mesh"] = {"status":"UNKNOWN","reason":str(error)}
                fixed = None
                if slot["stage"] != 3:
                    try:
                        mount_p, mount_r, mount_audit = identity.model_camera_mount(root)
                        fixed = (mount_p, mount_r); source["fixed_mount"] = mount_audit
                    except Exception as error:
                        source["fixed_mount"] = {"status":"UNKNOWN","reason":str(error)}
                source_plan = checked(protocol["plans"][slot["plan"]])
                binding = geometry_source_binding(root,trial["directory"],source_plan,source["input_artifacts"],asset,source.get("fixed_mount") if slot["stage"] != 3 else None)
                source["geometry_source_binding"] = binding
                if binding["supported"] is not True:
                    asset["supported"] = False; asset["reason"] = "geometry_sources_differ_from_original_plan_or_archived_mount"
                projected = [build_geometry(frame, slot, metadata, helpers, points, asset, fixed) for frame in frames]
                source["frames"] = projected
                save_images(bag, projected, output, helpers)
                for frame in projected:
                    if frame["image_status"] != "PRESENT":
                        frame["eligible_geometric_subset"] = frame["visible_label_eligible"] = False
                        frame["exclusion_reasons"] = list(dict.fromkeys(frame["exclusion_reasons"]+[frame["sampling_reason"] or "missing_original_rgb"]))
                        frame["exclusion_reason"] = ";".join(frame["exclusion_reasons"])
                source["frames"] = projected
                source["extraction_status"] = "EXTRACTED_PROPOSALS_REVIEW_PENDING" if audit["status"] == "KNOWN" else "UNKNOWN_SAMPLING_CLOCK_OR_FOLLOW"
            except Exception as error:
                source.update(extraction_status="INCOMPLETE_EXTRACTION_PRESERVE_ALL_OUTPUTS", error=type(error).__name__+":"+str(error))
                for frame in source["frames"]:
                    if frame["image_status"] == "SELECTED":
                        frame["image_status"] = "MISSING"
                    frame["eligible_geometric_subset"] = frame["visible_label_eligible"] = False
                    frame["exclusion_reasons"] = list(dict.fromkeys(frame["exclusion_reasons"]+["incomplete_extraction"]))
                    frame["exclusion_reason"] = ";".join(frame["exclusion_reasons"])
    source["coverage"] = frame_coverage(source["frames"])
    # Whole original inputs are rechecked after the two bag passes; no TOCTOU claim.
    if record is not None:
        require(verify_original_inputs(trial, record) == source["input_artifacts"], "Original input artifacts changed during extraction")
    require(protocol["producer_tools"] == tool_pins(), "Producer changed during extraction")
    write_new(output/"recording.json", source)
    return source


def verify_recording(recording, protocol_pin):
    """Semantic outer check before the unchanged low-confidence cache API."""
    protocol = checked(protocol_pin); plans = validate_protocol(protocol)
    source = read(recording)
    require(source.get("schema_version") == 1 and source.get("kind") == KIND and source.get("protocol") == protocol_pin
            and source.get("sampling_rule") == RULE and source.get("producer_tools") == protocol["producer_tools"], "Wrong extraction/schema/producer binding")
    slots = [s for s in protocol["slots"] if s["slot_id"] == source.get("slot_id")]
    require(len(slots) == 1, "Foreign original slot")
    slot = slots[0]
    require((source["source_trial"],source["target_class"],source["stage"],source["camera_mode"],source["expected_actor_ids"])
            == (slot["source_trial"],slot["target_class"],slot["stage"],slot["camera_mode"],expected_actor_ids(slot)), "Extraction identity/camera/actors differ")
    plan = plans[slot["plan"]]
    terminal_path = Path(plan["output"])/"slots"/(slot["slot_id"]+".json")
    terminal = source.get("terminal",{})
    if terminal.get("terminal_record") is not None:
        require(terminal["terminal_record"]["path"] == str(terminal_path.resolve()),"Terminal metadata belongs to another original slot")
        original = checked(terminal["terminal_record"])
        require(original.get("id") == slot["slot_id"] and original.get("plan_sha256") == plan["plan_sha256"]
                and original.get("record_sha256") == canonical({k:v for k,v in original.items() if k != "record_sha256"})
                and original.get("status") in TERMINAL and terminal.get("status") == original["status"],"Original terminal identity/digest/status differs")
        for relative,evidence in source.get("input_artifacts",{}).items():
            require(isinstance(relative,str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts
                    and evidence.get("sha256") == original.get("artifact_hashes",{}).get(relative)
                    and type(evidence.get("bytes")) is int and evidence["bytes"] >= 0,"Extraction inputs differ from original terminal hash map")
        if any(f.get("image_status") == "PRESENT" for f in source["frames"]):
            expected_inputs = {relative for relative in original.get("artifact_hashes",{}) if relative in INPUT_FILES or relative.startswith("rosbag/")}
            require(set(source.get("input_artifacts",{})) == expected_inputs,"Present-image extraction omitted original bag/config/telemetry source hashes")
    else:
        require(terminal.get("status") == "UNAVAILABLE_OR_NOT_TERMINAL" and not source["frames"] and not terminal_path.is_file(),
                "Missing terminal pin cannot certify extracted opportunities")
    windows,shutter_evidence = source_shutter_history(source["source_trial"],source.get("input_artifacts",{}))
    if source["frames"]:
        require(source.get("shutter_windows") == windows and source.get("shutter_evidence") == shutter_evidence,"Source shutter history/ACK evidence changed")
    asset = source.get("scene_asset_audit",{})
    geometry_binding = geometry_source_binding(protocol["frozen_root"],source["source_trial"],plan,source.get("input_artifacts",{}),asset,
                                               source.get("fixed_mount") if source["stage"] != 3 else None)
    if any(f.get("visible_label_eligible") for f in source["frames"]):
        require(geometry_binding.get("supported") is True and source.get("geometry_source_binding") == geometry_binding,
                "Actual geometry resources differ from original plan/archived fixed mount")
        require(source["stage"] == 3 or bool(source.get("fixed_mount",{}).get("resolved_model_sdf_sha256")),"Fixed mount lacks original recursive source evidence")
    audit = source.get("sampling_audit", {})
    original_sampling = source.get("sampling_metadata")
    recomputed_frames = None
    if original_sampling is not None:
        recomputed_frames,recomputed_audit = sampling_schedule(original_sampling["clock_ns"],original_sampling["follow_events"],original_sampling["image_rows"])
        require(recomputed_audit == audit,"Sampling audit differs from retained original clock/FOLLOW/RGB timestamp index")
        require(len(recomputed_frames) == len(source["frames"]),"Retained timestamp index opportunity denominator differs")
    if audit.get("status") == "KNOWN":
        require(original_sampling is not None,"Known sampling requires the retained original timestamp index")
        expected_ticks = list(range(audit["first_follow_clock_ns"]+1000000000, audit["final_recorded_clock_ns"]+1, 2000000000))
        require([f["scheduled_ns"] for f in source["frames"]] == expected_ticks, "Missing/extra fixed opportunities or final tail")
    else:
        require(not source["frames"], "Unknown sampling cannot certify selected frames")
    used, keys = set(), set()
    for index, frame in enumerate(source["frames"]):
        if recomputed_frames is not None:
            original_frame = recomputed_frames[index]
            require(all(frame.get(field) == original_frame.get(field) for field in
                        ("opportunity_index","time_s","scheduled_ns","source_acquisition_ns","source_time_s","source_offset_ns","duplicate_source_count","source_rgb")),
                    "RGB opportunity differs from original nearest/tie/duplicate sampling rule")
            require(original_frame["image_status"] == "SELECTED" or frame["image_status"] == "MISSING",
                    "Missing/ambiguous timestamp index cannot supply a present image")
        key = f'{frame["time_s"]:.6f}'
        require(key not in keys and frame["opportunity_index"] == index and frame["time_s"] == frame["scheduled_ns"]/1e9, "Opportunity keys alias/change")
        keys.add(key)
        relative = frame.get("image_file")
        if frame["image_status"] == "PRESENT":
            require(isinstance(relative,str) and Path(relative).name == relative, "Local source image basename required")
            path = Path(recording).parent/relative
            require(path.is_file() and sha(path) == frame.get("image_sha256") and path.stat().st_size == frame.get("image_bytes"), "Wrong/missing source image")
            acquisition = frame["source_acquisition_ns"]
            require(type(acquisition) is int and abs(acquisition-frame["scheduled_ns"]) <= 100000000 and acquisition not in used
                    and frame.get("duplicate_source_count") == 1, "Wrong/duplicate selected source timestamp")
            require(frame.get("source_time_s") == acquisition/1e9 and frame.get("source_rgb",{}).get("source_acquisition_ns") == acquisition,
                    "Image acquisition time evidence disagrees")
            used.add(acquisition)
        else:
            require(relative is None and frame["eligible_geometric_subset"] is False, "Missing source image cannot enter metrics")
        require(frame["eligible_geometric_subset"] == frame["visible_label_eligible"], "Visibility flag disagrees")
        require(all(obj["id"] in source["expected_actor_ids"] and obj["class_name"] == source["target_class"] for obj in frame["gt"])
                and len({obj["id"] for obj in frame["gt"]}) == len(frame["gt"]), "Foreign/duplicate GT actor")
        if frame["visible_label_eligible"]:
            statuses = {g["id"]:g["status"] for g in frame["actor_geometry"]}
            require(set(statuses.values()) <= {"KNOWN_IN_VIEW","KNOWN_OUT_OF_VIEW","KNOWN_BEHIND_NEAR_PLANE"}
                    and {key for key,value in statuses.items() if value == "KNOWN_IN_VIEW"} == {g["id"] for g in frame["gt"]},
                    "Missing in-view actor GT cannot become a known negative")
            timestamp = frame["source_acquisition_ns"]/1e9
            time_audit = frame.get("source_time_audit",{})
            needed = {"vehicle",*source["expected_actor_ids"]} | ({"base_link","tracking_camera_mount"} if source["stage"] == 3 else set())
            require(time_audit.get("source_image_s") == timestamp and set(time_audit.get("exact_source_samples_s",{})) == needed
                    and all(values and all(type(t) in (int,float) and math.isfinite(t) and abs(t-timestamp) <= 1e-9 for t in values)
                            for values in time_audit["exact_source_samples_s"].values()),"Exact geometry proof belongs to another RGB acquisition")
            camera,camera_reason = choose_camera_info([frame.get("camera_info",{})],frame["source_acquisition_ns"],frame["source_rgb"])
            require(camera_reason is None,"Eligible camera calibration does not match source RGB")
            boxes = []
            for obj in frame["gt"]:
                box = obj.get("bbox",[])
                require(isinstance(box,list) and len(box) == 4 and all(type(v) in (int,float) and math.isfinite(v) for v in box)
                        and box[2] > box[0] and box[3] > box[1],"Invalid amodal GT bbox")
                fully = box[0] >= 1 and box[1] >= 1 and box[2] < camera["width"]-1 and box[3] < camera["height"]-1
                require(obj.get("fully_in_frame") is True and fully,"Derived fully-in-frame flag disagrees with bbox")
                boxes.append(box)
            actual_overlap = any(min(a[2],b[2]) > max(a[0],b[0]) and min(a[3],b[3]) > max(a[1],b[1]) for i,a in enumerate(boxes) for b in boxes[i+1:])
            actual_shutter = any(w["start_s"]-1 <= timestamp <= (float("inf") if w["end_s"] is None else w["end_s"])+1 for w in windows)
            require(not actual_overlap and not actual_shutter and shutter_evidence["complete_recorded_actions"] is True,
                    "Source-time overlap/shutter evidence excludes visible labels")
            require(frame["truth_complete"] is True and not frame["exclusion_reasons"] and not frame.get("shutter_guard") and not frame.get("overlap")
                    and frame.get("source_time_audit",{}).get("complete") is True
                    and source.get("scene_asset_audit",{}).get("supported") is True
                    and source.get("scene_asset_audit",{}).get("closed_scene_occluders_complete") is True
                    and len(frame["actor_geometry"]) == len(source["expected_actor_ids"])
                    and {g["id"] for g in frame["actor_geometry"]} == set(source["expected_actor_ids"])
                    and all(g["status"].startswith("KNOWN_") for g in frame["actor_geometry"])
                    and all(g["fully_in_frame"] for g in frame["gt"]), "Incomplete geometry cannot become visible eligible")
            if source["stage"] == 3:
                camera_audit = frame.get("camera_geometry",{})
                require(camera_audit.get("status") == "KNOWN" and camera_audit.get("method", "").startswith("Bracketed physical")
                        and camera_audit.get("source_image_s") == timestamp
                        and type(camera_audit.get("tf_translation_error_m")) in (int,float) and 0 <= camera_audit["tf_translation_error_m"] < .005
                        and type(camera_audit.get("tf_angle_error_rad")) in (int,float) and 0 <= camera_audit["tf_angle_error_rad"] < .03,
                        "Stage3 requires actual source-time dynamic physical camera corroborated by optical TF")
    require(source.get("coverage") == frame_coverage(source["frames"]),"Derived extraction coverage/denominators/reasons differ from retained opportunities")
    return source, protocol, plans


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "protocol", "extract", "verify"), nargs="?", default="describe")
    parser.add_argument("--core-plan", type=Path); parser.add_argument("--core-sha256")
    parser.add_argument("--extension-plan", type=Path); parser.add_argument("--extension-sha256")
    parser.add_argument("--protocol", type=Path); parser.add_argument("--protocol-sha256")
    parser.add_argument("--slot-id"); parser.add_argument("--recording", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.action == "describe":
        print(json.dumps({"kind": KIND, "rule": RULE, "actual_bag_reads": 0, "actual_inference": False, "formal_attempts_started": 0})); return 0
    if args.action == "protocol":
        require(all((args.core_plan,args.core_sha256,args.extension_plan,args.extension_sha256,args.output)), "Explicit original two plans/SHA and fresh output required")
        protocol = make_protocol({"path":str(args.core_plan),"sha256":args.core_sha256}, {"path":str(args.extension_plan),"sha256":args.extension_sha256})
        assert_external_output(protocol,args.output)
        write_new(args.output, protocol)
    else:
        require(args.protocol is not None and args.protocol_sha256, "Explicit prospective protocol/SHA required")
        binding = {"path":str(args.protocol),"sha256":args.protocol_sha256}
        if args.action == "extract":
            require(args.slot_id and args.output is not None, "Original slot ID and fresh external directory required")
            source = extract(binding, args.slot_id, args.output); print(json.dumps({"status":source["extraction_status"],"coverage":source["coverage"]}))
        else:
            require(args.recording is not None, "Recording required")
            source, _, _ = verify_recording(args.recording, binding); print(json.dumps({"status":"VERIFIED_PROPOSALS_NOT_APPROVAL","coverage":source["coverage"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
