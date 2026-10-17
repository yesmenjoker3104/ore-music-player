from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.audio import stem_playback_backend as backend_module
from ore_music_player.infrastructure.audio import stretched_stems as stretched_module
from ore_music_player.infrastructure.audio.stem_playback_backend import (
    StemPlaybackBackend,
)

SR = backend_module.SAMPLE_RATE
TRACK_SECONDS = 10


class FakeRepo:
    def find(self, track_id: str) -> dict[str, Path]:
        return {"vocals": Path("vocals.wav"), "drums": Path("drums.wav")}


def _track(track_id: str = "t1") -> Track:
    return Track(track_id=track_id, path=f"{track_id}.mp3", title=track_id)


def _fake_stems(paths: dict[str, Path]) -> dict[str, np.ndarray]:
    n = SR * TRACK_SECONDS
    return {name: np.zeros((n, 2), dtype=np.float32) for name in paths}


def _fake_time_stretch(audio: np.ndarray, rate: float) -> np.ndarray:
    out_len = round(len(audio) / rate)
    idx = np.linspace(0, len(audio) - 1, out_len).astype(int)
    return audio[idx]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> StemPlaybackBackend:
    monkeypatch.setattr(backend_module, "load_stems", _fake_stems)
    monkeypatch.setattr(backend_module, "_time_stretch", _fake_time_stretch)
    return StemPlaybackBackend(FakeRepo())


def _wait_for_speed(backend: StemPlaybackBackend, speed: float) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if backend._applied_speed == speed:
            return
        time.sleep(0.01)
    raise AssertionError(f"speed {speed} was not applied")


def test_current_track_is_set_on_load(backend: StemPlaybackBackend):
    track = _track()
    assert backend.current_track is None

    backend.load(track)

    assert backend.current_track == track


def test_seek_keeps_loaded_track(backend: StemPlaybackBackend):
    backend.load(_track())

    backend.seek(4.0)

    assert backend.current_track is not None
    assert backend.position_seconds == pytest.approx(4.0, abs=1e-3)


def test_stem_volume_survives_reload(backend: StemPlaybackBackend):
    backend.load(_track("a"))
    backend.set_stem_volume("vocals", 0.3)

    backend.load(_track("b"))

    assert backend.stem_volumes["vocals"] == pytest.approx(0.3)
    assert backend.stem_volumes["drums"] == pytest.approx(1.0)


def test_master_volume_survives_reload(backend: StemPlaybackBackend):
    backend.set_volume(40)
    backend.load(_track())

    assert backend._mixer is not None
    assert backend._mixer._master_volume == pytest.approx(0.4)


def test_speed_change_keeps_position_in_original_time(backend: StemPlaybackBackend):
    backend.load(_track())
    backend.seek(4.0)

    backend.set_speed(2.0)
    _wait_for_speed(backend, 2.0)

    assert backend.position_seconds == pytest.approx(4.0, abs=1e-3)
    assert backend.duration_seconds == pytest.approx(TRACK_SECONDS, abs=1e-3)


def test_seek_after_speed_change_uses_original_time(backend: StemPlaybackBackend):
    backend.load(_track())
    backend.set_speed(0.5)
    _wait_for_speed(backend, 0.5)

    backend.seek(6.0)

    assert backend.position_seconds == pytest.approx(6.0, abs=1e-3)
    assert backend._mixer is not None
    assert backend._mixer.position_seconds == pytest.approx(12.0, abs=1e-3)


def test_loop_points_follow_speed(backend: StemPlaybackBackend):
    backend.load(_track())
    backend.set_speed(2.0)
    _wait_for_speed(backend, 2.0)

    backend.set_loop(2.0, 6.0)

    assert backend._mixer is not None
    assert backend._mixer.a_point == SR
    assert backend._mixer.b_point == int(6.0 / 2.0 * SR)
    assert backend._mixer.loop_enabled is True


def test_speed_returns_to_original_stems(backend: StemPlaybackBackend):
    backend.load(_track())
    backend.set_speed(1.5)
    _wait_for_speed(backend, 1.5)

    backend.set_speed(1.0)

    assert backend._applied_speed == 1.0
    assert backend._mixer is not None
    assert backend._mixer.length == SR * TRACK_SECONDS


def test_speed_is_applied_after_load_when_already_set(backend: StemPlaybackBackend):
    backend.set_speed(1.25)
    backend.load(_track())

    _wait_for_speed(backend, 1.25)

    assert backend.duration_seconds == pytest.approx(TRACK_SECONDS, abs=1e-3)


def test_speed_applies_before_all_chunks_are_stretched(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(backend_module, "load_stems", _fake_stems)
    monkeypatch.setattr(backend_module, "_time_stretch", _fake_time_stretch)
    monkeypatch.setattr(stretched_module, "CHUNK_SECONDS", 2.0)
    backend = StemPlaybackBackend(FakeRepo())
    backend.load(_track())
    backend.seek(1.0)

    backend.set_speed(2.0)
    _wait_for_speed(backend, 2.0)

    assert backend.position_seconds == pytest.approx(1.0, abs=1e-3)
    assert backend._mixer is not None
    assert backend._mixer.position_seconds == pytest.approx(0.5, abs=1e-3)
