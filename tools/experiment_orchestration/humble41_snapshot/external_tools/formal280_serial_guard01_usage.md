# 正式 120 + 160 槽的外部串行调用说明

此工具只串行调用原 `reliability_v4_guard.py run-one`，不选槽、不修改原槽、不替代原准入或容量校验。当前只做 Windows 小型 fake-guard 测试；本文没有表示正式准入、280 槽或真实飞行已经完成。

## 使用前与命令

须先完成真实的开发证据、存储预算、最终根构建、协议登记、正式计划和封存准入。使用实际最终 admission manifest、它绑定的原 guard 和正确的 Ubuntu 22.04 / ROS 2 Humble 环境；路径不得用本文占位符直接运行。保持原独占运行约束，不与已有飞行或其他重任务并行。

```bash
python -B /mnt/d/WSL/UAVHumble22-validation/formal280_serial_guard01.py \
  --manifest ACTUAL_FINAL_ADMISSION.json \
  --output NEW_EXTERNAL_BATCH_DIRECTORY \
  --guard-command \
  /bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_BOUND_GUARD.py
```

`--guard-command` 必须是最后一个选项。它接受 argv，不经 shell 拼接；工具仅追加 `run-one --manifest ACTUAL_ABSOLUTE_MANIFEST_PATH`。原环境脚本负责进入 Humble 环境，原 guard 验证实际源、计划、容量和工具绑定并持原锁。本工具不导入 guard、不持第二把原锁。输出须为父目录已存在的全新目录，位于原 guard state 和最终冻结根之外；不得覆盖或接续旧 batch 目录。

## 顺序和停止条件

所有选择沿用原 guard：先 core120 的首个 PENDING，再 extension160 的首个 PENDING，均依各 plan 的 `trials` 顺序。正式计划按类别、6 个核心组或 8 个扩展条件、seed1000 至 seed1009 展开；本工具不重排。

只有原 guard 退出 0、唯一新增原调用目录的 `admission.json` / `outcome.json` 绑定和结构均有效、该槽真实闭合且剩余数恰减 1，才进入下一次调用。普通 `PASS`、`FAIL`、`INCOMPLETE_EVIDENCE`、`EVALUATION_PENDING` 都保留并继续。STOP、REFUSED、RUNNING、基础设施错误、中断、未知状态、非零退出、子进程异常、坏 JSON、重复槽、多个新增原调用目录或分母跳变立即停止，不自动重试。

原 guard 始终检查全 280 分母。最多调用 280 次；最后一次闭合报告 0 PENDING 即结束，不加第 281 次调用。若入口已没有 PENDING，须验证原 guard 的准确 `NO_PENDING_SLOTS` 哨兵；没有原调用目录且 stdout 只有环境前文或截断 JSON 会保守停止。普通闭合优先读取原结构化回执，允许 stdout 含正常环境前文。0 PENDING 不表示全部 PASS，也不表示项目验收通过。

## 查看进度和保留证据

```bash
tail -n 10 -f NEW_EXTERNAL_BATCH_DIRECTORY/events.jsonl
```

`events.jsonl` 按调用开始、原槽闭合或停止逐行追加并 flush；每次 `0001/` 等目录保留 `stdout.log`、`stderr.log`、`process.json` 和成功核对时的 `observed_result.json`。批次结束查看 `summary.json`，区分本 batch 闭合数与此前已消费槽数；停止后的 `guard_reported_pending_slots` 可能只是上一次已核实的旧数，只有 `pending_count_current_after_verified_completion=true` 才表示已核实耗尽。

真正飞行证据仍位于原 guard state 的 UTC_UUID 目录：`admission.json`、`outcome.json`、`runner.log`，以及原槽工件。可查看当前 `runner.log` 的末尾；本工具不 hash 此日志，也不读取 rosbag/遥测大文件。不要高频运行原 runner `status`：它默认 `read_slots(verify_artifacts=True)`，会重 hash 历史工件。原 guard `check` 同样不是进度轮询入口，且在 RUNNING 时会拒绝。

停止后保留所有原目录、标记、槽状态、manifest 和旧 batch。不得删除 RUNNING marker、修改失败终态、自动换 seed 或重跑原槽。中断并不证明原子进程已退出；先由主代理核对真实进程和原运行状态、完成原要求的故障诊断。只有原 guard 再次允许剩余 PENDING 时，才可用另一个全新 batch 目录继续；本工具不制造 resolution 或绕过原阻断。

## 纯测试范围

```powershell
python -B -W error::ResourceWarning -m unittest -v test_formal280_serial_guard01
```

在本外部工具目录执行。测试只使用临时小文件和 fake 子进程，不调用实际 guard、WSL、准入、登记、仿真或正式工件。纯测试通过只说明串行调度的这些路径被检验，不能替代 Linux 环境或正式飞行验收。
