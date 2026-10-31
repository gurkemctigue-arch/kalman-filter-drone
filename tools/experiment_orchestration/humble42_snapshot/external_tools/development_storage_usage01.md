# Parameterized candidate storage collector

This helper is prepared for future metadata collection only. It has not run against a real candidate. Independent review of the final tool/dependency digests is still required. It grants no formal capacity or seed authorization.

Files: `measure_development_completed_storage.py`, `measure_development_completed_storage.sh`, `test_measure_development_completed_storage.py`.

`bash measure_development_completed_storage.sh describe` is inert and prints the exact helper manifest/digest. The manifest incorporates the actual final core, safety and extension tool identities; obtain it again after their reviewed revisions are final. Do not register a digest from an earlier dependency revision.

The future explicit invocation is:

```bash
bash /mnt/d/WSL/UAVHumble22-validation/measure_development_completed_storage.sh measure \
  --admission /mnt/d/WSL/UAVHumble22-validation/ACTUAL_FINAL_EXTENSION_ADMISSION.json \
  --admission-sha256 ACTUAL_FILE_SHA256 \
  --contract /mnt/d/WSL/UAVHumble22-validation/ACTUAL_FINAL_EXTENSION_CONTRACT.json \
  --contract-sha256 ACTUAL_FILE_SHA256 \
  --reviewed-helpers-sha256 INDEPENDENTLY_REVIEWED_FINAL_HELPER_CANONICAL_SHA256 \
  --output /root/ACTUAL_NEW_CANDIDATE/results/freeze_validation/artifact_storage_CANDIDATE_01
```

The extension admission already binds the actual candidate manifest, reviewed source, original core contract, reviewed dependency tools, frozen extension protocol and actual safety registry. The extension contract is independently reviewed and its original complete16 run must exist. Existing real APIs recheck complete same-source core12 PASS, complete safety4 PASS and its frozen guard validation, actual strict512 runtime/build supplement, all16 attempts/markers/reports and the real owner terminal after wait/cleanup. Candidate41 globals and old PASS evidence are not substituted.

The output contains one schema-compatible size receipt per original core12/extension16 trial plus `complete28.json`. All 28 distinct actual75s source-clock recordings must close healthily. Auxiliary files and bag files are inventoried with stat; bag/video/model payloads are not opened by accounting. Original failed statuses remain in the receipts. All28 PASS is required for `eligible_for_budget_input=true`; the collector always reports `capacity_admission_performed=false` and `formal_seed_use_authorized=false`.

The `3 * raw + 2 * compressed` component is a conservative archive bound from original component sizes, not an observed peak. Safety4 storage is outside the persistent280 mapping and must be included separately in remaining-work/reserve assumptions. Use the unchanged physical inventory/budget/guard tools to account for actual Windows volume and WSL VHD backing, current free space, growth, delivery reserve and additional work. New receipts cannot replace this separate capacity decision.

Pure tests: `python -B -m unittest test_measure_development_completed_storage -v`. Fixtures use temporary small synthetic files and never run real candidate measurement, ROS, inference, simulation, archive or formal seeds.
