# Humble43 原生 v2 组件04真实验证快照

实际 UAVHumble22 运行已退出0：**85项全部通过、0失败、0错误、0跳过**，并完成3项无实际动作的工具描述核验。本目录保存原工具、纯调度测试与真实原生结果的最小字节快照；它不代表飞行验收、安全4通过、最终研究准入或正式280完成。

| 原生测试模块 | 实际数量 | 结果 |
|---|---:|---|
| development_calibration_v2 | 30 | 全部PASS，无跳过 |
| development_final_root_v2 | 40 | 全部PASS，无跳过，包含9项真实冻结authority测试 |
| seal_development_final_source_v2 | 15 | 全部PASS，无跳过 |

原[root_terminal.json](evidence/native04/root_terminal.json)的状态为 `PASS_NATIVE_85_COMPONENT_TESTS_ONLY_NOT_ADMISSION`，SHA256为 `9e5826f023e05f0ab6488cfa5f5909ac87b69be1e7d254772ed495fcbd9c1742`。三项describe均返回0、`actual_action_executed=false`，且实际canonical与原revision02清单匹配：

- connection：`556d5fcd280a92ac50e7cbad2c7e0b634841e046172fa29a0ec1274a075f9531`
- calibration：`02ed94b29a4aa207b9860474c595e382d29ef7eada314c46a2eaedaa0754eb8c`
- seal：`a194e1910477f8e2850dcbcf91512be6c413880df98a525812f3ccc89533fbfb`

原终态报告10个部署文件字节未变，finally核验1940个原文件；本次peer与归档没有重新哈希那1940个文件。8次空闲采样均ready，锁状态依次为3次ABSENT、5次FREE。这些采样不能解释原锁路径此前缺失的原因。

此前原Humble02的9项锁争用ERROR和组件03的测试前调度拒绝均保留：03因 `Expected original machine lock identity is unavailable` 返回 `tests_run=false`，没有运行85项，不能计作85项失败或通过。04新调度观察区分ABSENT与FREE；缺失时只读检查精确普通/已删除FD引用，权限、解析、界限或竞态不确定时拒绝。它不创建、打开、删除或持有机器SITL锁，子测试继续使用原 `run_lock`，没有修改源或跳过9项真实authority测试。本快照未取得03的独立原始分流日志，不重建或冒充该日志。

[实际peer核查收据](review/humble43_v2_components04_actual_peer01.json)逐项核对原85结果、真实stderr中的ok记录、9项authority、3项canonical及8次空闲证据。[准备回执](review/humble43_v2_components04_preparation01.json)和[相对03的源码差异](review/root_humble_v2_components04_vs03_01.diff)保留调度改动的范围。新增独立纯测试28项全部通过，但其[小回执](review/test_root_humble_v2_components04_lock_observation01_run01.json)明确原运行只获得工具合并解码输出，未保存分流原始字节日志；这些纯测试与真实85项分开计数。

目录内 `evidence/native04/` 原样保存终态、三个suite结果及stdout/stderr、三个describe及stderr，包括原本为空的日志。`tools/` 中共用helper只复用了 `_suite` 入口，没有执行其安装main。v2实际10文件与revision02依据见[前一具名快照](../humble43_extension_alignment_v2_snapshot/README.md)；本目录不复制权重、bag、遥测、全物理身份报告或1940文件清单。

工具仍依赖本机 `/mnt/d/WSL/UAVHumble22-validation`、实际43冻结根与Humble环境；克隆本目录不构成独立可运行环境。安全4、扩展16、容量、定标、最终封存与正式准入分别依据各自真实记录，正式仍0/280。

`ARCHIVE_MANIFEST.json`记录23个原始payload文件的来源、字节数与SHA256；`SHA256SUMS`覆盖这23个文件、本说明和manifest，排除校验表自身。所有复制保留原始字节，不更改旧快照或原证据。
