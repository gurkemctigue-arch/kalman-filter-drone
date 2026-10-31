# Parameterized independent final-root connection

This package prepares source, cold-builds it, and explicitly publishes validated canonical registrations. It does not admit or execute formal trials. No actual candidate42 source scan, copy, build, prerequisite check, registration, simulation, archive, inference or final admission was performed while preparing these helpers. The author checks use only tiny synthetic temporary files.

The unchanged candidate42 whole-tree map (698 protected files) and classified runner map (293 source files) remain separate. Counts are evidence from the actual source review, never substitute constants in the helpers. The source copy has no overlay. Original three planning DRAFT files and preparation `source_sha256.txt` are retained. The source preparation manifest always describes the original DRAFT source; it must not be rewritten after publication. Only explicit published canonical planning bindings can be allowed by `builder.source_check(context, allowed_planning)`.

## Inert inspection and future source preparation

Use `/root/uav_humble22/venv/bin/python -B` inside `UAVHumble22`; the actual builder owns its clean shell, build, verification and mandatory full suite in one bounded process group. `describe` is inert apart from hashing the small bound external helpers:

```text
python -B prepare_development_final_root.py describe
python -B build_development_final_root.py describe
python -B publish_development_final_protocols.py describe
```

Get the actual reviewed tool manifest canonical SHA from `describe`, independently review it, and supply it explicitly. Select fresh independent paths, for example a new `/root/uav_tracking_fullplan_v4_humble42_final01` source/build root and a separate `/mnt/d/.../results/frozen_fullplan_v4_humble42_final01` results store. These examples are not reservations or authorization. The final root and results store must not exist, their unaliased parents must already exist, and any failed attempt remains retained with no in-place retry.

```text
python -B prepare_development_final_root.py inspect --candidate ACTUAL_CANDIDATE_JSON --candidate-sha256 ACTUAL_CANDIDATE_SHA --destination-root NEW_FINAL_ROOT --results-store NEW_PHYSICAL_D_RESULTS --reviewed-tools-sha256 REVIEWED_HELPER_CANONICAL_SHA --output /mnt/d/WSL/UAVHumble22-validation/NEW_PROPOSAL.json
python -B prepare_development_final_root.py copy --proposal ACTUAL_PROPOSAL_JSON --proposal-sha256 ACTUAL_PROPOSAL_SHA --reviewed-tools-sha256 REVIEWED_HELPER_CANONICAL_SHA
python -B build_development_final_root.py build --preparation-outcome PHYSICAL_RESULTS/freeze_validation/source_preparation_outcome.json --preparation-sha256 ACTUAL_PREPARATION_SHA --reviewed-tools-sha256 REVIEWED_HELPER_CANONICAL_SHA
```

`inspect` deliberately invokes real candidate/source/build authority and source inventory checks; it must wait until the current exclusive heavy action is finished. Source-only preparation does not read or certify development28/calibration readiness. A successful copy does not authorize registration. A successful cold build yields `PHYSICAL_RESULTS/freeze_validation/final_root_build_development01/chain.json`, with actual owned terminal/start/process/log, colcon, system FastCDR, import/ament/bridge origin, eleven generated-message CDR checks, all mandatory test/skip evidence, and strict512 runtime closure. It authorizes no flight.

All `{path, sha256}` pins use **resolved physical ordinary-file paths**, especially results JSON files. Obtain a pin with `prepare_development_final_root.binding(path)`. For example, `binding(ROOT/'results/.../chain.json')` returns the physical D-backed path; use that returned `path`. Do not place the lexical `ROOT/results/...` symlink alias directly in a pin. `checked` intentionally refuses such lexical aliases. Final-root canonical planning file pins still resolve into the actual final source root.

## Readiness and protocol publication

Before publication, obtain actual same-source core12 PASS, independently completed safety4 PASS, extension16 PASS, real28 storage accounting and physical capacity budget, and actual R0 calibration from the two predetermined person/car velocity recordings. Preserve every original attempt. This connection adds a strict original28-PASS check because the normal extension gate intentionally permits disclosed algorithm failures. A normal gate heading `PASS` cannot upgrade original `FAIL` records or known algorithm failures.

Using the normal frozen tools in the actual final root:

1. Define untouched seed004 PROBE12 and EXTENSION_PROBE16 target snapshots in the new root, with canonical class order `person, car` and original six-group order. Do not execute those snapshots.
2. Build and validate core/extension gates against the one complete actual candidate42 source plan for each matrix. Preserve original terminal record and file SHA bindings. No original record may have status or engineering result other than PASS; no evaluator override can promote an old failure.
3. Run the actual `tools/reliability_v4_register.py safety-summary --target-plan TARGET_CORE --core-gate CORE_GATE --facts ACTUAL_SAFETY_FACTS --output-directory NEW_SAFETY_ASSEMBLY`. Keep its actual `started.json`, artifact and `outcome.json`.
4. Prepare an explicitly pinned JSON request below, then run the new publisher. It calls the normal gate, protocol, navigation and safety validators before staging any canonical bytes.

```json
{
  "schema_version": 1,
  "kind": "PARAMETERIZED_EXPLICIT_CANONICAL_PUBLICATION_REQUEST",
  "action": "protocols",
  "copy_build": {"path": "ACTUAL_BUILD_CHAIN", "sha256": "ACTUAL_SHA"},
  "expected_canonical_sha256": {"core": "ORIGINAL_DRAFT_SHA", "extension": "ORIGINAL_DRAFT_SHA"},
  "reviewed_tools_sha256": "REVIEWED_HELPER_CANONICAL_SHA",
  "target_plans": {"core": {"path": "ACTUAL_TARGET_CORE", "sha256": "ACTUAL_SHA"}, "extension": {"path": "ACTUAL_TARGET_EXTENSION", "sha256": "ACTUAL_SHA"}},
  "gates": {"core": {"path": "ACTUAL_CORE_GATE", "sha256": "ACTUAL_SHA"}, "extension": {"path": "ACTUAL_EXTENSION_GATE", "sha256": "ACTUAL_SHA"}},
  "safety_assembly": {"path": "ACTUAL_SAFETY_ASSEMBLY_OUTCOME", "sha256": "ACTUAL_SHA"}
}
```

```text
python -B publish_development_final_protocols.py protocols --request ACTUAL_REQUEST --request-sha256 ACTUAL_REQUEST_SHA
```

Only the original `status`/`registration_utc` fields and extension `development_readiness` field change. The original .60/.75 navigation safety gates and named512/4-thread resources remain unchanged. Publication retains original backups and explicit intents, uses the normal runner lock and atomic file replacement, and retains partial failure without rollback or retry. A successful outcome is `PUBLISHED_NOT_ADMITTED`.

## Replay publication and separate final seal

After successful core/extension publication:

1. Define the untouched FORMAL120 and EXTENSION_FORMAL160 plans with their actual source/model/runtime/file/digest bindings. Keep all 280 rows PENDING and no trial directories.
2. Run actual `tools/reliability_v4_register.py replay-config --core-plan FORMAL_CORE --candidate ACTUAL_DEVELOPMENT_CALIBRATION --output-directory NEW_REPLAY_ASSEMBLY`. This must use the real new calibration/export evidence; the helper does not manufacture parameters.
3. Create another exact-schema publication request: the common fields above with `action: replay` and `expected_canonical_sha256: {replay: ORIGINAL_REPLAY_DRAFT_SHA}`. Replace `target_plans`, `gates`, `safety_assembly` with `protocol_publication` (bound successful first publication outcome), `formal_plans` (bound core/extension formal plans), and `replay_assembly` (bound actual replay registrar assembly outcome).
4. Run `python -B publish_development_final_protocols.py replay --request ACTUAL_REQUEST --request-sha256 ACTUAL_REQUEST_SHA`. It rechecks the first publication's exact allowed canonical source delta, original build artifacts, normal registered replay/artifact validators and full development calibration guard. It publishes the replay candidate bytes only.
5. **Next required work, outside these three helpers:** verify all three actual published canonical pins; verify the final tree against the original whole-tree inventory plus only those three allowed deltas; produce and independently review a new immutable final source/planning manifest with updated whole-tree and planning hashes and unchanged classified/flight maps. Retain the original preparation manifest and immutable candidate42 freeze. Neither is the new final manifest.
6. Assemble the actual complete final admission request using the real physical capacity records, safety/calibration evidence and untouched formal plans. The actual admission-seal entry is `NEW_FINAL_ROOT/tools/reliability_v4_register.py seal --request ACTUAL_ADMISSION_REQUEST --output-directory NEW_ADMISSION_ASSEMBLY`. The unchanged registrar performs the complete guard validation; a JSON heading or publisher result cannot grant admission.
7. Independently verify the real emitted admission manifest and existing dynamic `formal41_guard_adapter01.py`/`formal280_serial_guard01.py` bindings before any seed1000-1009 formal attempt. The final manifest producer, request, seal, capacity admission and formal execution have not been implemented or executed by this source/build/publication preparation task.

The fixture suite checks path aliases/real symlinks on Humble, map separation, DRAFT and source integrity, bounded ownership and evidence closure, mandatory original28-PASS semantics, normal safety/replay validator connections, failure retention and no implicit action. Fixtures are not flight, readiness or admission evidence.
