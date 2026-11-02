# Formal54 supplementary preflight adaptation

This external helper adapts the archived supplementary metadata precheck to the actual, unchanged formal48 DDS adapter. It creates no formal plan, protocol, seal, admission, initial-admission receipt, slot or authorization. All 280 original formal slots, failed-slot records and existing guard/owner gates remain authoritative. The old helper, shell, author tests, historical independent fixtures and handoff are preserved byte for byte in `original_byte_archive`; no historical41 file or receipt is replaced.

The sole execution change is explicit adapter identity. The new contract kind is `FORMAL54_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION`; the new preflight audit kind also has a `FORMAL54` prefix. Historical contracts/audits cannot be reused as evidence of this future binding. The old metadata checks remain in place: actual sealed admission file SHA and internal canonical digest, named original plans, extension reference, physical final-root guard, approved producers/helpers, exact ordered twelve person/car x six-group seed1000 detection/video sources, fixed sampling rule, full280 denominator, zero added formal slots, no selection-derived authorization, unattempted first preflight and preserved later FAIL history. The helper reads only bounded small ordinary metadata/code. It never reads a bag, log, model or whole source tree.

## Explicit adapter identity

Before the new contract is created, preserve an actual inert formal48 `describe` stdout JSON and create a new external identity JSON with exactly these fields:

```json
{
  "schema_version": 1,
  "kind": "FORMAL54_EXPLICIT_REVIEWED_ADAPTER_BINDING_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_NOT_LATER_THAN_CONTRACT",
  "shell": {"path": "ACTUAL_CANONICAL_ABSOLUTE_FORMAL48_SHELL_PATH", "sha256": "ACTUAL_BYTES_SHA256"},
  "python": {"path": "ACTUAL_CANONICAL_ABSOLUTE_FORMAL48_PYTHON_PATH", "sha256": "ACTUAL_BYTES_SHA256"},
  "describe": {"path": "ACTUAL_CANONICAL_ABSOLUTE_DESCRIBE_JSON_PATH", "sha256": "ACTUAL_STDOUT_BYTES_SHA256"},
  "manifest_canonical_sha256": "ACTUAL_DESCRIBE_MANIFEST_CANONICAL_SHA256",
  "reviewed_tools_sha256": "INDEPENDENTLY_ACCEPTED_FORMAL48_TOOL_CANONICAL_SHA256"
}
```

The contract retains all original fields and adds `adapter_binding: {path, sha256}`. Its `adapter.shell`, `adapter.python`, `adapter.reviewed_tools_sha256` must equal the identity's corresponding fields. Its original `adapter.argv_prefix` must use that actual shell and the original exact `--manifest-sha256` **file byte SHA**, `--reviewed-tools-sha256` adapter canonical, and any original explicitly pinned resolutions. The internal admission canonical is a different value and cannot replace its file SHA. No adapter action/slot flag is permitted in the prefix.

The identity is supplied independently on the CLI as its absolute path and byte SHA. The independently reviewed adapter canonical is also a mandatory separate CLI argument; neither a contract nor a self-consistent invented describe manifest can replace it. The identity's describe JSON raw bytes, internal canonical, independently reviewed canonical, actual sibling shell/Python/test bytes and original formal48 filenames must agree. Those small pins are rechecked immediately before exec. Adapter code is never imported or executed by this identity verification.

`actual_formal48_describe_windows01.json` is a real Windows **inert describe** result, with its exact invocation and original independent-review comparison in the adjacent receipt. It proves the described source manifest only; it is not a Linux environment/DDS preflight, formal binding contract or runtime acceptance. For actual Linux contracts use canonical physical Linux paths. Do not relabel Windows path pins as existing Linux bindings.

## Command prefix for the new serial wrapper

The future concrete prerequisites and independently reviewed new helper canonical must already exist. The following is an unexecuted shape, not an actual contract or grant:

```bash
/usr/bin/python3 -B ACTUAL_NEW_SERIAL_SCRIPT \
  --manifest ACTUAL_ORIGINAL_SEALED_ADMISSION_JSON \
  --output ACTUAL_FRESH_EXTERNAL_SERIAL_OUTPUT_DIRECTORY \
  --guard-command bash /mnt/d/WSL/UAVHumble22-validation/formal54_supplementary01/formal_supplementary_preflight.sh \
  --contract ACTUAL_NEW_CONTRACT_JSON \
  --contract-sha256 ACTUAL_CONTRACT_FILE_SHA256 \
  --reviewed-tools-sha256 INDEPENDENTLY_REVIEWED_NEW_PREFLIGHT_CANONICAL_SHA256 \
  --adapter-binding ACTUAL_NEW_ADAPTER_BINDING_JSON \
  --adapter-binding-sha256 ACTUAL_ADAPTER_BINDING_FILE_SHA256 \
  --adapter-reviewed-tools-sha256 INDEPENDENTLY_REVIEWED_FORMAL48_TOOL_CANONICAL_SHA256
```

`--guard-command` remains last. The serial wrapper still appends exactly `run-one --manifest ACTUAL_MANIFEST_PATH`. The helper appends a separate checked preflight audit, rechecks pins, then replaces itself with the original adapter via `os.execvpe`. It retains the original stdout/stderr, exit status and signal ownership. It adds no completion hook, retry, scheduling owner or flight process. The formal48 adapter retains DDS setup/preflight, actual sealed guard and original native owner behavior.

`verify` accepts the same explicit flags and performs read-only metadata verification; it does not write an audit or start the guard. Default `describe` is inert. The future sequence remains **both actual formal plans → actual supplementary protocol → actual sealed admission and new binding/contract → checked first supplementary audit → original initial full280 admission → actual starts**. No old receipt or canonical is manufactured to bridge a missing step.

## Validation scope

The tests use tiny synthetic metadata, the actual approved detection protocol semantic verifier, and fake exec callbacks. The archived historical independent fixtures are rerun as regression fixtures; that does not make the new implementation independently reviewed. The final author test receipt/log report the actual native Windows test outcome. They do not validate real Linux exec/signal propagation, actual future contracts or flights. A separate reviewer must inspect the final source and canonical before formal use.
