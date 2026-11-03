# Closed probe02 position / velocity tail review

This directory preserves a small diagnostic record for GitHub review. It does not change either original flight result: position remains FAIL and velocity remains PASS.

`actual_sidecar_evidence.json` is a byte-identical copy of the original results diagnostic (SHA256 `e9e3c2ad60ca5a4117b964921f67084aa1a8a5d9635c60167b262a43f20febe0`). The two files in `inputs/` are also byte-identical copies of the completed navigation evaluation sidecars. `publication_receipt.json` records their original paths, hashes, copy time, and equality checks. `.gitattributes` disables text conversion throughout this directory.

The [PNG](artifacts/position_velocity_tail_distance.png) and [PDF](artifacts/position_velocity_tail_distance.pdf) compare the recorded 10 Hz distance errors from 86 s to each recording's end. Position returns inside the original +/- 0.5 m band at the observed sample 90.152 s, leaving only 2.320 s before the recorded end 92.472 s. The original final dwell requirement is 3 s. The physical crossing is bounded by adjacent samples, rather than known exactly. Velocity maintains its final sampled in-band suffix from 58.100 s.

The actual [plot receipt](artifacts/plot_receipt.json) records the script, pinned inputs, Python / Matplotlib versions, actual start/end times, and output hashes. The script uses only these copied small JSON inputs; it accesses no ROS, WSL, bag, or telemetry files.

To reproduce from the repository root with Python and Matplotlib installed, choose a fresh destination:

```powershell
python -B tools/diagnostics/humble54_probe02_position_speed_tail_review01/plot_tail_comparison.py --output-dir tools/diagnostics/humble54_probe02_position_speed_tail_review01/artifacts_rerun01
```

Existing output directories are refused to preserve prior artifacts. The figure explains the recorded stability failure; it does not identify which controller term or target acceleration caused the late excursion.
