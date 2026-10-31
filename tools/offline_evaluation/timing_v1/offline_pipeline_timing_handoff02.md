# External offline observed timing: corrected author handoff 02

This handoff supersedes `offline_pipeline_timing_handoff01.md` after the independent reviewer found two blocking job-log provenance issues. Prior handoff, author receipts 01–03, original experiments and frozen42 remain retained; they are not overwritten or promoted to evidence for this revision.

## Current frozen author identity and tests

| File | SHA-256 |
| --- | --- |
| `offline_pipeline_timing.py` | `35b53d5a1eebbac41ce51253765336928cb6873690d7870238927492c7e30e1a` |
| `test_offline_pipeline_timing.py` | `a6a3a3e3dc72ca20da90449a546fe7f30a8ccd8b2cbeb201557e6addd5a33f5f` |

Manifest canonical SHA-256: `5050ed369c680fd6b7c746fc7481b0635fd6aaebf2159e4ffc6d1b6bef4faeee`.

Both Windows Python 3.12 and Humble22 Python 3.10 passed **45/45 author pure fixtures**, native exit code 0, no skips/failures/errors. Native receipts bind the fixture IDs, actual platform, source manifest, driver and full UTF-8 test log:

- `offline_pipeline_timing_author_windows04.json`, SHA-256 `5eb83c2d046cb107495d446b46a273d18ec74c0de5ac2a3b137009c3e8c7e69a`.
- `offline_pipeline_timing_author_humble04.json`, SHA-256 `988f2617c67eab44f3c107380ac88dfa5051366749bbbfed87dbe3e0a8592493`.

The WSL launcher printed a localhost-proxy warning. The native receipt was written by Linux Python and records native exit code 0; no flight conclusion follows from the warning or the test result.

All test inputs were synthetic temporary fixtures, including the fully mocked native-reader tests. No actual bag/job-log export or analysis, inference, simulation, build, installation, heavy bag/weight hashes, core restart, formal trial, Git upload, or immutable-source mutation was performed for this revision. Independent reviewer `/root/review_repair_patch` owns its separate `test_offline_pipeline_timing_independent01.py`; the author has not modified it. Independent review is pending at handoff time.

## Blocking findings corrected

1. **Normalized job events must be backed by the complete bound original log evidence.** The file-analysis entry point checks every job-log index against `context.job_logs`, reparses every bounded original log, and requires the complete normalized job event list to equal that reconstructed list in original log/physical-line order and content. This includes malformed/decode-error timing opportunities. No bound logs plus any normalized job event is rejected. Adding, deleting, reordering, changing a physical line, or forging even an internally consistent duration is rejected before a report is written. All original pins are rechecked before and after analysis.
2. **Every event at a duplicated physical log coordinate is unknown.** The pure analyzer counts all valid `(log_index, line_number)` coordinates before assigning any known sample. If the same coordinate appears twice with different job keys, both opportunities remain in the denominator and both prefix/predict metrics are UNKNOWN. Coordinates from two distinct log indices are independent. The original events are never deduplicated, sorted or repaired.

File-analysis coverage now states `bound_job_logs_reparsed`, `bound_original_job_events_reconstructed`, and `normalized_job_events_equal_bound_original_logs`. This asserts equality against the selected bound original logs; it does not assert that omitted logs never existed or that a recording tail is valid. A caller-created context is not signed independent provenance; root must approve the original immutable inputs/context pin.

The pure `analyze_events` function supports synthetic fixtures. Real source-bound timing evidence must use `analyze_files` / CLI `analyze`, which enforces the original-log reconstruction check. A pure function result is not a native-export or provenance certificate.

## Measurement boundaries retained

No measurement endpoints or online protocols were added. The tool remains standard-library-only for import/default `describe`/normalized analysis; explicit future `export` alone lazily imports native ROS and the existing frozen `scripts/evaluate_stage1_flight.py:134` reader. It binds 11 named small original source files, trial config/receipts where present, bag metadata, selected small logs, and normalized events. It never hashes bag/model payloads or uses truth IDs.

Reported observations remain:

- Detector receive rate in **UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN**, never physical wall FPS.
- Processed acquisition rate in detector ROS source-clock seconds; simulation seconds only under a separately verified recorded `use_sim_time` contract.
- Acquisition to the detector's prepublication `completed_s` clock sample (`detector_node.py:843,867–888`); excludes later delivery.
- Existing detector `inference_wall_s` processing/publication prefix; not pure YOLO prediction.
- Controller-reported measurement age (`controller_node.py:146–164,215–219`); not a causal acquisition-to-command match.
- Completed final job prefix before its timing-log write and exactly-one `yolo_predict` stage, requiring schema 1/final scope and a consistent exclusive stage/prefix partition (`inference_timing.py:67–83`). Inclusive lock holds are never added.

Actual worker monotonic completion FPS and all causal capture-to-controller, capture-to-PX4-setpoint, physical capture-to-PX4-effect metrics remain **NOT_OBSERVED**, null statistics and zero known samples. Recorded controller command opportunities, including decode errors, remain in their unknown denominator. `TrackingCommand.msg` has no UUID/acquisition/job token; supervisor restamps (`flight_supervisor.py:790–791`); PX4 gets a new publish timestamp (`adapter_node.py:407,449`). Nearest, first, repeated-payload or track-only joins cannot resolve that missing causal chain and are never used. Recorder timestamps are never subtracted from ROS/source timestamps or rescaled by RTF.

Bag order, source/recorder reversal, epoch change, duplicate source/job keys, partial jobs, failure/early return, invalid durations, malformed logs and missing unique job keys remain explicit. `native_bag_read_to_end` only means reaching the original reader's end; neither it nor receipt availability certifies health, closure, recording tail, flight acceptance, or formal experiment admission.

## Output and original-input protections

At least one explicit `--protected-root` is mandatory. Root must bind the **actual original immutable plan/output root**, not a placeholder/unrelated directory. All declared roots are existing canonical directories stored in context and validated by analysis. Fresh export and report outputs must stay outside the entire source root, original trial, all protected roots, and the resolved `source_root/results` target even if that directory links outside the source filesystem. That resolved target is recorded and checked. Existing outputs and aliases of original inputs are refused. Named source/receipt/metadata bindings must point at the exact original paths; identical copies elsewhere are rejected.

Exports retain `started.json`, partial events and `failed.json` on failure, never overwrite evidence, and never produce a valid completed context for a failed read. Tool/source/test identities and bound small inputs are rechecked. No core/formal result or acceptance ledger is updated by this tool.

## Future execution, not performed here

Only after independent review should root schedule a read against approved immutable original inputs. Native export can read the entire bag and may use the original reader's temporary decompression cache; root must check storage/CPU/temp space and wait for its exclusive window. This task authorizes no actual read merely because the pure tests passed.

Run export and analysis in the same native path namespace. Windows/WSL path aliases are not interchangeable source pins. Example placeholders below must be replaced by root before execution:

```bash
python3 -B /mnt/d/WSL/UAVHumble22-validation/offline_pipeline_timing.py describe

python3 -B /mnt/d/WSL/UAVHumble22-validation/offline_pipeline_timing.py export \
  --source-root /path/to/approved/frozen/source \
  --trial /path/to/approved/original/trial \
  --protected-root /path/to/approved/original/plan-output \
  --job-log /path/to/approved/original/detector.log \
  --output /path/to/fresh/external/timing_export

python3 -B /mnt/d/WSL/UAVHumble22-validation/offline_pipeline_timing.py analyze \
  --events /path/to/fresh/external/timing_export/events.jsonl \
  --context /path/to/fresh/external/timing_export/context.json \
  --context-sha256 SHA256_PRINTED_BY_EXPORT \
  --output /path/to/fresh/external/timing_report.json
```

Both `--job-log` and `--protected-root` can repeat. Missing job-log evidence stays unknown. Future online causal instrumentation would require a separate protocol revision and new independent trials; it is outside this frozen implementation.
