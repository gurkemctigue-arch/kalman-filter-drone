# Prospective47 legacy assertion repair evidence

This snapshot preserves Windows comparison/test receipts as original bytes. It
does not rerun, replace or relabel the original Humble46 full-suite FAIL. That
failure and the original45 stopped flight/owner failure remain separate evidence.

The exact source45 commit is `57dd00965b749c64060cd86409fa6e68feb1c10a`.
Comparison02 executes the original45 fixture functions/protocol and runner read
from that commit, then supplies the same original45 legacy protocol independently
to the original45 and current46 `trial_spec` implementations. Both trial objects
have 28 keys. Their sole difference is the explicit pair inserted at argv index 74:

```text
--supervisor-stream-timestamp-mode receipt_wall
```

Old normalized trial SHA is
`37bb3da92a9fc27516a4220592d864c0ab885ed537ed0b273878e4a8322372e3`;
new normalized SHA is
`fc7b96087836086f1d83dc9a76a58bcc8a07af0a838cf6813c466f1251f89150`.
After verifying and removing only that exact pair from a detached copy, the full
objects match and the old SHA returns. The current fixture protocol separately
adds only the explanatory `supervisor_stream_policy` text; passing either fixture
protocol into the same new runner produces identical trials. Comparison02 keeps
the full protocols/trials and precise differences; Comparison01 remains its raw
predecessor. Their test-source pin predates the assertion edit intentionally.

The main patch changes only the legacy assertion in
`tests/test_car_surface_registration.py`. It first requires one literal flag and
the exact adjacent `receipt_wall` value, then removes that checked pair only from
the normalized detached copy and still requires the original37bb SHA. All other
legacy fields and argv remain protected by that original full-object hash. The
production runner flag, runtime implementation, frozen46 and strict tools do not
change. Removing the production flag would select the new automatic source mode
and break the intended legacy semantics.

The related Windows run passed 32 tests, skipped 0, in 5.385 s, with whole-call
exit0 and before/after source pins unchanged. It covers both the surface-policy
module and supervisor-stream module. The final edited test SHA is
`35c49e0fa21a9bbafc294550668c99c5ea251c4378e8bb338c89bd4b0e2d1e2c`.
Independent repair review passed and is included. No WSL/native build/flight was
performed for these comparison, related-test or snapshot operations.

The separate root-owned complete Windows suite passed: 1789 total, 11 skipped,
0 failures, whole-call exit0, Python3.12.3. The original unittest duration is
759.591 s; the launcher measured 772.0 s wall time. Those are separate timings.
All five watched source pins matched before and after. The raw full log/receipt
and exact root launcher are included under `windows_full/`.
The complete Windows-suite independent review also passed; its exact original
receipt is included under `review/` alongside the assertion-repair review.

The original46 Linux suite had 5 skipped tests and one failure; that platform's
skip count and failed result remain unchanged. The Windows11-skip PASS does not
reclassify original46 or establish a prospective47 native result. Source47 native
build/full tests and flight validation have not run for this snapshot.

Raw copies retain line endings, paths and embedded timestamps exactly;
`.gitattributes` disables text conversion for this directory. SHA256SUMS covers
all current snapshot files except itself; manifest.json lists copied-file pins
and excludes its own hash to avoid self-reference.
