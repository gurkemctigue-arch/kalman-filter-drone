# 本地进度监控

`scripts/monitor_project_progress.py` 使用 Python 标准库，在主机上读取小型 events、ledger、plan 和进程创建时间，不启动 WSL/ROS/仿真、不读取 rosbag。输出只能写到本项目独立监控目录；拒绝写入 frozen 目录或其他已有资料目录。

状态含义如下。所有状态均与工程验收、项目是否全部完成分别报告。

| 状态 | 可核实的含义 |
| --- | --- |
| RUNNING | 目标 PID 及内核创建时间匹配，独立监控进程身份和心跳有效 |
| EVALUATING | 与 RUNNING 相同，且任务显式登记为独立评价阶段 |
| STOPPED_FAULT | 已知非零退出或当前批次明确记录故障停止；进程可能还在清理 |
| COMPLETED | 当前受监命令退出0，或相应记录完整结束；不代表工程PASS |
| STALE | 原活动任务的独立心跳过期或监控进程已消失；不能声称仍在运行 |
| UNVERIFIED | 没有进程创建身份/心跳、外部进程退出但退出码未知、记录不足或时钟异常 |

只存在日志或 START_SLOT，不能显示 RUNNING。PID被系统复用也不能冒充原任务。普通算法FAIL、EVALUATION_PENDING和基础设施异常在统计中分别保留，未尝试槽不计完成。

## 查看已有批次

下面读取已经停止的 Humble21，结果应为 STOPPED_FAULT、7/12已尝试、5未执行。ledger是外部只读输入，所有输出位于项目自己的新目录。

```powershell
python scripts/monitor_project_progress.py snapshot --output results/project_progress/humble21 --events results/frozen_fullplan_v4_humble21/reliability_v4_humble21_probe_seed004_matrix/serial_driver/events.jsonl --ledger D:/WSL/UAVHumble22-validation/humble21_execution_ledger/core.json --plan results/frozen_fullplan_v4_humble21/reliability_v4_humble21_probe_seed004_matrix/plan.json
```

之后可以用短命令刷新相同只读来源：

```powershell
python scripts/monitor_project_progress.py snapshot --output results/project_progress/humble21
Get-Content results/project_progress/humble21/progress.json -Encoding utf8
Start-Process results/project_progress/humble21/index.html
```

本地HTML每5秒重载最新快照，另每秒显示快照年龄，并在活动心跳过期时改为STALE。终态历史记录仍显示其结束时间；陈旧终态不变成“仍在运行”。浏览器不需要HTTP服务，也不读取私有网页或GitHub登录信息。

## 监控下一条真实命令

使用包装方式能获得子进程的真实退出码；运行哪个命令由调用方明确指定，监控器本身没有自动试验、重试或恢复能力。以下只是短小的本地演示：

```powershell
python scripts/monitor_project_progress.py run --output results/project_progress/local_demo --phase evaluation --task-id local-demo-001 --label "本地监控演示" -- python -c "import time; time.sleep(2)"
```

任务阶段可选 `simulation`、`evaluation`、`archive`、`statistics`、`documents`、`batch`。把每个真实步骤分别包装，才能明确显示仿真、评价、归档和材料阶段；完整批次仅包装一次时，其阶段就是batch，不能从日志内容猜测内部正在做哪一步。可同时传入 `--events`、`--ledger`、`--plan`，显示当前槽、分母和最新原始终态。跨阶段依次使用同一输出目录会积累唯一任务清单；`--task-id`不得重复。同一输出目录禁止两个活动监控器并发占用。

对已启动的本机进程可使用：

```powershell
python scripts/monitor_project_progress.py watch --output results/project_progress/attached_task --phase simulation --pid 12345
```

必须把12345替换为实际本机PID。Windows监控器不会启动WSL查询Linux进程；监控已有 `wsl.exe` 包装进程只能证明该Windows包装进程仍在，不能证明其中仿真仍正常。要获得每步真实结果，应由启动器显式逐步包装并绑定相应ledger。外部附着进程退出后无法取得其退出码，显示UNVERIFIED，不能猜测成功。

`--interval`默认1秒，`--stale-after`默认10秒，仅是**进度页心跳**时效；它们不改变PX4状态、目标预测或任何飞行保护门限。监控进程异常退出后，单独执行snapshot会重新检查内核进程身份和心跳；HTML自身也会过期。输出中保存监控与目标各自PID、创建时间、最后心跳、任务起止时间、最后事件时间和已记录退出码。源记录缺失或解析错误会显示在errors中，不凭空补齐。

`Ctrl+C`停止watch时不会结束所附着的外部应用。停止run会终止它直接启动的子进程，**不承诺终止该进程的全部后代或WSL内部任务**；复杂实验仍须使用项目自身的清理流程。主机重启或监控器被强行终止后，旧活动记录显示STALE/UNVERIFIED，需要明确的新命令接续，不自动重跑旧槽。

## 结束摘要与通知

每次快照生成 `progress.json` 和 `index.html`。终态另存 `end_summary.json`；运行下一条任务时，上一条结束摘要保留且有明确task ID/时间。任务及独立心跳保存在 `monitor_state.json`，命令输出单独存入 `command_*.log`。这些是本地运行资料，位于被Git忽略的results中。

加上 `--notify` 会在结束或故障后尝试Windows本机通知，并将结果写入 `notification.json`。`submitted=true`只表示Windows通知API调用成功，不能证明用户看到；关闭通知、系统策略或服务失败会记录具体错误。相同终态去重，默认不开通知。无论通知成功与否，HTML与结束摘要均可查看。监控器不会向他人发送消息，也不能自动唤醒聊天或保证模型会话继续工作。

验证命令仅启动短小Python子进程，包括真实成功、非零退出及监控器停止后心跳过期；不运行仿真：

```powershell
python -m unittest tests.test_project_progress_monitor -v
```
