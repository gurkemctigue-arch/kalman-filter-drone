# 汽车 RGB-D 表面测量修正（开发候选）

汽车框的深度 ROI 可能同时包含前后两辆车。ROI 中位深度在两层比例跨过 50% 时会跳变，即使图像目标仍连续运动。旧开发记录在相邻 0.1 秒内发生约 4.61 米的中位深度跳变，随后出现错误轨迹出生及指定目标关联歧义。

本候选提供 `component_centroid_v1` 测量修正。它只适用于已声明尺寸族的汽车，默认关闭，尚不能代表新的闭环或身份验收通过。

## 处理规则

1. 保留检测器本帧所有已通过置信度和框有效性检查的类别框，供地面及独占支持排除使用。列表索引与原始 `candidate_id` 分开。
2. 仅在 RGB 与对齐深度的整数纳秒时间戳及 optical frame 一致时准备修正。相机内参沿用固定标定合同，并记录缓存 CameraInfo 的真实来源；不宣称逐帧同步了 CameraInfo。
3. 查询采集时刻的 `camera_frame <- map` TF，将世界 up 转到相机坐标。等待不超过 0.02 秒；不使用 latest TF、固定相机 up 或最近姿态。零时间戳因 tf2 的 latest 特殊语义而回退原测量。
4. 每帧共享一次原始严格深度有效域 `min < Z <= max` 的预处理，以及全部检测框以外的地面拟合。
5. 每个汽车候选必须有唯一充分的独占前景几何支持，且完整 ROI 中仅有一个充分、与其距离范围相交且全部符合该模型的分量。没有证据时返回 UNKNOWN，不按峰大小或距离选择。
6. 有支持时使用该完整实测分量的三维质心，替换 `position_camera_m`。其他候选及所有原始深度质量字段保留。

质心是 `visible_surface_proxy_component_centroid`，不是物理车中心或单个传感器像素。固定点集下质心满足刚体变换等变性；视角、遮挡、框和支持分量变化仍可能移动参考点。

## 保留的行为与限制

- UNKNOWN、TF 不可用、图像预算超限等均记录原因并使用原测量；不删除候选、不清空原有有效深度，也不增加整帧丢弃条件。原 `navigation_enabled` 的同步门保持原行为。
- 这不是 pending 或共享支持去重实现。原始受污染测量可能仍在 UNKNOWN 回退路径中出现。
- bbox、置信度、原 ROI `depth_m`、有效率、标准差和上下界保持原义；不能将原中位深度当作修正质心的 z。
- 沿用原 ROI 质量启发式 R。质心误差尚未完成物理标定，分量散布没有被当作 R。估计器使用实际修正世界点和原同采集时刻机体姿态协方差，重新计算杠杆臂项，不重复添加 pose R。
- 原关联距离、马氏门限、0.60 秒观测门、0.75 秒预测门、身份歧义及长时丢失保护均未放宽。导航仍使用其独立的几何参考和有效性规则。
- 无运行时 Gazebo 真值或实体身份输入；不授权自动换目标或长时 ReID。

## 配置和诊断

开发命令显式追加 `--car-surface-recovery`；它要求 `--class car`。未指定开关时，runner 即使读到基础 YAML 中遗留的 `true` 也会显式关闭修正。`run_config.json` 和归档 runtime YAML 均记录实际配置。

| detector 参数 | 默认值 |
| --- | --- |
| `car_surface_recovery_enabled` | `false` |
| `car_surface_recovery_method` | `component_centroid_v1` |
| `surface_geometry_frame` | `map` |
| `surface_tf_timeout_s` | `0.02` |
| `surface_max_image_pixels` | `307200` |
| `surface_max_roi_pixels` | `307200` |
| `surface_max_visible_boxes` | `64` |

固定尺寸族为 `[4.5, 1.8, 1.5]` 米，尺寸标准差 `[0.45, 0.18, 0.15]` 米。地面和采样参数沿用已声明的几何规则。

`/tracking/detection_diagnostics` 记录帧级来源、整数时间戳、epoch、K/图像尺寸、CameraInfo 来源、TF 查询和 up、共享地面及工作预算；每候选记录 raw/output 三维点、支持或 UNKNOWN 原因、参考种类和应用动作：

| action | 含义 |
| --- | --- |
| `RAW_BASELINE` | 未启用修正 |
| `RAW_FALLBACK` | 已启用但本候选不满足修正条件，保留原点 |
| `USE_COMPONENT_CENTROID` | 采用有支持的完整分量质心 |

通过 `(clock_epoch, acquisition_ns, candidate_id)` 对齐 observation。完整点云不逐帧写入诊断；原录包、K、框、参数及冻结源码可用于离线重建。

## 已有机制证据与后续验收

原记录条件重放的 145 帧、889 个输出已在 Windows 和 Ubuntu 22.04 复现。B3.1P 对窗口 55 个汽车候选中的 15 个使用质心，40 个 UNKNOWN 保留 raw；29.9 秒的原错误边从距离 4.881 米、Mah² 808.96，变为 0.503 米、Mah² 8.185，通过原 1.5 米／9.21 门限。窗口 32.5 秒保持 TRACKING，但末尾归档含 COASTING。

这些结果条件于原记录事件表，未证明完整任务身份、75 秒持续效果或新闭环成功。下一步为新冻结版本的冷构建、完整 Humble 验证及同条件汽车 crossing 闭环；随后检查汽车多目标主动云台和完整开发矩阵，再决定是否进入正式留出实验。旧失败、未知和正式 0/280 状态保留。
