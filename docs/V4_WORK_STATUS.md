# v4 开发与验证状态

更新：2026-10-29。**v4 仍在开发验证，整个项目尚未完成本轮修复后的正式验收。** 已发布的 v3 交付包含失败和证据边界；其“最终报告”文件名不代表 v4 已通过。

本次 GitHub 更新是**开发检查点**。`nav04` 因新 PX4 rootfs 的启动路径问题终止，`nav05` 在约 13.944 s、1.57 m 时出现 PX4 起飞阶段磁航向对准 reset；保护逻辑随后停止继续任务。两次失败及原有证据完整保留，没有用后续代码覆盖失败记录。新 `px4_native` 原生起飞分支先交由 PX4 起飞、完成航向对准与悬停资格检查，再切换 Offboard；**该分支尚未完成真实 SITL 飞行验证，单元测试不能替代飞行证据**。

## 当前进展

| 内容 | 已有工作 | 尚需完成 |
| --- | --- | --- |
| 导航参考 | 独立 RGB-D 地面参考；汽车端面/侧面/双面唯一几何解；独立滤波和物理距离/高度评价；回归测试通过 | 新几何版本实际闭环、遮挡和多目标交叉验证 |
| 时间与不确定性 | 同采集 RGB-D/TF、PX4 协方差、源时钟与 reset 保护；`nav05` 实际录制并独立审计 raw PX4 1496 条，`clock_domain_valid=true`、receipt 最大约 8 ms | 原生起飞新流程重新录制，取得完整时钟及空间连续性验收；`nav05` 整体仍因启动 reset 失败 |
| 磁传感器接口 | 钉住 ENU/gauss 与 FLU→FRD 合同；Jazzy 环境实际 PX4 ELF 构建、启动 marker 与两项真实加载磁场库均已核验 | Humble 独立 ELF/加载库核验、原生流程动态 ego 评价和闭环探针；不能预设其消除全部航向误差 |
| 环境迁移 | Ubuntu 22.04/Humble 独立环境；Agent、patched PX4 和 ros_gz 已独立编译通过；系统 ABI 与独立小世界 RGB-D/时钟/服务桥接通过；保留已有 Jazzy 环境 | 同步最终原生启动源码后构建工程，完成本环境 SITL 与完整闭环验收 |
| 原生起飞 | 启动参数、原生起飞/Offboard 时序、独立就绪条件和源码冻结；独立离线审计接口 | 新分支实际 SITL、启动参数/命令/模式时序与最终交接的独立录包评价 |
| 指定个体证据 | 从首次 REQUEST 到完整 `/clock` 末尾的固定 10 Hz 身份覆盖；未确认与静默尾段保留为未知 | 最终版本多目标录包的独立物理身份审计与完整任务覆盖门检查 |
| 正式工程重复 | 运行器、不可覆盖槽位账本、完整分母与评价接线 | 开发关口通过、性能门预登记、冻结源码/环境后执行 120 槽 |

已有开发探针证明了部分时序改进，也暴露了导航丢失和转弯限制。失败录制和尾段仍保留；单元测试、构建成功、进程正常退出和少量探针都不能代替完整工程通过。

## 接下来如何验收

1. 完成每环境的隔离 PX4、ROS 与桥接构建，生成真实源码/二进制 manifest，核对实际加载动态库与启动日志。
2. 以开发种子执行新的行人/汽车、指定个体、短长遮挡、云台与交叉探针，保留 raw bag、配置、hash 和独立评价。
3. 在正式结果出现前登记导航性能门；最终开发关口须覆盖两类别 × 六组，并对不可修改的槽位、真实启动/磁场/源时钟/导航/身份/云台证据独立重新验收。只有性能门已合法登记且这 12 格通过，才允许冻结和执行正式计划。当前状态仍为 `UNREGISTERED_PENDING_DEVELOPMENT_PROBES`。
4. 正式 v4 为两类别 × 六组 × 十个留出种子 **1000–1009 = 120 槽**，每槽只尝试一次；失败和基础设施中止继续计入分母。开发探针禁止消费这些正式种子。

v4 使用相同留出种子在类别/组之间比较。原 v3 的四基线研究使用 0–9，属于另一份冻结研究；不能把 v4 表述为与 v3 配对重跑或四基线复现。

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

新一轮视频、图表、Word/PDF 与统一验收页应在实际探针和正式验证之后更新，报告成功、失败及缺失证据的完整分母。
