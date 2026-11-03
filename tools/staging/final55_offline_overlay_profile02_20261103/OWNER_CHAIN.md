# Prepared preserved-attempt owner chain

This is a read-only validator implementation, not an actual continuation
registration. `PRODUCTION_ENABLED` is false and `PRODUCTION_PROFILE` is empty.
The CLI refuses before reading a profile, writing a receipt, starting a task,
or staging an overlay. No actual frontier, root review, continuation history,
owner05 profile, or final owner closure is instantiated by these files.

The implementation reuses `validate_owner_closure.py` with raw SHA-256
`945717313097725eba537f9078297f3e91e32bfdde89e810ed01ae7a2a3d546f`.
The original file is checked when imported and again at the beginning and end
of every chain audit. Its stable source binding is included in `input_bindings`.
The fixed slot implementation is not modified by this new chain validator.

## API and result boundary

`validate_chain(profile, read=small_reader, now=actual_utc)` accepts a profile
already fixed by its caller. It validates one or more closed owner segments
against the same original sixteen-slot plan and class-specific capture contract.
`validate_continuation_profile(...)` additionally requires a nonempty incomplete
contiguous original prefix.

An incomplete prefix produces `BOUND_PRESERVED_PREFIX_CHAIN`. A full chain
produces `OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION`. Neither status is a
flight behavior PASS, a cold-build result, a native-idle check, staging admission,
or launch permission. Original `PASS`, `FAIL`, and `INCOMPLETE_EVIDENCE` remain
unchanged. Unsupported metadata faults refuse instead of acquiring an invented
exception or claiming a completed owner.

The gate and outer supervisor are separate source files. Owner05 executes the
registered gate with `--profile PROFILE --output OWNER --execute`; the gate
calls collector05 in the same Linux process. Native `owner_source` consequently
identifies collector05, while the actual WSL argv identifies the gate. These
roles must not be conflated.

## Profile structure

The common root fields are `plan` (raw path and SHA binding), `plan_digest`,
`source_digest`, `class_model_contract`, `snapshot_audit_contract`, and ordered
`segments`. They use the same source308/capture204 rules as the fixed slot
validator. Exactly seventeen named historical nested build files remain part of
capture204. They are not deleted, ignored generically, or equated with source308.

Each segment contains:

- Unique `segment_id`, original `disposition`, and exact preceding `after_slot`.
- `source_files`, `description`, `launch_files`, and `closure_files`.
- Initial owner04 also has its original `native_plan_alias`; its source roles
  are `launcher`, `monitor`, `collector`, `entry`, and `plan`.
- A continuation adds `gate`, `chain_validator`, and `registered_profile` source
  roles. Its description adds `registered_admission_unc` to the original owner04
  description fields. All seven pins exclude the launcher; `launcher_source`
  binds the launcher separately.

Every file binding is exactly `{path, sha256}`. The early launch roles for
owner04 are `started`, `first_monitor`, and `first_native`. A registered
continuation additionally binds `registered_admission` at the original external
native owner sibling `OWNER.admission.json`.

All segments bind closure roles `outer_terminal`, `native_terminal`,
`monitor_final`, `monitor_end`, and exact native `events` JSONL. Continuations
also bind `registered_entry_terminal` under their original native owner.

Original external native owner files stay external. Only the authenticated
plan's `frozen_root/results` alias is redirected to its original `results_root`,
as implemented by the fixed slot reader. No broad `/root` redirection exists.

## Controlled owner04 stop

`ROOT_REVIEWED_CONTROLLED_STOP` is supported only with actual named evidence.
It preserves original native and Windows status `STOPPED_FAULT` and actual
exit2. It does not relabel them as successful completion.

Its `stop_evidence` binds exactly `root_review`, `intent`, `native_state`,
`windows_started`, `signal_tool`, `preflight`, `signal_receipt`, and
`prepared_source`. The source file and original launch pins must match those
in the original registered intent and signal preflight. Only a positive
collector PID signal is accepted; PID/boot/start ticks and child PPID identify
the actual collector and original current child.

The `root_review` is written by the parent only after real closure. It contains:

- `schema_version: 1`, `status: ROOT_REVIEWED_CLOSED_FRONTIER_PRESERVED`,
  `kind: CONTROLLED_SIGINT_COLLECTOR_ROLLOVER`, `segment_id`, and actual
  `reviewed_utc` after the outer owner terminal time.
- Common `plan` with path/raw SHA and original `plan_sha256`.
- Exact `outer_terminal`, `native_terminal`, `events`, `intent`, and
  `signal_receipt` bindings.
- `frontier_record`, the original independent audit row for the unappended
  actual current slot, and `frontier`, its stable projection.
- Actual `original_error: "KeyboardInterrupt: "` and
  `original_engineering_verdict_preserved: true`.

The stable frontier projection uses `id`, `original_status`, `marker`,
`terminal`, `record_sha256`, `started_utc`, and `finished_utc`. Marker and terminal
are original raw file bindings. The audit row retains the original collector
keys `slot_id`, `original_marker`, `original_terminal`, `original_started_utc`,
`original_finished_utc`, `terminal_sha256`, `record_sha256`,
`known_algorithm_failures`, and `unobserved_checks`.

While waiting on its existing child, a controlled SIGINT may leave the frontier
event sequence `START_SLOT` then `STOPPED_FAULT`, without `CHILD_EXIT`, without
`COMPLETE_SLOT`, and without appending to native `collected`. This exact shape
is accepted only when the real original slot terminal independently proves
flight exit0, complete original evaluations, valid capture, known behavior
values, shutter/long-loss safety, and original engineering verdict. The actual
current child must then be observed exited by its original owner and both
Windows held handles must really close. A signal receipt alone proves none of
these. An invented COMPLETE event is rejected.

## Registered continuation

The continuation's `registered_profile` bytes describe exactly the current
chain profile with that continuation and all later segments removed. The
validator recursively audits that strictly shorter profile. Its stable result
must match the actual previous prefix and the gate's early admission.

The stable projection is exactly `status`, `plan`, `after_slot`, `closed_ids`,
`pending_ids`, `closed`, and `input_bindings`. `input_bindings` is a sorted list,
not a mapping; it contains only explicitly read closed evidence and the fixed
slot source binding. There is no generated wall-clock field in the result.
Future pending output creation does not change this old-prefix audit.

The early admission binds the original gate, registered profile, chain source,
collector, same Linux identity, original plan, exact closed/pending IDs and
stable chain result. `unknown_evidence_exceptions` must be `{}` and
`automatic_retry` must be false. Its original raw bytes must match the early
Windows copy, outer observed SHA, and final registered-entry receipt. The
registered-entry receipt also binds the original native terminal raw bytes and
actual exit, and predates actual WSL task exit.

Derived old prefix events are explicitly labeled
`DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX` and
`executed_by_this_owner: false`. They are not additional flights. New slots
require exact `START_SLOT`, `CHILD_EXIT` and original-terminal `COMPLETE_SLOT`
provenance. If a segment begins after k original slots and collects m new slots,
its `collected_slots` is m. A completing continuation has k + m = 16 and exactly
2 + 2k + 3m native events; monitor aggregate event counts alone are insufficient.

Subsequent launches must follow both the preceding real outer exit and its
required actual root review. Reused owners, overlapping segments, reruns, gaps,
wrong source pins, changed raw metadata, unknown behavior, and copied identities
from another final child refuse.

## Small verification

Run only synthetic/small-file Windows checks with:

```powershell
python -B -m unittest discover -s tools/staging/final55_offline_overlay_profile02_20261103 -p 'test_*.py' -v
```

The chain fixtures are inert in-memory receipts. They do not contact WSL,
spawn commands, read bags, claim real flight results, or publish an actual
continuation profile. The independent slot suite additionally checks named
small original metadata using the production reader; it does not read native
processes, models, or large telemetry.
