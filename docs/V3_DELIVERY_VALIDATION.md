# v3 交付工具验证记录

本记录对应 2026-10-27 Windows 主副本的验证结果。以下执行由主代理完成并确认；本记录整理时仅重新读取文档和源码 SHA，没有重复运行测试，也没有启动仿真或读取 bag。

## 已执行结果

| 检查 | 实际结果 | 范围 |
| --- | --- | --- |
| `test_metric_supplement.py` | 12 项通过 | 已保存指标提取、缺失/不适用/零值、物理身份与原任务短遮挡恢复分母 |
| `test_full_plan_report.py` | 22 项通过 | 主 166、独立工程 16、补充 16、指标补表、检测审核与来源绑定的报告完成门 |
| `test_report_docx_gate.cjs` | 14 项通过 | Markdown 摘要及六份当前 JSON 的大小/SHA 检查、旧完成标记拒绝、来源变化拒绝；未打包真实最终 DOCX |
| Windows 全套 Python 测试 | 604 项：599 PASS、5 SKIP，退出 0 | 主代理执行会话 `42535`；SKIP 不计作通过 |

针对性检查和全套测试存在覆盖重叠，不能把上表数量相加作为互不重复的测试总数。独立工程守卫此前的 13/13 夹具通过属于既有验证，不表示已完成 16 项真实工程飞行。

本轮针对性命令为：

```powershell
python -B -m unittest discover -s tests -p test_metric_supplement.py -v
python -B -m unittest discover -s tests -p test_full_plan_report.py -v
node tests/test_report_docx_gate.cjs
```

## 本次源码绑定

下列 SHA-256 在测试通过后读取，并在写入本记录前再次核对一致。它们绑定这次交付工具实现；不替代正式研究清单及原始结果的来源摘要。

| 文件 | SHA-256 |
| --- | --- |
| `scripts/build_full_plan_report.py` | `bc64d9c2067dd891b18194ab83cf9ab254deae22390df29c8d6f0df0a54e1c7c` |
| `scripts/build_metric_supplement.py` | `222c45e5898c597199d1db5da5340c2139c08bfff64153f81aba97010a2954d6` |
| `scripts/render_research_docx.cjs` | `dd28af5ddcf3a33af71607d5fd85b850214d7d03a01bdacf552770456a3c42f7` |
| `tests/test_full_plan_report.py` | `75bb40bbb262268cdb87b0ebe4652da80732ac61b79a55ddf24dcea3e2e34d38` |
| `tests/test_metric_supplement.py` | `a0233fa043526bf8cf5d4274b513397ae0561f6b8e35f38291d1058b1d901e25` |
| `tests/test_report_docx_gate.cjs` | `f45f9622a9223161a24d7ce77adeed89a09bbc05d2239878b766011467b7d568` |

## 能说明什么

这些结果证明当前主副本的相关测试与拒绝条件已通过，包含计划绑定、终态集合、源文件变化、缺失指标及检测审核摘要等夹具。报告会保留负结果；物理身份指标与原 track_id/target_uuid 的任务连续性分别呈现，空几何任务的 ID Switch 零值不能作为有效物理身份观测。

报告完成门要求主 166、主离线 166、独立工程 16、补充 16 的真实终态与来源绑定，以及覆盖准确任务集合的指标补表。Word 门还会在实际打包前重新读取当前六份 JSON 并验证大小/SHA，拒绝沿用来源已经变化的旧完成标记。

## 仍需实际完成

正式研究尚有 PENDING 槽位，因此本次测试通过不能表述为三阶段研究已全部完成。后续按 [FULLPLAN_V3_DELIVERY_COMMANDS.md](FULLPLAN_V3_DELIVERY_COMMANDS.md) 串行执行，保留每条失败及不完整结果：

1. 完成剩余主飞行、全部主离线处理和汇总，再完成独立 16 项工程飞行与其补充评价。
2. 用真实终态证据生成最终指标补表、研究图、验收页面、固定八条演示及结果报告，核对当前来源绑定。
3. 生成真实最终 DOCX，执行 OOXML 校验、PDF 渲染及逐页图片检查；记录真实页数、检查结论与文件 SHA。
4. 在独立修订冻结根执行真实 cleanup 探针，单独核对节点退出、信号、残留和正式结果前后 SHA。

没有在本记录中认证真正的最终 DOCX/PDF 版面、真实独立 16 项飞行或真实 cleanup 探针。正式冻结源码、原始实验文件及 FAIL 判定未因这些工具测试而修改。
