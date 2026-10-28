# v3 正式研究结束后的交付命令

本文记录 v3 的后续执行顺序与路径。2026-10-27 主版最近全套 Windows 验证完成 604 项（599 PASS、5 SKIP），进程退出 0；针对当前补丁的指标补表 12 项、结果报告 22 项及 Word 来源门 14 项检查也均通过。独立 16 项守卫夹具此前为 13/13 通过，尚未完成独立 16 项真实飞行验证。验证范围与源码 SHA 见 [V3_DELIVERY_VALIDATION.md](V3_DELIVERY_VALIDATION.md)。正在运行的正式飞行必须先结束；不得把测试、bag 后处理、绘图或视频转码与正式飞行并行执行。最终结果以原始清单为准，FAIL、INCOMPLETE 和 INTERRUPTED 均保留，不同名重试、不覆盖失败。

## 1. 本轮已核对的路径

| 项目 | 本轮取值 |
| --- | --- |
| 冻结 Linux 源码根 | `/root/uav_tracking_fullplan_v3` |
| 冻结 results 的 D 盘目录 | `/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v3` |
| 主计划 prefix | `fullplan_v3` |
| 主计划 output 参数的原始文本 | `results/full_plan_research_v3` |
| 主计划 canonical SHA-256 | `58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28` |
| 正式环境清单 | `results/environment_manifest_before_formal.json`，相对于冻结源码根 |
| 独立 16 项 prefix（后续新建） | `extended_engineering_v3` |
| 独立 16 项清单目录（后续新建） | `results/extended_engineering_v3_matrix`，相对于冻结源码根 |
| 独立 16 项补充后处理目录（后续新建） | `results/full_plan_supplement_v3`，相对于冻结源码根 |

v3 已保存的 `plan.json` 中，阶段二三的 output/report 是相对路径。恢复飞行和运行主离线阶段时，`--output` 必须继续传入 `results/full_plan_research_v3`；改传绝对路径会改变重建计划的摘要，恢复检查应当拒绝。现有 `run_full_plan_windows.ps1` 拼接的是绝对 output，不能直接用于这份 v3 计划的恢复。本页统一使用冻结根自身的 `run_research_session.sh`；它会切到正确工作目录，并把 TMPDIR、ROS 日志放在 D 盘 results/runtime 中。

以下 bash 命令在同一个 WSL shell 中执行。变量仅用于本任务，不改全局环境：

```bash
tracking_frozen='/root/uav_tracking_fullplan_v3'
tracking_main='/mnt/d/基于yolo和卡尔曼滤波'
tracking_results="$tracking_frozen/results"
tracking_study="$tracking_results/full_plan_research_v3"
tracking_engineering="$tracking_results/extended_engineering_v3_matrix"
tracking_supplement="$tracking_results/full_plan_supplement_v3"
```

所有主计划运行仍使用冻结源码。后续新增的报告、补充后处理与 cleanup 工具从 Windows 主副本调用，不复制进冻结根、不重新构建冻结根。

## 2. 主 166 次飞行和主离线阶段

原 100 条阶段一记录为 66 PASS、34 FAIL（velocity 51/80、position 15/20）。2026-10-27 首个真实守卫槽 `s2_person_crossing_locked_seed000` 为 PASS，守卫返回 0、`stop=false` 且无错误。后续会话推进至 114/166 终态、剩 52 PENDING 时，`s2_car_crossing_locked_seed003` 因 supervisor `ABORTED` 和遥测过期触发守卫停止，录制进程正常退出，原槽保留 FAIL。此处是检查点；后续计数及是否恢复以清单和独立诊断为准，本页不按每个飞行刷新。不能把所有原台账 FAIL 归为算法失败。

`fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08` 原评价器发生 SQLite error 11，未生成可评分 JSON。已完成的[独立审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)发现：原压缩帧未正常结束；独立 libzstd 输出的数据库完整性为 `ok`、消息数与元数据一致；原生 ROS reader 输出少了末尾 128 KiB，重现 SQLite error 11。原生输出是独立输出的逐字节前缀。原始记录与正式 FAIL 结论保持原样，独立衍生数据库没有替代正式评价；不能把该错误归为跟踪算法失败或断言原始 SQLite 内容损坏。

主版 `run_guarded_full_plan.py` 已经通过纯夹具和首个真实槽验证；它调用原冻结 master，每次严格 `--resume --stop-after 1`，保持原计划及 166 次分母。详见[主守卫说明](GUARDED_FULLPLAN_V3_CONTINUATION.md)。下列只读命令校验原始输出文本与计划 SHA：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_guarded_full_plan.py" \
  --frozen-root "$tracking_frozen" \
  --study-output results/full_plan_research_v3 \
  --expected-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28
```

已有真实会话审计为 `results/fullplan_v3_guarded_continuation_v1`（首槽）与 `results/fullplan_v3_guarded_continuation_v2`（后续，因真实基础设施停止而退出 2）。不能同时启动另一会话；必须先完成针对该停止的诊断。未来确有 PENDING 需要继续且环境空闲时，使用全新、从未存在的审计目录，例如：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_guarded_full_plan.py" \
  --frozen-root "$tracking_frozen" \
  --study-output results/full_plan_research_v3 \
  --expected-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28 \
  --audit-output "$tracking_main/results/fullplan_v3_guarded_continuation_v3" \
  --execute
```

首次工程检查可另加 `--max-new-flights 1`；默认逐槽继续全部 PENDING。守卫保留正常完成的负面性能结果；遇到基础设施异常、缺失报告或非预期退出则停在下一槽之前。不要改动冻结源码，也不要在会话持有哈希期间修改主守卫、分类器或其空闲进程助手。

主 166 个飞行槽全部进入终态，PX4、Gazebo、ROS launch/bag 进程停止且研究写锁释放后，串行处理已有录制。这里不使用 `--allow-partial-offline`：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  scripts/run_full_plan_research.py \
  --phase offline --prefix fullplan_v3 \
  --output results/full_plan_research_v3 --resume
```

该阶段对阶段二非 auto_unique 录制先进行独立物理身份评价，再运行在线状态与跟随瞬态评价；auto_unique 无选定物理任务时明确记为不适用。缺 bag、无法读取及失败也必须获得对应终态，不能删除这些槽位。

离线入口结束后，重新生成主研究统计（包含 bootstrap，仍不与飞行并行）：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  scripts/run_full_plan_research.py \
  --phase summarize --prefix fullplan_v3 \
  --output results/full_plan_research_v3
```

继续前检查 `summary.json` 的 166 个不同 trial 全为 PASS/FAIL/INCOMPLETE/INTERRUPTED、`all_flight_slots_terminal=true`、`all_offline_slots_attempted=true`，并逐项核对 `offline_manifest.json` 的 166 个任务名、计划 SHA 和终态。`all_flights_pass=false` 不意味着可以删掉失败；完整执行与全部通过是两个结论。

`s2_car_crossing_locked_seed003` 等基础设施提前停止记录可能没有原始阶段二 safety JSON。原主离线入口不会生成或读取这份缺失的安全评分，而是独立尝试物理身份、状态精度和瞬态评价，保留原飞行 FAIL；缺失的行为评分不能编造成可评分算法失败。离线可读、缺失及不完整情况依真实输出另列。

### 2.1 全 166 条独立失败分类

所有原计划槽终态、主离线和汇总完成且环境空闲后，从 Windows 主项目根生成一个全新的外部审计目录。此工具只读取既有小型 JSON，不执行 bag 解码或评价，不触发飞行与重试：

```powershell
python -B scripts/summarize_full_plan_failure_taxonomy.py `
  --root results/frozen_fullplan_v3 `
  --stage1-taxonomy results/stage1_failure_taxonomy_v3_100/failure_taxonomy.json `
  --output results/full_plan_failure_taxonomy_v3_166
```

最终快照不传 `--allow-partial` 或 `--trial`，应有 `is_final166=true`、准确 166 个名字、前后来源摘要一致。它只表示原始终态完整；报告缺失、`FAIL_OR_INCOMPLETE`、已报告或独立确认的基础设施异常分别保留，不强行转成算法失败。不能把先前单条 `stage2_car_crossing_seed000_saved_report_audit` 当作最终 166 次统计。工具边界、单条快照及验证状态见 [全 166 分类说明](V3_FULL166_FAILURE_TAXONOMY_GUIDE.md)。

## 3. 独立 16 项工程扩展

这些试验覆盖四项加减速、十项在线故障和两项较远距离。每条件仅一条独立工程飞行，不能并入主 166 的十次重复分母。正式主研究及主离线入口均已结束后，新建这份清单：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  scripts/run_extended_engineering.py \
  --prefix extended_engineering_v3 \
  --output results/extended_engineering_v3_matrix \
  --preregistration "$tracking_frozen/planning/online_estimator_preregistration.json" \
  --wall-timeout 300 --render-backend egl --plan-only
```

原冻结命令在这里仅用于 `--plan-only`；已有 manifest 不重新创建。实际飞行使用主版独立守卫。它只在主 166 飞行与主 166 离线槽均为真实终态时允许执行，验证主清单、summary 和原计划绑定，并在全程保护其 SHA。新守卫及其夹具须在空闲窗口通过验证，Windows 主项目根执行：

```powershell
python -B -m unittest discover -s tests -p test_guarded_engineering.py -v
```

通过后回到 WSL 做只读校验，再做单槽工程复核：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_guarded_engineering.py" \
  --frozen-root "$tracking_frozen" \
  --study-output results/full_plan_research_v3 \
  --expected-main-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28 \
  --engineering-output results/extended_engineering_v3_matrix
```

上一步只读验证通过后：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_guarded_engineering.py" \
  --frozen-root "$tracking_frozen" \
  --study-output results/full_plan_research_v3 \
  --expected-main-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28 \
  --engineering-output results/extended_engineering_v3_matrix \
  --audit-output "$tracking_main/results/extended_engineering_v3_guard_v1" \
  --max-new-flights 1 --execute
```

首槽经复核后，以全新 `extended_engineering_v3_guard_v2` 审计目录去掉 `--max-new-flights 1` 继续剩余 PENDING。守卫逐次调用原冻结 `run_extended_engineering.py --resume --stop-after 1`，不重试 PASS/FAIL/INTERRUPTED。原入口遇到任意历史失败都会返回 2，守卫将其与全清单实际终态核对；不能把这个历史失败退出码误当成本次基础设施异常。每个新槽仍需准确的报告、日志、returncode、运行参数和读取证据；详见[独立 16 项守卫说明](GUARDED_ENGINEERING_V3.md)。该工具只生成基础安全评价，在线状态与瞬态指标由下一节补充。

## 4. 主副本后处理工具的验证和独立 16 项补充

飞行期间不运行本节测试。本节夹具已包含在本次通过的全套验证中，它们不产生真实实验数据。以后若相关源码发生变化，在环境空闲时从 Windows 项目根执行相应回归检查：

```powershell
python -B -m unittest tests.test_full_plan_supplement tests.test_metric_supplement tests.test_full_plan_report tests.test_cleanup_probe
```

测试通过后，回到前述 WSL shell。以下入口是 Windows 主副本；实际 evaluator、anchor 和 ROS 环境仍来自冻结根。工具读取主 summary、主 plan、主 offline manifest 以及独立 16 manifest，并检查所有终态、任务名、源 SHA、写锁和空闲进程：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_full_plan_supplement.py" \
  --frozen-root "$tracking_frozen" \
  --summary "$tracking_study/summary.json" \
  --plan "$tracking_study/plan.json" \
  --offline-manifest "$tracking_study/offline_manifest.json" \
  --engineering-manifest "$tracking_engineering/manifest.json" \
  --output "$tracking_supplement" --plan-only
```

检查新 manifest 的 16 个 trial 绑定后，执行：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/run_full_plan_supplement.py" \
  --frozen-root "$tracking_frozen" \
  --summary "$tracking_study/summary.json" \
  --plan "$tracking_study/plan.json" \
  --offline-manifest "$tracking_study/offline_manifest.json" \
  --engineering-manifest "$tracking_engineering/manifest.json" \
  --output "$tracking_supplement" --resume
```

已有 evaluator 输出及半成品只核对并保留，不覆盖、不静默重试。补充目录必须是冻结 results 的单个直接子目录。16 个补充终态中允许保留 INCOMPLETE_EVIDENCE/INTERRUPTED，但不能宣称相应指标已经测得。

补充 manifest 保存主 summary 等输入文件的 SHA。完成后不要再次改写主 summary 或独立工程清单；如确需修订，保留原补充目录并用新目录生成新一版，随后使 cleanup 和交付报告绑定新路径。

## 5. 指标表和研究图

以下仍在 WSL shell 中串行执行。指标补充只读已保存的 JSON/派生 state JSONL，不读取 bag、不运行 YOLO。输出 JSON/Markdown/CSV 必须使用新文件名；任何同名输出已存在时会拒绝：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/build_metric_supplement.py" \
  --summary "$tracking_study/summary.json" \
  --plan "$tracking_study/plan.json" \
  --trial-root "$tracking_results" \
  --engineering-manifest "$tracking_engineering/manifest.json" \
  --include-state-frames \
  --output "$tracking_results/metric_supplement_v3.json"
```

`--include-state-frames` 只将已有 PREDICTED 状态与短快门请求/响应窗口相交；这不等于逐像素独立验证的渲染可见性。若缺侧车或参考，仍须报告缺失/覆盖率，不能填零。逐飞行 p95 的组均值也不是合并所有帧的 p95。

补表另提取已有短遮挡后恢复时间与原 track_id/target_uuid 连续性，按请求窗、已观察恢复、已知/未知身份和未恢复列出条件分母；它不提供独立物理身份或长时 ReID 认证。每组同时保留 `metric_evidence_status_counts`，最终报告据此将不适用和普通缺失分开。旧冻结 summary 的任务均值 ID Switch 没有排除空几何任务的 0；主要 ID Switch 结果采用补表中有帧/几何标签门控后的数值与有效/缺失分母。旧 summary 与绘图导出的 `flight_units.csv` 对应字段作为历史来源保留，不能未经说明替代新补表。

绘图器默认仍指向旧 v1，所以必须显式指定两个 v3 参数。它产出 PNG/PDF/SVG、逐飞行 CSV、配对区间 CSV 和输入 SHA 清单；不包括独立 16 的伪重复统计：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  reports/plot_full_plan_study.py \
  --summary "$tracking_study/summary.json" \
  --output "$tracking_results/research_figures_v3"
```

## 6. 浏览器验收页面和视频

先只索引本轮 v3，确保所有正式失败、缺证据和未完成项均可查看。历史结果可以另生成整项目页面，不能并入 v3 完成率：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/build_acceptance_dashboard.py" \
  --results-dir "$tracking_results" \
  --output "$tracking_results/验收总览_v3.html"
```

下面预先固定 seed000 的八条演示：阶段一行人/汽车、阶段二 crossing 行人/汽车、阶段三两类别 midpoint/active。它们是明确选出的说明案例，不是成功率样本；即使失败也不替换为更好 seed。脚本要求原始 `onboard.mp4`、`run_config.json`、`summary.json` 实际存在，缺失时停止并保留缺交付说明。

视频转码使用 ffmpeg/ffprobe，必须等全部飞行结束后再执行。交付目录必须不存在；输出 H.264 MP4，并验证帧数、尺寸、逐帧相对时间戳、时长和帧率，原视频不裁剪、不加速、不覆盖：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/build_browser_demos.py" \
  --trial "$tracking_results/fullplan_v3_online_estimators_person_velocity_adaptive_kf_seed00" \
  --trial "$tracking_results/fullplan_v3_online_estimators_car_velocity_adaptive_kf_seed00" \
  --trial "$tracking_results/fullplan_v3_stage23_s2_person_crossing_locked_seed000" \
  --trial "$tracking_results/fullplan_v3_stage23_s2_car_crossing_locked_seed000" \
  --trial "$tracking_results/fullplan_v3_stage23_s3_person_gimbal_midpoint_seed000" \
  --trial "$tracking_results/fullplan_v3_stage23_s3_person_gimbal_active_seed000" \
  --trial "$tracking_results/fullplan_v3_stage23_s3_car_gimbal_midpoint_seed000" \
  --trial "$tracking_results/fullplan_v3_stage23_s3_car_gimbal_active_seed000" \
  --acceptance "$tracking_results/验收总览_v3.html" \
  --output "$tracking_results/browser_demos_v3"
```

Windows 用户直接打开 `results/frozen_fullplan_v3/验收总览_v3.html` 和 `results/frozen_fullplan_v3/browser_demos_v3/index.html`。归档时保留本轮文件夹结构，不能只复制 HTML 而遗漏视频、JSON、图和原始 bag。

## 7. 最终中文结果报告

本工具从 Windows 主副本运行，读取冻结证据并产出 Markdown 和同名 `.sources.json`。以下八个视频链接只能在上节转码成功后传入。若某个实际缺失，应明确列作缺交付，不创建占位视频：

```bash
bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_main/scripts/build_full_plan_report.py" \
  --summary "$tracking_study/summary.json" \
  --plan "$tracking_study/plan.json" \
  --offline-manifest "$tracking_study/offline_manifest.json" \
  --supplement-manifest "$tracking_supplement/manifest.json" \
  --metric-supplement "$tracking_results/metric_supplement_v3.json" \
  --environment "$tracking_results/environment_manifest_before_formal.json" \
  --engineering-manifest "$tracking_engineering/manifest.json" \
  --engineering-summary "$tracking_engineering/summary.json" \
  --trial-root "$tracking_results" \
  --detection "$tracking_main/results/detection_research/detection_report.json" \
  --review "$tracking_main/results/detection_research/visual_review.json" \
  --evidence "$tracking_supplement/manifest.json" \
  --evidence "$tracking_results/metric_supplement_v3.json" \
  --evidence "$tracking_results/metric_supplement_v3.md" \
  --evidence "$tracking_results/metric_supplement_v3.csv" \
  --evidence "$tracking_results/research_figures_v3/manifest.json" \
  --evidence "$tracking_results/验收总览_v3.html" \
  --evidence "$tracking_results/browser_demos_v3/index.html" \
  --evidence "$tracking_results/browser_demos_v3/manifest.json" \
  --evidence "$tracking_main/docs/V3_FAILURE_DIAGNOSIS_DRAFT.md" \
  --evidence "$tracking_main/docs/V3_BAG_INFRASTRUCTURE_AUDIT.md" \
  --evidence "$tracking_main/docs/V3_STAGE1_FAILURE_TAXONOMY_100.md" \
  --evidence "$tracking_main/results/stage1_failure_taxonomy_v3_100/failure_taxonomy.json" \
  --evidence "$tracking_main/results/stage1_failure_taxonomy_v3_100/artifact_sha256_manifest.json" \
  --evidence "$tracking_main/docs/V3_FULL166_FAILURE_TAXONOMY_GUIDE.md" \
  --evidence "$tracking_main/results/full_plan_failure_taxonomy_v3_166/failure_taxonomy.json" \
  --evidence "$tracking_main/results/full_plan_failure_taxonomy_v3_166/failure_taxonomy.md" \
  --evidence "$tracking_main/docs/FULLPLAN_V3_DELIVERY_COMMANDS.md" \
  --video "$tracking_results/browser_demos_v3/demo_01.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_02.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_03.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_04.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_05.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_06.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_07.mp4" \
  --video "$tracking_results/browser_demos_v3/demo_08.mp4" \
  --output "$tracking_results/研究结果报告_v3.md"
```

报告自身不解码视频、不重算实验、不生成 Word。当前 `build_full_plan_report.py` 只接受 `.md`；不能改扩展名冒充 DOCX。最终完成标记还要求显式 `--offline-manifest`、`--supplement-manifest` 与 `--metric-supplement`：核对主计划 canonical SHA、准确 166 个离线终态、独立工程 16 及补充 16 个终态、两份计划和当前 summary/plan/offline/工程清单的来源 SHA；指标 JSON 还须绑定当前 summary/plan/工程清单，覆盖准确 166+16 任务及计划指标键。旧调用仍可生成明确未完成的快照，不能产生最终完成标记。完整分组指标、缺失/不适用及短恢复条件分母会嵌入正文；不只保留补表链接。

检测章直接引用已有 `reviewed_aggregate` 的合并 mAP 和类级 GT/TP/FP/FN 分母，不能用逐录制 AP 的平均值补造。检测报告中的 `review_file_sha256` 必须匹配当前审核清单原字节 SHA；同样的帧数不能证明相同帧ID。缺少或不匹配时不复报检测数值，并保持未完成。mAP 类别分母仅统计 GT 物体数大于 0 的类别；纯预测类别仍留在类表中。

完整阶段一分类另见 `V3_STAGE1_FAILURE_TAXONOMY_100.md` 及上列 JSON 与来源摘要：原 100 次为 66 个已评分 PASS、33 个已评分行为验收 FAIL、1 个已确认基础设施异常，证据不足/未知为 0。原台账仍为 66 PASS / 34 FAIL，完整执行分母仍为 100；若另报可评分行为验收结果，分母是 99，必须同时交代那 1 个不可评分基础设施异常。已分类只说明结果和证据状态，不能推断 33 次行为失败的共同深层根因。该分类范围是阶段一 100 条，不代表完整 166 条。

`V3_FAILURE_DIAGNOSIS_DRAFT.md` 是较早的代表性遥测诊断草稿：汇总扫描 80 条 velocity，深入检查少量指定 PASS/FAIL 记录；其机制结论仍只适用于明确列出的样本。car position seed08 的压缩帧未正常结束、原生 reader 尾部输出缺失与独立 libzstd 数据库完整性对照，引用已完成的 `V3_BAG_INFRASTRUCTURE_AUDIT.md` 及其机器报告；该记录未补写正式 JSON、未重飞，也未改判 PASS。最终报告保留所有原 FAIL，不把缺失评分当作零误差；后续阶段二、三的失败分型需独立纳入，不能从阶段一分类外推。

### 7.1 最终 Markdown 转 Word，再渲染 PDF 检查

已按本机安装的 docx skill（`<DOCX_SKILL_ROOT>/SKILL.md`）准备 `scripts/render_research_docx.cjs`。该脚本只负责排版，要求最终 MD 与同名 `.sources.json` 的 SHA 一致、`completion_contract_version=2`、`execution_ledger_complete=true`，并明确通过补充 16 项和指标补表完成校验。它再次读取五份当前台账与指标补表，共六份小 JSON，核对保存的大小/SHA；来源有变化时拒绝生成 Word。来源使用相对 MD 的路径，允许保持目录结构后从 Linux 转到 Windows；不能把未更新的旧完成标记当作最终凭据。它不因 FAIL 自动删除数据，也不把终态称作全部通过。输出为新的 DOCX 和同名 `.render.json`，拒绝覆盖原件。

Word 来源门已实际执行并通过 14 项检查，未打包真正的最终 DOCX。全部实验与后处理结束后，在 Windows 主项目根确认当时的语法和依赖；若源码没有变化，无需重复已经通过的门检查：

```powershell
node --check scripts/render_research_docx.cjs
node -e "require('docx')"
node tests/test_report_docx_gate.cjs
```

只有第二条实际报缺少 `docx` 模块时，才执行 `npm install --no-save --package-lock=false docx`，然后重查依赖；不预先安装。新增报告完成门的 22 项 Python 测试和 Word 来源门的 14 项检查已通过。相关源码改变时可用 `python -B -m unittest discover -s tests -p test_full_plan_report.py -v` 及上述 Node 门检查回归。最终真实数据通过完成门后，渲染真正的最终报告，显式追加六张已有正式研究图：

```powershell
node scripts/render_research_docx.cjs `
  --input results/frozen_fullplan_v3/研究结果报告_v3.md `
  --output results/frozen_fullplan_v3/研究结果报告_v3.docx `
  --figure results/frozen_fullplan_v3/research_figures_v3/flight_status.png `
  --figure results/frozen_fullplan_v3/research_figures_v3/stage1_recorded_outcomes.png `
  --figure results/frozen_fullplan_v3/research_figures_v3/stage1_paired_intervals.png `
  --figure results/frozen_fullplan_v3/research_figures_v3/stage2_physical_identity.png `
  --figure results/frozen_fullplan_v3/research_figures_v3/stage3_paired_intervals.png `
  --figure results/frozen_fullplan_v3/research_figures_v3/follow_transient_evidence.png
```

宽表使用 A4 横向分节，其余正文为 A4 纵向；Markdown 相对证据链接会按 DOCX 位置转换，图和源文档 SHA 写入 `.render.json`。现有计划书 DOCX/PDF不作修改。不能仅因脚本退出成功就判定版面通过。

回到 WSL shell，调用同一 skill 的 OOXML 检查和 LibreOffice helper。先把 `<DOCX_SKILL_ROOT>` 替换为 WSL 可访问的 skill 实际目录。新建 PDF/页面目录前确认它不存在；失败工件保留，修订后使用新名称：

```bash
tracking_docx_skill='<DOCX_SKILL_ROOT>'
test ! -e "$tracking_results/report_document_v3" || exit 2
mkdir -p "$tracking_results/report_document_v3/pages"

bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_docx_skill/scripts/office/validate.py" \
  "$tracking_results/研究结果报告_v3.docx"

bash "$tracking_frozen/scripts/run_research_session.sh" \
  "$tracking_docx_skill/scripts/office/soffice.py" \
  --headless --convert-to pdf \
  --outdir "$tracking_results/report_document_v3" \
  "$tracking_results/研究结果报告_v3.docx"

pdfinfo "$tracking_results/report_document_v3/研究结果报告_v3.pdf"
pdftoppm -jpeg -r 100 \
  "$tracking_results/report_document_v3/研究结果报告_v3.pdf" \
  "$tracking_results/report_document_v3/pages/page"
```

随后实际逐页查看渲染图片，重点检查中文缺字、宽表溢出、数字/单位/置信区间断行、标题孤行、图像裁切与分页，核对负结果、unknown、缺失数和研究边界仍在文中。用最终 PDF 的真实页数核对页面图片数；记录检查结论与文件 SHA，才算完成 Word/PDF 交付。当前渲染器的 `.render.json` 明确保留 `RENDER_AND_PAGE_INSPECTION_REQUIRED`，不会提前声称已检查。若安装路径或工具不可用，先补齐实际环境并记录，不跳过渲染检查。

## 8. 计划书、Word 和研究结论的剩余检查

仓库已有 `docs/最终版毕业设计计划书_三阶段修订版.docx`（44,770 bytes）和同名 PDF（388,150 bytes）。`docs/FINAL_PLAN.md` 与该 DOCX 的修改时刻均为 2026-10-27 01:40:49；对应生成器是 `scripts/create_final_plan_docx.py`，读取 `FINAL_PLAN.md`，默认名称仍是旧版无后缀 DOCX，可通过 `--output` 明确指定新名称。这里核对了文件存在、源 Markdown 和生成器，没有打开或重新渲染 Word，不能仅凭修改时刻认证版面或全文一致。

当前计划书源已写明实际 Ubuntu 24.04.1 / ROS 2 Jazzy / PX4 v1.17.0 / Gazebo Harmonic、166 次主研究及独立工程范围；它没有把 Ubuntu 22.04/Humble 声称为已验证。计划书作为设计文档已经有 Word 工件；v3 最终研究结果 DOCX 的渲染器现已准备，真实最终 Word/PDF 工件及逐页检查仍待本页前述步骤实际完成。不能把编写渲染器当作已完成交付。

论文结论须同时保留以下边界：

- 每类/方法重复以整次真实飞行为单位；主 166 和独立 16 分开，独立 16 每条件不是十次。
- 历史检测 Precision/Recall/AP 来自已复核静态子集，不能扩展为本轮全部多目标/遮挡准确率；历史汽车检测资源与正式资源不同，须注明。
- 在线状态误差参考可见表面锚点，不能声称物体中心绝对精度；控制距离/高度的模型原点统计和视觉锚点语义分开。
- 阶段二几何 HOTA/IDF1 需要按几何标签和可见性范围解释；unknown 和无新鲜检测留在物理身份机会分母。UUID 连续不等于物理身份全程正确。
- 重选确认是新的显式选框任务，不是长时 ReID 自动认回。完整 ReID 仍在首版范围外。
- 检测处理帧率、图像到命令延迟采用仿真时间；纯推理耗时采用墙钟。RTF=0.5 的仿真不能宣称墙钟实时或实机验证。
- 多目标加主动云台联合工程验证、清理修订后的探针和原始失败历史须单列；仅完成主 166 与独立 16 不能代替这些独立验收。

## 9. 正式完成后的 cleanup 独立验收

Windows 主副本的 `run_cleanup_probe.py` 已准备显式 v3 清单绑定；新增夹具已包含在本次通过的全套验证中，真实 cleanup 飞行探针仍未完成。就绪检查要求主飞行 166、主离线 166、独立 16、补充 16 全部终态，验证计划自身 SHA、任务名和补充保存的当前输入文件 SHA。终态允许负结果；这不认证全部通过。

全部研究与补充结束后，将经审查的清理修订同步到可变 `/root/uav_tracking_project`，核对源 SHA并通过针对性夹具后，才新建独立 cleanup 冻结根。当前明确的未来源码同步文件为 `scripts/run_stage1_trial.py`、`scripts/run_cleanup_probe.py`、`tests/test_trial_shutdown_signals.py`、`tests/test_cleanup_probe.py`、`tests/test_simulation_seed.py`（send_signal 替身兼容）、`uav_tracking/research_failures.py`、`tests/test_research_failures.py`、`docs/POST_FREEZE_SHUTDOWN_REVISION.md` 与 `docs/CLEANUP_ENGINEERING_PROBES.md`。若随后 guard 或审查改变范围，先更新该清单；当前不执行同步。准确审计约定见 [CLEANUP_ENGINEERING_PROBES.md](CLEANUP_ENGINEERING_PROBES.md)；不得同步进正式 v3 或历史冻结根：

```bash
bash /root/uav_tracking_project/scripts/freeze_full_plan_workspace.sh \
  /root/uav_tracking_fullplan_cleanup_v3 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_cleanup_v3
```

冻结脚本需要完成新根构建、导入路径隔离和全套测试。任一失败保留证据并停止，不复用已有失败根。新根创建成功后，依次运行就绪检查和两次真实探针，上一条执行及清理全部结束后才执行下一条：

```bash
cd /root/uav_tracking_fullplan_cleanup_v3

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage1 --prefix cleanup_v3 --check-ready \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage1 --prefix cleanup_v3 --execute \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage3_multi --prefix cleanup_v3 --execute \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json
```

阶段一准确 ROS 图为 8 个节点；阶段三多目标主动云台图为 9 个，必须逐节点核对停止标记后的 clean 退出、单次进程 SIGINT、无超时升级、无新观测残留、旧清单前后 SHA 不变。外层退出 0 或飞行 PASS 不能代替该证据。结果目录分别为 `cleanup_v3_stage1_person_seed00` 和 `cleanup_v3_stage3_multi_person_seed00`，审计在相邻 `_cleanup_audit/cleanup_report.json`。第一次有残留时第二次应拒绝，不能批量 kill 后冒充清理成功。

cleanup 新根的原始录制与审计单独归档。完成后可用 `build_acceptance_dashboard.py --additional-results-dir` 生成包含新根的另一个交付页，并在结果报告追加真实 cleanup 审计链接；不得改变正式研究原 summary 来消除已记录失败。
