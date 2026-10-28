# Offline evaluation of recorded stage-one flights

`scripts/evaluate_stage1_flight.py` reads a rosbag and the optional flight
monitor event log. It creates no ROS node, publishers, services or subscriptions.
It does not alter the online controller or use truth for runtime association.
Its current report has `schema_version: 3`. The engineering summary requires
this schema together with correlated shutter responses, independently
confirmed new-task selection and sustained tracking afterward; an older report is insufficient evidence even
if its historical `acceptance.result` was `PASS`.

Source the same ROS and message builds used for recording. Current WSL
integration uses ROS Jazzy; the evaluator uses the installed `rosbag2_py`,
`px4_msgs` and project interface definitions. It supports rosbag2 storage
plugins installed on that machine, including MCAP and SQLite.

```bash
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source /root/uav_tracking_project/ros2_ws/install/setup.bash
python3 scripts/evaluate_stage1_flight.py results/TRIAL/rosbag \
  --target-class person --output results/TRIAL/offline_evaluation.json \
  --telemetry-jsonl results/TRIAL/telemetry.jsonl \
  --monitor-summary results/TRIAL/summary.json
```

Use `--target-class car` for the vehicle trial. Set `--desired-distance-m` and
`--desired-height-m` to the exact controller configuration used in that trial.
For the current car configuration, those distances are 9 m and 2 m:

```bash
bash scripts/evaluate_stage1_flight.sh results/CAR_TRIAL/rosbag \
  --target-class car --desired-distance-m 9 --desired-height-m 2 \
  --output results/CAR_TRIAL/offline_evaluation.json \
  --telemetry-jsonl results/CAR_TRIAL/telemetry.jsonl \
  --monitor-summary results/CAR_TRIAL/summary.json
```

The evaluator does not infer these setpoints from the parameter snapshot.
Use the values archived with that trial. It has no `--command-mode` argument:
the trial runner selects that mode with `--command-mode velocity|position` and
records it in `run_config.json`. Mode-specific PX4 command checks require the
recorded setpoints and phase evidence; this scalar evaluator's PASS does not
by itself certify every setpoint field or both control modes. Supervised
takeoff and HOLD use velocity commands even during a position-following trial.

`--start-s` and `--end-s` select a simulation-time interval; otherwise the
first recorded `FOLLOW` phase is used as the start, with a monitor event/summary
fallback. Without a handoff timestamp, all readable messages are evaluated and
that limitation is included in the report. `interval.recorded_end_s` retains
the full readable recording's latest effective source/receive time even when
a shorter slice is selected. The final engineering summary requires
`covers_recorded_trial_end: true` and an evaluated end at/after that recorded
end. A diagnostic time slice ending before a later loss cannot pass full-trial
acceptance by presenting its own earlier endpoint as a fresh trial tail.

Record at least these topics alongside the monitor's `telemetry.jsonl`:

```bash
ros2 bag record --use-sim-time -o results/TRIAL/rosbag \
  /clock /tracking/state /tracking/status /tracking/observations \
  /tracking/detection_diagnostics /tracking/command /tracking/flight_phase \
  /tracking/flight_command /tracking/selection \
  /vehicle/odometry /fmu/out/vehicle_status_v1 \
  /ground_truth/poses /ground_truth/vehicle_poses \
  /fmu/in/trajectory_setpoint /tf /tf_static \
  /camera/color/image_raw /camera/aligned_depth_to_color/image_raw \
  /camera/color/camera_info
```

The PX4 branch may expose `/fmu/out/vehicle_status` instead of the `_v1` name;
the evaluator accepts both. `/ground_truth/world_poses` and
`/ground_truth/uav_poses` are also accepted truth topic names. Large camera,
setpoint and TF payloads are intentionally excluded from deserialization by
this scalar-metric evaluator; retain them for replay and visual audits.

## Meaning of the results

Detection availability is the fraction of completed inference diagnostic frames
with a candidate or valid depth. The denominator includes empty detections. It
does not represent precision, recall or mAP; those remain `null` without labeled
boxes. Simulation latency (`completed_s - stamp_s`) and inference wall duration
are reported separately because simulation may run slower than wall time.

Controller distance/height errors use the same target estimate that drives
the controller. They are labeled `estimated_*` and are internal consistency
metrics. RMSE includes FOLLOW and PREDICT samples, while HOVER's unset zero error
fields are excluded. HOVER duration and all loss/failure counts remain in the
report. Error distributions include signed and absolute 95th percentiles.

The monitor's `horizontal_vehicle_span_m` is
`sqrt((max(x)-min(x))^2 + (max(y)-min(y))^2)` over its recorded UAV positions.
For `person_flight_v06`, about **12.486 m** describes the aircraft's horizontal
position range. It is neither target displacement, net start-to-end motion,
nor accumulated UAV flight-path length.

The target model pose is in Gazebo world; PX4 odometry is in its estimator's
local `map` origin. A spawn/ground reference offset, especially in z, must not
be removed by fitting an arbitrary bias. The evaluator does no such fit and
does not substitute PX4 odometry for Gazebo UAV truth. With time-matched target
and `stage1_uav` model truth in the same parent frame, it reports independent
horizontal following distance and height above the target model origin. That
height reference differs from the visual box/depth surface. Target position
and velocity estimation RMSE stay `null` until an independent frame transform
and matching target measurement anchor are defined and evaluated.

`ground_truth.horizontal_distance_error_m` and
`height_above_target_origin_error_m` retain the **whole selected evaluation
interval**, including loss and HOVER. The physical target keeps moving while
the UAV hovers, so increasing distance error during that period remains in
the result. The separately labelled `ground_truth.active_tracking` subset
includes only samples whose most recent controller status at or before that
sample is FOLLOW or PREDICT. That status is held until the next status/end;
no future status is used to label an earlier truth sample.

The subset uses the same uncorrected model origins, desired distances and
time-matching tolerance. It does not remove surface/model-origin bias or
replace the whole-interval metrics. Report its `active_duration_s`,
`matched_samples` and `matched_fraction_of_whole_interval` with its errors.
The last field is the active matched-pose count divided by the whole-interval
matched-pose count, not a duration fraction or detector recall. All losses,
HOVER durations and failed occlusion checks remain in the report. If a trial
contains explicit reselection, the default interval can include both selected
tasks; any additional task-specific time slices must be labelled and retain
the full-trial report.

State transition times use the later of the state header and recorded receive
`/clock`. A measured state retains image acquisition time, so using its header
alone would claim recovery before a delayed image actually reached the
controller. Unheadered PX4/phase messages use the latest recorded `/clock`;
recorder wall timestamps are never mixed with simulation time. Clock sampling
still limits the exact transition-time precision.

## Messages before the first clock sample

An unheadered message received before the first recorded `/clock` may decode
successfully yet have no independent simulation timestamp. The reader retains
such messages in `inputs.startup_unclocked_messages` (per-topic counts) and
`inputs.startup_unclocked_records` (topic, original `record_timestamp_ns` and
exact `serialized_cdr_base64`). It assigns no invented simulation time and
excludes these records from timed metrics. Messages with their own usable
header/diagnostic timestamp remain usable even before that first clock sample.

This ordinary recorder-startup race is reported as a limitation, separately
from corrupt/mismatched messages in `read_errors`. It does not by itself force
FAIL when later readable clock samples establish the simulation timebase.
Conversely, a topic named `/clock` without any readable samples is insufficient:
`acceptance.clock_timebase_available` is false and the evaluator cannot report
PASS. Keep the original records; do not relabel recorder wall time as simulation
time to avoid this limitation.

## Occlusion and braking checks

Monitor shutter requests define event windows. They are corroborated by
candidate-free detector frames; a pose-change request alone does not establish
that the camera image was obscured. Every close/open request must have a
positive integer `request_id` and exactly one matching
`shutter_service_result` event. Its `active` action and `request_time_s` must
match the request, `time_s` must not precede it, and `success` must be the
boolean `true`. The successful close response must arrive no later than the
open request. Missing IDs/responses leave incomplete evidence; duplicate,
failed or mismatched responses fail. Legacy success-only responses are not
guessed or attached to an operation. An unclosed window fails.

Each event's `shutter_execution` retains close/open request IDs, response
times, `close_success`, `open_success`, `close_ack_before_open_request`, and
failure reasons. All three booleans are required gates. These correlated
SetEntityPose acknowledgements corroborate execution; neither the request
interval nor the response interval independently measures exact rendered-image
occlusion duration. Inspect detector evidence and the onboard video alongside
these events.

The runner's `--short-occlusion-s` defaults to **0.2 s**; the scheduled long
shutter remains **3.0 s**. This argument configures the trial runner/monitor,
not the offline evaluator. The evaluator reads the actual recorded close/open
events, so archived 0.4 s trials retain their own durations and outcomes.
The 5 Hz CPU inference cap, sampling and inference delay have turned a 0.4 s
shutter request interval into an approximately 0.8 s valid-depth acquisition gap.
This exceeds the fixed 0.75 s measurement prediction limit: a resulting LOST
state is correct, while the prediction-only short-occlusion test must fail.
Neither a requested duration below 0.75 s nor the new 0.2 s default guarantees
a pass. Retain `valid_depth_gap_straddling_event_s` and actual transition times.

Short recovery requires the first MEASURED state in the recovery window whose
original `header.stamp` (image acquisition) and recorded receive simulation time
are both at or after shutter opening. Missing receive time cannot certify
recovery; the report retains `post_open_measured_missing_receive_time_count`.
The reported `first_measured_after_open_s` is that state's effective transition
time, using the later of acquisition and recorded receive simulation time.
An old pre-opening frame delivered after opening is excluded from both
recovery timing and recovered-identity comparison. The check
`no_loss_during_short_occlusion` covers closing through this fresh recovery,
including the time after opening. If recovery is absent, it covers the full
recovery window. A LOST before fresh recovery fails the check; matching both
the prior `track_id` and `target_uuid` on fresh recovery is also required.

Each short/long event reports PREDICT, LOST, HOVER, measured recovery, identity
before/after, diagnostic gaps and vehicle speed. Long events must show LOST and
HOVER before opening. After a long loss, any MEASURED or PREDICTED state before
a valid, independently confirmed explicit SELECT/RESET on
`/tracking/selection` fails `no_automatic_recovery_after_long_loss`. Controller
FOLLOW/PREDICT is checked independently starting 0.10 s after LOST, allowing
two 20 Hz ticks for a previously queued status; an unauthorized return fails
`no_tracking_control_before_reselection_after_long_loss`. These guards extend
beyond the normal recovery window through the confirmed command boundary,
or through trial end when no explicit operation is confirmed. Empty, invalid
or unconfirmed requests do not open that boundary.

The report retains `first_unrequested_measured_after_loss_s`,
`first_unrequested_predicted_after_loss_s`,
`first_unrequested_active_state_after_loss_s`,
`first_unrequested_tracking_control_after_loss_s`, and
`tracking_control_grace_after_loss_s` so these checks can be reviewed.
Braking uses odometry while HOVER persists and requires
speed at or below 0.30 m/s for at least 0.40 s within 2.0 s of HOVER. The
thresholds are configurable and are embedded in the report. An isolated slow
sample cannot pass; a stationary vehicle can satisfy holding but is explicitly
not counted as a demonstration of braking from motion.

Every event is retained as `PASS`, `FAIL` or `INCOMPLETE_EVIDENCE`. Missing topics,
read errors, missing shutter events, or missing arming/Offboard evidence prevent
an overall pass. This outcome covers the observed behavior in one trial; it
does not assert a ground-truth accuracy target or replace repeated paired
experiments. Preserve the original bag and all failed runs.

## Explicit reselection evidence

The managed trial's optional `--occlusions --reselect-after-loss` enables an
explicit test-script selection of a new task after the long event. The monitor
waits until at least FOLLOW +32 s, requires LOST/HOVER and one fresh real
detector box, and publishes a new UUID on `/tracking/selection`. It logs the
request and a matching MEASURED confirmation separately; see
[STAGE1_FLIGHT.md](STAGE1_FLIGHT.md) for the exact conditions and command.

The default long event opens at FOLLOW +28 s and its evaluator recovery window
ends at +31 s. The later explicit restart must not be counted as automatic
recovery, continued original identity or full ReID. Long-occlusion PASS requires
observed prediction, loss, HOVER, sustained low speed and no unrequested
measured/predicted state or tracking control after loss, followed by a confirmed
explicit new task and sustained tracking through trial end. Short-occlusion PASS requires observed recovery
from a post-opening acquisition with the same track/task identity, with no
LOST before that recovery.

The evaluator derives `explicit_reselection` from the bag's selection and
state records, rather than trusting the monitor's confirmation boolean. It
looks from LOST through trial end, so an intentional restart after the normal
recovery window remains observable. The original UUID comes from the last
identified state at or before LOST. SELECT is action code 0, CLEAR is 1 and
RESET is 2; CLEAR never authorizes a restart.

A candidate operation needs a positive source stamp and known receive time,
both at/after loss, with no more than 0.05 s future source skew. Its effective
request time is the later of source and receive. SELECT requires a nonempty
UUID different from the original, a matching category when supplied, and
either a positive track ID or finite box center with positive finite width
and height. RESET may omit the requested UUID but must still produce a new
task identity.

The first active state after that operation must itself confirm the new task:
MEASURED, received at/after the request, acquired at/after shutter opening,
with nonnegative measurement age plus transport age no greater than the
configured prediction limit (currently 0.75 s). It must have the correct
category, a positive track ID, and a nonempty UUID different from the original.
For SELECT the UUID must equal the requested UUID; a track-ID selection must
also match the requested track. A first old-UUID, predicted, stale or mismatched
state cannot be excused by a later correct measurement.

Each long event reports `explicit_reselection.confirmed`,
`original_target_uuid`, `requested_target_uuid`, `confirmed_target_uuid`,
`selection_time_s`, `confirmation_time_s`, `confirmation_image_stamp_s`,
`confirmed_track_id`, `action` (`SELECT` or `RESET`),
`selection_action_code`, `first_valid_request_s`, and `invalid_candidates`.
`first_explicit_reselection_s` is populated only for a confirmed operation.
An invalid or unconfirmed operation leaves the protection boundary closed.

Individual long-loss protective-hover checks can be true when the task never
restarts, but schema 3's overall long-event result also requires sustained
tracking after a confirmed explicit reselection. Without that confirmation,
this extra requirement has incomplete evidence. The final engineering summary
also requires the monitor's explicit request and confirmation together with
the bag-derived confirmed new UUID, full recorded-trial coverage, complete
setpoint classification, the requested PX4 mode, artifacts, and both categories
in both command modes. See
[STAGE1_ACCEPTANCE.md](STAGE1_ACCEPTANCE.md) for the full matrix and gates.

## Sustained tracking after reselection

A single new-UUID MEASURED confirmation is insufficient: a trial that follows
for 1.05 s and then remains LOST/HOVER must fail. Each long event includes
`post_reselection_tracking`, evaluated from its bag-derived new-task
confirmation through the full trial end. It does not stop after the first
successful five seconds or ignore a later loss.

Its nine required checks are:

| Check | Required evidence |
| --- | --- |
| `minimum_recording_duration` | At least 5 s from confirmation to trial end |
| `minimum_state_span` | At least 5 s between first and last recorded state |
| `minimum_control_span` | At least 5 s between first and last FOLLOW/PREDICT status |
| `same_target_active_states_only` | Every state is MEASURED/PREDICTED, has the confirmed UUID and category, and a positive track ID |
| `tracking_control_only_after_grace` | First FOLLOW/PREDICT arrives within 0.10 s; no other lifecycle is recorded after that grace |
| `continuous_state_evidence` | State sampling gaps, including the two interval boundaries, are at most 0.5 s |
| `continuous_control_evidence` | Control-status sampling gaps, including boundaries, are at most 0.5 s |
| `fresh_state_at_trial_end` | Last state is at most 0.5 s old, has known receive time and the same active identity, and its measurement age at trial end is at most 0.75 s |
| `tracking_control_at_trial_end` | Last status is FOLLOW/PREDICT and at most 0.5 s old |

Any later LOST, AMBIGUOUS, UNINITIALIZED, identity change, or control return to
HOVER/FAILSAFE invalidates the corresponding check even when fresh following
subsequently resumes. Prediction is allowed within the unchanged measurement
freshness bound; a recent publication of an old prediction cannot certify a
fresh target at the trial tail. The measurement-age calculation adds reported
prediction age to elapsed time from the state's header through trial end.

The report preserves thresholds, observed duration, state/control spans,
sampling-gap maxima, final evidence ages, counts by state/lifecycle,
`first_invalid_state_s`, `first_uuid_mismatch_s`, and
`first_nontracking_control_after_grace_s`. Its result is PASS only when every
required check is exactly true; observed violations fail, and missing evidence
remains incomplete. The long-event check
`sustained_tracking_after_reselection` is required in the evaluator result and
in the engineering summary. The summary independently validates durations,
tail ages, identity/time agreement and strict thresholds, so a standalone PASS
label or an older schema cannot satisfy this gate.
