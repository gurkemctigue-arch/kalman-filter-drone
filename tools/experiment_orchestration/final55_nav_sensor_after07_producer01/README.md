# Direct after07 nav28 / sensor4 producer

Preparation only. This tool has not executed a real evaluation, extracted an image, created a review, registered a future result, run a gate, or admitted a formal batch. Root executes it only after real after07 staging/cold validation and independent source review. The actual final55 target descriptor supplies the authoritative builder, runner, external sensor module and contract.

`python -B producer.py` and `describe` only print the two actions. An action without `--execute` also reads no inputs. Actual execution requires Linux `UAVHumble22`, the exact reviewed producer SHA and the unchanged original idle/SITL lock guard. It does not launch WSL or create an owner, trigger, retry, flight, gate or admission.

Use actual canonical file paths and actual file SHAs already produced and reviewed. The following variables deliberately have no future values:

```sh
python3 -B "$tracking_producer" nav --execute \
  --reviewed-source-sha256 "$tracking_reviewed_producer_sha" \
  --target-plan "$tracking_actual_core_or_extension_target" \
  --target-plan-sha256 "$tracking_actual_target_sha" \
  --registration "$tracking_actual_navigation_registration" \
  --registration-sha256 "$tracking_actual_navigation_registration_sha" \
  --output-directory "$tracking_fresh_external_navigation_receipt"

python3 -B "$tracking_producer" sensor --execute \
  --reviewed-source-sha256 "$tracking_reviewed_producer_sha" \
  --target-plan "$tracking_actual_extension_target" \
  --target-plan-sha256 "$tracking_actual_extension_target_sha" \
  --contract "$tracking_actual_declared_sensor_contract" \
  --manifest "$tracking_actual_four_slot_sensor_manifest" \
  --manifest-sha256 "$tracking_actual_four_slot_sensor_manifest_sha" \
  --output-directory "$tracking_fresh_external_sensor_receipt"
```

Both output directories must be fresh, have a canonical existing parent, and be external to the final/original source and original evidence roots. No overwrite or restart exists. Preflight failures before directory creation raise directly. Once a fresh receipt directory exists, collection writes a terminal including actual failures and partial outputs.

Navigation uses all 28 exact registered argv lists serially and the bound original evaluation timeout (currently 1800 s per evaluator). It checks new report and three sidecar conflicts immediately before invocation. It retains actual UTC, direct child integer exit, closed log SHA and execution JSON. Any incomplete evaluator or cleanup error stops remaining slots without retry. The same owned child is awaited even when its initial `/proc` metadata fails; adopted-child reaping excludes the direct child. Cleanup keeps the original TERM 10 s / KILL 5 s grace. A final completion candidate is accepted only by the unchanged original `read_navigation_reevaluation_manifest()`; rejection retains the candidate and an ERROR terminal. Original failure outcomes remain unchanged. A zero evaluator exit or a COMPLETED producer terminal is not engineering PASS.

Sensor consumes the exact declared contract and module, calls their original `evaluate_development_manifest()` API, saves its actual result verbatim, then invokes the runner's original four-cell binding validator. It never creates image observations, extraction manifests or reviews. `INCOMPLETE`, FAIL, null, UNOBSERVED and original denominators remain intact. The existing API's `NOT_APPLICABLE` branch is distinguished from corroborated visual evidence in [CALL_CARD.md](CALL_CARD.md). Real missing extraction/review work remains root's separate task.

All runtime source/target inputs are rechecked before claiming completion; the original target/source/protocol snapshot is revalidated at the end. A final original-validator rejection or source drift stops completion. This producer supplies external evidence to the existing later gate CLIs; it does not invoke those gates.

Only Windows synthetic checks:

```text
python -B -m unittest discover -s tools/experiment_orchestration/final55_nav_sensor_after07_producer01 -p test_producer.py -v
```

The fixtures mock evaluators and native process metadata; they cannot establish native cleanup, actual bag/schema validity, readiness or physical performance. Exact original calling cards and schemas are in [CALL_CARD.md](CALL_CARD.md).
