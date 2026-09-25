from pathlib import Path
from zipfile import ZipFile

import pytest

from ore_music_player.infrastructure.update_service import (
    _version_key,
    is_newer_version,
    prepare_update,
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


def test_prepare_update_rejects_archive_without_executable(tmp_path: Path) -> None:
    archive_path = tmp_path / "update.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("ore-music-player/readme.txt", b"invalid")

    with pytest.raises(RuntimeError, match="does not contain"):
        prepare_update(archive_path, tmp_path / "staged")
