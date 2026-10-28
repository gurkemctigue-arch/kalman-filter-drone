<#
Prepare an authenticated-by-HTTPS, SHA256-checked Canonical Jammy WSL image.
Default Prepare downloads only. Import is a separate, explicit action and never
stops, unregisters, exports, or changes any existing distribution.
#>
[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Import')]
    [string]$Action = 'Prepare',
    [string]$CacheDirectory = 'D:\WSL\Downloads\Jammy'
)
$ErrorActionPreference = 'Stop'
$distroName = 'UAVHumble22'
$installDirectory = 'D:\WSL\UAVHumble22'
$imageName = 'ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz'
$baseUrl = 'https://cloud-images.ubuntu.com/wsl/jammy/current'
$pinnedSha256 = '1483cc5c1dce13064f774834cbffdff226559fd522a67a381a8ea77d63fb4109'
$pinnedBytes = 341130963

$cachePath = [IO.Path]::GetFullPath($CacheDirectory)
if (-not $cachePath.StartsWith('D:\WSL\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'CacheDirectory must be inside D:\WSL; no system-drive downloads are allowed.'
}
if ([Environment]::Is64BitOperatingSystem -eq $false -or
    $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'This pinned image is for an x86_64/AMD64 WSL host.'
}
$null = Get-Command curl.exe -ErrorAction Stop
$null = New-Item -ItemType Directory -Path $cachePath -Force
$checksumsPath = Join-Path $cachePath 'SHA256SUMS'
$signaturePath = Join-Path $cachePath 'SHA256SUMS.gpg'
$imagePath = Join-Path $cachePath $imageName

function Get-OfficialFile([string]$Url, [string]$Destination) {
    & curl.exe --fail --location --silent --show-error --retry 4 --connect-timeout 30 --output $Destination $Url
    if ($LASTEXITCODE -ne 0) { throw "Official download failed: $Url" }
}
Get-OfficialFile "$baseUrl/SHA256SUMS" $checksumsPath
Get-OfficialFile "$baseUrl/SHA256SUMS.gpg" $signaturePath
$checksumLine = Get-Content -LiteralPath $checksumsPath |
    Where-Object { $_ -match ('^[a-fA-F0-9]{64}\s+\*?' + [regex]::Escape($imageName) + '$') }
if (@($checksumLine).Count -ne 1) { throw 'Canonical checksum file does not identify exactly one amd64 image.' }
$officialSha256 = ($checksumLine -split '\s+')[0].ToLowerInvariant()
if ($officialSha256 -ne $pinnedSha256) {
    throw 'Canonical current image changed. Review and update the pinned image/hash before downloading/importing.'
}
if (-not (Test-Path -LiteralPath $imagePath)) {
    $partialPath = "$imagePath.partial"
    Write-Host "Downloading Canonical Jammy image: $pinnedBytes bytes (325.3 MiB)."
    & curl.exe --fail --location --silent --show-error --retry 4 --connect-timeout 30 --continue-at - --output $partialPath "$baseUrl/$imageName"
    if ($LASTEXITCODE -ne 0) { throw 'Rootfs download failed; its partial file is retained for a resumable retry.' }
    $partialHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($partialHash -ne $pinnedSha256) { throw 'Partial image SHA256 mismatch; it was not imported.' }
    Move-Item -LiteralPath $partialPath -Destination $imagePath
}
$actualHash = (Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $imagePath).Length
if ($actualHash -ne $pinnedSha256 -or $actualBytes -ne $pinnedBytes) {
    throw 'Cached image SHA256/size mismatch; it was not imported.'
}
$record = [ordered]@{
    schema_version = 1
    checked_at_utc = [DateTime]::UtcNow.ToString('o')
    canonical_url = "$baseUrl/$imageName"
    canonical_checksums_url = "$baseUrl/SHA256SUMS"
    sha256 = $actualHash
    bytes = $actualBytes
    sha256_matches_official_https_file = $true
    gpg_signature_downloaded = $true
    gpg_signature_verified = $false
    image_path = $imagePath
    planned_distribution = $distroName
    planned_install_directory = $installDirectory
    action = $Action
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cachePath 'verified-image.json') -Encoding UTF8
Write-Host "Verified: $imagePath"
Write-Host "SHA256: $actualHash"
if ($Action -eq 'Prepare') {
    Write-Host 'Preparation complete. No WSL distribution was imported or modified.'
    return
}

$null = Get-Command wsl.exe -ErrorAction Stop
$distros = @(& wsl.exe --list --quiet) -replace "`0", ''
if ($LASTEXITCODE -ne 0) { throw 'Cannot list WSL distributions.' }
if (@($distros | ForEach-Object { $_.Trim() }) -contains $distroName) {
    throw 'UAVHumble22 already exists; refusing to replace or modify it. Inspect its state first.'
}
if (Test-Path -LiteralPath $installDirectory) {
    throw 'D:\WSL\UAVHumble22 already exists; refusing to reuse/overwrite its contents.'
}
$resolvedInstall = [IO.Path]::GetFullPath($installDirectory)
if ($resolvedInstall -ne 'D:\WSL\UAVHumble22') { throw 'Unexpected WSL install target.' }
& wsl.exe --import $distroName $resolvedInstall $imagePath --version 2
if ($LASTEXITCODE -ne 0) { throw 'WSL import failed; no other distribution was changed.' }
& wsl.exe --distribution $distroName --user root --exec cat /etc/os-release
if ($LASTEXITCODE -ne 0) { throw 'Imported distribution could not report its OS.' }
Write-Host 'Import complete. Package installation/build/simulation are separate steps.'
exit 0
