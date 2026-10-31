# Humble42 post-core safety register/review/run checklist

Scope: read-only source/metadata audit plus this new external memo. No safety registration, safety flight, runtime preflight, module import, test, bag read, model inference, or formal action was executed. Core42 was reported active during this audit; this memo does not assert its current counts or outcome. Root owns scheduling after original core closure.

## 1. Exact reviewed inputs

- Candidate: `/mnt/d/WSL/UAVHumble22-validation/development_candidate_humble42_01.json`, SHA256 `2248074dcd477a50e73c8f5b5cc523390c01c08d14636742729d7474a7768ce2`.
- Final core contract: `/mnt/d/WSL/UAVHumble22-validation/development_contract_core_reliability_v4_humble42_probe01_01.json`, SHA256 `25e47f00b5aea543fd035b07d7c1a46aa5aecd8ff287d629ebd9dfad4e4c5e41`.
- Final core tools canonical: `4e5614388567b60ff5ab925390a37e254c8b8940f3092aa892579cf5cbd6359f`.
- Final safety tools canonical: `fa7e2461320a299a7ca8cb224722ac7c34358efed127d79cdf07d0efae4af275`.
- Safety Python SHA256 `64fed65c6a6a547b97c415f0e5b4a5c973b506c086c466f54f98d8d81877ff36`; shell `9731461cf64136847c5c3fee08a799230abe8b900527010a3d003c02c57e37ee`; tests `60f35657bc7f8380afde9844a75b5aee1606cf9065f6e17041d00f628e470064`.
- Independent final-core safety sync addendum: `development_safety_final_core_sync_independent_addendum01.json`, SHA256 `a8523983f50589af2b48e7f42edb7d41045ad1fbe07c6df7757b2326efb8aafb`.
- Explicit candidate root `/root/uav_tracking_fullplan_v4_humble42`, prefix `reliability_v4_humble42_probe01`.
- Original card/tail remain unchanged: card SHA256 `4cfad726ba7349efdbc0bc20129e95aa8f2414e65adf7e31539ad887bbe46e2c`, tail SHA256 `05d1d11b6357db83a9805fc96f013e01c1c7741d109d6c10501e497215c2b612`.

`development_safety_usage01.md` retains historical pending-review wording and an obsolete `757c...` core pin. Do not modify this history or use that old pin. The final independent sync addendum, actual final source and final contract above establish the current identity.

## 2. Admission before registration

The authoritative original run-core terminal is:
`/root/uav_tracking_fullplan_v4_humble42/results/reliability_v4_humble42_probe01_seed004_matrix/observed_driver01/execution_terminal.json`.
It is NOT the plan-creation terminal in `results/freeze_validation/...core_plan_driver01/`.

Actual gate (`development_safety.py:95`, `development_runner.py:539`):

1. Current final candidate, contract, source/build/runtime/tool bindings match. `load_contract` rechecks the actual immutable original plan and clean original plan-owner terminal. Logical root/results paths may resolve to the physical D-drive evidence tree; preserve both recorded identities.
2. Original run-core terminal: schema1, action `run-core`, returncode native integer0, status `ORIGINAL_CORE_TERMINALS_COMPLETE`, errors and slot_read_error null; planned/attempt/terminal counts are native integer12; exact contract pin and plan identity; entry before=after=current; final_errors empty; cleanup exactly `{"residual_processes":[]}`; no zero-attempt recovery or formal/retry flags.
3. All12 original slot rows in the exact plan order have both status and engineering_result PASS. Actual report audits, slot summaries and attempt audits agree. Re-read all12 original `.started.json` and `.attempt_terminal.json`, exact attempt numbers1..12, one original attempt each, contract/source/plan/time bindings; no replacement summaries.
4. Actual original post-wait observer owner is healthy and identical to terminal observer. Actual aggregate row statuses/digests equal the terminal counts. Verify source bytes, and no runtime residual.
5. All safety audit/trial paths are absent and not symlinks; runtime is idle. Registration performs full normal evidence verification, which can hash original artifacts; schedule after core has finished, not concurrently.

Any original FAIL, missing evidence, source/owner/cleanup change, incomplete denominator, or infrastructure fault refuses safety. Never rewrite/retry/promote the original core to satisfy this gate.

## 3. Future register command (not executed by this audit)

Run only after the actual gate above holds. The shell isolates UAVHumble22, Humble, the reviewed bridge/PX4-msg/project overlays and runtime/source/build/resource contracts.

```powershell
wsl.exe -d UAVHumble22 -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/development_safety.sh register --manifest /mnt/d/WSL/UAVHumble22-validation/development_candidate_humble42_01.json --manifest-sha256 2248074dcd477a50e73c8f5b5cc523390c01c08d14636742729d7474a7768ce2 --core-contract /mnt/d/WSL/UAVHumble22-validation/development_contract_core_reliability_v4_humble42_probe01_01.json --core-contract-sha256 25e47f00b5aea543fd035b07d7c1a46aa5aecd8ff287d629ebd9dfad4e4c5e41 --reviewed-tools-sha256 fa7e2461320a299a7ca8cb224722ac7c34358efed127d79cdf07d0efae4af275
```

`register` creates a prospective registry only; flight_actions_executed must be0. Expected actual registry:
`/root/uav_tracking_fullplan_v4_humble42/results/reliability_v4_humble42_probe01_safety_seed004_audit/registry.json`.
Its real SHA cannot be known before registration and must not be invented.

## 4. Independently review the actual new registry before run

Use actual freshly created bytes and preserve their SHA256 in a separate new review receipt. Independently verify (`development_safety.py:199,262,296,310`):

- schema_version1; kind `RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY`; scope `PARAMETERIZED_SAFETY4_ORIGINAL_DEVELOPMENT_ATTEMPTS_NOT_FORMAL_GATE`; actual created_utc.
- Exact source_core_plan file path/SHA and internal plan_sha256; actual core_completed_prerequisite contains healthy original run-core terminal, all12 original terminal/record/start/owner bindings and all_original_core_cells_pass true.
- source_binding, freeze_source_sha256, flight_source_hashes, entry_binding and driver path/SHA equal the actual current final candidate; safety_tools_sha256 equals final fa7e...; original card/tail path/SHA equal reviewed bytes. entry_binding also contains final safety canonical.
- formal_seeds_consumed false; automatic_retry false; policy has no automatic extension/formal permission.
- Four trials only, this order: person_auto_unique_multi_seed004; person_locked_ambiguity_seed004; car_auto_unique_multi_seed004; car_locked_ambiguity_seed004. Exact fresh trial directories use candidate prefix + `_safety_` + ID. All seed4, stage2, clean, adaptive_kf, velocity, midpoint, ground_footprint, standard motion, class-derived reviewed resources.
- Auto scenes: target_mode auto_unique, association legacy, parallel scenario, initial_select none, minimum2 candidates, duration35 and no_follow_duration35.
- Locked scenes: locked_target, hybrid_3d, ambiguity scenario, initial_select middle, minimum3 candidates, duration50.
- Actual prospective flight argv preserves the class resource model/size/threads/distance, native3m takeoff, source_sim timestamping, rendering/magnetic/bridge registration, current geometry/recovery/exclusive/pacing/rate policies. It does not substitute old root41 paths.
- Every trial has exact five `execution_commands` and correct canonical argv SHA: flight, source_clock, native_startup, specialized, terminal_speed. Check the actual complete argv, not only the hashes. Auto specialized is frozen `run_stage23_matrix.py --evaluate-auto-unique`; locked specialized is frozen `evaluate_stage2_flight.py` with no-require-occlusions, require-ambiguity and terminal-expectation hover. Tail is original external tail script plus original card.

The tool regenerates these definitions/core bindings and requires exact equality again on run. A registry hash alone is not an independent review.

## 5. Future run command (requires actual reviewed registry SHA)

Same exact candidate/contract/tools arguments; replace the one placeholder only after independent actual registry review. The following is documentation, not an executable value:

```powershell
wsl.exe -d UAVHumble22 -- /bin/bash /mnt/d/WSL/UAVHumble22-validation/development_safety.sh run --manifest /mnt/d/WSL/UAVHumble22-validation/development_candidate_humble42_01.json --manifest-sha256 2248074dcd477a50e73c8f5b5cc523390c01c08d14636742729d7474a7768ce2 --core-contract /mnt/d/WSL/UAVHumble22-validation/development_contract_core_reliability_v4_humble42_probe01_01.json --core-contract-sha256 25e47f00b5aea543fd035b07d7c1a46aa5aecd8ff287d629ebd9dfad4e4c5e41 --reviewed-tools-sha256 fa7e2461320a299a7ca8cb224722ac7c34358efed127d79cdf07d0efae4af275 --registry-sha256 ACTUAL_INDEPENDENTLY_REVIEWED_REGISTRY_SHA256
```

Run rejects any preexisting attempt terminal/start, execution_terminal, slots_facts, observer driver or trial directory and rechecks idle runtime. It owns one machine run lock and directly flies each scene once; it does not nest normal run_plan or acquire a second SITL lock.

## 6. Execution and completion audit

Each original scene: flight outer timeout3200s, then source_clock/native_startup/specialized/terminal_speed each outer timeout1800s. The observer retains actual native ownership and original archive post-wait outcome (archive wall budget1800s). Source/core/registry bytes and no residuals are checked around each scene (`:354`).

Flight/source/native failure, missing/malformed/foreign evidence, runtime/source/build/observer/cleanup fault stops the sequence and preserves attempted plus pending denominator4. Only a complete specialized or tail algorithm FAIL may remain and continue. No automatic retries or rewrites.

Per scene require exactly five execution receipts and twelve bound evidence objects: run_config, configuration/source_sha256, configuration/runtime_parameters, bag_integrity, recording_closure, process_exit_codes, px4_source_clock_report, native_startup_report, terminal_hover_speed_evaluation, configuration/gazebo_rendering_libraries, configuration/magnetic_environment and the correct specialized auto_unique_evaluation_v2 or stage2_evaluation report.

Saved run_config/YAML/source snapshot must reproduce prospective resources and policies, occlusions=false, reselect_after_loss=false, no_bag=false and vehicle FLU point offset[0,0,.24]. Runtime audit also checks supported-birth class policy, geometry/recovery/exclusive/pacing, source_sim freshness, native handoff, actual llvmpipe rendering, magnetic, bridge and processes (`:235`).

Tail must preserve the original full5.2s interval ending at the original final recorded Clock. Both observed odometry speed and offline-GT body-point speed must be <=0.30m/s. Complete exact boolean check sets, recorded clock and no decode/unavailable-type errors are required. No shifted/truncated window or relaxed threshold. GT remains offline only (`:277`).

Interpretation (`:354,437,475`):

- execution_terminal returncode0 / SAFETY4_ORIGINAL_ATTEMPTS_COMPLETE means all4 original attempts closed without infrastructure stop; it does NOT by itself mean algorithm allPASS.
- slots_facts.result PASS requires all4 original PASS and healthy completion. Only then are development_validation_summary and original development_guard_validation produced.
- Require development_guard_validation result PASS, error null, exact actual evidence bindings, healthy original post-wait owner and empty residuals. `require_completed_safety` rereads all actual records and reruns the actual final-root `tools/reliability_v4_guard.py` full validate_safety each call, preserving/checking the original guard outcome.
- This remains development evidence. Extension needs this exact Context + actual registry pin and its own separate reviewed admission/plan/contract. Formal registration and formal seed consumption remain separate later actions; safety does not start them automatically.
