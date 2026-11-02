# 冻结源码快照的显式审计兼容

Humble54 的实际飞行快照扫描包含 17 个原已冻结的历史 `build/lib` 副本，其中 8 个与 canonical 源码内容不同。它们全部匹配原完整冻结映射；原注册源码没有缺失或变更。原 frozen54 guard 的严格集合比较仍会拒绝这份额外项，不能把衍生审计通过冒称为原 guard 通过，也不能删除快照中的额外项。

当前工作区新增 `tools/reliability_v4_snapshot_audit.py`，guard 默认精确匹配保持。显式 contract 才允许使用独立审计根；它核对真实计划、原冻结报告及三份完整映射、全部当前注册源、原 scanner 的完整结果、原导入隔离收据和实际工具字节。未知、缺失、变化的源以及路径逃逸均拒绝，历史副本差异写入结果。原导入收据没有记录每个进程具体模块路径，该限制保留。

最终 Windows 定向回归为 90 项：89 通过、1 项既有平台跳过；独立源码与元数据复核通过。原日志、收据、源码 SHA 和验证边界见 [测试快照](../tools/diagnostics/snapshot_audit54_validation01/README.md)。尚未运行真实 Humble54 原件消费或 native 双根联调。

后续实际接线必须按这个顺序执行：

1. 将最终四个审计工具（guard、driver、helper、原样 registrar）及包标记封存到专用、不可变的 native 审计根，记录源和目标 SHA。算法运行根仍独立保留。
2. 在当前完整核心批次结束后的原生空闲窗口，验证八个具体模块的当前真实导入来源、审计工具实际路径和原件读取；这不能追认历史进程现场。
3. 只有实际 canonical12 全部 PASS 且 owner 真正结束后，使用该固定工具根的 helper 创建新 contract；同根 driver 前瞻登记并执行安全四场。保留原报告和完整快照。
4. 用同一工具根的 registrar 发布最终 seal，`manifest.tool` 始终绑定同一真实 guard 绝对路径和 SHA。不能安全试验后改指 final 算法根中的 guard 副本。
5. 原 formal48 adapter 静态检查显示会加载真实 `manifest.tool`；实际双根接线仍须原生验证。继续使用原正式逐槽守卫及全部时钟、身份、控制和清理门槛。

正式长批次另需验收 durable native dummy 与真实启动接线。三组执行工具的原字节快照及当前验证边界见 [执行工具快照](../tools/experiment_orchestration/formal54_execution_tools01/README.md)。这些工具验证不计入正式 280 场实验。
