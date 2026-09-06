param([string]$OutputDirectory = "release")

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir
$releaseDir = [IO.Path]::GetFullPath((Join-Path $projectDir $OutputDirectory))
if (-not $releaseDir.StartsWith($projectDir + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Build output must be inside the project directory"
}

# Package the checked-in image/audio/font files without regenerating or
# modifying them. Asset generators are explicit development tools.
python .\doors_ransom.py --self-test
if ($LASTEXITCODE -ne 0) { throw "Resource self-test failed" }
python .\doors_ransom.py --runtime-self-test
if ($LASTEXITCODE -ne 0) { throw "Source runtime self-test failed" }
python .\security_behavior_test.py
if ($LASTEXITCODE -ne 0) { throw "Security behavior regression test failed" }
python .\ransom_setting.py --self-test
if ($LASTEXITCODE -ne 0) { throw "Settings source self-test failed" }

python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath "$releaseDir" `
    --workpath "$projectDir\build" `
    "$projectDir\ransom.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$builtExe = Join-Path $releaseDir "ransom.exe"
foreach ($testArguments in @("--self-test", "--runtime-self-test")) {
    $testProcess = Start-Process -FilePath $builtExe -ArgumentList $testArguments -WindowStyle Hidden -PassThru
    if (-not $testProcess.WaitForExit(60000)) {
        Stop-Process -Id $testProcess.Id -Force -ErrorAction SilentlyContinue
        throw "Packaged runtime test timed out: $testArguments"
    }
    if ($testProcess.ExitCode -ne 0) {
        throw "Packaged runtime test failed: $testArguments"
    }
}

# Check the exact generated executable with the locally installed Defender
# engine.  This is a release gate, not an exclusion or a protection change.
$defenderRoot = Join-Path $env:ProgramData "Microsoft\Windows Defender\Platform"
$mpCmdRun = Get-ChildItem -LiteralPath $defenderRoot -Recurse -Filter "MpCmdRun.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1 -ExpandProperty FullName
if ($mpCmdRun) {
    & $mpCmdRun -Scan -ScanType 3 -File $builtExe
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $builtExe -PathType Leaf)) {
        throw "Microsoft Defender rejected the built ransom.exe; do not distribute this build"
    }
} else {
    Write-Warning "Microsoft Defender command-line scanner was not found; no local AV release check ran"
}
$builtSize = (Get-Item -LiteralPath $builtExe).Length
if ($builtSize -ge 20000000) {
    throw "Built EXE is not below 20 MB: $builtSize bytes"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath "$releaseDir" `
    --workpath "$projectDir\build" `
    "$projectDir\ransom_setting.spec"
if ($LASTEXITCODE -ne 0) { throw "Settings PyInstaller build failed" }
$settingsExe = Join-Path $releaseDir "ransom_setting.exe"
$settingsTest = Start-Process -FilePath $settingsExe -ArgumentList "--self-test" -WindowStyle Hidden -PassThru
if (-not $settingsTest.WaitForExit(60000)) {
    Stop-Process -Id $settingsTest.Id -Force -ErrorAction SilentlyContinue
    throw "Packaged settings self-test timed out"
}
if ($settingsTest.ExitCode -ne 0) { throw "Packaged settings self-test failed" }
$settingsSize = (Get-Item -LiteralPath $settingsExe).Length
if ($settingsSize -ge 20000000) { throw "Settings EXE exceeds 20 MB" }

# Retire old variants only after both new EXEs pass. Keep recoverable copies
# outside release so only the two current programs are distributed.
$releaseRoot = $releaseDir
$archiveRoot = [IO.Path]::GetFullPath((Join-Path $projectDir "legacy_releases"))
$archiveDir = Join-Path $archiveRoot (Get-Date -Format "yyyyMMdd-HHmmss-fff")
foreach ($variantName in @("ransom_midium.exe", "ransom_short.exe", "ransom_really_short.exe")) {
    $variantExe = [IO.Path]::GetFullPath((Join-Path $releaseRoot $variantName))
    $archiveTarget = [IO.Path]::GetFullPath((Join-Path $archiveDir $variantName))
    if ([IO.Path]::GetDirectoryName($variantExe) -ne $releaseRoot -or
        -not $archiveTarget.StartsWith($archiveRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe legacy archive path"
    }
    if (Test-Path -LiteralPath $variantExe -PathType Leaf) {
        New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
        Move-Item -LiteralPath $variantExe -Destination $archiveTarget
    }
}
Write-Host "Built and verified ransom.exe ($builtSize bytes) and ransom_setting.exe ($settingsSize bytes)"
