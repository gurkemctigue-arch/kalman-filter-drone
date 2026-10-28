# v4 同测量四估计器比较设计草案

本设计仍为 **DRAFT_NOT_FROZEN_NOT_EXECUTED**。纯数组复放、录包导出、在线数值复现和独立状态主题核对已实现。Humble04汽车开发录制的 `export02` 已真实导出 **204个测量、1220个输出**，在线导航float64数值复现与全部1220对独立native-state核对均PASS。此证据只完成开发录制的导出/复现关口；比较参数尚未定标登记，正式20录制×4方法未执行，也不改变该开发飞行的原终态。它不增加飞行槽、不改动原120槽工程协议，没有产生正式比较结论。机器可读状态见[独立预登记草案](../planning/reliability-v4-estimator-replay-preregistration.json)。120槽不覆盖原计划所有噪声/距离/延迟等工况，新增矩阵另见[剩余执行计划](../planning/reliability-v4-remaining-execution.md)。

## 可以回答的问题

同一条原始导航测量序列可以同时输入 raw、EMA、固定传感器噪声 KF、几何自适应 KF。四种方法使用相同的目标任务、观测、时间、公共门控和评价真值，因此可以比较“给定这些已发生的传感器测量和飞行轨迹，哪种状态估计误差更小”。

这些图像和测量由最终 v4 控制策略飞行时产生。离线替换估计器不能改变无人机轨迹、相机视角或遮挡机会，所以它不能回答“四种估计器分别控制无人机时，谁跟随得更好”。原 120 槽继续检验实际系统；这项独立研究补充同测量条件下的状态估计比较。

## 固定样本与失败处理

在最终、唯一冻结的 v4 工程计划中预先选定 `stage1_velocity` 组全部两类 × 十个种子：`person`、`car` 各使用 **1000–1009**，共 20 个槽。JSON 列出全部 20 个 `slot_id`。每条录包复放四种方法，得到 80 个“方法 × 录制”分析单元，独立试验数仍为每类 10。

选择只由类别、组和种子决定，不能在看到成功率或误差后挑包。FAIL、INTERRUPTED、基础设施中止、没有起飞或证据不完整的槽全部保留；缺包不换种子、不重试填补。没有可计算状态估计区间时记为 `null` 并报告原因，不能填零误差。原工程终态不随离线结果改变。

这些录制只覆盖工程协议中已规定的 clean、standard 运动和短长遮挡等条件。它们不等于每一种深度噪声、延迟、距离和运动工况都完成了十次重复。新增工况需要另行冻结样本矩阵。

## 四种方法和当前代码的实际含义

当前 `/tracking/navigation_state` 由独立 [NavigationEstimator](../ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py) 生成。它内部关闭默认质量缩放并显式使用每次传入的几何与位姿合成协方差。`--estimator-method` 目前切换可见表面/身份管理路径的估计器，不能据此宣称已经切换了导航输出。

另外，[kalman.py](../uav_tracking/core/kalman.py) 在收到显式 `measurement_covariance` 时直接使用该矩阵，不再运行默认 confidence/depth 质量缩放。因此本草案准确比较“几何自适应”，没有把方法命名为已经实现了原计划的置信度/深度质量自适应导航。

原surface跟踪链已经实现由confidence、深度有效率和离散度调节R，并保留其原有测试/历史研究。这里的边界针对新增独立导航输出及其四法研究对象，不能据此说原surface要求完全没有实现。

| 方法 | 位置与预测 | 观测噪声 |
| --- | --- | --- |
| raw | 当前公共接受的原始导航测量；更新间零阶保持 | 不进行 KF 融合 |
| EMA | 相同测量的因果 EMA；更新间零阶保持 | `alpha` 待开发集定标 |
| fixed KF | 六维匀速状态，按采集时间更新并因果预测 | `R0_sensor[class] + R_pose(t)` |
| geometry adaptive KF | 相同状态、Q、P0 和时间模型 | `R_geometry(t) + R_pose(t)` |

固定 KF 的“固定”指传感器/导航参考噪声项；两种 KF 都保留完全相同的实时位姿不确定性。否则固定 KF 同时少用一类车辆信息，比较将混入位姿传播的差异。每类的 `R0_sensor`、Q、P0、共同初速度规则及 EMA alpha **尚未定标**，JSON 均保留 `null`；当前程序默认值不自动等于本研究已登记参数。

如果后续要研究原计划的置信度、深度有效率和离散度自适应，可另行预登记 `R_quality(t) = s(q) R_geometry(t) + R_pose(t)` 及缩放界限。这应有独立方法名称与参数，不得靠改标签代替实现，也不能重复缩放位姿不确定性。它不属于本草案的四方法主比较。

## 同测量与因果时序

复放应从融合前的导航测量和完整图像机会开始，保留空帧、无效几何、门控拒绝、丢流和失败尾段。不能只读取已发布的后验状态，也不能只筛选在线 `fusion_accepted=true` 的结果而隐去所有拒绝样本。

四种方法共享预先登记的因果门控、身份/重选/重置序列和相同接受样本。公共门控的参数与初值须在开发证据上冻结，不能使用未来观测或目标真值。该消融是在共同门控条件下比较估计输出，不研究各方法自己的关联或异常点拒绝能力。原观测 0.60 s、预测 0.75 s、里程计 0.50 s 与未来 0.05 s 门保持不变；raw/EMA 保持输出不能延长有效期。

记录源时间、发布、回调收到、记录交付和原始顺序，确保观测在实际可用前不会影响输出。对采集时间状态误差与交付后当前时间误差分别命名，不用理想外推消掉传输龄。所有方法在相同 10 Hz 时间轴上评价，从 FOLLOW 和独立 ego 校准结束的较晚者直到完整 `/clock` 末尾；长丢失、悬停与静默尾段仍进入覆盖分母。

raw/EMA 的速度是同一任务内、合法时间间隔的因果有限差分；KF 状态速度在相同网格时刻与共同的真值速度定义比较。原始导航的“相同区间割线速度”诊断另列，不能把它和瞬时状态速度 RMSE 混为一项。共同初速度规则不得读取未来窗口或真值。

离线比较之前，首先用冻结输入复现在线导航 KF 的初始化、接受/拒绝、采集后验、投影输出和有效性。等价性容差与核验方法也必须先用开发数据/纯夹具冻结；复现不一致时应停止解释方法差异。

## 录制与协方差来源

现有主题包括原始 RGB-D、CameraInfo、完整 `observation_frames`、TF、车辆位姿协方差和导航诊断。开发代码的 schema2 导航诊断已拆分 `R_geometry`、`R_pose` 和合成 R，并记录实际所选位姿、相机变换、初始化速度及采集/处理/发布时刻。导出器核对合成 R 与实际融合 R，按准确的位姿样本重建位姿传播项；缺失质量字段单列计数，不能补造质量值。旧冻结录制保持原样，缺少这些证据时不能仅添加字段名就视作可复现。

schema2 每次去重导航机会的证据合同包括：

- 采集 ID、源/发布/可用时间和顺序，以及 UUID、track/candidate ID、类别、框与空帧；
- 原始世界坐标测量、参考有效性、几何/融合拒绝原因、支撑点和残差；
- `R_geometry`、`R_pose`、`R_total` 三个世界坐标系 3×3 矩阵，单位 m²；
- confidence、depth_valid_ratio、depth_std_m，以及存在时的显式质量缩放因子；
- 真正用于传播的 pose 源时戳、位置、6×6 协方差，以及 Jacobian 或足以重建的杆臂、坐标语义；
- 同采集 RGB-D/TF、声明的几何尺寸与不确定性、模型权重和源码/运行环境/评价器 hash。

所有矩阵须有限、对称且半正定。两种 KF 使用同一个 `R_pose(t)`；不能从合并 R 中减去一个未记录的“估计 pose 项”，也不能从目标真值拟合 R。若选择从已有消息重建而不增加字段，必须证明相同采集、相同 TF 和相同所选 pose 样本能复现在线值，不能用后来的最近位姿代替。

目标真值仅进入离线评价。所有方法共用声明 ENU 轴向和独立车辆前段冻结的地图平移；禁止用目标轨迹或各方法误差重新对齐。原始飞行、模型、库和终态 hash，与后续独立复放/评价源码 hash 分别保存。

## 指标与配对统计

主指标为每条 trial 的三维位置 RMSE。次指标为速度 RMSE、95%位置误差分位数、短遮挡预测误差、状态/真值覆盖以及观测接受拒绝数。误差采用共同、独立真值支持的时间样本，并同时显示各方法自己的覆盖；缺失状态不以真值补齐。共同支持的证据要求尚未定标，须在正式结果前冻结。

每类按同一个 seed 构成四方法配对块。主对比为 `geometry_adaptive_kf − fixed_kf` 的每条 trial RMSE 差，负数表示前者更小；对 raw、EMA 的同类对比作为次分析。报告所有 trial 值、均值/中位差和完整失败/缺失数。

JSON 提议采用 **95% 配对百分位 bootstrap CI**，按每类的 trial/seed 块重采样 10,000 次，统计 RNG seed 为 20261029；同一次抽样保留该 seed 四种方法的关系。不能把图像帧、多个时间窗口或 bootstrap 抽样次数当作独立重复，也不能按长包的帧数给它更高 trial 权重。

若有缺失配对，可显示有限配对的条件性 CI，但必须同时列实际 n、所有缺失槽与理由，以及原定每类 10 的分母。它不代表无条件成功率；不足十对不能称为完成了十次有效比较。没有配对或无信息的重采样应报告不可估计/局限，不制造精度。十条试验本身也限制区间稳定性和外推范围。本草案不要求 p 值；若要检验显著性，需事先另定检验族及多重比较规则。

## 何时需要额外闭环试验

如果论文仅声称“同测量条件下的状态估计改进”，本设计配合原 120 槽系统验证即可分别支持两个结论；原 v3 四基线研究作为历史证据单列，不能混入新版配对。

如果要声称“四种估计器造成闭环跟随差异”，最小独立闭环矩阵为两类 × 十个配对种子 × 四种实际接通导航输出的方法，共 80 条。只有其中 20 条与最终 `stage1_velocity` 在源码、方法、场景、控制参数和种子上完全一致，才可能复用它们并追加 60 条。当前仅切换表面估计器的开关不能满足这一条件。本草案没有批准或实现新增 60 条，也不扩大现有 120 槽运行器。

## 已实现接口与真实录包验证入口

[replay_comparison.py](../uav_tracking/replay_comparison.py) 提供 `replay_states`、`score_states`、`replay_trial` 和 `paired_trial_summary`。状态复放函数不接收真值；真值只进入单独的评分函数。纯 core 不读文件；只有收到 CLI 实际核验后、绑定当前数组/登记摘要/审计文件 hash/源码与逐周期计数的证据回执，才标为 `COMPUTED_WITH_VERIFIED_EXPORT_AND_ONLINE_EQUIVALENCE`。缺失证据仍为 `COMPUTED_PENDING_ONLINE_EQUIVALENCE`；一个 PASS 字符串或布尔值不能解除 pending。开发导出也不自动满足正式登记，任何离线结果都不改变原飞行判定。

[export_estimator_replay_v4.py](../scripts/export_estimator_replay_v4.py) 连接 ROS bag reader、[数组归一化与状态核对](../uav_tracking/replay_export.py)、[真实在线导航数值复现](../uav_tracking/navigation_reproduction.py)及独立真值评分网格。它只接受当前选定的单目标 `stage1_velocity` 政策，保留空帧、拒绝、身份变更和完整 `/clock` 尾段。数值复现以实际 `NavigationEstimator.update/project`、真实初始化速度和每次 R 为准；四种比较方法自己的共同 P0/初速度是另一套前瞻登记合同，不能强行将两者视作相同初始化。

导出前要求原始录包的完整性证据：ext4 SQLite 正常关闭、metadata/主题条数一致、标准 zstd 完整帧和字节往返、原生 ROS 压缩 reader 全量读回。正式种子还须先核对登记与开飞 UTC、最终计划、类别/组/种子、终态槽记录、原始配置/结果文件 hash 和当前导出/审计源码 hash；不读取 bag 后再补登记。原槽 FAIL/INTERRUPTED 等状态照常保留。

真实导出需要已 source 的 ROS 2/消息环境、`PyYAML` 与系统 `zstd` CLI。Humble 安装脚本已包含它们；便携 GitHub CI 只运行合成夹具和 zstd 往返，不安装 ROS 或运行正式 bag。开发种子可使用如下入口，输出目录必须全新：

```bash
python scripts/export_estimator_replay_v4.py /path/to/development_trial --output /path/to/new_export
```

正式种子1000–1009的命令还必须传 `--registration REGISTERED.json --slot-id person_stage1_velocity_seed1000` 等准确槽名；当前草案不能运行该路径。输出包含 `arrays.json`、`online_equivalence.json`、`native_state_audit.json` 和 `truth_alignment.json`。export的PASS只说明该录制的导出、在线诊断数值和独立状态主题核对通过；源时钟、原生起飞、实际跟随和正式重复仍由各自独立验收判定。

真实开发验证见[export02执行记录](../results/development_offline_v4_humble04_car_seed00_export02/execution_status.json)与[源码/消息来源](../results/development_offline_v4_humble04_car_seed00_export02/environment_and_source.json)。它读取原Humble04汽车bag和04消息安装树，核验online关键源码与04一致。首次 `export01` 的164项独立状态差异对应JSON float64与消息float32 wire量化，失败原件保留；新导出按消息字段声明精确cast后全部通过，量化后一ULP差仍会拒绝，未扩大online float64容差。新完整Clock评价保留10574条Clock、203个机会和202个真值支持，末端稳定性仍右删失，原飞行Gazebo退出-11仍保留。

后续 `export03` 用同一真实开发bag重新离线导出，在三份审计侧car中增加完整数组输入的canonical SHA绑定（只排除审计内容和三个循环文件hash字段）。实际文件验证器通过204个测量、1220个输出/task周期；分别替换位置、协方差、任务UUID、真值位置后，即便重新封装数组文件hash，也全部拒绝。正式入口拒绝开发导出；旧 `export02` 原件保留，并因缺新版来源/输入绑定而不能满足新版关口。见[真实JSON集成记录](../results/development_offline_v4_humble04_car_seed00_export03/gate_integration/integration_report.json)。开发验证使用独立 `DEVELOPMENT_ONLY_FILE_HASH_SOURCE_BOUND_EXPORT_AND_ONLINE_AUDIT` 回执，纯core不能据此升格正式比较。

[run_estimator_replay_v4.py](../scripts/run_estimator_replay_v4.py) 只处理导出的 JSON 数组，不导入 ROS 或 bag reader。当前草案可执行：

```bash
python scripts/run_estimator_replay_v4.py plan
python scripts/run_estimator_replay_v4.py inventory --inputs-manifest /path/to/manifest.json
```

`plan` 不读取试验数据；`inventory` 只读取包含全部 20 槽的路径清单及文件元数据，不打开试验内容。清单为 `schema_version=1` 和 `slots` 字典，每个预定槽的值为 `{"path":"export.json","sha256":"实际文件SHA256"}`，缺失槽明确填 `null`。不能从清单中删掉失败或缺包槽。

`run --configuration REGISTERED.json --inputs-manifest manifest.json --output NEW_DIRECTORY` 在读取清单或试验数组前，先检查配置为 REGISTERED、自身摘要、开发定标来源，以及实际复放代码/KF helpers 和最终 FORMAL 计划文件的 hash。配置仍须补齐明确 R0、Q、P0、EMA、公共门控和证据要求，并在首条留出正式飞行前冻结。该检查不自动产生注册证据。输出目录独占创建，保留原工件。

读取数组后，CLI 实际打开同目录三份审计 JSON，核对数组绑定的文件 SHA；检查完整输出/测量/task 周期、独立 native 一对一原始序号、在线更新及输出计数、真实接收时间与 float32 年龄合同、原数值容差、完整 clock 读取证据，并逐项核对导出/在线/helper/消息源码与登记及当前文件。真值审计必须保留声明 ENU、仅车辆前五秒平移对齐、独立 ego holdout 和 ±0.05 s 速度导数窗口的来源。缺失文件、篡改计数、替换源码或空 PASS 报告都保留 pending；仍可输出明确标注的描述性数值。

三个侧car还必须绑定同一个完整测量/身份/task/输出/真值/时间区间payload摘要，防止数组内容与实际审计输入脱离。仅顶层数组hash、侧car自身hash或PASS标签均不充分。该绑定提供文件来源与输入一致性证据，不是对恶意伪造全部原始证据的数字签名。

汇总分别报告 `finite_pairs`、`verified_pairs`、完整十槽分母及待审计槽。十条数值可算记录仍可能只有九条证据已验；只有全部十对通过独立审计和共同支持门，`complete_ten_pair_matrix` 才为真。整项完成要求两类共二十条；原工程 FAIL、INTERRUPTED 和缺失继续单列。不能把离线核对通过解读为实际跟随、source_clock 或整个计划验收通过。

归一化输入采用三个事件数组 `measurements`、`task_events`、`output_events`，具体字段见模块文档。测量 `source_s` 是采集时间，`available_s` 是估计节点处理可用时间，不能换成 recorder 交付时间。输出分别保存实际状态 header 的 `state_source_s`、发布的 `source_s`、交付的 `available_s`：按发布机会生成、按实际 header 投影、按交付时间评分，评分时不再外推状态。wrapper 以独立匹配的真实导航状态接收时钟确定 `available_s=max(publication,native_receipt)`；诊断主题的接收 proxy 另存，不能掩盖 native 状态晚到。接收时钟受 `/clock` 记录粒度影响，沿用原 50 ms 未来容差；这不证明零传输延迟。缺少独立 native 状态或接收时钟时不认证交付可用性；迟到过期仍按原年龄保留。

从同一条 schema2 导航诊断派生的 task/measurement/output 可以共享该消息的真实 `record_sequence`。排序使用 `(event_time, record_sequence, causal_suborder)`；只有同一周期内部才按 task→measurement→output 排序，不能让同一 `/clock` tick 中较晚 callback 的测量泄漏给较早输出。独立实际 navstate 的 bag 序号作为核对证据保留，不伪造乘号后的“原始序”。

task `bind` 和 `state` 都必须显式保存实际视觉状态，首绑为 ambiguous/lost 时不能默认 tracking。首次选定前的空 UUID/empty 测量仍计入诊断机会，不编造身份；丢失/clear/换任务后的旧 UUID 永久关闭。没有真实输出机会时不会生成理想消息流，静默尾段与过期预测保留在完整时间分母。

当前测试覆盖注册阻断与不可变来源、真实审计文件 SHA/源码/逐周期核验、三种输出时刻和独立 native 交付、同 tick 周期因果顺序、真值不进入门控、R_pose 仅加一次、共门控拒绝、空帧/重复/过期/丢流、永久旧任务关闭、仅车辆对齐与静默真值尾段，以及以 trial 为单位的配对 CI 和完整分母。Humble04 汽车真实导出验证与纯夹具分别记账。异常在线数值仍保留 FAIL，空记录/缺 delivery/不一致年龄不产生 PASS；开发集定标、参数前瞻登记、正式录制独立核验和四法统计仍须完成。
