# Humble22 诊断开发检查点（2026-10-30）

本页记录北京时间 2026-10-30 03:19 已有的小型执行证据，补充并覆盖旧状态页中“当前无仿真”“观察器尚未实际运行”等较早状态。它是开发检查点，不是三阶段完成报告，也不代表可靠性问题已解决。正式实验仍为 **0/280**；验收数值候选尚未登记。

## 本轮代码与验证

新增独立本机进度监控、独立 Linux 资源/ROS 接收观察器、监管节点回调诊断和失败时间线导出。监管诊断记录原始/接受/拒绝状态计数、拒绝原因、源时与接收时、已完成回调间隙和当前静默年龄，不改变状态接受规则或飞行保护门限。其稳态时钟定时器仍由监管节点同一个 executor 调度，executor 阻塞也会延迟诊断，因此不能替代独立观察器。

行人三个阶段的速度指令加速度限值候选改为 `[0.7, 0.7, 0.5] m/s²`，位置参考继续使用 `[3.0, 3.0, 3.0] m/s²`。该候选旨在降低追赶和显式重选时的指令突变，尚未取得完整闭环任务收益证据。

Humble22 冻结源清单含 **540 个文件**，canonical SHA-256 为 `6c88ff6e297611666af1d17d95da202b837db0ddf9aa4323b8649b690e81bce3`。四个 ROS 包构建通过，模块/ament 来源隔离、实际消息序列化及系统 FastCDR 来源核验通过。Linux 全套运行 **1329 项，1327 通过、2 项跳过，44.58 秒**；源码前后未变。该清单绑定本地实际运行源，包含不上传的运行环境清单，不能将其等同 Git 提交树哈希。

真实 ROS 冒烟检查已完成：独立观察器运行约 5 秒并保存 5 个采样，接收线程无错误、写队列无丢弃或写入错误；另实际收到 3 条监管诊断，节点保持 `DISABLED`，没有伪造 PX4 状态。此检查没有启动飞行或 PX4，也没有实际 Clock/VehicleStatus 流，证明范围仅为观察与诊断工具的运行。

## 汽车具名诊断执行

`reliability_v4_humble22_diagnostic_car_clean_seed000` 于 UTC 2026-10-29 19:17:32 至 19:19:13 执行，外层监控于北京时间 2026-10-30 03:19:15 记录命令结束。运行器和独立观察器退出码均为 0，观察器没有被强制停止；执行前后均核对 540 个源文件，绑定上述同一 canonical SHA。请求为 20 秒无遮挡跟随、唯一实例、汽车、中位云台、速度模式、开发种子 0，未消费正式留出种子。

原始摘要记录起飞、Offboard 和跟随，终止原因为 `follow_duration_reached`，`basic_flight_passed=true`，同时明确 `offline_evaluation_required=true`。这只表示基础执行完成；距离/高度持续稳定、导航有效覆盖、身份、安全及完整工程结论须依独立评价另行报告。它不能替代完整遮挡任务、12 核心格、4 安全格、16 扩展格或正式重复统计。

本机 [进度页](../results/project_progress/current/index.html) 随后续具名命令更新。其 `COMPLETED` 只表示当前受监命令结束，不表示项目完成；当前任务 ID、时间、真实退出码和心跳需一并查看。使用方法见 [进度监控说明](PROJECT_PROGRESS_MONITOR.md) 与 [资源/ROS 观察器说明](RUNTIME_HEALTH_OBSERVER.md)。

## 原身份 UNKNOWN 审计

本轮只读分解 Humble21 原两条行人记录，保留首次 REQUEST 到完整记录 Clock 尾段的固定 10 Hz 分母和原结论：

| 开发场景 | 全任务 correct / wrong / unknown | 可确认正确比例下界 | UNKNOWN 主要细分 |
| --- | --- | --- | --- |
| stage2 crossing | 359 / 0 / 111，共 470 格 | 76.38% | 无新鲜所选轨迹框 70；遮挡保护区/未排除遮挡 31；待确认 2；无身份证据 4；投影裁边或未核实范围 4 |
| stage3 multi active | 352 / 0 / 108，共 460 格 | 76.52% | 无新鲜所选轨迹框 71；遮挡保护区/未排除遮挡 30；待确认 3；无身份证据 4 |

“无新鲜所选轨迹框”不能证明检测器漏检、目标不可见或管理器已 LOST；遮挡保护区也不是精确渲染遮挡时长。`wrong=0` 不能解释为全任务身份保持 100%。本轮没有修改原评价器、保护门或分母，详见本机 [UNKNOWN 审计摘要](../results/development_20261030/identity_unknown_audit01/summary.md)。

## 证据与下一步

本机原始证据位于被 Git 忽略的 `results/`，以下链接用于本地核查，GitHub 不包含这些运行工件、录包或权重：

- [构建与完整测试汇总](../results/frozen_fullplan_v4_humble22/freeze_validation/build_validation_summary.json)
- [冻结源清单](../results/frozen_fullplan_v4_humble22/freeze_validation/source_freeze_manifest.json)
- [真实 ROS 监管诊断冒烟结果](../results/development_20261030/observer_smoke01/supervisor_ros_smoke.json)
- [独立观察器 5 秒采样](../results/development_20261030/observer_smoke01/health.jsonl)
- [汽车诊断执行与前后源绑定](../results/frozen_fullplan_v4_humble22/reliability_v4_humble22_diagnostic_car_clean_seed000_observer/diagnostic_execution.json)
- [汽车原始执行摘要](../results/frozen_fullplan_v4_humble22/reliability_v4_humble22_diagnostic_car_clean_seed000/summary.json)

接下来先分析本次独立观察器、监管诊断和汽车离线评价，定位状态超时与导航失效，再验证行人控制候选、完整遮挡/重选、多目标及云台。后续开发关口、前瞻登记、容量核算、正式重复和材料交付依 [12 项工作计划](../planning/reliability-v4-next-actions-20261030.md) 推进；[验收候选](../planning/reliability-v4-acceptance-candidate-20261030.md) 继续保持未登记，历史失败、待验收和未知均保留。
