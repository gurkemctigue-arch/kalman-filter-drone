# probe02 剩余五场的实际续跑

21:07（北京时间）检查：完整行人回放的五个workers已退出，原bench主进程仍在汇总约1GiB日志，session25910尚无最终输出。源审发现逐命令/逐RGB全表扫描等汇总热点，正在隔离候选中准备优化，不中途更换本次实现。新[离线计时诊断页](../results/diagnostics/humble54_pipeline_timing_view01/index.html)仅收录四次已闭合短回放，41项计数检查一致、Chrome交互验证通过；它不替代完整回放结果或正式验收。

**软件计时更新：short04于20:47:24实际完成，五个进程全部exit0，清理错误为空，前台session83611已回收，线程45336同线程释放防休眠。** 三条DDS边分别76/453/504条，全部得到受控候选匹配；504条适配器命令中151条FOLLOW拥有完整软件链，353条FAILSAFE按非FOLLOW原样保留。252个收到的RGB中76个有FOLLOW链。全候选命令的回调到回调时间中位数753674083ns、p95为1158279926ns，命令可能复用同一图像，不能把该子集统计当总体性能或物理E2E。原summary副本及分母在[short04诊断](../results/diagnostics/humble54_pipeline_timing_run04/review01.json)。原short01/02停止、short03完整但0候选均保留；没有重分类历史strict未知。

20:49:56，root实际启动完整行人原速回放，输出 `/root/humble54_pipeline_bench01_full_person01`，前台session25910、临时防休眠线程36824，50117条输入且不截断。完整行人/汽车的结果必须来自各自真实终态，不能由short04外推。当前容量清理选择仍待用户答复；独立容量刷新CLI已源审与必要回归通过，当前153GiB缺口仍未解决。

**最新容量结论：20:16:32，显式after28续接真实结束。** 6个实际步骤（新idle、inventory、person export、car export、R0、full280 budget）均exit0，整体因原容量门保留exit2。所需244.936135 GiB，D盘快照可用92.117596 GiB，差152.818540 GiB；完整280槽、1.15系数、22 GiB后续开销和17.958118 GiB临时预留均保留。原始[预算与续接终态副本](../results/diagnostics/humble54_after28_budget_review01/review01.json)已保存，storage SHA为 `45dffb5746b38ee1fe96acab430a6799095c7fff239f381928af2c4b9440fe78`。前台session61617已回收，线程37816同线程释放临时防休眠。容量不足尚未解决，final55/正式0/280不变，不能套用旧“12步完整成功”的stage入口。

person export含752次测量和4511个输出事件，car export含747次测量和4507个输出事件；两者原 `online_equivalence_status` 与 `native_state_audit_status` 均为PASS。R0文件316797B，状态 `CANDIDATE_NOT_REGISTERED`、范围 `DEVELOPMENT_ONLY`。它是正式比较前的候选，不是正式算法优势结论。

第二次短计时已修复新就绪文件竞态并通过四节点就绪，随后因动态导入读包helper未先注册sys.modules停止；原short02失败和退出保留，4个算法进程均正常退出、replay exit1，cleanup_errors为空。fixed06仅增加该模块注册，23项回归通过，root复核源码及新增真实dataclass加载回归；第三次原生回放尚未开始，实际计时样本仍为0。

**两次实际退出后的更新：actual28 已于 19:51:59 完成，28 份大小凭证齐全；随后总流程于 19:52:07 真实停止，exit 2。** 唯一错误为 `Refused: Refusing large input`。汇总文件为 244,845 B，受限的是其引用的两份汽车身份评价明细（3,066,769 B 和 7,660,044 B），超过原通用读取器的 2 MiB 上限。原 7 个执行步骤均 exit 0，physical inventory、两类 export、R0 和完整 budget 尚未执行。原 terminal、源码、文件测量与退出均保留，正在修复显式续接；不能把本次停止写成容量不足或测量全部成功。前台 session89816 已真实回收，线程17644已同线程释放临时防休眠。

19:55:31，独立软件管线短回放实际启动；19:56:21 已真实退出 2，前台 session32666 已回收，线程22628已释放临时防休眠。其原 summary 记录 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`，回放尚未开始，有效计时样本为0，4组子进程均已退出且 cleanup_errors 为空。正在修复新就绪 JSON 的发布竞态；原失败输出在 `/root/humble54_pipeline_bench01_short01`，小原件副本在 `results/diagnostics/humble54_pipeline_timing_run01`。本次没有修改历史 strict UNKNOWN 或物理端到端结论，正式仍0/280。

**最新闭合检查点（2026-11-03 19:48:54，北京时间）：原扩展16/16已完成，11 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE；collector07、monitor、launcher均实际exit0；正式0/280。** after07完整测量已真实开始，当前receipt尚无最终terminal，未取得正预算或正式准入。以下按真实执行顺序保留各检查点，较早的运行中/待结束描述不是当前状态。

2026-11-03 18:00:37（北京时间），新 collector07 已实际调用原单槽入口，开始 `car_extension_latency_seed004`。Windows 原 monitor 持有 WSL 子进程，外层 launcher 持有 monitor 的原 Popen 并临时防止休眠；不自动重试、不覆盖旧实验。实际启动及心跳记录在 `results/diagnostics/humble54_pending_collector07_launcher01/`。

实时显示：[原进度页](../results/monitor_humble54_probe02_owner07/index.html)。该页报告进程、心跳、原始终态数和当前槽；实验通过率以真实终态为准。启动校验期间原生输出尚不存在，暂时显示无事件是正常的，不能据此判断路径错误。

本次原计划仍为 16 场。开始续跑时已有 11 场原始终态：7 PASS、3 FAIL、1 INCOMPLETE_EVIDENCE；后五场依次为汽车 latency、combined、speed_changes_velocity、speed_changes_position、far_distance。原来的 FAIL、null、INCOMPLETE 及原 owner06 退出码 2 均不改变。

注册源 SHA 为 `7d2523325bca8ef520fe0e5a7bd78da355943099e3f45efee2c3ad4e870cdd9b`，profile SHA 为 `c36f17363874173ee7fed08d482a68f518fd44cffd581d757de09ccd649ded55`，Windows launcher SHA 为 `3cfd98f01d6d9373aa01c45fd691ffd5a34e8dd1d3363edd12a990280322c923`。准备版实际 native check02 exit 0；注册差异只含三个源码字面及两个 profile 字段，原版本和回执已归档。执行入口还会重核完整冻结源与前 11 场证据。

汽车 dropout 的短窗未在原观察窗内恢复，故身份比较显式 null。新规则仅在已有明确丢失、明确无恢复、完整时钟/录包和原安全检查均满足时，将它记录为条件不可评价；原跟踪失败不变，不把身份未知计为身份成功，也不放行其他未知或物理身份准入。

同日 17:55:41—17:55:46，受控 ROS 消息关联 native03 已真实 exit 0：8 条单发送者消息得到 OBSERVED_CANDIDATE，16 条竞争发送者消息保持 UNKNOWN，真实清理完成。它只验证独立探针的受控关联能力，历史 strict 的 1,857 条 UNKNOWN 不改，完整管线及物理 E2E 仍未观测。

后续须先等原 owner 及其子进程真实结束，再用实际完整 16 场结果执行 28 条件空间测量、定标及完整 280 场预算。当前正式实验仍为 0/280；完整预算、final55 构建与正式准入尚未完成。若出现新故障或容量不足，保留原结果并解决实际问题，不能降低阈值、减少实验或宣称全部完成。

一次诊断更正：root 曾将启动时文件未生成和工具输出中的 JSON 转义误判为 UNC 错误。随后 root 与两个独立审查均按实际字符核实：路径均为两个起始反斜杠、段间单反斜杠，原页已正常读取。运行源码未修改，实验未重启；临时冗余只读 reader 已按创建身份核验后结束，原 monitor 和 WSL 子进程继续运行。

18:20:08，第 12 场 `car_extension_latency_seed004` 产生原始 PASS：距离 RMSE 0.741951 m，高度 RMSE 0.154516 m，真值覆盖率 1.0；原导航距离、高度、状态覆盖及末段稳定六项检查均为 true，无基础设施停止。终态原字节 SHA 为 `b2f1ec888c217cd1ac8e0dcfc56a19e4746dc5096e7902cf8c6d04c732330ab1`。原 collector 核验后继续第 13 场汽车 combined；此时累计 12/16：8 PASS、3 FAIL、1 INCOMPLETE_EVIDENCE。

同轮身份条件分类修复仅作用于 workspace 中的未来离线工具，运行中的 frozen54 和 collector07 源码均不改。38 项模块测试、9 项 runner 测试及独立的真实汽车小原件/4 项代表 fixture 复核通过。新 staging 候选也已准备并由 root 静审，仍保持生产关闭、未来输入未登记；它们不能替代真实完整 16 场、完整预算或正式实验。

18:45:46，第 13 场 `car_extension_combined_seed004` 产生原始 FAIL，终态 SHA 为 `50cda01cbc0850b94aa52962f365d5fb7daec7daff7b4fcd6503178fe4f5a00b`。距离 RMSE 为 2.036874 m，高度 RMSE 为 0.160389 m；导航高度、状态/真值覆盖及末段距离/高度稳定均通过，但全窗距离误差未通过。短时遮挡预测、未丢失及恢复后身份检查均通过；长遮挡开始时状态已是 LOST，事件窗内没有观察到预测阶段，因此该项为 false。长遮挡后的悬停、禁止自动恢复和显式重选后的持续跟踪检查均通过。以上来自原评价小文件，尚不能单凭它们断定长遮挡前丢失的具体原因；原 FAIL 不改，无基础设施停止。

collector07 复核原第 13 场后于 18:46:42 实际启动汽车 `speed_changes_velocity`；累计 13/16 原始终态为 8 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE，另三场尚待各自终态。当前原 monitor、WSL 子进程及外层 Popen 持有链继续运行，尚不满足后续原生测量的空闲条件。

原导航抽样文件进一步显示：第一次无效样本在仿真 34.852 s，原因为 `stale_navigation_measurement`；第一次 LOST 样本为 34.952 s，早于 42.36 s 的长遮挡。49.372 s 显式重选后恢复持续跟踪，之后末段稳定。因此长遮挡窗内没有预测阶段，不能解释为“没有执行悬停保护”。此处只读原小报告及抽样帧，未读取 telemetry/bag；尚未确认导致 34.852 s 失鲜的具体输入或处理环节。诊断及原字节绑定见 `results/diagnostics/humble54_probe02_car_combined_small_review01/review.json`。分段误差仅用于定位问题，不替换原验收窗口或阈值。

19:04:21，第 14 场汽车 `speed_changes_velocity` 产生原始 PASS，终态 SHA 为 `91860f3fddddc85c25cf478ce2707dcb77557b9498ddb29b81b0ad38b48a6f2c`。距离 RMSE 为 0.642943 m，高度 RMSE 为 0.160741 m，状态覆盖率为 0.914894，真值覆盖率为 1.0，原六项导航检查均通过。collector07 随后实际进入 `speed_changes_position`，剩最后的汽车位置变速和远距离两场；此时扩展累计 14/16 为 9 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE。开发成果页已按这些原终态重生成，正式仍为 0/280。

独立软件时延台架的 windows04 已完成源码和假对象复核，当前入口见 `tools/diagnostics/humble54_pipeline_timing_bench01/CURRENT.md`。它保留原检测、导航估计、控制和 adapter 代码路径，仅在隔离回放中观测对象来源及三条 DDS 边；尚未进行该完整管线的原生实测。其候选软件时延不能替代原飞行时延或物理 E2E，观察开销也尚未单独测量。root 的只读 Linux 路径查询已确认 frozen54/results 符号链接和原 core person/car velocity 路径均存在并解析至原发布目录，无需路径补救；后续实际执行仍须原逐件 SHA 核查。

后续 nav28/sensor4 的外置直接 producer 已通过 14 项作者假对象测试及独立复核，源码 SHA 为 `e1c439d51a5ae6569ae7efe34b3eb899228977a2fbf27d9d1f3bf2aa88bd3f75`，独审回执在 `tools/experiment_orchestration/final55_nav_sensor_after07_producer_review01/independent_review01.json`。它按原注册逐条执行并调用原完成清单校验器，sensor 部分只消费真实提取与阅图材料，不生成身份成功或人工审图结论。尚无任何实际 nav28 或 sensor4 producer 执行；必须在完整终态、实际容量预算、新 cold 构建与真实 target/注册之后再执行，原 FAIL/null 和准入门保持不变。

19:22:19，第 15 场汽车 `speed_changes_position` 产生原始 PASS，终态 SHA 为 `057534448a7e4da809e8f84dc09705f1c3d016f5ace6e0cb10b06ab4b8c4ebab`。距离 RMSE 为 0.617890 m，高度 RMSE 为 0.169138 m，状态覆盖率为 0.914894，真值覆盖率为 1.0，原六项导航检查均通过。collector07 随后实际启动最后一场汽车 `far_distance`；扩展原终态累计 15/16：10 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE。开发成果页按原终态重生成，尚不能把原 collector、monitor 或 launcher 计为已退出。

19:41:32.705733，第16场 `car_extension_far_distance_seed004` 产生原始 PASS，执行状态为 COMPLETED，无基础设施停止。距离 RMSE 为 **0.6593609238394991 m**，高度 RMSE 为 **0.15419769757319002 m**；valid_state_coverage 为0.9148936170212766，truth_coverage 为1.0。原六项导航检查 `base_link_distance`、`base_link_height`、`navigation_coverage`、`truth_coverage`、`final_distance_settled`、`final_height_settled` 均为 true。原终态[JSON](../results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/slots/car_extension_far_distance_seed004.json)文件 SHA256 为 `f03c983121b8913e0d3be31ad64fef6ca694df964a2214adbc6eac48f1ed2047`，`record_sha256` 内容摘要为 `ec7daddb35e3924aba2dca8cddd098b16f15f328ec0b4c2dff0f68d0d8b05159`。两种摘要分别保留，不混用。

19:42:07.987811，native collector07 的 `/root/uav_tracking_collection54_probe02_owner07/terminal.json` 记录 `COLLECTION_FINISHED`、returncode0、current_slot null。原 owner identity 为 PID266942、boot ID `f79204a4-99cd-42cf-b886-aa905b1cac6a`、start_ticks10982275。native terminal 原文件 SHA256 为 `34a60e0bc189c0b1845e0d4a0dc85388e968a53a666e2cfdeedb46eb48e03432`，与 Windows launcher 留存的[原字节副本](../results/diagnostics/humble54_pending_collector07_launcher01/native_terminal.json)一致。11个原闭合观察加5个本次实际续槽，共16原终态，累计 **11 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE**。collector正常退出表示采集/核对流程结束，不表示16格工程全部通过。

19:42:09.296661，原 Windows [launcher terminal](../results/diagnostics/humble54_pending_collector07_launcher01/terminal.json) 为 OWNED_MONITOR_ENDED、returncode0、closure_verified true、errors[]、interruptions[]；原 monitor实际returncode0，native collection returncode0，临时防休眠线程41076已同线程释放。launcher terminal 文件 SHA256 为 `8f5056620e21b60860d9d8785b79eab0c74a243071f08d039711f166b5d771e9`。旧owner06/observer07/trigger09的原exit2不变，未把原失败改为成功。

19:43:26，after07直接测量的七个实际输入完成登记；19:47:01独立复核确认仅登记字面变化、原流程与原工具不改，原件在 `tools/experiment_orchestration/humble54_closed_measurement01/registration01/` 和 `review_registration01/`。root约19:47实际启动该测量进程，tools session89816持有原调用，临时防休眠线程17644请求成功。原receipt的 `started_utc` 为 `2026-11-03T11:48:45.275129+00:00`（北京时间19:48:45.275129），与进程开始后的原full16闭合复核分开记录。

19:48:54从 Windows 只读原 `D:\WSL\UAVHumble22-validation\humble54_probe02_closed_measurement_after07_01` 小JSON：started/state均为 STARTED_DIRECT_MEASUREMENT，native_idle实际exit0，尚无terminal。这是当时观察，不预写后续actual28、physical inventory、两类exports、R0或full280 budget成功；后续实际进展以该目录的原state/terminal和真实退出码为准。若完整预算不足，原负budget与整体exit2必须保留；[容量刷新设计卡](reliability-v4-capacity-refresh-design-20261103.md)只是未实施的最小连接方案，不能替代实际容量修复。

开发成果页已使用原小JSON重生成：core12+extension16共28/28终态，23 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE；独立安全4/4 PASS单列，正式仍0/280。本次仅更新文档与派生HTML/输入凭证，没有启动WSL、原生重任务或新的owner，没有修改原证据、冻结源或measurement工具，没有Git提交。
