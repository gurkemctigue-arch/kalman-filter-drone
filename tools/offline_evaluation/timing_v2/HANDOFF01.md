# Offline timing validity candidate 01

This is a reviewable offline bug fix, not a flight, formal result, protocol publication, or new online freeze. No source under the project tree, existing external tool, frozen source, bag, model, or live simulation was modified or opened by this work.

## Files and actual verification

- `original/` preserves the existing tool and two existing test files byte for byte. The original tool equals both the existing external and public tool: SHA256 `35b53d5a1eebbac41ce51253765336928cb6873690d7870238927492c7e30e1a`.
- `candidate/` contains the proposed tool and tests. Production SHA256 `c6367a2dd7e7a733958a9c15bf6ee3bff6e2b1fa93205c303148f5523d39a4e2`.
- `candidate01.diff` changes one production hunk: only the controller-status age eligibility block, adding 11 lines. The remainder of production bytes, including original source/hash/provenance validation and every other endpoint, is identical.
- `windows_unittest_results01.json` and the four raw stdout/stderr files record actual Windows Python 3.12.3 runs: original 48/48 and candidate 56/56, both exit 0. The eight added tests cover true zero, default zero, prediction age, missing/malformed/inconsistent fields, uint64 identity, decode and clock failures, exact denominators, command-age defaults, and source/tool binding. Native export tests use mocked modules and temporary fixtures only.
- `synthetic_differential01.json` is explicitly synthetic. Only `controller_reported_measurement_age_source_s` differs; every other report field is identical. It is not an experiment result.
- Main `git status --short` was empty after verification. Only small source/metadata hashes were calculated. No WSL, native ROS, bag read, or simulation ran.

## Eligibility and preserved denominator

Known age requires one of the actual producer combinations: integer lifecycle 2 / string reason `tracking` / boolean prediction_active false, or lifecycle 3 / `coasting_prediction` / true. It also requires a positive uint64 track_id and finite, non-boolean, nonnegative reported age. Real FOLLOW age 0.0 remains known. PREDICT does not require visible target and no new age cutoff is introduced.

Other valid lifecycle values remain in the original total and become unknown under the existing schema, with reason `measurement_age_not_applicable_to_controller_lifecycle`; their value is null, not zero. Missing, malformed or inconsistent fields have explicit reasons. Decode errors and invalid source clock retain their existing priority. No sample is removed, reordered, inferred from command_age_s, or converted to a delay success.

An independent child read the actual production diff and test/result files and reported no blocker. That review ran no additional tests and made no changes.

## Minimal later integration

Do not modify an old export context's tools hashes to make it appear produced by this candidate. Its existing exact context.tools == tool_manifest() check is intentionally unchanged, so an original-tool context cannot be silently reused as a candidate-tool export.

At the parent's later, separately scheduled offline evaluation window, use this candidate's existing `export` command against the unchanged frozen source/trial, original job logs, and all existing protected roots, writing to a NEW independent output directory. Then use this same unchanged candidate's `analyze` command with the newly emitted context path/hash and a NEW report path. These are the unchanged CLI arguments:

```text
python3 candidate/offline_pipeline_timing.py export --source-root SOURCE51 --trial CLOSED_TRIAL --output NEW_EXPORT --job-log ORIGINAL_DETECTOR_LOG --protected-root IMMUTABLE_PLAN_OR_OUTPUT_ROOT
python3 candidate/offline_pipeline_timing.py analyze --events NEW_EXPORT/events.jsonl --context NEW_EXPORT/context.json --context-sha256 ACTUAL_NEW_CONTEXT_SHA256 --output NEW_REPORT.json
```

All uppercase names are placeholders to resolve from actual parent-owned pins; no real export, integration or bag operation has been performed. Repeat `--protected-root` as needed to preserve the original protected roots; use the original trial's actual job-log list. The candidate does not relax binding or output protection and does not require any new flight or online instrumentation.

## Existing end-to-end metric and scope correction

The timing tool's NOT_OBSERVED causal fields describe that tool's own endpoints; they must not be generalized into a claim that the project has no image-to-control metric. The unchanged `scripts/evaluate_navigation_reference.py` already calls `visual_metrics` in `scripts/evaluate_follow_dynamics.py`, which reports `image_to_first_tracking_command_sim_s` and documents its source-time definition. The parent has independently inspected an actual first Humble51 result containing this metric; this work did not read that result or compute new real statistics.

That existing metric can report image acquisition to the first valid FOLLOW/PREDICT control cycle in simulation seconds. It reconstructs the accepted source image as state.header minus prediction_age_s, deduplicates task/track/source, and excludes holds/failsafe. Its implementation matches the latest recorded preceding state within 150 ms and the same track; command/status share the control timestamp by actual producer code. This is the existing documented engineering association, not token-verified evidence of the precise state consumed or command publication completion. The control timestamp is sampled at tick start. Report these limits; do not silently relabel it as physical wall-time, PX4 effect latency, or real-time capability.

No PX4 effect ACK is required by the user's requested FPS/end-to-end reporting. The current candidate only repairs default-zero pollution in the separate controller-reported information-age statistic. It adds no ACK requirement, new endpoint, online field, flight gate, or claim that adaptive KF universally wins.
