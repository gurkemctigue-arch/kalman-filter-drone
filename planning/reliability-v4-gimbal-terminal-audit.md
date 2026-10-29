# Offline gimbal terminal-message audit

This is an offline evaluation revision, not a new flight result. Keep every
original plan, slot record, report, recording and failure unchanged. All six
development stage-3 slots must receive separately named evaluations, including
the slots whose old gimbal report passed. Formal held-out flights are not run
by any command on this card.

## Accepted terminal redundancy

Gazebo Sim 8.15 `JointStatePublisher::PostUpdate` skips publication only when
`0 < simTime - lastUpdateTime < updatePeriod`; zero elapsed source time can
therefore produce repeated feedback while the world is paused. Source:
[registered upstream implementation](https://github.com/gazebosim/gz-sim/blob/446a44335a45b704b4d36dabcc5508ee34eeb3d8/src/systems/joint_state_publisher/JointStatePublisher.cc#L160).
This observation alone never authorizes ignoring a duplicate.

The new evaluator preserves the complete recorded `/clock` delivery stream.
A successful recording closure must bind a successful pause service ACK and
the observed final Clock. The archive must independently report successful
recorder closure, raw validation and native-reader validation. The recorded
Clock count must match the native archive count, never regress, and end at
the closure's final source time.

Only the contiguous final JointState run at that global final source and
receive time can be redundant. Every JointState field must match, including
header, names/order, position, velocity and effort; float payloads are compared
by their IEEE bits. Normally retain the first terminal sample as independent
timed feedback and exclude its later redundant copies.

A real final-source feedback sample can arrive just before the Clock callback
for that final time. Revision 2 retains this preceding real sample when the
complete delivery sequence is valid, its latest preceding Clock equals its
receive time, its first following Clock is the global final Clock, its source
leads its receive Clock by at most exactly 50,000,000 nanoseconds, and its
complete payload equals the subsequent terminal run. The terminal run must
start after that final Clock callback, with no earlier feedback at the same
source time. Only subsequent copies whose source and receive times both equal
the global final Clock are excluded; the preceding real sample is retained.
Its source, receive time and record sequence remain explicit in the audit.

Redundant copies supply no geometry/interpolation/sample denominators.
Original positive duplicate counts and original delivery-order errors remain
in the report alongside effective counts and a payload hash. Missing or
regressing delivery sequence, an intermediate Clock, conflicting preceding
payload, excess source lead or multiple early duplicates cannot satisfy this
additional boundary case.

Live or middle duplicates, time resumed after a duplicate, payload conflicts,
regression, later zero, missing complete Clock, unsuccessful pause/closure or
final Clock mismatch remain failures. The pure fixture API without
`pause_context` retains the original strict duplicate behavior. No online
callback, control, association or flight-safety threshold is changed.

## Preparation and execution

Prepare a new frozen evaluation source root by replacing only these offline
classes in a copy of the original source snapshot:

- `scripts/evaluate_stage3_gimbal.py`;
- `scripts/run_reliability_v4.py` (excluded from flight-source mapping);
- `scripts/build_reliability_v4_probe_gate.py` (an offline helper).

The new target PROBE plan must bind those exact immutable sources. Registering
six diagnostic evaluation commands allows navigation thresholds to remain
DRAFT; it does not register thresholds or authorize an acceptance gate.
Creating a final development gate still requires genuinely REGISTERED numeric
navigation thresholds and all existing acceptance checks. The target is an
evaluation source snapshot only. Confirm its
flight-source map equals the immutable original PROBE plan before evaluation.
Do not edit the old source snapshot to make validation pass.

Set shell variables to the actual new target plan, immutable original plan,
registration output and completed overrides-manifest paths. Paths below are
placeholders, not completed evidence.

```bash
python -B NEWROOT/scripts/build_reliability_v4_probe_gate.py \
  --target-plan NEW_TARGET_PLAN --probe-plan ORIGINAL_CORE_PLAN \
  --register-gimbal-reevaluations --output SIX_GIMBAL_REGISTRATION
```

This command exclusively creates the registration and runs zero evaluators.
It records all six original slot/report SHA bindings and exact future argv,
including `--selected-target` for the two multi-target slots. It refuses an
existing registration or an already existing reevaluation output. The fixed
new report name is `gimbal_terminal_audit_rev2.json`, inside each original trial.
Every original flight must already have an immutable completed record.
Keep every revision-1 source snapshot, registration, execution manifest,
`gimbal_terminal_audit_v4.json` report and its original FAIL unchanged. Use a
new source root, new registration and new six-slot execution manifest for
revision 2; no revision-1 execution or registration can substitute for them.

Execute each `planned_evaluations[].command` exactly, serially, during the
designated bag-analysis window. Preserve actual start/end UTC, exit code,
error and an exclusively created log for each invocation. This is the only
step that reads bags. `0` means evaluator PASS; `2` preserves a substantive
FAIL/INCOMPLETE verdict. Do not retry or omit failed reevaluations.

The evaluator automatically SHA-binds `recording_closure.json` and
`bag_integrity.json` from that same trial. The registered argv also binds
`--source-plan`, `--slot-record` and `--original-report`. Output creation is
exclusive. Its `evaluation_source` records actual script and reader/geometry
helper hashes. It does not hash large bag files again.

## Completed overrides manifest

Write a separate JSON only after all six executions have ended:

```json
{
  "schema_version": 1,
  "kind": "RELIABILITY_V4_SIX_STAGE3_GIMBAL_REEVALUATIONS",
  "registered_utc": "COPY_REGISTRATION_CREATED_UTC",
  "created_utc": "ACTUAL_COMPLETION_UTC",
  "prospective_registration": {"path": "REGISTRATION_ABSOLUTE_PATH", "sha256": "ACTUAL_SHA256"},
  "source_plan": {"path": "ORIGINAL_PLAN", "sha256": "ACTUAL_SHA256", "plan_sha256": "ORIGINAL_DIGEST"},
  "evaluation_source_hashes": {"COPY_ALL_KEYS_FROM_REGISTRATION": "COPY_ALL_VALUES"},
  "predetermined_gimbal_slots": ["COPY_ALL_SIX_SORTED_IDS_FROM_REGISTRATION"],
  "slots": [{
    "slot_id": "ACTUAL_ID",
    "record_file_sha256": "ORIGINAL_RECORD_SHA256",
    "evaluation_overrides": [{
      "kind": "gimbal",
      "original_report_sha256": "ORIGINAL_GIMBAL_REPORT_SHA256",
      "report": "NEW_REPORT_ABSOLUTE_PATH",
      "report_sha256": "ACTUAL_NEW_REPORT_SHA256",
      "evaluation_root": "NEWROOT",
      "execution": {
        "command": ["EXACT_REGISTERED_ARGV_ELEMENTS"],
        "started_utc": "ACTUAL_UTC",
        "finished_utc": "ACTUAL_UTC",
        "returncode": 0,
        "error": null,
        "log": "ACTUAL_LOG_ABSOLUTE_PATH",
        "log_sha256": "ACTUAL_LOG_SHA256"
      }
    }]
  }]
}
```

Include all six slot entries and their actual verdicts. The manifest kind is
specific to this complete core stage-3 matrix; it does not authorize changing
other evaluator results or stress-extension records.

```bash
python -B NEWROOT/scripts/build_reliability_v4_probe_gate.py \
  --target-plan NEW_TARGET_PLAN --probe-plan ORIGINAL_CORE_PLAN \
  --evaluation-overrides-manifest COMPLETED_MANIFEST --output NEW_CORE_GATE
```

The builder and the existing independent `validate_probe_gate` both recheck
the original evidence, separate registration, all-six coverage, source hashes,
actual argv/selected-target flag, UTC order, logs and five report input
bindings. The old terminal status counts remain visible in gate generation.
An original FAIL is never replaced inside its record. A failed reevaluation
or any unrelated unsatisfied navigation/safety requirement still prevents
core gate publication.

## Validation scope

Pure tests cover strict default behavior, complete payload conflicts, missing
or regressing Clock, closure/ACK/final-time failures, middle/live duplicates,
later zero, independent sample denominators, selected-target metrics,
exclusive report creation, source provenance, historical command compatibility,
complete registration/manifest bindings, wrong command/log/old SHA and omitted
slots. These tests are software evidence; actual six-bag results must be
reported separately after execution.
