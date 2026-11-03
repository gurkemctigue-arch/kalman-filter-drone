# 查看当前实验

**2026-11-03 10:31（北京时间）实际检查点：新 normal CLI 正在原计划中单独执行下一个 PENDING 通信延迟槽，4 START、3 个原终态（2 PASS、1 INCOMPLETE_EVIDENCE）、12 个未尝试槽；正式仍 0/280。** 本次使用 `--max-new-trials 1`，实际 START 为 10:25:24.728624，第三场 dropout 不重试、缺证未解决。请打开新的[监督进度页](../results/project_progress/humble54_extension_supervised02/index.html)；其事件来自旧 owner 历史观测的拷贝及实际新 START marker，仅为派生观察，不是新 owner、准入或通过结论。

旧 owner 仍 `STOPPED_FAULT`，旧等待器已 `STOPPED_REFUSED_NO_RETRY`、`followon_launched=false` 且句柄关闭，不再等待自动续接。新槽结束须先核原终态和安全证据，再决定下一 PENDING 槽；后续容量/导出/定标须另用新 CLI，当前未启动。当前进程身份、session 与临时防休眠 receipt05 见[执行记录](../planning/reliability-v4-execution-20261103.md)。以下 09:44 及更早块中的“当前/等待”均保留为历史描述。

**2026-11-03 09:44（北京时间）检查点：Humble54 扩展 16 正在运行，2 场 START、1 场原始 PASS、14 场未开始；正式研究仍为 0/280。** 09:44:07 的进度 JSON 为 `RUNNING`，命令与监控器的创建身份和新鲜心跳核验通过；当前槽为 `person_extension_depth_holes_seed004`。首场深度噪声于 09:38:26 记录原始工程 PASS，距离/高度 RMSE 为 0.757915/0.161986 m，两项末端持续稳定通过；navigation 原报告的 `RECORDED_WITH_CENSORED_FAILURES` 保留。核心 12/12 与独立安全 03 的四场原始工程 PASS 均已闭合；扩展整批尚未结束。

实际启动的后续等待器在 09:44:04 仍为 `WAITING_FOR_EXTENSION`，`followon_launched=false`。它先等待原扩展进程退出并核验闭合，再有条件执行八步后续工作；当前未启动后续原生工作、未创建正式准入或正式飞行。其原始启动与等待快照见[准备归档](../tools/experiment_orchestration/humble54_closed_followon01/manifest.json)，具体步骤见[执行记录](../planning/reliability-v4-execution-20261103.md)。

安全 02 原终态保持 `STOPPED_FAULT`、08:08:49 命令退出 2：首场原始 `INFRASTRUCTURE_ERROR`、其余 3 场未执行，无自动重试。其 `KeyError: 'result'` 已复现；修复保持 source/native 通过原公共 reader 严格解释 `evaluation_status`，专属及末端报告严格使用 `result`。08:17:42 完成的实际原生合同与只读诊断，及另行 5 项 Humble 单元测试（2.692 秒、全部通过、无跳过），都不构成旧槽重新验收或新飞行通过。安全 03 使用新 registry、新 driver 及 contract03 独立登记执行。

安全 01 历史批次仍为 07:42:37 `STOPPED_FAULT`、命令退出 2：首场基础设施错误、其余 3 场未执行。原命令目录绑定错误、两项路径修复小测及随后安全 02 的独立失败分别保留，不拼接为安全通过。

已有行人速度开发录包的时序导出与两项分析已实际完成，三条命令均退出 0，用时分别为 28.739、7.346、9.137 秒。48,104 条规范化事件＝47,177 条选定 bag 话题消息＋927 条 job 记录，不是原生录包总消息数。10 Hz 是来源时钟速率；检测处理前缀墙钟中位数 25.984 ms，采集至预发布来源时钟中位数 80.000 ms。真实端到端时延和工作线程墙钟 FPS 仍为 `NOT_OBSERVED`。严格 lineage 保留 1,857 条原命令＝0 已知、1,857 未知；1,377 条有候选的命令中 1,374 条为多候选、另 3 条虽单候选仍因诊断索引约束未知，没有放宽原方法或改计为零延迟。

已有身份报告的每任务提取现已完成：四个多目标场景首次请求的已知覆盖率为 0.621–0.680，显式重选后为 0.961–0.998。首次分母包括计划短/长遮挡和等待重选区间，不能当作纯可见画面的识别准确率；原报告理由也不证明所有未知的因果来源。没有应用每 UUID 验收阈值，未知不改为正确。汽车多目标主动云台完整 753 格仍为 614 正确、0 已知错误、139 未知，诊断 714 帧（619/0/95）单独保留。

- [扩展 16 实时进度](../results/project_progress/humble54_extension16_run01/index.html)、[首场原件](../tools/experiment_orchestration/humble54_extension_first01/README.md)及[本轮执行记录](../planning/reliability-v4-execution-20261103.md)：当前唯一仿真批次；09:44 检查点为 2 START、1 原始 PASS、14 未开始，不预记未终态场景。
- [安全 03 原件与闭合核验](../tools/experiment_orchestration/humble54_safety4_closed03/README.md)、[命令终态页](../results/project_progress/humble54_safety4_run03/index.html)及[最终摘要](../results/project_progress/humble54_safety4_run03/end_summary.json)：4 场原始 PASS，开发 guard 通过，Linux owner 与 Windows 命令均闭合；不代表正式研究完成。
- [schema03 原生合同、诊断、5 项单测及前瞻 registry 原件](../tools/diagnostics/safety54_schema_recovery03_archive01/README.md)：工具修复与新飞行验收分开，旧失败不改写。
- [安全 02 命令终态](../results/project_progress/humble54_safety4_run02/index.html)与[最终摘要](../results/project_progress/humble54_safety4_run02/end_summary.json)：历史批次已停止，1 场原始基础设施错误、3 场未执行。
- [安全 02 原始执行终态](../results/frozen_fullplan_v4_humble54/reliability_v4_humble54_safety02_audit/execution_terminal.json)及[owner 终态](../results/frozen_fullplan_v4_humble54/reliability_v4_humble54_safety02_audit/owner_terminal.json)：退出 2，无自动重试，原终态记录清理残留列表为空。
- [安全路径修复与真实 Humble 两项小测](../tools/diagnostics/safety54_symlink_recovery02/README.md)及[安全 01 命令终态](../results/project_progress/humble54_safety4_run01/index.html)：新修复不覆盖旧失败，工具测试不计为飞行通过。
- [开发录包时序原件与严格 lineage 的派生摘要](../tools/diagnostics/humble54_dev_timing01/README.md)：完整小报告、来源哈希与三条原命令样例；未知和时间域边界保留。
- [核心 12 场原件与闭合边界](../tools/experiment_orchestration/humble54_core12_closed01/README.md)及[核心命令终态](../results/project_progress/humble54_core12_run01/index.html)：核心开发通过保持，不能代替安全 4、扩展 16 或正式重复验收。
- [每个请求任务的身份计数、遮挡请求范围与未知理由](../tools/diagnostics/humble54_identity_per_uuid_audit01/README.md)：四份已有报告的描述性提取，不是重新评价或新增飞行。
- [汽车云台原件与同种子比较](../tools/experiment_orchestration/humble54_car_gimbal_pair01/README_PAIR.md)及[当前环境与原生验证](../planning/reliability-v4-humble54-native-validation-20261103.md)：画面居中改善不等于物理跟随改善，工具验证不计为飞行通过。

核心 12 和安全 4 是同一个开发种子的独立工程结果，现均已闭合；扩展 16、定标、容量、最终冷构建与正式协议准入、重复研究仍须独立完成。安全 01、02 及更早运行快照均为历史记录，不能用于判断当前状态。

实时页面、录包及录像位于本机，GitHub 保存代码和小证据快照。批处理可以独立运行，网页不会主动向聊天发送完成消息。PASS/FAIL 以每个原始终态为准；命令退出或报告文件生成不等于整个项目验收完成。

<details>
<summary>此前运行记录与入口（按各自时间阅读）</summary>

**2026-11-02 20:10（北京时间）修复进展：时钟桥与数据桥分离候选已通过生产 RGB-D 组件检查，新增 54 项测试通过。** 20 秒仿真时间取得 202 组同步 RGB-D，时钟最大接收间隔约 33.7 ms，三进程正常退出。Windows 完整回归发现的旧夹具模式错误已修正，受影响两模块回归通过；新冷构建和 75 秒飞行复验待完成。原 Humble51 仍为 **3 PASS / 1 FAIL / 8 PENDING**，正式 **0/280**，项目尚未全部验收。详见[候选与真实证据](../planning/reliability-v4-clock-isolation-20261102.md)。

**2026-11-02 19:10:29（北京时间）监控终态：Humble51原核心命令已退出2、STOPPED_FAULT；原始结果3 PASS、1 FAIL、8 PENDING，正式0/280。** 第四场行人云台中位的source-clock/native-startup未通过独立硬门，当前不能把下方18:58的“运行中”当作实时状态。4次未来源时刻拒绝、1次诊断交付越界和2条raw/timing缺配对，以及1次phase时间越界均保留；起飞、模式序列和handoff检查通过。84.028秒附近的聚集只是诊断线索，共同根因仍待原包核实。查看[停止说明与后续诊断](../planning/reliability-v4-humble51-clock-stop-20261102.md)、[最小原件](../tools/diagnostics/humble51_clock_stop01/README.md)和本机[命令终态](../results/project_progress/humble51_core_run01/index.html)。后续新的只读诊断不等于该原核心批次仍在飞行，下方历史快照原样保留。

**当前入口：Humble51。2026-11-02 18:58:44（北京时间）快照为3/12个原始工程PASS、3个对应外层核验闭合；第四场行人云台中位运行，另8场未开始，正式0/280。** 四包冷构建36.4秒；完整Linux套件1870项为1865通过、5项已说明原因的平台跳过。当前页面应核对最新观测时间与进程身份：

- [Humble51核心场景、原始终态与录像](../results/project_progress/humble51_core_slots01/index.html)：每15秒只读观察本机小文件。
- [Humble51命令进程、身份与心跳](../results/project_progress/humble51_core_run01/index.html)：检查运行进程是否仍为原始命令，以及外层退出结果。
- [本轮验证记录与后续步骤](../planning/reliability-v4-humble51-validation-20261102.md)和[前三场原件快照](../tools/experiment_orchestration/humble51_core_first3_snapshot01/README.md)：区分工程通过、完整身份分母与尚未完成的工作。

这些实时页、录包和录像位于本机，GitHub只保存源码与最小证据快照。实验程序可以独立运行，页面不会主动向聊天发消息。行人交叉753个完整身份时间格中648正确、0已知错误、105未知；第一任务单独覆盖仅67.70%，未知继续保留。原Humble50的11 PASS/1 FAIL属于历史批次，不与51混计。下方文字与入口原样保留为历史快照。

**最新入口：Humble50。2026-11-02 12:46（北京时间）快照为3/12个原始PASS、3个外层核验闭合，核心批次仍在执行，正式0/280。** 本轮已完成行人速度跟随、位置跟随和多目标交叉，四包冷构建及完整Linux测试已通过。以页面的最新观测时间为准：

- [当前核心场景、原始终态与录像](../results/project_progress/humble50_core_slots01/index.html)：每15秒观察原始小文件；RUNNING标记本身不证明进程存活。
- [当前命令进程与心跳](../results/project_progress/humble50_core_run01/index.html)：核对进程身份、心跳和命令退出结果。
- [本轮验证记录、物理误差和身份分母](../planning/reliability-v4-humble50-validation-20261102.md)：明确哪些已完成，哪些仍待验证。

这些页面和录像存在于本机。实验程序能够独立运行；网页不会自动唤醒聊天或向聊天发送完成消息。下方Humble47及更早入口为历史记录。

**2026-11-02：旧协议兼容断言已修复，完整Windows套件1789项、11项平台跳过、无失败；正在冻结新的Humble47来源。** 原46的冷构建通过与完整Linux测试失败保留，尚未47原生验证或飞行，正式0/280。见[验证记录与后续修复](../planning/reliability-v4-humble46-validation-20261102.md)。

**2026-11-02（北京时间）：Humble45核心批次停止后，已完成时序取证和时钟修复候选；145项相关测试及22项补充复验通过，最终独审通过。** 原结果1 PASS、1基础设施错误、10未开始保持，正式仍0/280；接下来准备新Humble46隔离构建、完整原生测试和新核心批次。见[故障、修复与后续工作](../planning/reliability-v4-humble45-position-abort-20261102.md)。

可观看本轮[汽车远距离单场录像](../results/frozen_fullplan_v4_humble45/reliability_v4_humble45_recording_probe02_car_extension_far_distance_seed004/onboard.mp4)，或打开[核心12实时进度页](../results/project_progress/humble44_recording01/index.html)。页面每15秒观察一次本地原始小文件，浏览器刷新后显示最新内容；页面不会向聊天主动发送消息。录像及实时页仅在本机存在，GitHub保存源码和最小证据快照。

**2026-11-01 23:17（北京时间）：44冷构建通过、完整测试3项夹具ERROR；修补后13项原生定向测试全部通过，正准备45重新验证，未开始飞行。** 正式仍0/280。本机[本轮进度页](../results/project_progress/humble44_recording01/index.html)会在步骤经核实后更新；[44失败原件](../tools/diagnostics/humble44_validation_failure01/README.md)与此前43失败均保留。

**2026-11-01 22:39（北京时间）：约2.7秒处录制证据异常已定位；正在准备Humble44录包队列候选与原生验证，尚未新飞行。** 原43批次继续为STOPPED_FAULT，正式0/280。4项新测试和36项相关Windows回归通过，不等于原生飞行修复已验收。见[诊断原件](../tools/diagnostics/humble43_clock_boundary_snapshot01/README.md)与[后续路线](../planning/reliability-v4-humble44-recording-repair.md)。

**2026-11-01 22:02（北京时间）批次终态：Humble43扩展16已停止，原始槽为12 PASS、4 FAIL，原生driver退出2；完整外层审计计数15，最后汽车远距离的source-clock及native-startup未通过硬门。** 核心12和安全4的既有通过记录保留，正式仍0/280。该最后失败不能当作允许的压力算法FAIL，容量collector/定标/正式发布前置未满足；当前继续离线取证，尚未选择修复。详见[停止与诊断记录](../planning/reliability-v4-humble43-extension-stop-20261101.md)及[原件快照](../tools/diagnostics/humble43_extension_stop_snapshot01/README.md)，本机[进度页](../results/project_progress/humble43_extension01/index.html)为STOPPED_FAULT。下方运行中描述均为有时间标记的历史。

**2026-11-01 20:31:33（北京时间）快照：Humble43核心12、安全4已完整闭合并独审通过；扩展16为13 START、12原终态（10 PASS/2 FAIL），前12个outer均闭合，汽车combined运行，另3格未开始；正式仍0/280。** 第12场汽车延迟原PASS，距离/高度RMSE为0.761595/0.168965米、末端稳定通过；原终态12:19:16.879080 UTC、outer闭合12:19:59.602627 UTC，flight_exit0、infrastructure_stop=false、outer error=null。整批尚未结束，完整28格容量、定标、最终根和正式重复研究仍待执行。实时状态见[扩展批次页](../results/project_progress/humble43_extension01/index.html)。

新增[物理身份恢复补充工具](../tools/offline_evaluation/physical_recovery_v1/README.md)：20项微型合成测试通过，末次摘要修改后另有2项定向复验通过；独立只读审查代码SHA `f25327c03509aba6c0c5ec2d8358d65d1ca2e22da63e4a45076e23e99a52182c` 无阻塞。工具区分首次恢复、后来证实原个体及显式选择新个体，保留全部40槽/80机会与未知/缺报/删失，不改原评价。**真实补充协议和分析附件尚未生成**：须在真实FORMAL120生成且全部120槽未START时原生登记，最终由统一交付入口另行引用，不冒称原报告生成器自动消费。下方较早“当前”描述均为历史快照，按其时间阅读。

**2026-11-01 19:26:24（北京时间）快照：Humble43同源核心12独审通过，原生v2组件04的85项及3项describe真实通过；安全4原四场全部PASS、完整原guard及闭合独审通过，安全批次主命令退出0，正式仍0/280。** 扩展16场已有10场开始、9个原始终态：7 PASS、2 FAIL，前九个外层attempt均已闭合；行人八场及汽车深度噪声已完成，第十场汽车深度空洞运行，另六场尚未开始；后续状态以本机进度页为准，整批尚未闭合。

第九场`car_extension_depth_noise_seed004`于10:52:04.143306 UTC记录原COMPLETED/PASS，flight_exit0、infrastructure_stop=false；outer于10:52:36.053992 UTC闭合、error=null。距离/高度RMSE为0.723148/0.161357米。第十场`car_extension_depth_holes_seed004`原槽于10:56:05.664373 UTC START，outer于10:56:00.017823 UTC START；截至本快照尚无终态，不预记PASS。

新增[Modern Standby派生快照](../tools/diagnostics/humble43_modern_standby_snapshot01/README.md)：506/507事件848770报告2715.306845秒实际睡眠，与第三槽2714.9889287秒UTC/monotonic间隙仅差0.3179163秒，强支持主机待机解释；后续848828另报告903.207217秒实际睡眠。旧42/107等限定查询无匹配的历史保留，Reason不识别操作者，不据此归责用户。新任务辅助进程PID10468的0x80000003请求已被API接受；这不证明永久排除睡眠或保证后续不中断。

第六场速度控制加减速原PASS；第七场位置控制加减速原FAIL，唯一未过的性能门为`final_distance_settled=false`，距离稳定时间仍为null并右删失；第八场远距离于10:27:25.595403 UTC原PASS，outer于10:27:56.265509 UTC闭合、error=null。三场均COMPLETED、flight_exit0、infrastructure_stop=false，不能把第七场距离RMSE达标解释为持续稳定。[前五场失败与原件快照](../tools/experiment_orchestration/humble43_extension_partial05_snapshot01/README.md)保留4 PASS/1 FAIL；其中5原终态、11未开始是第六场START之前的历史时点，原字节保留。

第五场[combined原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_combined_seed004.json)于09:22:51.706659 UTC记录COMPLETED/FAIL、flight_exit0、infrastructure_stop=false；[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/05_person_extension_combined_seed004.attempt_terminal.json)于09:23:21.491184 UTC闭合、error=null。surface_flight的`long.prediction_observed=false`：34.86秒已提前LOST，长遮挡请求43.4秒才开始，不能说是正常长遮挡导致失锁。短遮挡PASS、50.4秒显式重选后的43.164秒持续跟踪PASS均保留，但不抵消原FAIL；外层还登记导航性能门失败，详见[验证记录](../planning/reliability-v4-humble43-validation-20261101.md)。

当前请打开本机[Humble43扩展批次进度页](../results/project_progress/humble43_extension01/index.html)。首场[原槽终态](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_depth_noise_seed004.json)于06:29:51.150954 UTC生成，[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/01_person_extension_depth_noise_seed004.attempt_terminal.json)于06:31:00.198600 UTC闭合：flight_exit0、COMPLETED、infrastructure_stop=false、error=null，started_this_invocation=1且原audit存在。原规划、PENDING、独审及FINAL发布依据仍见[13:46扩展16启动快照](../tools/experiment_orchestration/humble43_extension16_start_snapshot01/README.md)，原字节保留。命令心跳不能替代真实终态，104项静态check不计作新增原生测试或实验PASS。核心及安全原件仍见[核心独审收据](../tools/experiment_orchestration/humble43_core12_closure_snapshot01/humble43_core12_closed_independent01.json)及[安全4闭合快照](../tools/experiment_orchestration/humble43_safety4_closure_snapshot01/README.md)。

该首场深度噪声压力样本的原始录包为4,148,883,456 B、压缩为1,214,272,594 B，在线与research的RGB/Depth四流各933条；[原归档报告](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_person_extension_depth_noise_seed004/bag_integrity.json)记录实际`zstd -T4 -19 --long=27 --check`策略。单场不能代替完整28格容量测量，也不授予正式准入。

第三场[dropout原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_dropout_seed004.json)于08:33:48.425056 UTC记录PASS、flight_exit0、infrastructure_stop=false，其[外层attempt](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/observed_driver01/03_person_extension_dropout_seed004.attempt_terminal.json)于08:35:04.731320 UTC闭合、error=null。第四场latency的[原槽](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_extensions_probe01_seed004_matrix/slots/person_extension_latency_seed004.json)已于08:57:53.783337 UTC记录PASS、flight_exit0、infrastructure_stop=false；此前16:40:02快照中的latency START状态现为历史。

第三槽从07:25:06.748207至08:33:48.425056 UTC共4121.676849秒；其中导航评价UTC跨度2832.642921秒，原monotonic耗时仅117.6539923秒，差2714.9889287秒。其余四命令两种计时仅微秒差。08:40:36 UTC的有限Windows System事件查询无匹配，两owned进程仍alive、lease未到期；这些旧结果当时不足以归因。后续506/507记录实际Modern Standby，强支持待机解释，仍不能识别操作者、归责用户或将约69分钟都记作算法耗时。完整UTC与monotonic均保留，详见[工程时钟边界](../planning/reliability-v4-humble43-validation-20261101.md)。本批原8—10小时、整体5—6天仅为条件估计，完整28格后按实际活跃计时与UTC分别重算，不套首场约27分钟作承诺。

本机[Humble43安全批次进度页](../results/project_progress/humble43_safety01/index.html)提供命令级心跳和真实退出状态，尚不显示四场的槽位计数。原完整guard于05:12:36.708586—05:16:57.707220 UTC通过，monitor的owned-main于05:16:58.567204 UTC记录code0；四场原PASS见上述闭合快照或本机`results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_safety_seed004_audit/`原始小JSON。闭合依据为postwait owner COMPLETE及原guard，较早COPY_VERIFIED_PENDING_OWNER_CLOSURE候选不代表最终owner仍未收尾。原[核心进度页](../results/project_progress/humble43_core01/index.html)保留12个原始PASS；旧Humble42、41及`current/`页面均为历史记录。

已完成场景的[行人速度跟随录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage1_velocity_seed004/onboard.mp4)和[行人位置跟随录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage1_position_seed004/onboard.mp4)可以直接观看。完整原始记录位于`results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_seed004_matrix/slots/`。全部12条导航报告仍为`RECORDED_WITH_CENSORED_FAILURES`；各场完整任务机体参考末端距离/高度稳定检查均为true，但必须保留模型原点参考等窗口的未稳定结果，不能把工程PASS改述为所有分析窗口通过。

还可观看[行人多目标交叉](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage2_crossing_seed004/onboard.mp4)、[云台中位](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage3_midpoint_seed004/onboard.mp4)、[主动云台](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage3_active_seed004/onboard.mp4)及[多目标主动云台](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage3_multi_active_seed004/onboard.mp4)。单目标中位/主动的画面中心RMSE为57.705711/17.004366像素，两者均有717/751个可观测机会；各场物理距离、高度和末端机体参考稳定检查通过。它们是一个开发种子的结果，不代表正式效果结论。

行人两条多目标场景的主身份分母分别为753格：交叉649正确、0已知错误、104未知；多目标主动648正确、0已知错误、105未知。未知继续计入分母。交叉场景104格的证据分解和边界见[独立核查小收据](../tools/diagnostics/humble43_identity_unknown_snapshot01/README.md)，不能把未知当作正确，也不能把粗原因直接解释成YOLO或通信故障。

汽车[速度跟随录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage1_velocity_seed004/onboard.mp4)和[位置跟随录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage1_position_seed004/onboard.mp4)已生成。完整任务的距离/高度RMSE分别为0.750666/0.162098米和0.703718/0.167942米；两场机体参考末端距离、高度稳定均通过。导航报告仍含删失窗口，单个开发种子的通过不能代替汽车全部场景或正式重复可靠性结论。

汽车[多目标交叉录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage2_crossing_seed004/onboard.mp4)已生成，完整任务距离/高度RMSE为0.852427/0.152493米，末端机体参考稳定及18项阶段二检查通过。独立主身份网格753格中647正确、0已知错误、106未知，保守正确覆盖85.923%；两个显式请求任务均独立映射到同一物理汽车。该场既保留未知身份，也保留导航删失窗口；不能将工程PASS解释为全时刻身份确定或所有窗口通过。

汽车[云台中位录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage3_midpoint_seed004/onboard.mp4)已生成。完整任务距离/高度RMSE为0.728828/0.157771米，机体参考末端稳定检查通过；751个检测机会中719个提供有效中心观测，其框中心RMSE为81.548670像素。

汽车[主动云台录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage3_active_seed004/onboard.mp4)对应原槽于03:22:48 UTC完成PASS，13项云台检查通过。距离/高度RMSE为0.739129/0.161260米，导航覆盖0.916223404、真值覆盖1.0；框中心RMSE为13.043403像素（718/750个机会）。本开发种子的中心误差较中位低，距离和高度误差略高，不能据此称主动模式全指标更好或已经证明总体可靠性提升。

汽车[多目标主动云台录像](../results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage3_multi_active_seed004/onboard.mp4)对应原槽于03:52:20 UTC完成PASS，13项云台检查通过。距离/高度RMSE为0.841079/0.174023米，导航覆盖0.898936170、真值覆盖1.0；框中心RMSE为5.554585像素（674/751个机会）。主身份754格中645正确、0已知错误、109未知：首次任务322格中215正确、107未知；重选后432格中430正确、2未知。该主汇总最初通过原报告1 MiB有界前缀读取，原整批记录与报告绑定现已由既有独审通过；未知仍保留，不能当作全时刻身份已知。

Humble43已完成四包隔离构建、来源检查和真实消息序列化检查；1763项Linux检查中1758通过、原5项平台跳过。另一个具名单场汽车交叉诊断已通过，但完整身份网格754格仍有110格未知，保守正确覆盖为644/754；该诊断不能拼入核心12或正式280。详情见[本轮证据与准入顺序](../planning/reliability-v4-humble43-validation-20261101.md)。

原生v2组件04已实际退出0：30+40+15共85项全PASS、0跳过，9项真实authority完整执行，3项describe的canonical全部匹配，原终态finally核验1940个原文件。[新最小快照](../tools/experiment_orchestration/humble43_native_v2_components04_snapshot01/README.md)保存原终态、suite结果/日志、describe和peer核查。Windows78通过/7跳过、原Humble02的76通过/9锁争用ERROR均保留；组件03是tests_run=false的测试前调度拒绝，未运行85项，不计作测试失败或通过。

安全4已真实完成4 PASS、完整原guard PASS、闭合独审PASS与主命令code0。扩展原plan闭合和104项静态独审已通过，PENDING保持原样，root仅改变status另产独立FINAL runtime合同；原16场run当前10场开始、9终态（7 PASS/2 FAIL）、第十场汽车深度空洞运行、其余6场未开始，全部原结果保留，整批owner仍待最后收尾。之后依次完成其余实际扩展、28格容量实测、两条预定录制导出与R0定标、独立最终来源构建/登记/封存、正式120+160和统计交付。v2定标/发布工具按原协议保留可评价压力场景的算法FAIL；原安全失效或缺证仍不能据此放行，开发关口通过不构成正式准入。

核心12独审、原生04组件补验与安全4开发关口已通过；后续还有扩展、容量/定标、最终准入及280次正式飞行，整个剩余工作维持5—6天量级估计，发生新故障时按实测修订。此处是带时间的快照，最新状态以实际原件和实时页为准。进度页、视频和完整原始结果仅在本机存在；GitHub保存源码和最小证据说明，网页不会自行向聊天发送完成通知。

<details>
<summary>Humble42及更早历史快照（不能用于判断当前进程）</summary>

**2026-11-01修复快照：自动新生支持门控和逐信号退出观测已进入候选源码，通过小范围行为测试及独立审查，尚未新冻结/飞行。** 原生记录确认30.7秒未支持观测初始化track4，后续成为歧义竞争者；物理重复身份仍未证实。下一步新隔离版本重做汽车交叉，再决定完整核心12，见[修复计划](../planning/reliability-v4-humble43-repair.md)。原结果与正式0/280不变。

**2026-11-01 04:57（北京时间）诊断快照：原生录包因果窗口提取完成。** 一次完整读取204,788条消息，原件前后校验未变；五个精确时刻的RGB/Depth/CameraInfo全部导出，临时缓存已清理。正在分析31.5秒起的关联歧义，尚无新修复飞行或正式实验。见[提取工具与真实回执](../tools/diagnostics/humble42_native_causal_snapshot01/README.md)。原8/1/3与正式0/280不变。

**2026-11-01 04:47（北京时间）诊断快照：一次真实RGB-D最小退出流程通过。** 原汽车交叉世界在暂停启动、实际出帧、暂停排空后，仅收到SIGINT，Gazebo约0.117秒后正常退出，全部自有进程退出0且无残留。此探针没有PX4、ROS桥接、检测器和完整飞行，原汽车交叉故障仍未解决。正在准备原录包因果窗口提取；完整证据边界见[诊断归档](../tools/diagnostics/humble42_shutdown_snapshot01/README.md)。原批次8/1/3与正式0/280保持。

**2026-11-01更新：Humble42原核心批次已结束并停止，8 PASS、1 FAIL、3 PENDING，主命令退出2。当前没有飞行仿真运行，正在诊断。** 第9项汽车交叉提前失锁，且Gazebo退出-9、owner闭合未通过；后三个汽车云台槽没有执行，正式仍0/280。完整误差、身份分母、退出边界及后续步骤见[本批结果](../planning/reliability-v4-humble42-results-20261101.md)。下面03:08及更早的运行中描述均为历史快照。

原[命令监控页](../results/project_progress/humble42_core01/index.html)现在为STOPPED_FAULT；原[槽位页](../results/project_progress/humble42_core_slots01/index.html)记录9个原槽终态。它们不代表新的诊断任务正在运行。原42不会通过重写终态或补跑同名槽继续准入；先定位关联与退出故障，再决定修复和新同源验证。

**2026-11-01 03:08（北京时间）快照：Humble42 核心12已有6项原始PASS，行人六场景全部通过，接下来为汽车六场景，正式仍为0/280。** 本批汽车结果尚未产生，不能据行人结果宣称汽车可靠性已解决。新版本已完成独立四包冷构建、模块/ament隔离和消息序列化检查；1748项Linux测试中1743通过、5项平台跳过。汽车采用04微调YOLO11m、512输入和CPU4线程，行人维持320输入和CPU2线程；请求仿真速度0.125倍，0.60秒观测时效及0.75秒预测期限保持原值。整批观察器收尾及后续安全/扩展仍待实际完成。

当前请打开[Humble42实时槽位进度页](../results/project_progress/humble42_core_slots01/index.html)，它只读取原始开始/终态记录；批命令心跳和真实退出码另见[原命令监控页](../results/project_progress/humble42_core01/index.html)。原始计划位于 `results/frozen_fullplan_v4_humble42/reliability_v4_humble42_probe01_seed004_matrix/plan.json`，槽位开始/终态在其 `slots/` 目录；原41进度页已是历史。新12场按行人、汽车顺序各运行速度、位置、交叉、中位、主动云台、多目标主动云台，均重新执行，不继承旧PASS。预计核心批次约4–5小时，以实际终态和观察器关闭结果为准。

后续依次为安全4、扩展16、28条实际容量测量、两条指定开发录制导出和R0定标、独立最终根冷构建/登记/封存、280次正式实验及统计交付。所有准入都依赖前一步真实证据。原`observed_driver01/`前六条完整attempt（含来源检查及owner收尾）耗时20.19–30.26分钟，平均24.02分钟；线性外推280次本身约112小时，汽车/扩展尚未实测，另计前置开发和分析交付。因此剩余按5–6天量级估算，遇新故障继续修订，不承诺固定完成时刻。此前93小时是原41五个行人样本的历史外推。

本轮行人中位/主动云台画面中心RMSE为57.358889/17.539419像素，均观测716/750个机会，两项物理距离/高度及末端稳定均通过。多目标主动云台的物理距离/高度RMSE为0.811182/0.151243m，导航覆盖0.890957、真值覆盖1.0；完整10Hz身份网格754格中649正确、0已知错误、105未知，已知覆盖0.860743。它们只支持当前开发seed004的结论，不能把未知算成正确或替代正式重复。

新补充检测与时延工具均已完成源码/合成测试独审并同步GitHub，实际提取/推理/审核仍待独占窗口。补充检测前瞻选源及首正式飞行前必须创建实际协议的步骤见[补充执行卡](../planning/reliability-v4-supplementary-evaluation-execution.md)。以下较早记录均为历史快照。

**最新：2026-10-31，后台时延测量已结束。** 两组固定配置各1008次、未知0，命令实际退出码0；[进度页](../results/project_progress/inference_tail_worker01/index.html)现为已完成记录。512中位/p99时延较低，最大值略高。已选512/CPU4作为下一轮待验证资源，正在完成新来源冻结和构建工具适配；尚未启动新闭环批次。见[资源决定与真实证据](../planning/reliability-v4-humble42-resource-decision-20261031.md)。正式仍0/280。以下较早快照保留为历史。

**最新：2026-10-31 22:53（北京时间）。** Humble41 原核心12已完整关闭，结果为 **11 PASS、1 FAIL**；失败项是汽车多目标主动云台。新正式实验仍为0/280，安全4与扩展16尚未执行。目标在短遮挡前已因一次YOLO调用耗时7.55墙钟秒而过期。当前正在以12张精确采集时戳的原始RGB诊断推理尾延迟；尚未选定新配置或启动新核心批次。临时推理宽限候选经独审不通过，已撤销，103项定向回归通过；原0.60/0.75秒门限保留。见[复核记录](../planning/reliability-v4-humble41-grace-review-20261031.md)与[原图清单](../results/inference_tail_core41_01/inputs/inputs.json)。以下内容为19:55历史快照，不能据其判断当前进程仍在运行。

2026-10-31 19:55（北京时间）快照：当前执行 **Humble41 同源核心12场景开发验证**。行人全部6项及汽车速度、位置、多目标交叉、云台中位4项的原始终态均为 PASS，合计10/12；第11项汽车主动云台已启动，最后一项汽车多目标主动云台尚未尝试。正式120核心与160扩展实验均未开始，完整批次观察器仍待结束后核验。

本机请打开[Humble41实时进度页](../results/project_progress/humble41_core01/index.html)。页面显示任务进程身份、心跳时间、当前场景、原始终态计数和异常原因；以页面时间和状态为准。页面中的“命令完成”只指该批命令，不能解释为项目验收全部通过。

每个场景依次经历起飞、75秒仿真时间的跟随任务、关闭录包、归档完整性检查和离线评价。飞行完成后，计数会等原始评价终态产生再更新。仿真采用非实时运行配置，75秒仿真飞行与归档评价会占用更长的实际时间。

前5个行人场景的完整执行实测为18.69–21.06分钟/项，平均19.84分钟；其中飞行部分约12.4–12.6分钟。第6项多目标主动云台耗时23.87分钟，首个汽车速度场景为18.92分钟，不同组别耗时有差异。按前5项吞吐粗算，280次正式实验本身约需93小时，尚须另计剩余开发、准入和最终分析；汽车其他组别仍待实测。这个估计替代此前基于短探针的较短估计，不承诺后续无故障。

当前开发结果中，行人主动云台的画面中心RMSE为17.756像素，中位模式为56.974像素，两项的距离、高度和末端稳定检查均通过。这是单个开发种子的观察，不能替代正式重复比较，也不能据此判断汽车问题已解决。

首个汽车速度跟随开发样本的距离/高度RMSE为0.759727/0.167390米，导航覆盖0.914894，真值覆盖1.0，六项工程门和末端持续稳定均通过。源时钟三流9258条全部配对，原生起飞、丢失安全、录包归档及清理检查通过。一个开发样本仍不足以证明汽车总体可靠性，剩余场景和正式重复仍需实际验证。

随后汽车位置模式的距离/高度RMSE为0.717087/0.156348米；多目标交叉为0.863683/0.157409米，完整身份分母754格中647正确、0观察到错误、107未知（覆盖0.858090），18项安全检查通过。汽车云台中位距离/高度RMSE为0.757138/0.163001米，11项中位检查通过，导航评价画面中心RMSE为81.718像素。以上均为同一个开发种子的结果，主动云台比较和正式重复仍待完成。

需要核对原始记录时，查看本机路径：

- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_seed004_matrix/slots/`：每个场景的开始记录和完整终态。
- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_seed004_matrix/observed_driver01/`：执行记录；整批结束后才能核实完整批次观察器的关闭结果。
- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_person_stage1_velocity_seed004/onboard.mp4`：已完成首项的机载画面。录像本身不代替定量评价。

旧 `results/project_progress/current/` 是此前Humble31任务的历史记录，其中的已结束状态不能用于判断Humble41是否运行。其他旧页面和失败记录保留。

进度页与视频属于本机结果，不随GitHub源代码提交；从GitHub新克隆后，没有本机结果时这些链接不可用。本文是带时间的入口说明，网页也不会自动向聊天发送完成通知。

</details>

</details>
