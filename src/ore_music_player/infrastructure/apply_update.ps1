param(
    [Parameter(Mandatory = $true)]
    [string]$CurrentApplication,
    [Parameter(Mandatory = $true)]
    [string]$StagedApplication
)

$ErrorActionPreference = 'Stop'
$current = [System.IO.Path]::GetFullPath($CurrentApplication)
$staged = [System.IO.Path]::GetFullPath($StagedApplication)
$backup = "$current.previous"

try {
    while (Get-Process -Id ([int]$env:ORE_MUSIC_PLAYER_PARENT_PID) -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
    }
    if (Test-Path -LiteralPath $backup) {
        Remove-Item -LiteralPath $backup -Recurse -Force
    }
    Rename-Item -LiteralPath $current -NewName ([System.IO.Path]::GetFileName($backup))
    Move-Item -LiteralPath $staged -Destination $current
    $oldData = Join-Path $backup 'data'
    $newData = Join-Path $current 'data'
    if (Test-Path -LiteralPath $oldData) {
        if (Test-Path -LiteralPath $newData) {
            Remove-Item -LiteralPath $newData -Recurse -Force
        }
        Move-Item -LiteralPath $oldData -Destination $newData
    }
    Remove-Item -LiteralPath $backup -Recurse -Force
    Start-Process -FilePath (Join-Path $current 'ore-music-player.exe')
}
catch {
    if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $current)) {
        Rename-Item -LiteralPath $backup -NewName ([System.IO.Path]::GetFileName($current))
    }
    throw
}
