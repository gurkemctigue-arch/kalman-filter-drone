# Windows owner for the new complete development matrix

Root actually invoked this entry at 2026-11-03 04:47:46 UTC. Immutable early
monitor/native snapshots are in `actual_start01/`. The first new original slot
START is 04:47:53.727684 UTC. These are launch records only; completion, held-
handle exit verification, complete16 and formal admission remain separate.
The launcher source is fixed at
`8f6ceb38bc8ce7fb6aa6bec80f02b260b551082bde1d0a700ea1561a87ac79a1`.

`start_owner04.py` defaults to a pinned command description with
`status=NOT_STARTED`. Only the root agent's explicit invocation starts anything:

```powershell
python -B tools/experiment_orchestration/humble54_probe02_windows_owner04/start_owner04.py --execute
```

All collector, entry, plan, and generic monitor source SHA256 values are fixed
in the script. The command starts the unchanged generic Windows monitor in
`run` mode with task `humble54_probe02_full16_owner04`. Its owned WSL command
invokes the pinned collector04 from this project's tools directory, using the
new probe02 plan and `--after-slot __before_first__`. It performs collection only;
engineering FAIL or incomplete original verdicts remain unchanged.

The CLI plan path uses the frozen root's `/root/.../results/...` alias. The
collector resolves that path before recording it; its early/final plan binding
therefore checks the canonical `/mnt/d/.../results/frozen_fullplan_v4_humble54/...`
path (`CANONICAL_NATIVE_PLAN`), alongside the same fixed raw plan SHA256.

The Linux collector owner is `/root/uav_tracking_collection54_probe02_owner04`.
Its authoritative state/events/terminal live on Linux ext4. The generic monitor
reads those small files through `\\wsl.localhost\UAVHumble22\root\...`; it does
not read bags. Its output is `results/monitor_humble54_probe02_owner04`.

The outer Windows owner writes only to the new directory
`results/diagnostics/humble54_probe02_windows_owner04`. Both Windows output
directories and the native owner directory must be absent before execution.
There is no automatic retry or resume, and no historical owner is reused.

The outer owner holds a creation-bound Windows handle for the generic monitor,
then obtains the exact WSL child identity from that monitor's fresh state. It
checks the task ID, source paths, monitor creation identity, and WSL creation
identity before holding the WSL handle. `OpenProcess` uses synchronization and
limited-query access; `GetProcessTimes` checks the recorded creation token.
`WaitForSingleObject` and `GetExitCodeProcess` provide actual termination and
exit codes, and `Popen.wait` independently checks the monitor's exit code.
An early refusal before WSL-handle acquisition cannot produce verified closure.

A temporary `SetThreadExecutionState(0x80000003)` request holds system and display
awake on the outer owner's thread. Its receipt binds the current monitor PID
and creation token. The request remains until the monitored commands have
actually exited, then releases with `0x80000000`. It changes no global power
policy and does not override explicit user sleep or lid policy.

Output includes the source/command binding and identities in `started.json`, a
small rolling `state.json`, raw first/final monitor snapshots, a byte-for-byte
copy of the native terminal, raw monitor stdout/stderr, and `terminal.json`.
The terminal cross-checks native source/plan/entry pins, actual exit codes, and
the last owned child's recorded exit. All artifact digests are SHA256 of raw
bytes. The terminal does not contain its own digest; the caller computes it.
`closure_verified` certifies the checked invocation's closure, not engineering
acceptance, admission to formal experiments, or project completion.

Preparation validation used Python AST parsing and the inert default mode only.
No WSL, monitor, collector, power request, simulation, or recording was started
by the preparing agent.
