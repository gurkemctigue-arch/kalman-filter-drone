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

默认 DDS 配置已发布上述消息。版本化名称为 `/fmu/out/vehicle_local_position_v1`；`EstimatorStatusFlags` 与版本0的 `VehicleAttitude` 分别为 `/fmu/out/estimator_status_flags`、`/fmu/out/vehicle_attitude`。UAVHumble22 的小规模实际 import 已验证相应消息和字段可用，证据在 `D:/WSL/UAVHumble22-validation/logs/px4_message_bootstrap_audit.json`；这不等于已经验证实时消息流或原生起飞闭环。

`tests.test_startup_readiness` 的9项纯测试覆盖地面/空中对准区别、两个消息的独立时效、边界与未来时间、错误墙钟域、sample/publication 关系、有效性/融合/故障标志、缺字段及非法几何。它不运行 ROS/Gazebo/PX4。实际还须核对所用 estimator flags 与 primary estimator 一致；切换到多 EKF 时，不能默认实例0就是当前 primary。
