# Humble36：实际构建、起飞等待阻断与七帧几何复现

本记录保留失败和证据边界。Humble36 没有完成跟随任务，不能用于开发准入、性能定标或完整任务容量估计。正式实验仍为 **0/280**，种子 1000–1009 未使用。

## 实际构建与检查

来源提交为 `c76fb7c7971d2a4da60ba4b21aa528bb0c8b86cf`，冻结来源 canonical 为 `52105051ef72ea4c8b50e3ce6b4db9523cc8f6f2b9cd44e8ea9243f03996f403`。独立审阅文件为本机 `D:/WSL/UAVHumble22-validation/reviewed_freeze_review_humble36_02.json`，SHA-256 为 `4daf6532ee4aa61c85e463310d5509ad6eff04be9997ce46aa15286448310f3f`。

- Prepare、Copy、四包冷构建与 Validate 的实际有界动作均 PASS，均只执行一次，来源及所保留旧证据的绑定前后相同，无残留进程。
- Linux 实际完整回归 **1602 项：1597 通过、5 项原平台跳过**，78.200 秒。模块/ament 隔离、Humble 系统 FastCDR 来源与真实消息 CDR 往返均通过。
- Prepare01 曾在动作前因审阅文件中的固定枚举标签不匹配而拒绝，记录保留；02只修正这一审阅标签。该预检拒绝不是一次飞行。

实际验证入口为 `results/frozen_fullplan_v4_humble36/freeze_validation/build_validation_summary.json`。上述构建通过不代表实际飞行通过。

## 单槽开发试验原终态

正常冻结 runner 生成并执行了唯一汽车 `stage2_crossing / seed004 / 75 s` 的 PROBE 计划，显式启用汽车表面修复及 RTF 0.125 / flight wall 1000 s。计划 canonical SHA 为 `c2c38aa050fa0491d82c8f7136f0d6dacf05c4199077833d0c5aff134e576075`。入口工具经作者、root 与另一代理分别检查；Windows、Linux 各8项纯检查通过；没有改写 flight argv 或取得第二层 SITL 锁。

无人机始终停在地面 WAITING。root在确认地面状态后，使用绑定原完整 argv 与 `/proc` 启动身份的 Linux pidfd，仅给该 trial 发送 SIGINT，要求原逻辑完成停录、归档和清理。原 summary 显示：

| 项目 | 原始结果 |
|---|---|
| source 区间 | 0.02–64.42 s |
| monitor 墙钟时间 | 522.361 s |
| FOLLOW 开始、ARM、OFFBOARD | null / false / false |
| 最大高度 | 0.036786 m |
| 检测帧数 | 642，641 帧检测到目标 |
| 跟随设定值数 | 0 |
| median / P95 detection source latency | 0.104 / 0.116 s |
| median inference wall time | 0.358933 s |
| 原槽终态 | INFRASTRUCTURE_ERROR / FAIL，NO_TAKEOFF |

该段起飞前检测供给不等于完整跟随任务的固定10Hz身份覆盖。它没有任何目标请求、遮挡事件或跟随性能评价，不能据此宣称身份或汽车导航改善。

原 driver 为 `STOPPED_ATTEMPT_RETAINED`、returncode 2，record 保留 INFRASTRUCTURE_ERROR；observer 聚合未健康收尾（null及原错误保留），不能包装为正常 orchestration PASS。来源绑定前后相同、最终残留进程为空。原录制关闭 PASS，124136 条原生记录的归档、完整读回 PASS，owned spool 未保留；bag/ROS/Gazebo/PX4退出0，monitor被中断退出1，Agent按原SIGINT退出-2。原失败及全部记录不改写、不在该槽重试。

## 起飞等待的时序证据

12 秒独立只读 DDS 观察保存于本机 `D:/WSL/UAVHumble22-validation/humble36_live_startup01.json`。它没有发送命令或读 bag，记录30条心跳、3条VehicleStatus与12条supervisor诊断。29个心跳接收间隔为0.383053–0.416406墙钟秒，其中15个超过原0.4秒连续性门。12条diagnostic均为WAITING；最后累计status122/122接受，无时钟拒绝，所观测preflight均true、failsafe均false，odometry新鲜。

当前adapter按20Hz ROS/source时间发送；RTF 0.125使期望墙钟间隔正好0.4秒。supervisor的`_on_heartbeat`在墙钟间隔超过0.4秒时重置prestream开始时间，WAITING要求连续预流满足原时长。按外部实测接收序列回放，这一窗口的prestream累计不可达原要求。外部订阅器接收时刻不是supervisor内部回调时刻，因此不能把回放冒充内部逐事件追踪；但它与静态源码及持续WAITING高度一致。

下一独立候选将显式登记更高的adapter发送频率并检查实际运行参数和真实到达间隔，保留原0.4秒门、controller/supervisor频率和180秒native起飞预算。它需要新的来源、构建与实际飞行，不能直接声称已修好。更高adapter频率会同时提高TrajectorySetpoint发送率，必须明确记录，不能仅称心跳修改。

## 旧35数据的独立七帧几何复现

旧35录包的精确采集25.3、26.2、32.4、33.0、36.3、36.8、37.0秒已完整提取RGB-D、CameraInfo、全部候选、atomic observations及所有同源导航诊断。实际全扫197905条原生记录，GT未反序列化；7组header/K精确一致、临时缓存清理、源前后SHA相同。root另重算188个提取产物的实际SHA，全部匹配。

独立工具重现七帧所有已发布pair判定，关键未解释像素严格为 **14 / 7 / 0**，9项纯测试和另一代理的独立全部采样/判定重算通过。33.0秒的非选中pair297像素中16个无效仍保留并拒绝；前两次外部工具失败也保留。

14/7像素与selected的原扩张几何域相容，但名义车体内分别仅1/14、0/7；距其原exclusive实测support约1.5 m，距已拟合face约3 m，因此原visible-only条件拒绝。第三候选原exclusive缺数组来自detector发布条件；按原native采样补建的追加离线模型虽有效，对14/7像素仍解释0个。不能用第三车假设或扩张域内这一条件直接放行。

root已亲自查看原RGB红点放大及空间支持图。结果把后续研究收敛到可见表面支持与模型适配；它不是新运行时修复、物理身份保证或旧飞行通过。入口为本机 `D:/WSL/UAVHumble22-validation/humble35_pixel_reconstruction01/findings_zh.md`，图为该目录 `visual02/critical_three_frames.png`、`spatial01/acquisition_36300000000_spatial.png`。历史35原始结果保持。

另一个离线单面共享几何域候选已通过14项数学检查及七帧独立反事实核算：9个原有效单面模型重建、4个双面模型保持、8个无效/缺失模型仍UNKNOWN。它没有使任何原本拒绝的选中目标pair通过，14/7像素的可见支持拒绝也没有改变。因此没有作为成功修复接入。该候选是新的工程假设域，不能描述成原独立参数域的等价化简或概率保证；结果保存在本机 `single_face_seven_frame_counterfactual01/counterfactual.json`。
