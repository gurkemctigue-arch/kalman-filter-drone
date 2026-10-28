# v4图表与文档工具复用清单

本清单只审查源码入口，未读取留出录制、生成结果或执行视频转码。v3报告和图表保留其原协议与版本，不直接更名为v4。真实图表必须在相应录制及独立评价完成后生成。

| 入口 | 可复用部分 | v4使用边界或待适配项 |
| --- | --- | --- |
| `scripts/summarize_reliability_v4.py` | 已核验计划/槽/报告hash的120核心与可选160扩展快照；逐flight CSV、分组、配对差及HTML | 新版就绪，16项合成JSON测试通过。结果仍需实际不可变计划与终态槽；运行中不提前采纳零散报告。它不生成科学图或Word |
| `scripts/plot_stage23_acceptance.py` | 同seed成对散点、原结果矩阵、身份机会分母条形图、PNG/PDF与绘图数据来源 | 输入是旧`OFFLINE_STAGE23_PLANNED_SEED_PAIR_SUMMARY`，不可直接接新summary。可复用绘图函数设计，须显式映射新分组/八状态/REQUEST至完整Clock身份指标，保留失败点和缺失种子 |
| `scripts/plot_research_results.py` | Matplotlib PNG/SVG保存、配对区间和覆盖率图的视觉形式 | 固定旧`adaptive_kf`、四份`stage1_final_v2`录制与人工写死的132张审核说明；旧surface-anchor/故障seed回放不等于新导航20条独立flight四法。需使用新replay汇总的`geometry_adaptive_kf`、实际分母与来源，不能原样运行后称v4 |
| `scripts/plot_stage1_acceptance.py` | 轨迹、深度采样间断和遮挡/phase时间线形式 | 固定四个旧trial名，仅读telemetry而非新导航物理评价；可作运行过程示意，不能据此计算base_link跟随或KF世界坐标准确性 |
| `scripts/build_acceptance_dashboard.py` | 中文静态HTML、相对证据链接、原视频卡片、缺失清单和报告历史 | 正式进度分支固定166主+16扩展；旧身份字段与评价器schema选择也须逐项更新。新summary HTML可先提供v4槽位入口；完整新卡片不能绕过原哈希/原终态 |
| `scripts/build_full_plan_report.py` | 小JSON生成中文Markdown、来源SHA、图表/视频索引与缺失表的框架 | 明确校验`planned_flights=166`和旧166+16六份台账，不能接120+160新协议。需独立v4报告入口或有版本区分的schema，保留旧完成门 |
| `scripts/render_research_docx.cjs` | A4中文排版、真实表格/链接、PNG/JPEG附录、输入和输出SHA、已有文件保护 | 完成来源门强制旧166+16台账，不能删除门后把v4草稿包装成最终版。须先实现并测试v4最终来源合同，再渲染对应Markdown；依赖Node `docx` |
| `scripts/create_final_plan_docx.py` | 计划书Markdown转Word、中文字体、列表编号和页码 | 输入固定`docs/FINAL_PLAN.md`，仅输出路径可配；它是计划书转换器，不能代替结果报告或验收来源检查。生成前应核对最终计划与v4实际比较边界 |
| `scripts/build_browser_demos.py` | 显式指定录制的H.264副本、原帧数/时长/逐帧相对时间核对、来源SHA与浏览器页面 | 逻辑基本可复用；依赖ffmpeg/ffprobe，必须在重任务结束的窗口运行。固定/预先说明的示例seed包括失联、悬停和重选，不据样例选择推算成功率 |
| `scripts/stage2_identity_contact_sheet.py` | 按图像原header与身份JSONL时刻严格匹配的接触表，缺图留空；amodal框明确标识 | 需实际原bag、图像解码及Pillow，属于重分析窗口；不能现在与SITL并行。新版身份JSONL字段经实际检查后复用，不能把投影框当可见人工标签 |

## 真实资料齐备后的顺序

1. 从不可变core/extension计划与槽记录生成新summary，保留全部120/160计划分母及终态；同测量四法另接已登记的replay汇总。正式门未登记或矩阵未执行时，标题只标开发/待完成。
2. 科学图从已保存、已核验的小JSON/CSV生成，输出PNG及SVG/PDF，并保存输入SHA、脚本SHA、软件版本与绘图数据。逐flight/seed为样本单位；右删失不填0；双方PASS只是单列条件子集。
3. 对明确记录的示例做视频副本与时间对齐接触表。原视频、原bag和失败记录不改写；遮挡/长丢失/重选尾段保留。
4. 根据真实计划、登记、全部终态、检测审核和replay来源生成新版中文报告。Word最终门须同时区分“全部槽已尝试”“独立证据充分”“工程全部通过”，不能把其中一个当作另一个。
5. Word到PDF目前没有仓库内通用转换入口。选定实际可用的Word或LibreOffice后登记渲染器版本，核对页数、表格跨页、图像/链接和中文字体，再发布新版本；不覆盖v3。

此清单未执行依赖探测或兼容性保证；列为可复用的绘图/排版框架仍需新版fixture检查和真实输入核验。当前不会生成空矩阵假图或假Word结果。
