# Interface contract

The message package is the boundary between perception, estimation, control,
and vehicle integration. A node may be replaced without changing the other
nodes when it preserves this contract.

## Topics

| Topic | Type | Publisher | Consumer | Required semantics |
| --- | --- | --- | --- | --- |
| `/tracking/observations` | `uav_tracking_interfaces/msg/TargetObservation` | detector | estimator | One message per candidate observation. `header.stamp` is the image acquisition time. `position_camera_m` is valid only when `depth_valid=true`; depth ratio/spread are carried for adaptive measurement noise. |
| `/tracking/selection` | `uav_tracking_interfaces/msg/TargetSelection` | UI/test script | estimator | Optional in single-instance mode. In designated-instance mode, `ACTION_SELECT` initializes the target by `track_id` or the supplied bounding-box selection and `ACTION_CLEAR` invalidates it. |
| `/tracking/state` | `uav_tracking_interfaces/msg/TargetState` | estimator | controller/logger | `header.frame_id` is `state_frame`. A predicted state must set `state=STATE_PREDICTED` and increment `prediction_age_s`. |
| `/tracking/command` | `uav_tracking_interfaces/msg/TrackingCommand` | controller | PX4 adapter | The command is expressed in `header.frame_id`; the adapter performs ENU/NED conversion. `valid=false` is a hold/failsafe request, not permission to publish stale motion. |
| `/tracking/status` | `uav_tracking_interfaces/msg/TrackingStatus` | controller | supervisor/logger | Lifecycle and failure reasons are logged for every trial. Adapter health is logged separately and must not create a second publisher for this topic. |

The PX4 adapter also subscribes to `/fmu/out/vehicle_odometry` and publishes
the controller's vehicle-state input as `nav_msgs/Odometry` on
`/vehicle/odometry`: pose is ENU in `map`, and twist is body FLU in
`child_frame_id=base_link`. The controller rotates twist with the full pose
attitude to obtain world-frame velocity for the portable algorithm.

## Time and frames

- Use ROS time (`use_sim_time=true`) for every message in simulation.
- Preserve sensor acquisition time; do not replace it with callback time.
- The camera optical frame follows REP-103. Transform the camera point with a
  timestamped TF lookup before filtering it.
- The estimator publishes in one stable local/world frame (`map` by default).
- PX4's NED convention is isolated in `uav_tracking_px4_adapter`; no core or
  controller node should silently negate axes.
- A stale observation is rejected when its age exceeds the configured limit.
- Controller inputs and PX4 commands require positive source timestamps and
  an initialized ROS clock. Future clock skew is tolerated up to 50 ms;
  tolerated future stamps contribute zero transport age.
- The estimator also drops out-of-order frames after a newer timestamp has
  already been processed; this prevents delayed sensor packets from moving the
  filter backwards in time.
- Camera updates commit at acquisition time. Output timer ticks project a
  copy of the filter to the current ROS time, without advancing the committed
  filter or counting a missed camera frame. A normally delayed, in-order image
  can therefore still be accepted after a newer output prediction.
- The default observation-age limit is 0.60 s. Loss occurs after 0.75 s without
  an accepted three-dimensional measurement, independently of camera/output
  callback frequency; diagnostic tracks are retained for 3.0 s. Frame-based
  coast limits remain available to portable callers, but ROS uses seconds.
- Once an established task enters `LOST`, both modes require explicit
  reselection or reset. A delayed acquisition cannot undo that loss even if
  its acquisition time predates the timer tick that detected the timeout.
- A candidate with invalid depth may refresh 2-D association, but it cannot
  refresh the last valid 3-D measurement timestamp; the published state stays
  `STATE_PREDICTED` until the prediction timeout.
- For a measured output, `header.stamp` is the acquisition time; for an
  extrapolated output it is the projection time. `prediction_age_s` is the time
  from that output timestamp to the last accepted 3-D measurement. A consumer
  adds message transport age to obtain measurement age at the current time.
  `covariance` is the full row-major 6x6 covariance for
  `[x,y,z,vx,vy,vz]`, including position/velocity cross terms.

## QoS starting point

Sensor observations and states should use best-effort, depth 5, volatile QoS
when sourced from a high-rate sensor. Commands and status should use reliable,
depth 10, volatile QoS. Record the actual QoS in the experiment log because a
QoS mismatch can look like an estimator failure.

## Identity modes

`target_profile=single_instance` describes the core experiment scope. The
estimator uses `target_mode=auto_unique`, matching the portable core's
`TargetMode.AUTO_UNIQUE`: it selects only one confirmed eligible candidate and
reports ambiguity otherwise. Any subsequent frame containing several
eligible detector candidates also pauses the task, preserving its UUID and
track ID. `STATE_AMBIGUOUS` is explicit on `/tracking/state`; the controller
publishes invalid motion and `LIFECYCLE_HOVER` with reason
`target_ambiguous`. Timer projections and empty frames cannot clear this
pause. A single candidate associated with the original selected track can
resume the task before the loss timeout; another remaining track cannot.
Unconfirmed candidates and candidates lacking depth still count toward
ambiguity. It does not claim identity persistence among same-class objects.
The extension uses `target_mode=locked_target`, matching
`TargetMode.LOCKED_TARGET`, and requires an explicit `TargetSelection` plus a
separate association implementation. A nearest same-class detection must not
silently replace the selected target after loss. `target_uuid` is the task
identity; `track_id` remains a transient tracker identifier.
