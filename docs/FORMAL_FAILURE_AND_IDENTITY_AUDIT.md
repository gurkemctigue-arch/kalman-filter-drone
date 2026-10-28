# v2 正式失败与身份记录边界审计

本次只读核对正式结果中的小型 JSON、ROS/PX4/录制日志、少量遥测行及冻结源码；未打开或解压 bag，未运行测试、推理、仿真、构建或绘图。本文仅作为 Windows 主副本的审计说明，不进入正在执行的冻结源码，也不修改正式数据或参数。

审计对象为 `fullplan_v2_online_estimators_car_velocity_{raw,fixed_kf,adaptive_kf}_seed00`。后续主研究进度与成败总数继续以 manifest 为准，本文不作为动态进度清单。

## 可确认的失败性质

三次均属于正式运行中实际观测到的跟踪/遮挡恢复失败，当前基础设施分类器均为 `infrastructure_failure.stop=false`、`reasons=[]`。这不等于认证系统没有任何传输或清理问题；它表示现有证据没有将这些失败归因为无法起飞、录包不可读、节点在飞行中退出或评价器执行失败。

共同证据：

- 子矩阵记录 `launch_returncode=0`、`evaluation_returncode=0`；评价进程成功写出 FAIL 报告，不代表验收成功。
- `summary.json` 的基础飞行、解锁与 Offboard、monitor 成功均为真，终止原因为 `follow_duration_reached`。三次达到约 3 m 高度，存在实际水平运动。
- `offline_evaluation.json` 为 schema 3、`evaluation_revision=3`，`missing_topics=[]`、`input_read_error_count=0`，输入的 `read_errors`、`unavailable_types` 均为空，时钟可用。
- 子矩阵验收记录 bag 和非空视频齐全，速度设定值互斥与到达 PX4 的证据通过。长期丢失后没有未经选择自行恢复，显式新任务也均得到一次测量确认。
- 持续跟踪尾窗接收时钟回退数与无效接收时钟数均为 0，chronology 检查通过；本次 FAIL 不能用已修正的混合时间戳误判解释。

| 方法 | 遥测中首次 LOST / 仿真 s | 短遮挡请求区间 / 仿真 s | 重选确认 / 仿真 s | 重选后首次 LOST / 仿真 s | 重选后有效跟踪控制跨度 / s |
| --- | ---: | --- | ---: | ---: | ---: |
| raw | 21.36 | 29.7–30.1 | 49.756 | 51.36 | 1.500 |
| fixed_kf | 30.46 | 29.8–30.2 | 49.940 | 51.56 | 1.548 |
| adaptive_kf | 30.46 | 29.7–30.1 | 49.780 | 51.56 | 1.700 |

首次 LOST 遥测的 `prediction_age_s` 均约 0.76 s。raw 在短遮挡开始前已经失联，因此其短遮挡窗口没有预测阶段，不能描述成“短遮挡单独导致了第一次丢失”。fixed/adaptive 在短遮挡窗口观测到 PREDICTED，随后 LOST；短遮挡验收的 `no_loss_during_short_occlusion=false`。三次短遮挡均有真实空检测证据，遮挡服务成功、关闭 ACK 先于开启请求。

三次长遮挡窗口的失联、悬停、保持低速和禁止自动恢复均通过；进入该窗口时已经处于停留/失联状态，`braking_from_motion_demonstrated=false`，故不能把低速悬停称为本次长遮挡下“从运动制动”的证据。重选后都再次 LOST，持续跟踪控制仅约 1.5–1.7 s，未达到至少 5 s 的要求。尾窗仍保留大量 LOST/HOVER，`minimum_control_span`、`same_target_active_states_only`、末端新鲜跟踪等检查失败。

三次重选尾窗的 `first_uuid_mismatch_s=null` 仅说明该窗口没有记录到错误任务 UUID，不能据此认证物理个体身份或证明跟踪成功。丢失后维持原任务并悬停属于安全行为，仍未完成持续跟踪验收。

## 日志支持与不能确认的原因

三份 `ros.log` 均在正常跟踪/停留切换之后出现 runner 发起的 `SIGINT` 清理。多个节点的 `process has died ... exit code -2`、KeyboardInterrupt，及 raw 的 rclpy Task 析构异常均出现在该终止段；三次 detector 都记录 `process has finished cleanly`。不能把这些结束时清理异常改写成更早飞行中失联的已证实根因，也不能删除它们。

`process_exit_codes.json` 均记录 Gazebo/PX4/bag/monitor/ROS 顶层进程为 0、Agent 为 -2。冻结 runner 的 `run_stage1_trial.py:310–327` 在飞行循环中检查进程及 ROS 子节点提前退出，并在 finally 中按顺序停止进程和保存退出码；因此退出码需结合阶段和日志顺序解释。

fixed/adaptive 的 `bag.log` 各记录 1 条 transport-layer message lost 警告，发生在试验结束清理附近。保留该警告；当前小日志未给出其对应话题及与失联事件的关联，不能推断它导致了短遮挡或重选后的跟踪失败。PX4 的 LED 设备打开提示、DDS 创建 failsafe_flags writer 的信息也不是发生飞行 failsafe 的证据。

| 方法 | 跟踪评价区间图像采集至推理完成延迟 max / 仿真 s | 同区间推理 wall-time max / s |
| --- | ---: | ---: |
| raw | 0.188 | 0.2182 |
| fixed_kf | 0.344 | 0.5100 |
| adaptive_kf | 0.404 | 0.6141 |

这些区间最大值没有提供与每次首次失联的逐帧因果对齐。不能仅凭它们宣称“算力不足”“某种滤波一定更差”“检测器崩溃”或“深度锚点变化就是根因”。可确认的是接受测量没有在安全时限内持续维持任务、随后安全悬停；检测、关联、三维异常门控、可见表面变化和时序各自的作用尚未由本次轻量审计分离。

`summary.json` 与离线报告采用不同消息范围和时间边界，因此计数、距离误差及延迟分位数可以不同。控制器自身估计误差不是独立真值误差；Precision/Recall/mAP 及在线三维真值误差在这些基础飞行报告中仍为空，不能填为零或当作算法已认证精度。

## 阶段二、三正式槽位实际覆盖

以下来自冻结 `plan.json` 与 `/root/uav_tracking_fullplan_v2/scripts/run_stage23_matrix.py:52–87`，不是根据试验成败事后选定的范围。

| 范围 | 飞行数 | 初始目标与选择 | 遮挡/重选 | 解释边界 |
| --- | ---: | --- | --- | --- |
| 阶段二 crossing，person/car 各 10 seeds | 20 | 三同类目标，`locked_target`，图像 middle 框选 | 无脚本遮挡，无显式重选 | 同一关联配置跨 seeds 重复；不是两种关联算法的配对比较 |
| 阶段二 parallel 工程，两类各一次 | 2 | 三同类目标，middle 框选 | 短长遮挡及显式重选 | 单次工程安全验证，不是十次遮挡重复 |
| 阶段二 ambiguity 工程，两类各一次 | 2 | 三同类目标，middle 框选 | 自然几何歧义，最终持续悬停 | 无脚本遮挡/重选；需实际所选轨迹歧义证据 |
| 阶段二 auto_unique 工程，两类各一次 | 2 | 多候选时不选择 | 无重选，持续停止 | 有意没有所选个体；离线身份/状态误差槽为 NOT_APPLICABLE_NO_SELECTED_TASK |
| 阶段三 active/midpoint，两类各 10 对 seeds | 40 | 单目标 `auto_unique` 自动初锁 | 两模式均有短长遮挡及显式重选 | 单目标云台配对；不能称为 40 次多目标指定个体联合重复 |

多目标主动云台已经有另列工程 probe，但不属于上述 40 次分母。阶段二、三合计正式 66 槽；独立扩展 16 槽和既有探针不抵扣，也不并入这些重复分母。

## 身份与安全记录是否可供离线核对

冻结源码记录链完整覆盖所需字段，后续仍需逐次核对实际 bag/消息覆盖，不能凭配置断言尚未执行的槽位已经有完整数据。

| 记录 | 字段或事件 | 冻结源码位置 |
| --- | --- | --- |
| `/tracking/state` | 状态、`track_id`、`target_uuid`、测量年龄、位置/速度及异常测量计数 | `state_estimator_node.py:282–355`；monitor `on_state:228–243` 保存任务状态及确认事件 |
| `/tracking/tracks` | 所有轨迹框、matched/projected、候选与测量时刻、selected、rejected_measurements；全局 associations、歧义轨迹/检测/合并不确定分量及任务 UUID | `stage2_telemetry.py:8–47`；monitor `on_tracks:315–317` 原样存入遥测 |
| `/tracking/selection` | 选择/清除/重置动作、图像框、track_id、UUID、来源与时间 | `TargetSelection.msg`；monitor `publish_visual_selection:552–564` 每次生成新 UUID |
| 初始与重选事件 | requested/confirmed UUID、框及源图时刻；明确的 TEST_SCRIPT_INITIAL_SELECTION / TEST_SCRIPT_EXPLICIT_RESELECTION | monitor `tick:515–539` 与 `on_state:228–243` |
| 控制状态/命令 | lifecycle、track_id、原因、新鲜度与有效性；任务 UUID 可通过同时间状态及轨迹关联，命令本身不带 UUID | monitor `on_status:245–249`；`TrackingCommand.msg` |
| bag | RGB/Depth/CameraInfo、完整观测帧、状态/轨迹/选择/控制、TF、PX4、云台反馈/命令与独立 GT | 冻结 runner `run_stage1_trial.py:255–265` |

安全评价使用明确记录序列和收到的 `/clock`；不能按后来较好的状态移动确认边界。二维匹配 ID 与任务 UUID 是两个身份层次；稳定 UUID 或 `track_id` 不是物理个体正确性的证据。直接外部 API 按 track_id 选择且不提供 UUID 可以沿用旧 UUID；正式测试脚本的每次框选则生成新 UUID。

## 真值隔离与指标边界

冻结 detector 只消费 RGB/Depth/CameraInfo 及飞行阶段；`candidate_id` 来自 `enumerate(YOLO boxes)`，不是仿真 ID。估计器只消费观测帧、显式选择和相机 TF，关联使用类别、图像几何和三维/马氏门控。控制器、云台与相机 TF 消费所选目标状态、PX4 里程计和关节反馈；未发现目标 GT 名称/ID 参与关联或跟随的通路。

GT 话题被桥接并录制，离线评价才使用演员/模型身份。场景演员 cmd_vel、遮挡板 `vision_shutter` 和云台关节名称属于仿真测试/硬件接口，不是算法的目标身份输入。因此只能说“算法不消费目标 GT”，不能说“运行时没有 GT 话题或 Gazebo 名称”。

冻结 `run_full_plan_research.py:262–276` 仅为阶段二非 auto_unique 调用物理身份评价；阶段三正式单目标调用在线状态与动态误差评价，不生成多目标物理身份报告。阶段二 `evaluate_physical_identity.py` 提供：

- 每个显式任务的 `amodal_simulation_mot`、`unoccluded_geometry_mot` 中的 HOTA、IDF1、ID Switch；新任务不跨 UUID 累计为身份切换。缺少完整 GT 的机会保持 unscorable，不能补成空 GT。
- `selected_physical_identity_all` 的 CORRECT、WRONG_PHYSICAL_ACTOR、NOT_OBSERVED、UNKNOWN_GEOMETRY、UNKNOWN_TASK_INITIAL_ID，以及全任务机会正确比例、已知帧条件一致率和 unknown/unobserved 比例。
- `conservative_selected_identity.retention_lower_bound`、`known_coverage` 与任务内观测到的物理身份切换；unknown 保留在总分母。未观测到错误不等于全程身份保持 100%。

原 `summary` 将任务内的 HOTA/IDF1/IDSW 先取任务均值，再以整次飞行/seed 为统计单位；帧、重选窗口或离线噪声种子不是额外独立飞行。amodal 和无遮挡几何指标的标签范围必须说明；将其作为可见检测标签发表前仍需独立可见性审核。

`follow_dynamics.windows` 的 `first_measured_confirmation_after_request_s` 与 `confirmation_censored` 描述显式重新选框后新任务的测量确认。它们不是长时间离场后自动认回原物理个体的 ReID 重捕获率/时间；完整 ReID 第一版未实现。跟随稳定时间仍需同时报告右删失和缺失窗口，不能用重选确认快替代持续跟踪或稳定时间。

## 本次证据入口与哈希

正式根目录为 `results/frozen_fullplan_v2/`，三份失败的完整原始目录均保留；[在线估计子矩阵](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_repetition_report.json) 包含验收和基础设施分类证据。[冻结主计划](../results/frozen_fullplan_v2/full_plan_research_v2/plan.json) 的 canonical SHA256 为 `2791685e042c6253b8715da939dfcb53193e7d7b211540a7ad2734b86630c7e2`。

| 方法 | 原始评价 | SHA256 |
| --- | --- | --- |
| raw | [offline_evaluation.json](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_car_velocity_raw_seed00/offline_evaluation.json) | `15bff93af6fec8f47db202a3b7e2c5cd88c1338f424ee2a255ff40904120bf63` |
| fixed_kf | [offline_evaluation.json](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_car_velocity_fixed_kf_seed00/offline_evaluation.json) | `18bb5703ec679ec6283337de82a50bf649c52471522e6badb2f8aa3c8cf04a4b` |
| adaptive_kf | [offline_evaluation.json](../results/frozen_fullplan_v2/fullplan_v2_online_estimators_car_velocity_adaptive_kf_seed00/offline_evaluation.json) | `8dc32ee1457ed452074a99ce00117dbc5e47751bf98d2fe40a675641b0e0a3b3` |

本审计不据三个 seed00 条件样本判定滤波方法优劣，不替代全矩阵配对统计，也不提出改变正式阈值或重试失败槽位。
