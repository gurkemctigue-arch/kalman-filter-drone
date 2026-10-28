# v3 汽车交叉 seed003：时效保护中止与停机后资源检查

日期：2026-10-27，Asia/Shanghai。范围为 `fullplan_v3_stage23_s2_car_crossing_locked_seed003`。只读检查原始小日志、Windows 资源及事件接口、WSL 当前资源和既有系统 journal；没有读 bag、运行评价器、测试或构建，没有重飞、修改冻结源码、放宽安全阈值或改写原 FAIL。本文位于 Windows 主副本，不在正式冻结根内。

## 已确认的触发链

原始 [ros.log](../results/frozen_fullplan_v3/fullplan_v3_stage23_s2_car_crossing_locked_seed003/ros.log) 第 36 行先进入 HOLD；第 37 行在 Unix wall time `1793095704.561886098`，即 **18:08:24.561886 +08:00**，记录：

| 字段 | 原记录 |
| --- | --- |
| 状态及原因 | `ABORTED: flight guard: odometry_stale, status_stale` |
| 当前 wall monotonic | `2461.115313 s` |
| odometry wall 年龄 / 门限 | `3.508 / 0.500 s` |
| 最后 odometry 接收 monotonic | `2457.606972 s` |
| status wall 年龄 / 门限 | `4.542 / 2.000 s` |
| 最后 status 接收 monotonic | `2456.573278 s` |
| ROS 当前仿真时刻 | `38.148 s` |
| 最后 odometry 消息仿真时刻 | `37.896 s` |
| PX4 标志快照 | `arming_state=2, nav_state=14, failsafe=False, preflight_pass=True` |

由消息 stamp 算出的仿真年龄约 0.252 s，不能替代 wall watchdog 的 3.508 s 接收年龄。保护确实按冻结时的 wall 门限触发，但这些字段不足以区分主机调度停顿、仿真减速/暂停、DDS/节点调度停顿等具体来源，也不足以证明发生过主机睡眠或 OOM。

[外层退出码](../results/frozen_fullplan_v3/fullplan_v3_stage23_s2_car_crossing_locked_seed003/process_exit_codes.json) 为 Gazebo 0、PX4 0、ROS 0、bag 0、monitor 1、agent -2。原快速停止路径没有启动后续评价器，不能因 bag 返回 0 就声称其内容已经完整解码或安全评价通过；这些外层返回码也不替代逐节点退出清理验证。外部守卫按预期停止、返回 2，余下 52 个 PENDING 未被消耗。该原 FAIL 保留，不重试 seed003。

## 停机后的资源快照及局限

18:12:02 的 Windows 只读快照：CPU 约 1%；物理总量 33,272,696 KiB、可用 7,443,672 KiB；虚拟内存可用 11,999,896 KiB。`D:\pagefile.sys` 分配 30,983 MiB、使用 4,611 MiB、峰值 6,693 MiB。C 可用 5,018,824,704 bytes，D 可用 242,060,988,416 bytes。它证明当时没有持续的 CPU 饱和或物理内存耗尽，不是失败发生时的资源采样。

首次诊断 WSL 命令在 18:12:02 进入的实例显示 kernel 约 18:11:59 启动、uptime 不足一分钟。诊断没有调用 shutdown 或 reboot；旧实例已在进入该命令前结束。WSL 正常空闲关闭可解释新实例，但不能仅据此确认旧实例为什么结束。当前空闲实例的可用内存为 15,986,192,384 bytes，swap 总量 4,294,967,296 bytes、使用 0；两次一秒 `vmstat` 样本均约 100% idle，memory PSI 为 0。这些新实例数值不能用于排除旧飞行时的内存压力或 OOM。

既有持久 journal 保留了原 boot `92541348a10144e385a906b5b2678855`（17:27:25–18:09:24）。按该 boot、Unix 时间 1793095500–1793095860（18:05–18:11）、warning 以上级别及最多 30 条记录的有界查询，仅返回 18:09:24 的 `Operation canceled @p9io.cpp:258 (AcceptAsync)` 和 `Failed unmounting init.mount - /init`。这些是中止约一分钟后的关闭记录，不能用来解释 18:08:24 的时效失效，也不能据日志未记载断言没有 OOM。早一次跨 Windows/WSL 的日期引号传递导致筛选未生效，已结束该查询；本结论只采用上述后续有界查询，不将宽范围输出当成精确时间窗证据。

Windows `Get-WinEvent` 在线查询及直接读取 `C:\Windows\System32\winevt\Logs\System.evtx` 均报 `The interface is unknown`。EventLog 服务当时为 `StartPending`，现有 System.evtx 大小 20,975,616 bytes、修改时间为 2026-10-26 12:49:38。没有启动或修改该服务；本次无法据 Windows 事件确认或排除失败时的睡眠、资源耗尽或驱动事件。

## 后续执行边界

直接原因已确认是两条 wall 数据时效同时超过冻结保护门限；外部根因仍未知。当前停机资源检查足以支持由主运行过程安排**下一个 PENDING 的汽车 crossing seed004 单槽**，使用同一冻结参数和新的独立审计目录，再检查该槽的原始输入资格和守卫结果；这不是证明所有外部停顿风险已经消失。不得重试 seed003、延长 0.500/2.000 s 门限、覆盖历史失败，或把停机后低负载写成原试验全程无资源问题。若新槽再次出现同类异常，应继续保留新失败并停止后续槽，不能无诊断消耗整个队列。

全部 WSL 诊断进程已结束；后续资源观察由主运行过程协调，避免与飞行或守卫空闲检查冲突。
