from dataclasses import dataclass, field

import pytest

from ore_music_player.application.playback_service import PlaybackService
from ore_music_player.application.ports import PlaybackBackendError
from ore_music_player.domain.models import Track
from ore_music_player.domain.playback_state import PlaybackState, PlaybackStatus


@dataclass
class FakePlaybackBackend:
    calls: list[tuple] = field(default_factory=list)
    fail_seek: bool = False

    def load(self, track: Track) -> None:
        self.calls.append(("load", track.track_id))

    def play(self) -> None:
        self.calls.append(("play",))

    def pause(self) -> None:
        self.calls.append(("pause",))

    def stop(self) -> None:
        self.calls.append(("stop",))

    def seek(self, position: float) -> None:
        if self.fail_seek:
            raise PlaybackBackendError("seek failed")
        self.calls.append(("seek", position))

    def set_speed(self, speed: float) -> None:
        self.calls.append(("set_speed", speed))

    def set_volume(self, volume: float) -> None:
        self.calls.append(("set_volume", volume))

    def set_loop(
        self,
        start_seconds: float | None,
        end_seconds: float | None,
    ) -> None:
        self.calls.append(("set_loop", start_seconds, end_seconds))


def make_track(track_id: str = "track-001") -> Track:
    return Track(track_id=track_id, path=f"{track_id}.mp3", title=track_id)


def test_load_syncs_track_speed_and_clears_old_loop() -> None:
    state = PlaybackState().load_track("old-track")
    state = state.set_a(10.0).set_b(20.0).set_loop_enabled(True)
    backend = FakePlaybackBackend()
    service = PlaybackService(backend, state)

    result = service.load(make_track("new-track"))

    assert result.track_id == "new-track"
    assert result.status is PlaybackStatus.STOPPED
    assert result.loop_enabled is False
    assert backend.calls == [
        ("load", "new-track"),
        ("set_speed", 1.0),
        ("set_volume", 100.0),
        ("set_loop", None, None),
    ]


def test_pause_does_not_call_backend_when_stopped() -> None:
    backend = FakePlaybackBackend()
    service = PlaybackService(backend)

    result = service.pause()

    assert result.status is PlaybackStatus.STOPPED
    assert backend.calls == []


def test_play_pause_stop_are_forwarded_after_loading() -> None:
    backend = FakePlaybackBackend()
    service = PlaybackService(backend)
    service.load(make_track())

    service.play()
    service.pause()
    service.stop()

    assert backend.calls == [
        ("load", "track-001"),
        ("set_speed", 1.0),
        ("set_volume", 100.0),
        ("set_loop", None, None),
        ("play",),
        ("pause",),
        ("stop",),
    ]


def test_seek_and_speed_are_forwarded() -> None:
    backend = FakePlaybackBackend()
    service = PlaybackService(backend)
    service.load(make_track())

    service.seek(12.5)
    service.set_speed("0.75")

    assert ("seek", 12.5) in backend.calls
    assert ("set_speed", 0.75) in backend.calls
    assert service.state.position_seconds == 12.5
    assert service.state.speed == 0.75


def test_seek_does_not_update_state_when_backend_fails() -> None:
    backend = FakePlaybackBackend(fail_seek=True)
    service = PlaybackService(backend, PlaybackState().load_track("track-001"))

    with pytest.raises(PlaybackBackendError):
        service.seek(12.5)

    assert service.state.position_seconds == 0.0


def test_volume_is_stored_in_state_and_forwarded() -> None:
    backend = FakePlaybackBackend()
    service = PlaybackService(backend)

    service.set_volume("42")

    assert service.state.volume == 42
    assert backend.calls == [("set_volume", 42.0)]


def test_loop_points_are_synchronized_with_backend() -> None:
    backend = FakePlaybackBackend()
    service = PlaybackService(backend)
    service.load(make_track())

    service.set_a(10.0)
    service.set_b(20.0)
    service.enable_loop()
    service.disable_loop()

    assert backend.calls[-4:] == [
        ("set_loop", None, None),
        ("set_loop", None, None),
        ("set_loop", 10.0, 20.0),
        ("set_loop", None, None),
    ]
    assert service.state.loop_enabled is False
