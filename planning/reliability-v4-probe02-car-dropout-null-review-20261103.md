# probe02 第 11 场 car dropout 条件 null 复核（2026-11-03）

对象为 `car_extension_dropout_seed004`。仅只读原冻结评价源码、小报告和小型 sidecar；未读 bag/telemetry、启动 WSL、重飞、执行冻结源码或修改历史结果。续跑/准入决定不在本复核范围。

- 原 terminal SHA256：`f80a774d1af43cbb6e8525662bb13f3c2853c9c19d68ac57ccd82435b9015f17`。
- 原状态 **COMPLETED / FAIL**，`flight_exit_code=0`、`infrastructure_stop=false`，唯一负面评价器为 surface_flight，pending/incomplete 均为空。
- 原冻结 `evaluate_stage1_flight.py` 经 UNC 小文件读取，SHA256 `655cf6fc7c0cc2a954db7d06d2fbb00a000f2fca80ba0930d153025e28efb7c1`，与该场记录的 `configuration/source_sha256.json` 完全一致。

**null 的准确含义**

冻结源码 L645 将恢复观察窗定为打开后 3 s；L653–656 要求窗内存在 MEASURED 状态，且图像/header 时间及非空接收仿真时间均不早于打开。L662 将 identity 默认设为 None；只有遮挡前状态和合格恢复状态都存在，L663–665 才比较 `track_id` 与 `target_uuid`。

本次短请求窗为 **30.960–31.240 s**，关闭/打开 ACK 成功于 30.980/31.260 s；恢复观察窗为 **31.240–34.240 s**。原报告 `first_measured_after_open_s=null`、缺失接收时间的候选计数为 0。因此没有合格恢复状态可组成身份前后比较对，`identity_preserved_on_observed_recovery=null` 属于**未观察到恢复而无法比较**；不能补为 true/false，也不能解读为已发生或已排除身份切换。此检查仅比较运行时编号，亦不等于独立物理身份验证。

**实际失败与记录完整性证据**

- 短窗内两帧检测均无候选/有效深度，预测已出现；随后 `first_lost_s=31.660`、HOVER=31.652，`no_loss_during_short_occlusion=false`。
- 该检查虽名为 short，源码 L716 实际观察至恢复或恢复窗末端；31.660 s 的 LOST 位于开挡之后，不能写成遮挡板关闭期间已丢失。
- 源码 L743 规定任一必需项为 false 即事件 FAIL；该行为失败与身份 null 并存，原短事件及工程 **FAIL 均保留**。
- flight 的缺失 topic 为空、read_errors/unavailable_types 均为空；navigation 的 incomplete_reasons 为空、malformed_input_counts 为空。小报告没有指向缺 topic、解码错误或缺接收时间导致此次身份 null。
- navigation 固定 10 Hz 侧文件持续存在：31.652 s 因 stale 无效、31.752 s 采样为 LOST，直到显式重选后的 51.052 s 才恢复有效；它佐证记录仍持续，不能替代原 `/tracking/state` 消息验证。
- 恢复窗内 message sidecar 有 176 条（20 valid、156 lost）；raw sidecar 的 26 个采集机会均为 `no_accepted_selected_measurement`，fusion accepted=0。其前一 accepted 导航参考图像时间为 30.900 s、接收 30.984 s、track_id=1；此为导航参考旁证，不冒充原身份比较对。
- 长请求窗 43.960–47.040 s 开始时仍 LOST，故 `prediction_observed=false`；重选请求 50.960 s、确认 50.976 s，随后持续跟踪检查 PASS。长事件原 FAIL 保留。

**小原证据与未解决问题**

- [实际小证据](../tools/diagnostics/humble54_probe02_car_dropout_null_review01/actual_small_evidence.json)，68259 bytes，SHA256 `e23de17bffdbc80e1d8655ee24fd7a99c360c36bc8261c9545a568b77ca5b388`，创建 UTC `2026-11-03T09:21:36.768524+00:00`；含全部输入路径/SHA/mtime、源码行、原 null、恢复窗及 sidecar 行号/统计。
- 同目录保留冻结 evaluator、source map、flight 报告及原 terminal 的原字节副本，`.gitattributes` 禁止文本换行转换；原件未改。
- root 已完成原生短窗 raw 导出；本代理仅读取其小 manifest 并独立汇总：[补充证据](../tools/diagnostics/humble54_probe02_car_dropout_null_review01/actual_raw_extract_addendum.json)，SHA256 `adce1ffbf17c545c0ed00bce3c2eb8534050cb01cc0b2238f56aad5f6f14e463`。原 manifest SHA256 `2818cafb2de57f3a7559eb50b90a946acbe53f3246dd5b44c8a6f526c73006a6`，同目录另存原字节副本；all_selected_topics_scanned=true、absent_topics=[]、clock_regression_count=0，导出 9 张 raw RGB。
- 按精确采集 ns 分组，30.7/30.8/30.9/31.0/31.1 s 各有 raw RGB、raw Depth、research RGB、research Depth、诊断各 1 条；31.2/31.3/31.4/31.5 s 各仅有 raw RGB/Depth 各 1 条，未见对应 research 流/诊断，不能将其视为“YOLO 已处理但没检出”。
- **root 原图观察，待独立图像复核**：31.0/31.1/31.2 s 接近黑屏，31.3/31.4/31.5 s 已见汽车；root 报告缺流与 seed=4 预期 DROP 相符。本代理未查看原图或重放随机生成器，该图像/配置因果判断不冒充本代理独立结论。
- acquisition_ns/header ns 是原记录的采集时间；latest_read_clock_ns 与 recorder wall 时间不能作为精确节点回调时间。关联/门控及完整时间因果仍待进一步核查；不补身份、不改 FAIL，不自动泛化允许其他未知项继续。

## 实际 telemetry 窗口已执行（后续补充）

以上保留各次复核当时的读取边界。root 已单遍读取两场完整闭合 telemetry，并逐 SHA 匹配原 terminal；本代理仅核对其 [compact findings](../tools/diagnostics/humble54_probe02_loss_telemetry_windows01/window_findings01.json)，21928 bytes、SHA256 `fbb86a1ca50459a405b90bf0b593eca0396ff8f0aae459e0af9988b0d44c76a0`；原字段/行号/offset 提取 SHA256 为 `acfc758bc1e39429b137791402a925e2c7074d3aa0475391851604f707460501`，未重新扫描大文件。

car 窗口内 3 次当前 selected 更新全部 accepted、当前 selected 拒绝为 0；末次 source=30.900 s，在记录 time_s=30.984 s 接受，马氏距离平方 0.000344355 < 9.21。HOVER=31.652 s、measurement_age≈0.752 s，surface LOST=31.660 s、prediction_age≈0.760 s；下一个有效深度候选 source=31.600 s、completed_s=31.668 s、置信度 0.932143，检测完成时已超过原预测期限 31.650 s。这补充了恢复前新鲜度超限的实际时序，原身份 null 与 FAIL 保留。

该证据不包含完整候选两两评分，不能排除所有关联问题；所有 time_s/completed_s 保留仿真时间语义，不能当作真实物理端到端延迟。先前小报告的“本代理未读 telemetry”只描述当时任务范围，不能再理解成项目尚未执行实际 telemetry 窗口核查。
