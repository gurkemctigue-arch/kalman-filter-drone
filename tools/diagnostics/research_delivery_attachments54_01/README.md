# 独立研究附件接线：小文件证据快照

这里只保存报告/交付工具、合成检查及独审的小文件；没有生成实际研究报告或 Word，没有读取原 bag、events、JSONL、模型或实验大文件，也没有启动 WSL、ROS、PX4、Gazebo 或原生仿真。

现有主报告新增四类独立附件引用：前瞻动态检测、物理恢复、可观测时序、控制 tick 记录链。主报告的标题、段落和表格沿用既有通用文档块，因此可直接进入 Word，未修改 Word 排版器。未提供时逐项显示 `PENDING_NOT_PROVIDED`；拒绝或缺失不展示数值；有效小绑定的状态仍为 `SAVED_REPORT_SMALL_BINDINGS_CHECKED_NOT_REVERIFIED`，不冒充原始数据重分析或独立语义复验。

控制 tick 保留每条原控制命令分母及 UNKNOWN，端点为“采集→控制循环取时（tick开始）source_sim”，在 update/publish 之前，不代表完整回调因果、发布完成、PX4 执行或物理墙时端到端。汇总身份覆盖不能证明每个 `target_uuid` 任务均达门槛；逐任务弱项和未提供证据保持独立解释。

两项独审发现已修复并纳入合成检查：超限报告在任何无界报告 hash 前拒绝；原计划目录与 timing exporter 的真实 resolve 路径可以按实际 canonical 目录唯一匹配，同 basename 的其他批次不能替代。

作者与独审都实际跑过 **38/38** 两模块合成测试。该两轮检查对应主报告 SHA `54298ef43a60aa405e5a8ba388e7a8e943151db0840ef1e39e87488307d8b811`。此后仅添加一段逐任务身份解释文字；当前主报告 SHA 是 `29b78a3158b707acbe9acfffc7c6f58a12772252373874df0fa32978ddf5a901`，只单列 AST、两项现有针对性检查及文字 diff 独审。**不能把此前 38 项检查追认为当前主报告 pin 的全套重跑。** 其余三文件 pin 未变；逐文件关系、命令、原日志、作者和独审收据均见 manifest 与 evidence。

此变更作为外置交付工具使用，不能复制进要求逐字节保持原 flight 源的 final55 staging。正式算法与试验目录由原计划及明确 CLI 参数指定，工具 checkout 的根目录仅承载交付实现、模板和依赖。外置工具树应包含原有完整依赖；本目录四源快照不是独立可运行软件包。

主报告在原有参数之外支持重复提供：

```
--prospective-detection ACTUAL_DETECTION_REPORT.json
--physical-recovery ACTUAL_RECOVERY_REPORT.json
--timing ACTUAL_TIMING_REPORT.json
--control-tick-lineage ACTUAL_CONTROL_TICK_REPORT.json
```

既有 `--replay-source-root`、`--detection-source-root` 应指向对应冻结算法源码；`--core-plan`、`--extension-plan`、`--summary` 使用实际原计划及绑定结果。新包只能输出到新的独立目录。交付页面另支持 `--v4-control-tick-lineage`，保留旧 timing kind 的未观测边界。此准备不改变任何原槽裁决、正式研究分母、项目验收或 flight 登记。

`collect_snapshot.py` 只对每件不超过 1 MiB 的源码、日志和收据作原字节复制；本目录的局部 `.gitattributes` 保留这些原始字节。不执行评价器、不运行测试、不改 Git index。最终 DOCX/PDF 原生渲染和逐页视觉验收仍需在实际文档生成后完成。
