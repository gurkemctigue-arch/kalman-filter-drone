param(
    [ValidatePattern('^v[0-9]+$')]
    [string]$AuditSuffix = 'v7',
    [ValidateRange(0,166)]
    [int]$MaxNewFlights = 0,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$trackingRoot = Split-Path -Parent $PSScriptRoot
$trackingLinuxRoot = '/mnt/' + $trackingRoot.Substring(0,1).ToLowerInvariant() + '/' + $trackingRoot.Substring(3).Replace('\','/')
$trackingAudit = Join-Path $trackingRoot "results/fullplan_v3_guarded_continuation_$AuditSuffix"
if ($Execute -and (Test-Path -LiteralPath $trackingAudit)) {
    throw "Preserve existing audit; choose an unused suffix: $trackingAudit"
}
$trackingArguments = @('-e','bash',
    '/root/uav_tracking_fullplan_v3/scripts/run_research_session.sh',
    "$trackingLinuxRoot/scripts/run_guarded_full_plan.py",
    '--frozen-root','/root/uav_tracking_fullplan_v3',
    '--study-output','results/full_plan_research_v3',
    '--expected-plan-sha','58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28')
if ($Execute) {
    $trackingArguments += @('--audit-output',
        "$trackingLinuxRoot/results/fullplan_v3_guarded_continuation_$AuditSuffix",
        '--max-new-flights',[string]$MaxNewFlights,'--execute')
}
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class TrackingGuardAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
if ([TrackingGuardAwake]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
    throw 'Could not keep the experiment computer awake.'
}
try {
    & wsl.exe @trackingArguments
    $trackingExitCode = $LASTEXITCODE
} finally {
    [void][TrackingGuardAwake]::SetThreadExecutionState([uint32]2147483648)
}
exit $trackingExitCode
