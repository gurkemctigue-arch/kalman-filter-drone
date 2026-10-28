# Paused recording graph readiness

The Humble06 person development slot retained eight raw PX4 odometry samples
without adapter timing diagnostics at the start of its recording. Its original
source-clock verdict remains INCOMPLETE. The runner previously checked only
topic names before unpausing, which did not prove subscriber discovery.

The startup gate now keeps Gazebo paused and requires all nine critical topics:
Clock, RGB, depth, CameraInfo, target truth, vehicle truth, native PX4 odometry,
adapted odometry and the odometry timing diagnostic. Every topic must have one
publisher of the expected type with a valid endpoint GID. Adapted odometry and
timing publishers must belong to `/uav_tracking_px4_adapter`. The native DDS
publisher is identified by its exact topic and type, without assuming a ROS
node name for PX4's bare DDS participant.

The gate requires the adapter's native-odometry and Clock subscriptions. When
recording is enabled it separately requires `/rosbag2_recorder` subscriptions
on every critical topic; other consumers cannot satisfy this requirement.
Publisher/subscriber QoS must be positively compatible. Unknown compatibility
does not count as a match.

A read-only `std_srvs/Trigger` service,
`/uav_tracking_px4_adapter/startup_readiness`, proves a callback on the real
adapter is running while simulation time is paused. It reports native publisher
discovery on that actual node using the public `Node.count_publishers` API,
explicitly labeled `NODE_GRAPH_DISCOVERY_NOT_RMW_MATCH`; Humble does not provide
the subscription's middleware match count as a public Python method. Both
adapted publishers report their actual matched subscription counts through
`Publisher.get_subscription_count`. Adapted publisher counts must
cover every compatible subscription observed in the graph, including the
recorder.

Accepted endpoint identities must remain unchanged for 1.0 wall second and a
further 0.5 wall second guard, with actual callback/matching checks repeated
throughout. Any failed observation or endpoint replacement restarts both
windows. The total gate wall budget is 45 seconds; each callback has a 0.75
second wall budget. An owned process exit, ROS component failure or readiness
timeout fails the slot before unpause, without an automatic retry.

`graph_startup_readiness.json` records every graph snapshot, endpoint GID,
QoS check, actual callback result, assessment, guard state and final outcome.
This is startup evidence only: full-recording raw/timing/adapted correspondence,
source-clock validity and independent navigation evaluation remain required.
No source sample is waived and no evaluation start boundary changes.

A separate diagnostic using the unmodified Humble06 build established that
native odometry's DDS publisher, the adapter and recorder endpoints can all
exist with `/clock` fixed at zero and zero raw/adapter messages. Thus waiting
for native publisher discovery before unpause has no initial-sample dependency
in this environment. Its preserved raw evidence is
`/root/uav_humble22/logs/paused_graph_06_diagnostic01/report.json`.
