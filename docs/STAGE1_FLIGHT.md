# Stage-one PX4 flight graph

The stationary `stage1_single_*` worlds are sensor tests. Flight acceptance uses
`stage1_flight_person.sdf` or `stage1_flight_car.sdf`: a single Gazebo world named
`stage1_flight` contains the real PX4 x500 model `stage1_uav`, one visual target,
and a collisionless rendering shutter. PX4 attaches to the existing vehicle
with `PX4_GZ_MODEL_NAME=stage1_uav` and `PX4_GZ_STANDALONE=1`.

## Camera and frames

The stock PX4 `x500_depth` includes an OakD-Lite with a 1920x1080 RGB camera
(HFOV 1.204) and a 640x480 depth camera (HFOV 1.274). Those images cannot be
treated as aligned RGB-D. The project's `x500_stage1` inherits the normal x500
motors, body, IMU, magnetometer, barometer and GPS, and adds one `rgbd_camera`.
Both images therefore use the same 640x480 projection, stamp and origin.

The sensor is at `(0.13233, 0, 0.26078)` metres in body FLU, matching the stock
OakD sensor origin, and points down by 0.35 rad. The optical frame is named
`camera_link` for compatibility with the common tracking interface; its axes
are right/down/forward. `flight_tf` publishes:

```
map -- PX4 ENU/FLU Odometry, dynamic --> base_link
base_link -- physical mount + optical basis, fixed --> camera_link
```

It uses only `/vehicle/odometry`. There is no fixed world-to-camera transform
and no simulator pose input to the tracking graph. Gazebo publishes the RGB-D
topics `/camera/rgbd/{image,depth_image,camera_info}`; the flight bridge maps
them to the stable ROS camera topics. A Harmonic runtime probe confirmed
`frame_id=camera_link`, `fx=fy=465.741156`, `cx=320`, `cy=240`.

## One command source and supervised takeoff

```
controller /tracking/command
  -> flight_supervisor /tracking/flight_command
  -> px4_adapter /fmu/in/{offboard_control_mode,trajectory_setpoint}
```

The adapter requires fresh armed/OFFBOARD status. The supervisor starts
disabled unless `auto_start=true` is explicit; it also requires
`simulation_only=true` and `use_sim_time=true`. It waits for fresh odometry,
passing preflight checks, and 1.2 seconds of adapter heartbeats before sending
normal Offboard/arm VehicleCommands. It climbs 3 m above the initial PX4 local
height while holding the initial x/y and ENU yaw zero, limits horizontal speed
to 0.8 m/s and vertical speed to 0.7 m/s, and settles before forwarding fresh
visual controller commands. Missing/stale/invalid visual commands produce
zero-velocity hover. An Offboard exit, disarm or stale PX4 state latches
`ABORTED`; it does not repeatedly rearm the vehicle.

`/tracking/flight_phase` is a `std_msgs/String` containing `PHASE: reason`.
Phases are `DISABLED`, `WAITING`, `REQUEST_OFFBOARD`, `TAKEOFF`, `FOLLOW`,
`HOLD`, and `ABORTED`. Separate the phase at the first colon when monitoring.

## Run in WSL

For an isolated trial with recording and the event monitor, run from the
Linux project root after building and sourcing the workspace:

```bash
bash scripts/run_stage1_trial.sh \
  --class person --name person_trial_01 --duration 45 \
  --occlusions --short-occlusion-s 0.2
```

Use `--class car` for the car configuration and a new result name for every
trial. The runner refuses to overwrite an existing result directory. It owns
Gazebo, PX4, the Agent, ROS nodes, the monitor and recording. Its default
`--render-backend egl` uses headless EGL; on this host the trial environment
sets `LP_NUM_THREADS=4` and `OMP_NUM_THREADS=2`. Camera updates are 10 Hz with
scene shadows disabled. The optional `wslg` backend is diagnostic: an available
D3D12 renderer was slower in the full flight run and is not the tested default.
Run one simulator at a time.

The current car configuration uses `models/yolo11s.pt`, CPU inference with
`inference_image_size: 480`, and a 5 Hz inference cap. An `on_predict_start`
callback reapplies `inference_threads: 2` after Ultralytics' lazy backend setup;
diagnostics record the actual PyTorch thread count. A 50 Hz lightweight poll
uses the latest image and the 5 Hz start-to-start cap, avoiding extra 0.2 s
timer quantization when an inference overruns one period. It does not create
an inference queue. The aligned RGB-D sensor and calibration remain 640x480.
Use the parameter snapshot in each result directory for historical trials.
The latest 480 configuration requires its own flight result; the offline
[OpenVINO comparison](OPENVINO_CPU_COMPARISON.md) is not flight acceptance.

Manual component operation is also available:

Build and source the ROS workspace first, including the console scripts
`flight_tf`, `flight_supervisor`, `scenario_motion` and the `x500_stage1` model. Run these in
four terminals from the Linux project root, with the same `GZ_PARTITION`
(default `stage1_flight`) and `ROS_DOMAIN_ID` (default `0`):

```bash
bash scripts/run_stage1_flight.sh gazebo person
bash scripts/run_stage1_flight.sh agent person
bash scripts/run_stage1_flight.sh px4 person
STAGE1_AUTO_START=true bash scripts/run_stage1_flight.sh ros person
```

Use `car` in all four commands for the car world. No stationary-camera launch,
fake vehicle or controlled-observation publisher may run alongside this graph.
The default control mode is velocity. Set `STAGE1_COMMAND_MODE=position` on
the ROS command to evaluate position commands; the launch argument is applied
only to the visual controller. The supervised takeoff remains a velocity
phase. For the managed trial, use `--command-mode position`, for example:

```bash
bash scripts/run_stage1_trial.sh \
  --class person --name person_position_trial_01 --duration 45 \
  --command-mode position --occlusions --short-occlusion-s 0.2
```

During FOLLOW the supervisor forwards the selected visual command mode;
takeoff, missing/stale visual commands and HOLD use bounded/zero velocity
commands. Position-mode trials can therefore contain velocity messages in
those phases. Each PX4 setpoint activates only one position/velocity field
set; inactive fields are NaN. Inspect the phase and `run_config.json` rather
than assuming every message in a position trial is a position command.

## Position-mode reference generation

The ROS controller defaults to `slew_position: true`, also set explicitly in
the person/car parameter files. The portable core's `FollowConfig` retains
its `false` default for callers that explicitly want the direct desired
position; the ROS flight configuration enables the moving-reference behavior.

In that mode, the controller integrates from its previous position reference,
initializing it from the actual vehicle position when no prior reference is
available. Target velocity feedforward and proportional error from the desired
follow position to that previous reference drive the nominal reference speed:

```text
v_nominal = speed_then_accel_limit(Kff * v_target + Kp * deadzone(p_desired - p_ref_previous))
p_proposed = p_ref_previous + v_nominal * dt
p_ref = p_vehicle + clip_per_axis(p_proposed - p_vehicle, max_position_lead_m)
```

The nominal speed/acceleration limits use `max_velocity_mps` and
`max_acceleration_mps2`. `max_position_lead_m: [1.0, 1.0, 0.5]` is a hard
per-axis ENU bound relative to the **actual** vehicle position: at most 1 m
East, 1 m North and 0.5 m Up in either direction. It is not a 1 m spherical
radius or a bound relative to the previous reference. Integrating the previous
reference preserves useful lead over a moving target; restarting the
integration from the vehicle every tick would leave only a tiny dt-sized lead.

When actual vehicle motion makes the hard lead bound conflict with nominal
slew limits, the lead bound takes priority. Consequently the final projected
reference does not have an unconditional speed/acceleration derivative
guarantee. The controller separately limits the realized rate before updating
its internal slew-velocity state, so an exceptional projection rate is not
stored as the next nominal state. PX4 still receives position-only setpoints
in healthy position FOLLOW; these internal velocities are not simultaneously
published as PX4 velocity setpoints.

The retained `stage1_final_v1_car_position` trial exposed the need for this
behavior: after reselection, a roughly 3.3 m position-reference step caused
about 24 degrees of nose-down pitch and loss of the car from the camera field
of view. With the reference fix, `car_flight_v08_position` reached the trial
end in FOLLOW and its schema-3 offline evaluation reports PASS. This is one
position-mode probe; the four-condition `stage1_final_v2` matrix remains pending.

The flight launch requests reliable KEEP_LAST(1) RGB, depth and CameraInfo,
matching the Gazebo bridge. The detector's `image_reliability` parameter also
supports `best_effort` for camera deployments whose publishers offer that QoS.
The monitor's RGB input is reliable with depth 1. See
[ROS2_SIMULATION.md](ROS2_SIMULATION.md) for the recorded delivery diagnosis.

`px4_stage1_startup.sh` runs PX4's normal `rcS`, then configures the deliberately
absent RC/GCS with `COM_RC_IN_MODE=4` and `NAV_DLL_ACT=0`. This ordering matters:
PX4 v1.17 applies environment overrides before airframe defaults; the x500
airframe's later `NAV_DLL_ACT=2` can otherwise restore a GCS requirement. All
estimator, Offboard and remaining arming checks stay enabled.

The target models use Gazebo `VelocityControl` with zero initial velocity.
They are visual/depth scene actors with gravity and collisions disabled, so
ground-contact friction cannot tip the mesh or change the prescribed speed.
This simplification applies only to test targets; the x500 retains real
Gazebo rigid-body, motor and sensor dynamics under the PX4 flight controller.
`scenario_motion` publishes body-frame Twist through `/scenario/target/cmd_vel`,
starting once after the first `FOLLOW` phase. A two-second speed ramp reaches
0.5 m/s, followed by straight segments and gentle left/right turns (at most
0.07 rad/s). Its only inputs are the flight phase and simulation clock.
The target keeps moving through visual `HOLD` and stops on `ABORTED`; losing
the target therefore never pauses the physical test environment. The car
starts at x=11 m, yaw=0, with the asset's forward axis along model +X.
The stationary sensor worlds remain stationary unless this explicit motion
topic is supplied. The `vision_shutter` starts at z=-50; moving that visual to
the aircraft's forward line of sight creates an actual rendered occlusion.
Neither operation supplies observations to the tracker.

## Occlusion duration and fresh recovery

With `--occlusions`, the short rendered shutter interval starts at FOLLOW
+12 s and lasts `--short-occlusion-s` (default **0.2 s**). The runner accepts
values strictly between 0 and 0.75 s. The long interval remains FOLLOW +25
to +28 s, or **3.0 s**. These are requested physical shutter intervals; the
recorded events and candidate-free images must corroborate the occlusion.

The estimator's 0.75 s prediction limit applies to the age of the last valid
three-dimensional measurement. A 5 Hz CPU inference cap, sensor sampling,
frame delivery and inference time can make the measurement gap longer than
the shutter interval. Historical 0.4 s shutter trials contained about 0.8 s
between valid-depth acquisitions. Once measurement age exceeds 0.75 s,
LOST/HOVER is the correct response. A 0.4 s physical occlusion therefore has
no general guarantee of prediction-only recovery on this configuration.
The current 0.2 s/3.0 s test conditions do not change that timeout.

For a short-occlusion pass, recovery must use a MEASURED state whose image
acquisition timestamp is at or after shutter opening. Receiving an older
image after opening does not count. From closing through that fresh recovery,
no LOST state is allowed, and the recovered `track_id` and `target_uuid` must
match the pre-occlusion target. If fresh recovery is absent, the evaluator
checks for loss through the end of its recovery window and cannot certify
identity-preserving recovery. A loss still requires explicit selection even
when the requested shutter duration was called short.

Keep all historical 0.4 s successes and failures with their original configs
and evaluator versions; they do not certify the newer freshness checks.
The person/car by velocity/position trials using 0.2 s/3.0 s need their own
recorded results before any condition is declared passed.

## Explicit selection after long loss

Long loss latches LOST/HOVER and requires an explicit new selection. Opening
the shutter does not authorize switching to a fresh same-class detection.
To exercise the user/test-script selection interface, opt in explicitly:

```bash
bash scripts/run_stage1_trial.sh \
  --class car --name car_reselection_trial_01 --duration 45 \
  --occlusions --short-occlusion-s 0.2 --reselect-after-loss
```

`--reselect-after-loss` requires `--occlusions` and is disabled by default.
The monitor waits until at least 32 simulated seconds after the first FOLLOW,
after the scheduled long shutter interval at +25 to +28 s. It sends one
`TargetSelection` on `/tracking/selection` only while the estimator is LOST,
the controller is HOVER, and a real detector diagnostic no older than 0.4 s
contains exactly one candidate with valid depth. The selection uses that
candidate's image box, a **new** target UUID, and source
`TEST_SCRIPT_EXPLICIT_RESELECTION`. It uses no Gazebo identity or target pose.

The monitor records `explicit_reselection_requested`, then
`explicit_reselection_confirmed` only when a MEASURED state carries that UUID.
`summary.json` retains the enabled/requested/confirmed fields, and the runner
records `/tracking/selection` in the bag. A missing eligible candidate leaves
the request/confirmation absent; enabling the flag alone does not establish
success. This starts a new selected task, not automatic ReID or evidence that
the original identity survived long loss. The +32 s gate is later than the
evaluator's default recovery window after the long event (+28 to +31 s), so
the explicit restart is kept separate from that event's recovery evidence.

The schema-3 evaluator independently checks `/tracking/selection` and target
states from the bag. A valid selection/reset must be followed by a first
active state that is a fresh MEASURED confirmation with a new target UUID,
the expected category and valid track ID. A stale or old-UUID active state
cannot be retroactively authorized by a later matching measurement. Monitor
event/summary flags alone do not establish this confirmation.

The evaluator then checks the new task from confirmation through the full
recorded trial end: at least 5 s of state/control evidence, the same UUID and
category throughout, only MEASURED/PREDICTED states, and continuous
FOLLOW/PREDICT controller status after the 0.10 s transition grace. State and
control evidence gaps and final sample ages must be at most 0.5 s; the final
target measurement must also satisfy the unchanged 0.75 s freshness limit.
A later LOST or return to HOVER invalidates sustained recovery even if the
first confirmation or the first five seconds succeeded. The long-event
`sustained_tracking_after_reselection` gate is required for PASS. See
[STAGE1_FLIGHT_EVALUATION.md](STAGE1_FLIGHT_EVALUATION.md) for all exact checks,
evaluation commands and timebase rules.

The model pose streams `/ground_truth/poses` and
`/ground_truth/vehicle_poses` are bridged only for recording and offline
evaluation. Runtime tracking, control, TF and the flight supervisor do not
subscribe to them. Compute true relative-distance metrics from both Gazebo
pose streams so that an EKF local-origin offset is not mistaken for error.
