# 研究冻结之后的主版退出清理修订

`fullplan_v1` 已冻结并开始正式研究。主源码随后发现并修复的退出清理问题，不能回填成该冻结研究已经验证的行为，也不能覆盖原录制或原日志。

首轮 `fullplan_v1_online_estimators_person_velocity_adaptive_kf_seed00` 的严格工程评价为 PASS，但停止录制时，`ros.log` 记录 controller 和 state_estimator 在 SIGINT 已关闭默认 ROS context 后，再次无条件调用 `rclpy.shutdown()`，抛出 `rcl_shutdown already called`，节点退出码为 1。外层 launch/运行器的退出码不能替代各节点退出记录。该异常发生在试验停止清理阶段；原工程评价及异常日志均按原样保留，不能把日志异常写成无异常退出。

Windows 主源码的修订仅涉及节点入口的退出清理：controller、state_estimator、PX4 adapter、flight supervisor、flight TF、gimbal adapter 及两类场景运动节点，正常处理 `KeyboardInterrupt` 和 `ExternalShutdownException`，销毁已创建节点后使用 `rclpy.try_shutdown()` 幂等关闭 context。构造失败及清理失败仍会关闭 context；正常业务异常继续向外抛出，不以正常退出掩盖故障。运动节点只在 context 仍有效时发送原有停止命令。

detector 既有的独立信号请求、推理 worker 完整 join、节点销毁和 context 关闭顺序保持原样。未修改估计、关联、控制、参数、实验条件或评价标准。修改没有同步到 `/root/uav_tracking_fullplan_v1`，正式研究继续使用原冻结版本。

`tests/test_ros_node_shutdown.py` 在不启动 ROS、仿真或推理的条件下，加载生产 `main()` 并模拟已关闭 context、SIGINT、外部关闭、正常返回、构造失败和业务/清理异常，检查清理及故障传播顺序。它属于入口逻辑验证，不代表真实 ROS launch 的信号退出已经干净通过。

## v2 首条正式飞行的真实退出边界

`fullplan_v2` 冻结版本已包含上述 `try_shutdown()` 修订，四个 ROS 包构建、导入隔离及冻结 Linux 环境 492 项测试全部通过。但是，首条 `fullplan_v2_online_estimators_person_velocity_raw_seed00` 的真实退出仍记录了 `destroy_node()` 内的 `KeyboardInterrupt`。这次没有出现旧版 `rcl_shutdown already called`，两种异常不能混称，也不能把单元测试通过写成真实关闭已无异常。

只读核对 [ROS 日志](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_person_velocity_raw_seed00/ros.log)、[录包日志](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_person_velocity_raw_seed00/bag.log)、[monitor 摘要](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_person_velocity_raw_seed00/summary.json)、[外层退出码](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_person_velocity_raw_seed00/process_exit_codes.json) 和冻结运行器源码，顺序为：

1. monitor 达到 `follow_duration_reached`，记录 `monitor_success=true`、退出码 0；主运行日志随后写明 `monitor exited 0`。这是正常结束，没有监测到飞行中 ROS 子进程死亡而提前中止。
2. 运行器进入 `finally`，先停止 monitor，再停止 bag 并等待压缩结束。bag 日志在墙钟 Unix 时间 `1793043070.546` 停止发现及暂停录制，`1793043087.648` 写明 `Recording stopped`。
3. 运行器随后对 ROS 进程组发送 SIGINT；launch 日志第 35 行记录 `user interrupted with ctrl-c (SIGINT)`，随后逐个向子节点发送 SIGINT。日志中 6 条 `process has died` 全部在这条停止记录之后，停止记录之前没有 traceback、KeyboardInterrupt 或子节点死亡记录。bridge 的两条信号记录在 `1793043087.862` 和 `1793043087.891`，晚于 bag 正常停止。
4. controller、state_estimator、flight_supervisor 的 traceback 均位于 `destroy_node()` 内部，最终为 `KeyboardInterrupt`。这三个节点及 scenario_motion、flight_tf、px4_adapter 共 6 个节点被 launch 记录为退出码 -2；detector 和 parameter_bridge 则记录为 clean。外层 `ros` 退出码仍为 0，不能用它掩盖这些子节点退出记录。
5. 后续严格飞行评价为 PASS，运行与评价返回码均为 0；这是所录任务区间的工程验收，与退出清理是否无异常分别保留。外层退出码还记录 bag/monitor/PX4/Gazebo 为 0、agent 为 -2。

入口的 `except (KeyboardInterrupt, ExternalShutdownException)` 只包围节点创建和 spin，清理阶段的 `destroy_node()` 位于外层 `finally` 内；其间再次收到的 `KeyboardInterrupt` 不会被前述 except 吞掉。内部 finally 仍会尝试执行 `rclpy.try_shutdown()`，但日志不能据此证明整个清理函数完成。运行器向进程组发信号，launch 又向子节点发信号，构成两条已知信号路径；这组日志没有逐节点信号计数，不能断言每个异常具体由第几次 SIGINT 导致。

核查时，首条运行器记录的旧 ROS PID 838、子节点 PID 1110–1117 均已不存在；Gazebo/agent/PX4/bag/monitor/ROS 的旧 session ID 522、525、602、836、837、838 也没有残留进程。当前进程属于下一条独立录制。这仅是该时点的进程快照，不代表未来所有退出都无残留。

仅查看冻结根、该试验目录和 PX4 rootfs 顶层，未发现新的 `core*` 文件；`/var/crash` 现有条目最新为 10 月 25 日。内核 `core_pattern` 实际为 `|/wsl-capture-crash %t %E %p %s`，本次没有追踪该 WSL handler 的全部输出位置，不能由这些浅层检查断言全系统没有新 core。原日志中上述退出码为 SIGINT 的 -2，没有观察到 SIGSEGV/SIGABRT 退出记录。

以上只更新 Windows 主版审计说明。冻结源码、原日志、原飞行评价和清单均不修改；真实 launch 的干净退出仍未通过验证，后续在正式飞行结束后的独占窗口单独诊断。

## 主版运行器的单路 SIGINT 修订，等待独立真实验证

后续仅修改 Windows 主版 `scripts/run_stage1_trial.py` 的停止路由：ROS 服务的初始 SIGINT 只发送给 `ros2 launch` 主进程，由 launch 向其节点转发，其他服务仍向原进程组发送 SIGINT。若 ROS 主进程未在既有超时内退出，仍依次向原进程组发送 SIGTERM、SIGKILL 并等待，超时数值不变。未改变节点清理代码、检测、滤波、关联、控制、安全年龄或试验参数。

该方案依据本机 Jazzy 的实际源码：shell 的 ROS 分支使用 `exec ros2 launch`，没有遗留中间 shell；`ros2launch/api/api.py` 中 `launch_a_launch_file()` 创建 `LaunchService` 并在同一进程调用 `run()`。`launch_service.py` 捕获初始 SIGINT 并产生 `due_to_sigint=True` 的关闭事件；`execute_local.py` 的 `__on_shutdown()` 在 `context.noninteractive` 为真时向子节点转发该 SIGINT。CLI 的 `--noninteractive` 默认值是 `not sys.stdin.isatty()`，因此主版运行器同时对 ROS 的 Popen 显式设置 `stdin=DEVNULL`，避免调用者有终端时 launch 不转发。其他服务的 stdin 继续继承。

专属 `tests/test_trial_shutdown_signals.py` 只加载生产 `start()`、`stop()` 的 AST 并使用进程替身，检查 ROS 单独初始信号、其他服务进程组信号、原 TERM/KILL 兜底和 stdin 路由；不启动任何进程。既有 seed 测试只为 Process 替身补充 `send_signal()` 空方法，原种子行为及断言保持。这些测试验证信号路由意图，不能证明 ROS 节点真实退出已干净，或证明所有关闭时序问题已解决。

Windows 定向验证：上述 8 项信号测试全部通过，用时 0.022 s；既有 seed 测试 1 项通过、3 项 POSIX shell 检查按环境跳过，用时 0.219 s。未运行全套测试、构建、ROS launch、仿真或 bag 分析。

当前 `fullplan_v3` 的 166 次主研究及后续独立 16 项扩展继续使用原冻结源码，本次主版修改不回填冻结根，也不改写 v1/v2/v3 原退出日志。只有主飞行 166、主离线 166、工程扩展 16 及扩展补充后处理 16 全部终态后，才在新根 `/root/uav_tracking_fullplan_cleanup_v3` 和新结果目录 `results/frozen_fullplan_cleanup_v3/` 开展独占验证。stage1 需覆盖 8 个预期节点，stage3_multi 需覆盖 9 个；须证明每节点在停止标记后的真实干净退出，外层 ROS/monitor 返回 0 或飞行 PASS 均不足。在两项真实探针完成前，本项仍为待验证，见 [cleanup 协议](CLEANUP_ENGINEERING_PROBES.md)与 [v3 交付命令](FULLPLAN_V3_DELIVERY_COMMANDS.md)。
