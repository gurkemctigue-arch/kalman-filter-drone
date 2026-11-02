# Formal54 serial signal ownership patch

Revision 02 fixes two findings from independent static review. Each spawn now
clears the previous child's identity before capturing the new one. A capture
exception waits the actual new Popen handle without signaling an unverified
identity; its terminal records the independent `owned_popen_pid`,
`identity_unverified`, and capture error instead of reusing the prior child.

Finalization now has an explicit stop-handler decision boundary, reached only
when no owned adapter remains. Requests handled before that boundary are
included in one final snapshot, even if they arrive after provisional result
annotation. The same snapshot writes summary, lifecycle heartbeat/terminal and
`serial_exit_code`, which main returns directly. Signals handled after the
window closes are post-terminal observations and cannot mutate the committed
task. This is a single decision boundary, not a claim of a filesystem atomic
transaction across multiple JSON files or protection from later external kills.

The original 23-test log/receipt/describe and diff remain unchanged. Their
matching prior source bytes are preserved in `revision01_byte_archive`.
The current 25-test round adds a second-child identity-capture exception
regression and a stop-after-annotation regression (including the closed-window
case). Current evidence is `author_windows_validation02.json`,
`formal54_serial_describe_windows02.json` and
`formal280_serial_guard54_revision02.diff`. The native dummy fixture only drops
its duplicate manual summary write because finalization now owns that write;
both Linux dummy signal tests remain unexecuted.

This is an external, prospective orchestration patch. No workspace source or
historical external helper was edited. No WSL, ROS, simulator, real guard,
formal slot, or Linux dummy signal test has been executed by its author.

`formal280_serial_guard01.original.py` and its original test are original-byte
read-only archives. The serial archive SHA256 is
`6c8d2cd68b2f5d3a8acfea791ca1c82d49d595d664745073dea851802ac7971a`.
The derived serial keeps every original gate/receipt helper unchanged; a test
compares their complete ASTs. Original `guard.execute_one` remains inside the
existing formal48 adapter; this patch does not implement or change that guard.

## Entry and lifecycle

Run `formal280_serial_guard54.py describe` without any runtime side effect.
The actual CLI retains `--manifest`, a fresh `--output`, and the LAST option
`--guard-command` consuming its whole prefix. The serial appends exactly
`run-one --manifest ABSOLUTE_MANIFEST`. It works with the independently bound
supplementary preflight prefix; that prefix must eventually exec the unchanged
formal48 adapter. Original receipts and the full 280 denominator remain
authoritative, and ordinary engineering FAIL/unknown evidence still continue.

Default actual execution is Linux-only and owns one Popen child at a time.
Each child uses `start_new_session=True`. Before forwarding a requested SIGINT
or SIGTERM, it verifies PID, kernel start token/start_ticks, PGID and session
against the owned child. Only that positive child PID receives the first stop
signal. It never signals a process group, uses process names, kills WSL, or
escalates to SIGKILL. Repeated incoming signals are recorded without repeatedly
interrupting the original adapter's cleanup. The real Popen wait is retained
until exit; there is no batch deadline or cleanup timeout in this patch.

The adapter's own original signal handler is responsible for its runner and
flight cleanup. This serial's wait receipt proves the direct adapter was
waited; it does not replace or certify the adapter/native cleanup receipts.
An unverified/reused identity is never signaled: the serial retains its Popen
handle, waits, records failure, and does not start another slot.

Additional files in the fresh batch output:

- `lifecycle_heartbeat.json`: native serial PID/token, last owned child identity,
  requests, forwarded signal, state and actual wait count. Updated at attachment,
  once per one-second child wait, between child waits and at terminal. Metadata
  checking can temporarily make heartbeat stale; it is not a background timer.
- `lifecycle_events.jsonl`: child start and actual forwarded-stop events.
- `NNNN/owned_process_started.json` and `owned_process_terminal.json`: exact argv,
  identities, real Popen return code and wait completion.
- `lifecycle_terminal.json`: summary binding and explicit `COMPLETED`,
  `STOPPED_BY_SIGNAL`, or `FAILED_OR_REFUSED`. An internally requested cleanup
  signal after an I/O error remains a failure, not an external user stop.

The original `summary.json` scope/status and all receipt checks are preserved;
its extra fields distinguish orchestration outcome from engineering acceptance.
No old output is resumed or overwritten. Lifecycle attachment only happens
after the original serial has created a fresh output and its started receipt.

## Progress monitor and stopping

Do not launch this long-running owner with the unchanged project's monitor
`run` action when that monitor may be interrupted. Its KeyboardInterrupt path
sends SIGTERM to its direct serial child, waits only five seconds, then kills
the serial. The first signal would reach this patch correctly, but the later
forced kill could destroy ownership before the original adapter finishes its
up-to-minutes cleanup. This patch cannot repair an ancestor's forced kill.

Instead launch the serial under a durable Linux process owner, retain its real
Linux PID/token from `lifecycle_heartbeat.json`, and use the unchanged monitor
`watch --pid ACTUAL_LINUX_SERIAL_PID` separately. Monitor `watch` never kills
its external target. A deliberate stop must verify the serial's recorded
creation token before sending SIGINT/SIGTERM to that serial PID, then wait for
`lifecycle_terminal.json` and the original adapter cleanup receipts. Stop the
watcher separately afterwards. Neither a tool session id nor a Windows PID is
the Linux producer identity. The existing two-plan bridge can continue reading
the unchanged serial summary/events/original guard state.

The durable-launch integration itself is not executed or certified here.

## Validation boundary

`author_windows_validation01.json` and its log record only pure fake-process
tests plus inert describe on Windows. These tests exercise original gate
semantics, stop/no-next-slot behavior, PID reuse/PGID mismatch rejection, real
handler registration/restoration, the actual backend's Popen/positive-PID call
shape, actual-wait semantics through fake handles, I/O-failure cleanup, fresh
output protection and separate stopped/failed terminal states.

When root has exclusive native validation time, run these two dummy-only tests:

```bash
/usr/bin/python3 -B /mnt/d/WSL/UAVHumble22-validation/formal54_serial_signal01/test_native_owned_signal54.py
```

They start only temporary Python owner/dummy-child processes. One test sends
real SIGINT and one sends real SIGTERM; both require the dummy cleanup file,
actual wait completion, exact process identities and no surviving dummy child.
They do not import a real guard or use a formal admission. Do not describe the
patch as natively validated or ready for formal execution before those tests,
independent source review, actual prefix binding and planned prestart checks.
