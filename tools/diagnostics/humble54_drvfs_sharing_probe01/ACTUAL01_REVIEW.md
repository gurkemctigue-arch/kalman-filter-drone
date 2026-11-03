# Independent read-only review of actual01

Reviewed the root-executed actual DrvFS experiment from
`results/diagnostics/humble54_drvfs_sharing_actual01`; did not rerun it.

The raw overall receipt SHA256 is
`84432447f3c8ff79e2b916b98f52ad2ff1700cf9cfe4dfe63ecd143e67c4dbd4`.
All 14 listed artifact hashes match their current raw bytes. Nested native
results match the separate original native JSON files. The executed probe's
source SHA remains
`7685c8ef54c222264eb3570e6eb80a02bbf10ffe197f65d13d2a1ba95d2af958`.
Both collector source pins match the registered originals before and after.

Old03 raised one real `PermissionError(errno=13)` at 04:38:33.889374 UTC, with
the destination hash unchanged. Its writer call lasted 0.012649586 seconds. The
original leftover temporary file is retained as evidence.

New04 observed 71 real `PermissionError(errno=13)` events in the pinned writer,
from 04:38:36.275212 through 04:38:38.273429 UTC. Windows released the conflicting
handle at 04:38:38.281141 UTC; the same writer call succeeded at
04:38:38.309105 UTC, after 2.045156218 seconds. Its exact output matches the
expected new value, and no temporary file remains. This supports actual
sharing-conflict retry, independently of the timing-only observation.

Both owned native commands exited zero. Raw stdout binds each mode/outcome to
its original native-result SHA. The raw stderr logs, decoded as UTF-16LE,
contain the WSL localhost-proxy notice, with no Python traceback.

Conclusion: the actual file-sharing probe passes. This evidence concerns only
metadata replacement under a real Windows sharing conflict; it is not a flight,
collector-loop fault test, capacity result, or readiness decision.
