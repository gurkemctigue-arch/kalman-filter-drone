# 原始三阶段计划与v4剩余交付清单

快照：2026-10-29。此清单是源码和已有小型证据的静态审计，不是新实验结果，也不登记性能阈值或扩大正式协议。**当前v4没有完成最终工程验收。**

v3历史已归档166主槽（107 PASS、58 FAIL、1 INTERRUPTED）及16项独立工程扩展（2 PASS、14 FAIL），它们属于Ubuntu24.04/Jazzy。v4在独立Ubuntu22.04/Humble环境开发；新结果、旧失败和两个环境的分母分别保留，不能以历史Jazzy材料补作新Humble通过。

## 三阶段：实现、证据与缺口

| 原计划内容 | 已有实现/证据 | v4完成前仍需交付 |
| --- | --- | --- |
| 阶段一：两类唯一实例、RGB-D/TF、六维KF、互斥位置/速度、预测及LOST悬停 | 核心、ROS包、世界、适配器与评价器已有；Humble04汽车clean20秒原生起飞/FOLLOW、有效原始bag、source_clock/native_startup PASS | 最终源两类速度/位置闭环、真实短遮挡预测/恢复、长丢失悬停及显式重选；物理距离/高度、覆盖和稳定性独立通过 |
| 原confidence/depth自适应R | surface跟踪链已实现confidence、有效深度率、深度离散度质量缩放，保留原测试和历史研究 | 明确surface研究对象与新增navigation研究对象；不能把已有surface实现误报为缺失，也不能用它替代navigation新实验 |
| v4独立navigation KF | 使用独立地面参考和 `R_geometry + R_pose`；Humble04汽车有效覆盖100%，位置RMSE约0.09645m；尾10秒距离/高度RMSE约0.01892/0.00447m | 当前只是无遮挡开发证据，最后GT bracket缺失、稳定性右删失、Gazebo退出-11；新Humble06完整闭环和独立验收待做 |
| 阶段二：三同类、初框指定个体、歧义悬停、不自动替换 | `TargetManager`、hybrid_3d关联、安全状态机、独立物理身份评价和REQUEST至完整Clock的10Hz审计已有；v3保留成功/失败 | 最终Humble两类多目标交叉、遮挡、LOST后重选录制；逐任务物理身份、未知覆盖和ID指标实际核验，不只证明UUID连续 |
| 阶段三：真实三轴云台反馈、机体慢偏航回正 | 中位/主动/多目标主动世界和接口已有；动态采集时刻TF、实际camera-link GT离线核对已有 | 最终Humble两类×中位/主动/多目标主动关口与十次正式重复；图像中心、轴误差/限位及base_link物理跟随分别验收 |
| 实机迁移边界 | 算法/适配器分离、ENU/FLU↔NED/FRD合同已有 | 输出依赖/版本/参数/标定及接口说明；不承诺硬件即插即用或真实飞行通过 |

## 当前120槽实际覆盖

来源：[工程协议](reliability-v4-preregistration.json)与[trial_spec](../scripts/run_reliability_v4.py)。两类别×以下六组×留出seed1000–1009=120槽，**仍DRAFT、未执行**。

| 组 | 类别各10槽的条件 |
| --- | --- |
| `stage1_velocity` | 唯一实例、中位云台、速度设定值 |
| `stage1_position` | 唯一实例、中位云台、位置设定值 |
| `stage2_crossing` | 三同类、middle初框选择、hybrid_3d、交叉、速度设定值 |
| `stage3_midpoint` | 单目标、中位三轴云台、速度设定值 |
| `stage3_active` | 单目标、主动三轴云台、速度设定值 |
| `stage3_multi_active` | 三同类指定个体、交叉、主动三轴云台、速度设定值 |

共同条件：45秒、clean、standard、RTF0.5、短遮挡0.2秒、长遮挡3秒及显式重选；person距离5m/YOLO11n320/2线程，car距离9m/YOLO11s640/4线程。原保护界保持：观测0.60秒、预测0.75秒、odom0.50秒、马氏9.21。CPU llvmpipe属于新渲染条件，不能与历史auto/D3D12性能混池。

单目标standard路径包含2秒启动加速、直线与左右缓转；这是每次试验中的组合路径，不能说每种运动分层各有十次独立试验。多目标crossing里被选中心actor沿直线、另外两actor换道，不能称被选目标完成同一缓转工况。速度由同seed在0.45–0.55m/s抽取，不构成独立加减速扫描。同一类别没有多个预登记跟随距离。

## 原计划工况：已有入口与缺失验证

[run_stage1_trial.py](../scripts/run_stage1_trial.py)已有下列选项；[sensor_fault_bridge.py](../scripts/sensor_fault_bridge.py)作用于图像/深度流，不读取GT。

| 工况 | 现有入口/定义 | 历史16扩展 | 新Humble仍缺 |
| --- | --- | --- | --- |
| 深度噪声 | `--condition depth_noise`，0.05m帧偏置+逐像素高斯噪声 | 两类各1次 | 最终源独立冻结、重复与结果 |
| 深度空洞 | `--condition depth_holes`，25%空洞 | 两类各1次 | 同上 |
| 检测机会丢帧 | `--condition dropout`，RGB-D共享200ms窗口10%丢失 | 两类各1次 | 同上；准确称输入流掉帧，不称已模拟所有检测器漏检机制 |
| 通信/交付延迟 | `--condition latency`，RGB-D队列增加0.12仿真秒、原采集戳保留 | 两类各1次 | 同上；仅该注入点，不能泛称DDS/Offboard全链路故障 |
| 组合故障 | `--condition combined`，噪声0.05m、空洞20%、丢帧10%、延迟0.08秒 | 两类各1次 | 同上 |
| 加速/减速 | `--motion-profile-kind speed_changes`，平滑降速/升速、保留S路径 | 两类×速度/位置，共4次 | 最终源独立冻结、重复与统计 |
| 不同距离 | `--desired-distance-m` | person7m/car12m各1次；默认person5m/car9m另在历史主研究 | 每类多个距离的最终源配对样本；不能把不同类别的5m/9m当距离消融 |
| 多目标歧义与唯一实例多候选 | `--scenario-kind ambiguity/parallel/crossing` 与 `--target-mode auto_unique/locked_target` | 历史阶段二有专项 | 最终版本开发回归与独立安全证据；120固定交叉不等于覆盖全部歧义场景 |

历史16由[run_extended_engineering.py](../scripts/run_extended_engineering.py)固定为4加减速+10在线故障+2远距，**每条件一次**。历史离线测量扰动四法工具也不等于传感器故障下的真实闭环。现已另建[最终Humble独立扩展草案](reliability-v4-extension-preregistration.json)：两类×八工况×十seed=160槽（五故障、两控制模式加减速、远距离），与120核心分开；仍须实际开发关口、前瞻登记/冻结和运行，不能把新增草案当新结果。

## 四法比较

已有surface raw/EMA/fixed/adaptive实现和v3历史研究。新增navigation采用geometry/pose R，当前 `--estimator-method` 不切换这条独立导航KF。

新增[同测量四法设计](../docs/V4_ESTIMATOR_COMPARISON_DESIGN.md)固定取两类 `stage1_velocity` 各10槽，共20录制、80方法×录制单元；它只支持给定共同测量/轨迹的状态估计比较。Humble04汽车 `export02` 已真实导出204测量/1220输出、online/native审计PASS，但不是四法正式实验。剩余：开发集定标并登记R0/Q/P0/EMA/共同门控和支持覆盖要求，冻结实际复放/导出/评分来源，再核验全部20录制和配对bootstrap统计，失败/缺包不换种子。

若报告要声称四法导致闭环跟随差异，须另有两类×十seed×四种实际导航方法的80飞行矩阵；最多20条可在合同完全一致时复用，其余不在120中。原confidence/depth缩放若加入navigation比较，另行实现/登记 `s(q) R_geometry + R_pose`，不能仅改方法名或重复缩放pose R。

## 指标与工具能否用于新录制

| 指标 | 可用工具 | 新版剩余/解释边界 |
| --- | --- | --- |
| Precision、Recall、mAP | [evaluate_detection_recordings.py](../scripts/evaluate_detection_recordings.py)、独立网格投影、review-file、低conf缓存；已新增[配置/缓存来源核验](../docs/DETECTION_EVALUATION_PROVENANCE.md) | 历史只有人工/独立视觉复核的完全可见静态子集，不能称新120整体精度。脚本保留person320/car480/2线程历史默认，另支持recorded/explicit参数与实际模型、图像、源码、cache及审核绑定；轻量fixture已验，新录制真实推理/标签复核与统计仍待执行 |
| FPS与端到端延迟 | flight评价已有仿真时钟处理FPS、wall推理、采集到处理/命令延迟 | 新版逐槽实际统计；不得把10Hz上限当实测FPS，也不能把sim时间延迟当墙钟实时性 |
| 位置/速度RMSE、p95、预测误差 | [evaluate_navigation_reference.py](../scripts/evaluate_navigation_reference.py)、schema2导出与复放评分 | 新版完整分母与GT支持、静默尾段和遮挡窗口；surface锚点与独立地面导航参考分别命名 |
| 距离/高度、中心误差、超调、稳定时间、抖动 | 导航/云台/flight评价与历史metric supplement已有实现 | 确认新版汇总实际读入对应新schema；右删失/缺真值不填0，主动云台画面改善不代替base_link误差 |
| 保持率、ID Switch、IDF1、HOTA | [evaluate_physical_identity.py](../scripts/evaluate_physical_identity.py)与portable MOT；已与固定官方TrackEval公式对照 | 工具可对新多目标包评价，含动态云台独立camera GT/TF核对；仍须实际执行，保留unknown/不可见与REQUEST至完整Clock时间分母。amodal诊断与可见几何子集分开 |
| 短时恢复率/时间 | 历史metric supplement有同track/同UUID短遮挡恢复数与时间 | 同track/UUID不是独立物理身份保证，需与physical audit结合；开幕ACK不等于实际渲染可见时间 |
| 长丢失显式重选 | explicit_selection确认率/时间已有 | 新任务UUID确认与原个体自动ReID不同；完整ReID仍在范围外，不产生伪ReID重捕获指标 |

[历史指标覆盖审计](../docs/FINAL_METRIC_COVERAGE_AUDIT.json)明确限定旧166+16管线，不能原封改称v4验收。新版必须单列机器可读覆盖表、结果索引和缺失项。

## 环境、实验与交付的剩余顺序

1. **Humble06冻结与开发闭环。** Humble05四包/隔离PASS，969测试中旧fixture漏mock渲染capture的1 ERROR已修，旧冻结失败保留。06须新建冻结、全套检查及两类完整真实飞行。CPU llvmpipe的两项真实RGB-D关闭smoke已PASS，但不是PX4/YOLO飞行性能验收。
2. **最终12格开发门与参数登记。** 两类×六组完整、同一最终飞行关键源码/权重/环境的开发证据；独立登记物理RMSE、navigation/GT/身份覆盖及末端稳定要求，四法另登记定标参数。不以进程退出0、录包完整或少数指标PASS替代工程终态。
3. **正式及独立扩展。** 合法冻结后串行120槽；另冻补充工况矩阵后执行。每槽一次保留失败/中止，基础设施异常先诊断再运行未尝试槽。开发不能消费1000–1009；不把开发探针补作正式重复。
4. **离线评价与统计。** 全部计划槽纳入台账，四法20录制、工况扩展和检测标签审计分别报告；生成每类/条件试验级统计、配对区间、失败分类、原始结果CSV和来源hash。新版[轻量汇总工具](../docs/V4_RESULT_SUMMARY.md)已接入120/160不可变计划/槽的来源核验、JSON/CSV/HTML与同seed配对，真实正式统计尚待数据。原失败不回写。
5. **可视化及最终材料。** 为新版生成可打开的HTML入口、参数/源码/模型与原始bag索引、逐项验收图表、保留丢失/悬停的固定seed演示视频、最终计划书与研究报告Word/PDF。现有8段v3演示、v3最终文档和历史图表保留原版本标签，不能作为v4新录制。
6. **复现与GitHub。** 更新Ubuntu22.04/Humble从依赖到SITL的可复现命令、模型下载/SHA/许可说明、最小运行与验收方式；最终源测试通过后同步已授权仓库。大bag/权重不直接进Git，提供本地/外部工件索引；浏览器展示入口与源码提交分开验收。

冻结验收资料、视频和报告可以由代理继续制作，不需要用户人工跑十次。可见标签复核与最终成果观看需要真实图像证据和明确审核记录；是否由代理完成不改变该证据要求。当前不需要用户操作实机或为仿真补作人工飞行。

## 本轮未改的机器可读状态

`reliability-v4-estimator-replay-preregistration.json` 的 `implementation_status` 仍写真实录包未验证，应由协议所有者同步为Humble04开发export02证据，保留研究DRAFT和参数未登记。`reliability-v4-preregistration.json` 的性能门仍未注册；本清单不替它选择阈值。旧交接记录按时间保留，不可把旧pending和新证据混读。
