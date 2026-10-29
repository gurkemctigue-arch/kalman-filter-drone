# V4 独立图表与原始 CSV

`scripts/build_reliability_v4_figures.py`只读已明确指定的summary JSON，生成可独立导出/排版的PNG、PDF、SVG和CSV。它不导入ROS、不读bag、不运行检测/滤波/飞行，也不选择阈值或注册参数。当前正式矩阵尚未执行；本工具的测试图明确标记 `FIXTURE_ONLY`，不是研究结果。

```bash
python scripts/build_reliability_v4_figures.py \
  --summary /new_summary/summary.json \
  --replay-summary /verified_replay/summary.json \
  --output /new_figures_directory
```

没有完整四法证据时省略 `--replay-summary`；对应图保留pending。输出目录须全新。`--only core_verdicts`可明确选择已具备数据的小图，其余图ID记录为omitted，不冒充全部图组。默认逐图生成全部可用图组，每张及时关闭以限制内存。PNG为180dpi，PDF嵌入TrueType字体，SVG保留文本；Matplotlib/Python版本和实际脚本/依赖hash写入manifest。

图组分别保留核心与扩展队列、两类、六核心组/八工况及原始终态。FORMAL输入必须完整包含120/160槽；开发PROBE按实际计划槽数展示，并明确不属于正式结果。图表包括全部PASS/FAIL/INTERRUPTED/基础设施错误/缺证/待评价/运行中/待运行，不能删去失败或把pending当成功。

可用指标分为物理base_link距离/高度和在线导航误差、导航/真值覆盖、稳定状态与右删失、云台几何/反馈、指定任务身份覆盖、分别定义可见性的IDF1/HOTA/ID Switch、FPS/时延、命令变化率、画面中心和短请求遮挡预测。指标没有有限值时不绘制该面板，manifest明确pending。请求遮挡窗口不能称为独立测得的像素遮挡。推理墙钟耗时、仿真时间FPS、图像到检测完成与图像到首命令延迟分别标注，不能混为同一种端到端延迟。

每个数值点代表一条飞行试验。原FAIL的有限误差仍显示为FAIL；0是有效数值，缺失保持空白。稳定时间只显示已实际SETTLED且非删失的值，右删失/缺失/不一致单独计数，不能填0。图注和CSV区分独立trial数与误差/帧样本数；summary没有 `metric_sample_counts`时，`source_error_samples`留空，不能用trial n代替。

配对图直接使用summary中同class/seed的active−midpoint、position−velocity和扩展−预登记clean参考。全部有限配对与双方原工程PASS子集分别显示，保留每侧原状态和每个null差值。`n/10`是正式设计分母，实际提供的开发计划配对数另列；条件CI沿用源summary，不因缺失而伪造区间。负差值只表示该指标的左侧数值更小，对coverage/FPS等不能自动解释为改进。

四法图额外要求：summary的完整verified状态；实际hash绑定的20份trial report及registered_configuration文件；配置摘要一致；用保留的证据回执重新核对完整配对汇总。旧summary若没有 `trial_report_artifacts`/`registered_configuration_artifact`，或任一证据未verified，保持pending。程序不猜路径、不打开未绑定的trial文件。每法位置/速度RMSE使用四法共同真值支持，CSV分别保留共同位置/速度误差样本数和20条试验原工程状态。这是同测量条件离线估计比较，不是四个闭环控制器的因果对比。目前登记实现只有位置配对CI；速度值可展示，速度配对CI明确pending，不能擅自补一项未经登记的结果。

输出包括全计划槽CSV、全逐试验指标CSV、所有逐seed配对差CSV、每张图直接使用的CSV及三种图格式。没有被选中绘制或完全缺失的指标仍保留在全量原始CSV/manifest中。每个文件都带相对路径、字节数和SHA256，生成期间再次核对输入/实现hash；有变化则不发布最终manifest，已产生的部分工件保留且不可覆盖。

`manifest.json`合同为schema1、`kind: RELIABILITY_V4_FIGURES`，包含 `summary_path/summary_sha256`、可选 `replay_summary_path/replay_summary_sha256`、`figures`、`csv`、`pending`、`omitted_figure_ids`、`cohorts`、`input_sources`、`source_hashes`。每张图项包含 `figure_id/path/sha256/bytes/format/caption/scope/source_role`；同figure_id对应PNG/PDF/SVG三项。报告/Word流水线逐件核验后可嵌PNG，同时保留矢量文件与原始CSV来源。最终manifest最后写出，不代表飞行验收或项目完成。

轻量专项：`python -B -m unittest tests.test_reliability_v4_figures -q`。测试使用小型合成JSON，只渲染少量明确的fixture小图以核对状态/数值/配对三种图型；不读取真实留出数据、不生成正式论文成果。

新增图族展示物理距离/高度的95%绝对误差分位数、KF误差范数p95及移动任务反侧超调；前两项必须先由当前源码绑定的summary重建，旧signed-p95摘要不能直接改标绝对误差。位置模式另展示设定点一阶变化率RMS（m/s）与二阶差分RMS（m/s²）。所有命令变化指标包含有意跟随/重选瞬态，不是机体实测运动或纯噪声。每族也可使用原summary的逐seed配对差与条件区间。

操作层恢复图保留三种不同分母的短请求窗观察比例、仅同track_id与target_uuid恢复成功时的条件时间，以及初始选框/重选合并的显式确认比例和条件时间；均不称物理重捕获或ReID。缺失/非法原时间字段会使两项全短窗观察比例保持null；显式null只表示未观察/无时间，不能作为失败。条件已知恢复率与有效成功时间仍可单独展示。确认右删失、身份检查未知、未观察/无时间、缺失/不一致分别保留。

独立计数图分别展示每组可读来源的池化请求窗结局及全部计划飞行的来源状态，不能把窗口数当独立试验数。始终导出 `all_operational_recovery_evidence.csv` 与 `all_operational_recovery_windows.csv`，包含原飞行状态、逐窗状态、所有窗口分母及 `missing_or_invalid_timing_windows`。逐飞行指标CSV的恢复时间使用 `source_window_samples`；`source_error_samples`在这些行为空，比例的实际分子/分母另列，不用trial n替代。
