# 正式280槽外层准入工具与实际输入合同

工具为 `tools/reliability_v4_guard.py`，不属于 runner 的飞行源扫描目录。当前实现不运行正式仿真、不登记协议、不生成虚构PASS。缺少下面任一实际输入时拒绝启动。`check`只读；`run-one`通过全部检查后最多调用一次冻结runner的 `--max-new-trials 1`，保留原FAIL/缺证/基础设施停止，不重试。

## 可执行入口

在实际 Ubuntu/WSL 环境中使用最终根的 Humble Python/依赖；下面命令中的路径均须替换成真实路径。工具本身可以放在主树或独立工具目录，其绝对路径及实际SHA单独绑定，不混进 `flight_source_hashes`。

```bash
# 独立metadata盘点：无manifest、不导入飞行源、不读包或hash源码。
python -B /absolute/tools/reliability_v4_guard.py storage-probe \
  --distribution UAVHumble22 --mount /mnt/d --mount /mnt/e \
  --output /absolute/new/storage_inventory.json

# 正式准入只读检查；缺证则返回2，不创建runner started标记。
python -B /absolute/tools/reliability_v4_guard.py check \
  --manifest /absolute/final_admission.json --output /absolute/new/admission_check.json

# 所有真实输入齐备之后，才可调用；每次仅一槽，无自动批循环。
python -B /absolute/tools/reliability_v4_guard.py run-one \
  --manifest /absolute/final_admission.json
```

已有基础设施停止时，须额外传对应计划的 `--core-resolution PATH --core-resolution-sha256 SHA` 或 `--extension-resolution PATH --extension-resolution-sha256 SHA`。诊断JSON必须包含实际 `result=PASS`、原 `plan_sha256`、该计划**全部**原停止记录的 `resolved_record_sha256`、晚于失败的 `created_utc`、非空 `evidence:[{path,sha256},...]`。没有诊断或有RUNNING未闭合旧尝试时拒绝，不将其变回PENDING。工具只按 core→extension 顺序选择下一条原PENDING；core中普通算法FAIL不会消失。

## 所有文件绑定

`BINDING`统一表示恰含 `{"path":"绝对实际文件路径","sha256":"实际文件SHA256"}`，不允许额外键。路径与字节都验证；原bag/VHD不由guard hash。小JSON/YAML/log/脚本等独立证据最大128MiB；超出该界应保留失败并明确另行设计输入，不能绕过校验。JSON重复键、NaN/Infinity拒绝。

最终manifest是schema1对象，至少包含下列键：

```text
schema_version: 1
kind: RELIABILITY_V4_FORMAL_ADMISSION
created_utc: 真实UTC，晚于三份登记，早于任何正式飞行
final_root: 实际最终冻结根绝对路径
tool: BINDING（本工具实际执行文件）
plans: {core: BINDING（120正式plan.json）, extension: BINDING（160正式plan.json）}
registrations: {core: BINDING, extension: BINDING, replay: BINDING}
calibration: BINDING（真实R0_candidate.json）
safety: BINDING（真实最终四安全summary）
state_directory: 最终results内独立全新目录，不能位于某个trial内
storage: 下节完整容量对象
manifest_sha256: 去掉本字段后的canonical JSON SHA256
```

canonical算法为 `json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False)` 的UTF-8 SHA256。可导入guard的 `sealed(manifest,'manifest_sha256')`生成；这只是封口，不代表准入通过。第一条正式飞行前必须存在完整280预算；工具首次成功执行前独占写 `initial_admission.json`，绑定manifest/tool/完整280容量。以后必须继续使用同一manifest/tool；不能在看过正式结果后补第一次容量登记。

两正式plan必须是相同最终root/source/model的完整120和160，extension实际绑定core文件SHA/digest。工具调用冻结 `validate_plan` 和 `verify_sources` 保留其现有完整开发gate、实际源码/环境/权重合同；不绕过既有必需校验，也不额外遍历hash旧bag。

三份registration必须是最终根 `planning/` 中原对应名字的实际文件。core与extension顶层均需 `status=REGISTERED`、`registration_utc`；core还需合法数值 `navigation_acceptance`。两者先于core正式plan创建。四法配置须通过现有 `validate_registered_config`、`verify_registration_artifacts`，绑定实际core文件；其登记晚于core定义且早于首飞。manifest晚于三登记，所有原飞行开始时间必须晚于manifest和三登记。

## R0和真实开发gate

实际 core gate恰12格、extension gate恰16格，不能使用fixture。R0的 `development_plan` 须是 core gate 引用的同一个完整 seed004 两类六组canonical计划，来源仅 `person_stage1_velocity_seed004` 和 `car_stage1_velocity_seed004`。工具验证候选的计划、两个终态record、两份arrays、原run_config/bag_integrity与原包路径，以及实际online/native/truth sidecars；重新执行**数组函数**核定标统计，不读bag。原EVALUATION_PENDING允许，但基础设施停止/不完整飞行不能充定标来源。

四法 `freeze_requirements.development_calibration_evidence.artifact_hashes` 必须以**候选文件的实际resolved绝对路径**为键保存其实际SHA。已登记参数逐项等于该候选 `candidate_parameters`；候选policy及calibrator源也须匹配。生成最终root/登记时勿改变实际开发飞行源或评价源；需要变更时保留旧证据，另作前瞻验证。

## 四安全事实与最终汇总

实际driver先保存独立 `RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY`、逐命令facts和原报告；最终数值gate未登记时，保持 `RELIABILITY_V4_SAFETY_EXECUTION_FACTS`，不先填未来summary的PASS。全部实际证据完成后，最终summary只组装原事实和最终gate bindings：

```text
schema_version: 1
kind: RELIABILITY_V4_FINAL_SAFETY_SUMMARY
result: 由四槽真实结果推导
evidence_scope: REAL_RECORDED_DEVELOPMENT_EVIDENCE
created_utc: 全部实际评价和facts结束后、两工程协议登记前
bindings: 最终core gate.evidence.bindings原对象
source_facts: BINDING（原slots_facts.json）
slots: 与原facts.slots完全一致的四项数组，不重新编辑槽事实
```

facts必须真实 `result=PASS`、`evidence_scope=REAL_RECORDED_DEVELOPMENT_EVIDENCE`、`planned_count=4`、`attempted_count=4`、`pending_count=0`；`registry`绑定原前瞻registry，且registry≤飞行开始≤评价结束≤facts≤summary。registry绑定实际canonical core PROBE文件/SHA/digest、flight_source_hashes、原execution_card、driver、tail_script、四个原名字和原完整flight_argv。guard核对这些真实绑定，不因summary单独写PASS就接受。

四个slot ID固定为两类 `person/car` × `auto_unique_multi/locked_ambiguity` × seed004。每个原slot需含 `id,target_class,case,seed:4,result,trial_directory,executions,evidence`。可保留driver的全部其他真实诊断字段。

`executions`恰有 `flight,source_clock,native_startup,specialized,terminal_speed` 五项；每项保留真实 `argv`、`started_utc`、`finished_utc`、`returncode`、`error`、`log:BINDING`。`terminal_speed`另有 `code_script:BINDING`，它是实际执行的独立.py，须与冻结执行卡的tail Python代码逐字一致，且匹配registry.tail_script。guard支持实际argv第3项为该.py路径或stdin的 `-`；均不改原命令事实。原报告不改名。

每槽 `evidence` 至少绑定下面12项（`runtime_parameters`按真实YAML安全解析，不要求变成JSON）：

| key | 原trial内路径 |
| --- | --- |
| run_config | run_config.json |
| source_snapshot | configuration/source_sha256.json |
| runtime_parameters | configuration/runtime_parameters.yaml |
| bag_integrity | bag_integrity.json |
| recording_closure | recording_closure.json |
| process_exit_codes | process_exit_codes.json |
| source_clock | px4_source_clock_report.json |
| native_startup | native_startup_report.json |
| specialized | auto_unique_evaluation_v2.json 或 stage2_evaluation.json |
| terminal_speed | terminal_hover_speed_evaluation.json |
| rendering | configuration/gazebo_rendering_libraries.json |
| magnetic | configuration/magnetic_environment.json |

独立报告需实际PASS，并核验原冻结evaluator、同一bag/output和必要命令flags；支持driver在最终root cwd下的相对 `scripts/...` 原参数。唯一实例确有持续多候选且末端歧义悬停；指定个体确有selected几何歧义、同UUID停控；尾速原5.2s延伸到closure最终Clock。source/native、真实renderer、磁场loaded libraries和基础设施分别验证。成功子进程要求 gazebo/px4/bag/monitor/ros 均0；只允许owned agent为0或预定SIGINT的-2。真实results symlink通过已核resolve一致的原lexical `dev_root/results/trial` 调现有classifier，避免丢失冻结root。

## 容量对象storage

```text
volumes: [{id: 本manifest内卷ID, mount: /mnt/d, windows_volume_id: storage-probe实际UniqueId}, ...]
results_volume: 上述某ID
vhd_host: {distribution: UAVHumble22, path: 实际/mnt/.../ext4.vhdx, volume: 对应ID}
temporary_peak_bytes: {每个卷ID: 显式声明临时上界bytes}
temporary_bound_rule:
  revision: three_raw_two_compressed_plus_margin_v1
  raw_growth_factor: 显式有限数值≥1
  compressed_growth_factor: 显式有限数值≥1
  extra_bytes_by_volume: {每个卷ID: 显式余量bytes}
  basis: 解释这是从原归档大小推导的保守预算，不是实测峰
delivery_reservations:
  offline_replay20/videos12/detection_audit/figures_documents/runtime_logs:
    bytes_by_volume: {每个卷ID: 尚需持久化bytes；每项总和必须>0}
    basis: 对应任务预算来源与增长余量
additional_remaining_bytes: {每个卷ID: 未来build/复制/其他持久化预算，显式可为0}
cells: 恰28项，结构见下文
```

volumes只列实际results和当前WSL VHD宿主涉及的卷。同卷用同一个ID汇总一次；Windows UniqueId重复的两个声明拒绝。工具通过 `/mnt/<drive>` 的实际DrvFS/9p挂载和 `os.statvfs` 查询Windows卷剩余bytes，同时从当前WSL发行版的Windows注册表核实际VHD位置；不使用 `/root` 的虚拟free替代真实宿主容量。ext4逻辑free另作必要补充检查，其检查保守采用宿主卷总剩余预算，不降低物理门。

每个cell为 `{matrix:'core'|'extension',target_class:'person'|'car',condition:原组/工况,persistent_bytes_by_volume:{所有卷ID:bytes},basis:显式预算依据与增长余量,development_size_evidence:BINDING,archive_evidence:BINDING}`。必须完整12核心+16扩展各格，始终保留每格十条正式计划；即使部分正式槽已失败也不能删除相应预算格。原size evidence应为现有测量helper的 `scope=FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE`、`trial`、`files:{原相对路径:bytes}`、`total_trial_bytes`。工具核它属于真实对应开发gate槽，按**具名文件列表逐文件stat**，不递归遍历或hash包。archive_evidence必须是同槽原 `bag_integrity.json`；原压缩文件只stat大小，raw/comp对应bytes从该原归档JSON取值。

每格临时预算推导为 `3*ceil(raw_bytes*raw_growth_factor) + 2*ceil(compressed_bytes*compressed_growth_factor) + 该卷extra_bytes`；所有28格取最大。临时目录分布可能涉及VHD和results，因此对每个涉及卷保守预留此完整界；同一物理卷只计一次。声明temporary_peak不得低于推导界，实际reserve取 `max(8GiB,temporary_peak_bytes)`。这是一条已声明增长假设下的保守预算；不把一个开发样本或公式称为未来峰值的实测证明。高熵故障工况的较大raw/comp数据必须实际进入28格。

每卷准入为：`physical_free >= 未尝试正式槽逐格持久化预算之和 + 剩余delivery/additional预算 + max(8GiB,临时上界)`。第一次涵盖全部280；后续仅扣除已尝试槽，任何FAIL不补跑。交付固定预留不随飞行完成悄悄减少。每槽结束再次采样/重算，下一槽前再从当前free准入；不足时在任何新started标记前拒绝，PENDING保持原样。新盘路径必须在正式plan创建和manifest封存前确定，不能中途改results symlink或迁移旧记录。

## 当前尚缺的真实输入

最终canonical12/四安全/16扩展实际证据；两个具名R0实际arrays+审计和候选；三份真实REGISTERED；最终120/160未执行plan与两个实际gate；四安全原registry/facts和最终summary；28格持久化/原archive大小证据；实际卷UniqueId/VHD信息、逐格增长/临时/交付完整预算；最后是自绑定工具和封口manifest。工具实现、fixture通过或metadata盘点均不能代替这些输入。当前正式280仍未由本工具执行。
