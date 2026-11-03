# final55 profile02 preparation

This is a separate, **disabled preparation**, not an executable staging driver.
It leaves profile01, the ten reviewed overlay files, flight277, all original
probe01 attempts and the original contract unchanged. The actual new probe02 is
the complete 16-slot registration, not a selection of successful old attempts.

`check_preparation.py` reads only named small metadata. It verifies the fixed
profile01 source bytes before evaluating its constant metadata, constructs a
prospective profile changing exactly four plan/contract pins, and never passes
that profile to `prepare`, `run` or `execute`. No native tree, model or bag is
read. `--execute` always rejects before any input read or output creation.

Run the metadata check from the project root:

```powershell
python -B tools/staging/final55_offline_overlay_profile02_20261103/check_preparation.py
```

The new development contract is
`tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical_probe02_20261103.json`.
It differs from `contract_canonical02.json` by exactly two literal byte
replacements: `source_plan.path` changes probe01 to probe02 and its SHA becomes
the actual new file SHA. Its separate `.creation.json` records the actual UTC,
old/new bytes, observed metadata sources and scope. This is post hoc development
source binding, not formal preregistration or completed four-slot evidence.

## Fixed differences

| Field | Original profile01 | Prospective profile02 |
|---|---|---|
| extension plan | `extension16_probe01_matrix/plan.json` | `extension16_probe02_matrix/plan.json` |
| extension file SHA | `f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055` | `1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54` |
| extension content digest | `ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761` | `837e533b75800c4c3fdd19f4937d55d92e50fe833da5c6b8801494dfbc77d15b` |
| contract file SHA | `f4f5d040b9701dcd6a2fcafbcb672699ba2c16940c1f712756d5d83193e93ea0` | `11bcebbe460eecc24c9c5bc920f977b421013c9df862f60e667e5ee07f3625e3` |
| contract canonical digest | `35f61541d5eab4fddd856a9c4b9ed76f2d6e0c66a8d172cf94256129e2315c17` | `7c689e742d0a5451ac995b1a1bd2efa14ad6f74c14e2056359877f18cafd868e` |

Core12 remains the original core plan. Safety03 remains an independent original
qualification; it does not replace owner closure for the new extension owner.
The 308-source, 185-scanner and 277-flight maps and all ten overlays retain the
reviewed original pins. The changed descriptor bytes will require a newly
computed actual complete cold map; this tool does not predict its SHA.

## Owner closure required before a future enabled revision

`owner_closure.schema.json` defines two document types, without creating any
instance or filling future SHA, state, exit code or UTC. The schema is a design
contract; it is not yet a production validator or a launch authorization.

1. At actual launch, bind the actual plan, collector04, runner/entry and Windows
   monitor source bytes; record the actual Windows monitor and owned WSL PID
   plus creation FILETIME, Linux collector PID/start ticks/boot ID, command argv
   and actual start UTC. Keep `started_utc` separate from document `created_utc`
   and verify it against the original monitor `task.started_utc`. Preserve this
   fixed launch binding.
2. An external observer holding the actual Windows process handles must observe
   both owned WSL and monitor exit, record their integer zero exit codes and
   matching creation identities, then create a separate closure receipt binding
   the launch file, real collector terminal, real Windows end summary and all
   16 new-plan START/terminal files.
3. Require collector `COLLECTION_FINISHED`, `current_slot=null`, integer
   `returncode=0`, no possibly active child and all 16 actual closed slots.
   Preserve actual engineering PASS, FAIL and evidence verdicts. Reject missing,
   interrupted, infrastructure-stop or still-active executions.
4. A future validator must check unique full16 coverage, file digests, process
   identities, exact source pins, evidence semantics and chronology:
   last slot finish <= collector finish <= WSL exit <= monitor exit <= receipt
   generation <= current UTC. JSON Schema alone cannot verify these conditions.
5. Windows `end_summary.json` is written before its monitor exits. Its
   `monitor_check.verified_alive=true` can therefore be normal and cannot serve
   as proof of monitor exit. Process enumeration or a slot gap also cannot
   replace the external held-handle exit observations.
6. Before actual staging, an independently reviewed enabled profile02 must bind
   the real launch/closure files and fixed production collector pins, then
   acquire the existing SITL lock and perform the native idle guard again.

The launch-only profile below now binds actual start files and source pins.
Actual closure and an enabled staging driver remain absent. No arbitrary CLI
receipt, placeholder, current process snapshot or claimed future value can
enable staging. Old probe01 images cannot serve as new
probe02 four-slot evidence; new sensor4 and navigation28 manifests must bind
the new extension16 plus original core12 explicitly.

The intended native collector output is
`/root/uav_tracking_collection54_probe02_owner04`. This names the intended
location only; no receipt instance, terminal status, future SHA or future UTC is
asserted here. Actual launch and closure must come from the real owner run.
For either designed receipt, `record_sha256` must be the SHA256 of canonical
sorted compact JSON with its own `record_sha256` field excluded; a future
validator must independently recompute it and all referenced file digests.

## Actual owner04 validator

`validate_owner_closure.py` implements validation of the **actual outer-owner
format**, rather than requiring instances of the earlier conceptual schema.
The real outer files use raw file SHA256 bindings and have no self digest.
The conceptual schema remains a design document, not the production input
format. This validator has no subprocess, WSL, simulator, model or bag API.

`actual_launch_bindings.json` binds only actual existing `started.json`,
`first_monitor_state.json` and `first_native_state.json`, with real source pins.
It contains no terminal, future exit, future closure SHA or future UTC. The
launcher source is fixed to
`8f6ceb38bc8ce7fb6aa6bec80f02b260b551082bde1d0a700ea1561a87ac79a1`.
Its canonical native plan is the actual `/mnt/d/.../plan.json`; the command's
`/root/.../results/...` alias is verified separately.

```powershell
python -B tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_closure.py --check-launch
```

This checks eight small source/launch files and reports
`PASS_ACTUAL_LAUNCH_ONLY_NOT_CLOSURE`. The earlier `check_preparation.py` remains
the separate four-override preview; its unbound owner flags describe that
preview and do not replace the actual launch check.

Full validation is implemented as the read-only `validate` API and covered by
synthetic in-memory fixtures for the complete single-owner04 shape. It does not
implement a future chain of continued owners. The production CLI is literally disabled and its
fixed closure-profile binding is empty. It rejects before reading input or
creating output. Root must first review actual terminal files, create a new
fixed closure bindings file linked to the immutable launch-profile SHA, then
review the code/pins before enabling full production validation. No arbitrary
profile or receipt override exists on the CLI.

The eventual interface, currently refused, is:

```powershell
python -B tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_closure.py --receipt-output ABSOLUTE_FRESH_EXTERNAL_JSON_FILE
```

Full validation checks both raw owner copies and original native/monitor files;
early/final process creation identities; actual monitor/WSL held-handle and
Popen integer exits; source/plan pins; preserved power lease; all 16 original
markers and self-digested terminals; recording/source metadata; and the exact
50-event invocation sequence. Duplicate, missing, derived or interrupted
attempts, unknown behavior checks, future timestamps, source changes and absent
handles reject. Existing engineering FAIL/INCOMPLETE are preserved. A stopped
owner or unfinished matrix remains insufficient; no continuation exception is
preapproved here.

The independently reusable `snapshot_capture_contract` and `validate_slot`
functions audit one preserved attempt without assuming one owner executed all
16 slots. The snapshot contract is the actual original
`snapshot_audit54_contract03.json`, bound by raw SHA together with its original
1585-entry metadata map and core registration. Capture204 is derived exactly
from scanner185, the 17 named historical build copies, explicit DDS and the
trial's selected model. It is compared separately from registered source308.
Class, trial model, protocol model and model SHA must agree. Person and car use
different exact capture file SHAs (`0094a501...` and `c003f1b8...`). No build
copies are removed or generically ignored.

The slot function also verifies raw runtime configuration and the four original
small evaluator reports. It checks recording, source clock, native startup,
shutter and long-loss safety, and refuses unknown behavior values even if an
owner-provided `unobserved_checks` list is empty. Known algorithm failures remain
failures. The function returns a slot audit, never an owner-closure or project
admission claim. Its default rechecks all read inputs for concurrent changes.

Regression checks include the actual fixed launch files, both named completed
original core capture/configuration/evaluator sets and the actual new probe02
first slot through the production default reader, synthetic source308/capture204 shapes, exact named17
retention, class/model mismatch, and a child marker written before a delayed
START event. They read no bag, large telemetry, model or WSL file. The current
owner04 source and launch record remain untouched; any actual stop and possible
owner05 continuation require their own later review and real evidence chain.

The default `Inputs` reader verifies the plan content digest and binds exactly
`plan.frozen_root/results` to its canonical `plan.results_root`. This avoids
Windows UNC traversal of the Linux results symlink. Original input reference
strings and raw SHA bindings remain unchanged. No other `/root` subtree is
redirected; external owner files retain their original UNC/native handling.

The generic monitor's static identities may retain `alive=true` at closure.
The WSL exit can be observed by the faster outer poll before the generic
monitor records `task.finished_utc`. Final event time can follow the native
collector's `finished_utc`. The validator handles these actual ordering rules
and never treats a polling timestamp as the exact kernel exit time.

A successful future full report uses
`PASS_OWNER_CLOSURE_ONLY_NOT_ENGINEERING_ADMISSION`, with `validated_utc`,
`plan`, `input_bindings`, `slot_count`, `slots`,
`preserved_engineering_counts` and `validator_source`. It authorizes no staging,
native idle claim, cold build, sensor4 evidence, navigation28 gate or formal
admission. The production staging driver for profile02 still requires a
separate implementation and review; profile01 cannot serve as its fallback.
