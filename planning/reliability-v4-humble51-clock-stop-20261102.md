# Humble51 核心批次停止与时钟诊断

北京时间 **2026-11-02 19:10:29**（UTC 11:10:29），原核心命令监控生成 `STOPPED_FAULT`、退出码2。原核心12场为 **3 PASS、1 FAIL、8 PENDING**，正式研究仍 **0/280**。第四场 `person_stage3_midpoint_seed004` 已有原始FAIL和外层停止记录，不能继续使用18:58的“第四场运行中”快照描述当前状态。

前三场工程PASS与对应外层核验继续保留，原Humble50的11 PASS/1 FAIL独立保留；不把不同来源的通过场景拼接成完整核心。原计划、失败槽、未知样本、记录缺口和外层异常均不覆盖、不重试。

- [停止原小JSON快照](../tools/diagnostics/humble51_clock_stop01/README.md)与[原路径/SHA清单](../tools/diagnostics/humble51_clock_stop01/manifest.json)
- [本机原核心命令终态](../results/project_progress/humble51_core_run01/index.html)与[原槽进度页](../results/project_progress/humble51_core_slots01/index.html)
- [停止前的18:58检查点](reliability-v4-humble51-validation-20261102.md)，该原文不追写新状态

## 为什么停止

第四场原槽于UTC 11:09:48.320622完成，状态为 `COMPLETED/FAIL`、`engineering_result=FAIL`、`flight_exit_code=0`、`infrastructure_stop=false`。这些字段说明飞行程序正常结束，不能据此宣称独立时钟和证据合同通过。实际负评价为 `source_clock` 和 `native_startup`；没有待评价或被省略的不完整报告。

| 独立评价 | 实际记录 | 保留的合同 |
| --- | --- | --- |
| source-clock源时间 | 4次 `future_or_wrong_domain_source_timestamp`；在线拒绝与独立重算一致 | sample/publication相对adapter receipt最多未来50 ms |
| timing诊断交付 | 1次 `diagnostic_delivery_outside_clock_contract` | delivery减receipt须在−50至+500 ms内 |
| raw/timing配对 | 2条raw没有匹配timing diagnostic，列为incomplete | 原始精确timestamp pair必须完整配对 |
| native记录覆盖 | 1次 `phase_source_time_stale_or_future`，`full_recording_coverage=false` | phase delivery减source须在−50至+500 ms内 |

native的参数、起飞命令、命令顺序、PX4模式序列、地面就绪、handoff稳定和handoff后的视觉任务检查均为true。source-clock已有9320组独立匹配的raw/timing/adapted三联记录；raw和matched odometry最大记录间隔约92 ms，低于500 ms连续性门，尾段覆盖到93.816 s。这些通过项不能抵消4次实际源时间拒绝、1次交付越界或两条缺配对。

外层第四attempt于UTC 11:09:57.452891保留错误：`Original source-clock/native-startup evidence must independently PASS`。它按硬门停止后续场景；原3/1/8状态未被改成其他结果。当前证据不足以把这次停止解释为YOLO、卡尔曼滤波、跟随控制或云台算法性能故障。

## 已定位的共同窗口及解释限度

只读扫描原 `px4_source_clock_report.frames.jsonl` 后，4次future拒绝和1次diagnostic交付越界集中在同一窗口。这里的record序号属于source-clock评价器过滤后的读取序列；不能直接当作任意另一组topics的全bag序号。

| 侧车行 / diagnostic record | sample / publication / s | adapter receipt / s | recorder latest Clock / s | 原记录异常 |
| --- | --- | ---: | ---: | --- |
| 8351 / 48299 | 84.076 / 84.080 | 84.028 | 84.028 | publication未来52 ms |
| 8352 / 48300 | 84.092 / 84.096 | 84.028 | 84.028 | 未来68 ms |
| 8353 / 48301 | 84.108 / 84.112 | 84.028 | 84.028 | 未来84 ms |
| 8354 / 48302 | 84.120 / 84.124 | 84.028 | 84.028 | 未来96 ms |
| 8355 / 48305 | 84.128 / 84.136 | 84.116 | 84.028 | 此条被接受，但delivery减receipt为−88 ms |

下一条的delivery为84.120 s，再下一条恢复到84.152 s；该窗口附近 `reset_counter` 始终为12。已有侧车未显示该处车辆参考系reset。以上事实使节点Clock回调、recorder观察到的Clock与消息排队顺序成为具体待查项，但尚不能据此确定它们与phase异常、两条缺配对具有同一根因。

native侧车只保存22个handoff-readiness样本，均ready，不包含后程phase覆盖失败的具体行。source-clock侧车按diagnostic逐行保存，也没有列出那两条“没有diagnostic的raw”的timestamp pair。因此随后进行了下述原包诊断，保留原50 ms门限和原失败。

## 随后完成的原包只读诊断

一次原生只读遍历实际用时37.007秒，仅解码上述五个时钟/里程计/阶段topic，共55814条消息；各topic计数与原归档报告一致，受保护原报告、配置、bag元数据及压缩包的前后SHA完全相同。421条窗口记录、诊断摘要与实际脚本已附在[只读诊断附件](../tools/diagnostics/humble51_clock_stop01/native_readonly/summary.json)，未重新判定原试验。

两条缺失配对的sample/publication分别为84.040/84.048秒、84.052/84.060秒，均在上述窗口。唯一phase越界记录为source 84.100秒、recorder最新Clock 84.032秒，差为−68 ms。4次future、1次diagnostic交付越界、两条缺配对和1次phase越界由此全部定位到同一时间窗口。

Clock源数值仍按4 ms推进，没有超过20 ms的源步长缺口；但Clock 84.028到84.032秒两条消息的原recorder时间戳间隔为**0.916707468秒**，期间先收到一批raw odometry，随后Clock消息批量补到。这区分了源步长完整与交付及时性：不能把完整归档理解为时钟交付无停顿，也不能单凭这一包定位暂停发生在publisher、DDS、执行器还是recorder。

原observer在UTC 11:01:29.276–11:01:32.277的4个资源样本中，`MemAvailable`约13.23 GiB，swap全空、OOM计数为0，memory PSI为0；整体CPU忙碌约16%–25%。observer采样间隔约1秒，队列及丢弃均为0。没有内存耗尽或整体CPU饱和证据；这些1秒聚合样本仍不能排除不足1秒的局部调度停顿。完整health记录保存在原本机归档，未将其整体上传。

## owner异常不是原始归档被改写

整批外层还保留 `Owner outcome differs from original immutable D copy candidate`。独立复核区分了两个真实生命周期阶段：

- D盘小文件 `observer_driver/execution_terminal.json` 是原始 `COPY_VERIFIED_PENDING_OWNER_CLOSURE` 候选，仍保持原字节。
- 最终外层中的owner状态是 `NATIVE_FAILED_RAW_ARCHIVED`，`driver_exception=true`、`healthy_cleanup=false`，对应原核心验证异常退出路径。

两阶段归档均保留。archive记录的4份local/archive文件的SHA和字节数一致，状态为 `VERIFIED_COPY`；原归档字节核对正确。面向成功路径的healthy验证拒绝该失败终态，不意味着原copy候选被篡改，也不能反过来把失败owner当作healthy通过。整批最终清理记录没有残留进程；这不改变原FAIL和失败路径状态。

最小快照保留了小copy候选、native退出终态和归档清单；未打包约318 KiB的完整外层或约27 MiB的health JSONL。完整原件继续位于本机，原错误文本保留。

## 下一步最短工作顺序

1. **原包只读诊断已完成。** 五个topic全程扫描、两条缺配对和phase异常定位、窗口提取及原包前后字节核对均已完成；不重复解压或重新飞行以替代这次失败。
2. **验证时钟交付隔离方案。** 当前同一`parameter_bridge`承载Clock、RGB-D、真值和云台流，适配器raw订阅使用小深度的sensor QoS。检查独立Clock桥、队列和执行器的实际影响，以有限组件压力或单场验证区分改进效果；共用桥及小队列目前是待验证因素，不能写成已确定根因。
3. **按证据修复并验证。** 若需改代码，先形成能复现原异常的最小测试或组件验证，再完成相应原生验证；不通过放宽时效、删除行、重写原report或借用旧批次PASS获得通过。本记录没有宣布新来源已冻结、Humble52已启动或主因已确定。
4. **恢复后续完整验收路线。** 只有新来源实际通过同源核心12及健康闭合，才继续安全4、扩展16、真实28格容量和R0定标、独立final-root、首次正式START前的协议登记与正式280场，再完成统计、视频、最终Word/PDF和统一交付。

原实验脚本不再运行该核心批次；继续进行的只读诊断与开发工作是后续工作，不应称原批次仍在自动飞行。
