# Humble32 构建、基础闭环与核心场景执行快照

更新快照：**2026-10-30 15:16 UTC（北京时间23:16）**。核心12格原终态为1 PASS（person position）、1 FAIL（person velocity，`infrastructure_stop=false`），person crossing运行、9格PENDING；正式仍0/280。主树detector最小分段计时已通过29项行为测试及独立审查，但尚无33构建/runtime证据，冻结32没有加载该改动。首槽时效链、根因未证边界和后续诊断入口见[专项记录](reliability-v4-humble32-timing-failure-20261030.md)。以下14:51内容作为原历史快照保留。

静态快照时间：**2026-10-30 14:51:22 UTC（北京时间 22:51:22）**。本文件记录该时刻已落盘的证据，不是实时进度，也不宣称整个项目或阶段验收完成。

Humble32 已完成构建和完整测试，两类 20 秒 clean 基础检查通过开发准入；12 个核心场景已开始，快照时第 1 槽尚未登记终态。**本轮正式实验为 0/280，正式种子 1000–1009 尚未使用。**

## 冻结来源与构建

- 运行环境：`UAVHumble22`，Ubuntu 22.04、ROS 2 Humble、Gazebo Harmonic，以及隔离的 PX4 运行根。
- 来源提交：`b1a2e04ab9e8fdfba86c7477339cf3edda98a035`。
- Linux 冻结根：`/root/uav_tracking_fullplan_v4_humble32`。
- Windows 结果根：`results/frozen_fullplan_v4_humble32`。
- 597 个文件的冻结来源 canonical SHA256：`8f0e4f9b8d31fa6fe088ce28c64378c144c4a4bc903aa7a5063cfa5d1d2cbc84`。
- 冻结清单 SHA256：`87aaaa60b329390043ef053bdaae6360d836f3fa62389130c9f9d05ea24972ee`。

4 个 ROS 软件包完成冷构建，耗时 19.7 秒；模块与 ament 来源隔离、FastCDR 和 11 类真实生成消息的 CDR 往返检查通过。完整 Linux 测试运行 1537 项：**1532 通过、5 项按原精确平台条件跳过**，测试耗时 120.177 秒。构建验证摘要在 14:29:24 UTC 登记 `PASS`，但其 `runtime_acceptance=NOT_YET_EVALUATED` 只表示当时尚未飞行，不应随后改写该原摘要。

构建前后冻结源不变，旧 Humble28、29、30、31 已绑定证据不变；旧失败不提升为新成功。原 Humble28 核心结果仍为 8 PASS / 4 FAIL。

主要构建证据：`results/frozen_fullplan_v4_humble32/freeze_validation/build_validation_summary.json`，SHA256：`9bdb30548291f51a95d306089193b9f9481203a930fcc1846ad8dccd8834a766`。

## 两类 20 秒 clean 开发检查

驱动目录：`results/frozen_fullplan_v4_humble32/reliability_v4_humble32_clean20_serial01`。两槽各执行一次，保留原始终态；14:47:03 UTC 驱动登记 `TWO_CLEAN20_ORIGINAL_ATTEMPTS_COMPLETE`、退出码 0。

| 检查项 | 行人 | 汽车 |
| --- | --- | --- |
| 主运行 | 退出 0，完成 20 秒跟随 | 退出 0，完成 20 秒跟随 |
| PX4 源时钟独立评价 | PASS，3760 组三元消息匹配 | PASS，3796 组三元消息匹配 |
| 原生起飞及完整记录覆盖 | PASS，`full_recording_coverage=true` | PASS，`full_recording_coverage=true` |
| base_link 距离 RMSE | 0.325727 m | 0.772190 m |
| base_link 高度 RMSE | 0.319907 m | 0.304757 m |
| 导航有效状态覆盖 / 真值覆盖 | 1.0 / 1.0 | 1.0 / 1.0 |
| base_link 末端距离及高度持续稳定 | 均通过 | 均通过 |
| 录包闭合、完整性及 ROS 子进程退出 | 通过 | 通过 |
| 原 surface 评价 | INCOMPLETE_EVIDENCE | INCOMPLETE_EVIDENCE |
| 原 navigation 评价 | RECORDED_WITH_CENSORED_FAILURES | RECORDED_WITH_CENSORED_FAILURES |

本次导航开发准入针对登记的 **base_link 跟随控制参考**。原导航报告仍含其他参考项的未稳定结果，不能用该准入覆盖原始报告。clean 场景没有设计遮挡，因此原 surface 报告的遮挡证据不足结果按原样保留；它不提供短遮挡、长丢失、重新选框、多目标或云台主动模式的完整验收。

独立只读复核确认：20 项两类终态、评价报告和原始小工件的 SHA，以及 observer 的 3 项绑定 SHA 均吻合。两类 8 个 ROS 子进程逐一正常结束；录包进程退出 0。XRCE agent 的 `-2` 为记录的 SIGINT 退出，不能单独当作运行失败。驱动最终无残留仿真进程、无来源绑定错误。

独立 observer 正常退出，无强制停止、驱动异常或失效样本错误。首个新鲜样本 age 0.0108 秒，末个 age 0.2797 秒，均保持原 10 秒墙钟新鲜度要求。

| 两类原终态 | SHA256 |
| --- | --- |
| `person_terminal.json` | `ebac6246e791db15691e092e4c7e455a2368094f8681cb01861b88ce08608ac9` |
| `car_terminal.json` | `5fa15b474d163b393dd3fe916c43622124bac3c531959d4c36e122f92374e7d8` |

## 汽车 640 输入的性能波动

汽车使用固定 `yolo11m_car_sim_train20_04.pt`、640 输入、4 个推理线程，仿真实时因子 0.25；行人为 `yolo11n.pt`、320 输入、2 个线程。推理上限为 10 Hz，它是上限，不保证实际逐帧达成。

以下统计仅使用各自 telemetry 中 **FOLLOW 收件窗口**的真实记录，窗口之外的初始化观测不计入此表。

| 指标 | Humble31 独立汽车 640 短测 | Humble32 汽车 clean20 |
| --- | --- | --- |
| FOLLOW 内实际观测 | 198 | 118 |
| 约 20 秒窗口中的实际观测率 | 约 9.9 Hz | 约 5.9 Hz |
| 相邻唯一观测源时间间隔 | 中位数 0.1 秒，最大 0.2 秒 | 35 次 0.1 秒、82 次 0.2 秒 |
| 完整检测 job wall 中位数 | 0.246281 秒 | 0.635027 秒 |
| Humble32 job wall p95 / 最大值 | — | 0.715379 / 0.779407 秒 |
| Humble32 观测收件 age 中位数 / p95 / 最大值 | — | 0.224 / 0.272 / 0.292 秒 |
| Humble32 控制所用 measurement age p95 / 最大值 | — | 0.400 / 0.452 秒 |

全程摘要中的 job wall 中位数为 0.620523 秒，与上述 FOLLOW 子窗口的 0.635027 秒分母不同。`inference_wall_s` 覆盖整个检测工作项，包括解码、预测、深度与几何处理、锁和发布；**不能把它解释为纯 YOLO 推理耗时**。

Humble32 汽车 FOLLOW 记录未出现 LOST 或 stale，目标 UUID 始终一致；它证明此次单目标短测未丢失，不证明多目标物理身份已正确保持。行人 FOLLOW 窗口为 200 条真实观测，199 个相邻源间隔全部为 0.1 秒。

Humble31 独立汽车 640 短测与 Humble32 汽车 clean20 的归档运行参数，在仅归一冻结根名之后相同。归档算法来源摘要相同，只有注册脚本 `scripts/run_reliability_v4.py` 的 SHA 不同。现有轻证据尚不能确定变慢原因：主机负载、温度、Windows/WSL 调度或混合 P/E 核分配均只能列为待证假设，不能下因果结论。

Humble32 汽车运行中的 160 个健康样本显示，Python 进程组 CPU 中位数约 603.5%（单核为 100%）、Gazebo 68%、PX4 21%、录包 28%；未记录 swap 或 OOM。这些组级统计不能定位单个工作项的瓶颈，也不能证明 observer 引起了退化。

因此，目前不能宣称连续 10 Hz 身份证据覆盖问题彻底解决。固定 10 Hz 全任务身份分母、最低覆盖 0.80、UNKNOWN 保留等要求继续有效；不能通过降网格、补预测或放宽新鲜度门获得通过。

## 核心场景当前状态及后续准入

12 核心计划：`results/frozen_fullplan_v4_humble32/reliability_v4_humble32_probe01_seed004_matrix/plan.json`。

14:49:16 UTC，驱动实际发出第 1/12 槽 `person_stage1_velocity_seed004` 的 `START_SLOT`。在本快照时尚未出现首槽终态，故不能报告 12 核心已通过。执行事件和终态以 `core_serial01/events.jsonl`、`core_serial01/execution_terminal.json` 为准。

本地可视化进度入口：`results/project_progress/humble32_core12_01/index.html`。页面状态可能随实际驱动更新；本文件始终保持上述静态时间边界。

下一步依序为：完成同源 12 核心，检查真实身份覆盖与汽车性能；然后完成 4 项安全及 16 项扩展；通过后再完成定标、28 格真实容量测量和正式登记，才执行 120 次核心及 160 次扩展正式实验。普通算法 FAIL 和证据不足保留原分母，基础设施或来源故障按原约定停止，原槽不自动重试，也不拼接跨版本成功。

正式实验、四法离线配对比较、最终身份/检测统计和最终研究交付仍未完成。本快照不修改冻结 Humble32、旧失败记录或原评价报告。
