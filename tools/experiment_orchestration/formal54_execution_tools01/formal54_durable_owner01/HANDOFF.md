# Durable owner 01: wiring and review boundary

This directory adds external lifetime orchestration only. It edits no workspace,
frozen root, original adapter or serial. It creates no formal plan, supplementary
protocol, registration, seal, initial admission or flight authorization. The
existing formal54 serial still calls the original supplementary preflight and
formal48 adapter for every invocation; the actual sealed guard alone selects
slots and preserves the complete 280-slot denominator and ordinary FAIL rows.

The final existing serial source dependency is revision02, independently accepted
by root: canonical `d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8`.
Its entry SHA is `2e0d15f735bb82b3f6a2d819620c4f8f03100b853e04485dddacdd4b426c1393`;
its owned-process helper SHA is
`ae7d7482fb33354d79a3e87416e53d3e1e08ddaef6d5d4e59844bb7f4b7f355c`.
Old revision01 canonical `c96753...` is archival. Source metadata is compared
read-only; this author has not rerun or imported the actual serial or adapter.

## Ownership and stopping

`launch` validates explicitly supplied owner and serial reviewed canonicals,
the actual small source/describe/input byte pins, and a fresh external owner and
serial-output directory. It constructs the existing serial argv exactly; the
original `--guard-command` stays last. The request supplies no slot-selection
override. These checks bind orchestration inputs; they grant no admission.

The launcher starts one detached worker with `start_new_session=True`, closed
stdin and separate persistent stdout/stderr files. It verifies the actual Linux
PID, boot/start token, start_ticks, session, PGID, executable and exact argv.
Only then does it write an append-only launch ACK. The worker cannot start a
serial before that ACK; if no ACK arrives within 30 seconds it aborts without
starting one. This is a startup handshake budget, not a flight/cleanup deadline.
After ACK the worker starts one existing serial in its own detached session and
retains the actual Popen handle until `wait` returns. There is no total serial,
flight or cleanup deadline and no SIGKILL or process-group signal API.

`stop` verifies the worker's original registry and actual identity/command. It
also waits for the worker's immutable `worker_control_ready.json`, proving its
signal handlers are installed; an immediate post-launch stop cannot hit the
worker's default-handler window. It records a new stop request, rechecks the
identity and sends INT or TERM to that positive worker PID only. The worker
rechecks the original serial identity and exact command before forwarding once
to its positive PID. Repeated requests are retained without repeatedly
interrupting original cleanup. The worker waits for the real serial handle;
the serial and adapter retain responsibility for their existing child waits
and native/archive cleanup. No another slot is started by the durable owner.

If identity capture/reuse/command verification fails, no unverified PID is
signaled. A known Popen handle is still waited; PID disappearance never becomes
an invented exit code. Errors, startup failure and incomplete original terminal
evidence are retained. There is deliberately no blind forced-cleanup fallback.

## What the watcher proves

`watch` reads small metadata and kernel identity only. It has no spawn or signal
operation; interrupting it returns 130 without modifying or stopping execution.
`--once` returns a single JSON snapshot. A missing/changed worker without a
terminal is reported as incomplete evidence, never completion.
Both watch and stop bind `worker_spawned.json` to this registry's exact worker
command and the original `launch_ack.worker_spawn` byte pin. A copied receipt
from another live owner or changed acknowledged receipt stays incomplete.
An incomplete terminal JSON publication is retained as an observation error;
it is not completion. Stop continues to require a complete bound terminal.

`terminal.json` records the actual serial wait/return code and binds its original
serial `lifecycle_terminal.json`. `serial_exit_evidence_complete` means that the
wait happened and that original terminal's owner identity/exit code agree. It
does **not** certify descendant/native cleanup or engineering acceptance. Those
remain in original formal48/serial invocation receipts. Stop-handler acceptance
closes only with no live owned serial, before terminal facts are committed.

The durable heartbeat carries actual serial identity. `adapter_observation.json`
cross-checks the serial's current recorded child against `/proc` and records the
observed argv. The supplementary shell/Python/adapter exec transitions can
legitimately change argv while keeping PID/start_ticks. This observation does
not authorize signaling an adapter or invent full identity coverage. Complete
per-invocation adapter identities, initial commands and actual waits remain in
the existing serial's `NNNN/owned_process_started.json` and
`owned_process_terminal.json`; the durable terminal binds the serial's closure.

## Prospective request schema

Create a fresh actual external JSON only after the original formal prerequisites
exist. The following is a schema shape, not an actual request or contract:

```json
{
  "schema_version": 1,
  "kind": "FORMAL54_DURABLE_SERIAL_LAUNCH_REQUEST_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_BEFORE_LAUNCH",
  "python_executable": "ACTUAL_CANONICAL_PHYSICAL_PYTHON_EXECUTABLE",
  "serial_entry": {"path": "ACTUAL_FORMAL54_SERIAL_ENTRY", "sha256": "ACTUAL_FILE_SHA256"},
  "serial_description": {"path": "ACTUAL_REVISION02_DESCRIBE_JSON", "sha256": "ACTUAL_FILE_SHA256"},
  "reviewed_serial_tools_sha256": "d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8",
  "manifest": {"path": "ACTUAL_ORIGINAL_SEALED_ADMISSION", "sha256": "ACTUAL_FILE_SHA256"},
  "serial_output": "ACTUAL_FRESH_EXTERNAL_SERIAL_OUTPUT",
  "working_directory": "ACTUAL_EXISTING_CANONICAL_WORKING_DIRECTORY",
  "guard_command": ["bash", "ACTUAL_SUPPLEMENTARY_PREFLIGHT_SHELL", "--contract", "ACTUAL_CONTRACT", "--contract-sha256", "ACTUAL_SHA", "--reviewed-tools-sha256", "ACTUAL_ACCEPTED_PREFLIGHT_CANONICAL", "--adapter-binding", "ACTUAL_ADAPTER_BINDING", "--adapter-binding-sha256", "ACTUAL_SHA", "--adapter-reviewed-tools-sha256", "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a"],
  "input_files": [{"path": "ACTUAL_SMALL_CONTRACT_OR_ADAPTER_INPUT", "sha256": "ACTUAL_FILE_SHA256"}]
}
```

Use the canonical physical interpreter, for example the resolved
`/usr/bin/python3.10`, rather than a symlink path. `input_files` explicitly
preserves the planned supplementary contract/identity/describe/protocol/selection
and adapter/preflight code pins; the actual supplementary and adapter gates
still validate their own complete inputs on each slot. The actual admission
file SHA remains distinct from its internal canonical. The registry preserves
the complete input list; the worker reconstructs the exact serial/worker argv
and list from the original request and rejects a resealed registry that changes
arguments or drops source pins.

## Future commands, not executed by this author

After independent review and native dummy acceptance, root can start a future
formal serial in its authorized window:

```bash
ACTUAL_PHYSICAL_PYTHON -I -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/formal54_durable_owner.py launch \
  --request ACTUAL_REQUEST_JSON --request-sha256 ACTUAL_REQUEST_FILE_SHA \
  --owner-directory ACTUAL_FRESH_EXTERNAL_OWNER_DIRECTORY \
  --reviewed-tools-sha256 INDEPENDENTLY_ACCEPTED_DURABLE_CANONICAL \
  --reviewed-serial-tools-sha256 d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8
```

Preserve launch stdout: its returned registry path/byte SHA and Linux worker
identity are the control inputs. This is neither a Windows PID nor a tool
session ID. Then observe separately:

```bash
ACTUAL_PHYSICAL_PYTHON -I -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/formal54_durable_owner.py watch \
  --owner-directory ACTUAL_OWNER_DIRECTORY --registry-sha256 ACTUAL_REGISTRY_FILE_SHA --interval 5
```

Stopping that watcher has no execution effect. A deliberate graceful stop is:

```bash
ACTUAL_PHYSICAL_PYTHON -I -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/formal54_durable_owner.py stop \
  --owner-directory ACTUAL_OWNER_DIRECTORY --registry-sha256 ACTUAL_REGISTRY_FILE_SHA --signal TERM
```

The stop command waits for the durable terminal without a five-second forced
kill. Interrupting its wait leaves the recorded graceful request active; it
does not escalate. Do not wrap this owner/serial with the unchanged project's
monitor **run** action. Its separate **watch** action can observe the recorded
actual Linux serial PID, while these original receipts remain authoritative.

## Validation and remaining risks

Only Windows static and fake-process tests are author validation. They do not
spawn a child, use WSL, load a real serial/guard, read a bag/model, start ROS,
or prove native detach/signals. The final receipt records the actual count and
source pins. Native source `test_native_durable_dummy.py` is supplied **unrun**;
root must schedule it in a genuinely idle native window:

```bash
ACTUAL_PHYSICAL_PYTHON -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/test_native_durable_dummy.py
```

It uses explicitly synthetic metadata and a temporary Python dummy serial,
never the real guard or a formal flight. It checks launch detachment, stopping a
real watch without killing the dummy, both real INT/TERM paths, dummy cleanup,
actual Popen wait and original terminal identity/exit binding. Its synthetic
canonicals are fixture inputs and cannot replace the accepted actual serial
canonical in a real launch.

A WSL shutdown, Windows restart, OOM or external forced kill can still break
ownership. A worker missing without its terminal stays incomplete; this tool
does not automatically adopt, retry or kill a possible orphan serial. Disk/I/O
failure can prevent publishing evidence even while a handle is safely waited.
`/proc` verification and positive-PID signaling are separate kernel operations;
the narrow identity-check/signal race is not an atomic pidfd guarantee. Launch
and stop require independent source review and native validation before actual
formal use. Closing the Codex conversation does not create a callback: an
actually launched detached owner can continue its process work, and progress
must be read from these files/watch; agent messages require an active turn.
