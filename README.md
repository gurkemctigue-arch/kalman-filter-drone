# RGB-D UAV target tracking and following

中文验收入口：[验收总览](results/验收总览.html) · [查看与复核方法](docs/验收使用指南.md) · [三阶段实际状态](docs/THREE_STAGE_STATUS.md) · [最终计划书](docs/最终版毕业设计计划书_三阶段修订版.docx)。页面和报告保留历史失败、身份未知、缺失及未执行项；工程通过与正式重复研究完成分别判断。

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
writes JSON records under `results/`. These are estimator baselines; they do
not replace the later rosbag/PX4 closed-loop trials.

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

The historical `stage1_final_v2` engineering record passed all four person/car
velocity/position demonstrations, including sustained tracking after explicit
reselection. See the [historical aggregate report](results/stage1_final_v2_report.json).
This is a scoped result for that source revision and four conditions, not a
current v3 reliability claim. In the frozen v3 study, all 100 stage-one
repeated trials are terminal: 66 PASS and 34 FAIL. Existing failure typing
identifies 33 scoreable behavioral failures and one recording/evaluation
infrastructure failure; formal offline aggregation and diagnosis remain in
progress. The final Linux build completed for all four ROS packages and the
then-current 133 verification tests passed. The current v3 frozen Linux
workspace passed all 531 tests, built all four ROS packages and verified that
its imports use that frozen root. These checks do not replace the repeated
research results.
The original eight v1 formal flights remain archived (7 original PASS, 1
original FAIL); the revised v3 study uses a separate 166-flight matrix without
adopting those recordings. The current v3 summary covers 166 main slots, of
which 127 are recorded or attempted; status counts are 85 PASS, 42 FAIL and
39 PENDING. Its stage-two 26 slots
are terminal at 19 PASS and 7 FAIL; stage-three has one FAIL and 39 PENDING.
The main offline queue and the separate 16 engineering flights remain
outstanding.
The current Windows suite also passed 563 tests with 5 platform skips; this
main-copy check is separate from the 531-test frozen Linux validation.
Current progress comes from
`results/frozen_fullplan_v3/full_plan_research_v3/plan.json` and its linked
manifests. Continue the original frozen runner one slot at a time through the
[external guard](docs/GUARDED_FULLPLAN_V3_CONTINUATION.md), using the original
relative output text `results/full_plan_research_v3`. See the
[research runbook](docs/FULL_PLAN_RESEARCH_RUNBOOK.md) and
[delivery sequence](docs/FULLPLAN_V3_DELIVERY_COMMANDS.md) for the remaining work.

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
