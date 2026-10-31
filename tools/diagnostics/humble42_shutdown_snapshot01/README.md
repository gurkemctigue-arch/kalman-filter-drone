# Humble42 renderer shutdown diagnostic

This directory preserves the independently reviewed diagnostic and its actual
Ubuntu 22.04 / ROS 2 Humble execution receipt. It is separate from the immutable
Humble42 source and failed core batch.

On 2026-10-31 at 20:47 UTC, the original car-crossing world produced two real,
increasing 640×480 RGB and depth frames, acknowledged unpause/pause, and drained
callbacks. Gazebo exited 0 approximately 0.117370396 seconds after its sole
SIGINT. All six owned processes exited 0; no TERM, KILL, or residual process
was observed. The original 8/5/3-second cleanup budgets were retained.

The 21 synthetic review cases and this one native lifecycle observation cover
different scopes. This run did not start PX4, the ROS bridge, the detector or a
75-second flight. It neither reproduces nor repairs the original slot09 failure,
and provides no admission to pending or formal trials. Original results remain
8 PASS, 1 FAIL, 3 PENDING; formal trials remain 0/280.

The full process snapshots and native logs stay in the external diagnostic
archive. `actual_independent01.json` binds their hashes and records limitations.
The archived invocation contains the exact original paths and refuses to reuse
its output. A future run needs a fresh output and an explicit serial schedule.
