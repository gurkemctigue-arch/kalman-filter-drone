# Humble54 核心 12 场实际墙钟统计

本报告只统计已经闭合的 Humble54 核心开发 12 场：行人与汽车各 6 场，均为 seed004。原始槽均记录 PASS、`infrastructure_stop=false`、清理残留列表为空；这是原记录的描述，不是重新执行飞行或验收。主派生结果为 `core12_wall_timing.json`，包含各原件路径、字节数、SHA-256、原始时间字段及统计。

**Owner 调用单调计时均值为 19.036 分钟，中位数 18.721 分钟，范围 17.611–21.817 分钟；12 场合计 228.430 分钟。** 槽自身 UTC 跨度均值为 18.746 分钟，中位数 18.406 分钟，范围 17.525–21.256 分钟。

| 原槽（均为 seed004） | Owner 调用单调计时／分钟 | 原槽 UTC 跨度／分钟 |
| --- | ---: | ---: |
| person_stage1_velocity | 17.651 | 17.600 |
| person_stage1_position | 17.611 | 17.525 |
| person_stage2_crossing | 18.941 | 18.809 |
| person_stage3_midpoint | 18.528 | 18.365 |
| person_stage3_active | 18.335 | 18.106 |
| person_stage3_multi_active | 20.681 | 20.411 |
| car_stage1_velocity | 18.096 | 17.785 |
| car_stage1_position | 18.427 | 18.070 |
| car_stage2_crossing | 20.104 | 19.699 |
| car_stage3_midpoint | 19.322 | 18.875 |
| car_stage3_active | 18.914 | 18.446 |
| car_stage3_multi_active | 21.817 | 21.256 |

两个口径的端点不同：

- Owner 调用计时使用同一原进程中明确记录的 `slot_invocation_started` → `slot_invocation_returned` 单调时钟差。对应源代码在 `run_plan` 调用前记录开始，在调用返回、读取并监控原槽清单后记录结束；包含本次 normal runner 的准备、飞行、归档、评价和返回后的清单处理，排除随后 owner 的策略核验。12 对端点均唯一，返回记录只改变对应一个原槽。
- 原槽 UTC 跨度使用该槽终态自身的 `started_utc` → `finished_utc`。原槽终态没有配套单调起止字段，所以不将这个 UTC 跨度改称同一个单调计时值。JSON 还单列了 Owner 同端点的 UTC 差，便于核对。

原 owner 在 UTC 2026-11-02 19:40:14 至 23:28:42 运行。明确的 `owner_started` → `owner_terminal` 事件单调跨度为 13,707.957936417 秒。结束端点使用终态事件，未用最后一次 heartbeat 替代。计划中的 75 秒是来源／仿真跟随时长，未用作墙钟耗时，也未按 RTF 换算。

为控制证据体积，仅保留原 owner 终态、与原 owner 绑定 SHA 一致的 batch 源码，以及具名 610,225 字节 owner events 中 **39 条非 heartbeat 原始行**。该 events 在确认不超过 1 MiB 后读取一次；`owner_event_source_pin.json` 记录完整源 SHA、提取行号和原始行 SHA。完整计划与 12 份槽终态只做小文件读取及哈希，原件仍在 JSON 记录的路径和[既有核心证据归档](../../experiment_orchestration/humble54_core12_closed01/README.md)，没有重复复制整套报告。

本批只有一个开发种子，不包含扩展 16 场、安全批次、正式重复研究或其他硬件条件。这里不外推完整 28 工况吞吐、280 次耗时或完成日期。未读取 bag、大遥测、图像或模型，未运行 WSL、原生程序或评价器；未修改项目状态顶部或提交 Git。
