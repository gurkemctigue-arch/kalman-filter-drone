# Humble32 行人速度核心试验：计划外时效丢失诊断

日期：2026-10-30。范围：原始 `person_stage1_velocity_seed004` 的只读诊断。没有修改生产代码、冻结的 Humble32、原试验结果或任何安全门；没有启动 WSL、额外仿真、profiler 或读取 rosbag。

## 当前结论与边界

已确认直接触发链：选定轨迹 2 的最后有效测量来自源时间 **85.2 s**，下一次有效候选来自 **85.6 s**，但到 **85.972 s** 才完成检测管线。系统在此之前越过 **0.75 s** 的测量保鲜门限，进入 LOST / 悬停，并要求重新选框。后续候选建立轨迹 3，没有替换任务轨迹 2。这个安全响应与现行身份保持策略一致。

**尚未确定哪一个计算、锁等待、消息发布或系统调度环节造成检测服务时间突增。** 现有 `inference_wall_s` 不是纯 YOLO 时间，也不是包含尾部所有工作的完整 worker 时间，不能把这次事件归因为“YOLO 本体变慢”或“诊断历史增长”。需要先做分段计时。

原 `summary.json` 的 `basic_flight_passed=true`、`monitor_success=true`、`termination_reason=follow_duration_reached` 只说明基础飞行与持续时间完成，不等于完整工程或论文验收通过。原试验与后续独立评价必须保留。

随后 root 已确认该槽原始终态为 FAIL、`infrastructure_stop=false`、`negative_evaluators=['surface_flight']`，source / native 评价 PASS，navigation 原删失结果保留。root 实际目视原 `frame_00401.jpg`（约 80.1 s，FOLLOW、黄色选中轨迹 2）与 `frame_00451.jpg`（约 90.1 s，HOLD、仍有绿色检测框、任务保留旧 UUID）；这支持上述安全锁止链，但画面叠加框不是独立物理身份真值，本轮未据此替代身份评价。

## 原始证据与来源绑定

试验目录 `R`：

`results/frozen_fullplan_v4_humble32/reliability_v4_humble32_probe01_person_stage1_velocity_seed004`

下列 SHA-256 在 Windows 对原文件流式计算；计算前后文件大小和 mtime 均一致。遥测定位使用按字节 seek 后的小段逐行 JSON 读取，没有解包或读取 bag。下表 SHA 绑定完整原文件，而非人工摘录。

| 相对 R 的文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `telemetry.jsonl` | 66535665 | `2d5b55e2652932f809ac1ae3967a4ddbd4b554156a57362a9638e0506231b8d9` |
| `summary.json` | 4876 | `15f025e307381ef1930a0f7610350d559f6eed56f370e5a3bf872aafe825348f` |
| `run_config.json` | 1960 | `88f02ea63c3fb6c9ae1549325390e630bdf4c3c933b2f7898c483a95bbf5a5f8` |
| `configuration/runtime_parameters.yaml` | 3926 | `f660bb5672e05d12cdcb452a891784272e66be38615e10b5e958da8120a03dae` |

原运行配置：行人、stage 1、速度控制、`auto_unique`、`legacy` 关联、`adaptive_kf`、推理输入 320、线程 2、最大推理频率 10 Hz、75 s 跟随、目标实时因子 0.25、seed 4。相机消息分辨率为 640×480，不能把该分辨率误记为推理输入尺寸。

原参数：`max_prediction_duration_s=0.75`、`max_observation_age_s=0.6`、`track_retention_duration_s=3.0`。计划内短遮挡为 32.96–33.24 s，长遮挡为 45.96–49.04 s；summary 记录长遮挡后的显式重选已确认，任务 UUID 为 `90328b07-4410-4db3-b5bb-67b4ce0a44cc`。本次 85.0–86.5 s 窗口没有快门事件。

原 summary：跟随从 20.952 s 开始，95.940 s 结束；整次 `median_inference_wall_s=0.1169184379998569`，检测源时间延迟 P95 为 `0.2688000000000071 s`。末帧 95.5 s 的 1.578441665 wall s 是后续极端样本，不能用它解释首次计划外丢失。

随后第二个 `person_stage1_position_seed004` 槽的 summary 显示，同为 75 s 注册持续时间，其 job 中位数为 `0.02584839600012856 wall s`、源时间检测延迟 P95 为 `0.06800000000000139 s`，且完成 `follow_duration_reached`。该 summary 路径为 `results/frozen_fullplan_v4_humble32/reliability_v4_humble32_probe01_person_stage1_position_seed004/summary.json`，4896 字节，SHA-256 `3a7219736967b36a62c31f96799aa1d98d37ebef0117e2d02c8ea1f1a2ae563d`；root 同时确认该槽独立工程终态 PASS。这反对“所有 75 秒试验都会随时长必然退化”的推断，但两个槽的控制模式不同，不能当作隔离变量的因果试验。后续诊断应保留相同条件并比较每个槽实际时序分布。

## 实际时间链

表中采集、完成和事件记录时间均为 **ROS 源仿真秒**；job 一列为 `perf_counter` 测得的 **wall 秒**。记录时间 `time_s` 是监视器收到并写入事件时的当前源时间，不等于图像采集或检测完成时间。显示值四舍五入，原始精度保留在上述文件中。

| 事件 | 图像源时间 | 检测 completed_s | 事件记录 time_s | inference_wall_s | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| 正常检测 | 85.0 | 85.064 | 85.064 | 0.104467 | 一个有效深度行人框 |
| 检测服务时间增大 | 85.1 | 85.344 | 85.368 | 0.879908 | 一个有效框；之后仍关联轨迹 2 |
| 最后接受的旧目标测量 | 85.2 | 85.684 | 85.696 | 1.381739 | 一个有效框；surface 与 navigation 均接受 |
| 轨迹 2 状态记录 | 85.2 | — | 85.736 | — | `associations=[[2,0]]`，状态 tracking |
| 控制保鲜门触发 | — | — | 85.956 | — | `stale_target`，测量年龄约 0.752 s |
| 轨迹 2 首次计划外 LOST | 85.2 | — | 85.968 | — | 输出 stamp 85.960，年龄约 0.760 s |
| 下一次检测完成 | 85.6 | 85.972 | 85.980 | 1.156163 | 一个有效框；源采集间隔 0.4 s |
| 候选建立新轨迹 | 85.6 | — | 85.992 | — | 轨迹 3 初始化；选定轨迹仍为 2，任务仍 LOST |
| 飞行监督器进入 HOLD | — | — | 86.008 | — | phase 内记录源时间 86.000；零速度悬停 |

85.2 s 测量的 surface 马氏距离平方为 `0.0011870306246847553`，门限为 `9.21`，`rejected_measurements=0`。navigation 对 85.2 s 的 `measurement_processing_s=85.688`、`fusion_accepted=true`、`fusion_reason=accepted`。该次导航接受事件在 85.732 s 被监视器记录。

关键门计算：

```text
旧测量源时间                  85.200
允许预测时长                  +0.750
理论保鲜边界                  85.950
下一检测完成时间              85.972
相对理论边界已晚              0.022 s（源时间）

下一候选源采集间隔             85.600 - 85.200 = 0.400 s
下一候选自身完成延迟           85.972 - 85.600 = 0.372 s
旧测量到下一完成的总年龄       0.400 + 0.372 = 0.772 s > 0.750 s
```

下一帧在估计器处理时约为 85.976 s，其自身年龄约 `0.376 s < 0.6 s`，所以不是新观测自身过期。此前旧任务已经因真实 elapsed age 超界锁存重新选择要求。轨迹 3 的出现不是自动切换目标的证据；选定 ID 与 UUID 保持轨迹 2，navigation 随后记录 `no_accepted_selected_measurement / invalid_navigation_reference`。

worker 等待时间：85.1 / 85.2 / 85.6 三帧分别约为 `0.000952 / 0.001331 / 0.005648 wall s`。已知突增主要发生在现有 job 计时区间内；这仍不能区分 YOLO、深度几何、后续锁等待和 observation 发布。

## 源码路径与可排除项

以下行号对应本次审查时的主树源文件；本诊断不改这些文件。

| 位置 | 已确认行为及意义 |
| --- | --- |
| `ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py:359` `_infer_snapshot`；计时起点 369、字段取值 531 | 起点在 RGB/depth 解码前；包括 `predict`、ROI / navigation 深度采样、后续输入锁等待、frame / individual observation 的构造与发布。`completed_s` 在最终锁内、发布之前读取。`inference_wall_s` 在 diagnostics 字典构造中取值，**不包括**其后的 `json.dumps` 和 diagnostics publish；worker 仍忙到这些工作结束。 |
| 同文件 300 `_process_latest`；`inference_worker.py:30` `submit` | 单 worker、单 future，busy 时丢弃新提交，由调用方保留最新 RGB；没有累积图像 FIFO。采集跳帧可能扩大观测间隔，是当前非排队策略的预期效果。 |
| `state_estimator_node.py:622` `_expire_elapsed_target`；`target_manager.py:362` `_expire_by_time` | 按旧目标最后测量的源时间执行 0.75 s 保鲜门，超界锁存 `_requires_reselection`。不能用新到达帧的接收时间刷新旧测量年龄。 |
| `target_manager.py:509` `_associate` | 重新选框要求生效时，排除旧 selected track；因此新候选可建轨迹 3，不能自动复活或替换任务轨迹 2。 |
| `target_manager.py:798` `predict_with_result`；`stage2_telemetry.py:9` `track_snapshot`；`state_estimator_node.py:637` `_publish` | `_tracks` 只在 reset 中 clear，REMOVED 仍保留；每次输出遍历全部保留轨迹，复制最后测量诊断，甚至对 removed filter 做固定 6D 投影，再序列化全部轨迹。快照层再次 deepcopy 诊断。成本随累计建立的轨迹数增长。 |
| `state_estimator_node.py:325` `_flush`、622、637 | 定时器先调用 `predict_with_result`，之后 `_publish` 又检查 elapsed expiry；目标已过期时可能再执行一次全轨迹预测。丢失后的重复工作是可测优化候选，尚未证明是首因。 |
| `scripts/stage1_flight_monitor.py:332` `on_tracks`、221 `event` | 轨迹诊断 JSON 进入监视器后再次 loads / dumps / 文件写入；视频回调也遍历保留轨迹。会增加 CPU 与 I/O，但不直接证明 detector 的某段耗时。 |
| `kalman.py:110` `last_update_diagnostics`、119 `_record_update` | 每轨迹只有最后一次诊断，记录被整体替换，没有递归追加所有测量历史。协方差矩阵维度固定；数值增大不等于矩阵计算复杂度增长。 |
| `detector_node.py:252` `_on_depth`；`state_estimator_node.py:180` `_point_pose_uncertainty` | 深度 deque 上限 15，接收时刻字典按其清理；pose deque 上限 400，最近样本搜索上界为 400。未发现随全任务长度无限增长的这些缓存。 |
| `state_estimator_node.py:289` `_transform`；构造处 133 | 使用标准 `Buffer()` 与每观测有限 timeout lookup，没有项目自建的无限 TF 历史。没有在本轮启动 ROS 或读取已安装 tf2 源码，不能把其实际耗时或缓存实现视为已测。 |
| `navigation.py:120` `sample_depth_points`、181 `fit_ground_plane`；`detector_node.py:46` overlap | 地面样本上限 1200、每目标支持点上限 500，RANSAC 默认 80 次；同帧 overlap 按候选两两枚举，单 pair 上限 4096 像素。复杂度与当前帧候选数、样本数有关，不读取全任务历史。 |

实际小样本对照：一轨迹时 tracks JSON 约 4.5 KB，二轨迹约 8.5 KB，三轨迹约 12.5 KB；每个 retained 诊断约 3.4 KB、23 个字段，末尾没有增长成完整历史。第一条 removed 轨迹自 45.9 s 保留，但 74.9 s 与 84.5 s 附近的检测小样本中位数仍约 `0.074 / 0.072 wall s`。轨迹 3 是 85.95 s 失效之后才产生，不能倒过来把第三条轨迹的开销作为这次首次超界的已确定原因。

另一个待测点是 detector 的输入锁：最终锁覆盖 frame、individual observation 发布与 diagnostics 序列化、发布；可靠 DDS 发布或锁竞争若阻塞，可拖慢 worker 和主执行器的传感器回调。现有数据没有单独计时，不能认定发生过该阻塞。估计器与 detector 是不同节点进程，其 JSON 成本对 detector 的影响也可能通过 CPU / DDS / 录制背压间接发生。

## 下一步最小独立诊断方案

先在独立诊断版本与新目录增加计时，不改旧 Humble32 或原终态。保留全部保鲜、关联、安全、超时和 identity 门，以及单 worker 非排队策略；不靠增大门限或减弱检查获得通过。诊断仅使用开发 seed，不能代替正式重复实验或重写本次结果。

1. 每 job 记录采集戳、提交戳和 `[clock_epoch, acquisition_ns]` job key。保留现有字段；worker 的 finally 对成功、提前返回、异常各输出恰好一条小结构化 `INFERENCE_JOB_TIMING` 日志，由原 `ros.log` 保留。最终 clock 定义为 `production_work_before_timing_log_wall_s`，覆盖最后 diagnostics encode / publish，但排除新增 timing 日志自身写出，避免自测循环。现有 detection 消息只带发布前已知的 partial 分段；不新建 topic、pending 队列或上一 job 批量搬运。记录同一 worker 的 `thread_time` CPU 时间与 wall 时间，区分计算和等待；多线程 PyTorch 的总计算不能只凭 worker thread CPU 归因。
2. 对现有工作做连续互斥的分段计时：RGB/depth decode、`model.predict`、box / ROI / navigation depth geometry、最终 input lock 等待、持锁内 frame 构造、frame publish、individual observation publish、diagnostics encode、diagnostics publish。各段总和与 whole job 对账，剩余项明确记为 residual，不把旧 `inference_wall_s` 重命名成 pure inference。
3. 为 `_process_latest` timer 记录 timer 到达 / callback 进入的源时间与 wall 时间、input lock 等待 / 持有时间、busy drop 次数；RGB/depth 回调各记录 lock wait 的聚合计数和最大值。不要每个深度消息追加大 JSON，以免诊断本身改变负载。
4. **未来可选；本次未实现：**估计器增加轻量分段：TF lookup、姿态协方差最近搜索、association / KF、ground geometry、timer predict、snapshot deepcopy / JSON encode、各 publisher wall 时间；同步记录 active / lost / removed 数、消息字节数、诊断队列可见的延迟。单独记录一次 callback 内 `predict_with_result` 的调用次数，检验过期后的重复预测成本。只有 detector 分段结果支持继续定位时再决定，不能把此项写成已执行。
5. 输出每段数量、中位数、P95、最大值，以及每次旧测量年龄接近 / 跨越原 0.75 s 门的前后短窗口。按同一 job sequence 对齐源时间和 wall 时间；对 `acquisition_gap + completion_age` 与保鲜边界逐项复算。记录 drop / exception / unmatched / rejected 事件，不能只记录成功帧。
6. 先做一个独立的同条件开发诊断试验，串行、保留全部原始结果并验证计时附加成本。只有确定慢段后才提出相应修复：例如裁剪或一次性归档 removed 轨迹诊断、避免重复预测、缩小锁内发布区、处理 DDS 背压或优化模型 / 深度几何；任何身份、安全或消息行为改变仍需单独验证。该诊断试验尚未启动。

## 本次主树实施状态

已在主树 `detector_node.py` 与新增 `inference_timing.py` 实现最小分段记录：decode、YOLO predict、depth / navigation geometry、三处 input lock 等待及持有、frame 构造及发布、individual observation 发布、diagnostics encode / publish。每个被 worker 接受的 job 在 finally 尝试写一条 `INFERENCE_JOB_TIMING` 结构化 INFO 日志，涵盖成功、提前返回和异常；key 为 `[clock_epoch, acquisition_ns]`。日志写出故障不能替换原始算法或发布异常。正常诊断消息带 `timing_before_diagnostics`，标明其为 partial；原 `inference_wall_s` 仍在原来的计时区间取值。`stage1_flight_monitor.py` 现有 JSON 透传已保存该附加字段，不需要改变监视器。

最终日志的 `production_work_before_timing_log_wall_s` 等于连续互斥 stages 的 wall 时间之和；`input_lock_holds` 是持锁期间的 inclusive 元数据，不能再次加进总和。thread CPU 只代表当前 worker thread。最后一次 clock 排除新增计时日志自身的 encode / INFO 写出，该额外开销尚未实测，不能宣称可忽略。

timer 只在接受的 snapshot 上携带该次输入锁等待和取快照前已发生的持锁时间；后者明确命名 `timer_input_lock_snapshot_hold_wall_s`，不声称包含之后的 worker submit / release。未新增所有 timer / RGB / depth 回调的聚合采集系统。未实现上述第 4 项估计器分段、removed 轨迹剪枝或 TF 行为修改。没有新增线程、topic 或队列；算法和原发布频率未调整。冻结 Humble32 仍使用其原源码，运行中的原试验没有加载这些新代码。

Windows 轻量行为验证：现有 detector / worker 23 项与新增 timing 6 项联合 **29 PASS，0.287 s**。新测试通过可控阶段时长验证完整总和、锁等待与持有不重复计数、发布次数、旧 `inference_wall_s` 与新尾段的边界、异常对象保持、提前返回单记录及锁释放。该结果只验证代码行为，不证明实时根因或仿真运行性能。空闲的 `humble32_clean_review` 已完成独立 diff 审查：**无阻断，独立运行同 29 项 PASS，0.239 s**；确认无新线程 / queue / topic、原保护和发布顺序保留、最终总和边界及异常传播。实际独立诊断运行与日志附加成本测量仍待后续安排。

独审时 Windows 原始文件 SHA-256：`detector_node.py`（当时CRLF）为 `4cf6888fd78ded87edc34b5dd17df88e3df40ac608415f72956005f3d30e1534`，`inference_timing.py` 为 `9439cf0985b0244eccc437f26fdb1691e7a48d3518c1b7faa2b8372d18742d72`，新增 `test_inference_timing.py` 为 `87911e04a8bd8c8b0545926073ac29ae551864925fa9e7e2beef5569718e745d`。提交前按仓库 `.gitattributes` 统一LF，`detector_node.py` 的提交字节 SHA-256 为 `d4d0581bcbafafcab28a1c9784a754e590182e302c193579347e54795120c4ad`，其余上述两件SHA不变；仅换行规范化，无语义更改。下一冻结来源与外部最终source review必须使用实际提交及LF字节，不能把旧Windows CRLF审查SHA当成新冻结文件SHA；此时尚未生成33最终source review。本文前面的静态定位行号描述的是增加计时代码前的同源实现，加入计时后行号会移动，函数名保持不变。

结论状态：**直接时效失效链已记录；性能根因待分段证据；原试验完整验收以独立原始评价为准。**
