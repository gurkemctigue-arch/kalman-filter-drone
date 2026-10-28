# 评价修订 3：接收时钟与派生运行时间分开审计

新一轮研究使用冻结名称 `fullplan_v2`；其中评价器使用 `evaluation_revision: 3`。研究版本与评价版本分别标记，不能混用。

## 三种时间证据

`record_sequence` 表示 bag reader 的实际读取顺序，用于确认前后、持续追踪窗口和事件先后。`received_sim_s` 表示录制时最近一个 `/clock` 值，是近似接收时钟。消息 header 有各自语义：MEASURED 保留图像采集时间，PREDICTED 使用预测时刻。

原先声明的 `max(header stamp, received_sim_s)` 派生运行时间继续用于区间起止、时长及相关指标，不在本修订全面重定义。这种混合时间允许回退，因为预测 header 可能略领先 recorder 最近收到的 `/clock`，而随后 MEASURED 又保留旧图像 header。

v1 汽车 raw bag 的真实例子如下，四条状态都属于同一新目标 UUID 和 track 2：

| 读取序号 | 状态 | header（秒） | received_sim_s | 派生运行时间 |
| --- | --- | --- | --- | --- |
| 28883 | PREDICTED | 55.240 | 55.224 | 55.240 |
| 28887 | MEASURED | 55.100 | 55.224 | 55.224 |
| 31760 | PREDICTED | 60.640 | 60.624 | 60.640 |
| 31762 | MEASURED | 60.500 | 60.624 | 60.624 |

两次派生时间各回退 16 ms，实际接收时钟没有回退。不能把这种异步组合直接判成安全失败，也不能通过增加 epsilon 或放宽测量新鲜度来处理。

## 硬检查与诊断

修订 3 保留修订 2 的完整 reader 序号边界：确认前的记录排除；确认记录及其后所有状态和控制纳入，不论其派生时间是否与确认相同或回退。确认后的 LOST、歧义、错误 UUID 或非法轨迹继续失败。首个 active 状态不能被后续正确记录追认。

`chronological_state_and_control_evidence` 的时间依据明确改为真实 `received_sim_s`。生产入口在排序前给所有记录补全或保留序号，将窗口内状态和控制按全局 reader 序号合并，检查接收时钟有效且不回退。比较基点是确认记录自身的接收时钟，不能用可能略领先的派生确认时间。真实接收时钟回退为 FAIL；缺失、非有限或负接收时钟为 INCOMPLETE_EVIDENCE，不能通过。

保留 `state_time_regression_count` 和 `control_time_regression_count` 作为派生时间诊断，并增加真实接收时钟回退计数、无效计数、比较依据和作用范围。精确状态列表索引的独立内存调用只具备各流顺序，单独标记 `PER_STREAM_IN_MEMORY`；正式评价入口统一保留全局序号。

不修改 `.75 s` 预测/接受新鲜度、`.60 s` 输入新鲜度、既有未来时间容差、控制宽限、持续时间、证据间隙、模型参数、轨迹或资源。此修订不依据跟随误差调参。

## 证据保留与新研究

原 v1 八次试验及其 7 个原 PASS、1 个原 FAIL 保留。`offline_evaluation_revision2.json` 的独立 FAIL、来源审计及两次回退的 chronology sidecar 也保留。修订 2 的源码和测试归档在 `results/evaluation_revision2_source/`，与当前源码分开。

修订 3 对同一原始 bag 的核对另存 `offline_evaluation_revision3.json` 和 `.audit.json`，不重飞、不覆盖已有报告，也不回写 v1 子清单。审计区分原 plan 文件字节的 `original_plan_file_sha256` 与 plan 内的 `original_plan_canonical_sha256`；两者不同是正常的。原 FAIL 文件的前后字节 SHA 必须一致。

预注册 `study_revision` 明确评价修订 3 的时间契约。正式 `fullplan_v2` 主研究重新执行全部 166 次，不复用 v1 八次录制。独立后处理重评价不能替代新的研究重复。

## 针对性验证

测试覆盖两组真实 16 ms 异步样例通过、真正接收时钟回退失败、跨状态与控制流的接收时钟回退失败、无效时钟不能通过、预测状态作为尾窗锚点使用自身接收时钟，以及同时间戳和回退时间的坏状态继续失败。测试不启动仿真；真实 bag 核对使用 D 盘临时解压目录并保留来源 SHA。
