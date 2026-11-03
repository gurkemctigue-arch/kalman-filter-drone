# extension16 期间的补充评价与 replay 接续检查点

2026-11-03。这里只读取 Windows 上的小源码、计划、terminal 和已保存组件回执，未运行 WSL、仿真、推理、bag、模型哈希或多分钟测试，未创建真实补充协议或登记。工作根、D 盘祖先及 planning/tools 的具名适用层级没有 AGENTS.md。本页是新说明，不改旧证据、旧执行卡或冻结根。

## 已有能力与具体缺项

| 项目 | 已有、无需重写 | 尚需真实完成 |
| --- | --- | --- |
| 补充检测 | `tools/offline_evaluation/prospective_detection_v1`；原47项及独审合计52项合成验证；producer canonical `0581776c…2fa3`；固定12条seed1000选源 | final55真实120/160计划产生后、任何正式START前创建实际 protocol；随后实际抽取、独立GT-only图像审核、推理、评价及verify-report |
| 正式 supplementary 前置接线 | 已有 `formal55_supplementary01`，修复固定外置guard路径；canonical `b8f75eccb143871130671a00ad5cf75fe0768e43bc46bb0a99c2586f207b0580`；Windows63项通过/230.991秒 | 实际sealed admission之后才可生成真实合同、绑定当前新工具及实际adapter，并核验实际原生串行接线；不能沿用旧54/42合同或其canonical冒充新55 |
| 物理身份恢复 | `physical_recovery_v1` 标准库工具；源码SHA `f25327c03509aba6c0c5ec2d8358d65d1ca2e22da63e4a45076e23e99a52182c`；已有Humble20项/0.390秒原日志 | FORMAL120全120槽零START时单独创建真实physical protocol，绑定40槽/80机会；之后生成独立附件。现有formal55 preflight字段只消费detection protocol，并未消费physical protocol |
| 四法 replay | 原export/calibrate、`reliability_v4_register.py replay-config` 与publication入口均已实现 | 从本次canonical54两条具名velocity录制真实导出并生成R0；待final55真实FORMAL120全PENDING时组装候选、发布canonical再seal；最后才有20录制×4方法的实际比较 |

旧 `reliability-v4-supplementary-evaluation-execution.md` 中Humble42组件身份是历史状态；新55接线使用上述新版本。它也未列physical protocol这项独立事前动作，不能遗漏。两种补充协议都不能在正式数据出现后倒填。Windows不可见 `/root` 不能证明尚未开始，真正登记须在原生可观察的实际最终根进行。

本轮可补齐的是本检查点、实际小文件绑定、输出路径/容量预留清单与后续命令审查。现存63项Windows套件约4分钟，不在extension运行时重跑；physical20项虽很快，但代码SHA未变且已有原生验证，重复并不补上真实协议缺口。Linux exec/信号/实际adapter接线、读包、定标和新55冷构建均保留到单一空闲窗口。

## 两条 velocity export 与 R0 的确定输入

原计划位于 `/root/uav_tracking_fullplan_v4_humble54/results/reliability_v4_humble54_core12_probe01_matrix/plan.json`，实际文件207807字节，SHA256为 `ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b`，内部 `plan_sha256` 为 `3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31`。

| 原slot ID | 原terminal文件SHA256 | 本次只读状态 |
| --- | --- | --- |
| `person_stage1_velocity_seed004` | `77d22a38c34ffae598063fd14d5520824d20c7ac9194f691ab051d26b6967291` | PASS、COMPLETED、非INFRA、flight exit整数0 |
| `car_stage1_velocity_seed004` | `81aa5f0e41c99d7cd6f603fb2d52345fed11e5030a8e9fab856ccfd56da226c9` | PASS、COMPLETED、非INFRA、flight exit整数0 |

两条完整目录从 `trials[].directory` 查，不能换clean、旧版本、45秒诊断或较好结果。它们都是75秒、seed004、单目标stage1_velocity。Windows工作副本的原export/calibrator字节与该计划保存SHA一致：export `08edc1f57a5f1d8de4e93d3a00f8aefdc6b7fb72aab52f815c756d017d1a72ac`，calibrator `0a6f3982e395024d7abf3da43e2e685dc0d88157686496dd2cd3e0296f462fe9`；这不是本轮重新验证Linux源或录包。

以下摘自既有最终登记卡的原CLI并填入本次确定输入，是未来命令，未执行。须等core/safety/extension owner及子进程全部闭合、Windows调用结束并核原生idle后，串行各导出一次。拟新目录 `reliability_v4_humble54_development_calibration01` 本次Windows只读时不存在，执行时仍须再查；失败保留部分结果，不覆盖重跑。开发导出不传 `--registration` 或 `--slot-id`。

```bash
set -euo pipefail
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_core="$tracking_dev/results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
tracking_calibration="$tracking_dev/results/reliability_v4_humble54_development_calibration01"
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
source "$tracking_dev/scripts/humble22_env.sh"
test ! -e "$tracking_calibration"
test ! -L "$tracking_calibration"
tracking_person_trial="$("$STAGE1_PYTHON_EXECUTABLE" -B -c 'import json,sys; p=json.load(open(sys.argv[1])); print(next(t["directory"] for t in p["trials"] if t["id"]=="person_stage1_velocity_seed004"))' "$tracking_core")"
tracking_car_trial="$("$STAGE1_PYTHON_EXECUTABLE" -B -c 'import json,sys; p=json.load(open(sys.argv[1])); print(next(t["directory"] for t in p["trials"] if t["id"]=="car_stage1_velocity_seed004"))' "$tracking_core")"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_person_trial" \
  --output "$tracking_calibration/person_export"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_car_trial" \
  --output "$tracking_calibration/car_export"
bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/calibrate_estimator_replay_v4.py" \
  --plan "$tracking_core" \
  --person-arrays "$tracking_calibration/person_export/arrays.json" \
  --car-arrays "$tracking_calibration/car_export/arrays.json" \
  --output "$tracking_calibration/R0_candidate.json"
```

执行审查点：两份arrays各绑定自己原具名录制、原归档和原terminal；`online_equivalence.json`、`native_state_audit.json`、`truth_alignment.json` 三份独立sidecar及非循环payload绑定齐全；export数值/独立native状态检查实际PASS，truth来源与覆盖保留。calibrator会再次调用既有export evidence verifier，取FOLLOW至最终Clock区间全部独立有效 `R_geometry`，保留融合拒绝和排除原因，不平均R_pose或拟合目标真值；R0最小特征值严格大于1e-12，不加隐式jitter。Q/P0/EMA和公共支持要求来自原候选策略，不能用留出数据调整。输出是 `CANDIDATE_NOT_REGISTERED`，不是四法已登记或优越性结论。

## extension 结束后的最小串行顺序

1. 确认core12、safety03与extension16真实完整终态、owner/Windows命令和子进程闭合；检查原生idle。保留extension原工程FAIL。
2. 按[新storage卡](reliability-v4-storage-snapshot-measurement.md)从固定eedd8d9完整暂存tools02，运行明确绑定schema03的28格测量；不要使用原normal卡第2节的旧测量命令或tools01 helper。再记录实际guard物理卷inventory。
3. 上述两条具名export及R0候选；保存各步骤的真实命令、UTC、exit和完整日志。任何步骤失败停止，调查后另选新路径。
4. 实际28格、物理inventory及显式增长/五交付预算齐后组装容量；`detection_audit`须计入原两条、新12条抽样/叠图/审批/缓存、timing和physical附件，不能沿用旧90机会估计。
5. 按[final55 staging卡](reliability-v4-final55-source-staging.md)准备与冷构建，再按normal card完成gate/safety assembly、core/extension发布及真实120/160定义。新delivery工具始终外置，不修改54或冷构建后的55全树。
6. 固定audit registrar组装replay候选并发布canonical；实际最终源三登记齐全且所有正式槽尚未START时，分别生成detection与physical两份真实补充protocol并独立核pins/UTC/分母。原guard不消费它们，physical也未自动接入detection preflight。
7. 完成真实seal、最终source sidecar与新formal55 supplementary合同/adapter/serial绑定，再由原guard逐槽执行。此处没有新增飞行、提前登记或准入。

父任务另已授权准备外置 `D:/WSL/UAVHumble22-validation/run_humble54_closed_followon01.sh`，将第1—3步落实为一次性、失败停止的未来原生接续入口，含固定双SHA、真实终态/START/owner核验、现有idle查询、逐步骤真实日志和全新外部收据。该脚本目前仅准备及静审，本文没有执行它；Windows原调用句柄/创建时间与真正退出由父任务的独立等待器负责，不能靠owner文件提前接续。具体脚本SHA以独审完成后的最终绑定为准。

真正正式录制齐备后，独立代理负责原图和无预测标签叠图审核，用户不必手工标注。physical/timing保留未知及完整分母；replay是给定同一录制轨迹的四法状态估计比较，不是四种控制器的闭环因果试验。最终报告和dashboard只引用实际生成并通过自身语义校验的独立附件。
