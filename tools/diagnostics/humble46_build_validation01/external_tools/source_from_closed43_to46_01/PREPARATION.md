# Humble46 source adapter：仅候选，尚未执行

入口 `assemble_closed43_to46_source.py`。现已固定真实commit
`de89a6696d60a113929c97bab775dc2258ef4d01` 与实际maps SHA
`427be692d9706aa901b3843d92f5422ebff5cc076bbfd5f0942290af066ec4d8`；
此前双None占位阶段已结束。常量缺失/非法仍在任何后端/source/Git/输出动作前拒绝。
本文不是运行授权，须先完成独立peer审查再由root实际执行。作者仅准备脚本、
34件小metadata清单、实际Windows源码maps/Git/newgate bindings及AST检查；
没有执行assembler、WSL、构建或飞行，没有打开原bag/运行时负载；Git已提交证据
snapshot的字节作为完整source map的一部分实际hash，不能称未读取任何历史字节。

复用未改45 adapter及其44 adapter、`retain43`、`retain_failed44`、42 Retainer与
原generic/build backend。健康来源仍43，44 suite FAIL、45 build/validate PASS与
45 core STOP 1 PASS/1 INFRASTRUCTURE_ERROR/10 PENDING（raw terminal_count=1）分别
保全；owner mismatch原文保留。45原结果只复制34件固定小metadata到全新external
历史目录，不改变capsule的原白名单、两条closed boundaries或文件/字节上限。

`historical45_metadata_pins01.json`绑定准备时实际34件原件（1,546,721字节），
SHA256 `c386b25fd3998ab44917881c944d1eb70afc7db608e169c6a47c7412bcb7a483`。
这是清单，不是已复制或新验收的回执。实际执行时逐件重新核对原SHA/大小、按字节
复制fresh external、保全精确失败字段、再次核对原件。失败输出不能覆盖后重试。

## 实际commit maps已准备，等待外部独审回执

`reviewed_commit46_maps01.json`现为实际文件：1123个完整source条目、295个classified
条目；相对43完整Git/物理delta为16 changed、270 added、0 removed，classified为
4 changed、1 added、0 removed。map诚实保持作者PREPARED状态，独审由外部回执绑定
实际map与adapter SHA；不先把作者准备标成已独审，也不改map状态制造SHA循环。字段：

- `schema_version=1`；
- `scope=COMMITTED46_FULL_SOURCE_AND_CLASSIFIED_MAPS_NOT_RUNTIME_ACCEPTANCE`；
- `status=ACTUAL_COMMIT_MAPS_PREPARED_FOR_INDEPENDENT_REVIEW`；
- `source_commit`：真实最终40位commit；`source_root`：实际`/mnt/d/...`源码根；
- `baseline_commit`：健康43的`25bd5aa92c642a98503ce586ed028daa224e4326`；
- `files`、`files_canonical_sha256`：完整tracked+继承ignored+原override物理SHA map；
- `allowed_delta`：相对43完整的`changed/added/removed`，须逐类等于实际Git delta；
- `classified_source_hashes`、`classified_canonical_sha256`、`classified_delta`：
  最终实际runner计算，并由完整map包含；不得使用旧44两文件runtime delta；
- `review_evidence`：非空的实际最终source/test独审小回执`path/sha256`；
- `supervisor_stream_timing_sha256`：实际注册stream摘要的canonical SHA；
- `prospective_gate_bindings`：实际新gate generator的`bindings()`结果，包含新stream
  digest、实际flight/evaluation/model/magnetic及继承各策略绑定；它不是已生成gate；
- `formal_or_runtime_acceptance_claimed=false`。

使用原canonical JSON规则。独审须核对完整真实map，而不是仅信任作者自报的delta。
adapter实际执行仍重新计算所有map/delta，并调用原`candidate_binding`核对每个新增/
修改源码的实际物理字节与已提交Git blob。旧原件、generic strict512/resource、
source overrides、安全和capsule检查不改。

新协议必须明确注册source模式：两类source age均0.5秒、future均0.05秒，RTF0.125
规划两类wall预算均4秒，上界10秒。实际runner验证协议与trial显式flag；实际gate
generator绑定须与独审pin完整相等。此步骤不生成plan/gate、不宣称真实参数已运行，
安全4场仍须按独立补充检查核对实际run_config/runtime YAML。

实际commit与maps SHA已固定，现交peer独审最终候选脚本；root另行安排独占原生
窗口。CLI沿用`--source-root --name v4_humble46 --commit --core-tools-sha256`。
只产PENDING source review/capsule/历史摘要，不自动freeze/build/validate/flight或FINAL。
所有46 source/results/history/review/capsule/outcome路径必须全新；一次失败保留原输出。
