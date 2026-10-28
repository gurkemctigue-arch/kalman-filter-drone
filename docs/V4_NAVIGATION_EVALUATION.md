# v4 地面足迹导航参考与物理跟随评价

本页对应新增 `scripts/evaluate_navigation_reference.py`。它只做离线评价，不向检测、关联、导航滤波或控制器提供真值。v3 冻结源代码、试验和旧版 `evaluate_follow_dynamics.py` 的模型原点指标不作改写。

## 评价参考与必需证据

v4 控制参考为目标的地面足迹中心，运行配置须记录 `control_reference=ground_footprint`。运行时几何来自 RGB-D、采集时刻 TF、运动方向与已声明的通用尺寸先验，不能把 v3 真值标定偏移作为运行时补偿。

离线目标真值采用目标模型在地面的原点。无人机被控制点为 `base_link`，不能把无人机模型原点直接当作该点。试验必须显式保存 `vehicle_control_point_offset_flu_m`；当前模型的声明值为 `[0,0,0.24]` 米。评价器在每一时刻以独立真值姿态旋转该偏移，再加到无人机模型原点上。这个声明仅用于离线真值转换，不是目标关联或运行时导航的输入。

CLI 拒绝缺失、相互矛盾或不能建立坐标语义的证据，要求：

- `run_config.json` 中的地面足迹模式、目标类别和显式无人机控制点偏移；
- `configuration/runtime_parameters.yaml` 中实际使用的期望距离、高度与零 `desired_offset_m`；控制器订阅 `/tracking/navigation_state`，检测和估计均启用导航，估计帧为 `map`；
- 原始时效门限保持观测 0.60 秒、预测/控制 0.75 秒；
- 已记录世界 SDF 中声明 ENU 且航向为零；不以当前源文件代替缺失的历史运行世界；
- `/vehicle/odometry` 为 `map → base_link`，具有有限的位置、姿态；独立无人机真值能提供至少十个校准配对及后续保留区间。

地图到真值世界的轴向由上述 ENU 源合同决定，旋转固定为单位阵。平移只由无人机前五秒里程计和独立无人机真值的分量中位数冻结，随后报告无人机保留区间误差。目标位置、目标误差、尺寸先验和后续表现均不参与这个变换的选择或重新拟合。

## 输入与调用

纯函数接口不读取文件、不启动 ROS：

```python
result = evaluate(records, config, physical=None, events=None)
```

`records` 为 `evaluate_stage1_flight.Record` 序列。核心主题为 `/tracking/navigation_state`、`/tracking/navigation_diagnostics`、`/tracking/status`、`/tracking/selection`、`/tracking/flight_phase`、`/vehicle/odometry` 与 `/ground_truth/*`。原有 `/tracking/state` 仍承担可见表面轨迹、身份和云台用途，本评价器不把它当作地面导航状态。

在 ROS 工作空间已经 source 后，从项目根目录运行：

```bash
python scripts/evaluate_navigation_reference.py results/TRIAL \
  --target-class car \
  --output results/TRIAL/navigation_reference_evaluation.json
```

多目标试验须附带由初始 REQUEST 框独立确定的任务到物理目标映射：

```bash
python scripts/evaluate_navigation_reference.py results/TRIAL \
  --target-class person \
  --physical-identity-report results/TRIAL/physical_identity_evaluation.json \
  --output results/TRIAL/navigation_reference_evaluation.json
```

映射接口为 `physical["tasks"][target_uuid]["initial_mapping"]["physical_id"]`。未知映射保留为空；不根据预测位置、最近目标、轨迹 ID 或最终跟随对象猜测真值。一次新选框立即建立新的评价任务，旧任务的有效状态不能填补新任务。

CLI 只在执行时读取 rosbag，临时扩展所读取的主题并恢复原主题表。JSON 报告之外生成 `.frames.jsonl`、`.raw_frames.jsonl`、`.message_frames.jsonl` 三个逐帧文件。原始包保持只读。

## 原始导航与滤波状态

`raw_navigation` 对导航诊断中的 `acquisition_s + target_uuid + track_id` 去重，保留首次发布。定时器重复发送前一个图像的诊断不会产生新观测。`output_s` 是无 ROS header 的诊断消息的源时间；操作时间取它与记录/接收时间的最大值，避免 `/clock` 采样略晚或略早造成错误回溯。

`raw_navigation.metrics.position_error_m` 比较原始地面足迹测量和同一采集时刻的独立目标真值。`velocity_error_mps` 仅比较同一任务、同一轨迹、相邻且间隔不超过 0.75 秒的两次有效位置的割线速度，与真值在完全相同区间的割线速度；首次观测、拒绝观测、换轨或间隔过长不产生速度样本。这是区间平均速度，不等于瞬时 KF 速度。几何有效性和融合门控分开统计：原始几何准确但被滤波门控拒绝的观测仍可评价原始几何。

`raw_navigation.valid_reference_coverage` 的分母是已记录的去重图像采集机会，仅表示这些观测内的几何有效率。它不宣称覆盖了没有发布消息的图像或整个时间轴。`invalid_reason_counts` 记录实际不可用原因；`diagnostic_reason_counts` 保留几何/融合诊断码，包括有效和接受的诊断。

`kf_navigation` 的主分母是固定 10 Hz 时间网格，从 FOLLOW 与五秒无人机校准结束的较晚者开始，一直延伸到全部记录结束。消息完全停止、LOST、AMBIGUOUS、任务不匹配、错误坐标帧、非有限值和测量陈旧都保留在分母。有效状态必须最近 0.15 秒内收到，且预测龄加上当前时刻与消息时戳之差不超过原始 0.75 秒门限。

主指标 `kf_position_error_m`、`kf_velocity_error_mps` 将实际收到并携带的位置和速度直接对比网格当前时刻真值，不额外做理想外推消除传输延迟。另有 `message_level` 按消息源时间评价并单列 `delivery_age_s`，用于区分状态本身的精度与交付延迟。`valid_state_coverage`、`position_truth_coverage`、`velocity_truth_coverage` 分别报告状态、位置真值和速度真值的覆盖。没有独立变换或足够真值时不填零误差。

## 跟随误差、收敛与失败尾段

物理跟随始终从独立无人机与所请求物理目标的真值计算，与导航消息是否继续发布无关：

| JSON 字段（位于 `whole_interval.metrics`） | 定义 |
| --- | --- |
| `base_link_distance_error_m` | 目标地面原点与无人机 `base_link` 水平距离减期望距离 |
| `base_link_height_error_m` | 无人机 `base_link` 高度减目标地面原点高度，再减期望高度 |
| `model_origin_distance_error_m` | 同上，以无人机模型原点计算，保留历史口径 |
| `model_origin_height_error_m` | 同上，以无人机模型原点计算，保留历史口径 |

上述四项均包含 RMSE、均值、95%绝对误差分位数等摘要。长时间丢失后的悬停、流中断以及未恢复的失败尾段仍产生独立物理误差。`inactive_control_samples` 单列未活动的控制机会。

`whole_interval.transients.base_link.distance/height` 和 `model_origin.distance/height` 报告全区间收敛指标。`windows[]` 另报告协议规定的初始 FOLLOW 到首次遮挡/新选框区间，以及每一次显式选框到下一次选框/记录结束的任务区间。不能用初始窗口成功替代全区间失败。

固定距离带为 `max(0.5 m, 期望距离的10%)`，高度带为 0.25 米。收敛必须在记录结束前保持至少三秒的连续、有效、活动控制且在带内的最终后缀。消息间断、未知身份、缺少真值、停跟和超带会中断后缀。`settling_time_s=null` 表示右删失，不能当成零秒收敛；`settled_through_interval_end` 和 `settling_right_censored` 是机器可读标志。对移动任务报告绝对反向越界量，不声称是静态阶跃的百分比超调。

`evaluation_status=RECORDED_WITH_CENSORED_FAILURES` 和 CLI 返回 0 仅表示已完成有证据的评价，试验仍可能失败；`INCOMPLETE_EVIDENCE` 返回 2。总体工程 PASS 还须按预先登记的门槛检查物理跟随、身份保持、长丢失悬停和安全证据，不能由评价器返回码推断。

## 验证边界

`python -B -m unittest tests.test_navigation_evaluation -v` 使用合成消息检验独立坐标变换、带姿态的控制点转换、目标偏差不得参与校准、原始去重/速度、错误帧、非有限值、0.60/0.75 秒门限、传输延迟、未知任务、静默丢流、失败尾段、缺失真值和严格配置证据。这些测试证明评价规则按定义执行，不代替真实 Gazebo/PX4 闭环试验。实现期间未读取或解压正式 rosbag，以避免与仿真争用内存。
