# YOLO11 car robustness comparison

The `car_flight_v01` run used YOLO11n at 640 pixels, confidence 0.45, camera
pitch 0.35 rad and about 9 m desired distance to the RGB-D surface anchor. It
completed basic flight, but car dropouts prevented a valid long-occlusion
prediction/loss test. This offline comparison diagnoses appearance robustness;
it does not establish a new flight acceptance pass.

## Inputs and method

`scripts/run_car_detector_comparison.sh` reads the **original**
`/camera/color/image_raw` Image messages from
`/root/uav_tracking_project/results/car_flight_v01/rosbag`. It samples every
0.5 simulated seconds starting at the recorded first FOLLOW time, 25.6 s.
It preserves raw PNGs and an acquisition/record timestamp manifest under
`results/car_detector_comparison/`. No annotated video or screenshots are
used as inference inputs. The original compressed bag remains unchanged; its
decompression cache is temporary and removed after extraction.

The additional 16 unannotated viewpoint PNGs come from the saved independent
Gazebo experiment: eight car headings at 45 degree intervals and 5/9 m ranges,
with the flight camera projection. There is no new rendering during this
comparison. See [VISUAL_ASSETS.md](VISUAL_ASSETS.md) for their provenance.

Both models use unchanged pretrained weights, the same input frames, CPU,
default Ultralytics all-class prediction/NMS, and postfilter
for COCO car class 2 at **0.45** confidence, matching `detector_node.py`.
640 and 480 inference sizes are compared. Timing includes each prediction call
after warmup and excludes disk reads and annotation drawing. These are isolated
offline CPU timings, not full ROS/PX4 end-to-end latency.

The historical script requested two PyTorch threads before lazy backend
initialization but did not record the actual count during prediction. A later
audit found that Ultralytics `select_device('cpu')` can overwrite that limit.
The archived timing column below therefore is **not a verified two-thread
benchmark**; detection counts and failure images remain valid observations.
The controlled two-thread comparison, including end-to-end preprocessing/NMS
cost, is in [OPENVINO_CPU_COMPARISON.md](OPENVINO_CPU_COMPARISON.md).

## Observations

The script's requested-shutter flag leaves 80 nominally unoccluded sampled
frames. Two of these, **38.1 s and 53.6 s**, are still completely black in the
raw rendered image at shutter release. They remain in the reported counts and
failure lists; visually confirming their occlusion explains the two 640-small
failures without silently removing them.

| Model / inference size | Car detected in nominally unoccluded flight frames | Static viewpoints | CPU median / p95 |
| --- | ---: | ---: | ---: |
| YOLO11n / 640 | 54/80 (67.5%) | 7/16 | 0.042 / 0.045 s |
| YOLO11s / 640 | 78/80 (97.5%) | 15/16 | 0.097 / 0.111 s |
| YOLO11n / 480 | 59/80 (73.75%) | 4/16 | 0.030 / 0.032 s |
| YOLO11s / 480 | 77/80 (96.25%) | 14/16 | 0.065 / 0.086 s |

At 640 pixels, YOLO11s detects all 78 visibly unoccluded sampled flight frames.
Its remaining static failure is `view4.png`, a direct front view at 5 m; all
eight 9 m headings are detected. At 480 pixels it also misses flight frame
60.6 s and the 5 m direct rear view, so 640 is the preferred first runtime
comparison. Full per-image scores, class predictions, timings and failure
files remain in `results/car_detector_comparison/comparison.json`; representative
annotations are stored separately from the raw inputs.

Subsequent full-flight profiling of YOLO11s/640 (`car_flight_v03`) showed a
median inference wall duration of 0.188 s and p95 image-to-completion latency
of 0.413 s. At a 5 Hz schedule, inferences longer than one period cause dropped
scheduling ticks and can exhaust the 0.75 s freshness budget. That run is
retained as a failed trial. An interim runtime configuration used
**YOLO11s/480** with the same 640x480 RGB-D camera, confidence threshold,
5 Hz cap and unchanged safety timeouts. A restored **PyTorch YOLO11s/640**
probe added two-thread enforcement after lazy backend setup and a 50 Hz
latest-image poll with the same 5 Hz inference cap, but still reached LOST
under late completed measurements. The current candidate is again
**PyTorch YOLO11s/480**, retaining that callback and scheduling fix.
Diagnostics record the actual thread count. Its flight result is pending;
the 0.75 s prediction and 0.60 s observation-age limits remain unchanged.

## Minimal runtime candidate

The initial candidate changed only the car checkpoint to **YOLO11s**, retaining 640-pixel inference,
confidence 0.45, desired surface distance 9 m, two inference threads and the
existing 5 Hz inference cap. The median/p95 offline timing leaves room within
the 0.2 s inference period in an isolated benchmark, but historical thread
counts were not verified and full-flight load must still be measured. The
new verified two-thread 640 PyTorch result is 118.3/141.3 ms median/p95 for
common preprocessing, inference, NMS and box scaling. OpenVINO FP32 gave
112.6/134.8 ms, only about a 5% median improvement, so it remains an isolated
experiment rather than the current flight backend.
No threshold, loss timeout, association rule or ground-truth interface needs
to change to obtain the measured offline gain.

The downloaded checkpoint is `models/yolo11s.pt` in the Windows project,
visible in WSL as `/mnt/d/基于yolo和卡尔曼滤波/models/yolo11s.pt`. For a native
Linux project copy, copy/install it and set `model_path` to the corresponding
file, for example `/root/uav_tracking_project/models/yolo11s.pt`, or install it
as a bringup resource before using a relative model path.

Source:
<https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt>

SHA-256:
`85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5`.

These counts measure detection availability on one sampled run and one small
view set. They are not Precision, Recall, mAP or proof of broad generalization.
Keep `car_flight_v01` and its failed long-occlusion result. Re-run the same real
flight and rendered occlusions with the new checkpoint before claiming the
car condition passed. No model retraining or truth-derived runtime boxes were
used in this comparison.
