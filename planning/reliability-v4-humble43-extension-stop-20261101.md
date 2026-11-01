# Humble43扩展停止及下一步取证

2026-11-01。核心12和安全4的既有通过记录保留；扩展16的原始槽均已执行，最终为12 PASS、4 FAIL，但整批未通过后续准入。原生driver于14:02:03.708476 UTC以2退出，Windows进度为STOPPED_FAULT，清理记录无残留仿真进程。正式仍0/280，当前继续做离线故障定位。

| 扩展条件 | 行人 | 汽车 |
| --- | --- | --- |
| 深度噪声 | PASS | PASS |
| 深度空洞 | PASS | PASS |
| 检测丢帧 | PASS | PASS |
| 通信延迟 | PASS | PASS |
| 组合故障 | FAIL | FAIL |
| 加减速：速度控制 | PASS | PASS |
| 加减速：位置控制 | FAIL | PASS |
| 远距离 | PASS | FAIL |

行人组合故障、行人位置控制加减速、汽车组合故障是原冻结函数接受并保留的压力算法FAIL。最后汽车远距离的source-clock和native-startup不通过属于硬证据门失败，原合同明确拒绝；不能扩大前述允许范围，也不能将四个FAIL全称作可接受算法失败。原终态`terminal_count=15`与16个真实槽文件有不同含义：最后attempt在完整审计完成前被拒绝，统计12/4仍保留全部原始结果。

汽车延迟距离/高度RMSE为0.761595/0.168965m，速度控制加减速为0.614883/0.160255m，位置控制加减速为0.636575/0.173637m，三者末端稳定均通过。汽车组合故障在34.86s提前LOST，早于42.86s的长遮挡；距离RMSE2.210805m，重选后42.776s持续跟踪通过但不抵消FAIL。它和行人同一时刻提前丢失的现象相符，尚不能仅凭此替代完整传输因果证据。

最后汽车远距离实际完成飞行与归档，距离/高度RMSE0.655091/0.180627m，原flight_exit0、infrastructure_stop=false。失败细节是：

- source-clock记录9173 raw、9173 timing、9174 adapted；9173个三元组均有效，但额外1条adapted未被原匹配消耗。报告clock_domain_valid及vehicle_frame_continuity_valid为true，不代表整个source-clock通过。
- native-startup的1846条phase中，1条`最新已录clock − phase.source_sim_s`超出原`[-.05,.50]s`门（容差1e-9）。其他起飞、原生模式顺序、交接与稳定检查通过。报告没有保存该条具体时间或超界方向。
- source-clock sidecar只逐diagnostic列出成功/失败匹配；native sidecar只保存交接窗口，均不能独自定位上述两条记录。

启动边界是待查疑点：source-clock连续性区间从第一条raw delivery 0.572s起，但未配对adapted检查覆盖全部消息；native起飞区间始于4.7s，phase时间门却覆盖全记录。现有启动图已检查clock/raw/timing/adapted的录包端点、QoS、GID及稳定时间，不能说它们缺少订阅屏障。phase也没有构造时锁存发布。尚无原生证据证明异常在启动处、两个FAIL同源，或真实源时钟出错。

下一步复用冻结原函数，在独占窗口串行读取原source-clock四话题和native-startup九话题，保留各自过滤序号，定位未消耗adapted及唯一异常phase，并导出相邻clock/raw/timing。只读原录包，不解码图像、深度或真值，不运行控制或推理。按证据决定修复，保留原FAIL和全部门限；新验证使用新的具名输出，不能覆盖或补写这次原槽。

9份原始小JSON及16槽状态/摘要已收入[原件快照](../tools/diagnostics/humble43_extension_stop_snapshot01/README.md)，manifest SHA为`5a112ecf36ca47adf2a9c9b337ac009918da55d5af993a99d3f7b4575189ad54`。原driver还保留owner与immutable-copy比较错误；当前不将派生拒绝当作独立归档损坏根因。

完整28格容量采集、定标与正式发布暂不执行，因为其真实前置条件未满足。已经准备的容量脚本仍未执行，不能用它宣称空间足够。新物理身份恢复补充工具仅完成Windows合成测试和只读审查，真实前瞻协议、原生测试和正式附件仍待后续有效窗口。
