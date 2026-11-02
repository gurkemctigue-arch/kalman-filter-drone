# 离线时延统计修复 v2

本版修复控制器信息龄统计：悬停、丢失或失效状态默认填写的 `0.0` 不再当作零时延观测。只有实际 FOLLOW/PREDICT 状态、合法轨迹及一致的状态字段才能提供已知信息龄；有效 FOLLOW 的真实零值仍保留。全部原状态机会继续计入分母，不可评价值为 `null`，并报告原因。

生产代码相对 v1 仅增加 11 行资格判断，未改变其他统计端点、输入来源校验或在线算法。v1 及历史导出保持原样。原始标准库合成测试为 48/48，本版为 56/56，均在 Windows Python 3.12.3 实际通过；原始测试记录及日志随目录提供。这些测试包含模拟原生读取器，不能作为实际 ROS 消息、录包时延或飞行验证。

可独立复验，无需 ROS 或实际录制：

```bash
cd tools/offline_evaluation/timing_v2
python -B offline_pipeline_timing.py describe
python -B -m unittest -v test_offline_pipeline_timing test_offline_pipeline_timing_independent01
```

后续实际分析须用本版 `export` 写入全新的外部目录，再由同一本版 `analyze` 消费新 context 的实际 SHA。不得修改旧 context 的工具哈希以复用旧导出。资源、冻结源、原录制和输出保护要求见 [交接说明](HANDOFF01.md)。目前本版尚未用于实际录包分析。

项目另有 `navigation_reference_evaluation.json` 中的 `visual_control_metrics.image_to_first_tracking_command_sim_s`，用于报告图像采集至首个有效跟随控制周期的仿真源时钟间隔。它由状态时间减预测龄还原源图，按任务/轨迹/源时刻去重，并采用同轨迹、前序不超过 150 ms 的状态关联；控制命令与状态使用同一 tick 时间。这是既有工程关联指标，不能解释为精确消费或发布完成时间、物理墙钟时延或 PX4 实际效果时延。未记录的严格因果端点仍为未知；本修复不新增 PX4 ACK 要求或飞行验收门。

`snapshot_manifest.json` 记录复制文件的原路径、字节数和 SHA-256；`.gitattributes` 保留原字节。测试记录中的绝对路径是来源说明，克隆后不会自动有效。`synthetic_differential01.json` 为合成差分，不是实验结果。
