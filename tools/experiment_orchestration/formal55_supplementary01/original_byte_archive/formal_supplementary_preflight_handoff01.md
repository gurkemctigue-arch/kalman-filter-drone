# Supplementary metadata preflight handoff 01

This is a reviewed-source handoff candidate, not an actual experiment contract, registration, flight admission, or statement that formal experiments have started. All example paths and SHA values marked `ACTUAL_*` are placeholders. This handoff created no such artifacts and ran no WSL, inference, recording extraction, original adapter, original guard, or simulation.

## Frozen author identity

The source remains external to the final frozen tree, at `D:/WSL/UAVHumble22-validation`. Its three-file tool manifest canonical SHA256 is `53f96e7a92cf8c839d8ff245e8db45b06cfb65371614a012536c417146d609d1`.

| File | SHA256 |
| --- | --- |
| formal_supplementary_preflight.py | 5884e3739d496bf21905d6e0f9b0235aa32441791f78dd17a589176e326bc715 |
| formal_supplementary_preflight.sh | 91145e9524e9f6f7ab2114ed39c611fd02d024f9b5ca06521fa43150d896e6c2 |
| test_formal_supplementary_preflight.py | 1ab0ebcf0cfb7751e218174f5d555e788a028b058e0a84e4f39a42f5b84738d9 |
| formal_supplementary_preflight_author01.json | c9788a2abf201c5cb781d9d76a0666ef88975e50fe977d0b0d405f500588657e |
| formal_supplementary_preflight_author01_tests.log | d4435f0600fa8c9585402b698776c695be07d66506a315632d80cbfe654686e9 |

Author validation: Windows Python 3.12.3, 34 synthetic metadata tests, 34 PASS, no skips, native exit 0. Tests use the actual independently reviewed protocol semantic verifier with fabricated small plans/markers and a fake exec callback. They do not validate a real environment, real flight behavior, Linux exec/signals, a real serial run, or the actual forthcoming contract.

## Exact original command API

The unchanged `formal280_serial_guard01.py` accepts `--manifest`, `--output`, and last `--guard-command` with `argparse.REMAINDER`. Its line 174 appends exactly `run-one --manifest PHYSICAL_MANIFEST_PATH` to that argv prefix. It has no supplementary-protocol option. The original guard's admission schema is unchanged. No fields are added to the original sealed admission.

The new helper has only `describe` (default, inert), `verify` (explicit read-only), and `run-one` (explicit gate then original exec). There is no create or plan action. A successful `run-one` appends only the separate external precheck witness, rechecks its small input pins and new tool identity, then uses `os.execvpe` for the exact original adapter prefix plus the unchanged action/manifest suffix. It emits no successful stdout/stderr decoration. The original adapter therefore retains stdout JSON, `NO_PENDING_SLOTS`, native exit status, signal handling, process ownership, runtime/source checks, and original guard behavior. A precheck refusal exits 2 before adapter exec and writes JSON only to stderr.

Future command shape, not executed here:

```bash
/usr/bin/python3 -B /mnt/d/WSL/UAVHumble22-validation/formal280_serial_guard01.py \
  --manifest ACTUAL_ORIGINAL_SEALED_ADMISSION_JSON \
  --output ACTUAL_FRESH_EXTERNAL_SERIAL_OUTPUT_DIRECTORY \
  --guard-command bash /mnt/d/WSL/UAVHumble22-validation/formal_supplementary_preflight.sh \
  --contract ACTUAL_EXTERNAL_BINDING_JSON \
  --contract-sha256 ACTUAL_EXTERNAL_BINDING_SHA256 \
  --reviewed-tools-sha256 53f96e7a92cf8c839d8ff245e8db45b06cfb65371614a012536c417146d609d1
```

Do not append a manifest/action to the configured prefix: the existing serial wrapper appends them. `--guard-command` must be last. Paths in actual Linux JSON must use actual canonical resolved physical Linux paths, not the Windows paths in this archival handoff. The original adapter shell remains responsible for entering the exact UAVHumble22/Humble environment. The new shell itself performs no environment setup.

## Binding schema, not a generated contract

The external contract has exactly these 12 fields. Every pin is exactly `{path,sha256}`, uses an absolute original canonical physical ordinary-file path, and refers to actual bytes. The following is a schematic template only and deliberately has no valid timestamp or hashes:

```json
{
  "schema_version": 1,
  "kind": "FORMAL_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_AFTER_PLANS_PROTOCOL_AND_ADMISSION",
  "admission": {"path": "ACTUAL_ORIGINAL_SEALED_ADMISSION_JSON", "sha256": "ACTUAL_SHA256"},
  "plans": {
    "core": {"path": "ACTUAL_ORIGINAL_CORE_OUTPUT/plan.json", "sha256": "ACTUAL_SHA256"},
    "extension": {"path": "ACTUAL_ORIGINAL_EXTENSION_OUTPUT/plan.json", "sha256": "ACTUAL_SHA256"}
  },
  "detection_protocol": {"path": "ACTUAL_NEW_EXTERNAL_PROTOCOL_JSON", "sha256": "ACTUAL_SHA256"},
  "selection": {"path": "ACTUAL_SUPPLEMENTARY_SELECTION_JSON", "sha256": "ACTUAL_SHA256"},
  "selection_basis": {"path": "ACTUAL_ORIGINAL_DELIVERY_SELECTION_JSON", "sha256": "ACTUAL_SHA256"},
  "detection_review": {"path": "ACTUAL_ORIGINAL_APPROVED_DETECTION_REVIEW_JSON", "sha256": "0583f950a1557ece5988633d9c812f46b326f26c3bb15b4c5176303becd21a9e"},
  "adapter": {
    "shell": {"path": "ACTUAL_EXTERNAL_DIRECTORY/formal41_guard_adapter01.sh", "sha256": "302ce280d6f89e80fbc5ce8ec43ec92dcdb306400dd2116c53a2a6cb547a9fa5"},
    "python": {"path": "ACTUAL_EXTERNAL_DIRECTORY/formal41_guard_adapter01.py", "sha256": "139ac592e4ead129fc14b93019b4b5b0d7deba700babcb95f58d64dac3278435"},
    "reviewed_tools_sha256": "dad2f80df700805f65b7bbb4cbcb80b6a1ca856527eb4eaa5f51e814ab2d6fbb",
    "argv_prefix": ["bash", "ACTUAL_EXTERNAL_DIRECTORY/formal41_guard_adapter01.sh", "--manifest-sha256", "ACTUAL_ORIGINAL_ADMISSION_FILE_SHA256", "--reviewed-tools-sha256", "dad2f80df700805f65b7bbb4cbcb80b6a1ca856527eb4eaa5f51e814ab2d6fbb"],
    "resolutions": {}
  },
  "preflight_tools_sha256": "53f96e7a92cf8c839d8ff245e8db45b06cfb65371614a012536c417146d609d1",
  "audit_log": "ACTUAL_FRESH_EXTERNAL_AUDIT_JSONL"
}
```

If original independently reviewed resolution files are required, `adapter.resolutions` may contain only `core` and/or `extension` original file pins. The corresponding original `--core-resolution`, `--core-resolution-sha256`, `--extension-resolution`, and `--extension-resolution-sha256` pairs must occur once in `argv_prefix`. Its original argv ordering and argument strings are preserved. Duplicate flags, unknown flags, action/slot options, or changed admission/tool digests are refused. The adapter files must remain the named reviewed siblings of the external preflight source.

## What is checked and what is still original authority

The helper calls the actual approved `prospective_detection_dataset.validate_protocol(protocol, check_tools=True)` from hash-pinned source bytes. It does not call protocol creation. The review's approved three-file canonical is `0581776c0ad6bd3c36e895d9f0795174b22bfd44eef0d1c323f9949b31432fa3`; the actual protocol separately binds the two producer path/SHA objects. Their meanings are not interchangeable.

The helper checks original sealed admission/internal digest, both actual named original `output/plan.json` pins, extension core reference, final root/results/guard paths, plan source/model-map agreement, the eight actual small protocol helper sources, actual selection basis SHA/axes, exact ordered twelve person/car x six group seed1000 sources, full280 denominator, zero added flight slots, no formal-flight authorization from selection, and unchanged sampling rules. Real model weights are never opened by this helper. It verifies times `both plans <= protocol <= binding <= now`, original admission and selection before binding, and actual starts after original initial admission and binding.

Only bounded ordinary `.json`, `.jsonl`, `.py`, and `.sh` files up to 8 MiB are read; duplicate and nonfinite JSON are refused. Original marker paths are checked/pinned before the original protocol verifier may read them. The helper does not hash the whole source, access bags, read runtime logs, extract recordings, run YOLO, perform capacity admission, or choose slots. The actual guard, adapter, source seal, original full280 capacity admission, serial loop, and owner remain authoritative for all their existing functions. Whole-source prestart verification remains a separate original prestart action, not a new per-slot whole-tree hash.

The binding JSON, detection protocol, and audit must be outside the entire immutable final tree, its resolved results target, original guard state, and all plan/trial outputs. Use fresh external files under `D:/WSL/UAVHumble22-validation` (Linux `/mnt/d/WSL/UAVHumble22-validation`) only after the actual original prerequisites exist. No current provisional or development plan may replace an actual formal plan.

## First and later invocation semantics

The first precheck requires no original `initial_admission.json` and all280 original directory/start/terminal products absent. Only then can it establish `first_preflight_all280_untouched` in a new external chained JSONL. Original adapter/guard execution follows afterward and alone may create the original initial admission. A failed precheck does not create an original slot or admission. A successful precheck is merely a precheck attempt; it does not prove that exec or a flight later completed.

Later invocations require that preserved first witness precede the original valid initial admission and every actual start. Completed/started slots, including FAIL, are allowed; requiring all PENDING again would stop a legitimate serial run. Missing prestart history after the first real attempt is refused and cannot be retrofitted. Audit sequence, bindings, timestamps, hash chain, and current original initial pin are rechecked. Existing source/admission/history is never rewritten, and no failed slot is retried or replaced by this helper.

There must be one scheduling owner and one serial writer. The new audit is a provenance chain, not a new global process lock or an independent runtime owner. The unchanged original owner/guard retain scheduling exclusion and cleanup. The helper has no post-exec completion hook. Author tests exercise first and later FAIL history, post-audit metadata drift, false PASS reviews, changed plans/helpers, oversized markers, future clocks, output confinement, missing audit, bogus selection, and unchanged argv/stdout/exit via a fake callback. Concurrent-writer and real Linux signal behavior are not author-test claims.

## Required real sequence after development validation

1. Let the original root-owned development core, safety, extension, capacity evidence, replay calibration, final-root build, and original registrations close under their existing gates. This handoff changes none of them.
2. Create the actual final-root FORMAL120 and EXTENSION_FORMAL160 plans, still entirely unattempted; complete the original replay registration binding those actual plans.
3. Before any formal attempt, create the actual external supplementary detection protocol using the reviewed producer and preserve the actual original selection/basis/review pins. Do not create the supplementary binding contract yet: its exact original sealed-admission pin must already exist.
4. Complete the original final source seal/whole-source prestart verification and original full280 capacity seal, producing the actual original sealed admission. The budget must include old two detection subsets, new twelve uncapped full-trajectory subsets/overlays/cache/review, and timing outputs.
5. Only after that actual admission exists, create and independently inspect the actual external binding contract, preserving its actual SHA. Verify its metadata binding with explicit `verify`, then enter the original serial loop through the above prefix only in its authorized idle/exclusive window. Existing original behavior still decides whether a slot may start.
6. After original recordings close and resources are idle, run separately reviewed extraction, no-prediction visual label review, inference/evaluation/semantic report verification and timing analysis under their own interfaces. All280 terminal rows remain the engineering denominator; the twelve-source supplement is only its declared evaluation subset.

The reviewed snapshot is a source archive, not a portable standalone deployment. It depends on the original humble41/humble42 external adapter/owner/serial and guard, actual immutable final root/registrations/plans/admission, and the reviewed prospective detection tools and original selection files. Copying files into a new directory does not grant readiness or admission and does not preserve old absolute-path contracts automatically.
