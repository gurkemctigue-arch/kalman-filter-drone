# 2026-10-27 独立链路稳定性探针复核

## 结论与研究边界

独立工程探针 `diagnostic_v3_car_crossing_memory_relief_20261027_v2` 完整结束，飞行 runner 与 ROS observer 均返回 0，诊断捕获完整、没有残留仿真进程，正式 166 槽清单前后不变。此探针复用了原阶段二汽车交叉 seed005 的冻结算法、控制、安全门限和资源参数，只使用独立结果名称；原 seed003、seed005 的 FAIL 必须保留，探针不占用或替换正式槽。

这一次运行没有重现原来的 odometry/status stale 中止，可以支持恢复逐槽守护实验。它不能证明原故障根因已经确定或永久消除，也不能替代阶段二的离线身份评价、重复试验与统计验收。飞行 monitor 的 `basic_flight_passed=true`、`follow_duration_reached`、`offline_evaluation_required=true` 应同时保留。

复核仅解析小 JSON/JSONL 和末尾文本日志，没有读取或解码 rosbag，没有重新运行测试或仿真，没有改动冻结源码、参数与清单。

## 证据范围

- 诊断归档：`results/link_stability_probe_20261027_v2/`，session 起于 UTC 11:01:59.312885，summary 完成于 UTC 11:04:37.695635。
- 飞行证据：`results/frozen_fullplan_v3/diagnostic_v3_car_crossing_memory_relief_20261027_v2/`。
- Windows 资源采样：`results/host_link_stability_probe_20261027_v3.jsonl`。注意文件名后缀 v3；按实际 UTC 时间，它覆盖本次 v2 飞行探针。
- 正式清单检查点：76 PASS、40 FAIL、50 PENDING；本诊断不更新这些数值。
- 冻结计划 SHA256：`58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`。

## ROS 接收链路

ROS observer 共写出 158 条聚合。飞行 monitor 声明的仿真区间为 0.1–60.7 s，跟随起点为 17.752 s。按照聚合的最新已接收 `/clock` 筛选，并要求窗口内实际收到 phase，飞行区间得到 121 个聚合（仿真 0.288–60.236 s），其中跟随区间得到 86 个聚合（17.776–60.236 s）。1 Hz 聚合无法精确切分起止边界，表中的 gap 是归属这些聚合的已完成回调间隔。

| 接收链路 | 跟随窗口最大已完成回调间隔 | 跟随窗口最大采样接收年龄 |
| --- | ---: | ---: |
| 原始 PX4 odometry | 0.065884 s | 0.016208 s |
| 转换后 odometry | 0.065149 s | 0.015458 s |
| 原始 PX4 status | 1.061999 s | 1.046999 s |
| ROS `/clock` | 0.040069 s | 0.006867 s |
| flight phase | 0.143674 s | 0.075271 s |

跟随窗口中，原始与转换后 odometry 均没有空的聚合窗口；status 有一个无新消息的 1 Hz 窗口，但对应实际完成间隔为约 1.062 s，符合低频状态消息可能跨聚合边界的情况，不能据此称为链路中断。整个捕获期（包括 monitor 结束后的收尾）status 最大已完成间隔为 1.071542 s，原始 odometry 为 0.065884 s、转换后为 0.065149 s。未出现 ABORTED phase。

跟随/飞行窗口的 observer 聚合最大间隔为 1.002492 s；全程最大 1.062249 s 出现在第一个聚合。最终 writer 写出 158 条、404575 B，队列为 0，丢弃为 0，无错误、无日志限额触发，线程已退出。最大 write+flush 为 0.001504 s，最大 JSON 编码为 0.000401 s。聚合中的 `writer_alive=true` 是运行时状态；最终退出状态必须以 `ros/summary.json` 的 `writer_alive=false` 为准。

这些时间是本观察器 Python callback 的执行时间，不能当作 DDS 包到达时间，也不能直接代替 flight supervisor 的本地回调年龄。转换后 odometry header 使用 adapter 的缓存 ROS 时钟，不以它与 supervisor ROS now 的差值推断物理推进量。

## 原生 Gazebo stats

1442 个 CLI 行全部可解析为完整 JSON 对象，无损坏行；其中 53 条是初始暂停消息，1389 条已经推进且未暂停。迭代数从 1 增至 18026，仿真时间从 0.004 增至 72.104 s，已推进消息之间没有迭代数或仿真时间回退/停滞。

- 全部已推进消息：最大 CLI 接收间隔 0.214355 s，最大 Gazebo realTime 增量 0.214568 s，最大 simTime 增量 0.056 s；最大的间隔发生在刚解除暂停时。
- monitor 跟随区间：827 条原生消息，最大 CLI 接收间隔 0.121448 s，最大 Gazebo realTime 增量 0.108558 s，最大 simTime 增量 0.056 s。
- 跟随区间报告的 RTF 中位数 0.500016，5%–95% 分位约 0.499263–0.500875；瞬时最小/最大仍有 0.172378/0.826427，不应只引用中心分布而忽略这些短暂波动。

此记录未显示秒级的原生 stats 空档。CLI 接收单调时间可能受到 Transport/CLI 缓冲与观察器调度影响；realTime 是 Gazebo 消息字段，不能将某一条 CLI 接收空档独立解释为物理引擎暂停。本次多数消息一行一个 JSON，已按实际内容核实，不能对未来未知输出格式做同样假设。

## 宿主与 Linux 资源

Windows 采样共 31 次，UTC 11:01:55.210324–11:04:34.383258，最大采样间隔 5.409386 s。可用内存最低 6661 MiB，约 6.50 GiB；提交量最大 42468950016 B，约 39.55 GiB，提交上限约 50.73 GiB。

Windows 并非全程没有磁盘换入：11 个样本的 Pages Input/sec 非零，峰值 2305 pages/s；Page Reads/sec 峰值 189。此类计数也包含文件映射硬缺页读取，不能直接等同于 pagefile 交换，更不能在缺少进程归属证据时指认 WSL。采样结果不能重建各次采样之间的瞬时峰值，也不能将采样率简单相加为读取总量。

Linux 资源 observer 共 158 个采样，最大间隔 1.005362 s。`MemTotal−MemAvailable` 从 681472 KiB 增至峰值 2115392 KiB，约从 0.650 增至 2.017 GiB，净增约 1.368 GiB；峰值 UTC 11:03:37.485975。匿名页峰值 1546200 KiB，约 1.475 GiB。全程 SwapUsed、pswpin、pswpout、oom_kill 均为 0，memory PSI 累计停顿为 0；major fault 从 16750 增至 20088，不能把这些文件读取缺页当作 OOM 或 swap。

当前证据支持“本次在较充足宿主余量下完成了一次同参数工程探针”。它不支持“关闭应用就是已证明的根因修复”“以后不会再停顿”或“Windows 没有任何硬缺页读取”。正式实验仍应一次一槽，保留失败并在新的基础设施中止时停止续跑。

## 关键小文件 SHA256

| 文件 | SHA256 |
| --- | --- |
| `link_stability_probe_20261027_v2/summary.json` | `53286af061026e79e7a248e205d4100ae17af6b044defd82a152307580dde42d` |
| `link_stability_probe_20261027_v2/ros/aggregates.jsonl` | `376682595acba4624e2b22535039e112dd025ca9c2e1e584fbbde34cf83d4929` |
| `link_stability_probe_20261027_v2/native_gazebo_lines.jsonl` | `74eab1d2d7df1dc7e28119df77121198828050d9f49bfec6587d32e99149da72` |
| `host_link_stability_probe_20261027_v3.jsonl` | `cf22986701b1645a9a7671ea4369a0943652f1ee9d5c17c4174066288f63b025` |
