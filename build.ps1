$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The project virtual environment is missing: .venv\Scripts\python.exe'
}

$mpvDirectory = Join-Path $projectRoot 'vendor\mpv'
$mpvDll = Get-ChildItem -LiteralPath $mpvDirectory -Filter '*.dll' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('libmpv-2.dll', 'mpv-2.dll', 'mpv-1.dll') } |
    Select-Object -First 1
if ($null -eq $mpvDll) {
    throw 'vendor\mpv must contain libmpv-2.dll, mpv-2.dll, or mpv-1.dll'
}

& $pythonPath -m pip install -e '.[build]'
& $pythonPath -m PyInstaller --noconfirm --clean ore_music_player.spec

$archivePath = Join-Path $projectRoot 'dist\ore-music-player-windows-x64.zip'
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
Compress-Archive -Path 'dist\ore-music-player' -DestinationPath $archivePath
Write-Host ('Created {0}' -f $archivePath)