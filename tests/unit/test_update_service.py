import json
import os
import subprocess
import sys
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
    update_script_path,
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


def test_start_update_process_runs_outside_application_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("ore_music_player.infrastructure.update_service.sys.platform", "win32")
    current_application = tmp_path / "ore-music-player"

    with patch("ore_music_player.infrastructure.update_service.subprocess.Popen") as popen:
        start_update_process(
            tmp_path / "staged" / "ore-music-player",
            current_application,
            tmp_path / "apply_update.ps1",
        )

    working_directory = Path(popen.call_args.kwargs["cwd"])
    assert current_application not in (working_directory, *working_directory.parents)


def _exited_process_id() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _run_apply_script(
    current_application: Path,
    staged_application: Path,
    log_path: Path,
    working_directory: Path,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["ORE_MUSIC_PLAYER_PARENT_PID"] = str(_exited_process_id())
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(update_script_path()),
            "-LogPath",
            str(log_path),
            "-CurrentApplication",
            str(current_application),
            "-StagedApplication",
            str(staged_application),
            "-SkipLaunch",
        ],
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="The update script runs on Windows only")
def test_apply_update_script_replaces_application(tmp_path: Path) -> None:
    current_application = tmp_path / "ore-music-player"
    (current_application / "data").mkdir(parents=True)
    (current_application / "ore-music-player.exe").write_bytes(b"old")
    (current_application / "data" / "settings.ini").write_text("kept", encoding="utf-8")
    staged_application = tmp_path / "staged" / "ore-music-player"
    staged_application.mkdir(parents=True)
    (staged_application / "ore-music-player.exe").write_bytes(b"new")

    result = _run_apply_script(
        current_application,
        staged_application,
        tmp_path / "update.log",
        working_directory=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert (current_application / "ore-music-player.exe").read_bytes() == b"new"
    assert (current_application / "data" / "settings.ini").read_text(encoding="utf-8") == "kept"
    assert not staged_application.exists()
    assert not (tmp_path / "ore-music-player.previous").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="The update script runs on Windows only")
def test_apply_update_script_restores_previous_application_on_failure(tmp_path: Path) -> None:
    current_application = tmp_path / "ore-music-player"
    current_application.mkdir()
    (current_application / "ore-music-player.exe").write_bytes(b"old")
    log_path = tmp_path / "update.log"

    result = _run_apply_script(
        current_application,
        tmp_path / "missing" / "ore-music-player",
        log_path,
        working_directory=tmp_path,
    )

    assert result.returncode == 1
    assert (current_application / "ore-music-player.exe").read_bytes() == b"old"
    assert not (tmp_path / "ore-music-player.previous").exists()
    assert "rollback_completed" in log_path.read_text(encoding="utf-8")
