import json
import urllib.error
import urllib.response
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from ore_music_player.infrastructure.update_service import (
    GITHUB_API_URL,
    _version_key,
    fetch_latest_release,
    is_newer_version,
    log_update_event,
    prepare_update,
    start_update_process,
    update_log_path,
)


def test_version_comparison_handles_release_tags() -> None:
    assert is_newer_version("v0.2.0", "0.1.0")
    assert not is_newer_version("v0.1.0", "0.1.0")
    assert _version_key("1.2") == (1, 2, 0)


def test_prepare_update_extracts_application_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "update.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("ore-music-player/ore-music-player.exe", b"exe")
        archive.writestr("ore-music-player/_internal/app.dll", b"dll")

    staged = prepare_update(archive_path, tmp_path / "staged")

    assert staged == tmp_path / "staged" / "ore-music-player"
    assert (staged / "ore-music-player.exe").read_bytes() == b"exe"


def test_fetch_latest_release_returns_none_when_no_releases_exist() -> None:
    error = urllib.error.HTTPError(GITHUB_API_URL, 404, "Not Found", {}, BytesIO())
    with patch("urllib.request.urlopen", side_effect=error):
        assert fetch_latest_release() is None


def test_prepare_update_rejects_archive_without_executable(tmp_path: Path) -> None:
    archive_path = tmp_path / "update.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("ore-music-player/readme.txt", b"invalid")

    with pytest.raises(RuntimeError, match="does not contain"):
        prepare_update(archive_path, tmp_path / "staged")


def test_log_update_event_writes_json_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    log_update_event("download_failed", archive=tmp_path / "update.zip")

    log_file = update_log_path()
    payload = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["event"] == "download_failed"
    assert payload["archive"] == str(tmp_path / "update.zip")


def test_start_update_process_passes_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("ore_music_player.infrastructure.update_service.sys.platform", "win32")

    with patch("ore_music_player.infrastructure.update_service.subprocess.Popen") as popen:
        start_update_process(
            tmp_path / "staged" / "ore-music-player",
            tmp_path / "ore-music-player",
            tmp_path / "apply_update.ps1",
        )

    command = popen.call_args.args[0]
    assert "-LogPath" in command
    assert str(update_log_path()) in command
