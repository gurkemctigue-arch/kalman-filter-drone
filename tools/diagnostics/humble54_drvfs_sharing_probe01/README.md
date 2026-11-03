# Actual DrvFS metadata sharing probe

This is an actual, deliberately tiny Windows/WSL file-sharing experiment. It does
not execute a collector loop, ROS, Gazebo, PX4, a recording, or a flight. Passing
it makes no claim about flight reliability, capacity, readiness, or the separate
fake-child fixtures for collector fault supervision.

The script is inert without `--execute`. The root agent controls actual WSL
execution. Output must be a new directory under this project's `D:\...\results`.
Existing output is refused, and neither case is automatically retried.

## Registered sources

| Helper | SHA256 |
| --- | --- |
| Original external collector03 | `dd4583da4f34b216bc5dd5a95aa904459ebc7f68e2bfba026a2e3e66706d9c86` |
| Registered collector04 | `bf9168f2b5b6dc31e43c187d894f860a4d77e780ded6a4b453c2545c5b5aee0e` |

Both the Windows driver and the Linux helper enforce these pins. No production
profile, plan, terminal, source file, or historical result is changed.

## Actual operation and assertions

For each helper, Windows creates a project-owned scratch `state.json`, then opens
it with `CreateFileW(GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING)`. Sharing excludes
`FILE_SHARE_DELETE`. The owned WSL Python helper imports the exact source module,
writes a start handshake, and calls that module's real `write_json` function.
There is no replacement of `Path.replace` and no injected exception. A Python
trace observes only real OS exception events in the exact pinned `write_json`
function; it does not change that helper's logic or source bytes.

Windows releases its file handle two seconds after observing the native start
handshake. The original03 case must raise a real `PermissionError` with errno 13
and leave the original destination bytes unchanged. The new04 case must succeed,
write the exact expected value after at least one observed real
`PermissionError(errno=13)` within that same call, take at least 1.5 seconds in
its writer call, and leave no temporary files. Both native commands must exit zero and preserve their
source hashes. Otherwise the probe records FAIL; an unexpected filesystem result
must be investigated rather than relabelled a pass.

The driver records Windows and native UTC times, native platform and PID, the
exact invocation and source hashes, observed exception, writer duration, target
hashes, temporary files, stdout/stderr, per-case receipts, and an overall
`receipt.json` with artifact hashes. An old03 leftover temporary file is preserved
as evidence. No output or source file is deleted.

## Invocation controlled by the root agent

From the project directory, in PowerShell:

```powershell
python -B tools/diagnostics/humble54_drvfs_sharing_probe01/probe_drvfs_sharing.py --execute --distribution UAVHumble22 --old-source D:/WSL/UAVHumble22-validation/collect_humble54_pending03.py --new-source tools/experiment_orchestration/humble54_pending_collector04_source/collect_humble54_pending04.py --output 'D:/基于yolo和卡尔曼滤波/results/diagnostics/humble54_drvfs_sharing_actual01'
```

Preparation validation was limited to Python AST parsing and the default
`NOT_STARTED` mode. Those checks are not actual DrvFS execution evidence. Actual
status comes only from the newly generated receipts after explicit execution.
