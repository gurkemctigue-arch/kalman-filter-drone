# 独立工程探针：ROS 接收链路与原生 Gazebo 时钟观察

主副本工具为 [observe_ros_link.py](../scripts/observe_ros_link.py)。它用于另起名字的独立诊断探针，不能覆盖正式失败、代替主 166 条结果、放宽 watchdog 或改变已冻结控制/资源参数。已通过 4 项窄单元测试，以及 Linux Jazzy 环境中无仿真、无发布者的 4 秒 ROS 启动/退出实测；这不代表已验证真实飞行链路。

## 已知源码事实与尚未确定的原因

冻结阶段二 launch 把 supervisor、adapter、估计器、控制器、桥接和检测器启动为不同进程。supervisor 使用默认单线程 `rclpy.spin`，订阅回调只更新接收值与 `time.monotonic()`；其内部没有 tracks JSON、视频或 telemetry 文件写入。monitor 的视频编码/写文件与轨迹 JSON 不能直接占据 supervisor 的 Python executor 或 GIL。可能的跨进程耦合是 CPU 调度、内存、文件系统、DDS 发布/队列或 Gazebo/PX4 时间链路，现有记录尚不能确定是哪一条。

supervisor 的 `_tick` 是 ROS 时钟定时器，但状态新鲜度检查使用单调墙钟。一段仿真或 callback 停顿后，下一个 tick 可以看到很大的墙钟年龄并锁存 ABORTED。这是保留的安全行为，不应通过放宽门限来掩盖。

尤其不能把 `ros_now - odom.header.stamp` 直接解释成 Gazebo 物理时间推进量。adapter 收到原始 PX4 里程计后，用本进程 `get_clock().now()` 重写 ROS header；supervisor 的 ROS clock 也依赖本进程 `/clock` callback。两者都可能是延迟处理后的缓存时钟。很小的 ROS 差值与很大的墙钟年龄，可以同时出现在上游仿真停顿、桥接/DDS 停顿或本地 callback 延迟中。

对应冻结源码位置：`flight_supervisor.py:126-130,143-163,170-175,277-280,312-314,349-356`；`adapter_node.py:196-210,228-246`；阶段二 launch `:26-49`。Jazzy 的 `rclpy/__init__.py:101-106` 使用默认单线程 executor，`time_source.py:71-75` 的 `/clock` 本身也是普通 subscription，`node.py:1774-1781` 令无显式 clock 的 timer 使用 node clock。

高频观察负载也应区分：估计器默认每 0.02 仿真秒预测并发布 tracks JSON；monitor 同步解析、再序列化并写 buffered telemetry，也同步生成约 5 帧/仿真秒的视频及周期 JPEG。原录制还包括 640×480、10 Hz 的 RGB 与 float depth，单这两路未压缩像素约 21.5 MB/仿真秒。它们是可观察的负载路径，不是现阶段已证实的根因；file-mode zstd 主要在录制结束后压缩，不能未经测量便把运行中停顿归因于压缩。

## 观察器读取与输出

工具只订阅五路：原始 PX4 VehicleOdometry、VehicleStatus、`/clock`、转换后的 `/vehicle/odometry` 和 flight phase。全部是 BEST_EFFORT、VOLATILE、KEEP_LAST depth 5；没有应用/控制发布、目标或真值读取、参数客户端，也不导入冻结算法。ROS 自身可能产生发现、参数事件等基础设施流量；这里不声称节点绝对没有任何 publisher。订阅 callback 只记录计数、墙钟接收时间和原始时戳，不逐条写文件。

独立 steady-clock timer 每墙钟 1 秒生成一次聚合，包含每路消息数、最后回调时间、当前接收年龄、窗口/全程最大已完成接收间隔、最新源时戳及最近已观察的 `/clock`。另外记录观察器本身的采样间隔、writer 队列长度、丢弃计数和写盘耗时。少于两个接收样本时，最大已完成间隔保持 null，不当作 0 延迟。

文件写入由单独线程完成，队列上限 16 项；callback 入队使用非阻塞操作。实时输出只能是新的本地 ext4 `/tmp` 子目录，默认日志最多 16 MiB。队列溢出、写盘失败或达到大小上限均显式记录，最终返回 2，不能把这类观察缺失当作正常链路。默认 600 秒墙钟停止，可限制在 1 至 7200 秒。没有自动复制到 D 盘的步骤，避免复制本身污染探针时序。

`receipt` 指 Python callback 被执行的时间，不是网络包抵达内核或 DDS 缓存的时间。BEST_EFFORT 也会丢消息；单独缺少观察回调不能证明发布端没有发消息。工具不输出飞行 PASS/FAIL 或根因结论。

## 后续待执行命令

以下为独立探针窗口内的准备命令，不是正式 50 个剩余 PENDING 的继续入口。先由探针调度器加载原 ROS 与 px4_msgs 环境、保证 ROS_DOMAIN_ID 与被观察系统相同。冻结 trial runner 当前显式使用 ROS_DOMAIN_ID=0、GZ_PARTITION=stage1_flight；另一个独立 launcher 应让观察器继承它的真实取值。

```bash
tracking_main='/mnt/d/基于yolo和卡尔曼滤波'
probe_observer_parent="$(mktemp -d /tmp/ros-link-observer-XXXXXX)"
/usr/bin/python3 "$tracking_main/scripts/observe_ros_link.py" \
  --output-dir "$probe_observer_parent/ros" \
  --duration-wall-s 600
```

运行中的 Python argv 只有主副本脚本与本地输出目录，不带 `--frozen-root` 或冻结源码路径。不要把此观察器与正式 guard 同时启动；它是独立工程探针的一部分。

实际查阅本机已安装 CLI help 后确认，Harmonic 没有 `gz stats` 子命令。原生 stats 是 Gazebo Transport topic，现有有效只读命令为：

```bash
source /opt/ros/jazzy/setup.bash
GZ_PARTITION=stage1_flight GZ_IP=127.0.0.1 \
  gz topic --echo --topic /world/stage2_flight/stats \
  --json-output --duration 600 > "$probe_observer_parent/gz_stats.jsonstream"
```

该命令不会运行仿真、改变参数或发布控制。stats 输出是消息流，不能假定整个文件是单个 JSON，也不能假定每行恰好一条完整消息或输出立即 flush；CLI 自身不附接收单调墙钟。后续调度器若需要与 ROS callback 对齐，应保留原始输出并有界重建完整 JSON 对象，为收到的完整对象附独立 receipt monotonic 时间；该时间仍可能受 CLI stdout 缓冲影响，不能当作 Gazebo 的发布时间或仅凭文件写入时间建立因果顺序。world 名与 GZ_PARTITION 必须匹配实际独立探针；stats 不存在时保留缺失证据，不能换成 ROS `/clock` 冒充原生物理进度。原生 stats 与 `/proc` 的实际采集由独立 launcher 负责，不另启第二个采集器。

两个观察命令应由同一探针调度器并行管理；上面的独立代码块本身不启动飞行或后台进程。全部仿真进程退出、观察器完成后，才把 `/tmp` 新目录复制到新的 D 盘证据目录，并保留 `session.json`、`aggregates.jsonl`、`summary.json` 和原生 stats。不要覆盖已有探针目录或正式试验。

## 空载验证证据

执行命令为 `python -B -m unittest discover -s tests -p test_ros_link_observer.py -v`，4 项全部通过。空载实测先加载 `/opt/ros/jazzy/setup.bash` 与 `/root/px4_msgs_ws/install/setup.bash`，再运行主副本脚本 `--duration-wall-s 4`，退出码 0。证据位于 [results/ros_link_observer_empty_20261027_1901](../results/ros_link_observer_empty_20261027_1901)，记录脚本 SHA256 为 `60838838b15c07233e9bed9bce078b02ea700f74b8350106c60f2d26e20d14b5`。

该实测在本地 ext4 `/tmp` 写入 5 条聚合，包含 4 个墙钟秒采样与 FINAL；总观察时长 4.052 秒，首个采样间隔约 1.052 秒，之后约 1 秒。五路消息计数全为 0，缺失接收年龄与间隔保持 null；writer 已退出，队列/丢弃数均为 0，无错误、无大小截断。此处只验证消息类型可加载、节点/steady timer 能运行与日志有界落盘/正常退出，不验证真实发布端、丢包或飞行安全。

本次空载核验还发现：单次 WSL 命令结束后，再次调用 WSL 时原 `/tmp` 目录可能消失。尚未确定具体清理机制。因此采集、停机确认与结束后小日志复制应由同一个仍存活的 Linux launcher 完成，不能依赖下一次 WSL 调用仍能读取 `/tmp`。空载证据已在观察器退出后的同一 shell 内复制，并在 Windows 中复核 JSON。

## 用观察区分哪些路径

| 同一停顿期间的独立证据 | 优先检查的链路，仍需对应进程证据 |
| --- | --- |
| 原生 Gazebo stats 迭代与时间也停止，其他源一同停顿 | 仿真/渲染/宿主调度；不能仅凭一个 D 盘 observer 的写入间隔认定整个 VM 暂停 |
| 原生 stats 正常，ROS `/clock` 停止 | Gazebo→ROS bridge、DDS 或观察器接收 callback |
| 原生 stats 与 `/clock` 正常，原始 PX4 odometry/status 停止 | PX4、uXRCE-DDS Agent 或相关传输/接收路径 |
| 原始 PX4 正常，转换后 odometry 停止 | adapter 的 executor、转换、发布或 DDS 路径 |
| 独立观察器各源正常，supervisor 仍报告接收过期 | supervisor 本地 callback/调度/DDS 实例；需 callback entry/exit 与 publish 耗时证据 |
| ROS aggregate 自身也出现明显墙钟空档 | 观察器调度或 executor 空档；结合原生 stats、writer 延迟和宿主独立采样，不能自行给出全系统结论 |

若上述观察仍不能定位，下一步独立探针可记录 supervisor/adapter 的 callback entry/exit 与 publish 耗时、monitor 的 on_image/on_tracks/write/flush 耗时，以及相关 PID/TID 的 schedstat、状态和等待点。使用内存有界缓冲，结束后再写盘；这些新增插桩应放在明确的独立版本中，保留正式研究源码与 watchdog/RTF 不变。
