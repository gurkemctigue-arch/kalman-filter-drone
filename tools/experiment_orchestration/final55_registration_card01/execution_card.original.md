# Final55 normal registration and complete-source sealing execution card

Status: STATIC FUTURE EXECUTION CARD ONLY. No command in this card has been run.
This card extends `planning/reliability-v4-final-registration-execution.md` using
actual current source. It does not report core12/safety4/extension16 completion,
create a plan/contract, publish metadata, modify frozen54, start WSL/native or
admit a formal slot. Every `ACTUAL_...` input below must be an existing measured
artifact before that action; future timestamps and guessed pins are forbidden.

## 1. Selected route and immutable roots

- Development algorithm root stays `/root/uav_tracking_fullplan_v4_humble54`.
- The independent audit package stays `/root/uav_tracking_snapshot_audit54_tools01`.
- Its exact guard path remains `/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py` throughout safety registration, registrar seal, formal48 and serial execution.
- A future fresh algorithm root may be `/root/uav_tracking_fullplan_v4_final55`.
- Current tools are public normal runner, audit safety, stat storage, public probe gate and audit registrar. The old DDS48 finalroot-v2 candidate/publication/sealer chain and source53 execution contexts are unselected. No historical candidate/publication receipt is created to imitate them.

The audit package's four source files and package marker have original byte
snapshots, but source preservation alone does not validate native execution.
Real native audit/safety/owner acceptance remains whatever the original tools
require. This card adds no flight, denominator or acceptance gate.

## 2. Evidence required before this registration sequence

Use the actual complete canonical seed004 core12 plan and its original 12
terminal records, actual four-safety prospective registry/facts/executions with
4/4 PASS, and actual complete seed004 extension16 plan and all original 16
terminal records. Retain ordinary engineering FAILs and infrastructure stops.
A core gate requires the existing complete engineering checks; extension gate
preserves permitted algorithm failures but cannot conceal missing/safety/native
or infrastructure evidence. An incomplete original matrix does not become
complete merely because this card exists. Named person/car stage1_velocity
exports/calibration use only those canonical12 slots; their export CLI and
candidate generation remain the original steps in the planning document.

Use the existing public stat tools for capacity after the 28 original trials
are closed; do not rerun evaluators or read bag payloads just to measure sizes:

```bash
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_audit=/root/uav_tracking_snapshot_audit54_tools01
tracking_core_dev="$tracking_dev/results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
tracking_extension_dev=ACTUAL_EXTENSION16_PLAN_JSON
tracking_sizes=ACTUAL_NEW_INDEPENDENT_SIZE_DIRECTORY
tracking_inventory=ACTUAL_NEW_HOST_INVENTORY_JSON
tracking_assumptions=ACTUAL_EXPLICIT_STORAGE_ASSUMPTIONS_JSON
tracking_budget=ACTUAL_NEW_INDEPENDENT_BUDGET_JSON

bash "$tracking_dev/scripts/run_research_session.sh" \
   "$tracking_audit/tools/reliability_v4_guard.py" storage-probe \
   --distribution UAVHumble22 --mount /mnt/d --output "$tracking_inventory"
bash "$tracking_dev/scripts/run_research_session.sh" \
   "$tracking_dev/tools/measure_reliability_v4_storage.py" \
   --core-development-plan "$tracking_core_dev" \
   --extension-development-plan "$tracking_extension_dev" \
   --physical-inventory "$tracking_inventory" --output "$tracking_sizes"
bash "$tracking_dev/scripts/run_research_session.sh" \
   "$tracking_dev/tools/reliability_v4_storage_budget.py" \
   --core-development-plan "$tracking_core_dev" \
   --extension-development-plan "$tracking_extension_dev" \
   --size-evidence-dir "$tracking_sizes" --physical-inventory "$tracking_inventory" \
   --assumptions "$tracking_assumptions" --output "$tracking_budget"
```

Use only actual distinct Windows mounts; `/mnt/d` is the currently identified
host/data volume, not an instruction to fabricate other disks. The budget
output's `storage` object is the admission-request storage value. The same
physical volume must aggregate results/VHD growth once; the original guard
rechecks real capacity at seal and before each slot. A stat budget preview is
not initial admission. Preserve the three-raw/two-compressed bound and actual
reservations; do not infer missing assumptions from a successful build.

## 3. Fresh final root: build while all top-level protocols remain DRAFT

The actual source entry is `scripts/freeze_full_plan_workspace.sh`; no current
`freeze_candidate.sh` entry was found. The current reviewed wrapper is:

```bash
tracking_source=ACTUAL_SOURCE_OR_REVIEWED_STAGING_ROOT
tracking_final=/root/uav_tracking_fullplan_v4_final55
tracking_results="/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_final55"

/bin/bash "$tracking_source/tools/diagnostics/reliability54_build01/prepare_and_validate.sh" \
   "$tracking_final" "$tracking_results" "$tracking_dev"
```

This is a future heavy native window. `tracking_source` is inferred from the
wrapper's own location. Its five runtime registrations must exactly match
reference54. It must supply the same actual flight/model/runtime sources as the
completed development evidence; do not use merely similar version names.
`tracking_final` and `tracking_results` must be fresh, and the results-store
parent must already exist. The wrapper currently accepts the dedicated D-drive
results regex. Public freeze also expects the source's actual
`results/recorded_estimator_research/research_report.json` for its build copy.

Do not run that copy directly from immutable frozen54: frozen54 has a generated
`results` symlink. The integrity helper explicitly refuses a source map already
containing that symlink when validating a newly generated results link, and the
copy/ln sequence must not merge old results. Use the checked project source or a
fresh reviewed staging source with a normal results directory, keeping frozen54
read only. Review source-map equality rather than changing immutable54.

The wrapper clears inherited old prefixes, sources ROS/venv/bridge/PX4 underlays,
uses the system FastCDR CMake package independently of the reviewed DDS runtime,
sets TMPDIR=/tmp, executes public cold colcon/module+ament isolation/full suite,
and preserves complete source_before/source_after/frozen_actual maps plus the
original freeze report. It then calls `record_native_validation.py` to record
compiler selection and actual generated CDR/import evidence.

At this point core and extension top-level status and replay are still DRAFT.
The existing numeric `navigation_acceptance` is already REGISTERED in source;
verify its adopted values, actual requirements file SHA and original numeric
registration rather than resetting them. Numeric registration is distinct from
top-level protocol registration.

Important: `record_native_validation.verify_original_freeze()` rehashes the
complete tree against that cold-build DRAFT map, including planning. It is
appropriate now. After allowed planning publication, do not rerun it and claim
that the whole current tree equals the old DRAFT tree. Keep its original receipt
as cold-build-time evidence; final metadata/tree closure is a new sidecar.

## 4. Target snapshots, gates, then four-safety summary

After the build succeeds, use final55's own wrappers and runner. Both target
plans are definitions only and must remain entirely PENDING forever. Do not
run them. The runner already propagates the explicit split-clock setting; its
plan CLI has no separate split-clock flag.

```bash
export HUMBLE22_PROJECT_ROOT="$tracking_final" STAGE1_PROJECT_ROOT="$tracking_final"
source "$tracking_final/scripts/humble22_env.sh"
tracking_registration="$tracking_final/results/final55_registration"
mkdir "$tracking_registration"
tracking_core_target_output="$tracking_final/results/final55_target_core"
tracking_extension_target_output="$tracking_final/results/final55_target_extension"
tracking_core_target="$tracking_core_target_output/plan.json"
tracking_extension_target="$tracking_extension_target_output/plan.json"
tracking_core_gate="$tracking_registration/core_gate.json"
tracking_extension_gate="$tracking_registration/extension_gate.json"
tracking_extension_cutoff="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
tracking_safety_facts=ACTUAL_FOUR_SAFETY_FACTS_JSON
tracking_safety_assembly="$tracking_registration/safety_assembly"

bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/run_reliability_v4.py" plan \
   --frozen-root "$tracking_final" --probe --seeds 4 \
   --output "$tracking_core_target_output" --prefix reliability_v4_final55_target_core
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/run_reliability_v4.py" plan \
   --frozen-root "$tracking_final" --probe --extensions --seeds 4 \
   --output "$tracking_extension_target_output" --prefix reliability_v4_final55_target_extension
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
   --target-plan "$tracking_core_target" --probe-plan "$tracking_core_dev" \
   --output "$tracking_core_gate"
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
   --target-plan "$tracking_extension_target" --probe-plan "$tracking_extension_dev" \
   --registration-utc "$tracking_extension_cutoff" --output "$tracking_extension_gate"
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_audit/tools/reliability_v4_register.py" safety-summary \
   --target-plan "$tracking_core_target" --core-gate "$tracking_core_gate" \
   --facts "$tracking_safety_facts" --output-directory "$tracking_safety_assembly"
```

The extension cutoff is a gate-validation cutoff, not protocol registration.
It must follow all 16 actual finished times and not be in the future. If several
plans are really required, repeated `--probe-plan` retains every original slot;
the safety summary specifically requires one complete canonical12 gate.

The safety output is `safety_summary_candidate.json`. Its assembly must happen
BEFORE top-level core/extension publication: `gate_context()` verifies the
actual target protocol SHA, and `assemble_safety()` requires both subsequent
registration times to follow its actual summary creation. Publishing top-level
metadata first would stale the target definition and violate the time ordering.
After publication retain the original target/gate artifacts, but do not try to
rebuild gates or reassemble safety against the now-stale DRAFT target protocol.

## 5. Restricted core/extension publication

The small public metadata helper source is now present at
`tools/reliability_v4_publication.py`. Its actual source CLI is `protocols`,
`replay`, and `source-sidecar`, each taking `--request`, `--request-sha256`, and
`--output-directory`. The code must have its own accepted source review and
validation before use; this card is not that acceptance. Keep it outside the
fixed native audit package rather than changing that package's four tool bytes.

Do not assume immutable a32060d/frozen54 or a staging copy of it contains this
newly added helper. `tracking_publication_source` names the separately reviewed
Git-checkout file, independently of the algorithm copy source.
The helper is stdlib-only until it explicitly imports the request-bound roots;
it has no parent-directory ROOT assumption. Deploy the accepted source as a
new independent tool copy and call it through final55's wrapper. These are
future copy/byte-check steps, never writes to the fixed audit package:

```bash
tracking_publication_source="/mnt/d/基于yolo和卡尔曼滤波/tools/reliability_v4_publication.py"
tracking_publication_root=/mnt/d/WSL/UAVHumble22-validation/final55_publication_tools01
tracking_publication="$tracking_publication_root/reliability_v4_publication.py"
tracking_publication_sha=8e1c903e25abe1557e64c2ab4c64662691e8962aeb2769aa57d2ec57f8064cd6
mkdir "$tracking_publication_root"
cp -- "$tracking_publication_source" "$tracking_publication"
printf '%s  %s\n' "$tracking_publication_sha" "$tracking_publication" | sha256sum --check --strict
cmp -- "$tracking_publication_source" "$tracking_publication"
```

The literal SHA above is the statically reviewed 30,259-byte source revision,
not a claim that this copy or native invocation already exists. Source changes
require a new review/pin; do not silently substitute another producer version.
If the chosen cold-copy source includes this file, the actual final55 complete
map includes that in-root source copy too. If it does not, the final map must not
claim to contain the external helper: the publication started/outcome ledgers
instead retain the actual external producer path/SHA, and its Git original must
be delivered separately. The external producer is not part of the algorithm
root's full-map inventory. Do not amend a cold frozen tree to add it afterward.

The helper requires each of its three output directories to be a fresh DIRECT
child of resolved final results; the commands below use that shape. Request JSON
files may remain in the separate registration metadata directory.

The following literal shell function creates a fresh request from actual file
bindings for that existing source interface. It does not publish anything.
Only set `tracking_publication` and its SHA to the actually reviewed helper.
Do not substitute a guessed SHA or use an unreviewed changing workspace file.

```bash
tracking_registration="$tracking_final/results/final55_registration"
tracking_protocol_request="$tracking_registration/protocol_publication_request.json"
tracking_protocol_publication="$tracking_final/results/final55_protocol_publication"

tracking_publication_request() {
  tracking_pub_action="$1"
  tracking_pub_request="$2"
  shift 2
  bash "$tracking_final/scripts/run_research_session.sh" - \
    "$tracking_publication" "$tracking_publication_sha" "$tracking_final" "$tracking_audit" \
    "$tracking_pub_action" "$tracking_pub_request" "$@" <<'PY'
import hashlib
import importlib.util
from pathlib import Path
import sys

producer, accepted_sha, root, audit, action, output, *inputs = sys.argv[1:]
producer = Path(producer).resolve(strict=True)
assert hashlib.sha256(producer.read_bytes()).hexdigest() == accepted_sha
spec = importlib.util.spec_from_file_location("accepted_final55_publication_request_api", producer)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)
root = Path(root).resolve(strict=True)
audit = Path(audit).resolve(strict=True)
archive = (root / "results/freeze_validation/source_integrity").resolve(strict=True)
labels = {
    "protocols": ("core_target", "extension_target", "core_gate", "extension_gate", "safety_assembly"),
    "replay": ("protocol_publication", "core_plan", "replay_assembly"),
    "source-sidecar": ("protocol_publication", "replay_publication", "admission", "native_validation"),
}[action]
assert len(inputs) == len(labels)
request = {
    "schema_version": 1, "kind": pub.KIND, "final_root": str(root),
    "audit_guard": pub.binding(audit / "tools/reliability_v4_guard.py"),
    "freeze_report": pub.binding(archive / "source_frozen_integrity.json"),
    "frozen_map": pub.binding(archive / "frozen_actual.json"),
}
request.update({name: pub.binding(value) for name, value in zip(labels, inputs)})
assert set(request) == pub.FIELDS[action]
pub.write_new(Path(output), request)
print(pub.sha(output))
PY
}

tracking_protocol_request_sha="$(tracking_publication_request protocols "$tracking_protocol_request" \
  "$tracking_core_target" "$tracking_extension_target" "$tracking_core_gate" "$tracking_extension_gate" \
  "$tracking_safety_assembly/outcome.json")"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_publication" protocols --request "$tracking_protocol_request" \
  --request-sha256 "$tracking_protocol_request_sha" --output-directory "$tracking_protocol_publication"
```

The request's common exact fields are `schema_version`, `kind`, `final_root`,
`audit_guard`, `freeze_report`, `frozen_map`; the kind is
`RELIABILITY_V4_EXPLICIT_PLANNING_PUBLICATION_REQUEST`. Protocol publication adds
only the five exact bound inputs shown above. `safety_assembly` is the original
registrar `outcome.json`, not a hand-written PASS object or a guessed candidate
path. The common report/map pins always point to this new final55 root's actual
cold-build archive, not development54's report.

The helper validates complete unexecuted target snapshots, the actual generated
gates and both original gate-validator branches, and the real audit registrar
safety assembly before changing canonical bytes. It archives the original three
DRAFTs, publishes only core/extension, and records a new outcome. Its success
means metadata publication; it is not a full admission or flight.

Allowed final-tree changes are limited to these three canonical paths:

- `planning/reliability-v4-preregistration.json`
- `planning/reliability-v4-extension-preregistration.json`
- `planning/reliability-v4-estimator-replay-preregistration.json`

For this phase, core changes only top-level `status` and `registration_utc`.
Extension changes only `status`, `registration_utc`, and `development_readiness`.
The readiness value is the actual extension gate `{path,sha256,evidence}`.
Both real UTC stamps follow the actual safety summary, and extension registration
also follows all 16 development terminal times. Neither stamp may be future.
Keep all numeric requirements, classes, seeds, groups, conditions, timing,
resources, model paths, safety policy and existing experiment design unchanged.
Do not alter the replay file during this phase.

The original DRAFT bytes must be archived before replacement in new independent
results directories. A publication temporary file must be in the canonical
planning file's own directory so `os.replace` is on the same ext4 filesystem;
results may resolve to D and cannot be used as the replace source. A partial
publication failure stays evidence to diagnose, not permission to rerun in place.

## 6. Formal definitions: extension --probe-gate is the CORE gate

After BOTH core and extension are REGISTERED, freeze the original full120 and
full160 definitions. Both commands below pass CORE_GATE. The extension gate is
bound separately through the canonical extension protocol's readiness object.
`make_extension_plan()` first calls `make_plan()`, whose --probe-gate requires
`ready_for_formal_reliability_v4` and the original core checks. Passing EXT_GATE
here would be wrong. The older planning document's CORE_GATE example is correct.

```bash
tracking_core_formal_output="$tracking_final/results/final55_core120"
tracking_extension_formal_output="$tracking_final/results/final55_extension160"
tracking_core_formal="$tracking_core_formal_output/plan.json"
tracking_extension_formal="$tracking_extension_formal_output/plan.json"

bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/run_reliability_v4.py" plan \
   --frozen-root "$tracking_final" --formal --probe-gate "$tracking_core_gate" \
   --output "$tracking_core_formal_output" --prefix reliability_v4_final55_core
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_final/scripts/run_reliability_v4.py" plan \
   --frozen-root "$tracking_final" --formal --extensions \
   --probe-gate "$tracking_core_gate" --reference-plan "$tracking_core_formal" \
   --output "$tracking_extension_formal_output" --prefix reliability_v4_final55_extension
```

Use no classes/groups/conditions/seeds subsets and never execute these bare
formal runner plans. They must remain 280/280 PENDING through replay registration
and the first seal. The public runner checks the current source and all original
gate bindings; source54's original flight sources and policy can qualify a new
final55 root through those exact checks, without a source53 wrapper. A changed
flight/model/runtime policy does not gain that qualification from this card.

## 7. Assemble replay candidate, then publish its exact bytes

```bash
tracking_calibration_candidate=ACTUAL_CANONICAL12_R0_CANDIDATE_JSON
tracking_replay_assembly="$tracking_registration/replay_assembly"

bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_audit/tools/reliability_v4_register.py" replay-config \
   --core-plan "$tracking_core_formal" --candidate "$tracking_calibration_candidate" \
   --output-directory "$tracking_replay_assembly"
```

This produces `replay_configuration_candidate.json` and preserves the exact
canonical replay DRAFT as `source_draft.original.json`. It binds the complete
core.source_hashes, real named development records/arrays/sidecars/recording
metadata and validated calibration geometry. It requires all core120 slots
PENDING. It does not publish the canonical planning file. Publication must copy
that validated candidate's SAME bytes, not reconstruct its JSON or reset UTC.

Use the same accepted helper and request builder; bind the earlier successful
protocol-publication outcome, the actual core plan, and the original replay
registrar outcome. No new replay fields are filled manually.

```bash
tracking_replay_request="$tracking_registration/replay_publication_request.json"
tracking_replay_publication="$tracking_final/results/final55_replay_publication"
tracking_replay_request_sha="$(tracking_publication_request replay "$tracking_replay_request" \
  "$tracking_protocol_publication/outcome.json" "$tracking_core_formal" \
  "$tracking_replay_assembly/outcome.json")"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_publication" replay --request "$tracking_replay_request" \
  --request-sha256 "$tracking_replay_request_sha" --output-directory "$tracking_replay_publication"
```

The three replay-specific request fields are exactly `protocol_publication`,
`core_plan`, `replay_assembly`. The helper uses the actual validated registrar
artifact bytes and its original DRAFT archive, validates registration/artifacts
again, and refuses an already executed formal slot or already registered replay.
Its source snapshot remains distinct from the audit four-tool package.

## 8. Actual admission request, registrar seal, and read-only check

The request has exactly these top-level fields, with actual existing pins:
`schema_version,kind,final_root,plans,registrations,calibration,safety,state_directory,storage`.
The kind is `RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST`. Plans are core/extension
file bindings; registrations are canonical core/extension/replay bindings;
calibration is the actual candidate binding; safety is the actual summary binding;
storage is the actual budget output's `storage` object. The state directory is a
fresh independent path under final results and MUST NOT be precreated. Do not
supply created_utc/tool/manifest digest: registrar creates these actual fields.
A whole-source sidecar is not an allowed extra request field.

The following is a literal future metadata assembly step, using the real fixed
audit guard's binding/write APIs. It creates only the new request file, not a
seal/state/flight. Select actual paths before running it:

```bash
tracking_request="$tracking_registration/admission_request.json"
tracking_state="$tracking_registration/guard_state"
tracking_safety_summary="$tracking_safety_assembly/safety_summary_candidate.json"

bash "$tracking_final/scripts/run_research_session.sh" - \
  "$tracking_final" "$tracking_audit" "$tracking_core_formal" "$tracking_extension_formal" \
  "$tracking_calibration_candidate" "$tracking_safety_summary" "$tracking_budget" \
  "$tracking_state" "$tracking_request" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

root, audit, core, extension, calibration, safety, budget, state, output = map(Path, sys.argv[1:])
root = root.resolve(strict=True)
audit = audit.resolve(strict=True)
guard_path = audit / "tools/reliability_v4_guard.py"
assert str(guard_path) == "/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py"
spec = importlib.util.spec_from_file_location("actual_final55_admission_guard", guard_path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
assert guard.sha(guard_path) == "e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e"
state = state.absolute()
assert not state.exists() and not state.is_symlink()
assert state.resolve().is_relative_to((root / "results").resolve(strict=True))
assert state.resolve() != (root / "results").resolve(strict=True)
value = json.loads(budget.read_text(encoding="utf-8"))
assert value["admission_performed"] is False
request = {
    "schema_version": 1, "kind": "RELIABILITY_V4_ADMISSION_ASSEMBLY_REQUEST",
    "final_root": str(root),
    "plans": {"core": guard.file_binding(core), "extension": guard.file_binding(extension)},
    "registrations": {
        "core": guard.file_binding(root / "planning/reliability-v4-preregistration.json"),
        "extension": guard.file_binding(root / "planning/reliability-v4-extension-preregistration.json"),
        "replay": guard.file_binding(root / "planning/reliability-v4-estimator-replay-preregistration.json"),
    },
    "calibration": guard.file_binding(calibration), "safety": guard.file_binding(safety),
    "state_directory": str(state), "storage": value["storage"],
}
guard.write_new(output, request)
print(json.dumps(guard.file_binding(output), indent=2))
PY
```

```bash
tracking_seal_assembly="$tracking_registration/seal_assembly"
tracking_admission="$tracking_seal_assembly/final_admission.json"
tracking_check="$tracking_registration/final_guard_check.json"

bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_audit/tools/reliability_v4_register.py" seal \
   --request "$tracking_request" --output-directory "$tracking_seal_assembly"
bash "$tracking_final/scripts/run_research_session.sh" \
   "$tracking_audit/tools/reliability_v4_guard.py" check \
   --manifest "$tracking_admission" --output "$tracking_check"
```

The registrar automatically binds its adjacent audit guard's exact absolute
path/bytes, calls the real full guard check, and requires pending280 and no state
creation. It exclusively publishes `final_admission.json` with the validated
bytes and an assembly outcome. This proves ADMISSION_CHECK_ONLY; it is not the
initial-full280 receipt or a flight. Replacing its tool path with final55's
same-named guard would be rejected. Formal48 loads the actual manifest.tool.

## 9. Complete final source/planning sidecar, preserving the cold DRAFT maps

After the real registrar seal, use the same accepted helper's actual third
action. This is an explicit final-source metadata operation; it creates no plan,
state or trial. It reads/hashes the complete filtered source map, including
weights, so schedule this final closure once rather than treating it as a free
progress query.

```bash
tracking_sidecar_request="$tracking_registration/source_sidecar_request.json"
tracking_sidecar_output="$tracking_final/results/final55_source_sidecar"
tracking_sidecar_request_sha="$(tracking_publication_request source-sidecar "$tracking_sidecar_request" \
  "$tracking_protocol_publication/outcome.json" "$tracking_replay_publication/outcome.json" \
  "$tracking_admission" "$tracking_final/results/freeze_validation/native_build_supplement.json")"
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_publication" source-sidecar --request "$tracking_sidecar_request" \
  --request-sha256 "$tracking_sidecar_request_sha" --output-directory "$tracking_sidecar_output"
```

The four specific fields are `protocol_publication`, `replay_publication`,
`admission`, and `native_validation`. The latter binds the original successful
final55 cold-build supplement; use its actual retained filename if a separately
retained correction has a different name, without rewriting the old supplement. The source currently emits `registered_final_map.json` and
`registered_source_sidecar.json`, plus the independent started/outcome ledger.
It calls the original fixed guard's read-only check and requires all280 PENDING
with no guard state before retaining this final sidecar. The sidecar explicitly
states that the current final tree does not equal the original DRAFT tree.

The existing public `source_integrity.file_map(root)` covers the full original
rsync-filtered source, including ignored source/runtime registrations, weights
and symlink targets. `differences(expected,actual)` reports missing/added/changed.
The generated `results` symlink must be verified against the original declared
store and removed only from the copy-source comparison, exactly as the original
freeze verification does. Do not read results/bag/VHD content into this map.

The final sidecar must retain and bind the ORIGINAL cold-build DRAFT report and
three maps, import/native-build receipts and raw DRAFT archives. Recompute a NEW
complete final tree map after all three canonical registrations are published.
Require no missing or added source path and no changed source except the three
explicit canonical planning paths. Require the exact published core/extension
allowed-field deltas and replay candidate bytes, and the same actual results
link. Bind final canonical files, both immutable formal plans/gates, safety,
calibration/capacity artifacts, fixed audit guard/tools and actual admission.
Write a new independent sidecar with its own digest into results; do not replace
any cold-build map/report, source_sha256.txt or native_build_supplement.

The registrar seal does not itself implement a complete-tree sidecar. The old
finalroot-v2 sealer implements one only through its unselected old candidate/
publication chain; it is not an appropriate substitute for current actual
normal54-owner artifacts. The new public metadata helper uses the existing file_map/differences/write_new
APIs to record this final allowed transition, with no algorithm change. It needs
its own source/metadata validation before actual use; this static card is not
native acceptance.
This remains an independent source seal, not a fabricated old publication receipt
or an extra field accepted by the original registrar.

## 10. Formal execution boundary

Only after actual original prerequisites, native validation and complete final
metadata/source closure may the existing formal54 supplementary/serial/durable
owner sequence consume the actual admission. It must use the original full280
plans and fixed audit guard. This card does not launch that owner or authorize a
retry. Original ordinary FAILs stay in their denominators; infrastructure stops
need the original exact separately bound diagnosis before another PENDING slot.

`check` leaves guard state untouched. Actual `run-one` is the operation that
creates initial_full280/state receipts and consumes one original PENDING slot;
the formal48/supplementary/serial wrappers retain ownership and existing checks.
Never substitute a bare runner batch or an unselected legacy finalroot wrapper.

## 11. Source-review facts and remaining minimal work

- Public registrar supports an audit root different from algorithm root. All
  three registrar actions must use the fixed audit package's copy, not final55's
  similarly named file. Its guard loads normal runtime from manifest.final_root.
- Snapshot audit retains original complete map evidence while verifying actual
  scanner-visible flight sources and registered model/DDS, without deleting old
  historical copies. Planning is outside the flight scanner, but that does not
  make the old whole-tree DRAFT map a current final-tree seal.
- The actual cold-build wrapper, normal runner/gate/stat/registrar APIs exist.
  Core/extension canonical publication and final whole-source sidecar are the
  small metadata boundary handled by the new separate publication helper; no new flight controller, candidate
  framework, private legacy module clone or acceptance threshold is needed.
- All future outputs and command invocations require actual retained evidence.
  This card is static source analysis and has not been native-tested or run.

## 12. Static review record (not execution evidence)

The external-review agent independently compared the new helper to the actual
public registrar/safety/guard/build source, rather than treating synthetic
fixtures as proof of those interfaces. The original registrar really writes
`started.inputs`, `outcome.artifact`, `validated_bytes_sha256`, and replay
`detail.source_draft_archive` in the shapes consumed here. The safety driver
sets each fact's `result` from the original slot status; registrar checks the
four PASS facts and deep-copies them into `summary.slots`. The real guard returns
`check(...).report.capacity.pending_slots`. The real native supplement contains
`public_import_isolation` with path/SHA/isolated, and binds the cold original map
and report. These are source compatibility findings, not real final55 outputs.

Independently read source pins for this card revision:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| tools/reliability_v4_publication.py | 30259 | 8e1c903e25abe1557e64c2ab4c64662691e8962aeb2769aa57d2ec57f8064cd6 |
| tests/test_reliability_v4_publication.py | 34075 | 99f20cfcb8b7f378c33f6b00c3c423d41de352c4d0fc465cfedce109affbfc36 |
| fixed audit guard | 86011 | e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e |

The helper and tests, plus both literal request-construction Python blocks in
this card, parsed as Python3.10 syntax without executing those modules. Earlier
static findings (one missing require message and an insufficiently explicit
fixed guard path/SHA) were corrected in the recorded revision. No further
blocking source issue was found in this bounded static review. The author
reported 32 Windows metadata/transaction tests passing in 4.378 seconds; this
review did not rerun them, and their symlink behavior uses Windows mocks.
No raw stdout or runtime receipt was invented for this source review. Real
symlinks, future source deployment, cold build, metadata publication, native
guard integration, source sidecar and any formal slot remain unexecuted here.
