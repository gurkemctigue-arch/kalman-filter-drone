# 原生因果窗口导出工具交接

本工具只把已经关闭的原始 rosbag 中一段因果窗口的原始消息与图像导出到新的外部目录，不启动仿真、推理、轨迹关联重放或控制。它不修改原始结果，也不产生算法通过证书。本轮作者仅运行了 Windows 构造数据测试；真实原生读包由 root 在独立审查和运行空闲检查后另行安排。

冻结的两个文件位于 `D:/WSL/UAVHumble22-validation`：

| 文件 | SHA-256 |
| --- | --- |
| extract_native_causal_window.py | 9893f7d821e7f1ae6de9b6f966db3860dfac0aea7a14d58057a55282a45e9542 |
| test_extract_native_causal_window.py | 0ac6c4eeb7c2e4327176206e728e60ce2b8cbfd5d280f295b6fa39dc4e1e60d7 |

工具清单的 canonical SHA-256 为 `eff7665491f0a63db4bd75a0ccd70ac009b5ff058589e296b35c1008d860d3a7`。无参数或 `--describe` 只读取这两个工具文件，不打开实验、不导入 ROS。真实执行必须显式提供 `--execute-after-core-idle`、上述工具身份及七项原始输入的绝对物理路径和 SHA。这个显式参数只是调用方的调度声明，本工具不会自行证明系统空闲，也不是新的运行准入层。

作者最终收据 `extract_native_causal_window_author02.json` 的 SHA 为 `7cb275f12ac9cbf3e8e7e400deb4890057c86cdd5484b10e33c83a6d4423f67d`。其 34 项构造测试全部通过、原生进程退出码为 0，测试前后两个源文件身份相同。日志 `extract_native_causal_window_author02.log` 的 SHA 为 `4170a1684b93563f20f71eda25b6cc3a77146dd0605fa6f75c9273f80ec657c6`。`author01` 是保留的中间稿收据，不能替代 author02 或独立审查。

实际 42 调用已经整理为 `extract_native_causal_window42_invocation01.json`，SHA 为 `d53164c9a5ba5e8f657d60d0970ad0cf66c2be6fb47949f61b086cd593b3787c`；便于阅读的 shell 命令在 `extract_native_causal_window42_invocation01.command.txt`，SHA 为 `69b326de3bcf85a4307da82ece4af9acd09b3d35cb63d49392aef54bca028758`。生成这些文件时只对七个既有小 JSON 计算摘要，没有解码原始 core terminal，也没有打开压缩包、执行命令或构造 NativeRuntime。

七项绑定的选择位置如下；完整物理 Linux 路径和原始 SHA 均在 invocation JSON 中：

| 标签 | 选择的原始文件 |
| --- | --- |
| source_review | 外部 reviewed_freeze_review_v4_humble42_01.json |
| source_manifest | frozen42 结果根目录 / freeze_validation/source_freeze_manifest.json |
| plan | reliability_v4_humble42_probe01_seed004_matrix/plan.json |
| slot | 上述 matrix / slots/car_stage2_crossing_seed004.json |
| attempt | 上述 matrix / observed_driver01/09_car_stage2_crossing_seed004.attempt_terminal.json |
| core_terminal | 上述 matrix / observed_driver01/execution_terminal.json |
| contract | 外部 development_contract_core_reliability_v4_humble42_probe01_01.json |

root 的执行顺序是：审查最终工具和构造测试；确认仿真及其他大负载已停止；设置 Humble、实际 PX4 消息 overlay 和 frozen42 overlay；创建外部缓存父目录 `/root/uav_humble22/native_causal_cache`，并确认外部输出 `.../UAVHumble22-validation/humble42_native_causal_window01` 尚不存在；先运行 invocation 的 `metadata_preflight_argv`，成功后再安排 `native_export_argv`。两个 argv 都已经提供，准备文件本身不会执行它们。

小文件预检只调用 `validate(args)`：校验七项 pin、原计划/slot/attempt/停止 terminal/contract 间的绑定、必需源码和消息定义以及六项小录包证据；压缩文件仅核对文件类型、大小和既有完整性证据，不读取其 payload、不计算其摘要、不导入 ROS。预检还明确断言本次 42 的 FOLLOW 为 18.1 秒、窗口为源时钟 29.5–33.0 秒。它不是 native reader 或全源树复核结果。禁止把预检成功写成原始 FAIL 已修复。

42 的五个精确 RGB + Depth + CameraInfo 请求是 31.4、31.5、31.6、31.7、32.2 秒。窗口参数按 FOLLOW 偏移 `[11.4, 14.9]` 解释，而不是写死任意试验的绝对时间。41 必须另外提供其自身七项原始绑定、源根、trial、slot 和新输出；其 FOLLOW=17.652 秒，相同偏移得到 29.052–32.552 秒，并非 42 的同一场景帧。对 41 可显式选择自己的源时间帧或 `--frame-follow-offset-s`，不能擅自以最近帧替代缺帧。当前尚未生成实际 41 调用，也未验证 41 的真实七项元数据。

原始 42 slot 的 FAIL、核心统计 8 PASS / 1 FAIL / 3 PENDING、STOPPED_FAULT owner 及 Gazebo -9 错误均保留在输入副本和终态 manifest 中。工具不要求整个 core 或 owner 健康；它只要求当前选定录包已有真实关闭和完整性证据，允许对失败样本做离线诊断。校验的是所需冻结源文件和原 pin 的关系，不是重新对整个 698 文件源树做散列。

原生环境仅在真正执行时加载 `rosbag2_py`、rclpy 和 rosidl。Humble 和实际 ament prefix 必须一致；自定义 Python 消息类的解析来源必须在对应 frozen root 的 ros2_ws 内，字段名与归一化后的 wire type 都要匹配原始 .msg。PX4 类来源必须在显式的实际 px4_msgs prefix 内，不猜测父目录或放宽到其他工作区。实际小 import 探针由 root 单独完成：`humble42_native_import_probe01.json`，SHA `1e33908948015ab59721dba29708b9e2a21ae6612b75f2aca5f91865f51ec148`；其本机来源显示 PX4 位于 `/root/uav_humble22/px4_msgs_ws/install/px4_msgs`，自定义消息位于 frozen42 的 ros2_ws/install。此探针没有验证所有消息类型或 native 读包。

导出器通过 AST 从原 pin 对应的 `scripts/evaluate_stage1_flight.py` 只提取未改动的 `open_bag_reader` 函数，不执行模块顶层代码。其支持已关闭的 FILE zstd 原生读取，返回 reader 和 storage 信息。不要将原 39 的 telemetry-only 导出器审查说成该原生读包接口的审查。本工具独立测试仍不能替代 root 的真实 Linux 原生验证。

实际 I/O 为两次压缩文件串流摘要（读包前、读包后）和一次完整 native 消息遍历，不是总计只读一次磁盘。所有原始 topic 都计数，禁止 storage filter；遍历结果必须精确复现原有 topic counts。默认不反序列化真值；只有显式 `--include-offline-gt` 才导出，并标记只能离线解释，绝不反馈给运行系统。

每次 native 读取创建工具独占的临时目录，原 reader 的解压与复制只能落入该目录。缓存预算覆盖原始解压大小加压缩包复制回退；42 这一包约需 2.57 GiB，默认上限 4096 MiB。收据保留 owned 路径、close API 是否存在及调用结果、目录是否删除、全局 tempfile.tempdir 是否恢复。调用方与包装器释放 reader 引用，借用上下文退出后再回收和清理；读取、关闭或清理错误都留下 partial 结果。没有 close API 时只如实记录引用释放，不宣称实际 close 被调用。

默认限额为：单个压缩包 1024 MiB、缓存 4096 MiB、导出数据 128 MiB、单条消息 16 MiB、原生消息 1000000 条、选中事件 20000 条、轨迹 64 个。参数允许在固定硬上限内缩放，不能无限扩大。预算耗尽后保留失败 manifest 和已写出的 partial 文件，不覆盖、不续写、不回滚原记录。终态 manifest 在数据预算外，确保错误仍可记录。

输出包括：七个原始输入的逐字节副本、events.jsonl、所选消息的原始 CDR、原始完整 RGB/Depth 像素与 CDR 及尺寸/step/encoding/endian 元数据、image_requests.json、track_anchors.json 和 manifest.json。只要精确源 stamp 对应的任一 RGB/Depth/CameraInfo 缺失或重复，就保留 unknown 状态及全部重复件，不插值、不缩放、不改编码、不补帧。CameraInfo 原消息和内参完整保留。

窗口内保留所有候选和整个 track snapshot，包括 last_measurement_s、三维观测与协方差，以及 surface/nav 状态和控制边界。每条事件分别记录原始 header 整数纳秒、原 acquisition/output 浮点字段、仅用于窗口比较的派生整数、native bag record 纳秒和最后一条已记录 /clock 代理。这个 /clock 代理不是生产端接收时刻，不可将 recorder wall clock 减去仿真时间当端到端延迟。

迟到但首次观测到的源采集帧可以进入窗口；已见过的采集身份或旧 header 不会仅凭旧时间戳把窗口后的定时缓存全部导出。实际仍落在窗口的 publication/output/记录时钟状态照常保留。TF 还检查各 transform 的原始 stamp；tf_static、初始选框、场景配置和飞行 phase 作为标注清楚的原始全局上下文保留。边界事件不当作窗口内的新观测。

track anchors 的 first_observed 只表示本包中首次看到的完整快照，不擅自声称轨迹真实诞生。关联前私有预测器状态、未发布的 pairwise gate 分数及未观测到的 rejected scores 标记 NOT_OBSERVED；不声称精确重放关联或已经确定错误根因。真实导出后应先核对 last_measurement、全部候选几何与控制状态的时序，再判断 31.6 秒后的 LOST 是重复候选、真实交叉还是其他机制；证据不足就保留未知。

成功终态 `COMPLETE_RAW_EXPORT_ONLY_NOT_ALGORITHM_ACCEPTANCE` 仅代表此次原始导出完成，并且原小文件 pin、生成消息模块 pin 和压缩 payload 在前后核对中一致。任何异常终态为 `ABORTED_PARTIAL_ORIGINALS_RETAINED`。原试验的工程 FAIL 和 owner 错误不因导出成功而改变。
