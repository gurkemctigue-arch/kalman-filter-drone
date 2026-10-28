# Gazebo visual assets and detector evidence

The runtime detector consumes rendered RGB images. Model names, entity IDs and
Gazebo pose truth are not detector inputs. The target wrappers expose pose truth
for offline evaluation only. The initial TrajectoryFollower motion was later
replaced by scenario commands to Gazebo VelocityControl, with target gravity
and collisions disabled. This prevents ground friction from stopping or tipping
the visual test targets. PX4 vehicle physics remain active; see
[STAGE1_FLIGHT.md](STAGE1_FLIGHT.md).

## Sources and redistribution

The following original archives are vendored unchanged below
`ros2_ws/src/uav_tracking_bringup/models/`. Each Fuel metadata response identifies
its license as **Creative Commons Zero v1.0 Universal (CC0 1.0)**:
<https://creativecommons.org/publicdomain/zero/1.0/>.

| Local directory | Pinned OpenRobotics Fuel model | Author in model.config | Archive SHA256 |
| --- | --- | --- | --- |
| `fuel_walking_person` | [Walking person, v3](https://fuel.gazebosim.org/1.0/OpenRobotics/models/Walking%20person/3/Walking%20person.zip) | Marina Kollmitz; created with Makehuman | `89cbcc1fd470338823b9cdf82c79aaabd4c86d72935386065deccf1e481a5178` |
| `fuel_prius_hybrid` | [Prius Hybrid, v3](https://fuel.gazebosim.org/1.0/OpenRobotics/models/Prius%20Hybrid/3/Prius%20Hybrid.zip) | Ian Chen | `ea5d10f1a2c4e89f8a0441f2c9e623575ecd9a7670c81c3f23bb9204ca32b1ab` |
| `fuel_hatchback` | [Hatchback, v3](https://fuel.gazebosim.org/1.0/OpenRobotics/models/Hatchback/3/Hatchback.zip) | See original model.config | `dcd34e68cf43863991768c3ddbdeb322d6ee8bddaa01aa7da8267bbacfdb60ed` |
| `fuel_suv` | [SUV, v4](https://fuel.gazebosim.org/1.0/OpenRobotics/models/SUV/4/SUV.zip) | See original model.config | `729c066a1a2c1ba75a4453050a3c5022f02ccdfa75a4d4db4bab56104e3a1d54` |

The download script preserves archives and upstream metadata JSON under
`results/asset_validation/source_archives/`. The generated target wrappers use
direct mesh URIs: the upstream models sometimes refer to their original Fuel
directory name, so including their unmodified model.sdf with our vendor directory
name would fail to resolve resources. Relative mesh-to-texture paths remain
unchanged. Install the complete resource directory hierarchy.

## Validation

Run `bash scripts/run_assetcheck.sh` inside the installed ROS/Gazebo environment.
It uses `GZ_PARTITION=assetcheck` and `ROS_DOMAIN_ID=73`, starts only a Gazebo
camera world and RGB bridges, and never starts PX4. It records real images after
30 rendered frames (early renderer frames can precede texture uploads), then
invokes unmodified YOLO11n at 320 and 640 pixels. It stores input images,
annotated images, frame counts, detections and the weights SHA256 in
`results/asset_validation/`.

The tested weights hash is
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
Walking person v3 was detected as `person` at confidence 0.847 (320) and 0.908
(640) from a 3 m high camera, at 6 m range and 0.30 rad downward pitch.

Prius Hybrid v3 produced `car` confidence 0.852 (320) and 0.539 (640) from a
front-side view at 9 m range and 0.20 rad downward pitch. Other alternatives were
also tested rather than silently assumed suitable: Hatchback v3 was classified
as `airplane`; SUV v4 mostly as `truck`/`bus` from that viewpoint. Their images and
all predictions remain in the evidence JSON.

`bash scripts/run_asset_viewpoints.sh` additionally reproduces 16 static Prius
views with the flight camera projection (horizontal FOV 1.204 rad, pitch 0.35
rad, camera height 3 m), eight headings at 45 degree intervals, and ranges of
5 m and 9 m. The generated world, RGB images and predictions remain in
`results/asset_validation/flight_viewpoints/`. This check exposed severe domain
shift at 5 m; most headings fail or are classified as airplanes. At 9 m,
640-pixel inference detects `car` above 0.4 for seven of eight headings. One
diagonal view still fails. Examples at 9 m: rear 0.618, side views 0.864/0.834,
front-side views 0.596/0.652; direct front gives 0.837 at 320 but 0.429 at 640.
The old dark `stage1_single_car.sdf` camera view also fails and is retained under
`results/asset_validation/stage1_car/`.

Therefore, the car flight experiment begins with about 9 m following distance,
640-pixel inference and confidence threshold **0.45**. The 0.4 count above only
describes these diagnostic predictions; it is not a lowered runtime threshold.
Use the measured operating conditions and short occlusion behavior; do not claim
viewpoint-independent car detection or reinterpret false classes as cars. These
snapshots do not establish Precision/Recall.

## Model frames, physical sizes and observation anchor

The `target_car` wrapper has a 4.60 x 1.80 x 1.50 m collision box, centered at
model-local `(0, 0, 0.75)` m. Its inertial center is `(0, 0, 0.70)` m and mass is
1200 kg. Its model origin is at ground level, not at the physical mass center.
Model-local **+X is the car's front, +Y is left, +Z is up**. The vendor OBJ's
native front is -Y; a visual yaw of +pi/2 aligns it with model +X. The mesh has a
0.01 scale and 0.02 m vertical offset. These simplified collision and inertial
values support scripted motion; they are not a validated vehicle dynamics model.

The `target_person` wrapper uses a 0.45 x 0.35 x 1.70 m collision box centered
at `(0, 0, 0.85)` m, 70 kg mass and inertial center `(0, 0, 0.95)` m. The model
origin is also at ground level. The full textured mesh retains its original
shape, so collision dimensions are not a tight rendered bounding volume.

**A detected RGB-D target position is a visible-surface observation anchor.**
The implementation obtains the depth median of valid pixels in the detection
ROI, backprojects the 2D bounding-box center with that optical-axis depth, then
transforms the resulting point into the world frame:

`p_observed = T_world_camera * (Z_median * inverse(K) * [u_box, v_box, 1])`.

It is not the model origin, a 3D box center, a mass center or a semantic keypoint.
Because depth is pooled across the ROI, the resulting ray/depth pair need not
even coincide with one actual rendered surface pixel. Background contamination,
car hood/windshield shape, yaw and pitch can all move this anchor. KF estimates
smooth this same observable anchor; the filter does not infer an unseen object
center from the mesh dimensions.

For the early flight setup, the drone's forward RGB-D optical center was about
3.25 m above ground and the car model origin started 9 m ahead. With car yaw pi,
its nose pointed toward the camera. The front collision extent was then
about `9 - 4.6/2 = 6.7` m ahead of the drone body origin (slightly less from the
forward-mounted camera). A box-center/median-depth observation typically falls
on the front body, hood or windshield, so its range can be roughly 1 to 2.3 m
shorter than the model-origin range. Its height is above the ground-level model
origin as well. Exact offsets depend on the actual view and must be measured
from recorded RGB-D, not asserted to be exactly 2.3 m.

Consequently, controller `desired_distance_m: 9.0` means distance to this visual
anchor. It does not guarantee 9 m to the car model origin. Placing an initial car
origin around 11 m ahead can yield a visible surface near 9 m, but that is a
scene-initialization approximation and does not change observation semantics.
The current flight car starts with its model origin 11 m ahead and yaw zero,
so its rear faces the following aircraft. Collision geometry is disabled for
the scripted visual target; the dimensions still explain the difference
between a visible surface anchor and model origin.
No runtime algorithm may look up Gazebo mesh poses or dimensions to secretly
subtract a truth-derived offset.

Offline evaluation must state the reference point. A residual against the
ground-level model origin includes an expected, viewpoint-dependent geometric
bias. Report that bias separately from random error; do not describe it as
zero-mean sensor noise or tune KF covariance to conceal it. If a ground-truth
center RMSE is required, define and validate a center-estimation method first.
When comparing raw/EMA/fixed/adaptive KF, keep the same visual-anchor definition
and clearly distinguish model-reference error, residual bias, variance and
temporal smoothness. Changing visible faces during turns can also affect the
apparent anchor velocity without an equal change in object-center velocity.

These are visual asset smoke checks, not a detection benchmark or closed-loop
acceptance. Viewpoint, motion, range, lighting and domain shift must be assessed
in the real onboard runs. A rendered but weakly detected asset must not be
replaced by truth-derived bounding boxes.
