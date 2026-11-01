# Humble43验证与剩余准入

2026-11-01 17:27:20（北京时间）快照。本文件说明当前证据和待执行工作，不替代原始评价。核心12独审通过；原生v2组件04的85项和3项describe真实通过；安全4原四场全部PASS、完整原guard及闭合独审PASS，安全批次主命令退出0。扩展16场已有6场开始、5原始终态（4 PASS/1 FAIL），前五个outer均闭合，第六场速度控制加减速已开始、10尚未开始；后续状态以原monitor为准，整批尚未闭合。第五combined保留原算法FAIL，第三槽UTC/monotonic差异仍未归因。其余扩展、容量/定标及正式准入仍待完成，正式仍0/280。历史Humble42保持8 PASS、1 FAIL、3 PENDING。

第六场`person_extension_speed_changes_velocity_seed004`的原槽于09:27:20.264007 UTC START，外层于09:27:16.137633 UTC START，截至本快照尚无终态。[前五场失败与原件快照](../tools/experiment_orchestration/humble43_extension_partial05_snapshot01/README.md)保留4 PASS/1 FAIL；其中11未开始是第六场START之前的历史时点，原字节保留。

## 已完成的修复验证

Humble43固定来源为`/root/uav_tracking_fullplan_v4_humble43`。该版本已完成四个ROS包的隔离构建、模块/ament来源检查、FastCDR检查和真实消息序列化往返。Linux全套1763项中1758通过、原5项平台跳过。汽车保持原生PT/FP32的04微调权重、512输入/CPU4，行人320输入/CPU2；请求RTF为0.125，PX4适配器50Hz。观测时效0.60秒、预测期限0.75秒等原门限不变，不证明实机实时性。

独立具名诊断`reliability_v4_humble43_birthdiag01`已经完成一次75秒汽车交叉任务并获得原始工程PASS，原始观察器、归档和清理均完成。距离/高度RMSE为0.857657/0.155009米，机体参考的末端距离与高度稳定。导航分析仍含删失窗口；身份主口径为754格中644正确、0已知错误、110未知，正确覆盖85.4111%。普通诊断口径648/754不能代替保守主口径。这一场只支持单次开发诊断结论，不计入核心12或正式280，也不支持“所有身份均正确”。

诊断完整独审收据为本机`D:/WSL/UAVHumble22-validation/humble43_birthdiag01_final_independent01.json`，SHA256：`62cc3df97c0ccd42f35f2b076b277fb5a2004b0c2df550499f6560ace725c39d`。原批次终态SHA256：`44c272c2e9a71ad42d6d12ca51f3901ded43807f580fe834c5c7ac16d5a62098`。

## 当前核心12

原生runner已为`reliability_v4_humble43_probe01_seed004_matrix`全部12槽生成原始工程PASS，整批主命令及进度桥均退出0。原RUN终态于2026-11-01 03:55:20.860506 UTC记录`ORIGINAL_CORE_TERMINALS_COMPLETE`，planned/attempt/terminal计数为12/12/12、状态计数为PASS12，error和slot_read_error均为null、final_errors为空、cleanup无残留。原owner终态为COMPLETE、归档进程返回0、四个原生会话均healthy；这些原值已由既有`development_safety.actual_core`完整独立复验通过。行人/汽车各六组：速度、位置、交叉、中位云台、主动云台、多目标主动云台。每组seed004、75秒；禁止重用旧槽、拼入单次诊断或放宽门限。

真实[本机独审收据](../tools/experiment_orchestration/humble43_core12_closure_snapshot01/humble43_core12_closed_independent01.json)为49,654字节，SHA256：`f94f6f01e4da2c2ddca804ff2478e33de59a5ab9f227d6bdfde7d8d4aa653c1a`。审计于03:57:05.852929至04:00:06.134654 UTC执行，原调用实际退出0；原validator返回result=PASS、completed_count=12、all_original_core_cells_pass=true，收据中的safety_or_extension_admitted、formal_seed_use_authorized与formal_seeds_consumed均为false。该收据只确认当前来源的核心开发关口，不替代后续安全、扩展、定标或正式准入。

| 已产生原始终态 | 工程状态 | 距离RMSE/m | 高度RMSE/m |
| --- | --- | ---: | ---: |
| person_stage1_velocity_seed004 | PASS | 0.758609 | 0.147545 |
| person_stage1_position_seed004 | PASS | 0.763342 | 0.162684 |
| person_stage2_crossing_seed004 | PASS | 0.930522 | 0.150463 |
| person_stage3_midpoint_seed004 | PASS | 0.765062 | 0.159948 |
| person_stage3_active_seed004 | PASS | 0.751913 | 0.164592 |
| person_stage3_multi_active_seed004 | PASS | 0.904853 | 0.155198 |
| car_stage1_velocity_seed004 | PASS | 0.750666 | 0.162098 |
| car_stage1_position_seed004 | PASS | 0.703718 | 0.167942 |
| car_stage2_crossing_seed004 | PASS | 0.852427 | 0.152493 |
| car_stage3_midpoint_seed004 | PASS | 0.728828 | 0.157771 |
| car_stage3_active_seed004 | PASS | 0.739129 | 0.161260 |
| car_stage3_multi_active_seed004 | PASS | 0.841079 | 0.174023 |

表中RMSE取`navigation_reference_evaluation.json`的完整任务区间和`base_link`参考，包含悬停等非活动控制样本。十二条报告状态均为`RECORDED_WITH_CENSORED_FAILURES`；模型原点参考等窗口存在未持续稳定结果，原值保留。十二场机体参考下的末端距离/高度稳定条件均为true，不能把工程PASS解释为所有指标或所有窗口通过。整批主命令已正常退出，原owner与全部原记录的既有独审已通过，删失窗口仍按原值保留。

行人单目标中位与主动云台的画面中心RMSE分别为57.705711与17.004366像素，均观察到717/751个机会。主动模式的距离RMSE略低，高度RMSE略高；单个开发种子不提供统计显著性，也不支持所有指标均改善。行人多目标主动的画面中心RMSE为9.463841像素，观察到678/750个机会。

汽车中位云台的检测框中心RMSE为81.548670像素，在751个机会中719个提供有效中心观测（覆盖0.957390146）；该条件度量不等于经人工可见标签认证的物理中心精度。完整任务距离/高度RMSE为0.728827693/0.157771105米，导航覆盖0.916223404、真值覆盖1.0，末端距离和高度稳定检查通过。

汽车主动云台于2026-11-01 03:22:48 UTC完成原始PASS，13项云台检查通过。完整任务距离/高度RMSE为0.739129442/0.161260169米，导航覆盖0.916223404、真值覆盖1.0，末端机体距离/高度稳定检查为true；检测框中心RMSE为13.043403像素，观察到718/750个机会。该开发种子的中心误差较中位模式低，但距离和高度误差略高，不能称全指标更好，也不能替代正式重复比较。

汽车多目标主动云台于2026-11-01 03:52:20 UTC完成原始PASS，13项云台检查通过。完整任务距离/高度RMSE为0.841078587/0.174022697米，导航覆盖0.898936170、真值覆盖1.0，末端机体距离/高度稳定检查为true；检测框中心RMSE为5.554585像素，观察到674/751个机会。

行人多目标交叉的保守主身份网格为753格中649正确、0已知错误、104未知；行人多目标主动为753格中648正确、0已知错误、105未知。交叉的104未知包含1格请求未确认、1格任务边界、30格保护窗内几何身份不可认证和72格无新鲜选中目标证据。后102格独立真值完整；它们不是文件缺失，但也不能算正确或直接归因为检测/通信故障。首次任务322格中218正确、104未知；重选后任务431格均已知正确，仅描述该场该任务。完整核查与证据SHA见[身份未知快照](../tools/diagnostics/humble43_identity_unknown_snapshot01/README.md)。

汽车交叉于2026-11-01 02:34:44 UTC完成原始PASS，18项阶段二检查全部通过，退出码为Gazebo/PX4/ROS/bag/monitor=0、DDS Agent=-2（原规则允许的SIGINT）；退出观测完整、errors为空。主身份口径为`physical_identity.json`的`conservative_task_time_identity`：从首次请求17.84秒至最后录制Clock 93.108秒，753格中647正确、0已知错误、106未知，正确覆盖0.859229748。首次任务322格中217正确、105未知；显式重选后431格中430正确、1未知。两次初始框均独立映射到同一物理汽车，不以UUID连续性证明身份。未知原因计数为1格请求未确认、102格含未知身份帧、2格格内无身份帧、1格任务边界；这些粗原因不直接定位检测或通信故障。上述主汇总最初仅做原报告1 MiB前缀内的有界读取；原整批记录与报告绑定现已由既有独审复验通过，未知分母与原结论保持。

汽车多目标主动的主身份网格为754格中645正确、0已知错误、109未知；首次请求任务322格中215正确、107未知，重选后任务432格中430正确、2未知。该主汇总最初同样来自原报告1 MiB前缀内的有界读取，原整批记录与报告绑定现已由既有独审复验通过；不能用零已知错误或重选后的高覆盖抹去未知，也不能把粗原因直接归为YOLO或通信根因。

当前候选SHA256为`6a0325714f0bc4a874219f5585b282daf658557266b75959e532073447b6eafb`；实际FINAL核心合同SHA256为`c0e179b91b001af98caa4c59290a21972acc006b5fbe8542f63e163700b9bf9b`；核心计划原件SHA256为`939fcbff695afd5ed99cea0479c97fbdb4d85928d6f5afd24ad8b45c6b6c9403`。它们绑定实际来源和原12槽，不是正式280的登记。

本机[进度页](../results/project_progress/humble43_core01/index.html)提供原始心跳和槽计数，原始开始/终态位于上述矩阵的`slots/`。原批次主命令已退出，独审已按既有工具复验每槽原始审计、来源前后、原owner的归档/关闭和无残留结果；实际收据及其SHA见上文。

## 扩展结果判定与v2工具

在Humble43扩展计划建立和飞行之前，已于2026-10-31 23:07:05 UTC记录协议对齐决定。原冻结研究协议允许逐项披露、完整可评价的特定压力算法失败；后加外部定标/发布工具却要求扩展16全PASS。这是额外约束，现以具名v2工具复用原协议判定。原v1工具、原报告和所有历史失败保持原字节，v2不覆盖它们。

核心12和安全4仍须全部工程PASS。扩展16必须完整执行、通过原始完整性和安全检查；只允许原冻结函数复算接受并准确列出的算法FAIL。安全失败、基础设施停止、缺失证据、隐藏/篡改FAIL、跳过场景均不能作为可接受的算法FAIL。长丢失悬停、持续低速、禁止自动恢复、重选前禁止控制等条件继续执行。原FAIL仍是FAIL，不变为PASS；正式研究也不以280次全部成功为结论前提。

v2共10个文件，当前部署字节对应revision02闭合清单SHA256：`83eebf67bfaafc02e1ae0f2a555b2d8408be40b5bc381be1063133dcf86c8afd`。Windows复验85项中78通过、7项按明确平台条件跳过，9项调用真实冻结判定的夹具全部执行通过。原Humble02补验85项中76通过、9项在原SITL排他锁处报错，尚未进入该9项的实际判定。原错误保留；组件03因`Expected original machine lock identity is unavailable`在调度检查处停止，实际drivers/simulation均为空、tests_run=false，85项均未运行。这是测试前调度拒绝，不计作85项测试失败或通过。

实际组件04已退出0：calibration30、connection40、seal15共85项全PASS，0失败、0错误、0跳过，全部9项真实冻结authority测试执行；3项describe均返回0且canonical匹配。原终态状态为`PASS_NATIVE_85_COMPONENT_TESTS_ONLY_NOT_ADMISSION`，SHA256：`9e5826f023e05f0ab6488cfa5f5909ac87b69be1e7d254772ed495fcbd9c1742`。10个部署源字节未变，原生finally核验1940个原文件；peer没有重哈这1940项。8次只读空闲采样均ready，原锁观察依次为3次ABSENT、5次FREE，未推断03缺失原因。调度观察不创建、删除或持有机器锁；子测试仍通过原`run_lock`正常获取和释放锁。

[04最小证据快照](../tools/experiment_orchestration/humble43_native_v2_components04_snapshot01/README.md)保存原工具、独立纯测试、真实终态、三个suite结果及原stdout/stderr、三个describe和peer核查收据。纯调度测试28项和原生85项分开计数，不以静态夹具代替真实原生执行。

这些是组件验证，不是飞行验收，v2尚未用于实际定标、最终发布或正式准入。v2实现与较早原始结果保留于[具名v2快照](../tools/experiment_orchestration/humble43_extension_alignment_v2_snapshot/README.md)，04真实验证另见上述新快照，旧快照不改写。完整数据保留在本机；工具依赖现有外部编排环境，不能保证任意GitHub克隆可独立运行。

## 安全4真实闭合

原`development_safety.sh run`命令经既有唯一monitor运行，四场person/car×auto_unique_multi/locked_ambiguity均已产生原PASS，planned4、attempted4、pending0。原终态文件SHA256为`cd53295d127b4afdffa12e0714f9deaad826632aefb29b590f475892dfd6a4b0`。随后完整冻结安全guard于05:12:36.708586—05:16:57.707220 UTC执行通过，guard原件SHA256为`9268be526d5a00ea293979868303c935605daa4a2e7b46c8e841d8eef5be75d2`；monitor的owned-main于05:16:58.567204 UTC记录code0。[安全4最小闭合快照](../tools/experiment_orchestration/humble43_safety4_closure_snapshot01/README.md)保留原terminal、facts、guard及随后实际形成的[独立静态闭合收据](../tools/experiment_orchestration/humble43_safety4_closure_snapshot01/humble43_safety4_closed_independent01.json)；该收据引用真实原native guard结果，不是新跑的validator。本机[安全进度页](../results/project_progress/humble43_safety01/index.html)保留命令级状态，核心旧页继续保留12原PASS。

原终态中的postwait owner为`COMPLETE`、healthy_cleanup=true，归档进程returncode0、无强制停止或错误，entry前后相同、final_errors和残留均为空。较早归档COPY候选的`COPY_VERIFIED_PENDING_OWNER_CLOSURE`不是postwait最终owner；不能只看候选标签宣称未闭合，也不能只凭COPY产物宣称已闭合。本次依据postwait实际终态及完整原guard。这个结果只完成四安全开发关口，不授予扩展或正式准入。

扩展FINAL admission文件SHA256为`890a8531fb438c251e4ab469e17978cef24dd03239556515b39ec1946e1dac14`，其publication为`0c0622d29154d87458a3c32c9ee9b9cef845824d85afdfcc2246736fd61eb30b`。实际原plan已于05:41:55.836422 UTC以returncode0闭合，完整PENDING16通过104项独立静态check。root另产仅status变化的FINAL runtime合同，SHA256为`68d9ebb2c5a2888e4bfaa6cbf6142298a663380ddce0074aafa1bb0f28912058`，原publication为`deb6b086af27bdf09ec31d816b36c2c8f57837639c49f58da0cb324e4e4ca681`。[扩展16启动快照](../tools/experiment_orchestration/humble43_extension16_start_snapshot01/README.md)逐字节保留原plan、PENDING、独审、FINAL、publication及规划终态；104项是静态check，不是新增原生测试或飞行PASS。

原16场run于05:46:07 UTC实际启动，13:46启动快照原字节保留。首场[原槽终态](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_depth_noise_seed004.json)于06:29:51.150954 UTC生成，status与engineering_result均PASS，execution_status=COMPLETED、flight_exit_code=0、infrastructure_stop=false。其[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/01_person_extension_depth_noise_seed004.attempt_terminal.json)于06:31:00.198600 UTC闭合，error=null、started_this_invocation=1，原audit存在。当前已有6场开始、5原终态（4 PASS/1 FAIL），前五个outer均闭合、第六场运行、10尚未开始。这不表示扩展整批或整批owner已经闭合，后续START以本机[扩展批次进度页](../results/project_progress/humble43_extension01/index.html)及原件为准。

首场距离/高度RMSE为0.769030/0.154279米，导航覆盖0.916223404、真值覆盖1.0，六项工程检查通过。其[原归档报告](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_person_extension_depth_noise_seed004/bag_integrity.json)记录原始录包4,148,883,456 B、压缩1,214,272,594 B；在线RGB、在线Depth、research RGB、research Depth四流各933条。实际[recording policy](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_person_extension_depth_noise_seed004/configuration/recording_policy.json)及compression_command均为`zstd -T4 -19 --long=27 --check`，不能套用较早T1实测。该单个深度噪声压力样本不等于完整28格容量测量，也不证明280次空间足够。各开发scope仍不代替实际16格终态、容量/定标、最终封存及正式280。

第三场[dropout原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_dropout_seed004.json)于08:33:48.425056 UTC终态PASS、engineering PASS、flight_exit0、infrastructure_stop=false；[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/03_person_extension_dropout_seed004.attempt_terminal.json)于08:35:04.731320 UTC闭合、error=null。第四场latency的[原槽START](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_latency_seed004.started.json)及[外层START](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/04_person_extension_latency_seed004.started.json)分别记录08:40:02.398752和08:39:59.802360 UTC，其[原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_latency_seed004.json)已于08:57:53.783337 UTC生成PASS、flight_exit0、infrastructure_stop=false；此前latency运行中快照现为历史。

第五场[combined原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_combined_seed004.json)于09:22:51.706659 UTC记录COMPLETED/FAIL、engineering FAIL、flight_exit_code=0、infrastructure_stop=false；其[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/05_person_extension_combined_seed004.attempt_terminal.json)于09:23:21.491184 UTC闭合、error=null。原slot的negative_evaluators列为`surface_flight`，`long.prediction_observed=false`；原outer的known_algorithm_failures同时保留`surface:long:prediction_observed=FAIL`及`navigation:REGISTERED_PERFORMANCE_GATES_FAILED`，两层原分类均保持。

该场34.86秒已经提前LOST，预定长遮挡请求43.4秒才开始；不能把先失锁解释为正常长遮挡触发，也不能用长遮挡窗口内首次LOST代替全程首次失锁。[原surface报告](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_person_extension_combined_seed004/flight_evaluation.json)保留短遮挡PASS，以及50.4秒显式重选、50.404秒确认后43.164秒持续跟踪PASS。原[导航报告](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_person_extension_combined_seed004/navigation_reference_evaluation.json)全程base_link距离RMSE为2.451894米、绝对误差p95为6.488093米，高度RMSE为0.170694米，真值752/752；末段距离/高度持续稳定均true不能证明全程达标。这些局部恢复和末端收敛不抵消原FAIL，不重试或改写同名槽。

第三槽UTC START 07:25:06.748207→08:33:48.425056共4121.676849秒，必须保留。其navigation command UTC 07:46:25.933494→08:33:38.576415跨度2832.642921秒，原`elapsed_wall_s=117.6539923`由执行源码的`time.monotonic()`计量，差2714.9889287秒（约45分15秒）；其他四条命令UTC与monotonic仅微秒差。原评价returncode0、error=null及工程PASS不变，但该时间差不能解释为约69分钟算法耗时，也不能删掉UTC跨度或将monotonic冒充UTC。

08:40:36 UTC完成的有限只读核查，在Windows System日志07:40—08:40 UTC范围内查询Kernel-Power 42/107、Power-Troubleshooter 1及Kernel-General 1，均返回`NoMatchingEventsFound`；两owned进程33712/28584仍alive，新lease未到期。该范围和事件集合不足以确定原因，不能据此归因用户休眠或宣称已证实时钟跳变；工程计时异常保持未归因，不新造审计结果或改写原记录。后续完整28格分别汇总原UTC跨度与实际活跃计时，并披露无法解释的差异。

## 下一步顺序

1. 核心12原`actual_core`独立复验已通过；保留实际收据、全部原始PASS及完整owner、归档、来源和清理证据，不以此覆盖任何历史失败。
2. 原生v2组件04完整补验及安全4原四场/完整guard/主命令退出已通过；保留独立scope与真实闭合原件。
3. 扩展原规划及PENDING16静态独审已通过、独立FINAL合同已发布；当前6场开始、5原终态（4 PASS/1 FAIL）、10尚未开始，继续按原冻结流程完成其余原槽与整批owner收尾，保留combined算法FAIL、全部安全结果和时钟异常，不把局部恢复或单场通过当作整批闭合。
4. 用完整28格实测录包/归档/临时峰值和剩余空间；导出预定两条核心速度录制，完成R0定标。不能用一个小样本估计就宣布280次容量足够。
5. 完成独立最终来源准备、冷构建、正式120+160登记、四法回放绑定、补充检测/时延的前瞻协议、源码封存及首正式前完整准入。
6. 执行280次正式飞行、20条同观测四法离线比较、检测/身份/时延统计，生成图表、视频、最终计划书和研究报告，再同步GitHub。

核心12独审、原生04组件补验及安全4开发关口已通过；扩展6场已开始、5/16原终态（4 PASS/1 FAIL）、10场未开始，仍须完成当前第六场和其余槽、容量/定标、最终准入及280次逐次飞行与归档。本批原8—10小时、整体5—6天仍是条件估计；完整28格后按实际活跃计时与UTC分别重算，不套最初首场约27分钟作承诺，也不恢复历史较短小时估计。算法FAIL、未知身份、未稳定窗口与未归因计时差异均保留；现阶段不预设“自适应KF所有指标最好”或“主动云台必然提升整体可靠性”。
