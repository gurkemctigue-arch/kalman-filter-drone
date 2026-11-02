# Humble53 核心停止：具名小原件快照

对应 **2026-11-03 01:51 北京时间**批次停止检查点：原开发槽 **7 PASS、1 FAIL、4 PENDING**，正式 **0/280**。详见[停止原因与下一步](../../../planning/reliability-v4-humble53-core-stop-20261103.md)。本目录不是新实验或重新评价。

`slot_07/08` 与 `attempt_07/08` 保留第七场汽车速度、第八场汽车位置的完整原件；`core_outer_terminal.json`、`run_core_supplement_terminal.json` 和 `monitor_end_summary.json` 保留三种各自范围的终态。原 outer 的 `terminal_count=7` 不被改写为原槽计数：实际 8 个原槽终态为 7 PASS/1 FAIL，第八 attempt 的 `audit=null` 保留。

第七场原导航报告支持物理 `base_link` 距离/高度 RMSE 0.731619546664657/0.1595441003376031 m 及全区间末段均持续稳定；其 `RECORDED_WITH_CENSORED_FAILURES` 标签和删失窗口未改动。第八场原来源时钟、原生起飞、表面跟随、录制闭合和 bag 完整性报告分别保留，不预先认定几个失败属于同一根因。

`observer_copy_terminal.json`、`observer_native_exit_terminal.json`、`observer_archive_manifest.json` 仅保存小型 owner 终态及归档清单，不复制清单所引用的大原始流。外层记录 owner outcome 与较早 D COPY 候选不一致；失败路径原始归档和残留 `[]` 均保留。补充 sidecar 的 `error=null` 不代表健康 PASS，其实际 `returncode=2` 和原故障绑定未改。

`delivery_test_results.json`、`delivery_test_browser_demoall.py.log`、`delivery_test_acceptance_dashboardall.py.log` 是 **2026-11-03 交付工具测试原件**：新增及原视频两模块 16 项、交付入口两模块 43 项，共 59 项通过。它们不是 59 次飞行、原生测试或正式研究结果。

`snapshot_manifest.json` 从实际 `Path` 对象记录每件完整复制文件的真实来源路径、大小和 SHA-256；路径内容没有人为构造的字面 `\u...` 片段。具名文件逐件核对源/副本字节一致，原文件不修改；Git `-text` 规则保留原字节。未复制或读取大帧流、bag、视频、遥测/窗口，未执行测试、Office、WSL 或仿真。原核心计划和完整分析输入仍在本机原目录，不能宣称这个小快照包含完整实验归档。
