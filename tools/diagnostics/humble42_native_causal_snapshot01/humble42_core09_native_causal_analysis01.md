# 42 / core09：未支持的新轨迹与持续歧义

本次只读分析使用已经完成的原生导出 `humble42_native_causal_window01`，未重读原始 bag、旧 telemetry 或图像像素，未启动 WSL、推理或仿真，也未修改源码或原始记录。完整的关键标量、原始 record_index 与 source/clock 分域保存在同目录外的 `humble42_core09_native_causal_compact01.json`。导出 manifest 为 COMPLETE，记录 204788 条、一次 native 遍历、两次压缩摘要，originals unchanged=true、独占缓存已删除且 tempfile 设置已恢复；这不改变原 slot FAIL、8/1/3 统计和 owner/Gazebo 错误。

已经观测到的因果链：

| 原始 record_index | 原 acquisition / output 秒 | 已记录 /clock 代理秒 | 证据 |
| --- | --- | --- | --- |
| 65142 / 65181 | 30.6 / 30.6 | 30.736 / 30.752 | 候选 c0 远处形状框深度 13.052；track2 接受，全部轨迹为 1、2、3。 |
| 65356 / 65362 | 30.7 / 30.7 | 30.832 | 唯一 c0 框约 [256.82,89.58,405.67,139.47]，深度 9.724、overlap_count=0、recovery_enabled=true、supported=false；新增 track4，diagnostics 为当前帧 INITIALIZED/accepted=true，世界位置 [17.357,-0.102,1.023]。 |
| 65586 / 65625 | 30.8 / 30.8 | 30.936 / 30.952 | 近似连续远处形状框 c1 深度恢复到 13.026 并关联 track2；track4 只预测。 |
| 66499 / 66708 | 31.2、31.3 | 31.348、31.440 | track4 又分别接受 c1/c0，均是当前帧 supported=false；最后接受停在 31.3。31.3 发布速度约 [-2.026,0.517,0.232] m/s。 |
| 66917 / 66923 | 31.4 / 31.4 | 31.536 | track3 接受 c0；另 c1 的新增被 overlap_birth_surface_support_unknown 延迟。 |
| 67138 / 67145 | 31.5 / 31.5 | 31.636 | track3 对 c0、c2 歧义：ambiguous_track_ids=[3]，detection_indices=[0,2]；track2 接受 c1。 |
| 67371 / 67378 | 31.6 / 31.6 | 31.740 | track3 接受 c1，last_measurement=31.6，当前 d²=0.8789 < 9.21；该候选 supported=false，说明“所有 unsupported 均不能更新既有轨迹”会误伤本次已接受更新。 |
| 67583 / 67589 | 31.7 / 31.7 | 31.836 | 歧义改为两个轨迹竞争一个候选：tracks=[3,4]，detection=[1]；track2 仍接受 c0。 |
| 68693 / 68699 | 32.2 / 32.2 | 32.336 | tracks=[3,4] 继续竞争近处 c0；track3 last_measurement 仍是 31.6，track4 仍是 31.3。 |
| 68753 / 68756 | output=32.36；track snapshot acquisition=32.2 | 32.360 | surface 与 track3 转 LOST，prediction_age=0.76；定时快照明确 projected=true。 |

31.4–32.2 没有新增轨迹，始终是 IDs [1,2,3,4]，merge_uncertainty_detection_indices 始终为空。track4 在 32.0 已为 lost，但仍在歧义集合中。上述两个歧义类型是原始发布结果，不是根据图像猜出来的。31.5 两个近处候选的小框完全落在大框内，IoU=0.6559、深度差 0.0101 m，支持重复/混合检测的研究假设，不能证明它们对应同一物理个体。

surface 和 navigation 必须分开。navigation 的最后接受源测量停在 31.2；31.4 的 record 66922 和 31.6 的 record 67377 均为 exclusive_pair_not_uniquely_accepted，31.5、31.7 后则有 no_accepted_selected_measurement。surface 的 31.6 更新确实成功，之后因关联歧义没有新更新，32.36 的 LOST 与其 0.75 秒到期规则一致。后续 track3 缓存 diagnostics 中的 ACCEPTED/31.6 且 current_frame=false，不是新的尝试或接受，更不能据其旧 d² 判断当前 pair gate。

未观测到的内容仍是未知：track4 的物理身份、31.5 两框的物理同一性、关联前私有预测状态、所有拒绝 pair 的分数与门控矩阵，以及“阻止 track4 后一定能闭环成功”的反事实。当前原始发布快照只支持“未获 surface 支持的新轨迹进入确认态，之后成为歧义竞争者”，不能把它写成物理伪目标已经证实。

建议的最小 birth 修复仅作用于**自动新增的 unmatched detection**：在原关联和歧义判断完成以后、调用新轨迹初始化以前，如果 recovery_enabled 明确为 true 而 surface_measurement_supported 不是 true，则 defer，不创建或 promote 已确认的三维轨迹。这个判断覆盖当帧没有 overlap anchor 的情形，正好覆盖 record 65356/65362；记录独立、明确的 birth defer reason。原始候选仍必须留在这一帧的关联输入、歧义判断和日志中，不能在入口删除它。

边界应分别处理：

- recovery 未启用的普通模式保留原 birth 规则；不要把缺失字段擅自解释成支持证据。
- enabled 且 supported=true 的后续新采集可重新进入原 birth/confirmation 流程。沿用原来的 overlap、重复采集与时钟 epoch 约束；缓存、预测定时消息及先前 unsupported 帧不能冒充 supported confirmation。
- 已存在轨迹继续使用原关联与更新门控，避免 blanket 拒绝 31.6 这类 supported=false 但已合法关联的更新。
- 用户明确选框可以确定任务身份；选框本身不能把未知深度变成受支持的三维测量。如果尚无轨迹，可保留框选/UUID 的待初始化状态，等同一个选框目标获得合格源测量后初始化。不要用邻近对象代替，也不要默默把该流程当普通自动 birth；具体选择接口需由 root 核对后定案。

这个位置的 guard 可以保留当帧真实的“一轨迹多候选”和既有“多轨迹一候选”判定，不会自动换目标或选择最近对象。它不能保证所有物理多解都已表述：一个真实新目标若一直只有 unsupported 观测，将被延迟或无法初始化；必须如实统计这个代价。随后获得 supported 的新入口应仍可确认。31.5 的当前帧多框歧义也不会仅靠 birth guard 自动消失，应该继续停控保护。

最小验证应覆盖：无 overlap 的 enabled/unsupported birth 被 defer；overlap 情形继续保护；之后 fresh supported 新入口可确认；unsupported/cached 帧不能累计 confirmation；未启用的普通模式行为保持；既有轨迹的 31.6 更新仍可接受；明确选框保持 UUID 并等待有效三维测量；一轨迹两候选及两个既有轨迹竞争同一候选仍进入歧义而非自动挑选。通过后再做独立的新 probe，观察是否阻止类似 track4 的未经支持初始化、是否改善指定个体保持，并保留失败试验。

若需要证明某个候选为何同时通过 tracks3/4 的关联条件，应在新 probe 记录关联前 predictor、每个 pair 的实际 gate/score 和拒绝原因；不能从本次发布后快照补造。这些诊断有助于评价 birth 修复，但当前有限 guard 的设计证据已经足够。此处只给设计，不修改代码或重新运行实验。
