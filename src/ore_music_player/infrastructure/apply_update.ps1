param(
    [Parameter(Mandatory = $true)]
    [string]$CurrentApplication,
    [Parameter(Mandatory = $true)]
    [string]$StagedApplication,
    [switch]$SkipLaunch
)

$ErrorActionPreference = 'Stop'

$current = [System.IO.Path]::GetFullPath($CurrentApplication)
$staged = [System.IO.Path]::GetFullPath($StagedApplication)
$backup = "$current.previous"
$backupName = [System.IO.Path]::GetFileName($backup)
$currentName = [System.IO.Path]::GetFileName($current)
$oldData = Join-Path $backup 'data'
$newData = Join-Path $current 'data'
$renamed = $false
$dataMoved = $false
$logPath = Join-Path ([System.IO.Path]::GetTempPath()) 'ore-music-player-update.log'

function Write-UpdateLog {
    param([string]$Message)

    try {
        Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    }
    catch {
    }
}

function Start-Application {
    param([string]$ApplicationDirectory)

    Start-Process -FilePath (Join-Path $ApplicationDirectory 'ore-music-player.exe') -WorkingDirectory $ApplicationDirectory
}

function Restore-PreviousApplication {
    try {
        if ($dataMoved -and (Test-Path -LiteralPath $newData)) {
            Move-Item -LiteralPath $newData -Destination $oldData
        }
        if (Test-Path -LiteralPath $current) {
            Remove-Item -LiteralPath $current -Recurse -Force
        }
        Rename-Item -LiteralPath $backup -NewName $currentName
        if (-not $SkipLaunch) {
            Start-Application $current
        }
    }
    catch {
    }
}

try {
    Write-UpdateLog ("update started: current={0} staged={1}" -f $current, $staged)
    $parentPid = [int]$env:ORE_MUSIC_PLAYER_PARENT_PID
    if ($parentPid -le 0) {
        throw 'ORE_MUSIC_PLAYER_PARENT_PID is missing or invalid'
    }
    while (Get-Process -Id $parentPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
    }
    if (Test-Path -LiteralPath $backup) {
        Remove-Item -LiteralPath $backup -Recurse -Force
    }
    Rename-Item -LiteralPath $current -NewName $backupName
    $renamed = $true
    Move-Item -LiteralPath $staged -Destination $current
    if (Test-Path -LiteralPath $oldData) {
        if (Test-Path -LiteralPath $newData) {
            Remove-Item -LiteralPath $newData -Recurse -Force
        }
        Move-Item -LiteralPath $oldData -Destination $newData
        $dataMoved = $true
    }
    if (-not $SkipLaunch) {
        Start-Application $current
    }
    try {
        Remove-Item -LiteralPath $backup -Recurse -Force
    }
    catch {
    }
}
catch {
    Write-UpdateLog ("update failed: {0}" -f $_.Exception.Message)
    if ($renamed) {
        Write-UpdateLog 'restoring previous application'
        Restore-PreviousApplication
    }
    exit 1
}


