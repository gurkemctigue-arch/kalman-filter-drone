# 可复现实验与统计协议

本协议区分独立飞行、录制输入重放和检测标签三个实验单位。它们解决不同问题，不能把数量相加，也不能把同一段录像的多次重放称为多次真实闭环飞行。

## 1. 实际闭环重复

`scripts/run_stage1_repetitions.py` 顺序启动 person/car × velocity/position × 10 个种子，共 40 次独立 PX4/Gazebo 启动。每个种子由运行器控制实际场景速度及已声明的故障参数；每组保留 run_config、源文件/模型权重哈希、rosbag、视频、原始日志、严格 schema-3 评价。

每个计划名字只能运行一次。`--resume` 保留已记录失败，并评价因中断而留下的现有 bag；它不以同名成功替换失败。`--stop-after 4` 只限制本次新增次数，最终报告仍保留完整 40 次计划和 `complete=false`。失败、启动异常和证据不完整均进入失败率分母。修复后新矩阵使用新前缀，原失败矩阵保留。

```bash
bash scripts/research_env.sh scripts/run_stage1_repetitions.py \
  --prefix stage1_repetitions_v2 --condition clean --stop-after 4
# 继续该计划；已失败名字不会重新运行
bash scripts/research_env.sh scripts/run_stage1_repetitions.py \
  --prefix stage1_repetitions_v2 --condition clean --resume --stop-after 4
```

每个类别/控制模式分别给出次数、成功/失败、Wilson 95% 失败率区间、整段 Gazebo 模型原点跟随距离/高度误差的均值和样本标准差。缺失 RMSE 不用 0 代替，数量独立报告。整段指标包含 HOVER 和失败；它不是目标三维估计精度。汽车期望距离为 9 m，行人为 5 m。

一次只运行一个仿真。离线 YOLO、网格/真值投影和滤波重放与正式 SITL 串行，避免 CPU 负载改变推理新鲜度。历史负载干扰试验保留，单独列为失败条件，不能默默删除。

## 2. 真实录制输入的滤波配对重放

四份 `stage1_final_v2` 原始 bag 提供真正相机测量、检测空帧、置信度、深度有效率、深度离散度和采集/完成时间戳。

四方法为原始测量保持、EMA（α=0.35）、固定 R 卡尔曼、自适应 R 卡尔曼。两种 KF 共用六维恒速模型、过程噪声和异常观测门控，仅 R 计算方式不同。一次生成扰动序列后，四方法共享完全相同的输入，保存其 SHA-256，禁止逐算法另抽噪声。

条件为：原始录制、额外 0.08 m 高斯测量噪声、20% 深度空洞、20% 检测帧丢失、0.15±0.05 s 额外通信时延，以及已记录参数的组合故障。每种故障 10 个种子。未扰动原始录制只运行 1 次，避免把十份完全相同结果当作十个独立样本。每份录制为 204 条方法/条件/种子记录，四份共 816 条。

滤波按采集时刻更新，在实际到达时刻评价，不把延迟测量回填成实时输出。乱序观测按源时间水位拒绝。预测年龄大于 0.75 s 记为不可用，不填补为零误差。保留 KF 拒绝数、乱序数、输出覆盖率、全部失败种子和缺失真值次数。

主配对 RMSE 比较使用同一种子下四方法都有输出的帧交集，并同时列出各方法全部机会覆盖率和自身可用帧误差。这样拒绝困难样本不会仅凭较低条件误差获得优势。统计以种子为单位，计算自适应 KF 减去各基线的均值差和 10,000 次配对 bootstrap 95% 区间。区间条件于这四份源录制，不表示跨场景总体置信区间；多项区间为探索性比较，不据此夸大显著性。

重放不让四方法分别改变飞行动力学，因此不能据此声称某滤波器导致闭环控制误差改善。此结论需要独立的在线滤波器干预实验。

### 参考点与坐标

真实 RGB-D ROI 返回可见表面，而 Gazebo 目标 pose 返回模型原点。两者在汽车上可相差数米。离线提取通过独立 Gazebo UAV pose 与真实渲染模型的相机外参，把 camera 测量变换到 world；该步骤只用于离线隔离目标估计器，假设理想 ego pose，不能当作运行时 PX4 odometry/map 误差已经被验证。

外参通过 `gz sdf -p` 展开 merge include 后解析，不能漏掉 `x500_base` 的 0.24 m 模型偏移。固定相机相对 UAV 模型原点的位置为 `[0.13233,0,0.50078]` m；运行 TF 中相对 base_link 的 z=0.26078 m 是不同参考，二者不矛盾。

每类只用 velocity 源录制中按时间排列的最初 20% 几何完整入镜、避开遮挡请求前后 1 s 且有原始深度的观测，估计 model-local 恒定表面锚点的坐标中位数。该选择不依赖检测置信度或拟合残差。训练截止时刻、样本数和残差写入结果。训练之后的所有检测机会为时间 holdout；同类 position 录制整段为另一飞行 holdout，禁止重新拟合。

同时报告 holdout 原始测量到冻结锚点的残差和未经校准的模型原点差异。固定锚点是视角相关表面的近似，转向、截断、ROI 变化可能使它失效。大残差必须保留并解释；不得再用 holdout 偏移修正使数字变小。结果名称始终为**校准表面锚点误差**，不称“独立目标中心定位精度”。

```bash
bash scripts/research_env.sh scripts/run_research_recordings.py --phase extract
bash scripts/research_env.sh scripts/run_research_recordings.py --phase replay
```

## 3. 独立检测真值与视觉审核

静态行人和汽车的渲染网格来自实际 SDF 使用的 DAE/OBJ，包含其单位、视觉 pose、尺度和场景节点变换。网格顶点通过独立 actor/UAV pose、相机内参和真实外参投影，得到 amodal 框。标签生成不读取 YOLO 框。带 skin/controller 或无法解析的网格直接报错，不近似冒充真值。

每份录制按时间从推理机会中选取约 1 Hz、最多 45 幅源图，选择包含原在线检测为空的帧，不按成功与否取样。保留所有抽样机会和排除原因。第一批检测评价限于独立几何完整入镜、遮挡请求前后 1 s 之外的静态渲染子集。目标重叠、遮挡及画面截断需要单列评价，不能把 amodal 投影框直接称为精确 visible 标注。

对候选标签生成原图、GT/预测叠框和目标放大接触表。审核者逐图确认投影与可见物体一致，并把批准的源时间戳写入独立 review JSON。正式结果只使用该已审核集合，未审核项明确 PENDING；排除项仍在报告中。审核可以由代理目视进行，用户仍可复查原图。

在冻结图像上重新运行同一 YOLO 权重，以 conf=0.001 收集完整 PR 曲线，避免在线阈值 0.45 截断 AP。每类报告在线阈值处 Precision/Recall，以及 IoU .50 和 .50:.05:.95 的 101-point AP。实现明确为 all-area/no-crowd/no-maxDet 的静态仿真子集约定，不冒称完整 COCO 数据集评分，更不推断真实世界泛化。

```bash
bash scripts/research_env.sh scripts/run_research_recordings.py --phase detection
# 逐图审核后，重用冻结预测，应用独立审核列表
bash scripts/research_env.sh scripts/run_research_recordings.py --phase detection \
  --reuse-predictions --review-file results/detection_research/visual_review.json
```

## 4. 阶段二物理身份

`/tracking/tracks` 的采集时间、track_id 和 bbox 用于评价，只接受 `matched=true && projected=false` 的新检测。旧框、预测输出、稳定 UUID 不能当作物理身份正确的证据。空检测帧保留。

每次显式选框是一个新任务。预期物理演员只能由**用户/脚本发出的 REQUEST 框及其记录的源图像 image_stamp_s**，与该源时刻的独立 mesh/actor GT 唯一匹配建立；不能用首次成功 selected track 反过来定义预期演员，否则首次选错会被伪装成正确。源图像时间缺失、不新鲜、竞争者 GT 不完整或 REQUEST 几何匹配不唯一，整项任务的初始身份保持 unknown。后续同 UUID 的每个新检测独立匹配真实演员；若匹配成其他演员，计为错误，UUID 不变不能掩盖。若多演员框同时可行、演员框存在遮挡重叠、截断、外部遮挡或任何竞争者缺失可插值 GT，则保守记为 unknown。unknown 留在总分母，分别给出已知覆盖率、已知帧一致率、全任务保持率下界和任务内物理演员切换。

HOTA/IDF1/CLEAR IDSW 单独按标准匹配定义计算，显式区分 amodal 仿真诊断与无遮挡几何子集。HOTA 在 19 个 IoU alpha=.05:.05:.95 上平均，使用 global alignment 与 association；CLEAR IDSW 采用上一时刻匹配优先、再最大化 IoU，跨未匹配间隙比较上次身份；IDF1 采用全序列一对一身份分配。每次显式重选分段，不把合法新任务当成身份切换。

`scripts/verify_tracking_metrics_reference.py` 已对照固定官方 TrackEval commit `12c8791b303e0a0b50f753af204249e622d0281a`，60 个随机序列、每序列 15 帧，HOTA 全部 19 alpha/counts、IDF1、CLEAR IDSW/TP 误差不超过 1e-12。原官方源 SHA-256 记录于 `results/research_validation/trackeval_comparison.json`。此校核验证计算公式，不替代标签审核。

```bash
bash scripts/research_env.sh scripts/evaluate_physical_identity.py results/STAGE2_TRIAL \
  --target-class person --output results/STAGE2_TRIAL/physical_identity.json
```

评价同时写出 `.frames.jsonl`，包含 GT、fresh track 框、任务和保守物理匹配，供独立可视化复查。运行节点不得订阅该真值或使用离线结果帮助关联。

## 5. 在线滤波干预与 PX4/map 坐标精度

预注册文件为 `planning/online_estimator_preregistration.json`。主矩阵是两类别 × 四种真实控制器输入滤波策略 × 十种子，共 80 次独立 velocity 飞行；另两类别 × 十种子，共 20 次 adaptive-KF position 兼容飞行。后者不冒称四方法 position 对照。所有方法共享原 adaptive-KF 安全门控和关联观察器，只有控制器真正使用的输出估计不同。默认 adaptive 策略保持原实现。原始测量和 EMA 在帧间做位置零阶保持，其速度以真实采集 dt 差分并保持，允许相同形式的前馈。控制参数、安全新鲜度、目标和检测参数按类别冻结，不能为基线单独调参。

在正式 166 次矩阵开始前，资源冻结为全组请求 RTF=0.5、行人 YOLO11n/320/2 threads、汽车相同 YOLO11s 权重/640/4 threads。早期 RTF=0.7 的汽车歧义工程探针遇到约 0.657 s 的 wall 推理尖峰并触发既定丢失保护；旧预注册及失败记录保留，正式矩阵尚未开始时统一修改两类别和全部方法的仿真速率。这是有意减慢的仿真，实际 wall latency 和 achieved RTF 都需保留；不能把仿真时间中的新鲜度 PASS 称为 wall-time 实时能力。0.75 s 失联和 0.60 s 输入新鲜度阈值不放宽。同类别四方法资源完全一致。重复运行器 CLI 明确支持 `--real-time-factor --car-image-size --car-threads --person-image-size --person-threads` 并写入每条计划 spec。

降速仿真需明确监督时钟域：PX4 vehicle_status 约 2 Hz 仿真时间发布，在 RTF=0.5 时正常墙钟间隔约 1 s。原 1 s 墙钟状态超时会在边界误报并阻止起飞。仿真运行器因此仅对仿真 runtime_parameters 注入 `status_timeout_s=1/requested_RTF`（RTF=0.5 为 2 s 墙钟），并记录请求 RTF 与实际监督阈值；通用节点面向实机的默认 1 s 墙钟不变。目标 0.60/0.75 s 仿真时间、odom/command 阈值均不变。旧失败探针保留，不能把监督启动失败算作关联算法失败，正式矩阵前必须先通过相同冻结资源的起飞及状态链路资格试验。

物理云台与指定个体联合场景的离线身份标签不得套用阶段二固定相机外参。评价器在每个原始图像时间插值独立物理 camera/base link 模型相对位姿及无人机世界真值，再同该时刻反馈驱动的局部光学 TF 核验（平移小于 0.005 m，旋转小于 0.03 rad，与云台几何验收一致）。不使用 PX4 map 位姿或云台命令作为相机真值；动态 TF 缺失、超出 0.10 s 插值跨度或几何不一致时身份保留为 unknown，禁止退回静态外参。缺少完整真值的帧不参与 MOT 分数，仍保留在指定任务机会分母。

新增 `motion_profile_kind=speed_changes` 保持默认标准轨迹不变，以 C1 余弦连接实现 .35/.60/1.0 速度倍率的减速与加速；两类别 × 两控制模式的四条工程录制用于覆盖新运动条件，也可支持十种子离线配对故障重放，不能把四条录制称为十次独立新轨迹飞行。

`scripts/evaluate_online_state_accuracy.py` 的 schema 2 直接评价实际 `/tracking/state`，包含运行时 PX4 odometry 和 TF。主对齐旋转固定为 R=I，这是源码坐标契约，不通过测试误差选择：实际 world 的 spherical_coordinates 明确 ENU/零 heading；PX4 commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` 的 `GZBridge.cpp:545` 将 Gazebo ENU 位置换成 NED(y,x,-z)，`:713-742` 的 NavSat 使用 north/east/up 并增加 GPS 噪声，`EKF2.cpp:1687-1688` 输出 POSE_FRAME_NED 的位置；本项目 `adapter_node.py:148-154` 再逆变换为 ENU/FLU。因此初始磁航向估计偏差不能被当成位置世界轴的旋转。每条录制只用最初固定 5 s 的**无人机位置**确定原点 translation，绝不读取目标点或 holdout 来拟合；同时列出后段无人机位置和未经消除的姿态残差。实际 expanded SDF 的 base_link 相对模型原点偏移参与校准，避免漏掉 0.24 m。之后 transform 冻结，目标误差仍对比第 2 节独立训练后冻结的可见表面锚点，同源校准时段排除，其他录制整段为目标 holdout。

原 schema 1 从最初 ego 姿态关系反推旋转，可能把 PX4 heading 估计误差错误变成 GNSS 世界轴误差；其原 `online_state_accuracy.json` 保留，schema 2 使用新 `online_state_accuracy_v2.json`，并把旧姿态对齐作为 sensitivity 完整列出，禁止覆盖原数值或按 holdout 选更优对齐。schema 2 还提供约 2 Hz 的 ego 位置/姿态误差时间线与原 `/fmu/out/vehicle_odometry` 的 reset_counter 变化、估计方差和 quality，用于区分坐标契约、重置与连续传感器漂移。

分别报告状态自身 header 时刻的误差，以及最新录制 `/clock` 的接收时刻误差。接收评价保留原实际携带的状态，不用理想外推或回填隐藏时延；接收时间受 `/clock` 采样周期量化。GT 只作有界插值，绝不外推。速度参考由锚点世界位置的 ±0.05 s 对称差分生成，包含目标旋转。LOST/歧义/过龄输出保留在覆盖率分母。该评价弥补理想 GT ego 重放的边界，但目标表面锚点本身仍是近似，不冒称独立模型中心精度。

```bash
bash scripts/research_env.sh scripts/evaluate_online_state_accuracy.py results/STAGE1_TRIAL \
  --target-class person --output results/STAGE1_TRIAL/online_state_accuracy_v2.json
```

控制抖动定义为间隔不超过 0.2 s 的相邻有效 velocity 命令之 `||Δv_cmd||/Δt` 和 `|Δyaw_rate|/Δt`。这是命令变化量，包含真实跟踪瞬态，不等同于机体测得的加速度；HOLD、position 和 failsafe 不混合。统计依旧以飞行/种子为单位，帧数不是独立样本数。
