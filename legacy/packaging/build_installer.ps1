# Build ACB_Tool_Setup.exe from core/version.py single-source-of-truth version.
# Run after PyInstaller onedir produces packaging\dist\ACB Tool\.
#
# Output: packaging\dist\ACB_Tool_Setup.exe

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$versionFile = Join-Path $root 'core\version.py'
$iss         = Join-Path $PSScriptRoot 'installer.iss'
$distFolder  = Join-Path $PSScriptRoot 'dist\ACB Tool'

$m = Select-String -Path $versionFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $m) { throw "Could not extract __version__ from $versionFile" }
$version = $m.Matches[0].Groups[1].Value
Write-Host "ACB Tool installer build -- version $version"

$ma = Select-String -Path $versionFile -Pattern '__author__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $ma) { throw "Could not extract __author__ from $versionFile" }
$publisher = $ma.Matches[0].Groups[1].Value
Write-Host "Publisher: $publisher"

if (-not (Test-Path $distFolder)) {
    throw "PyInstaller bundle missing: $distFolder. Run the onedir build first."
}

$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { $iscc = 'C:\Program Files\Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found." }

& $iscc "/DAcbVersion=$version" "/DAcbPublisher=$publisher" $iss
if ($LASTEXITCODE -ne 0) { throw "ISCC exit code $LASTEXITCODE" }

$out = Join-Path $PSScriptRoot 'dist\ACB_Tool_Setup.exe'
if (-not (Test-Path $out)) { throw "Installer not produced at $out" }
$mb = [math]::Round(((Get-Item $out).Length / 1MB), 2)
Write-Host "Installer: $out"
Write-Host "Size: $mb MB"

