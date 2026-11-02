# v4 独立交付入口

`scripts/build_acceptance_dashboard.py --v4-package` 只整理已保存的真实 v4 文档包、工程 summary 和显式附件。它不启动仿真、ROS、模型推理或 bag 读取，也不导入原 reporter 的 `verify_package` / `final_gate`。不带 `--v4-package` 时，历史入口保持原行为；两种入口不混用。

## 使用

在原始绝对路径可访问的环境中运行。所有参数都指向现存文件；`--output` 必须是新的 HTML 路径，位于输入、试验和冻结目录之外。

```text
python scripts/build_acceptance_dashboard.py --v4-package <文档包目录或documents.json> --output <独立目录/index.html> --v4-prospective-detection <detection_report.json> --v4-physical-recovery <physical_recovery.json> --v4-timing <时序报告.json>
```

三个附件参数可省略或重复；省略显示“未提供”。脚本输出 HTML 和同名 `.sources.json`。后者记录核对过的小文件、原状态计数，以及明确未重读的原始数据绑定。重复生成需要新的输出路径，不能覆盖前一版。

脚本不猜测 Linux/Windows 路径映射，不自动寻找“相似”报告。搬运文档后若原绝对路径无法访问，正式证据会显示缺失；应在能访问原路径的环境生成入口，再保留相对目录结构交付。

## 输入与边界

- 文档包必须是 schema 1 的 `RELIABILITY_V4_DOCUMENT_PACKAGE`，带同目录 `sources.json`。核对结构摘要、来源索引一致性和五个保存输出（两份 Markdown、两份 HTML、`documents.json`）的 SHA-256/大小；这不等于按原请求重建整个验收。
- 工程部分读取包中绑定的原始 `FORMAL` core 120 与 `EXTENSION_FORMAL` extension 160 计划及 schema 1 summary。完整分母始终为 280；原 PASS/FAIL、未知状态、未完成和 summary 缺失槽保留。开发等价场不计入正式分母。缺失、被拒绝或无法访问的正式来源不会产生通过数和零误差。
- 检测附件只支持 `PROSPECTIVE_ALL_ACTOR_DYNAMIC_DETECTION_REPORT_V1`，核对完整 280 槽协议、两份原计划绑定、缺失槽台账及存在的独立可见标签复核文件。展示的是保存报告中的已批准可见子集指标；本入口不重读录制/预测缓存、不重算 mAP，也不执行 prospective 检测工具的 `verify-report`。
- 恢复附件只支持 `PROSPECTIVE_PHYSICAL_RECOVERY_APPENDIX_V1` 分析报告及其独立描述范围，保留原 40 槽的短遮挡与显式重选两类共 80 机会。协议文件不能代替分析报告。该工具没有 `verify-report`，入口不能声称恢复附件已独立复验。显式重选不是自动 ReID，未知和未确认时延保留。
- 时序附件只支持 `OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E`，核对小型导出 context 及保存的 events 绑定一致性，并将其 `source_root` / `trial` 精确绑定到原始 120＋160 计划中的唯一冻结来源/试验，保存槽 ID；旧批次、开发和外部时序不能混入。不重读 events/job 原日志或 bag。实际 worker 墙时 FPS、因果图像到控制/设定值时延及物理采集到 PX4 生效时延必须保持 `NOT_OBSERVED`。不得跨时钟相减或按 RTF 换算。
- 未知 schema、损坏的小文件绑定、错用原计划或缺失机会台账会被拒绝或明确显示缺失。大源数据未在此重核，不能据入口页面声称全部来源闭合。文档原生分页、图表重建、视频覆盖和项目整体验收也不能由这个页面证明。

每个读取文件上限 32 MiB，拒绝重复 JSON 键和非有限 JSON 数值。工具不遍历原始目录、不对整个源树或录包做哈希，也不更改原槽裁决。

## 串行验证

新增纯 JSON fixture 测试覆盖原分母、未知/缺失、篡改绑定、未知 schema、恢复/时序边界及输出保护：

```text
python -m unittest discover -s tests -p test_acceptance_dashboard_v4.py
python -m unittest discover -s tests -p test_acceptance_dashboard.py
```

测试不依赖 ROS/Gazebo/PX4。正式资料的验证仍应使用各原生产工具和原验证器，并单独保存其回执；入口不会补造回执。

2026-11-03 已在 Windows 实际执行上述新增与原入口两个模块：`test_acceptance_dashboard*.py` 共 **43 项通过**；同批视频新增与原模块 16 项通过，四模块合计 59 项。原始两份日志和结果 JSON 见[交付测试原件](../tools/diagnostics/humble53_core_stop_snapshot01/README.md)。这次仅验证纯 fixture 交付行为，没有产生新的原生测试、仿真飞行、正式 280 槽结果或完整交付验收结论。
