from __future__ import annotations

from pathlib import Path

import pytest

from ore_music_player.infrastructure.separation.stem_repository import StemRepository


@pytest.fixture
def repo() -> StemRepository:
    return StemRepository(":memory:")


def test_find_returns_none_for_unknown_track(repo: StemRepository) -> None:
    assert repo.find("no-such-id") is None


def test_save_and_find_stems(repo: StemRepository, tmp_path: Path) -> None:
    stems = {
        "vocals": tmp_path / "vocals.wav",
        "drums": tmp_path / "drums.wav",
    }
    for p in stems.values():
        p.touch()

    repo.save("track-1", stems)
    result = repo.find("track-1")

    assert result is not None
    assert result["vocals"] == stems["vocals"]
    assert result["drums"] == stems["drums"]


def test_save_overwrites_existing(repo: StemRepository, tmp_path: Path) -> None:
    old = {"vocals": tmp_path / "v1.wav"}
    new = {"vocals": tmp_path / "v2.wav"}
    for p in list(old.values()) + list(new.values()):
        p.touch()

    repo.save("track-1", old)
    repo.save("track-1", new)
    result = repo.find("track-1")

    assert result is not None
    assert result["vocals"] == new["vocals"]


def test_delete_removes_stems(repo: StemRepository, tmp_path: Path) -> None:
    stems = {"bass": tmp_path / "bass.wav"}
    stems["bass"].touch()
    repo.save("track-1", stems)
    repo.delete("track-1")
    assert repo.find("track-1") is None


def test_all_track_ids_with_stems(repo: StemRepository, tmp_path: Path) -> None:
    for tid in ("t1", "t2"):
        p = tmp_path / f"{tid}.wav"
        p.touch()
        repo.save(tid, {"vocals": p})

    ids = repo.all_track_ids_with_stems()
    assert set(ids) == {"t1", "t2"}
