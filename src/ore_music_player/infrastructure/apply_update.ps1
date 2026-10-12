param(
    [Parameter(Mandatory = $true)]
    [string]$CurrentApplication,
    [Parameter(Mandatory = $true)]
    [string]$StagedApplication,
    [string]$LogPath = "",
    [switch]$SkipLaunch
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = $env:ORE_MUSIC_UPDATE_LOG
}
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    $LogPath = Join-Path $localAppData 'OreMusicPlayer\update.log'
}

function Write-UpdateLog {
    param([string]$Message)

    try {
        $logDirectory = Split-Path -Parent -Path $LogPath
        if ($logDirectory) {
            New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        }
        $timestamp = [DateTime]::UtcNow.ToString('o')
        Add-Content -LiteralPath $LogPath -Value "$timestamp $Message" -Encoding UTF8
    }
    catch {
    }
}

$current = [System.IO.Path]::GetFullPath($CurrentApplication)
$staged = [System.IO.Path]::GetFullPath($StagedApplication)
$backup = "$current.previous"
$backupName = [System.IO.Path]::GetFileName($backup)
$currentName = [System.IO.Path]::GetFileName($current)
$oldData = Join-Path $backup 'data'
$newData = Join-Path $current 'data'
$renamed = $false
$dataMoved = $false
Write-UpdateLog "update_started current='$current' staged='$staged'"

function Start-Application {
    param([string]$ApplicationDirectory)

    Start-Process -FilePath (Join-Path $ApplicationDirectory 'ore-music-player.exe') -WorkingDirectory $ApplicationDirectory
}

function Restore-PreviousApplication {
    try {
        if ($dataMoved -and (Test-Path -LiteralPath $newData)) {
            Move-Item -LiteralPath $newData -Destination $oldData
            Write-UpdateLog 'rollback_data_restored'
        }
        if (Test-Path -LiteralPath $current) {
            Remove-Item -LiteralPath $current -Recurse -Force
        }
        Rename-Item -LiteralPath $backup -NewName $currentName
        Write-UpdateLog 'rollback_completed'
        if (-not $SkipLaunch) {
            Start-Application $current
            Write-UpdateLog 'previous_application_started'
        }
    }
    catch {
        Write-UpdateLog "rollback_failed $(($_ | Out-String).Trim())"
    }
}

try {
    $parentPid = [int]$env:ORE_MUSIC_PLAYER_PARENT_PID
    if ($parentPid -le 0) {
        throw 'ORE_MUSIC_PLAYER_PARENT_PID is missing or invalid'
    }
    Write-UpdateLog "waiting_for_parent pid=$parentPid"
    while (Get-Process -Id $parentPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
    }
    Write-UpdateLog 'parent_exited'
    if (Test-Path -LiteralPath $backup) {
        Remove-Item -LiteralPath $backup -Recurse -Force
        Write-UpdateLog "removed_previous path='$backup'"
    }
    Rename-Item -LiteralPath $current -NewName $backupName
    $renamed = $true
    Write-UpdateLog "renamed_current backup='$backup'"
    Move-Item -LiteralPath $staged -Destination $current
    Write-UpdateLog "moved_staged current='$current'"
    if (Test-Path -LiteralPath $oldData) {
        if (Test-Path -LiteralPath $newData) {
            Remove-Item -LiteralPath $newData -Recurse -Force
        }
        Move-Item -LiteralPath $oldData -Destination $newData
        $dataMoved = $true
        Write-UpdateLog 'migrated_data'
    }
    if (-not $SkipLaunch) {
        Start-Application $current
    }
    Write-UpdateLog 'updated_application_started'
    try {
        Remove-Item -LiteralPath $backup -Recurse -Force
        Write-UpdateLog "removed_previous path='$backup'"
    }
    catch {
        Write-UpdateLog "remove_previous_failed $(($_ | Out-String).Trim())"
    }
}
catch {
    $details = ($_ | Out-String).Trim()
    Write-UpdateLog "update_failed $details"
    if ($renamed) {
        Restore-PreviousApplication
    }
    exit 1
}

