# 两个目标失鲜窗口的只读遥测摘录

本目录只描述冻结试验中两个局部窗口的原始已记录行为，不重放、不飞行、不推理，
不改动原终态、FAIL、null 或任何验收门。`actual_windows01.json` 是保留原字段的摘录；
`window_findings01.json` 是由摘录生成的描述性统计，不是新增真值或完整因果证明。

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `actual_windows01.json` | 4161301 | `acfc758bc1e39429b137791402a925e2c7074d3aa0475391851604f707460501` |
| `window_findings01.json` | 21928 | `fbb86a1ca50459a405b90bf0b593eca0396ff8f0aae459e0af9988b0d44c76a0` |
| `extract_closed_windows.py` | 4402 | `4343f0d293ca2963b1cdb9f658c60e410176dd8d2cb939005e84942789527e7f` |
| `summarize_windows.py` | 5579 | `e783863543bb4da4bbe1987b469a3fe85d655258cb63a0e86fdfe9059106194d` |

提取器要求原 terminal 为 COMPLETED、infrastructure_stop 为 false，并核对原遥测完整
SHA 与 terminal 的 artifact hash；只读遍历前后复核大小、mtime，未修改原数据。
保留的种类为 control_status、detection、observation、target_state、navigation_state、
tracks、navigation_diagnostics。只要该行记录的 `time_s`、`stamp_s` 或 `acquisition_s`
**任一个**落在闭区间窗口内便纳入，因此不能称为纯接收时刻窗口；保留行的 `time_s`
可能在窗口外。`original_line` 从 1 起，`original_byte_offset` 从 0 起，计入原换行字节。

`time_s`、检测的 `stamp_s`/`completed_s`、RGB/Depth received、worker_started 均保持
原记录的 simulation/ROS 时间和浮点精度；它们不是绝对 monotonic/realtime 端点，
也不是精确 DDS 接收时刻。`inference_wall_s` 仅是已记录的局部耗时，不能与模拟时间差
混算物理 E2E，不能用 RTF 换算成已观测端到端时延。没有补造整数纳秒或 header 身份。
`nominal_expiry_s = 最后接受的 acquisition + 原配置 0.75` 只是描述性阈值，
不是测得的精确状态转换时刻。

| 原试验（原结果均为 FAIL） | person_extension_combined_seed004 | car_extension_dropout_seed004 |
| --- | --- | --- |
| 摘录闭区间 | [33.8, 35.2] | [30.7, 31.85] |
| 保留行数 | 391 | 313 |
| 原遥测字节数 / 行数 | 83569561 / 21556 | 90646951 / 21538 |
| 当前帧选中测量提交：接受 / 拒绝 | 5 / 0 | 3 / 0 |
| 最后接受 source / logged time | 34.1 / 34.228 | 30.9 / 30.984 |
| 最后接受原行 / 字节偏移 | 5238 / 14837579 | 4040 / 13253710 |
| 后续 depth-valid detection source / completed | 34.8 / 34.904 | 31.6 / 31.668 |
| 该 detection 原行 / 字节偏移 | 5394 / 15303976 | 4210 / 13580566 |
| stale_target 悬停 time / 原行 | 34.852 / 5378 | 31.652 / 4204 |
| surface LOST time / 原行 | 34.86 / 5379 | 31.66 / 4205 |
| 名义过期时刻 | 34.85 | 31.65 |
| 最后接受 source → 后续检测 source | 0.7 模拟秒 | 0.7 模拟秒 |
| 最后接受 source → 后续检测 completed | 0.804 模拟秒 | 0.768 模拟秒 |

原 person terminal SHA256：
`f57d22dff4989c8bbb45b56ba2151d66e52b5689984cd0a0104f531d4749b655`；
原 person telemetry SHA256：
`d08546aa2c779b40c8bc9b4f96498368f4668ab488f85992e9a61fb066c3a74c`。
原 car terminal SHA256：
`f80a774d1af43cbb6e8525662bb13f3c2853c9c19d68ac57ccd82435b9015f17`；
原 car telemetry SHA256：
`edf4b6c6ef9282969bc4a154aa45de256ad8e6f825cc5528ea65a95ee47e266c`。

已观测到的这些“当前帧选中后提交给滤波器”的测量尝试全部 accepted，不能把它们
标成马氏距离拒绝。但日志没有给出每个候选配对的关联分数、候选否决/门控、未选中
候选或完整关联血缘，**因此不能排除完整关联过程的影响**。检测完成相对名义阈值的
时间只支持部分 stale_target 行为描述，不能单独定位全部失败原因，也不能证明身份
保持、恢复或将原 FAIL/null 升级为成功。物理 E2E 与完整候选关联仍未由此观测。
