[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputDocx,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [switch]$ValidatePathsOnly
)

$ErrorActionPreference = 'Stop'
$documentInputPath = [System.IO.Path]::GetFullPath($InputDocx)
$documentOutputPath = [System.IO.Path]::GetFullPath($OutputPdf)
$documentSidecarPath = [System.IO.Path]::ChangeExtension($documentOutputPath, '.render.json')
if (-not (Test-Path -LiteralPath $documentInputPath -PathType Leaf)) { throw 'Input DOCX is missing.' }
if ([System.IO.Path]::GetExtension($documentInputPath).ToLowerInvariant() -ne '.docx' -or
    [System.IO.Path]::GetExtension($documentOutputPath).ToLowerInvariant() -ne '.pdf') { throw 'Expected DOCX input and PDF output.' }
if ((Test-Path -LiteralPath $documentOutputPath) -or (Test-Path -LiteralPath $documentSidecarPath)) { throw 'Preserve existing PDF and render sidecar; choose new filenames.' }
$documentInputHash = (Get-FileHash -LiteralPath $documentInputPath -Algorithm SHA256).Hash.ToLowerInvariant()
$converterScriptHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ValidatePathsOnly) {
    [pscustomobject]@{ status='PATHS_VALIDATED_NO_WORD_STARTED'; input=$documentInputPath; output=$documentOutputPath } | ConvertTo-Json -Compress
    return
}

# Only CoCreateInstance; never GetObject or attach to the user's running Word.
$priorWordProcessIds = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
if (-not ('UavWordProcessIdentity' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class UavWordProcessIdentity {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@
}
$wordApplication = $null
$ownedWordDocument = $null
$ownsWordInstance = $false
$wordProcessId = [uint32]0
$temporaryPdfPath = Join-Path ([System.IO.Path]::GetDirectoryName($documentOutputPath)) ('.uav-word-' + [guid]::NewGuid().ToString('N') + '.pdf')
try {
    $wordApplication = New-Object -ComObject Word.Application
    [void][UavWordProcessIdentity]::GetWindowThreadProcessId([IntPtr]$wordApplication.Hwnd, [ref]$wordProcessId)
    if ($wordProcessId -eq 0 -or $priorWordProcessIds -contains [int]$wordProcessId -or $wordApplication.Documents.Count -ne 0) {
        throw 'COM instance ownership is unproven; no existing Word instance will be modified or closed.'
    }
    $ownsWordInstance = $true
    $wordApplication.Visible = $false
    $wordApplication.DisplayAlerts = 0
    $wordApplication.AutomationSecurity = 3
    $wordVersion = $wordApplication.Version
    $wordExecutable = (Get-Process -Id ([int]$wordProcessId)).Path
    $wordProductVersion = (Get-Item -LiteralPath $wordExecutable).VersionInfo.ProductVersion
    $outputParent = [System.IO.Path]::GetDirectoryName($documentOutputPath)
    [void][System.IO.Directory]::CreateDirectory($outputParent)
    # ConfirmConversions=false, ReadOnly=true, AddToRecentFiles=false.
    $ownedWordDocument = $wordApplication.Documents.Open($documentInputPath, $false, $true, $false)
    if ([System.IO.Path]::GetFullPath($ownedWordDocument.FullName) -ne $documentInputPath -or $wordApplication.Documents.Count -ne 1) {
        throw 'Unexpected document set in the private instance.'
    }
    $ownedWordDocument.Repaginate()
    [void]$ownedWordDocument.Fields.Update()
    for ($tocIndex = 1; $tocIndex -le $ownedWordDocument.TablesOfContents.Count; $tocIndex++) {
        $documentToc = $ownedWordDocument.TablesOfContents.Item($tocIndex)
        try { [void]$documentToc.Update() }
        finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($documentToc) }
    }
    $ownedWordDocument.Repaginate()
    $pageCount = $ownedWordDocument.ComputeStatistics(2)
    if ($pageCount -lt 1) { throw 'Word reported no document pages.' }
    $ownedWordDocument.ExportAsFixedFormat($temporaryPdfPath, 17)
    if (-not (Test-Path -LiteralPath $temporaryPdfPath -PathType Leaf) -or (Get-Item -LiteralPath $temporaryPdfPath).Length -lt 100) {
        throw 'Word did not produce a nonempty PDF.'
    }
    if ((Get-FileHash -LiteralPath $documentInputPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $documentInputHash) {
        throw 'Original DOCX changed; PDF will remain an unpromoted temporary artifact.'
    }
    if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $converterScriptHash) {
        throw 'Converter source changed during rendering; preserve temporary output for diagnosis.'
    }
    if (Test-Path -LiteralPath $documentOutputPath) { throw 'PDF target appeared during rendering; preserve both files.' }
    Move-Item -LiteralPath $temporaryPdfPath -Destination $documentOutputPath
    $record = [ordered]@{
        schema_version=1; kind='PRIVATE_WORD_PDF_RENDER'; generated_utc=[DateTime]::UtcNow.ToString('o');
        input=[ordered]@{ path=$documentInputPath; sha256=$documentInputHash };
        converter=[ordered]@{ path=$PSCommandPath; sha256=$converterScriptHash };
        renderer=[ordered]@{ executable=$wordExecutable; version=$wordVersion; product_version=$wordProductVersion; process_id=$wordProcessId; private_instance_confirmed=$true };
        output=[ordered]@{ path=$documentOutputPath; sha256=(Get-FileHash -LiteralPath $documentOutputPath -Algorithm SHA256).Hash.ToLowerInvariant(); bytes=(Get-Item -LiteralPath $documentOutputPath).Length; word_pages=$pageCount };
        validation='PDF_GENERATED_PENDING_PER_PAGE_VISUAL_REVIEW'; source_saved=$false
    }
    $sidecarStream = [System.IO.File]::Open($documentSidecarPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    $sidecarWriter = New-Object System.IO.StreamWriter($sidecarStream, (New-Object System.Text.UTF8Encoding($false)))
    try { $sidecarWriter.WriteLine(($record | ConvertTo-Json -Depth 7)) }
    finally { $sidecarWriter.Dispose() }
    $record | ConvertTo-Json -Depth 7 -Compress
}
finally {
    try {
        if ($null -ne $ownedWordDocument) {
            try { $ownedWordDocument.Close(0) }
            finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($ownedWordDocument) }
        }
    }
    finally {
        if ($null -ne $wordApplication) {
            try { if ($ownsWordInstance) { $wordApplication.Quit(0) } }
            finally { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApplication) }
        }
    }
    # No Stop-Process, no close-all, no changes to pre-existing Word instances.
}
