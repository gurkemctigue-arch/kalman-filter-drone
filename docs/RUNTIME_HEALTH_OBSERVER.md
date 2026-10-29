# 独立运行资源与仿真时钟观察器

`scripts/observe_runtime_health.py` 用于下一次另起名字的诊断飞行。它复用 `watch_sim_resources.py` 的 Linux 主机采样，以及 `observe_ros_link.py` 的接收计数和异步限额写入器，补充进程 CPU/RSS、磁盘空间及可选 ROS 时钟接收观察。

它必须作为独立 Linux 进程运行，不加入飞行监管节点的 executor。主循环用 `time.monotonic()` 每秒采样；ROS 接收在该观察器自己的线程、context 和 executor 中运行，使用传感器 QoS。没有 ROS 环境时可以省略 `--ros`，仍记录主机资源。此工具不发布消息、不修改进程或飞行保护门限。

在已加载对应 ROS 2 与 `px4_msgs` 环境的独立终端启动，例如：

```bash
python3 scripts/observe_runtime_health.py \
  --output-dir '/mnt/d/基于yolo和卡尔曼滤波/results/development_20261030/runtime_health_probe01' \
  --duration-wall-s 600 \
  --ros
```

输出目录必须位于 `/mnt/d` 下且尚不存在。示例目录名称仅供后续新诊断使用，本文没有启动观察器或仿真。当前 PX4 接口默认使用 `/fmu/out/vehicle_status_v1`；安装接口若使用未带版本的名字，显式加 `--status-topic /fmu/out/vehicle_status`。

`health.jsonl` 含启动记录、每秒样本和结束记录，每条都 flush。记录内容包括：

- wall/UTC 与 monotonic 时间、实际采样间隔及采集耗时；
- `/proc` load、memory、swap、major faults、OOM 累计计数、CPU/memory/I/O pressure；
- Linux 根分区及输出所在 D 盘挂载的可用空间；
- Gazebo、PX4、Python、录制器四个互斥进程组的 RSS 和 CPU 增量，不保存命令行、参数或环境变量；
- 可选 `/clock` 和原始 VehicleStatus 的独立观察器接收 monotonic 时间、接收年龄、间隙、源时间和计数；
- 写入队列深度、丢弃采样数、写入耗时、限额和错误。

CPU 的 100% 代表一个逻辑核心，多个核心可以超过 100%。首次出现或 PID 被复用时 CPU 增量为 `null`，不当作零；RSS 按进程累加，共享页可能重复计算。低频轮询可能遗漏两次采样之间创建又退出的进程。

`sim_seconds_per_monotonic_second_observed` 只描述此独立观察器收到的 Clock 在两个采样间推进多少。VehicleStatus 原始微秒时间保持未独立验证的域标记。观察器 callback 的时间不是监管节点 callback 的时间，不能据此直接重建监管 executor 的执行顺序。

D 盘写入通过有界队列交给独立 writer 线程。磁盘变慢时会记录队列和丢样；退出最多等待已有 writer 的有界 drain。若未完全 flush、丢样、达到字节上限或 ROS 接收异常，会明确报告 `flushed_cleanly=false` 并以非零状态结束。SIGINT/SIGTERM 请求正常退出并刷新。输出默认上限 16 MiB，可用 `--max-log-mib` 指定 1–64 MiB。

纯 Python 测试覆盖 PID 复用、CPU/RSS 汇总、录制器分类优先级、敏感命令不落盘、仿真 Clock 停止/回退与接收时钟分离。尚未执行 Linux/ROS 实际运行验证，历史失败与根因状态保持不变。
