# Pause and drain before closing the recording

The immutable Humble09 car development slot recorded one final raw PX4 sample
at source 38.740 seconds / recorder receipt 38.744 seconds after the last
recorded timing/adapted pair at 38.732 seconds. Its original source-clock
verdict remains INCOMPLETE. Startup correspondence from 0.572 seconds was
complete. This is a recorder-close boundary issue, independent of the earlier
startup-discovery repair.

After the monitor terminates, the runner now keeps Gazebo, PX4, ROS and the
recorder alive. A separate observer receives actual Clock and raw odometry,
requests `pause: true` on the owned world's control service and requires a
positive acknowledgement. It continues receiving raw odometry, timing
diagnostics and adapted odometry while the world is paused.

Closing is allowed only after the observed Clock source stamp stops advancing,
raw/timing/adapted message counts stop increasing for 0.5 wall second, and the
last raw sample/publication pair has its corresponding diagnostic. An accepted
diagnostic also requires its declared adapted odometry header to have been
received. A rejected diagnostic requires no adapted message for that sample.
A later raw, diagnostic, adapted message or advancing Clock restarts the quiet
window. Repeated Clock messages carrying the same paused stamp are allowed.

The Humble10 person slot retained one missing ground-truth bracket on its last
scheduled navigation sample (208/209 truth coverage), even though all 3835
source triples matched. The evaluation PosePublisher plugins previously ran
at 30 Hz while physics runs at 250 Hz. All sixteen target/vehicle evaluation
publishers, including inline multi-actor worlds, now use `update_frequency=-1`,
the upstream plugin's unthrottled default. In the exact gz-sim8_8.15.0 source,
only a positive frequency sets a nonzero update period (lines 227-234);
PostUpdate publishes on each unpaused update when that period is zero (lines
318-386). The versioned source is preserved at
`D:/WSL/UAVHumble22-validation/logs/PosePublisher_gz_sim8_8_15_0.cc`.

The closing observer additionally requires real target and vehicle truth at
the exact final Clock stamp, for every actor declared in the runtime world.
It reads only truth frame names and source headers for logging completion;
no position, entity identity, selection or association feeds the online
estimator/controller. Future-only or old truth cannot fill that final stamp.
Late truth delivery restarts the quiet window. No timestamp is rewritten and
no pose is extrapolated.

The observer has a 10 second total wall budget, including discovery and the
pause service. It writes `recording_closure.json` with the actual pause
response, per-observation counters, final correspondence, quiet duration,
failure reasons and cleanup outcome. Failure still closes and archives the
recording; a previously successful monitor cannot make a failed closure a
successful trial. An existing flight exception remains the primary exception.
Startup failures before unpause have an explicit skipped-closure record.

Only after the observer finishes does the runner stop the recorder, then ROS,
PX4 and Gazebo. Independent source-clock evaluation still checks the complete
recorded Clock tail and every raw/timing/adapted sample. No final sample is
removed, waived or assigned a different evaluation start/end. Ground-truth
coverage at the tail is independently reported, including any missing bracket.

The first minimal API validation uses real Humble publishers/subscribers and
the production observer with a synthetic Gazebo pause acknowledgement, without
running Gazebo, PX4 or a recorder. It checks delayed diagnostics, cross-topic
reordering, rejected last samples, a late second raw and a missing diagnostic
that must time out. Its scope is recorded explicitly at
`/root/uav_humble22/logs/public_recording_closure10_smoke01/summary.json`.
Real simulation and full-recording evidence are separate validations.
