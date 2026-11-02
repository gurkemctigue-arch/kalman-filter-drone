# Humble53 完整 75 秒复验小文件快照

2026-11-02 22:31（北京时间）检查点：原失败场景的独立复验已通过，**1/1 原始工程 PASS**。本场为行人、第三阶段云台中位、开发 seed004；真实机体距离/高度 RMSE 为 0.7722/0.1540 米，末段距离和高度稳定检查均通过。来源时钟独立匹配 9224 组消息，无失败或证据不完整；独立原生起飞评价通过，原 driver 和双桥外层均正常退出。

这是一场复验，不代表汽车、主动云台、核心 12 场或整体可靠性全部通过。新核心 12 场计划已于 22:30:46 生成，命令退出 0；**计划生成时 0/12 完成、12 PENDING**，不是 12 场飞行通过。正式实验仍为 **0/280**。随后运行状态不能由本固定快照推断。

下列文件从实际原件完整复制，保留原路径字段、schema 和字节；`snapshot_manifest.json` 记录每件来源、大小与 SHA-256。该清单只核这些小文件，不声称重新读取或核验原 bag、视频或大体积遥测数据。

| 文件 | 用途 |
| --- | --- |
| `slot_record.json` | 原槽 `COMPLETED/PASS`、工程指标、评价与原始数据摘要绑定 |
| `attempt_terminal.json` | 原外层单槽闭合，`error=null` |
| `driver_execution_terminal.json` | 原 driver 终态，`FAILED_EQUIVALENT_ACTUAL_PASS`、退出 0 |
| `split_run_execution_terminal.json` | 双桥执行外层终态，退出 0、`error=null` |
| `px4_source_clock_report.json`、`native_startup_report.json` | 独立来源时钟与原生启动评价原件 |
| `navigation_reference_evaluation.json`、`flight_evaluation.json`、`gimbal_evaluation.json` | 完整小型评价报告，含原结论及边界 |
| `monitor_summary.json`、`process_exit_codes.json` | 飞行结束原因与进程退出原件 |
| `recording_closure.json`、`bag_integrity.json` | 原录制关闭与归档检查收据；本次没有读 bag |
| `core_plan.json`、`core_plan_driver_terminal.json`、`split_plan_core_execution_terminal.json` | 实际新核心 12 场计划、原 driver 的初始 PENDING 证据与两层生成动作终态 |

后续仍须依次完成新核心 12、安全 4、扩展 16、容量与定标、最终准入、正式 280 次重复及完整评价/交付。原 Humble51 失败与 Humble52 超时均保留，未拼入本轮计数。此目录不启动 WSL、仿真、推理、测试或实验，也不修改冻结来源、算法和门限。
