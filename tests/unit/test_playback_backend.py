import sys
from types import SimpleNamespace

from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.audio.playback_backend import (
    LibMpvPlaybackBackend,
)


class FakeMpvPlayer:
    def __init__(self, **_) -> None:
        self.play_calls: list[str] = []
        self.seek_calls: list[float] = []
        self.stop_calls = 0
        self.time_pos = 0.0
        self.pause = False

    def stop(self) -> None:
        self.stop_calls += 1

    def play(self, path: str) -> None:
        self.play_calls.append(path)

    def seek(self, position: float, reference: str) -> None:
        self.seek_calls.append(position)
        self.time_pos = position


def test_load_starts_track_immediately(
    monkeypatch,
    tmp_path,
) -> None:
    player = FakeMpvPlayer()
    monkeypatch.setitem(
        sys.modules,
        "mpv",
        SimpleNamespace(MPV=lambda **kwargs: player),
    )
    track_path = tmp_path / "song.mp3"
    track_path.touch()

    backend = LibMpvPlaybackBackend()
    backend.load(Track("track-001", str(track_path), "Song"))

    assert player.stop_calls == 1
    assert player.play_calls == [str(track_path)]
    assert player.pause is False

def test_play_reloads_track_after_stop(
    monkeypatch,
    tmp_path,
) -> None:
    player = FakeMpvPlayer()
    monkeypatch.setitem(
        sys.modules,
        "mpv",
        SimpleNamespace(MPV=lambda **kwargs: player),
    )
    track_path = tmp_path / "song.mp3"
    track_path.touch()

    backend = LibMpvPlaybackBackend()
    backend.load(Track("track-001", str(track_path), "Song"))
    backend.stop()
    backend.play()

    assert player.play_calls == [str(track_path), str(track_path)]
    assert player.pause is False


def test_set_loop_returns_to_start_when_current_position_passed_end(
    monkeypatch,
    tmp_path,
) -> None:
    player = FakeMpvPlayer()
    monkeypatch.setitem(
        sys.modules,
        "mpv",
        SimpleNamespace(MPV=lambda **kwargs: player),
    )
    track_path = tmp_path / "song.mp3"
    track_path.touch()

    backend = LibMpvPlaybackBackend()
    backend.load(Track("track-001", str(track_path), "Song"))
    player.time_pos = 20.0
    backend.set_loop(10.0, 15.0)

    assert player.seek_calls == [10.0]
