# Humble53 核心前四场小文件快照

检查点为 **2026-11-03 00:16 北京时间（2026-11-02 16:16 UTC）**：四个行人场景的原始工程结果均为 PASS，原 attempt 审计均已闭合；第五场行人主动云台已有 driver START，余七场待执行，正式 **0/280**。表格和边界见[本轮检查点](../../../planning/reliability-v4-humble53-core-checkpoint-20261103.md)。本固定快照不代表后续运行状态。

目录中 `slot_01`—`slot_04` 是四个原槽完整记录，`attempt_01`—`attempt_04` 是四个原 attempt 完整终态。第四场的 `px4_source_clock_report.json`、`native_startup_report.json`、`gimbal_evaluation.json` 与 `navigation_reference_evaluation.json` 均保留原件；导航的 `RECORDED_WITH_CENSORED_FAILURES` 和原有删失窗口未改写。`driver_start_05.json` 保存第五场的原 driver START，不能当作飞行完成或通过。

`core12_summary.json` 与 `core12_summary.csv` 原样复制自 2026-11-02 16:16:33.673712 UTC 的按需 collector 快照。它当时只按 normal-slot START 记状态，原计数为 **4 PASS / 8 PENDING**；结合更早 16:16:12.814246 UTC 的第五场 driver START，可说明四场完成、第五场编排已开始、余七场待执行。没有为了统一口径而修改原 summary。collector 的 `attempt_audit_bound` 仅表示 record 内容结构绑定，不能替代原 native attempt 的完整审计；本目录另存了实际原 attempt 终态。

`HUMBLE53_STAGE2_UNKNOWN_EVIDENCE_CARD01.md` 是实际第三场身份未知分析卡：固定时间格 **753 = 648 正确 + 0 已知错误 + 105 未知**，覆盖 86.0558%；未知为 30 个遮挡保护、72 个无新鲜检测和 3 个边界单元。首次任务仅 67.70% 覆盖。卡片所核原身份/安全报告未见缺 GT 或初始映射未知，结论仅限本场。原大身份报告未复制进本目录，其来源与 SHA 由卡片明确保留；不能把这张卡片当作已附全部原分析输入。

`snapshot_manifest.json` 为每件完整复制文件列出实际来源、大小及 SHA-256。复制时仅核这些具名小文件；没有读取 bag、视频、遥测数据，也没有重跑评价、测试或仿真。所有原路径字段和 schema 保留，Git `-text` 规则保持原字节。旧 Humble51 失败、Humble52 超时和单场等价复验均独立保留，未混入本批。源码、算法、门限及原工程结论未改动。
