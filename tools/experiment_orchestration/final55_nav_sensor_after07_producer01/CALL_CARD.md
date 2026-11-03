# after07 navigation28 / sensor4 source review and calling card

This is a future calling card, not registration or an execution receipt. Only Windows small source/JSON was inspected. No WSL/native command, bag/model read, evaluator or gate has been run here. The old 08 owner chain exited 2 and must not be called.

## Actual prerequisite paths

- Staging: `/root/uav_tracking_final55_stage_after07_01`; staging receipt: `/mnt/d/WSL/UAVHumble22-validation/final55_stage_after07_01`.
- Final cold root: `/root/uav_tracking_fullplan_v4_final55`.
- Measurement: `full28_storage_measurement_probe02_after07_01`.
- Calibration/R0: `reliability_v4_humble54_development_calibration_probe02_after07_01/R0_candidate.json`.
- Budget: `full280_storage_budget_probe02_after07_01/budget.json`.

The last three are the actual future measurement outputs under frozen54's results, not the old `_08` paths. They must really exist, have their full terminal/bindings, and pass the unchanged positive full280 budget before staging/cold. No path or future SHA is registered by this card. Windows UNC `is_dir`/`readlink` is not evidence of a Linux source/result path being absent; Linux canonical resolution must be checked at actual idle execution.

## Existing direct tools

| Function | Existing source / current reviewed SHA256 |
|---|---|
| Prospective registration and completion validator | `scripts/build_reliability_v4_probe_gate.py` / `fa7d150a0e68b4678d0727139e206e20a629971d7bfeae0882d0f804381185ae` |
| Runner/command schema, including conditional identity | `scripts/run_reliability_v4.py` / `32c4cd091a6aa09a56135b4f7d69dd4f70e8e693f1d76878aa61f5a72f45182d` |
| Actual navigation evaluator | `scripts/evaluate_navigation_reference.py` / `b49984d495ec7b12e623e961f3d606958aaef682ddfbc636f9c21ed2d52abcb4` |
| Generic person/car dropout/combined extractor CLI | `tools/diagnostics/humble54_dropout_gap01/extract_short_window.py` / `364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4` |
| Pure four-cell sensor API | `tools/offline_evaluation/sensor_input_interruption_v1/evidence.py` / `aca8932895eb44361265347164f5cd62fe427ccb61907c5844309162b33a7ffc` |

These pins describe the prepared version. Actual execution must load the future final55 target's own source/descriptor bindings and verify them. Do not use old document tables containing the pre-opt-in runner/module SHA. The prepared after07 contract file SHA is `ca7eacc64aace573f14790b23ca6b4b4b6a26000c67147fef9fb3f38eb0251e7`; its canonical JSON digest is `cdba3fc3e6470effa329407742cc10f4c72d139a0d8f37e93b069ed22096dfed`. The actual future target descriptor is authoritative.

After successful after07 staging, the existing cold CLI remains:

```sh
/bin/bash /root/uav_tracking_final55_stage_after07_01/tools/diagnostics/reliability54_build01/prepare_and_validate.sh \
  /root/uav_tracking_fullplan_v4_final55 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_final55 \
  /root/uav_tracking_fullplan_v4_humble54
```

From the actual cold final root, define the two seed-4 target plans using the original registration card's `run_reliability_v4.py plan --probe --seeds 4` and its `--extensions` counterpart. Keep every target slot PENDING forever. They are definitions, not another development flight batch.

## navigation28: existing registration, actual evaluator, exact completion schema

Use actual canonical variables for the final root, cold core target, original core12 probe01 plan and original extension16 **probe02** plan. Registration is already a CLI:

```sh
bash "$tracking_final/scripts/run_research_session.sh" \
  "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_core_target" \
  --probe-plan "$tracking_core_dev" --probe-plan "$tracking_extension_dev" \
  --register-navigation-reevaluations \
  --navigation-report-basename "$tracking_new_basename" \
  --output "$tracking_actual_prospective_registration"
```

The uniform plain `.json` basename and its `.frames.jsonl`, `.raw_frames.jsonl`, `.message_frames.jsonl` siblings must be absent in all 28 original trial directories before registration and again immediately before each invocation. The evaluator itself uses write mode, so this second refusal is necessary. Append the specifically registered new outputs; preserve all original reports/sidecars/terminals.

Run each `registration.planned_evaluations[].command` exactly as recorded, serially. Its existing CLI is the final root's `run_research_session.sh evaluate_navigation_reference.py ORIGINAL_TRIAL --target-class person|car [--physical-identity-report ORIGINAL_IDENTITY_REPORT] --output NEW_REPORT`. Multi-target commands retain the original independent physical-identity artifact. Each original plan currently has `evaluation_timeout_s=1800.0`; use the exact bound plan value without extending it. An evaluator exit 0 means `RECORDED_WITH_CENSORED_FAILURES` and complete numeric evidence; it does not mean navigation performance PASS. Exit 2 is incomplete evidence and stops the producer.

The completion manifest read by `read_navigation_reevaluation_manifest()` is exactly this shape; all placeholder values below must be actual later artifacts, never prefilled future results:

```json
{
  "schema_version": 1,
  "kind": "RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATIONS",
  "prospective_registration": {"path": "ACTUAL_CANONICAL_REGISTRATION", "sha256": "ACTUAL_FILE_SHA"},
  "source_plans": ["COPY_THE_TWO_ACTUAL_REGISTRATION_SOURCE_OBJECTS"],
  "evaluation_source_hashes": {"COPY": "THE_ACTUAL_REGISTRATION_OFFLINE_SOURCE_MAP"},
  "registered_utc": "COPY_ACTUAL_REGISTRATION_CREATED_UTC",
  "created_utc": "ACTUAL_COMPLETION_UTC",
  "slots": [
    {
      "plan_path": "ACTUAL_ORIGINAL_PLAN_PATH",
      "slot_id": "ACTUAL_PREDETERMINED_SLOT",
      "record_file_sha256": "ACTUAL_ORIGINAL_TERMINAL_FILE_SHA",
      "evaluation_overrides": [
        {
          "kind": "navigation",
          "original_report_sha256": "COPY_ACTUAL_FIXED_ORIGINAL_SHA",
          "report": "ACTUAL_FIXED_NEW_REPORT_PATH",
          "report_sha256": "ACTUAL_NEW_REPORT_SHA",
          "evaluation_root": "ACTUAL_COLD_FINAL_ROOT",
          "execution": {
            "command": ["EXACT_ACTUAL_REGISTRATION_ARGV"],
            "started_utc": "ACTUAL_CHILD_START_UTC",
            "finished_utc": "ACTUAL_CHILD_EXIT_UTC",
            "returncode": 0,
            "error": null,
            "log": "ACTUAL_CANONICAL_CLOSED_LOG",
            "log_sha256": "ACTUAL_LOG_SHA"
          }
        }
      ]
    }
  ]
}
```

Retain all 28 unique `(plan_path, slot_id)` keys, exactly one override per slot. Source objects contain `mode/path/sha256/plan_sha256` and are copied verbatim from registration. Both core and extension gate validators independently recheck all 28 executions, original terminal/report/physical-artifact SHA, the actual final evaluator/helper provenance and the complete numeric grids. Chronology is original finish ≤ registration ≤ invocation start ≤ exit ≤ completion ≤ now. No boolean PASS list substitutes for these artifacts.

## sensor4: existing extractor and exact API inputs

The generic extractor already supports both classes and both conditions; no new extractor is necessary. The old named person-only executor hardcodes probe01/old module pins and is unusable for this batch. For each genuinely missing contract-window extraction, the direct existing CLI is:

```sh
bash "$tracking_dev/scripts/run_research_session.sh" \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble54_dropout_gap01/extract_short_window.py \
  --source-root /root/uav_tracking_fullplan_v4_humble54 \
  --plan "$tracking_extension_dev" --slot-id "$tracking_actual_fixed_slot" \
  --output "$tracking_fresh_external_extraction_directory"
```

All four fixed IDs are `person_extension_dropout_seed004`, `person_extension_combined_seed004`, `car_extension_dropout_seed004`, `car_extension_combined_seed004`. Actual extraction scans the original six topics and retains all acquisition opportunities in the original short window ±0.3 s, at most 32 raw RGB opportunities. Do not substitute the separate first-LOST post-hoc diagnostic window.

AI or a person must actually inspect images and record a new independent review where needed. Human-only intervention is not required. Review schema: `kind=INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE`, `review_type=DIRECT_IMAGE_REVIEW_AI|DIRECT_IMAGE_REVIEW_HUMAN`, actual UTC `created_utc`, nonempty string array `reviewers`, exact actual extraction manifest `path/sha256`, and ordered `images` retaining every original `file/sha256/acquisition_ns` plus the actual `observation`. Allowed observations are `TARGET_AND_SCENE_VISIBLE`, `ONE_PERSON_AND_SCENE_VISIBLE_IN_CONTACT_SHEET`, `ONE_CAR_AND_SCENE_VISIBLE_IN_CONTACT_SHEET`, `SCENE_OBSCURED_NEAR_BLACK_TARGET_NOT_VISIBLE`. Corroborated-null cells need visible before/after and an actually reviewed obscured acquisition after close ACK and before open request. Do not manufacture a visual observation from a brightness threshold.

The complete sensor input manifest is small:

```json
{
  "schema_version": 1,
  "contract_sha256": "ACTUAL_CANONICAL_JSON_CONTRACT_DIGEST",
  "source_plan": {"path": "COPY_ACTUAL_CONTRACT_SOURCE", "sha256": "COPY_ACTUAL_CONTRACT_SOURCE_SHA"},
  "slots": [
    {
      "slot_id": "ACTUAL_FIXED_SLOT",
      "extraction_manifest": {"path": "ACTUAL_EXISTING_EXTRACTION_MANIFEST", "sha256": "ACTUAL_SHA"},
      "visual_review": {"path": "ACTUAL_EXISTING_DIRECT_REVIEW", "sha256": "ACTUAL_SHA"}
    }
  ]
}
```

Exactly four unique fixed entries are required. The API is `evaluate_development_manifest(manifest_path, contract)`; it has no CLI. It returns `UPSTREAM_INPUT_INTERRUPTION_CORROBORATED`, `NOT_APPLICABLE` or `INCOMPLETE`, with original FAIL/nulls retained. `NOT_APPLICABLE` is the original API's branch for an already observed boolean detector check with diagnostics. It still needs bound extraction/review files in the four-slot input manifest; that branch does not independently validate their image contents, and this distinction must stay explicit. Only the corroborated-null branch performs the image/window/drop-ledger checks. Never hand-write PASS for an observed cell.

The original short fields currently show person dropout detector null/0 diagnostics; person combined true/1; car dropout true/2 plus identity null and demonstrated loss; car combined true/3. These small JSON observations do not certify full module validity, owner closure or readiness. The car identity null needs the exact conditional opt-in and stays FAIL/UNOBSERVED, never an identity success or exclusion of switching.

There is an existing probe02 person-dropout extraction/review candidate under `results/diagnostics/humble54_probe02_person_dropout_input_extract03`: manifest SHA `1355c559f2015acfc3ed77a56529b9e92ffbfdd0a34e5e9262bafc2a2de1ce71`, review SHA `875c42fda26e6f76d033bff39edcfb0f6e943fb836114c278e9829cd507c0ad9`. Actual native API revalidation must still check all original files, images and canonical paths. Existing car-dropout extraction is another input candidate, not a completed review. Existing person-combined `raw_window01` uses a first-LOST 33.8–35.2 s post-hoc selection and is not the contract-window extraction.

## Minimal missing code and final gate calls

No existing code in the inspected scripts/diagnostic/orchestration/offline-evaluation scope runs the registered 28 commands and emits the completion manifest. Add one direct serial producer that keeps exact argv/actual UTC/integer exits/log SHA, rejects all report/log conflicts, preserves failures, and finishes by calling the original `read_navigation_reevaluation_manifest()`. No owner or trigger is needed. A second subcommand may consume the real four-slot sensor manifest and the **actual target descriptor's** module/contract, call `evaluate_development_manifest()`, save its real result, and independently run the runner's manifest binding validator. It must never create image observations.

Once both actual inputs are valid, the existing builder CLI remains sufficient for gates:

```sh
bash "$tracking_final/scripts/run_research_session.sh" "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_core_target" --probe-plan "$tracking_core_dev" \
  --navigation-reevaluation-manifest "$tracking_actual_nav_complete" --output "$tracking_core_gate"
bash "$tracking_final/scripts/run_research_session.sh" "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_extension_target" --probe-plan "$tracking_extension_dev" \
  --navigation-reevaluation-manifest "$tracking_actual_nav_complete" \
  --sensor-input-evidence-manifest "$tracking_actual_sensor4" \
  --registration-utc "$tracking_actual_extension_cutoff" --output "$tracking_extension_gate"
```

Cutoff is an actual current/past UTC after all original extension finishes. Sensor evidence is extension-only; do not mix the old six-gimbal override. Core failure, incomplete evidence, long-loss safety failure, identity/physical missing structure, stale source/pins, nonpositive budget or any path conflict stops the corresponding boundary. No gate, publication or formal admission is implied by this card.
