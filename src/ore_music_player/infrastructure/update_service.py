from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from ore_music_player.version import __version__

GITHUB_API_URL = "https://api.github.com/repos/yesmenjoker3104/ore-music-player/releases/latest"
RELEASE_ASSET_NAME = "ore-music-player-windows-x64.zip"
UPDATE_LOG_FILE_NAME = "update.log"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: str
    download_url: str


def update_log_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base_directory = Path(local_app_data) if local_app_data else Path(tempfile.gettempdir())
    return base_directory / "OreMusicPlayer" / UPDATE_LOG_FILE_NAME


def log_update_event(event: str, **fields: object) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "event": event,
        **fields,
    }
    path = update_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError:
        return


def _version_key(version: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
    if match is None:
        raise ValueError(f"Unsupported version: {version}")
    return tuple(int(part or 0) for part in match.groups())


def is_newer_version(version: str, current_version: str = __version__) -> bool:
    return _version_key(version) > _version_key(current_version)


def fetch_latest_release(timeout_seconds: float = 10.0) -> ReleaseInfo | None:
    log_update_event("check_started", current_version=__version__)
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "OreMusicPlayer-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            log_update_event("release_not_found", status_code=error.code)
            return None
        raise

    tag_name = str(release.get("tag_name", ""))
    if not tag_name or not is_newer_version(tag_name):
        log_update_event(
            "no_update",
            current_version=__version__,
            latest_tag=tag_name,
        )
        return None

    assets = release.get("assets", [])
    asset = next(
        (
            item
            for item in assets
            if item.get("name") == RELEASE_ASSET_NAME
            and isinstance(item.get("browser_download_url"), str)
        ),
        None,
    )
    if asset is None:
        raise RuntimeError(f"Release asset not found: {RELEASE_ASSET_NAME}")
    release_info = ReleaseInfo(tag_name.removeprefix("v"), asset["browser_download_url"])
    log_update_event(
        "release_found",
        version=release_info.version,
        download_url=release_info.download_url,
    )
    return release_info


def download_release(release: ReleaseInfo, destination: Path) -> Path:
    log_update_event(
        "download_started",
        version=release.version,
        download_url=release.download_url,
        destination=destination,
    )
    parsed_url = urlparse(release.download_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("Release download URL must use HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        release.download_url,
        headers={"User-Agent": "OreMusicPlayer-Updater"},
    )
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    log_update_event(
        "download_completed",
        version=release.version,
        destination=destination,
        size_bytes=destination.stat().st_size,
    )
    return destination


def _validate_archive(archive_path: Path) -> str:
    with zipfile.ZipFile(archive_path) as archive:
        files = [Path(name) for name in archive.namelist() if not name.endswith("/")]
    roots = {path.parts[0] for path in files if path.parts}
    if len(roots) != 1:
        raise RuntimeError("Update archive must contain one application directory")
    root = next(iter(roots))
    if Path(root) / "ore-music-player.exe" not in files:
        raise RuntimeError("Update archive does not contain ore-music-player.exe")
    for path in files:
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise RuntimeError("Update archive contains an unsafe path")
    return root


def prepare_update(archive_path: Path, staging_directory: Path) -> Path:
    log_update_event(
        "staging_started",
        archive_path=archive_path,
        staging_directory=staging_directory,
    )
    archive_root = _validate_archive(archive_path)
    if staging_directory.exists():
        shutil.rmtree(staging_directory)
    staging_directory.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(staging_directory)
    staged_application = staging_directory / archive_root
    log_update_event("staging_completed", staged_application=staged_application)
    return staged_application


def start_update_process(
    staged_application: Path,
    current_application: Path,
    update_script: Path,
) -> None:
    if sys.platform != "win32":
        raise RuntimeError("In-app updates are supported on Windows only")
    log_path = update_log_path()
    log_update_event(
        "apply_started",
        current_application=current_application,
        staged_application=staged_application,
        update_script=update_script,
        log_path=log_path,
    )
    environment = os.environ.copy()
    environment["ORE_MUSIC_PLAYER_PARENT_PID"] = str(os.getpid())
    environment["ORE_MUSIC_UPDATE_LOG"] = str(log_path)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(update_script),
            "-LogPath",
            str(log_path),
            "-CurrentApplication",
            str(current_application),
            "-StagedApplication",
            str(staged_application),
        ],
        env=environment,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    log_update_event("apply_process_started", log_path=log_path)


def update_script_path() -> Path:
    return Path(__file__).with_name("apply_update.ps1")


def make_update_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="ore-music-player-update-"))
