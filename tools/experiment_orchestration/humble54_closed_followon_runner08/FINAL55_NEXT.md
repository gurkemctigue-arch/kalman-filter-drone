# runner08 之后的 final55 执行索引

**当前状态更正（2026-11-03）：旧 owner06、observer07、trigger09 已真实以 exit 2 停止，runner08 未启动。旧 runner08 必须取得旧07的三个真实 exit 0及其完整闭合，当前条件不成立，禁止直接调用08或把旧失败改写为成功。** 新 collector07 仅续原计划剩余5槽；必须等待其实际退出、16槽原件复核和新闭合审计后，才可使用 [新直接测量准备入口](../humble54_closed_measurement01/README.md)复用原08的28格测量、具名 velocity exports、R0 与完整280槽预算。该入口仍 `PRODUCTION_ENABLED=False`、`REGISTERED_INPUTS={}`，没有预登记未来结果。下文涉及旧07 full profile、旧08结果路径及 candidate04 旧chain接口的内容仅保留为原技术索引，须由真实新闭合和后续已审适配替代，不能直接执行；原120+160=280范围、容量预留、正式验收条件全部保留。

本卡只整理已存在的源码、CLI 和顺序；未启动 WSL、读取 bag/模型、登记任何未来证据或修改 06/07/08/09。以下均为未来动作，`ACTUAL_*` 只能来自当时真实原件。已有完整卡无需重写：

- [离线叠加、navigation28 与 sensor4](../../../planning/reliability-v4-final55-offline-overlay-20261103.md)，其中 probe01 示例须由下述已审 candidate04 的 probe02 固定绑定替代。
- [normal registration 原卡](../final55_registration_card01/execution_card.original.md)：safety assembly、三项 publication、120/160 定义、seal、source sidecar 的完整命令及精确请求 schema。
- [formal55 supplementary 原卡](../formal55_supplementary01/post_admission_execution_card.original.md)：actual Linux describe、identity、contract、verify、原 durable54/serial54 的完整 schema 与命令。
- [两种事前补充协议及 replay 检查点](../../../planning/reliability-v4-supplementary-replay-prerequisites-20261103.md)：补上旧卡未列出的物理身份协议。

## 1. 入口原件与 staging 阻断

先取得 durable07 的实际完整 full16 closure/profile/saved audit，以及 runner08 的成功 terminal、28 格测量、实际物理 inventory、两份具名 velocity export 的独立 sidecar、R0 candidate 和正容量 budget。runner08 成功标识为 `COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION`；单独 rc0 不代替终态、每项输入绑定和正预算。

本次采用的 budget 是 `/root/uav_tracking_fullplan_v4_humble54/results/full280_storage_budget_probe02_followon08/budget.json`，R0 为 `.../results/reliability_v4_humble54_development_calibration_probe02_08/R0_candidate.json`；不得换回 followon05 的结果。容量必须完整 28 cells/280 slots、原假设 `bc0ef3a6…60b049`、全部 logical/physical `fits_declared_* is True`。不足或未知即停止，不降低预留。

现有 staging 驱动是 [candidate04](../../staging/final55_profile03_driver_candidate04/stage_profile02.py)，本卡核对的原 SHA 为 `082ed8b6fc229cc1d188f27e4b896a4864695dfbcaf65c57fe06fcf9d28e4f7f`。它仍为 `PRODUCTION_ENABLED=False`、`REGISTERED_INPUTS={}`；必须由 root 在实际原件齐备后登记 `full_chain_profile` 与 `budget` 两个原始 path/SHA，审查并记录修改后的实际源码 SHA，才可运行。不能回退 profile01、check_preparation 或旧 owner 单段 closure。

```bash
# 仅在上述实际登记、源审查和原任务退出之后。
python3 -B /mnt/d/基于yolo和卡尔曼滤波/tools/staging/final55_profile03_driver_candidate04/stage_profile02.py --execute
```

原驱动持有既有 SITL 锁并核 native idle；固定生成 `/root/uav_tracking_final55_stage_probe02_05` 和 `/mnt/d/WSL/UAVHumble22-validation/final55_stage_probe02_05`。这些 `_05` 是驱动的既有路径，不代表使用旧 followon05 的 budget。新路径有任何冲突即拒绝；不覆盖旧尝试。保留其 admission、base outcome、driver outcome、完整基线与10文件叠加/descriptor实测 map。

## 2. cold、未飞 target、导航28与输入4

从实际成功 staging 自身调用原入口，不能从 frozen54 的 results symlink 直接复制：

```bash
/bin/bash /root/uav_tracking_final55_stage_probe02_05/tools/diagnostics/reliability54_build01/prepare_and_validate.sh \
  /root/uav_tracking_fullplan_v4_final55 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_final55 \
  /root/uav_tracking_fullplan_v4_humble54
```

要求实际 cold colcon、import/ament 隔离、完整套件、native validation 成功，保存本次原始 DRAFT `source_before/source_after/frozen_actual` 和 supplement。叠加后的实际308/185 map按本次基线核验，flight277、六模型、五runtime与开发证据一致；不得继续用旧308/185全部字节不变的断言。cold 后不补代码、测试、descriptor或文档。

按 normal 原卡第4节，用 final55 的 `run_reliability_v4.py plan --probe --seeds 4`，以及同参数加 `--extensions`，建立 core12/extension16 target。两 target 永远只作定义，全部 PENDING、不执行；三项顶层协议仍 DRAFT，数值 navigation registration 保持原值。

```bash
# 变量均为实际 canonical 路径；core_dev=原canonical12，ext_dev=本次probe02完整16。
"$tracking_python" -B "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_core_target" --probe-plan "$tracking_core_dev" --probe-plan "$tracking_ext_dev" \
  --register-navigation-reevaluations --navigation-report-basename "$tracking_new_navigation_basename" \
  --output "$tracking_external_nav_registration"
```

选择28槽全部尚不存在的统一新 JSON basename；依 `planned_evaluations[].command` 原样逐条串行执行，保存真实 argv/UTC/整数 exit0/日志和新report SHA。随后按 builder 的 `read_navigation_reevaluation_manifest()` 原 schema形成独立完成清单：kind `RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATIONS`、实际 prospective registration 绑定、sources/UTC、28唯一槽及实际 execution。现有 builder 只有登记和校验入口，没有“执行28次”或“自动生成完成清单”的 CLI；不能虚构命令或完成记录。任一门都重核全部28，结构完整的性能 FAIL 保留。

sensor4 必须来自同一 probe02 的 person/car × dropout/combined 四个固定原槽。使用合同固定的真实 extractor CLI `extract_short_window.py --source-root ... --plan ... --slot-id ... --output ...` 分别提取新目录，再由实际 AI/人独立阅图，按 `sensor_input_interruption_v1/evidence.py` 的 `evaluate_development_manifest(manifest_path, contract)` 全4槽重核。旧 probe01 的行人图不能充作 probe02；旧具名 person-only executor硬编码 probe01，不能直接运行。四槽 manifest、原图/review、合同均须真实存在且外置，不能用四个 PASS 标签替代。

```bash
bash "$tracking_final/scripts/run_research_session.sh" "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_core_target" --probe-plan "$tracking_core_dev" \
  --navigation-reevaluation-manifest "$tracking_nav_complete" --output "$tracking_core_gate"
bash "$tracking_final/scripts/run_research_session.sh" "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_extension_target" --probe-plan "$tracking_ext_dev" \
  --navigation-reevaluation-manifest "$tracking_nav_complete" --sensor-input-evidence-manifest "$tracking_sensor4" \
  --registration-utc "$tracking_extension_cutoff" --output "$tracking_extension_gate"
```

cutoff须为实际 UTC、晚于原16槽全部完成且不在未来。sensor参数只给 extension；不混用旧六 gimbal override。缺证、安全失败、core gate未就绪均阻断后续登记。

## 3. 严格沿用 normal registration 的顺序

依 normal 原卡第4—9节顺次完成，不能跳步：

1. 固定 `/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_register.py safety-summary`，绑定实际 core target/core gate 与原 safety03 完整4/4 PASS facts，先产出真实 safety assembly。
2. 外置已审 `reliability_v4_publication.py protocols --request ... --request-sha256 ... --output-directory ...`，发布 core/extension。本卡核对源码仍为 `8e1c903e…64cd6`；请求精确字段按原卡，所有输入使用本次实际原件。
3. 用 final55 runner `plan --formal --probe-gate CORE_GATE` 建完整120；用 `plan --formal --extensions --probe-gate CORE_GATE --reference-plan CORE120` 建完整160。**两个命令均传 core gate**；extension gate由已发布 readiness 独立绑定。无子集，全部280保持PENDING。
4. 固定 audit registrar `replay-config --core-plan CORE120 --candidate ACTUAL_RUNNER08_R0 --output-directory ...`；再用 publication `replay` 发布候选原字节。仍要求正式槽全未开始。
5. 完成下一节两份补充协议，再按原卡 `seal`、固定 guard `check`、publication `source-sidecar`。seal请求storage取08实际budget的 `storage`，不加自造字段；state目录不预创建。保留 cold DRAFT map，最终sidecar仅允许原卡的三项planning规定变化。

## 4. 首个正式 START 前：两份补充协议都必须实有

在三项 canonical 登记齐、实际120/160计划齐、所有280零START/零trial产物时，独占串行建立下列两项。可先于 seal，不得等到数据出现后补登。

```bash
bash "$tracking_final/scripts/run_research_session.sh" \
  /mnt/d/WSL/UAVHumble22-validation/prospective_detection_dataset.py protocol \
  --core-plan "$tracking_core_formal" --core-sha256 "$tracking_core_file_sha" \
  --extension-plan "$tracking_extension_formal" --extension-sha256 "$tracking_extension_file_sha" \
  --output "$tracking_detection_protocol"
python3 -B /mnt/d/基于yolo和卡尔曼滤波/tools/offline_evaluation/physical_recovery_v1/physical_recovery.py protocol \
  --core-plan "$tracking_core_formal" --core-sha256 "$tracking_core_file_sha" \
  --output-dir "$tracking_physical_protocol_directory"
```

上述 producer 在执行时仍须核实际源/pin。detection沿原卡已审两个外置源，固定12个 seed1000来源与完整280分母，失败来源不换seed。physical本卡核对源码 SHA 为 `f25327c03509aba6c0c5ec2d8358d65d1ca2e22da63e4a45076e23e99a52182c`，产出 `physical_recovery_protocol.json`，固定40原多目标槽/80恢复机会，不新增飞行。其原 API `validate_protocol()` 用于复核来源、规则和UTC；该工具没有 `verify` CLI。两协议输出均外置、全新，不写入已cold final树。

**原 guard和formal55 supplement不会自动消费 physical protocol。** 首formal前必须独立核其真实path/SHA、producer、core计划绑定、实际UTC、40/80与all120未开始声明，并把它及producer实际源作为原 durable request现有 `input_files` 的附加小文件绑定；不能给 supplement contract添加不存在的physical字段，也不能把detection `verify`通过当作physical已完成。这只补齐启动所用输入身份，语义复核仍由原physical API与主流程承担。

## 5. sealed admission 后只复用原正式 owner

完成真实 seal/check/source sidecar后，逐项按 formal55 supplementary 原卡执行 actual Linux formal48/serial54/新55 describe → actual adapter identity → 新55 contract → `formal_supplementary_preflight.sh verify` → 原 durable54 launch request/launch。使用新55 canonical `b8f75ecc…7b0580`、原formal48 canonical `dbc9358d…f2d5a`及同一固定外置 audit guard；不沿用旧54 supplement合同，不修改adapter，不新增owner/trigger/包装器。

launch request的 `input_files` 需枚举原卡所有源、describe、合同、plans、detection协议/selection/review/helpers、guard与实际sidecar，另加上节physical协议和源。实际ACK/registry/持有句柄证据齐备后才能报告正式开始。首次 supplement先写audit，再 exec原adapter，最后原guard创建 initial-full280 admission并启首槽；禁止绕过supplement直接run-one。

## 尚需真实产生并绑定的结果

| 边界 | 必须是实际原件，准备文件不能替代 |
|---|---|
| full16→08→stage | 07实际closure/full profile/saved audit；08成功terminal、28尺寸/inventory/export sidecars/R0/正budget；candidate04实际注册源码及两个输入pins |
| stage→cold | staging实际admission/outcomes、baseline/overlay/descriptor map；55自己的cold/freezer/source maps/full suite/native supplement |
| cold→readiness | 两个PENDING target；事前navigation28登记、28实际执行/新报告/完成manifest；probe02真实sensor4提取/review/manifest；实际两gate与safety assembly |
| readiness→formal定义 | protocols publication outcome；120/160实际plans；replay assembly/publication outcome；真实detection及physical protocols |
| 定义→首START | admission request/seal/check、最终source sidecar、Linux describe/identity/contract/verify、完整input_files、原durable request/实际ACK/registry |

任何实际输入漂移、路径冲突、未闭合子进程、非正容量、缺证或安全门拒绝均停在对应边界，保留原结果。完成owner链、预算、构建或登记中的任一项，都不等于工程全部通过或正式280已执行。
