# 原始软件管线独立计时台架

这是独立软件回放台架，运行冻结源码中的原始 detector、navigation estimator、controller、PX4 adapter。它不启动 Gazebo、PX4 SITL、飞行 supervisor，不解锁、不飞行。原始四个 `main()`、SingleThreadedExecutor、检测工作线程和实际消息对象保持原路径；观察代码只在各独立进程中安装和撤销钩子。

当前目录最初交付时只执行了 Windows fake 验证，尚无原生完整管线实测。原生运行状态应以独立输出目录的 `started.json`、原始 JSONL、日志、`summary.json` 为准，不能由测试通过推断。

## 测量对象与边界

指标为 `bench_rgbd_callback_to_adapter_callback_monotonic_ns`：

- t0：实际选入检测快照的 RGB 与 Depth 原始回调入口时间的较晚值。
- t1：原始 adapter 的真实 TrackingCommand 订阅回调入口时间。
- 中间必须连接实际接受的工作快照、原始推理发布、估计器实际接收对象、被接受的导航更新、实际预测快照、控制器本次 `_step` 的局部 `target`，以及原始 adapter 接收对象。
- 三条 DDS 边分别使用固定 c7 探针的原始 take 元数据、成对 realtime/monotonic 发布窗口、单写者图轮询与完整有类型字段比较。仅替换该探针私有模块中的 PoseStamped 字段校验函数，以支持三类真实跟踪消息；没有修改原探针文件或其匹配规则。
- 小消息逐字段、逐嵌套消息、逐序列记录。浮点数记录位表示，保留 signed zero 和可证明的 NaN payload；不使用 CDR padding 相等、`repr` 或图像摘要作为身份凭据。无法证明 scalar float32 NaN payload 时保留 UNKNOWN。
- 仅 `valid=True` 且 mode 为 VELOCITY/POSITION 的命令计入 FOLLOW 候选。HOLD、SEARCH、FAILSAFE、缺边和未被选中或未贯通的输入不会被当作有效跟随时延。

每条 DDS 边始终只有 `OBSERVED_CANDIDATE` 级别。原生 rclpy 在这里没有暴露可绑定的 publisher GID；轮询也无法证明瞬时外部写者绝对不存在。全链只有三条边均成立且全部局部对象来源成立时，才形成 `CANDIDATE_SOFTWARE_LATENCY`。不得改写为 KNOWN、原现场端到端时延或物理 E2E。历史 strict 1857/1857 UNKNOWN 不变，physical E2E 保持 NOT_OBSERVED。

回放发布机会按类型完整计数，检测器实际收到的每个 RGB 回调另列机会表。两者没有声称逐图像 DDS 身份连接；它们的数量差不能直接归因于特定丢包机制。报告保留全部 adapter 回调、各边 take/pub/UNKNOWN、非 FOLLOW、工作线程拒收和未形成候选的 RGB。median/p95/max 只描述候选子集；同一 RGB 首个候选时延另列，后续控制 tick 的值含旧信息年龄，不能当作新的独立图像处理时延。

图像对象表最多 8 项，作业快照表另限 8 项，每项间接持有 RGB/Depth，因此观察器至多持有 24 个图像引用（实际可重合）；其余小对象及待接收/预测索引最多 64 项。淘汰产生缺链而非 id 复用连接。事件使用有界非阻塞队列写入；任何丢事件、钩子错误、进程时钟域不一致、原 Executor.shutdown 非 True 或非正常退出均使全链 UNKNOWN/未完成。钩子本身会带来观察开销，本台架没有声称零开销。

## 输入与隔离

`person004_short01.manifest.json` 已从关闭的原 trial 小型元数据生成，绑定原计划、终态、捕获的完整 YAML、原始 YOLO11n 权重与所有录包文件的 SHA。生成清单时没有读取 bag/权重负载。显式 native 会读取并复核这些负载；只验证选定原权重，其他未选权重不加载。

只回放原始 RGB、Depth、CameraInfo、TF、TF static、`/clock`、原始 PX4 VehicleOdometry 与任务 phase/selection，按原记录顺序、时间间隔、原序列化字节发布。QoS reliability/durability 从原 metadata 读取，回放队列深度在清单中显式声明。禁止回放旧 tracking 输出、状态/确认消息、解锁标志、setpoint、truth。记录的原始 VehicleOdometry 是允许的环境输入：由原始 adapter 转换为隔离的 `/vehicle/odometry`，没有绕过转换回放旧算法结果或伪造已解锁状态。

所有输入和算法输出显式重映射到独立 `/bench/...` 命名空间，controller 命令直接接原始 adapter。adapter 原始 `require_vehicle_status=True` 保留，没有向它伪造状态；其 setpoint/heartbeat 只输出到 bench sink。实际 `/fmu` 发布者必须为零，原始节点构造任何未隔离 `/fmu` 端点前直接拒绝，主进程也持续扫描。

只在 `UAVHumble22`、独立 ROS_DOMAIN_ID 和 `ROS_LOCALHOST_ONLY=1` 中运行，复用现有项目机器锁。锁由 CLI 自己非阻塞获取，**调用者不要再用一个单独 flock 包住 CLI**。锁被采集器占用时退出，不与采集器并行。

压缩包使用冻结源码中原始 `open_bag_reader()`，其临时解压位置被限定到本次拥有的 native ext4 scratch；不会在原压缩包旁创建 `.db3`。源文件运行前后均复核 SHA。ROS 日志进入新的 bench 输出目录。异常或超时只清理本次启动的进程组，原始证据和历史结果不覆盖。

## 命令

以下默认命令不打开清单、录包或模型，也不会启动 ROS：

```powershell
python -B tools/diagnostics/humble54_pipeline_timing_bench01/bench.py
python -B -m unittest discover -s tools/diagnostics/humble54_pipeline_timing_bench01 -p test_bench.py -v
```

待采集器释放机器并完成独立审查后，在原 Ubuntu 会话显式运行短前缀。输出目录必须尚不存在，且位于冻结源码外：

```bash
bash /root/uav_tracking_fullplan_v4_humble54/scripts/ros_python.sh \
  '/mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble54_pipeline_timing_bench01/bench.py' native \
  --manifest '/mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble54_pipeline_timing_bench01/person004_short01.manifest.json' \
  --output /root/humble54_pipeline_bench01_short01 \
  --domain-id 211 --timeout-s 480 --drain-s 2 --cleanup-s 30
```

该清单以原速发布前 16000 个所选输入记录。原报告 follow_start 为 17.752 simulated seconds，录包约 752.5 wall seconds；前缀可能需要数分钟，是否产生 FOLLOW 候选只能由实测确认。启动前哈希和模型加载不属于 t0/t1 区间。若没有有效 FOLLOW、任何边为 UNKNOWN 或实测失败，保存实际失败，不缩小未知分母或回填结果。完整回放应在短前缀验证后，用新清单将 `record_limit` 明确设为 null 并分配新输出目录及足够 watchdog；完整回放不是本次 fake 测试的已完成事项。

`validation_windows04.json` 与测试日志记录补充清理和浮点标量修复后的实际本地验证，`source_sha256_windows04.json` 固定该次被测源文件与清单；它们不构成原生实验结果。windows01/02/03 留作先前版本的测试记录，不能用于当前源字节的验证。
