# 两计划只读事件桥（准备工具，尚未正式启动）

此桥沿用现有 core 桥的标准事件格式。它只读取两份原计划、原 `slots/<id>.started.json` 和原闭合槽 JSON，不调用 guard/runner/WSL/仿真，不修改原源、旧桥或当前 monitor，也不建立页面、服务或准入。

未来须先有真实 core120 和 extension160 计划、实际文件 SHA，以及 serial batch 本地 OS PID 与创建 token。桥和 PID 必须在同一 OS 运行；不会借 WSL 命令发现另一系统的 PID。下面全部是占位符，本轮不要运行：

```bash
python -B /mnt/d/WSL/UAVHumble22-validation/bridge_formal280_events01.py \
  --project-root ACTUAL_PROJECT_WITH_EXISTING_MONITOR \
  --core-plan ACTUAL_CORE_DIRECTORY/plan.json --core-plan-sha256 ACTUAL_CORE_FILE_SHA \
  --extension-plan ACTUAL_EXTENSION_DIRECTORY/plan.json --extension-plan-sha256 ACTUAL_EXTENSION_FILE_SHA \
  --pid ACTUAL_SERIAL_BATCH_PID --expected-start-token ACTUAL_KERNEL_CREATION_TOKEN \
  --batch-summary ACTUAL_NEW_SERIAL_BATCH_DIRECTORY/summary.json \
  --output /mnt/d/WSL/UAVHumble22-validation/NEW_FORMAL_EVENT_BRIDGE_DIRECTORY \
  --expected-total 280 --interval 5
```

输出必须为本外部工具目录下全新的直接子目录。原槽扫描位置是**实际传入计划文件的同目录 `slots/`**，不把计划中旧 Linux 绝对路径当成 Windows 路径，也不搜索其他版本。两计划的原始文件 SHA、内部摘要、模式、120+160 分母、全局唯一安全 slot ID、extension 对 core/protocol 的摘要绑定均会检查；这些检查仅服务观察，不代替正式 guard 准入。

新 `events.jsonl` 首行 `BRIDGE_BOUND_PLANS` 提供完整280分母；随后每个原启动/闭合最多发一次 `START_SLOT` / `COMPLETE_SLOT`，包含 `slot/number/matrix/matrix_number/total/utc`、原状态、原源 SHA 和计划 SHA。原 FAIL、缺证、基础设施终态均保留；UNKNOWN/RUNNING、未写完 JSON、缺原启动 marker 或缺槽不制造 COMPLETE。基础设施/中断另发原 monitor 已识别的停机事件。只读桥故障也明确停止观察，不能写成工程失败或成功。

现有 `scripts/monitor_project_progress.py` 可直接消费新 events。**未来观察时应使用没有遗留单计划来源的新 monitor 输出，且不要同时传单份 core/extension 的 `--plan`**；旧 monitor 会优先使用单计划的 trial 数覆盖事件中的280。不要为本准备任务重启或改动正在运行的 core monitor。此桥不生成替代正式计划。

PID 创建身份失配/退出，或所指定原 serial summary 出现后，会再扫描一次并写 `bridge_terminal.json`。batch summary 只触发终止观察；`GUARD_PENDING_EXHAUSTED`、进程消失或 wrapper 返回0都不能补造槽闭合，更不能补造 PASS。原普通 FAIL 的执行闭合不等于验收通过；未知和未尝试继续留在分母。桥的终态记录观察范围和未知结果，不声称项目完成。

5秒一次低频扫描只读小 JSON（单文件8MiB上限），从不验证大工件、bag、JSONL、日志、视频或原 guard 容量。已发事件记录的是当时源 SHA；全套源/工件持续约束由原 guard 保持。

纯 fixture 检查从项目源根运行，测试只在本外部目录的临时子目录写小模拟 JSON，导入现有 monitor 的纯读取/计数函数，不启动 monitor/页面/进程：

```powershell
python -B -W error::ResourceWarning -m unittest discover -s D:/WSL/UAVHumble22-validation -p test_bridge_formal280_events01.py -v
```

`UAV_BRIDGE_PROJECT_ROOT` 可为测试明确指定现有项目源根；未设时使用测试命令当前目录。这只是 fixture 兼容性验证，不是两真实计划、Linux运行、准入或正式飞行证据。
