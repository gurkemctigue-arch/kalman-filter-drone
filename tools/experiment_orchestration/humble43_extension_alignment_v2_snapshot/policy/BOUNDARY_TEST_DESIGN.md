# Boundary-test design (not executed)

These tests are requirements for a later v2 implementation. They must exercise the unchanged frozen production authorities, not a new algorithm-failure whitelist or a mock that accepts arbitrary statuses. No test or validator was executed for this staging proposal.

## Authority fixture and observation

Build minimal bounded synthetic metadata fixtures for the original frozen `extension_algorithm_failures` and `validate_probe_gate(..., extensions=True)` with the real required evaluator set, source/runtime provenance, signatures/bindings and full 2x8 matrix. Do not fake their return values in acceptance tests. Existing unit mocks may isolate lifecycle binding failures, but acceptance/rejection of extension outcomes must use the actual unchanged frozen functions. A second integration fixture runs full publisher `prepare_protocols`; its existing frozen gate call must execute and reject before any bytes can be published. Testing only `require_original_development_records` proves binding behavior, never extension admissibility.

Each accepted fixture must assert: original record bytes/digest/status/engineering_result unchanged, exact failures recomputed by original functions, all16 denominator/order retained, actual counts preserved, truthful all-pass diagnostic, and no formal/publication artifacts accidentally created. A complete extension performance FAIL must remain FAIL in both original records and calibration provenance, while readiness carries explicit original-contract scope.

| Boundary | Expected later behavior | Evidence/assertion |
| --- | --- | --- |
| Complete healthy all16 PASS | Accept original-contract readiness | counts PASS16, all_original_cells_pass true, every original known list empty |
| One full healthy original navigation performance FAIL, remaining15 PASS | Accept only if frozen failure function/complete gate accepts | original FAIL unchanged; PASS15/FAIL1; all-pass false; exact original navigation disclosure retained per slot |
| Each algorithm outcome that original frozen code permits (short/long surfaces), including permitted UNOBSERVED values | Match frozen function, never local policy | Build fixtures from actual original branches; compare exact sorted output with original audit and gate known failures |
| Safety predicate fails under otherwise allowed extension FAIL | Reject | LOST/hover/low-speed/no-auto-recovery/no-tracking-before-reselection and real shutter ACK ordering remain mandatory |
| Source/native startup, clocks, owner, cleanup or report binding fails | Reject | No calibration candidate or publication; exact rejection from unchanged authority/lifecycle check |
| INVALID / INCOMPLETE_EVIDENCE / EVALUATION_PENDING / MISSING surface or incomplete evaluator set | Reject | Original validator remains authority; no conversion to algorithm FAIL |
| Arbitrary unregistered failure name or surface status inconsistent with exact failure list | Reject | Real frozen failure function rejects; wrapper cannot bypass |
| known_algorithm_failures missing, added, removed, reordered where exact frozen representation differs, or edited after audit | Reject | Original gate exact equality and original terminal audit equality exercised |
| Original status changed to PASS, attempted reinterpretation via overrides | Reject | Original record SHA, same-source binding and no-evaluation-overrides preserved |
| Missing/duplicate/misordered slot or attempt,17th slot, missing original FAIL | Reject | Exactly16 ids/order and count remain required |
| started marker, terminal, attempt number or entry_binding mutated | Reject | Every existing original exact-equality check retained |
| Core12 contains one FAIL or full safety4/guard fails | Reject | Added extension relaxation cannot affect core/safety admission |
| Selected person/car seed004 velocity source is FAIL, wrong class/seed/group, changed recording, only74s or missing native archive | Reject | Existing selected_recordings, exact sample identity,75s/closure/native/online/truth and capacity validation unchanged |
| Original R0 calibration sources/membership/thresholds | Identical result given same two actual arrays | Reuse original exporter/calibrator, include KF rejects, no truth-based sample selection |
| Valid complete gate but changed source root/model/plan/source hash or second source plan | Reject | All existing publisher extra same-source/root/one-plan bindings retained |
| Record execution status != COMPLETED, infra_stop true or flight rc !=0 | Reject | Both wrapper health checks and original validator exercised |
| Original target/formal products already exist or any target not PENDING | Reject | Original untouched-PENDING/one-shot safeguards remain |
| Added v2 files only | All v1 tool identities unchanged | Compare exact pre/post v1 byte hashes; no import/module alias rebinding |
| v2 admission or request contains old v1 canonical/hash/name | Reject | New own/dependency/origin checks and exact reviewed real identity required |
| Complete v2 connection with tampered publisher/build/wrapper/test or seal pin | Reject | Full actual manifest/transitive connection checks; no selective pinning |
| Formal matrix has ordinary algorithm FAILs | Preserve terminal result and continue original next-PENDING behavior | Completion means0 PENDING, not all280 PASS; rejected infrastructure evidence still fails the actual guard |

## Existing tests requiring versioned replacements

`test_development_calibration.py` around164-194 encodes the original all16 behavior; leave it unchanged for v1. New v2 tests replace only that added acceptance policy and assert actual status summaries/disclosures. `test_development_final_root.py` around360-435 currently requires empty extension known failures and all records PASS; new v2 integration tests retain all source/record/healthy-execution/duplicate/override boundaries but require only core records all PASS after the actual frozen extension gate validates.

The staged helper is explicitly a binding helper with a caller precondition; an integration test must prove that `prepare_protocols` invokes the unchanged full frozen extension gate before invoking it. If v2 exposes a new public entry bypassing `prepare_protocols`, that entry must call the original full gate as well; documenting a precondition alone does not authorize a bypass.

## Exit condition for later deployment

All meaningful unchanged original rejection boundaries pass; full16 disclosed-algorithm-FAIL acceptance passes through real original code; both fixed calibration-source constraints pass; v1 byte identity is unchanged; the complete v2 connection/seal manifests are independently reviewable. Only then may root schedule actual v2 use. This is engineering verification within existing authorization, not a new user-permission flow.
