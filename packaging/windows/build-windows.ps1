[CmdletBinding()]
param([switch]$SkipInstaller, [string]$CertificateThumbprint)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot
try {
    if (-not [Environment]::Is64BitProcess) { throw 'Python/PowerShell x64 wird benötigt.' }
    & python -c "import sys; assert sys.platform == 'win32' and sys.version_info[:3] == (3, 13, 17), 'Build benötigt Python 3.13.17 x64'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13.17 x64 fehlt.' }
    if (-not (Test-Path '.venv-build\Scripts\python.exe')) {
        & python -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Build-Umgebung konnte nicht angelegt werden.' }
    }
    $buildPython = Join-Path $projectRoot '.venv-build\Scripts\python.exe'
    & $buildPython -m pip install -r packaging/windows/requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installation der Build-Abhängigkeiten fehlgeschlagen.' }
    & $buildPython packaging/windows/package.py prepare
    if ($LASTEXITCODE -ne 0) { throw 'Build-Vorbereitung fehlgeschlagen.' }
    & $buildPython -m PyInstaller --clean --noconfirm packaging/windows/MKVAudioConverter.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller-Build fehlgeschlagen.' }
    if ($CertificateThumbprint) {
        foreach ($file in @('dist\MKVAudioConverter\MKVAudioConverter.exe', 'dist\MKVAudioConverter\MKVAudioConverter-cli.exe')) {
            & signtool.exe sign /sha1 $CertificateThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $file
            if ($LASTEXITCODE -ne 0) { throw 'Signieren der EXE fehlgeschlagen.' }
        }
    }
    & $buildPython packaging/windows/package.py collect
    if ($LASTEXITCODE -ne 0) { throw 'Paketierung fehlgeschlagen.' }
    $appVersion = (& $buildPython -c 'from mkv_audio_converter import __version__; print(__version__)').Trim()
    if (-not $SkipInstaller) {
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        $compilerPath = if ($compiler) { $compiler.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
        if (-not (Test-Path $compilerPath)) { throw 'Inno Setup 6 fehlt. Offiziell installieren oder -SkipInstaller verwenden.' }
        & $compilerPath "/DAppVersion=$appVersion" "/DSourceRoot=$projectRoot" packaging/windows/installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer-Build fehlgeschlagen.' }
    }
    if ($CertificateThumbprint -and -not $SkipInstaller) {
        & signtool.exe sign /sha1 $CertificateThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 "dist\windows\MKVAudioConverter-$appVersion-windows-x64-setup.exe"
        if ($LASTEXITCODE -ne 0) { throw 'Signieren des Installers fehlgeschlagen.' }
    }
    & $buildPython packaging/windows/package.py checksums
    if ($LASTEXITCODE -ne 0) { throw 'Prüfsummen konnten nicht geschrieben werden.' }
    Write-Host 'Fertige Pakete: dist\windows'
} finally { Pop-Location }
