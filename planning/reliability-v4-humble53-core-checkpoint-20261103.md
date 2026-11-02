# Humble53 核心 12 场：前四场检查点

截至 **2026-11-03 00:16（北京时间；UTC 为 2026-11-02 16:16）**，同源核心批次仍在执行：前四场均为原槽 `COMPLETED/PASS`，四个原 attempt 已完成审计且 `error=null`；第五场行人单目标主动云台已由 driver 开始，余七场待执行。正式实验仍为 **0/280**。本页是固定检查点，不代表后续实时结果。

| 场景（均为行人、开发 seed004） | 原工程结果 | 真实机体距离 RMSE（m） | 高度 RMSE（m） | 末段距离/高度稳定 |
| --- | --- | ---: | ---: | --- |
| 速度跟随 | PASS | 0.7636 | 0.1575 | 均通过 |
| 位置跟随 | PASS | 0.7749 | 0.1715 | 均通过 |
| 多目标交叉、指定个体 | PASS | 0.9238 | 0.1519 | 均通过 |
| 三阶段云台中位 | PASS | 0.7732 | 0.1630 | 均通过 |

四场的独立来源时钟及原生起飞评价均为 PASS；第四场的中位云台检查也为 PASS。第四场原槽于 2026-11-02 16:14:16.777348 UTC 完成，原 attempt 于 16:15:36.352804 UTC 闭合。其导航报告原标签仍为 `RECORDED_WITH_CENSORED_FAILURES`，前四场均保留这一全局标签和原有删失窗口；表中稳定结果只引用各自 `base_link` 末段持续稳定字段。工程原 PASS 与导航报告的完整标签分别保留，不重新裁决原结果。

第五场 `person_stage3_active_seed004` 的原 driver START 为 2026-11-02 16:16:12.814246 UTC。原 collector 快照在 16:16:33.673712 UTC 只识别 normal-slot START，当时仍记为 **4 PASS / 8 PENDING**；本检查点结合独立 driver START 描述为 **4 已完成、1 正在开始、7 待执行**，不改写原 JSON/CSV，也不预记第五场 PASS。后续本机状态见[核心槽进度](../results/project_progress/humble53_core_slots01/index.html)与[命令监控](../results/project_progress/humble53_core_run01/index.html)。

第三场的身份指标采用固定 10 Hz、首次明确选框 REQUEST 到最终记录 Clock 的完整时间格：**753 = 648 正确 + 0 已知错误 + 105 未知，已知覆盖率 86.0558%**。105 个未知由 **30 个外遮挡保护、72 个无新鲜被选目标检测、3 个确认/任务边界/末尾单元**构成。本场小报告未暴露缺 GT 或初始映射未知；这不表示其他场景没有这些问题。第一次任务覆盖率仅 67.70%，重选后的第二次为 99.77%，不能用总体覆盖率掩盖第一任务的空窗。未知不算正确，稳定 track ID、UUID、预测或悬停不能补作物理身份观测。细节见[实际 Humble53 身份未知证据卡](../tools/experiment_orchestration/humble53_core4_snapshot01/HUMBLE53_STAGE2_UNKNOWN_EVIDENCE_CARD01.md)。

本轮仍使用来源提交 `bcc012f8fe4c5139eda51f68a47a35396d417ee8`，本次更新仅保存文档和具名小文件证据。旧 Humble51 第四场的来源时钟/原生启动失败及 Humble52 原生测试超时均完整保留；较早 75 秒等价复验是独立的 1/1 结果，未并入本核心 12 场计数。本开发条件的前四场通过不能证明汽车、主动云台、其他种子或整体可靠性已经通过。

后续路线保持：完成本同源核心 12；安全 4；扩展 16；真实容量与 R0 定标；独立最终根构建及正式准入；正式 280 次重复、状态估计配对比较及身份/检测/恢复评价；最终交付。原失败、未知和删失继续保留。四场原槽、原 attempt、第四场评价、原 collector JSON/CSV 和第五场 driver START 的完整小文件见[证据快照](../tools/experiment_orchestration/humble53_core4_snapshot01/README.md)。
