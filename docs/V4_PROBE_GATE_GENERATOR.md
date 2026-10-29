# V4 开发关口离线生成

`scripts/build_reliability_v4_probe_gate.py` 只组装已有不可变开发证据，不启动仿真、不读取 bag 数据库、不运行评价器、不登记协议，也不创建正式计划。当前未形成完整新版开发矩阵时，它应拒绝输出。

核心关口要求两类 × 六组的全部独立工程验收 PASS：

```bash
python scripts/build_reliability_v4_probe_gate.py \
  --target-plan /final_source/results/probe_snapshot/plan.json \
  --probe-plan /final_source/results/core_development/plan.json \
  --output /new_artifacts/core_gate.json
```

扩展关口要求两类 × 八工况全部可评价；允许的算法失败从现有 `extension_algorithm_failures` 原样保留，时钟、启动、录制完整性和长丢失悬停安全缺证仍拒绝：

```bash
python scripts/build_reliability_v4_probe_gate.py \
  --target-plan /final_source/results/extension_probe_snapshot/plan.json \
  --probe-plan /final_source/results/extension_development/plan.json \
  --registration-utc ACTUAL_CURRENT_OR_PAST_UTC \
  --output /new_artifacts/extension_gate.json
```

`--registration-utc` 必须是显式 UTC、当前或过去、严格晚于所有实际开发终态记录。它只是传给临时验证上下文的截止时间，元数据标为 `NOT_PROTOCOL_REGISTRATION`；不改变原计划、协议、登记状态或时间。正式协议之后仍须在真实时刻单独登记，其实际注册 UTC 会再次检查相同开发记录；禁止倒填时间或使用未来截止时间。

`--target-plan` 必须是相应的 PROBE / EXTENSION_PROBE 冻结快照，导航阈值已 REGISTERED，源码、权重、协议和当前生成器/验证器文件与快照一致。该目标快照可以尚未执行。`--probe-plan` 可重复，每份显式提供的计划包含的所有槽都会进入关口；不能从中挑选成功子集。重复计划、缺终态、基础设施中止、篡改原工件、来源不一致、漏单元格均拒绝。

原始报告须来自目标使用的独立评价修订。本最小生成器不推断或执行离线重评，也不自动寻找新的覆盖报告；若需要现有验收合同允许的 `evaluation_overrides`，须另行明确准备并审计证据，不得覆盖旧报告或终态记录。

输出先落到同目录临时 JSON，现有 `validate_probe_gate` 重新读取该实际工件及其引用的冻结计划、终态、运行配置和独立报告。通过后才独占创建最终 gate；现有输出永不覆盖。checks 中的布尔值不能替代验证器的独立复核。生成元数据保留目标计划哈希、实际实现哈希及原始终态计数，扩展 FAIL 不改写成飞行 PASS。

纯 fixture 专项：`python -B -m unittest tests.test_reliability_v4_probe_gate -q`。测试只生成标为 `ORCHESTRATION_FIXTURE_ONLY` 的合成证据，不产生可用于真实验收的 gate。
