# 未来新录制的四线程无损归档更新（2026-10-30）

根据完整样本的固定 T1/T4 比较，将主开发树中未来新录制的归档参数调整为 `zstd -T4 -19 --long=27 --check`，并同步 profile 的 `threads: 4`。归档仍在飞行进程停止后执行；原始包、历史结果及 Humble25/Humble28 冻结来源保持原字节。新来源须完成 Linux 验证与新 freeze 后用于后续飞行。

测量终态为 `D:\WSL\UAVHumble22-validation\humble25_archive_threads_benchmark02\terminal.json`，于 **2026-10-30 10:09:51 UTC** 完成，SHA-256 为 `8946d1c7ff5fe8b985eb10e83e7cb2101be5b6eaf8cad30112618377f86f0d25`。终态为 `COMPLETED_TWO_FIXED_CANDIDATES_NO_POLICY_CHANGE`；基准自身没有修改生产策略。本次源码调整另行记录于此。

| 固定候选 | 压缩管线 wall 秒 | 含校验的候选总 wall 秒 | 归档 bytes | 实际进程组采样峰值 RSS bytes |
| --- | ---: | ---: | ---: | ---: |
| `-T1 -19 --long=27 --check` | 323.464 | 469.633 | 496,177,751 | 483,291,136 |
| `-T4 -19 --long=27 --check` | 110.074 | 223.118 | 496,177,751 | 931,700,736 |

T4/T1 压缩墙钟比为 **0.34030**，本样本约减少 **65.97%**。两份压缩产物的 SHA-256 也完全相同：`f034f8339d2dcadb4ab1aefbf9124b3128189dbbd5f9ab49a52e74383408bbe3`。进程组采样峰值约为 460.90/888.54 MiB，四线程增加了内存需求。该采样值与 GNU time 的单进程峰值是不同口径，不能把各进程独立峰值相加当作同时峰值。

两个候选均在各自 900 秒总预算内完成标准 zstd 检查、完整解压 SHA/bytes 和原生全流读取。解压结果均为 **2,139,459,584 bytes**，SHA-256 为 `811835ee933d05b2e46559c67227d8335715c08d7fd381d0a4c27a1015069498`；ROS `SequentialCompressionReader` 均读完 **148,711 条消息、31 个话题**，逐话题计数与原记录一致。两个原生临时缓存最终均为空；12 个自有进程组均正常退出且无残留。原包 stat/SHA 及冻结小输入前后校验通过，独立复核的 38 项小证据 SHA 全部匹配。

测量仅使用 Humble25 的一个 75 秒干净汽车样本，固定先 T1 后 T4、各一次。管线包含原压缩包解码到 stdout，再编码候选；它不是直接从 ext4 SQLite 归档的等价计时。固定顺序也可能受缓存影响，结果没有重复测量置信区间。该终态没有通过扩展故障容量门或正式实验准入。

[现有吞吐估计](reliability-v4-throughput-20261030.md)中的 **68.26 小时**基于 Humble28 单线程完整 driver，包含飞行、归档和既有评价。此次只支持归档阶段的提速候选，不能用 0.34030 直接缩放整个估计。应在最终模型、最终来源和录制策略下取得核心与 extensions16 的实际 ext4 归档耗时、故障双流大小及峰值 spool/VHD 增长，再更新工期和宿主容量预算。

实现只改固定线程常量、实际 profile 与现有真实 zstd 集成测试的命令断言。SQLite 完整检查、精确解压 byte/SHA、原生全流/解压校验、发布副本 SHA、spool 所有权及失败保留路径保持不变。静态检查后，root 在重任务空窗实际执行 Linux `python -B -m unittest discover -s tests -p test_recording_archive.py -v`：8 项全部通过、0 跳过、用时 0.159 秒，包含两个真实 zstd CLI 集成用例。随后仍需 Humble29 的完整来源哈希绑定、构建和统一验证。29 helper 的安全 AST 检查无需放松，最终 review/commit/files/classified map 应绑定新的归档来源。
