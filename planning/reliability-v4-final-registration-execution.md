# 最终前瞻登记与 280 槽执行依赖审查

2026-10-30 当前更新：项目已单独采纳[工程要求决策](reliability-v4-engineering-requirements-decision-20261030.md)，导航数值门为距离/高度RMSE上限1.0/0.40米、导航/真值/指定个体物理身份覆盖下限0.80/0.99/**0.80**，并保留末端持续稳定。数值登记与本机[采纳回执](../results/development_20261030/numerical_gates_adoption01.json)不等同正式准入；核心和扩展均为75秒，整体协议仍DRAFT、正式0/280。旧0.75身份门提议不采用。后续正式登记必须实际核对需求文档、SHA与登记UTC，不能只依赖数值域校验。

现有 `tools/reliability_v4_register.py` 提供 `safety-summary`、`replay-config` 和 `seal` 三个独立组装入口；`tools/reliability_v4_guard.py check/run-one` 负责实际逐槽准入。它们不替代core/extension协议登记或正式计划生成，均需真实12核心、4安全、16扩展、定标和容量输入。下文更早的“registrar未实现”等描述仅表示当时状态；不得据此重复开发已有工具。Humble23及所有旧冻结字节保持不变，本页只更新主树执行说明。

本文件仅依据现有源码、三份草案和执行卡作轻量审查；没有登记协议、创建正式计划、运行仿真、解包、重算录制或推送 GitHub。`3ad042df64c53e8b6b6636d17f78912ab04db17f` 仍是本次审查起点的公开检查点。Humble16 原计划、记录与缺证不变；正在修复的 closure readiness 源码须先由主代理完成验证。下面的 `FINAL_DEV` 表示最终修复后、已完成实际开发证据的那个新根，不能预先认定为 Humble16。

后续实现更新：审查发现的外层缺口现已落实为 `tools/reliability_v4_guard.py`，输入合同和真实执行命令见 `planning/reliability-v4-guard-inputs.md`。它将四安全、三登记、R0与12/16开发证据及实际宿主容量合并为逐槽准入；没有修改原runner/飞行/评价源，也没有执行正式槽。以下“尚无守护入口”等语句保留为发现缺口时的历史描述；实际正式执行必须使用新 `run-one`，不能直接用裸runner批跑。现成registrar的三项组装入口见顶部更新，真实输入仍须完成。

## 实际依赖顺序

1. 最终飞行源稳定，四包构建、实际 module/ament 隔离和必要检查完成；在相同飞行源、权重、PX4 runtime、Gazebo libraries、渲染和协议下完成两类 clean 预检、canonical seed004 两类六组 **12 核心格**、独立 **4 歧义安全槽**、两类八条件 **16 扩展格**。保留每个原终态；开发只用非 1000–1009 种子。
2. 仅从该 canonical12 计划的 `person_stage1_velocity_seed004`、`car_stage1_velocity_seed004` 两个具名完整槽各导出一次实际 arrays 与 online/native/truth sidecars，再计算候选 R0。不得用 clean20s、另名 car45 诊断、旧版本或较好结果替代。
3. 审核候选工程门和四法参数；准备独立最终执行根 `FINAL_ROOT`，固定真实结果存储路径。原开发冻结根保持不变。先在最终根登记 core 的数值 `navigation_acceptance`，保留 extension 的相同实验设计。最终根的飞行、评价、权重及 runtime 映射必须与实际开发证据相符。
4. 在最终根建立**只作源码/门限 target snapshot、绝不执行**的 core 与 extension PROBE 计划；用 gate CLI 引用实际开发计划，分别组装 12 格与 16 格 gate。独立四安全证据另作强制前置条件，不能由这两个 gate 代替。
5. extension 协议写入 `REGISTERED`、真实 UTC 和真实 16 格 gate binding；core 协议也明确登记，且两者此后不再改动。先创建不可变 120 槽 core FORMAL plan，再创建绑定它的 160 槽 EXTENSION_FORMAL plan。
6. **此时才有四法登记所需的正式 core plan 路径、文件 SHA、plan digest。** 据此补齐四法全部参数与实际定标/源文件绑定，写入 `REGISTERED` 和 UTC，计算 `configuration_sha256`，验证。仍不得启动任何正式飞行。
7. 对三份最终登记、两个正式计划、两个开发 gate、四安全汇总、定标和源码/环境/权重映射作最终封存；通过宿主真实容量和单槽临时空间硬门，才逐槽启动 280 唯一尝试。四法登记时间须早于首个正式槽，尤其全部20条 stage1_velocity 记录。

“三份 REGISTERED → 再创建所有正式 plan”不能严格按字面实现：四法配置反向绑定正式 core plan。正确顺序是先固定数值和实验选择，再生成未执行正式 plan，补齐四法绑定，最后统一封存并允许飞行。这不需要先消费留出数据。

## 已有命令入口

以下是待执行模板，变量须由实际最终根和不可变计划填写；本次审查没有执行。全部重任务仍由唯一重窗口串行安排。环境包装须实际选择 Humble 最终根，不能让继承变量导入旧 build。`run_research_session.sh` 将临时目录和 ROS 日志放在该根的 `results/runtime`。

```bash
tracking_dev=/root/uav_tracking_fullplan_FINAL_DEV
tracking_dev_core="$tracking_dev/results/ACTUAL_CANONICAL12/plan.json"
tracking_dev_extension="$tracking_dev/results/ACTUAL_EXTENSION16/plan.json"
tracking_final=/root/uav_tracking_fullplan_FINAL_ROOT
tracking_tag=reliability_v4_FINAL_TAG
tracking_calibration="$tracking_dev/results/${tracking_tag}_development_calibration"
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$tracking_dev/scripts/humble22_env.sh"
```

开发导出以实际计划内 `trials[].directory` 为准，不凭目录名字猜测。创建全新导出目录，不能重用或覆盖旧产物；两次 export 会真实读包，应各仅做一次。开发导出不传正式 `--registration` / `--slot-id`。

```bash
tracking_person_trial="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(next(t["directory"] for t in p["trials"] if t["id"]=="person_stage1_velocity_seed004"))' "$tracking_dev_core")"
tracking_car_trial="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(next(t["directory"] for t in p["trials"] if t["id"]=="car_stage1_velocity_seed004"))' "$tracking_dev_core")"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_person_trial" \
  --output "$tracking_calibration/person_export"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_car_trial" \
  --output "$tracking_calibration/car_export"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/calibrate_estimator_replay_v4.py" \
  --plan "$tracking_dev_core" \
  --person-arrays "$tracking_calibration/person_export/arrays.json" \
  --car-arrays "$tracking_calibration/car_export/arrays.json" \
  --output "$tracking_calibration/R0_candidate.json"
```

calibrator 要求完整两类六组 seed004 PROBE 定义，且两个具名槽已有终态、`execution_status=COMPLETED`、`infrastructure_stop=false`、`flight_exit_code=0`。原终态允许因未登记门而是 EVALUATION_PENDING；它不要求篡改原终态为 PASS。定标只取完整 FOLLOW→Clock 尾的独立几何有效 `R_geometry`，保留融合拒绝、去重和排除原因，不平均 `R_pose`，不读目标真值拟合。均值最小特征值须严格大于 1e-12，无隐式 jitter。

完成最终根准备、core 数值登记之后，建立两个**不运行**的 target snapshot。下述 `plan --probe` 只创建定义，不消耗开发或正式种子。`tracking_final` 与两个 output 及所有 trial 名必须全新。

```bash
export HUMBLE22_PROJECT_ROOT="$tracking_final"
source "$tracking_final/scripts/humble22_env.sh"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" plan \
  --frozen-root "$tracking_final" --probe --seeds 4 \
  --output "results/${tracking_tag}_gate_target_core" \
  --prefix "${tracking_tag}_gate_target_core" --wall-timeout 300
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" plan \
  --frozen-root "$tracking_final" --probe --extensions --seeds 4 \
  --output "results/${tracking_tag}_gate_target_extension" \
  --prefix "${tracking_tag}_gate_target_extension" --wall-timeout 300
tracking_core_gate="$tracking_final/results/${tracking_tag}_core_gate.json"
tracking_extension_gate="$tracking_final/results/${tracking_tag}_extension_gate.json"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_final/results/${tracking_tag}_gate_target_core/plan.json" \
  --probe-plan "$tracking_dev_core" --output "$tracking_core_gate"
tracking_extension_cutoff="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_final/results/${tracking_tag}_gate_target_extension/plan.json" \
  --probe-plan "$tracking_dev_extension" \
  --registration-utc "$tracking_extension_cutoff" --output "$tracking_extension_gate"
```

extension cutoff 必须严格晚于全部实际16开发终态，且不晚于当前时刻；秒级刚好相等时应等下一秒再取值。它只是 gate 的临时验证 cutoff，**不是协议登记**。gate CLI 不写 REGISTERED。需要多份实际开发计划时可重复 `--probe-plan`，但每份计划的**全部**槽都会保留，不能从含基础设施失败的计划中只挑成功槽。

core gate 会用最终 target 的 `navigation_acceptance` 对原完整报告重新作纯文件判决；不需要仅为“原 EVALUATION_PENDING → 新登记门”重新运行 evaluator 或重飞。extension gate 允许明确列出的压力算法 FAIL，保存准确 `known_algorithm_failures`，但原生起飞、源钟、录制闭合和长丢失悬停/重选安全缺证不能充作 readiness。

extension 登记完成后，下面两个现成 plan 命令只冻结定义、不启动飞行。160 扩展通过 `--reference-plan` 绑定实际120 core，不能省略。

```bash
tracking_formal_core="$tracking_final/results/${tracking_tag}_core/plan.json"
tracking_formal_extension="$tracking_final/results/${tracking_tag}_extension/plan.json"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" plan \
  --frozen-root "$tracking_final" --formal --probe-gate "$tracking_core_gate" \
  --output "results/${tracking_tag}_core" --prefix "${tracking_tag}_core" --wall-timeout 300
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" plan \
  --frozen-root "$tracking_final" --formal --extensions --probe-gate "$tracking_core_gate" \
  --reference-plan "$tracking_formal_core" \
  --output "results/${tracking_tag}_extension" --prefix "${tracking_tag}_extension" --wall-timeout 300
```

不传 classes/groups/conditions/seeds 子集：formal 强制完整120/160。即使只先运行 core，最终根存在 extension 协议时，core formal 创建也会要求它已登记且真实16开发 gate 有效。

## 尚未接好的登记输入和硬门

现有registrar CLI负责安全汇总、四法配置和最终封存，不自动生成core/extension协议的登记或正式计划。后两项仍须在新的最终根显式生成并验证，至少完成下表；不得发明不存在的 `register` 子命令。根内原开发协议不能就地改写。

| 登记/绑定 | 精确字段与验证依赖 |
| --- | --- |
| core | 顶层 `status=REGISTERED`、实际登记UTC和证据来源；`navigation_acceptance.status=REGISTERED`；独立[工程要求决策](reliability-v4-engineering-requirements-decision-20261030.md)已采纳 `maximum_base_link_distance_rmse_m=1.0`、`maximum_base_link_height_rmse_m=0.40`、`minimum_valid_state_coverage=0.80`、`minimum_truth_coverage=0.99`、`minimum_physical_identity_coverage=0.80`、`require_final_window_settled=true`。`validate_navigation_gates`只核登记标记、数值域和布尔，需求来源文件SHA与实际登记UTC须另外核实；原3s稳定定义和安全门不改。数值已登记不等于顶层协议/正式准入已登记 |
| extension | `status=REGISTERED`、`registration_utc`、`development_readiness={path,sha256,evidence}`；evidence 为实际16格 gate 对象。UTC须晚于16开发终态且早于正式 core `created_utc` 与每条正式飞行。不可只填 PASS 布尔值 |
| 四法 calibration | 把实际 R0 candidate 的 `candidate_parameters` 逐项写入 `calibration`，置其 `status=REGISTERED`；保留禁止用留出数据定参的标记。同步更新 implementation_status 的真实说明，不能保留“参数未登记”同时声称完成 |
| 四法正式绑定 | `freeze_requirements.final_engineering_plan_path/file_sha256/digest` 来自实际120 core；这里的 `flight_source_hashes` 要写 **完整 `core_plan.source_hashes`**，不是 `run_reliability_v4.flight_source_hashes()` 的过滤子集；`model_hashes`用实际 plan值；runtime map 恰为 `px4_runtime_manifest_sha256`、`magnetic_library_registration_sha256` |
| 四法代码绑定 | `offline_replay_source_hashes` 覆盖 `replay_comparison.SOURCE_FILES`；`evaluation_source_hashes` 至少覆盖全部 `EXPORT_SOURCE_FILES`，且值与实际最终源一致；不要因为 core/models/kalman 同时属于飞行和离线依赖而漏登 |
| 四法定标证据 | `development_calibration_evidence.scope=DEVELOPMENT_ONLY`、真实 `artifact_hashes`；同时明确实际候选文件、两个具名槽、计划、arrays/三个sidecar和小录制证据的文件映射。现有 config validator 只查该 hash map 的格式，registrar 必须实际核对文件与候选 provenance，不能把任意64位字符串当证据 |
| 四法封口 | `registered_estimator_parameters={sha256:canonical_sha256(calibration)}`；`registration.registered_utc`；最后设置 `registration.configuration_sha256=configuration_digest(config)`。执行 `validate_registered_config(config)` 与 `verify_registration_artifacts(config,source_root=FINAL_ROOT)`，且登记UTC早于第一条正式飞行 |
| 四条安全 | 按 `reliability-v4-ambiguity-execution.md` 的两类×两情形真实原命令、退出码、source/native、闭合归档、实际歧义/禁止换目标、5.2s独立物理尾速证据组装独立不可变汇总，绑定最终 flight/model/runtime。当前 core/extension `validate_probe_gate` **没有读取这四条**，需要外层正式启动守护显式拒绝缺失或非PASS |
| 容量 | 见下节；当前 runner 和现有 Humble16 serial driver **均没有容量硬门**。`measure_humble16_completed_storage.py` 仅事后统计；不能当成 run 前准入 |

最终根准备/构建与最终整体封存是两个步骤：三份 planning JSON 不属于 runner 的 `source_hashes()` 扫描目录，但总 freeze manifest 可能包含 planning。须在最终登记和两个正式计划全部就绪后生成最终总清单；不能先封存草案、后悄悄更改却继续声称总清单未变。算法源码若再变，gate 绑定会不匹配，须保留旧证据并重新安排前瞻开发；纯登记变化不要求再次飞同一开发矩阵。

## 280 总容量和每槽临时裕量

已知问题：原 D 盘实际可用约164GiB而旧 cleanlike 外推为162–182GiB；100条 depth_noise/depth_holes/dropout/latency/combined 正式槽会同时录原和fault RGB-D，主动云台也可能放大录制。WSL的虚拟 ext4 空闲不能当成宿主物理空闲；其 vhdx 也位于 D。既有3.2GiB单槽临时峰不是全部故障条件的上界。必须先用最终12+16各格真实文件大小完成预算，再决定实际结果卷，不能把不足的预算解释成足够。

正式启动前需生成独立容量证据，至少包含：采样UTC、Windows各实际卷的可用 bytes、results symlink真实路径、WSL vhdx实际宿主卷、ext4逻辑可用量、开发每格完整持久化 bytes、归档/解包临时峰、剩余开发/新freeze和材料预算、采用的显式增长裕量及其理由。容量测量可用文件 stat 和宿主卷查询，不必重hash或解包；但压缩大小未知的工况不能用clean值默默填充。

预算按12核心格和16扩展格分别计算 `10 * 每格单次完整持久化预算`，保留全部280槽，不用成功数缩分母。持久化预算须包含 bag、telemetry、逐帧sidecar、日志和新增正式评价/四法arrays；20条四法导出与12条视频、检测审核、报告、runtime日志不能遗漏或重复计入。只有一个开发样本的“每格预算”并非统计上界，须显式保守加量并逐槽更新；不把一次最大值称为已证明的上界。

对每个实际物理卷分别要求：

`physical_free >= remaining_persistent_budget_on_volume + remaining_build_and_delivery_budget_on_volume + max(8 GiB, declared_simultaneous_temporary_peak_on_volume)`

如果results卷和vhdx宿主卷相同，按卷聚合一次，包含二者合计增长；若分盘，分别保证数据卷和vhdx宿主卷的临时与增长空间。还须满足 ext4 自身逻辑容量，但不能用它替代宿主容量。若估计临时峰超过8GiB，保留实际更大值；8GiB是最低可用临时裕量，不是最大允许临时文件尺寸。旧失败、包和冻结源不回收；任何新盘路径必须在正式 plan 创建前固定，不能运行中移动或改symlink。

建议用**外层独立守护**接在正式 `run` 之前，不改冻结飞行代码：先绑定两个正式计划、四法登记和四安全汇总并核验UTC，再核验本次容量；通过才调用 `run --max-new-trials 1`。每槽后做一次轻量文件大小与宿主卷重新采样、扣减剩余预算、再决定下一条PENDING。容量不足应在 `.started.json` 创建之前拒绝启动，保留待执行槽。当前尚无这个守护入口；不可直接把下面的裸 run 复制为无人值守280批跑。

```bash
# 只有外层正式登记/安全/容量守护PASS后，才能逐次调用：
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" run \
  --plan "$tracking_formal_core" --max-new-trials 1
# 120核心所有既定槽尝试完成、无未解决基础设施停止之后，再处理160扩展：
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/run_reliability_v4.py" run \
  --plan "$tracking_formal_extension" --max-new-trials 1
```

非零飞行/基础设施故障停止；恢复只允许带与原全部 `infrastructure_stop` 终态record SHA一致的真实 `--infrastructure-resolution`，不重试原槽。普通算法FAIL保留并按既定规则继续PENDING。run退出0只代表没有调度/基础设施停止，不代表所有工程PASS。

## 可避免的重复重任务与必须保留的检查

- 原 EVALUATION_PENDING 仅由尚未登记数值引起时，直接gate重判既有报告；不要为了换标签再读包、重飞或覆盖终态。最终同源证据已由新矩阵生成时，不再批量重评旧15。
- 定标只需预定两条velocity实际export各一次；calibrator仅数组/审计文件，不重读bag。20条正式四法比较复用正式core stage1_velocity，不新增80条或60条闭环飞行。
- 四安全专项与16扩展各有独立目的，不能拿12核心替代，也不增加正式280分母；不为每个登记target PROBE实际起飞。
- 新最终根若只是登记/存储固定且实现映射逐项相同，实际开发证据可经现有gate引用，不重飞完整矩阵。新根ROS build仍须证明import/ament隔离；最终选择的必要全套检查集中一次，不反复做相同全套。
- gate/plan/run当前会按既有合同多次hash源/小评价文件，`read_slots()`还会验证已记录json/jsonl/log等证据，可能产生明显累计IO；本审查不绕过、不关闭这些检查，也不把裸`status`称为免费操作。外层容量统计只读stat，避免额外遍历hash全部旧包。
- 四法正式导出须保留真实export/online/native/truth审计和文件绑定；不能为了减轻IO改用fixture或只读原数值摘要。正式数组导出失败仍保留该计划槽的缺失原因；完整20槽输入manifest必须列所有ID，缺失填null，不能只列成功录制。

完成280原终态后，先按固定20槽导出并登记全部缺证，再调用现有 `run_estimator_replay_v4.py run --configuration FINAL_REGISTERED_REPLAY_JSON --inputs-manifest COMPLETE20_JSON --output NEW_DIRECTORY`。其结果是同一实现轨迹/测量条件下的四法离线比较，不把它称为四法闭环因果优势。最终统计、检测审核、12条事先固定视频、图表和Word/PDF仍是后续真实执行项，本文件不声称已完成。
