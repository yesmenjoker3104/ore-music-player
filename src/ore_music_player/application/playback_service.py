from __future__ import annotations

from decimal import Decimal

from ore_music_player.application.ports import PlaybackBackend
from ore_music_player.domain.models import Track
from ore_music_player.domain.playback_state import PlaybackState


class PlaybackService:
    def __init__(
        self,
        backend: PlaybackBackend,
        state: PlaybackState | None = None
    ) -> None:
        self.backend = backend
        self.state = state or PlaybackState()

    def load(self, track: Track) -> PlaybackState:
        self.backend.load(track)
        self.state = self.state.load_track(track.track_id)
        self.backend.set_speed(float(self.state.speed))
        self._sync_loop()
        return self.state

    def play(self) -> PlaybackState:
        self.state = self.state.play()
        self.backend.play()
        return self.state

    def pause(self) -> PlaybackState:
        next_state = self.state.pause()
        if next_state is not self.state:
            self.backend.pause()
        self.state = next_state
        return self.state

    def stop(self) -> PlaybackState:
        self.backend.stop()
        self.state = self.state.stop()
        return self.state

    def seek(self, position_seconds: float) -> PlaybackState:
        self.state = self.state.set_position(position_seconds)
        self.backend.seek(self.state.position_seconds)
        return self.state

    def set_speed(
        self,
        speed: Decimal | float | int | str,
    ) -> PlaybackState:
        self.state = self.state.set_speed(speed)
        self.backend.set_speed(float(self.state.speed))
        return self.state

    def set_a(
        self,
        position_seconds: float,
    ) -> PlaybackState:
        self.state = self.state.set_a(position_seconds)
        self._sync_loop()
        return self.state

    def set_b(
        self,
        position_seconds: float,
    ) -> PlaybackState:
        self.state = self.state.set_b(position_seconds)
        self._sync_loop()
        return self.state

    def enable_loop(self) -> PlaybackState:
        self.state = self.state.set_loop_enabled(True)
        region = self.state.loop_region
        if region is not None:
            self.backend.set_loop(region.start_seconds, region.end_seconds)
        return self.state

    def disable_loop(self) -> PlaybackState:
        self.state = self.state.set_loop_enabled(False)
        self._sync_loop()
        return self.state

    def clear_loop(self) -> PlaybackState:
        self.state = self.state.clear_loop_points()
        self._sync_loop()
        return self.state

    def _sync_loop(self) -> None:
        region = self.state.loop_region if self.state.loop_enabled else None
        if region is None:
            self.backend.set_loop(None, None)
        else:
            self.backend.set_loop(region.start_seconds, region.end_seconds)