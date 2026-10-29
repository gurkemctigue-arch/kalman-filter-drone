# 28 格实际开发证据的容量预算组装器

`tools/reliability_v4_storage_budget.py` 仅把既有元数据和显式预算假设组装为
`reliability_v4_guard.py` 所需的 `storage` 对象。它不登记协议，不给工程结果新增
PASS，不调用 runner，也不准入任何正式槽。工具和测试的创建不表示已经运行。

## 输入与来源

- 完整、同一冻结根/source/model/results 的 seed004 两类六组 `PROBE` 计划和
  两类八工况 `EXTENSION_PROBE` 计划，各格必须恰有一个原槽，共 28 格。
- 原 `freeze_validation/artifact_storage/<trial.name>.json` 文件大小回执，以及
  每格原 `bag_integrity.json`、`summary.json`、`recording_closure.json` 和终态记录。
  原试验可保留 `FAIL` 或 `EVALUATION_PENDING`，但必须真实 `COMPLETED`、flight
  exit 为整数 0、无 infrastructure stop、归档和 closure 闭合，且最终录制 Clock
  覆盖 `follow_start + 75s`。正常 monitor 最后一帧可能记为 74.98s，不能用该帧
  取代收尾后的完整源钟区间。2026-10-30 前瞻协议的12核心和16扩展均为75s；
  原45s、20s clean、缺格和中止试验不能充当75s对应槽或直接提供其容量实测。
- 现有 guard 的 `storage-probe` 原 JSON，必须是
  `RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY` / `METADATA_ONLY_NOT_FORMAL_ADMISSION`。
  组装器用 `NativeStorage` 重新核对实际 DrvFS/9p 挂载、Windows UniqueId、当前
  宿主卷空闲和注册表对应的 WSL VHD 路径；ext4 逻辑空闲另列，不能替代宿主空闲。
- 一份单独的小型 assumptions JSON。增长因子、预算及其依据必须显式提供；工具
  没有隐藏的默认增长或默认交付预算，也不会从旧 Jazzy 录制推断当前 28 格。

所有输入计划/回执/元数据/工具文件都绑定小文件 SHA。原 bag、telemetry、视频
和 VHD 不读取或 hash；只按回执中的具名文件列表逐项 stat，没有目录递归扫描。
原 receipt 的 `trial` 保持计划中的词法路径；路径安全和物理卷判断单独 resolve。
每个实际物理卷只有一个 `drive_D` / `drive_E` 等 ID，不把同一 UniqueId 重复计容。

## 预算假设模板

下列 `null` 必须替换为经过讨论的有限因子或非负整数 bytes；模板本身不能用于
组装。三种增长因子都必须 ≥1。五项交付预算每项合计必须 >0，各卷都必须显式
列出；同卷示例只有 `drive_D`，分卷时每份 bytes map 还必须列出 `drive_E`。

```json
{
  "schema_version": 1,
  "kind": "RELIABILITY_V4_STORAGE_ASSUMPTIONS_NOT_ADMISSION",
  "basis": "填写假设来源、日期和采用这些余量的理由",
  "persistent_growth_factor": null,
  "raw_growth_factor": null,
  "compressed_growth_factor": null,
  "persistent_extra_bytes_by_volume": {"drive_D": null},
  "persistent_basis": "每格完整开发总 bytes 的增长因子及每条额外持久化预算依据",
  "temporary_extra_bytes_by_volume": {"drive_D": null},
  "temporary_basis": "三 raw、两 compressed 的保守假设和额外余量依据，非实测峰值",
  "additional_remaining_bytes": {"drive_D": null},
  "additional_remaining_basis": "剩余构建和其他预算，填 0 也需说明理由",
  "delivery_reservations": {
    "offline_replay20": {"bytes_by_volume": {"drive_D": null}, "basis": "20 条离线回放新增输出"},
    "videos12": {"bytes_by_volume": {"drive_D": null}, "basis": "12 份演示视频"},
    "detection_audit": {"bytes_by_volume": {"drive_D": null}, "basis": "检测审计输出"},
    "figures_documents": {"bytes_by_volume": {"drive_D": null}, "basis": "图表、Word 和 PDF"},
    "runtime_logs": {"bytes_by_volume": {"drive_D": null}, "basis": "剩余日志"}
  }
}
```

每格 results 卷持久化预算为 `ceil(total_trial_bytes * persistent_growth_factor)`，
再为每个卷加该卷显式 `persistent_extra_bytes_by_volume`。分卷时 VHD 侧没有要
永久留下的逐槽副本，可明确填 0；原始 spool 等临时副本按临时界计算，不能再次
当作 280 份永久输出。完整正式预算始终是每格十条、共 280 条，不挑成功样本。

临时界与 guard 的现有合同逐字同义：每格计算
`3*ceil(raw_bytes*raw_growth_factor) + 2*ceil(compressed_bytes*compressed_growth_factor)`，
各卷加自己的额外 margin，再对 28 格取最大值。每个涉及的实际物理卷都保守
预留完整界，同卷只计一次；最终 reserve 为 `max(8GiB, temporary_peak_bytes)`。
这是已声明假设下的预算，不是未来体积或临时峰值的实测保证。

## 使用与结果边界

在全部 28 格真实回执存在、卷位置已确定、假设已填好之后，从当前 WSL 环境运行：

```bash
python -B tools/reliability_v4_storage_budget.py \
  --core-development-plan /absolute/core_probe_matrix/plan.json \
  --extension-development-plan /absolute/extension_probe_matrix/plan.json \
  --size-evidence-dir /absolute/results/freeze_validation/artifact_storage \
  --physical-inventory /absolute/storage_inventory.json \
  --assumptions /absolute/storage_assumptions.json \
  --output /absolute/results/new_storage_budget01/budget.json
```

缺少任何对应格会列出 `matrix/class/condition/缺失文件`，返回 2，不生成半成品
storage，也不拿 clean 或其他历史源补齐。输出只能是全新 JSON，位于真实 results
里的独立新目录或项目外；禁止原试验、原矩阵、回执目录、任何输入别名，以及冻结
或当前源码树的 config/build/install 等位置，防止把预算文件加入冻结扫描范围。

输出 `kind=RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION`，含：

- `storage` 与其 canonical SHA，后续原样放入 guard manifest；
- `provenance`，保留原 28 格终态、实际输入小文件绑定、完整假设和工具来源；
- `capacity_preview`，按当次宿主空闲列出完整 280 预算、交付、临时预留和差额。

即使预览有足够空间，也不产生 admission；空间不足时仍可保存明确显示不足的
预算提案。后续现有 guard 必须核最终计划、真实开发 gate、登记、R0、这些原始
证据及当时实际宿主容量，并在每个新槽前重新判断。组装器不改变该合同。

测试仅使用小型 synthetic JSON 与占位文件，覆盖拒绝缺格/伪终态/错源/短时长、
具名 size 变化、单卷和分卷计容、五项交付、禁止读包/VHD、输出路径保护，并把
组装对象交给原 `validate_storage` 核结构与算式。fixture 不是运行证据或正式准入。
