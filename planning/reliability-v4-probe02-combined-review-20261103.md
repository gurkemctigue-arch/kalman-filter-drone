# probe02 第 5 场 combined 小报告复核（2026-11-03）

对象：`person_extension_combined_seed004`。本次仅读取已完成试验的小报告、终态及配置；未读 telemetry/bag，未启动 WSL、重推理或改判。

**原件与结论**

- 原终态：`results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/slots/person_extension_combined_seed004.json`。
- 终态 SHA256：`f57d22dff4989c8bbb45b56ba2151d66e52b5689984cd0a0104f531d4749b655`。
- `execution_status=COMPLETED`、`flight_exit_code=0`，工程结果仍为 **FAIL**；唯一负面评价器为 `surface_flight`，`pending=[]`、`incomplete=[]`。
- `infrastructure_stop=false`，残留进程为空。不能把正常结束或保护行为通过解释为整个系统验收通过。
- 下列报告位于 `results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_person_extension_combined_seed004/`。
- `flight_evaluation.json` SHA256：`cac220667d127c797f3034e85fd0e6ccafbe5a68942051222e2be3b95efa3faa`。
- `navigation_reference_evaluation.json` SHA256：`df41e1061172cc8ad9de4b0d97250246670b075340197e8fc5c7d235873e66f9`。

**遮挡与保护行为**

| 项目 | 已记录证据 |
| --- | --- |
| 短遮挡 | 29.800–30.080 s，事件 PASS；3/3 固定 10 Hz 预测样本有效，预测位置 RMSE 0.227208 m |
| 长遮挡 | 42.800–45.880 s；关闭/打开服务均成功，关闭 ACK 42.820 s、打开 ACK 45.900 s |
| 长窗检测中断 | 16/16 检测诊断帧无候选，0 帧有效深度 |
| 长窗预测检查 | `first_predicted_s=null`、`prediction_observed=false`，原事件 FAIL 保留 |
| 窗口内 LOST/HOVER | `first_lost_s=42.816`、`first_hover_s=42.852`；两项检查均通过 |
| 低速保护 | 长遮挡开始速度约 0.012529 m/s、进入 HOVER 约 0.012609 m/s；持续低速通过 |
| 恢复约束 | 禁止自动恢复、显式重选前禁止跟踪控制两项通过 |
| 显式重选 | 请求 49.800 s、确认 49.844 s，随后 43.088 s 持续跟踪检查通过 |

遮挡时间是请求窗口，服务 ACK 佐证执行；不能当作精确渲染遮挡边界。由于长窗开始已接近静止，`braking_from_motion_demonstrated=false`，本场不构成运动中刹停证据。

**长遮挡之前是否已经丢失**

`flight_evaluation.json.estimator.state_duration_s` 为 MEASURED 6.052 s、PREDICTED 54.096 s、LOST 14.984 s；三者合计 **75.132 s**，对应 FOLLOW 评价窗口 **17.800–92.932 s**。这是离线评价字段，不能拿包含启动过程的 `summary.json` 状态计数推导时间顺序。

49.844 s 确认重选后持续跟踪检查通过；42.800–49.844 s 最多容纳 7.044 s。因此聚合时长表明约至少 7.940 s LOST 位于长遮挡之前。该推论不能给出首次 LOST 的时间，也不能证明紧邻 42.800 s 之前仍为 LOST；窗口内的 `first_lost_s=42.816` 不能解释为全场首次丢失。

**距离和高度指标口径**

- 主距离 RMSE **2.221946489 m** 来自 navigation 报告 `whole_interval.metrics.base_link_distance_error_m`：17.800–92.932 s、固定 10 Hz、752 个样本，独立真值覆盖率 100%，保留 150 个非跟踪控制样本。
- KF 有效状态为 602/752（80.053%），LOST 为 150/752；这是导航可用性，不能当作身份覆盖率或算法成功率。
- 49.800 s 重选窗口初始距离误差为 6.510401 m；重选后 6.300 s，即约 56.100 s 起，距离持续入带至结束。
- 同口径 base_link 高度 RMSE 为 0.166444 m；重选后约 0.100 s 起持续入带。
- flight 报告的模型原点、密集真值全窗距离 RMSE 为 2.225739 m；其 FOLLOW/PREDICT 子集为 1.684294 m。二者口径不同，不能用子集替换主全窗结果或删除丢失尾部。

**证据边界与后续待核**

- flight 缺失 topic 为空、输入读取错误为 0；navigation `incomplete_reasons=[]`、`malformed_input_counts={}`。本场 FAIL 由明确检查失败触发。
- 当前为单一目标真值映射；`physical_identity_sha256=null`，不能据此宣称已完成指定个体的独立物理身份验证。
- recorded combined 故障为深度噪声 0.05 m、空洞 20%、丢帧 10%、延迟 0.08 s；关联为 legacy，预测上限 0.75 s。配置本身不能证明哪项导致先前丢失。
- 后续仅需原生窄窗 **30–43 s**：提取状态/控制转变、末次接受观测、轨迹关联与拒绝原因、观测 header 与接收仿真时间，确认首次 LOST 时间及原因。
- 窄窗结果应输出少量转变和统计；不得覆盖原报告、改判原 FAIL，或将本次小报告复核冒充完成了该窄窗诊断。
