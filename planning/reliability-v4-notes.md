# Reliability v4 实施记录

## 计划快照

2026-10-29 用户授权修复剩余问题，计划见 `reliability-v4-plan.md`。首要任务是对照原始失败和代码隔离原因，不预设放宽安全门或改写失败结果。

## 决策

- v3 冻结源和正式结果不修改；新开发/研究使用独立目录。
- 先在已有 Jazzy 栈处理算法和工程问题，Humble 独立验证另排。

## 发现、偏离与新未知

- 已证实时序失败：car/raw/seed01 与 car/position/adaptive/seed03 最后接受采集均为 29.600 s，恢复采集 30.200 s、处理 30.404/30.408 s；在 30.352 s 先因旧测量年龄 0.752 s 悬停。此时融合拒绝计数为零。person/fixed/seed04 恢复推理约 27 ms，但采集间隙已达 0.9 s，说明仅优化推理不足。
- 分母区分：全部 40 个汽车速度试验短事件 13 PASS/27 FAIL，行人对应 39/1；旧“31/33”来自其他审计范围，不能混用。
- 已证实参考点偏差：22–29.7 s，car adaptive seed00 相对自身表面参考的距离/高度均值误差约 -0.030/-0.002 m，独立模型原点指标却为 +2.112/+0.818 m。person 对应 -0.039/-0.007 m 和 +0.038/+0.724 m。必须增加运行时地面参考估计，不能靠增益或离线固定补偿纠正。
- 云台与身份链继续独立审计。原始记录缺世界坐标测量、创新与协方差，因此“重选后连续拒绝”成因尚未确定；先补诊断。

## 实施中的变更

- 检测快照新增 RGB/Depth 回调接收、提交、worker 开始、采集间隔和等待时间诊断，保留非排队 worker 与原接受语义。
- 单次试验支持显式 `--max-inference-rate-hz` 与 `--monitor-tick-s`，默认仍为原 5 Hz / 0.10 s，以便独立消融。monitor 的 ACK 后最小遮挡驻留不变；旧试验不重标。
- 导航参考采用独立 RGB-D 点云地平面和声明的类别尺寸先验，身份关联/云台继续使用原表面轨迹。静止汽车仅在可见端面形状可区分长宽时接受；不可观测、侧视、地面缺失须明确拒绝。

## 验证

- 启动前 Git：`main` 干净，HEAD `01e3477`。
- 检测 worker 回归 13 项通过；基础设施运行器回归 5 项通过（Windows Python unittest）。未因本轮修改放宽 0.60/0.75 s 门限。
- 当前可用内存约 14 GB；C 盘约 12 GB、D 盘约 199 GB可用。已查实际 Linux 进程，暂无 PX4/Gazebo/ROS 仿真残留；新 bag 放 D 盘。

## 独立开发探针（不替代正式重复）

- `/root/uav_tracking_fullplan_v4_timing01` 已独立构建/导入隔离及 614 项 Linux 测试通过。结果存 `results/frozen_fullplan_v4_timing01`，冻结后不修改源码。
- `reliability_v4_timing10_car_seed01`、`...seed03` 保持原640/YOLO11s/4线程、RTF0.5、monitor0.10s，仅检测上限10Hz：两次均正常完成45s FOLLOW窗口，基本飞行、短恢复和显式重选通过。seed01最后有效采集29.7、恢复采集30.2/处理30.392，恢复年龄0.692s；406次测量0拒绝。仍待完整离线门，不把monitor0返回当正式PASS。
- `/root/uav_tracking_fullplan_v4_nav01` 已独立构建/导入隔离及652项Linux测试通过。结果存 `results/frozen_fullplan_v4_nav01`。
- `reliability_v4_nav_car_clean_seed00` 首次地面参考闭环 **失败并保留**：17.3s开始测量，下降至新高度并偏航后表面观测横向摆动、连续门控拒绝，19.6s最后尝试NIS50.35，最终LOST/悬停，monitor退出1。不能因几何单测通过宣称实际闭环完成。
- 该失败的独立ego评价已完成：位置holdout RMSE0.0596m、姿态RMSE0.0837rad/max0.2034rad。正在独立比较PX4 source时间/接收时间、姿态误差与采集TF，未调整门限、R或控制增益。
- 导航接线审查发现并在主副本修复：无效消息不得携带表面数值；可选几何异常须转invalid而不退出ROS；pose_std必须有限非负；混合相机frame拒绝；导航要求RGB/Depth同采集(1e-6s容差)。这些新修复未回写nav01冻结。
- Windows临时目录使用8.3别名，造成两个guard fixture的冻结根不一致；仅测试fixture规范化resolve，未放松生产冻结检查。专项回归通过。

## 环境与后续实验

- 官方Jammy WSL镜像325.3MiB已下载并核验Canonical SHA256，独立`UAVHumble22`注册成功，实际Ubuntu22.04.5/Python3.10.12，路径`D:\WSL\UAVHumble22`。APT准备进行中；尚未声称ROS/桥接/SITL验证通过。
- 现有Ubuntu24/Jazzy注册表路径为D盘；C盘余量不等于WSL ext4可增长余量。大录包仍放D盘新结果目录。
- 新正式工程验证草案为两类别×六关键条件×10种子=120槽，地面参考自适应KF版本；与原v3四基线科研分开。必须先通过开发探针门，才冻结与执行；不可用草案替代实际终态。

## nav02 消融与新的修复项

- `/root/uav_tracking_fullplan_v4_nav02` 构建/导入隔离及709项Linux测试通过，冻结源码不回写。`reliability_v4_nav_car_wmm_seed00` 仅修改声明磁场仍失败，不能声称该改动已消除航向误差。
- `reliability_v4_nav_car_cov_wmm_seed00` 加入PX4位姿协方差传播后20秒窗口正常结束，表面身份始终为同一轨迹。独立全记录物理评价得到base_link距离RMSE **0.6693m**、高度 **0.2044m**；导航有效覆盖 **87.86%**，导航位置RMSE **0.7655m**。这是开发证据，**尚未通过完整验收**。
- 导航在19.05–19.55s及36.15s后不可用，保留失败尾段。后段原因为 `car_face_heading_inconsistent` / `car_end_view_required`，说明仅支持可见端面不足以覆盖计划内转弯；正在增加可观测端面/侧面的几何唯一假设，歧义或截断仍拒绝。
- 独立审查修复了raw/EMA输出初始协方差、2D转首次3D初始化、fixed基线分离固定R与共享门控R，以及pose cache必须为map→base_link的缺陷，专项测试通过；新修复未回写nav02。
- 已实现显式源时钟合同（尚待实际SITL验证）：`--px4-time-mode source_sim`在rcS启动client前设置 `UXRCE_DDS_SYNCT=0`；adapter验证源采样/发布时间与ROS时钟同域，以采样时间发布Odometry，单独保留接收时间诊断。跨域、过旧、未来、重复及时间回退不刷新位姿，回退要求节点重启。兼容旧运行的receipt模式保留并明确警告。20项时钟/坐标/协方差专项回归通过。
- 磁接口审查出现新的可证伪假说：Gazebo8.15磁插件每帧查表覆盖world磁向量；默认NED输出、传感器旋转与PX4的磁分量映射可能不一致。正在核对钉住源码并建立任意姿态解析测试，**尚未把它确认为实测航向误差根因**，也未修改原PX4或旧试验。
- 隔离Ubuntu22/Humble及Harmonic依赖安装、Python依赖检查完成；开始串行构建，尚未完成桥接或SITL验收。

## nav03 前置构建

- 原 Ubuntu 的隔离 `/root/PX4-Autopilot-v4mag` 已成功完成真实构建；Micro-CDR 网络失败通过独立、精确提交缓存解决，未改系统全局 Git，未复制旧生成头或伪造构建 stamp。日志为 `results/px4_magnetic_build_20261028T210700534820152.log`。
- `config/px4_magnetic_runtime.json` 已由构建后验证生成。实际 PX4 ELF SHA256 为 `9450433e65ecff4f730480b83a29abbecae87f10304f828d7930a008b43ac3a6`；独立源码补丁、依赖提交和启动 marker 绑定于该记录。该文件是机器专用证据，Git 忽略但新冻结必须包含。
- 原 Ubuntu 与 Humble 分别登记 Gazebo 实际安装的动态库；相同源文件不代表两个发行版 ELF 相同。等待登记校验接线完成后创建 nav03 新冻结，验证 `source_sim`、磁接口和汽车侧面/双面几何。构建成功不代表航向或闭环验收通过。

- `/root/uav_tracking_fullplan_v4_nav03` 四包构建及导入隔离通过，但完整 Linux 806 测试有两项旧 shell fixture 失败：测试只拦截 PATH 中的 `python3`，新入口显式使用 `/usr/bin/python3`，因而绕过 fake interpreter。该副本保留失败日志，未启动飞行；主工作区仅修正 fixture 显式设置 `STAGE1_PYTHON_EXECUTABLE`，六项专项通过。
- 新冻结 `/root/uav_tracking_fullplan_v4_nav04` 四包构建、导入隔离及 **806 项 Linux 测试全部通过**，结果存 `results/frozen_fullplan_v4_nav04`。开始 `reliability_v4_nav04_car_clean_seed00`，20 秒 FOLLOW，10 Hz、source_sim、新磁接口、地面导航与位姿协方差；开发种子 0，不消费正式种子。
- 此 nav04 探针在起飞前基础设施中止：`px4 exited 255`，日志明确 `. cannot open etc/init.d-posix/rcS`。新隔离构建的 rootfs 尚无 `etc` 链接，而旧启动入口只给 `-s`，禁止了 PX4 的默认构建目录发现，依赖旧环境先前运行的残留初始化。Gazebo 实际磁库已与登记匹配，但 PX4 未完成启动、无磁 marker，不能计为飞行成功。修复主入口显式传本次 build/etc 和 `-w build/rootfs`，由 PX4 上游自身创建链接；不复制旧参数、生成文件或改 ELF。

## nav05 起飞初始化与原生启动修复

- `/root/uav_tracking_fullplan_v4_nav05` 四包、导入隔离、806 项 Linux 测试通过。`reliability_v4_nav05_car_clean_seed00` 使用新显式 build/etc 启动，PX4 和磁 marker 均成功，实际磁库匹配登记；但尚未进入 FOLLOW，在起飞中止。
- 独立时钟报告确认 `clock_domain_valid=true`，1496 个 raw/diagnostic 配对全部使用同域有效源时刻，source-to-receipt 最大约8 ms。整体仍为 **FAIL**：13.944 s `reset_counter` 11→12 后原保护持续拒绝，supervisor 因 odometry_stale 中止。不能将“保护正确触发”当作该试验成功。
- 原始 ego-only 缓存显示此重置发生高度约1.572 m、yaw 修正约0.026 rad。钉住 PX4 的 `checkHaglYawResetReq()` 正是在起飞 HAGL>1.5 m 时强制首次空中磁对准，`heading_good_for_control` 还需其后1秒；地面多等几秒无法消除这次正常初始化。
- 主工作区加入显式 `--takeoff-mode px4_native`（默认 legacy 保留）：NAV_TAKEOFF 的 param4..7 明确 NaN，PX4 以机载当前位置和 AMSL+MIS_TAKEOFF_ALT 原生起飞，完成后 AUTO_LOITER；最终对准和高度/速度稳定后再接管 Offboard。原 frame_guard 不修改，接管后的 reset 仍锁定 hold/restart。
- 新模式 pre-rcS 显式记录 `MIS_TAKEOFF_ALT=3.0`、`COM_TAKEOFF_ACT=0`、`SENS_IMU_MODE=1`，消除任务结束动作和多 EKF 实例假设。VLP 源时效0.50秒，1Hz flags 用独立1.50秒辅助状态门；原里程计0.50、目标0.60/0.75门不变。HOLD/FOLLOW 之前检测器的既有 activation epoch 阻止起飞图像进入关联/KF；handoff 清理 supervisor 缓存。
- native/legacy/readiness/detector 39 项专项通过；新模式真实飞行尚未运行。Humble Agent 独立构建成功，已将唯一重负载窗口交给其 patched PX4 编译，root 不同时启动仿真或录包分析。

## Humble03 原生起飞、录制边界与下一冻结

- Ubuntu22/Humble/Harmonic 隔离环境完成 Agent、PX4、ros_gz 与四包构建，消息/ament 导入均在独立冻结内；`humble03` 的 861 项 Linux 测试通过。Humble 原生 PX4 ELF SHA256 为 `6cf784c1cb4de2945b4291aa9391a2301c78315a1462ef3f51f541e119fd7ce7`，使用专用动态库登记，不能以 Jazzy 登记替代。
- `/root/uav_tracking_fullplan_v4_humble03` 汽车种子0的20秒 FOLLOW 探针实际完成 NAV_TAKEOFF、空中磁对准、AUTO_LOITER→Offboard→FOLLOW，monitor返回0。其原生起飞约花39墙钟秒、约12.4源秒，暴露原40墙钟秒流程预算可能误截正常仿真。
- 下一版在主工作区改为40源秒流程预算和独立180墙钟秒上限，独立 STEADY_TIME timer 在 `/clock` 暂停时仍检查墙钟。每条 phase 保留 source 时间后缀及新增双起点/elapsed，独立评价核对；不放宽odom/target时效、frame reset或接管稳定门。native专项52项通过，runner专项44项通过；尚未在新冻结飞行。
- Humble03 原压缩 bag 的原生读回失败：原生解压少128KiB；独立流式解压得到838205440字节SQLite，integrity/quick_check均ok、40852条与metadata一致，但压缩frame未完整终结。原件SHA和失败记录保留，诊断派生副本仅用于定位，原试验不能因其SQLite可恢复而改判正式PASS。正在将录制与压缩分开，并增加关闭/完整性/原生读回门。
- 新导航诊断 schema2 分别记录几何R、精确样本传播的位姿R及实际合成R，记录来源pose6×6/源时刻/杆臂、采集TF、质量字段、测量处理与输出发布时间及初始化速度。36项导航/不确定性专项通过；诊断不改变线上KF算法，不宣称已额外实现质量缩放。
- 发现现有 `estimator_method` 只切表面轨迹输出，未切独立导航KF。为避免错误宣称，新增同一最终录制的离线四法比较草案；20条正式stage1_velocity含失败全部保留，GT仅评分。纯复放、导出与在线等价审计及开发定标仍待完成，120工程槽仍未冻结执行。

## Humble04 原生录制修复与状态计时发现

- `uav_tracking.recording_archive` 将录制改在唯一拥有的ext4 spool中使用原生sqlite3无压缩。关闭后SQLite页/metadata/topic条数核验，再由标准zstd CLI产生完整frame，执行独立流式SHA往返与Humble SequentialCompressionReader全量读取/解压SHA；校验后原样发布到结果盘，失败保留spool。真实Humble03诊断副本838205440字节/40852条的完整归档实验通过，未改旧槽判定。
- `/root/uav_tracking_fullplan_v4_humble04` 的4包、导入隔离与901项Linux测试通过。新car20秒槽41174条消息的原始bag_integrity、source_clock、native_startup均PASS。导航覆盖100%、GT202/203=99.51%；KF位置RMSE0.09645m/速度0.07453m/s；base_link距离/高度RMSE0.62951/0.26644m，尾10秒0.01892/0.00447m。仍缺最后GT bracket导致严格稳定时间右删失，且无遮挡surface评价不完整，不能将这几项PASS拼成正式工程PASS。
- 同冻结person20秒探针未进入FOLLOW：source5.652s、native elapsed0.600sim/2.520wall时，status receipt wall age2.010s超过2.000s而ABORT；status源戳5.152s、源龄仅0.500s，odom接收龄0.014s，failsafeFalse/preflightTrue。录制完整性和source_clock PASS，native FAIL，失败原件保留。正在将source_sim supervisor状态时效与原source1.0s/future0.05s合同对齐，并独立保留wall停流上限；不改odom/目标/重置保护门，不自动重跑同槽。
- Gazebo两槽均在关闭后退出-11；kernel定位Ruby gz CLI在libgcc展开栈时SIGSEGV，正在只读匹配core取栈，不把运行成功解释为清理正常。ROS launch父退出0也不能掩盖子节点关闭时RuntimeError。
- 新独立导航在线数值复现helper和同测量四法纯core已通过专项，独立bag导出仍在集成。共享reader新增可选保留Clock，导航新评价显式启用，避免其它话题停流后遗漏clock-only静默尾段；历史默认读取行为保留。尚未消费任何正式种子。
- 新source_sim supervisor将VehicleStatus源龄明确保持1.0s、未来界0.05s，并独立使用10s有效接收墙钟停流界；旧receipt_wall默认仍为1s。复用源时钟验证拒绝非法/过旧/未来/重复，源戳或ROS clock回退锁止至节点重启，拒绝不刷新已接受状态。状态墙钟界只在ROS-time控制tick检查，不宣称暂停clock时有独立10s steady watchdog；原生180s独立steady总预算另行保留。新run_config/runtime YAML和正式runner逐项绑定，主协议明确Humble22登记；新源合同/原生/runner/离线审计/时钟专项105项通过，尚未新冻结或实际飞行。
- 四法replay的导出/运行脚本及replay_comparison、replay_export、navigation_reproduction明确作为纯离线来源单独绑定，完整source manifest仍包含它们；只改离线工具不要求重飞。recording_archive和core/kalman仍属飞行关键来源。fixture helper仅为ORCHESTRATION_FIXTURE_ONLY，不是实际运行证明。
- 新离线工具在04 car有效原始bag上完成204测量/1220输出的真实数值复现PASS（1016次缓存重复不重更新），独立native核对首次为证据不完整：144个协方差及20个年龄差异均恰对应TargetState.msg的float32 wire量化，JSON诊断为float64。首次导出及164差异保留在`results/development_offline_v4_humble04_car_seed00_export01`，不扩大整体数值门限，另按字段声明精确cast再核对。新preserve_clock导航评价保留10574个Clock，区间18.0–38.2及203分母、202真值、原KF/物理指标均未改变，严格末端稳定性仍右删失；独立导出不替代闭环工程验收。
- v4后续协议明确`gazebo_render_driver=llvmpipe`，trial_spec/CLI/run_config逐项绑定，auto保留历史语义。正式runner独立核验`configuration/gazebo_rendering_libraries.json`：三条CPU环境值、原始/proc映射的inode/device与每个记录ELF身份一致、SHA结构、实际swrast与LLVM库、没有WSL D3D12驱动及捕获状态PASS；缺失或冲突为基础设施失败。渲染变更仅面向新槽，旧auto退出-11和失败证据不覆盖，不混为同一性能条件。
- 精确wire核验修复后，另名`results/development_offline_v4_humble04_car_seed00_export02`真实重导exit0、整体PASS：204测量/1220输出，独立online float64数值复现及全部1220对native-state均PASS。只对消息声明为float32的协方差与预测年龄执行显式cast后精确比较，量化后1ULP差仍拒绝；Point/Vector3和online float64门保持原样。源码/消息导入隔离及NavEstimator、KF、models、uncertainty、TargetState.msg对04的哈希等价已保存。旧export01缺证原件保留；此开发clean槽不代替正式配对重复、失败/遮挡任务或工程验收。renderer协议/runner最终47项专项通过，等待全源合并后05隔离构建与全套。
