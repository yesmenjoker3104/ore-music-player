param(
    [string]$ExePath = (Join-Path $PSScriptRoot 'dist\ore-music-player\ore-music-player.exe'),
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

$progId = 'OreMusicPlayer.AudioFile'
$extensions = @('.mp3', '.wav', '.flac', '.m4a', '.ogg')
$classesRoot = 'HKCU:\Software\Classes'
$progIdPath = Join-Path $classesRoot $progId

if ($Unregister) {
    foreach ($extension in $extensions) {
        $openWithPath = Join-Path (Join-Path $classesRoot $extension) 'OpenWithProgids'
        if (Test-Path -LiteralPath $openWithPath) {
            Remove-ItemProperty -LiteralPath $openWithPath -Name $progId -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $progIdPath) {
        Remove-Item -LiteralPath $progIdPath -Recurse -Force
    }
    Write-Host 'Removed Ore Music Player file association.'
    return
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Executable not found: $ExePath. Run build.ps1 first or pass -ExePath."
}
$resolvedExePath = (Resolve-Path -LiteralPath $ExePath).Path

New-Item -Path (Join-Path $progIdPath 'shell\open\command') -Force | Out-Null
Set-Item -LiteralPath $progIdPath -Value 'Ore Music Player audio file'
Set-Item -LiteralPath (Join-Path $progIdPath 'shell\open\command') -Value ('"{0}" "%1"' -f $resolvedExePath)
New-Item -Path (Join-Path $progIdPath 'DefaultIcon') -Force | Out-Null
Set-Item -LiteralPath (Join-Path $progIdPath 'DefaultIcon') -Value ('"{0}",0' -f $resolvedExePath)

foreach ($extension in $extensions) {
    $extensionPath = Join-Path $classesRoot $extension
    $openWithPath = Join-Path $extensionPath 'OpenWithProgids'
    New-Item -Path $openWithPath -Force | Out-Null
    try {
        New-ItemProperty -LiteralPath $openWithPath -Name $progId -PropertyType None -Value ([byte[]]@()) -Force | Out-Null
    }
    catch {
        New-ItemProperty -LiteralPath $openWithPath -Name $progId -PropertyType String -Value '' -Force | Out-Null
    }
}

Write-Host "Registered Ore Music Player for: $($extensions -join ', ')"
Write-Host "Command: $resolvedExePath"
Write-Host 'To make it the default, choose Ore Music Player in Windows Settings > Apps > Default apps.'
