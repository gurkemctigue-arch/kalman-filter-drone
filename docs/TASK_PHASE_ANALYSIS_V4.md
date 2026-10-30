# v4 task phase appendix

Implementation plan:

1. Read existing JSON and stream complete JSONL files, bind their actual SHA256 bytes and the analyzer source in a new output manifest. Never read bags or import flight/evaluator code.
2. Preserve the original navigation grid, calibration cutoff and identity cells. Add pre-FOLLOW, `[0,45)`, `[45,75]` and remaining recording-tail views. Assign a cell by its original left endpoint, flag boundary crossings, and verify every denominator and identity outcome is conserved.
3. Build an event partition only from recorded, ordered events. Missing or inconsistent events produce `UNRESOLVED_EVENTS`; never infer a successful confirmation. Keep overlapping flags separate from mutually exclusive phases, and mark unavailable evidence explicitly.
4. Write JSON, CSV and a readable HTML appendix into a new directory only. Validate conservation, boundaries, unknown/wrong evidence, missing inputs, unique-instance identity N/A and non-finite rejection with small fixtures.

This appendix does not change primary outcomes, introduce engineering gates, or establish algorithm improvement. Its output status describes the completeness of the appendix, not an engineering or flight PASS.

## Inputs and invocation

The standalone script uses only the Python standard library. Supply explicit paths so original Linux report paths can be reviewed from Windows without rewriting the original reports:

```bash
python -B scripts/analyze_task_phases_v4.py \
  --mode specified \
  --navigation-report /evidence/trial/navigation_reference_evaluation.json \
  --navigation-frames /evidence/trial/navigation_reference_evaluation.frames.jsonl \
  --identity-report /evidence/trial/physical_identity.json \
  --identity-frames /evidence/trial/physical_identity.frames.jsonl \
  --raw-frames /evidence/trial/navigation_reference_evaluation.raw_frames.jsonl \
  --summary /evidence/trial/summary.json \
  --telemetry /evidence/trial/telemetry.jsonl \
  --occlusions expected \
  --output-dir /new-output/task-phase-appendix
```

Use `--mode auto_unique` for the four unique-instance core groups and their extensions. Omit identity inputs in that mode: full-task identity is **N/A**, never zero UNKNOWN or 100% identity coverage. `specified` requires the original `conservative_task_time_identity` audit and the navigation report's `physical_identity_sha256` must match the supplied identity report bytes. `--occlusions none` describes an explicitly declared trial without shutter stimuli. The default `unknown` leaves event phases `UNRESOLVED_EVENTS`.

The navigation report and main frame sidecar, monitor summary and telemetry are required for a complete appendix. Raw and identity frame sidecars add optional overlapping flags. An explicitly supplied but missing/invalid input makes the appendix `INCOMPLETE_EVIDENCE`. An absent optional sidecar is `UNAVAILABLE`. Reports remain readable when evidence is incomplete, with missing result objects represented as null. Exit code 0 means a complete appendix; 2 means incomplete evidence. Existing output directories are refused.

JSON documents are limited to 32 MiB, individual JSONL records to 4 MiB, and retained analysis records to 200,000. JSONL, including large telemetry, is scanned completely and streamed; unused telemetry payloads are discarded after validation. Limits or parse errors produce incomplete evidence rather than successful truncation. NaN, Infinity, overflowed JSON exponents, boolean metrics and nonnumeric timestamps are rejected.

## Denominators and boundaries

- The physical-follow denominator is the entire original FOLLOW-anchored navigation grid through its recorded endpoint, including invalid navigation and hovering tails.
- The navigation-validity denominator starts at the original report's `navigation_evaluation_start_s`, which may be later than FOLLOW because of calibration. No recalibration or interpolation occurs.
- Identity uses its original REQUEST-anchored cells through the last recorded Clock, including its final partial cell. Original `correct`, `wrong` and `unknown` outcomes are never recalculated. Wrong evidence cannot be erased by splitting a cell.
- The four mutually exclusive time buckets use the original sample/cell **left endpoint**: before FOLLOW; `[F,F+45)`; `[F+45,F+75]`; and `t>F+75`. A cell crossing a bucket or phase boundary stays whole in its left-endpoint bucket and increments `crosses_boundary_cells`. Navigation points at exactly `F+75` belong to the second FOLLOW segment. Identity, navigation and physical denominators stay separate.
- A second independent view partitions every original sample into an event phase. Both views separately conserve all primary counts, identity outcomes, metric sample counts and squared-error sums. They must not be added together as distinct opportunities.

Original navigation metric counts/RMSE and identity outcome totals are checked against the supplied sidecars. The appendix records its source SHA, complete input SHA/byte counts, original declared evaluator provenance and a canonical input-manifest SHA. Declared provenance is preserved, not newly certified. No source file, primary report or existing result is modified.

## Events and overlapping evidence

Complete, ordered events support initial confirmation, normal following, short request/recovery, long request to open, open to explicit REQUEST, REQUEST to new confirmation, the first five seconds after confirmation, later running and the monitor-to-recording tail. Initial confirmation may cross FOLLOW. Specified-task confirmations come from the original identity task audit; unique-mode explicit confirmation is labeled as monitor surface-state evidence. Short recovery is explicitly the first original 10 Hz **valid MEASURED, active** navigation sample after the short open request. This resolution is retained and does not replace a primary recovery gate. Neither endpoint tolerances nor a later identity Clock can manufacture a complete five-second navigation recording.

Missing/repeated events, failed shutter actions, unconfirmed tasks, timestamp regressions or an insufficient recorded recovery window leave one explicit `UNRESOLVED_EVENTS` phase. Counts are still conserved there. A complete main time split can therefore coexist with an incomplete event appendix.

Flags are overlapping observations rather than exclusive causes. Main frames supply LOST/ambiguity, navigation invalidity, inactive control and generic physical-truth missing flags. Optional raw frames describe fusion acceptance/reasons on their own acquisition-opportunity denominator. Original selected-identity rows and optional physical frames supply no fresh selected evidence, geometry/task uncertainty, shutter guard, expected-actor projection clipping and missing independent identity truth. Their acquisition times are placed only into the corresponding original identity cell, with matching task UUID; they are not forward-filled. Both all-cell and UNKNOWN-cell flag counts are shown.

Per-cell snapshot presence and detailed per-navigation-point truth-missing causes are not explicitly exported by the original evaluators, so the appendix marks them `UNAVAILABLE`. Projected truth clipping is not a claim that a detector box was clipped. Grid interruption brackets and the post-confirmation grid prefix describe recorded samples; they do not prove uninterrupted physical availability between samples. All failures and unknown evidence remain in the original denominators.

## Outputs and verification

Open `index.html` for the time/phase table and completeness notes. `segments.csv` contains the same principal counts and distance/height RMSE. `analysis.json` contains full metric, overlap, boundary, interruption and conservation details; `input_manifest.json` binds actual inputs and analyzer source. Neither the HTML nor a complete appendix implies primary PASS.

Focused verification:

```bash
python -B -m unittest discover -s tests -p test_task_phase_analysis_v4.py -v
```

Fixtures cover different physical/navigation denominators, pre-FOLLOW and recording tails, original wrong cells crossing boundaries, partial final cells, missing/reversed events, incomplete five-second recordings, initial confirmation after FOLLOW, unique-instance N/A, missing files, metric mismatch, non-finite values, SHA binding and refusing output overwrite. Fixtures are synthetic and do not establish any new Humble29 result.
