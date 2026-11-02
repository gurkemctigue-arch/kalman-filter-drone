# Humble53 失败诊断与下一轮修复执行

2026-11-03，北京时间。本轮正在修复和验证，不是新的完整验收结论。原 Humble53 核心保持 **7 PASS / 1 FAIL / 4 PENDING**，正式研究保持 **0/280**。原槽、报告、门限、未知身份区间与失败分母全部保留。

## 两条独立故障链

汽车位置模式在 53.552 s 首次出现 stale_target，53.560 s 原 track2 进入 LOST。最后接受的测量采集于 52.8 s；下一帧 53.3 s 在 53.584 s 才完成，超过原 0.75 s 预测期限。窗口内原 track2 的 22 个不同测量时间戳均被 KF 接受，没有先发生 KF 拒绝的证据。慢帧 YOLO 墙时 3.6623 s、调用线程 CPU 时 3.5656 s，其中网络推理 3.6107 s；不能将它仅解释为排队或调度等待。

另一个窗口位于 76.55–76.68 s。原包只读抽取完整取得 Clock 27295 条、raw/timing/adapted 各 9246 条、phase 1861 条。56894 条选定消息的原生顺序与 SQLite timestamp/id/CDR 顺序完全一致，无解码错误，保护的原输入未变。原报告的 8 次 diagnostic、1 次 odometry、3 次 phase 越界均精确定位；记录端旧 Clock 落后约 52–152 ms 仿真时间，之后约 2–13 ms 记录墙时内追上。排除了抽取重排；具体 DDS/执行器积压机制仍须前瞻实验验证。这组异常晚于跟踪失锁，不能合并成同一个原因。

具名原生抽取输出：`D:/WSL/UAVHumble22-validation/candidate53_clock_raw01/`。工具为 [extract_clock_window.py](../tools/diagnostics/humble53_clock_window01/extract_clock_window.py)，只生成诊断附件，不重评原试验。

## 修复候选与验证顺序

1. 检测器保留 CPU4、原权重、512 输入和全部预测参数，每次预测仍核对调用线程的实际线程数，仅在不匹配时重设。官方 PyTorch 2.5.1 OpenMP 实现即使同值调用 setter，也会在 MKLDNN 分支清缓存；实际 Humble 环境已确认启用 OpenMP/MKLDNN。此机制成立，不单独证明原慢帧根因。新增 6 项线程纠正/外部重置/线程局部/失败传递测试及原相关回归合计 39 项通过。
2. 先完成生产后台 worker 的隔离对照，再进行实际新源码构建和飞行。首批各 36 次，输入、实际 tensor、参数、权重及全部检测框一致；中位数约 0.2681/0.2631 s，p99 约 0.7731/0.3904 s。另一次直接调用真实生产 helper 的对照已完成，各 144/144 次，输入和全部框仍完全一致；中位数 0.2611/0.2525 s，p99 0.3976/0.3691 s，最大值 0.5100/0.3711 s。条件未随机交错，未施加仿真负载，这些数值不证明稀有尖峰消除。原始绑定及逐对核对见 [144 次比较收据](../tools/diagnostics/detector_tail_candidate01/production144_readonly_comparison.json)，工具和限制见 [诊断说明](../tools/diagnostics/detector_tail_candidate01/README.md)。
3. 独立比较 recorder `/clock` 当前 depth2048 与候选 depth1，保持 reliable/volatile 和其他证据主题配置；使用生产 RGB-D、双桥及可明确登记的单次录制暂停压力。必须同时核对非 Clock 数据、源间隔、末端覆盖和真实退出。减少 Clock 数量本身不是改善证据。候选尚未写入生产配置。
4. 两项候选有依据后，冻结全新 Humble 来源，实际执行四包冷构建、FastCDR 编译来源、模块/ament 隔离、生成消息 CDR 和完整原生测试。新源码不复用旧构建通过结论。
5. 先执行全新汽车位置模式 seed004、75 s 的失败场景复验；通过后执行同源核心12、安全4、扩展16。每槽只尝试一次。来源时钟、原生启动或基础设施异常停止后续执行；开发核心的普通工程 FAIL 也停止并诊断。
6. 依原计划完成真实容量、R0 定标、最终准入、正式280次、配对分析与文档交付。开发对照不能替代正式重复。

## 执行方式

公开 `run_reliability_v4.py` 与 `run_stage1_trial.py` 已具备双桥、DDS、PX4、实际进程、录制闭合、独立评价及来源绑定检查。下一轮采用这些原公开 API 和通用薄批次观察器，避免继续复制只服务某个版本号的外层工具。每次仅消费一个 PENDING 槽，检查真实终态与原报告后才推进；命令退出零不视为工程 PASS。此调整不移除运行时检查、研究准入或时效门限。

当前未解决的实质未知是：线程 guard 在完整仿真负载下能否改善慢帧尾部，以及最新 Clock 接收策略能否在保留证据完整性的同时消除积压。没有需要用户补充才能进行的设计决策；常规实现、实验与 GitHub 同步沿用现有授权。

## 原始时钟组件对照及诊断混杂

四个原始条件均已真实运行，原件与 SHA 见 [V1 小文件证据](../tools/diagnostics/recorder_clock_candidate01/evidence_v1/comparison.json)。三类相机流在各自前瞻登记的固定 20 源秒窗口中均为 200 帧、时间戳和完整像素/标定多重集一致；末端 Clock 闭合且自有进程无残留。

| 请求的 Clock history depth / 暂停墙秒 | 最新录入 Clock 减 producer receipt | 原参考界越界数 | 证据状态 |
| --- | --- | --- | --- |
| 2048 / 0.6 | −44 至 +4 ms | 0 | 完整；未复现原异常 |
| 1 / 0.6 | −4 至 +60 ms | 0 | 完整；比独立观察少 17 条 Clock，最大源步长 72 ms |
| 2048 / 1.0 | −68 至 +4 ms | 5 | 完整；受控暂停后复现参考落后 |
| 1 / 1.0 | 0 至 +72 ms | 0 | **不完整**；proxy event 1104（源 10.04 s）未录入 |

最后一项 sent=2225、recorded=2224，缺失发生于暂停期间，不能把该条件改记通过。诊断 producer 的 publisher history 为 10，recorder 使用自动选择的 profile、未单独认证其实际队列；100 源 Hz 在当前 RTF 下暂停 1 墙秒会产生约 12.5 条 timer 数据，此处存在诊断队列自身的混杂。下一对条件将对两个独立诊断主题显式采用相同的可靠、volatile、depth1024 队列，生产五项 profile 保持原样，Clock 仍为唯一条件差异；输出独立命名，四项原结果保留。

少录 Clock 是 depth1 的实际代价，不能单独视为修复。当前组件未运行 PX4/YOLO，proxy 也不是 PX4 adapter；所有完整飞行仍须逐条通过原时效门，不能补 Clock、删除越界或放宽门限。生产配置在此快照时仍为 depth2048。

之后完成的新 proxy1024 配对证据见 [完整小原件与比较](../tools/diagnostics/recorder_clock_candidate01/evidence_proxy102401/comparison.json)。两组同一执行 probe、原始输入 pins、暂停源起止与前瞻窗口；生产五项 profile 中仅 Clock depth 为条件差异，两个诊断主题均显式1024。三类各200帧、全部producer/control、末Clock及进程清理均完整。旧组仍5次越界（−68至+4ms），候选0次（0至+92ms），候选少28条Clock、最大源步长96ms。独立只读复核逐项核原件和当前输入后支持将depth1作为下一完整飞行候选；root据此已把当前生产 `/clock.depth` 改为1，其余四profile保持。这里不授予完整飞行修复或验收结论，原四条件及原Humble53保持不变。

## 新构建和执行入口核对

完整源码复制映射覆盖全部未排除文件、ignored 运行时注册、权重和符号链接，分别核对复制前源码、复制后源码与冻结副本；任何缺失、新增或字节变化都会阻止后续验收。公开 freeze 在两次 source 后均重新应用当前 DDS，完整测试启动前另存实际继承环境。独立静态复审未发现明确构建阻断；尚不能替代实际冷构建和进程库加载验证。

root 已在 `UAVHumble22` 实际执行三个构建辅助测试模块，**16 项全部通过、无跳过**，并分别通过两份 shell 脚本的 `bash -n`。Windows 检测器/复制相关五模块为 33 项、29 通过/4 平台跳过。这些结果均不代表新四包已构建或飞行通过。

通用 batch owner 现仅支持开发 `core/PROBE` 与 `extension/EXTENSION_PROBE`；正式 `FORMAL/EXTENSION_FORMAL` 被拒绝，防止直接调用 normal runner 绕过独立正式 guard。16 项 owner 定向测试通过。单独的 `monitor_events.jsonl` 兼容现有进度页，并保留 FAIL 与 PENDING 分母；原 events 和原槽不重写。

旧 hardcoded 外部 safety/容量/发布工具不能冒充兼容新的 normal-owner。公开 core/extension gate、registrar、正式 guard 本身可直接读取原计划和原槽；当前正在补最小的公共安全四槽事实生产者与 stat-only 容量收据入口，R0 导出/定标继续复用现有公开工具。正式 280 槽仍必须经过原独立 guard。

还确认公开 `run_research_session.sh` 原先无条件把 `TMPDIR` 改成 `results/runtime/tmp`，因此外层设 `/tmp` 仍会在实际 flight/evaluator 调用时退回 Windows 挂载目录。已改为 `STAGE1_TRANSIENT_DIR` → 继承 `TMPDIR` → 原结果目录默认值，先拒绝非绝对路径再创建目录，ROS 日志仍在 results。新增四项真实 shell 集成检查在 Humble 原生 **4/4 通过**；Windows **4 项平台跳过**。独立静态复审通过。后续原生调用同时显式设 `STAGE1_TRANSIENT_DIR=/tmp` 和 `TMPDIR=/tmp`，防止继承旧的显式覆盖值；仍须核实际运行配置和临时峰值。

公共容量入口 `tools/measure_reliability_v4_storage.py` 已定稿，Windows 最终 **15 项全部通过**，独立静态复审通过。它仅 stat 大文件，核对全部 28 格原小证据、原 source/native PASS、75 s 闭合、lossless 映射及当前大小，保留健康算法 FAIL；收据直接供现有 budget 工具读取。当前只是工具验证，尚无 Humble54 完整 28 格输入或正式容量准入。

公共安全入口 `tools/run_reliability_v4_safety.py` 提供 register/run/check，读取实际 canonical12 和已结束 normal-owner，前瞻登记两类×两歧义情形四槽与实际五命令，不制造旧 candidate/run-core 收据。当前 Windows 新模块 **11 项、1 项符号链接权限 subtest 跳过**；原 guard **48 项通过、无跳过**。新 guard 显式绑定 split-clock 声明、命令、两桥与 DDS 的实际进程/映射库和保存配置。root 在原 Humble53 行人交叉的真实归档上作只读 helper 语义检查：最初因 colcon symlink-install 被普通文件 hash 拒绝，修正为限制链接解析后仍在 frozen root 再核实际字节后，完整桥/DDS 检查返回 true。原记录未改、未重评，也不算新的安全四飞行。

随后 root 在 Humble 原生执行同一新 safety 模块，**11 项全部通过、无跳过（1.771 s）**，其中实际创建了符号链接并走原生分支。这仍是合成证据回归，不是新的四场仿真；真实四场必须等新同源 canonical12 全通过后前瞻运行。
