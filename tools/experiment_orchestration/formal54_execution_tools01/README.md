# Formal54 execution tools: original-byte source and evidence snapshot

This directory preserves the final reviewed bytes of three external execution
tools for Git review and reproduction. It is **not** a new formal admission,
registration, experiment plan, launch request, flight result or runtime test.
Copying these files does not relocate or authorize their original absolute-path
contracts. The external originals and frozen project sources were not edited.

| Original external tool group | Accepted source canonical SHA256 | Preserved validation |
| --- | --- | --- |
| `formal54_serial_signal01` | `d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8` | 25 Windows pure tests; 2 Linux dummy tests observed by root |
| `formal54_supplementary01` | `b0c4f60b438455569f46f2160ac4bb0e46202fca311a57f9b25181fe7d4b680c` | 55 Windows synthetic metadata/fake-exec tests |
| `formal54_durable_owner01` | `f90b780da8d8020c6fec111fd40ac771a315afe82bdb532b8de9984309ce4b2f` | 31 Windows fake-process/static tests; durable native tests not yet run |

These are tool-validation counts, not formal flight or algorithm success rates.
The original 280-slot guard denominator, ordinary FAIL rows, source/runtime
gates and adapter cleanup remain under the existing formal guard and adapters.

The serial's [root native receipt](formal54_serial_signal01/root_native_validation01.json)
records actual SIGINT/SIGTERM dummy tests: 2 passed, native return code 0.
That invocation retained a **tool observation only**. It did not capture a
separate independent raw stdout file; none has been synthesized in this snapshot.
The receipt proves no formal flight or complete durable-owner integration.

The durable [native dummy test source](formal54_durable_owner01/test_native_durable_dummy.py)
is provided for a future exclusive native idle window. No durable native
execution is claimed here. Future native evidence must be recorded separately.

## Files and provenance

[manifest.json](manifest.json) binds every copied file to its original absolute
source path, relative snapshot path, byte size and SHA256. It also preserves each
tool's source manifest and accepted canonical. The code, tests, final HANDOFF,
final author receipts, describe output and corresponding small logs were copied
without text or line-ending normalization. The serial's two `.original.py`
files are included because its final approved source manifest/runtime checks
still require those exact reference bytes.

[snapshot_verification.json](snapshot_verification.json) records the Windows
static verification: 33 copied files (336,272 bytes), exact source/destination
hash equality, 13 Python files parsed using Python 3.10 syntax rules, and the
shell's LF/shebang check. Source canonicals were recomputed from metadata
without importing or executing these tools. No unit tests, real child process,
WSL command, ROS node, simulator, bag/model read or flight ran during snapshot
creation. This repeats no native-validation claim.

[historical_evidence.json](historical_evidence.json) summarizes the superseded
23/28/30-test revisions, original formal41-only supplementary binding, the
intermediate adapter-only subset and the author evidence-writer failure. Each
entry includes actual original metadata paths, sizes and SHA256. Historical
source archives remain external and are referenced by their original archive
manifests instead of copying all old source revisions. A passed historical test
suite can still have a subsequently identified coverage gap; it is not relabeled
as a failed flight. The evidence-writer failure was a `.log` suffix refusal,
not a production or unit-test failure.

Author receipts retain their original wording and absolute paths, including
their then-pending independent-review scope. They were not rewritten to imply a
new review or validation. The accepted source canonicals above identify the
final bytes accepted in the parent review session; the snapshot itself creates
no new independent-review receipt.

## Reproduction boundary

Read the original group handoffs for the future wiring:

- [Serial ownership and signals](formal54_serial_signal01/HANDOFF.md)
- [Supplementary protocol/adapter bindings](formal54_supplementary01/HANDOFF.md)
- [Durable launch, watch, stop and risks](formal54_durable_owner01/HANDOFF.md)

This is a provenance snapshot, not a standalone portable runtime bundle.
Original dependencies include the reviewed formal48 adapter/native owner,
prospective detection producers/review, original physical frozen root, actual
formal plans/protocol/contract/admission and runtime environment. They are not
recreated here. For example, supplementary fixture paths expect the original
external producer layout; do not assume a copied test directory is a complete
deployment. Use actual canonical Linux paths and independently reviewed pins
when constructing future real inputs. Do not execute the copied tools as an
alias for an already bound external entry point.

The original bytes include Windows-produced JSON line endings. Git blob bytes
must remain identical to the manifest when these files are committed; this task
did not modify repository `.gitattributes`, the main README, existing sources or
the Git index. The parent integration step owns those repository changes.
