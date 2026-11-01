# Humble43 第 3 槽身份未知解释快照

本目录仅归档 `person_stage2_crossing_seed004` 的只读核查小收据，不包含原始大报告、逐帧 sidecar 或 rosbag，不改变评价门槛、旧证据及算法结论。

主指标为 `physical_identity.json.conservative_task_time_identity`：固定 10 Hz 任务时间分母 **753 格 = 649 正确 + 0 错误 + 104 未知**。普通诊断的 651/753 不能替代该口径。

| 显式选择任务 | 主分母 | 正确 | 错误 | 未知 |
|---|---:|---:|---:|---:|
| 首次选框 | 322 | 218 | 0 | 104 |
| 长时丢失后重新选框 | 431 | 431 | 0 | 0 |

104 格未知全部属于首次任务：请求尚未确认 1 格、任务切换边界 1 格、保护窗内几何身份不可认证 30 格，以及无新鲜选中目标证据 72 格。后者中 44 格在遮挡保护窗内、28 格在窗外。

除两格请求/任务边界外，其余 **102 格的独立几何真值完整**；未知不表示报告文件或 GT 丢失。保护窗包括遮挡请求前后的保守缓冲，不能说其中每帧都实际被挡住。“无新鲜选中目标证据”也不足以归因为 YOLO 或通信故障。两次任务均独立映射至同一物理行人，但 UUID 本身不是物理身份凭据。

零观测错误不代表全部时间身份正确，更不代表整个项目通过。重选后的 431 格全部已知正确仅描述本槽该任务，不能推及其他试验。

本机原报告目录为：

`D:\基于yolo和卡尔曼滤波\results\frozen_fullplan_v4_humble43\reliability_v4_humble43_probe01_person_stage2_crossing_seed004\`

主要依据是该目录的 [physical_identity.json](D:/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_person_stage2_crossing_seed004/physical_identity.json) 及 `physical_identity.frames.jsonl`，并核对阶段二、飞行与导航评价。上述绝对路径只在保留原数据的本机有效；克隆仓库不会获得这些外部数据。收据包含五个依据文件的字节数与 SHA256。

收据由外部原文件逐字节复制，大小 12,484 字节，SHA256 为 `4fcd4b8cd1c755d596d013aca8da97006238517b3723d2cbba847a35f52e9dc1`。本快照未执行生产代码、bag 读取、WSL、飞行或新增测试。`SHA256SUMS` 覆盖本说明与收据，不覆盖校验表自身。
