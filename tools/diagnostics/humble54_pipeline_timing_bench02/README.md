# Indexed software timing bench version 02

Only offline trace reduction changes from the original fixed07 bench. bench.py, observer.py, typed_message.py and the schema evidence are copied byte for byte. The original bench01 directory remains unchanged and reproducible.

The indexed reducer keeps the original c7 assessment and all gates, reasons and denominators. Windows synthetic differential tests and an independent review passed. An actual offline re-reduction of all six closed full-person traces matched all 27 reducer fields exactly, including every DDS pair, command, RGB opportunity and raw trace binding. Its measured reduce_files call took 55.484 seconds; sampled current-process RSS peaked at 6,544,707,584 bytes. No original reducer region was separately timed, so this is not a measured native speedup ratio.

The actual full-trace verification receipt is retained in results/diagnostics/humble54_pipeline_timing_perf_verify_full_person01/. It does not modify the original native terminal. The source map and adoption record in this directory bind this new diagnostic version. Use the existing complete input manifests under bench01/full_replay_manifests01 with the existing Humble environment and a fresh external output. Native execution still holds its own existing machine lock; do not add a second outer lock.

This is independent instrumented software replay. Physical E2E remains NOT_OBSERVED and historical strict UNKNOWN remains unchanged. Formal research is still 0/280. No algorithm, model, flight parameter, production archive policy or acceptance threshold changes here.
