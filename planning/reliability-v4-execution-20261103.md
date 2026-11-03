# 2026-11-03 接续执行记录

本记录是执行检查点，不是全项目验收报告。用户已授权继续修复、仿真、统计、交付及 GitHub 同步。正式研究仍为 **0/280**。

**12:10（北京时间）实际检查点：8 START、7 原终态（3 PASS、2 INCOMPLETE_EVIDENCE、2 FAIL）、8 未尝试。** 第七场 `person_extension_speed_changes_position_seed004` 于 `04:04:47.689033 UTC` 原始 FAIL / COMPLETED，terminal SHA `ec7e46918d6677b9359a63df5b40f898020e4fb0759fdd1ef98e834b81a31729`；非INFRA、flight exit0、无清理残留。距离/高度RMSE为0.657147/0.162859 m，末端连续距离稳定为false，其余五项导航检查true，source/native/surface均PASS。collector实际核验后启动原第八场 `person_extension_far_distance_seed004`，当前唯一重原生任务仍为session52906。下方11:50及更早描述保留为历史。

已实际完成[位置模式末端复核与可视化](../tools/diagnostics/humble54_speed_position_review01/README.md)：同seed两次独立飞行各保留752行，位置模式末端连续在原稳定带中只有2.136秒，未满足原3秒要求；速度模式为39.152秒。root已直接阅图，不以末帧误差小替代持续稳定，不改原FAIL。[组合场全窗口图与窄触发链](../tools/diagnostics/humble54_combined_navigation_review01/README.md)也已生成并直接阅图。图表是原数据诊断，不是新飞行或修复通过证明。

本轮应用 `grill-for-unknowns` 做源码/证据复核，沿用本执行记录作为实施与未知项记录。当前可由代理独立处理的未知项包括：组合场首次丢失的实际输入流补证、汽车两个输入附件、位置模式控制动态成因、完整28格容量和最终冻结原生验证。已决定保持0.60秒新观测年龄上限、0.75秒预测保护、原统计窗口与全部失败；不以延长保护或改变门限解决压力失败。无需用户重复确认已授权工作。

**11:50（北京时间）新采集器实际运行：7 START、6 原终态（3 PASS、2 INCOMPLETE_EVIDENCE、1 FAIL）、9 未尝试。** 原第七槽 `person_extension_speed_changes_position_seed004` 正在原 normal CLI 中运行，新[串行采集进度页](../results/project_progress/humble54_pending_collection03/index.html)显示完整16格分母。前六槽事件为明确标注的原件观察拷贝，不伪造本owner曾启动它们，也未复制旧owner的FAULT事件；新事件标明 `ACTUAL_CHILD_INVOCATION`，原正式试验START仍以原 `.started.json` 为准。

外置 collector 代码 SHA256 `dd4583da4f34b216bc5dd5a95aa904459ebc7f68e2bfba026a2e3e66706d9c86`，14项标准库fixture/fake-child测试通过；root此前实际只读前置exit0，确认六个原终态及来源、安全齐备，再显式调用 `--execute`。运行 session **52906**；Windows monitor **16596** / FILETIME `134381511872112352`，owned WSL **46712** / FILETIME `134381511874567318`；Linux collector **149576**，当前实际子命令 **149577**。`power_owner54/receipt08/state.json` 实读ACTIVE，observer **23740**，只申请本monitor存活期间的临时防休眠、不改全局策略。

collector只对连续原PENDING逐次调用不变的单槽入口；每次完成后核原报告/配置/终态SHA、source/native/录包及长时九项安全检查，再继续下一槽。新的未知、基础设施/来源或安全问题立即停，不重试旧槽。已知压力算法FAIL继续保留；原历史null独列 `unobserved_checks`，不算已知算法失败。原owner/waiter仍保持原停止状态，无容量、export、final55或正式后续自动接续。第六场15份原始小证据见[字节快照](../tools/experiment_orchestration/humble54_extension_sixth01/README.md)。

**11:47（北京时间）原终态复核：** 第六场 `person_extension_speed_changes_velocity_seed004` 实际已于 `03:40:24.461884 UTC` 原始 **PASS / COMPLETED**，原 terminal SHA256 `a152e62b340e4ebbc55613cad93a938f1cfe010ed9b4cd0bb4602e19e5a0855d`。normal CLI/监督 session65985 已退出0，非基础设施停止、无残留；source/native/surface PASS、六项导航门均 true。距离/高度 RMSE 为 0.696673/0.169817 m，有效导航覆盖 0.914894、真值覆盖1.0，两项末端持续稳定通过。当前共6终态：3 PASS、2 INCOMPLETE_EVIDENCE、1 FAIL，10 PENDING。此前归档阶段描述只代表当时过程，不作为当前状态。其 4,617 条 PX4 设定值均为 velocity-only，position-only/同时 position+velocity/invalid 均为0。

原六槽连续前缀的原生只读 collector 检查已经实际退出0。该复核确认组合场的导航距离 RMSE **2.296435 m** 超过原1.0m门，高度 RMSE0.149508m、有效导航覆盖0.800532、真值覆盖1.0，其余五项导航门为true。这是按原冻结门复核的数值 **FAIL**；原 navigation 报告标签仍为 `RECORDED_WITH_CENSORED_FAILURES`，原 terminal 的顶层负面 evaluator 只有 `surface_flight`，没有新增或改写原字段。长窗 prediction=False 与额外确认的全窗距离超限均保留，不能称为仅缺证或仅日志问题。collector 此时尚未启动采集；正在将其历史null观察从 `known_algorithm_failures` 单独列为 `unobserved_checks`，随后才会用新名字输出正式采集记录。

两份已导出行人数据已实际调用只读模块：dropout 返回 `UPSTREAM_INPUT_INTERRUPTION_CORROBORATED`、errors=[]；combined 返回 `NOT_APPLICABLE`（短窗原本已有检测诊断）、errors=[]，仍保留 `surface:long:prediction_observed=FAIL`。首次调用因原合同指向 `/root/.../results` 符号链接、未显式给 canonical path，保留为 `INCOMPLETE`；第二次另存规范路径合同，只改变同一 source_plan 的路径表示，原文件 SHA/科学参数/四槽不变。两次结果与原件见[52份字节保留快照](../tools/diagnostics/humble54_input_evidence02/README.md)。没有改原缺证或原FAIL，汽车两格未齐，完整四槽/工程准入仍未完成。

**11:26（北京时间）接续检查点：原扩展计划 6 START、5 个原终态（2 PASS、2 INCOMPLETE_EVIDENCE、1 FAIL）、10 个未尝试槽。** 第六槽 `person_extension_speed_changes_velocity_seed004` 已于 `2026-11-03T03:21:54.939210Z` 实际 START，normal CLI 仅执行该一个原 PENDING 槽。新[命令监督页](../results/project_progress/humble54_extension_speed_velocity04/index.html)只监督本条命令及其真实退出码，不以无 events 的页面计数代表矩阵进度。Windows monitor PID **31988** / FILETIME `134381497020715128`，owned WSL PID **34872** / FILETIME `134381497024909290`，unified-exec session **65985**。临时防休眠 `power_owner54/receipt07/state.json` 已实读 ACTIVE，observer **16704**，绑定上述 monitor 身份、不改变全局策略。

第五槽组合扰动于 `03:12:44.978442 UTC` 原始 **FAIL / COMPLETED**，terminal SHA256 `596db684d39afe1eb561b710550541728a71e5e6c564118a1206d204c557c677`；flight0、infra=false、cleanup 空、source/native PASS，长时九项安全行为均 true，但 `prediction_observed=false`。原 FAIL 保留。上一命令正常退出 0 仅表示执行结束，不代表该槽工程 PASS。

通信延迟已实际完成新命名离线诊断：[数值原件](../results/diagnostics/humble54_navigation_grid_fix01/numeric_verdict01.json)。修复后的网格分母一致，原数值 validator 返回 PASS，六项导航门均 true，距离/高度 RMSE 为 0.777998/0.151949 m；新报告 SHA256 `36a6eb06315e0c5a6ddc0c85914aa7924c3a3aec472d891f6de8fb3bd9c1acfd`。这是单次开发诊断，不是完整 28 格预登记复评、工程准入或原终态改判。两份原缺证终态继续不变。

实际空闲窗口串行调用新提取器 `364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4`，session **19086** 已正常退出 0；分别完整扫描两类输入与诊断话题，导出行人 dropout/combined 两份各九张原图。root 已直接查看全部联系图：dropout 31.4/31.5 秒、combined 29.9/30.0 秒近黑，前后可见行人。各新目录 `humble54_person_{dropout,combined}_input_extract02` 已另存 `visual_review_native01.json`，绑定同一实际图像 SHA 与可解析 native 路径，旧提取及旧阅图不动。显式固定两类别×两工况的描述性合同位于 `results/diagnostics/humble54_input_evidence_contract01/contract.json`；它不是预注册，汽车两槽尚未运行，完整四槽附件仍未齐，尚无真实模块复评结果或 ready。

以下 10:53 及更早块均为历史检查点；旧 owner/waiter 仍停止，不作为新采集进程使用。

**10:53（北京时间）实际检查点：原扩展计划 5 START、4 个原终态（2 PASS、2 INCOMPLETE_EVIDENCE）、11 个未尝试槽。** 第五槽 `person_extension_combined_seed004` 已在新 normal CLI 单槽调用中实际 START：`2026-11-03T02:50:53.012521Z`。本次 Windows monitor owned child 为 PID **50620** / creation FILETIME `134381478446741119`，WSL 命令为 PID **47440** / FILETIME `134381478448326284`，unified-exec session **90558**。上一 latency 调用 session **95312** 已正常退出 **0**，不把其原槽改判 PASS。

临时防休眠 `D:/WSL/UAVHumble22-validation/power_owner54/receipt06/state.json` 已实读核验：observer PID **52092**，monitor PID **50620** / FILETIME `134381478446741119`，`status=ACTIVE`，心跳 `2026-11-03T02:52:52.1797843Z`，`scope=TEMPORARY_SYSTEM_SLEEP_REQUEST_ONLY`、`global_power_policy_changed=false`。这是本轮临时系统休眠请求，不是全局电源策略变更。

当前[监督进度页](../results/project_progress/humble54_extension_supervised02/index.html)继续汇合旧 owner 历史观测的拷贝及实际新 START/终态 marker，只是派生观察，不是新 owner、正式准入或扩展全批 PASS。旧扩展 owner 仍 `STOPPED_FAULT`；旧 waiter/followon01 仍 `STOPPED_REFUSED_NO_RETRY`、`followon_launched=false`，句柄关闭。不得伪造或复用其 `COMPLETED` 状态。仅逐一使用 normal CLI 监督原 PENDING 槽，每个新终态先核原件与安全证据，再决定下一槽；不自动重试失败或缺证槽。

第四槽 `person_extension_latency_seed004` 原终态为 `INCOMPLETE_EVIDENCE`，完成时间 `2026-11-03T02:42:57.447159+00:00`，原件 SHA256 `c411dd9f7cd0e5db64cd4e12404d424a01ab91a5598073a05c80c90cda47b93a`；flight_exit0、非 infrastructure stop、cleanup residual `[]`，source-clock/native-startup/surface 均 PASS，navigation 原标签 `RECORDED_WITH_CENSORED_FAILURES` 不变。工程原因 `Transient denominator differs from the whole interval` 已定位：19.0–94.1 秒、0.1 秒网格共 752 行，末行 `94.10000000000001` 比上界高 `1.4210854715202004e-14` 秒，严格区间过滤使四个瞬态块均只剩 751 行。这是统计实现不一致，并非算法性能阈值失败证据。候选网格修复已有 35 项测试通过，但尚无真实 bag 的新命名复评；冻结 54 未变，当前批次仍用原源码，原终态不改。

第三槽 `person_extension_dropout_seed004` 的原 `INCOMPLETE_EVIDENCE`、短窗 research/diagnostic=0 及 interruption=null 均保留。新抽图实际 `COMPLETED`、exit0（session62132）；独立阅图已实际记录九张原图，31.4/31.5 秒近黑，前后可见行人，见[联系图](../results/diagnostics/humble54_dropout_gap01_extract01/contact_sheet.png)和[独立阅图原件](../results/diagnostics/humble54_dropout_gap01_extract01/visual_review01.json)。原提取 manifest 仍为 `PENDING_VISUAL_REVIEW`，不能称原缺证已修复或准入。

正式仍 **0/280**。完整 actual28 容量、两类开发录包导出/R0、final55 及正式重复研究均待各自实际执行。以下 10:31 及更早块全部保留为历史记录，不能用于判断本轮进程状态。

**10:31（北京时间）实际单槽续跑：原计划已有 4 START、3 个原终态（2 PASS、1 INCOMPLETE_EVIDENCE）、12 个未尝试槽。** 新 normal CLI 使用 `--max-new-trials 1`，仅执行原计划下一个 PENDING 通信延迟槽；实际 START 为 `2026-11-03T02:25:24.728624Z`，不重试第三场 dropout，不改其缺证判定。新[监督进度页](../results/project_progress/humble54_extension_supervised02/index.html)使用拷贝的旧 owner 历史观测及实际新 START marker 派生观察，不是新 owner、准入或扩展全批通过证明。

本次 Windows monitor owned child 为 PID **16816** / creation FILETIME `134381463176279356`，WSL 命令为 PID **18688** / FILETIME `134381463178057290`，unified-exec session **95312**；独立 watch session **1323**。新临时防休眠 observer PID **51192**，`power_owner54/receipt05/state.json` 为 `ACTIVE`，不改全局电源策略。当前槽结束后须先核新原终态及安全证据，才决定下一个 PENDING 槽；未授权用自动重试覆盖旧缺证。

旧 owner 的 `STOPPED_FAULT`、原 monitor/WSL 退出 2，以及原等待器 `STOPPED_REFUSED_NO_RETRY` / `followon_launched=false` 均保持原样。`followon01` 不会被复用或伪记为 `COMPLETED`；后续容量、导出及定标需按实际条件使用新的 CLI，目前未由此续跑启动。短窗证据冲突仍待最小修复，正式仍 **0/280**。下方 **10:17 及更早段落均为历史检查点**。

**10:17:32（北京时间）实际终态：扩展批次已停止，2 PASS、1 INCOMPLETE_EVIDENCE、13 PENDING。** 第三场 `person_extension_dropout_seed004` 原判为 `INCOMPLETE_EVIDENCE`，owner 为 `STOPPED_FAULT`，原 Windows monitor/WSL 命令均退出 2；不能继续按下方 RUNNING 描述判断。约 **31.3–31.58 s** 的短遮挡观察窗被 seed004 两个 **200 ms** 的检测掉帧窗完整覆盖，该短窗诊断样本为 **0**，原 `interruption` 为 **null**。原判和缺证保留，尚待最小修复；没有把 null 改成零或普通算法压力 FAIL。

有条件等待器已终止于 `STOPPED_REFUSED_NO_RETRY`，`followon_launched=false`，所持原进程句柄已关闭，**自动续接已不再等待**，未运行原生 follow-on。root 另行实际调用既有 `native_idle02`，返回 `matching_processes=[]`、退出 0；该调用没有单独原始回执，不构成新审计或后续八步已运行的证据。当前仅在决定是否继续执行原计划剩余 **13 个 PENDING 槽且不重试第三槽**，尚未启动续跑；源码暂存、28 格容量测量、导出/R0 定标及正式准入均不能提前记为完成。正式仍 **0/280**。

以下 **10:02 及更早段落、带“当前/运行中/已等待”字样的旧章节均为历史检查点**，保留原文供追溯，不是继续启动旧进程或后续任务的指令。

**10:02（北京时间）接续观察：扩展已为 2 个原始 PASS，第三场 `person_extension_dropout_seed004` 正在执行。** 第二场 `person_extension_depth_holes_seed004` 于 `01:59:49.833276 UTC` 记录 `PASS / COMPLETED`、非基础设施停止、flight exit 0；距离/高度 RMSE 为 0.752211/0.165787 m、导航有效覆盖 0.916223、真值覆盖 1.0，六项工程检查均为 true。其原终态文件为 55,135 字节，文件 SHA256 `8b1bf279e500a882edaf04cefba5f962f288d89e02023d8c882b8ce35fddfe09`；内部 `record_sha256` 为 `b86c7ad707dca76b207867cbebdf68e7a23db923386324d864570ab1da884082`，两者不混用。第三场 START 为 `01:59:53.488846 UTC`；`02:02:21 UTC` 进度仍 RUNNING。另行实际 Windows 进程查询核对原 monitor 19256、WSL 4888、waiter 28932 的创建 FILETIME 均未变，未启动并行原生任务。下面 09:44 及更早段落保留其当时含义，不将其旧计数视作当前结果。

**09:44（北京时间）实际检查点：扩展 16 正在运行，2 START、1 原始 PASS、14 未开始。** 重新读取的进度生成于 `2026-11-03T01:44:07.757396+00:00`，状态 `RUNNING`，命令与监控器的创建身份及新鲜心跳核验通过；当前为 `person_extension_depth_holes_seed004`，其 START 为 `01:38:29.546129 UTC`。首场深度噪声已于 `01:38:26.893766 UTC` 记录原始工程 PASS，未预记其余场景。核心 12/12 与安全 03 四场原始工程 PASS 均已闭合，正式仍为 0/280。

## 已实际完成

- Humble54 同源核心 12 场原始工程 PASS 已闭合，保留同一开发种子的限制。
- 扩展首场 `person_extension_depth_noise_seed004` 原始 PASS / COMPLETED，`flight_exit_code=0`、`infrastructure_stop=false`，清理残留列表为空；距离/高度 RMSE 为 0.7579153021/0.1619863085 m，有效状态覆盖 0.9162234043、真值覆盖 1.0，末端持续稳定均通过。navigation 原状态 `RECORDED_WITH_CENSORED_FAILURES` 保留。[首场最小原件](../tools/experiment_orchestration/humble54_extension_first01/README.md)含九个原始小型 JSON，七份试验报告与终态 artifact 哈希一致，终态内部摘要及 START 绑定核验通过；未读 bag 或改原评价。
- 安全 02 于北京时间 08:08:49 结束：1 INFRASTRUCTURE_ERROR、3 未执行。五条子命令退出 0，但汇总读取不存在的 `result` 字段导致 `KeyError`；source/native 原报告采用 `evaluation_status`。
- 修复只调整末尾汇总，source/native 仍由原 `read_evaluation` 严格校验。Windows 63 项专项检查运行成功，4 项平台条件跳过；其结果来自执行代理的实际工具返回，未另造原始日志。
- Ubuntu 22.04/Humble 实际 5 项回归全部通过，2.692 秒、无跳过；保存原始日志及退出码。它们是组件测试，不是五次飞行。
- 实际 native03 创建 contract03 并完成只读 schema 诊断，退出 0。首份快照调用原 helper，另两份按原始字节及完整映射等价核验。没有重判旧安全 02，没有改原登记时间，没有修改冻结的 Humble54 飞行源码。
- 修复及原始小证据已提交并推送 `d1635cf`、`c6b30d2`。

## 当前唯一飞行批次：扩展 16

- 冻结运行根：`/root/uav_tracking_fullplan_v4_humble54`；没有修改冻结飞行源码。
- [实时进度](../results/project_progress/humble54_extension16_run01/index.html)；[原计划](../results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix/plan.json)。计划于 `01:15:23.564925 UTC` 实际创建，模式 `EXTENSION_PROBE`，共 16 场开发种子 004；未消耗正式种子。
- 计划原文件 SHA256：`f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055`；登记 digest：`ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761`。这两个值分别绑定文件字节与计划内容，不能混用。
- [Linux owner 状态](../results/frozen_fullplan_v4_humble54/humble54_extension16_owner01/owner_state.json)：启动时 PID 134468、start ticks `7830987`、boot ID `f79204a4-99cd-42cf-b886-aa905b1cac6a`。09:19 的 RUNNING 记录是历史观察；当前 START/终态计数以上述 09:44 实际进度和原槽标记为准。
- Windows monitor PID 19256，creation FILETIME `134381420603083387`；owned WSL 命令 PID 4888，creation FILETIME `134381420604764583`。本轮 unified-exec session 为 29911。
- 临时防休眠 observer PID 44952，依据 `D:/WSL/UAVHumble22-validation/power_owner54/receipt04/state.json`：09:18:41 状态 `ACTIVE`，API request 返回 `2147483648`，绑定 monitor 19256 的上述创建身份；不改变全局电源策略。旧 observer 50284 不属于此当前有效收据，不能混用。

只保留一个重型原生任务，扩展批次活动期间不另开 WSL/仿真或录包分析。保留每个原始终态；基础设施或证据门失败仍先停止定位，不改称普通压力算法失败。

## 已实际启动的有条件后续等待器

Windows waiter 于 `01:37:42.141035 UTC` 启动，PID 28932、creation FILETIME `134381434621456534`，运行 `D:/WSL/UAVHumble22-validation/wait_humble54_extension_followon01.py --execute`。`01:44:04.603462 UTC` 实读状态仍为 `WAITING_FOR_EXTENSION`、`followon_launched=false`，原 monitor/WSL 精确句柄退出码均为 null；并未启动后续原生步骤。实际启动、等待快照与来源文件见[独立原件归档](../tools/experiment_orchestration/humble54_closed_followon01/manifest.json)。

等待器持有原 monitor PID 19256 / FILETIME `134381420603083387` 与 WSL PID 4888 / FILETIME `134381420604764583` 的句柄；须等待原进程退出并完成闭合核验，才有条件顺序执行八步：元数据预检、空闲检查、源码暂存、28 格容量统计、物理卷清单采集、行人指定开发录包导出、汽车指定开发录包导出、R0 定标。无自动重试，未创建正式准入、final55 最终构建、参数假设收据或新飞行。防休眠仅为临时系统请求，不改变全局电源策略；正式仍为 0/280。

## 已结束的安全 03 批次（历史检查点）

安全 03 于北京时间 08:21:54 首场 START。08:26:18 的核对为 1 START、0 终态、3 未开始；首场最后已记录采集时间约 29.5 仿真秒，owner 心跳新鲜。此时间快照不能证明此后仍在运行，应读取以下实际入口。

- 冻结运行根：`/root/uav_tracking_fullplan_v4_humble54`。
- [实时进度](../results/project_progress/humble54_safety4_run03/index.html)。
- 原生 owner：`results/frozen_fullplan_v4_humble54/reliability_v4_humble54_safety03_audit/owner_state.json`；结束后查同目录 `owner_terminal.json`、`execution_terminal.json`。
- registry SHA256：`ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf`。
- Windows monitor PID 15484，creation FILETIME `134381388887778865`；owned WSL PID 51320，creation FILETIME `134381388889337195`。本轮 unified-exec session 为 59721。
- 临时防休眠 observer PID 33500，原件位于 `D:/WSL/UAVHumble22-validation/power_owner54/receipt03/`。API 请求已接受，随原 monitor 结束释放；不改变系统全局策略。

不要再次启动原安全 02 或并行启动第二个仿真。安全 03 任一非 PASS 都按原工具停止并保留，先定位原因，再决定新的独立尝试。

08:45:25 核对：两场行人安全验证均已原始 PASS，第三场 `car_auto_unique_multi_seed004` 正在运行，检测采集时间约 24.1 仿真秒，第四场未开始。没有将运行中的汽车场景预记通过。

09:02:08 整批已完成：四场原始 PASS、20 条命令退出 0、完整 guard PASS，原生 owner 与 Windows 命令均退出 0，无待执行或未闭合槽。随后 root 串行原生查询确认无仿真进程残留，防休眠 observer 已正常释放。上述 PID/session 是已结束的历史身份，不应重启。[闭合原件快照](../tools/experiment_orchestration/humble54_safety4_closed03/README.md)已独立复核，正式仍为 0/280；扩展 16 待系统盘空闲窗口维护后启动。

## 后续按实际结果推进

1. 安全 03 已闭合，扩展入口 `D:/WSL/UAVHumble22-validation/run_humble54_extension16_probe02.sh` 已实际执行并创建上述独立计划，当前串行运行扩展 16；继续监控真实原终态，不重新启动安全批次或当前扩展计划。
2. 扩展 16 保留全部原始终态与压力失败。基础设施或证据门失败仍需先解决，不能把它归作普通算法压力失败。
3. 使用完整核心 12 + 扩展 16 的真实体积核算容量；完成两类预定 velocity 开发录包导出及 R0 定标。storage 第三 producer/driver 配对已通过独立静审及 41/41 项 Windows 回归；仍不能用组件验证代替真实 28 格测量。
4. 按 [final55 暂存说明](reliability-v4-final55-source-staging.md)建立新最终根、冷构建、前瞻登记、容量准入及封存。保留原冻结映射；原固定外置 guard 路径不变。
5. 全部准入完成、补充协议在首场 START 前登记后，执行正式核心 120 + 扩展 160。保留失败、未知、未执行和删失，不选成功种子替换原槽。
6. 完成 20 条录制 × 4 估计器配对分析、检测审核、身份/恢复与时序附件，再生成最终计划书、研究报告、图表、视频和统一交付入口。Word/PDF 需要真实渲染及逐页检查。

扩展运行期间已核对[补充评价与定标接续清单](reliability-v4-supplementary-replay-prerequisites-20261103.md)，其中物理身份恢复协议须单独在正式 START 前创建，不能由检测协议替代。另已准备[显式容量假设](reliability-v4-humble54-storage-assumptions01.json)：三项增长因子 1.15、每槽另留 16 MiB、临时公式另留 2 GiB、剩余构建 4 GiB，五类交付合计 18 GiB。Windows 实际原预算器的 assumptions schema 校验通过，独立静核算术一致；仅实际 storage-probe 确认 results/VHD 同在 D 卷时适用。它们是前瞻余量，不是 28 格测量、空间充足证明或正式准入；真实预算不足时保留差额，不通过减少余量或丢弃失败来适配容量。

本轮[核心 12 场实际计时](../tools/diagnostics/humble54_dev_wall_timing02/README.md)已提取并独立复算：owner 调用单调计时均值 19.035822 分钟，范围 17.611350–21.816790 分钟。它包含准备、飞行、归档、评价和返回后的清单处理，排除随后策略核验；不是纯飞行或算法推理时间。之前约 112 小时的正式实验估计来自旧 Humble42 六次完整 attempt，仅是历史条件外推；当前尚未获得 Humble54 完整 28 格的混合场景耗时与容量，不能作为确定交付时间。

## 关键原件

- [schema03 原始证据及绑定](../tools/diagnostics/safety54_schema_recovery03_archive01/README.md)。
- 新 driver SHA256：`6f93e58d6281aa882c4b89273fcfaa1dc1897d9651174e2b947d82bd28d5c172`。
- native03 回执 SHA256：`155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf`。
- contract03 SHA256：`0d5bc8770c039615249caeeabd2b18598564a4cf50ae31e4023f4e47ae7a30ef`。
- 原生及工具文件在 `D:/WSL/UAVHumble22-validation/`，外置 guard 位于 `/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py`。
- C 盘由 0 可用字节恢复到约 228 MiB，仅压缩 15 份本项目已停止写入的工具日志，逐份内容 SHA 不变；未删除文件。原件记录：`D:/WSL/UAVHumble22-validation/project_tool_log_ntfs_compression03.json`。D 盘完整正式预算仍待上述真实测量。
