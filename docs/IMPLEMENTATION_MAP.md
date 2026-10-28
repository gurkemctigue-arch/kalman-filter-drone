# Implementation map and acceptance boundaries

This is an evidence snapshot from 2026-10-26. The installed integration
environment is Ubuntu 24.04.1 under WSL2, ROS 2 Jazzy, Gazebo Harmonic 8.15,
PX4 v1.17.0, matching `px4_msgs` v1.17.0 and XRCE-DDS Agent v2.4.3. Linux
`colcon build`, sensor bridging and integrated PX4 flights have been executed.
The original Ubuntu 22.04/Humble proposal has not been separately reproduced;
the exact installed versions and source signatures are in
[VERSION_LOCK.md](VERSION_LOCK.md).

## Ownership and the running flight graph

| Package/node | Responsibility | Must not own |
| --- | --- | --- |
| `uav_tracking_nodes/detector` | YOLO11 inference, depth ROI validity/spread, timestamped candidate observations and diagnostics | Persistent identity, flight commands |
| `uav_tracking_nodes/state_estimator` | Optical-to-map TF, target selection/association, 3D KF, gates and elapsed-time loss | PX4 message types or simulator identity |
| `uav_tracking_nodes/controller` | World-coordinate follow commands, moving position reference with bounded vehicle-relative lead, and controller lifecycle | PX4 sign conversions or simulator truth |
| `uav_tracking_bringup/flight_tf` | Dynamic `map -> base_link` from vehicle odometry; fixed optical mount | Target pose or a static world-camera transform |
| `uav_tracking_px4_adapter/flight_supervisor` | Simulation-only Offboard/arming requests, supervised takeoff, visual handoff and latched abort | Target observations, GT association |
| `uav_tracking_px4_adapter/px4_adapter` | ENU/FLU to NED/FRD conversion, setpoint/heartbeat publication, fresh armed/Offboard gate, acknowledgements | Detection/filtering or target choice |
| `uav_tracking_bringup/scenario_motion` | Repeatable target motion after first `FOLLOW`, continuing during visual loss | Observations or any target/vehicle GT subscription |
| trial monitor and offline evaluator | Rendered shutter stimuli, videos, bag recording and independent evaluation | Simulator truth in runtime tracking/control |

`stage1_flight_person.sdf` and `stage1_flight_car.sdf` each contain the real
PX4 x500 dynamics and its onboard aligned 640x480 RGB-D sensor in the same
world as one visual target. PX4 attaches to `stage1_uav`; a second aircraft or
stationary fake camera is not used for flight acceptance. Target scene actors
have gravity/collisions disabled and prescribed planar motion; their motion
is test input, while the x500 retains physical motor/rigid-body dynamics.
The stage-one camera is fixed at its mount; active three-axis gimbal flight
belongs to stage three.

Only one command source feeds PX4:

```text
RGB-D -> detector -> estimator -> controller
                                  |
                                  v
                     flight_supervisor -> px4_adapter -> PX4
```

The supervisor requires explicit simulation `auto_start=true`, preflight
health and heartbeat prestreaming. It uses bounded velocity for takeoff,
then forwards the selected visual position or velocity mode exclusively.
Inactive PX4 position/velocity fields are NaN. Missing/stale visual commands
produce zero-velocity hover; disarm, Offboard exit, failsafe or stale vehicle
state latch `ABORTED` and do not trigger automatic rearming. Abort messages
retain stream ages, source stamps and status values from the failing tick.

## Position reference and constraint priority

The ROS controller and both flight parameter files enable `slew_position=true`;
the portable `FollowConfig` API retains a false default unless the caller
enables it. The enabled position path maintains a moving reference, starting
from the vehicle when uninitialized and otherwise integrating the last
reference. Its nominal velocity is target-velocity feedforward plus
proportional error from the desired follow position to that last reference,
with deadzone, speed and acceleration limiting. It does not restart that
integration from the current vehicle on every tick.

After nominal integration, the published reference is projected into the
per-axis ENU box `p_vehicle +/- [1.0, 1.0, 0.5] m`, configured through
`max_position_lead_m`. These are separate East/North/Up limits about the actual
vehicle, not a radial distance or a reference-to-reference limit. The hard
vehicle-relative lead bound takes priority when it conflicts with nominal
slew limits, such as when the aircraft drifts backward. Therefore the final
projected reference's derivatives are not unconditionally speed/acceleration
bounded. The realized reference rate is separately limited before updating
the internal slew state; projection exceptions cannot inject an unbounded
rate into that state. The internal reference velocity is not an additional
PX4 velocity command: healthy position FOLLOW activates only position fields.

This is a control-reference implementation change, not evidence of a general
tracking or state-estimation improvement. Its retained failure, follow-up
probe and separately evaluated final matrix are listed below.

## Current flight evidence

The authoritative trial directories currently reside in the Linux mirror
`/root/uav_tracking_project/results/`; Windows result copies may lag. Each
trial retains `run_config.json`, configuration/source hashes, process logs,
`telemetry.jsonl`, `onboard.mp4`, compressed rosbag and offline evaluation.

| Trial | Observed result | Meaning and remaining boundary |
| --- | --- | --- |
| `person_flight_v06` | Historical `PASS` under an earlier evaluator; about 12.49 m UAV horizontal span | The stricter freshness check found LOST before recovery from a fresh post-opening image. The old report cannot certify current short-occlusion acceptance. |
| `car_flight_v01` through `car_flight_v06` | Failed or incomplete engineering acceptance | Retained failures expose detection-view, timing, scheduling and CPU latency issues. In v06, 640-pixel inference recovered from the short shutter but exceeded measurement freshness later, before the long shutter. |
| `car_flight_v07` | Recorded schema-2 offline short/long `PASS`; velocity mode; about 20.17 m UAV horizontal span | Real YOLO11s/480 RGB-D flight, correlated shutter responses and explicit box reselection were recorded. This earlier single-condition report does not replace schema-3 or the final person/car by position/velocity matrix. |
| `stage1_final_v1_car_position` | Reselection caused an approximately 3.3 m position-reference step, about 24 degrees of nose-down pitch and loss of camera field of view | Retained failure motivating the moving-reference and hard lead limits. It is not a passing position-mode condition. |
| `car_flight_v08_position` | Schema-3 offline `PASS`; FOLLOW persisted through trial end with the reference fix | One engineering probe; this does not certify the complete `stage1_final_v2` matrix or a research-level improvement. |
| `stage1_final_v2_person_velocity` | Schema-3 offline and aggregate `PASS`; about 20.08 m UAV horizontal span | Final person/velocity condition: fresh short-shutter recovery, long-loss braking, explicit new task selection and sustained recovery through trial end. All 730 FOLLOW setpoints use velocity fields only. |
| `stage1_final_v2_car_velocity` | Schema-3 offline and aggregate `PASS`; about 20.14 m UAV horizontal span | Final car/velocity condition passes the same gates. All 728 FOLLOW setpoints use velocity fields only. |
| `stage1_final_v2_person_position` | Schema-3 offline and aggregate `PASS`; about 19.44 m UAV horizontal span | Final person/position condition passes the same gates. All 730 FOLLOW setpoints use position fields only; takeoff/HOLD use separate velocity-only messages. |
| `stage1_final_v2_car_position` | Schema-3 offline and aggregate `PASS`; about 19.24 m UAV horizontal span | Final car/position condition passes the same gates. All 732 FOLLOW setpoints use position fields only; takeoff/HOLD use separate velocity-only messages. The existing t=63.7 s frame also shows the car within the field of view and FOLLOW. |
| Earlier failed/incomplete flights | Retained under their original trial names | Initialization, rendering load, timestamp and other failures remain evidence; newer passing runs do not erase them. |

`results/stage1_final_v2_report.json`, captured at
`2026-10-25T21:08:22.615142+00:00`, records aggregate `PASS` for all four
conditions (4/4), with no missing passed conditions or required trial
artifacts. Every condition confirms real visual flight, shutter service
acknowledgements, schema-3 short/long occlusion and full-trial recovery, actual
requested PX4 FOLLOW mode, bag data and a nonempty onboard video. Setpoint
counters are complete and conserved; mixed, partial, infinite, inactive and
invalid position/velocity messages are zero. These are stage-one engineering
acceptance runs, not independent repeated research trials or measurements of
detector/estimator accuracy.

The initial car report counted one startup phase message before the first
`/clock` as a read error. The evaluator now preserves such successfully decoded
messages in `startup_unclocked_messages` and exact recorder-time/CDR records,
separate from actual deserialization errors. Removing that misclassification
does not change the car's real long-occlusion failure.

The evaluator reads zstd file-compressed SQLite bags with
`SequentialCompressionReader` and a disposable decompression directory, leaving
the source bag unchanged. Its top-level GT statistics retain the whole selected
interval, including HOVER while the target continues moving. The separately
labelled `ground_truth.active_tracking` subset covers controller FOLLOW/PREDICT
only. Model-origin/visible-surface offsets are retained; target position and
velocity RMSE remain unavailable until the coordinate transform and measurement
anchor have independent calibration. Detector candidate fractions are not
Precision/Recall/mAP. See [STAGE1_FLIGHT_EVALUATION.md](STAGE1_FLIGHT_EVALUATION.md).

## Explicit selection and recovery after removal

The estimator subscribes to `/tracking/selection` with
`uav_tracking_interfaces/msg/TargetSelection`. A box-based `ACTION_SELECT`
with `track_id=0` waits for a matching observation, calls `lock_detection`,
and can initialize a new track after the old track is `REMOVED`. It switches
the manager to `locked_target`; task UUID and transient tracker ID remain
separate. A fresh task UUID describes a new explicit selection, not automatic
recognition of an old physical identity.

Current `ACTION_RESET` and `ACTION_CLEAR` both call `unlock_target`: they clear
the selected identity and pending box but do not clear all tracks or restore
the configured initial mode. In `auto_unique`, the next unique observation can
therefore acquire a target. After any box selection has switched the manager
to `locked_target`, RESET alone leaves it waiting for another explicit
selection. This behavior was verified with a pure-core REMOVED/reset/select
probe. The live box-selection path has also been exercised in car v07;
see its bag and explicit selection events for the new task UUID.

Schema-3 offline evaluation independently confirms a valid bag-recorded
selection/reset followed by a fresh MEASURED first active state with the new
task UUID. It then requires at least 5 s of continuous same-UUID active-state
and FOLLOW/PREDICT control evidence, through the full trial end rather than
only an initial successful window. A later LOST/identity change or return to
HOVER fails that sustained-recovery gate. Sampling/tail evidence and target
measurement freshness must also satisfy the recorded thresholds; see
[STAGE1_FLIGHT_EVALUATION.md](STAGE1_FLIGHT_EVALUATION.md). The monitor's
confirmation flag alone is insufficient.

For a test monitor that has explicitly enabled reselection, a real detector
diagnostic supplies the box without any GT lookup:

1. After the long shutter opens and at least 32 seconds after first FOLLOW,
   wait while the estimator is LOST and the controller HOVER for a diagnostic
   with age at most 0.40 s, matching
   `class_name`, exactly one candidate and valid depth. Do not choose the
   highest-confidence/nearest candidate from an ambiguous frame.
2. Publish one `TargetSelection` on `/tracking/selection`: `action=0`,
   `track_id=0`, the task class, `center_u_px=(x1+x2)/2`,
   `center_v_px=(y1+y2)/2`, `width_px=x2-x1`, `height_px=y2-y1`.
   Set the header to the explicit selection time and optical frame
   `camera_link`, `source=TEST_SCRIPT_EXPLICIT_RESELECTION`, and a fresh task
   UUID unless the operator explicitly supplies another task identity.
3. Record the request, original box/time/source and selected UUID, then verify
   a new measured state and resumed control for that UUID. Record
   `/tracking/selection` alongside the ordinary flight topics.

The box matcher requires IoU above 0.05 and rejects an exact best-score tie.
The current selection callback does not enforce header age or expire a pending
box, so the monitor must enforce freshness itself. Multi-target selection
robustness and a selection timeout remain interface-hardening work for stage
two. Removed tracker IDs should not be submitted as a substitute for a fresh
box selection.

## Engineering acceptance and remaining validation boundaries

The final acceptance status is recorded in `STAGE1_ACCEPTANCE.md` and the
four-condition aggregate report. The `stage1_final_v2` flight matrix is
complete with all four conditions passing (4/4). It establishes:

- Person and car flights in both position and velocity modes, with fresh
  identity-preserving recovery during the short shutter and actual braking
  from motion after the long shutter.
- Explicit box reselection after long loss, confirmed from the bag as a new
  measured task UUID, without model names, truth IDs or synthetic observations.
- Actual PX4 setpoints in the requested FOLLOW mode, with complete classified
  counters and no mixed, partial, infinite or inactive position/velocity fields.

Proportional fault checks for invalid/absent depth, delayed/out-of-order
observations, stale controller commands and stale PX4 status/Offboard exit
remain a separate validation boundary. Pure tests cover several guards, but
ordinary low-latency flights alone do not demonstrate all injected
communication/sensor failure conditions. The 4/4 engineering result does not
establish those additional fault experiments or the later research studies.

`auto_unique` enters ambiguity whenever more than one valid same-class
candidate exists, including after acquisition. Prediction ticks and empty
frames cannot silently clear that ambiguity. It may recover the original task
only through an unambiguous association before the prediction deadline.
Both modes latch long loss until an explicit selection/reset; a delayed old
frame cannot resume the task. Core and controller regressions cover those
guards; the stage-one flight worlds themselves contain one target.

The manager has elapsed-time coast/retention limits in addition to its portable
frame-count fallback. Output-rate predictions project snapshots without
consuming camera frames or advancing committed measurement time. Invalid depth
and rejected gates cannot refresh 3D measurement age. The ROS controller also
checks transport age, and the flight supervisor/adapter separately check wall
reception age so a stale final message cannot command motion indefinitely.

## Later research and stages

The detector selects one class per launch (`person` or `car`); both conditions
use the same interfaces. Synthetic paired raw/EMA/fixed-KF/adaptive-KF estimator
baselines exist. Recorded-image paired comparisons, repeated closed-loop
conditions, calibration, labelled detector accuracy, IDF1/HOTA and a complete
multi-target designated-instance study remain research experiments. A single
bag's frame count is not ten independent experimental repetitions.

Stage two adds multiple same-class targets, association/ambiguity validation
and explicit designated-instance experiments. Stage three adds active gimbal
control with joint feedback and aircraft yaw coordination. Full long-absence
ReID, active search, avoidance and real flight remain outside the initial scope.

For a fresh Linux build, install the root portable package from `ros2_ws`
(`python3 -m pip install -e ..`) before `colcon build`; a ROS package build
does not itself install that separate distribution. Build/run commands are in
[ROS2_SIMULATION.md](ROS2_SIMULATION.md) and [STAGE1_FLIGHT.md](STAGE1_FLIGHT.md).
