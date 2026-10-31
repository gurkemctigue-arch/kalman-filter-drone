# Detector weights

The repository keeps source code and simulation assets under version control, but
does not commit the YOLO checkpoint binaries. Place the required pretrained or
locally supplied trained artifacts in this directory before running the detector:

- `yolo11n.pt` for pedestrian experiments;
- `yolo11m_car_sim_train20_04.pt` for the current Humble42 car candidate;
  this is the simulation-finetuned YOLO11m checkpoint, not the upstream
  YOLO11s baseline. Its SHA256 is
  `bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c`.

The current car resource choice is 512 input, four CPU threads and native
PT/FP32; pedestrian inference remains 320 input and two CPU threads.
The [resource receipt](../config/car_sim_train20_04_m512_resource_receipt.json)
binds the original image regression and worker timing evidence. Those
development measurements do not establish completed flight acceptance.
The trained checkpoint must be supplied from the local model artifact; an
upstream download of `yolo11s.pt` cannot replace it. Earlier YOLO11s/640 and
YOLO11s/480 configurations belong to their recorded historical experiments.

The upstream download URLs and licensing notes are documented in
[`docs/CAR_DETECTOR_COMPARISON.md`](../docs/CAR_DETECTOR_COMPARISON.md) and
[`docs/OPENVINO_CPU_COMPARISON.md`](../docs/OPENVINO_CPU_COMPARISON.md).
