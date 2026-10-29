# Recording closure 的实际回调就绪门

本修复只解决录制收尾观察器在停止世界前尚未收到必要源流的问题。总墙钟预算仍为 10 秒；暂停后的完整源流对应关系、最终 Clock 精确真值、0.5 秒安静窗口和独立全包审计保持原要求。

## 已观察到的问题

冻结 Humble14 的开发槽 `person_stage1_velocity_seed004` 保留原 FAIL。原 observer 在 2.039328 秒时仅收到 raw 两次，Clock、timing、adapted、target GT、vehicle GT 均为零，却继续请求暂停；暂停 ACK 在 2.342981 秒。Clock 随后才到达，而 timing、adapted 和 GT 在原 10 秒窗口内始终没有回调。

独立只读 rosbag2 诊断确认：包内最终 Clock 为 64.38 秒，声明的 `target_person` 和 `stage1_uav` 的最后 GT 源戳均恰为 64.38 秒。bag recorder 与 closure observer 是不同订阅者，因此包内有证据不能替代 observer 实际收到的证据，也不能据此把原 FAIL 改成 PASS。记录的 QoS 兼容，但原历史 endpoint GID 未保存，无法倒推出 DDS 匹配的具体时刻。

旧逻辑最多等待 2 秒且仅观察 Clock/raw，超时后无论是否就绪都暂停。新的 volatile 订阅可以在不同时间发现不同发布者；生产者被提前暂停后，没有到达过的 GT/timing 订阅不会因继续等待而自动获得历史数据。

原件与只读诊断：`results/frozen_fullplan_v4_humble14/reliability_v4_humble14_probe_seed004_matrix/diagnostics/person_stage1_velocity_seed004_closure_readonly/diagnostic.json`。原 trial、plan、slot 和冻结源码不改。

## 最小修复

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
