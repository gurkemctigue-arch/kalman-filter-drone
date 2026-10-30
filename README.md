# RGB-D UAV target tracking and following

**当前分支是 v4 开发检查点，三阶段功能已实现，最终验收与正式重复研究尚未完成。** 最新执行快照、来源和失败边界见[当前交接记录](planning/reliability-v4-current-state.md)，后续工作依[可靠性修复与交付方案](planning/reliability-v4-next-actions-20261030.md)推进。公开文档是带时间的快照；本机[进度入口](results/project_progress/current/index.html)读取受监任务的最新状态。

最新检查点（创建于北京时间2026-10-30 09:38:31，非实时状态）：Humble28已冻结566个文件，完成四包构建、模块/ament隔离、FastCDR来源核验及11项真实CDR消息往返；Linux全套1434项检查中1429通过、5项精确平台跳过，用时47.781秒，冻结来源前后不变。新版本统一非实时RTF=0.25、600秒飞行wall预算，保持原0.60/0.75秒保护。截至本快照，两类20秒clean串行检查已启动且尚无批次终态，核心12格全部PENDING，正式仍0/280，完整28格容量未准入。

Humble27运行历史：行人20秒clean完成，导航PASS；原RTF=0.5的汽车clean失效，47/47相邻测量机会的下一处理时刻距上次采集为0.796–1.024源秒，超过原0.75秒预测保护，随后锁存LOST。入站观测未超过0.60秒；该时效包含图像转换、检测和深度/导航处理，不能当作纯YOLO推理耗时。

同一冻结27的独立汽车资源诊断仅将RTF改为0.25，实际完成20源秒跟随；导航距离/高度RMSE为0.74435/0.30698米，导航和真值覆盖均204/204，末段距离与高度均已稳定。源时钟、原生起飞、归档、观察器及清理检查通过；无设计遮挡的surface原结论仍为INCOMPLETE_EVIDENCE。这是单次非实时仿真诊断，不能代替75秒工程验收、正式重复或实机时延验证，原0.5失败保持。

原27核心12格仍全部PENDING，0.5与0.25记录分别保留。新28须继续完成同源clean、12核心、4安全、16扩展、定标与容量核算；单次诊断或测试通过不能代替最终验收。原26启动失败及更早结果见下方历史检查点。

Humble26检查点（2026-10-30）：Ubuntu 22.04/Humble26 已完成新来源冻结、四包构建、模块/ament 隔离、FastCDR 来源核验和真实消息序列化往返；Linux 全套1417项检查中1412通过、5项按精确平台条件跳过，用时49.068秒，检查前后冻结来源不变。首条20秒clean检查在pre-unpause桥进程身份发现时失败，8.79秒后退出1；普通`/proc`进程遍历触发`Proc identity is truncated or no longer alive`，尚未进入跟随验证，已清理且无残留。12格核心PROBE全部PENDING，须修复后新冻结再验证。起飞等待、输出时效、像素排除修复与[汽车m960检测候选](planning/reliability-v4-detector-m960-development-selection-20261030.md)尚无本轮飞行通过结论，[新无损归档](planning/reliability-v4-lossless-archive-20261030.md)的完整28格容量仍未准入。

Humble25原核心12格的9 PASS、3 FAIL保持不变：六个行人格均PASS，汽车起飞交接、交叉跟踪和多目标主动云台FAIL。正式试验仍为0/280。测试通过、程序执行完成和整次工程验收分别判断；下文 v3 报告与结果计数属于历史冻结版本。

核心 120 槽覆盖两类目标与六组工程条件；原计划距离、噪声、延迟、加减速等八个扩展条件另有 160 槽，共 280 槽，当前均未开始正式运行。范围和剩余工作见 [执行计划](planning/reliability-v4-remaining-execution.md)。

中文验收入口：[结果工件说明](docs/RESULTS_ARTIFACTS.md) · [查看与复核方法](docs/验收使用指南.md) · [三阶段实际状态](docs/THREE_STAGE_STATUS.md) · [已归档计划书](docs/最终版毕业设计计划书_最终版.docx)。结果页面和报告属于本地归档工件，保留历史失败、身份未知、缺失及未执行项；工程通过与正式重复研究完成分别判断。

This repository implements a simulation-first RGB-D UAV target following system with YOLO11, 3-D Kalman filtering and PX4 Offboard control. Estimation and control remain independent from ROS 2, PX4 and Gazebo so the same core can be tested, replayed and connected to a future vehicle adapter.

WSL EGL shutdown failures and the explicit Gazebo-only CPU rendering option are documented in the [shutdown diagnosis](docs/GAZEBO_WSL_SHUTDOWN_DIAGNOSIS.md). Historical `auto` driver selection is preserved; new Humble validation selects `--gazebo-render-driver llvmpipe` and checks the actual rendering libraries.

The supported target classes are `person` and `car`. The target manager exposes two modes:

- `AUTO_UNIQUE`: lock the only confirmed candidate; multiple candidates produce an `ambiguous` state.
- `LOCKED_TARGET`: select a bounding box at task start and keep that physical target. Short occlusions coast with the 3-D filter; long loss becomes `lost` and requires re-selection.

The implementation includes a portable Python core, deterministic synthetic experiments and an integrated PX4/Gazebo flight graph with an onboard aligned RGB-D camera. Runtime tracking uses images, TF and vehicle state; Gazebo truth is reserved for offline evaluation.

## Quick start

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
python -m pytest  # optional; install the test extra if pytest is unavailable
python -m uav_tracking.simulation --mode auto_unique --target-class person --steps 120
python scripts/run_synthetic_experiments.py --target-class both --seeds 10
```

The first command installs the portable package and its test dependencies. The unittest
command is sufficient for a minimal environment; pytest is only a convenience
runner. ROS 2 execution is separate and should be performed in the WSL/Ubuntu
environment described in `docs/ROS2_SIMULATION.md`.

The portable GitHub Actions workflow runs these fixtures on Ubuntu 22.04 with
Python 3.10 and 3.12, including standard `zstd` archive checks. It does not
install ROS, start Gazebo/PX4, or certify a completed flight experiment. The
[v4 estimator comparison design](docs/V4_ESTIMATOR_COMPARISON_DESIGN.md)
documents the array replay, recording exporter and online numerical audit.
One car development recording passed export and numerical reproduction;
prospective calibration and the complete formal comparison remain pending.

The experiment command uses one deterministic noisy observation sequence per
seed for raw measurements, EMA, fixed-noise KF, and adaptive-noise KF, then
writes JSON records under the local, ignored `results/` directory. These are
estimator baselines; they do not replace the later rosbag/PX4 closed-loop
trials. See [the results artifact note](docs/RESULTS_ARTIFACTS.md) for the
public-clone boundary and the optional dashboard.

## PX4 / Gazebo flight

The current validation target is Ubuntu 22.04, ROS 2 Humble, Gazebo Harmonic
and PX4 v1.17.0. Isolated builds, bridges and partial development probes have
run; complete v4 flight acceptance remains pending. The earlier Ubuntu 24.04.1 /
ROS 2 Jazzy experiments belong to the historical v3 archive below.
Build and source the workspace as described in the
[simulation guide](docs/ROS2_SIMULATION.md) and
[version lock](docs/VERSION_LOCK.md), then run from the Linux project root:

```bash
bash scripts/run_stage1_trial.sh \
  --class person --name person_flight_trial_01 --duration 45 --occlusions
```

The runner owns Gazebo, PX4, the XRCE-DDS Agent, ROS nodes, recording and the
monitor. Each trial requires a new result name. Run one simulation at a time.
See the [flight guide](docs/STAGE1_FLIGHT.md) for the graph, manual component
commands, supervised takeoff, target motion and rendered occlusions. The
[acceptance record](docs/STAGE1_ACCEPTANCE.md) contains the current per-class
results, failed trials and remaining limits; synthetic and controlled smoke
tests are separate evidence.

The independent [v4 condition extensions](docs/V4_CONDITION_EXTENSIONS.md)
retain 160 slots in addition to the 120 core slots. Formal scheduling requires
prospective registration, actual development evidence and a bound clean core
reference plan. Both formal matrices are currently unexecuted.

The historical `stage1_final_v2` engineering record passed four scoped
person/car velocity/position demonstrations. The frozen v3 research archive
now records all 166 main flight slots: 107 PASS, 58 FAIL and 1 INTERRUPTED.
The separate 16-flight engineering extension records 2 PASS and 14 FAIL; two
of those stops are explicitly classified as infrastructure failures. The
post-flight supplement has 15 recorded slots and one incomplete-evidence slot.
These counts preserve negative results and are not an algorithm success rate.

The main offline ledger covers all 166 slots (160 recorded, 4 incomplete
evidence and 2 not applicable because no selected task existed). The local
archive also contains the metric supplement, figures, acceptance dashboard,
browser demos and the final report. Those large result artifacts are ignored by
Git and are described in [the results artifact note](docs/RESULTS_ARTIFACTS.md).
The published repository contains the source, tests and reproducible commands;
it does not claim that a public clone contains private bags or reports.

The historical v3 Linux validation used Ubuntu 24.04.1, ROS 2 Jazzy, Gazebo Harmonic
and PX4 v1.17.0. Independent v4 Ubuntu 22.04/Humble builds, bridge checks and
partial flight probes are recorded in the [Humble validation log](docs/HUMBLE_ISOLATED_VALIDATION.md);
they do not yet establish complete v4 acceptance. Two historical independent shutdown
probes passed in a new cleanup checkout: all 8 stage-one and 9 multi-target
stage-three ROS nodes exited cleanly, with no observed residual processes and
no changes to the formal research ledgers. See the [delivery status](docs/DELIVERY_STATUS.md)
for the final counts and artifact locations.

One historical car/position flight (seed08) failed evaluation with SQLite
error 11. An [independent audit](docs/V3_BAG_INFRASTRUCTURE_AUDIT.md) found an
unfinished zstd frame and a native ROS decompression output missing its final
128 KiB; an independent decoder produced an intact SQLite database. That
original FAIL remains unchanged and is an infrastructure/evidence failure,
not a measured tracking error. The audit did not establish why compression
failed to finish. All 34 stage-one v3 FAIL results must remain visible; their
causes cannot all be inferred from this one diagnosis.

Historical reports such as `person_flight_v06` used earlier acceptance rules;
their old PASS does not certify current fresh-image recovery. The historical
final person/car by velocity/position matrix uses correlated shutter service
responses and bag-confirmed explicit reselection. Models, sources,
licenses and visible-surface measurement semantics are documented in
[visual assets](docs/VISUAL_ASSETS.md).

## Design boundaries

The current code supports a selectable velocity or position setpoint, but only one setpoint mode is active per controller instance. The three-axis gimbal model treats yaw and pitch as line-of-sight control and roll as horizon stabilization. Long-term appearance ReID, obstacle avoidance, and real-flight validation remain separate extensions.

The portable core's `LOCKED_TARGET` mode requires a user or test script to
select the initial bounding box. It disables automatic target replacement
during loss; physical identity still requires independent evaluation of data
association, including unobservable intervals. Stable re-identification after a
track is removed is intentionally outside the MVP. The deterministic demo is
not a ROS/PX4/Gazebo validation result.
