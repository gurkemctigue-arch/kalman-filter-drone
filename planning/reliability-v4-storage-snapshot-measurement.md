# Humble54 的显式快照审计与 28 格大小测量

`tools/measure_reliability_v4_storage.py` 默认仍严格比较原计划与飞行快照，不接受额外历史副本。仅在显式提供下面四项参数时，才使用相邻的 `reliability_v4_storage_snapshot_audit.py`，依据原完整冷冻映射核对全部 scanner 源码及所选模型、DDS 的快照集合。原有额外副本、差异和导入证据限制均保留；未知、缺失、变化的项仍拒绝。

该选项要求原固定审计工具的实际原生合同/首三份快照验证回执，以及实际完成的安全四场 registry、逐场记录、facts、guard validation、summary 和 owner 终态。它检查这些保存证据的绑定关系，重查当前 scanner 文本 SHA 和模型 stat；不重跑原 `validate_contract` / `validate_snapshot` 或安全 validator，不重新读取模型内容。袋、遥测和 VHD 也只 stat。保存的原生验证不等于本次新做了一次原生验证。

保存的原生回执仅接受以下三组已审查的 producer 与 driver 配对，任何交叉配对均拒绝：

| 回执版本 | producer SHA-256 | driver SHA-256 |
| --- | --- | --- |
| native01 | `1062409c9ef2aee5c611831f5100db9ce081557570bd28859a057c7c00cec8cc` | `6d6d1b56d14866355c7d423d3eaaed420860f20190d59acdfa20b853b9f3073b` |
| symlink recovery02 | `dda5af047eaa82c53e55260597c3643680c394fabab9cfc12c56dd15373a965c` | `82c5ee395e81db0a15339149d8775cf3a8fe1c9fdce524e9e54cf2bc3d287e73` |
| result-schema recovery03 | `a7c40c182f2101a90cd5a07b0e45b67116500ae60b4983095a6cbb86f5cb8984` | `6f93e58d6281aa882c4b89273fcfaa1dc1897d9651174e2b947d82bd28d5c172` |

三组都必须使用原 `e64e9da6…` guard、原 helper 和 registrar。recovery02 还要求真实完成的命令合同诊断；recovery03 单独要求保存的两个原公开 reader 归一化结果均为 PASS、原 raw report 的 `evaluation_status` schema，以及仅 specialist/tail 使用 raw `result` 的汇总诊断通过。recovery03 会重新绑定并读取原 safety02 的两个小 JSON report，核对各自 SHA 和 schema；它不重跑 reader 或旧槽 validator，也不读取袋、遥测或模型内容。两个恢复分支均要求原失败与合同保留、源文件及冷冻 metadata 前后不变。旧回执不能用于证明新 driver，准备文件或 synthetic 测试也不能替代实际回执。

实际 recovery02 原生回执的 SHA 为 `a50b14e46548a39a71609ad46a3b07e857bf15437d6e9e5f56d7491eaf270a20`，新 contract02 的 SHA 为 `91a0d3809aa8ae63bd24414a361e854e7d0c2e952ffdf80cf5a9701ae1938ef3`。原 safety01 的失败和 contract01 继续保留；该回执只证明新合同与命令路径诊断完成，不能代替 safety02 四场、extension16 或完整大小测量的实际完成记录。

实际 recovery03 原生回执的 SHA 为 `155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf`，新 contract03 的 SHA 为 `0d5bc8770c039615249caeeabd2b18598564a4cf50ae31e4023f4e47ae7a30ef`。其 `full_old_slot_reaudit_performed` 为 false，`original_registry_not_revalidated_or_rewritten` 为 true；它证明新合同与只读 schema 诊断完成，不证明旧槽已整体重验或四场已通过。原 safety01/safety02 的 INFRA、contract01/02 和原结果继续保留，不追溯改写或升级为 PASS；后续必须采用新合同前瞻登记并完成新 safety03 四场。

执行顺序如下：

1. canonical core12 全部通过，原 core owner 结束且清理完成。
2. 在原生空闲窗口完成既定导入审计、durable dummy 与原固定工具的合同/快照联调，保留真实回执。工具准备、Windows fixture 或静态接口检查不能代替该回执。
3. 用原固定工具和合同前瞻登记安全四场，真实执行并完成四场 PASS、guard 与 owner 闭合。
4. 按公开 CLI 登记、执行同源 extension16，保存全部终态。大小测量保留原 FAIL 等状态；不因计入空间而授予 readiness。
5. 从独立外置工具树运行大小测量。保留整个相邻工具目录及其 imports，不把新版工具写入 frozen54 或后续冷构建完成的 final55。输出必须是实际 results 下独立、尚不存在的新目录。
6. 之后由原预算工具结合真实物理盘清单、增长假设和交付预留组装容量预算；正式准入及逐槽守卫继续独立执行。

以下是未来执行卡，尚未在此文档更新中执行。只有 safety03 四场 PASS、guard 与 owner 闭合，且同源 extension16 全部完成终态登记、28 格均保留完整 75s 录制和原生归档验证后，才进入暂存与测量。`/root/uav_tracking_storage_measure54_tools01` 是此前的旧 b2f4 adapter bundle，继续保留；不能沿用它执行 schema03。新版必须从已审查 commit 暂存到全新 `tools02`，保留完整相邻 `tools/` 及 imports，不覆盖 tools01 或写入 frozen54/final55。

先在原生空闲窗口从 Windows 工作仓库的固定 Git commit 导出工具。下列命令只准备外置工具，不启动测量：

```bash
set -euo pipefail
tracking_repo=/mnt/d/基于yolo和卡尔曼滤波
tracking_commit=eedd8d9abcd6890b0bd5d0155f76ac08253426b9
tracking_tools=/root/uav_tracking_storage_measure54_tools02
test "$(git -C "$tracking_repo" rev-parse "$tracking_commit^{commit}")" = "$tracking_commit"
test ! -e "$tracking_tools"
test ! -L "$tracking_tools"
mkdir -- "$tracking_tools"
git -C "$tracking_repo" archive --format=tar "$tracking_commit" tools | tar -xf - -C "$tracking_tools"
(
  cd -- "$tracking_tools"
  sha256sum -c - <<'PINNED_TOOLS'
bea4c4ba80fe99991c5f13f91c2b00f375c94954af53ffbfa19e47d19f69bb6c  tools/measure_reliability_v4_storage.py
b6bb0f5a402ba1093d1c5d5061c5b2ac0d99b9153e7af73257ae5fdc873b2323  tools/reliability_v4_storage_snapshot_audit.py
e02424cc5df2e103c8994afca8fdeee7fba02c777e0bb50fd7e54576d3e6b4aa  tools/reliability_v4_storage_budget.py
e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e  tools/reliability_v4_guard.py
9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6  tools/reliability_v4_snapshot_audit.py
PINNED_TOOLS
)
```

随后使用实际 safety03 registry/native03 的已核对 SHA，不从未审查的最新文件自动取得任意新 SHA。registry 是前瞻登记文件；其固定 SHA 本身不代表四场已经完成。若任何输入字节变化或输出目录已经存在，应停止并查明原因，不改 pin、不覆盖输出、不重写历史结果：

```bash
tracking_runtime=/root/uav_tracking_fullplan_v4_humble54
tracking_tools=/root/uav_tracking_storage_measure54_tools02
tracking_registry="$tracking_runtime/results/reliability_v4_humble54_safety03_audit/registry.json"
tracking_native=/mnt/d/WSL/UAVHumble22-validation/safety54_schema_recovery03/native_recovery03.json
tracking_registry_sha=ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf
tracking_native_sha=155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf
test "$(sha256sum "$tracking_registry" | cut -d' ' -f1)" = "$tracking_registry_sha"
test "$(sha256sum "$tracking_native" | cut -d' ' -f1)" = "$tracking_native_sha"
test ! -e "$tracking_runtime/results/full28_storage_measurement_audit03"
test ! -L "$tracking_runtime/results/full28_storage_measurement_audit03"

PYTHONDONTWRITEBYTECODE=1 bash "$tracking_runtime/scripts/run_research_session.sh" "$tracking_tools/tools/measure_reliability_v4_storage.py" \
  --core-development-plan "$tracking_runtime/results/reliability_v4_humble54_core12_probe01_matrix/plan.json" \
  --extension-development-plan "$tracking_runtime/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json" \
  --output "$tracking_runtime/results/full28_storage_measurement_audit03" \
  --snapshot-audit-registry "$tracking_registry" \
  --snapshot-audit-registry-sha256 "$tracking_registry_sha" \
  --snapshot-audit-native-receipt "$tracking_native" \
  --snapshot-audit-native-receipt-sha256 "$tracking_native_sha"
```

四项参数必须一起出现。收集器必须看到完整 12+16 格，保留原状态和分母，并在发布输出前复查小文件、scanner 集合、文本和模型 stat。每格及汇总新增 `source_snapshot_validation`，明确保存原生/安全证据、当前文本检查、模型未重读以及非准入边界。缺少真实前置证据时拒绝，不生成部分大小证据。

测量完整输出后，容量预算组装器还需要以下六项 CLI 输入；它不把工程 FAIL 升级为 PASS，也不授予正式准入：

- `--core-development-plan`：本次 Humble54 core12 的原 `plan.json`。
- `--extension-development-plan`：与 core 同冻结根、source/model/results 的本次 extension16 原 `plan.json`。
- `--size-evidence-dir`：新生成的 `results/full28_storage_measurement_audit03`，内含全部 28 份 `<trial.name>.json`；不是其 `summary.json`，也不是旧 `freeze_validation/artifact_storage`。每格仍需原 terminal、`bag_integrity.json`、`summary.json`、`recording_closure.json`；必须 `COMPLETED`、整数 flight exit 0、无 infrastructure stop、75s Clock 覆盖、归档与 closure 闭合。完整曝光的原 FAIL/INCOMPLETE_EVIDENCE/EVALUATION_PENDING 可计容并原样保留，中止和缺格不可替代。
- `--physical-inventory`：guard `storage-probe --distribution UAVHumble22 --mount /mnt/d` 的真实 JSON，准确覆盖 results/VHD 宿主卷；若实际分卷，须传全部涉及卷。组装时重查卷 UniqueId、当前宿主空闲和注册表 VHD 路径，ext4 逻辑空闲另列。
- `--assumptions`：单独小 JSON，显式给出三种增长因子（均 ≥1）、各卷持久化/临时额外量、剩余构建量及依据，以及 `offline_replay20`、`videos12`、`detection_audit`、`figures_documents`、`runtime_logs` 五项正数交付预算。字段模板见 [容量预算组装器](reliability-v4-storage-budget-tool.md)。
- `--output`：实际 results 下全新独立目录中的新 `.json`，例如 `results/full28_storage_budget_audit03/budget.json`；不能放入原测量、原矩阵、原试验或源码/构建目录。

预算命令使用新 tools02 中未改动的 `reliability_v4_storage_budget.py`（SHA `e02424cc…b4aa`），六项参数齐备后串行执行。输出给出完整 280 槽预算、物理容量差额、临时预留及 `storage` canonical SHA；后续正式计划/manifest 的原守卫和逐槽容量检查仍须单独通过。

Windows 定向验证命令为 `python -B -m unittest tests.test_measure_reliability_v4_storage tests.test_measure_reliability_v4_storage_snapshot_audit`。首版为 29/29 通过，用时 417.593 秒；recovery02 兼容补丁完整重跑为 34/34 通过、无跳过，用时 328.371 秒；recovery03 兼容补丁完整重跑为 41/41 通过、无跳过，用时 311.353 秒。recovery03 增加七项测试，覆盖第三配对的完整 28 格预算兼容、原 FAIL 保留与禁止载荷读取，以及新旧交叉配对、未完成诊断、归一化 reader 失败、raw schema 漂移、原 report 变更、早于原生诊断的 registry 和未知 producer 的拒绝。旧版本 fixture 从当前源精确反向应用已审查修补，每一步核对完整旧 SHA；它们只是 synthetic 输入，不是重建的实际执行证据。

上述三次完整测试的原 stdout/stderr 仅存在于本会话工具输出，没有另存原始日志文件。这些 synthetic 结果不代表实际安全四场、扩展 16 或容量测量已完成；原生前置证据另由上述真实回执给出。
