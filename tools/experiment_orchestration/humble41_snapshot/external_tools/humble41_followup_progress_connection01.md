# Humble41 后续实时进度接线 01

2026-10-31。只读核对现有 monitor、两个 bridge、usage 和 producer 源码后整理；没有启动任何监控、桥、WSL、测试、guard 或实验，没有改动原结果。下列所有未来 PID、token、SHA 和新路径均须由 root 的真实运行产生，不能原样执行占位模板。

## 1. 各自页面与可观察范围

| 后续任务 | 页面入口 | 现有槽事件支持 |
|---|---|---|
| 四场安全验证 | 全新 `results/project_progress/<NEW_SAFETY_PAGE>/index.html` | 只有命令级心跳和真实子进程退出；现有 core/formal 桥均不支持 safety registry |
| 十六场开发扩展 | 全新 `results/project_progress/<NEW_EXTENSION_PAGE>/index.html` | 既有两个桥不支持 EXTENSION_PROBE16；基础 monitor 保持命令心跳，新专用最小适配须独审后才能提供16槽事件 |
| 正式120+160 | 全新 `results/project_progress/<NEW_FORMAL_PAGE>/index.html` | 既有 formal 两计划桥提供完整280分母及原 START/COMPLETE 事件 |

每阶段使用全新 monitor 目录、唯一 task-id 和实际任务 label，不复用 core 页、旧 events、旧 ledger 或旧 task。root 应在新页实际生成后向用户提供其真实入口；统一交付入口若需切换，也应只链接真实存在的新页。旧 core 页保留其原任务终态。

monitor 输出必须位于运行该脚本的项目 ROOT 内，路径任何组件不得以 `frozen_` 开头。推荐主树 `D:/基于yolo和卡尔曼滤波/results/project_progress/...`；不得放入冻结结果目录。bridge 输出则必须是 `D:/WSL/UAVHumble22-validation` 的全新直接子目录，二者不是同一目录。

## 2. monitor 的实际 parser 与身份

`scripts/monitor_project_progress.py` 只有 `run`、`watch`、`snapshot` 子命令，没有 `--kind`、`--owner-pid` 或 `--owner-start-token`。

- 三者都要求 `--output`，都可选 `--events`、`--ledger`、`--plan`、`--notify`。
- `run/watch` 要求 `--phase`，支持 `simulation/evaluation/archive/statistics/documents/batch`；可选 `--task-id`、`--label`、`--interval`（默认1秒）、`--stale-after`（默认10秒）。要求有限且 `0 < interval < stale-after`。
- `run` 的非空命令 argv 放在全部 monitor 选项之后，用 `--` 分隔；代码只去掉此第一处分隔符。Windows → WSL 内层 `wsl.exe ... -- ...` 的第二个 `--` 保留。
- `watch` 只接本机 OS 的 `--pid`，自行记录该 PID 当时的创建身份，不读取另一 OS 的 PID。
- `snapshot --output DIR` 是一次读源并更新已有页面，不启动进程或持续心跳；不能当作后台监控。

`run` 是实际子进程的唯一启动入口；若任务已由其他原入口启动，应 `watch --pid <实际本机producer PID>`，不得再 `run` 一次。Windows monitor 启动 `wsl.exe` 时，记录的是 Windows wsl producer 的 PID 和 `windows_filetime:<实际创建 FILETIME 十进制值>`；不是 Windows monitor 自身 PID，也不是工具 session ID 或 WSL 内部 PID。Linux 版本 token 为 `linux:<实际boot_id>:<实际start_ticks>`。桥和其被核验 PID 必须同 OS。

实际 Windows owner 信息来自新页的 `monitor_state.json`：`task.process.pid` 与 `task.process.start_token`；`monitor_process` 是独立 monitor 的身份，不能替代 producer。只有 `alive=true` 且创建 token 匹配才可绑定 bridge；PID 重用或未知身份拒绝。

页面/JSON 由独立 monitor 持续写入，需同时核心跳、monitor 和 producer 身份。RUNNING 只证明该本机 producer 仍存在，不代替 ROS/owner 健康验证。`run` 捕获 child 的真实返回码：0显示 COMPLETED，非0显示 STOPPED_FAULT；均不是工程验收。`watch` 的外部 PID 消失后取不到退出码，结束可为 UNVERIFIED，不能把 watch 自身返回0当作 producer 成功。不要终止 monitor 来代替原 runner/owner 的正常停止与有界清理。

## 3. 安全4：独立命令级页面

必须先由 root 完成真实 core12 全 PASS 和 safety registry 独审。以下 Windows PowerShell 模板把**原安全执行命令**放在 monitor 后面；只有选择 monitor 为唯一启动入口时才使用：

```powershell
python -B 'D:/基于yolo和卡尔曼滤波/scripts/monitor_project_progress.py' run `
  --output 'D:/基于yolo和卡尔曼滤波/results/project_progress/<NEW_SAFETY_PAGE>' `
  --phase batch --task-id '<NEW_UNIQUE_SAFETY_TASK>' --label '四场歧义安全验证（命令状态）' `
  --interval 1 --stale-after 10 -- `
  wsl.exe -d UAVHumble22 -u root -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/safety_runner41.sh run `
  --review '<ACTUAL_REVIEW_PATH_IN_WSL>' --review-sha256 '<ACTUAL_REVIEW_FILE_SHA>' `
  --reviewed-tools-sha256 '<ACTUAL_REVIEWED_SAFETY_CANONICAL>' `
  --frozen-root /root/uav_tracking_fullplan_v4_humble41 `
  --registry-sha256 '<ACTUAL_REVIEWED_REGISTRY_FILE_SHA>'
```

不传 `--events/--plan/--ledger`，因此不宣称安全槽计数。safety `run` 的 registry 路径由原工具固定为 `ROOT41/results/reliability_v4_humble41_safety_seed004_audit/registry.json`，CLI 接受的是 `--registry-sha256`，没有 `--registry PATH`。registry 是实际 scope `HUMBLE41_SAFETY4_ORIGINAL_DEVELOPMENT_ATTEMPTS_NOT_FORMAL_GATE` 的四 trial 审计定义，含 source/core 绑定；其 started JSON 使用嵌套 `trial/registry/source_binding`，不是 normal runner 的 `id/plan_sha256/flight_command` start marker。不能改字段、套 core12 plan 或把 registry 当 FORMAL plan。

最终四场是否 PASS，要核原 audit 的 `execution_terminal.json`、每场原行、`slots_facts.json`、`development_validation_summary.json` 和 `development_guard_validation.json`；页面 COMPLETED 不能替代这些原证据。

## 4. extension16：先保持命令级准确性

只有真实安全4和原 core 全通过、原 extension plan/独审 final contract 齐备后，才可用以下唯一启动模板：

```powershell
python -B 'D:/基于yolo和卡尔曼滤波/scripts/monitor_project_progress.py' run `
  --output 'D:/基于yolo和卡尔曼滤波/results/project_progress/<NEW_EXTENSION_PAGE>' `
  --phase batch --task-id '<NEW_UNIQUE_EXTENSION_TASK>' --label '十六场开发扩展验证（命令状态）' `
  --interval 1 --stale-after 10 -- `
  wsl.exe -d UAVHumble22 -u root -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/extension_runner41.sh run-extension `
  --review '<ACTUAL_REVIEW_PATH_IN_WSL>' --review-sha256 '<ACTUAL_REVIEW_FILE_SHA>' `
  --reviewed-tools-sha256 '<ACTUAL_REVIEWED_EXTENSION_CANONICAL>' `
  --frozen-root /root/uav_tracking_fullplan_v4_humble41 `
  --safety-tools-sha256 '<ACTUAL_REVIEWED_SAFETY_CANONICAL>' `
  --safety-python-sha256 '<ACTUAL_SAFETY_PY_FILE_SHA>' `
  --contract '<ACTUAL_EXTENSION_FINAL_CONTRACT_PATH_IN_WSL>' `
  --contract-sha256 '<ACTUAL_EXTENSION_FINAL_CONTRACT_FILE_SHA>'
```

当前既有 `bridge_humble41_events01.py` 的 `--kind` **只支持 core**，严格固定 root41、PROBE、prefix `reliability_v4_humble41_probe01` 及两类六组12格。没有 `--kind extension/safety`。formal 桥也不能靠 `--expected-total 16/28` 读取开发矩阵，因为仍强制 FORMAL/EXTENSION_FORMAL 两计划模式。

extension16 原 plan 则是 `EXTENSION_PROBE`、prefix `reliability_v4_humble41_extensions_probe`、两类八条件 seed004，位于原 `reliability_v4_humble41_extensions_probe_seed004_matrix/plan.json`。顺序为 person 后 car，各类依次 depth_noise、depth_holes、dropout、latency、combined、speed_changes_velocity、speed_changes_position、far_distance。它不能伪装成 core plan。

monitor `--plan` 只读取 trials 得到分母，**不会扫描原 slots**；没有合法 START/COMPLETE 事件就没有完成槽计数。故以上基础模板不传 plan，避免把未观测的0终态显示成已核验进度。

### 4.1 新专用 extension16 候选的准确接线

新外置 `bridge_humble41_extension_events01.py` 只增加严格 EXTENSION_PROBE16 的初始化和 CLI，直接复用 core `run_bridge` 与 formal `PlanEvents.scan`。旧 core 桥、reader、monitor 和飞行工具均保持不变。Windows 私有小 JSON fixture 已实际9项通过、0 skip、0.171秒，原日志为 `bridge_humble41_extension_events01_windows_tests01.log`；**尚须独审，下列不是已启动的新桥，也不表明真实 extension plan 已存在。**

取得实际工具独审后，在第4节新 monitor 的 `--` 之前增加 `--events 'D:/WSL/UAVHumble22-validation/<NEW_EXTENSION_EVENTS>/events.jsonl'`，label 可改为“十六场开发扩展验证”。producer 启动后，从该新 monitor 的真实 state 取得 Windows producer PID/token，再独立调用：

```powershell
python -B 'D:/WSL/UAVHumble22-validation/bridge_humble41_extension_events01.py' watch `
  --project-root 'D:/基于yolo和卡尔曼滤波' `
  --plan '<ACTUAL_EXTENSION16_PLAN_PATH_VISIBLE_ON_WINDOWS>' --plan-sha256 '<ACTUAL_EXTENSION16_FILE_SHA>' `
  --pid <ACTUAL_WINDOWS_WSL_PRODUCER_PID> --expected-start-token '<ACTUAL_WINDOWS_CREATION_TOKEN>' `
  --output 'D:/WSL/UAVHumble22-validation/<NEW_EXTENSION_EVENTS>' --interval 5
```

该专用入口没有 `--kind`。它固定两类八条件、整数seed4与 `class_extension_condition_seed004` 的16个精确ID顺序，逐 trial 核 `target_class/extension_condition/seed`、plan文件SHA及内部digest；`condition` 字段不作为八维身份，因为后三条件的底层 condition 可为 clean。输出头给出16完整分母，原FAIL/UNKNOWN/缺started/半写JSON处理沿用原 reader；PID退出后仍末扫，绝不补造缺槽。不存在的未来 plan 会拒绝，不因工具fixture PASS而被创建或准入。

新桥事件对应同一新 monitor 页；等 producer/monitor/bridge 真实终结后，按第6节方式对该 extension 页和该 extension events 做一次最终 snapshot。安全4仍没有槽桥支持，保持命令级状态。

## 5. 正式280：新 monitor + 既有两计划桥

只有真实正式 seal、全280 PENDING、容量及全部前置实际通过后才启动。准确 adapter 串行命令见 `formal41_serial_adapter_connection01.md`；将其作为本 monitor 的唯一子命令。以下字段必须使用同一实际 sealed manifest 和全新 serial batch：

```powershell
python -B 'D:/基于yolo和卡尔曼滤波/scripts/monitor_project_progress.py' run `
  --output 'D:/基于yolo和卡尔曼滤波/results/project_progress/<NEW_FORMAL_PAGE>' `
  --events 'D:/WSL/UAVHumble22-validation/<NEW_FORMAL_EVENTS>/events.jsonl' `
  --phase batch --task-id '<NEW_UNIQUE_FORMAL_TASK>' --label '正式120+160验证' `
  --interval 1 --stale-after 10 -- `
  wsl.exe -d UAVHumble22 -u root -- /usr/bin/python3 -B /mnt/d/WSL/UAVHumble22-validation/formal280_serial_guard01.py `
  --manifest '<ACTUAL_SEALED_MANIFEST_PATH_IN_WSL>' `
  --output '/mnt/d/WSL/UAVHumble22-validation/<NEW_FORMAL_SERIAL_BATCH>' `
  --guard-command /bin/bash /mnt/d/WSL/UAVHumble22-validation/formal41_guard_adapter01.sh `
  --manifest-sha256 '<ACTUAL_SEALED_MANIFEST_FILE_SHA>' `
  --reviewed-tools-sha256 '<ACTUAL_REVIEWED_FORMAL_ADAPTER_CANONICAL>'
```

**不要同时传单份 core 或 extension `--plan`。** monitor 会优先用单计划 trials 覆盖 events 的280，导致只显示120或160。也不能把 serial 原生 `GUARD_CALL_STARTED/ORIGINAL_SLOT_CLOSED` 直接当 monitor events：monitor 只数 `START_SLOT/COMPLETE_SLOT`。

producer 确实已启动后，从新页的真实 `monitor_state.json` 取得 `task.process.pid/start_token`，再启动独立 Windows 只读 bridge。它没有 `watch` 子命令，也没有 `--kind`：

```powershell
python -B 'D:/WSL/UAVHumble22-validation/bridge_formal280_events01.py' `
  --project-root 'D:/基于yolo和卡尔曼滤波' `
  --core-plan '<ACTUAL_CORE120_PLAN_PATH_VISIBLE_ON_WINDOWS>' --core-plan-sha256 '<ACTUAL_CORE120_FILE_SHA>' `
  --extension-plan '<ACTUAL_EXTENSION160_PLAN_PATH_VISIBLE_ON_WINDOWS>' --extension-plan-sha256 '<ACTUAL_EXTENSION160_FILE_SHA>' `
  --pid <ACTUAL_WINDOWS_WSL_PRODUCER_PID> --expected-start-token '<ACTUAL_WINDOWS_CREATION_TOKEN>' `
  --batch-summary 'D:/WSL/UAVHumble22-validation/<NEW_FORMAL_SERIAL_BATCH>/summary.json' `
  --output 'D:/WSL/UAVHumble22-validation/<NEW_FORMAL_EVENTS>' --expected-total 280 --interval 5
```

传入的两计划必须是实际正式原文件，而不是另存快照；Windows 路径需映射到真实共同结果位置。桥从每份实际 plan 的同目录 `slots/` 读原 marker/terminal，不解析其中 Linux directory 字符串为 Windows 路径，不跨版本找同名成功槽。它核 schema、study_kind、两文件 SHA、内部 plan digest、FORMAL/EXTENSION_FORMAL 模式、120+160分母、唯一安全ID及 extension 对实际 core/protocol 的绑定。

桥只传播原 FAIL/缺证/中断等标签，不计算工程 verdict；UNKNOWN/RUNNING、缺原 started、未写完 JSON 或缺槽不会补造 COMPLETE。原 serial summary 或 producer 身份终结后还有最后一次扫描，随后保存 `bridge_terminal.json`。桥自身返回0不等于原实验成功，进程消失也不补造槽终态。

## 6. 收尾、旧页保留与最终一次 snapshot

monitor 可能在子进程退出后先于5秒桥的末扫结束，页面会暂时保留末槽未读的快照。**先确认原 producer、monitor 和 bridge 均已真实终结，再用已有 snapshot 更新同一 owned 页**：

```powershell
python -B 'D:/基于yolo和卡尔曼滤波/scripts/monitor_project_progress.py' snapshot `
  --output 'D:/基于yolo和卡尔曼滤波/results/project_progress/<SAME_NEW_FORMAL_PAGE>' `
  --events 'D:/WSL/UAVHumble22-validation/<SAME_NEW_FORMAL_EVENTS>/events.jsonl'
```

此动作不启动新心跳、producer 或桥，不创建缺槽证据。页面最终命令状态、桥记录槽计数和原工程 PASS/FAIL 应分别阅读。安全4与基础 extension16 无槽事件时，页面只能报告命令退出及心跳证据；原验收结论仍由各自原执行证据核定。

不要用 runner `status`、guard `check`、解码 bag 或全工件 rehash 当作高频进度查询。原任务停止时保留旧页、旧 state/events、原未尝试分母与原故障；下一阶段使用另一真实新页并发布新入口。

## 7. 本次源身份

| 本次只读源码 | SHA-256 |
|---|---|
| `scripts/monitor_project_progress.py` | `759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98` |
| `bridge_humble41_events01.py` | `94568d694a4379cd744343b13643d442abe67749bf3a7e34bf08cbef25d064aa` |
| `bridge_formal280_events01.py` | `0229bf564ec3609ee226b388e9024276516f76d05f8f9bdc110235c8ed18e270` |

上述均为文件字节 SHA，不是未来 plan/registry SHA、PID token 或执行结果。本文没有假造未来值或宣告后续任何阶段已启动。
