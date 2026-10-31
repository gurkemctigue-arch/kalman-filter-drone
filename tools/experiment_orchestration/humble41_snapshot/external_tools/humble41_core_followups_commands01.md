# Humble41 已启动核心批次与后续证据链命令单 01

2026-10-31。本单由现存 40 版命令单、38 版正式链工作单、41 版外置工具及项目现有 CLI 静态整理。编写本单没有运行 WSL、describe、构建、测试、计划、登记、测量、导出、准入或飞行。它不修改冻结源、参数、数值门、既有执行入口或原结果。

## 1. 已启动的 core41：只记录快照，不重复启动

root 已真实启动同源 core12。启动快照为：monitor 工具 session **16926**，bridge 工具 session **35694**；这些 session 编号不是操作系统 PID。Windows producer PID **3996**，creation token **`windows_filetime:134379087186078613`**。首个原槽 `person_stage1_velocity_seed004` 的 started UTC 是 **`2026-10-31T08:26:46Z`**。

已读 monitor 快照为：任务 `humble41_core12_driver01`，Windows monitor PID 12028，token `windows_filetime:134379087184637955`，开始 `2026-10-31T08:25:18.611651+00:00`；该快照 heartbeat `2026-10-31T08:29:28.708595+00:00`，`finished_utc` 与 `returncode` 均为 null。这里只证明该时刻尚无 monitor 终态，不表示阅读本文时仍在运行，也不表示任何槽已 PASS。

本单不提供再次执行 plan-core、run-core、monitor 或 bridge 的命令。不要另开仿真、重发 core run、重启现有桥或复用旧 monitor 输出。查看进度使用 root 已启动的只读通道：

- 页面：`D:/基于yolo和卡尔曼滤波/results/project_progress/humble41_core01/index.html`。
- 原事件：`D:/WSL/UAVHumble22-validation/humble41_core_events01/events.jsonl`。
- 完整结果：原 plan、每个原 slot terminal、原执行 driver 及 source/observer/录包/工程评价证据。

事件桥不读 bag、不重算工程结论、不补造终态。12 分母不因中断或未尝试而缩小。最终进度可在 producer/bridge 真实结束后由 root 用既有 snapshot 更新，不能替代完整原证据核验。

旧40原批次保留 **3 PASS / 1 INFRA / 8 PENDING**；第四次尝试涉及 postflight D 盘 I/O observer staleness。旧失败不得重评为 PASS，不得将旧成功槽拼入41。41 不要求再跑独立单汽车探针。

## 2. 当前真实来源、工具身份和原产物

下表的 canonical 是工具清单摘要，文件 SHA 是原文件字节摘要，两者不能互换。未来文件的摘要不在本单中预填。

| 项目 | 当前真实值 |
| --- | --- |
| 主源码提交 | `8d542aff7827fded5b371971795796ce751a17aa` |
| 冻结开发根 | `/root/uav_tracking_fullplan_v4_humble41` |
| Windows results | `D:/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble41` |
| 外置工具根 | `/mnt/d/WSL/UAVHumble22-validation`（Windows 为 `D:/WSL/UAVHumble22-validation`） |
| source review | `reviewed_freeze_review_humble41_01.json` |
| source review 文件 SHA | `c112dca912301f7d2f79a6bc113dd21592c285f1c1cacb4a21511f22b34d50b9` |
| 独立 source/runtime helper canonical | `044ab32510e89c9da462040c5ff2391840b92ed6efd6dbda18fd218e6cd55686` |
| core matrix canonical | `8c9241e5f9ba7a54988b27d0f016e40d52ece37b8c9c85de410cb24463361cf3` |
| `matrix_runner41.py` 文件 SHA | `1e748d97f4c5687d53447af3acbe4506072279c063e6e77b31b262fe76df3ced` |
| safety canonical | `4b2600def87b15d2c3bbc0fd2279aee55e14eaaef1c18e048f87b48cba3d09fd` |
| `safety_runner41.py` 文件 SHA | `68f0b5567daccb4e27c08ba2d28a82e53dc90793d12e884415e9c0d48ab7854f` |
| extension canonical | `5303228b39c9e1a24254f912760832a9deceefac7e2b873d667f9e0c980ad72d` |
| `extension_runner41.py` 文件 SHA | `1408f38574b581cf0b187e1423a1fc680df2fd5b1c3368cc1fdcb8f2f04b29e7` |
| storage helper canonical | `d7fe68f92c9f95023e848888750ae2fd9ee58f1b5063f6e9cb34129da9a069e5` |
| 原安全 tail 文件 SHA，保持不变 | `05d1d11b6357db83a9805fc96f013e01c1c7741d109d6c10501e497215c2b612` |
| native owner tools canonical | `e558bf367038a2bb3530d7e5a8ea3e3fae7eb84ac19d02acedecc7c5c2be3ea3` |
| `local_runtime_observer41.py` 文件 SHA | `2f1348d862525777800df823780a269ef235b0df8d96b9ec378dc61c2be99914` |
| native frozen collector 文件 SHA | `f174ec21ebf962f156d76f8d35f802eebf318163555815527a3e2227b914f180` |
| event bridge41 canonical | `43dcc5b70ee26957545c5f84f5543fab3b19117db608c0d6fbbfcfba40064753` |
| 既有 monitor helper 文件 SHA | `759136d0eda40bb3a61c9e30e0272e1f6b8810b351dbe4c75dc17db5951bfd98` |
| build validation summary 文件 SHA | `d84ca882ccc440b33a8019e3ab0a8b86b68b00da8cac67f1092c0f2535954924` |
| core final contract | 外置根下 `matrix_runner41_contract_core_final01.json` |
| core final contract 文件 SHA | `054031d0146b3dc7fa2ebe9698bc3bea4d0223098b8ebbf18b10659e967a9e73` |
| core 原 plan 文件 SHA | `38aa57fddd8476fd124554775fb70f63dcc0af893a9fbb914f6439a89d9a614b` |
| core 原 plan 内部 `plan_sha256` | `a29d1a32e0d5dcbba1bd3d7663bc99000f69284cab72fe05c8ae4ae8ed1bc057` |

原 core plan：`ROOT41/results/reliability_v4_humble41_probe01_seed004_matrix/plan.json`。原执行 driver：同一 plan 目录下 `observed_driver01/execution_terminal.json`。原 plan driver：`ROOT41/results/freeze_validation/matrix_runner41_core_plan_driver01/execution_terminal.json`。`ROOT41` 在本单是位置说明，实际命令用下面的 `tracking41_root`。

root 已完成实际冷构建/full validation、native owner Linux 验证以及同源 **no-SITL pressure PASS** 后才创建 core41。它们是基础设施证据，不是 core 算法全通过的结果。现存独审回执包括：

| 外置回执 | 文件 SHA |
| --- | --- |
| `humble41_core_runner_independent01.json` | `47fa09ba5f6796396ff08f2ea2af5de1aaa3e04675c3ca43e5710fb57f7871b7` |
| `humble41_safety_independent01.json` | `d98b2c4a2d54184c2beaa376db749163cf0b48ab09e32f8d3694aafe3c6f2a5e` |
| `humble41_extension_storage_independent01.json` | `b509f9b034d99643e87a17f60de09ee5ae46e310f09231ff3d58ea935eec818f` |
| `humble41_events_bridge_independent01.json` | `69e1520909868cd7d604edd832c1e06dacd73bec12d437b1a37ce140ab15bb11` |

extension/storage 独审状态为 `NO_BLOCKING_STATIC_FINDING_NOT_ACTUAL_EXTENSION_OR_CAPACITY_ADMISSION`；核读 Linux 27+23 测试全 PASS、0 skip。工具测试与静态审查没有生成安全4、扩展16、存储测量或正式飞行结果。

### 既有 owner 的完整闭合要求

41 外置执行器使用 `owner.make_observer(directory, root, archive_wall_budget_s=1800.)`。原外层 driver 保存实际 `observer._finished` 为 `observer_owner_terminal`；后续读取此完整原结果调用 `owner.validate_observer_root(actual_owner_finish_result, directory, root)`，传入 None 会拒绝。

只拿 D 盘 `observer_driver/execution_terminal.json` 不构成 owner 闭合；该复制阶段文件为 `COPY_VERIFIED_PENDING_OWNER_CLOSURE`、healthy false。native live 日志在私有 tmpfs 中采集，先停 native 再归档，保留本地原证据；freshness10s、session7200s、rotation5400s、archive1800s 均保持。不能因复制目录存在就声称源钟、owner、清理都健康。

### 保持冻结的工程条件

使用 UAVHumble22：Ubuntu22.04 / ROS2 Humble / Gazebo Harmonic；PX4 根 `/root/uav_humble22/PX4-Autopilot-v4mag`，桥接 overlay `/root/uav_humble22/ros_gz_shutdown_A01_ws`，Python `/root/uav_humble22/venv/bin/python`。不得继承 Jazzy 或旧冻结根环境。

75s 原任务、RTF0.125、flight wall1000s、adapter50Hz、控制/监督20Hz、推理上限10Hz 不变。person 为 YOLO11n320、2线程、距5m；car 为 train20_04 YOLO11m640、4线程、距9m；far 格 person7m/car12m。car exclusive measurement、surface recovery、supported birth 保持 true，person 对应能力保持隐式 off/false。

距离 RMSE≤1m、高度≤0.4m、导航覆盖≥0.80、真值覆盖≥0.99、物理身份覆盖≥0.80、原末端持续稳定与新鲜度条件均保留。无完整 ReID，不以 Gazebo 真值在线帮助关联。

## 3. 后续 Bash 公共变量

以下供 root 在实际 core 批次关闭、机器空闲、对应证据满足后于 UAVHumble22 中逐段调用，不是一键脚本。新 shell 须重新设置。来源发生改变必须核实新审查绑定，不能只更新命令中的 SHA 绕过原独审。

```bash
tracking41_external=/mnt/d/WSL/UAVHumble22-validation
tracking41_root=/root/uav_tracking_fullplan_v4_humble41
tracking41_review="$tracking41_external/reviewed_freeze_review_humble41_01.json"
tracking41_review_sha=c112dca912301f7d2f79a6bc113dd21592c285f1c1cacb4a21511f22b34d50b9
tracking41_safety_tools=4b2600def87b15d2c3bbc0fd2279aee55e14eaaef1c18e048f87b48cba3d09fd
tracking41_safety_python=68f0b5567daccb4e27c08ba2d28a82e53dc90793d12e884415e9c0d48ab7854f
tracking41_extension_tools=5303228b39c9e1a24254f912760832a9deceefac7e2b873d667f9e0c980ad72d
tracking41_storage_tools=d7fe68f92c9f95023e848888750ae2fd9ee58f1b5063f6e9cb34129da9a069e5
```

## 4. core12 原始全部 PASS 后：安全登记与四安全

先核12原格全部工程 PASS、同源 source/build、完整 driver/owner/observer、源钟、原生起飞、录包归档、清理无残留。core 普通算法 FAIL 也阻止本步；保留失败进行另行诊断，不拼旧槽、不改分母、不替换成功尾段。

### 4.1 只登记，不飞行

```bash
/bin/bash "$tracking41_external/safety_runner41.sh" register \
  --review "$tracking41_review" --review-sha256 "$tracking41_review_sha" \
  --reviewed-tools-sha256 "$tracking41_safety_tools" \
  --frozen-root "$tracking41_root"
```

将实际创建 `ROOT41/results/reliability_v4_humble41_safety_seed004_audit/registry.json`，登记四条原 argv、源、core 与安全 tail 绑定。既有 audit/试验目录拒绝覆盖和重试。该未来 registry 的创建 UTC 和文件 SHA 尚未在本单中填写。

### 4.2 核对真实 registry 后执行四安全

root 独立核对真实 registry 的全 argv、类别、模式、source/core/tool/tail、新目录与顺序，然后从同一原件取文件 SHA：

```bash
tracking41_registry="$tracking41_root/results/reliability_v4_humble41_safety_seed004_audit/registry.json"
tracking41_registry_sha=$(sha256sum "$tracking41_registry" | cut -d ' ' -f 1)
/bin/bash "$tracking41_external/safety_runner41.sh" run \
  --review "$tracking41_review" --review-sha256 "$tracking41_review_sha" \
  --reviewed-tools-sha256 "$tracking41_safety_tools" \
  --frozen-root "$tracking41_root" \
  --registry-sha256 "$tracking41_registry_sha"
```

CLI 没有 `--registry` 路径参数或 `--contract`；它读取上面固定 audit 的原 registry。直接试验由此入口持有唯一外层 SITL 锁。四个原 case 依次为 person `auto_unique_multi35s`、person `locked_ambiguity50s`、car `auto_unique_multi35s`、car `locked_ambiguity50s`。

必须真实保存 `execution_terminal.json`、`slots_facts.json`、`development_validation_summary.json`、`development_guard_validation.json` 与完整原证据。四安全原 PASS **且**完整原 frozen guard PASS 后才推进扩展；不得将算法/guard FAIL 重标为 PASS。

## 5. 安全及原 guard 全通过后：扩展16

### 5.1 创建原16格与 pending 契约

```bash
/bin/bash "$tracking41_external/extension_runner41.sh" plan-extension \
  --review "$tracking41_review" --review-sha256 "$tracking41_review_sha" \
  --reviewed-tools-sha256 "$tracking41_extension_tools" \
  --frozen-root "$tracking41_root" \
  --safety-tools-sha256 "$tracking41_safety_tools" \
  --safety-python-sha256 "$tracking41_safety_python"
```

未来位置：原 plan 为 `ROOT41/results/reliability_v4_humble41_extensions_probe_seed004_matrix/plan.json`；plan driver 为 `ROOT41/results/freeze_validation/extension_runner41_plan_driver01/execution_terminal.json`；pending 为外置根下 `extension_runner41_contract_extension_pending01.json`。

root 独审真实两类×八条件、seed004、16全 PENDING、source/build/tool/core/safety、原 argv、plan terminal、实际 owner 终态及清理后，另存 `extension_runner41_contract_extension_final01.json`，保留 pending。final status 必须为 `FINAL_MATRIX_NORMAL_RUNNER_DEVELOPMENT_INDEPENDENTLY_REVIEWED`，真实绑定和 false 权限字段均保留。CLI 不自动发布 final；本单没有声称该文件已经创建，不预填其 SHA，不加入 `zero_attempt_recovery`。

### 5.2 实际 final 独审后执行原16格

```bash
tracking41_extension_contract="$tracking41_external/extension_runner41_contract_extension_final01.json"
tracking41_extension_contract_sha=$(sha256sum "$tracking41_extension_contract" | cut -d ' ' -f 1)
/bin/bash "$tracking41_external/extension_runner41.sh" run-extension \
  --review "$tracking41_review" --review-sha256 "$tracking41_review_sha" \
  --reviewed-tools-sha256 "$tracking41_extension_tools" \
  --frozen-root "$tracking41_root" \
  --safety-tools-sha256 "$tracking41_safety_tools" \
  --safety-python-sha256 "$tracking41_safety_python" \
  --contract "$tracking41_extension_contract" \
  --contract-sha256 "$tracking41_extension_contract_sha"
```

先 person 后 car，每类原顺序：`depth_noise`、`depth_holes`、`dropout`、`latency`、`combined`、`speed_changes_velocity`、`speed_changes_position`、`far_distance`。seed004、75s、阈值和原 argv 不变。每次 normal runner 调用只允许 `max_new_trials=1`，原 normal runner 持锁，不叠加第二个外层 SITL 锁。

原 run driver 位于计划目录 `observed_driver01/execution_terminal.json`。原健康闭合的算法 FAIL/UNKNOWN 计入完整分母；基础设施、来源、录包、observer 或清理失败停止后续，不自动重试/续跑。退出0不代表16格算法全 PASS。完整16原健康终态和全归档证据才可用于完整28格统计。

## 6. 完整12+16原闭合后：stat28

在空闲窗口调用：

```bash
/bin/bash "$tracking41_external/run_humble41_storage_measure01.sh" measure \
  --review "$tracking41_review" --review-sha256 "$tracking41_review_sha" \
  --reviewed-helpers-sha256 "$tracking41_storage_tools" \
  --matrix-tools-sha256 "$tracking41_extension_tools" \
  --safety-tools-sha256 "$tracking41_safety_tools" \
  --safety-python-sha256 "$tracking41_safety_python"
```

`--matrix-tools-sha256` 必须传 extension canonical `530322...`，因为实际导入 extension41；不能传 core canonical `8c9241...`。CLI 没有 `--frozen-root` 或 `--output`。固定输出为 `ROOT41/results/freeze_validation/artifact_storage41_01`：28条以原 trial 命名的 receipt 与 `complete28.json`。

工具核原全部12+16和安全前置证据，再只 stat 文件及具名小报告；不读/hash/decode bag 负载，不宣称测得未来临时峰值，不进行容量准入。失败/未知格保留；缺格、短录制、源钟/起飞/归档/owner/来源缺证不能解释为普通算法失败。本单没有 future receipt、complete28、inventory、budget 的 SHA 或容量值。

## 7. 两条具名 velocity 真实导出与 R0 候选

这一步可由 root 在 core 关闭、两条具名录制原完整终态及来源/归档核实后安排独立空闲重窗口，不必等待扩展16结束。export 真正读取 bag，与 stat28 不同，不与仿真或其他重任务并发。

只接受 canonical12 原目录：

- `ROOT41/results/reliability_v4_humble41_probe01_person_stage1_velocity_seed004`。
- `ROOT41/results/reliability_v4_humble41_probe01_car_stage1_velocity_seed004`。

不能用 crossing 探针、position 模式、clean20、旧来源或成功尾段替代。以下所有 `NEW_*`/`ACTUAL_*` 都是模板占位符，必须先换成真实独占新路径；不可原样执行或覆盖原件：

```bash
/bin/bash "$tracking41_root/scripts/run_research_session.sh" \
  "$tracking41_root/scripts/export_estimator_replay_v4.py" \
  "$tracking41_root/results/reliability_v4_humble41_probe01_person_stage1_velocity_seed004" \
  --output NEW_PERSON_EXPORT
/bin/bash "$tracking41_root/scripts/run_research_session.sh" \
  "$tracking41_root/scripts/export_estimator_replay_v4.py" \
  "$tracking41_root/results/reliability_v4_humble41_probe01_car_stage1_velocity_seed004" \
  --output NEW_CAR_EXPORT
/bin/bash "$tracking41_root/scripts/run_research_session.sh" \
  "$tracking41_root/scripts/calibrate_estimator_replay_v4.py" \
  --plan "$tracking41_root/results/reliability_v4_humble41_probe01_seed004_matrix/plan.json" \
  --person-arrays NEW_PERSON_EXPORT/arrays.json \
  --car-arrays NEW_CAR_EXPORT/arrays.json \
  --output NEW_R0_CANDIDATE.json
```

真实 export 输出 `arrays.json`、`online_equivalence.json`、`native_state_audit.json`、`truth_alignment.json`。必须核原源/录制绑定、online 等价、native 状态、真值对齐与数值复现。源脚本核具名原完整终态、`execution_status COMPLETED`、无基础设施停止、`flight_exit_code 0` 等原证据；不能用工具通过标签代替实际校验。

定标仍是 `CANDIDATE_NOT_REGISTERED`；本单没有声称导出或定标已经执行。后续正式 export 才使用现有 `--registration` 和 `--slot-id` 两参数绑定真实正式录制。

## 8. 实际容量与独立最终根

后续章节均是现有 API 的模板。`ACTUAL_*` 表示实际原件路径/数值/摘要，`NEW_*` 表示实际独占新输出；它们既不是已存在结果，也不是获准绕过前置条件的文字。以下脚本必须通过对应真实 Humble 根的 `scripts/run_research_session.sh` 进入隔离环境。

### 8.1 物理卷 inventory 与280预算

```bash
/bin/bash "$tracking41_root/scripts/run_research_session.sh" \
  "$tracking41_root/tools/reliability_v4_guard.py" storage-probe \
  --distribution UAVHumble22 --mount /mnt/d --output NEW_INVENTORY.json
/bin/bash "$tracking41_root/scripts/run_research_session.sh" \
  "$tracking41_root/tools/reliability_v4_storage_budget.py" \
  --core-development-plan ACTUAL_SOURCE41_CORE12_PLAN \
  --extension-development-plan ACTUAL_SOURCE41_EXTENSION16_PLAN \
  --size-evidence-dir ACTUAL_STAT28_DIRECTORY \
  --physical-inventory NEW_INVENTORY.json \
  --assumptions ACTUAL_ASSUMPTIONS.json \
  --output NEW_BUDGET.json
```

实际 inventory 须核主机注册表对应的 VHD 所在物理卷；不能把 `/root` 虚拟 free 当宿主容量。如果 VHD 不在 D，须盘点真实卷；results/VHD 同卷只聚合一次，不虚增空间。budget 默认从开发 plan 的 `results_root` 推导结果卷；若最终结果换卷，先做显式实际映射及必要最小审查适配，不能将 D 预算冒用于另一卷。

每格10次，共280；双 RGB-D 故障格必须用对应原格实测尺寸。显式 assumptions 含5类交付预算 `offline_replay20`、`videos12`、`detection_audit`、`figures_documents`、`runtime_logs`，以及剩余构建、增长和余量。临时界按三 raw、两 compressed 加余量，reserve 至少 `max(8GiB, temporary peak bound)`；这是上界，不是已经观察到的未来峰值。budget 为 preview/non-admission，原 guard 每槽前后还要重查实际物理容量。

### 8.2 新最终执行根

只有实际容量路径确定后，准备独立 `ACTUAL_FINAL_ROOT` 与固定最终 results 位置。保留 dev41 全部原件；飞行、算法、评价、权重、runtime/library 映射须与实际开发证据相等，只有明确允许的离线呈现例外。四个 ROS 包须在新根真实构建并核 module/ament 隔离，不复制旧 build/install 冒充构建。最终根路径、最终源清单、构建回执和 SHA 均由真实产物决定，本文不预填。

## 9. 最终 target、gates、安全汇总与两工程登记

先在真实最终根固定已采纳数值，core/extension 顶层仍保持草案。创建不飞行的完整两类 target；core 默认6组，extension 默认8条件，不传缩小范围的选项：

```bash
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/run_reliability_v4.py plan \
  --frozen-root ACTUAL_FINAL_ROOT --output NEW_TARGET_CORE_DIRECTORY \
  --prefix NEW_TARGET_CORE_PREFIX --probe --seeds 4
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/run_reliability_v4.py plan \
  --frozen-root ACTUAL_FINAL_ROOT --output NEW_TARGET_EXTENSION_DIRECTORY \
  --prefix NEW_TARGET_EXTENSION_PREFIX --probe --extensions --seeds 4
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/build_reliability_v4_probe_gate.py \
  --target-plan ACTUAL_FINAL_CORE_TARGET_PLAN \
  --probe-plan ACTUAL_SOURCE41_CORE12_PLAN --output NEW_CORE_GATE.json
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/build_reliability_v4_probe_gate.py \
  --target-plan ACTUAL_FINAL_EXTENSION_TARGET_PLAN \
  --probe-plan ACTUAL_SOURCE41_EXTENSION16_PLAN \
  --registration-utc ACTUAL_CUTOFF_UTC_STRICTLY_AFTER_ALL16_TERMINALS \
  --output NEW_EXTENSION_GATE.json
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/tools/reliability_v4_register.py safety-summary \
  --target-plan ACTUAL_FINAL_CORE_TARGET_PLAN --core-gate NEW_CORE_GATE.json \
  --facts ACTUAL_SOURCE41_SAFETY_FACTS --output-directory NEW_SAFETY_ASSEMBLY
```

extension cutoff 必须是实际产生、严格晚于16终态的当前/过去 UTC，不填未来时间，也不是 protocol 的登记时间。`safety-summary` 在改 canonical 工程协议前执行，生成 `safety_summary_candidate.json`，不自动发布 canonical。

root 保存三份 planning 原字节及预期 SHA，明确发布 core、extension 为真实 REGISTERED/实际 UTC，并绑定实际 gate、四安全和来源。三份 canonical 路径为 `planning/reliability-v4-preregistration.json`、`planning/reliability-v4-extension-preregistration.json`、`planning/reliability-v4-estimator-replay-preregistration.json`。现有 registrar 没有“publish engineering core protocol” CLI；本文不发明该命令，不覆盖既有 REGISTERED。

## 10. 正式120/160定义、replay登记、最终封存

### 10.1 两正式定义，不飞行

两工程登记完成后，使用同一最终根的现有 runner：

```bash
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/run_reliability_v4.py plan \
  --frozen-root ACTUAL_FINAL_ROOT --output NEW_FORMAL_CORE_DIRECTORY \
  --prefix NEW_FORMAL_CORE_PREFIX --formal --probe-gate ACTUAL_CORE_GATE
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/run_reliability_v4.py plan \
  --frozen-root ACTUAL_FINAL_ROOT --output NEW_FORMAL_EXTENSION_DIRECTORY \
  --prefix NEW_FORMAL_EXTENSION_PREFIX --formal --extensions \
  --probe-gate ACTUAL_EXTENSION_GATE --reference-plan ACTUAL_FORMAL120_PLAN
```

默认正式种子1000–1009，完整 core120 + extension160，全部280 PENDING。extension 的 `--reference-plan` 绑定真实 core120；不向 extension 传 core `--groups`。本步仅定义，不等于准入或首次飞行。

### 10.2 replay-config 必须先于全部正式首飞

```bash
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/tools/reliability_v4_register.py replay-config \
  --core-plan ACTUAL_FORMAL120_PLAN --candidate ACTUAL_R0_CANDIDATE \
  --output-directory NEW_REPLAY_ASSEMBLY
```

产生 `replay_configuration_candidate.json`；它绑定真实 FORMAL120 路径/SHA/digest，因此必须在120定义后。root 核真实两导出、全部 sidecar、参数、来源，保留草案原字节/原 SHA 后发布实际 canonical replay。不能重写既有 REGISTERED，也不能先飞再补登记。

### 10.3 最终源清单与真实 seal

三登记和两正式定义齐备后，才封完整 source/planning manifest，保留旧 preparation manifest。组装真实 request：恰含 `schema_version:1`、`kind:RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST`、`final_root`、`plans`（core/extension）、`registrations`（core/extension/replay）、`calibration`、`safety`、`state_directory`、完整实际 `storage`。所有绑定均为实际解析路径及文件 SHA；guard state 为最终 results 内独立未创建目录。调用方不能预填 `created_utc`、`tool`、`manifest_sha256`，这些由 registrar 生成。

```bash
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/tools/reliability_v4_register.py seal \
  --request ACTUAL_COMPLETE_ADMISSION_REQUEST.json \
  --output-directory NEW_SEAL_ASSEMBLY
```

原 guard 须实际核完整证据、三登记、两正式计划全280 PENDING、最终源和真实物理容量，才能发布 `final_admission.json`。这不是正式结果，不得用命令单、工具测试、候选标签或单次开发 PASS 替代准入。

## 11. 正式280执行及 native-owner 适配边界

现有原 authority API 是 `tools/reliability_v4_guard.py run-one --manifest ACTUAL_SEALED_MANIFEST`。它一次只取原首个 PENDING，每槽前后重新检查容量并保留原失败/未知；基础设施/RUNNING 停止须先真实诊断，不能删标记、改终态、换 seed 或自动重跑。

新的 `formal41_guard_adapter01.py/.sh` 和测试**正在准备**：计划在不改原 guard、选槽、锁、准入与 argv 的条件下外包 native owner。当前不能将它的候选文件、尚未独审的 canonical、未来最终 driver/进度页当作已验证入口或真实结果。待作者/独审/Linux 验证真实闭合后，root 才绑定实际 adapter canonical 与实际 sealed manifest 文件 SHA，形成最终命令。本文不预填这些值，也不启动正式槽。

现存 `formal280_serial_guard01.py` 只串行调用原 guard，`--guard-command` 必须为最后一项，自动追加 `run-one --manifest PATH`。新 adapter 的衔接尚不能假定已经完成；不能直接将候选 CLI 塞入旧 serializer 并声称已兼容。现有 usage 是 `formal280_serial_guard01_usage.md`。执行与只读进度应由 root 根据最终真实绑定发布，避免高频调用会重 hash 历史工件的 runner `status` 或 guard `check`。

0 PENDING 只表示原计划消费完，不等于280 PASS或整个项目通过。所有原失败、缺证、中断和基础设施停止须保留，报告算法结果与工程证据完整性时明确分开。

## 12. 正式20×4离线比较及最终交付

从 core120 两类 velocity seed1000–1009 的20条真实录制导出，使用 `export_estimator_replay_v4.py ACTUAL_TRIAL --output NEW_EXPORT --registration ACTUAL_REGISTERED_REPLAY_CONFIG --slot-id ACTUAL_SLOT_ID`。完整20输入 manifest 包含所有预定 ID，缺失/失败条目明确保留，不能挑成功样本。无需新增80次飞行。

```bash
/bin/bash ACTUAL_FINAL_ROOT/scripts/run_research_session.sh \
  ACTUAL_FINAL_ROOT/scripts/run_estimator_replay_v4.py run \
  --configuration ACTUAL_CANONICAL_REGISTERED_REPLAY_CONFIG \
  --inputs-manifest ACTUAL_COMPLETE20_INPUT_MANIFEST \
  --output NEW_REPLAY80_DIRECTORY
```

比较 raw、EMA、fixedKF、geometry_adaptiveKF，共80单元；每类10个配对 seed，95% bootstrap10000次，帧不作为独立试验。结论限定于同测量/同轨迹估计比较，不预设 adaptive KF 全指标优越。

最后仍需实际正式报告与统计、身份/检测评价、原始结果表、图表、论文材料、演示和统一交付更新。工具测试、core12、stat28或280终态登记中的任何单项，都不能独自表示项目全部验收完成。本单没有宣布安全4、扩展16、stat28、正式280、20×4或整体验收已经完成。
