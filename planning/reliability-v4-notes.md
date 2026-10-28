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
