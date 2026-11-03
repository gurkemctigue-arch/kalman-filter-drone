# 第八场失去原 runner 后的最小有效路径

结论：原第八场即使完成 75 s FOLLOW、monitor 返回 0、录包随后完成，也不能补写为原 runner 正常完成。若继续使用原公共 CLI 和固定 tools02 取得完整 28 格计容，最小可行路径是：**保留原 12 格 core 和 safety03，另行前瞻登记并完整执行同一 frozen54 源码的 16 格 extension 开发矩阵。** 原 extension 的成功、失败、缺证、第八次中断及尚未尝试槽均保留，不挑选替换结果。

## 原源码确定的边界

本核对从 Git commit `eedd8d9abcd6890b0bd5d0155f76ac08253426b9` 读取原 `scripts/run_reliability_v4.py`，SHA256 为 `069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11`，与 frozen54 原计划一致。当前工作区 runner 已有后续改动，不能用其当前 SHA 代替原件。

- 原 runner 第 2389–2391 行：发现任何模拟/录包/飞行进程即拒绝新 run；必须先等真实原飞行及清理结束。
- 第 2395–2403 行：START 存在但终态缺失时，写入 `INTERRUPTED`、`execution_status=INTERRUPTED`、`infrastructure_stop=True`，然后立即返回；该槽不会重新变成 PENDING。
- 第 2404–2408 行：后续继续原 PENDING 还需绑定中断终态哈希的独立基础设施诊断，不能默默跳过中断。
- 第 2483–2507 行：公共 CLI 只有 `plan/run/status`，没有 eval-only 或“接管原 flight 并补原正常终态”的入口。
- 原 `make_extension_plan` 第 1183–1221 行支持用新 prefix、全新目录创建完整扩展开发计划；不能复用已有试验目录。

因此，对孤儿 flight 的真实结束、压缩、录包完整性与事后独立评价，可以另存为有来源限制的诊断证据；它们不具备原 runner 的命令返回、完整评价链和正常终态，不能冒充原第八格 COMPLETED。原实际中断也不能被新实验通过覆盖。

## 为什么不能拼接旧七格和新九格

固定 `measure_reliability_v4_storage.py` 的 SHA 为 `bea4c4ba80fe99991c5f13f91c2b00f375c94954af53ffbfa19e47d19f69bb6c`。第 192–197 行逐格要求原终态属于允许的 PASS/FAIL/INCOMPLETE/EVALUATION_PENDING、执行 COMPLETED、整数 flight_exit=0、无基础设施停止、配置无错且清理闭合。INTERRUPTED 不满足这些要求。

`reliability_v4_storage_budget.py:56–88` 要求同一完整 canonical 开发计划覆盖两类别、全八条件、seed 4、75 s；`measure:189–203` 还绑定每个原终态的 plan_sha 和原目录。把旧结果移到新计划、复制终态、跨计划拼格或伪造新 START，都会破坏真实执行来源。第 339–340 行要求实际 28 个独立完整物理格。

原 core12 与全新 extension16 可以共用：`measure:98–128` 比较 frozen_root、results_root、source/model/config maps 和完整 protocol 的精确一致性，未固定 extension 的旧 prefix。原 safety snapshot adapter `prepare:95–112` 绑定 canonical core 计划和安全合同；它没有把旧 extension 计划 SHA 写成不可更换条件。因此，在原 core、原安全回执及全部同源关系未变时，无需仅为扩展编排中断再飞一遍 core12 或 safety4。实际工具仍须自行重查这些条件，本文不替代执行。

## 前瞻执行顺序

1. 等待当前孤儿 flight 真实清理、录包归档与所有子进程退出，保留监督器/runner 消失、observer 身份、真实时间和退出证据。禁止重启第八场，禁止凭 monitor 0 宣称原 runner 0。
2. 在原图彻底空闲后，用原入口按原逻辑登记第八次中断；保留旧 owner、waiter、collector03 的停止状态。其余原未尝试槽保持未尝试，原 cohort 记录为因基础设施故障终止，不能给未尝试槽伪造终态。
3. 先修外置监督工作流，保持 frozen54、原单槽入口02、算法、.60/.75、遮挡窗口、故障强度、原门槛和完整分母不动。权威 owner/state 优先放外置 Linux ext4；Windows monitor 只读 UNC 事件，不再让 D 盘共享冲突终止顶层 WSL 监督。原子写入采用独立临时名及有界 EACCES 重试；日志异常时如子进程仍活，须等待其真实结束后再结束 owner，且不启动下一槽。
4. 用短假子进程验证暂时 EACCES、重试耗尽、子进程仍活及真实非零退出等边界，确认不会“监督器先走、runner 被带走”，也不会自动重试原槽。准备、fixture 和实际原生运行须明确区分。
5. 在看新结果前，用原公共 `plan --extensions --probe` 冻结全新 16 格计划及精确文件/内部 SHA；两类、全八条件、seed 4、75 s，固定顺序和每格一次。新 entry03 绑定这个实际新计划；不能继续用写死旧计划的 entry02。新的监督器从零前缀开始，保存确切源码、owner/child 身份和真实命令返回。
6. 按原单槽机制完整执行全部 16 格。算法 FAIL 可以原样保留；未知证据、安全/来源/基础设施异常立即停止后续。未知短窗不能借用别的场景补证，也不能挑更容易的种子。若再中断，保留真实中断并重新评估完整计容路径，不能将它设回 PENDING。
7. 新 16 格全有真实完整终态且监督器实际退出后，再制作与新计划绑定的具名后处理入口：原 core12 + 新 extension16、固定 eedd8d9 tools02 大小测量、原生 idle、真实 inventory、原两类 velocity export、R0。全部新目录、逐步实际 UTC/exit/log SHA；旧 followon01 和未完成的 followon04 准备文件不能冒充已执行。

## 计容完整不等于正式准入

新 16 格主要补齐实际完整计容证据，不保证工程全部通过。同一 frozen54 的无连续缺帧上界、固定遮挡和 .75 s 保护仍存在已诊断交互；原 combined 距离与预测失败可能重现，不能因重复批次而忽略旧失败或宣称算法改进。

全窗性能、安全、身份、未知样本与开发准入继续按原规则审查。若为真实可靠性修复修改后续 frozen55 的算法或协议，则须完成同一最终源码的 core12 + extension16 开发验证及对应安全/容量前置，不能把 frozen54 的 core 与 frozen55 的 extension 混成同源 28 格。正式 held-out 1000–1009 不用于本次开发工作。

本说明是只读源码决策；未启动 WSL、飞行、重评或真实后处理，没有修改原终态。followon04 的未执行 helper 仅作为待审准备保留，目前不能执行。
