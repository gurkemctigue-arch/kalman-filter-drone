# V3 阶段一失败原因只读诊断（草稿）

本稿说明 v3 正式重复试验中的可用性失败，不能把安全悬停或未观测到 UUID 错切写成跟随成功。现有证据支持两条已发生的路径：短遮挡后的有效测量在 0.75 s 时效边界之后到达，导致任务锁止；显式重选后，连续三维融合拒绝使最后有效测量时间冻结，再次触发锁止。后者为什么被拒绝，尚不能仅凭现有遥测归因于错误测量、真实表面锚点变化、TF 误差或过紧的滤波模型。

## 审计范围与版本

- 冻结源码：WSL `/root/uav_tracking_fullplan_v3`。只读检查了相关源码，并核对其 SHA-256 与该次试验的 `configuration/source_sha256.json` 一致。
- 证据目录：项目 `results/frozen_fullplan_v3/`。读取小型 JSON、结束试验的 `monitor.log` 和必要遥测时间片；未读取或解压 bag，未运行 YOLO、仿真、评价器、测试或构建，也未修改冻结源码或任何试验结果。
- 完整扫描了已结束的 **80 次 velocity 试验汇总**的检查字段；深入检查 **3 次 FAIL 和 3 次 PASS** 的离线 JSON，部分使用遥测片段。没有逐条审计全部离线记录，不代表全体计划试验或全部 166 次记录的结论。
- velocity 汇总更新于 `2026-10-27T07:55:01.232714+00:00`。position 矩阵在审计时仍在增长，本稿仅对已结束的指定 position 试验作结论，不冻结其总完成数或通过率。
- [导入隔离记录](../results/frozen_fullplan_v3/freeze_validation/import_isolation.json)显示核心和节点模块来自 v3 冻结根目录，`isolated: true`；源码哈希清单中的旧 `build/lib` 副本不应替代这些实际导入源。

## 完整 velocity 汇总能够说明什么

来源：[80 次正式 velocity 汇总](../results/frozen_fullplan_v3/fullplan_v3_online_estimators_repetition_report.json)。

| 条件 | PASS / 已记录 | FAIL |
| --- | --- | --- |
| person / raw | 10 / 10 | 0 |
| person / EMA | 10 / 10 | 0 |
| person / fixed KF | 9 / 10 | 1 |
| person / adaptive KF | 10 / 10 | 0 |
| car / raw | 3 / 10 | 7 |
| car / EMA | 3 / 10 | 7 |
| car / fixed KF | 3 / 10 | 7 |
| car / adaptive KF | 3 / 10 | 7 |
| 合计 | 51 / 80 | 29 |

29 个失败记录全部未通过 `offline_occlusion` 和 `long_occlusion_braking_from_motion`，其中 14 个还未通过 `sustained_tracking_after_reselection`。这三个字段在这些汇总记录中均无缺项。29 个失败记录的 `exclusive_setpoint_fields`、`explicit_new_task_after_loss`、`full_recorded_trial_end` 均为真；这仅说明汇总中的相应证据通过，不能据此证明身份绝对正确、每次控制动作安全或失败试验已完成有效跟随。

汽车四种滤波方式均只有 3/10 通过，不代表通过的是同三个种子，也不支持“自适应 KF 已提高正式端到端成功率”的结论。完整失败分母必须保留。

## 本稿使用的代表记录

下列简称均对应完整试验名，便于后续查找原始证据。

| 简称 | 完整试验名及离线结果 | 用途 |
| --- | --- | --- |
| C-RAW-01 | [fullplan_v3_online_estimators_car_velocity_raw_seed01](../results/frozen_fullplan_v3/fullplan_v3_online_estimators_car_velocity_raw_seed01/offline_evaluation.json)，FAIL | 短遮挡后锁止，但重选后持续跟随通过 |
| P-FIX-04 | [fullplan_v3_online_estimators_person_velocity_fixed_kf_seed04](../results/frozen_fullplan_v3/fullplan_v3_online_estimators_person_velocity_fixed_kf_seed04/offline_evaluation.json)，FAIL | 短遮挡失败，重选后连续融合拒绝 |
| C-POS-03 | [fullplan_v3_position_compatibility_car_position_adaptive_kf_seed03](../results/frozen_fullplan_v3/fullplan_v3_position_compatibility_car_position_adaptive_kf_seed03/offline_evaluation.json)，FAIL | position 模式中时效锁止与融合拒绝分别出现 |
| C-RAW-00 | [fullplan_v3_online_estimators_car_velocity_raw_seed00](../results/frozen_fullplan_v3/fullplan_v3_online_estimators_car_velocity_raw_seed00/offline_evaluation.json)，PASS | 同类别/控制模式、不同种子的时效边界对照 |
| P-RAW-04 | [fullplan_v3_online_estimators_person_velocity_raw_seed04](../results/frozen_fullplan_v3/fullplan_v3_online_estimators_person_velocity_raw_seed04/offline_evaluation.json)，PASS | 与 P-FIX-04 同 seed、类别和控制模式的基线对照 |
| C-POS-02 | [fullplan_v3_position_compatibility_car_position_adaptive_kf_seed02](../results/frozen_fullplan_v3/fullplan_v3_position_compatibility_car_position_adaptive_kf_seed02/offline_evaluation.json)，PASS | 同类别/控制模式/滤波方法、不同种子的对照 |

上述深入检查的离线 JSON 均有可读 `/clock`、`read_errors: {}` 和完整录制尾部覆盖。因此这些代表记录的 FAIL 不能归结为 bag 解码失败或提前截断评价。

## 路径一：采集间隔尚短，但到达时已超过有效性预算

C-POS-03 的配置 `short_occlusion_s` 是 0.2 s，实际关闭/打开请求为 29.700–30.100 s，区间长 0.400 s。服务成功应答为 29.800 和 30.200 s。关闭应答后的保持、0.05 s 渲染余量与监控调度均包含在实际请求区间中；不能把名义 0.2 s 直接当作有效图像遮挡时长。

以下行号是 C-POS-03 [telemetry.jsonl](../results/frozen_fullplan_v3/fullplan_v3_position_compatibility_car_position_adaptive_kf_seed03/telemetry.jsonl)的 1 起始文本行号，时间均为仿真秒。

| 遥测行 | 到达/处理时间 | 证据 |
| --- | --- | --- |
| 2281 | 29.720 | 最后接受的 selected track 1 测量采集于 29.600，`rejected_measurements=0` |
| 2370 | 30.352 | 控制状态 HOVER，`reason=stale_target`，`measurement_age_s=0.7520000339` |
| 2371 | 30.360 | 输出 target state LOST |
| 2382 | 30.408 | 采集于 30.200 的新候选已经到达，但任务 track 1 仍 LOST；另建 track 2，任务不自动转移 |

采集间隔是 `30.2 - 29.6 = 0.6 s`；恢复候选传输/处理约 0.208 s。它到达时旧测量年龄为 **0.808 s**，已经超过固定 0.75 s，且 30.360 s 的输出定时器已使任务进入需要显式重选的锁止状态。这条链中选中轨迹的融合拒绝计数仍为 0，不能将首个丢失归因于 KF 异常观测门控。

C-RAW-01 出现几乎相同的路径：遥测第 2290 行最后接受 acquisition 29.600；第 2377 行在 30.352 s 因 `stale_target` HOVER，第 2378 行 30.360 s LOST；第 2390 行 acquisition 30.200 的新观测在 30.404 s 才处理。其新 UUID 在 49.800 s 确认后仍可持续跟随约 13.400 s，所以该次“重选后跟随”通过，整体依然因短事件和后续长事件的前置状态失败。

对照 C-RAW-00：同样最后接受 acquisition 29.600（遥测第 2285 行），恢复 acquisition 30.200 在 **30.332 s** 处理（第 2373 行），旧测量年龄 **0.732 s**，在阈值前恢复同一轨迹。它比 C-POS-03 的处理时刻早 0.076 s；这是跨种子/模式的时效现象对照，不是只改变延迟一个变量的因果实验。

保护逻辑按既定边界工作，但 0.4 s 左右的实际请求和约 0.2 s 延迟令系统接近不可恢复边界。这是正式试验中的跟随可用性限制，不能因为之后正确悬停就计为成功。

## 路径二：重选后有检测和关联，但三维融合连续拒绝

C-POS-03 在 49.808 s 确认显式选择的新 UUID，任务轨迹为 3。其遥测记录如下：

| 遥测行 | 处理时间 / acquisition | 选中轨迹的状态 |
| --- | --- | --- |
| 5183 | 49.808 / 49.600 | 新任务开始，接受测量，拒绝计数 0 |
| 5387 | 51.208 / 51.000 | 仍接受，`last_measurement_s=51.0` |
| 5413 | 51.396 / 51.200 | `associations=[[3,0]]`，但 `matched=false`、拒绝计数 1，最后有效测量仍 51.0 |
| 5442 | 51.596 / 51.400 | 同一候选仍关联 track 3，拒绝计数 2，最后有效测量仍 51.0 |
| 5463 | 51.752 | HOVER / `stale_target`，年龄 0.7520000339 s |
| 5464 | 51.760 | LOST，之后任务不自动切至跟上新候选的 track 4 |

离线结果保留了重选后 1.848 s 的活动控制跨度、613 条 LOST 状态和 223 条 HOVER 控制状态，直到记录结束 62.880 s。`first_uuid_mismatch_s=null`、接收时钟回归计数 0；失败来自实际后续失测和悬停，不能以“已确认新 UUID”抵消。

检测片段能够进一步排除“这两帧没有候选或没有有效深度”的解释，但不能独立证明三维测量正确：

| 检测遥测行 / acquisition | 框 `[x1,y1,x2,y2]` / px | 深度 / m | 置信度 / 深度有效率 |
| --- | --- | --- | --- |
| 5385 / 51.0（接受） | `[320.94,57.09,383.71,102.04]` | 17.0913 | 0.9042 / 1.0 |
| 5411 / 51.2（拒绝） | `[321.97,68.73,382.59,113.92]` | 17.1917 | 0.9018 / 1.0 |
| 5440 / 51.4（拒绝） | `[307.22,83.79,366.90,126.73]` | 17.2963 | 0.8895 / 1.0 |

这里存在明显的图像框位置变化，深度仍有数值且置信度较高。遥测没有记录拒绝时的原始世界坐标测量、创新向量、P/R 矩阵及马氏距离，也没有独立真值表面锚点；不能进一步断言是正确表面运动被门控误拒，或是视觉/深度锚点异常理应被拒。更不能据此直接放宽门槛。

P-FIX-04 有相同的拒绝链：第 5320 行接受 acquisition 50.300；第 5349、5378、5409 行分别处理 50.500、50.700、50.900，均仍关联 `[3,0]`，拒绝计数依次 1、2、3；第 5410 行 51.052 s 因年龄 0.752 s HOVER，第 5411 行 51.060 s LOST。其重选后活动控制跨度仅 1.548 s。

P-FIX-04 的第 5347 行检测框为 `[361.87,0.97,386.89,68.02]`，acquisition 50.500、深度 12.3379 m、置信度 0.7107、深度有效率 1.0；随后两帧框分别为 `[378.62,18.00,402.28,96.16]` 和 `[360.16,46.49,383.19,122.64]`，深度约 12.27–12.29 m。这支持检查接近画面上沿时框/表面锚点变化的假设，但本稿没有验证裁剪、相机运动补偿或真实物理测量误差，不能把假设当成原因。

P-RAW-04 是现有同 seed、类别和控制模式的匹配对照：两者 `seed=4`、Gazebo seed 5、目标速度 0.47360480897374346 m/s、320 推理尺寸、2 线程、名义短遮挡 0.2 s、clean、standard motion 配置一致，方法分别为 raw 和 fixed KF。raw 短事件在 30.328 s 同轨迹恢复（遥测第 2386 行）；新任务在 49.720 s 确认（第 5189 行），其后活动控制跨度 13.348 s 并通过。闭环飞行路径、检测几何和实时调度仍会随滤波结果变化，因此这一对结果显示了基线差异，但不足以隔离滤波门控的单一因果作用。

## 后续长事件失去“运动中丢失制动”的前置条件

三次深入检查的失败试验在短事件后已长期 LOST/HOVER，到固定 FOLLOW+25 s 的长遮挡触发时未在正常跟随。因此它们的 `prediction_observed=false`，初始速度接近零，`braking_from_motion_demonstrated=false`：

| 试验 | 长请求区间 / s | HOVER 入口附近速度 / m/s | 新任务之后的控制跨度 / s |
| --- | --- | --- | --- |
| C-RAW-01 | 42.700–45.900 | 0.00996 | 13.400，PASS |
| P-FIX-04 | 42.300–45.500 | 0.00713 | 1.548，FAIL |
| C-POS-03 | 42.700–45.900 | 0.00498 | 1.848，FAIL |

这不是三次独立的“长遮挡制动失败”机理。短事件造成的任务锁止让后续计划事件不再满足运动跟随前提；对完整脚本应保留 FAIL，但研究统计应区分“长事件前已经失效”和“运动中长丢失后未成功制动”，避免把一个早期故障重复解释为多个独立故障。

作为对照，C-POS-02 在长事件前仍跟随，HOVER 入口速度约 0.4672 m/s，43.360 s LOST 后制动检查通过，重选后控制跨度 13.000 s。C-RAW-00 的对应速度约 0.5342 m/s，重选后控制跨度 13.000 s。

## 评价器与指标解释

本次深入检查未发现把这些真实 LOST/HOVER 错报为 FAIL 的证据。输出状态、控制原因、持续跟随结果和冻结逻辑能够互相印证；已记录的 FAIL 应保留。

不过，`valid_depth_gap_straddling_event_s` 只是诊断字段，不能直接当成选中轨迹连续失测时长。冻结评价器取严格 `< close` 的最后一个诊断有效深度时间，以及严格 `> open` 的第一个时间；位于关闭边界的有效帧会被排除，且诊断有效深度不等于 KF 接受的测量。C-RAW-00 报告该字段为 0.900 s，却仍可在 0.75 s 阈值前恢复：其真正最后接受帧在关闭边界 29.600，恢复采集 30.200、处理 30.332。此处“0.9 s 却 PASS”的表面矛盾是指标边界和语义问题，不能据此认定状态保护或验收被绕过。

报告的 `no_automatic_recovery_after_long_loss=true`、UUID 一致和设定值互斥，仅支持对应观测范围内没有记录到违例；它们不补偿长期 HOVER 的可用性损失，也不证明多目标中的物理身份保持。后者需要独立物理身份评价，本稿未审计阶段二数据。

## 冻结源码证据

以下行号以本次读取的 v3 冻结文件为准。其 SHA-256 与 C-POS-03 的[归档源码清单](../results/frozen_fullplan_v3/fullplan_v3_position_compatibility_car_position_adaptive_kf_seed03/configuration/source_sha256.json)一致：

| 冻结文件 | 相关位置与语义 | SHA-256 |
| --- | --- | --- |
| `uav_tracking/core/target_manager.py` | 约 300–322 行：年龄从最后接受测量起算、超限锁止；530–552 行：融合拒绝计数和 coasting；650–679 行：输出预测也执行到期检查 | `165253c04d907e88c86036127e4d0d0046a6ddaf79476c3fe286bdda2c044f6e` |
| `uav_tracking/core/kalman.py` | 341–384 行：计算创新马氏距离，大于阈值则 `update()` 返回 False | `bbfe900fbd1fd7181910f82f72e43b87eff0fd0f2c218044f1d8a056a566d5fb` |
| `ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py` | `_flush` 使用当前时间做预测；`_publish` 保留测量采集时间并记录 prediction age / LOST | `ed506bab64d03eb76ae603b2abe7652f6b51d3bc44c35d2a1a61e6af2eaff239` |
| `ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/controller_node.py` | 约 129–152 行：仅 MEASURED/PREDICTED 有效，年龄包含预测及传输时间 | `edd957014484b3f3f3b7caf72e32f68404d17bbab0f29db80abad7ca3edb890d` |
| `scripts/evaluate_stage1_flight.py` | `evaluate_occlusion` 分别检查状态恢复、长失保护和持续重选；诊断 gap 采用严格边界 | `bfd78659ff3d75f2f2bde343d53bf8a0d3c9529b7f0e630f000c2fd53ecddabf` |
| `scripts/stage1_flight_monitor.py` | 166–170 行：固定相对偏移；约 452–502 行：等待关闭应答后保持 duration+render margin 再开帘 | `9644a952e07f23a4040d1677ecdd60a6df644cf8c17f3e3e5f06befdb455ef8f` |

## 小型 JSON 证据指纹

下面是审计时实际读取文件的 SHA-256；未对仍更新的 position 总汇总声明固定指纹，也未把缺失字段填为零。

| 文件 | SHA-256 |
| --- | --- |
| velocity 完整重复汇总 | `9f0413f4aff67a87e7bd92c408337f7090cac5ac3c13eaf8aba762e61e2479e9` |
| C-RAW-01 / `offline_evaluation.json` | `792425cfa51b66da83efee747d41ec4831b3c26271cdb00323446915665bddb7` |
| P-FIX-04 / `offline_evaluation.json` | `64c38be443de7a29dc9ab338436c9373a8856ec7b38ebbd3f6230787b80e057c` |
| C-POS-03 / `offline_evaluation.json` | `ae530cf68a02af3094bc463e3d51306e7f403f21b628ca29fab5126720e2f10a` |
| C-RAW-00 / `offline_evaluation.json` | `3b452ecdac6921802efaab35405ddee8233eb836d0cfcd22c357ac72e6921417` |
| P-RAW-04 / `offline_evaluation.json` | `f047c781540abdba49624d69873d95e96ae104c29c3519fc81f257190142bcf6` |
| C-POS-02 / `offline_evaluation.json` | `3a8a1d1f05515aca4aa4743d8f5dd6b717d234804d045ead394d69ca401b7e79` |
| `freeze_validation/import_isolation.json` | `3ab96c1fe451e166d2de29816124b765cc24b2eebd1e066df0c9c1766f079c80` |

本稿是供最终报告引用的诊断草稿，未提出或实施对冻结正式试验的修改。后续若研究具体门控原因，需要独立保留拒绝前的原始三维测量、创新与协方差、对应 TF/深度锚点及真实几何证据；在此之前，结论应停留在“连续融合拒绝导致有效测量冻结并失去跟随”。
