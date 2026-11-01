param(
    [Parameter(Mandatory=$true)][string]$LeasePath,
    [Parameter(Mandatory=$true)][string]$StatusPath
)
$ErrorActionPreference = 'Stop'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class UavFollowDisplayPowerState01 {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
"@
$trackingAwakeFlags = [uint32]2147483651
$trackingAwakeEncoding = New-Object System.Text.UTF8Encoding($false)
$trackingAwakePrevious = [uint32]0
function Write-TrackingAwakeStatus([string]$State, [uint32]$ApiResult) {
    $trackingAwakeStatus = [ordered]@{
        schema_version = 1
        scope = 'TASK_SCOPED_SYSTEM_AND_DISPLAY_AWAKE_NO_GLOBAL_POWER_CHANGE'
        status = $State
        pid = $PID
        utc = [DateTimeOffset]::UtcNow.ToString('o')
        lease = $LeasePath
        release_signal = $StatusPath + '.release'
        requested_flags = $trackingAwakeFlags
        previous_execution_state = $ApiResult
        api_accepted = ($ApiResult -ne 0)
        claim_boundary = 'An accepted API request does not certify absence of sleep or override explicit sleep/lid policy.'
    }
    $trackingAwakeJson = $trackingAwakeStatus | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText($StatusPath + '.tmp', $trackingAwakeJson, $trackingAwakeEncoding)
    Move-Item -LiteralPath ($StatusPath + '.tmp') -Destination $StatusPath -Force
}
try {
    while (Test-Path -LiteralPath $LeasePath) {
        if (Test-Path -LiteralPath ($StatusPath + '.release')) { break }
        $trackingAwakeLease = Get-Content -LiteralPath $LeasePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($trackingAwakeLease.scope -ne 'TASK_SCOPED_SYSTEM_AND_DISPLAY_AWAKE_NO_GLOBAL_POWER_CHANGE') {
            throw 'Unexpected task-awake lease scope'
        }
        if ([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($trackingAwakeLease.expires_utc)) { break }
        $trackingAwakePrevious = [UavFollowDisplayPowerState01]::SetThreadExecutionState($trackingAwakeFlags)
        if ($trackingAwakePrevious -eq 0) { throw 'Windows refused the system/display-awake request' }
        Write-TrackingAwakeStatus 'ACTIVE' $trackingAwakePrevious
        Start-Sleep -Seconds 30
    }
} finally {
    $trackingAwakeReleased = [UavFollowDisplayPowerState01]::SetThreadExecutionState([uint32]2147483648)
    Write-TrackingAwakeStatus 'RELEASED' $trackingAwakeReleased
}
