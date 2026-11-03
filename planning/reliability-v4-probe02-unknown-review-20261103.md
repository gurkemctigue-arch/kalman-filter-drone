# Probe02 第三场缺证复核与续接

2026-11-03 14:13（北京时间）检查点。完整项目尚未验收，正式研究仍为 0/280。

新 probe02 已尝试 3/16 场：前两场 PASS，第三场 `person_extension_dropout_seed004` 为 `INCOMPLETE_EVIDENCE`，剩余 13 场尚未尝试。第三场飞行返回 0，录包完整性、源时钟、原生起飞与长时丢失安全检查通过；其监督程序因短窗检测器诊断缺失停止。Windows 与 WSL 子进程真实退出均已记录，防休眠请求已释放，无自动重试。

本次只读重读该场的原始录包，完整导出短窗前后 8 帧。直接看图确认 29.8、29.9 秒为近黑遮挡图像，其余图像可见行人。按原 seed=4、200 ms 窗口、10% 丢帧算法复算，这两帧均为 DROP；research RGB/depth 与检测诊断在该短窗内均没有输入机会。固定外部评价器返回 `UPSTREAM_INPUT_INTERRUPTION_CORROBORATED`，errors 和 known_algorithm_failures 为空。这说明故障注入阻断了输入，不能证明检测器在被遮挡图像上的表现，也不把原 null 或原 INCOMPLETE 改成 PASS。

原监督器保留 `STOPPED_FAULT` 与真实错误。经原收集器和冻结评价器逐场复核，三场原件构成完整已闭合前缀。第三场导航评价为 PASS：距离 RMSE 0.716932 m，高度 RMSE 0.155711 m，末段距离与高度稳定。续接仅从第四场 `person_extension_latency_seed004` 开始，未知许可仅适用于这份已审终态，其他新未知仍需检查。

本地关键原件：

- `results/diagnostics/humble54_probe02_windows_owner05/terminal.json`
- `results/diagnostics/humble54_probe02_dropout_review03/root_review.json`
- `results/diagnostics/humble54_probe02_dropout_review03/native_prefix_audit.json`
- `results/diagnostics/humble54_probe02_person_dropout_input_extract03/manifest.json`
- `results/diagnostics/humble54_probe02_person_dropout_input_extract03/visual_review_native03.json`
- `results/diagnostics/humble54_probe02_person_dropout_input_extract03/input_evidence_evaluation03.json`

同一空闲窗口完成两个固定历史 telemetry 文件的透明 NTFS 压缩样本。前后完整 SHA、文件身份、大小、修改时间及正常解压读取校验通过，实际分配量减少 105,504,768 字节（100.62 MiB）。没有删除或改写原始内容，没有压缩活动录包或 WSL VHD。该结果只代表两文件样本，不能推断全项目收益或正式 280 场容量已准入。

接下来依次完成剩余 13 场收集、完整 28 条开发记录空间测量、物理容量预算、R0 定标、新最终来源构建与验收、正式批次、离线比较及最终交付。候选脚本与小型单元测试不计入真实飞行次数。
