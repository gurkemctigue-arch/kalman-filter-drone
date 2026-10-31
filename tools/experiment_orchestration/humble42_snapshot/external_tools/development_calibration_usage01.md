# Development calibration wrapper — preparation only

This external tool is `development_calibration.py` with its shell and small
synthetic tests. It does not change the frozen repository or the established
core, safety, extension, observer, build, exporter or calibrator tools.

`describe` reads tool source identities only. `plan` validates the actual
same-candidate core12, safety4 and extension16, their original attempts and
post-wait observer owners, then emits a PENDING command contract. No export,
calibration, inference or flight is launched by planning. The unchanged original
prerequisite validators may hash recorded archive artifacts; planning therefore
is not a promise of zero archive I/O. Do not invoke it alongside an active run.

`run` accepts only the separately reviewed final command contract SHA and one
fresh output directory. Its sole work commands are the unchanged frozen CLIs:

1. Export `person_stage1_velocity_seed004`.
2. Export `car_stage1_velocity_seed004`.
3. Compute the candidate from those two exports and the actual complete core
   PROBE plan, preserving the original person/car and six-group order.

Each original CLI has an 1800 s outer allowance. Exports use no `--registration`
or `--slot-id` flags. There is one original machine-wide `runner.run_lock` around
the three direct commands and an original local runtime observer with a 1800 s
archive wall budget. Every command binds the source/build/candidate/tools,
core/safety/extension prerequisite files, chosen recordings and exact argv.
The first command/validation/source/owner failure stops the batch, retaining
attempt markers, command logs, partial outputs and the unattempted commands.
Existing outputs are never overwritten or resumed.

## Explicit final admission

The independent admission JSON must be a named external
`development_calibration_admission_<name>.json`, schema version 1, scope
`PARAMETERIZED_TWO_NAMED_DEVELOPMENT_EXPORTS_AND_R0_CANDIDATE_ONLY`, status
`FINAL_DEVELOPMENT_CALIBRATION_ADMISSION_INDEPENDENTLY_REVIEWED`, authorized
actions exactly `["plan", "run"]`, and contain all original `core.FALSE_FIELDS`
as false. There are no default source roots, candidates or executable contracts.

It binds all five named JSON files by exact `{path, sha256}`:

- `extension_admission` and `extension_contract`;
- `candidate_manifest`, `core_contract` and `safety_registry`, identical to the
  actual extension admission context.

`tools_canonical_sha256` is the actual calibration tool manifest canonical.
`dependency_tools` is exactly the actual final core, safety and extension
canonicals. They are independently supplied dynamic inputs, rather than draft
pins. The admitted `prefix` must be fresh and distinct from core and extension.

`selection` is exactly:

```json
{"classes":["person","car"],"seed":4,"group":"stage1_velocity","slot_ids":["person_stage1_velocity_seed004","car_stage1_velocity_seed004"]}
```

The `storage` object has exactly `scope`, `temporary_directory`,
`physical_backing_root`, `output_volume_root`, `minimum_reserve_bytes` and
`output_budget_bytes`. Its scope is
`ONE_EXPORT_TEMPORARY_HEADROOM_NOT_FORMAL280_ADMISSION`, reserve is 8589934592
bytes and budget is an independently reviewed positive integer. All three paths
are explicit canonical Linux absolute paths. Temporary must match the actual
Python `tempfile.gettempdir()`, backing must be the actual physical backing
volume and output must be the actual volume containing the output parent.

Capacity is checked before each command, including the unspent output budget.
One export requires `3 * raw_sqlite_bytes + 2 * compressed_sqlite_bytes + 8 GiB`
of logical temporary headroom. Physical backing must cover that requirement
plus the remaining output budget, and the output volume must retain its own
8 GiB reserve. This is not the formal280 storage admission.

## Invocation after independent source/admission review

```bash
bash /mnt/d/WSL/UAVHumble22-validation/development_calibration.sh describe
bash /mnt/d/WSL/UAVHumble22-validation/development_calibration.sh plan \
  --admission /mnt/d/WSL/UAVHumble22-validation/development_calibration_admission_<name>.json \
  --admission-sha256 <independently-reviewed-final-admission-sha>
```

The PENDING contract contains the actual full three argv arrays and bindings.
An independent reviewer must review it and create a separately named final
contract with status
`FINAL_DEVELOPMENT_CALIBRATION_COMMANDS_INDEPENDENTLY_REVIEWED`, preserving its
other bindings. Only then can `run` take that final file and SHA:

```bash
bash /mnt/d/WSL/UAVHumble22-validation/development_calibration.sh run \
  --admission /mnt/d/WSL/UAVHumble22-validation/development_calibration_admission_<name>.json \
  --admission-sha256 <independently-reviewed-final-admission-sha> \
  --contract /mnt/d/WSL/UAVHumble22-validation/development_calibration_contract_<name>_final01.json \
  --contract-sha256 <separately-reviewed-actual-three-command-contract-sha>
```

No actual admission or command contract is supplied with this preparation.

## Output validation and boundary

The wrapper calls the unchanged frozen `verify_export_evidence`,
`bind_named_recording` and `geometry_statistics`. All three actual export
sidecars and the replay payload must bind and pass original numerical/native
evidence checks. R0 uses all unique valid pre-fusion full geometry covariance
observations from FOLLOW through final recorded Clock, including KF rejects;
truth, posterior acceptance and best-performing samples never select membership.

The complete covariance, membership, exclusions, acquisition IDs, provenance,
original Q/P0/EMA/common gate/common support parameters, source/policy hashes and
candidate plan are rechecked. `CANDIDATE_NOT_REGISTERED` remains mandatory.
There is no automatic registration, formal-seed admission, superiority claim,
new flight, inference, retry, recovery or project acceptance.

When `results` is a directory symlink, the plan and exported-array bindings use
the real paths emitted by the frozen calibrator's `resolve(strict=True)` calls.
The exact original CLI argv, recording metadata and terminal-record paths keep
their original spelling. Real temporary Linux directory-link fixtures cover
this connection; both path aliases must identify the same file and SHA.
