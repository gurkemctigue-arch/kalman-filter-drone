# 阶段二汽车交叉 seed000：已保存报告的独立核对

对象：`fullplan_v3_stage23_s2_car_crossing_locked_seed000`。
本次只读取已保存的小型 JSON 及相关评价规则，没有读取 bag、telemetry、图像或视频，也未运行仿真、测试或重新评价。

结论：该次属于**已有可读评分的 FAIL**，原报告独立保留了“轨迹快照时间校验失败”和“末尾持续跟踪失败”两项负面证据。不能将二者直接解释为同一根因或因果链。

## 快照检查为什么是 false

原 [stage2_evaluation.json](../results/frozen_fullplan_v3/fullplan_v3_stage23_s2_car_crossing_locked_seed000/stage2_evaluation.json) 保存：

- `tracks_snapshot_count=1780`，即通过当前校验并被接受的快照数。
- `tracks_snapshot_errors` 只有一项：`time_s=46.028`，`reason="snapshot has no valid receive time"`。
- 因此 `all_tracks_snapshots_present_and_valid=false` 并不是“完全没有快照”，而是至少一条快照没有通过要求。

冻结的 `scripts/evaluate_stage2_flight.py` 第 156–157 行在下列任一条件下生成这个相同错误：

```python
row.received_sim_s is None or output > row.received_sim_s + .05
```

即：没有有效接收仿真时间，或快照声明的输出时间比接收时钟领先超过 50 ms。该错误项未保存 `received_sim_s`、`output_s`、`acquisition_s`、原始快照内容或记录顺序号，因此**只凭现有报告无法区分这两个分支**，更不能断定是缺少时钟、发布器时间戳错误、时钟采样滞后或评价规则有问题。

相关冻结评价器 SHA-256 为 `a1a705f4d45c6cd2eb8597368a9bf4eb2f1d4a6e0fe9e937ba97e769fc16159e`，与该次试验 `configuration/source_sha256.json` 中归档的值一致。

## 持续跟踪失败的独立证据

这次只有一次初始选框：17.400 s 请求，17.532 s 确认，选中的 track ID 为 2。末尾持续评价窗口为约 **55.564–60.760 s**：

| 保存字段 | 值及含义 |
|---|---|
| `state_count` / `state_counts` | 121 条，全部 `LOST` |
| `lifecycle_counts` | 45 条 `HOVER` |
| `tracking_control_count` | 0 |
| `control_span_s` | null，没有可计算的有效跟踪控制跨度 |
| `last_state_measurement_age_at_trial_end_s` | 26.6599998474 s |
| `maximum_state_evidence_gap_s` | 约 2.98 s |
| `maximum_control_evidence_gap_s` | 3.00 s |
| `first_uuid_mismatch_s` | null，不能因此认定物理身份始终正确 |

`same_target_active_states_only`、`continuous_state_evidence`、`continuous_control_evidence`、`fresh_state_at_trial_end`、`tracking_control_at_trial_end` 均为 false；`minimum_control_span` 和 `tracking_control_only_after_grace` 为 null。原报告据此给出 `sustained_tracking.result=FAIL` 和 `final_sustained_tracking=false`。

这里 `sustained_tracking.confirmation_time_s=55.564` 是末尾评价窗口的起点，**不是第二次选框确认**。原始选框确认仍是 17.532 s，报告 `selection_count=1`。轨迹消息持续存在也不能代替有效跟踪：末尾状态全部是 LOST，最后一条消息时间接近录制结束，与最后有效测量已过期并不矛盾。

`active_states_remain_fresh=true` 只约束有效活动状态的测量新鲜度，不能证明整个任务持续活动；本次尾部全部 LOST，因此与持续跟踪失败不冲突。本次没有读取完整时序，未确定最早丢失时刻、丢失机制或快照错误与丢失之间的先后因果关系。

## 为什么保留为评分失败

- 原始输入解码没有错误：`read_errors={}`、`unavailable_types={}`，`clock_recorded=true`，读到 13,274 条时钟，尾部覆盖为 true。
- 起飞/Offboard 与初始选框确认检查通过；监控为 `follow_duration_reached`，监控返回码 0。
- bag 进程返回码为 0；此信息与解码结果共同说明本次不同于阶段一 seed08 的不可读取记录，但单独的 bag 返回码不是完整性证明。
- 原生评价器正常生成 FAIL 报告，评价返回码 **2**。这里 2 是已有评分的负面结果，不能一概按“非零返回码”归为基础设施异常。
- manifest 的 `infrastructure_failure.stop=false`，原正式 FAIL 保留。

本场景 `require_occlusions=false`、`require_ambiguity=false`，报告也没有实际遮挡事件或歧义窗口。相关可选检查的 true 不能用于声称已经演示遮挡/歧义处理。物理身份评价明确为 `evaluated=false`；报告不认证 IDF1、HOTA、mAP 或三维精度。

## 独立产物

[独立 JSON](../results/stage2_car_crossing_seed000_saved_report_audit/failure_taxonomy.json) 与 [摘要](../results/stage2_car_crossing_seed000_saved_report_audit/failure_taxonomy.md) 标记为 `SELECTED_TRIALS_SNAPSHOT`、`is_final166=false`，只包含这一条记录。原计划和 stage23 manifest 在采集前后指纹相同；原正式记录未修改。

原报告 SHA-256：`461d79fe6416e61859f83a4cabe19161913c05b88d877772a8f8b45142f3eaf3`。

