# Humble 软件时延关联能力最小探针

本目录只测试一个能力：受控的 ROS 消息发布窗口，能否通过真实 DDS
`source_timestamp` 与原 executor 实际 take 得到的消息建立唯一候选关联。
不运行飞行、YOLO、原算法管线、Gazebo、PX4、Supervisor、arm 或原 fmu 话题。
不测物理 E2E，不改变历史 strict UNKNOWN，也不替代 280 次正式实验。

当前状态：首次 native 在错误的 ament FastDDS 版本查询处停止，0 事件、UNKNOWN。
非 ament 版本门已修复，当前只验证无 ROS 假对象；尚未重跑修后的 native 探针。

固定依据是原机 rclpy 3.3.22 的实际 `executors.py` 副本，其 SHA256 为
`cfd24d4952d061299d395820bfffae3afb95a87ac186ca131194be349846e7fd`。
该版本 `_take_subscription` 的真实局部变量是 `msg_info`，原函数先执行
`sub.handle.take_message(sub.msg_type, sub.raw)`，再仅返回 tuple 第一个对象；
原 `_execute_subscription` 仍以一个消息参数调用原 handler。本探针不虚构双参回调。

探针在调用原 `_take_subscription` 的当前线程临时设置 Python return profiler，
在原函数 return event 读取其实际 `msg_info`，然后恢复 profiler，记录元数据。
原 take 只调用一次，原消息、返回对象、参数、异常和 handler 保留。
已有 profiler 时不替换它，记录 UNKNOWN；观测异常不能覆盖原调用结果。
profiler 会增加该线程原 take 调用内所有函数的开销；没有低开销或无时间扰动承诺。

固定官方 rclpy 3.3.22 的 native take 只向 Python 暴露 source/received timestamp，
没有逐样本 publisher_gid。runtime gate 核对原 executors 文件与方法 SHA、rclpy 3.3.22、
rmw_fastrtps 6.2.10、FastDDS 2.6.12 和 RMW 标识；不满足则停止，不改原安装。
rclpy/rmw 继续通过真实 ament package.xml 核版本。FastDDS 是非 ament CMake 安装，
不再错误查询 ament 的 fastrtps；从实际 `/proc/self/maps` 唯一 FastDDS 库映射推导
同一安装前缀下 `share/fastrtps/cmake/fastrtps-config-version.cmake`，要求库文件名
版本和唯一 literal `PACKAGE_VERSION` 均恰为 2.6.12，且配置原字节 SHA 必须为
`8edb8f6935ce6eb8e383c40d785156fcca62f3834852e5a0cb8f5377d3bd5001`。
没有/多个/已删除映射、非 versioned 库名、缺文件、错误版本或 SHA 均停止为 UNKNOWN，
不回退到另一份无关的已安装配置。UNC 实读的小版本配置副本在 `version_metadata01/`；
大库只读文件元数据，没有读取 payload 或计算 hash，故仍非运行库完整认证。
本探针不安装或扩展 RMW，不读图像、bag、weights，不创建后台 owner 或触发器。

无 ROS 验证命令（Windows 或 Linux，标准库即可）：

```text
python -m unittest discover -s tools/diagnostics/humble54_timing_capability_probe01 -p test_probe.py -v
```

只有当前重任务及真实子进程全部退出、具备独占空闲窗口后，才在原 UAVHumble22
已经 source 好的原 ROS 环境执行下面的小 CLI。`--domain-id` 必须是独占未使用的值；
示例 211 只是占位，运行前核实。输出路径必须尚不存在，不覆盖任何旧记录。

```text
python3 tools/diagnostics/humble54_timing_capability_probe01/probe.py native --domain-id 211 --output /tmp/humble54_timing_capability_probe01_run01 --messages 8 --timeout-s 20
```

CLI 只在本进程设 `ROS_LOCALHOST_ONLY=1`、独立 domain 和唯一随机新 topic；所有节点
和 publisher 生命周期由本进程创建/保存。先做单 writer，再做真实双 writer 竞争负例。
每次发布均使用相同完整 PoseStamped 内容和相同 header，原 publish 前后记录
realtime/monotonic 成对锚点；每次 take 保留原始元数据、完整消息 CDR 字节、对象血缘。
订阅 handler 仍是原注册函数，记录实际接收对象是否与 take 原返回对象相同。
图谱在发现、每次 spin、各阶段开始/结束多次采样，保存全部 endpoint GID/名称/QoS。
图谱和自有 writer 清单必须包围该阶段全部数据，图谱采样最大间隔默认 200 ms；
缺时间证据、采样间隔超限或未登记的 publish writer 均拒绝候选。

图谱轮询不能证明采样间绝不存在短暂外部 writer，因此输出只可称
`OBSERVED_CANDIDATE`；绝不输出 KNOWN，也不能把随机 topic 当安全隔离证明。
唯一自有 writer 的生命周期、全过程采样及源时间窗口是本受控能力实验的条件。
竞争 writer 即使发布窗口不重叠、内容完全一致，也必须保留 UNKNOWN。

source_timestamp 非正/缺失/重复、窗口重叠或窗口外、锚点不一致、竞争/未知 writer、
整消息不一致、元数据丢失及一 publish 匹配多个 take 都保留 UNKNOWN。
take 必须具备真实整型（排除 bool）monotonic 时钟且满足
`0 <= entered <= exited <= recorded`；publish 的两锚点也必须整体有序。
若 publish 开始晚于 take 已结束，则拒绝候选。take 可以与同步 publish 重叠，
不能要求 publish 完成早于 take 进入。上述只是必要因果门，不会提升为 KNOWN。
默认时间编码窗口不确定度为 2 ns，锚点偏移容限为 100 μs，均写入结果；
这是受控探针的显式判定参数，不能证明小于容限的时钟跳变不存在。
时钟关联只用于候选配对，不据此计算或命名整条算法 E2E。

退出码 0 表示本次单 writer 所有消息得到候选、真实竞争负例均被拒绝且对象一致；
退出码 2 表示能力未观察到或运行/版本门失败。二者都不是项目验收 PASS/FAIL。
`raw_events.json` 与 `summary.json` 均为 UTF-8，含全部原始小消息事件与摘要 SHA 绑定。
DDS 清理前先保存 `raw_events_before_cleanup.json` 及强制 UNKNOWN 的
`summary_before_cleanup.json`；若清理原生崩溃，保留已观测事件，不能冒充终态。
记录实际加载库的相关 maps 行但不读大二进制计算 hash，因此不是运行库完整认证。
探针将原方法、环境及上下文清理恢复；进程原生崩溃可能来不及写终态，必须 UNKNOWN。
Humble 原 `executors.py:233–269` 的 `shutdown` 返回 bool；原始返回值保留在 cleanup，
只有 `True` 才算完成，`False`、非 bool 或异常均使终态 UNKNOWN。
尚未量化 profiler 开销、重传语义或原算法输入/输出透明性；这些属于后续独立工作。

独审前源码及旧回执完整保存在 `archive/pre_review_20261103T090726Z/`，其 SHA 与
原 `fake_validation_receipt.json` 一致。修后验证单独保存为 `fake_validation_receipt_v2.json`，
不会改写旧回执的来源字节。

首次真实 native 探针在 ament 查询 fastrtps 时停于 `rclpy.init` 之前，0 条原始事件、
UNKNOWN，不能作为能力验证通过。该次实际 source `4032859d…6db09`、当时测试回执和
4 份 native 输出均逐字节保存在 `archive/native01_source4032859_before_fastdds_fix/`。
非 ament 版本门修复仅完成无 ROS 测试，新的 native 执行仍由 root 在独占窗口安排。
