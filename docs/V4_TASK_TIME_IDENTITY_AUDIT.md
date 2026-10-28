# 指定个体的完整任务时间分母

`scripts/evaluate_physical_identity.py` 新增 `conservative_task_time_identity`。它补齐旧指标的时间覆盖缺口：旧 `conservative_selected_identity` 只统计实际存在的 detection diagnostic 帧，并且任务要等到 snapshot 出现才建立。因此，诊断流完全停止后的尾段、已 REQUEST 但从未 CONFIRMED 的任务，不能仅靠旧 `known_coverage` 判断身份保持。

新审计从第一次显式 REQUEST 到 rosbag 中最后一条 `/clock`，按首 REQUEST 锚定的 0.1 秒半开时间单元覆盖整个区间。单元数为 `ceil((end-start)/0.1)`，计算时仅用 `1e-9` 容差消除浮点整数边界误差；最后不足 0.1 秒的单元仍保留。分母不取最后一次诊断、最后一次成功匹配或最后一次选定状态。没有 `/clock`、时钟回退、没有 REQUEST 或 REQUEST 后没有正时长时，结果为 `INCOMPLETE_EVIDENCE`，coverage 和正确率下界为 null。

任务由实际 `/tracking/selection` 的 REQUEST 创建，不要求存在任何 snapshot。预期物理个体仍独立由 REQUEST 框在其原始 `image_stamp_s` 的真值投影建立；不能从 tracker 选中的框反推。CONFIRMED 使用测试脚本记录的 `initial_selection_confirmed` 或 `explicit_reselection_confirmed` 事件。仅有稳定 UUID、已发送 REQUEST 或已知请求框，不代表系统已经确认目标。

每个时间单元采用保守证据规则：

- 尚未确认、请求框无法独立映射、CLEAR/RESET 后、任务边界跨入单元，或单元内没有新鲜身份帧，记为 unknown。
- 对已确认且独立初始化已知的任务，单元内任何已知错误物理匹配优先记为 wrong，不能通过挑选同单元最后一张正确框隐藏短暂错跟。
- 其余只有单元内全部身份证据都已知且正确时才记为 correct；同单元含 unknown 的证据仍为 unknown。
- 不跨单元插值、前向填充或复用旧框。诊断流停止后，录制时钟继续覆盖的尾段全部为 unknown。

采样单元归属其开始时的任务；新 REQUEST 会创建新任务，单元内发生任务切换则不凭混合证据确认正确。重复使用 REQUEST UUID 标为歧义，不能作为新任务的身份认证。CLEAR/RESET 后到下一次 REQUEST 之间保留在总分母中，记为 unknown。

新字段的主要结构为：

| 字段 | 含义 |
| --- | --- |
| `coverage_basis` | `fixed_10hz_request_to_recorded_clock_end` |
| `interval.start_s/end_s` | 首 REQUEST 与最后 `/clock`，结束端点不包含在单元内 |
| `scheduled_samples` | 全部固定时间单元数，等于 correct + wrong + unknown |
| `known_coverage` | (correct + wrong) / scheduled_samples |
| `retention_lower_bound` | correct / scheduled_samples |
| `requested_task_count` | 实际 REQUEST 数量，包括从未被确认的请求 |
| `unconfirmed_requested_tasks` | 没有有效 CONFIRMED 的 UUID 列表 |
| `tasks` | 每 UUID 的请求时间、源图时间、确认时间、独立预期物理个体及计数 |
| `unknown_reason_counts`、`timeline` | 未知原因与各时间单元的可追溯结果 |

旧逐帧 MOT、物理身份匹配与 `conservative_selected_identity` 保留，继续用于检查图像中的具体错跟和帧级诊断。新固定时间分母用于覆盖率和全任务保持率下界；两种指标不能替换名称混报。旧的冻结报告没有该新字段，在实际重新运行离线评价前不能声称已经通过新审计。本次没有重新读取任何 rosbag。

CLI 新报告的 `evaluation_source` 保存实际 evaluator 及其五个直接本地依赖的 SHA-256：`evaluate_stage1_flight.py`、`extract_research_recording.py`、`research_labels.py`、`research_metrics.py`、`stage2_identity.py`。这份离线评价来源与飞行冻结代码分别登记；对旧飞行包运行新的只读审计，不能冒充旧飞行已经使用新代码。

`tests.test_physical_identity_evaluator` 增加9项专项，覆盖停止诊断后的时钟尾段、从未确认且从无 snapshot 的请求、待确认时段、混合未知帧、短暂错跟、显式重选、最后部分单元、CLEAR/RESET/任务边界和缺失/回退时钟。与既有 evaluator、stage2 identity 测试合计22项通过。它们使用纯数据 fixture，不启动 ROS/Gazebo/PX4。
