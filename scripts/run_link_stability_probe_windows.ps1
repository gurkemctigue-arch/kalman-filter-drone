param([string]$AuditSuffix = 'v2',
      [ValidateSet('stage2_crossing','stage3_midpoint','stage3_midpoint_seed001')][string]$Profile = 'stage2_crossing')
$ErrorActionPreference = 'Stop'
if ($AuditSuffix -notmatch '^v[0-9]+$') { throw 'Use a distinct vN audit suffix' }
$trackingRoot = Split-Path -Parent $PSScriptRoot
$trackingLinuxRoot = '/mnt/' + $trackingRoot.Substring(0,1).ToLowerInvariant() + '/' + $trackingRoot.Substring(3).Replace('\','/')
$trackingHostLog = Join-Path $trackingRoot "results/host_link_stability_probe_20261027_$AuditSuffix.jsonl"
$trackingStdout = Join-Path $trackingRoot "results/link_stability_probe_driver_20261027_$AuditSuffix.stdout.log"
$trackingStderr = Join-Path $trackingRoot "results/link_stability_probe_driver_20261027_$AuditSuffix.stderr.log"
foreach ($trackingPath in @($trackingHostLog,$trackingStdout,$trackingStderr)) {
    if (Test-Path -LiteralPath $trackingPath) { throw "Preserve existing probe: $trackingPath" }
}
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class TrackingProbeAwake {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint state);
}
'@
$trackingWriter = [System.IO.StreamWriter]::new($trackingHostLog, $false, [System.Text.UTF8Encoding]::new($false))
try {
    [void][TrackingProbeAwake]::SetThreadExecutionState(2147483649)
    $trackingArgs = @('-e','bash','/root/uav_tracking_fullplan_v3/scripts/run_research_session.sh',
        "$trackingLinuxRoot/scripts/run_link_stability_probe.py",'--profile',$Profile,'--execute')
    $trackingProcess = Start-Process -FilePath 'wsl.exe' -ArgumentList $trackingArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $trackingStdout -RedirectStandardError $trackingStderr
    $trackingProcessHandle = $trackingProcess.Handle
    do {
        $trackingMemory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
        $trackingRow = [ordered]@{utc=[DateTime]::UtcNow.ToString('o');
            available_mib=$trackingMemory.AvailableMBytes; committed_bytes=$trackingMemory.CommittedBytes;
            commit_limit_bytes=$trackingMemory.CommitLimit; pages_input_per_s=$trackingMemory.PagesInputPersec;
            page_reads_per_s=$trackingMemory.PageReadsPersec;
            diagnostic_only=$true; interval_target_s=5}
        $trackingWriter.WriteLine(($trackingRow | ConvertTo-Json -Compress))
        $trackingWriter.Flush()
        if (-not $trackingProcess.HasExited) { Start-Sleep -Seconds 5 }
        $trackingProcess.Refresh()
    } while (-not $trackingProcess.HasExited)
    $trackingProcess.WaitForExit()
    if ($null -eq $trackingProcess.ExitCode) { throw 'WSL exit code unavailable; inspect diagnostic logs' }
    Write-Output "Independent probe exited $($trackingProcess.ExitCode); host log: $trackingHostLog"
    exit $trackingProcess.ExitCode
} finally {
    $trackingWriter.Dispose()
    [void][TrackingProbeAwake]::SetThreadExecutionState(2147483648)
}
