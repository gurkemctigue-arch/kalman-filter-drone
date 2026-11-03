# probe02 第 7 场 position 加减速复核（2026-11-03）

仅读取原终态、小报告、记录参数与已闭合的小型 navigation sidecar，对照第 6 场 velocity；未读 telemetry/bag、启动 WSL、重推理或修改代码、阈值、原判定。

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

position 并非从未入带：初始窗约 22.452 s 起已稳定至首次遮挡；重选后约 59.452 s 起又持续入带。实际 sidecar 随后记录末次超上界为 **88.652–90.052 s** 的 15 个采样点：首点误差 +0.500515562 m，89.352 s 达峰值 **+0.560628353 m**，末点 +0.508939842 m。

90.152 s 误差降至 +0.493616500 m，之后 24 个采样点保持入带；末样本 92.452 s 仅 **+0.102679216 m**。但至录制结束 92.472 s 的末段驻留仅 **2.320 s**，不足原定 3 s，直接解释了 final=false。该段采样间隔约 0.1 s、至录制终点差 0.020 s，满足 0.15 s 连续性容限；失败来自晚期超带后驻留不足，而不是末误差很大、缺真值或末段掉状态。上述时刻是固定 10 Hz 观察值，真实跨界仅能界定于相邻采样之间。

position 的导航/控制仅在 43.052 s 因 stale 变为无效、43.152 s 转 LOST，49.452 s 网格点恢复后一直有效到末尾；89 s 后 35 个样本全部 active/navigation_valid=true。早先向近侧 0.530153 m 的超调不是最后一次中断。velocity 自 58.100 s 连续入带，至录制末尾驻留 **34.760 s**；89 s 后 39 点均有效且误差为 +0.229685851～+0.426458917 m，末样本 92.800 s 为 +0.249388455 m，距结束 0.060 s。

**参数、不能归因之处及待核**

- 两场 `run_config.json` 仅试验名与 `command_mode` 不同；记录的 runtime_parameters.yaml 也只有 `command_mode` 不同。均 seed=4/Gazebo seed=5、clean、speed_changes、adaptive_kf、legacy 关联，目标距离 5 m。
- 两原报告的 navigation 评价脚本及依赖绑定一致；本次实际执行的稳定函数 SHA256 `03c81478632f38ba2ca49b91b14cf5b43e0c6f8c545c6cbf037f2f62fb118cb9` 与原报告依赖一致，重算两场全窗、初始窗、重选窗全部稳定字段均精确吻合。当前 Windows navigation 外层脚本 SHA 为 `b49984d495ec7b12e623e961f3d606958aaef682ddfbc636f9c21ed2d52abcb4`，不同于原冻结 `bbff6c746ed76d0139c194cdfc1409f38dc422d64ddbc73da2995a0838df4422`；本次未执行该外层脚本。
- position 记录 `slew_position=true`、position lead 限幅 [2,2,0.5] m、position acceleration 限幅 [3,3,3] m/s²；这些参数仅构成后续检查线索，尚未证实具体因果。
- 末段判据诊断已由 sidecar 完成，无需为确认该失败原因读包；sidecar 不含目标瞬时加速度、无人机速度和控制设定值，尚不能归因于某个控制限幅、变速相位或估计延迟。此单对 seed=4 也不足以支持总体或显著性结论。
- 实际证据：[actual_sidecar_evidence.json](../results/diagnostics/humble54_probe02_position_speed_tail_review01/actual_sidecar_evidence.json)，创建 UTC `2026-11-03T08:59:22.370819+00:00`，SHA256 `e9e3c2ad60ca5a4117b964921f67084aa1a8a5d9635c60167b262a43f20febe0`；保存输入路径/SHA/mtime、全窗条件转变及两场 89 s 后原 sidecar 行与行号。
- 原 position sidecar 为 414581 bytes、SHA256 `33866893a65779b6bbc2105d2dcda51905ba659345926480609f5e83d4520fa5`；velocity 为 412621 bytes、SHA256 `b94152e657d20e96df4673e351e9bdc18628160a6415ee30fd76dcbf48fbd758`。原工程 FAIL/PASS 均保持，不延长原试验窗口或放宽阈值。
- GitHub 可审查的[原字节证据副本](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/actual_sidecar_evidence.json)及两份小 sidecar 已另存 tools；[复制回执](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/publication_receipt.json)保留来源与相等性，原 results 证据不变。
- 末段对比图：[PNG](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/artifacts/position_velocity_tail_distance.png)、[PDF](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/artifacts/position_velocity_tail_distance.pdf)；明确 ±0.5 m、90.152 s 观察入带、92.472 s 结束及 2.320<3.000 s，并将跨界显示为相邻采样间的区间。[绘图脚本](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/plot_tail_comparison.py)与[实际回执](../tools/diagnostics/humble54_probe02_position_speed_tail_review01/artifacts/plot_receipt.json)可供复核重跑。
