# OpenVINO CPU comparison for YOLO11s

The 2026-10-26 isolated comparison found only a **5–7%** median latency
improvement from OpenVINO FP32 over PyTorch when both were genuinely limited
to two inference threads. This is insufficient evidence to replace the
current PyTorch path. Keep the detector's new callback that reapplies its
thread limit after Ultralytics initializes the backend. No production
detector, configuration, ROS package dependency or simulator was changed by
this investigation.

## Inputs and method

The comparison used the original 80 nominally unoccluded raw RGB frames from
`car_flight_v01` and the same 16 saved static viewpoints used in
[CAR_DETECTOR_COMPARISON.md](CAR_DETECTOR_COMPARISON.md). Inputs had no boxes,
labels or video overlays. All images were loaded before timing.

For each size, both backends used identical LetterBox, BGR-to-RGB, CHW FP32
normalization, the installed Ultralytics NMS and box scaling. NMS retained its
runtime defaults: all classes, confidence 0.25, IoU 0.7, maximum 300 boxes.
Only afterward were COCO class 2 and confidence >= 0.45 selected. The measured
end-to-end interval includes preprocessing, network inference, NMS and box
scaling; it excludes image IO, export, compilation, warmup and plotting. It
does not measure ROS delivery, depth processing or live sensor-to-state delay.
Backend order alternated per image. Each backend had three common-pipeline
warmups before the measured frames.

The 640x480 sensor images have a 4:3 aspect ratio. To preserve the existing
PyTorch `rect=True` inputs, the static OpenVINO model shapes are:

| Requested inference size | Actual BCHW tensor |
|---|---|
| 480 | 1 x 3 x 384 x 480 |
| 640 | 1 x 3 x 480 x 640 |

A square 480x480 export would change padding and computation, so it was not
used as a supposedly equivalent backend comparison. The camera resolution and
calibration were unchanged.

The host was the WSL2 Intel Core i5-13500H environment, exposing 16 logical
CPUs. PyTorch's actual thread count during timing was 2; interop threads were
1, and OpenCV threads were 1. OpenVINO compilation explicitly used CPU,
`INFERENCE_NUM_THREADS=2`, `NUM_STREAMS=1`, `PERFORMANCE_HINT=LATENCY` and
`INFERENCE_PRECISION_HINT=float32`. The compiled model confirmed all four
relevant device/thread/stream/precision properties. No affinity restriction
was required. No Gazebo or other benchmark ran concurrently.

## Results

These are the 80 raw-flight-frame results. Latencies are milliseconds.

| Size | Backend | End-to-end median / p95 | Network median / p95 | Car detections |
|---|---|---:|---:|---:|
| 480 | PyTorch | 74.32 / 83.61 | 72.88 / 82.20 | 77/80 |
| 480 | OpenVINO FP32 | 69.04 / 78.03 | 67.39 / 76.46 | 77/80 |
| 640 | PyTorch | 118.32 / 141.26 | 116.70 / 138.72 | 78/80 |
| 640 | OpenVINO FP32 | 112.57 / 134.76 | 110.79 / 132.62 | 78/80 |

The median reductions were 7.1% at 480 and 4.9% at 640. Each row is one
96-image pass, with its 80 flight images shown here; this is an engineering
comparison, not a statistically replicated performance claim. The final JSON
also retains maxima and every per-image time, including slow samples.

On the 16 viewpoints, PyTorch/OpenVINO both detected 14/16 at 480 and 15/16 at
640. Across both sizes and both input groups, there were **zero detection
presence disagreements**. Best matched car boxes had median IoU essentially
1, and the largest confidence difference was about 3.6e-6. The detections are
numerically consistent on this sample, not a proof of equality on all images.

Failures remain visible:

- Both sizes/backends missed `rgb_38.100.png` and `rgb_53.600.png`, the two
  previously inspected black shutter-release frames.
- Both 480 paths additionally missed the visible `rgb_60.600.png`.
- Both 480 paths missed `view0.png` and `view4.png`; both 640 paths missed
  `view4.png`.

Availability on these images is not labeled Precision, Recall or mAP. The
640 model preserves the earlier detection advantage, but its roughly 113 ms
OpenVINO median is still slower than the roughly 74 ms PyTorch 480 median.
This test does not establish that 640 can meet the live 0.75 s freshness
budget while Gazebo, PX4 and ROS compete for CPU.

## Thread-setting finding

Ultralytics 8.4.188 `utils/torch_utils.py:364` calls
`torch.set_num_threads(NUM_THREADS)` in `select_device('cpu')`. Therefore
setting two threads only before `YOLO.predict` setup is insufficient. An
initial exploratory pass was excluded because of that reset. The final
benchmark reapplied the limit after setup and records the actual value for
each measured size. The main detector independently received an
`on_predict_start` callback that applies its configured thread count after
backend setup and before warmup/inference.

Similarly, the Ultralytics OpenVINO adapter does not expose the two-thread
configuration used here, and its generic CPU path can select AUTO. This
investigation used `ov.Core.compile_model` explicitly and did not route the
production detector through that adapter. A future backend integration must
preserve these CPU/thread/shape/FP32 settings and preprocessing/NMS behavior.
No wrapper was added because the measured gain was small.

## Reproduction and provenance

The isolated environment is `/root/uav_tracking_project/.venv-openvino`, with
system site packages visible. Its creation used `venv --system-site-packages
--without-pip`; the existing system pip installed into the venv with its
`--python` option. The final dry-run and installation added only OpenVINO
2025.4.1 and openvino-telemetry 2025.2.0. Existing NumPy 1.26.4, Torch
2.5.1+cpu, ROS, PX4 and Gazebo packages were preserved. Ultralytics was
8.4.188. No ONNX, NNCF, INT8 calibration or FP16 export was introduced.

```bash
/root/uav_tracking_project/.venv-openvino/bin/python \
  /root/uav_tracking_project/scripts/benchmark_openvino_car.py \
  --source-root /mnt/d/基于yolo和卡尔曼滤波 \
  --output /root/uav_tracking_project/results/openvino_car_comparison \
  --threads 2
```

The source checkpoint is
`https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt`,
SHA-256 `85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5`.
Its upstream [license](https://www.ultralytics.com/license) and the exported
metadata identify AGPL-3.0; the exported model retains that provenance.
[OpenVINO](https://github.com/openvinotoolkit/openvino/blob/master/LICENSE)
uses Apache-2.0. Installed runtime and telemetry license texts are archived
alongside the result. Visual-asset CC0 licensing does not apply to weights.

`results/openvino_car_comparison/comparison.json` records source/model/input
hashes, versions, device properties, all 96 per-image paired records and
failure lists for each size. `export_480/` and `export_640/` retain the copied
original checkpoint, FP32 XML/BIN and exporter metadata.

| Export | SHA-256 |
|---|---|
| 480 XML | `d72a394648e5b038db2f2066ff7b93b4dd0f06adc3bbfac6ff3c0bf5ac1e50ba` |
| 480 BIN | `c8ccff835db7a02a9655bc84ccbea48258a1f47ee678632ef641c8cf3f431ee0` |
| 640 XML | `4a3128106ba9f50d47408a190d7896125684d14b405c08c48ed51d60d14f0c21` |
| 640 BIN | `d3e91a52fabb50c2ea253fa0bda3f6ef40f1322172ef8ece04929eb8c4ea8011` |
