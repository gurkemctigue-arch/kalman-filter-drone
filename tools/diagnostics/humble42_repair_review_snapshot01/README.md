# Review of the next development repair

The reviewed change defers automatic unmatched births with unknown surface
support, including frames without an overlap anchor. It does not remove candidates
from association, weaken ambiguity protection, extend prediction, or authorize
automatic target switching. A real new target may therefore initialize later;
surface support is not a physical identity certificate.

The birth review covers eight independent synthetic boundary cases. Root also ran
76 related behavior tests on Windows. Two previous tests asserted the old
unsupported-birth behavior and were updated to the explicit new policy; the
supported, image-separated birth case still initializes immediately.

The stop observer passed 27 external synthetic cases. Its source is installed as
`uav_tracking/stop_observer.py`, byte-identical to reviewed helper SHA
`7109b924f3e58d63f3b0b8af700c27c870086379b8226d4fa07520a46b6ae1a8`.
The package import is the only AST difference from the reviewed candidate runner.
Root's ten trial behavior tests exercise actual delegated cleanup with fake OS
calls, and five publication tests exercise incomplete-evidence fault handling.

These reviews allow an independently named integration diagnosis. No new flight,
Linux build, full core pass or formal admission follows from the synthetic tests.
The original Humble42 result remains 8 PASS / 1 FAIL / 3 PENDING.

The next steps and evidence limits are in
[the repair plan](../../../planning/reliability-v4-humble43-repair.md).
