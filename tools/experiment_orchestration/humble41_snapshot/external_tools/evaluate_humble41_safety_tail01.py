import hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "scripts"))
import evaluate_stage1_flight as base
import evaluate_stage2_flight as stage2

trial, card = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(strict=True)
def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

inputs = [trial / name for name in ("run_config.json", "bag_integrity.json", "recording_closure.json")]
inputs += [card, Path(base.__file__), Path(stage2.__file__)]
archive = json.loads((trial / "bag_integrity.json").read_text(encoding="utf-8"))
closure = json.loads((trial / "recording_closure.json").read_text(encoding="utf-8"))
if archive.get("status") != "PASS" or closure.get("status") != "PASS":
    raise ValueError("Original archive and recording closure must independently pass")
bag = (trial / "rosbag").resolve(strict=True)
expected = {bag / "metadata.yaml": archive["published_metadata_sha256"]}
for item in archive["compressed_files"]:
    relative = Path(item["path"])
    path = bag / relative
    if relative.is_absolute() or not path.resolve(strict=True).is_relative_to(bag) or path.is_symlink():
        raise ValueError("Unsafe original bag input path")
    if path.stat().st_size != item["bytes"]:
        raise ValueError("Original bag byte count disagrees with archive")
    if path in expected: raise ValueError("Duplicate archive input path")
    expected[path] = item["sha256"]
if len(expected) < 2 or any(sha(path) != value for path, value in expected.items()):
    raise ValueError("Original bag bytes disagree with published archive hashes")
inputs += list(expected)
before = {str(path): sha(path) for path in inputs}
config = json.loads((trial / "run_config.json").read_text(encoding="utf-8"))
offset = config["vehicle_control_point_offset_flu_m"]
if len(offset) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in offset):
    raise ValueError("No finite declared offline body-point geometry")
records, metadata = base.read_rosbag(trial / "rosbag", preserve_clock=True)
clocks = [base.stamp_s(row.message.clock) for row in records if row.topic == "/clock"]
if not clocks or any(b < a for a, b in zip(clocks, clocks[1:])):
    raise ValueError("Missing/regressing original Clock; no tail certification")
end, start = clocks[-1], clocks[-1] - 5.2
odom = sorted((stage2.operational(row) for row in records if row.topic == "/vehicle/odometry"), key=lambda row: row.time_s)
odom = [row for row in odom if start <= row.time_s <= end]
speeds = [base._speed(row) for row in odom]

def body_point(transform):
    p, q = transform.transform.translation, transform.transform.rotation
    values = [p.x, p.y, p.z, q.x, q.y, q.z, q.w]
    if not all(math.isfinite(x) for x in values): raise ValueError("Nonfinite vehicle GT")
    norm = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
    if abs(norm - 1.) > 1e-3: raise ValueError("Invalid vehicle GT quaternion")
    x, y, z, w = q.x/norm, q.y/norm, q.z/norm, q.w/norm
    u, v, s = offset
    return (p.x + (1-2*y*y-2*z*z)*u + 2*(x*y-w*z)*v + 2*(x*z+w*y)*s,
            p.y + 2*(x*y+w*z)*u + (1-2*x*x-2*z*z)*v + 2*(y*z-w*x)*s,
            p.z + 2*(x*z-w*y)*u + 2*(y*z+w*x)*v + (1-2*x*x-2*y*y)*s)

points, vehicle_names = {}, set()
for row in records:
    if not row.topic.startswith("/ground_truth/"): continue
    for transform in row.message.transforms:
        name = transform.child_frame_id.strip("/")
        if not (name == "stage1_uav" or name.endswith("::stage1_uav") or name.rsplit("/", 1)[-1] == "stage1_uav"): continue
        vehicle_names.add(name)
        if len(vehicle_names) != 1: raise ValueError("Ambiguous independent vehicle GT names")
        t, point = base.stamp_s(transform.header.stamp), body_point(transform)
        if t in points and math.dist(points[t], point) > 1e-6: raise ValueError("Conflicting same-stamp vehicle GT")
        points[t] = point
gt = sorted((t, p) for t, p in points.items() if start <= t <= end)
pairs = [(a[0], b[0], math.dist(a[1], b[1]) / (b[0]-a[0])) for a, b in zip(gt, gt[1:]) if b[0] > a[0]]
gaps = lambda times: max((b-a for a, b in zip([start]+times, times+[end])), default=math.inf)
checks = {
    "input_decode_complete": metadata.get("clock_recorded") is True and not metadata.get("read_errors") and not metadata.get("unavailable_types"),
    "odom_tail_spans_five_seconds": bool(odom) and odom[-1].time_s-odom[0].time_s >= 5.-1e-9,
    "odom_tail_covers_original_end": gaps([row.time_s for row in odom]) <= .5,
    "all_observed_odom_speeds_le_0_30_mps": bool(speeds) and all(math.isfinite(v) and v <= .30 for v in speeds),
    "gt_tail_spans_five_seconds": bool(gt) and gt[-1][0]-gt[0][0] >= 5.-1e-9,
    "gt_tail_covers_original_end": gaps([row[0] for row in gt]) <= .10,
    "last_gt_equals_final_clock": bool(gt) and abs(gt[-1][0]-end) <= 1e-9,
    "all_gt_secant_speeds_le_0_30_mps": bool(pairs) and all(math.isfinite(row[2]) and row[2] <= .30 for row in pairs),
}
if any(sha(path) != value for path, value in before.items()): raise ValueError("Tail-audit input changed")
report = {"schema_version":1, "result":"PASS" if all(checks.values()) else "FAIL",
    "trial":str(trial), "interval":{"start_s":start, "end_s":end}, "checks":checks,
    "odom_speed_mps":base.summary(speeds), "independent_gt_base_link_secant_speed_mps":base.summary(row[2] for row in pairs),
    "declared_body_offset_flu_m":offset, "source_sha256":before, "bag_reader":metadata,
    "vehicle_gt_names":sorted(vehicle_names), "original_published_archive_sha256":{str(p):v for p,v in expected.items()},
    "scope":"Independent offline speed supplement only; full original tail retained. Does not certify ambiguity, physical target identity, continuous-time peak speed or flight safety."}
with (trial / "terminal_hover_speed_evaluation.json").open("x", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, allow_nan=False)
    handle.write("\n")
print(json.dumps({"result":report["result"], "checks":checks}, indent=2))
raise SystemExit(0 if report["result"] == "PASS" else 2)
