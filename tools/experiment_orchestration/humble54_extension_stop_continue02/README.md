# Humble54 扩展第三槽停止与原计划逐槽继续

这是原始小证据的独立字节归档，不是新的开发门、成功批次或正式准入。`manifest.json` 逐项记录 13 份原件的实际来源路径、字节数和 SHA-256；其中 7 份 dropout 试验 JSON 已与原 terminal 的 `artifact_hashes` 比较，原 terminal 的内部 `record_sha256` 也已按原规范复算一致。两个 START 的命令均与同一原计划匹配。原文件没有改写，未复制其他目录、录包、遥测、权重或逐帧 sidecar。

原 extension owner 于 2026-11-03 02:17:27 UTC 停止，保留 **2 PASS、1 INCOMPLETE_EVIDENCE、13 PENDING**。第三槽 `person_extension_dropout_seed004` 已完成飞行：`execution_status=COMPLETED`、`flight_exit_code=0`、`infrastructure_stop=false`，并非一次未完成飞行或基础设施故障；其工程证据不足和原停止结果均原样保留。旧 waiter 实际读到原 monitor 与 WSL 均退出 2，故记录 `STOPPED_REFUSED_NO_RETRY`、`followon_launched=false`；没有启动先前准备的 native follow-on。

父任务随后通过归档的 `run_humble54_pending_latency01.sh`，调用不变的 normal runner `run --plan 原计划 --max-new-trials 1`，执行原计划下一条尚未尝试的 `person_extension_latency_seed004`。其真实 START 为 **2026-11-03 02:25:24.728624 UTC**。归档前旁读的原 monitor 保存状态在 02:35:20 UTC 仍显示该命令运行中；归档时该槽尚无 terminal，因此本归档不包含或预言它的结果。START 是尝试证据，当前进程存活仍应查看实际 monitor，不能只凭标记判断。

“13 PENDING”指旧 owner 停止时的清单：其中 latency 此后已 START，其余 12 条当时尚未 START；latency 不计作 PASS。此次是**同一原计划剩余槽的数据采集继续**，没有重试 dropout、替换种子、拼接另一个计划，也没有把旧 owner 改成 COMPLETED。后续每次仍须检查原终态和 source/native 安全证据；本目录不声称其余 12 条已经执行。完整 75 秒、退出零且无基础设施停止的原 INCOMPLETE 录制可以用于容量核算，这不赋予工程 readiness。正式试验仍为 **0/280**。

第三槽短挡板请求窗口为 31.30–31.58 秒，报告记录窗内诊断帧数为 0，因此 `detector_interruption_observed=null`。其预测、短时未进入 LOST、同 ID 恢复检查为真；长遮挡检查通过。注入器按源时间的 200 毫秒整窗同时丢弃 RGB 和 Depth。依据原 seed 4、drop fraction 0.1 和未变的 SHA-256 掩码公式，窗口 `[31.2,31.4)`、`[31.4,31.6)` 均被丢弃，完整覆盖此次短挡板窗口。没有输入图像时，无法要求 detector 产生“处理了图像但没有候选框”的诊断；这说明整帧 dropout 与视觉遮挡观测要求发生了叠加混淆。

上述因果解释没有补出缺失的视觉证据：本次未读取 bag 或查看窗内原图，不能把“按规则应丢帧”或“有预测状态”等同“已经独立看到物理遮挡”，更不能将原 null 改成 PASS。需要后续独立核对已录制的上游 raw 图像、下游 fault 流与对应时间证据，并保留原评价结果；科学适用性与正式准入的接线仍未补齐。当前 extension gate 仍会拒绝这项原未知证据，不能用容量统计或新的数据采集命令替代它。

本次没有修改共享评价器。`evaluate_*` 源码属于 runner 的离线映射，单独修改它不会改变 `flight_source_hashes`；但共享 stage1 evaluator 的变化会影响 source-clock/native/navigation 等报告的 helper provenance，且现有 extension 接口不支持该类离线 override。这些限制不能通过改旧哈希或隐去原失败来绕过。已完成的 core12 与 safety03 原证据继续保留。

此归档只做具名小文件读取、复制和哈希核验，没有运行 WSL、仿真、测试、评价器或 Git 提交。`manifest.json` 中的检查是字节与来源核对，不是新的实验结果。
