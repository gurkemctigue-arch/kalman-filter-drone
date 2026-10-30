# Owned ROS launch child lifecycle during bounded bridge discovery

The first Humble26 clean20 startup stopped before unpause while enumerating
owned launch descendants. The old parser used one error for both a truncated
`/proc/PID/stat` record and a complete record in state Z/X. That old log cannot
determine which condition occurred; no old frozen source or result is changed.

The next source revision will distinguish these conditions before a new freeze:

- Validate the record PID, minimum structure, process state and decimal integer
  fields through starttime before classifying any process as dead.
- Raise a specific `ProcessNotAliveError`, derived from
  `RuntimeRegistrationError`, only for a complete valid Z/X record. Include PID,
  state and parsed creation/parent identity in that exception.
- In `find_owned_parameter_bridge`, only a non-leader child whose executable
  has not been confirmed as a bridge may be skipped for this typed lifecycle
  condition. Its parsed parent must still match the queued kernel-child parent.
- Keep malformed/truncated records, identity drift, leader failures, confirmed
  bridge failures, permissions and other I/O errors fatal. Never catch the
  `RuntimeRegistrationError` base class as a transient lifecycle condition.
- Preserve the capture loop's exact comparison with its previously discovered
  bridge. A dead or missing previously selected bridge must fail before any
  replacement can be verified or before physics can be unpaused.

Portable fixtures will exercise ordinary Z/X children, malformed records bearing
Z/X, parent mismatch, all leader identity reads, and selected bridge loss with a
healthy replacement. Existing ESRCH, bounds, ELF and cleanup tests remain in the
same targeted suite. These fixtures are orchestration evidence; a fresh Linux
build and actual kernel process checks belong to the next independently bound
source revision. No success or formal flight is asserted by this decision.
