# 独立物理身份恢复补充工具 v1

本目录只补充“恢复消息是否有独立物理身份支持”的离线描述，不改冻结43、原评价、原PASS/FAIL、原身份单元、原正式协议或报告生成器。实现及CLI仅使用Python标准库，不导入NumPy、YOLO、ROS，不读取bag，不运行仿真、推理或构建。**尚未生成真实补充protocol或分析任何真实试验。**

实现见[physical_recovery.py](physical_recovery.py)，微型合成边界测试见[test_physical_recovery.py](test_physical_recovery.py)。绑定、原导航网格及原身份分母检查沿用[原任务阶段分析](../../../scripts/analyze_task_phases_v4.py)的思想，保持独立附件；本工具不充当原runner的计划校验或正式准入工具。

无副作用的描述命令：

```text
python -B physical_recovery.py describe
```

真正执行须等主流程生成、验证真实FORMAL120计划后，在原生Linux环境且首条正式START之前，串行安排下列步骤。示例路径是占位符，不能用合成计划冒充真实登记；本工具不会启动正式飞行。

```text
python3 -B physical_recovery.py protocol --core-plan /actual/formal120/plan.json --core-sha256 ACTUAL_SHA256 --output-dir /new/external/protocol-directory
python3 -B physical_recovery.py analyze --protocol /new/external/protocol-directory/physical_recovery_protocol.json --protocol-sha256 ACTUAL_PROTOCOL_SHA256 --output-dir /new/external/appendix-directory
```

登记绑定实际计划文件SHA、内部digest、工具代码SHA、规则和UTC，以及全部40个`stage2_crossing`/`stage3_multi_active`原槽。每槽登记short及long后的显式重选两个机会，共80；不是80次新飞行。必须确认原120个槽均无START、terminal或试验产物，计划保持在原`output/plan.json`，父目录在当前原生平台可访问。Windows不能以看不到`/root`、`/mnt/d`路径证明未开始。分析再核对协议早于所有原120个START及代码/计划字节；晚登记、缺START却已有产物或不同来源均拒绝。实际协议登记依赖原主流程的独占调度，不提供跨进程原子锁或外部时间见证。

每个原槽只读取原terminal、`physical_identity.json`、`navigation_reference_evaluation.json`、`navigation_reference_evaluation.frames.jsonl`、`telemetry.jsonl`和`summary.json`。原terminal内部digest、逐文件artifact SHA及navigation→physical SHA必须匹配。JSON/JSONL完整读到EOF并校验读取前后大小/mtime；拒绝NaN、重复JSON键、过长记录及保留行数超限，不接受截断前缀。所有计划槽及全部来源路径始终列出；缺terminal、停止、缺报告或哈希不符保留原机会，时间为null。输出目录必须全新，且解析符号链接后也不能进入冻结源码、原results、原plan、原trial或工具源码目录。

short锚点为原短遮挡open请求，观察至open后3个ROS仿真秒。显式重选只认`explicit_reselection_requested`，初选仅是背景；新描述窗从request起3秒，包含等待确认的时间，**这不是原显式重选验收门**。两类窗口均截于下一REQUEST或原录制终点；下一REQUEST截点为右开，不能在新任务生效时把同tick旧任务消息计为恢复。close时原任务按完整请求表确定并交叉检查原身份单元；CLEAR/RESET、任务边界不确定以及遮挡中任务改变均保留，后续候选不能凭旧REQUEST复活失效任务。

候选使用monitor的`navigation_state`、`state==1`，分别保留源`stamp_s`及仿真接收`time_s`。两者都须在窗口内，任务UUID吻合，track ID为规范正整数，向量/年龄有限，`age+receive-source<=0.75s`，不接受未来源时间。**monitor没有保存frame_id，本工具只验证可观察字段，不能声称完整复现原navigation_valid。** 原`.15s`是10Hz选流超时，在此仅作为独立导航接收流覆盖诊断；不是传输时延上限，也不是物理证据覆盖率。`active`、PREDICTED以及同一10Hz单元相交都不能代替MEASURED或证明来自同张图像。

物理join键固定为`(源秒数按Decimal(str(x))取ROUND_HALF_EVEN微秒整数, UUID, 规范track ID)`，精确连接`selected_identity_timeline`；不挑最近帧。重复navigation MEASURED键或重复identity键即UNKNOWN，即使副本相同。当前冻结发布器只有接受本时刻测量且surface为MEASURED时才发布navigation MEASURED；普通50Hz预测state2不参与重复测量计数。本工具不自行放宽将来可能变化的重复发布语义。

独立身份只认`match.status==known`且physical ID存在，优先使用`conservative_task_time_identity.tasks`的请求→物理个体映射；完整表中的UNKNOWN不从仅已观测任务的旧表补齐。非空映射冲突使相关机会INCOMPLETE，其他独立机会继续保留。尊重原shutter请求区间及含端点±1秒保护，未完成区间无限延伸；保护内身份保持UNKNOWN，不重算或放宽原几何规则。

逐事件分别保存首次合格MEASURED的SAME/WRONG/UNKNOWN、之后首次有证据确认原个体的接收/源时间、全部已知异目标证据、原始键及行号、UUID、独立映射、源哈希、登记/实际事件数、缺证原因和右删失。首次未知不会被后来的正确倒填；先错误后正确仍保留错误，不能洗白。显式重选另外区分“选回原个体”和“忠实跟随新请求”：合法选择另一人/车称DIFFERENT_FROM_ORIGINAL，只有偏离新请求独立物理映射才称WRONG_REQUESTED_ACTOR，不自动计作系统ID Switch。这仍是用户/脚本选框辅助评价，不是自动ReID。

主数为“窗口内有原物理目标证据且无已观测异目标证据的机会数/全部登记机会数”，仅为描述性观察下界。UNKNOWN与缺失不移除，不宣称连续身份安全成功率。另列ever-supported、异目标、请求忠实和实际事件数（缺报的实际计数为未知，附已知槽数/计划槽数）；确认耗时只汇总有证据事件并附n/N，未恢复不填0。

分析仅生成独立JSON、CSV、Markdown附件；后续由统一交付入口引用。原报告生成器不会自动消费本附件。未来如工具代码或规则改变，需要在正式开始之前另行前瞻登记；不得改写已用的协议日期或原结果。

可选微型合成复验（只创建临时目录内的合成JSON，无真实protocol或试验）：

```text
python -B -m unittest -v test_physical_recovery
```
