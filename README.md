# RGB-D UAV target tracking and following

**当前分支是 v4 开发检查点，尚未完成修复后的正式验收。** `nav04`、`nav05` 的失败记录保留；新原生起飞分支仍待实际 SITL 验证，Humble 验证和正式 120 槽尚未完成。请先查看 [v4 当前状态](docs/V4_WORK_STATUS.md) 和 [验收合同](docs/V4_ACCEPTANCE_CONTRACT.md)。下文 v3 报告与结果计数属于历史冻结版本。

中文验收入口：[结果工件说明](docs/RESULTS_ARTIFACTS.md) · [查看与复核方法](docs/验收使用指南.md) · [三阶段实际状态](docs/THREE_STAGE_STATUS.md) · [最终计划书](docs/最终版毕业设计计划书_最终版.docx)。结果页面和报告属于本地归档工件，保留历史失败、身份未知、缺失及未执行项；工程通过与正式重复研究完成分别判断。

This repository implements a simulation-first RGB-D UAV target following system with YOLO11, 3-D Kalman filtering and PX4 Offboard control. Estimation and control remain independent from ROS 2, PX4 and Gazebo so the same core can be tested, replayed and connected to a future vehicle adapter.

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

The first command installs the portable package and NumPy. The unittest
command is sufficient for a minimal environment; pytest is only a convenience
runner. ROS 2 execution is separate and should be performed in the WSL/Ubuntu
environment described in `docs/ROS2_SIMULATION.md`.

The experiment command uses one deterministic noisy observation sequence per
seed for raw measurements, EMA, fixed-noise KF, and adaptive-noise KF, then
writes JSON records under the local, ignored `results/` directory. These are
estimator baselines; they do not replace the later rosbag/PX4 closed-loop
trials. See [the results artifact note](docs/RESULTS_ARTIFACTS.md) for the
public-clone boundary and the optional dashboard.

## PX4 / Gazebo flight

The tested WSL baseline is Ubuntu 24.04.1, ROS 2 Jazzy, Gazebo Harmonic and PX4
v1.17.0. Build and source the workspace as described in the
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

The frozen Linux validation used Ubuntu 24.04.1, ROS 2 Jazzy, Gazebo Harmonic
and PX4 v1.17.0. The original Ubuntu 22.04/Humble combination remains a
portability target rather than a verified environment. Two independent shutdown
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
