param(
    [ValidatePattern('^/root/uav_tracking_fullplan_[A-Za-z0-9_]+$')]
    [string]$LinuxRoot = '/root/uav_tracking_fullplan_v2',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$')]
    [string]$Prefix = 'fullplan_v2',
    [ValidatePattern('^full_plan_research_[A-Za-z0-9_]+$')]
    [string]$StudyName = 'full_plan_research_v2',
    [ValidateSet('plan', 'flights', 'offline', 'summarize', 'all')]
    [string]$Phase = 'all',
    [ValidateRange(0, 10000)]
    [int]$StopAfter = 0,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
# Scoped to this process/thread: keep the computer available for a long
# experiment while allowing the display to turn off. No power-plan edits.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class TrackingExperimentAwake {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@

$trackingArguments = @('-e', 'bash', "$LinuxRoot/scripts/run_research_session.sh",
    'scripts/run_full_plan_research.py', '--phase', $Phase, '--prefix', $Prefix,
    '--output', "$LinuxRoot/results/$StudyName")
if ($Resume) { $trackingArguments += '--resume' }
if ($StopAfter -gt 0) { $trackingArguments += @('--stop-after', [string]$StopAfter) }
$trackingPreviousState = [TrackingExperimentAwake]::SetThreadExecutionState([uint32]2147483649)
if ($trackingPreviousState -eq 0) { throw 'Could not keep the experiment computer awake.' }
try {
    & wsl @trackingArguments
    $trackingExitCode = $LASTEXITCODE
}
finally {
    [void][TrackingExperimentAwake]::SetThreadExecutionState([uint32]2147483648)
}
exit $trackingExitCode
