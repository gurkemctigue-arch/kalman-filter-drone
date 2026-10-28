# PX4 原生起飞初始化与 Offboard 接管合同

本页记录 opt-in 原生起飞模式的源码依据和纯 readiness helper。默认旧启动模式保留；原生模式的 supervisor、参数、录包接线与实际飞行结果由新的独立试验分别验证。它不改变磁融合模式，不放宽 active Offboard 的 reset 或 source clock 保护，也不读取目标真值。

钉住的 PX4 commit 为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`。地面对准完成后再固定多等几秒，无法消除标准的首次空中磁对准：`EKF/aid_sources/magnetometer/mag_control.cpp:51–54` 在起飞时清除 `mag_aligned_in_flight`；362–373 行在 HAGL 超过 1.5 m 时请求 yaw reset；452–455 行在空中重置后置位该标志。`EKF/ekf.h:247–255` 的 `isYawFinalAlignComplete()` 还要求置位后超过1秒。`EKF2.cpp:1617` 将其发布为 `VehicleLocalPosition.heading_good_for_control`。因此该最终完成标志不能作为地面起飞前置条件。

原生路径让 PX4 完成起飞和预期的初始化，然后接管：

1. 在 disarmed 状态，确认 PX4 preflight、同域新鲜里程计、地面 tilt/yaw 对准和有效 GNSS 援助。
2. 请求 `VEHICLE_CMD_NAV_TAKEOFF`，确认接受/进入 `AUTO_TAKEOFF` 后再 arm。官方 `Commander.cpp:335–344` 的 CLI 也是此顺序；1064–1073 行只切 takeoff mode，不自动 arm。
3. 起飞期间保持 Offboard heartbeat 和安全零设定值，但不请求 Offboard，不锁定 active Offboard frame epoch；PX4 自身控制起飞和正常 yaw 初始化。
4. 等待 armed `AUTO_LOITER`、有效 GNSS/局部状态、最终空中对准，以及实际高度和速度满足 supervisor 的连续 settle 条件。
5. 清理起飞前缓存的控制参考并明确建立视觉任务/导航 epoch，再请求 Offboard；接管后任何 reset 仍按原合同 hold/restart。

`navigator_main.cpp:598–638` 将 NAV_TAKEOFF 的 param5/6 任一非有限值解释为当前机载 global 位置；param7 原样传递。`navigator/takeoff.cpp:184–194` 在 param7 非有限时使用当前机载 global altitude + `MIS_TAKEOFF_ALT`。因此参数应明确写 NaN，不能沿用 ROS 消息的零默认值，把 0 m AMSL 或经纬度零当成目标。`navigator_main.cpp:621–623` 还明确将 takeoff yaw 设为 NaN，交给能处理 yaw reset 的 FlightTaskAuto。

`Commander.cpp:2024–2038` 在 takeoff 完成后转 `AUTO_LOITER`，除非 `COM_TAKEOFF_ACT=1` 且存在可用 mission。新试验须显式配置/归档 `MIS_TAKEOFF_ALT` 和完成动作。已接受并起飞后不得不断重复发送 param7=NaN 的 NAV_TAKEOFF，否则可能再次以当前高度加起飞高度更新目标；重试、ACK 和 phase 约束由 supervisor 负责。

纯合同入口位于 `uav_tracking_px4_adapter/startup_readiness.py`：

```python
readiness_issues(local_position, estimator_flags, now_s,
                 require_inflight_alignment=False) -> list[str]
```

`now_s` 是 ROS `/clock` 仿真源时刻。返回空列表仅表示这两个辅助消息满足该时刻的 readiness 条件；armed/AUTO_LOITER、命令 ACK、wall liveness、实际高度/速度和持续 settle 由 supervisor 独立检查。

| 数据 | 源时效合同 | 必须满足的条件 |
| --- | --- | --- |
| `VehicleLocalPosition_v1` | sample、publication 均不旧于0.50秒、不超前0.05秒，sample不晚于publication | xy/z/vxy/vz valid，xy/z global，有效有限位置/速度/heading，非 dead reckoning |
| `EstimatorStatusFlags` | sample、publication 均不旧于1.50秒、不超前0.05秒，sample不晚于publication | tilt/yaw align，GNSS pos/vel 融合，非 inertial/wind dead reckoning，非 GNSS/mag fault 或磁场扰动 |
| 最终 handoff 附加条件 | 同上 | `heading_good_for_control`、`cs_in_air`、`cs_mag_aligned_in_flight` |

flags 的独立1.50秒门来自实际源码发布合同：`EKF2.cpp:1882–1903` 名义每1秒发布一次，控制/故障/创新状态改变时立即发布；DDS 的5Hz是上限，不能当作实际5Hz更新。若把这个低频辅助消息也要求每0.50秒连续新鲜，就无法可靠累计1秒 settle。此门仅用于启动 readiness；原里程计0.50秒、目标观测0.60秒和预测/控制0.75秒门保持原样。所有缺字段、非法时刻、错误时钟域和 NaN 几何均为等待理由，不默认为健康。

原生启动流程使用两个独立预算，均从确认 armed AUTO_TAKEOFF、进入 `NATIVE_TAKEOFF` 的同一个控制 tick 起算：`native_takeoff_timeout_sim_s=40` 限制 PX4/ROS 源时间流程，`native_wall_timeout_s=180` 限制实际单调墙钟等待。原 legacy `takeoff_timeout_s=40` 继续用于旧 Offboard 起飞模式。低实时率仿真不再把40秒墙钟误当40秒物理过程；源时钟回退或非法值不会重启预算。

ROS-time 的20Hz控制 timer在 `/clock` 停止时也会停止，因此 native 模式另建0.10秒 `ClockType.STEADY_TIME` timer，独立检查180秒墙钟上限。超时立即锁定 ABORTED、发布无效零速度命令和 phase证据，停止接管；PX4当时仍由原生模式控制。这个 watchdog 不更改里程计、目标或 frame reset门。实际超时原因明确为 `native_source_budget_exhausted` 或 `native_wall_budget_exhausted`，源时钟回退单独记录。

phase证据在最终 `source_sim_s` 前记录 `phase_wall_monotonic_s`、`native_started_source_s`、`native_started_wall_s`、`native_elapsed_source_s`、`native_elapsed_wall_s`。成功进入 REQUEST_OFFBOARD或失败退出native流程时冻结双elapsed，后续HOLD/FOLLOW/ABORTED不继续累计原生启动耗时。离线审计分别核源时间与单调墙钟，不通过实际RTF拟合把两者互相替代；新预算参数须显式写入录制的runtime配置。

### VehicleStatus 的源时效与接收停流

Humble04 行人 clean 探针在 `source_sim_s=5.652`、状态源戳5.152秒时因接收墙钟龄2.010秒超过旧2.000秒门而中止；源龄实际只有0.500秒。设定RTF0.5不能证明每段执行都达到该实时率，因此不能用 `1 / requested_RTF` 推算源时效。该失败冻结和原始录包保留，不回改判定。

新版本默认仍为 `status_timestamp_mode=receipt_wall`、`status_timeout_s=1.0`，保留旧接收墙钟语义。`source_sim` 运行显式配置 `status_source_max_age_s=1.0`、`status_source_max_future_s=0.05`，以 `VehicleStatus.timestamp × 1000` 与 ROS `/clock` 纳秒比较；这与原 adapter 和独立启动审计的状态源时效一致。复用源时钟验证器拒绝非法、过旧、未来、重复和回退的状态消息，它们不刷新已接受状态或接收墙钟；PX4源戳或ROS时钟回退锁止至节点重启。控制tick仍检查已缓存状态的当前源龄，不能因没有新callback而永远健康。

source模式独立配置 `status_timeout_s=10.0` 作为有效状态消息的接收墙钟停流上限，同时保留原1.0秒源龄门。这个停流检查只在ROS-time控制tick执行；暂停 `/clock` 时不保证10秒墙钟即触发。它与上文独立steady timer执行的180秒原生启动总预算是两件事，不能混称。运行参数和 `run_config.json` 同时存储模式、源龄/未来界、10秒墙钟界及设定RTF，正式runner逐项核对；不修改里程计0.50秒、目标观测0.60秒、预测0.75秒和frame reset保护。独立native审计仍用原1.0秒/0.05秒VehicleStatus源门。

默认 DDS 配置已发布上述消息。版本化名称为 `/fmu/out/vehicle_local_position_v1`；`EstimatorStatusFlags` 与版本0的 `VehicleAttitude` 分别为 `/fmu/out/estimator_status_flags`、`/fmu/out/vehicle_attitude`。UAVHumble22 的小规模实际 import 已验证相应消息和字段可用，证据在 `D:/WSL/UAVHumble22-validation/logs/px4_message_bootstrap_audit.json`；这不等于已经验证实时消息流或原生起飞闭环。

`tests.test_startup_readiness` 的9项纯测试覆盖地面/空中对准区别、两个消息的独立时效、边界与未来时间、错误墙钟域、sample/publication 关系、有效性/融合/故障标志、缺字段及非法几何。它不运行 ROS/Gazebo/PX4。实际还须核对所用 estimator flags 与 primary estimator 一致；切换到多 EKF 时，不能默认实例0就是当前 primary。

## 独立离线启动审计

新入口是 `scripts/evaluate_native_startup.py TRIAL --output TRIAL/native_startup_evaluation.json`。它提供不依赖 ROS 的 `evaluate(records, config)`，CLI 才惰性导入 ROS 读包；本次开发只运行纯 fixture，没有读取实际 rosbag。正式 runner 将其列为必需评价。

审计使用录制的 run_config、runtime_parameters、参数覆盖 manifest，并解析 `px4.log` 中真实 `param show` 的 `MIS_TAKEOFF_ALT=3`、`COM_TAKEOFF_ACT=0`、`SENS_IMU_MODE=1`、`UXRCE_DDS_SYNCT=0`。声明参数不能代替实际值证据；缺省或来源不全为 `INCOMPLETE_EVIDENCE`。它独立检查 NAV_TAKEOFF 的 param4–7 均为 NaN、先命令切入 AUTO_TAKEOFF 再 arm、armed AUTO_TAKEOFF→AUTO_LOITER→Offboard 顺序、无提前 Offboard 或有效视觉任务。

phase String 在保留原 `PHASE: reason` 前缀后，追加唯一的 `; source_sim_s=<源时刻>`。新 native 审计要求此字段有限、单调，且对录制 `/clock` 的年龄在 −0.05至0.50秒内；没有该字段的旧录制不能靠接收时间推断源时刻。REQUEST_NATIVE_TAKEOFF 的地面目标锚点、REQUEST_OFFBOARD 前完整1秒的 settle 窗口均以显式 phase 源时刻定义。数据必须已在对应 phase 之前录制，不能借助之后到达的同时间标签消息。

handoff 窗口采用20Hz离线检查，以录制 VLP、EstimatorStatusFlags、VehicleStatus 和适配后里程计独立确认最终 heading、融合/故障标志、源时效、armed AUTO_LOITER、0.18米位置容差与0.20m/s速度上限。它不调用在线 readiness helper，也不读取 GT 或拟合坐标偏差。完整 `/clock` 末尾仍纳入状态流覆盖检查；后续 ABORTED 或静默尾段不能因前面完成过接管而消失。

报告包含固定9项 checks、failures、incomplete_evidence、逐点 settle sidecar，以及实际脚本和唯一直接本地依赖 `evaluate_stage1_flight.py` 的 SHA-256。只有全部 checks 明确为 true、两个问题字典均为空才 PASS，CLI 返回0；FAIL或证据不足返回2。新的双预算审计还要求起点恒定、elapsed与原时钟相符、接管不超过任一预算且完成后不再变化；缺墙钟证据为证据不足。一次成功录制本身不能证明暂停clock时steady timer确实运行，后者由实际代码来源和独立callback专项验证。

`tests.test_native_startup_evaluator` 的19项纯测试覆盖成功流程、真实/声明参数差异、命令/模式顺序、完整 settle、源时效、提前视觉、失败/静默尾段、缺流、phase源时刻、双预算与CLI来源记录；`tests.test_native_takeoff` 的13项节点级fixture覆盖原生状态机及源时间慢速流程、暂停ROS clock时独立wall callback、回退拒绝和完成预算冻结。它们只证明合同与实现逻辑，不能替代新版本实际原生起飞与后续闭环验收。既有Humble03冻结及其结果保持原样。
