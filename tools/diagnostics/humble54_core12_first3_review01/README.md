# Humble54 canonical12：前三场小文件独立审查

本目录只审查原 `person_stage1_velocity_seed004`、`person_stage1_position_seed004` 和 `person_stage2_crossing_seed004`。原 slot、原计划和不超过 1 MiB 的 JSON/log 证据支持这三场按已登记工程门槛取得 PASS；这不表示所有原报告的状态都是 PASS，也不表示 canonical12 或后续正式矩阵已完成。

实际校验记录见 [review_receipt.json](review_receipt.json)，收集代码见 [collect_small_evidence.py](collect_small_evidence.py)。本次校验了原 slot 清单中的 **127 个小 JSON/log 文件（42 + 42 + 43）**，其实际 SHA256 均与原 slot 记录相符。没有覆盖或修改任何原件。

| 原场景 | 距离 RMSE/m | 高度 RMSE/m | 有效导航覆盖 | 六项工程门槛 |
| --- | ---: | ---: | ---: | --- |
| person velocity | 0.772993 | 0.149616 | 688/752，91.49% | 全部符合 |
| person position | 0.758464 | 0.166427 | 689/752，91.62% | 全部符合 |
| person crossing | 0.885960 | 0.173842 | 670/752，89.10% | 全部符合 |

三场真值覆盖均为 752/752，距离和高度最终持续稳定标记均成立。原 source-clock 和 native-startup 报告为 PASS，原脚本及依赖摘要与计划一致；原运行配置、flight argv、源码快照及清理记录无矛盾。204 项源码/模型/DDS 快照与原完整冻结 map 对应，包含原有 17 项额外副本。本审查不证明每个历史飞行进程实际导入了哪个模块。

三场 navigation 原报告状态均为 `RECORDED_WITH_CENSORED_FAILURES`。第三场 physical identity 原状态为 `RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS`：小 slot 所嵌完整任务时段统计为 **649 正确、0 错误、104 未知，共 753 个样本，覆盖 86.19%**。原小日志中的 **651/0/101，共 752 帧**是另一组诊断分母，不能替代完整请求时段。

第三场 `physical_identity.json` 为 1,663,576 字节，超出本轮边界，本审查没有读取或重新计算其摘要。root 已直接读取该大报告并提供逐任务值：任务 1 为 219/0/103，共 322，覆盖 68.01%；任务 2 为 430/0/1，共 431，覆盖 99.77%。本审查仅核对这组父代理提供数字的加和，**没有独立复核大报告或逐任务值**。论文应保留逐任务差异，不能把汇总超过 80% 写成每个任务都超过 80%。

本次未读取或重新计算大 telemetry、任何 JSONL sidecar、bag、模型二进制、VHD 或超过 1 MiB 的 ROS 日志；未启动 WSL/native、原评估器或目标代码。录包完整性和清理结论限于原小报告记录，未重新解包或评价原始录包。后续槽、汽车、云台、安全四场、正式准入和算法优越性均不属于本次结论。
