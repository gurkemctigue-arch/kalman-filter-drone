# Prepared lossless level 22 comparison

This directory is preparation only. `python -B benchmark.py` prints its description. It does not load the original benchmark, query native processes, read a source archive, compress anything, or import ROS. `host_resources.py` separately requires its explicit `--query`; it reads host memory and file attributes, never VHD payloads.

After root source review and after all flight/collector/evaluation children have actually exited, root may explicitly run **inside the existing UAVHumble22**:

```sh
bash tools/diagnostics/humble54_lossless22_bench01/run.sh --execute \
  --reviewed-source-sha256 <exact benchmark.py SHA256> \
  --reviewed-manifest-sha256 <exact sources.json SHA256>
```

The original `stage.py` idle guard holds the existing SITL lock throughout. No WSL launcher, owner, watcher, trigger, retry or next job is created. The only runtime output is the single fresh external directory `/mnt/d/WSL/UAVHumble22-validation/humble54_lossless22_bench01`. If it already exists, execution refuses; failed outputs are retained.

The two actual original plan IDs are `car_stage1_velocity_seed004` from core12 probe01 and `car_extension_depth_noise_seed004` from extension16 probe02. The core plan retains its historical `/root/.../results` working directory; its immutable published archive is separately derived from **that plan's `results_root / trial.name`**. Both locations and exact original terminal/small artifacts are bound in `sources.json`; no old paths or manifests are rewritten. Archive/raw SHA and byte counts in preparation are expectations from the original integrity receipts. Payloads have not been independently re-read by this preparation.

Each source is tested once at `-T1 -19 --long=27 --check`, then once at `-T1 --ultra -22 --long=27 --check`. Each candidate retains the existing **900 s total budget**, including CLI test, complete decode byte/SHA comparison, native full-topic/full-message read, exact native-cache SQLite byte/SHA and candidate SHA. Compression is original archive decode-to-stdout then re-encode, so its wall time includes decoding and is not direct production raw SQLite compression time. Fixed order and two samples provide no confidence interval or full fault-capacity conclusion.

The completed humble25 T1/T4 benchmark supplies the unchanged owned-child, GNU time, process-group RSS, wait and cleanup primitives. This tool adds actual host/guest resource admission and monitoring: each must have at least 5 GiB available at candidate start; running values below 2 GiB or simultaneous measured child-group RSS above 3 GiB stop the candidate. A host snapshot is triggered about two seconds after the previous query completes; the query itself has a ten-second timeout, so a maximum two-second sample interval is not guaranteed. Actual query timings, resource samples and owned query processes are retained. No compression ratio is used for memory admission. Sampling cannot prove every instantaneous peak.

The original 22 GiB host reserve is preserved. Start admission additionally reserves three times the **exact raw sizes** across the two sources for outputs and private native cache, assuming no compression savings. Runtime host free space below the fixed reserve stops work. The fresh tree's unique-inode logical/allocated bytes, guest free space, registry-backed VHD logical/allocation size and actual D free space are sampled. Only this private tree is scanned; no production spool or VHD is written directly.

Existing production archives already use `-T4 -19 --long=27 --check`; previous improvements are already adopted. This candidate changes no production archive policy, source archive, old manifest, full 280 schedule or reserve. **Unmeasured saving remains 0 bytes**, including in benchmark receipts; any complete observed paired differences are diagnostic only. Adopting a profile would require a separate source review, compatibility evidence and a new complete 28-cell measurement/capacity decision. No formal capacity gate is passed here.

Small Windows fixture checks:

```powershell
python -B -m unittest discover -s tools/diagnostics/humble54_lossless22_bench01 -p test_benchmark.py -v
```

Fixtures cover inert default, explicit native execution gating, unknown/low memory and reserve rejection, original small metadata bindings, and a fully synthetic native reader's full-topic denominators and exact raw SHA. They do not execute a compressor, ROS, native process query or read a real source bag/model.
