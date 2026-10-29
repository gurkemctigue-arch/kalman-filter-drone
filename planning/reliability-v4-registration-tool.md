# 正式登记工件组装工具

`tools/reliability_v4_register.py` 只组装全新文件，不修改最终根的三份
canonical planning JSON，不创建正式计划，不调用飞行、评价器、bag reader 或
`guard.run-one`。现有 gate / plan / calibration CLI 仍是各自实现入口。
本工具的存在、静态检查或 fixture 测试均不表示真实协议已登记或正式实验完成。

## 三个动作

```bash
python -B /absolute/tools/reliability_v4_register.py safety-summary \
  --target-plan /absolute/final/results/NEW_GATE_TARGET/plan.json \
  --core-gate /absolute/final/results/ACTUAL_CORE_GATE.json \
  --facts /absolute/development/results/ACTUAL_SAFETY_AUDIT/slots_facts.json \
  --output-directory /absolute/new/safety_assembly

python -B /absolute/tools/reliability_v4_register.py replay-config \
  --core-plan /absolute/final/results/ACTUAL_FORMAL_CORE/plan.json \
  --candidate /absolute/development/results/ACTUAL_CALIBRATION/R0_candidate.json \
  --output-directory /absolute/new/replay_assembly

python -B /absolute/tools/reliability_v4_register.py seal \
  --request /absolute/admission_assembly_request.json \
  --output-directory /absolute/new/seal_assembly
```

这些是模板，本次实现没有执行它们。每次必须使用全新独立目录；已有输出、原
trial 内部和冻结 source/build 树均拒绝，且检查在创建组装账本之前完成。算法
模块只通过 `guard.load_runtime(final_root, plan)` 导入并保留其模块路径隔离检查，
工具不会预先导入主树的 `uav_tracking`。

`safety-summary` 生成 **safety_summary_candidate.json**。它核对真实 canonical12
gate、原 facts/registry/四槽、五次实际执行的 argv/UTC/退出码/log SHA、独立 tail
代码与冻结执行卡逐字一致、至少12类原工件 SHA、原 source/native 报告、专项检查
和覆盖原最终 Clock 的完整5.2秒物理尾速报告，逐项保留原 `facts.slots`，包括真实
进程退出码。原 facts 缺尝试或失败不能变成 PASS。

该候选**仍待完整 guard 安全校验**：完整 runtime YAML/源码映射、renderer/magnetic
独立校验、nested 进程合同、精确命令/路径语义以及之后真实协议登记的时间关系由
`seal` 中原 `guard.check → validate_safety` 完整再核。当前安全 API 要求真实登记
时间，而 summary 必须先于登记产生，因此生成时不填占位登记或未来 UTC，也不
声称已通过最终安全门。候选 `kind/result` 仅按原事实组织兼容字段，账本明确标记
`PENDING_SEAL_WITH_REAL_PROTOCOL_REGISTRATIONS`，不能单独充作准入凭证。

`replay-config` 要求实际 FORMAL core 定义且120槽全为原 PENDING；读取最终根原
replay 草案，在新目录生成 **replay_configuration_candidate.json**。参数逐项采用
真实 canonical seed004 两条 velocity 的 R0 candidate，保存完整 core source map，
实际 offline/export source map、模型/runtime、原 arrays、三个独立 sidecar、具名
record/run_config/bag_integrity、policy 和 helper 的真实 SHA。原 guard 开发校验会
重新执行数组统计及独立 export 审计，不能仅凭 hash 格式或候选 PASS 字段生成。
现有 `validate_registered_config` 与 `verify_registration_artifacts` 也必须通过。

生成的配置含完整 `REGISTERED` schema 和实际生成 UTC，供后续显式发布；**最终根
canonical 文件此时仍是原草案，不能因此称它已真实登记**。原草案精确字节另存
`source_draft.original.json`。root 后续发布必须先保存 canonical 原字节、核预期原
SHA，再只更新该真实指定路径；不能重写任何已有 REGISTERED 配置。发布后仍需
完整 seal。这个 canonical 发布步骤与 core/extension 登记由 root 显式操作，本
工具首版不支持自动替换，避免不完整事务被误认为最终封存。

`seal` 的 request 恰含以下字段，不接受调用者指定创建时间、工具或封口 digest：

```text
schema_version: 1
kind: RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST
final_root: 最终真实冻结根
plans: {core: BINDING, extension: BINDING}
registrations: {core: BINDING, extension: BINDING, replay: BINDING}
calibration: BINDING
safety: BINDING
state_directory: 最终 results 下独立、尚不存在的 guard state 目录
storage: guard-inputs.md 中实际完整28格/卷/VHD/临时/交付预算对象
```

BINDING 恰为实际绝对 `path/sha256`，所有容量数值和证据由已授权实际工作产生，
不由 registrar 猜测。manifest 使用实际 UTC、单独绑定兄弟 guard 的实际文件
SHA，并按 guard canonical 算法封口。原 `guard.check` 必须用真实三登记、两正式
计划、开发/定标/四安全和完整280预算全部通过后，才独占发布
**final_admission.json**。没有后门、fixture backend、降级准入或 `run-one` 调用。
这次 check 只读，不创建 `initial_admission.json` 或 runner `.started.json`。

## 依赖顺序与账本

1. 完成最终 canonical12、四安全、扩展16和两个具名实际 export/候选定标；保留
   全部原 FAIL/缺证和完整分母。
2. 在全新 final root 先固定 navigation 数值，使用现有入口生成只作定义的
   target PROBE 与12/16 gate。此时不要先登记 core 顶层状态；改变 live protocol
   后，旧 target snapshot 的协议 SHA 校验会正确拒绝再次生成 gate。
3. 生成先于真实 core/extension 登记的 safety candidate；随后 root 显式完成两
   份 canonical 协议登记。用现有 plan CLI 创建120与绑定它的160定义，不执行。
4. 生成 replay 配置候选并由 root 显式发布到真实 canonical 路径；它反向绑定
   已存在的120正式计划，因此不能把“三登记后再生成所有计划”当作字面顺序。
5. 最终完整 source/planning 清单须在三登记就绪后另行封存。准备真实容量
   request，执行 `seal`，之后正式执行仅可经过原 guard 的 `run-one`。

每个新目录保留 `started.json`、`outcome.json`，均绑定 registrar 自身实际 SHA；
manifest 单独绑定 guard。校验文件只放该目录 `.validation/`，通过后原字节以
独占 hard link 发布；失败保留原因并删除未发布候选，不留下可用封口 manifest。
账本不原地重试、不覆盖；发生失败后由 root 诊断再使用新具名目录。

成功回执保留临时校验位置和发布后的相同字节 SHA；临时路径在结束时删除，不能
把它当成另一个长期证据文件。任何准入检查只证明当时实际输入，首次飞行仍须
原 guard 再核当前来源、真实容量与所有登记。工具没有组装最终总源码清单、
自动选工程阈值、自动生成容量预算、自动定标读包或自动修改 canonical 草案的
功能；缺失这些实际输入时仍拒绝 seal。
