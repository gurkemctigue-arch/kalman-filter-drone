# 离线 GT 端点修订执行说明

当前路线更新：Humble16已把端点修补与阶段三显式运行参数一起重新冻结，并使用新完整开发矩阵生成同源报告。因此不再为旧15补全套 navigation 重评或 overrides，也不以旧15替代16开发gate或定标。本页下方保留原先设计的纯离线修订备用路线；它不是16当前必做步骤，且不能跨越飞行关键来源差异复用旧证据。

本修订只处理 `PoseSeries.at` 的左右精确样本查找。既有严格 `abs(dt) < 1e-9 s` 条件不变；命中时返回实际源样本，真实越界与长缺口仍拒绝。精确重复源戳保留稳定首样本查找，不新增 GT 一致性推断或改动其他模块的去重规则。任何冻结15源码、原报告、原槽和原计划均不改。

15行人 clean 原末格为 `39.352000000000004 s`，实际末 Clock 和声明 GT 为 `39.352 s`，相差一个 ULP。原报告的212/213真值覆盖及 unknown 保留；其覆盖仍满足既定0.99候选门。本修订不阻止15按原冻结继续开发飞行，尚未读取录包或生成新版评价结果。

最终统一离线来源准备好后按以下顺序执行：

1. 新建并冻结完整最终评价 snapshot，保存脚本/helper SHA；确认与15的飞行关键源码、模型、运行时、安全参数均相同。`scripts/evaluate_online_state_accuracy.py` 属于已声明离线来源，不能借本修订改变在线算法或重新飞行。
2. 在重分析窗口中，使用该 snapshot 的 `evaluate_navigation_reference.py` 对15核心**全部 navigation 证据**统一另名重评，而不是只修一个 unknown 格。扩展 navigation 证据也须与最终 helper 来源一致。多目标评价继续显式传入独立物理身份报告。
3. 新主报告在原 trial 目录另命名，如 `navigation_reference_offline_endpoint_v1.json`；三个对应 sidecar 与执行日志也使用新名。执行前逐一确认新路径不存在。保存实际命令、返回码、执行时间、日志与新报告 SHA，禁止复用或修改原报告。
4. 比较原计划、原槽及其原 `artifact_hashes` 所列工件的前后 SHA。`read_slots` 会继续核验全部旧工件；新文件不改变原终态，也不能把失败重标为成功。
5. 新开发 gate 的每个相应 `probe_slots` 引用附 `evaluation_overrides`：`kind=navigation`、新 `report`、`report_sha256`、最终 `evaluation_root` 和真实 `execution`。最终脚本及所有 helper 的来源必须一致；只保留未变的主脚本 SHA 不够。
6. 现有 gate CLI 不接收 overrides。独立装配新 schema2 gate/override 清单，绑定最终离线来源、原15飞行来源和完整12格，然后调用现有 `verification_context` 与 `validate_probe_gate` 验证，成功后独占写出新 gate。仅在完整开发、既定数值门及前瞻登记条件满足后供正式计划引用。

这条路线已由 `tests/test_reliability_v4_runner.py` 的 `test_probe_offline_revision_requires_new_named_report_with_actual_provenance` 覆盖。它不授权重试失败槽、改写旧记录、删去 unknown 分母或放宽任何验收门。本次有限专项为 `tests.test_online_state_accuracy` 与 `tests.test_navigation_evaluation`；真实新版重评留待统一最终离线 snapshot。
