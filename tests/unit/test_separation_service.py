from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ore_music_player.application.separation_service import SeparationService
from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.separation.stem_repository import StemRepository


@pytest.fixture
def repo() -> StemRepository:
    return StemRepository(":memory:")


@pytest.fixture
def service(tmp_path: Path, repo: StemRepository) -> SeparationService:
    return SeparationService(
        stem_repository=repo,
        stems_dir=tmp_path / "stems",
        project_root=tmp_path,
    )


def _make_track(tmp_path: Path) -> Track:
    audio = tmp_path / "song.mp3"
    audio.touch()
    return Track(
        track_id="track-abc",
        path=str(audio),
        title="Test Song",
        duration_seconds=120.0,
    )


def test_has_stems_returns_false_when_no_record(service: SeparationService) -> None:
    assert service.has_stems("nonexistent") is False


def test_has_stems_returns_false_when_file_missing(
    service: SeparationService, tmp_path: Path, repo: StemRepository
) -> None:
    repo.save("track-1", {"vocals": tmp_path / "missing.wav"})
    assert service.has_stems("track-1") is False


def test_has_stems_returns_true_when_files_exist(
    service: SeparationService, tmp_path: Path, repo: StemRepository
) -> None:
    wav = tmp_path / "vocals.wav"
    wav.touch()
    repo.save("track-1", {"vocals": wav})
    assert service.has_stems("track-1") is True


def test_separate_saves_stems_and_returns_paths(
    service: SeparationService, tmp_path: Path
) -> None:
    track = _make_track(tmp_path)
    fake_stems = {
        "vocals": tmp_path / "stems" / track.track_id / "vocals.wav",
        "drums": tmp_path / "stems" / track.track_id / "drums.wav",
    }

    with patch(
        "ore_music_player.application.separation_service.separate",
        return_value=fake_stems,
    ):
        result = service.separate(track)

    assert result == fake_stems
    assert service.has_stems(track.track_id) is False  # files don't actually exist


def test_delete_stems_removes_record(
    service: SeparationService, tmp_path: Path, repo: StemRepository
) -> None:
    wav = tmp_path / "v.wav"
    wav.touch()
    repo.save("track-1", {"vocals": wav})
    service.delete_stems("track-1")
    assert repo.find("track-1") is None
    assert not wav.exists()
