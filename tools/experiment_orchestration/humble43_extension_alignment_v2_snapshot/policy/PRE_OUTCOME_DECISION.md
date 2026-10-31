# Extension contract alignment: static proposal only

Decision fixed at UTC: **2026-10-31T23:07:05+00:00**.

At this decision the parent execution coordinator confirmed **extension43 has not been planned or executed**. This statement is the coordinator's current-state confirmation, not a newly executed extension command. No extension43 plan, run, record, bag, model, or new outcome was inspected to choose this policy. Core43 is currently active. All existing external source/metadata and frozen-source files remain untouched.

## Basis fixed before new extension outcomes

The frozen research contract already accepts complete, healthy extension stress runs with precisely disclosed algorithm failures. The user's plan requires failed trials to be retained and counted. The later external wrapper's all16 PASS rule is an added restriction, not an original research requirement. This proposal removes only that added restriction; it introduces no new failure whitelist, gate, threshold, evaluator or source of truth.

The unchanged original `original41.audit_record(..., extension=True)` and frozen `extension_algorithm_failures` / `validate_probe_gate(..., extensions=True)` remain the only authorities on permitted extension outcomes and exact disclosures. Original FAIL records stay FAIL. Readiness satisfying the original extension contract is explicitly distinguished from all engineering cells passing. Formal280 completion does not imply or require all280 PASS; all original failures remain in the denominator and final reports.

Core12 must still all PASS, and the original full safety4/guard checks still must PASS. Source/runtime, clocks/native state, identity, owner, started markers, per-attempt terminals, reports and hashes, complete recording and missing-evidence checks remain unchanged. The first formal run still needs actual registration, final source seal, safety evidence, actual capacity admission and complete evidence; this proposal is not any such admission.

## Artifacts

- `01_semantic_policy_delta.patch`: exact minimal semantic diff against the two existing v1 baseline files. **Review-only; never apply to live v1.**
- `proposed_sources/*.py.txt`: non-executable complete source text for reading this semantic delta; these still contain baseline v1 module/file identities and are **not deployable v2 tools**.
- `DEPENDENCY_STRATEGY.md`: complete versioned coexistence plan, including manifest and downstream seal identities.
- `BOUNDARY_TEST_DESIGN.md`: required meaningful tests and acceptance evidence, **not executed**.
- `baseline_and_artifact_sha256.json`: only the two baseline-source bindings and staged artifact hashes; no canonical v2 hash is guessed.

No WSL, production imports, validators, tests, flights, bags or models were run/read for this staging task. Only bounded source/metadata text reads and standard-library text/diff generation occurred. The patch is not a deployment authorization mechanism; root reviews and completes authorized work without adding a user-confirmation step.

## Scope deliberately kept narrow

`measure_development_completed_storage.py` already validates original extension FAIL records using the frozen authority and keeps exact disclosures. Its `all28_original_cells_pass` is a truthful diagnostic. Its stricter `eligible_for_budget_input` label has no consumer located by static searches in the external top-level or repository scripts/tools/tests/config. We do not patch storage now or claim that label has blocked execution. If a future real consumer uses it as a policy gate, align that separately in a versioned implementation while retaining all28 PASS as a truthful diagnostic and keeping the original capacity requirements.

Existing v1 tests that assert the added all16/all28 policy are not modified. The proposed change requires new v2 tests and the integration boundaries below before any deployment.

## Actual v2 implementation follow-up

The authorized implementation is now present as10 actual new-named files under `implementation_v2/`; see `IMPLEMENTATION_V2_STATUS.md` and `v2_ten_file_closed_manifest.json`. The earlier semantic .py.txt comparison remains review-only. No source import, test, deployment, admission, plan or flight was executed by this staging task.
