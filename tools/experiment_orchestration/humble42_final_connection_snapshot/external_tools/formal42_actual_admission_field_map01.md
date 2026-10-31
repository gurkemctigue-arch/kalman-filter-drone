# Humble42 实际正式准入字段与连接表（只读准备）

记录日期：2026-11-01，Asia/Shanghai。依据是冻结根 `/root/uav_tracking_fullplan_v4_humble42` 的实际源代码、小型元数据和已准备工具的独立审查。本文未执行 prerequisite、源树大哈希、复制、构建、录包导出、容量准入、正式规划、登记或飞行。

状态只引用 root 提供的当时快照：core42 **2 started / 1 PASS**；这不是本文件重新采样的实时计数。完整 core12、safety4、extension16、实际标定、最终根和正式准入均尚未由该快照证明。旧41的 11 PASS / 1 FAIL 仍是原12次，不能继承为42的结果。

下文大写名称仅是文档占位符，不是可执行请求、预留路径或已有证据。所有待定路径、SHA、bytes、预算假设、UTC 和实际状态必须以后用真实产物填写。

## 请求恰含九个字段

权威入口为冻结 `tools/reliability_v4_register.py:29` 的 `REQUEST_FIELDS` 与 `assemble_seal`（297行），不是手写最终 manifest。`BINDING` 恰含 `{path, sha256}`；path 是实际文件的 **resolved 物理绝对路径**，sha256 是其实际文件字节摘要，不得增加键。`ROOT/results/...` 若为指向 D 盘的目录链接，应以其真实 `/mnt/d/...` 文件路径作绑定。原不可变 plan/record/size receipt 内的词法路径和实际命令 argv 保持原样，不能为“规范化”重写它们。

| 请求字段（全部） | 来源及实际生成入口 | 必须先有的真实事实；当前待补 |
| --- | --- | --- |
| `schema_version` | 固定严格整数 `1`。 | 由请求作者填写；不是额外状态或版本证据。 |
| `kind` | 固定 `RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST`。 | 不能使用最终 manifest 的 kind 冒充组装请求。 |
| `final_root` | 独立最终源根；复用 `prepare_development_final_root.py inspect/copy` 和 `build_development_final_root.py build`，见已审 handoff。 | 实际独立 ext4 源/构建根、独立 D 盘 results、无 overlay、原 DRAFT 与准备清单保留；实际冷构建、隔离、FastCDR、11项生成消息 CDR、完整规定测试、strict512 资源闭合。实际新根/路径/构建结论待产生。 |
| `plans` | 恰为 `{core:BINDING, extension:BINDING}`；两者由最终根 `scripts/run_reliability_v4.py plan` 生成，extension 使用 **`plan --extensions`**。准确模板见下文。 | core 为 FORMAL120，extension 为 EXTENSION_FORMAL160；两类、原六组/八工况、held-out seed1000–1009；两计划同 final_root/source/model/runtime；extension 绑定实际 core 文件SHA及内部 digest；`output/plan.json` 与绑定的物理文件一致。首次 seal 时全部280 PENDING、无 trial 目录。两正式计划尚待真实创建。 |
| `registrations` | 恰为 `{core:BINDING, extension:BINDING, replay:BINDING}`；来自实际最终根 canonical `planning/reliability-v4-preregistration.json`、`reliability-v4-extension-preregistration.json`、`reliability-v4-estimator-replay-preregistration.json`。用已审 `publish_development_final_protocols.py protocols/replay` 显式发布。 | 真正 REGISTERED、真实 UTC、合法数值 navigation gate；core/extension 先登记再定义 formal plans；replay 则必须在 formal core 已定义后绑定它。不能用 results 中脱离 canonical 的 candidate 文件替代。三文件及其实际 SHA/UTC 均待产生。 |
| `calibration` | 实际 development candidate 的 BINDING。复用已审 `development_calibration.sh plan/run`；其仅调用冻结 exporter 两次和 calibrator 一次。原始命令见下文。 | 同一42实际完整开发来源，只取 `person_stage1_velocity_seed004`、`car_stage1_velocity_seed004`；实际 arrays、三类审计 sidecars、原 record/run_config/bag_integrity/包路径均核验；原 geometry_statistics 重算成立。candidate 保留 `RELIABILITY_V4_DEVELOPMENT_CALIBRATION`、`CANDIDATE_NOT_REGISTERED`、`DEVELOPMENT_ONLY`。实际导出/候选尚待产生。 |
| `safety` | 实际 `safety_summary_candidate.json` 的 BINDING。由最终根 registrar `safety-summary --target-plan ... --core-gate ... --facts ... --output-directory ...` 组装。 | 真实 prospective registry、原四槽都 PASS、原 `slots_facts.json` planned4/attempted4/pending0；每槽五项 executions、至少12类原证据、原尾速代码/5.2s至最终Clock、原阈值、真实进程闭合。summary 在 facts 后、两工程协议登记前生成。不能绑定 raw facts 或手填 PASS。实际 safety4/facts/summary 待产生。 |
| `state_directory` | 请求作者选取最终物理 results 内的独立新目录。 | 当时不存在、非链接、不在 trial 内，不能提前 mkdir；与独立 seal 输出目录分开。第一次 `seal` 的只读 guard.check 也必须保持它不存在。实际路径待选；不得复用旧 admission state。 |
| `storage` | **完整预算输出中的 `.storage` 原对象**。由实际最终根 `tools/reliability_v4_storage_budget.py` 的六个 CLI 参数生成，见下文。不是整个 budget 报告，也不是一份 BINDING。 | 同一42完整28格 size/archive 真实证据、当前 native inventory、显式增长/临时/交付/剩余工作假设；首次完整280容量通过。当前实测28格、物理库存、假设、bytes 和实际预算结论均待补。 |

调用者不得提供 `created_utc`、`tool`、`manifest_sha256`；原 registrar 在实际 seal 时生成真实 UTC、绑定实际 sibling guard 并封口。它原样调用 guard.check，要求 `result=PASS`、`pending_slots=280`，才独占发布 `RELIABILITY_V4_FORMAL_ADMISSION`；这一步不创建初始 admission state，也不飞行。

source/model/runtime/resource 合同由两个实际 plan、其 gate 和原 guard/runner 校验连接；它们不是可随意扩充的第十个请求字段。原 guard 同样没有 whole-tree seal 或 build-chain 输入字段；独立封存连接必须在外层真实执行。

## storage 的全部组成与来源

| `.storage` 字段 | 实际来源与约束 |
| --- | --- |
| `volumes` | 数组，每项恰实际卷的 `id`、`mount`、`windows_volume_id`；用当次 storage-probe/native backend 的实际挂载及 Windows UniqueId，禁止重复 UniqueId。 |
| `results_volume` | 实际最终 results 所在卷的上述 id。 |
| `vhd_host` | `{distribution,path,volume}`；发行版为实际 `UAVHumble22`，path 必须来自当前用户 Lxss 注册表所登记 BasePath/VhdFileName 对应的真实 VHD；不能猜路径。 |
| `temporary_peak_bytes` | 每个涉及卷显式给出保守临时上界 bytes，不能低于下述推导界。不是“实测峰值”。 |
| `temporary_bound_rule` | `{revision,raw_growth_factor,compressed_growth_factor,extra_bytes_by_volume,basis}`；revision 固定 `three_raw_two_compressed_plus_margin_v1`，两个增长因子为显式有限数且≥1，basis 说明实际样本与保守假设。 |
| `delivery_reservations` | 恰覆盖 `offline_replay20`、`videos12`、`detection_audit`、`figures_documents`、`runtime_logs`；每项 `{bytes_by_volume,basis}`，每项总额>0。当前尚需产物的数量/格式/大小依据待真实制定，不填虚构测量值。 |
| `additional_remaining_bytes` | 每卷显式给未来构建/复制/其他尚需持久化 bytes；为0也须在 assumptions 说明依据。已存在数据已反映在当前free，不重复计入未来量。安全4不属280持久化格，尚需安全/导出/中间工作应另有明确预算。 |
| `cells` | 完整28项；每项为 `{matrix,target_class,condition,persistent_bytes_by_volume,basis,development_size_evidence,archive_evidence}`。matrix 为 core/extension；2类×6 core组及2类×8 extension工况，不能混用旧源或缺格。两个 evidence 都是实际 BINDING。 |

`development_size_evidence` 由已审 `measure_development_completed_storage.sh measure` 生成的一格原 receipt 提供；`archive_evidence` 是该原槽的 `bag_integrity.json`。collector 只做具名文件 stat/元数据盘点，保留原失败；其原 prerequisite 验证器可能读取并哈希归档，不能在运行负载中当作轻量只读命令调用。`eligible_for_budget_input=true` 需要 same-candidate core12+safety4+extension16 全PASS和健康闭合；普通 extension gate 的 PASS 标题不能替换原16条的结果。

每格形式固定为10次，全部28格合计280次。每格持久化量由实际 `total_trial_bytes` 乘显式 `persistent_growth_factor` 向上取整，加各卷明确 extra。每卷临时界为全部28格的最大值：

```text
max_cell(3 * ceil(raw_bytes * raw_growth_factor)
       + 2 * ceil(compressed_bytes * compressed_growth_factor)
       + temporary_extra_bytes[volume])
reserve[volume] = max(8 GiB, temporary_peak_bytes[volume])
required[volume] = 所有尚未尝试正式槽的持久化预算
                 + 五项剩余交付预算 + additional_remaining_bytes + reserve
```

首次 seal 必须预算全部280，不能先跑再补预算。FAIL 不删分母、不重跑；后续 guard 只扣已尝试槽的未来持久化量，交付预算不随飞行偷偷清零。每槽后/下一槽前按当前实际free重核。

当前布局的 D 盘 results 与 UAVHumble22 的 VHD **预计共用一个 Windows 物理卷**，须由当次查询证实；若证实，则只使用一个 id/UniqueId 汇总一次，不能把 results free 与 VHD host free 当两份容量相加。NativeStorage 真实核 `findmnt` 的9p/DrvFS及 D:来源、`Get-Volume -DriveLetter D` 的UniqueId、当前 `statvfs(/mnt/d)`、当前发行版和 `HKCU/.../Lxss` 的登记VHD。ext4 逻辑free另查，不能替代宿主物理free。

assumptions 原 schema 要求：`schema_version:1`、`kind:RELIABILITY_V4_STORAGE_ASSUMPTIONS_NOT_ADMISSION`、`basis`、三个增长因子、`persistent_extra_bytes_by_volume`、`persistent_basis`、`temporary_extra_bytes_by_volume`、`temporary_basis`、`additional_remaining_bytes`、`additional_remaining_basis`、`delivery_reservations`。没有隐含默认增长、余量或交付数值。一次 development export 的8GiB/3raw+2compressed检查不等于正式280容量准入。

## 经源代码核准的后续命令模板

这些命令在真实前置条件完成后由 root 排程执行；本文没有运行它们。`PYTHON` 表示实际隔离 Humble venv Python，`FINAL_ROOT`/各输入都是待绑定的真实物理路径；不要直接复制占位符执行。

1. 最终根冷构建通过后，先定义两个 **不执行** 的目标 PROBE 快照。canonical class 顺序为 person、car，core 原顺序固定如下；extension 不接受 `--groups`：

```bash
PYTHON -B FINAL_ROOT/scripts/run_reliability_v4.py plan --frozen-root FINAL_ROOT --output NEW_TARGET_CORE_DIR --prefix reliability_v4_NEW_TARGET_CORE --probe --seeds 4 --classes person car --groups stage1_velocity stage1_position stage2_crossing stage3_midpoint stage3_active stage3_multi_active
PYTHON -B FINAL_ROOT/scripts/run_reliability_v4.py plan --frozen-root FINAL_ROOT --output NEW_TARGET_EXTENSION_DIR --prefix reliability_v4_NEW_TARGET_EXTENSION --probe --extensions --seeds 4 --classes person car
```

2. 对接实际 same-source 完整开发计划，生成原工具 gate；extension 的 cutoff 是调用当时真实已到达UTC，只用于临时验证，不能冒充协议登记。不得添加 evaluation overrides 将原FAIL提升：

```bash
PYTHON -B FINAL_ROOT/scripts/build_reliability_v4_probe_gate.py --target-plan PHYSICAL_TARGET_CORE_PLAN --probe-plan PHYSICAL_ACTUAL42_COMPLETE_CORE_PLAN --output NEW_CORE_GATE_JSON
PYTHON -B FINAL_ROOT/scripts/build_reliability_v4_probe_gate.py --target-plan PHYSICAL_TARGET_EXTENSION_PLAN --probe-plan PHYSICAL_ACTUAL42_COMPLETE_EXTENSION_PLAN --registration-utc ACTUAL_EXTENSION_CUTOFF_UTC --output NEW_EXTENSION_GATE_JSON
PYTHON -B FINAL_ROOT/tools/reliability_v4_register.py safety-summary --target-plan PHYSICAL_TARGET_CORE_PLAN --core-gate PHYSICAL_CORE_GATE --facts PHYSICAL_ACTUAL_SAFETY_FACTS --output-directory NEW_SAFETY_ASSEMBLY_DIR
```

已审 publisher `protocols --request ... --request-sha256 ...` 再核真实12+4+16全PASS、实际 cold build、gates、summary，显式发布两份 canonical。它不生成正式计划、不授予正式准入。

3. 两份工程协议真实登记后，才创建不执行的正式计划。`--formal` 使用冻结协议的完整 held-out seeds，不指定子集；extension 必须引用已存在的真实正式 core：

```bash
PYTHON -B FINAL_ROOT/scripts/run_reliability_v4.py plan --frozen-root FINAL_ROOT --output NEW_FORMAL_CORE_DIR --prefix reliability_v4_NEW_FORMAL_CORE --formal --probe-gate PHYSICAL_CORE_GATE
PYTHON -B FINAL_ROOT/scripts/run_reliability_v4.py plan --frozen-root FINAL_ROOT --output NEW_FORMAL_EXTENSION_DIR --prefix reliability_v4_NEW_FORMAL_EXTENSION --formal --extensions --reference-plan PHYSICAL_FORMAL_CORE_PLAN --probe-gate PHYSICAL_EXTENSION_GATE
```

4. 真实 development calibration 的内部原始工作命令仅为：

```bash
PYTHON -B ACTUAL42_ROOT/scripts/export_estimator_replay_v4.py ACTUAL_PERSON_STAGE1_VELOCITY_SEED004_TRIAL --output NEW_PERSON_EXPORT
PYTHON -B ACTUAL42_ROOT/scripts/export_estimator_replay_v4.py ACTUAL_CAR_STAGE1_VELOCITY_SEED004_TRIAL --output NEW_CAR_EXPORT
PYTHON -B ACTUAL42_ROOT/scripts/calibrate_estimator_replay_v4.py --plan PHYSICAL_ACTUAL42_COMPLETE_CORE_PLAN --person-arrays PHYSICAL_PERSON_EXPORT_ARRAYS_JSON --car-arrays PHYSICAL_CAR_EXPORT_ARRAYS_JSON --output NEW_CALIBRATION_CANDIDATE_JSON
PYTHON -B FINAL_ROOT/tools/reliability_v4_register.py replay-config --core-plan PHYSICAL_FORMAL_CORE_PLAN --candidate PHYSICAL_ACTUAL_CALIBRATION_CANDIDATE --output-directory NEW_REPLAY_ASSEMBLY_DIR
```

实际采用已审 wrapper 的显式 admission、独立 reviewed 三命令 contract、one-export容量检查、唯一运行锁、真实 owner/terminal 闭合；不绕开它直接跑上面的裸命令。development exports 不加 `--registration` 或 `--slot-id`。R0用 FOLLOW→最终Clock 的全部独立有效 pre-fusion完整几何协方差，含KF拒绝样本，按UUID/track/source时间去重；不能由真值误差、posterior或最好样本挑选。原Q/P0、EMA=.35、common gate=9.21、support=.8保持不变。随后 publisher `replay --request ... --request-sha256 ...` 发布真实 canonical replay；request.calibration 仍绑定 development candidate。

5. 实际28格量测与完整预算使用现成工具；先等实际 extension admission/contract 和所有开发闭合事实齐备：

```bash
bash /mnt/d/WSL/UAVHumble22-validation/measure_development_completed_storage.sh measure --admission PHYSICAL_ACTUAL_EXTENSION_ADMISSION --admission-sha256 ACTUAL_SHA --contract PHYSICAL_ACTUAL_EXTENSION_CONTRACT --contract-sha256 ACTUAL_SHA --reviewed-helpers-sha256 e81621f3ed020deb0656d1465ab39b71c350df2ddfe1a1f30d2600d13ecebab7 --output NEW_PHYSICAL_SIZE_EVIDENCE_DIR
PYTHON -B FINAL_ROOT/tools/reliability_v4_guard.py storage-probe --distribution UAVHumble22 --mount /mnt/d --output NEW_PHYSICAL_INVENTORY_JSON
PYTHON -B FINAL_ROOT/tools/reliability_v4_storage_budget.py --core-development-plan PHYSICAL_ACTUAL42_COMPLETE_CORE_PLAN --extension-development-plan PHYSICAL_ACTUAL42_COMPLETE_EXTENSION_PLAN --size-evidence-dir PHYSICAL_ACTUAL28_SIZE_DIR --physical-inventory PHYSICAL_NEW_NATIVE_INVENTORY --assumptions PHYSICAL_REVIEWED_ASSUMPTIONS --output NEW_BUDGET_JSON
```

collector 输出一份 `<trial.name>.json`/格和 `complete28.json`。budget 的 `--size-evidence-dir` 必须是实际 development results 下的目录；不要把这些输入移进最终 trial 或改写原 receipt。request.storage 复制 NEW_BUDGET_JSON 的 `.storage` 原对象；其 `.storage_sha256` 是出处信息，不是第十个请求字段。

6. 最后三份 canonical 发布后，保留原准备 `source_sha256.txt`/原候选 freeze，另行产出实际最终 whole-source/planning 清单，只允许这三份 planning 文件的显式变动；classified/flight/model maps 保持原合同。root 已指派 `review_repair_patch` 准备独立单文件 `create/verify/admit` 外层连接及 tests，复用 publisher 的受控三处变动与 builder 校验。该连接尚在准备，实际文件/CLI/审查摘要待其交付；本文不重复实现或假定其已运行。外层 admit 将在原 seal 前后 verify，正式 serial 开始前再 verify；**原 guard 本身不读取 whole-tree 清单**，没有新增逐槽 wrapper 的需求。

原实际 seal 入口是：

```bash
PYTHON -B FINAL_ROOT/tools/reliability_v4_register.py seal --request PHYSICAL_COMPLETE_ACTUAL_REQUEST --output-directory NEW_SEAL_ASSEMBLY_DIR
```

必须接到上述独立外层验证并独立审查实际产物；seal成功后还需实际 guard check，再由现成 `formal41_guard_adapter01.py` + `formal280_serial_guard01.py` 串行调用原 guard。适配器从真实 sealed manifest 读取 root/guard/plans/state，未硬编码41或640；不要让旧640 preparation/build/admission常量拒绝新的真实512合同。512必须由42的 actual strict512 source/build/runtime证据支持，而不是把旧640数字替换文本后继续使用旧证据。

## 复用边界与真正剩余工作

已准备且不应重复开发：参数化 core/safety/extension 运行与闭合工具、28格 storage collector、两个具名 development export/R0 wrapper、独立 final-root prepare/build/publish、dynamic formal guard adapter/serial driver。工具通过的小fixture/独立审查只证明工具准备，不能代替实际实验输入。

仍须由实际执行接上：完整42 core12→safety4→extension16门；28格实测和当前物理卷映射/显式预算；实际两个导出及R0候选；独立最终根实际copy/cold build/隔离/CDR/全套测试；目标PROBE与实际gates/安全summary；两canonical登记→正式120/160定义→replay登记；正在准备的最终封存外层实际运行及独立核验；真实九字段request/原seal/full280容量检查；最后才是正式280及后续20回放、12视频、检测审计与完整交付。

本次有界检查在 external 顶层小JSON及41 freeze_validation中未发现可充当42输入的实际旧完整准入请求；旧 `humble21_storage_budget_preparation_handoff01.md` 仅复用schema/算式，其21路径、45s样本和旧状态不适用于42；旧 `humble25_registered_wsl_vhd_allocation01.json` 仅说明registry-backed VHD映射结构，其旧free/bytes不是当前容量证据。旧JSON一律仅作schema参考，不替代新source、gate、bytes、UTC、标定或结果。

源代码定位：register `REQUEST_FIELDS:29` / `assemble_safety:74` / `assemble_replay:220` / `assemble_seal:297`；guard `read_plans:305` / `validate_development:362` / `NativeStorage:669` / `validate_storage:750`；storage_budget `read_development_plan:56` / `storage_location:159` / `assumptions_contract:193` / `main:316`；runner `make_plan:989` / `make_extension_plan:1092` / `main:2352`；gate builder `target_snapshot:35` / `assemble:212` / `run:296` / `main:343`；calibrator `geometry_statistics:34`。这些定位来自冻结42实际源文本读取，未import或执行这些生产模块。
