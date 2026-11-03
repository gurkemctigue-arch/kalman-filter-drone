# 原开发矩阵剩余槽的串行采集

这是外置工具，仅负责 `SUPERVISED_PENDING_COLLECTION`。它不会改旧 owner、旧等待器、原计划、源码、评价器或已有终态；不自动重试，不执行 capacity、导出、正式规划或正式试验。

当前准备状态是工具和小型假命令测试已完成，**没有启动真实采集**。root 应等第六槽 `person_extension_speed_changes_velocity_seed004` 真正完成压缩、全部评价与终态写入，并完成当前离线抽图，核对后再显式启动。若第六槽出现新的未知或安全/来源问题，检查阶段会拒绝，不创建采集 owner。

默认只读检查（在原 native 路径可解析的环境运行）：

```bash
python3 -B /mnt/d/WSL/UAVHumble22-validation/collect_humble54_pending03.py \
  --after-slot person_extension_speed_changes_velocity_seed004
```

root 核准后的真实启动命令（下列命令尚未执行）：

```bash
python3 -B /mnt/d/WSL/UAVHumble22-validation/collect_humble54_pending03.py \
  --after-slot person_extension_speed_changes_velocity_seed004 \
  --output /mnt/d/基于yolo和卡尔曼滤波/results/diagnostics/humble54_pending_collection03 \
  --execute
```

输出目录必须全新且在冻结树和原结果树之外；上述名称若已存在，必须选新名称，不覆盖或自动恢复旧 owner。

从 Windows 使用现有独立进度监视器拥有该单条命令，可以另外记录 WSL 子进程创建身份及退出码：

```powershell
python -B scripts/monitor_project_progress.py run --output results/monitor_humble54_pending_collection03 --phase simulation --task-id humble54_remaining10_pending_collection03 --label humble54_remaining10_pending_collection03 --events results/diagnostics/humble54_pending_collection03/events.jsonl --plan results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix/plan.json -- wsl.exe -d UAVHumble22 -- python3 -B /mnt/d/WSL/UAVHumble22-validation/collect_humble54_pending03.py --after-slot person_extension_speed_changes_velocity_seed004 --output /mnt/d/基于yolo和卡尔曼滤波/results/diagnostics/humble54_pending_collection03 --execute
```

## 逐槽条件

程序先核原计划完整文件 SHA 和内部摘要、原单槽入口 SHA、原 runner SHA、原5槽终态 SHA，以及现有连续终态前缀。第六槽必须真实关闭；所有下一槽的 terminal、started 和试验目录都必须不存在。原 PENDING 只能按计划顺序进入，每次只执行：

```bash
bash /mnt/d/WSL/UAVHumble22-validation/run_humble54_pending_one02.sh 原下一槽ID
```

该原入口继续负责 native idle 和原 runner 的单槽锁、原源码/环境验证。外置工具不替代这些检查。每次命令必须真实退出 0；随后复核新增终态内容摘要和 plan/name/flight 绑定、成功调用/无基础设施停止/无残留、保存 runtime 配置 SHA、原 source capture SHA、全部四种独立评价的命令/退出/报告 SHA/原验证结果、source-clock/native PASS、录包闭合/完整性 PASS、全部读取证据和 long 的九项原 shutter/丢失/悬停/持续低速/禁自动恢复/重选前禁控制检查。每槽前后还核完整原 source map 及所有此前终态 SHA 未改变。

已知算法 False 可以保留并继续采集，例如组合条件下 long prediction=False。原 FAIL 仍为 FAIL，原导航性能门失败仍为失败；已观测的 person combined 同时存在 long prediction=False 和原导航距离 RMSE 2.2964 m 超过原 1 m 门槛，不能描述为仅一项失败。`known_algorithm_failures` 只记录已知 False 或原导航性能 FAIL；历史 null 单列 `unobserved_checks`，不计为已知失败。新短窗 detector=null（特别是尚未核验的 car）或其他任何新必需未知都立即停止后续槽，留给 root 真抽图、阅图与独立复核；不会把 person 的补证泛化到 car。仅原已 pin 的历史 person dropout 短 null 允许原样留在初始历史前缀。

已明确的旧导航 ULP 缺证只在原源码精确 pin 下处理：原 evaluator/runner 返回单一原 reason `Transient denominator differs from the whole interval`，原报告记录完整且无 malformed，旧 floor 网格与原完整网格仅差 1，浮点商距整点不超过 1 ULP。程序只在内存校验这一关联的分母/真值计数，再交原 validator 检查是否存在第二个结构错误。原报告和终态不会改写，输出仍记录原 `INCOMPLETE_EVIDENCE`；这只允许继续采集，不能冒充评价修复或工程 PASS。其他导航结构错误立即停止。

## 输出与监督

全新的 output 内包含 `state.json`、`events.jsonl`、各实际子命令日志和最终 `terminal.json`。事件记录真实子 PID、开始/结束 UTC、真实退出码及原终态。运行时 state 每秒写入心跳；原始状态保留在 `initial_closed` 和 `collected`。

`COLLECTION_STARTED` 后会对原已闭合前缀逐槽记录一对 `START_SLOT` / `COMPLETE_SLOT`，明确标记 `event_semantics=DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX`、`executed_by_this_owner=false`。这些事件的 `utc` 是本次实际观察时间；原开始/结束 UTC 分别另存，原 marker/terminal 的实际绝对路径和 SHA 一并绑定。它们只为新进度页提供完整 16 槽分母和原 FAIL/缺证计数，不声称本 owner 启动了旧槽。新增实际子进程事件则标为 `executed_by_this_owner=true`。不复制旧 owner 的 STOPPED_FAULT 事件，也不修改旧 owner 或等待器。

- `COLLECTION_FINISHED` 只表示所有剩余原槽都已调用、退出并完成采集后核验；原 FAIL/INCOMPLETE 没有变为 PASS。
- `STOPPED_FAULT` 保留具体错误、最后子命令退出和当前槽，不启动下一槽，也不重试。若监督中断时子进程仍活动，会明确标注，不能仅凭旧文件声称已停止或结束。
- 退出 0 只表示串行采集结束，无工程全通过或正式就绪含义。root 可以同时编写独立离线工具；不要同时改冻结源码或覆盖任何原报告。

仅验证工具的短测试（不使用 WSL、ROS、真实包或模型）：

```powershell
python -B -m unittest discover -s D:/WSL/UAVHumble22-validation -p test_collect_humble54_pending03.py -q
```

测试的 plan、源文件、终态和子命令都是临时 synthetic fixtures。假子进程验证顺序继续、已知算法失败保留、未知/安全/来源/报告篡改即停、真实非零退出即停以及 terminal/started/目录禁止重试；不构成实际采集或环境验证证据。
