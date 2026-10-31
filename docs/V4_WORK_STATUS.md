# v4 开发与验证状态

**最新：2026-10-31，Humble38 同源核心 12 格已经实际关闭，11 PASS、1 FAIL，正式仍 0/280。** 汽车单目标速度/位置、两类三种云台配置以及行人指定个体均已通过本轮开发验证；汽车交叉提前丢失尚未通过。独立时序排查已定位到大外包候选出生后形成竞争轨迹、持续歧义并触发原 0.75 秒丢失锁存，正在针对性修复与回归。原失败、未知、删失及旧版本记录保留；整批正常退出不表示全部验收完成。完整原 12 格指标、身份分母和下一版修复边界见[本轮核心结果](../planning/reliability-v4-humble38-results-20261031.md)。以下较早的“当前”描述均是历史。

下一步执行方案已于2026-10-30整理为[12项工作及完成条件](../planning/reliability-v4-next-actions-20261030.md)，涵盖监控、状态超时、汽车断链/重选、稳定性、身份、云台、开发关口、正式登记、280次重复与交付。本次仅制定方案，未启动新实验。

2026-10-30 复核：最新 Humble21 已于北京时间 10 月 29 日 20:14 停止，当前没有仿真运行。12 个核心开发槽为 1 FAIL、5 EVALUATION_PENDING、1 INFRASTRUCTURE_ERROR、5 未执行；5 个待验收槽的数值性能门尚未登记。汽车基础短测仅 197/219 个导航状态有效，距离/高度未持续稳定到结束，不能称可靠性问题已解决。4 安全、16 扩展和正式 280 项尚未开始。四类剩余问题的逐项状态、最新物理指标、云台及身份边界见[本次可靠性复核](V4_RELIABILITY_REVIEW_20261030.md)。以下较早的运行中描述均是历史记录，不能用来判断当前进程状态。

更新：2026-10-29。**v4 仍在开发验证，整个项目尚未完成本轮修复后的正式验收。** 已发布的 v3 交付包含失败和证据边界；其“最终报告”文件名不代表 v4 已通过。

本检查点承接已公开的 `ea46897`。Ubuntu 22.04/Humble16 已完成四包构建（10.0 s）、真实模块与 ament 来源隔离检查；Linux 套件运行 **1161 项测试，结果 OK（跳过 2 项，33.217 s）**，跳过项不计为通过。源清单包含509个文件；构建、隔离、源一致性与跳过原因保存在本地 `results/frozen_fullplan_v4_humble16/freeze_validation/`。新同源实际验证进行中，完整工程验收和正式研究尚未完成。

Humble15 原阶段三任务虽完成飞行和录制，但保存的参数快照缺少显式 topic 与零偏置声明，原 `INFRASTRUCTURE_ERROR` 保留；原计划另有3个 `EVALUATION_PENDING` 和8个 `PENDING`。Humble16 两类阶段三 YAML 共补6行，值与原节点默认一致。12核心和16扩展的28格实际参数生成、runner审计、source-clock及navigation配置解析均通过。另合入离线 `PoseSeries.at` 首末端浮点精确匹配修复，原严格 `<1e-9 s` 条件、长缺口与真实外推拒绝规则保持不变。

16采用新完整开发矩阵直接生成统一来源的评价证据，不再为旧15补全套 navigation overrides；旧15及独立汽车45秒诊断不替代16开发gate或最终定标。原失败、缺证、未知与待执行项保留。参数预检和历史诊断不是新版本完整飞行验收，当前继续两类新 clean、12核心、4歧义安全与16扩展开发验证。

Humble14 两类 clean20s 已完成独立源时钟、原生起飞、归档读回、CPU 渲染、正常退出和最终 Clock 同戳真值检查；行人208/208、汽车217/217导航评价点真值完整，距离/高度RMSE分别约0.305819/0.262907m与0.584973/0.263610m。两条未施加快门，遮挡项 INCOMPLETE 保留。随后首个完整核心槽虽然独立安全和物理性能满足候选门，仍因收尾 observer 未收到必要源流而保留原 FAIL、flight_exit=1；原计划其余11槽保持 PENDING。

Humble15 已加入暂停前实际源回调就绪要求，发现等待与暂停后排空共享原10秒预算；明确存在的闭合/归档失败或坏报告会停止后续实验。历史缺文件保持未知，有效 PASS 也不授予工程通过。真实 DDS 四用例分别复现旧故障、验证晚到源成功、缺 GT 拒绝暂停和 rejected raw 不要求 adapted；只有暂停 RPC 使用 fixture，这些是组件证据。原14录制、计划、槽和失败记录未改，这些修复由16承接验证。

Humble12 两类真实 clean20s 已验证源数据首尾配对、原生起飞、录包读回、CPU 渲染、全部进程正常退出及最终 Clock 同戳的全部真值；行人207/207、汽车210/210评价点真值完整，base_link距离/高度RMSE分别约0.3262/0.2583m与0.6059/0.2633m，均稳定到末端。22项真实 ROS 生命周期行为已有独立证据；这些历史无遮挡飞行不能代替新版本完整任务验收。

13轮完整任务进一步暴露两项算法与任务边界：位置设定值参考未对实际机位闭环时存在持续跟随滞后；多目标交叉时，已知重叠框按现有完整性门拒绝导航测量，可能持续 HOLD。当前版本承接位置参考反馈和消息失效时的参考复位、场景 publisher 命名冲突与模型资源解析修复；有限换道是新场景定义，不能消除原重复交叉的失败或冒充算法修复。严格前景身份证书只增加离线证据，运行时几何与身份保护不变。完整任务效果仍须 Humble16 同源开发飞行验证，不能沿用旧版本测试或 clean 飞行宣布通过。

固定 seed004、两类×六组的12格核心开发和两类×八条件的16格扩展开发尚未全部通过；两类×两情形的4条歧义安全专项另行验证。正式 **120 核心 + 160 扩展 = 280 槽尚未开始**。失败、身份未知、缺证与右删失继续保留。最新逐次证据见[当前交接记录](../planning/reliability-v4-current-state.md)与[执行计划](../planning/reliability-v4-remaining-execution.md)；以下为保留的历史过程，不能用旧的“当前进展”表格代替最新逐次记录。

以下保留此前修复过程与边界。GitHub `6cba405` 是较早的**开发检查点**。`nav04` 因新 PX4 rootfs 的启动路径问题终止，`nav05` 在约 13.944 s、1.57 m 时出现 PX4 起飞阶段磁航向对准 reset；保护逻辑随后停止继续任务。两次失败及原有证据完整保留，没有用后续代码覆盖失败记录。新 `px4_native` 原生起飞分支先交由 PX4 起飞、完成航向对准与悬停资格检查，再切换 Offboard。Humble03 汽车开发探针已实际进入 FOLLOW 并结束运行，但压缩录包未通过原生读取，**尚不能据此通过独立完整验收**。

随后 Humble04 的新汽车原始录包通过了完整性、源时钟与原生起飞独立检查，导航有效覆盖100%，尾10秒实际距离/高度RMSE约0.01892/0.00447m。它仍是无遮挡开发探针，末端GT缺一个bracket，Gazebo关闭退出-11，不能替代完整正式关口。Humble04 行人在原生起飞时因 `status_age_wall=2.010 > 2.000 s` 中止；此时源状态龄仅0.500s，odom龄0.014s，独立source_clock仍PASS。主树已修正 `source_sim` 状态计时合同并保留独立墙钟停流界，新版本尚待完整飞行验证，失败原件与判定不改写。

该汽车原始bag已完成真实schema2导出：最新另名 `export03` 保留 **204个测量、1220个输出**，在线导航float64数值复现与全部1220对独立native-state主题核对均PASS。独立gate接纳原导出，拒绝测量位置、协方差、任务身份或真值被替换的JSON；旧导出仍保留。它验证开发录制的导出和复现证据链，**不是正式四法比较，也不把原飞行终态改成PASS**。

Humble06四包、导入隔离及969项Linux测试通过。其行人20 s无遮挡飞行完成原生起飞与FOLLOW，实际CPU `llvmpipe` 渲染、录包及全部进程正常退出；导航/真值203/203，实际距离/高度RMSE约0.31775/0.25737 m，尾段均稳定。但启动时8条原始里程计缺少adapter诊断，source-clock仍为INCOMPLETE，不能报工程PASS。后续07、08在解除暂停前分别暴露Humble executor/context及Subscription API兼容问题；失败原件保留，汽车未跑。新09正收敛为Humble公开API，先验证真实最小pub/sub/service，再执行隔离构建、测试和两类新探针。WSL D3D12关闭故障已定位，06证明CPU方案可完成一次真实飞行，后续仍须逐槽验收。

## 当前进展

| 内容 | 已有工作 | 尚需完成 |
| --- | --- | --- |
| 导航参考 | 独立 RGB-D 地面参考；汽车端面/侧面/双面唯一几何解；独立滤波和物理距离/高度评价；回归测试通过 | 新几何版本实际闭环、遮挡和多目标交叉验证 |
| 时间与不确定性 | 同采集 RGB-D/TF、PX4 协方差、源时钟与 reset 保护；源状态龄及独立墙钟停流界已进入06真实飞行，启动诊断之后配对完整 | 09公开API启动门及全任务源时钟验收；06启动8条缺证仍保留为INCOMPLETE |
| 磁传感器接口 | 钉住 ENU/gauss 与 FLU→FRD 合同；Jazzy 与 Humble 独立 PX4 ELF 构建、manifest、Humble 专用动态库登记完成；Humble03 实际启动 | 原生流程完整动态 ego 评价和独立闭环验收；不能预设其消除全部航向误差 |
| 环境迁移 | Ubuntu 22.04/Humble独立环境、Agent、patched PX4、ros_gz、ABI/RGB-D桥接；06四包/隔离/969测试及行人实际飞行通过相应检查；08四包/隔离/979测试通过 | 新09公开API版本的完整构建、测试及两类SITL；单测通过不等于启动门已通过 |
| 原生起飞 | Humble04汽车实际完成native起飞与FOLLOW，独立native_startup PASS；主树增加40 s源时间与独立180 s steady-clock预算及双时钟审计 | 新预算/状态合同真实录制、两类与最终交接的完整独立评价 |
| 录包完整性 | 新录制采用ext4 SQLite正常关闭、条数核验、标准zstd完整帧、SHA字节往返和Humble原生reader全量读回；Humble04汽车41174条原始消息及行人中止包均通过完整性检查 | 后续每槽继续执行完整性门；Humble03原缺尾失败不改判 |
| 渲染与关闭 | 同PID映射定位WSL D3D12 TLS故障；llvmpipe真实RGB-D关闭smoke与06行人飞行/全子进程退出均通过；实际swrast/LLVM映射、环境及ELF核验 | 新冻结两类、遮挡、多目标和云台的处理性能与退出检查 |
| 指定个体证据 | 从首次 REQUEST 到完整 `/clock` 末尾的固定 10 Hz 身份覆盖；未确认与静默尾段保留为未知 | 最终版本多目标录包的独立物理身份审计与完整任务覆盖门检查 |
| 正式工程重复 | 运行器、不可覆盖槽位账本、完整分母与评价接线 | 开发关口通过、性能门预登记、冻结源码/环境后执行 120 槽 |
| 四估计器比较 | surface链已有confidence/depth质量自适应；v4导航另用几何与位姿R。Humble04汽车export03真实导出204测量/1220输出，online/native复现与完整payload证据gate通过 | 同测量导航四法的开发集定标、前瞻冻结及20条正式录制配对统计；不能把geometry自适应等同surface质量模型，不能声称四法闭环因果改进 |

已有开发探针证明了部分时序改进，也暴露了导航丢失和转弯限制。失败录制和尾段仍保留；单元测试、构建成功、进程正常退出和少量探针都不能代替完整工程通过。

## 接下来如何验收

1. 完成每环境的隔离 PX4、ROS 与桥接构建，生成真实源码/二进制 manifest，核对实际加载动态库与启动日志。
2. 以开发种子执行新的行人/汽车、指定个体、短长遮挡、云台与交叉探针，保留 raw bag、配置、hash 和独立评价。
3. 在正式结果出现前登记导航性能门；最终开发关口须覆盖两类别 × 六组，并对不可修改的槽位、真实启动/磁场/源时钟/导航/身份/云台证据独立重新验收。只有性能门已合法登记且这 12 格通过，才允许冻结和执行正式计划。当前状态仍为 `UNREGISTERED_PENDING_DEVELOPMENT_PROBES`。
4. 正式 v4 为两类别 × 六组 × 十个留出种子 **1000–1009 = 120 槽**，每槽只尝试一次；失败和基础设施中止继续计入分母。开发探针禁止消费这些正式种子。

v4 使用相同留出种子在类别/组之间比较。原 v3 的四基线研究使用 0–9，属于另一份冻结研究；不能把 v4 表述为与 v3 配对重跑或四基线复现。

这120槽固定为clean/standard，两类分别固定5 m/9 m距离；standard含启动加速、直线与缓转，但不等于独立加减速工况。噪声、空洞、掉帧、延迟、额外距离和 `speed_changes` 不在本矩阵中，已另建[160槽独立扩展草案](../planning/reliability-v4-extension-preregistration.json)，仍须开发关口、前瞻登记/冻结和实际执行。逐项缺口见[原计划剩余交付清单](../planning/reliability-v4-remaining-deliverables.md)，新版[结果汇总入口](V4_RESULT_SUMMARY.md)只读计划/槽小工件，尚无真实正式统计。

## 环境与 GitHub 边界

v4 从已发布基线 `01e3477` 开始开发。当前源码工作区的改动用于新版本，原 v3 冻结目录和结果独立保留。本轮只读核验原 `/root/uav_tracking_fullplan_v3` 的正式环境清单：**218 个源码/模型资产 hash 全部一致，无缺失**。本轮没有读取或重写旧 bag，也没有重新判定历史失败。

源码、测试、文档、补丁和公开查表配置适合提交；`results/`、下载权重、ROS 构建目录及机器专用 `config/px4_magnetic_runtime.json` 由 Git 忽略。manifest 记录本机源码/ELF 路径与 hash，不能作为跨机器通用二进制。正式冻结仍从磁盘记录它，不受 Git 忽略影响。

原 Ubuntu/Jazzy 与独立 Ubuntu 22.04/Humble 各有自己的工程副本、二进制和 manifest。Humble 的最终 manifest 位于其独立工程内，不从 Windows 根或原 Ubuntu 复制一个不同 ELF 的登记来冒充验证。源码 hash 的跨平台复现由根目录 `.gitattributes` 的 LF 规则约束。

Gazebo 动态库也按环境独立登记：Jazzy 使用 `config/gazebo_magnetic_runtime.json`，Humble 使用 `config/gazebo_magnetic_runtime_humble22.json`。正式计划冻结所选登记，逐次核对 `configuration/gazebo_loaded_magnetic_libraries.json` 中进程实际加载的库路径和 ELF hash。相同上游源码版本不能代替不同发行版二进制的真实匹配。

## 证据入口

- [完整修复计划](../planning/reliability-v4-plan.md)与[逐次实施记录](../planning/reliability-v4-notes.md)
- [正式验证草案](../planning/reliability-v4-preregistration.json)与[串行运行器](../scripts/run_reliability_v4.py)
- [导航几何](V4_NAVIGATION_REFERENCE.md)、[导航评价](V4_NAVIGATION_EVALUATION.md)、[位姿不确定性](V4_POSE_UNCERTAINTY.md)
- [源时钟独立评价](V4_PX4_SOURCE_CLOCK_EVALUATION.md)、[磁坐标合同](V4_MAGNETIC_FRAME_CONTRACT.md)
- [原生起飞合同](V4_NATIVE_STARTUP_CONTRACT.md)、[完整任务身份时间审计](V4_TASK_TIME_IDENTITY_AUDIT.md)、[验收与开发关口合同](V4_ACCEPTANCE_CONTRACT.md)
- [Humble 隔离验证进度](HUMBLE_ISOLATED_VALIDATION.md)
- [真实开发录包导出记录](../results/development_offline_v4_humble04_car_seed00_export03/execution_status.json)、[Gazebo关闭诊断](GAZEBO_WSL_SHUTDOWN_DIAGNOSIS.md)

新一轮视频、图表、Word/PDF 与统一验收页应在实际探针和正式验证之后更新，报告成功、失败及缺失证据的完整分母。
