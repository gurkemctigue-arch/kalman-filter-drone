# Stage 3 显式运行参数快照

冻结 Humble15 的首个 `person_stage3_midpoint_seed004` 已完成飞行、录包和严格收尾，随后在独立审计前被判为 `INFRASTRUCTURE_ERROR`。原计划保留 3 个 `EVALUATION_PENDING`、1 个 `INFRASTRUCTURE_ERROR` 和 8 个 `PENDING`，原记录不修改。

原因是 stage3 的两类 YAML 省略了节点默认值。在线节点会使用默认值，但独立审计要求这些设置必须出现在当次保存的 `runtime_parameters.yaml` 中，以便后续只凭录制证据解释结果。主树的两份 stage3 YAML 现显式补充以下设置，数值均与冻结节点原默认相同：

| 节点参数 | 显式值 | 严格检查 |
| --- | --- | --- |
| PX4 adapter `vehicle_odometry_topic` | `/fmu/out/vehicle_odometry` | runner 与 source-clock 配置解析 |
| PX4 adapter `vehicle_odom_topic` | `/vehicle/odometry` | runner 与 source-clock 配置解析 |
| controller `desired_offset_m` | `[0.0, 0.0, 0.0]` | navigation 配置解析 |

此修改没有改变默认控制行为、时效门或验收阈值。没有给 Humble15 原快照补写字段，也没有使用推测默认值使其原失败记录通过。

## 全参数生成预检

`results/freeze_validation/runtime_stage3_topics03/summary.json` 保存 12 个核心条件与 16 个扩展条件的完整纯静态预检。外部验证程序运行实际生产参数准备代码，在 `runtime_parameters.yaml` 写出后立即停止，另用隔离 scratch 根目录承接所有输出。每个条件均调用原 runner 参数审计、source-clock 的 `recorded_configuration()` 与 navigation 的 `recorded_configuration()`。

冻结15原配置的 28 格中，恰好 6 个 stage3 核心格重现上述缺键；补充显式声明后，28 格的三项配置契约全部通过。原15计划、槽和两份冻结 stage3 YAML 的 SHA 前后一致。此验证未启动 Gazebo、PX4 或 ROS 图，不代表飞行验收；只读来源核验可能调用 git/ldd。原01外部 harness 的路径错误、02 runner 单项通过和03扩展解析结果均保留。

## 独立开发诊断的界限

原 stage3 midpoint bag 的另名只读结果在 Humble15 的 `results/development_diagnostics_v4_humble15_stage3_midpoint01/diagnostic.json`：native、surface 遮挡安全和云台评价通过；source-clock 因显式 topic 缺证为 `INCOMPLETE`，navigation 因零偏置声明缺失而拒绝。没有生成或填补缺失的导航结果。这些结果只用于诊断，不能替代原槽或最终门。

另外单独新建的 car 45 秒 seed004 诊断采用未改 Humble15 源码，与原 car velocity 待执行槽语义相同，保留完整短长遮挡和显式重选。其三流 6294 条全部配对，距离/高度 RMSE 为 0.824001/0.178256 米，有效状态 394/457，真值 457/457，source、native、surface 与 closure 均通过。独立计划前后验证原核心计划和槽 SHA 不变。该诊断不消费原 `PENDING` 槽，不是最终完整矩阵的标定来源，也未消费正式种子。

后续须在新的统一来源版本中完成真实 stage3 与完整开发矩阵；不能把本页的静态检查和诊断结果当成整个阶段三完成。
