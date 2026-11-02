# Humble54 的显式快照审计与 28 格大小测量

`tools/measure_reliability_v4_storage.py` 默认仍严格比较原计划与飞行快照，不接受额外历史副本。仅在显式提供下面四项参数时，才使用相邻的 `reliability_v4_storage_snapshot_audit.py`，依据原完整冷冻映射核对全部 scanner 源码及所选模型、DDS 的快照集合。原有额外副本、差异和导入证据限制均保留；未知、缺失、变化的项仍拒绝。

该选项要求原固定审计工具的实际原生合同/首三份快照验证回执，以及实际完成的安全四场 registry、逐场记录、facts、guard validation、summary 和 owner 终态。它检查这些保存证据的绑定关系，重查当前 scanner 文本 SHA 和模型 stat；不重跑原 `validate_contract` / `validate_snapshot` 或安全 validator，不重新读取模型内容。袋、遥测和 VHD 也只 stat。保存的原生验证不等于本次新做了一次原生验证。

执行顺序如下：

1. canonical core12 全部通过，原 core owner 结束且清理完成。
2. 在原生空闲窗口完成既定导入审计、durable dummy 与原固定工具的合同/快照联调，保留真实回执。工具准备、Windows fixture 或静态接口检查不能代替该回执。
3. 用原固定工具和合同前瞻登记安全四场，真实执行并完成四场 PASS、guard 与 owner 闭合。
4. 按公开 CLI 登记、执行同源 extension16，保存全部终态。大小测量保留原 FAIL 等状态；不因计入空间而授予 readiness。
5. 从独立外置工具树运行大小测量。保留整个相邻工具目录及其 imports，不把新版工具写入 frozen54 或后续冷构建完成的 final55。输出必须是实际 results 下独立、尚不存在的新目录。
6. 之后由原预算工具结合真实物理盘清单、增长假设和交付预留组装容量预算；正式准入及逐槽守卫继续独立执行。

下面使用预定的目录名；运行前须核实实际扩展计划、registry、原生回执和新输出位置。两个 SHA 从当前实际小文件获得，并与已审查绑定核对：

```bash
tracking_runtime=/root/uav_tracking_fullplan_v4_humble54
tracking_tools=/root/uav_tracking_storage_measure54_tools01
tracking_registry="$tracking_runtime/results/reliability_v4_humble54_safety01_audit/registry.json"
tracking_native=/mnt/d/WSL/UAVHumble22-validation/snapshot_audit_native_integration01/native_contract_integration01.json
tracking_registry_sha="$(sha256sum "$tracking_registry" | cut -d' ' -f1)"
tracking_native_sha="$(sha256sum "$tracking_native" | cut -d' ' -f1)"

bash "$tracking_runtime/scripts/run_research_session.sh" "$tracking_tools/tools/measure_reliability_v4_storage.py" \
  --core-development-plan "$tracking_runtime/results/reliability_v4_humble54_core12_probe01_matrix/plan.json" \
  --extension-development-plan "$tracking_runtime/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json" \
  --output "$tracking_runtime/results/full28_storage_measurement_audit01" \
  --snapshot-audit-registry "$tracking_registry" \
  --snapshot-audit-registry-sha256 "$tracking_registry_sha" \
  --snapshot-audit-native-receipt "$tracking_native" \
  --snapshot-audit-native-receipt-sha256 "$tracking_native_sha"
```

四项参数必须一起出现。收集器必须看到完整 12+16 格，保留原状态和分母，并在发布输出前复查小文件、scanner 集合、文本和模型 stat。每格及汇总新增 `source_snapshot_validation`，明确保存原生/安全证据、当前文本检查、模型未重读以及非准入边界。缺少真实前置证据时拒绝，不生成部分大小证据。

Windows 定向验证命令为 `python -B -m unittest tests.test_measure_reliability_v4_storage tests.test_measure_reliability_v4_storage_snapshot_audit`，本次 29/29 通过，用时 417.593 秒；含完整 28 格预算兼容、默认严格拒绝、载荷禁止读取、伪准备回执、快照变异和收尾 stat 变异。原 stdout/stderr 仅存在于本会话工具输出，没有另存原始日志文件。这些 synthetic 结果不代表实际原生前置审计、安全四场、扩展 16 或容量测量已完成。
