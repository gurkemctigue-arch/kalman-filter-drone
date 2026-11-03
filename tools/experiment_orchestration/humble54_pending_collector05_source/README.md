# Prepared collector 05: class-specific saved captures

Status: `PREPARED_NOT_AUTHORIZED_FOR_CONTINUATION`. Production `main()` refuses
before reading the plan or starting a child. `HISTORY` is empty: no original
closed prefix, unknown-evidence exception or future owner chain is approved.
No collector05 production run, native launch, flight or WSL call has occurred.

This separate source preserves the registered probe02 plan and original
single-slot entry. Collector04 and its running owner are unchanged. It does
not create a new full16 plan, retry an attempted slot or change an old verdict.

The saved `configuration/source_sha256.json` differs by selected model. Each
trial now binds its class, trial model, protocol resource model and registered
model hash before checking the exact class-specific raw capture. Each capture
must contain 204 entries, exactly its selected `.pt` key and the explicit DDS
configuration hash. There is no fallback between classes.

| Class | Selected model | Original saved capture SHA-256 |
|---|---|---|
| person | `models/yolo11n.pt` | `0094a5013801e67fb6ae692cef785b190272708d71bfb0cd4a3349a0eb09ee46` |
| car | `models/yolo11m_car_sim_train20_04.pt` | `c003f1b86e56bc548b4a1f50d890950320d879dbf205b7c86c574c427c28009c` |

The full live source-map comparison remains independent and unchanged. A saved
capture with 204 entries does not substitute for that comparison. The existing
artifact/terminal/marker binding, evaluator checks, original FAIL retention,
new unknown-evidence stop, long-loss safety checks, sharing-conflict handling
and wait for real owned child exit remain in force.

`windows_test01_receipt.json` and `windows_test01.log` preserve the actual
Windows Python 3.12.3 run at 05:09:46--05:09:57 UTC on 2026-11-03: all 30
synthetic/fake-child tests passed, exit 0, all three source hashes unchanged.
The fixtures include successful person/car children, cross-class wrong captures
even with re-sealed terminal/artifact hashes, unknown class, wrong trial or
protocol model, registered model SHA, DDS, count and raw-byte rejection. They
also verify the disabled production CLI. This result is not native simulation
evidence or permission to continue.

Only after the actual previous owners have exited and root has reviewed a
bound closed-prefix/owner-chain contract can a separate registered profile
authorize continuation of the same original pending slots. This source's
status constant is intentionally not changed by the test runner.

Local `.gitattributes` protects sources and raw fixture evidence from Git
line-ending conversion. `manifest.json` records the exact source/evidence
hashes and original capture references.
