# Humble54 扩展首场原始终态最小归档

`person_extension_depth_noise_seed004` 原始工程终态为 **PASS / COMPLETED**，开始于 `2026-11-03T01:15:27.076989+00:00`，结束于 `01:38:26.893766 UTC`。`flight_exit_code=0`、`infrastructure_stop=false`，清理残留进程列表为空。这是一场开发种子 004 的独立结果，不能代替整个扩展 16 场或正式 280 次验收。

归档包含原始 START、原始终态及七份小型试验 JSON，均不超过 1 MiB；来源、字节数及 SHA256 见 [manifest.json](manifest.json)。七份试验文件逐一匹配原终态的 `artifact_hashes`；START 和终态另行核对文件字节哈希、任务 ID、计划摘要及开始时间。终态内部 `record_sha256` 已按原规范重新计算核验，它与终态文件本身的 SHA256 是两个不同值：

- 终态文件 SHA256：`1382341a973f05555ba8e13dc4213102f933f3ccc72c5f18439e2ae98dd2978b`。
- 终态内部记录摘要：`ce0fff0fd3b63ae2f90d6ddc2daf7fe79376bfc32781a5748b455ab06fa3c928`。
- 原计划文件 SHA256：`f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055`；内部计划摘要：`ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761`。计划只核对，不重复复制。

原终态的工程证据为：base_link 距离 RMSE **0.7579153021 m**、高度 RMSE **0.1619863085 m**、有效状态覆盖 **0.9162234043**、真值覆盖 **1.0**，距离和高度末端持续稳定检查均为 `true`。录包闭合、source-clock、native-startup、surface-flight 原报告通过；navigation 原报告状态仍为 **`RECORDED_WITH_CENSORED_FAILURES`**，其 `incomplete_reasons=[]`。工程 PASS 不会将 navigation 的删失状态改写为 PASS。

归档时另行读取的实时观察为北京时间 **09:44:07**：扩展批次 `RUNNING`，2 START、1 原始 PASS、14 未开始，活动槽为 `person_extension_depth_holes_seed004`。外部 waiter 在 **09:44:04** 仍为 `WAITING_FOR_EXTENSION`、`followon_launched=false`。这些时间快照只作派生观察，不能当作首场原始证据或整批终态；最新状态应查看[实时进度](../../../results/project_progress/humble54_extension16_run01/index.html)。

本次只归档指定的小型 JSON 原件，没有读取 bag、模型、telemetry 或大型 JSONL，没有重跑评价、启动新飞行或修改原始结果。正式研究仍为 **0/280**。
