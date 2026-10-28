# Detector weights

The repository keeps source code and simulation assets under version control, but
does not commit the YOLO checkpoint binaries. Download the required weights into
this directory before running the detector:

- `yolo11n.pt` for pedestrian experiments;
- `yolo11s.pt` for car experiments.

The upstream download URLs and licensing notes are documented in
[`docs/CAR_DETECTOR_COMPARISON.md`](../docs/CAR_DETECTOR_COMPARISON.md) and
[`docs/OPENVINO_CPU_COMPARISON.md`](../docs/OPENVINO_CPU_COMPARISON.md).
