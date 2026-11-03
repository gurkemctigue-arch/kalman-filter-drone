# after07 实际负预算之后的容量刷新设计卡

状态：**仅设计，未实施、未登记、未执行。** 本卡来自 Windows 小源码只读检查，不表示实际 measurement 已结束或负预算已产生。没有运行 WSL/native、inventory、budget、flight、staging 或正式验收；没有创建 owner、trigger、未来结果路径绑定或未来 SHA。当前 collector07 的实际独占执行保持不变。

本设计仅适用于：原 after07 measurement 确实完成全部 12 个步骤，所有步骤真实 exit 0，actual28、两次具名 velocity export 和 R0 均完整，但最终因完整 full280 容量预算不足而保留负结果、整体 exit 2。它不是通用 resume，也不能放行其他停止原因。

## 原负结果必须保留

原 `tools/reliability_v4_storage_budget.py:316` 的 CLI 对“证据完整、容量为负”的结果仍正常写出 budget 并 exit 0。原 `tools/experiment_orchestration/humble54_closed_measurement01/run_closed_measurement.py:344` 随后调用 `old.positive_budget()` 才因容量不足抛出异常。因此可能出现全部 12 个实际步骤 exit 0，而原 measurement terminal 保持：

```text
status = STOPPED_DIRECT_MEASUREMENT_PARTIAL_OUTPUTS_RETAINED
returncode = 2
errors[0].error = ValueError: Unknown or negative physical/logical full280 budget; stop without staging
```

以上是预期语义说明，不是预写实际结果。只有原件实际产生且完成复核，才可采用后续分支。原 terminal、原负 budget、原 stdout/stderr、原 owner/child identity、真实 UTC、原始 FAIL/null 和所有 SHA 必须原样保留；不得重写旧 terminal 为 COMPLETED/0，不得用新预算替换旧负预算，不得把全部 measurement 叙述为验收成功。

原 `run_closed_measurement.py` 保持不变，不重跑原 flight、actual28 测量、person/car export 或 R0 校准。任何复用都必须重新核对原产物及其绑定未变。

## 仅重做两步真实容量观察与预算

真正改善容量后，等待 collector07 和原 measurement 实际退出，取得原 `tools/staging/final55_offline_overlay_20261103/stage.py` 的 `linux_idle_guard()`，持有现有 `/tmp/uav_tracking_reliability_v4_sitl.lock`，并通过原实际 native blocker 检查。

复用原 `tools/experiment_orchestration/humble54_closed_followon_runner08/run_followon08.py` 中：

- `workflow_commands(p):220` 的 `physical_inventory`、`full280_budget` 两个 argv；
- `ros_command():215` 的原环境调用封装；
- `child_step():172` 的实际子进程等待和日志保存；
- `positive_budget():242` 的原 full280 正预算校验。

不能执行旧08 `run()`、原整批 `run_closed_measurement.run()` 或新增 owner/trigger 链。这里只复用原函数及两个独立原 CLI。保留原 `p["frozen"]`、`p["tools"]`、`p["audit_guard"]`、`p["core"]`、`p["extension"]`、`p["sizes"]`、`p["assumptions"]`。仅在实际执行时选择新的独立 receipt、inventory 和 budget 输出位置；本卡不登记这些未来位置。

原 CLI 的精确参数为：

```text
原 p["audit_guard"]：
storage-probe --distribution UAVHumble22 --mount /mnt/d --output ACTUAL_NEW_INVENTORY

原 p["tools"] / "tools/reliability_v4_storage_budget.py"：
--core-development-plan ORIGINAL_CORE
--extension-development-plan ORIGINAL_EXTENSION
--size-evidence-dir ORIGINAL_ACTUAL28
--physical-inventory ACTUAL_NEW_INVENTORY
--assumptions ORIGINAL_ASSUMPTIONS
--output ACTUAL_NEW_BUDGET
```

上述大写名称都是待实际产物产生后核对的参数角色，不是路径、hash 或结果绑定。精确命令列表应由原工厂生成，不在新实现中重新发明 shell 转义：

```python
# 设计示意：仅真实执行时使用已核对的实际输出参数。
refresh_paths = dict(original_paths)
refresh_paths.update(receipt=actual_new_receipt,
                     inventory=actual_new_inventory,
                     budget=actual_new_budget)
refresh_steps = [(name, argv) for name, argv in old.workflow_commands(refresh_paths)
                 if name in {"physical_inventory", "full280_budget"}]
```

应得到先 inventory、后 budget 的两个原 argv。`old.child_step()` 串行持有每个实际子进程，保留真正的 argv、UTC、PID/boot ID/start ticks、整数退出码、stdout/stderr，以及调用失败事实。中断后仍等待同一实际 handle；不自动重试、不分离执行、不伪造退出。两步之外原 idle guard 的元数据检查仍必须进行。

原 budget `assemble()` 会重新查询 Windows 实际物理卷空间、注册的 VHD 路径和 ext4 逻辑空间；它逐格核对已有28份 size receipts、原小证据及当前文件尺寸，不重读 bag/VHD 内容。已有五个固定原工具直接复用，不重新 `git show` 复制。不能调用原 `fresh_outputs()`：它为整个六步新批次设计，会拒绝已存在的 actual28、exports 和 calibration。

新输出必须独立且不存在，不覆盖原 measurement、原 inventory、原负 budget、28 size receipts、原 trials 或任何源/build 树。若新 budget 放在实际 results 下，其原 CLI 要求使用尚不存在的新父目录；若放在外部 receipt 下，则遵守原 `require_independent_output()` 的完整约束。两步或新正预算校验失败时，保留本次实际输出并停止。

## after07 staging 的四处精确连接边界

当前 `tools/staging/final55_after07_stage01/stage_after07.py` 只接收 `measurement_source`、`measurement_terminal`、`budget` 三项，并要求同一旧测量窗口内的成功预算。不能仅把新 budget 塞入原三项输入。

| 原位置 | 现有约束 | 容量刷新路线所需的最小适配 |
|---|---|---|
| `validate_terminal():117` | 原 terminal 必须 COMPLETED/0，errors 与 interruptions 均为空 | 原成功路线保持；仅新增“全部12步成功，唯一错误为原正预算容量门拒绝”的严格分支 |
| `run_registered():181` | budget 必须解析到旧 `p["budget"]` 固定原位置 | 分别核对原负 budget 与真实新正 budget，保持二者独立绑定 |
| `validate_terminal():135` | 原 terminal 的 input bindings 必须包含正在采用的 budget | 原 terminal 保留其原负 budget；真实刷新 receipt 单独绑定新 inventory 和新 budget |
| `run_registered():216` | budget 创建时间必须处于旧 measurement 的开始/结束之间 | 原路线保持；刷新预算必须处于新的实际两步执行窗口内，且晚于旧 measurement 结束 |

未来最小实现可以在原三项输入之外，增加一项明确的 `capacity_refresh` 绑定，引用真实两步执行的独立 receipt。该 receipt 应绑定原 measurement source/terminal、原负 budget、原复用产物、新 inventory、新 budget 及实际两步证据。不得制造一个替代旧 measurement terminal 的“成功副本”。

当前没有发现现成、完整的容量 refresh 终态适配 CLI。应在实际负预算产生、确认仅容量阻断后，再实现并独立复核以上窄分支；不创建新的多层 runner，不修改原测量、原 budget 算法或原容量规则。

## 刷新分支必须同时满足的验证条件

1. **原停止原因仅为容量。** 原 measurement 是实际注册的 after07 source，原 collector/profile/closure 输入均一致；恰有12个原命令、原顺序和12个整数 exit 0，日志及进程 identity 完整。原 terminal 保持 STOPPED/2、`interruptions=[]`，且仅有上述 `positive_budget()` 的容量拒绝。任何其他错误、缺步、非零步骤、缺失产物或源变化都拒绝此分支。

2. **原负 budget 本身完整。** 原 schema、28个唯一固定 cells、完整280 slots、storage digest、core/extension plans、原工具/guard SHA、原 assumptions provenance 均通过核对。对原 budget 调用原 `positive_budget()` 必须仅在原“Unknown or negative physical/logical”边界拒绝；不是之前的 schema、digest、plan、assumptions 或证据门失败。capacity preview 中应有明确容量不足事实，不能把缺失/未知输入当作可刷新负预算。

3. **原完整收集重新闭合。** 重新运行原小证据 full16 `closure_audit()`，核对原16槽、11个保留观察与5个实际调用、launcher/monitor/native 终态、原 source map 和日志绑定。与 saved audit 比较时，仍仅允许真实新 `created_utc` 不同；不能豁免其他字段。

4. **已测产物原样复用。** 原 actual28 summary、28 receipts、其原小输入及文件尺寸未变；两次具名 seed004 stage1_velocity exports、原 arrays/sidecars、R0 与它们的 provenance/SHA 未变。复核 R0 中已记录的数组和 export 验证绑定，不重新选槽、重算参数、替换失败或优化阈值。任何必须重做的缺失离线产物需要另行真实新执行证据，不能套用本卡的“两步刷新”分支。

5. **新旧预算 storage 完全相同。** 本路线只改善容量，因此新旧 `storage` 对象及 `storage_sha256` 必须完全相同。保持原1.15增长系数、全部280槽、per-slot extras、原 five delivery reservations、additional remaining budget、three-raw/two-compressed 公式和所有原 size/archive evidence。仅真实创建 UTC、新 inventory provenance/相应 small-input binding、实际 capacity snapshot 可以变化。不得为了变正降低预留、缩短试验、减少重复次数、删去失败或假定压缩收益。

6. **实际存储身份一致且重新测量。** 新 inventory、新 budget 保持相同实际 Windows volume ID、mount、results 位置、VHD 注册路径和 distribution。原 budget 会再次查询实时 free bytes；inventory 与 budget 间有真实写入，因此两者的 free bytes 不必逐字相等，不能把旧 inventory 的数量抄成新的预算容量。不能用 ext4 虚拟空闲代替宿主物理空闲。

7. **双窗口时间线和真实执行齐全。** 原 measurement end ≤ refresh start ≤ inventory 实际执行窗口 ≤ budget 实际执行窗口 ≤ refresh end ≤ 当前时间；各 JSON 的 `created_utc` 必须在相应实际生产步骤内。新 receipt 不得把两次执行描述成原12步的一部分，也不追加、重写原12步记录。

8. **新正预算与后续门保留。** 新 budget 必须通过原 `positive_budget()`：完整280槽、所有物理卷与 ext4 logical `fits_declared_* is True`。staging 前重新核对所有输入未变；正式批次前及每个正式槽仍由原 guard 检查当前容量。新预算完成不是正式 admission，也不是算法/飞行验收 PASS。

9. **全量拒绝条件继续成立。** 新文件冲突、原或新来源变动、任何原产物缺证、两步非零退出/中断、真实当前空间不足、storage 改变或时间线不成立，均停止并保留事实；不自动重试、不进入 staging、不发布正式验收通过结论。

## 容量修复的实际边界

原 `planning/reliability-v4-humble54-storage-assumptions01.json` 的固定后续开销为22 GiB：additional remaining 4 GiB，加五类 delivery 总计18 GiB。原 full280 临时保留为 `max(8 GiB, 按原样本派生的 three-raw/two-compressed 峰值加2 GiB)`。它与独立压缩 benchmark 的22 GiB宿主保留不是同一字段；二者不能混淆或据此降低任一门。

只可在真正回收或增加的 Windows 物理空间上建立新预算。WSL 内删除文件可能只增加 ext4 逻辑空闲，未必立即减少 VHD 在宿主卷的占用；本卡不授权删除、压缩、迁移或离线维护。未经实际验证的压缩/去重/清理收益不能登记。最终所需释放量以真实完整28格 budget 的 deficit 加后续真实空间变化为准，不能提前以不完整17格估计替代正式计算。

本卡完成后仍为**设计待实施**。下一步是等待并如实核对原 measurement 实际终态；若确属本卡的单一容量阻断，再进行最小实现、合成测试、独立复核和真实两步执行，不预登记任何未来输入 SHA。
