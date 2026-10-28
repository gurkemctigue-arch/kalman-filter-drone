# 阶段三行人中位云台 seed000：原 bag 与 ULog 只读时序审计

## 当前结论

正式 `fullplan_v3_stage23_s3_person_gimbal_midpoint_seed000` 保留 FAIL。中止时仅 VehicleStatus 超过壁钟门限，不能称为已证实的全链路暂停、内存不足、PX4 failsafe 或算法身份失败。正式守卫已停止；本轮检查不改冻结代码、安全门限、RTF 或失败槽。

本次先检查小日志、summary、metadata 和 PX4 源码，再在主代理确认所有仿真与测试空闲后，对原 bag 和 ULog 各创建一份独立 ext4 副本，完成一次过滤审计。入口 `scripts/audit_status_only_failure.py` 于 UTC 2026-10-27 11:55:09 完成，退出码 0；结果见 `results/stage3_status_source_audit_20261027_v1/summary.json`。原文件审计前后 SHA、大小、mtime 和 inode 全部相同。本次没有执行飞行、评分、测试、固件重构建或冻结源码修改。

ULog 的源 status 周期中位数为 0.504 s、最大 0.508 s，均属于 **PX4 仿真时钟**；这不能证明壁钟发布及时。bag 中最后两个 status 对应相邻源周期 51.628→52.132 s，却跨越 7.412276373 s 的 recorder 存储时间；相同窗口的 clock 和两路 odometry 也出现明显变慢及接收间隙。现有证据支持共同推进或接收变慢的解释，不能直接定为 status 单路丢包，也不能区分 Gazebo 物理推进、WSL 调度与 DDS/回调延后。

正式清单在本次中止后的检查点为 127/166 终态：85 PASS、42 FAIL、39 PENDING。这是历史检查点，不是后续动态进度来源。

## 中止现场

`ros.log` 的 Unix wall 时间 `1793100999.132603500`，即 UTC 2026-10-27 11:36:39.132603 / 北京时间 19:36:39.132603：

| 字段 | 保存值 |
| --- | --- |
| phase | ABORTED: flight guard: status_stale |
| supervisor wall monotonic | 2331.182791 s |
| status 最近回调 monotonic | 2328.866957 s |
| status wall age / limit | 2.316 / 2.000 s |
| odometry 最近有效回调 monotonic | 2331.015624 s |
| odometry wall age / limit | 0.167 / 0.500 s |
| supervisor 缓存 ROS now | 51.752 s |
| 转换后 odometry header | 51.736 s |
| 保存的 status DDS timestamp | 1793100995466084 us |
| 保存的 PX4 状态 | armed=2、nav=14、failsafe=false、preflight=true |

这些状态标志是上一次已接收消息的值，不是中止瞬间 PX4 内部状态的独立证明。16 ms 的 ROS now/header 差不能证明 Gazebo 物理时间在整个 2.316 s 内正常推进。

`summary.json` 的 monitor 区间为仿真 0.1–52.0 s、follow 起点 17.652 s、wall_duration 115.554 s；`termination_reason=flight_aborted`、`monitor_success=false`、退出码 1。虽然已有基础运动证据使 `basic_flight_passed=true`，这不能覆盖最终中止，离线评价仍要求另做。原日志中有遮挡后的 HOLD、重新 FOLLOW，再次 HOLD 后 status guard 中止，不能把此前计划内遮挡 HOLD 直接当作 status 过期原因。

bag metadata 声明 60662 条消息。此次已实际解码全部五个选定 topic 的 25038 条记录：raw status 108、raw odometry 5023、转换后 odometry 5030、clock 13827、flight phase 1050；计数与 metadata 相符。这不表示其他 topic 已经验证。单文件 `rosbag_0.db3.zstd` 大小 352085153 B，zstd 完整解出 1143320576 B SQLite 副本；正常关闭及可解码仍不等于业务指标有效。

## 由 PX4 与 ROS 源码可以确定的机制

当前 PX4 HEAD 与正式环境清单均为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`。本次没有重新构建固件或修改源文件。

1. `Commander.cpp:1931–1945` 在 PX4 时钟距离上次发布至少 500 ms，或状态改变时，发布 vehicle_status；主循环没有新命令/动作时 sleep 10 ms（`:1977–1979`，间隔定义 `Commander.hpp:217`）。因此稳态名义为 2 Hz **PX4 仿真时钟**，RTF=0.5 时约每 1 s 壁钟一条，实际周期还包含调度延迟。
2. `dds_topics.yaml` 的 vehicle_status `rate_limit: 5` 是 uORB 转发频率上限；生成 `dds_topics.h:383–390` 将它转成 200 ms 的 subscription interval。它不会将 2 Hz 的源自动补成 5 Hz。高频 odometry 与低频 status 的新鲜度裕量不同。
3. `utilities.hpp:78–84` 创建 PX4 输出 writer 时使用 BEST_EFFORT、TRANSIENT_LOCAL、KEEP_LAST；metadata 中 status/odometry 的 offered QoS 相符。supervisor 和 adapter 均以 `qos_profile_sensor_data` 订阅，即 BEST_EFFORT、VOLATILE、有限队列。匹配是有效的，可靠重传没有因此启用。
4. `uxrce_dds_client.cpp:239–250` 明确把实体创建与数据发送分成 reliable / best-effort 流。主循环 `:658–678` poll uORB、更新发送，再运行非阻塞 XRCE session。同一 client 处理多个 PX4 输出，并非 status 专用可靠链路。
5. **存在不报告逐条错误的发送丢弃路径**：实际生成 `dds_topics.h:484` 先 `orb_copy` 消费该 topic 更新；`:490` 的 `uxr_prepare_output_stream` 若返回 INVALID，`:497` 的错误打印已被注释，代码没有在这个分支重新投递该样本。这只是由源码确认的可能机制，本次没有计数证明此分支实际发生，不能直接写成根因。
6. DDS 输出 `VehicleStatus.timestamp` 已做时钟变换：`uORB/ucdr/vehicle_status.h:53` 为 `topic.timestamp + time_offset`；`dds_topics.h` 从 `session->time_offset` 取偏移。`uxrce_dds_client.cpp:63–65` 根据 Timesync 结果更新偏移，`:684–701` 周期同步。因此 **DDS timestamp 不是原始纯 boot/sim timestamp**；即使只计算相邻差，也可能混入动态 offset 变化，不能直接称为 Commander 发布周期。
7. supervisor 在 `_on_status` 执行时保存 `time.monotonic()`，其 guard 使用接收回调的壁钟年龄。它的 ROS timer、各 subscription 在本节点的默认 executor 内调度。adapter 会重写 odometry header 为自己缓存的 ROS 时钟。故这些缓存时间戳与原始 PX4/Gazebo 物理时钟必须区分。

## 尚未排除的解释

| 候选机制 | 为什么能出现 status 旧、odometry 新 | 尚需证据 |
| --- | --- | --- |
| Commander 或整个锁步仿真按壁钟推进变慢 | status 源低频，高频估计输出仍可恢复/持续 | 已证实源 status 的仿真周期正常；壁钟正常性仍需独立物理 stats 与调度证据 |
| XRCE 准备流、UDP、Agent 或 DDS 的单条/局部丢失 | BEST_EFFORT 无逐条恢复，低频缺一次影响明显 | 多个独立接收者、源 ULog、传输/发送计数 |
| supervisor 本地 subscription/executor 延后 | bag/独立 observer 可能收到，而该回调未及时处理 | 同一源 timestamp 的接收对照；必要时独立版本 callback entry/exit 插桩 |
| 共同短暂停顿后不同频率的恢复次序 | 高速 odometry 在恢复后先更新，status 还没到下一个周期 | 原生 Gazebo stats、clock、raw 两路、observer 自身间隔与进程调度联合观察 |

“odometry 在中止前 0.167 s 更新过”限制了故障形态，但不能单凭这一点排除更早的共同短暂停顿。当前宿主有较充足内存余量，不能继续把新的 status-only 失败自动归因于内存。原 PX4/Agent 文本日志没有对应断连或错误，不足以排除源码中的静默丢弃或局部调度延迟。

## 已执行的只读审计与来源绑定

审计持有冻结工作区的独占锁与空闲窗口锁。隔离目录为 `/tmp/status_source_audit_68kicmlh`，文件系统 ext4；原压缩 bag 与 ULog 均为实际复制，不是硬链接。pyulog 1.2.2 仅通过 `pip --no-deps --target` 安装在该临时目录，未改 ROS/PX4 Python 环境。

SQLite 以 `mode=ro&immutable=1`、query_only、8 MiB cache 打开；SQL 的 `WHERE topic_id IN (...)` 在读取 blob 前过滤。只反序列化上述五个 topic，没有读取 RGB/Depth blob 或调用完整 evaluator。压缩文件必须整文件解压一次；实际解压 6.541 s，低于事先 2300 MiB 上限。完成后仅移除本次新建的准确 SQLite 缓存，保留独立源副本和小诊断文件；主版输出不含解压数据库。

| 来源 | 字节数 | SHA-256 |
| --- | ---: | --- |
| 原 ULog `11_34_50.ulg` | 20280101 | `2b711f9d9d3738be584c7688628d41511ed27d9acfb2c1a42c89591a748f8540` |
| 原压缩 bag | 352085153 | `ffc1a6926d6521d275037694e5a9a2b82f81be63bdc4bae9d762ddf1be9057fa` |
| 原 metadata | 23907 | `ed53022293502d4f9e5a72ccc43f828d0590761f795ba4dbcf47065fe15b4b59` |
| 本次临时解压 SQLite | 1143320576 | `8f63a0d0f0b6c91dcf7b8773ee09356ae9343902439b9e29bd7ac3fb53ec3716` |

`source_before.json`、`source_after.json` 与 `summary.json` 记录前后完整 fingerprint；独立副本的 SHA 与源相同。`selected_topics.jsonl` 保留每条消息及时间域标签，`abort_window.json` 保留原日志中止 wall epoch 前后各 5 s 的所有选定 topic 记录。

## 实际时序与推断边界

ULog 过滤解析得到 vehicle_status 183 条、timesync_status 70 条，未报告 logger dropout 或文件损坏。`logged_topics.cpp:150` 使用 `add_topic("vehicle_status")`，默认未另设采样间隔；timesync_status 在 `:168` 配置 1000 ms、最多三个实例。当前 rootfs 没有 `etc/logging/logger_topics.txt` 覆盖文件。过滤结果没有 vehicle_odometry 数据集，因此不能用此 ULog 评价 odometry 源发布连续性。

vehicle_status 源时间戳从 0 至 69.776 s，间隔中位数 0.504 s、最大 0.508 s；关键段依次为 50.620、51.124、51.628、52.132、52.632、53.140 s。51.628 与 52.132 s 两条的 arming/nav/failsafe/preflight 标志均为 2/14/false/true。由于 ULog 自己也是订阅者且仿真时钟可变慢，既不能把这些周期换算成固定壁钟周期，也不能将 ULog 无 dropout 解释为操作系统没有暂停。

| 事件 | recorder / 日志 Unix wall 秒 | 对应仿真时间 | 说明 |
| --- | --- | --- | --- |
| 中止前最后 status 入 bag | 1793100996.663033423 | 源 51.628 s；前一条 bag clock 51.628 s | DDS timestamp `1793100995466084`，与 supervisor 缓存相同 |
| supervisor 记录中止 | 1793100999.132603500 | 其缓存 ROS now 51.752 s | 这是原日志，不是 recorder 时间 |
| bag 首次记录 ABORTED phase | 1793100999.661583823 | 前一条 bag clock 51.760 s | 比中止日志晚 0.528980323 s |
| 下一条 status 入 bag | 1793101004.075309796 | 源 52.132 s；前一条 bag clock 52.136 s | DDS timestamp `1793100995970084` |

这两条 status 的 DDS timestamp 差为 504000 us，ULog 对应源差也为 504000 us；结合该段 timesync 的 estimated_offset `-1793100943838084 us`，可以绑定到同一相邻源周期，而不是从 DDS 相邻差盲推源时钟。两条 recorder 存储点相距 7.412276373 s，仅这两个存储点的源时间推进比约为 0.068；该值包含传输与接收延迟，**不是 Gazebo 原生 RTF 测量**。

在这段附近，全记录最大存储间隙分别为 clock 0.998057116 s、raw odometry 0.949473940 s、converted odometry 0.900957311 s；其时间区间有重叠。中止日志 wall 时刻，bag 已有的最近 clock 只有 51.728 s，落后该条记录 0.355245396 s；supervisor 的缓存为 51.752 s，说明两个接收者并非同时处理每条消息。bag 后续到仿真 52.136 s 才收到下一条 status；中止发生在相邻 status 的仿真周期尚未走完时。

因此源仿真周期正常与壁钟 status guard 触发可以同时发生，无需先假设本次丢掉了某条 status。原记录支持共同推进或接收变慢及低频 status 裕量被耗尽，但不直接确定变慢发生在 Gazebo、WSL、PX4 调度、XRCE/DDS 还是接收回调。它也不排除叠加的局部丢弃。原失败没有同期原生 Gazebo stats/进程调度与多接收者入口计时，不能从 bag 存储间隔唯一定位根因。

本次只形成诊断证据，不评分、不修改原 FAIL、不重试原槽。审计进程结束并清理解压缓存后，已明确向主代理释放重任务窗口；后续独立同参数 probe 的 ROS observer 与原生 Gazebo stats 只用于验证可恢复性和补充机制证据，不回填本次原失败。
