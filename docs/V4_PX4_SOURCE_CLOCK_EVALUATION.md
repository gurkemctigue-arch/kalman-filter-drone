# v4 PX4 原采集时间独立审计

`scripts/evaluate_px4_source_clock.py` 检查一次录制是否保留了 PX4 原采集时间，以及原始消息、适配器诊断和输出里程计能否一一核对。它不会从真值、目标轨迹或到达时间拟合时差，也不会修改在线消息、TF、原始 bag 或历史试验。

## 当前启动契约

`run_stage1_trial.py --px4-time-mode source_sim` 将模式同时写入 `run_config.json`、保存的 adapter 运行参数以及 `STAGE1_PX4_TIME_MODE`。`run_stage1_flight.sh` 的 PX4 分支在启动 rcS **之前**导出 `PX4_PARAM_UXRCE_DDS_SYNCT=0`，避免 XRCE 将模拟源时间改为 Agent UNIX 时间。`px4_stage1_startup.sh` 在正常 rcS 返回后只显示这个参数，并不在 client 已启动后才改变时间模式。历史 `receipt` 模式仍显式设置为 1，不属于本审计的通过范围。

adapter 的 `source_sim` 要求 `use_sim_time=true`。它使用 PX4 `timestamp_sample` 生成 ROS odometry header，另保留 `timestamp`、callback 时刻 ROS 时钟和有效性原因。原有年龄门限保持 0.50 秒，允许未来误差 0.05 秒。源时间或 ROS 时钟倒退后，在线保护锁存无效，须重启节点，不能静默重设 TF 时间原点。

时间单调不能证明空间参考不变。新增 frame guard 从 raw `reset_counter` 检查局部位置/姿态估计是否重置：首次有效位置或速度命令之后锁定参考，锁定后 counter 变化（包括 255→0）将使里程计输出无效，直至节点重启。诊断分别记录 `source_time_valid`、`frame_locked`、`reset_counter`、`vehicle_frame_valid` 和 `vehicle_frame_reason`。因此可以出现时钟有效而空间参考已重置的情况。

## 调用

```bash
python scripts/evaluate_px4_source_clock.py TRIAL \
  --output TRIAL/px4_source_clock_report.json
```

CLI 只读取以下四个 topic，保留 `/clock` 的原始记录顺序和尾段：

- `/clock`
- `/fmu/out/vehicle_odometry`
- `/vehicle/odometry_timing`
- `/vehicle/odometry`

读取压缩 bag 复用现有临时解压机制，不向源 bag 旁写解压文件。虽然不会保留图像或真值，文件级压缩仍可能要求解压整个存储文件；应与仿真或编译错开。

纯接口不依赖 ROS：

```python
report = evaluate(records, config)
```

`records` 使用 `evaluate_stage1_flight.Record`，须保留 `/clock` 行、`record_sequence` 和来自已录制 `/clock` 的 `received_sim_s`。纯调用者负责提供真实录制顺序，不能把 header 当作接收时间。`config` 应来自 `recorded_configuration(trial)`；它强制要求实际保存的 `run_config.json`、`configuration/runtime_parameters.yaml` 和 `configuration/px4_parameters.json`。运行与 adapter 必须同时声明 `source_sim`，保存参数必须明确包含模拟时钟、两个源时间门限和三个输入/输出 topic，启动覆盖证据必须包含 `UXRCE_DDS_SYNCT=0`。当前源码默认值不能替代历史配置缺项。

## 三方核对与报告

原始 PX4 消息和 timing 诊断必须具有相同 `timestamp_sample/timestamp`。适配器输出必须具有相同的 sample header、`map/base_link` frame、转换后的位置、速度和姿态；相同 header 但来自其他样本的内容不能满足核对。PX4→ROS 的物理坐标转换复用已测试的纯转换函数，时钟接受/拒绝逻辑则独立实现，不调用在线 `OdometrySourceClock.resolve()` 来认可其自身诊断。

每一条诊断都检查原始时间整数、sample≤publication、重复样本、原有年龄/未来门限、源时钟/ROS 时钟回退和回退锁存。声明“accepted”不能代替这些检查。缺 raw、缺诊断、缺输出或内容不符都不能通过。拒绝错误域的在线行为是正确的保护行为，但这次存在错误时钟域的试验仍报告失败。

报告分别提供：

- `clock_domain_valid`：独立时间证据有效时为 true，错误域/倒退等为 false，证据不够为 null。
- `vehicle_frame_continuity_valid`：按 raw counter 和诊断中的锁定状态检查空间参考连续性；锁后重置为 false。
- `source_clock_pass`：仅整体 `evaluation_status=PASS` 时为 true；任一失败或证据缺项均为 false。
- `failures`、`incomplete_evidence` 与每条独立原因，不只统计成功消息。

时延单独列出采集→PX4 发布时间、采集→adapter callback、采集→raw recorder、callback→diagnostic recorder、callback→odometry recorder 和采集→odometry recorder。recorder 的接收时间使用最近已记录的 `/clock`，不是 rosbag 的 UNIX 时间；报告明确保留其 50 ms 量化容差。不会为了显示更低延迟把消息回填到源时间。

连续性区间从首个 raw PX4 的接收时刻直到**整个录制的最后 `/clock`**，同时检查 raw 和已匹配输出的 0.50 秒最大空档，包含开头间隙和停止输出后的尾段。首个 raw 之前的启动区间不在本判定范围。至少需要 3 个独立匹配样本，诊断自身重复发布不能填补丢失输出。返回码 0 仅对应 PASS；FAIL 或 INCOMPLETE 返回 2。配置缺失也会生成 INCOMPLETE 报告。

输出报告和逐条 `.frames.jsonl` 同时记录实际 evaluator 与 helper 的 SHA-256，配置证据另存 hash。这些 hash 不代替飞行源码的冻结 hash，不能据此声称历史飞行使用了当前源码。

新的 `run_reliability_v4.py` 将该评价作为每个槽位的首个独立评价阶段，核对报告 trial 路径、PASS 布尔条件以及 evaluator 和四个 helper 的冻结 hash。时钟 FAIL 会使工程槽位失败，INCOMPLETE 会保留为证据不足；时钟通过仍须继续满足导航、身份和云台条件。磁环境使用 `gazebo_enu` 及独立构建的 PX4 manifest；manifest 缺失时不会生成正式计划。历史 `coherent_wmm` 试验和已冻结版本不受此项前瞻接线影响。导航数值门限仍保持未登记，不能把时钟或进程成功转换成项目验收通过。

## 能力边界

该评价证明的是录制内的时间标签、可核对消息链和连续性条件，不能证明真实硬件的采样延迟、传感器标定或姿态精度。接近 receipt 的 source 数值不是独立时钟测量。空间 reset 检查依据实际 raw counter，但锁定起点仍使用 adapter 的 `frame_locked` 诊断；当前没有独立读取 `/tracking/command` 来验证“首个有效运动命令即锁定”。缺少此层核验不能表述成完整飞控状态机验收。

初始未锁定阶段允许 counter 随估计初始化改变。已锁定后不允许通过计数回绕、恢复旧 counter 或清除 `frame_locked` 来重新认可参考；发生空间重置时即使 `clock_domain_valid=true`，整体仍失败。相反，在线时钟正确拒绝错误域的试验仍不得写成时间验收通过。

单元测试在 `tests/test_px4_source_clock_evaluation.py`，覆盖时间域错误、无 raw/输出的自报诊断、错误 header/内容/frame、回退及其锁存、完整尾段丢流、延迟交付、缺接收时钟、空间 counter 重置/回绕、未锁定初始化、配置缺项和 evaluator provenance。单元测试通过不能替代新 source_sim 闭环录制；历史 receipt 试验不会被追认为 source_sim。
