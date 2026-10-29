# Recording closure 的实际回调就绪门

本修复解决录制收尾观察器在停止世界前尚未收到必要源流，以及活流跨话题交错时最新样本不能同时对应的问题。总墙钟预算仍为 10 秒；暂停后的完整源流对应关系、最终 Clock 精确真值、0.5 秒安静窗口和独立全包审计保持原要求。

## Humble16 活流交错与候选修复

Humble16 两类新 clean 与核心前两格已完成相应独立检查。第三格 `person_stage2_crossing_seed004` 保留原 `INFRASTRUCTURE_ERROR`，其余九格不继续执行。原收尾观察器在 10.092328 秒内实际收到 Clock/raw/timing/adapted/target GT/vehicle GT，计数分别为 189/179/188/188/188/188，但最新 raw 和最新 timing 未同时匹配，因此没有请求暂停。该失败不能改判为通过。

原 `ready_to_pause()` 把停止后要求的“最新 raw 与最新 diagnostic 严格对应”提前用于持续运行的多个源流。不同话题回调可能持续交错，即使已经完整收到较早的真实 raw、其 diagnostic 和 accepted 输出，也可能一直无法同时对齐最新样本。

候选只修改暂停前的就绪门：保存至多 256 个实际收到的 raw 键，与实际 diagnostic 求交集，至少一对在 accepted 时还必须实际收到相应 adapted header；rejected 不等待不存在的 adapted。Clock 和每个声明 GT frame 仍必须实际到达，畸形 diagnostic 仍拒绝。暂停后的 `assess()` 完全保持原实现，仍要求最终最新 raw/diagnostic/output 对应、每个 GT 与最终 Clock 精确同戳、0.5 秒安静窗口及全包独立审计。暂停前发现、暂停 RPC 和最终排空仍共享 10 秒，没有延长预算。

17 项纯行为回归通过。真实 ROS 2 Humble/DDS 组件证据位于 `results/freeze_validation/recording_closure17_smoke01/summary.json`；发布器延迟 1.5 秒创建必要组件，实际收到新 raw 后才发布上一 raw 的 diagnostic，从而维持真实跨话题交错。生产状态方法未替换，fixture 仅捕获实际状态对象用于等待真实 raw 回调，并替代 Gazebo pause RPC；未启动 Gazebo/PX4。

| Case | 结果与实际观察 |
| --- | --- |
| 冻结16旧逻辑、交错活流 | 10.002436 秒预期失败，全部六类回调已收到，从未 pause |
| 候选、同样交错活流 | 2.028051 秒严格最终闭合通过 |
| 候选、缺目标 GT | 10.002476 秒拒绝，未 pause |
| 候选、raw 与 diagnostic 无任何相同键 | 10.002348 秒拒绝，未 pause |
| 候选、accepted 无相应 adapted | 10.002444 秒拒绝，未 pause |
| 候选、rejected 且无 adapted | 2.024349 秒严格最终闭合通过 |

六项满足预期，前后导入源码 SHA 一致。组件结果不能替代后续新冻结的构建、两类 clean、12 格核心和正式研究。

同期另有一次代理进程查询引号解析事故：意外启动额外 `gz sim` 及 server/gui，向其 owned PID 发送 TERM，后续独立审计确认四个 PID 均已不存在。原调用没有记录确切 UTC，只保留进程相对 elapsed 时间；不能声称它对第三格没有影响，也不能把它直接当作已证实的唯一根因。确切命令、错误、PID、清理和时序局限保存在 `results/freeze_validation/closure16_incident01/incident.json`；原计划、槽和试验 SHA 不变。

## 已观察到的问题

冻结 Humble14 的开发槽 `person_stage1_velocity_seed004` 保留原 FAIL。原 observer 在 2.039328 秒时仅收到 raw 两次，Clock、timing、adapted、target GT、vehicle GT 均为零，却继续请求暂停；暂停 ACK 在 2.342981 秒。Clock 随后才到达，而 timing、adapted 和 GT 在原 10 秒窗口内始终没有回调。

独立只读 rosbag2 诊断确认：包内最终 Clock 为 64.38 秒，声明的 `target_person` 和 `stage1_uav` 的最后 GT 源戳均恰为 64.38 秒。bag recorder 与 closure observer 是不同订阅者，因此包内有证据不能替代 observer 实际收到的证据，也不能据此把原 FAIL 改成 PASS。记录的 QoS 兼容，但原历史 endpoint GID 未保存，无法倒推出 DDS 匹配的具体时刻。

旧逻辑最多等待 2 秒且仅观察 Clock/raw，超时后无论是否就绪都暂停。新的 volatile 订阅可以在不同时间发现不同发布者；生产者被提前暂停后，没有到达过的 GT/timing 订阅不会因继续等待而自动获得历史数据。

原件与只读诊断：`results/frozen_fullplan_v4_humble14/reliability_v4_humble14_probe_seed004_matrix/diagnostics/person_stage1_velocity_seed004_closure_readonly/diagnostic.json`。原 trial、plan、slot 和冻结源码不改。

## Humble15 的最小修复（历史）

`StreamDrainState.ready_to_pause()` 复用原对应关系判断，只排除尚未暂停时不适用的 ACK、最终 Clock 真值和安静窗口条件。暂停前必须实际收到 Clock/raw、最后 raw 对应的 timing、accepted raw 对应的 adapted，以及每个已声明 target/vehicle frame 的 GT。rejected raw 不要求不存在的 adapted；无关 frame 的 GT 回调不能充数。

`pause_and_drain()` 在原总 10 秒中等待上述条件。未就绪则记录缺证并失败，且不调用世界暂停服务。发现等待、暂停 RPC 和暂停后的排空共享同一总预算。原 `assess()` 未改变，最终 Clock 的每个声明 GT 仍须精确同戳。

对应纯行为测试为 `tests/test_recording_closure.py`，本次 14 项通过。

## 真实 ROS 2 Humble / DDS 组件验证

完整证据归档：`results/freeze_validation/recording_closure15_smoke01/summary.json`。四个独立进程分别使用 ROS domain 111–114，导入冻结14或主树的实际生产函数和状态类。真实 rclpy/DDS 发布和订阅；raw 立即发布，Clock publisher 延迟至 2.6 秒创建，其余所需 publisher 延迟至 3 秒创建。只用 fixture 替代 `gz service` 暂停 RPC，并记录实际 GID、QoS、首发时刻、回调计数、完整 closure JSON 和源码 SHA。

| Case | 组件结果 | 观察 |
| --- | --- | --- |
| 冻结14旧逻辑 + 晚到源 | 预期 FAIL，复现通过 | 2.151756 秒即 pause，暂停前 Clock/GT/timing/adapted 为零，10.002716 秒严格失败 |
| 候选 + 晚到源 | PASS | 必要实际回调到齐后 3.027434 秒 pause，3.486320 秒严格最终对应关系通过 |
| 候选 + target GT 一直缺失 | 预期 FAIL，拒绝通过 | 10.002616 秒失败，其他必要回调已到，pause 调用为零 |
| 候选 + rejected raw，无 adapted | PASS | adapted 回调为零，timing 明确 rejected，3.476244 秒通过 |

四项验证期望全部满足，前后导入源码 SHA 一致。本组件 smoke 未启动 Gazebo、PX4 或飞行，不替代后续冻结版本的两类 clean、完整开发矩阵与正式重复试验。
