# 正式飞行期间的 Windows 磁盘资源检查点

检查时间：2026-10-27 18:00–18:04，Asia/Shanghai。只在 Windows 侧读取指定目录的文件元数据、发行版注册路径及 pagefile 配置；未启动 WSL、读取 bag 或数据库内容、计算大文件哈希、构建、测试、移动、删除或修改配置。本文保存在主副本，未写入正式冻结根。

## 容量快照

| 时刻（+08:00） | C 可用 / bytes | D 可用 / bytes |
| --- | ---: | ---: |
| 18:00:00 | 5,031,157,760 | 244,854,763,520 |
| 18:01:53 | 5,030,789,120 | 未在此时记录 |
| 18:03:51 | 5,026,394,112 | 242,807,836,672 |
| 18:04:30 | 5,025,722,368 | 242,500,440,064 |

约四分半钟内 C 减少 5,435,392 bytes；此窗口没有复现约 50 MB/飞行的持续增长，不能把较早约 0.5 GB 的差额线性外推到剩余飞行。检查没有覆盖全部 C 盘，也没有历史文件大小基线，不能据此确定较早差额的完整来源。

## WSL、swap 与转储

| 精确位置 | 大小 / bytes | 创建或修改时间（+08:00）与检查结果 |
| --- | ---: | --- |
| `D:\work\SysYToolchain\wsl\Ubuntu\ext4.vhdx` | 36,523,999,232 | 18:00:01 修改；发行版注册 BasePath 也在该 D 盘目录，Ubuntu VHD 增长不直接占用 C |
| `D:\pagefile.sys` | 配置分配 28,898 MiB | Windows `Win32_PageFileUsage` 返回；当时使用 4,568 MiB、峰值 6,693 MiB，不能当作 C 盘增长 |
| `C:\Users\李东易\AppData\Local\Temp\D1D2CF03-2605-4F90-8185-AF1D871428A1\swap.vhdx` | 37,748,736 | 17:27:23 创建和修改；18:01:53 复查大小、修改时间不变 |
| `C:\Users\李东易\AppData\Local\Temp\wsl-crashes` | 0 个文件 | 指定目录递归检查为空；目录最近修改 01:09:21 |
| `C:\Users\李东易\AppData\Local\CrashDumps` | 不存在 | 用户级常见 dump 目录未发现 |
| `C:\ProgramData\Microsoft\Windows\WER\ReportQueue` | 0 个条目 | 目录为空 |
| `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_java.exe_b1e1ea2c4ffd47c088f52b2cbe7433b85641b737_aa480012_51699fc9-7351-4dec-81e4-2693a62269d3\Report.wer` | 17,832 | 17:43:41 修改；该报告目录只有此小文件 |
| `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_java.exe_b1e1ea2c4ffd47c088f52b2cbe7433b85641b737_aa480012_f12f762a-2383-4407-ac24-11338a39b6df\Report.wer` | 17,832 | 17:37:36 修改；该报告目录只有此小文件 |

这只排除了已检查位置中的重复大型转储，没有证明全系统不存在其他 dump。此次未找到能够安全认定为本项目新生成、可搬迁的大型转储。

## 活动日志与其他已查位置

以下路径均为活动应用数据，仅记录大小，不是清理或移动建议。特别是正在使用的 SQLite/WAL 不应按单文件搬迁。

| 精确位置 | 大小 / bytes | 观测修改时间（+08:00） |
| --- | ---: | --- |
| `C:\Users\李东易\.codex\logs_2.sqlite` | 75,636,736 | 18:01:24 |
| `C:\Users\李东易\.codex\logs_2.sqlite-wal` | 42,353,632 | 18:01:53 |
| `C:\Users\李东易\.codex\thread_history_1.sqlite` | 194,412,544 | 17:56:43 |
| `C:\Users\李东易\.codex\thread_history_1.sqlite-wal` | 2,286,632 | 18:01:52；18:00:48 时为 1,009,432 bytes，说明活动日志确有写入，但不足以解释较早全部差额 |
| `C:\Users\李东易\.codex\sessions\2026\10\25\rollout-2026-10-25T15-06-05-01a171e1-7e74-7131-8917-29e5f76048ae.jsonl` | 43,810,078 | 18:01:10 |
| `C:\Users\李东易\.codex\sessions\2026\10\27\rollout-2026-10-27T02-25-59-01a17976-5071-73e1-a427-9defbfdc9376.jsonl` | 7,266,332 | 18:01:19 |
| `C:\Windows\Temp\小灰-20261021-2147b.log` | 17,305,922 | 16:52:58；非项目证据，未操作 |

`C:\Users\李东易\AppData\Local\Temp` 顶层 220 个文件共 93,340,808 bytes，其中近四小时修改的文件共 2,773,639 bytes；该数字不包括子目录。定点检查其下一层未发现近期大型 dump，唯一识别的 swap 见上表。`C:\Users\李东易\AppData\Roaming\Code\logs\20261023T190947` 内 174 个文件合计 106,992 bytes；`.codex\log\codex-tui.log` 仅 17,580 bytes，最近修改为 2026-05-10。

未进行搬迁、删除、关闭应用或配置调整。后续由主运行过程每约十个试验检查 C/D 实际余量；本页是资源审计快照，不改变正式实验状态，也不能替代退出清理的真实验证。
