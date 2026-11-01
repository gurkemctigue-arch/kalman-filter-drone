# Humble43 扩展批次停止原件快照

原生批次于2026-11-01 14:02:03.708476 UTC结束，`returncode=2`。16个原始槽文件为12 PASS、4 FAIL；完整通过外层审计的计数为15，最后一条attempt明确因原source-clock/native-startup报告未PASS而拒绝。不能把16个槽文件存在解释为16次完整审计通过。

本目录9份JSON为原始文件的逐字节副本，合1,493,000字节。路径、SHA、全部16个槽的原状态及摘要见[manifest.json](manifest.json)；复制时核对副本和原件SHA一致。未复制bag、图像、完整遥测、health日志或私人系统事件XML。

最后汽车远距离槽完成飞行、录制和归档，flight_exit0、infrastructure_stop=false，但原工程FAIL：[source-clock](px4_source_clock_report.json)有9173个有效三元组和1条额外未配对adapted odometry；[native startup](native_startup_report.json)有1条phase时间超出原`[-.05,.50]s`门，其他起飞/交接检查通过。原始诊断尚未定位这两条记录，不认定它们同源，也不认定为真实时钟域错误或控制失败。

[原终态](original_execution_terminal.json)保留原始退出、owner/copy错误与空残留进程清单；[最后attempt](car_far_original_attempt.json)保留审计拒绝。该失败不属于冻结合同可接受的压力算法FAIL。当前不能运行要求扩展健康闭合的完整28格collector、定标或正式准入。

后续只在独占窗口读原始clock、raw、timing、adapted和phase，保持原过滤序号及原门，定位异常后再决定修复。原失败和所有历史证据保持不变。本快照不是新验收或容量准入。详细说明见[停止与诊断记录](../../../planning/reliability-v4-humble43-extension-stop-20261101.md)。
