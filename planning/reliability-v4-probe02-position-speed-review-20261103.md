# probe02 第 7 场 position 加减速复核（2026-11-03）

仅读取原终态、小报告与记录参数，对照第 6 场 velocity；未读 telemetry/bag、启动 WSL、重推理或修改代码、阈值、原判定。

**原件**

试验 ID 分别为 `person_extension_speed_changes_position_seed004`、`person_extension_speed_changes_velocity_seed004`。终态位于 `results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/slots/`，报告位于同结果根下 `reliability_v4_humble54_extension16_probe02_<试验ID>/`。

- position 终态 SHA256：`d64c7f7e401ccb8cf62cc393e5c45dfbdb7c25e38d07a246f69966d0d6aa8891`。
- velocity 终态 SHA256：`a482af35d8ad5dc4fb33480552becdf701ea94af28b22b26431ca6db7ff05681`。
- position navigation 报告 SHA256：`69eca93dae205e6cf7daea7e2b5ccd547a94508b0deaa298df3b985fb7124313`。
- velocity navigation 报告 SHA256：`2e289e0352617d4b524f8903a34cf74a0a54a63bef9f2a78d3750fbc1b11793c`。

**实际判定和同口径对照**

两场均 COMPLETED、`flight_exit_code=0`、无基础设施停止和残留进程，surface_flight 为 PASS。position 原工程 **FAIL** 只有 `final_distance_settled=false`；其余距离/高度 RMSE、导航覆盖、真值覆盖、最终高度稳定五项均通过。velocity 原工程 PASS，六项均通过。原判定保持。

| 指标 | position | velocity |
| --- | --- | --- |
| 全 FOLLOW 评价窗口（sim s） | 17.352–92.472 | 17.700–92.860 |
| 固定 10 Hz / 独立真值样本 | 752 / 752 | 752 / 752 |
| base_link 距离 RMSE（m） | 0.649293 | 0.642911 |
| base_link 高度 RMSE（m） | 0.165850 | 0.145346 |
| KF 有效状态 | 688/752（91.489%） | 689/752（91.622%） |
| LOST / stale 导航样本 | 63 / 1 | 63 / 0 |
| 非跟踪控制采样点 | 64 | 63 |
| 初始窗距离稳定时间（相对 FOLLOW） | 5.100 s | 4.300 s |
| 重选请求时刻 | 49.360 s | 49.700 s |
| 重选后首段持续入带（相对请求） | 10.092 s | 3.900 s |
| 重选后最终距离稳定（相对请求） | null，右删失 | 8.400 s |
| 重选后向近侧的最大超调 | 0.530153 m | 0 m |

表内距离、高度统一使用 navigation 报告的 base_link 真值口径，保留丢失/悬停段；不与模型原点或仅跟踪子集混用。navigation 两场均 `incomplete_reasons=[]`、`malformed_input_counts={}`、全窗真值覆盖 100%。

**`final_distance_settled=false` 的具体含义**

距离稳定要求误差位于 ±0.5 m，控制有效、证据连续，并形成至少 3 s 且一直延续至录制结束的末段。position 全窗及重选窗口均 `settled_through_interval_end=false`、`settling_time_s=null`、`settling_right_censored=true`，不能把 null 解释为零。

position 并非从未入带：初始窗约 22.452 s 起已稳定至首次遮挡；重选后约 59.452 s 出现首段持续入带，但没有取得延续到 92.472 s 的合格末段。重选窗口中至少曾出现向近侧 0.530153 m 的超调，较 0.5 m 带宽多约 0.030153 m；小报告没有给出其发生时刻或最终误差，不能直接认定该次超调就是末段失败原因。

velocity 的最终距离稳定始于绝对时刻约 58.100 s，并保持到结束。两场重选后的连续状态/控制检查均 PASS；position 该段约 43.088 s，末状态/控制距录制终点仅约 0.008/0.020 s。因此不能将 position 的末段失败直接描述为再次完全丢失或未恢复。

**参数、不能归因之处及待核**

- 两场 `run_config.json` 仅试验名与 `command_mode` 不同；记录的 runtime_parameters.yaml 也只有 `command_mode` 不同。均 seed=4/Gazebo seed=5、clean、speed_changes、adaptive_kf、legacy 关联，目标距离 5 m。
- navigation 评价脚本及全部依赖的来源绑定一致；这是同一指标定义下的一对试验，不能据单对结果断言 position 普遍较差或两者差异具有统计意义。
- position 记录 `slew_position=true`、position lead 限幅 [2,2,0.5] m、position acceleration 限幅 [3,3,3] m/s²；这些参数仅构成后续检查线索，尚未证实具体因果。
- 待原生窄窗：position 先查 89.000–92.472 s，必要时沿重选后 49.360–92.472 s 的小型评价 sidecar 定位最后一次条件中断；对照 velocity 末尾 89.000–92.860 s。
- 需输出最后一次超带/入带时刻、末段驻留时间、控制有效性与导航新鲜度，区分误差超带、驻留不足 3 s、导航/证据连续性中断；再核目标变速、估计、限幅设定值和实际机体响应是否同步。上述窄窗本次尚未执行，原 FAIL 不改判。
