# Humble54 development recording: observed timing and strict lineage

This archive preserves eight unchanged small external originals (909,112 bytes): the native execution receipt, export context, three raw logs, complete 885,260-byte timing report, and the one-use Python/shell source. The original Linux execution finished at 2026-11-02 23:47:33 UTC. Export, timing analysis, and lineage analysis all exited 0, taking 28.739, 7.346, and 9.137 wall seconds respectively. These are development observations from the person velocity seed004 recording; they grant no flight acceptance or formal-seed authorization.

## What the measurements mean

- **48,104 normalized events = 47,177 selected messages from eight bag topics + 927 job-log entries.** This is neither the total number of native bag messages nor a new bag integrity result. Original full topic totals remain separately visible in `originals/export/context.json`.
- Detector processed source rate is **10.0 Hz in the recorded ROS source clock**. It is not wall-clock worker FPS.
- Acquisition to detector prepublication median is **80.000 ms in the source clock** (927/927 known; maximum 164.000 ms). It is not physical capture to control or PX4 effect.
- Detector processing prefix wall median is **25.984 ms** (927/927 known; maximum 1161.673 ms). The completed production-job prefix median is **26.442 ms**, excluding its timing-log write and later delivery. Neither prefix is pure YOLO network inference time or a complete callback duration.
- Actual worker wall FPS and true capture-to-controller/PX4/effect causal latency remain **NOT_OBSERVED**. Recorder timestamp rates are reported in their explicitly unverified domain and cannot supply missing worker endpoints. Clock domains are not subtracted or scaled by RTF.

## Strict control-tick lineage remains unknown

The unchanged strict method reports **1,857 original commands, 0 known, 1,857 unknown**. Of these, 480 are inactive/invalid; 1,377 have at least one formula candidate. Within those 1,377, **1,374 have multiple formula candidates and three have a single candidate but remain unknown** because of the track diagnostic indexing constraint. Reasons can overlap: the report contains 515 commands marked `unindexable_native_lineage_for_track` and 18 native/diagnostic pairing anomalies.

Sharing one acquisition timestamp does not make multiple native state outputs uniquely identifiable. The strict method and denominator are unchanged; unknowns receive neither zero latency nor a fabricated E2E estimate. The endpoint being investigated is source-clock control-tick start, before controller update/publication, and does not establish subscriber consumption or PX4 execution.

`lineage_derived_summary.json` is explicitly **derived** from the existing full report: it copies all top-level original fields except the command list, computes the formula-candidate distribution, and retains exactly three unchanged original command objects (event indices 10044, 10066, 10091) selected as the first three with multiple formula candidates. Their matched native outputs include states 1 and 2 with shared image acquisition timestamps, demonstrating why the original strict result stays unknown.

The full lineage report is **not copied** here. Its existing external pin is 5,754,872 bytes, SHA-256 `c33b43419dc3b4e41782b977d8a67297d2135ecd014a418e224895cd6f1987b4`. The 55 MB normalized events, bags, and weights were neither read nor copied by this archival work. Large event/bag hashes in the archived native receipts are recorded provenance, not new payload revalidation by the archivist.

## Archive provenance

`source_manifest.json` records all unchanged original copies and the uncopied full-report pin. Local Git attributes disable newline conversion. `archive_validation.json` records hashes and bounded file/grammar checks. No Git staging or commit was performed by the archivist.

The archival session made **two bounded Windows reads** of the 5.75 MB full lineage report. The first derivation failed on an incorrect assertion that all 1,377 candidate-bearing commands had multiple formula candidates. Its exact source, failure receipt, and observed error excerpt are retained in `derivation_attempt01/`. The corrected attempt recomputed the distribution (1,374 multiple, three single but unknown) and copied the examples without modifying or rerunning either native analysis. `archive_small_evidence.py` is a one-use archival source, not an instruction to rerun it against an existing archive.

Current-process rcutils logger clock evidence is archived separately in `../rcutils_prefix54_actual02_review01/`; that audit does not establish the historical detector process provenance or worker FPS.
