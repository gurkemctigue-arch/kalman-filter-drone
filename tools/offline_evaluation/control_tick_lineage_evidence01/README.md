# control-tick lineage fix03：小源码与证据快照

这里保存当前已审 fix03、历史版本及未来执行准备，共 **32 个原文件、308,590 字节**。所有副本保留原始字节；[manifest.json](manifest.json)逐项记录原位置、相对路径、大小和 SHA256，局部 [.gitattributes](.gitattributes)使用 `-text` 防止 Git 换行转换。

当前落盘验证是 **Windows 纯合成测试 36/36 PASS**。真实 bag/events 接线验证、native logger probe 均尚未运行；这里没有正式实验结果、准入、协议或新飞行槽。打包没有重跑测试或 describe，也没有编辑 [v1 三个源文件](../control_tick_lineage_v1/README.md)、LIVE_PROGRESS 或 Git index。

## 当前修订

- [当前三个源文件的原字节副本](current_fix03/sources/README.md)；正常开发入口仍是 [control_tick_lineage_v1](../control_tick_lineage_v1/README.md)。
- [fix03 审查与修复记录](current_fix03/evidence/control_tick_lineage_fix03_review01.json)、[36 项测试 receipt](current_fix03/evidence/control_tick_lineage_fix03_tests01.json)、[实际原始日志](current_fix03/evidence/control_tick_lineage_fix03_tests01.log)及 [Windows inert describe](current_fix03/evidence/control_tick_lineage_fix03_describe01.json)。
- [fix02→fix03 差异](current_fix03/evidence/control_tick_lineage_fix03_source_diff01.patch)与 [原 revision01→fix03 完整差异](current_fix03/evidence/control_tick_lineage_full_fix01_03_source_diff01.patch)。

fix02 修复了浮点秒反算整数纳秒的歧义：按实际字段转换，在完整受支持整数域内核实来源唯一性；不能唯一确定时保持 UNKNOWN。fix03 使用实际检测诊断字段 `stamp_s`，绑定检测器源码，并验证没有错误 `acquisition_s` 回退。控制端点仍是 tick 开始，记录数值约束解不代表完整回调因果、发布完成或 PX4 执行。

当前方法 canonical 为：

```text
98c8ce9253fd1b46ef2bc5ec23f290918f4c1aa0d385d85939d050fe1fbb99dd
```

计算约定为 `json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=True).encode('utf-8')` 后做 SHA256。当前源文件 SHA：

| 文件 | SHA256 |
|---|---|
| control_tick_lineage.py | 5ef5d82999165ad2932c239f142dfa6b565cd4e43a2493c2f43c8c40be723247 |
| test_control_tick_lineage.py | d317356eeb23a23f0e05c9ed5346d4e0f950e09b3e7bb5aaf5f76d20f8ef2488 |
| README.md | d2fd12dba573cc791f1f60bf63d0a295c40e95a185c2701432402623c58ea690 |

`candidate_registration`另在会话中报告了只读独立复审、36 项重跑及额外数值 oracle；没有单独落盘 receipt/log，因此本快照没有为该会话报告编造独立文件。原 fix03 receipt 中创建时的 `PENDING` 状态保留原字节，后续会话复审未被倒填进历史 receipt。

## 历史与失败边界

- [revision01 archive](history/revision01_archive/manifest.json)保存最初三个源文件、作者 **27 项合成测试**及原 describe/handoff；其历史 canonical `9af126…`采用原作者的 `ensure_ascii=False`，保留该原约定。
- [numeric fix02 archive](history/fix02_numeric_only_archive/manifest.json)保存 schema 修正前的三个源文件、**33 项合成通过**、describe及审查记录；canonical `2d8c54…`采用 `ensure_ascii=True`。
- [完整浮点歧义反例](history/fix02_additional/control_tick_lineage_fix02_counterexample01.json)是明确标记的合成 events，保存原方法误报唯一、新逆映射保持 UNKNOWN 的对照；不是项目实录。
- [额外 F32 oracle](history/fix02_additional/control_tick_lineage_fix02_independent_oracle01.json)保存 900 组合成整数时间、182,987 次实际公式比较的数值检查；不是测得覆盖率。
- [中间失败 receipt](history/fix02_additional/control_tick_lineage_fix02_tests01.json)及 [原始失败日志](history/fix02_additional/control_tick_lineage_fix02_tests01.log)保留首轮 33 项中 **32 PASS、1 FAIL**。该轮失败暴露了异常原因未显示，随后修复；失败原件未被成功日志覆盖。

历史目录仅复制清单中的原小文件，未收录运行产生的 `__pycache__`/pyc。

## 未来执行准备

- [person1 DEVELOPMENT 真实接线验证卡](future/control_tick_lineage_development_validation_card01.md)：使用现有 public timing_v2 export → lineage analyze；须等 core owner 全部结束，在单重任务窗口执行。输出明确为 DEVELOPMENT，不伪造 FORMAL120/protocol/sidecar。
- [logger 最小 probe 原件](future/rcutils_prefix_clock_probe01.py)与 [未来时间源核验卡](future/rcutils_prefix_clock_future_audit01.md)：仅已准备并做过静态 AST 检查，尚未运行。未来核当前进程实际库来源及 system/steady/受控 ROSClock 对照；当前 audit 不能追认全部历史进程。

DEV 卡原位置为 `D:/WSL/UAVHumble22-validation/research_delivery_static_audit54_01/control_tick_lineage_development_validation_card01.md`；logger 两原件位于 `D:/WSL/UAVHumble22-validation/`。历史证据原位置也逐项列于 manifest。复制文件内部的原 Windows/Linux 绝对路径保持不变，属于原来源记录；迁移到新电脑后仍需按执行卡绑定实际环境。

[snapshot_verification.json](snapshot_verification.json)记录本次小文件逐字节核对及生成文档的 SHA，不表示运行了算法、native 接线或正式试验。
