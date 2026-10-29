# 最终同源的四条歧义安全开发执行卡

这是一张待执行开发卡，不是结果或协议登记。本卡不执行仿真；实际运行由主代理串行安排。四槽独立于核心12格、正式120核心和160扩展分母，不消耗1000–1009，不重跑或覆盖任何历史槽。使用最终已验证飞行源对应的新PROBE计划定位冻结根；13仅是当前候选修订，若后续更换冻结根则记录实际修订，不能沿用旧修订成功结论。

当前固定矩阵不足以强制覆盖两项行为：auto_unique只见一个目标；三目标crossing的stage2评价未要求实际所选目标几何歧义，零歧义窗口可使条件检查成立；160扩展也只继承单目标。历史两类auto_unique、行人ambiguity和汽车ambiguity v5的严格通过只作历史依据，原失败和未知区间保持不变。

| 新开发槽 | 场景/控制 | 专项必须观察到 |
| --- | --- | --- |
| person / auto_unique_multi / seed004 | stage2三行人，parallel，无选框，legacy，中位相机 | 多帧新鲜多候选、从未自动跟随、末尾≥5秒AMBIGUOUS/HOVER、无有效目标运动命令、物理速度证据 |
| car / auto_unique_multi / seed004 | 同上，三汽车 | 同上 |
| person / locked_ambiguity / seed004 | stage2三行人，middle初选，hybrid_3d，ambiguity | 所选track实际属于ambiguous_track_ids、控制暂停、无自动换任务、末尾≥5秒同UUID的AMBIGUOUS/LOST与HOVER、独立速度证据 |
| car / locked_ambiguity / seed004 | 同上，三汽车，50秒观察 | 同上；保留较长合并过程，不用普通lost悬停冒充几何歧义 |

先声明四个全新名字、实际源PROBE计划路径/文件SHA/plan_sha256、冻结根、飞行关键源码映射、权重SHA、磁场runtime/library绑定及本卡SHA。保存到全新的独立审计目录，逐槽记录原始命令、开始/结束UTC、退出码和独立评价文件SHA。已有名字/报告一律拒绝覆盖；基础设施失败时先保留并诊断，再决定未尝试槽。不能按结果删槽、换种子或更换判据。

下面的bash模板只提供命令。`tracking_root`应由明确指定的实际PROBE计划的`frozen_root`取得；`tracking_tag`须事前登记并从未使用。不要直接使用旧stage23整批flight模板：其默认起飞、时间、参考点、磁场和汽车资源不同。四槽不加人工快门或长失后重选，避免抢先触发另一种失联事件。

```bash
tracking_plan=/absolute/path/to/the/final_source_probe/plan.json
tracking_root="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["frozen_root"])' "$tracking_plan")"
tracking_tag=reliability_v4_safety13
tracking_card=/absolute/path/to/reliability-v4-ambiguity-execution.md

tracking_run_class() {
  tracking_class="$1"
  if [ "$tracking_class" = person ]; then
    tracking_model=yolo11n.pt
    tracking_size=320
    tracking_threads=2
    tracking_distance=5
  else
    tracking_model=yolo11s.pt
    tracking_size=640
    tracking_threads=4
    tracking_distance=9
  fi
  tracking_common=(
    --stage 2 --class "$tracking_class" --seed 4
    --condition clean --estimator-method adaptive_kf
    --command-mode velocity --gimbal-mode midpoint
    --real-time-factor 0.5 --max-inference-rate-hz 10
    --monitor-tick-s 0.02 --control-reference ground_footprint
    --motion-profile-kind standard
    --model-path "$tracking_root/models/$tracking_model"
    --inference-image-size "$tracking_size" --inference-threads "$tracking_threads"
    --desired-distance-m "$tracking_distance"
    --takeoff-height-m 3 --takeoff-mode px4_native
    --wall-timeout 300 --render-backend egl --gazebo-render-driver llvmpipe
    --magnetic-environment gazebo_enu
    --magnetic-runtime-manifest "$tracking_root/config/px4_magnetic_runtime.json"
    --magnetic-library-registration "$tracking_root/config/gazebo_magnetic_runtime_humble22.json"
    --propagate-vehicle-uncertainty --px4-time-mode source_sim
  )

  tracking_name="${tracking_tag}_${tracking_class}_auto_unique_multi_seed004"
  bash "$tracking_root/scripts/run_research_session.sh" \
    "$tracking_root/scripts/run_stage1_trial.py" "${tracking_common[@]}" \
    --name "$tracking_name" --target-mode auto_unique --association-mode legacy \
    --scenario-kind parallel --initial-select none --initial-min-candidates 2 \
    --duration 35 --no-follow-duration-s 35
  tracking_trial="$tracking_root/results/$tracking_name"
  bash "$tracking_root/scripts/run_research_session.sh" \
    "$tracking_root/scripts/run_stage23_matrix.py" \
    --evaluate-auto-unique "$tracking_trial/rosbag" --target-class "$tracking_class" \
    --output "$tracking_trial/auto_unique_evaluation_v2.json"
  tracking_common_checks

  tracking_name="${tracking_tag}_${tracking_class}_locked_ambiguity_seed004"
  bash "$tracking_root/scripts/run_research_session.sh" \
    "$tracking_root/scripts/run_stage1_trial.py" "${tracking_common[@]}" \
    --name "$tracking_name" --target-mode locked_target --association-mode hybrid_3d \
    --scenario-kind ambiguity --initial-select middle --initial-min-candidates 3 --duration 50
  tracking_trial="$tracking_root/results/$tracking_name"
  bash "$tracking_root/scripts/run_research_session.sh" \
    "$tracking_root/scripts/evaluate_stage2_flight.py" "$tracking_trial/rosbag" \
    --target-class "$tracking_class" --telemetry-jsonl "$tracking_trial/telemetry.jsonl" \
    --monitor-summary "$tracking_trial/summary.json" --no-require-occlusions \
    --require-ambiguity --terminal-expectation hover \
    --output "$tracking_trial/stage2_evaluation.json"
  tracking_common_checks
}
```

模板中的共通评价应对**每个**实际`tracking_trial`执行，外层守护保留每个退出码和日志；飞行非零不能写成成功，也不能因为专项报告缺失而跳过该槽记账。

```bash
tracking_common_checks() {
bash "$tracking_root/scripts/run_research_session.sh" \
  "$tracking_root/scripts/evaluate_px4_source_clock.py" "$tracking_trial" \
  --output "$tracking_trial/px4_source_clock_report.json"
bash "$tracking_root/scripts/run_research_session.sh" \
  "$tracking_root/scripts/evaluate_native_startup.py" "$tracking_trial" \
  --output "$tracking_trial/native_startup_report.json"
tracking_tail_speed
}
```

还需逐项保留/核验：`run_config.json`、`configuration/runtime_parameters.yaml`、`configuration/source_sha256.json`、实际world/model与权重说明、磁场实际启动/loaded libraries、renderer证据、原生bag读回与`bag_integrity.json`、`recording_closure.json`及其最终Clock/全部GT闭合、`process_exit_codes.json`和`ros.log`每个子进程退出、monitor/telemetry及完整未裁尾记录。native/source PASS、正常外层退出、独立专项PASS和物理尾速都分别判断，不能互相替代。无人工遮挡的surface INCOMPLETE属于预期覆盖边界，不改成遮挡PASS；这四槽也不适用普通跟随终态的导航稳定门。

唯一实例专用schema2评价已经核验末尾`/vehicle/odometry`速度≤0.30m/s。指定个体strict stage2的`terminal_hover()`只核状态、控制器和无效命令五秒，**没有实际速度判据**。因此四槽统一追加以下纯离线检查：原始Clock最后5.2秒、不根据成功帧移动窗口；改编PX4 odom的实测速度与独立Gazebo GT的base_link点位移速度同时保留。GT仅离线使用，按保存的机体几何杆臂变换，不读目标真值、不拟合偏置。相邻GT位置差分是记录间隔平均速度，不宣称连续时间峰值或飞行安全认证。

下面片段在实际飞行结束后由主代理运行，本卡编写时没有执行。`tracking_card`指向本卡的实际可读路径，供报告绑定审核过的代码文本；可位于独立审计目录，无需修改冻结源码。输出采用独占创建。

```bash
tracking_tail_speed() {
bash "$tracking_root/scripts/run_research_session.sh" - "$tracking_trial" "$tracking_card" <<'PY'
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
PY
}
```

按上面的顺序先定义全部函数，再由外层逐命令审计器记录各条原命令、UTC、退出码和日志，调用下面两个入口，顺序运行四个新槽。函数内部的每条命令都必须记账；不能把函数末条命令的退出码当作整槽结果。任一异常路径没有生成报告时，保留非零退出和日志并记为缺证，不能视为通过。首次运行前确认四个试验目录及所有评价输出均不存在。

```bash
tracking_run_class person
tracking_run_class car
```

最后汇总四条原飞行退出/基础设施状态、专项结果和独立尾速结果，附实际文件SHA及缺证原因。歧义未发生、只出现普通LOST、命令流断开、真值缺尾或真实速度未停均不能写为安全专项通过。任何失败原件保持不变，新增诊断另起文件；本卡不授权覆盖旧报告、重试同槽或修改正式协议。
