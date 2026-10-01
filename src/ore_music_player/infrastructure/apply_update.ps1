param(
    [Parameter(Mandatory = $true)]
    [string]$CurrentApplication,
    [Parameter(Mandatory = $true)]
    [string]$StagedApplication,
    [string]$LogPath = ""
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
Write-UpdateLog "update_started current='$current' staged='$staged'"

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
    Rename-Item -LiteralPath $current -NewName ([System.IO.Path]::GetFileName($backup))
    Write-UpdateLog "renamed_current backup='$backup'"
    Move-Item -LiteralPath $staged -Destination $current
    Write-UpdateLog "moved_staged current='$current'"
    $oldData = Join-Path $backup 'data'
    $newData = Join-Path $current 'data'
    if (Test-Path -LiteralPath $oldData) {
        if (Test-Path -LiteralPath $newData) {
            Remove-Item -LiteralPath $newData -Recurse -Force
        }
        Move-Item -LiteralPath $oldData -Destination $newData
        Write-UpdateLog 'migrated_data'
    }
    Remove-Item -LiteralPath $backup -Recurse -Force
    Write-UpdateLog "removed_previous path='$backup'"
    Start-Process -FilePath (Join-Path $current 'ore-music-player.exe')
    Write-UpdateLog 'updated_application_started'
}
catch {
    $details = ($_ | Out-String).Trim()
    Write-UpdateLog "update_failed $details"
    if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $current)) {
        try {
            Rename-Item -LiteralPath $backup -NewName ([System.IO.Path]::GetFileName($current))
            Write-UpdateLog 'rollback_completed'
        }
        catch {
            Write-UpdateLog "rollback_failed $(($_ | Out-String).Trim())"
        }
    }
    throw
}
