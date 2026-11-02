# RGB-D UAV target tracking and following

**2026-11-03 06:40（北京时间）检查点：Humble54 核心开发批次已有 9 个原始 PASS，第 10 场汽车云台中位正在运行；正式仍为 0/280。** 行人六组及汽车速度、位置、多目标交叉已通过。汽车位置场的独立距离/高度 RMSE 为 0.7049/0.1657 米，末端两项持续稳定通过；汽车三个云台场景仍待本轮判定。多行人主动云台的完整任务身份为 648 正确、0 已知错误、106 未知，共 754 格，不能用诊断帧分母替代。上述为同一开发种子的结果，尚不能代表整体可靠性或算法普遍优势。见[本轮验证与边界](planning/reliability-v4-humble54-native-validation-20261103.md)、[六个行人原件与独立复核](tools/experiment_orchestration/humble54_person6_closed01/README.md)、[前三个汽车原件](tools/experiment_orchestration/humble54_car3_closed01/README.md)、[正式启动路径修复](tools/experiment_orchestration/formal55_supplementary01/SNAPSHOT.md)及本机[当前批次进度](results/project_progress/humble54_core12_run01/index.html)。下方均为历史检查点，原失败不变。

**Historical checkpoint, 2026-11-03 03:37 CST: the separate Humble54 car-position failure-equivalent trial recorded original PASS; formal remains 0/280.** Distance/height RMSE were 0.704/0.170 m. This one trial is independent of the canonical12 and is not spliced into it. Humble53 remains 7 PASS / 1 FAIL / 4 PENDING. See the [original car evidence](tools/experiment_orchestration/humble54_car_position_closed01/README.md).

**Historical checkpoint, 2026-11-03: Humble54 completed the actual Linux cold build and suite: 2021 tests, 2016 passed and 5 platform skips; 1585 frozen entries remained unchanged.** The original supplement FAIL and the separate repaired supplement PASS are both retained. This build result is not flight acceptance. See [native validation and its boundaries](planning/reliability-v4-humble54-native-validation-20261103.md).

**2026-11-03 修复进展：Humble54 已完成检测器线程策略对照和录包时钟队列组件对照，尚待新冷构建和完整飞行。** 新时钟方案在诊断数据完整的配对测试中由5次参考越界降为0次，代价为跳过中间Clock；检测器保持原权重和CPU4设置。临时目录继承、完整源码复制校验、开发batch owner及公共安全/容量入口已补齐并在分项验证中。原Humble53的 **7 PASS / 1 FAIL / 4 PENDING** 和正式 **0/280** 不变，不能把组件或测试通过称为项目验收完成。见 [修复、原件和后续验证顺序](planning/reliability-v4-humble54-repair-20261103.md)。下方为历史快照。

**2026-11-03 01:51（北京时间）停止检查点：Humble53 核心 12 场批次已停止，原始结果为 7 PASS、1 FAIL、4 PENDING，正式仍 0/280。** 六个行人场景与汽车速度跟随通过；汽车位置跟随原 FAIL，后续四场汽车交叉/云台尚未执行，不能称核心 12 场通过。失败场的来源时钟、阶段时间及表面跟随检查分别未过门，录制闭合和 bag 完整性通过；多个失败是否同一根因仍在诊断，尚无修复完成结论。汽车速度场物理距离/高度 RMSE 为 0.7316/0.1595 米、末段均持续稳定，原导航删失记录保留。新增视频库存与 v4 交付入口及其原回归共 **59 项测试通过**，属于交付工具测试，不能计为飞行通过。见[停止原因、证据及下一步](planning/reliability-v4-humble53-core-stop-20261103.md)和[小原件快照](tools/diagnostics/humble53_core_stop_snapshot01/README.md)；本机[核心进度](results/project_progress/humble53_core_slots01/index.html)保留终态。下方运行中描述均为历史检查点。

**2026-11-03 00:16（北京时间）检查点：Humble53 新核心 12 场已有前 4 场原始工程 PASS，4 个原 attempt 审计均已闭合；第 5 场行人主动云台已开始，余 7 场待执行，正式仍 0/280。** 第四场行人云台中位的距离/高度 RMSE 为 0.7732/0.1630 米，末段两项持续稳定、来源时钟、原生起飞和中位云台检查均通过；旧 Humble51 对应失败完整保留。行人交叉的固定身份时间格为 753 格：648 正确、0 已知错误、105 未知，已知覆盖 86.06%，未知继续计入分母。本轮汽车及主动云台尚无通过结论，不能据此认定整体可靠性已解决。见[本轮四场结果与边界](planning/reliability-v4-humble53-core-checkpoint-20261103.md)、[原件快照](tools/experiment_orchestration/humble53_core4_snapshot01/README.md)及本机[核心进度](results/project_progress/humble53_core_slots01/index.html)。下方均为历史检查点。

**2026-11-02 22:31（北京时间）检查点：Humble53 已完成原失败场景的完整 75 秒复验，1/1 原始工程 PASS。** 本场为行人云台中位，距离/高度 RMSE 为 0.7722/0.1540 米，末段两项持续稳定通过；来源时钟、原生起飞及完整外层核验均通过。它只证明这一场复验通过，不能代表汽车、核心 12 场或整体可靠性已通过。新同源核心 12 场计划已生成，**计划生成时为 0/12 完成、12 PENDING**；正式仍 **0/280**。后续路线保持核心 12、安全 4、扩展 16、容量与定标、最终准入及正式重复研究。见[本轮结果与后续关口](planning/reliability-v4-humble53-native-validation-20261102.md)及[75 秒原件小文件快照](tools/experiment_orchestration/humble53_equivalent_snapshot01/README.md)。下方均为历史检查点。

**2026-11-02 21:35（北京时间）检查点：双桥候选已通过 Ubuntu 22.04/Humble 四包冷构建和完整 Linux 测试，1924 项中 1919 项通过、5 项按明确平台条件跳过。** 原 Humble52 测试因临时目录位于 Windows 挂载文件系统而超时，原始超时与不完整日志全部保留；新 Humble53 使用相同源码，将临时目录恢复为原生 `/tmp` 后完成独立验证。75 秒飞行复验仍待执行，正式 **0/280**，项目尚未全部验收。详见[本轮原生验证与后续关口](planning/reliability-v4-humble53-native-validation-20261102.md)。下方均为历史检查点。

**2026-11-02 20:10（北京时间）修复进展：时钟桥与数据桥分离候选已通过生产 RGB-D 组件检查，新增 54 项测试通过。** 20 秒仿真时间取得 202 组同步 RGB-D，时钟最大接收间隔约 33.7 ms，三进程正常退出。Windows 完整回归发现的旧夹具模式错误已修正，受影响两模块回归通过；新冷构建和 75 秒飞行复验待完成。原 Humble51 仍为 **3 PASS / 1 FAIL / 8 PENDING**，正式 **0/280**，项目尚未全部验收。详见[候选与真实证据](planning/reliability-v4-clock-isolation-20261102.md)。

**2026-11-02 19:10:29（北京时间）停止记录：Humble51核心批次已STOPPED，原始结果为3 PASS、1 FAIL、8 PENDING，正式仍0/280。** 第四场行人云台中位完成飞行，但独立source-clock记录4次未来源时刻拒绝、1次诊断交付越界及2条raw/timing缺配对；native-startup另有1次phase时间越界，硬门因此停止后续。起飞、模式序列与交接稳定检查均通过。已有侧车把5个source-clock异常定位到84.028秒附近，尚不能确定共同根因，正在继续原包只读诊断。owner异常路径的原始归档已保留；最终失败状态与较早copy候选的差异不代表原件被篡改。详见[停止原因、证据与最短下一步](planning/reliability-v4-humble51-clock-stop-20261102.md)及[小原件快照](tools/diagnostics/humble51_clock_stop01/README.md)。下方18:58及更早运行中描述均为历史快照。

**2026-11-02 18:58:44（北京时间）快照：Humble51 核心12场已有3个原始工程 PASS、3个对应外层核验闭合，第四场行人云台中位正在运行，另8场未开始；正式实验仍为0/280。** 本轮四包冷构建用时36.4秒；完整 Linux 套件1870项中1865通过、5项有明确平台原因的跳过。前三场的距离/高度RMSE分别为0.7624/0.1584、0.7865/0.1668、0.8940/0.1618米，末段距离和高度稳定检查均通过。行人交叉完整身份时间格为753格：648正确、0已知错误、105未知，覆盖86.06%；第一任务单独仅67.70%，不能称全程身份均已证实。汽车及主动云台的本轮结果仍待产生，原Humble50的11 PASS/1 FAIL保持独立，不能拼入51。见[本轮验证与剩余工作](planning/reliability-v4-humble51-validation-20261102.md)、[原件最小快照](tools/experiment_orchestration/humble51_core_first3_snapshot01/README.md)、本机[核心进度](results/project_progress/humble51_core_slots01/index.html)及[进程与心跳](results/project_progress/humble51_core_run01/index.html)。下方原文均保留为各自时点的历史快照，不代表最新运行状态。

**2026-11-02：Humble50 核心12场已完整闭合，11 PASS、1 FAIL，尚未进入正式280场。** 唯一失败是汽车多目标主动云台场景：短遮挡后原模型已有约0.34–0.41的目标框，被0.45阈值过滤，最终触发正确的LOST锁。原始图像、深度和同采集TF已复核；正在验证仅允许弱检测维护已有三维轨迹的修复，禁止弱框启动任务、自动换人或解除LOST锁。独立完整像素检查还解释了相邻车边缘造成的导航拒绝，原保护继续保留。详见[修复原理与验证边界](docs/CONFIDENCE_TIER_MAINTENANCE.md)。新版本仍须独立构建并重跑完整12场，下方均为有时间标记的历史快照。

**2026-11-02 14:28（北京时间）快照：Humble50 核心验证已闭合8场，均为原始工程PASS；六个行人场景及汽车速度、位置跟随通过，第九场汽车交叉已开始。** 汽车速度/位置两场的真实机体距离RMSE为0.751574/0.715457米、高度RMSE为0.153512/0.169195米，末段距离和高度持续稳定检查均通过。它们属于同一个开发种子，不能据此认定汽车总体可靠性已解决；整批、安全4、扩展16和正式280次仍待完成。见[汽车两场原件与边界](tools/experiment_orchestration/humble50_car_pair_snapshot01/README.md)、[本轮执行记录](planning/reliability-v4-humble50-validation-20261102.md)和本机[实时进度](results/project_progress/humble50_core_slots01/index.html)。下方状态按时间作为历史快照阅读。

**2026-11-02 13:41（北京时间）快照：核心验证已闭合5场，均PASS，第六场行人多目标主动云台正在离线评价。** 后续final-root-v2的DDS安装目录转换、CV2环境恢复及封存工具连接标识已完成三文件修复并实际应用；原生工具清单核验及独立复核通过，当前核心来源未变。真实final-root构建、适用专项测试和正式280次仍待执行，详见[修复源码与证据](tools/experiment_orchestration/humble50_finaltools_fix_snapshot01/README.md)。

**2026-11-02 12:46（北京时间）快照：Humble50 四包冷构建和完整 Linux 测试通过，新的核心12批次正在执行，前三场行人场景均为原始 PASS 且外层核验已闭合。** Linux 1819项检查为1814通过、5项平台跳过。行人速度/位置跟随与多目标交叉属于同一个开发种子，不代表正式重复结论；本轮汽车及云台场景仍待实际完成，正式仍0/280。请打开本机[当前核心进度页](results/project_progress/humble50_core_slots01/index.html)和[命令进程监控](results/project_progress/humble50_core_run01/index.html)，或阅读[本轮证据与后续步骤](planning/reliability-v4-humble50-validation-20261102.md)。下方较早状态均按其时间作为历史快照阅读。

**2026-11-02：旧协议兼容断言已修复，完整Windows套件1789项、11项平台跳过、无失败；正在冻结新的Humble47来源。** 原46的冷构建通过与完整Linux测试失败保留，尚未47原生验证或飞行，正式0/280。见[验证记录与后续修复](planning/reliability-v4-humble46-validation-20261102.md)。

**2026-11-02（北京时间）：Humble45核心批次停止后，已完成时序取证和时钟修复候选；145项相关测试及22项补充复验通过，最终独审通过。** 原结果1 PASS、1基础设施错误、10未开始保持，正式仍0/280；接下来准备新Humble46隔离构建、完整原生测试和新核心批次。见[故障、修复与后续工作](planning/reliability-v4-humble45-position-abort-20261102.md)。

**2026-11-01 23:17（北京时间）：Humble44四包冷构建通过，但完整Linux测试因3个旧夹具缺少新增QoS配置而失败。** 原1767项为3 ERROR、5平台跳过，原失败保留；现已补齐夹具，受影响的13项在Humble原生全部通过，正在准备新Humble45整套验证，尚未飞行复测。此前原生录包冒烟的1290条消息完整、无缺失或重复，仅属合成配置验证。正式仍0/280。见[44原始失败与后续验证](tools/diagnostics/humble44_validation_failure01/README.md)、[录包冒烟原件](tools/diagnostics/humble44_recorder_qos_smoke01/README.md)及[本轮路线](planning/reliability-v4-humble44-recording-repair.md)。

**2026-11-01 22:39（北京时间）：原生只读诊断已完成，已定位约2.7秒处缺失raw/timing和一次phase未来56毫秒；首clock边界解释已排除，共同根因未证实。** 新Humble44候选为5条关键证据流添加显式recorder深队列及每场配置快照；4项新测试、36项相关Windows回归通过，原生录包及新飞行验证待执行。原43失败与正式0/280保留。见[诊断原件](tools/diagnostics/humble43_clock_boundary_snapshot01/README.md)及[修复与验证路线](planning/reliability-v4-humble44-recording-repair.md)。下方状态按各自时间阅读。

**2026-11-01 22:02（北京时间）批次终态：Humble43扩展16已停止，原始槽为12 PASS、4 FAIL，原生driver退出2；完整外层审计计数15，最后汽车远距离的source-clock及native-startup未通过硬门。** 核心12和安全4的既有通过记录保留，正式仍0/280。该最后失败不能当作允许的压力算法FAIL，容量collector/定标/正式发布前置未满足；当前继续离线取证，尚未选择修复。详见[停止与诊断记录](planning/reliability-v4-humble43-extension-stop-20261101.md)及[原件快照](tools/diagnostics/humble43_extension_stop_snapshot01/README.md)，本机[进度页](results/project_progress/humble43_extension01/index.html)为STOPPED_FAULT。下方运行中描述均为有时间标记的历史。

**2026-11-01 20:31:33（北京时间）快照：Humble43核心12、安全4已完整闭合并独审通过；扩展16为13 START、12原终态（10 PASS/2 FAIL），前12个outer均闭合，汽车combined运行，另3格未开始；正式仍0/280。** 第12场汽车延迟原PASS，距离/高度RMSE为0.761595/0.168965米、末端稳定通过；原终态12:19:16.879080 UTC、outer闭合12:19:59.602627 UTC，flight_exit0、infrastructure_stop=false、outer error=null。整批尚未结束，完整28格容量、定标、最终根和正式重复研究仍待执行。实时状态见[扩展批次页](results/project_progress/humble43_extension01/index.html)。

新增[物理身份恢复补充工具](tools/offline_evaluation/physical_recovery_v1/README.md)：20项微型合成测试通过，末次摘要修改后另有2项定向复验通过；独立只读审查代码SHA `f25327c03509aba6c0c5ec2d8358d65d1ca2e22da63e4a45076e23e99a52182c` 无阻塞。工具区分首次恢复、后来证实原个体及显式选择新个体，保留全部40槽/80机会与未知/缺报/删失，不改原评价。**真实补充协议和分析附件尚未生成**：须在真实FORMAL120生成且全部120槽未START时原生登记，最终由统一交付入口另行引用，不冒称原报告生成器自动消费。下方较早“当前”描述均为历史快照，按其时间阅读。

**2026-11-01 19:26:24（北京时间）快照：Humble43 同源核心12独审通过，原生v2组件04的85项及3项describe真实通过；安全4原四场全部PASS、完整原guard及闭合独审通过，安全批次主命令退出0，正式仍0/280。** 扩展16场已有10场开始、9个原始终态：7 PASS、2 FAIL，前九个外层attempt均已闭合；行人八场及汽车深度噪声已完成，第十场汽车深度空洞运行，另六场尚未开始；后续状态以本机进度页为准。扩展整批尚未闭合，容量、定标及正式研究仍待完成。

第九场`car_extension_depth_noise_seed004`于10:52:04.143306 UTC记录原COMPLETED/PASS，flight_exit0、infrastructure_stop=false；outer于10:52:36.053992 UTC闭合、error=null。距离/高度RMSE为0.723148/0.161357米。第十场`car_extension_depth_holes_seed004`原槽于10:56:05.664373 UTC START，outer于10:56:00.017823 UTC START；截至本快照尚无终态，不预记PASS。

新增[Modern Standby派生快照](tools/diagnostics/humble43_modern_standby_snapshot01/README.md)：506/507事件848770报告2715.306845秒实际睡眠，与第三槽2714.9889287秒UTC/monotonic间隙仅差0.3179163秒，强支持主机待机解释；后续848828另报告903.207217秒实际睡眠。旧42/107等限定查询无匹配的历史保留，Reason不识别操作者，不据此归责用户。新任务辅助进程PID10468的0x80000003请求已被API接受；这不证明永久排除睡眠或保证后续不中断。

第六场速度控制加减速原PASS；第七场位置控制加减速原FAIL，唯一未过的性能门为`final_distance_settled=false`，距离稳定时间仍为null并右删失；第八场远距离于10:27:25.595403 UTC原PASS，outer于10:27:56.265509 UTC闭合、error=null。三场均COMPLETED、flight_exit0、infrastructure_stop=false，不能把第七场距离RMSE达标解释为持续稳定。[前五场失败与原件快照](tools/experiment_orchestration/humble43_extension_partial05_snapshot01/README.md)保留4 PASS/1 FAIL；其中5原终态、11未开始是第六场START之前的历史时点，原字节保留。

第五场`person_extension_combined_seed004`于09:22:51.706659 UTC记录COMPLETED/FAIL，flight_exit0、infrastructure_stop=false；外层于09:23:21.491184 UTC闭合、error=null。目标在34.86秒已提前LOST，长遮挡请求43.4秒才开始，因此`long.prediction_observed=false`，不能把提前失锁当正常长遮挡触发。短遮挡通过，50.4秒显式重选后43.164秒持续跟踪通过；这些局部通过不抵消原FAIL。外层另保留导航性能门失败，完整原件和边界见[当前验证记录](planning/reliability-v4-humble43-validation-20261101.md)。后续[观测空窗诊断](tools/diagnostics/humble43_combined_gap_snapshot01/README.md)显示，冻结丢帧规则的三个连续200 ms窗口与超出预测预算的测量间隙吻合；仍缺逐帧交付账本，原FAIL保持。

首场[原槽终态](results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_depth_noise_seed004.json)于06:29:51.150954 UTC生成，[外层attempt](results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/01_person_extension_depth_noise_seed004.attempt_terminal.json)于06:31:00.198600 UTC闭合，flight_exit0、COMPLETED、infrastructure_stop=false、error=null。该压力样本原始录包4,148,883,456 B、压缩1,214,272,594 B，在线与research的RGB/Depth四流各933条，实际归档策略为`zstd -T4 -19 --long=27 --check`；不能代表完整28格容量或280次准入。

第三场dropout原槽已于08:33:48.425056 UTC记录PASS，外层于08:35:04.731320 UTC健康闭合，但其导航评价的UTC跨度2832.642921秒与原monotonic耗时117.6539923秒相差2714.9889287秒；新增506/507事件报告2715.306845秒实际睡眠，强支持待机解释；不能将整槽约69分钟UTC跨度解释为算法耗时。原UTC与计时证据均保留，旧限定Windows事件查询当时未能归因，后续506/507证据见上述派生摘要，详见[计时边界与原件](planning/reliability-v4-humble43-validation-20261101.md)。本批原8—10小时、整体5—6天均为条件估计；待完整28格后按实际活跃计时与UTC分别重算，不以首场约27分钟作承诺。

扩展的原plan、PENDING、独审、FINAL及发布来源仍见[13:46扩展16启动快照](tools/experiment_orchestration/humble43_extension16_start_snapshot01/README.md)，原字节保留；当前命令状态见本机[扩展进度页](results/project_progress/humble43_extension01/index.html)。104项是静态check，不是104次原生测试或飞行；全部原失败、未知及完整分母继续保留。

[核心独审收据](tools/experiment_orchestration/humble43_core12_closure_snapshot01/humble43_core12_closed_independent01.json)确认completed12、all_original_core_cells_pass=true；[原生04快照](tools/experiment_orchestration/humble43_native_v2_components04_snapshot01/README.md)保留85项全PASS、0跳过及3项canonical核验；[安全4闭合快照](tools/experiment_orchestration/humble43_safety4_closure_snapshot01/README.md)保留真实四场终态、facts与完整guard。安全原guard于05:12:36.708586—05:16:57.707220 UTC通过，monitor的owned-main于05:16:58.567204 UTC记录code0；原终态中的postwait owner为COMPLETE，不能与较早COPY候选pending混为一谈。本机[安全进度页](results/project_progress/humble43_safety01/index.html)保留命令级退出状态，核心旧页保留12原PASS；这些开发关口不等于整个项目验收。

汽车主动云台检测框中心RMSE为13.043403像素（718/750个机会），中位为81.548670像素（719/751）；主动模式距离/高度RMSE为0.739129/0.161260米，略高于中位的0.728828/0.157771米，不能称全指标更好。汽车交叉主身份网格753格中647正确、0已知错误、106未知；汽车多目标主动为754格中645正确、0已知错误、109未知，未知继续计入分母。行人单目标主动/中位的画面中心RMSE为17.00/57.71像素；这些均为同一开发种子的观察，仍待正式重复比较。全部12条导航报告保留删失窗口；容量、定标与最终验收尚未完成。1763项Linux检查中1758通过、5项平台跳过。原失败、删失窗口与身份未知保留，见[当前验证与后续准入](planning/reliability-v4-humble43-validation-20261101.md)、[身份未知解释](tools/diagnostics/humble43_identity_unknown_snapshot01/README.md)及[实时进度入口](docs/LIVE_PROGRESS.md)。

**当前分支是 v4 开发检查点，三阶段功能已实现，最终验收与正式重复研究尚未完成。** 本机当前批次和查看方法见[实时进度入口](docs/LIVE_PROGRESS.md)；旧 `results/project_progress/current/` 是历史Humble31任务，不能用于判断当前实验。来源和历史失败边界见[交接记录](planning/reliability-v4-current-state.md)，后续工作依[可靠性修复与交付方案](planning/reliability-v4-next-actions-20261030.md)推进。公开文档均为带时间的快照。

<details>
<summary>历史开发记录（不代表当前运行状态）</summary>

2026-10-31 最新：原Humble41核心12已闭合，11 PASS、1 FAIL；后续640/512生产后台worker各1008次时延测量已完成。选512/CPU4作为下一轮待验证配置，尚无新闭环通过结论。正式仍0/280。见[配置决定与验证顺序](planning/reliability-v4-humble42-resource-decision-20261031.md)。下方较早快照保留为历史。

2026-10-31 23:15（北京时间）快照：Humble41原核心12已完整关闭，11 PASS、1 FAIL；失败集中在汽车多目标主动云台的一次推理长尾。临时宽限候选已撤销，原时效和丢失门限保留。当前正在执行原始RGB、固定配置、后台worker的长序列推理诊断；尚无新闭环通过结论，正式仍0/280。详见[复核与撤销](planning/reliability-v4-humble41-grace-review-20261031.md)和上述实时入口。下列快照属于历史。

2026-10-31 17:13（北京时间）快照：Humble41已完成同源四包构建、来源隔离及1728项Linux检查（1723通过、5项平台跳过），正在串行运行完整75秒核心12场景开发验证。行人速度、位置控制两项完整评价均为PASS，第三项行人多目标交叉正在运行，余9项尚未尝试；整批runtime owner关闭结果尚待批次结束。该版本尚未完成安全4项、扩展16项、最终准入或正式280项实验。下列较早检查点保留为历史。

2026-10-31 05:34（北京时间）检查点：Humble37完成原生起飞及完整75秒汽车交叉跟随，编排、观察器、归档和清理正常；原工程FAIL保留。固定10Hz身份753格为644正确、0错误、109未知，覆盖85.52%；阶段二18项安全检查通过。导航距离RMSE1.583m超过原1.0m门，有效导航覆盖79.36%低于80%，因此继续修复连续几何拒绝，不进入正式批次。Linux1612项检查中1607通过、原5跳过。正式仍0/280；见[37完整结果与导航中断](planning/reliability-v4-humble37-results-20261031.md)。下列检查点为历史记录。

2026-10-31 04:40（北京时间）检查点：Humble36四包构建及1602项Linux检查通过（1597通过、原5项平台跳过）；RTF 0.125汽车开发槽因起飞前心跳连续性阻断未起飞，原INFRASTRUCTURE_ERROR/FAIL及中断保留，录制归档和清理已完成。正在准备显式adapter发送频率修订，未宣称跟随改善。旧35七帧逐像素复现14/7/0及独立审查完成，第三车解释未获支持。正式仍0/280；详见[本次结果与修复边界](planning/reliability-v4-humble36-results-20261031.md)。下列较早检查点均为历史记录。

2026-10-30 14:13 UTC检查点：汽车640/512固定权重质量回归520槽全部完成，两候选均通过逐图开发门。640实际20秒闭环的源时钟、原生启动完整记录、203/203导航覆盖及base_link距离/高度末端稳定均满足相应短测检查；完整job墙钟中位数约0.250秒。新协议显式绑定04+640+CPU4及真实收据，相关171项回归通过。下一步为新来源冻结/构建及完整75秒开发关口，尚不代表可靠性问题全部解决或正式准入；正式仍0/280。详见[完整证据与边界](planning/reliability-v4-car-scale-results-20261030.md)。下列较早检查点均为保留的历史记录。

最新检查点（创建于北京时间2026-10-30 10:28，非实时状态）：Humble28已完成两类20秒clean导航检查，行人完整75秒速度、位置两槽均为原始PASS；第3槽行人多目标交叉已开始，其余9槽尚未尝试。原批次的独立监控存在7200秒总时限，已在第2槽全部结束后行政停止，保留原中断回执；新外部编排只续行原计划尚未尝试的10槽，采用有重叠的监控轮换。实际ROS监控生命周期与3会话交叠检查通过，冻结566个来源文件及所有飞行/安全门保持不变。详见[批次监控修订](planning/reliability-v4-batch-observer-20261030.md)。正式仍0/280，完整28格容量未准入。

Humble28四包构建、模块/ament隔离、FastCDR来源及11项真实CDR消息往返通过；Linux全套1434项检查中1429通过、5项精确平台跳过，用时47.781秒。全部场景统一非实时RTF=0.25及600秒飞行wall预算，保持原0.60/0.75秒保护；此条件不能证明实机实时性能。

Humble27运行历史：行人20秒clean完成，导航PASS；原RTF=0.5的汽车clean失效，47/47相邻测量机会的下一处理时刻距上次采集为0.796–1.024源秒，超过原0.75秒预测保护，随后锁存LOST。入站观测未超过0.60秒；该时效包含图像转换、检测和深度/导航处理，不能当作纯YOLO推理耗时。

同一冻结27的独立汽车资源诊断仅将RTF改为0.25，实际完成20源秒跟随；导航距离/高度RMSE为0.74435/0.30698米，导航和真值覆盖均204/204，末段距离与高度均已稳定。源时钟、原生起飞、归档、观察器及清理检查通过；无设计遮挡的surface原结论仍为INCOMPLETE_EVIDENCE。这是单次非实时仿真诊断，不能代替75秒工程验收、正式重复或实机时延验证，原0.5失败保持。

原27核心12格仍全部PENDING，0.5与0.25记录分别保留。新28须继续完成同源clean、12核心、4安全、16扩展、定标与容量核算；单次诊断或测试通过不能代替最终验收。原26启动失败及更早结果见下方历史检查点。

Humble26检查点（2026-10-30）：Ubuntu 22.04/Humble26 已完成新来源冻结、四包构建、模块/ament 隔离、FastCDR 来源核验和真实消息序列化往返；Linux 全套1417项检查中1412通过、5项按精确平台条件跳过，用时49.068秒，检查前后冻结来源不变。首条20秒clean检查在pre-unpause桥进程身份发现时失败，8.79秒后退出1；普通`/proc`进程遍历触发`Proc identity is truncated or no longer alive`，尚未进入跟随验证，已清理且无残留。12格核心PROBE全部PENDING，须修复后新冻结再验证。起飞等待、输出时效、像素排除修复与[汽车m960检测候选](planning/reliability-v4-detector-m960-development-selection-20261030.md)尚无本轮飞行通过结论，[新无损归档](planning/reliability-v4-lossless-archive-20261030.md)的完整28格容量仍未准入。

Humble25原核心12格的9 PASS、3 FAIL保持不变：六个行人格均PASS，汽车起飞交接、交叉跟踪和多目标主动云台FAIL。正式试验仍为0/280。测试通过、程序执行完成和整次工程验收分别判断；下文 v3 报告与结果计数属于历史冻结版本。

核心 120 槽覆盖两类目标与六组工程条件；原计划距离、噪声、延迟、加减速等八个扩展条件另有 160 槽，共 280 槽，当前均未开始正式运行。范围和剩余工作见 [执行计划](planning/reliability-v4-remaining-execution.md)。

</details>

当前v4计划正文见[修订计划书](docs/FINAL_PLAN_V4.md)；本轮正式Word/PDF仍待实际研究资料齐备后生成。历史交付与复核入口：[结果工件说明](docs/RESULTS_ARTIFACTS.md) · [查看与复核方法](docs/验收使用指南.md) · [三阶段历史状态](docs/THREE_STAGE_STATUS.md) · [已归档计划书](docs/最终版毕业设计计划书_最终版.docx)。历史结果页面和报告保留失败、身份未知、缺失及未执行项；工程通过与正式重复研究完成分别判断。

This repository implements a simulation-first RGB-D UAV target following system with YOLO11, 3-D Kalman filtering and PX4 Offboard control. Estimation and control remain independent from ROS 2, PX4 and Gazebo so the same core can be tested, replayed and connected to a future vehicle adapter.

WSL EGL shutdown failures and the explicit Gazebo-only CPU rendering option are documented in the [shutdown diagnosis](docs/GAZEBO_WSL_SHUTDOWN_DIAGNOSIS.md). Historical `auto` driver selection is preserved; new Humble validation selects `--gazebo-render-driver llvmpipe` and checks the actual rendering libraries.

The supported target classes are `person` and `car`. The target manager exposes two modes:

- `AUTO_UNIQUE`: automatically lock a unique eligible target; multiple eligible detections produce an `ambiguous` state even when some tracks are not yet confirmed.
- `LOCKED_TARGET`: select a bounding box at task start and keep that physical target. Short occlusions coast with the 3-D filter; long loss becomes `lost` and requires re-selection.

The implementation includes a portable Python core, deterministic synthetic experiments and an integrated PX4/Gazebo flight graph with an onboard aligned RGB-D camera. Runtime tracking uses images, TF and vehicle state; Gazebo truth is reserved for offline evaluation.

## Quick start

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
python -m pytest  # optional; install the test extra if pytest is unavailable
python -m uav_tracking.simulation --mode auto_unique --target-class person --steps 120
python scripts/run_synthetic_experiments.py --target-class both --seeds 10
```

The first command installs the portable package and its test dependencies. The unittest
command is sufficient for a minimal environment; pytest is only a convenience
runner. ROS 2 execution is separate and should be performed in the WSL/Ubuntu
environment described in `docs/ROS2_SIMULATION.md`.

The real generated-message CDR test runs when ROS and the generated interfaces
are available. Portable CI skips it only for an explicitly missing prerequisite;
registered native validation still fails for missing or broken dependencies.
See [the CI/native environment boundary](docs/CI_NATIVE_CDR.md).

The portable GitHub Actions workflow runs these fixtures on Ubuntu 22.04 with
Python 3.10 and 3.12, including standard `zstd` archive checks. It does not
install ROS, start Gazebo/PX4, or certify a completed flight experiment. The
[v4 estimator comparison design](docs/V4_ESTIMATOR_COMPARISON_DESIGN.md)
documents the array replay, recording exporter and online numerical audit.
One car development recording passed export and numerical reproduction;
prospective calibration and the complete formal comparison remain pending.

The experiment command uses one deterministic noisy observation sequence per
seed for raw measurements, EMA, fixed-noise KF, and adaptive-noise KF, then
writes JSON records under the local, ignored `results/` directory. These are
estimator baselines; they do not replace the later rosbag/PX4 closed-loop
trials. See [the results artifact note](docs/RESULTS_ARTIFACTS.md) for the
public-clone boundary and the optional dashboard.

## PX4 / Gazebo flight

The current validation target is Ubuntu 22.04, ROS 2 Humble, Gazebo Harmonic
and PX4 v1.17.0. Isolated builds, bridges and partial development probes have
run; complete v4 flight acceptance remains pending. The earlier Ubuntu 24.04.1 /
ROS 2 Jazzy experiments belong to the historical v3 archive below.
Build and source the workspace as described in the
[simulation guide](docs/ROS2_SIMULATION.md) and
[version lock](docs/VERSION_LOCK.md), then run from the Linux project root:

```bash
bash scripts/run_stage1_trial.sh \
  --class person --name person_flight_trial_01 --duration 45 --occlusions
```

The runner owns Gazebo, PX4, the XRCE-DDS Agent, ROS nodes, recording and the
monitor. Each trial requires a new result name. Run one simulation at a time.
See the [flight guide](docs/STAGE1_FLIGHT.md) for the graph, manual component
commands, supervised takeoff, target motion and rendered occlusions. The
[acceptance record](docs/STAGE1_ACCEPTANCE.md) contains the current per-class
results, failed trials and remaining limits; synthetic and controlled smoke
tests are separate evidence.

The independent [v4 condition extensions](docs/V4_CONDITION_EXTENSIONS.md)
retain 160 slots in addition to the 120 core slots. Formal scheduling requires
prospective registration, actual development evidence and a bound clean core
reference plan. Both formal matrices are currently unexecuted.

The historical `stage1_final_v2` engineering record passed four scoped
person/car velocity/position demonstrations. The frozen v3 research archive
now records all 166 main flight slots: 107 PASS, 58 FAIL and 1 INTERRUPTED.
The separate 16-flight engineering extension records 2 PASS and 14 FAIL; two
of those stops are explicitly classified as infrastructure failures. The
post-flight supplement has 15 recorded slots and one incomplete-evidence slot.
These counts preserve negative results and are not an algorithm success rate.

The main offline ledger covers all 166 slots (160 recorded, 4 incomplete
evidence and 2 not applicable because no selected task existed). The local
archive also contains the metric supplement, figures, acceptance dashboard,
browser demos and the final report. Those large result artifacts are ignored by
Git and are described in [the results artifact note](docs/RESULTS_ARTIFACTS.md).
The published repository contains the source, tests and reproducible commands;
it does not claim that a public clone contains private bags or reports.

The historical v3 Linux validation used Ubuntu 24.04.1, ROS 2 Jazzy, Gazebo Harmonic
and PX4 v1.17.0. Independent v4 Ubuntu 22.04/Humble builds, bridge checks and
partial flight probes are recorded in the [Humble validation log](docs/HUMBLE_ISOLATED_VALIDATION.md);
they do not yet establish complete v4 acceptance. Two historical independent shutdown
probes passed in a new cleanup checkout: all 8 stage-one and 9 multi-target
stage-three ROS nodes exited cleanly, with no observed residual processes and
no changes to the formal research ledgers. See the [delivery status](docs/DELIVERY_STATUS.md)
for the final counts and artifact locations.

One historical car/position flight (seed08) failed evaluation with SQLite
error 11. An [independent audit](docs/V3_BAG_INFRASTRUCTURE_AUDIT.md) found an
unfinished zstd frame and a native ROS decompression output missing its final
128 KiB; an independent decoder produced an intact SQLite database. That
original FAIL remains unchanged and is an infrastructure/evidence failure,
not a measured tracking error. The audit did not establish why compression
failed to finish. All 34 stage-one v3 FAIL results must remain visible; their
causes cannot all be inferred from this one diagnosis.

Historical reports such as `person_flight_v06` used earlier acceptance rules;
their old PASS does not certify current fresh-image recovery. The historical
final person/car by velocity/position matrix uses correlated shutter service
responses and bag-confirmed explicit reselection. Models, sources,
licenses and visible-surface measurement semantics are documented in
[visual assets](docs/VISUAL_ASSETS.md).

## Design boundaries

The current code supports a selectable velocity or position setpoint, but only one setpoint mode is active per controller instance. The three-axis gimbal model treats yaw and pitch as line-of-sight control and roll as horizon stabilization. Long-term appearance ReID, obstacle avoidance, and real-flight validation remain separate extensions.

The portable core's `LOCKED_TARGET` mode requires a user or test script to
select the initial bounding box. It disables automatic target replacement
during loss; physical identity still requires independent evaluation of data
association, including unobservable intervals. Stable re-identification after a
track is removed is intentionally outside the MVP. The deterministic demo is
not a ROS/PX4/Gazebo validation result.
