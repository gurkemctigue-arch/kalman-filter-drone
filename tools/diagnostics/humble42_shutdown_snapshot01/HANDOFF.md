# Renderer-only shutdown diagnostic: review handoff

**Not executed. Independent review and root's explicit serial execution are required.** The original probe, source freeze42, slot09 records and failed outcomes remain unchanged. This is not a complete original09 flight reproduction, an association repair, a formal seed, or admission to the unexecuted stage3 slots.

Files at initial handoff:

- `owned_rgbd_shutdown.py`: SHA256 `d088d1e93c5a86afd38de9ca2a3664f61b91cd7529a82d3006e21fd6a1983cb0`.
- `test_owned_rgbd_shutdown.py`: SHA256 `88595694f561df49684477bba21992c444e816004baa669e6a44c7e342545030`.

The 14 standard-library fixtures passed on Windows Python3.12 in under one second. They import no native Gazebo library and create no subprocess or simulation. Native Ubuntu3.10 API/runtime and the actual diagnostic remain untested. The fixtures verify increasing real-frame accounting, invalid-frame drain activity, original-window acceptance, optional stack gaps, no inference from unverified native subscribe returns and preservation of timeout/kill/missing-essential-evidence failures; they do not prove native shutdown.

## Verified native interface and implementation scope

The native API was read before implementation from the existing `scripts/probe_gazebo_shutdown.py`: `gz.transport13.Node`, `gz.msgs10.image_pb2.Image`, and `node.subscribe(Image, topic, callback)`; image fields `header.stamp.sec/nsec`, `width`, `height`, `data`. The original runner and recording closure use `gz service -s /world/<name>/control --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean --timeout 5000 --req 'pause: false|true'`.

The new tool imports the hash-bound existing probe for `owned_environment` and exact Boolean-response parsing. Native transport is imported only in a normal Python subprocess, launched with `start_new_session=True`, after the private partition is set. A privately passed connection FD carries bounded counters/ACKs; no image payload crosses to the parent. Normal Python/native process exit is observed by the parent, avoiding multiprocessing worker `os._exit` bypass of interpreter/static teardown. Runtime protobuf descriptors validate WorldControl.pause and Boolean.data as bool and validate Image fields. No new transport signature, message name or stop service was invented. The source file's imported Node unsubscribe API is also inherited from the original probe.

The original probe does not establish the native subscribe return type. The tool records each returned type/value (None explicitly `NONE`) and rejects call exceptions; neither None nor False nor zero is itself an actual-frame verdict. Only the post-unpause real-frame gate proves subscription activity.

The tool holds both exact existing locks, `/root/uav_tracking_humble_build_window.lock` and `/tmp/uav_tracking_reliability_v4_sitl.lock`, plus the fresh output lock. **Do not wrap it in either of these locks**, because they are nonblocking flock locks owned internally. It refuses other OS/distro, reused output, output inside the frozen root, mismatched source/world/self hashes, different seed5/LP4/OMP2 or 8/5/3 budgets, preloaded drivers and fewer than two increasing frames per stream.

Gazebo starts without `-r`, advertises the actual world-control service and stays paused through an observed quiet interval. Only an acknowledged unpause then at least two new nonempty increasing RGB frames and depth frames satisfies the frame gate. After the acknowledged pause, all received image callbacks (including invalid/duplicate frames) must become quiet. This is a bounded callback drain, **not a rosbag or full recording-stream closure proof**.

The tool captures bounded owned `/proc` creation identity, PID/PGID/session, process/task stat, wchan, kernel stacks, selected environment and mappings. It requires actual swrast and LLVM and rejects actual D3D12/WSL-driver mappings. Required owned identity/mapping evidence or cap overflow remains essential. Per root's task clarification, unavailable stack/wchan is recorded as optional `NOT_OBSERVED` with its reason and does not fail otherwise complete natural shutdown; it cannot support a root-cause claim. Timeout/TERM/KILL remains FAIL regardless of stack availability. A failed run can still provide useful diagnostics while remaining FAIL.

Each signal request and wait result is flushed to `events.jsonl` with UTC, monotonic time, deadline, grace, exact recipient identity and group/leader scope. Source/world/tool pins and intent are saved before the first child in `registration.json`. Final `report.json` records native exits and every owned participant. The separate native subscriber must unsubscribe and naturally exit0 within its2 s cleanup window; this checks actual native-process teardown, rather than an unsubscribe ACK alone. Service/dmesg subprocesses also have separate owned groups and exit/cleanup receipts.

Gazebo passes only with natural exit0 within the original initial8 s SIGINT window, no SIGTERM/SIGKILL, no missing gate/evidence and no remaining owned process. Escalation continues with original5 s TERM and3 s KILL for cleanup; diagnostics/cleanup never rehabilitate failure. Any TERM/KILL on another owned participant also fails the tool. Initial diagnostic-stop and failure-cleanup actions are labelled separately.

Before/after `dmesg --level=err,warn --ctime` logs preserve a bounded finite ring and matching lines. The earlier independent kernel probe's no-match result is not reinterpreted as proof against historical OOM; neither is a new no-match result. Missing kernel access is explicit missing evidence.

## Suggested root-only invocation after independent review

Resolve the actual frozen42 overlay/resource/plugin paths before running. The values below match the recorded original runtime conventions; the command derives the bringup share from the actual sourced overlay. It does not start PX4, ROS nodes, bridge, detector or a75 s flight. Choose one fresh diagnostic output and execute once; there is no automatic retry.

```bash
stage_diag_source=/root/uav_tracking_fullplan_v4_humble42
stage_diag_tools=/mnt/d/WSL/UAVHumble22-validation/humble42_shutdown_diagnostic01
stage_diag_world='/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble42/reliability_v4_humble42_probe01_car_stage2_crossing_seed004/configuration/runtime_world.sdf'
stage_diag_output=/mnt/d/WSL/UAVHumble22-validation/humble42_shutdown_diag_01
stage_diag_px4=/root/uav_humble22/PX4-Autopilot-v4mag
source "$stage_diag_source/scripts/source_ros_environment.sh"
source "$stage_diag_source/ros2_ws/install/setup.bash"
stage_diag_share="$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup"
/usr/bin/python3 "$stage_diag_tools/owned_rgbd_shutdown.py" \
  --execute-owned-diagnostic \
  --source-root "$stage_diag_source" \
  --runner-sha256 c49db44aba88249cbbafb27ab0d7de13be38419560466636a468a913071f2097 \
  --launcher-sha256 9b9f485f294110f74186abcf2cf48d1b09297927104a2fed42f1d1818ee6c319 \
  --probe-source "$stage_diag_source/scripts/probe_gazebo_shutdown.py" \
  --probe-sha256 cb9e6d946cb31a6aa8b0af09ef283d07060bf3d2650f5b8915936491e805f61c \
  --tool-sha256 d088d1e93c5a86afd38de9ca2a3664f61b91cd7529a82d3006e21fd6a1983cb0 \
  --world "$stage_diag_world" \
  --world-sha256 587adf76dd76cfd538454103181969330cb3372458b895571058c76f76966d74 \
  --world-name stage2_flight --output "$stage_diag_output" \
  --seed 5 --lp-threads 4 --omp-threads 2 --min-frames 2 \
  --sigint-grace 8 --sigterm-grace 5 --sigkill-grace 3 \
  --image-topic /camera/rgbd/image --image-topic /camera/rgbd/depth_image \
  --resource-path "$stage_diag_share/models" \
  --resource-path "$stage_diag_px4/Tools/simulation/gz/models" \
  --plugin-path "$stage_diag_px4/build/px4_sitl_default/src/modules/simulation/gz_plugins"
```

The tool expects the native system interpreter `/usr/bin/python3`; do not substitute a venv interpreter. A root-owned outer watchdog may be useful, but it must allow the finite startup and cleanup budgets and preserve all failure evidence. Killing the diagnostic owner without a complete participant-cleanup receipt is not an accepted run.

If this isolated lifecycle exits cleanly, that narrows the next contrast; it does not fix original09. Add bridge/PX4/ROS participants and their original stop order only if a separately reviewed next diagnostic is needed. Keep original09's association/occlusion FAIL and the separate owner immutable-copy failure independent.
