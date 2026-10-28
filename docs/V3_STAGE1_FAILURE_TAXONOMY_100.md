# v3 阶段一：100 次正式试验的逐项失败分类

日期：2026-10-27。统计对象是冻结的 80 次 velocity 试验与 20 次 position 兼容性试验，包含所有原台账 FAIL；没有重跑飞行或评价，也没有调整原台账。当前分类为 **66 次评分通过、33 次已完成评分的行为验收失败、1 次已确认基础设施异常、0 次证据不足而无法分类**。

原台账仍是 66 PASS / 34 FAIL。基础设施异常没有从完整 100 次的分母中移除，未被改判 PASS。这里“已分类”只说明结果和证据状态已经区分，不表示 33 次行为失败的深层根因均已查明。

## 分类规则与证据范围

- `SCORED_PASS`：原台账 PASS、顶层验收通过、原离线评价 PASS、评价返回码 0，且离线 JSON 可读、记录时钟存在、无读取/类型缺失错误、覆盖录制尾部。
- `SCORED_FAIL`：原台账 FAIL、顶层验收不通过、原离线评价 FAIL，并满足上述可评分证据条件。
- `CONFIRMED_INFRASTRUCTURE_FAILURE`：本次只对已经独立复现读取异常的汽车 position seed08 使用。它没有原始离线评价 JSON，不能将其归为已评分的跟踪失败。
- `INCOMPLETE_OR_UNKNOWN`：上述证据不充分或彼此矛盾的记录。本次为 0；没有把缺失值当成通过或零误差。

只读取了两个小型汇总 JSON、每次试验的 `summary.json`、`process_exit_codes.json`、现有 `offline_evaluation.json`，以及非零评价返回码对应的小型错误日志。单次 JSON 上限为 512 KiB，汇总上限为 2 MiB，错误日志上限为 64 KiB。本次未打开 bag、telemetry、图像或视频，也没有执行仿真、测试、构建、YOLO、完整评价或全 bag 哈希。

逐项证据、检查原值及小型来源 SHA 见：

- [机器结果与完整字段可用性](../results/stage1_failure_taxonomy_v3_100/failure_taxonomy.json)
- [100 次逐项分类表](../results/stage1_failure_taxonomy_v3_100/failure_taxonomy.md)
- [生成脚本](../scripts/summarize_stage1_failure_taxonomy.py)

## 分组结果

| 类别 / 控制 / 估计器 | 总数 | 评分通过 | 行为验收失败 | 基础设施异常 |
|---|---:|---:|---:|---:|
| 行人 / velocity / raw | 10 | 10 | 0 | 0 |
| 行人 / velocity / EMA | 10 | 10 | 0 | 0 |
| 行人 / velocity / fixed KF | 10 | 9 | 1 | 0 |
| 行人 / velocity / adaptive KF | 10 | 10 | 0 | 0 |
| 汽车 / velocity / raw | 10 | 3 | 7 | 0 |
| 汽车 / velocity / EMA | 10 | 3 | 7 | 0 |
| 汽车 / velocity / fixed KF | 10 | 3 | 7 | 0 |
| 汽车 / velocity / adaptive KF | 10 | 3 | 7 | 0 |
| 行人 / position / adaptive KF | 10 | 9 | 1 | 0 |
| 汽车 / position / adaptive KF | 10 | 6 | 3 | 1 |
| 合计 | 100 | 66 | 33 | 1 |

汽车各 velocity 方法的 3/10 只描述各自完成的端到端验收结果，不能据此宣称任一滤波方法提高了正式跟随通过率；通过种子、轨迹以及置信区间等比较仍应以原始配对研究报告为准。

## 33 次行为失败实际未通过哪些检查

顶层检查中，`offline_occlusion` 未通过 33 次，`long_occlusion_braking_from_motion` 未通过 32 次，`sustained_tracking_after_reselection` 未通过 18 次。检查有重叠，不能相加为失败试验总数。

直接按每次原离线 JSON 中的事件检查组合，可将 33 次行为失败分成下列互不重叠的观测组：

| 已记录的失败检查组合 | 次数 |
|---|---:|
| 短遮挡期间连续性失败；重选后持续跟踪通过 | 15 |
| 短遮挡期间连续性失败；重选后持续跟踪也失败 | 16 |
| 短遮挡连续性通过；长遮挡悬停后的持续低速检查失败；重选后持续跟踪失败 | 1 |
| 短遮挡连续性及长遮挡运动制动检查通过；重选后持续跟踪失败 | 1 |
| 合计 | 33 |

因此，不能将全部行为失败统一解释为短遮挡后锁止。最后两组对应：

- `fullplan_v3_online_estimators_car_velocity_fixed_kf_seed02`：短遮挡检查通过，长事件 `sustained_low_speed_after_hover=false`，重选后 `continuous_state_evidence=false`、`continuous_control_evidence=false`。这只是已失败检查的定位，本次没有检查该次完整时序或确定控制/融合根因。
- `fullplan_v3_position_compatibility_person_position_adaptive_kf_seed07`：短遮挡检查通过、长事件 `braking_from_motion_demonstrated=true`，但重选后持续跟踪失败，包括控制跨度、尾部新鲜度及连续性等检查。本次不把它归因于先前代表样本中的融合拒绝路径。

31 次短遮挡连续性失败的试验，其长事件 `prediction_observed` 也为 false。这里只报告两个字段在相同试验中的共同出现；评价窗口内的第一个 LOST/HOVER 时间等于事件开始时间，不能单靠该字段证明事件前状态，或把每个后续失败解释为独立因果故障。

先前 [代表性遥测诊断](V3_FAILURE_DIAGNOSIS_DRAFT.md)深入检查的时效边界及融合拒绝路径，仍仅适用于其中明确列出的记录。本次没有将代表样本的机制扩展成 33 次失败的共同根因。

## 数据可用性与评价边界

| 证据 | 可用/通过 | 缺失/不适用 |
|---|---:|---:|
| 可读监控摘要与进程退出 JSON | 100 | 0 |
| 可读原离线评价 JSON | 99 | 1（seed08） |
| 原评价返回码为 0 | 99 | 1 次非零 |
| 录制时钟存在、无读取错误、无未知类型、覆盖记录尾部 | 99 | 1 次不可评分 |
| 短/长遮挡服务执行、设定值字段互斥、显式重选等顶层检查 | 99 次均为 true | seed08 无对应原评分 |
| 在线状态精度评价 | 0 | 100 次均 `EXPLICITLY_SKIPPED` |

99 份原离线评价中，短事件“无丢失”通过 68 次、失败 31 次；长事件悬停与禁止自动恢复检查均通过 99 次，悬停后持续低速检查通过 98 次、失败 1 次；重选后持续跟踪通过 81 次、失败 18 次。

这些分别衡量不同性质的行为。安全悬停与没有自动恢复不能代替有效跟随；短事件 `identity_preserved_on_observed_recovery=true` 的 68 次只表示对应评价中的观测身份一致，不证明多目标物理身份保持。所有 100 次在线状态精度评价明确跳过，不能写成零误差、完备精度证据或精度提升结果。

## seed08 基础设施异常的处理

原台账的 `infrastructure_failure.stop=false`、理由列表为空，现状被完整保留。独立分类使用另一次已经完成的外部审计，而不是改写原字段：原生读取器在新建 D 盘副本中重现 SQLite error 11；独立增量解码得到通过 SQLite 完整性检查、消息数与元数据一致的完整数据库；原生解压结果缺少其末尾 128 KiB。

详见 [压缩记录审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)。没有替换 bag、补写正式 `offline_evaluation.json`、重跑该槽位或把它改判为成功。压缩帧为何未正常结束仍未确定。

## 后续总报告的使用方式

此报告固定为阶段一的 100 次正式终止记录子集，后续完整 166 次报告可以引用它并独立纳入阶段二、三的新记录；不能将 100 次的计数直接当作 166 次的结果，也不能用新的工程探针覆盖这里的正式失败。

两个原汇总在分类前后的 SHA 完全相同：

- 80 次 velocity：`9f0413f4aff67a87e7bd92c408337f7090cac5ac3c13eaf8aba762e61e2479e9`
- 20 次 position：`ef893fe2c6c583c36b9310f4b7b6efca2f9cf77e4d4b33e2753ff647258f1470`

生成结果通过了 100 行计数、名称唯一性、分类计数守恒及原台账前后指纹检查。没有更改正式台账、分类器、安全门控、补充实验源码或其他代理正在维护的代码。
