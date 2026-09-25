import sys
from types import SimpleNamespace

import pytest

from ore_music_player.application.ports import PlaybackBackendError
from ore_music_player.domain.models import Track
from ore_music_player.infrastructure.audio.playback_backend import (
    LibMpvPlaybackBackend,
)


class FakeMpvPlayer:
    def __init__(self, **_) -> None:
        self.play_calls: list[str] = []
        self.seek_calls: list[float] = []
        self.stop_calls = 0
        self._time_pos = 0.0
        self.duration = None
        self.pause = False
        self.eof_reached = False
        self.fail_seek = False
        self.fail_seek_once = False
        self.fail_position = False

    @property
    def time_pos(self) -> float:
        if self.fail_position:
            raise SystemError("Error reading mpv property")
        return self._time_pos

    @time_pos.setter
    def time_pos(self, value: float) -> None:
        self._time_pos = value

    def stop(self) -> None:
        self.stop_calls += 1

    def play(self, path: str) -> None:
        self.play_calls.append(path)

    def wait_until_playing(self, timeout: float | None = None) -> None:
        self.eof_reached = False

    def seek(self, position: float, reference: str) -> None:
        if self.fail_seek or self.fail_seek_once:
            self.fail_seek_once = False
            raise SystemError("Error running mpv command", -12)
        self.seek_calls.append(position)
        self.time_pos = position


def test_load_pauses_track_until_play_is_requested(
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
    assert player.pause is True


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


def test_seek_translates_mpv_command_error(
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
    player.fail_seek = True

    with pytest.raises(PlaybackBackendError):
        backend.seek(10.0)


def test_seek_reloads_track_after_eof_command_error(
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
    player.eof_reached = True
    player.fail_seek_once = True

    backend.seek(10.0)

    assert player.play_calls == [str(track_path), str(track_path)]
    assert player.seek_calls == [10.0]
    assert player.pause is True


def test_properties_keep_last_values_when_mpv_temporarily_fails(
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
    backend.load(Track("track-001", str(track_path), "Song", 120.0))
    player.time_pos = 12.5
    player.duration = 120.0

    assert backend.position_seconds == 12.5
    assert backend.duration_seconds == 120.0

    player.fail_position = True
    player.duration = object()

    assert backend.position_seconds == 12.5
    assert backend.duration_seconds == 120.0


def test_position_reports_duration_when_mpv_reaches_eof(
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
    backend.load(Track("track-001", str(track_path), "Song", 120.0))
    player.time_pos = 119.9
    player.duration = 120.0
    assert backend.position_seconds == 119.9

    player.eof_reached = True
    player.time_pos = None

    assert backend.position_seconds == 120.0
