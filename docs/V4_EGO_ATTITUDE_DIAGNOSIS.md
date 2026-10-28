# nav01 无人机姿态与相机变换失效诊断

诊断对象为 `results/frozen_fullplan_v4_nav01/reliability_v4_nav_car_clean_seed00`，这是保留的 FAIL 探针。本文不改写其结论，不向运行时注入由真值拟合的修正。新增结果为 `px4_camera_timing_diagnostic.json` 及 `.vehicle_only_input.json`，脚本为 `scripts/diagnose_px4_camera_timing.py`。

## 关键结果

| 固定接收时间区间 | 零偏移姿态 RMSE | ±0.5 秒扫描的最优 lag | 最优姿态 RMSE |
| --- | --- | --- | --- |
| 10 秒后 | 0.07955657 rad | +0.01 秒 | 0.07955456 rad |
| 16–20 秒 | 0.12331565 rad | 0.00 秒 | 0.12331565 rad |
| 17–20 秒 | 0.13054300 rad | −0.01 秒 | 0.13054223 rad |

lag 的定义是把标记为 `t` 的估计姿态和 `t+lag` 的无人机真值比较，负数表示估计落后于其标签。对失效附近的总姿态误差，单一时间偏移几乎没有收益，不能把问题主要归因于固定相机 TF 延迟。

17–20 秒的航向误差均值为 −0.12550511 rad（约 −7.19°），该动态区间最大绝对航向误差约 0.20335333 rad。12–16 秒的航向中位误差约 −0.09764611 rad。另作明确标记的诊断：去掉各扫描条件的中位航向偏差后，16–20 秒剩余航向残差在 lag=−0.14 秒时从 0.03824909 降至 0.02778931 rad。这说明偏差和次要动态相位因素可能并存；短时运动与估计收敛相互耦合，不能把这个离线最优值当成可移植的在线延迟补偿。

## PX4 已报告较大的姿态与位置不确定度

17–20 秒，原始 `/fmu/out/vehicle_odometry` 的三轴姿态标准差中位数约为 `[0.00995, 0.00526, 0.15758]` rad，航向相关轴的最大标准差约 0.19138 rad。位置标准差中位数约 `[0.10776, 0.10760, 0.17162]` 米。姿态方差在消息定义中表达于机体坐标，因此不能直接把三个分量无旋转地当作世界欧拉角方差；上述量级足以说明固定 0.05 米的位姿误差项不充分。

对于约十米的可见目标视线，仅 0.1576 rad 的航向不确定度就可能产生米量级横向投影不确定度。运行时应从 PX4 原始位置、姿态方差传播至 ROS 里程计，再通过 `J_pose Σ_pose J_poseᵀ` 加入每次三维观测协方差。不同图像共享的里程计误差存在相关性，这个传播不证明测量独立，也不能通过放宽时效门限消除问题。保持原有观测 0.60 秒、预测 0.75 秒和异常门控，分别消融环境磁场与协方差传播。

## 世界磁场与固件 WMM 不一致

已记录世界声明零航向 ENU，位置为纬度 `47.397971°`、经度 `8.546164°`，原磁场为 `[6e-6, 2.3e-5, -4.2e-5]` 特斯拉。其东偏磁偏角为 `atan2(E,N)=14.62087399°`。

实际编译当前钉住的 PX4 官方 WMM C++ 查表程序得到：

| 项目 | 固件 WMM 值 |
| --- | --- |
| PX4 commit | `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` |
| 磁偏角 D | `3.40576529503°` |
| 磁倾角 I，向下为正 | `63.1574668884°` |
| 磁场强度 | `4.82388168166e-5 T` |
| 一致的 ENU 磁场 | `[1.29398486953e-6, 2.17432866281e-5, -4.30411261194e-5] T` |

原环境偏角比固件预期大 `11.21510869°`，约 0.196 rad，与实测最大航向偏差量级接近。这只证明世界物理环境声明与固件预期不一致，尚未证明这就是 PX4 实际选用的磁传感器输入，更不能据此推断航向误差的主因。后续 mag-only nav02 仍保留约一米的初始横向偏差，并在约十九秒附近表面轨迹丢失；这一单项消融没有证明修改世界磁场消除了既有问题。需要进一步核实 Gazebo 磁传感器与独立 `sensor_mag_sim` 路径、设备 ID 和 EKF 选用实例。WMM 配置工具仍作为显式的仿真环境一致性修正保留，不作为已证实的闭环修复。

钉住源码 `src/modules/ekf2/params_magnetometer.yaml` 中 `EKF2_MAG_TYPE` 默认为 0（地面航向融合、飞行三轴融合），`EKF2_DECL_TYPE` 默认为 3（使用位置查表并在上锁时保存磁偏角）。诊断时共享 rootfs 的 `parameters.bson` 中有 `EKF2_MAG_DECL=3.40576505661°`，没有这两个模式的覆盖项。该文件是在 nav01 结束、尚未开始新试验时检查的，不能冒充原试验已经录制的完整参数转储；新增探针仍应保存运行参数证据。

## 实际磁源与 Gazebo 覆盖行为

补充源审查见 [V4_MAGNETIC_FRAME_CONTRACT.md](V4_MAGNETIC_FRAME_CONTRACT.md)。钉住的 PX4 `GZBridge.cpp:88` 默认订阅 Gazebo 磁源；独立 WMM 模块只有 `px4-rc.gzsim:198–201` 的 SENS_EN_MAGSIM=1 才启动，参数默认0。两条源都使用设备ID197388，`rcS:143–161` 的 CAL_MAG0/1_ID 仅为 AUTOCNF 校准预置，不能凭它判断实际 publisher 或 EKF 选择。

nav02 两个试验的四份已保存 BSON 均无 SENS_EN_MAGSIM 的非默认覆盖，日志明确启动4001和gz_bridge。这支持默认Gazebo源，但存档缺完整实际参数、模块列表与选用mag实例，不能把稀疏BSON当完整运行转储。

当前安装 Gazebo 8.15.0 的对应发布源码 `Magnetometer.cc:379` 只在初始化使用世界磁场；459–506行每帧从球面坐标读插件自己的旧磁表并覆盖该值。gz-sensors8.2.2的162–165行按传感器实际世界姿态逆旋转磁场。旧PX4桥接的 `[-y,-x,z]` 与这个对齐机体FLU传感器的任意姿态合同存在可解析验证的差异。已提供独立ENU/gauss+正确FLU→FRD补丁方案，仍待真实探针；它保留Gazebo/PX4两表偏角差约0.842°，不宣称世界向量已控制真实磁输入，也不宣称已有航向偏差已修复。

## 可复现的磁场配置工具

`scripts/configure_sim_magnetic_field.py` 的 `generate` 命令直接编译官方 `geo_mag_declination.cpp` 和 `geo_magnetic_tables.hpp`，校验 commit 与两个源文件 SHA-256。源码不作改写，只提供等价的标量 `math::constrain` 头，以避免依赖整套固件构建。结果保存在 `config/px4_wmm_reference.json`，输入与固件均采用 float32 查表精度。这个配置文件须与脚本一起进入新冻结版本。

```bash
python scripts/configure_sim_magnetic_field.py generate \
  --px4-root /root/PX4-Autopilot \
  --latitude-deg 47.397971 --longitude-deg 8.546164 \
  --output config/px4_wmm_reference.json
```

配置器只写显式不同的运行世界副本，保留原世界，并保存旧/新向量、地理位置、原/新世界校验和、查表来源和文件校验和：

```bash
python scripts/configure_sim_magnetic_field.py configure \
  --input-world SOURCE_WORLD.sdf \
  --output-world NEW_TRIAL/configuration/runtime_world.sdf \
  --evidence NEW_TRIAL/configuration/magnetic_environment.json
```

供 runner 调用的纯文件接口为：

```python
configure_world(source_world, runtime_world, evidence_json, lookup_json=DEFAULT_LOOKUP)
```

runner 应只在显式选择 `--magnetic-environment coherent_wmm` 时调用。工具拒绝改变位置却继续使用旧地点查表、非零航向/非 ENU 轴、未登记的固件来源或覆盖输入源世界。它不改变 EKF 参数、模型真值、目标位置、相机外参或任何实机设置。

## 源时间戳不能直接套用仿真时钟

3755 条 PX4 原始里程计中，`timestamp` 与 `timestamp_sample` 全部相等。首条二者为 `1793217716.465230 s`，接收 `/clock` 仅 `0.572 s`；日志记录 uXRCE 已同步偏移 `1793217715893230 us`。钉住的 `dds_topics.h.em` 和生成的 `uORB/ucdr/vehicle_odometry.h` 明确对两个时间字段都加上 `session.time_offset`，并非永远保留飞控启动时间。

原始同步时间还发生了跳变：在仿真 `11.052 s` 和 `23.452 s` 处，扣除相邻接收时差后的发布时差分别跳变约 `+11.298 s` 和 `+11.041 s`。在 `35.836 s` 处，一条时间突然回到启动/仿真域 `35.836 s`，下一条又回 UNIX 域。因此前五秒接收时间拟合出的单一仿射时钟映射未通过后续验证，报告中 `valid_for_source_timestamping=false`；这些仿射或直接源时间扫描不能解释为可用的修正结果。

nav01 所用 adapter 把里程计 header 设为接收时的 ROS `now()`，会丢失源采样时刻，但直接替换为当时同步的 `timestamp_sample` 会把 UNIX 墙钟与仿真 `/clock` 混用。在这个探针中两字段相等，所以仅替换字段也不能恢复先前没有记录的内部延迟。

可迁移方案应明确区分时钟合同：

- **Gazebo/PX4 仿真**：启动 uXRCE client 前显式配置仿真专用 `UXRCE_DDS_SYNCT=0`；钉住的 `GZBridge::clockCallback` 每次以 Gazebo `msg.sim()` 同步 PX4 单调时钟，确认 PX4 boot 时间与 ROS `/clock` 同域后，使用 `timestamp_sample` 作源时戳，接收时间另行保存。参数与映射验证结果必须录入试验配置。
- **实机**：保留经确认的 XRCE Agent/PX4 同步，ROS 与 Agent 使用一致的系统时间域；源采样时戳用于 TF，接收时戳用于传输健康检查，禁止使用仿真专用 boot/clock 假设。
- **其他时钟域**：由明确的同步桥或传感器时钟映射产生转换，并检测重启、回退、偏移跳变、漂移和未来时间。映射无效时拒绝该位姿参与采集时刻 TF；不得读取 Gazebo 真值修正时间或航向。

资料核对：[PX4 uXRCE-DDS 时间同步说明](https://docs.px4.io/main/en/middleware/uxrce_dds.html)、钉住源码 `src/modules/uxrce_dds_client/module.yaml` 的 `UXRCE_DDS_SYNCT`、`dds_topics.h.em` 以及 `src/modules/simulation/gz_bridge/GZBridge.cpp:331`。官方文档说明 XRCE 默认自动同步至 Agent OS 时间，部分仿真场合可禁用；原始nav01诊断没有改写adapter，后续开发接线如下。

### 后续 source_sim 接线的源码核对

新开发副本已新增 source_clock.py 和显式 source_sim 模式，与前述 nav01 诊断区分。`run_stage1_trial.py` 将同一模式写入 STAGE1_PX4_TIME_MODE、ROS adapter参数和参数证据；`run_stage1_flight.sh` 在执行PX4前 export PX4_PARAM_UXRCE_DDS_SYNCT=0。钉住 `rcS:129–136` 在 `rcS:324` 的 uxrce_dds_client start 之前导入环境参数；`module.yaml:88–97` 标记该参数需要重启。startup wrapper 只在rcS之后 show值，不能在这个位置才改变它。receipt模式显式恢复值1，避免先前试验持久参数串扰。

`EKF2.cpp:1684` 将 timestamp_sample 设为 imu_sample.time_us；1716行将 timestamp设为实际发布时的hrt_absolute_time。`dds_topics.h.em:126–140` 用session偏移序列化，生成 `uORB/ucdr/vehicle_odometry.h:53/58` 给两字段均加同一偏移。`uxrce_dds_client.cpp:206/317–322` 在建立session时选择同步或no-sync回调，后者69–72行将offset保持0。`GZBridge.cpp:331–345` 用Gazebo sim时刻同步PX4单调时钟，因此这种仿真专用合同有源码依据；还须实际录制确认两个时域在整个试验中一致。

新adapter使用sample源时刻作为Odometry header，receipt另存`/vehicle/odometry_timing`；对未启动时钟、错误时域、超过50ms的未来值、超过0.50s的旧值、sample晚于publication、重复及回退拒绝，不以now重新盖章恢复。时钟回退锁定无效并要求重启节点，避免混接TF历史。控制器继续保留既有新鲜度门。后续测试须包含完整仿真epoch、延迟/丢帧和TF采集时刻插值，不能仅凭parser测试声称闭环收益。

另一个独立边界是VehicleOdometry.reset_counter变化：位置或姿态坐标重置可能发生在时间仍单调时。新开发副本已增加 `frame_guard.py`：启动等待期间允许 EKF 的初始 reset；只有 adapter 实际通过 vehicle_ready/motion gate、准备发送有效运动命令时才锁定当前 reset epoch。缓存一条 valid 命令或 supervisor 的 WAITING 零速度命令不会提前锁定。

运动锁定后若 reset_counter 改变，frame guard 锁存失效；source clock 检测时钟回退时同样锁存失效。两者都会在 adapter 下一控制 tick 持续发送零速度 hold，保留 Offboard heartbeat，并禁止新的 valid 命令解除锁存，须显式重启/重新建立参考。这样无需等待既有里程计的0.50秒新鲜度窗口耗尽，旧世界命令也不会继续在新坐标中发送。未修改原有观测、预测或传输新鲜度阈值。`tests.test_frame_guard_motion` 的3项回归覆盖真实 adapter 的启动门、reset 后立即 hold 和时钟回退后 hold；实际飞行中的重置处理仍须后续探针验证。

## 验证与边界

本次只解压读取一次原始包，限定时钟、原始 PX4/ROS 里程计与无人机真值主题。保留的小缓存仅含无人机真值，目标真值和图像不进入诊断。已有 ego-only 前五秒平移标定与保留区间做法沿用，世界轴保持声明的 ENU 单位旋转，`base_link` 偏移 `[0,0,0.24]` 米仅用于离线真值点转换。

`tests.test_px4_camera_timing` 的四项测试核对 lag 符号、固定航向偏差不被主误差隐藏、时钟跳变使映射失效以及发布/采样时间区分；`tests.test_sim_magnetic_field` 的七项测试核对轴向、官方查表值、只改运行副本、源文件保护、坐标/位置/来源冲突拒绝和完整证据保存。新磁场环境、位姿协方差传播和时戳合同的实际闭环收益均应由后续预先登记的独立消融给出。
