# 2026-11-03 接续执行记录

本记录是执行检查点，不是全项目验收报告。用户已授权继续修复、仿真、统计、交付及 GitHub 同步。正式研究仍为 **0/280**。

**10:02（北京时间）接续观察：扩展已为 2 个原始 PASS，第三场 `person_extension_dropout_seed004` 正在执行。** 第二场 `person_extension_depth_holes_seed004` 于 `01:59:49.833276 UTC` 记录 `PASS / COMPLETED`、非基础设施停止、flight exit 0；距离/高度 RMSE 为 0.752211/0.165787 m、导航有效覆盖 0.916223、真值覆盖 1.0，六项工程检查均为 true。其原终态文件为 55,135 字节，文件 SHA256 `8b1bf279e500a882edaf04cefba5f962f288d89e02023d8c882b8ce35fddfe09`；内部 `record_sha256` 为 `b86c7ad707dca76b207867cbebdf68e7a23db923386324d864570ab1da884082`，两者不混用。第三场 START 为 `01:59:53.488846 UTC`；`02:02:21 UTC` 进度仍 RUNNING。另行实际 Windows 进程查询核对原 monitor 19256、WSL 4888、waiter 28932 的创建 FILETIME 均未变，未启动并行原生任务。下面 09:44 及更早段落保留其当时含义，不将其旧计数视作当前结果。

**09:44（北京时间）实际检查点：扩展 16 正在运行，2 START、1 原始 PASS、14 未开始。** 重新读取的进度生成于 `2026-11-03T01:44:07.757396+00:00`，状态 `RUNNING`，命令与监控器的创建身份及新鲜心跳核验通过；当前为 `person_extension_depth_holes_seed004`，其 START 为 `01:38:29.546129 UTC`。首场深度噪声已于 `01:38:26.893766 UTC` 记录原始工程 PASS，未预记其余场景。核心 12/12 与安全 03 四场原始工程 PASS 均已闭合，正式仍为 0/280。

## 已实际完成

- Humble54 同源核心 12 场原始工程 PASS 已闭合，保留同一开发种子的限制。
- 扩展首场 `person_extension_depth_noise_seed004` 原始 PASS / COMPLETED，`flight_exit_code=0`、`infrastructure_stop=false`，清理残留列表为空；距离/高度 RMSE 为 0.7579153021/0.1619863085 m，有效状态覆盖 0.9162234043、真值覆盖 1.0，末端持续稳定均通过。navigation 原状态 `RECORDED_WITH_CENSORED_FAILURES` 保留。[首场最小原件](../tools/experiment_orchestration/humble54_extension_first01/README.md)含九个原始小型 JSON，七份试验报告与终态 artifact 哈希一致，终态内部摘要及 START 绑定核验通过；未读 bag 或改原评价。
- 安全 02 于北京时间 08:08:49 结束：1 INFRASTRUCTURE_ERROR、3 未执行。五条子命令退出 0，但汇总读取不存在的 `result` 字段导致 `KeyError`；source/native 原报告采用 `evaluation_status`。
- 修复只调整末尾汇总，source/native 仍由原 `read_evaluation` 严格校验。Windows 63 项专项检查运行成功，4 项平台条件跳过；其结果来自执行代理的实际工具返回，未另造原始日志。
- Ubuntu 22.04/Humble 实际 5 项回归全部通过，2.692 秒、无跳过；保存原始日志及退出码。它们是组件测试，不是五次飞行。
- 实际 native03 创建 contract03 并完成只读 schema 诊断，退出 0。首份快照调用原 helper，另两份按原始字节及完整映射等价核验。没有重判旧安全 02，没有改原登记时间，没有修改冻结的 Humble54 飞行源码。
- 修复及原始小证据已提交并推送 `d1635cf`、`c6b30d2`。

## 当前唯一飞行批次：扩展 16

- 冻结运行根：`/root/uav_tracking_fullplan_v4_humble54`；没有修改冻结飞行源码。
- [实时进度](../results/project_progress/humble54_extension16_run01/index.html)；[原计划](../results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix/plan.json)。计划于 `01:15:23.564925 UTC` 实际创建，模式 `EXTENSION_PROBE`，共 16 场开发种子 004；未消耗正式种子。
- 计划原文件 SHA256：`f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055`；登记 digest：`ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761`。这两个值分别绑定文件字节与计划内容，不能混用。
- [Linux owner 状态](../results/frozen_fullplan_v4_humble54/humble54_extension16_owner01/owner_state.json)：启动时 PID 134468、start ticks `7830987`、boot ID `f79204a4-99cd-42cf-b886-aa905b1cac6a`。09:19 的 RUNNING 记录是历史观察；当前 START/终态计数以上述 09:44 实际进度和原槽标记为准。
- Windows monitor PID 19256，creation FILETIME `134381420603083387`；owned WSL 命令 PID 4888，creation FILETIME `134381420604764583`。本轮 unified-exec session 为 29911。
- 临时防休眠 observer PID 44952，依据 `D:/WSL/UAVHumble22-validation/power_owner54/receipt04/state.json`：09:18:41 状态 `ACTIVE`，API request 返回 `2147483648`，绑定 monitor 19256 的上述创建身份；不改变全局电源策略。旧 observer 50284 不属于此当前有效收据，不能混用。

只保留一个重型原生任务，扩展批次活动期间不另开 WSL/仿真或录包分析。保留每个原始终态；基础设施或证据门失败仍先停止定位，不改称普通压力算法失败。

## 已实际启动的有条件后续等待器

Windows waiter 于 `01:37:42.141035 UTC` 启动，PID 28932、creation FILETIME `134381434621456534`，运行 `D:/WSL/UAVHumble22-validation/wait_humble54_extension_followon01.py --execute`。`01:44:04.603462 UTC` 实读状态仍为 `WAITING_FOR_EXTENSION`、`followon_launched=false`，原 monitor/WSL 精确句柄退出码均为 null；并未启动后续原生步骤。实际启动、等待快照与来源文件见[独立原件归档](../tools/experiment_orchestration/humble54_closed_followon01/manifest.json)。

等待器持有原 monitor PID 19256 / FILETIME `134381420603083387` 与 WSL PID 4888 / FILETIME `134381420604764583` 的句柄；须等待原进程退出并完成闭合核验，才有条件顺序执行八步：元数据预检、空闲检查、源码暂存、28 格容量统计、物理卷清单采集、行人指定开发录包导出、汽车指定开发录包导出、R0 定标。无自动重试，未创建正式准入、final55 最终构建、参数假设收据或新飞行。防休眠仅为临时系统请求，不改变全局电源策略；正式仍为 0/280。

## 已结束的安全 03 批次（历史检查点）

安全 03 于北京时间 08:21:54 首场 START。08:26:18 的核对为 1 START、0 终态、3 未开始；首场最后已记录采集时间约 29.5 仿真秒，owner 心跳新鲜。此时间快照不能证明此后仍在运行，应读取以下实际入口。

- 冻结运行根：`/root/uav_tracking_fullplan_v4_humble54`。
- [实时进度](../results/project_progress/humble54_safety4_run03/index.html)。
- 原生 owner：`results/frozen_fullplan_v4_humble54/reliability_v4_humble54_safety03_audit/owner_state.json`；结束后查同目录 `owner_terminal.json`、`execution_terminal.json`。
- registry SHA256：`ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf`。
- Windows monitor PID 15484，creation FILETIME `134381388887778865`；owned WSL PID 51320，creation FILETIME `134381388889337195`。本轮 unified-exec session 为 59721。
- 临时防休眠 observer PID 33500，原件位于 `D:/WSL/UAVHumble22-validation/power_owner54/receipt03/`。API 请求已接受，随原 monitor 结束释放；不改变系统全局策略。

不要再次启动原安全 02 或并行启动第二个仿真。安全 03 任一非 PASS 都按原工具停止并保留，先定位原因，再决定新的独立尝试。

08:45:25 核对：两场行人安全验证均已原始 PASS，第三场 `car_auto_unique_multi_seed004` 正在运行，检测采集时间约 24.1 仿真秒，第四场未开始。没有将运行中的汽车场景预记通过。

09:02:08 整批已完成：四场原始 PASS、20 条命令退出 0、完整 guard PASS，原生 owner 与 Windows 命令均退出 0，无待执行或未闭合槽。随后 root 串行原生查询确认无仿真进程残留，防休眠 observer 已正常释放。上述 PID/session 是已结束的历史身份，不应重启。[闭合原件快照](../tools/experiment_orchestration/humble54_safety4_closed03/README.md)已独立复核，正式仍为 0/280；扩展 16 待系统盘空闲窗口维护后启动。

## 后续按实际结果推进

1. 安全 03 已闭合，扩展入口 `D:/WSL/UAVHumble22-validation/run_humble54_extension16_probe02.sh` 已实际执行并创建上述独立计划，当前串行运行扩展 16；继续监控真实原终态，不重新启动安全批次或当前扩展计划。
2. 扩展 16 保留全部原始终态与压力失败。基础设施或证据门失败仍需先解决，不能把它归作普通算法压力失败。
3. 使用完整核心 12 + 扩展 16 的真实体积核算容量；完成两类预定 velocity 开发录包导出及 R0 定标。storage 第三 producer/driver 配对已通过独立静审及 41/41 项 Windows 回归；仍不能用组件验证代替真实 28 格测量。
4. 按 [final55 暂存说明](reliability-v4-final55-source-staging.md)建立新最终根、冷构建、前瞻登记、容量准入及封存。保留原冻结映射；原固定外置 guard 路径不变。
5. 全部准入完成、补充协议在首场 START 前登记后，执行正式核心 120 + 扩展 160。保留失败、未知、未执行和删失，不选成功种子替换原槽。
6. 完成 20 条录制 × 4 估计器配对分析、检测审核、身份/恢复与时序附件，再生成最终计划书、研究报告、图表、视频和统一交付入口。Word/PDF 需要真实渲染及逐页检查。

扩展运行期间已核对[补充评价与定标接续清单](reliability-v4-supplementary-replay-prerequisites-20261103.md)，其中物理身份恢复协议须单独在正式 START 前创建，不能由检测协议替代。另已准备[显式容量假设](reliability-v4-humble54-storage-assumptions01.json)：三项增长因子 1.15、每槽另留 16 MiB、临时公式另留 2 GiB、剩余构建 4 GiB，五类交付合计 18 GiB。Windows 实际原预算器的 assumptions schema 校验通过，独立静核算术一致；仅实际 storage-probe 确认 results/VHD 同在 D 卷时适用。它们是前瞻余量，不是 28 格测量、空间充足证明或正式准入；真实预算不足时保留差额，不通过减少余量或丢弃失败来适配容量。

本轮[核心 12 场实际计时](../tools/diagnostics/humble54_dev_wall_timing02/README.md)已提取并独立复算：owner 调用单调计时均值 19.035822 分钟，范围 17.611350–21.816790 分钟。它包含准备、飞行、归档、评价和返回后的清单处理，排除随后策略核验；不是纯飞行或算法推理时间。之前约 112 小时的正式实验估计来自旧 Humble42 六次完整 attempt，仅是历史条件外推；当前尚未获得 Humble54 完整 28 格的混合场景耗时与容量，不能作为确定交付时间。

## 关键原件

- [schema03 原始证据及绑定](../tools/diagnostics/safety54_schema_recovery03_archive01/README.md)。
- 新 driver SHA256：`6f93e58d6281aa882c4b89273fcfaa1dc1897d9651174e2b947d82bd28d5c172`。
- native03 回执 SHA256：`155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf`。
- contract03 SHA256：`0d5bc8770c039615249caeeabd2b18598564a4cf50ae31e4023f4e47ae7a30ef`。
- 原生及工具文件在 `D:/WSL/UAVHumble22-validation/`，外置 guard 位于 `/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py`。
- C 盘由 0 可用字节恢复到约 228 MiB，仅压缩 15 份本项目已停止写入的工具日志，逐份内容 SHA 不变；未删除文件。原件记录：`D:/WSL/UAVHumble22-validation/project_tool_log_ntfs_compression03.json`。D 盘完整正式预算仍待上述真实测量。
