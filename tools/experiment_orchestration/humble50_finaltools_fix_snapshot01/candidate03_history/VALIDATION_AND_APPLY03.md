# Current application set and validation result

This note supersedes the initial static-only state in APPLICATION_AND_CALL_CHAIN01.md. Production files are still unchanged. No future final root, formal evidence or runtime acceptance has been created.

## The two files to apply later

1. Existing dds48_tools01/build_development_final_root_v2.py: apply final_root_v2_installed_dds_cv2_candidate01.patch, or verify and use build_development_final_root_v2.candidate01.py. Baseline c1660b80ed62b6295d088e3a3f18e099941647b8e81bcfa7a77511490ea95718; candidate 7405debd20fd1867858dba1b9a1baf507640fee3b4b2e77eb3df2e265ad60708.
2. Existing dds48_tools01/test_development_final_root_v2.py: apply final_root_v2_metadata_tests_candidate01.patch, or verify and use test_development_final_root_v2.candidate01.py. Baseline 70878d27c6ecf94d691264b4bb6f3831b99e405cf170f8940e40d0b801101a3b; candidate bdf88c4cc55311faa2e46a403538e7df3d4245b2fd447b7dc14d498e1c77a7d9.

Use candidate01 for both files. Candidate02 tests were an abandoned Windows fixture transport experiment and must not be applied. No OS path adapter is present in the application set. The production builder did not require any revision or weakened proof for testing.

Apply only after the required actual50 gates. The v2-specific preparation OWN includes both changed files, so regenerate and independently review that tools manifest/canonical before any new proposal or source preparation. Do not rewrite prior identity fields. Core2129 and original bounded/primitives/build50 inputs remain unchanged.

## Actual focused validation

One authorized UAVHumble22 venv run executed the original Linux path semantics: 17 tests passed, 0 failures/errors/skips, 69.790 seconds. The selected cases are CompletedBuildFixture (4 existing + 10 new) and 3 unchanged BuildOwnershipTests. Tests are synthetic metadata checks, not a real build or simulation.

All subprocess creation and actual source authority/scans, DDS acquisition, original environment/import/FastCDR/CDR/full-suite implementations were blocked at the outer runner; fixture mocks replace those native boundaries. Candidate metadata validation, exact original transition algorithm, complete CV2 delta/restoration proof, raw artifact binding, wheel hash checking on tiny fixture files and preload ordering remained active. No ROS or native CV2 module was imported.

The test fixture now supplies the three mandatory sidecars and complete source/preparation, transition and CV2 proof. New cases reject wrong root, extra loader item, incomplete environment restoration, undeclared import delta, started/module/DDS tamper, changed tiny wheel bytes, changed original cold bytes despite rebound chain labels, invalid local review adaptation, changed generated setup, and missing sidecars. Active verification proves preload occurs before import/CDR/suite; preload failure prevents those actions and the success receipt. The original offline no-source_check assertion remains intact.

The first Windows attempt is retained as FAIL: all 14 closure cases stopped in setUp because a real Windows drive colon is not a Linux LD separator; the three owner cases passed. The later abandoned adapter-only Windows attempt is retained as history, with no relevance to native acceptance. The actual application candidate is validated by the one native run without that adapter.

The native runner fixed all temp files and logs inside this preparation directory; its temp root is now empty. No actual DDS48/main source or pinned evidence was changed. Native cold build, original import/CDR/full suite and independent resulting-evidence review on a future new final root remain required later.
