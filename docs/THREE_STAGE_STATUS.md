# 三阶段实现与实际验收状态

**当前开发目标为 v4（Ubuntu 22.04 / ROS 2 Humble），三阶段代码均已实现，最终验收尚未完成。** Humble25已通过四包构建、模块/ament与FastCDR来源核验、消息序列化及1390项检查（1385通过、5项精确平台跳过）。两类clean20均完成；核心12格全部尝试，9 PASS、3 FAIL，运行与清理正常。六个行人格均PASS；汽车起飞交接、交叉跟踪和多目标主动云台FAIL。每槽终态与新增候选修复见[当前交接记录](../planning/reliability-v4-current-state.md)及[汽车检测失效诊断](../planning/reliability-v4-car-fragment-diagnosis-20261030.md)。不以测试计数或单项云台检查代替整次飞行验收；正式仍为0/280。

后续按[可靠性修复与交付方案](../planning/reliability-v4-next-actions-20261030.md)推进同源核心、安全及扩展验证，再完成定标、容量准入、正式重复和统计交付。本机[进度入口](../results/project_progress/current/index.html)显示受监任务的最新状态。**下文全部计数和“已结束”描述属于历史 v3 / Jazzy 归档**，不代表 v4 / Humble 已通过；历史材料保留供复核。

本页是工程与研究交付状态快照。`fullplan_v3` 的 166 个主飞行槽均已终态：107 PASS、58 FAIL、1 INTERRUPTED；主离线台账也覆盖 166 个槽，其中 160 RECORDED、4 INCOMPLETE_EVIDENCE、2 NOT_APPLICABLE_NO_SELECTED_TASK。另列 16 项工程扩展为 2 PASS、14 FAIL（其中两项明确为基础设施停止），补充后处理为 15 RECORDED、1 INCOMPLETE_EVIDENCE。失败、未知和不适用项均保留，不能把这些计数当作算法成功率。结果工件不随公开源码提交；本页在本地归档存在时可与 `results/frozen_fullplan_v3/` 中的清单、图表、验收页和报告互相核对。

阶段一的四次 `stage1_final_v2` 工程 PASS 仍然有效，但它们属于历史修订版和四个条件的单次闭环演示；冻结 v3 使用不同源码修订并完成 100 次重复试验。v3 的 34 个阶段一 FAIL 中，现有分型为 33 次可评分行为失败和 1 次录制/评价基础设施失败；正式离线台账、统计补表及全主研究失败分类已完成。执行槽位终态、单次演示通过和系统可靠性结论必须分别报告。

汽车所选目标几何歧义 v5 已严格 PASS；汽车多目标主动云台联合 v2 的短遮挡 FAIL 保留，修正计时后的联合 v3 已取得指定目标安全 18 项与所选目标云台协同 13 项 PASS，但身份仍有未知样本，距离和高度稳定时间均右删失。正式 `fullplan_v1` 首 8 次原评价为 7 PASS、1 FAIL；v1/v2 旧计划及原始报告保留，旧录制不计入 v3 分母。不能把已有单次工程通过改称正式重复研究全部完成。

历史工程录制和 v3 冻结研究均位于本地 `results/` 归档；下文未带 v3 前缀的工程目录均相对历史 results 根，正式 v3 目录相对冻结 results 根。`results/验收总览.html` 是需重新生成的静态入口，不能假设打开旧页面会自动刷新研究进度。公开克隆的归档边界见 [结果工件说明](RESULTS_ARTIFACTS.md)。

| 阶段 | 已实现并有实际记录的内容 | 最终研究状态与局限 |
| --- | --- | --- |
| 一：单目标状态估计与闭环 | RGB-D/YOLO、三维估计、PX4 跟随、行人/汽车、velocity/position、短长遮挡与重选；四份历史 v2 工程录制严格通过 | v3 阶段一的 100 个槽均已终态；所有在线和离线指标、失败分类与负结果已进入本地研究归档，不能把 107/166 主研究结果解释成单阶段成功率 |
| 二：多同类中的指定个体 | 三目标首框选择、全轨迹遥测、禁止自行换人、短遮挡/长失联、两类 crossing；两类唯一实例多候选安全及所选目标歧义悬停均已有工程记录 | v3 阶段二槽位已终态；指定个体的身份未知帧、失败和无选择任务按完整分母保留，不能宣称未知帧已自动 ReID |
| 三：三轴云台协同 | 三轴物理关节、编码器反馈动态 TF、视线控制、画面水平与机体缓慢回正；active/midpoint 接口和多目标联合记录均已保留 | v3 阶段三槽位已终态；联合实验中的短遮挡、身份未知以及距离/高度右删失仍按报告原值保留，主动云台不替代目标身份评价 |

三个阶段均已实现，预定主研究和独立扩展的执行与后处理均已结束。主研究并非全部工程验收通过；失败与性能局限仍是最终结果的一部分。独立退出清理验证也已完成，最终交付入口见 [交付状态](DELIVERY_STATUS.md)。

## 阶段一证据及研究范围

四份工程录制为 `stage1_final_v2_person_velocity`、`stage1_final_v2_person_position`、`stage1_final_v2_car_velocity`、`stage1_final_v2_car_position`；各自 `offline_evaluation.json` 记录严格验收，bag、视频、遥测和配置仍是核验依据。

已有 132 帧完整可见仿真检测标签经过目视复核，运行阈值 0.45 下汽车 Recall=0.7564，包含 19 次漏检。已有四源录制、四方法、五类故障各 10 个种子的 816 条离线重放记录；这不是 816 次独立飞行，也没有让四方法分别改变原飞行闭环。

实际在线误差审计已有 `stage1_final_v2_person_velocity/online_state_accuracy_v2.json`：冻结表面锚点位置 RMSE 约 0.1326 m，速度 RMSE 约 0.0793 m/s，输出可用率约 82.65%。它不等于理想 GT ego 回放约 0.0598 m，也不是独立模型中心误差。原 schema 1 的 1.7595 m 结果保留，schema 2 按源码坐标契约纠正评价变换，不能混写成运行算法精度改进。完整解释见 [已录制研究结果](RECORDED_RESEARCH_FINDINGS.md)。

## 阶段二：安全通过项、身份覆盖与失败历史

| 真实工程录制 | 安全评价 | 独立物理身份的全部任务机会 |
| --- | --- | --- |
| `stage2_person_parallel_probe_v2` | PASS | 220 次：170 正确、0 错误、35 无新鲜所选检测、15 unknown |
| `stage2_car_parallel_probe_v3` | PASS | 218 次：168 正确、0 错误、35 无新鲜所选检测、15 unknown |
| `stage2_person_crossing_probe_v1` | PASS | 217 次：139 正确、0 错误、78 unknown |
| `stage2_car_crossing_probe_v1` | PASS | 217 次：84 正确、0 错误、133 unknown |

上述“0 错误”只表示可确认样本未观察到错配，未知帧和无新鲜检测仍在完整分母中。尤其汽车 crossing 的正确比例下界为 84/217≈38.71%，不能写成“身份保持率 100%”。源图时间精确对齐的接触表位于两份 crossing 录制的 `identity_review/`；抽样观察不自动批准整段可见身份标签。amodal MOT 与无遮挡几何子集的范围见 [阶段二实现协议](STAGE2_IMPLEMENTATION.md)。

行人真实歧义录制 `stage23_engineering_v1_s2_person_ambiguity_locked_seed000/stage2_evaluation.json` 为 PASS。唯一实例多候选安全记录：行人为 `stage23_engineering_v1_s2_person_auto_unique_auto_seed000/auto_unique_evaluation.json` PASS；汽车采用同前缀 car 目录中的 `auto_unique_evaluation_v2.json` PASS，原 schema 1 解码/快照验证失败报告保留。

汽车真实歧义 v5 已严格通过，以下四份历史失败完整保留，不能靠末尾悬停单独判通过：

- `stage23_engineering_v1_s2_car_ambiguity_locked_seed000`：检测合并框中心及深度表面锚点变化，严格马氏关联不接受，产生新假设；之后歧义分量没有包含原所选轨迹。原轨迹失联并悬停是安全行为，但没有完成所要求的“所选目标几何歧义”验收。
- `stage2_car_ambiguity_probe_v2`：新合并框安全保护已加载，源码 SHA256 为 `918e6b7f026b6ec4e22e1a6ae746232fbbfe5beb5f1b92f57c76281439659d49`。本次在靠近尚未发生实际合并前出现推理时延尖峰：source35.0 的推理 wall-time 约 0.657 s，到达 35.568；下一 source35.5 到达 35.796。定时输出在 35.760 已因最后三维测量年龄 0.760 s 超过原 0.75 s 门限锁存 LOST。两帧都检测到三个高置信度目标；这是时延先触发失联，不是空检测或合并保护漏触发。后续禁止自行恢复符合原任务规则，严格报告仍为 FAIL。
- `stage2_car_ambiguity_probe_v3`：请求 RTF=0.5 后，在 sim10.2 的起飞阶段被 supervisor 的 `status_stale` 锁存中止，最大估计高度仅 0.047 m。PX4 Commander 源码每 500 ms PX4 时间发布状态、DDS 上限 5 Hz；正常状态周期在 RTF=0.5 下约 1 wall s，与旧 supervisor 的 1 wall s watchdog 相碰。odom 在中止时 wall 年龄为 0.014 s，adapter 的 ROS 时间状态门控没有记录重新关闭，PX4 未报 failsafe。此目录及严格 FAIL 保留；不能当成合并保护实际验证。
- `stage2_car_ambiguity_probe_v4`：修正 sim-only 状态 watchdog 后实际起飞，最大高度 2.968 m、水平跨度 14.242 m，正常完成 50 sim s 跟随观察，monitor 与基础飞行为成功，但严格“所选目标几何歧义”仍 FAIL。source44.2 合并框在44.376到达，推理 wall0.150 s；竞争轨迹2最后测量43.6，按source仅0.6 s，但在44.36输出tick已按0.76 s标 LOST，旧 merge 保护错误地先排除其状态。合并框因此新建轨迹5，后续歧义仅在2/5之间；所选轨迹1于44.760失联，安全悬停不能冒充歧义验证成功。

合并保护只添加冻结证据，不放宽三维接受门限、不融合不可靠观测、不创建重复身份；实际通过证据为后述 v5 真实录制，单元测试仅核对失败边界。新资源或场景验证须采用新探针名字，不能重跑覆盖上述失败。

针对 v4，非所选竞争轨迹即使先被输出tick标 LOST，只要该帧 source time 的最后三维测量年龄仍在原0.75 s内，也可仅供添加冻结边；它不复活、不更新、不解除所选任务的 LOST 锁存。source已过期的竞争轨迹仍不得供证。三项精确复现 source43.6/44.0、输出44.36、延迟source44.2次序及失败边界的回归测试已通过。新 `stage2_car_ambiguity_probe_v5/stage2_evaluation.json` 实际严格 PASS，包含所选目标的几何歧义、暂停控制和最终持续悬停；它不能抹去前述失败。

针对 v3，仿真 runner 显式设置 supervisor 的 wall-status watchdog 为 `1 / requested_RTF`（0.5 对应 2 wall s），记录到 `run_config.json`、`configuration/runtime_parameters.yaml` 和节点启动日志；实机节点默认仍为 1 wall s。未更改 odom/command watchdog、0.60 s 观测或 0.75 s 预测安全门限。monitor 现在将 abort、wall timeout、中断和未满足基础飞行证据传播为非零进程退出；显式 no-follow 试验仅免除视觉有效命令/水平位移要求，仍须有起飞和有效 PX4 流，完整安全结论仍由独立评价器给出。后续 v4 已实际起飞，v5 取得严格歧义 PASS；不能以此删除 v3 的中止记录。

## 阶段三与评价器版本

行人 `stage3_person_active_probe_v1` 和 `stage3_person_midpoint_probe_v1` 均有 `gimbal_evaluation.json` 与独立 `offline_evaluation.json` PASS。

汽车 `stage23_engineering_v1_s3_car_gimbal_active_seed000`、`stage23_engineering_v1_s3_car_gimbal_midpoint_seed000` 的独立 `flight_evaluation.json` 均为 PASS；当前三轴物理评价是各自 `gimbal_evaluation_v3.json`，均为 PASS。旧 schema 1/2 的编码器通道解码/覆盖检查失败报告保留，不能误写成原始物理证据从失败被覆盖为成功。当前报告采用受支持的最高 schema，与 PASS/FAIL 无关；验收页面展示具体采用文件和旧结果历史。

`stage3_multi_person_active_probe_v1` 仅作早期集成证据，其参数尚未继承完整阶段二歧义保护，不能替代最终联合验证。新 `stage3_multi_person_active_probe_v2` 使用 RTF=0.5 和完整阶段二指定个体安全参数，实际完成初始框选、短长遮挡及重选，指定目标安全 18 项与三轴物理 13 项均为 PASS。独立物理身份评价的全部 217 个任务机会为 166 正确、0 错误、35 无新鲜所选检测、16 unknown，不能将 166/217≈76.50% 写成全程 100%。实际在线冻结表面锚点位置 RMSE 约 0.1947 m、速度约 0.1086 m/s，状态有效覆盖约 85.46%；它包含云台动态图像时刻变换和 PX4 定位，不等于模型中心精度。汽车联合 v2 的失败与 v3 的实际结果见下文；这两类追加工程验证不属于正式 166 次主分母。

`stage3_multi_car_active_probe_v2` 的三轴物理 13 项 PASS，指定个体安全评价因短遮挡没有采到空检测而整体 FAIL；其短遮挡请求 29.6、关闭成功确认 29.7、打开请求 29.8、打开确认 29.9，只给约 0.1 s 的关闭确认后保持时间。短遮挡期间未失联、恢复保持原任务，长遮挡与显式重选后完整约 11.1 s 跟踪均通过，但这些不能取代缺失的实际短遮挡证据。该失败及原始录制完整保留。

汽车联合 v2 独立物理身份全部 216 个任务机会中为 87 正确、0 错误、34 无新鲜所选检测、95 unknown；动态相机独立几何 299/299 可用，物理身份 unknown 不能被这项几何可用率替代。在线表面锚点位置 RMSE 约 0.5721 m、速度约 0.2334 m/s，状态有效覆盖约 85.15%；215 次检测机会中 181 次可取所选框中心，条件中心 RMSE 约 8.78 px，可观测覆盖 84.19%。距离与高度瞬态没有保持到窗口终点，右删失如实保留；不能仅凭低画面中心误差称整个跟随性能已达标。

遮挡驱动现已改为与本次成功关闭 ACK 关联后开始保持，两类均固定加 0.05 s 渲染余量；云台位置刷新不重置计时，失败清理不改写原动作结果。新增与相关回归共 37 项通过，随后四个 ROS 软件包构建通过。请求与响应仍不是精确渲染遮挡时刻，真实空检测仍由原严格 evaluator 核验，详见 [遮挡刺激计时说明](SHUTTER_STIMULUS_TIMING.md)。

新 `stage3_multi_car_active_probe_v3` 已完成，严格指定目标安全 18 项与所选目标云台协同 13 项均 PASS。独立物理身份评价有 299 个诊断帧，其中任务机会共 216 次：95 正确、0 错误、36 无新鲜所选检测、85 unknown。完整机会分母下可确认正确比例为 95/216≈43.98%，不能写成身份保持率 100%。动态相机独立几何 299/299 可用，不消除身份未知样本。

联合 v3 实际在线冻结表面锚点位置 RMSE 为 0.473032 m、速度 RMSE 为 0.211498 m/s，状态有效覆盖为 84.7635%。215 次检测机会中 179 次可取所选框中心，覆盖 83.2558%；在这 179 次可观测样本上，画面中心 RMSE 为 9.21491 px，归一化中心误差为 0.0176036。179 个源图像到首次关联命令的平均延迟为 0.174726 仿真秒、95%分位数为 0.252 仿真秒；这是有命令匹配样本的条件统计，不能代替所有图像的端到端可用率或墙钟实时能力。

联合 v3 初始任务和重新选择任务的距离、高度稳定时间全部右删失，观察窗口内没有取得所要求的持续稳定证据；显式重选确认用时 0.08 仿真秒。安全及云台协同通过不能改写这些负结果，也不能将重选确认时间当成距离或高度稳定时间。

评价修订 3 当时的 Windows 完整测试共 492 项：487 项通过、5 项跳过；v2 冻结 Linux 副本的 492 项全部通过。当前 v3 冻结 Linux 副本另有 531 项测试、四个 ROS 软件包构建及导入隔离证据，原始日志位于本地归档的 `results/frozen_fullplan_v3/freeze_validation/`；这些均不替代真实飞行与重复统计。实际 bag 核对揭示的合法混合时刻回退已补回归：预测消息与图像测量可有不同时间语义，真正的接收时钟回退仍失败；记录序列窗口内的 LOST、歧义和错误 UUID 仍完整保留。原汽车 raw 真实 bag 的 `evaluation_revision=3` 重评 PASS 已独立保存，原 v1 判定及修订 2 的 FAIL 报告全部保留，不能覆盖或混写成新的飞行尝试。

## 正式主研究 166 次与另列 16 项扩展工程

| 预定范围 | 次数 | 当前状态 |
| --- | ---: | --- |
| 两类 × 四估计方法 × 10 seeds，velocity | 80 | 已终态：51 PASS、29 FAIL；离线台账与统计已归档 |
| 两类 × adaptive KF × 10 seeds，position | 20 | 已终态：15 PASS、5 FAIL；含 seed08 评价基础设施异常 |
| 两类 crossing × 10 seeds | 20 | 已终态：14 PASS、6 FAIL |
| 两类 parallel / ambiguity / auto_unique 工程安全 | 6 | 已终态：5 PASS、1 FAIL；已有探针仍单列 |
| 两类 × active / midpoint × 10 seeds | 40 | 已终态：22 PASS、17 FAIL、1 INTERRUPTED |
| 主矩阵合计 | 166 | 已终态：107 PASS、58 FAIL、1 INTERRUPTED；完整执行、离线、指标和失败分类见本地冻结归档 |

本次冻结研究使用本地 `results/frozen_fullplan_v3/` 归档，统一前缀为 `fullplan_v3`。其主计划 `results/frozen_fullplan_v3/full_plan_research_v3/plan.json` 的 canonical SHA256 为 `58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`；它绑定正式资源、配置和源码。恢复必须保持 `--output results/full_plan_research_v3` 的原相对写法。实时状态由原飞行子清单读取，正式离线评价不能用旧录制的重放结果抵扣。

`fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08` 保留原 FAIL，评价器曾报 SQLite error 11、未形成可评分评价 JSON。[独立 bag 审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)确认 zstd 帧未正常结束；独立解码得到完整 SQLite，ROS 原生路径则少输出末尾 128 KiB 并重现原错误。这是已确认的评价基础设施/证据问题，压缩为何未正常结束仍未确定，不能称为原始 SQLite 内容损坏或算法跟踪误差。34 个 FAIL 必须保留，其他失败也不能据此一概归为同一原因。

另外 [扩展工程协议](EXTENDED_ENGINEERING_PROTOCOL.md) 登记的 16 项运动、距离及故障条件已全部终态，为 2 PASS、14 FAIL；其中两次基础设施停止单独说明。它们与主矩阵独立记账，每个条件仅一次工程飞行，不能并入主矩阵冒充十次配对重复；既有探针不抵扣正式槽位。

正式矩阵在首条正式试验前统一修订为请求 RTF=0.5，行人 320/2 threads、汽车 640/4 threads；观测 0.60 s 和状态预测 0.75 s 安全年龄不变。早期 RTF=0.7 探针及其失败保留并分组，不能与新资源正式重复混算。实际工程环境是 WSL2 Ubuntu 24.04.1、ROS 2 Jazzy、Gazebo Harmonic、PX4 v1.17.0，具体消息版本及提交由 [版本锁定](VERSION_LOCK.md)与环境清单固定；不能宣称已经验证原计划 Ubuntu 22.04/Humble 组合。

总入口和冻结操作见 [正式研究运行说明](FULL_PLAN_RESEARCH_RUNBOOK.md)。已登记 RUNNING 中断槽位恢复为 INTERRUPTED，不自动重飞；冻结计划、子矩阵和离线 manifest 绑定计划及源码哈希。全部运行收齐、全部离线槽位尝试过与全部安全验收 PASS 是三个不同结论。失败保留为研究结果，不能改名重试直到成功后只保留成功值。

主版运行器的单路 SIGINT/非交互 stdin 修改没有回填正式冻结根。主研究及补充全部结束后，已在独立 cleanup 冻结根完成 stage1 与 stage3_multi 两次真实退出验证：分别覆盖 8 和 9 个 ROS 节点，均为 PASS，无观测到的进程残留，正式台账 SHA 未变。具体范围和原始工件位置见 [cleanup 验证协议](CLEANUP_ENGINEERING_PROBES.md)；本项不重评跟踪性能，也不进入原 166+16 分母。
