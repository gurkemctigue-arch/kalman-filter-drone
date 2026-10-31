# 参数化 safety4 外部工具：待独立审查

本次只准备工具和小型临时 JSON 测试，没有执行真实 register、run、WSL 或仿真。它不改变旧 41 工具、结果、阈值或任何依赖模块的根目录变量，也不指定新 42 根目录。

`development_safety.py/.sh` 接受 `development_runner.py` 已独立审查的显式 candidate manifest。两个动作都重新检查同源 build/source、实际完整 core12 的原始 run-core terminal、12 项原始 record/audit、每项 started/attempt 文件和原生健康 owner。必须是当前候选的 12/12 原始 PASS；旧 11 PASS/1 FAIL、手写 summary、缺项、source 或 owner 变化均不允许进入 safety。

`register` 只创建当前 candidate prefix 派生的新 safety audit 和 prospective registry，不飞行。registry 保存原四场固定顺序、每场完整飞行及四个评价 argv、各 argv 的 canonical SHA、实际 core 完成证据、source/build/tool/card/tail 绑定。之后必须由 root 独立审查这个实际 registry，`run` 才可接收其不可变 SHA。

原四场顺序保持：person auto_unique_multi、person locked_ambiguity、car auto_unique_multi、car locked_ambiguity，均使用开发 seed 004。唯一实例场 35 秒、两候选、禁止跟随；指定个体歧义场 50 秒、三候选、显式 middle 框选。安全阈值、native/source 门、5 次执行和 12 项证据保持原样。原末尾 5.2 秒完整区间同时检验观测里程计速度及离线 GT 机体点差分速度不超过 0.30 m/s，未截短、移窗或放宽。GT 只参与离线评价。

参数使用下列占位符，替换为已经独立审查的实际文件和 SHA；不要直接复制占位符执行。

```text
development_safety.sh describe

development_safety.sh register \
  --manifest <development_candidate_*.json> \
  --manifest-sha256 <actual-final-candidate-sha256> \
  --core-contract <development_contract_core_*_final*.json> \
  --core-contract-sha256 <actual-final-core-contract-sha256> \
  --reviewed-tools-sha256 <independently-reviewed-safety-tool-canonical-sha256>

# root 独立审查 register 实际输出后，另行执行：
development_safety.sh run \
  --manifest <same-final-candidate> \
  --manifest-sha256 <same-candidate-sha256> \
  --core-contract <same-final-core-contract> \
  --core-contract-sha256 <same-core-contract-sha256> \
  --reviewed-tools-sha256 <same-reviewed-safety-tool-canonical-sha256> \
  --registry-sha256 <separately-reviewed-actual-registry-sha256>
```

run 直接调用原 `run_stage1_trial.py`，只有一层 machine SITL lock，不调用普通 `run_plan`。每场恰好 flight、source_clock、native_startup、specialized、terminal_speed 五次执行。只有完整 specialized/tail 算法 FAIL 可保留并继续下一原始场；flight/source/native 非零、缺项、观察器、清理或来源异常立即停止，并保留已尝试和 pending 的原始分母。无重试、覆盖、自动后续动作或正式 seed 准入。

四场全部 PASS 后，工具生成的开发 summary 仍须交由实际候选冻结源码的完整 `guard.validate_safety` 重读验证。未来 extension 应调用 `require_completed_safety`，且传入同一显式 Context/registry SHA；不接受手工构造 admission。当前工具不会执行 extension 或授予正式验收。

首次 Python fixture 验证：`python -B -m unittest -v test_development_safety`，12 项全部通过，5.282 秒。测试只创建随后清理的小型临时 JSON/文本，不读取 rosbag 或模型，不启动子进程。shell 包装器沿用已审查的 development runner 隔离环境方式，实际 Linux 包装器及仿真尚未执行。

上游 512 资源与 build supplement 审查完成后，安全工具将 core 依赖锁定到 `757c36922fe6ea751d181d0f6b93af0ff97b2558dd1720794555b72c56fdc705`。main 在实际 runtime preflight 后，把真实 resource 绑定保存到 `built['_resource_runtime_binding']`，供 core entry 每次重验；缺失资源立即拒绝。只重验受影响的两项准入测试和新增 cache 测试，3 项全部通过，2.813 秒；其余原测试无变动。当前共有 13 项唯一测试有通过证据，仍等待独立安全工具审查。Humble `bash -n development_safety.sh` 也已通过，未执行包装器实际动作。
