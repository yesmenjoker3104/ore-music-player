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
from pathlib import Path
from urllib.parse import urlparse

from ore_music_player.version import __version__

GITHUB_API_URL = "https://api.github.com/repos/yesmenjoker3104/ore-music-player/releases/latest"
RELEASE_ASSET_NAME = "ore-music-player-windows-x64.zip"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: str
    download_url: str


def _version_key(version: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
    if match is None:
        raise ValueError(f"Unsupported version: {version}")
    return tuple(int(part or 0) for part in match.groups())


def is_newer_version(version: str, current_version: str = __version__) -> bool:
    return _version_key(version) > _version_key(current_version)


def fetch_latest_release(timeout_seconds: float = 10.0) -> ReleaseInfo | None:
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
            return None
        raise

    tag_name = str(release.get("tag_name", ""))
    if not tag_name or not is_newer_version(tag_name):
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
    return ReleaseInfo(tag_name.removeprefix("v"), asset["browser_download_url"])


def download_release(release: ReleaseInfo, destination: Path) -> Path:
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
    archive_root = _validate_archive(archive_path)
    if staging_directory.exists():
        shutil.rmtree(staging_directory)
    staging_directory.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(staging_directory)
    return staging_directory / archive_root


def start_update_process(
    staged_application: Path,
    current_application: Path,
    update_script: Path,
) -> None:
    if sys.platform != "win32":
        raise RuntimeError("In-app updates are supported on Windows only")
    environment = os.environ.copy()
    environment["ORE_MUSIC_PLAYER_PARENT_PID"] = str(os.getpid())
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(update_script),
            "-CurrentApplication",
            str(current_application),
            "-StagedApplication",
            str(staged_application),
        ],
        env=environment,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def update_script_path() -> Path:
    return Path(__file__).with_name("apply_update.ps1")


def make_update_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="ore-music-player-update-"))
