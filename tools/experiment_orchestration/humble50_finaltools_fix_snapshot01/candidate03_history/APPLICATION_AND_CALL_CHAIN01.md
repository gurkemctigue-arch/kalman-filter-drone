# Final-root-v2 installed DDS / CV2 candidate patch

Status: prepared code only. Not applied, imported, tested or executed. No future root, result store, run or evidence has been bound. The running actual50 core12 and all existing production, pinned tools and evidence remain untouched.

## Exact scope

The unified diff targets only the existing, as-yet-unexecuted `dds48_tools01/build_development_final_root_v2.py` entry. Original SHA256: `c1660b80ed62b6295d088e3a3f18e099941647b8e81bcfa7a77511490ea95718`.

Only existing functions `verify` and `validate_completed_build` change. Other changes are an import, three required BUILD_ARTIFACTS, two fixed original helper inputs, one semantics constant and four local proof helpers. Static AST comparison confirms that build, launch, owner checks, action_binding, validate_receipt, source_check, build_command and main stay identical. The original shell wrapper already correctly separates cold-underlay compilation from installed verification and needs no change.

## Affected call chain

1. Original preparation inspect/copy retains the actual candidate, source review, whole tree/classified maps and preparation outcome.
2. Original launch -> bounded owner -> original 2400-second combined build/verify budget -> original internal-build. Agent-free compilation and strict same-phase DDS checks remain intact.
3. Original wrapper internal-verify reads the unchanged cold preflight. It verifies that record and compile evidence before checking the actual prepared source via original source_check.
4. A local shallow review copy adapts only frozen_root to the actual destination. The proof binds original source_review, original source manifest, preparation outcome/manifest and source_verification. This local helper context is explicitly not a published destination source review. context.review and registries stay untouched.
5. The original byte-pinned build50 pure verify_transition accepts only same-root install/lib insertion at index 2; all remaining fields of the complete DDS report must match. The transition artifact also binds the actual generated setup hash. Original cold preflight bytes remain unchanged.
6. Before audit_origins, the byte-pinned CV2 helper preload_and_restore runs once. Complete environment restoration, exact import delta, started marker, four pinned wheel files, module origins and full before/after DDS are checked.
7. Original import/ament/bridge, CDR11 and full suite execute unchanged. Final strict fresh DDS comparison uses the installed report. The closure binds the transition and CV2 evidence. Three required artifacts are added: dds_install_transition.json, cv2_import_environment01.started.json and cv2_import_environment01.json.
8. Original validate_completed_build retains all original owner, compiler, suite, CDR, origins and resource checks. It additionally recomputes transition/CV2 proof and validates actual bound input hashes. This offline entry adds neither source_check nor a comparison with its caller's DDS environment, preserving support for later canonical publications validated by their publisher.

## Future application

Only after actual50 core12 and subsequent required gates pass, root must verify the baseline builder hash, then apply this diff to the existing same-named entry inside dds48_tools01. Do not run the candidate from this preparation directory: the original WRAPPER and preparation.EXTERNAL intentionally select dds48_tools01.

Replace only this unexecuted v2 builder. Do not modify reviewed_freeze_build, development_freeze_build, development_runner, bounded owner, reused primitives, build50 helpers or the main repository. Core2129 OWN_FILES and recursive dependencies do not include the v2 builder, so its fixed identity remains untouched. V2 preparation OWN naturally includes the changed builder SHA. Recompute and independently review the v2-specific tools manifest/canonical SHA before producing any new proposal or preparation. Never edit old proposal or old tools identity fields to reinterpret prior evidence.

Reuse calls only original build50 verify_transition and CV2's existing helper API; never its fixed-root load_context/build/validate/main. Helper paths, hashes and imported origins are checked each time and their bindings are saved in the transition record.

The historical bridge small metadata prerequisite is already restored by root: dds48_tools01/humble23_bridge_shutdown_diagnostic01/A01_final_validation01.json has the original SHA256 a5c8d2a593d4c8ea17a809723f12dafca28cca016b1e5aa4ae3934878ac1ed1b. It remains an unchanged required input. The independent peer receipt separately confirms this resolved prerequisite.

## Required later validation; none executed in this task

- Extend existing final-v2 fixtures with three mandatory artifacts and complete CV2 reports; preserve the explicit offline no-source_check invariant.
- Accept exact cold-to-installed insertion; reject wrong-root, duplicate or additional loader items, any other DDS change, setup hash change and source/preparation binding change.
- Check preload ordering before audit_origins. Reject undeclared environment changes, incomplete restoration, changed started/hash/module/wheel/full DDS evidence.
- Preserve failure logs and original no-retry behavior for helper, source, compiler and suite failures; no flight may start as part of these checks.
- Verify original 2400-second budget, PID/PGID/session/start_ticks, cleanup, original colcon argv and system FastCDR provenance remain unchanged.
- Run one real cold build plus original import/CDR/full suite on a separately selected fresh final root, then independently verify the actual resulting evidence. Registration, capacity admission and formal experiments remain subsequent gated work.
