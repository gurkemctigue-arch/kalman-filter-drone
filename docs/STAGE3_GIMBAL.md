# 三轴物理云台实现与验收协议

本文件描述阶段三接口和验收方法。代码与离线回归已经实现；实际 Gazebo/PX4 试验结果以对应 `results/` 下的录制与报告为准，不能仅凭本文或单元测试判定完成。

## 机械模型和坐标

`x500_stage3` 继承 PX4 的真实 `x500` 电机、IMU、GPS 和气压计，并增加三个真实 `revolute` 关节。三轴交点相对 `base_link` 为 `[0.13233, 0, 0.26078] m`，与阶段一测量采用的相机光心一致。各轴零点的机械链为：

`base_link → yaw(+Z) → fixed_pitch(0.35 rad) + pitch_delta(+Y) → roll(+X) → RGB-D sensor`

这里均采用右手 FLU：x 前、y 左、z 上。yaw 正角朝左；pitch 正角朝下；roll 正角遵循 +X 右手规则。关节反馈顺序统一为 yaw、pitch_delta、roll，角度单位 rad。总光轴俯角为 `0.35 + pitch_delta`，因此中位命令 `[0,0,0]` 精确等效于阶段一固定俯角。

光学坐标采用 x 右、y 下、z 前。`base_link ← camera_link` 的旋转为：

`Rz(yaw) Ry(0.35 + pitch_delta) Rx(roll) R_optical_to_FLU`

三个轴共点是本仿真云台的明确机械设计，不是假设所有真实云台都无连杆偏移。更换实机时须替换对应机械链和标定参数。

## 插件来源与实际语义

已对照与本机一致的 Gazebo Sim 8.15.0 源码，而非仅根据插件名称猜测：

- [JointPositionController.cc](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/joint_position_controller/JointPositionController.cc)：默认根据实际 `JointPosition` 计算 PID，经 `JointForceCmd` 驱动物理关节。`use_velocity_commands=true` 会改走 ABS/`JointVelocityCmd` 分支；本模型没有启用该分支，也没有写 `JointPositionReset`。
- [JointStatePublisher.cc](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/joint_state_publisher/JointStatePublisher.cc)：发布 `gz.msgs.Model`，其 header 来自仿真时间，`axis1.position` 读取实际 `JointPosition`。
- [PosePublisher.cc](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/pose_publisher/PosePublisher.cc)：link pose 相对其父 model；离线评价需先求 `inverse(model←base) (model←camera)`，不能把 link pose 直接当世界位姿。
- [ros_gz sensor_msgs conversion](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/sensor_msgs.cpp)：`gz.msgs.Model` 可转换为 `sensor_msgs/JointState`，保留原 header、joint name、position、velocity 和 effort。

Gazebo 通过 ROS Jazzy 的 vendor 包提供，路径在 `/opt/ros/jazzy/opt/gz_sim_vendor/`，不是另一个未经验证的系统 Gazebo。

## 命令、反馈、TF 和控制分工

| 数据 | 接口 | 来源与用途 |
| --- | --- | --- |
| 每轴位置命令 | `/gimbal/{yaw,pitch,roll}/cmd_pos`，`Float64` | ROS → Gazebo JointPositionController |
| 每轴实际反馈 | `/gimbal/joint_states`，`JointState` | Gazebo物理 → ROS，禁止用命令角代替 |
| 动态相机 TF | `base_link → camera_link` | `flight_tf(camera_mount_mode=gimbal)` 根据反馈角和反馈原始时间戳发布 |
| 云台诊断 | `/gimbal/diagnostics`，JSON `String` | 同时记录反馈、期望、命令、年龄、失效原因与地平线误差 |
| 慢机体 yaw 参考 | `/gimbal/body_yaw_reference`，`Vector3Stamped` | `header=map`，`vector.z=绝对 ENU yaw`；仅新鲜且有效的主动跟踪产生 |

`flight_tf` 默认仍为阶段一 `fixed` 模式。阶段三使用 `gimbal` 模式，完全不发布静态 `base_link → camera_link`。tf2 缓存真实反馈样本，并允许估计器按图像原始采集时刻插值查询。缺失、过期或错误顺序的反馈不被重新打当前时间戳发布。

云台 yaw、pitch 用图像估计得到的世界三维目标与 PX4 无人机状态求 LOS；无人机位置/速度控制继续使用世界坐标相对位置。两者没有同时直接使用同一个图像中心误差。

roll 在 yaw、pitch 转动后再计算。设 `u` 为世界上方向在 pre-roll 相机 FLU 系中的分量，则 `roll = atan2(-u_y, u_z)`。当 yaw、pitch 为零时退化为抵消机体横滚；当云台转向侧面时，不再错误地直接使用 `-body_Euler_roll`。

机体 yaw 回正参考连续积分，名义角速度不超过 `0.10 rad/s`，yaw 中位死区 `0.15 rad`，相对当前机体 yaw 的领先量不超过 `0.20 rad`。目标 UUID 改变、目标/反馈/无人机失效或切中位时清空参考。发生外部大幅姿态跳变时，领先量约束优先，投影重置有显式 `body_yaw_reference_reset` 标记；不得声称该重置瞬间的参考导数仍无条件满足名义速度界。

反馈超过 `0.20 s`、无人机状态超过 `0.50 s`、目标预测与传输累计年龄超过 `0.75 s`，或目标为 LOST/AMBIGUOUS 时停止积分并把命令保持到最后实际反馈角，不再发布机体回正参考。缺少合法反馈时不伪造零角度。

## 启动与试验

主试验 runner 支持 `stage3`，世界名为 `stage3_flight`，无人机实体仍为 `stage1_uav`。两类场景分别为 `stage3_flight_person.sdf` 与 `stage3_flight_car.sdf`，对应 `stage3_tracking_person.yaml` 与 `stage3_tracking_car.yaml`。

使用 `stage3_flight.launch.py`，通过 `gimbal_mode:=midpoint|active` 切换中位与主动模式；也可设置 `STAGE_GIMBAL_MODE`。RGB 和对齐 Depth 均仍为 640×480、10 Hz，共用 `/camera/rgbd`，与阶段一保持相同测量接口和安全时限。

必须保留命令、实际反馈、`/tf`、`/tf_static`、实际 link 真值、图像、目标状态、控制状态与模式参考。真值只进入独立离线评价进程。

离线检查：

```bash
python scripts/evaluate_stage3_gimbal.py results/TRIAL/rosbag \
  --mode active --output results/TRIAL/gimbal_evaluation.json
```

对照组使用 `--mode midpoint`。同一类别、轨迹速度、控制参数和录制窗口下，将对照报告传给 `--compare-midpoint results/MIDPOINT/gimbal_evaluation.json`。

评价器要求：三个编码器和三个命令均真实录制；主动模式三轴均有动作且命令/反馈有物理响应差异；相机 TF 为动态、每个时间戳精确源于反馈；反馈 FK 与 Gazebo 物理 link pose 的光轴角误差小于 `0.03 rad`、平移误差小于 `5 mm`；至少 98% 检测图像时刻具有可插值的两条动态 TF；中位模式没有主动 yaw 参考。阈值和缺证据的失败都写入报告。

评价 schema 2 区分启动未就绪诊断与有效测量声明。适配器可以先读到 stamp=0 的三个实际角度，再拒绝其源时间并冻结到这些角度；该条诊断明确为 `active=false`、`reason="invalid source timestamp"`、期望角和命令速率为空，因此没有 `joint_age_s`。只有同时满足这些条件且命令严格等于反馈时，评价器才将其逐条保留在 `not_ready_diagnostics`，不用于编码器源时间对齐或命令响应差异。声称 tracking/midpoint 就绪却缺年龄、主动输出或非冻结命令仍失败。

schema 3 进一步审计暂停启动阶段的源时间零反馈：Gazebo 在暂停且仿真时钟尚未推进时会重复发布 stamp=0 的同一关节角。仅当这些样本在录制投递顺序中全部先于首个正源时间，且角度完全相同，才在 `startup_unready_samples` 单独记录而不计入有效反馈和几何指标。启动零时间角度冲突、任何正源时间重复/回退、运行后重新归零均仍失败。反馈检查使用原始投递顺序，不能靠按源时间排序隐藏时钟回退。重新评价既有录制时分别另存 `gimbal_evaluation_v2.json`、`gimbal_evaluation_v3.json`，保留原报告及矩阵原决定。

画面中心误差由检测框中心计算，不能当作人工标注精度；独立真实地平线误差从 Gazebo 实际 link 姿态计算。主动/中位单次对照只能证明工程行为，不能替代论文多次重复的统计显著性。最终验收还需查看实际画面和无人机运动，且比较跟随误差、画面中心及地平线表现，不得只看云台命令是否发布。

阶段三遮挡刺激使用 `map ← camera_link` 的最新共同有效 TF，其姿态来自关节反馈，源时间年龄上限 `0.20 s`。遮挡板放在实际光心前 `0.60 m`、薄面法向沿光轴，并在激活期间以 `0.20 s` 最小间隔更新，避免云台转向或飞行前移后绕过静态板。TF 不可用时记录 `shutter_pose_unavailable`，不谎报关闭。首次关闭/打开请求保留原有 `shutter` 与 `shutter_service_result`；中途跟随更新单独记为 `shutter_pose_update` 和 `shutter_pose_update_result`，每次携带独立请求 ID、反馈 TF 源时间与实际请求位姿。刷新不会虚构新的关闭/打开时间边界，服务响应时间仍以真实收到响应时记录。该试验驱动不读取目标真值或云台命令角。

## 已执行的离线回归

`tests/test_stage3_gimbal.py` 25 项通过：机械轴符号、中位等效、任意朝向地平线、状态年龄与失效、实际反馈来源、source-time TF、yaw 参考积分/反转/变步长/UUID重置/环绕。

`tests/test_stage3_evaluation.py` 21 项通过：缺证据、静态相机 TF、实际安装/轴错误、命令回显假反馈、重新打时间戳、错误中位回正均不能被判定为通过；同时覆盖 ROS–Gazebo bridge 实际使用的 `/` scoped frame 名称、不同 parent frame 的拒绝、多目标只计算选定新鲜框及缺少选定框时不回退、明确无效源时间的冻结启动诊断与损坏就绪诊断的区分，以及暂停启动零源时间审计、冲突和运行时重复/回退的拒绝。其合成 fixture 仅用于验证评价器逻辑，绝不计入真实仿真结果。

本机 Gazebo 8.15.0 的 `gz sdf -k` 已分别解析 `x500_stage3/model.sdf`、`stage3_flight_person.sdf` 和 `stage3_flight_car.sdf`，三者均返回 `Valid.`。继承的 PX4 `x500_base` 传感器 `gz_frame_id` 产生原有扩展字段警告；没有新增关节、frame 或模型引用错误。此检查没有启动仿真，也不能替代真实关节响应与飞行验收。

`tests/test_stage3_shutter.py` 5 项通过：偏转光轴的正确遮挡法向/距离、TF 新鲜度/坐标系错误拒绝、周期刷新与真实开关事件分离、缺 TF 不宣称遮挡完成。原有 14 项 setpoint/遮挡请求关联回归也通过。

## 多目标与主动云台联合工程场景

默认仍使用阶段三单实例世界。可显式启用 `--multi-target`，对应环境 `STAGE_MULTI_TARGET=true` 和 launch 参数 `multi_target:=true`。联合世界为 `stage3_multi_person.sdf` 与 `stage3_multi_car.sdf`，内部 world 名称仍为 `stage3_flight`、飞行器名称仍为 `stage1_uav`。三个同类演员、初始位姿、纹理、速度控制和离线真值接口完整沿用阶段二，仅把飞行器替换成真实三轴云台的 `x500_stage3`。

multi 开关使 `stage2_motion` 与原单实例 `scenario_motion` 互斥启动，不会让两个场景节点同时驱动目标。三演员的命令桥始终存在；单实例世界没有对应接收方时不影响其原有接口。目标估计器的指定个体模式由 runner 显式 `--target-mode locked_target` 设置，launch 不暗中改变算法模式。

例如行人联合工程试验使用：

```bash
bash scripts/ros_python.sh scripts/run_stage1_trial.py \
  --name stage3_multi_person_engineering_v1 --stage 3 --class person --multi-target \
  --target-mode locked_target --initial-select middle --initial-min-candidates 3 \
  --scenario-kind parallel --gimbal-mode active --duration 43 \
  --occlusions --reselect-after-loss --desired-distance-m 5 \
  --association-mode hybrid_3d \
  --real-time-factor 0.5 --inference-image-size 320 --inference-threads 2
```

汽车对应 `--class car --desired-distance-m 9 --inference-image-size 640 --inference-threads 4`，其他验收逻辑相同。联合工程试验每类至少一组，独立于 66 项重复研究清单，不把工程单次试验混入配对统计样本。

联合场景必须继承阶段二指定个体估计器参数，包括 `reject_ambiguous_matches=true`、三维/马氏距离门控和全轨迹快照；仅传 `--association-mode hybrid_3d` 不足以替代这组身份安全参数。runner 使用 `apply_multi_target_identity` 合入阶段二估计器部分，同时保留阶段三云台、控制器和反馈图。早期 `stage3_multi_person_active_probe_v1` 使用旧继承方式，只能作为集成探测，不能当最终身份安全验收；后续修正使用新版本目录，保留 v1。

正式 166 项开始前，资源预注册由 0.7 修订并冻结为所有类别请求 RTF 0.5，行人仍 320/2、汽车仍 640/4，安全新鲜度没有放宽。更早 0.7 工程探测保留其原配置及失败；它们不能混成 0.5 的正式配对样本。0.5 是本机慢于墙钟的仿真运行条件，不证明实机墙钟实时性，实际推理墙钟延迟和达到的 RTF 仍须报告。

联合试验同时检查 `evaluate_stage2_flight.py` 的指定个体/遮挡/重选安全验收与 `evaluate_stage3_gimbal.py --mode active --selected-target` 的真实云台几何验收。多目标画面中心指标必须加 `--selected-target`：它只使用 `/tracking/tracks` 中每帧匹配到的指定目标框，跳过预测和歧义框；没有这条记录就不能通过图像指标检查，不会把其他同类框混入误差。

`tests/test_stage3_multi.py` 4 项通过，验证两类世界保留完全相同的三个演员、命令桥方向与唯一性，以及默认/联合模式分别只启用一个正确运动驱动。两份联合世界已用本机 Gazebo 8.15.0 的 `gz sdf -k` 验证为 `Valid.`；只有继承 PX4 模型的原有 `gz_frame_id` 扩展警告。这些是静态/离线检查，真实联合飞行是否通过以各次 bag 和评价报告为准。

## 汽车单实例云台工程录制的评价更正

Linux 工作区 `/root/uav_tracking_project/results/` 下以下两份录制的 schema 3 飞行报告均通过；独立云台评价更正后也全项通过：

| 试验目录 | 当前独立云台报告 | 有效反馈 / 暂停启动零时间反馈 | 中心 RMSE | 地平线 RMSE |
| --- | --- | --- | ---: | ---: |
| `stage23_engineering_v1_s3_car_gimbal_midpoint_seed000` | `gimbal_evaluation_v3.json`，11 项通过 | 3068 / 775 | 0.1263136 | 0.02429477 rad |
| `stage23_engineering_v1_s3_car_gimbal_active_seed000` | `gimbal_evaluation_v3.json`，13 项通过 | 3099 / 773 | 0.0343856 | 0.01100840 rad |

这些 v1 工程飞行仍是其原请求 RTF 0.7，未重写成 0.5。原 `gimbal_evaluation.json` 的失败、仅修复诊断后仍失败的 `gimbal_evaluation_v2.json` 以及原矩阵决定均保留。v3 所有有效反馈无重复、冲突或回退；启动未就绪诊断每次 1 条独立审计。它们证明这两份已有录制的物理几何和工程闭环，不能代替每类十个种子的正式配对统计，也不能代替多实例联合身份安全验收。
