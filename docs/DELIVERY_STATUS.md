# 三阶段交付状态

本文记录冻结 **v3 历史归档**，以下完成计数和环境结论限定于该修订。正在开发的 v4 尚未完成正式验收；Ubuntu 22.04/Humble 已另行完成隔离构建、桥接与部分开发飞行。当前进展见 [v4 状态](V4_WORK_STATUS.md) 与 [Humble 实测记录](HUMBLE_ISOLATED_VALIDATION.md)，不能将本页历史“完成归档”理解为 v4 全部通过。

2026-10-28：三个阶段的代码、仿真集成、预定研究执行、统计、图表和演示均已完成归档。工程验收仍包含失败，以下执行完成计数不能解释为算法成功率或所有性能要求均已达标。

| 范围 | 终态 | PASS | FAIL | INTERRUPTED |
| --- | ---: | ---: | ---: | ---: |
| 阶段一：状态估计与单目标闭环 | 100/100 | 66 | 34 | 0 |
| 阶段二：多目标中的指定个体 | 26/26 | 19 | 7 | 0 |
| 阶段三：三轴云台协同 | 40/40 | 22 | 17 | 1 |
| 主研究 | 166/166 | 107 | 58 | 1 |
| 独立工程扩展（每条件一次） | 16/16 | 2 | 14 | 0 |

主离线台账为 160 RECORDED、4 INCOMPLETE_EVIDENCE、2 NOT_APPLICABLE_NO_SELECTED_TASK；扩展补充台账为 15 RECORDED、1 INCOMPLETE_EVIDENCE。主研究失败分类保留 107 SCORED_PASS、50 SCORED_FAIL、1 CONFIRMED_INFRASTRUCTURE_FAILURE、4 REPORTED_INFRASTRUCTURE_FAILURE、4 INCOMPLETE_OR_UNKNOWN。基础设施失败和证据不完整不提供伪造的算法性能分数。

最终报告绑定当前主计划、汇总、离线、扩展及补充清单的 SHA 和文件大小，指标表覆盖 182 个主研究与扩展任务。主计划 SHA 为 `58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`，冻结原始数据未改。

本地结果入口（不随 Git 提交）：

- `results/frozen_fullplan_v3/交付入口.html`：视频、报告、计划书与证据的统一入口。
- `results/frozen_fullplan_v3/验收总览.html`：逐项结果、失败和证据入口。
- `results/frozen_fullplan_v3/browser_demos_v3/index.html`：8 段浏览器可播放演示。
- `results/frozen_fullplan_v3/full_plan_report_v3.md`：完整研究报告，配有 `.sources.json` 来源清单。
- `results/frozen_fullplan_v3/研究结果报告_v3_最终交付.docx`：最终 Word 报告，PDF 位于 `report_document_v3_final_delivery/研究结果报告_v3_最终交付.pdf`。
- `results/frozen_fullplan_v3/metric_supplement.{json,md,csv}`：逐飞行和分组指标。
- `results/frozen_fullplan_v3/full_plan_figures/`：6 组 PNG/PDF/SVG 图表及 CSV。

计划书见 [最终 DOCX](最终版毕业设计计划书_最终版.docx) 和 [PDF](最终版毕业设计计划书_最终版.pdf)。结果归档边界与复现方法见 [结果工件说明](RESULTS_ARTIFACTS.md)。

另外两次独立清理验证已在新冻结根完成：stage1 的 8 个、stage3_multi 的 9 个 ROS 节点均干净退出，无观测到的残留进程、无正式台账变化。该根四个 ROS 包构建、导入隔离、604 项 Linux 测试通过。清理证据保存在本地 `results/frozen_fullplan_cleanup_v3/`，不并入研究分母。

最终主副本验证为 607 项 Python 测试（602 通过、5 个平台跳过），另有 14 项 Word 完成来源门检查通过。该主副本验证与正式 v3 冻结 Linux 的 531 项、独立 cleanup 冻结根的 604 项分别记账。

本页 v3 历史数据的实际验证环境为 Ubuntu 24.04.1 WSL2、ROS 2 Jazzy、Gazebo Harmonic、PX4 v1.17.0；该归档不提供 Ubuntu 22.04/Humble 验证。完整 ReID、开放环境搜索、避障和真实机飞行仍属于后续扩展。身份未知样本、未稳定区间和现有失败应作为进一步优化的依据。
