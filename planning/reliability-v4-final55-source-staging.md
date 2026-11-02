# final55 的源 staging 与外置交付工具

本文件是未来执行说明，不是 staging、冷构建、准入或正式实验已经完成的收据。2026-11-03 本次只读取 Windows 上的小源码和原始计划元数据，未执行 WSL、ROS、原生构建或模型读取，未创建任何实际 staging 或运行元数据。它补充原 `D:/WSL/UAVHumble22-validation/final55_normal_registration_execution_card01.md`，不替换或修改该卡、54 的原件及旧收据。路线继续使用 normal registration，不使用旧 DDS48 sealer。

## 为什么 final55 不能直接复制当前工作区

`scripts/run_reliability_v4.py` 的 `source_hashes()` 扫描 `scripts`、`uav_tracking`、`ros2_ws/src`、`config`、`launch`、`models`、`patches` 中规定后缀的文件，以及少量根目录文件。`flight_source_hashes()` 实际为该完整 map 减去离线白名单和 runner；它不等同于“飞行进程实际 import 的模块”。54 开发证据与55 target 的 flight map 要求字典精确相等。

当前新 `scripts/build_acceptance_dashboard.py` 不在 `OFFLINE_HELPERS`，因此修改它会触发 flight map 不匹配。`scripts/build_reliability_v4_report.py` 在离线白名单内，但本次选择更简单的策略：55 staging 保留54完整308项 source map，所有新交付、lineage、图表、报告及 publication 工具外置，不改白名单或放宽 gate。

`tools/**`、`README.md` 和 `docs/**` 不进入该计划 map，但会进入完整 rsync 源复制证明。冷构建以后再把它们写入55，同样会破坏最终全树闭合。replay 注册绑定的是最终55的完整 source map；开发导出则另外核验指定在线、export 与 replay helper，不能混用这些 map 的含义。

## 已从真实小元数据确认的绑定

canonical 开发计划：

```text
/root/uav_tracking_fullplan_v4_humble54/results/reliability_v4_humble54_core12_probe01_matrix/plan.json
file SHA256: ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b
plan_sha256: 3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31
source_hashes: 308 entries
model_hashes: 6 entries
algorithm source commit: a32060d; immutable54 is not updated to the current delivery commit
```

六个模型全部保留；不能只复制当前 person/car 实际选用的两个权重：

| 相对路径 | 原计划 SHA256 |
|---|---|
| `models/yolo11m.pt` | `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95` |
| `models/yolo11m_car_sim_train20_04.pt` | `bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c` |
| `models/yolo11n.pt` | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| `models/yolo11s-seg.pt` | `1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3` |
| `models/yolo11s.pt` | `85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5` |
| `ros2_ws/src/uav_tracking_bringup/models/yolo11n.pt` | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |

五份 runtime registration 同样逐字节保持54，不能因 Git 忽略而漏掉本机文件：

| 相对路径 | 原计划 SHA256 |
|---|---|
| `config/dds_runtime_humble22.json` | `4e517b62e823585b53dd2ac503f65eaf9bc3fd4c59d9d8fdb900d985f99d030d` |
| `config/ros_gz_runtime_humble22.json` | `08cbc9ea8a2b6e50b71efc4910e5adef7c309b742fb0e9177cd803e934a028af` |
| `config/ros_gz_clock_runtime_humble22.json` | `908f8b7e18154377e57ce6f92922b63b36f7d4fb90ac79e61cc1b8dd95d3e4e4` |
| `config/px4_magnetic_runtime.json` | `3c4f9693cfab51c6b2049af619bfb6e3edbd22a8328468b7e84f75053485c66b` |
| `config/gazebo_magnetic_runtime_humble22.json` | `0e80e51994948b5186c3a76c7e5c9651d27cf3d9acf63109f3f66544de801e6a` |

以下未来命令在所有实际 core/safety/extension owner 与子进程闭合、取得单一重负载窗口后，才在 `UAVHumble22` 的 Bash 中执行。新路径先按当时实际情况核实；已存在则停止，选择新的路径，不覆盖旧尝试。不要把整段作为本轮已经执行的事实。

## 1. 建立全新 staging，跳过54的顶层 results 符号链接

```bash
set -euo pipefail
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_core_dev="$tracking_dev/results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
tracking_stage=/root/uav_tracking_final55_staging01
tracking_final=/root/uav_tracking_fullplan_v4_final55
tracking_project='/mnt/d/基于yolo和卡尔曼滤波'
tracking_results="$tracking_project/results/frozen_fullplan_v4_final55"
tracking_python=/root/uav_humble22/venv/bin/python

test "${WSL_DISTRO_NAME:-}" = UAVHumble22
test -d "$tracking_dev"
test -L "$tracking_dev/results"
test -f "$tracking_core_dev"
test -x "$tracking_python"
for tracking_new in "$tracking_stage" "$tracking_final" "$tracking_results"; do
  test ! -e "$tracking_new"
  test ! -L "$tracking_new"
done
test -d "$(dirname -- "$tracking_results")"
mkdir -- "$tracking_stage"
rsync -a --exclude='/results' \
  --exclude='__pycache__' --exclude='.pytest_cache' --exclude='results/' \
  --exclude='.git/' --exclude='node_modules/' --exclude='.test_temp/' --exclude='*.egg-info/' \
  --exclude='ros2_ws/build/' --exclude='ros2_ws/install/' --exclude='ros2_ws/log/' \
  "$tracking_dev/" "$tracking_stage/"
test ! -e "$tracking_stage/results"
test ! -L "$tracking_stage/results"
mkdir -p -- "$tracking_stage/results/recorded_estimator_research"
cp -- "$tracking_dev/results/recorded_estimator_research/research_report.json" \
  "$tracking_stage/results/recorded_estimator_research/research_report.json"
cmp -- "$tracking_dev/results/recorded_estimator_research/research_report.json" \
  "$tracking_stage/results/recorded_estimator_research/research_report.json"
test -d "$tracking_stage/results"
test ! -L "$tracking_stage/results"
```

这里额外的 `--exclude='/results'` 锚定 rsync 传输根，不带尾斜杠，因此跳过54顶层名为 `results` 的符号链接本身。其余排除项与实际公开 freeze/source-integrity 的规则相同。公开规则中的 `results/` 只按目录排除，不能单独用于跳过54已有的符号链接。staging 的普通 results 目录会在后续公开 freeze 中被正常排除；其真实 `research_report.json` 由公开 freeze 的显式 `cp` 读取。不要修改54的链接，不复制旧 recordings、slot、gate 或结果树。

## 2. 用原计划核验完整308项，不另建验证框架

下面直接调用 staging 内原字节 runner 的既有 `source_hashes()`，并先核对 runner 自身 SHA；不会调用实验入口。它核对名集和所有值，新增一个扫描可见文件也会拒绝。模型和 runtime 均包含在308项中，另核六模型子集及五runtime绑定以明确验收范围。失败后保留该 staging，调查并另选新路径，不修改54来迁就比较。

```bash
"$tracking_python" -B - "$tracking_dev" "$tracking_stage" "$tracking_core_dev" <<'PY'
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

dev, stage, plan_path = map(lambda value: Path(value).resolve(strict=True), sys.argv[1:])
raw = plan_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b'
plan = json.loads(raw)
assert plan['plan_sha256'] == '3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31'
assert plan['mode'] == 'PROBE' and plan['selected_seeds'] == [4]
assert plan['frozen_root'] == str(dev) and len(plan['trials']) == 12
expected = plan['source_hashes']
assert len(expected) == 308 and len(plan['model_hashes']) == 6
runner = stage / 'scripts/run_reliability_v4.py'
assert hashlib.sha256(runner.read_bytes()).hexdigest() == expected['scripts/run_reliability_v4.py']
spec = importlib.util.spec_from_file_location('reviewed54_staging_source_check', runner)
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
assert v4.source_hashes(dev) == expected, 'immutable54 actual source set/bytes differ from canonical plan'
actual = v4.source_hashes(stage)
assert actual == expected, 'staging source set/bytes differ from all 308 canonical entries'
assert {name: digest for name, digest in actual.items() if name.endswith('.pt')} == plan['model_hashes']
runtime = (
    'config/dds_runtime_humble22.json',
    'config/ros_gz_runtime_humble22.json',
    'config/ros_gz_clock_runtime_humble22.json',
    'config/px4_magnetic_runtime.json',
    'config/gazebo_magnetic_runtime_humble22.json',
)
for name in runtime:
    assert actual[name] == expected[name]
    assert (stage / name).read_bytes() == (dev / name).read_bytes()
original = json.loads((dev / 'results/freeze_validation/source_integrity/source_before.json').read_bytes())['entries']
planning = (
    'planning/reliability-v4-preregistration.json',
    'planning/reliability-v4-extension-preregistration.json',
    'planning/reliability-v4-estimator-replay-preregistration.json',
)
for name in planning:
    data = (stage / name).read_bytes()
    assert data == (dev / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == original[name]['sha256']
    document = json.loads(data)
    assert document['status'] == 'DRAFT_NOT_FROZEN_NOT_EXECUTED'
assert plan['protocol']['navigation_acceptance']['status'] == 'REGISTERED'
assert (stage / 'results').is_dir() and not (stage / 'results').is_symlink()
report = Path('results/recorded_estimator_research/research_report.json')
assert (stage / report).read_bytes() == (dev / report).read_bytes()
print('PASS: original plan pins; exact 308 source entries; all 6 models; 5 runtime registrations; 3 original DRAFTs; ordinary staging results and real report bytes')
PY
```

三个顶层协议仍为 DRAFT。原有数值 `navigation_acceptance` 已 REGISTERED，保持其原值和绑定，不把它重置为 DRAFT，也不提前发布顶层协议。不要在 staging 覆盖当前新 dashboard/report，不复制当前工作区的新 tests、planning 文档或其他交付工具进去。

## 3. 从 staging 自身调用既有公开冷构建入口

```bash
/bin/bash "$tracking_stage/tools/diagnostics/reliability54_build01/prepare_and_validate.sh" \
  "$tracking_final" "$tracking_results" "$tracking_dev"
test -L "$tracking_final/results"
test "$(realpath -e -- "$tracking_final/results")" = "$(realpath -e -- "$tracking_results")"
```

wrapper 的 source 从它自身所在位置推导，不能从当前工作区调用另一个 wrapper 并只传 staging 变量。它清理继承环境、核五份 runtime 与 reference54 相同，执行公开 freeze、cold colcon、import/ament isolation、完整原测试及原 native validation，并保存这次55自身的 `source_before.json`、`source_after.json`、`frozen_actual.json` 和原冷构建收据。公开 `source_sha256.txt` 只覆盖它声明的目录；完整树证明以 `source_integrity` 的 rsync-filtered 三份 map 为准。

构建结果不得提前写 PASS。失败尝试的目录和收据保留，不覆盖同名路径重做。

## 4. 新工具留在55之外，保持各自 import 根完整

新 publication 工具不要求出现在54或55源树。报告工具通过 `ROOT = parents[1]` 及同目录 imports 加载多个依赖，所以不应只孤立复制两个 `.py`。以下未来命令将**已审核并提交的交付 Git HEAD**归档成独立工具树；它不含 Git 忽略的模型、runtime 本机文件或 results，不可用作算法 staging。执行前必须已完成该工具提交的审核，不能把动态 HEAD 当作自动批准。

```bash
tracking_delivery_tools=/mnt/d/WSL/UAVHumble22-validation/final55_delivery_tools01
test ! -e "$tracking_delivery_tools"
test ! -L "$tracking_delivery_tools"
git -C "$tracking_project" diff --quiet HEAD -- scripts tools uav_tracking docs tests
tracking_delivery_commit="$(git -C "$tracking_project" rev-parse --verify HEAD)"
mkdir -- "$tracking_delivery_tools"
git -C "$tracking_project" archive --format=tar "$tracking_delivery_commit" \
  | tar -xf - -C "$tracking_delivery_tools"
tracking_publication="$tracking_delivery_tools/tools/reliability_v4_publication.py"
tracking_publication_sha=8e1c903e25abe1557e64c2ab4c64662691e8962aeb2769aa57d2ec57f8064cd6
printf '%s  %s\n' "$tracking_publication_sha" "$tracking_publication" | sha256sum --check --strict
printf 'external_delivery_commit=%s\nexternal_delivery_root=%s\n' \
  "$tracking_delivery_commit" "$tracking_delivery_tools"
```

若后续 publication 已审核源码的 SHA 发生变化，先完成新的源审核及实际字节核验，更新新执行请求的真实 binding；不能仅改上面的 pin 让比较通过，也不覆盖本次独立工具目录。固定审计工具包仍为 `/root/uav_tracking_snapshot_audit54_tools01`，其中 guard 的 SHA 保持 `e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e`。

后续使用原 normal execution card 的真实 CLI 和请求结构，令其 `tracking_publication` 指向这个外置工具文件，通过55的原 `scripts/ros_python.sh` 调用。新报告明确传入真实55的 `--core-plan`、`--extension-plan`、`--replay-configuration`、`--replay-source-root "$tracking_final"`、`--detection-source-root "$tracking_final"` 及各实际输入；新 dashboard 明确传入实际 `--v4-package`。lineage 的 context/source pins 绑定实际输入版本。输出进入新的独立结果目录，工具源码和输入哈希单独保留；外置工具不代替55原 gate evaluator，也不改写原 terminal report。不得以工具归档的默认 `ROOT` 冒充实际飞行源根。

## 5. 冷构建后仅允许三个规范 planning 文件发生变化

继续按原 normal card 执行：未飞的 target 定义 → core/extension gate → safety assembly → core/extension prospective publication → 正式120/160定义 → replay assembly/publication → 原 fixed guard admission → 新 final source sidecar。extension plan 的 `--probe-gate` 仍用 CORE_GATE，EXT_GATE 绑定 extension readiness。

最终 sidecar 对比的是本次55的完整冷构建 DRAFT map，而不是要求55整棵树等于旧54。只允许以下三个**已有**路径变化；不得有新增或缺失源路径：

- `planning/reliability-v4-preregistration.json`：只改顶层 `status`、`registration_utc`。
- `planning/reliability-v4-extension-preregistration.json`：只改 `status`、`registration_utc`、真实 `development_readiness`。
- `planning/reliability-v4-estimator-replay-preregistration.json`：必须为真实 registrar 生成并验证的 replay candidate 字节。

保留原冷构建 DRAFT map、native receipt 和三个原始 DRAFT archive；另建独立 final sidecar，不替换旧 map/report。不得在55添加本说明、新 README/docs、dashboard、lineage 工具或 tests；所有这类新文件继续留在外置工具树。registrar seal 是准入检查，不代替全树 sidecar。

## 实际源码依据

- `scripts/run_reliability_v4.py`：`HASH_FOLDERS`/`HASH_SUFFIXES`、`OFFLINE_HELPERS`、`source_hashes()`、`flight_source_hashes()`、`validate_probe_gate()` 的精确 flight-map 比较及 evaluator/helper provenance。
- `scripts/freeze_full_plan_workspace.sh`：公开 rsync 排除、真实 research report 的显式复制、cold build、隔离检查和原测试。
- `tools/diagnostics/reliability54_build01/source_integrity.py`：`RSYNC_EXCLUSIONS`、符号链接记录及拒绝已有 source results 链接、完整 pre/post/frozen 字节比较。
- `tools/diagnostics/reliability54_build01/prepare_and_validate.sh`：自身位置决定 source、五runtime reference比较及公开 cold-build调用。
- `tools/reliability_v4_register.py`、`scripts/run_estimator_replay_v4.py`：最终完整 source map、开发 export/helper及在线源的不同绑定。
- `tools/reliability_v4_snapshot_audit.py`：保留54原扫描额外文件的独立合同，不把55 map伪装成54历史快照。
- `tools/reliability_v4_publication.py`：三个规范路径及独立 final source sidecar 的实际限制。
