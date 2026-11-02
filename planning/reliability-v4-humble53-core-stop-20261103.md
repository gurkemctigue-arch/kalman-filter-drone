# Humble53 核心批次停止及后续工作

截至 **2026-11-03 01:51 北京时间**，本轮核心批次已处于 `STOPPED_FAULT`，不再是运行中。12 个原始开发槽为 **7 PASS、1 FAIL、4 PENDING**：六个行人场景及汽车速度跟随 PASS，第八场汽车位置跟随 FAIL，汽车交叉、中位云台、主动云台、多目标主动云台四场尚未执行。正式研究仍为 **0/280**；这批不是十种子正式重复，不能替代完整核心、安全、扩展和正式关口。

## 原始停止证据

原矩阵位于 `results/frozen_fullplan_v4_humble53/reliability_v4_humble53_probe01_seed004_matrix`，冻结来源仍为 `bcc012f8fe4c5139eda51f68a47a35396d417ee8`。本次只更新公开文档并复制具名小原件，不改该冻结来源、原槽、评价或门限。

| 原件 | 原始结果与边界 |
| --- | --- |
| 第八场 `car_stage1_position_seed004` | `COMPLETED / FAIL`；`infrastructure_stop=false`，原终态为 2026-11-02 17:49:01.456477 UTC。进程/录制结束不能等同工程通过。 |
| 来源时钟 | `FAIL`：8 次 `diagnostic_delivery_outside_clock_contract`、1 次 `odometry_delivery_outside_source_freshness`。9246 组 raw/timing/adapted 三元组可配对，未把交付时效失败改成缺数据或通过。 |
| 原生起飞与阶段时间 | `FAIL`：3 次 `phase_source_time_stale_or_future`；原生起飞、指令/模式序列及交接稳定等子检查通过，完整录制覆盖检查未过。 |
| 表面跟随 | 原 `surface_flight` 为 `FAIL`，短、长遮挡记录均存在。与时钟/阶段时间失败分别保留，不预先合并为同一个原因。 |
| 录制闭合与 bag 完整性 | 两份原报告均 `PASS`；仅证明各自范围，不能抵消行为或时效失败。 |
| 第八场外层 attempt | 保留原 `audit=null` 及 `Original source-clock/native-startup evidence must independently PASS`；未补造闭合审计。 |
| 核心外层终态 | `STOPPED_ORIGINAL_ATTEMPTS_RETAINED`，`returncode=2`；原 `attempt_count=8`、`terminal_count=7` 与实际原槽的 8 个终态分别保留。第八场 audit 缺失，不能为了统一计数修改原记录。 |
| 双桥补充 sidecar | 原 `returncode=2`，虽然 `error=null`、`final_errors=[]`，仍绑定原故障终态，不能称健康 PASS。 |

外层另外记录 `Owner outcome differs from original immutable D copy candidate`。原 owner 的失败路径原始归档状态为 `NATIVE_FAILED_RAW_ARCHIVED`，复制核验为 `VERIFIED_COPY`，原外层残留进程列表为 `[]`。这项 owner/COPY 候选差异独立保留，不能代替或抹去第八场飞行失败，也不能仅凭文字差异认定原件被篡改。

关键完整文件 SHA-256：

- 第八槽：`884c20621aad6c504f03668c8c7f7e944fc2aec6e1b465d49f1e9a5507c39ede`。
- 第八 attempt：`f9453350c9dae36c4a1d61c8d2856746d1ade9c75da5412eafa33d924469e812`。
- 核心外层：`186ee158eeb4efa17227547d86b43915c83c8e5a4399e6d6044a49b7b23dfb4e`。
- 双桥补充：`9c6e371f9c4f533dc918b1f0d522f85e722bab6cc929ebe0ecb544d701d0f048`。

完整具名原件、来源路径、字节数和 SHA 见[小文件快照](../tools/diagnostics/humble53_core_stop_snapshot01/README.md)。没有复制大帧文件、bag、视频或诊断窗口。

## 已确认的汽车速度结果

第七场 `car_stage1_velocity_seed004` 原工程 PASS。导航报告的全区间物理 `base_link` 距离 RMSE 为 **0.731619546664657 m**，高度 RMSE 为 **0.1595441003376031 m**；752 个计划点均匹配真值，原全区间末段距离/高度持续稳定均为 true。导航顶层仍为 `RECORDED_WITH_CENSORED_FAILURES`，原窗口和删失记录完整保留。这是一场固定开发种子的结果，不能据此认定汽车位置控制、云台或总体可靠性已解决。

## 当前诊断和下一步

先在原第八场证据中分别定位行为失联、来源时效越界和阶段时间越界的首个异常及因果先后。当前行为首断链候选涉及约 52.8 s 的最后测量、旧 `track_id=2` 与新 `track_id=3` 的关系，仍须独立证据核对；尚未确认根因或完成修复，不据此放宽门限、切换任务目标或重写原结果。

后续应先形成具名诊断和最小修复，再做对应回归、新来源构建及独立完整开发验证。当前同源核心未全过，不能直接推进依赖完整核心通过的安全、扩展、最终准入或正式批次。历史 Humble50/51、单场等价复验和当前 7 个 PASS 均不拼成新的完整 12 场通过。

## 本轮交付工具验证

2026-11-03，Windows 实际执行新增及原回归共四模块：浏览器视频两模块 **16 项通过**，交付入口两模块 **43 项通过**，合计 **59 项通过**。两份原始日志及 `test_results.json` 已附在上述小文件快照，原路径为 `D:/WSL/UAVHumble22-validation/delivery53_verification01`。

这是纯 fixture 的交付功能验证；没有本轮新原生测试、真实视频转码或飞行结论，也不能视为最终文档、视频覆盖和整个项目验收完成。既有完整 Linux 测试、冷构建和原生验证保持各自原范围，本次不扩大它们的结论。
