# 阶段一验收记录

阶段一目标是完成唯一实例模式下的行人、汽车 RGB-D 视觉跟随：检测、深度反投影、带时间戳的 TF、三维卡尔曼滤波、PX4 Offboard 闭环、短时遮挡预测，以及长时丢失后的悬停和显式重新选框。第一阶段固定云台中位。

## 总体状态：历史 final_v2 四条件工程验收 4/4 通过；v3 重复可靠性仍有限

ROS 2、Gazebo、PX4 SITL 和 uXRCE-DDS 已在 WSL2 中安装并集成；实际飞行场景已经使用 `x500_stage1`、机载 RGB-D、YOLO 和真实 PX4 Offboard 链路。早期“只完成 transport、目标世界尚未与飞行器合并”的描述已经过时。

上表记录的是历史 `stage1_final_v2` 修订版的四次工程演示，不等同于当前冻结 `fullplan_v3` 的重复可靠性结论。v3 阶段一已经完成 100/100 次终态试验，其中 66 次 PASS、34 次 FAIL；现有分型显示 33 次为可评分的行为失败，另 1 次为已确认的录制/评价基础设施失败。正式离线统计和失败诊断仍需完成。两套记录的源码修订不同，四次历史 PASS 因而只能证明对应修订和四个条件下的闭环演示，不应外推为当前 v3 的 100% 可靠性。

最终 `stage1_final_v2` 四条件在同一最终运行实现下依次完成真实视觉飞行，四份 schema 3 离线评价及[四条件工程汇总](../results/stage1_final_v2_report.json)均为 `PASS`。每次历史试验的全部必要检查通过，包含短遮挡同身份恢复、长丢失制动悬停、显式新 UUID 重选、重选后持续跟随、完整试验尾部覆盖及 PX4 设定值互斥。这一结论限定在该历史修订和四个条件；当前 v3 的重复试验仍保留失败结果并继续完成研究记录。

| 目标及控制模式 | 最终离线报告 | 结果 | 飞行器水平位置跨度 / m | 推理墙钟耗时中位数 / s | 重选后状态 / 控制证据跨度 / s |
| --- | --- | --- | --- | --- | --- |
| person / velocity | [person_velocity](../results/stage1_final_v2_person_velocity/offline_evaluation.json) | PASS | 20.0845 | 0.02538 | 11.560 / 11.500 |
| car / velocity | [car_velocity](../results/stage1_final_v2_car_velocity/offline_evaluation.json) | PASS | 20.1391 | 0.12946 | 11.980 / 11.952 |
| person / position | [person_position](../results/stage1_final_v2_person_position/offline_evaluation.json) | PASS | 19.4446 | 0.02891 | 11.980 / 11.948 |
| car / position | [car_position](../results/stage1_final_v2_car_position/offline_evaluation.json) | PASS | 19.2389 | 0.13154 | 11.240 / 11.200 |

水平位置跨度是 `sqrt((max(x)-min(x))² + (max(y)-min(y))²)`，表示飞行器在记录期间占据的位置范围，不等于净位移、目标位移或累计飞行路径长度。推理耗时仅指完成一次模型推理的墙钟时间，不等于端到端延迟或实际运行 FPS。重选后的两种证据跨度均超过 5 s，且一直检查到实际记录尾部；四次均未出现后续无效状态、UUID 变化或超出宽限的非跟随控制。

每次试验的 `run_config.json` 记录类别、模式和遮挡参数；配置、源码哈希、bag 和视频已通过汇总器的存在性检查。下列链接对应归档到项目 `results/` 的原始产物；WSL 原始路径为 `/root/uav_tracking_project/results/`。

| 试验 | 运行配置 / 源码哈希 | rosbag 元数据 / 机载视频 |
| --- | --- | --- |
| person / velocity | [配置](../results/stage1_final_v2_person_velocity/run_config.json) / [哈希](../results/stage1_final_v2_person_velocity/configuration/source_sha256.json) | [bag](../results/stage1_final_v2_person_velocity/rosbag/metadata.yaml) / [视频](../results/stage1_final_v2_person_velocity/onboard.mp4) |
| car / velocity | [配置](../results/stage1_final_v2_car_velocity/run_config.json) / [哈希](../results/stage1_final_v2_car_velocity/configuration/source_sha256.json) | [bag](../results/stage1_final_v2_car_velocity/rosbag/metadata.yaml) / [视频](../results/stage1_final_v2_car_velocity/onboard.mp4) |
| person / position | [配置](../results/stage1_final_v2_person_position/run_config.json) / [哈希](../results/stage1_final_v2_person_position/configuration/source_sha256.json) | [bag](../results/stage1_final_v2_person_position/rosbag/metadata.yaml) / [视频](../results/stage1_final_v2_person_position/onboard.mp4) |
| car / position | [配置](../results/stage1_final_v2_car_position/run_config.json) / [哈希](../results/stage1_final_v2_car_position/configuration/source_sha256.json) | [bag](../results/stage1_final_v2_car_position/rosbag/metadata.yaml) / [视频](../results/stage1_final_v2_car_position/onboard.mp4) |

此前 v1 汽车位置模式曾在新 UUID 确认后仅跟随约 1.05 s，随后再次 LOST/HOLD。该行为被新增的持续重选门槛否决，不能以旧 schema 2 的 PASS 作为最终验收依据。最终结论使用修复后的 v2 全新四条件记录；历史失败和旧报告应与重评记录一起保留，不能改写成成功试验。

## 实际环境与复现边界

实际版本和依赖证据见 [VERSION_LOCK.md](VERSION_LOCK.md)。当前环境是 Ubuntu 24.04.1 WSL2、ROS 2 Jazzy、Gazebo Harmonic 8.15.0、PX4 v1.17.0、同版本 `px4_msgs` 和 Micro XRCE-DDS Agent v2.4.3。

PX4 提交为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，`px4_msgs` 提交为 `86d8239e962f6939e05c3737784f60c02fa884db`。原计划中的 Ubuntu 22.04 / ROS 2 Humble 尚未单独复现，不能把 Jazzy 结果写成 Humble 验证。

当前行人参数使用 `models/yolo11n.pt`，汽车参数使用 `models/yolo11s.pt`，均使用 CPU 推理。可选 OpenVINO 实验保留在隔离环境中；本验收不据此声称已经替换主运行后端。每次试验必须保留实际参数、模型和源码哈希、启动参数及环境清单，最终以该次试验的归档为准。

## 已有基础证据

| 内容 | 证据 | 能支持的结论 |
| --- | --- | --- |
| Linux 最终构建 | [colcon 原始日志](../results/stage1_final_validation/colcon_build.log) | 四个 ROS 2 软件包全部构建通过 |
| 便携核心、目标管理、坐标转换、时间新鲜度、安全状态机与验收规则 | [完整验证日志](../results/stage1_final_validation/verification.log)，`scripts/verify_stage1.sh` | 最终全套 133/133 测试及 compileall 通过 |
| 严格离线评价器回归 | `tests/test_flight_evaluation.py` | 当前专门回归 28/28 通过；不能代替实际飞行 |
| 设定值、遮挡响应和最终汇总回归 | `tests/test_acceptance_setpoints.py` | 当前专门回归 14/14 通过 |
| 行人受控 ROS 闭环 | [person smoke](../results/stage1_smoke_person_final.json) | `passed: true`，验证受控观测链路 |
| 汽车受控 ROS 闭环 | [car smoke](../results/stage1_smoke_car_final.json) | `passed: true`，验证受控观测链路 |
| PX4 SITL / DDS / 适配器基础链路 | [PX4 smoke](../results/stage1_px4_person_smoke.json) 及日志 | 历史 transport 验证通过 |
| 自定义消息 rosbag | [smoke bag 元数据](../results/stage1_person_smoke_bag_merged/metadata.yaml) | 录制和类型识别基础证据 |
| 真正机载 RGB-D + YOLO + PX4 最终飞行 | [v2 四条件汇总](../results/stage1_final_v2_report.json) 与上表各次原始产物 | schema 3 及全部工程门槛 4/4 通过 |

最终测试计数为 133，包含上述 28 项评价器和 14 项汇总专项测试，不再与旧版 37 或 117 项记录混用。四条件飞行在这次最终构建与检查之后执行。

受控 smoke 明确标记 `CONTROLLED_TEST_SOURCE`，其三维观测由脚本生成。它用于验证 `MEASURED → PREDICTED → LOST` 和 `FOLLOW/PREDICT → HOVER/FAILSAFE`，不能当作真正视觉飞行的检测证据。实际视觉飞行应标记 `ONBOARD_RGBD_YOLO_PX4_FLIGHT`。运行时关联不读取 Gazebo 名称或真值 ID；真值仅供离线评价。

## 最终飞行必须满足的证据

- 机载 RGB-D 真正经过 YOLO、深度统计、TF、卡尔曼滤波和控制器驱动 PX4，飞行器已解锁并处于 Offboard；存在可观察的跟随运动。
- `/fmu/in/trajectory_setpoint` 的字段分类计数完整且守恒，不能用缺失计数默认成零。每条消息只包含完整有效的位置或速度字段；不允许两者同时有限、部分维度有效或无效无穷值。记录的 FOLLOW 阶段必须确实收到所请求模式的设定值；起飞与安全制动可使用速度模式。
- 短时遮挡期间出现预测，恢复测量采集于开帘之后且有接收时间；恢复前不进入 LOST，恢复的 `track_id` 与 `target_uuid` 均保持一致。
- 长时遮挡期间出现 LOST 和 HOVER，并在运动后实现持续低速制动。LOST 后、有效显式重选确认前，不能自动输出 MEASURED/PREDICTED，控制器也不能继续 FOLLOW/PREDICT；允许的控制更新宽限在报告中明确记录。
- 重新选框由 bag 中的 `/tracking/selection` 和其后的首个新鲜 MEASURED 状态共同证明。SELECT 必须有有效类别、框或轨迹以及新的 UUID；CLEAR 不算重选。RESET 也必须产生新的 UUID。旧身份、预测状态、过期状态或未确认请求不能证明重选成功。
- 从新 UUID 的 MEASURED 确认开始，必须有至少 5 s 持续状态和 FOLLOW/PREDICT 控制证据，并一直检查到试验结束。之后任何 LOST、歧义、UUID 变化或超出 0.10 s 过渡宽限的非跟随控制都失败；状态/控制记录间隔不得超过 0.5 s，试验尾部 0.5 s 内必须仍有新鲜同 UUID 状态和跟随控制。`post_reselection_tracking` 保留全部明细，不能用“只恢复了一瞬间”通过验收。
- 每个遮挡关闭和打开请求都有唯一 `request_id`、匹配动作/请求时间及成功服务响应；关闭成功响应发生在打开请求之前。使用评价报告 `schema_version >= 3`，旧版缺少持续重选检查或关联请求的服务结果不满足此证据。
- 最终报告必须覆盖完整 bag 的记录尾部，`interval.covers_recorded_trial_end` 为真；提前截到后续失败之前的时间片只用于诊断。
- 保留 bag、机载视频、运行与参数配置、源码和模型哈希、监控日志、离线结果及失败原因；归档时保留 WSL 原始记录及 Windows 项目 `results/` 副本的对应关系。

遮挡默认短请求为 0.2 s，长请求为 3.0 s，固定预测上限仍为 0.75 s。实际有效深度测量间隔还受采样、推理、传输和调度影响；0.2 s 不是通过保证。历史 0.4 s 请求曾产生约 0.8 s 有效深度间隔，触发 LOST 是正确保护，其短遮挡恢复测试应保留为失败。请求时间与服务响应只能佐证实体设置执行，不能声称它们精确等于渲染图像中的物理遮挡时长。报告应保留实际请求区间、关联响应、有效深度间隔及状态转换时间。

v2 的 person / velocity 实际短请求区间因调度为 0.300 s，其余三次为 0.200 s；四次长请求均为 3.000 s。短请求前后的有效深度采集间隔依上表顺序为 0.600、0.400、0.400、0.600 s，四次均实现同身份恢复且未触发短遮挡 LOST。它们是本次记录的结果，不构成任意场景或距离下同样遮挡长度都能通过的承诺。行人期望跟随距离为 5 m，汽车为 9 m，期望相对高度均为 2 m；它们和控制参数均保留在各次归档中。

## 复现与报告

在已安装的 WSL 环境中构建：

```bash
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
cd /root/uav_tracking_project/ros2_ws
colcon build --merge-install --symlink-install
source install/setup.bash
```

实际飞行启动、参数和安全流程见 [STAGE1_FLIGHT.md](STAGE1_FLIGHT.md)，离线指标说明见 [STAGE1_FLIGHT_EVALUATION.md](STAGE1_FLIGHT_EVALUATION.md)。当前严格门槛以评价器、汇总器和本验收清单为准。仅离线评价一项 PASS 不能代替四条件工程汇总。

检测可用率和推理延迟可以由运行记录计算；没有独立标注时，Precision、Recall 和 mAP 不得编造。控制器使用估计目标得到的误差应标记为内部一致性指标。Gazebo 模型原点的独立跟随误差与视觉框/深度表面锚点不同；未建立独立坐标和锚点对应前，不能把它写成目标位置或速度估计 RMSE。

历史四条件通过代表该历史修订下的一组阶段一工程闭环演示，每个条件各有一次记录；它不代表当前 v3 的重复可靠性已经通过，也不能据此宣称四组滤波基线的统计优劣或所有噪声、距离和延迟条件已经完成系统研究。当前 v3 阶段一已完成 100 次终态运行，但其中 66 次 PASS、34 次 FAIL（33 次可评分行为失败、1 次录制/评价基础设施失败），应与历史四次 PASS 分开统计。研究型基线比较仍应使用相同轨迹、随机种子和控制参数，连同失败试验共同统计。

阶段二的多同类指定个体实验和阶段三的三轴主动云台已有独立工程记录，当前正式研究状态见[三阶段状态页](THREE_STAGE_STATUS.md)；完整 ReID、主动搜索、自动避障和真实机飞行仍属于明确扩展范围。当前最终验证环境相对原计划的 Humble 版本差异、CPU 推理和几何/表面锚点的评价边界均应随本记录一并保留。
