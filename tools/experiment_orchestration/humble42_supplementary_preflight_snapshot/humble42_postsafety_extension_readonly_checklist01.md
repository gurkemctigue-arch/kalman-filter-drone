# Humble42 post-safety extension16 execution checklist

Read-only audit plus this exclusively created external memo. No actual admission JSON was constructed; no prerequisite function, module, runtime preflight, test, bag, inference, source-tree hash or simulation was run. Current core execution remains untouched. All commands below are future instructions for root after the original prerequisites close healthily.

## 1. Final reviewed tool identities and source documents

There is no `development_extension_usage01.md` or dedicated extension handoff in the external tools tree. Actual relevant documents located by rg are `development_extension_independent_review01.json`, `development_safety_final_core_sync_addendum01.json`, `development_safety_final_core_sync_independent_addendum01.json`; later final-root linkage is `development_final_root_handoff01.md`.

- Final extension canonical: `c232d556d11b7c141b6d9aa443ee0822792e72663dd5646dd6096636afeeb936`.
- Final core canonical: `4e5614388567b60ff5ab925390a37e254c8b8940f3092aa892579cf5cbd6359f`.
- Final safety canonical: `fa7e2461320a299a7ca8cb224722ac7c34358efed127d79cdf07d0efae4af275`.
- Extension Python SHA256 `731e1b5a525165ca518dc7f8c5b67a9c86ab42a69fe7092ba4adc6e74873bd96`; shell `0ec9624b9ff8de64f626f20225c1ccdeac6bfb11bf7d0c4f90a66e5807c8f5dc`; tests `690d79a93770362f1dd8c531d6329ad65e6a77d3fc902a6589a073a1d6f7fa74`. Direct small-file hashes still match.
- Final safety dependency file pins: Python `64fed65c6a6a547b97c415f0e5b4a5c973b506c086c466f54f98d8d81877ff36`, shell `9731461cf64136847c5c3fee08a799230abe8b900527010a3d003c02c57e37ee`, tests `60f35657bc7f8380afde9844a75b5aee1606cf9065f6e17041d00f628e470064`.
- Original independent extension review SHA256 `7d5257e334d80dd64538ee04275b3b81c7038a4a91e718be05d524fcf44511ee`; final sync independent addendum SHA256 `a8523983f50589af2b48e7f42edb7d41045ad1fbe07c6df7757b2326efb8aafb`.

The original review records the historical canonical `0a158...` with old core757c/safety17419 pins. The final sync addendum independently confirms extension source bytes unchanged and the dynamic core/safety bindings updated. Use final c232/core4e561/safetyfa7e identities above; do not rewrite the historical receipt or reuse its old canonical.

## 2. Admission after actual safety completion

`development_extension.py:110` accepts only a separately independently reviewed external ordinary JSON named `development_extension_admission_[A-Za-z0-9_]+.json`, supplied with its exact actual SHA256. No default admission exists. Actual prerequisite evaluation (`:171`) calls same-candidate `safety.actual_core` and `safety.require_completed_safety`: original core12 allPASS with healthy owner plus original safety4 allPASS and the original successful full frozen guard. A healthy run exit alone is insufficient. Preserve every original record and all source/build/runtime bindings.

Code-required admission fields (this is a field checklist, NOT an emitted admission):

- `schema_version`: native integer1.
- `scope`: `PARAMETERIZED_EXTENSION16_NORMAL_RUNNER_DEVELOPMENT_ONLY`.
- `status`: `FINAL_PARAMETERIZED_EXTENSION16_INDEPENDENTLY_REVIEWED`.
- `authorized_actions`: exactly `["plan","run"]`.
- `candidate_manifest`: exact `{path,sha256}` for `/mnt/d/WSL/UAVHumble22-validation/development_candidate_humble42_01.json`, SHA `2248074dcd477a50e73c8f5b5cc523390c01c08d14636742729d7474a7768ce2`.
- `core_contract`: exact `{path,sha256}` for `/mnt/d/WSL/UAVHumble22-validation/development_contract_core_reliability_v4_humble42_probe01_01.json`, SHA `25e47f00b5aea543fd035b07d7c1a46aa5aecd8ff287d629ebd9dfad4e4c5e41`.
- `safety_registry`: exact `{path,sha256}` for `/root/uav_tracking_fullplan_v4_humble42/results/reliability_v4_humble42_probe01_safety_seed004_audit/registry.json`, using the actual independently reviewed registry SHA produced after core. That SHA is unknown to this memo and must never be invented. This development helper explicitly requires this logical candidate-root path; do not transplant the later final-root helper's resolved-physical pin policy here.
- `extension_protocol`: exact `{path,sha256}` for `/root/uav_tracking_fullplan_v4_humble42/planning/reliability-v4-extension-preregistration.json`, SHA `ce0bbc1c59f65aa5d6619222cfc9489f6e22b9f9685f1041fed20e3e40c3ea89` from the actual reviewed candidate source map. The small actual file was read: 75s, exact8 conditions, formal seeds1000-1009 (development seed4 absent), far person7m/car12m, named velocity references except speed_changes_position. DRAFT status remains intact for development; this does not publish formal protocols.
- `dependency_tools`: exactly keys `core` and `safety` with final4e561/fa7e canonical values above.
- `tools_canonical_sha256`: final c232 canonical above.
- `prefix`: explicitly selected fresh string matching `reliability_v4_[A-Za-z0-9][A-Za-z0-9_-]{0,70}`, different from candidate prefix and old `reliability_v4_humble41_extensions_probe`. Root must select/independently review one real prefix; this memo does not reserve one.
- `experiment`: exactly classes `["person","car"]` in actual candidate order, conditions `["depth_noise","depth_holes","dropout","latency","combined","speed_changes_velocity","speed_changes_position","far_distance"]`, native integer seed4, duration_s75.0, native integer flight_count16.
- Five flags all literal false: `formal_seed_use_authorized`, `readiness_claimed`, `automatic_retry`, `automatic_next_action`, `resume_or_recovery_authorized`.
- `zero_attempt_recovery` must be absent, even if false.

Before actual planning, independently review this actual admission's bytes, exact dependency canonical/source protocol pins, real core/safety prerequisite identity and chosen fresh output names, then preserve its real SHA in a new separate review receipt. Do not manufacture a substitute core/safety summary or an actual admission before safety evidence exists.

## 3. Plan only; inspect the actual new PENDING contract

After admission review, in a new idle exclusive window:

```powershell
wsl.exe -d UAVHumble22 -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/development_extension.sh plan --admission ACTUAL_REVIEWED_EXTERNAL_ADMISSION_JSON --admission-sha256 ACTUAL_REVIEWED_ADMISSION_SHA256
```

No separate --manifest/--reviewed-tools option exists here; candidate/tools/core/safety pins are explicit admission fields. Shell isolates UAVHumble22/Humble, shutdown_A01 bridge, matching PX4 msgs, project overlay, venv and single-thread numerical libs. Each actual action performs the reviewed source/build/runtime/resource preflight and caches the real resource binding before creating Context.

Derived from actual admitted FRESH_PREFIX (`:94,263`):

- Plan: `/root/uav_tracking_fullplan_v4_humble42/results/FRESH_PREFIX_seed004_matrix/plan.json`.
- Original planning terminal: `/root/uav_tracking_fullplan_v4_humble42/results/freeze_validation/FRESH_PREFIX_extension_plan_driver01/execution_terminal.json`.
- PENDING contract: `/mnt/d/WSL/UAVHumble22-validation/development_extension_contract_FRESH_PREFIX_pending01.json`.
- Later run driver: plan output + `/observed_driver01`.

All output/plan_driver/pending_contract paths must be absent and not symlinks, runtime idle. Planning uses only actual frozen `make_extension_plan(formal=False,seeds=[4],all8conditions,bothclasses)` and `persist_plan`, retains untouched16 PENDING rows with no trial products, preserves healthy original plan owner/cleanup, and reports flights_started0. It rechecks actual core+safety before and after planning.

Independently audit actual persisted plan (`:195`): mode EXTENSION_PROBE; exact candidate root/source/model/config/magnetic/runtime/core protocol; admitted fresh prefix; both classes in order; seeds[4]; groups stage1_velocity/stage1_position; exact16 ordered IDs `CLASS_extension_CONDITION_seed004`; full75s; class model/image-size/thread policy, class geometry/recovery/exclusive/pacing policies; each condition's registered reference group and far distance; original core trial budget plus evaluation/postprocessing1800s; exact extension_protocol_binding including actual protocol contents. Frozen validator checks original flight/evaluator argv; do not edit commands.

## 4. Independently create a new FINAL contract from real planning evidence

PENDING is never executable. Keep the original PENDING contract and actual plan terminal unchanged. Independently review actual new outputs and publish a separate external final contract named `development_extension_contract_[A-Za-z0-9_-]+.json`, with separately preserved actual SHA. Do not prefill unknown plan/terminal/prerequisite hashes.

Required final-contract fields checked by `:302`:

- schema_version1, exact extension SCOPE, status `FINAL_PARAMETERIZED_EXTENSION16_NORMAL_RUNNER_INDEPENDENTLY_REVIEWED`.
- Exact `extension_admission` pin, actual full `entry_binding`, complete `experiment`, all five false flags and no zero_attempt_recovery.
- `prerequisites` exactly the actual reread result: keys core, safety, core_contract, safety_registry, dependency_tools. Core/safety must retain real original evidence and owner/full-guard bindings.
- `plan_pending`: exact immutable actual plan file path/SHA, internal plan_sha256, ordered16 slot_ids, initial_status_counts `{"PENDING":16}`. This is prospective identity, not a claim about later execution state.
- `plan_terminal`: exact original plan-driver execution_terminal metadata pin.
- Preserve original created_utc/evidence provenance when deriving the new contract; add independent-review provenance in a new receipt. Do not modify the original plan/terminal/PENDING receipt.

Original plan terminal itself must be action plan, returncode native integer0, error null, initial_pending and prerequisites identical, native flights_started0, entry before=after=final contract binding, final_errors empty, no residuals/allfalse flags, and actual original post-wait owner validation identical to saved observer. Run repeats all these checks against real files rather than trusting a FINAL heading.

## 5. Run once from the actual final contract

```powershell
wsl.exe -d UAVHumble22 -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/development_extension.sh run --admission SAME_ACTUAL_REVIEWED_EXTERNAL_ADMISSION_JSON --admission-sha256 SAME_ACTUAL_REVIEWED_ADMISSION_SHA256 --contract ACTUAL_INDEPENDENTLY_REVIEWED_FINAL_EXTENSION_CONTRACT_JSON --contract-sha256 ACTUAL_REVIEWED_FINAL_EXTENSION_CONTRACT_SHA256
```

Run requires all16 rows untouched PENDING, no existing run driver or trial paths and idle runtime (`:341`). Before every slot it checks entry/contract/source/plan, revalidates the real original core+safety/fullguard, checks prior immutable original extension terminals, and consumes exactly one original slot through `core.observed_run_plan` (normal runner max_new_trials1). The normal frozen runner alone owns the SITL lock; no outer/nested run_lock or altered argv.

Every original slot saves numbered started marker and attempt terminal with actual contract/entry/plan/time bindings and original_attempt_number1. `audit_record(extension=True)` rereads actual evaluator reports/runtime/bridge/process/archive evidence, independently requires source-clock/native-startup PASS and original flight exit0, recomputes engineering verdict and preserves known_algorithm_failures. Complete algorithm FAIL remains disclosed and may continue; infrastructure/source/owner/cleanup/evidence faults stop and retain original attempted/pending rows, without retry/resume/overwrite.

## 6. Completion interpretation and later publication boundary

Expected original run terminal: plan output + `/observed_driver01/execution_terminal.json`; scope extension, action run. Healthy complete closure is returncode0/status ORIGINAL_EXTENSION16_TERMINALS_COMPLETE, native planned/attempt/terminal counts16, all ordered original attempts/slots, actual row statuses/digests/counts, no slot-read/error/final cleanup/owner fault, original unchanged source/admission/contract/prerequisite bindings.

Returncode0 means original16 terminal evidence closed healthily; it does NOT itself mean all16 algorithms PASS. Independently inspect each actual status/engineering_result and audit known_algorithm_failures. Later final-root publication explicitly requires original core12+extension16 allPASS plus independent safety4/fullguard PASS, actual28 storage/capacity accounting and real calibration. A normal gate heading cannot promote algorithm FAIL. Extension completion grants no formal seed, automatic publication, readiness or whole-project acceptance.
