# Current-process rcutils prefix observation: actual02 independent review

This small archive preserves 18 external originals (92,234 bytes), including the failed actual01 attempt, the corrected actual02 attempt, five scripts, four controlled logger observations, and six saved ELF text outputs. It contains no ELF binaries, bags, model weights, or simulator data. External original bytes are unchanged; see `source_manifest.json`.

The independent reviewer executed only `review_saved_text.py` on Windows. It did not import ROS, start WSL, rerun either probe or the native checker, inspect historical detector processes, or open the mapped native libraries. The archived Linux scripts are evidence and were not run by the reviewer.

## Results and limits

- actual01 exited 1 because Humble has no `rclpy.clock_type` import at that path. Its empty stdout and original traceback are retained. The failure precedes `logging.initialize()`.
- Probe02 differs from probe01 by exactly one byte-preserving import replacement: `from rclpy.clock_type import ClockType` to `from rclpy.clock import ClockType`. Its logger name intentionally still ends in `probe01`.
- actual02 exited 0. Four decimal `{time}` tokens exactly equal the corresponding integer `{time_as_nanoseconds}` tokens. Each prefix lies inside its saved `time.time_ns()` call bracket. System and monotonic brackets do not regress during these four observations.
- The process-local ROS clock was set to 7, 9, 3, and 3 seconds. Prefixes instead match the system-time brackets and continue increasing. This process started no ROS node, DDS graph, simulator, or production detector.
- Saved ELF text shows `rcutils_log` calling `rcutils_system_time_now`, whose `clock_gettime` argument is 0 (`CLOCK_REALTIME` on this Linux ABI). It combines seconds times one billion plus nanoseconds. The timestamp passes as the fourth x86-64 System V argument through the output handler to the formatter and its token context.
- The individual token handler bodies are not present in the saved disassembly and were not reviewed. The actual decimal/integer console observations complement the timestamp argument trace.
- Saved maps and before/after path pins support the current audit process only. The independent reviewer checked the consistency of the saved evidence and hashes, without reopening libraries. This does **not** authenticate historical production detector source, libraries, load environment, or clock usage.
- Worker wall-clock FPS, inference duration, callback start/end, and publication endpoints remain **unestablished** by this audit. Logger-call brackets must not be used as worker timing endpoints.

| Event | Prefix ns | System before ns | System after ns | Controlled ROS ns |
| --- | ---: | ---: | ---: | ---: |
| 0 | 1793663364327784918 | 1793663364305122309 | 1793663364328220872 | 7000000000 |
| 1 | 1793663364356246569 | 1793663364348802063 | 1793663364356603233 | 9000000000 |
| 2 | 1793663364384335279 | 1793663364377125285 | 1793663364384684879 | 3000000000 |
| 3 | 1793663364410884027 | 1793663364405249703 | 1793663364411163495 | 3000000000 |

## Evidence

`actual01/` and `actual02/` preserve the original outputs; `scripts/` preserves the original scripts. `independent_review_receipt.json` records the separate arithmetic and saved-disassembly review. `archive_validation.json` records the original-byte checks, bounded file sizes, Python 3.10 grammar checks, and local Git attributes. Attributes disable newline conversion so staged original hashes can remain unchanged.

The original native checker receipt is retained with its original `PENDING_HUMAN_OR_AGENT_DISASSEMBLY_REVIEW` value. The independent review is a separate receipt and does not rewrite that historical file. This archive changes no experiment result, timing claim, identity denominator, or acceptance threshold.
