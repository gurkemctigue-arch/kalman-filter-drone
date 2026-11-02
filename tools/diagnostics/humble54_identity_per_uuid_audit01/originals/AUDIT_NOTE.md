# Humble54 已有身份报告的分任务提取

这是现有报告的描述性提取，不是重新评价或新增验收。源 schema 来自 `scripts/evaluate_physical_identity.py:340–442`：主口径是 `conservative_task_time_identity.tasks` 与其 `timeline`；顶层 `tasks` 属于诊断关联统计，不能代替完整请求任务网格。单独诊断帧口径来自 `conservative_selected_identity`。

准备阶段只读取原计划、四个小槽摘要和评价脚本/五项直接依赖，SHA 均与计划相符。`inputs_prepared.json` 固定这些小文件及原终态报告 SHA，准备时完整报告读取次数为 0。评价脚本 SHA 为 `3a0b640a309ad811cc13687482bf6b0992fcc56c9a939bdccccaf5b9c1af57d8`。

收到 root 在安全 01 命令结束、实际进程查询无匹配之后的明确空闲信号，实际执行：

```powershell
python -X utf8 -B D:/WSL/UAVHumble22-validation/humble54_identity_per_uuid_audit01/extract_per_uuid.py --output-dir D:/WSL/UAVHumble22-validation/humble54_identity_per_uuid_audit01/run01 --root-idle-signal root_explicit_idle_permission_after_safety01_exit_and_matching_processes_empty
```

执行返回 0，于 `2026-11-02T23:46:37.015227+00:00` 完成。四份现有报告分别为 1,663,576、1,692,013、3,066,769、7,660,044 字节，共 14,082,402 字节。它们逐份顺序读取，每份只打开一次，解析后不保留原大报告对象。每次缓冲字节的 SHA 与原槽及原评价完成记录匹配，解析后重算同一缓冲 SHA，文件 size/mtime/ctime/device/inode 前后相同。这不是第二次独立读取文件内容的事后 SHA 检查。

| 原场景 | 首次请求：正确 / 完整网格 | 未知 | 已知覆盖率 | 重选请求：正确 / 完整网格 | 未知 | 已知覆盖率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 行人交叉 | 219 / 322 | 103 | 0.680124 | 430 / 431 | 1 | 0.997680 |
| 行人多目标主动云台 | 217 / 322 | 105 | 0.673913 | 431 / 432 | 1 | 0.997685 |
| 汽车交叉 | 211 / 322 | 111 | 0.655280 | 429 / 432 | 3 | 0.993056 |
| 汽车多目标主动云台 | 200 / 322 | 122 | 0.621118 | 414 / 431 | 17 | 0.960557 |

八次请求任务的已知错误数均为 0，但未知没有算作正确。没有引入任何每 UUID 的验收阈值，也没有将整体 80% 工程门槛移到各任务上。

每任务固定网格计数、覆盖率和未知理由均从保存的时间格逐项核算，与报告任务摘要、报告整体摘要和小槽原始完整分母对账。完整网格总数分别为 753、754、754、753；单独诊断帧数为 752、753、743、714。两个口径保持分开。尤其汽车多目标主动云台完整口径为 614 正确 / 0 错误 / 139 未知，共 753 格；诊断帧为 619 / 0 / 95，共 714 帧。

主未知理由是 `unknown_identity_evidence_in_time_cell` 或 `no_identity_evidence_in_time_cell`，另保留未确认和任务跨格边界。诊断未知帧还记录外部遮挡、没有新鲜所选检测及个别多候选物理身份。诊断帧理由与主时间格理由单位不同，不能逐数互相替代，也不能凭这些标签断言 YOLO、通信或控制根因。`summary.json` 保存所有 UUID、请求/确认时刻、原初始独立物理映射、每任务未知理由和连续未知区间；`summary.md` 是简表。

本次没有读取 bag、模型或原始遥测，没有导入/运行评价器、ROS、WSL 或 native；没有修改源码、原报告、原槽或原验收结论。源报告的几何标签和物理身份没有重新独立标注。原始整体 PASS 与未知边界继续保留，本结果不证明连续身份确定性或总体可靠率。

输入卡 SHA256：`0d728975c11aac0816d9a2d633eec600f4622ba375e356056b8bdb8450f2a9c4`。

单次脚本 SHA256：`405c9fa0500a07615a0d4421ab5f8e42e13a3e77162d4d551d871382ce3a3428`。

实际 `run01/summary.json` SHA256：`ed288a6ba4fca970aa7eeb755679c399d0b04962fae6ebcfe4d7e250dd5ca383`。
