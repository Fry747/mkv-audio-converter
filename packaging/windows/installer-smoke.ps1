$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $projectRoot
try {
    $appVersion = (& python -c 'from mkv_audio_converter import __version__; print(__version__)').Trim()
    $installer = Join-Path $projectRoot "dist\windows\MKVAudioConverter-$appVersion-windows-x64-setup.exe"
    $installDir = Join-Path $env:RUNNER_TEMP 'MKV installer smoke test'
    $installLog = Join-Path $projectRoot 'windows-installer.log'
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`"", "/LOG=`"$installLog`"")
    $setupProcess = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($setupProcess.ExitCode -ne 0) { throw "Installer failed: $($setupProcess.ExitCode)" }
    & (Join-Path $installDir 'MKVAudioConverter-cli.exe') --check
    if ($LASTEXITCODE -ne 0) { throw 'Installed app failed tool check' }
    $sentinel = Join-Path $installDir 'user-media-do-not-delete.mkv'
    [IO.File]::WriteAllText($sentinel, 'user media must survive uninstall')
    $config = Join-Path $env:LOCALAPPDATA 'MKVAudioConverter\tools.json'
    $previousConfig = (Get-FileHash $config -Algorithm SHA256).Hash
    $uninstall = Start-Process -FilePath (Join-Path $installDir 'unins000.exe') -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw 'Uninstaller failed' }
    if (-not (Test-Path $sentinel)) { throw 'Uninstaller removed user media' }
    if ((Get-FileHash $config -Algorithm SHA256).Hash -ne $previousConfig) { throw 'Uninstaller changed tool configuration' }
    Write-Host 'Installer, installed CLI and non-destructive uninstall OK'
} finally { Pop-Location }
