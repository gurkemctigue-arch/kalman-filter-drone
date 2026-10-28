# v3 阶段三 person midpoint seed001 状态超时记录

本记录对应正式冻结 v3 的第二个阶段三槽
`fullplan_v3_stage23_s3_person_gimbal_midpoint_seed001`，由
`fullplan_v3_guarded_continuation_v7` 于 2026-10-27 执行。它是原计划中的一次正式尝试，结果和录包均保留；本记录不重写原评价，也不把缺少评价报告填成算法分数。

## 观察到的事实

监督器在仿真时间 50.5 s 进入 `ABORTED`。原始 telemetry 中的安全信息为：

| 项目 | 值 |
| --- | --- |
| status 年龄 | 2.344 s |
| status 门限 | 2.000 s |
| odometry 年龄 | 0.085 s |
| arming state | 2（armed） |
| nav state | 14（OFFBOARD） |
| failsafe | false |
| 最后 status 接收单调时刻 | 323.751442 s |
| 中止时 supervisor 单调时刻 | 326.095805 s |
| 最高高度 | 2.910 m |
| 起飞与 OFFBOARD 证据 | 已满足 |

因此，这次中止由状态新鲜度保护触发。它不是起飞失败，也没有证据表明 PX4 主动进入 failsafe。里程计在同一时刻仍新鲜，说明该次事件至少表现为低频 status 链路的接收间隔超过预算；不能仅凭这一点确定是 Gazebo 调度、WSL 资源、DDS/uXRCE 传输还是进程回调调度。

## 正式结果处理

- `summary.json`、`telemetry.jsonl`、`rosbag`、过程日志和审计事件均保留。
- `flight_evaluation.json` 和 `gimbal_evaluation.json` 没有生成，因此不能补造评价分数或把它当作已完成的普通性能 FAIL。
- v7 守卫在该槽后停止，剩余 37 个阶段三槽没有启动。
- 官方冻结台账没有被独立 probe 或诊断文件改写。

## 与 seed000 诊断的关系

seed000 的只读 ULog 审计显示源 `vehicle_status` 仿真时间周期中位数约 0.504 s、最大约 0.508 s，没有 ULog dropout 或 corruption；但同一源周期在录包存储时间上曾跨过数秒，且 clock 与 odometry 也有共同接收间隙。该证据支持“推进或接收变慢”的候选解释，不能证明 XRCE 丢失了某一条发布，也不能证明此次 seed001 与 seed000 有完全相同的根因。

本 seed001 尚未取得对应的独立 ULog 源周期审计，故不把源端发布规律外推到本槽。下一步可以在全新目录执行同参数的只读链路 probe，或在明确的新研究修订中评估 RTF/调度设计；不得在冻结 v3 研究中改 watchdog、伪造消息新鲜度或重试同名槽。

## 同参数独立 probe 对照

随后以新诊断名 `diagnostic_v3_stage3_person_midpoint_seed001_link_20261027_v1` 完成了同参数独立 probe。它不计入正式166槽，且 `official_ledger_unchanged=true`、`diagnostic_capture_complete=true`、`idle_after_probe=true`。

在该次正常完成的 FOLLOW 观察窗口中，独立 ROS observer 记录的最大完成接收间隔约为：raw status 1.096 s、raw odometry 0.114 s、converted odometry 0.114 s、`/clock` 0.105 s。status 仍明显低频，但没有达到正式 supervisor 的 2 s 中止门限。该 probe 还受到宿主调度影响（37个资源采样中21个出现 page input，最低可用内存约7.1 GiB），所以它只能说明本次未复现，不能证明正式中止的根因已修复。

两个正式槽加上两个独立 probe 的证据共同支持“status 低频裕量在当前 RTF/宿主调度下存在间歇性风险”。它们尚不足以在 Gazebo、WSL 调度、DDS/uXRCE 和节点回调之间唯一定位根因；后续恢复正式槽必须继续保留异常并逐槽运行。
