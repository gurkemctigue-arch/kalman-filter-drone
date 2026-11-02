# Humble54 car position original closed probe

This is one 75-second failure-equivalent developmental trial, original PASS. It is separate from the new canonical12 and is not a formal repeat. Independent base_link distance/height RMSE: 0.703947/0.170043 m; navigation coverage 0.916223, truth coverage 1.0; both final settling checks passed. Source clock, native startup, recording closure/integrity and actual cleanup passed; no residual graph.

The navigation evaluator retains its `RECORDED_WITH_CENSORED_FAILURES` report status and all loss/inactive intervals. The original engineering verdict uses its independently registered six checks, all true; no report or threshold is rewritten. Long-loss reselection is an explicit user/test action, not automatic identity recovery.

Files are byte-for-byte copies of the original small reports, slot and owner terminal. `snapshot.json` binds each source path, byte size and SHA256. Full bag, timing logs, frame sidecars, telemetry and video remain at the original local trial; this snapshot does not reproduce their contents. Historical Humble53 remains 7 PASS / 1 FAIL / 4 PENDING. Formal research remains 0/280.
