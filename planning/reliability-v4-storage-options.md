# v4 存储容量核查与可行范围

本文件记录 2026-10-29 的容量调查、用户授权清理结果与未执行的辅助方案，不是工程验收记录。没有修改旧槽结论、失败录制、绑定工件、冻结源码或实验协议，也没有给任何实验新增 PASS。

最新结果：用户明确授权删除一款已确认约71.217GiB的游戏目录，已精确执行并核实目录不存在；删除后宿主D盘可用225.486GiB，后续后台写盘约223.5GiB。本次仅删除该授权目录，其他用户文件、系统分页与虚拟机磁盘均保留。全盘私有清单及删除证据保存在项目外的validation目录，不上传GitHub。新增空间达到用户本次腾出至少50GiB的目标；正式实验是否足够，仍须用最终28格开发数据及暂存峰执行真实准入核算。

初次调查结论仍成立：**现有遥测和旧原始 SQLite 的普通 NTFS 透明压缩，以及当前 VHD 的整理空间，都无法提供数十 GiB 的缺口。停止为这些小收益占用仿真重任务窗口。** 初次调查未清理用户文件；下列较早容量快照用于保留估算来源。

## 当前磁盘快照与统计口径

本次最后一次 `Get-PSDrive` 快照为 C 空闲 565,288,960B（约 0.526 GiB），D 空闲 171,073,183,744B（约 159.33 GiB），E 空闲 10,363,125,760B（约 9.65 GiB）。空闲量随运行变化；它不是后续任务完成时的保证。

论文主线原规划包含 120 个 core 和 160 个 extension 正式槽。此前仅把四条 45s clean 类开发槽的体积外推至 280 条，均值情景约 139.32 GiB，观测最大情景约 149.79 GiB；再加开发、收尾临时峰与交付，曾粗估 162–182 GiB。该外推没有充分覆盖故障条件的双路 RGB-D 熵和其他条件差异，不能作为容量足够的结论。

下面文件大小均为逻辑 bytes，除明确列出的 NTFS 属性外，本轮没有测量原件实际簇分配，更没有读取或 hash 大文件内容。Linux `df` 显示的 VHD 虚拟剩余容量不能替代 Windows 宿主盘可用空间。

## 小收益候选的精确范围

| 候选 | 范围与结果 | 可行范围与决定 |
|---|---|---|
| 遥测透明压缩 | `results` 本层试验及当时 27 个直接 `frozen_*` 根下试验，共 367 个 telemetry，合 2,435,311,331B；严格关闭认证仅 24 个，合 756,672,934B | 当前认证范围即使极端压缩，节省也严格小于 0.705 GiB。全部候选逻辑总量也仅约 2.268 GiB。保留副本探针，暂不执行压缩 |
| 旧 `.db3` 透明压缩 | 扩大至 `results` 各直接容器、其直接子目录及显式 rosbag，共检查 369 个 bag 目录；仅 3 个原始 `.db3`，合 1,845,522,432B，均未设置 NTFS compressed 属性 | 仅两个 v2 文件可证明 writer 已停，合 1,497,260,032B，潜在节省严格小于 1.394 GiB。三条均无 metadata.yaml，不能将关闭 writer 等同录制有效。保留原件，不安排压缩 |
| WSL VHD 整理 | 总协调只读测得 `D:\WSL\UAVHumble22\ext4.vhdx` 22,577,938,432B（约 21.03 GiB），ext4 已用约 17.76GB | 可整理上界不到 5 GiB，实际可能更少。没有足够收益支持为此停止 WSL；不对挂载中的 VHD 设置普通 NTFS 压缩，也不修改或移动 VHD |
| pagefile | Win32_PageFileUsage 显示系统 pagefile 在 D，分配 22,528 MiB，本次使用约 141 MiB | 属于系统配置，不能把低当前使用量当成可直接释放空间。本次未调整 pagefile |
| E 盘 | 当前约 9.65 GiB 空闲 | 不足以承担完整正式数据集，不能当成消除缺口的方案 |

严格关闭遥测清单的完整 Windows 路径、精确 bytes、mtime、小型证据路径和摘要保存在：

`D:\WSL\UAVHumble22-validation\ntfs_telemetry_copy_probe01\closed_telemetry_manifest.json`

同目录另有 CSV。清单只覆盖上述明确浅层范围，并非完整磁盘或未来新槽目录。24 个纳入项需具备绑定终态槽、空 residual process 列表和所有 writer 的整数退出码；独立 clean 使用已结束 closure、monitor 结束字段和退出记录。343 个不满足该严格证据组合的候选逐项保留排除原因。FAIL、INFRASTRUCTURE_ERROR、EVALUATION_PENDING 保留原结论；“关闭”仅说明 writer 已结束。

旧原始数据库的完整清单位于：

`D:\WSL\UAVHumble22-validation\legacy_raw_db3_inventory01\legacy_raw_db3_inventory.json`

两个有关闭证据的文件为 `frozen_fullplan_v2/fullplan_v2_position_compatibility_car_position_adaptive_kf_seed02/rosbag/rosbag_0.db3`（907,784,192B）与 seed03 同路径（589,475,840B）。两条的 bag 退出码均为 -9，缺少 metadata.yaml；另有 `frozen_fullplan_v3/fullplan_v3_stage23_s3_car_gimbal_active_seed001/rosbag/rosbag_0.db3`（348,262,400B）没有 summary/exit 关闭认证。不能把这些失败/未证工件当成正常已验收 bag。

## 历史故障工况揭示的容量风险

轻量元数据表位于：

`D:\WSL\UAVHumble22-validation\historical_fault_storage01\historical_fault_storage.v3.json`

同目录有 `.v3.csv` 和 `READ_ME_FIRST.md`；引用 v3 即可。中间 v1/v2 文件仅保留准备过程，不用于完整时长汇总。数据来自旧 `frozen_fullplan_v3`，10 个故障 trial 的 rosbag metadata 都注明 **Jazzy、sqlite3、FILE zstd**。每个工况行人/汽车各一条，登记跟随时长 45s。10 条均通过 metadata 中非零话题消息数证明同时录制原 `/camera` 与注入 `/research/camera` 的 RGB 和 Depth。

| 工况 | 可用历史条数 | 达到登记跟随终点的条数 | 足时长压缩 bag 数据逻辑 bytes | 保留的中止试验 |
|---|---:|---:|---:|---|
| combined | 2 | 2 | 664,035,701–762,918,449 | 无 |
| depth_noise | 2 | 2 | 639,959,062–826,688,412 | 无 |
| depth_holes | 2 | 1 | 530,279,278 | car：53,809,171B，flight_aborted，无 follow_start |
| dropout | 2 | 1 | 316,743,456 | person：425,345,081B，follow 26.748s 后 flight_aborted |
| latency | 2 | 2 | 615,425,644–736,038,358 | 无 |

到达终点的 monitor follow 时长约 44.9–44.948s。达到时长与工程验收结果分别记录，例如 car dropout 仍保留非零 monitor 退出码。中止试验没有删除，也不能用它们的小体积预算完整时长录制。

另外列出 8 条同旧根、登记 45s 的 clean 上下文，压缩 bag 数据为 416,644,541–452,852,207B，均值 440,793,336B。这些 clean 的运动/云台配置并不严格配对，只提供容量参照。

敏感性演示：把各工况足时长历史观测最小/最大值机械用于五工况各 20 条的 100 个故障槽，bag-only 合计为 **51.53–59.10 GiB**；把同旧 clean 均值用于 100 条则为 **41.05 GiB**，差值 **10.48–18.04 GiB**。该范围不是置信区间、容量上界或对 Humble16/后续冻结的预测。每工况仅 1–2 条，类别有缺测，旧源码、启动收尾、话题配置、传感器噪声熵和渲染配置都可能改变体积；还未计 telemetry、导航逐帧日志等。

这个先验支持在 clean-only 估算之外保留十余 GiB 故障敏感性余量，并尽早用新冻结的扩展开发槽实测各工况。不能等全部 core 完成后才检查 extension 是否能装下。

## 保留但尚未执行的副本探针

`D:\WSL\UAVHumble22-validation\ntfs_telemetry_copy_probe01\` 保留 `Invoke-TelemetryCopyProbe.ps1`、`measure_telemetry.py`、清单生成器和 `EXECUTION_CARD.md`。本轮只完成 PS/Python AST 静态检查和默认 metadata-only 路径预检。没有复制/压缩遥测，没有启动跨 OS 内容测量，没有因此给实验新增 PASS。

该脚本若以后使用，只在全新专用目录创建副本，对副本显式执行单文件 `compact /C /F`，不用递归或 `/EXE`，原件不接收写入。记录原件/副本前后 SHA、Windows/WSL 逻辑 size 与 JSONL 行数，以及 `GetCompressedFileSizeW` 实际分配 bytes、压缩属性和 LastWriteTime。默认无 `-Execute` 时不读遥测内容、不启动 WSL、不复制或压缩；实际试验仍须总协调安排独占窗口。

因为当前收益很小，暂不安排该重读副本试验，也不将“脚本已准备”当成透明压缩已验证。

## C 盘写入核查与后续选择

项目源码、node_modules、实验输出位于 D。Linux 实验入口将 TMPDIR 和 ROS_LOG_DIR 指到对应 results/runtime；Linux 缓存的宿主 VHD 也在 D；Node24 staging 指定 tools_root；Word 转换器把临时 PDF 放在目标同目录。当前没有启动实际 Word 渲染。

当前进程 TEMP/TMP 位于 D 盘，未清理。Windows LOCALAPPDATA/APPDATA 仍在 C，自定义 pip/npm/HF/YOLO 缓存变量未设置；以后若在 Windows 安装依赖，可为那次子进程明确选择 D 盘项目缓存。本轮没有发现这些工具正在向 C 写入本项目大缓存的证据。

C 盘曾短时只剩约 20MB，后续只读快照恢复约 0.53–0.57 GiB。本轮有限范围查询不能证明短时下降来源。开发工具的会话数据库及 WAL 仍有活跃 writer，不能作为可回收空间；没有压缩会话、修改活跃 SQLite/WAL 或清理用户文件。私人目录和工具会话的盘点明细不进入仓库。

后续只监控 C，不为了小额空间操作运行中的工具数据。实际图表与 Word/PDF 交付仍等待真实正式数据。新正式数据盘应能承受完整数据、未通过试验的保留、临时收尾峰和交付余量；迁移新的输出位置时应在新冻结/计划中明确记录，保持原有绑定工件路径和内容不变。已有旧数据或用户其他文件如需清理，应由用户先明确可清理范围，本文件没有发出删除、移动或清理命令。
