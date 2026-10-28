# v3 汽车 crossing seed005：接收超时与采样调度关联

2026-10-27，只读诊断。正式试验为 `fullplan_v3_stage23_s2_car_crossing_locked_seed005`，原 FAIL 和 50 个 PENDING 均保留。没有消耗新的正式槽、读 bag、启动仿真或测试、修改冻结参数、关闭应用或更改系统设置。

## 确定的原始记录

[ros.log](../results/frozen_fullplan_v3/fullplan_v3_stage23_s2_car_crossing_locked_seed005/ros.log) 第 35 行在 Unix wall `1793096531.235022752`，即 18:22:11.235022 +08:00，记录 `ABORTED: flight guard: odometry_stale, status_stale`：

| 字段 | 值 |
| --- | --- |
| supervisor 当前 monotonic | `612.226688 s` |
| 最后有效 odometry 回调 monotonic / wall 年龄 / 门限 | `610.842419 / 1.384 / 0.500 s` |
| 最后 status 回调 monotonic / wall 年龄 / 门限 | `609.821428 / 2.405 / 2.000 s` |
| supervisor 当前缓存 ROS 时刻 | `35.752 s` |
| 最后 odometry.header.stamp | `35.664 s` |
| 最后 status 原 PX4 timestamp | `1793096520812612 us` |
| 当时缓存 PX4 标志 | `armed=2, nav_state=14, failsafe=False, preflight_pass=True` |

本次源码对照与 [trial 归档 SHA](../results/frozen_fullplan_v3/fullplan_v3_stage23_s2_car_crossing_locked_seed005/configuration/source_sha256.json)一致：

- `flight_supervisor.py`：`cb74d8354b40172872cce5ed68a1840c53dff172688c026d68cf97a904eb1413`。
- `adapter_node.py`：`ddf118074e7857cfc20c5ff3a6f3154f9895319c9a76803b8c4e41608157e8bb`。

supervisor 在其 odometry/status 接收回调内用 `time.monotonic()` 保存接收时刻，tick 用当前 monotonic 减该值检查 wall 时效。适配器收到原 PX4 odometry 后，用其**自身缓存的 ROS 当前时钟**重新生成 ROS Odometry header；supervisor 的 ROS now 也是该节点缓存时钟。因此 35.752−35.664=0.088 s **不能证明这段 wall 间隔内 Gazebo 只推进了 0.088 s**，也不直接给出原 PX4 odometry 源消息年龄。status.timestamp 是另一时域的 PX4 字段，不能直接与 ROS 秒数或日志 epoch 相减来诊断传输延迟。事后没有仍运行的原 PX4 可供查询，当前日志不足以重建它在超时窗口的时钟推进。

## 独立 observer 给出的关联与反证

原始 [host_observer_v3_car004.jsonl](../results/host_observer_v3_car004.jsonl) 含 594 个 /proc 样本；采样脚本 [watch_sim_resources.py](../scripts/watch_sim_resources.py) 的记录 SHA 为 `3632535f09fd161a5d85bb6f8e7481c8451c25d85e06fa7d1c53bd8888383d16`。文件名 car004 是原观察会话名，实际采样窗口也覆盖后续 seed005，不能误认为这些是两次独立资源观测。

| UTC 时刻 | 样本 monotonic / s | 与前样本间隔 / s | procs_running | CPU PSI some avg10 |
| --- | ---: | ---: | ---: | ---: |
| 10:22:09.620323 | 610.668476456 | 1.048929307 | 19 | 3.52% |
| 10:22:10.755627 | 611.803775557 | 1.135299101 | 31 | 6.32% |
| 10:22:14.140552 | 615.188702313 | 3.384926756 | 16 | 12.24% |
| 10:22:15.190190 | 616.238354499 | 1.049652186 | 11 | 15.64% |

supervisor 在 monotonic **612.226688** 实际执行了中止回调，位于 observer 的 **611.803775557–615.188702313** 长间隔内部，距前样本仅 0.422912443 s。这反对“整台 VM 在这完整 3.385 s 内持续完全冻结”的解释。

长间隔两端，`pswpin=pswpout=oom_kill=0` 均不变；`pgmajfault=15630` 不变，memory PSI total=0，IO PSI total=3,241,999 us 不变。MemAvailable 约 14,063,152→14,062,524 KiB；CPU PSI some total 从 11,240,712 增至 12,385,233 us。`/proc/stat` 的 user/system/idle 增量分别为 1744/761/618 ticks，iowait 与 steal 增量均为 0。这支持该窗口存在 runnable CPU 调度等待；它不单独定位到具体节点、宿主进程或虚拟化调度原因，也不排除 Windows 层分页或 I/O 等没有被 Linux PSI 直接反映的影响。/proc 字段按次读取，不是一个原子系统快照，不应从这些差分拟合精确的 host CPU 利用率。

observer 先记录 monotonic，再读若干 /proc 文件，随后向 D 盘 JSONL `write()`、`flush()` 并 sleep 1 s。因此 sample_gap 包含采样、写盘、休眠及调度时间；D 盘/9P 写入阻塞也可能拉长它，不能把该间隔直接称作全主机停顿。现有脚本没有分别记录 /proc 读取和文件 flush 耗时。

## 当前资源与历史范围

observer 在 10:25:01 UTC 已记录 `BOUNDED_OBSERVER_COMPLETED`，累计 601.989 s。实际进入后续诊断已是 18:40，故原实例的持续观察已结束，当前 WSL 是新实例；不得把新实例的 cgroup 或 OOM 计数当成原飞行的数据。

新实例 kernel 为 `6.6.114.1-microsoft-standard-WSL2`，可用 CPU 为 16、根 cpuset `0-15`。当前 `/init.scope/cpu.max` 为 `max 100000`，`nr_throttled=0`，memory.events 的 oom/oom_kill 为 0；该子组没有单独启用 cpuset 文件，继承范围需按根设置解释。旧飞行没有保存逐进程 cgroup 和节流计数，不能倒推其历史配额。

Windows 18:40:40 的一组快照为 CPU 5%、可用物理内存 **1,247,817,728 bytes**、committed 59,604,774,912 / limit 68,739,821,568 bytes（86%）、PagesInput 220/s，物理盘读约 137.65 MB/s。此时 C 可用 5,023,477,760 bytes、D 可用 239,031,005,184 bytes。相比早先停机检查，宿主可用内存明显减少，但没有失败时的同步 Windows 样本，不能宣称它已被证明是 seed005 的原因。未关闭或调整任何其他应用。

原始磁盘计数显示 C、D、E 都在同一物理盘 `0 C: D: E:`，把结果写 D 不代表与 Windows pagefile/应用获得了独立磁盘带宽。18:44:54 的一组 1.0253551 s raw-counter 差分为读 163.06 MB/s、写 5.72 MB/s、平均读 0.2210 ms、平均写 0.2534 ms、当前队列 0；这只说明该短窗口平均延迟较低，不能排除 18:22 的瞬时延迟。此前 formatted WMI 的 `AvgDisksecPerRead=0` 存在整数表示限制，不能被当作零磁盘延迟。

旧 boot `b9c5b11c3aa4476fa1105a3ddbff2a3f` 在 18:21:30–18:22:35 的持久 journal warning 以上、最多 30 条的查询没有条目；这不证明没有调度/宿主层异常。Windows EventLog 接口此前不可用，本次没有反复启动它或改变服务状态。

## 独立稳定性探针的捕获建议，尚未执行

在宿主资源足够且由主运行过程统一调度后，使用新工程探针名和原冻结参数，不消耗剩余正式 50 槽。需要同时区分 Gazebo 原生推进、原始 PX4 时间戳、ROS /clock 接收、supervisor 接收以及记录器自己的阻塞，才能定位问题。

已仅调用本机 Gazebo CLI 的帮助。Harmonic 的命令列表**没有 `gz stats` 子命令**；`gz topic` 支持 JSON echo、有限 duration 或有限消息数（两者互斥）。同分区的只读原生统计捕获语法为：

```bash
GZ_PARTITION=stage1_flight GZ_IP=127.0.0.1 \
  gz topic --echo --topic /world/stage2_flight/stats --json-output --duration 120
```

需按实际冻结世界名核对 topic，并给每次收到的原生统计附加独立 monotonic；同时记录原始 PX4 odometry/status timestamp、/clock 消息及其接收 monotonic。CLI 输出也可能缓冲，不能只看最终文件出现时间。采样结果可先存在内存或 ext4 的独立小文件中，结束后再归档 D；记录采样开始/完成和每次写出耗时，并与独立 Windows RAM/CPU/磁盘样本对齐。只观察必要小消息，避免图像解码、额外 YOLO、重复 bag 录制或高频 WMI 成为新干扰。

这些是取证设计建议，不是已运行探针，也不授权修改安全门限。当前直接失败仍是接收 wall 时效超限，具体调度/宿主/传输根因尚未确定。全部本代理诊断命令已结束，等待主运行过程协调。
