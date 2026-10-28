# 166 次主研究矩阵运行说明

当前正式研究为 `v3`：冻结 Linux 环境 [531 项测试通过](../results/frozen_fullplan_v3/freeze_validation/unittest.log)，[四个 ROS 包构建通过](../results/frozen_fullplan_v3/freeze_validation/colcon_build.log)，[导入路径隔离核验通过](../results/frozen_fullplan_v3/freeze_validation/import_isolation.json)。[主计划](../results/frozen_fullplan_v3/full_plan_research_v3/plan.json) 共 166 个槽。2026-10-27 首个外部守卫槽（阶段二行人 crossing seed000）PASS 后，已终态 101 槽（67 PASS、34 FAIL），65 槽 PENDING，原 100 个阶段一终态不变；剩余 65 槽已开始守卫续跑。主离线队列及独立 16 项扩展尚未完成。这是检查点，实时状态以原飞行子清单、`offline_manifest.json` 及 [summary.json](../results/frozen_fullplan_v3/full_plan_research_v3/summary.json) 为准。主版 Windows 后续完整验证为 563 通过、5 个平台跳过，与冻结 Linux 的 531 项分别记账。

旧 `v1` 的 8 次正式尝试按原评价仍为 7 PASS、1 FAIL，原录制和报告全部保留，不并入新 166 次分母。评价修订 3 已用原汽车 raw bag 独立核对为 PASS，并另存报告及 SHA 审计；原始 FAIL 和修订 2 的独立 FAIL 均不覆盖。时间契约及保留规则见 [评价修订 3](EVALUATION_REVISION_3.md)。

本次主计划 canonical SHA-256 为 `58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`；预注册 SHA-256 为 `1e2430af7eb5c89f3b7cc1b45ece0c9855bb5ca27b33be9c11d4753f0d3ecf78`；207 项源码摘要 map 的规范 JSON SHA-256 为 `2da787b1824d519b678cc511b01e5ec03e6c0b6c009b3eac5c00c1a61eec139b`。已有冻结根、正式计划及原始终态均保留，不重复冻结、不重试失败、不并行启动研究。恢复入口与完整前置条件见 [v3 外部逐槽守卫](GUARDED_FULLPLAN_V3_CONTINUATION.md)，后续离线、16 扩展、补充、cleanup 和报告命令见 [v3 交付执行顺序](FULLPLAN_V3_DELIVERY_COMMANDS.md)。

验收页支持与主计划同目录的 `superseded.json`。它按 `plan_sha256` 绑定旧 `plan.json`，匹配时展示历史替代原因及新前缀；不匹配时报告清单问题，不采用替代声明。现有 [v1 历史说明](../results/frozen_fullplan_v1/full_plan_research_v1/superseded.json) 只补充审计说明，不修改冻结源码、计划、原 7 PASS / 1 FAIL 或剩余 158 PENDING。v1/v2 历史录制不计入 v3 分母，也不以历史替代标识代替新研究的完成或通过证据。

总入口 `scripts/run_full_plan_research.py` 使用已经声明的试验：80 次 velocity 四滤波策略干预、20 次 adaptive position 兼容、20 次阶段二 crossing、6 次阶段二工程安全、40 次阶段三云台配对，共 166 次。不会把离线重放种子、工程探针或未执行槽位算成额外真实飞行。

研究在冻结根 `/root/uav_tracking_fullplan_v3` 内运行，统一 prefix `fullplan_v3`。主入口的 `--output` 必须保持原始相对文本 `results/full_plan_research_v3`；改为绝对路径会改变计划摘要，应被恢复检查拒绝。现有 Windows 长运行包装器拼接绝对 output，不能直接用于本计划恢复。锚点来源的原校准路径作为 provenance 保留，不在运行时读取，不需复制旧大 bag。

本机 C 盘空间不足以容纳全部录制，因此 Linux 源码、构建留在 ext4，冻结根 `results` 链接到 D 盘 `/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3`。不得覆盖或删除旧结果腾位置。WSL ext4 的虚拟可用容量不等于 Windows C 盘实际余量，正式运行前须核对实际主机空间。

长运行使用冻结根的 `scripts/run_research_session.sh`，它切到正确工作目录，并将当前进程的 `TMPDIR` 和 `ROS_LOG_DIR` 指向本研究的 `results/runtime/`，使离线 bag 解压和新 ROS 日志也使用 D 盘。不会更改全局环境或电源方案。PX4 自身 ULog 另保留在其 rootfs/log 路径，正式运行前需核实其存储和可用容量。

```bash
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/scripts/run_guarded_full_plan.py \
  --frozen-root /root/uav_tracking_fullplan_v3 \
  --study-output results/full_plan_research_v3 \
  --expected-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28 \
  --audit-output /mnt/d/基于yolo和卡尔曼滤波/results/fullplan_v3_guarded_next_batch01 \
  --max-new-flights 1 --execute
```

```bash
# 全部166飞行终态且仿真停止后，串行读取已有bag，不启动仿真
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  scripts/run_full_plan_research.py \
  --phase offline --prefix fullplan_v3 \
  --output results/full_plan_research_v3 --resume

# 离线入口结束后，由已有小JSON重新汇总论文统计，不读bag，不运行YOLO
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  scripts/run_full_plan_research.py --phase summarize --prefix fullplan_v3 \
  --output results/full_plan_research_v3
```

外部 guard 默认只读检查；上例显式 `--execute` 才飞一个新槽，审计目录必须全新且位于冻结根/results 之外。每槽调用原冻结 master 的 `--resume --stop-after 1`，检查报告、日志、输入资格及前后全部原始行，只允许该 PENDING 槽变为终态。首槽审阅后再扩大批次。出现解压/SQLite/I/O、崩溃或已尝试却缺少完整报告即停止；正常完成且可评分的负面结果保留为 FAIL 后继续。不直接使用无守卫的 `--phase flights` 或 `--phase all` 绕过这些检查，不与仿真并行执行离线评价、测试、构建或重型绘图。

历史 `fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08` 的 SQLite error 11 未被冻结分类器捕获，原 FAIL 不重评、不覆盖。[独立审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)确认压缩帧未正常结束，独立解码为完整 SQLite，而 ROS 原生解压路径少输出末尾 128 KiB。压缩未结束的原因未知，不能归为跟踪算法误差或原始 SQLite 内容损坏；另外 33 个 FAIL 也不能自动归为同类。新增外部工具不复制进冻结根、不改变冻结源码与计划。

冻结后源码、资源或协议哈希有变化，恢复会报错，必须保留旧计划并使用新冻结根/前缀/输出。失败、中断和已有未登记目录不会默默覆盖成成功。子矩阵原报告留在各自位置；原 flight-phase `EXPLICITLY_SKIPPED` 在线分析状态是历史事实，不会被改写。

冻结构建后会 source 新根的 install，再核对算法、ROS 节点、生成消息模块的实际文件路径，以及四个本项目 ROS 包的 ament prefix；任一仍指向旧项目或其他 underlay 就中止，并留下构建日志。通过时将路径证据保存为 `results/freeze_validation/import_isolation.json`。`research_env.sh` 和独立的 `evaluate_stage1_flight.sh` 均由脚本自身位置确定项目根；若继承的 `STAGE1_PROJECT_ROOT` 指向另一根，会在加载 ROS 环境前明确拒绝，应先取消旧变量或改用新根内的脚本。

阶段一在启动第一条飞行前即原子写入 `RUNNING_FLIGHT`，分析前写入 `RUNNING_EVALUATION`。恢复时，阶段一及阶段二三的残留 RUNNING 槽被保留为 INTERRUPTED，包括最后一个槽中断且已无 PENDING 槽的情况；此操作只修复进度记录，不重新飞行。恢复入口应只在上一运行进程已经停止后调用。计划文件自身摘要、离线清单所属计划及任务名集合都会检查。

总入口在读写计划、恢复记录、飞行和离线阶段持有当前冻结根的非阻塞系统进程锁；第二个写入入口会在接触清单前退出，不能把仍在运行的飞行误判成中断。进程崩溃后系统自动释放锁，锁文件保留。仅 `summarize` 可在主入口运行期间读取原子保存的快照；直接启动旧子运行器不共享该入口锁，因此正式矩阵必须统一经总入口调度，不并行调用子脚本。

每条飞行结束后先根据小清单检查基础设施资格；基本评价完成后再次检查，捕捉元数据完整但核心消息无法解码的情况。缺 bag/clock/无人机里程计、已有证据的未起飞、明确 supervisor ABORTED 或核心进程崩溃等会将当前槽保存为 FAIL，并立即停止当前子矩阵及总入口本次后续矩阵。剩余槽保持 PENDING，不能让同一启动故障继续浪费一百次。`infrastructure_stops.json` 保存原因及来源；修复外部环境后可 `--resume` 继续 PENDING，失败名字不会重飞。若修的是冻结源码或参数，应使用新冻结根/前缀并保留旧研究。普通检测、身份保持、跟随或云台性能 FAIL 仍正常计入重复研究，不触发基础设施早停。

## 汇总内容

`summary.json` 将后续离线 `online_state_accuracy_v2.json` 按 trial 名字接回真实飞行种子表，形成阶段一实际在线误差、覆盖率、控制命令抖动和四方法配对 bootstrap。全部可测量配对（包含失败飞行）与双方 PASS 的条件配对分开；缺失配对计入 excluded，不填零。失败率用所有已执行飞行为分母，未执行槽位单独显示，不假装失败或成功。

离线阶段还读取 `follow_dynamics.json`：第一段 FOLLOW 到首个预定遮挡的窗口评价初始距离/高度超调与稳定时间，显式重选形成另外任务窗口，完整区间误差保留之后的遮挡、丢失及悬停。汇总按真实飞行/种子统计，未稳定作为 right-censored 单独计数，缺失窗口单独列出，不能填成 0 s；已稳定样本的条件时间均值须同 censor 数一起阅读。对应 seed 配对同时给未稳定指示量，避免只比较成功稳定的时间。它们是运动目标任务瞬态，不能冒称静态阶跃响应。

同一报告的 `visual_control_metrics` 给出指定目标检测框的中心误差、全部检测机会中的可观测覆盖率，以及图像采集到首条同目标 active FOLLOW/PREDICT 跟踪命令的仿真时间。多目标只取同一源图像的 fresh matched 指定轨迹，不混入其他候选；空检测帧仍在覆盖率分母。延迟以 `state.header - prediction_age_s` 重建实际接受的源图像时刻，按任务、轨迹和图像去重，中间定时预测不算新图像。它包含估计及控制传递，止于跟踪命令，不代表 PX4/执行器响应或墙钟实时性能。总汇用 `follow_visual_` 前缀和原云台评价字段区分，配对和均值均以整次飞行为统计单位，另列机会加权覆盖率、观测样本数及缺失报告数。仅有旧版瞬态结果、没有完整 `visual_control_metrics` 的预存报告保留为历史和 INCOMPLETE_EVIDENCE，不覆盖成新结果。

阶段二先由 REQUEST 框及其源时刻独立建立任务预期物理演员。实际 state 即使错误追成其他演员，也仍与原请求演员比较；身份初始 unknown 则其误差参考缺失，active coverage 与 reference coverage 分开。HOTA/IDF1/CLEAR 分 amodal 诊断与无遮挡几何子集，保留每 seed、任务数、所有检测机会、所有任务机会、unknown 和未检测帧。

既有 66 计划每个 crossing seed 只有一条算法配置，因此只给该配置的逐种子统计与均值区间，不能凭空生成两算法配对差值。每条 flight 内如有多个合法重选任务，其 MOT 值先算任务均值，再以 flight 为统计单位；不是把任务或图像帧当独立重复，也不是宣称跨任务 pooled HOTA。

阶段三按同类别、同 seed 的 active 与 midpoint 做真实配对 bootstrap。画面中心误差以检测可见为条件，必须同时保留其样本数与全部机会 state coverage，不能因少检测而获得虚假的低中心误差。物理关节、反馈动态 TF 与飞行严格验收仍来自独立原评价器。

`v3` 已核对并冻结请求 RTF=0.5、行人 320/2 threads、汽车 640/4 threads，不放宽安全年龄。实际验证组合是 Ubuntu 24.04.1 WSL2、ROS 2 Jazzy、Gazebo Harmonic、PX4 v1.17.0 及匹配的 px4_msgs；原 Ubuntu 22.04/Humble 没有单独复现。旧研究及早期 RTF=0.7 工程探针、失败保留；这是减慢的仿真，不能声称 wall-time 实时或实机飞行。独立 16 项包含加减速、较远距离及故障覆盖，与已有离线故障重放均在主 166 分母之外单列。

`all_flights_attempted`、`all_flight_slots_terminal`、`all_offline_slots_attempted` 表示执行和证据进度；`all_flights_pass` 是不同的安全验收判断。试验完整执行并保留负结果，不等于所有工程/性能判断都 PASS。

## 完成后的指标补充与独立工程扩展后处理

主 166 汇总完成后，建议使用 Windows 主副本的 `scripts/build_metric_supplement.py` 读取已生成的主汇总和逐飞行小 JSON，导出逐飞行指标补充 JSON、Markdown 和 CSV。它补充在线锚点速度 RMSE/p95、接收时刻误差、命令变化率、检测处理帧率和纯推理墙钟耗时（若原始 flight JSON 有这些字段）、整段跟随误差、超调/稳定时间删失、图像中心误差、首命令仿真延迟和阶段二物理身份诊断。缺失值保持缺失；逐飞行 p95 的均值不等于合并帧 p95；这些表不能把主 166 与独立 16 合并为一个实验分母。

原计划指标与当前 JSON 来源、报告覆盖及证据限制的静态对照见 [最终指标覆盖审计](FINAL_METRIC_COVERAGE_AUDIT.json)。

```powershell
python scripts/build_metric_supplement.py `
  --summary results/frozen_fullplan_v3/full_plan_research_v3/summary.json `
  --plan results/frozen_fullplan_v3/full_plan_research_v3/plan.json `
  --trial-root results/frozen_fullplan_v3 `
  --engineering-manifest results/frozen_fullplan_v3/extended_engineering_v3_matrix/manifest.json `
  --output results/frozen_fullplan_v3/metric_supplement.json
```

如果要补充短遮挡窗口中的预测误差，可在上述命令追加 `--include-state-frames`；这只读取已有 `online_state_accuracy_v2.frames.jsonl`，将 TargetState header 仿真时刻与快门请求/响应窗口相交，并把 PREDICTED 状态单独计数。它不会把请求窗口当作渲染可见性真值，也不会读取 bag 或重新推理。

正式主飞行和独立 16 槽均已进入终态、主 166 离线清单完成且仿真进程停止后，才可对独立 16 已有 bag 运行补充后处理。该工具不会重飞、重试或覆盖原评价；它在冻结 Linux 根内通过 D 盘临时目录 wrapper 串行调用冻结的 `evaluate_online_state_accuracy.py` 和 `evaluate_follow_dynamics.py`，并另存来源 SHA 和任务日志。

```bash
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/scripts/run_full_plan_supplement.py \
  --frozen-root /root/uav_tracking_fullplan_v3 \
  --summary /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3/full_plan_research_v3/summary.json \
  --engineering-manifest /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3/extended_engineering_v3_matrix/manifest.json \
  --plan /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3/full_plan_research_v3/plan.json \
  --offline-manifest /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3/full_plan_research_v3/offline_manifest.json \
  --output /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3/full_plan_supplement_v3 \
  --resume
```

该命令的入口是 Windows 主副本脚本；实际路径按挂载位置调整。`run_full_plan_supplement.py` 在开始前检查 166 条主 flight 全部为 PASS/FAIL/INCOMPLETE/INTERRUPTED、主离线 166 槽均有终态、独立 16 槽均有终态，并取得冻结研究写锁；任一 PX4/Gazebo/研究写进程存在即拒绝。额外 16 的安全 `offline_evaluation.json` 已有时只校验并保留；补充 evaluator 输出若已有或只有半成品不会覆盖，缺 bag/配置/报告只记 INCOMPLETE_EVIDENCE。

阶段二和阶段三的身份边界仍须写入论文：正式 20 crossing 是指定个体物理身份统计；6 次工程安全槽另计；40 次阶段三正式配对为单目标主动/中位云台，不能当作多同类指定个体 ReID 重复。`conservative_selected_identity.retention_lower_bound`、`known_coverage`、`observed_physical_identity_switches_within_task` 来自物理标签评估；显式重选确认时间只是新任务 UUID 的确认，不是离场后的自动 ReID 重捕获。

## 独立图表和可追溯数据

`reports/plot_full_plan_study.py` 只消费总汇 `summary.json`，可以在 Windows 上绘制，不需要 ROS、YOLO、bag 解压或仿真：

```bash
python reports/plot_full_plan_study.py \
  --summary results/frozen_fullplan_v3/full_plan_research_v3/summary.json \
  --output results/frozen_fullplan_v3/full_plan_figures
```

输出包括飞行状态、阶段一逐飞行结果及配对区间、阶段二物理身份机会分布、阶段三主动云台减中位的配对区间，以及初始跟随瞬态的已稳定、未稳定和窗口缺失分布，每张同时生成 PNG、PDF、SVG。`flight_units.csv` 保留所有 166 槽及逐飞行瞬态指标；`paired_intervals.csv` 同时保留可测配对与双方 PASS 的条件结果；`follow_transient_groups.csv` 将条件稳定时间与删失、缺失计数一起导出。输入摘要按 SHA 命名存档，清单记录源计划、绘图脚本及全部产物的哈希。未执行、失败、缺失及未知身份不能改写成成功；早期全 PENDING 的绘图冒烟结果只验证图表程序，不是研究结果。

主飞行 166、主离线 166、独立工程 16 及补充后处理 16 全部终态后，另在 `/root/uav_tracking_fullplan_cleanup_v3` 新冻结根开展 stage1 与 stage3_multi 两个独占退出验证，使用新的 `results/frozen_fullplan_cleanup_v3/`。其守卫要求显式绑定主计划、主离线、工程和补充清单及源摘要。真实 PASS 须逐节点证明停止标记后的干净退出，stage1 应覆盖 8 个节点，stage3_multi 应覆盖 9 个节点；外层 ROS/monitor 返回 0 或飞行 PASS 都不足。命令和同步依赖清单见 [cleanup 协议](CLEANUP_ENGINEERING_PROBES.md)及 [v3 交付顺序](FULLPLAN_V3_DELIVERY_COMMANDS.md)，本页不把待执行探针或尚未生成的最终 Word/PDF、图表、视频写为已交付。
