# v4 云台、身份与时序审计

日期：2026-10-29。范围：只读冻结 v3 源码及现有轻量 JSON/JSONL；未解压 rosbag、未启动仿真、未修改冻结结果。以下结论区分可证实事实与仍需实验检验的原因。

## 已确认结论

1. 汽车 active 的工程验收为 1/10，midpoint 为 6/10；active seed001 为 INTERRUPTED。执行终态、云台机构验收和闭环任务验收不能互相替代。
2. 没有发现能解释上述差异的已证实云台几何错误。已有 9 份汽车 active 云台报告均通过云台检查。active000 的图像时刻动态 TF coverage 为 1.0，独立物理相机 link 与编码器几何最大角度误差为 0.002746 rad、最大位置误差为 9.63e-7 m，低于原门槛 0.03 rad、0.005 m。三轴实际运动、命令/编码器物理滞后和时间戳检查均通过。
3. active000 的短遮挡失败有明确时序证据：第一幅恢复观测到达时已经超过原 0.75 s 安全期限，触发必须重选的 LOST。不能通过放宽安全期限或允许 LOST 自动复活修复。
4. 高度参考点存在明确语义差异：运行时估计的是 RGB-D 可见表面锚点，物理评价使用模型原点。两者的误差必须分别报告，不能拟合偏移后宣称物理高度准确。
5. 多目标身份 unknown 主要来自同类 GT 投影重叠和没有 fresh 的选中检测。初始框映射并非当前主要缺证据点；20 个 crossing 槽的 initial mapping 全部为 CONFIRMED。unknown 不能计为 correct。

## 短遮挡失效的实证链

来源：`results/frozen_fullplan_v3/fullplan_v3_stage23_s3_car_gimbal_active_seed000/telemetry.jsonl`、`flight_evaluation.json`。

| 事件 | 仿真时间 / s | 说明 |
| --- | ---: | --- |
| 遮挡前最后有效图像采集 | 29.600 | confidence 0.939，depth 9.144 m，valid ratio 1 |
| 该图像推理/观测完成 | 29.804 | 采集至完成 0.204 s |
| shutter close request | 29.700 | 请求时刻，不是渲染遮挡开始真值 |
| close ACK 被 monitor 观测 | 29.800 | 轮询采样时刻，不是服务精确完成时刻 |
| 配置的最早 open request | 30.050 | 29.8 + duration 0.2 + render margin 0.05 |
| 实际 open request | 30.100 | 0.10 s tick 带来可确认的 0.05 s 量化等待 |
| open ACK 被 monitor 观测 | 30.200 | 仍不是精确渲染可见时刻 |
| 第一幅恢复有效图像采集 | 30.200 | confidence 0.935，depth 9.156 m，valid ratio 1 |
| 原预测期限 | 30.350 | 29.6 + 0.75 |
| 最后仍为 PREDICTED 的输出 | 30.340 | age 0.74 s |
| 首次 LOST 输出 | 30.360 | age 0.76 s |
| 恢复图像推理完成 | 30.404 | 相对最后有效采集已 0.804 s |
| 该帧处理后的状态 | 30.408 | 仍为 LOST，需要显式重选 |

恢复的源图像间隔是 0.6 s，但可用观测实际到达间隔已经越过安全期限。不能只看源图像间隔就判断短遮挡应当恢复。该例的安全期限差额为 54 ms；这只说明边界敏感，不证明移除恰好 54 ms 就必然解决所有种子。

冻结提交 `01e3477` 的 `scripts/stage1_flight_monitor.py`：199 行使用 `create_timer(0.10, self.tick)`；360–382 行仅在轮询时采集服务 ACK；474–475 行从观测到的 close ACK 开始加 dwell 与 rendering allowance；480–486 行在下一 tick 才判断并请求开门。配置 0.2 s 的 dwell 在该例成为 close ACK 至 open request 0.3 s、close/open request 间隔 0.4 s。**这些都不是独立测量的真实遮挡时长。**

`uav_tracking/core/target_manager.py` 中 `_expire_by_time` 在超过 `max_coast_duration_s` 后设置 LOST 及 `_requires_reselection`；`_associate` 排除需重选的已选轨迹。此安全锁存是明确设计要求。正确修复方向为减少调度额外等待、图像采样与推理/传输延迟，保留该锁存。

active000 在 long 遮挡开始前已因 short 失败悬停，所以 long 的 `prediction_observed=false` 不能单独证明长遮挡/云台故障。该槽显式重选后持续跟踪检查为 PASS，约 11.224 s 持续窗口；这不能抹去先前 short FAIL。

## 视觉改善、覆盖率与控制误差

以下保留失败，不剔除 LOST/HOVER。center 和 horizon 是现有云台报告的 RMSE；distance/height 是整段物理模型原点评价。LOST 时长四舍五入，供定位使用，精确值以 JSON 为准。

| 汽车槽 | center | horizon / rad | distance / m | height / m | active fraction | LOST / s | short 无丢失 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| active000 | .110 | .0123 | 5.88 | .82 | .55 | 19.45 | false |
| active001 | — | — | — | — | — | — | INTERRUPTED |
| active002 | .112 | .0105 | 5.92 | .77 | .55 | 19.50 | false |
| active003 | .118 | .0742 | 6.48 | .75 | .35 | 28.38 | false |
| active004 | .106 | .0151 | 5.12 | .80 | .55 | 19.41 | false |
| active005 | .109 | .0096 | 5.60 | .79 | .55 | 19.43 | false |
| active006 | .110 | .0102 | 5.75 | .79 | .55 | 19.41 | false |
| active007 | .102 | .0129 | 5.36 | .81 | .55 | 19.43 | false |
| active008 | .029 | .0090 | 2.20 | .74 | .85 | 6.39 | true |
| active009 | .129 | .0150 | 6.96 | .80 | .33 | 29.00 | false |
| midpoint000 | .123 | .0257 | 2.24 | .76 | .86 | 6.24 | true |
| midpoint001 | .120 | .0199 | 2.20 | .75 | .85 | 6.38 | true |
| midpoint002 | .269 | .0308 | 12.46 | .73 | .11 | 38.57 | false |
| midpoint003 | .121 | .0207 | 2.20 | .75 | .85 | 6.38 | true |
| midpoint004 | .196 | .0281 | 7.02 | .79 | .32 | 29.39 | false |
| midpoint005 | .123 | .0264 | 2.23 | .74 | .85 | 6.40 | true |
| midpoint006 | .281 | .0260 | 12.05 | .75 | .11 | 38.52 | false |
| midpoint007 | .122 | .0225 | 2.22 | .75 | .85 | 6.45 | true |
| midpoint008 | .184 | .0295 | 5.25 | .80 | .55 | 19.44 | false |
| midpoint009 | .122 | .0185 | 2.25 | .75 | .85 | 6.36 | true |

`scripts/evaluate_stage3_gimbal.py:286` 起的机构/信号检查及 346 行起的 active/midpoint 视觉比较，不要求整个飞行的短遮挡检查通过。中心误差条件于已经有检测的帧，缺测及任务丢失不能由此消除。无人机 LOST 后悬停而目标继续运动，使整段距离误差增长；因此 active000 的 5.88 m 不能单独归因于距离控制增益。即便 active-only 子集仍会包含重选后的追赶瞬态，不能直接当稳态偏差。

active000 的内部 FOLLOW/PREDICT 高度误差 RMSE 为 0.05855 m，而整段模型原点高度误差 RMSE 为 0.82290 m；两者参考点与样本集合均不同。`online_state_accuracy_v2.json` 的 frozen visible-surface anchor 状态评价也不是物体原点精度。需要新增有明确不确定性的导航物理参考点，独立维护其测量新鲜度，继续保留原可见表面评价。

## 云台代码审计

- 实际 ROS 路径为 `ros2_ws/src/uav_tracking_bringup/uav_tracking_bringup/gimbal_adapter_node.py`，调用 `uav_tracking/control/gimbal_geometry.py`。独立 `gimbal_controller.py` 不是此 ROS 节点实际使用的控制器，不能用两者坐标注释差异直接判定运行故障。
- `Rz(yaw) Ry(0.35 + pitch_delta) Rx(roll)` 的模型链与编码器 TF、SDF 和独立 link pose 记录一致。节点从世界目标相对位置算 LOS，roll 调平，机体 yaw 缓慢回正；没有发现同时用同一图像中心误差直接驱动云台和飞行器的证据。
- 冻结 v3 存在明确配置接线缺陷：`ros2_ws/src/uav_tracking_bringup/launch/stage3_flight.launch.py:38` 没有给 gimbal Node 的 parameters 传 `params` 文件，尽管 car/person YAML 包含 `uav_tracking_gimbal` 配置。当前已列值与节点默认一致，所以此缺陷不能解释已发生的 active/midpoint 差异。v4 开发源码已补传 `params`，保留命令行 `gimbal_mode` 最后覆盖的顺序；冻结 v3 不变，实际 ROS 参数覆盖仍需随 v4 启动检查。
- 本审计未修改云台算法，未根据无证据假设调增益。

## 物理身份 unknown 的含义与来源

`uav_tracking/stage2_identity.py:14` 的保守物理匹配协议要求：fresh 选中检测、无外部 shutter 不确定性、唯一 IoU >= 0.5 的候选、完整位于画面内，且该候选 GT 框与任何其他同类 GT 框无正重叠。框由 mesh 投影得到，属于 amodal box，正重叠不代表每个像素都不可见，但不足以独立证明可见的实例身份。

10 次 crossing 的选定任务机会计数：

| 类别 | unique unoccluded image match | 同类 GT 投影重叠 | 无 fresh 选中检测 | observed wrong |
| --- | ---: | ---: | ---: | ---: |
| person | 1330 | 849 | 0 | 0 |
| car | 572 | 785 | 412 | 0 |

计数来源为各槽 `physical_identity.json` 中选定任务逐帧结果；前期未选目标时不属于选定任务分母。20 个任务初始化均已独立 CONFIRMED。例 car crossing seed000：总检测机会 220，选定任务机会 139，其中 correct 36、unknown 103、wrong 0。请求框在图像 source 17.2 s 独立映射 car0，IoU 约 .9826；与 tracker 所选框 IoU 约 .9879。其余 unknown 不能解释为初始化没有时间戳，也不能据此声称全程身份正确。

`scripts/evaluate_physical_identity.py` 为 shutter 窗口加 +/-1 s guard；其 MOT unoccluded geometry 子集要求全部 3 个目标完整在画面内且 GT pair IoU <= .01，选定个体物理确认则排除任何正 IoU。这两个子集协议不同，应显式标注，不能为提高 coverage 放松选定身份确认条件。预期物理个体从用户/脚本的 REQUEST 框在原始 image stamp 独立建立，不能从 tracker 当前选中框反推预期身份。

缺失证据的合理恢复路径：保留 unknown 分母及原因分解；如需对重叠帧作物理身份结论，应使用独立实例可见像素/掩码标注或可审计人工逐帧复核。仅用最近 GT 三维位置、UUID 连续、预测轨迹连续或 amodal 框最高 IoU 不能补证。可以新增更可观测的场景做实验，但应独立标注，与原 crossing 失败/unknown 分开报告。运行时不得读取 GT，完整 ReID 仍属后续范围。

## 后续验证约束

1. 优先验证采集到推理完成及状态接受的实际时序预算，记录 close/open 调度超额；保留 0.60 s 观测、0.75 s 预测与 LOST 重选安全约束。
2. 导航参考点和可见表面独立估计，拒绝/缺失导航测量不能刷新导航年龄，ambiguity/LOST 禁止输出可用于控制的有效导航状态。
3. active/midpoint 使用相同种子和相同冻结参数做配对比较，保留全部失败、INTERRUPTED 及覆盖率；视觉子集、active 子集、全段物理误差分别报告。
4. 当前证据只定位上述具体链条，不证明已解释每一槽、每个早期丢失或每项高度误差。需要新 v4 探针检验改动，不能回写 v3 结果。
